"""
Callback query router — handles all inline-button presses.

Prefixes:
    select_rom      — show ROM list
    pick_rom:<name> — user picks a ROM
    proceed         — start patching
    cancel_flow     — cancel before patching starts
    cancel_job      — cancel during patching
    inedit_add      — admin: start add-ROM flow
    inedit_remove   — admin: show remove list
    inedit_list     — admin: list all ROMs
    inedit_del:<n>  — admin: confirm delete ROM
"""

from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.config import settings
from bot.services.queue_manager import DuplicateJobError, PatchJob
from bot.utils.helpers import user_display_name

logger = logging.getLogger(__name__)


def _main_keyboard(rom_name: str | None = None) -> InlineKeyboardMarkup:
    """Rebuild the main 3-button keyboard."""
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


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Central dispatcher for all callback queries."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data

    # ---- ROM selection flow ----
    if data == "select_rom":
        await _show_rom_list(update, context)
    elif data.startswith("pick_rom:"):
        await _pick_rom(update, context)
    elif data == "proceed":
        await _proceed(update, context)
    elif data == "cancel_flow":
        await _cancel_flow(update, context)
    elif data == "cancel_job":
        await _cancel_job(update, context)
    elif data == "back_to_main":
        await _back_to_main(update, context)

    # ---- Admin /inedit callbacks ----
    elif data == "inedit_add":
        await _inedit_add(update, context)
    elif data == "inedit_remove":
        await _inedit_remove(update, context)
    elif data == "inedit_list":
        await _inedit_list(update, context)
    elif data.startswith("inedit_del:"):
        await _inedit_delete(update, context)
    elif data == "inedit_back":
        await _inedit_back(update, context)
    else:
        await query.answer("Unknown action", show_alert=False)


# ===================================================================
# ROM selection
# ===================================================================

async def _show_rom_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available ROMs as inline buttons."""
    query = update.callback_query
    await query.answer()

    db = context.bot_data["db"]
    roms = await db.get_rom_mappings()

    if not roms:
        await query.answer("No ROMs configured yet. Ask the admin to add ROMs.", show_alert=True)
        return

    keyboard = []
    for rom in roms:
        keyboard.append(
            [InlineKeyboardButton(f"🎮 {rom['name']}", callback_data=f"pick_rom:{rom['name']}")]
        )
    keyboard.append([InlineKeyboardButton("« Back", callback_data="back_to_main")])

    session = context.user_data.get("patch_session", {})
    patch_type = session.get("patch_type", "?")
    filename = session.get("filename", "?")

    await query.edit_message_text(
        f"🎮 **Select a base ROM:**\n\n"
        f"Patch: `{filename}` ({patch_type})",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def _pick_rom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User selected a specific ROM."""
    query = update.callback_query
    rom_name = query.data.split(":", 1)[1]

    db = context.bot_data["db"]
    rom = await db.get_rom_by_name(rom_name)

    if not rom:
        await query.answer("ROM not found. It may have been removed.", show_alert=True)
        return

    session = context.user_data.get("patch_session")
    if not session:
        await query.answer("Session expired. Please send the patch file again.", show_alert=True)
        return

    # Store ROM selection
    session["rom_name"] = rom["name"]
    session["rom_file_id"] = rom["file_id"]

    await query.answer(f"Selected: {rom_name}")

    # Update the main message with the new button text
    patch_type = session.get("patch_type", "?")
    filename = session.get("filename", "?")

    await query.edit_message_text(
        f"{'📋' if patch_type == 'IPS' else '📦'} **{patch_type} file detected**\n\n"
        f"📄 File: `{filename}`\n"
        f"✅ ROM: **{rom_name}**\n\n"
        "Press **Proceed patching** to start!",
        reply_markup=_main_keyboard(rom_name),
        parse_mode="Markdown",
    )


# ===================================================================
# Proceed / Cancel
# ===================================================================

async def _proceed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Validate and enqueue the patching job."""
    query = update.callback_query

    session = context.user_data.get("patch_session")
    if not session:
        await query.answer("Session expired. Please send the patch file again.", show_alert=True)
        return

    if not session.get("rom_name") or not session.get("rom_file_id"):
        await query.answer(
            'Select a ROM file from the "Select Rom file" button',
            show_alert=True,
        )
        return

    await query.answer("Starting...")

    queue_mgr = context.bot_data["queue"]
    user = update.effective_user

    # Edit message to show queue status
    await query.edit_message_text(
        "⏳ **Adding to queue...**",
        parse_mode="Markdown",
    )

    job = PatchJob(
        user_id=user.id,
        chat_id=update.effective_chat.id,
        status_message_id=query.message.message_id,
        patch_file_id=session["patch_file_id"],
        patch_type=session["patch_type"],
        patch_hash=session["patch_hash"],
        rom_name=session["rom_name"],
        rom_file_id=session["rom_file_id"],
        patch_filename=session["filename"],
        user_display=user_display_name(user),
    )

    try:
        position = await queue_mgr.enqueue(job)
    except DuplicateJobError as exc:
        await query.edit_message_text(f"⚠️ {exc}")
        return
    except Exception as exc:
        logger.error("Failed to enqueue job: %s", exc)
        await query.edit_message_text("❌ Queue is full. Please try again later.")
        return

    # Clear session (job is now managed by the queue)
    context.user_data.pop("patch_session", None)

    if position <= 1:
        # Will start processing immediately
        pass  # The worker will update the message
    else:
        await query.edit_message_text(
            f"⏳ **You are in queue**\n"
            f"Position: **{position}** / {queue_mgr.get_queue_length()}\n\n"
            "Please wait...",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_job")]]
            ),
        )

    logger.info("Job enqueued: user=%d, position=%d", user.id, position)


async def _back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main patch session view from the ROM list."""
    query = update.callback_query
    await query.answer()

    session = context.user_data.get("patch_session")
    if not session:
        await query.answer("Session expired. Please send the patch file again.", show_alert=True)
        return

    patch_type = session.get("patch_type", "?")
    filename = session.get("filename", "?")
    rom_name = session.get("rom_name")

    emoji = "📋" if patch_type == "IPS" else "📦"
    rom_line = f"\n✅ ROM: **{rom_name}**" if rom_name else ""

    await query.edit_message_text(
        f"{emoji} **{patch_type} file detected**\n\n"
        f"📄 File: `{filename}`{rom_line}\n\n"
        "Select a ROM and press **Proceed patching**:",
        reply_markup=_main_keyboard(rom_name),
        parse_mode="Markdown",
    )


async def _cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel the patch flow before patching starts."""
    query = update.callback_query
    await query.answer("Cancelled")

    context.user_data.pop("patch_session", None)

    try:
        await query.delete_message()
    except Exception:
        await query.edit_message_text("❌ The process canceled")


async def _cancel_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel an active or queued patching job."""
    query = update.callback_query

    queue_mgr = context.bot_data["queue"]
    cancelled = await queue_mgr.cancel_job(update.effective_user.id)

    if cancelled:
        await query.answer("Job cancelled", show_alert=False)
        # The queue worker will handle message cleanup
    else:
        await query.answer("No active job to cancel", show_alert=True)


# ===================================================================
# Admin /inedit callbacks
# ===================================================================

async def _inedit_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the add-ROM flow."""
    query = update.callback_query
    if not query.from_user or query.from_user.id != settings.ADMIN_ID:
        await query.answer("Admin only", show_alert=True)
        return

    await query.answer()
    context.user_data["inedit_state"] = "awaiting_name"

    await query.edit_message_text(
        "📝 **Add ROM**\n\n"
        "Send me the display name for this ROM\n"
        "(e.g., `FireRed v1.0`, `Emerald`)\n\n"
        "Send /cancel to abort.",
        parse_mode="Markdown",
    )


async def _inedit_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show ROM list with delete buttons."""
    query = update.callback_query
    if not query.from_user or query.from_user.id != settings.ADMIN_ID:
        await query.answer("Admin only", show_alert=True)
        return

    await query.answer()
    db = context.bot_data["db"]
    roms = await db.get_rom_mappings()

    if not roms:
        await query.edit_message_text("📭 No ROMs configured.")
        return

    keyboard = []
    for rom in roms:
        keyboard.append(
            [InlineKeyboardButton(f"🗑 {rom['name']}", callback_data=f"inedit_del:{rom['name']}")]
        )
    keyboard.append([InlineKeyboardButton("« Back", callback_data="inedit_back")])

    await query.edit_message_text(
        "➖ **Remove a ROM:**\n\nTap to delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def _inedit_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all ROM mappings."""
    query = update.callback_query
    if not query.from_user or query.from_user.id != settings.ADMIN_ID:
        await query.answer("Admin only", show_alert=True)
        return

    await query.answer()
    db = context.bot_data["db"]
    roms = await db.get_rom_mappings()

    if not roms:
        await query.edit_message_text("📭 No ROMs configured.")
        return

    lines = ["📋 **Configured ROMs:**\n"]
    for i, rom in enumerate(roms, 1):
        lines.append(f"{i}. **{rom['name']}** — `{rom.get('file_name', 'N/A')}`")

    keyboard = [[InlineKeyboardButton("« Back", callback_data="inedit_back")]]

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def _inedit_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a ROM mapping."""
    query = update.callback_query
    if not query.from_user or query.from_user.id != settings.ADMIN_ID:
        await query.answer("Admin only", show_alert=True)
        return

    rom_name = query.data.split(":", 1)[1]
    db = context.bot_data["db"]
    removed = await db.remove_rom_mapping(rom_name)

    if removed:
        await query.answer(f"Removed: {rom_name}")
        logger.info("ROM mapping removed: %s", rom_name)
        # Refresh the remove list
        await _inedit_remove(update, context)
    else:
        await query.answer("ROM not found", show_alert=True)


async def _inedit_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the /inedit main menu."""
    query = update.callback_query
    if not query.from_user or query.from_user.id != settings.ADMIN_ID:
        await query.answer("Admin only", show_alert=True)
        return

    await query.answer()
    keyboard = [
        [InlineKeyboardButton("➕ Add ROM", callback_data="inedit_add")],
        [InlineKeyboardButton("➖ Remove ROM", callback_data="inedit_remove")],
        [InlineKeyboardButton("📋 List ROMs", callback_data="inedit_list")],
    ]
    await query.edit_message_text(
        "🎮 **ROM Management**\n\nSelect an action:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
