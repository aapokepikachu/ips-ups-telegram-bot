"""
Patch flow — handles incoming patch file documents and starts the patching flow.
"""

from __future__ import annotations

import logging

from telegram import (
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.config import settings
from bot.patching.engine import detect_patch_type
from bot.utils.helpers import compute_patch_hash, format_size, user_display_name

logger = logging.getLogger(__name__)


def _main_keyboard(rom_name: str | None = None) -> InlineKeyboardMarkup:
    """Build the 3-button keyboard shown after patch detection."""
    if rom_name:
        rom_btn_text = f"✅ {rom_name}"
    else:
        rom_btn_text = "📂 Select Rom file"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(rom_btn_text, callback_data="select_rom")],
            [
                InlineKeyboardButton("▶️ Proceed patching", callback_data="proceed"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_flow"),
            ],
        ]
    )


async def process_patch_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    document: Document,
) -> None:
    """
    Core logic shared by the auto-detect document handler and ``/patch`` reply.

    Downloads the file, detects the patch type, stores session state,
    and sends the selection keyboard.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    db = context.bot_data["db"]

    # Register user
    await db.upsert_user(user)

    filename = document.file_name or "patch"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("ips", "ups"):
        return  # silently ignore non-patch files

    # Size check
    if document.file_size and document.file_size > settings.MAX_FILE_SIZE:
        await update.effective_message.reply_text(
            f"❌ File too large! Maximum allowed size is **{format_size(settings.MAX_FILE_SIZE)}**.",
            parse_mode="Markdown",
        )
        return

    # Check for existing session / active job
    queue_mgr = context.bot_data["queue"]
    if queue_mgr.get_position(user.id) is not None:
        await update.effective_message.reply_text(
            "⚠️ You already have an active or queued job.\n"
            "Use /cancel to cancel it before starting a new one."
        )
        return

    # Download patch to detect type and compute hash
    try:
        tg_file = await context.bot.get_file(document.file_id)
        patch_data = bytes(await tg_file.download_as_bytearray())
    except Exception as exc:
        logger.error("Failed to download patch file: %s", exc)
        await update.effective_message.reply_text("❌ Failed to download the patch file. Please try again.")
        return

    # Detect patch type
    try:
        patch_type = detect_patch_type(patch_data)
    except ValueError as exc:
        await update.effective_message.reply_text(
            f"❌ **Invalid patch file**\n`{exc}`",
            parse_mode="Markdown",
        )
        return

    # Compute hash now, discard data to save memory
    patch_hash = compute_patch_hash(patch_data)
    del patch_data

    # Store session
    context.user_data["patch_session"] = {
        "patch_file_id": document.file_id,
        "patch_type": patch_type,
        "patch_hash": patch_hash,
        "rom_name": None,
        "rom_file_id": None,
        "filename": filename,
    }

    emoji = "📋" if patch_type == "IPS" else "📦"
    msg = await update.effective_message.reply_text(
        f"{emoji} **{patch_type} file detected**\n\n"
        f"📄 File: `{filename}`\n"
        f"📏 Size: {format_size(document.file_size or 0)}\n\n"
        "Select a ROM and press **Proceed patching**:",
        reply_markup=_main_keyboard(),
        parse_mode="Markdown",
    )

    # Store the message id so callbacks can edit it
    context.user_data["patch_session"]["menu_message_id"] = msg.message_id

    logger.info(
        "Patch session started: user=%d, type=%s, file=%s",
        user.id, patch_type, filename,
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    MessageHandler target for ``filters.Document.ALL``.
    Auto-detects ``.ips`` / ``.ups`` files and starts the patch flow.
    """
    if not update.message or not update.message.document:
        return

    # Skip if admin is in inedit flow (adding a ROM file)
    if context.user_data.get("inedit_state"):
        return

    await process_patch_document(update, context, update.message.document)
