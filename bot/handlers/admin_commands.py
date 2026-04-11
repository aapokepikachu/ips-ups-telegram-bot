"""
Admin-only command handlers.

/broadcast, /inedit, /db, /users, /current, /thumbnail, /caption, /helpa
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import Forbidden
from telegram.ext import ContextTypes

from bot.config import settings
from bot.utils.helpers import format_size, utcnow

logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID


# ------------------------------------------------------------------
# /broadcast
# ------------------------------------------------------------------
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward a replied message to all non-blocked users."""
    if not _is_admin(update.effective_user.id):
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text(
            "📡 **Broadcast Usage:**\n"
            "Reply to a message (text, photo, file, etc.) with /broadcast\n"
            "The message will be copied to all active users.",
            parse_mode="Markdown",
        )
        return

    db = context.bot_data["db"]
    users = await db.get_broadcast_users()
    total = len(users)

    status_msg = await update.message.reply_text(
        f"📡 Broadcasting to **{total}** users...", parse_mode="Markdown"
    )

    success = 0
    failed = 0
    blocked = 0

    for i, user_doc in enumerate(users):
        uid = user_doc["user_id"]
        try:
            await reply.copy(chat_id=uid)
            success += 1
        except Forbidden:
            blocked += 1
            await db.mark_user_blocked(uid)
        except Exception:
            failed += 1

        # Progress every 25 users
        if (i + 1) % 25 == 0:
            try:
                await status_msg.edit_text(
                    f"📡 Broadcasting... {i + 1}/{total}",
                )
            except Exception:
                pass

    await status_msg.edit_text(
        f"📡 **Broadcast complete!**\n\n"
        f"✅ Delivered: **{success}**\n"
        f"❌ Failed: **{failed}**\n"
        f"🚫 Blocked: **{blocked}**\n"
        f"📊 Total: **{total}**",
        parse_mode="Markdown",
    )
    logger.info(
        "Broadcast: delivered=%d, failed=%d, blocked=%d, total=%d",
        success, failed, blocked, total,
    )


# ------------------------------------------------------------------
# /inedit — ROM management entry point
# ------------------------------------------------------------------
async def inedit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the ROM management menu."""
    if not _is_admin(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("➕ Add ROM", callback_data="inedit_add")],
        [InlineKeyboardButton("➖ Remove ROM", callback_data="inedit_remove")],
        [InlineKeyboardButton("📋 List ROMs", callback_data="inedit_list")],
    ]
    await update.message.reply_text(
        "🎮 **ROM Management**\n\nSelect an action:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /db
# ------------------------------------------------------------------
async def db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show database statistics."""
    if not _is_admin(update.effective_user.id):
        return

    db = context.bot_data["db"]
    try:
        stats = await db.get_db_stats()

        data_size = stats.get("dataSize", 0)
        storage_size = stats.get("storageSize", 0)
        collections = stats.get("collections", 0)
        objects = stats.get("objects", 0)
        indexes = stats.get("indexes", 0)
        index_size = stats.get("indexSize", 0)

        # MongoDB Atlas free tier is 512 MB
        free_limit = 512 * 1024 * 1024
        used_pct = (storage_size / free_limit * 100) if free_limit else 0
        remaining = max(0, free_limit - storage_size)

        await update.message.reply_text(
            f"🗄 **Database Stats**\n\n"
            f"📊 Database: `{settings.DB_NAME}`\n"
            f"📁 Collections: {collections}\n"
            f"📄 Documents: {objects}\n"
            f"📏 Data size: {format_size(data_size)}\n"
            f"💾 Storage: {format_size(storage_size)}\n"
            f"🔑 Indexes: {indexes} ({format_size(index_size)})\n\n"
            f"**Free tier (512 MB):**\n"
            f"Used: {used_pct:.1f}%\n"
            f"Remaining: ~{format_size(remaining)}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Failed to get DB stats:\n`{exc}`", parse_mode="Markdown")


# ------------------------------------------------------------------
# /users
# ------------------------------------------------------------------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics."""
    if not _is_admin(update.effective_user.id):
        return

    db = context.bot_data["db"]
    stats = await db.get_user_stats()

    await update.message.reply_text(
        f"👥 **User Statistics**\n\n"
        f"📊 Total users: **{stats['total']}**\n"
        f"✅ Active (non-blocked): **{stats['active']}**\n"
        f"🚫 Blocked: **{stats['blocked']}**\n"
        f"📅 Active (7 days): **{stats['active_7d']}**\n"
        f"🕐 Recent (24 hours): **{stats['recent_24h']}**",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /current
# ------------------------------------------------------------------
async def current_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show active job and queue."""
    if not _is_admin(update.effective_user.id):
        return

    queue_mgr = context.bot_data["queue"]
    active = queue_mgr.get_active_job()
    pending = queue_mgr.get_pending_jobs()

    lines = ["⚙️ **Current Queue Status**\n"]

    if active:
        lines.append(
            f"🔧 **Active:** user `{active.user_id}` — "
            f"{active.patch_type} → {active.rom_name}"
        )
    else:
        lines.append("🔧 **Active:** None")

    lines.append(f"\n⏳ **Queued:** {len(pending)}")
    for i, job in enumerate(pending):
        lines.append(f"  {i + 1}. user `{job.user_id}` — {job.rom_name}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /thumbnail
# ------------------------------------------------------------------
async def thumbnail_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the thumbnail for outgoing patched files."""
    if not _is_admin(update.effective_user.id):
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text(
            "🖼 **Thumbnail Usage:**\n"
            "Reply to a photo or image file with /thumbnail\n"
            "That image will be used as the thumbnail for patched files.",
            parse_mode="Markdown",
        )
        return

    file_id = None
    if reply.photo:
        # Use the largest photo size
        file_id = reply.photo[-1].file_id
    elif reply.document and reply.document.mime_type and reply.document.mime_type.startswith("image/"):
        file_id = reply.document.file_id

    if not file_id:
        await update.message.reply_text("❌ Please reply to a **photo** or **image file**.", parse_mode="Markdown")
        return

    db = context.bot_data["db"]
    await db.set_setting("thumbnail_file_id", file_id)
    await update.message.reply_text("✅ Thumbnail updated!")
    logger.info("Thumbnail updated by admin")


# ------------------------------------------------------------------
# /caption
# ------------------------------------------------------------------
async def caption_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the caption template for outgoing files."""
    if not _is_admin(update.effective_user.id):
        return

    # Get template text from the message (after the command)
    text = update.message.text or ""
    parts = text.split(None, 1)
    if len(parts) < 2:
        db = context.bot_data["db"]
        current = await db.get_setting("caption_template") or "(default)"
        await update.message.reply_text(
            f"✏️ **Caption Usage:**\n"
            f"`/caption <template>`\n\n"
            f"**Placeholders:**\n"
            f"• `{{filename}}` — output file name\n"
            f"• `{{filesize}}` — file size\n"
            f"• `{{user}}` — user display name\n"
            f"• `{{romname}}` — selected ROM name\n"
            f"• `{{patchtype}}` — IPS or UPS\n"
            f"• `{{time}}` — timestamp\n\n"
            f"**Current template:**\n`{current}`",
            parse_mode="Markdown",
        )
        return

    template = parts[1]
    db = context.bot_data["db"]
    await db.set_setting("caption_template", template)
    await update.message.reply_text(
        f"✅ Caption template updated!\n\n**Preview:**\n{template}",
        parse_mode="Markdown",
    )
    logger.info("Caption template updated by admin")


# ------------------------------------------------------------------
# /helpa — admin help
# ------------------------------------------------------------------
async def helpa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed admin command reference."""
    if not _is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "🔐 **Admin Commands**\n\n"
        "**`/broadcast`**\n"
        "Reply to any message → copies it to all active users.\n"
        "Shows delivery, failed, and blocked counts.\n\n"
        "**`/inedit`**\n"
        "Manage the ROM selection list.\n"
        "• Add ROM: sends name, then forward the ROM file\n"
        "• Remove ROM: select from the list\n"
        "• List: view all mapped ROMs\n\n"
        "**`/db`**\n"
        "Show MongoDB usage, storage, collection count.\n\n"
        "**`/users`**\n"
        "Show total, active, blocked, and recent user counts.\n\n"
        "**`/current`**\n"
        "Show active patching job, queue length, queued users.\n\n"
        "**`/thumbnail`**\n"
        "Reply to a photo → sets it as the file thumbnail.\n\n"
        "**`/caption <template>`**\n"
        "Set the caption for outgoing files.\n"
        "Placeholders: `{filename}`, `{filesize}`, `{user}`,\n"
        "`{romname}`, `{patchtype}`, `{time}`\n\n"
        "**`/helpa`**\n"
        "This help message.",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# Admin state handler (for /inedit add flow)
# ------------------------------------------------------------------
async def admin_state_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles text/document messages when the admin is in an inedit flow.
    Registered in a separate handler group so it doesn't block normal handlers.
    """
    if not update.message:
        return
    if not _is_admin(update.effective_user.id):
        return

    state = context.user_data.get("inedit_state")
    if not state:
        return

    db = context.bot_data["db"]

    if state == "awaiting_name":
        if not update.message.text:
            await update.message.reply_text("❌ Please send a text name for the ROM.")
            return

        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("❌ Name cannot be empty.")
            return

        context.user_data["inedit_pending_name"] = name
        context.user_data["inedit_state"] = "awaiting_file"
        await update.message.reply_text(
            f"📁 Now forward or send the `.gba` ROM file for **{name}** from the channel.\n\n"
            "Send /cancel to abort.",
            parse_mode="Markdown",
        )
        return

    if state == "awaiting_file":
        doc = update.message.document
        if not doc:
            await update.message.reply_text(
                "❌ Please send or forward a **file** (not text/photo).",
                parse_mode="Markdown",
            )
            return

        name = context.user_data.get("inedit_pending_name", "Unknown")
        await db.add_rom_mapping(
            name=name,
            file_id=doc.file_id,
            file_unique_id=doc.file_unique_id,
            file_name=doc.file_name or "rom.gba",
        )

        # Clear state
        context.user_data.pop("inedit_state", None)
        context.user_data.pop("inedit_pending_name", None)

        await update.message.reply_text(
            f"✅ ROM **{name}** added successfully!\n"
            f"📄 File: `{doc.file_name}`",
            parse_mode="Markdown",
        )
        logger.info("ROM mapping added: %s → %s", name, doc.file_name)
