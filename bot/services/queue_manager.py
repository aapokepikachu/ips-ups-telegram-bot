"""
Async job queue — processes one patch job at a time.

Uses an ``asyncio.Queue`` backed by a tracking list so we can
iterate queued jobs to update their position messages.

Job states:
    received → queued → downloading_rom → downloading_patch →
    patching → uploading → completed | failed | cancelled
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, TimedOut

from bot.config import settings
from bot.database import Database
from bot.patching.engine import apply_patch, PatchError
from bot.services.progress import render_progress
from bot.utils.constants import (
    DEFAULT_CAPTION,
    FILE_DOWNLOAD_TIMEOUT,
    FILE_UPLOAD_TIMEOUT,
)
from bot.utils.helpers import (
    compute_cache_key,
    format_size,
    utcnow,
)

logger = logging.getLogger(__name__)

# Timeout constants (seconds)
_DL_TIMEOUT = FILE_DOWNLOAD_TIMEOUT
_UL_TIMEOUT = FILE_UPLOAD_TIMEOUT


class DuplicateJobError(Exception):
    """User already has an active or queued job."""


@dataclass
class PatchJob:
    """All state needed to execute a single patch job."""

    user_id: int
    chat_id: int
    status_message_id: int
    patch_file_id: str
    patch_type: str
    patch_hash: str
    rom_name: str
    rom_file_id: str
    patch_filename: str
    user_display: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    position: int = 0


class QueueManager:
    """Single-worker job queue with position tracking and cancellation."""

    def __init__(self, max_size: int, bot: Bot, db: Database) -> None:
        self._queue: asyncio.Queue[PatchJob] = asyncio.Queue(maxsize=max_size)
        self._pending: list[PatchJob] = []  # mirrors queue for iteration
        self._active: Optional[PatchJob] = None
        self._user_jobs: dict[int, PatchJob] = {}
        self._lock = asyncio.Lock()
        self._bot = bot
        self._db = db
        self._worker_task: Optional[asyncio.Task] = None
        self._last_edit: float = 0  # throttle edits

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        self._worker_task = asyncio.create_task(self._worker(), name="queue-worker")
        logger.info("Queue worker started (max_size=%d)", self._queue.maxsize)

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Queue worker stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def enqueue(self, job: PatchJob) -> int:
        """
        Add a job to the queue.  Returns the 1-based queue position.
        Raises ``DuplicateJobError`` if the user already has a job.
        """
        async with self._lock:
            if job.user_id in self._user_jobs:
                raise DuplicateJobError(
                    "You already have an active or queued job. "
                    "Use /cancel to cancel it first."
                )
            self._pending.append(job)
            job.position = len(self._pending)
            self._user_jobs[job.user_id] = job

        await self._queue.put(job)
        await self._db.create_job(
            user_id=job.user_id,
            patch_hash=job.patch_hash,
            rom_name=job.rom_name,
            patch_type=job.patch_type,
        )
        logger.info(
            "Job enqueued for user %d, position %d", job.user_id, job.position
        )
        return job.position

    async def cancel_job(self, user_id: int) -> bool:
        """Cancel a user's active or queued job. Returns True if found."""
        async with self._lock:
            job = self._user_jobs.get(user_id)
            if not job:
                return False
            job.cancel_event.set()
            # Remove from pending if still queued
            if job in self._pending:
                self._pending.remove(job)
            self._user_jobs.pop(user_id, None)

        await self._db.update_job_status(user_id, "cancelled")
        logger.info("Job cancelled for user %d", user_id)
        return True

    def get_position(self, user_id: int) -> Optional[int]:
        """Return 1-based queue position, 0 if active, None if not found."""
        if self._active and self._active.user_id == user_id:
            return 0
        for i, job in enumerate(self._pending):
            if job.user_id == user_id:
                return i + 1
        return None

    def get_queue_length(self) -> int:
        return len(self._pending)

    def get_active_job(self) -> Optional[PatchJob]:
        return self._active

    def get_pending_jobs(self) -> list[PatchJob]:
        return list(self._pending)

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------
    async def _worker(self) -> None:
        """Continuously pull jobs from the queue and process them."""
        while True:
            job = await self._queue.get()

            async with self._lock:
                if job in self._pending:
                    self._pending.remove(job)
                self._active = job

            try:
                if job.cancel_event.is_set():
                    await self._send_cancelled(job)
                    continue

                await self._db.update_job_status(job.user_id, "processing")
                await self._process_job(job)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Job failed for user %d: %s", job.user_id, exc)
                await self._db.update_job_status(job.user_id, "failed")
                await self._safe_edit(
                    job.chat_id,
                    job.status_message_id,
                    f"❌ **Patching failed:**\n`{exc}`",
                    parse_mode="Markdown",
                )
            finally:
                async with self._lock:
                    self._active = None
                    self._user_jobs.pop(job.user_id, None)
                self._queue.task_done()
                await self._update_positions()

    async def _process_job(self, job: PatchJob) -> None:
        """Execute a single patching job with explicit state transitions."""
        cancel_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_job")]]
        )
        cache_key = compute_cache_key(job.patch_hash, job.rom_file_id)

        # ---- State: CHECKING CACHE ----
        await self._progress(job, "🔍 Checking cache...", 5, cancel_kb)
        cached = await self._db.find_cache(cache_key)
        if cached:
            if job.cancel_event.is_set():
                await self._send_cancelled(job)
                return
            await self._progress(job, "✅ Cache hit! Sending file...", 90, cancel_kb)
            await self._send_cached(job, cached["output_file_id"])
            await self._db.update_job_status(job.user_id, "completed")
            return

        # Mark cache as in-progress to block concurrent duplicates
        await self._db.mark_cache_in_progress(cache_key, job.user_id)

        try:
            # ---- State: DOWNLOADING ROM ----
            if job.cancel_event.is_set():
                await self._send_cancelled(job)
                return
            await self._db.update_job_status(job.user_id, "downloading_rom")
            await self._progress(job, "📥 Downloading ROM...", 15, cancel_kb)
            try:
                rom_file = await self._bot.get_file(
                    job.rom_file_id,
                    read_timeout=_DL_TIMEOUT,
                )
                rom_data = bytes(await rom_file.download_as_bytearray())
            except TimedOut as exc:
                raise PatchError(
                    f"ROM download timed out ({_DL_TIMEOUT}s). "
                    "The file may be too large for standard Bot API. "
                    "Ask the admin to set up a local Bot API server."
                ) from exc
            except Exception as exc:
                raise PatchError(f"Failed to download ROM: {exc}") from exc

            # ---- State: DOWNLOADING PATCH ----
            if job.cancel_event.is_set():
                await self._send_cancelled(job)
                return
            await self._db.update_job_status(job.user_id, "downloading_patch")
            await self._progress(job, "📥 Downloading patch...", 30, cancel_kb)
            try:
                patch_file = await self._bot.get_file(
                    job.patch_file_id,
                    read_timeout=_DL_TIMEOUT,
                )
                patch_data = bytes(await patch_file.download_as_bytearray())
            except TimedOut as exc:
                raise PatchError(
                    f"Patch download timed out ({_DL_TIMEOUT}s)."
                ) from exc
            except Exception as exc:
                raise PatchError(f"Failed to download patch: {exc}") from exc

            # ---- State: PATCHING ----
            if job.cancel_event.is_set():
                await self._send_cancelled(job)
                return
            await self._db.update_job_status(job.user_id, "patching")
            await self._progress(job, "🔧 Applying patch...", 50, cancel_kb)
            try:
                patched_data = await apply_patch(rom_data, patch_data, job.patch_type)
            except PatchError:
                raise
            except Exception as exc:
                raise PatchError(f"Patching error: {exc}") from exc

            # Free source data early
            del rom_data, patch_data

            # ---- State: UPLOADING ----
            if job.cancel_event.is_set():
                await self._send_cancelled(job)
                return
            await self._db.update_job_status(job.user_id, "uploading")
            await self._progress(job, "📤 Uploading patched file...", 75, cancel_kb)

            # Build output filename
            base_name = (
                job.patch_filename.rsplit(".", 1)[0]
                if "." in job.patch_filename
                else job.patch_filename
            )
            out_filename = f"{base_name}.gba"

            # Build caption
            caption_template = (
                await self._db.get_setting("caption_template") or DEFAULT_CAPTION
            )
            try:
                caption = caption_template.format(
                    filename=out_filename,
                    filesize=format_size(len(patched_data)),
                    user=job.user_display,
                    romname=job.rom_name,
                    patchtype=job.patch_type,
                    time=utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                )
            except (KeyError, IndexError):
                caption = f"📦 {out_filename}"

            # Get thumbnail
            thumb_io = await self._get_thumbnail()

            # Send patched file to user
            patched_io = BytesIO(patched_data)
            patched_io.name = out_filename

            try:
                sent_msg = await self._bot.send_document(
                    chat_id=job.chat_id,
                    document=patched_io,
                    filename=out_filename,
                    caption=caption,
                    parse_mode="Markdown",
                    thumbnail=thumb_io,
                    read_timeout=_UL_TIMEOUT,
                    write_timeout=_UL_TIMEOUT,
                )
            except TimedOut as exc:
                raise PatchError(
                    f"File upload timed out ({_UL_TIMEOUT}s). "
                    "The output may be too large for standard Bot API."
                ) from exc

            # ---- Stage: CACHING RESULT ----
            await self._progress(job, "💾 Caching result...", 95, cancel_kb)

            cache_file_id = None
            cache_msg_id = None
            try:
                cache_io = BytesIO(patched_data)
                cache_io.name = out_filename
                cache_msg = await self._bot.send_document(
                    chat_id=settings.CACHE_CHANNEL_ID,
                    document=cache_io,
                    filename=out_filename,
                    caption=f"Cache: {out_filename} | ROM: {job.rom_name} | {job.patch_type}",
                    read_timeout=_UL_TIMEOUT,
                    write_timeout=_UL_TIMEOUT,
                )
                cache_file_id = cache_msg.document.file_id
                cache_msg_id = cache_msg.message_id
            except Exception:
                logger.warning("Failed to upload to cache channel, continuing")

            if cache_file_id:
                await self._db.store_cache(
                    cache_key=cache_key,
                    output_file_id=cache_file_id,
                    output_message_id=cache_msg_id,
                    patch_hash=job.patch_hash,
                    rom_name=job.rom_name,
                    patch_type=job.patch_type,
                )
            else:
                # Clean up the in-progress marker if caching failed
                await self._db.clear_cache_in_progress(cache_key)

            del patched_data  # free memory

            # ---- COMPLETED ----
            await self._db.update_job_status(job.user_id, "completed")
            await self._safe_edit(
                job.chat_id,
                job.status_message_id,
                f"✅ **Patching complete!**\n\n"
                f"🎮 ROM: {job.rom_name}\n"
                f"🔧 Patch: {job.patch_type}\n"
                f"📄 File: `{out_filename}`",
                parse_mode="Markdown",
            )
            logger.info("Job completed for user %d", job.user_id)

        except Exception:
            # Clean up in-progress cache marker on any failure
            await self._db.clear_cache_in_progress(cache_key)
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _get_thumbnail(self) -> Optional[BytesIO]:
        """Download the admin-configured thumbnail, or None."""
        thumb_file_id = await self._db.get_setting("thumbnail_file_id")
        if not thumb_file_id:
            return None
        try:
            tf = await self._bot.get_file(
                thumb_file_id, read_timeout=_DL_TIMEOUT
            )
            thumb_bytes = await tf.download_as_bytearray()
            thumb_io = BytesIO(bytes(thumb_bytes))
            thumb_io.name = "thumb.jpg"
            return thumb_io
        except Exception:
            logger.warning("Failed to download thumbnail, skipping")
            return None

    async def _send_cached(self, job: PatchJob, file_id: str) -> None:
        """Forward a cached file to the user — with thumbnail."""
        caption_template = (
            await self._db.get_setting("caption_template") or DEFAULT_CAPTION
        )
        base_name = (
            job.patch_filename.rsplit(".", 1)[0]
            if "." in job.patch_filename
            else job.patch_filename
        )
        out_filename = f"{base_name}.gba"
        try:
            caption = caption_template.format(
                filename=out_filename,
                filesize="(cached)",
                user=job.user_display,
                romname=job.rom_name,
                patchtype=job.patch_type,
                time=utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            )
        except (KeyError, IndexError):
            caption = f"📦 {out_filename}"

        # Always send thumbnail on cache hit
        thumb_io = await self._get_thumbnail()

        await self._bot.send_document(
            chat_id=job.chat_id,
            document=file_id,
            caption=caption,
            parse_mode="Markdown",
            thumbnail=thumb_io,
            read_timeout=_UL_TIMEOUT,
            write_timeout=_UL_TIMEOUT,
        )
        await self._safe_edit(
            job.chat_id,
            job.status_message_id,
            "✅ **Patching complete!** _(cached)_\n\n"
            f"🎮 ROM: {job.rom_name}\n"
            f"🔧 Patch: {job.patch_type}",
            parse_mode="Markdown",
        )

    async def _send_cancelled(self, job: PatchJob) -> None:
        """Clean up after cancellation."""
        await self._db.update_job_status(job.user_id, "cancelled")
        try:
            await self._bot.delete_message(job.chat_id, job.status_message_id)
        except Exception:
            pass
        try:
            await self._bot.send_message(job.chat_id, "❌ The process canceled")
        except Exception:
            pass

    async def _progress(
        self,
        job: PatchJob,
        stage: str,
        percent: int,
        reply_markup=None,
    ) -> None:
        """Update the status message with a progress bar (throttled)."""
        now = time.monotonic()
        if now - self._last_edit < 1.5:
            return  # throttle to avoid Telegram rate limits
        self._last_edit = now
        bar = render_progress(percent)
        text = f"⚙️ **Patching in progress...**\n\n{stage}\n{bar}"
        await self._safe_edit(
            job.chat_id,
            job.status_message_id,
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def _update_positions(self) -> None:
        """Update the status messages of all queued (waiting) jobs."""
        async with self._lock:
            total = len(self._pending)
            for i, job in enumerate(self._pending):
                job.position = i + 1
                try:
                    await self._bot.edit_message_text(
                        chat_id=job.chat_id,
                        message_id=job.status_message_id,
                        text=(
                            f"⏳ **You are in queue**\n"
                            f"Position: **{i + 1}** / {total}\n\n"
                            "Please wait..."
                        ),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_job")]]
                        ),
                    )
                except (BadRequest, TimedOut):
                    pass
                except Exception:
                    logger.debug("Failed to update position for user %d", job.user_id)

    async def _safe_edit(self, chat_id, message_id, text, **kwargs) -> None:
        """Edit a message, swallowing 'message is not modified' errors."""
        try:
            await self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                **kwargs,
            )
        except BadRequest as exc:
            if "not modified" not in str(exc).lower():
                logger.warning("edit_message failed: %s", exc)
        except (Forbidden, TimedOut):
            pass
        except Exception:
            logger.debug("Unexpected error editing message", exc_info=True)
