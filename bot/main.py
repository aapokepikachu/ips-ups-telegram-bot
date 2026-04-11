"""
Application factory — builds and configures the Telegram bot application.
"""

from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import settings
from bot.database import Database
from bot.handlers.admin_commands import (
    admin_state_handler,
    broadcast_cmd,
    caption_cmd,
    current_cmd,
    db_cmd,
    helpa_cmd,
    inedit_cmd,
    thumbnail_cmd,
    users_cmd,
)
from bot.handlers.callbacks import callback_router
from bot.handlers.errors import error_handler
from bot.handlers.patch_flow import handle_document
from bot.handlers.user_commands import (
    about_cmd,
    cancel_cmd,
    formats_cmd,
    help_cmd,
    patch_cmd,
    ping_cmd,
    queue_cmd,
    start_cmd,
    status_cmd,
)
from bot.services.queue_manager import QueueManager

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Health-check server (optional, for uptime monitors)
# ------------------------------------------------------------------
async def _health_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Minimal HTTP response for health checks."""
    try:
        await reader.read(1024)
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 2\r\n"
            "Connection: close\r\n"
            "\r\n"
            "OK"
        )
        writer.write(response.encode())
        await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


# ------------------------------------------------------------------
# Lifecycle hooks
# ------------------------------------------------------------------
async def post_init(app: Application) -> None:
    """Initialise database, queue worker, health server, and set bot commands."""
    # Database
    db = Database(settings.MONGO_URI, settings.DB_NAME)
    await db.init_indexes()
    app.bot_data["db"] = db

    # Queue
    queue_mgr = QueueManager(
        max_size=settings.MAX_QUEUE_SIZE,
        bot=app.bot,
        db=db,
    )
    await queue_mgr.start()
    app.bot_data["queue"] = queue_mgr

    # Health-check server
    if settings.PORT:
        server = await asyncio.start_server(
            _health_handler, "0.0.0.0", settings.PORT
        )
        app.bot_data["health_server"] = server
        logger.info("Health-check server listening on port %d", settings.PORT)

    # Set bot commands menu
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Welcome & instructions"),
                BotCommand("help", "Full command reference"),
                BotCommand("patch", "Start patching a file"),
                BotCommand("status", "Your current job status"),
                BotCommand("queue", "View the queue"),
                BotCommand("cancel", "Cancel your active job"),
                BotCommand("formats", "Supported patch formats"),
                BotCommand("about", "About this bot"),
                BotCommand("ping", "Check latency"),
            ]
        )
    except Exception:
        logger.warning("Failed to set bot commands menu")

    logger.info("Bot initialised ✓")


async def post_shutdown(app: Application) -> None:
    """Clean up resources."""
    # Stop queue
    queue_mgr = app.bot_data.get("queue")
    if queue_mgr:
        await queue_mgr.stop()

    # Close DB
    db = app.bot_data.get("db")
    if db:
        db.close()

    # Stop health server
    health_server = app.bot_data.get("health_server")
    if health_server:
        health_server.close()
        await health_server.wait_closed()

    logger.info("Bot shutdown complete ✓")


# ------------------------------------------------------------------
# Application factory
# ------------------------------------------------------------------
def create_app() -> Application:
    """Build the fully-configured Application instance."""
    app = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )

    # ---- Group 0: primary handlers ----

    # User commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("formats", formats_cmd))
    app.add_handler(CommandHandler("patch", patch_cmd))

    # Admin commands
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("inedit", inedit_cmd))
    app.add_handler(CommandHandler("db", db_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("current", current_cmd))
    app.add_handler(CommandHandler("thumbnail", thumbnail_cmd))
    app.add_handler(CommandHandler("caption", caption_cmd))
    app.add_handler(CommandHandler("helpa", helpa_cmd))

    # Document handler (auto-detect patch files)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Callback query handler (inline buttons)
    app.add_handler(CallbackQueryHandler(callback_router))

    # ---- Group 1: admin state handler (inedit add-ROM flow) ----
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND & ~filters.UpdateType.EDITED_MESSAGE,
            admin_state_handler,
        ),
        group=1,
    )

    # Error handler
    app.add_error_handler(error_handler)

    return app
