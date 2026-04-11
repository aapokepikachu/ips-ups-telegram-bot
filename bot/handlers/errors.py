"""
Global error handler for the Telegram bot application.
"""

from __future__ import annotations

import html
import logging
import traceback

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Log the error and notify the user with a generic message.
    Telegram-internal errors are logged at WARNING; everything else at ERROR.
    """
    logger.error("Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An unexpected error occurred. Please try again later."
            )
        except Exception:
            pass  # best-effort
