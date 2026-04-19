"""
User-facing command handlers.

/start, /help, /about, /ping, /status, /queue, /cancel, /formats, /patch
"""

from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import settings
from bot.utils.helpers import user_display_name

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message and brief instructions."""
    db = context.bot_data["db"]
    await db.upsert_user(update.effective_user)

    await update.message.reply_text(
        "👋 **Welcome to the IPS/UPS/BPS ROM Patcher Bot!**\n\n"
        "I can apply `.ips`, `.ups`, and `.bps` patches to GBA ROM files.\n\n"
        "**How to use:**\n"
        "1️⃣ Send me a `.ips`, `.ups`, or `.bps` patch file\n"
        "2️⃣ Select the base ROM from the list\n"
        "3️⃣ Press **Proceed patching** and I'll send you the result!\n\n"
        "Use /help for detailed instructions.",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /help
# ------------------------------------------------------------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Full user command reference."""
    api_note = ""
    if settings.LOCAL_API_URL:
        api_note = "\n• Large file support enabled (local Bot API)\n"

    await update.message.reply_text(
        "📖 **Bot Help**\n\n"
        "**Patch Workflow:**\n"
        "• Send a `.ips`, `.ups`, or `.bps` patch file (max 50 MB)\n"
        "• I'll detect the format automatically\n"
        "• Tap **Select Rom file** to pick a base ROM\n"
        "• Tap **Proceed patching** to start\n"
        "• The patched `.gba` file will be sent to you\n\n"
        "**Commands:**\n"
        "/start — Welcome message\n"
        "/help — This help text\n"
        "/patch — Instructions on starting a patch\n"
        "/status — Check your current job status\n"
        "/queue — See the current queue\n"
        "/cancel — Cancel your active job\n"
        "/formats — Supported patch formats\n"
        "/about — About this bot\n"
        "/ping — Check bot latency\n\n"
        "**Notes:**\n"
        "• Only one job per user at a time\n"
        "• Previously patched combos are cached for speed\n"
        f"• You do NOT need to send the ROM — just the patch file{api_note}",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /about
# ------------------------------------------------------------------
async def about_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot information."""
    api_mode = "Local Bot API ✅" if settings.LOCAL_API_URL else "Standard Bot API"
    await update.message.reply_text(
        "ℹ️ **About This Bot**\n\n"
        "🔧 **Purpose:** Apply IPS/UPS/BPS patches to GBA ROMs\n"
        f"👤 **Owner:** {settings.OWNER_NAME}\n"
        f"🗄 **Database:** MongoDB (`{settings.DB_NAME}`)\n"
        f"🌐 **API Mode:** {api_mode}\n"
        "☁️ **Hosted on:** Render\n"
        "⚡ **Engine:** Pure-Python IPS, UPS & BPS patcher\n\n"
        "📂 [Source Code](https://github.com/aapokepikachu/ips-ups-telegram-bot)\n\n"
        "_Only for files you own or have permission to use._",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ------------------------------------------------------------------
# /ping
# ------------------------------------------------------------------
async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Measure and report bot latency."""
    start = time.monotonic()
    msg = await update.message.reply_text("🏓 Pong!")
    elapsed = (time.monotonic() - start) * 1000
    await msg.edit_text(f"🏓 **Pong!** `{elapsed:.0f} ms`", parse_mode="Markdown")


# ------------------------------------------------------------------
# /status
# ------------------------------------------------------------------
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's current job status."""
    queue_mgr = context.bot_data["queue"]
    pos = queue_mgr.get_position(update.effective_user.id)

    if pos is None:
        await update.message.reply_text("📭 You have no active job.")
    elif pos == 0:
        await update.message.reply_text("⚙️ Your job is currently **processing**.", parse_mode="Markdown")
    else:
        total = queue_mgr.get_queue_length()
        await update.message.reply_text(
            f"⏳ You are in queue\nPosition: **{pos}** / {total}",
            parse_mode="Markdown",
        )


# ------------------------------------------------------------------
# /queue
# ------------------------------------------------------------------
async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current queue info."""
    queue_mgr = context.bot_data["queue"]
    length = queue_mgr.get_queue_length()
    active = queue_mgr.get_active_job()

    lines = ["📊 **Queue Status**\n"]
    if active:
        lines.append(f"⚙️ Active job: user `{active.user_id}`")
    else:
        lines.append("⚙️ No active job")
    lines.append(f"⏳ Queued: **{length}**")
    lines.append(f"📦 Max queue size: {settings.MAX_QUEUE_SIZE}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /cancel
# ------------------------------------------------------------------
async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel user's active or queued job."""
    queue_mgr = context.bot_data["queue"]
    cancelled = await queue_mgr.cancel_job(update.effective_user.id)

    if cancelled:
        # Clear session
        context.user_data.pop("patch_session", None)
        await update.message.reply_text("❌ Your job has been cancelled.")
    else:
        # Maybe there's just a session without a queued job
        if context.user_data.pop("patch_session", None):
            await update.message.reply_text("❌ Patch session cleared.")
        else:
            await update.message.reply_text("📭 You have no active job to cancel.")


# ------------------------------------------------------------------
# /formats
# ------------------------------------------------------------------
async def formats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain supported patch formats."""
    await update.message.reply_text(
        "📋 **Supported Patch Formats**\n\n"
        "**IPS** (International Patching System)\n"
        "• Extension: `.ips`\n"
        "• Header: `PATCH`\n"
        "• Max ROM size: 16 MB\n"
        "• Simple offset-based patching\n\n"
        "**UPS** (Universal Patching System)\n"
        "• Extension: `.ups`\n"
        "• Header: `UPS1`\n"
        "• No size limit\n"
        "• XOR-based with CRC-32 verification\n\n"
        "**BPS** (Beat Patching System)\n"
        "• Extension: `.bps`\n"
        "• Header: `BPS1`\n"
        "• No size limit\n"
        "• 4 action types with CRC-32 verification\n"
        "• Most advanced format, preferred for modern hacks\n\n"
        "_All formats are applied to GBA (.gba) ROM files._",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /patch
# ------------------------------------------------------------------
async def patch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    If used as a reply to a patch file, start the flow.
    Otherwise, show instructions.
    """
    reply = update.message.reply_to_message

    if reply and reply.document:
        filename = reply.document.file_name or ""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in ("ips", "ups", "bps"):
            # Defer to the document handler logic
            from bot.handlers.patch_flow import process_patch_document
            await process_patch_document(update, context, reply.document)
            return

    await update.message.reply_text(
        "📋 **How to patch:**\n\n"
        "1. Send me a `.ips`, `.ups`, or `.bps` file\n"
        "2. I'll detect the format automatically\n"
        "3. Or reply to a patch file with /patch\n\n"
        "_You don't need to send the ROM — just the patch file!_",
        parse_mode="Markdown",
    )
