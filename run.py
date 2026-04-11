"""
Entry point — configure logging and start the bot.
"""

import logging

from bot.config import settings
from bot.main import create_app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s | %(name)-28s | %(levelname)-7s | %(message)s",
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    )
    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Starting IPS/UPS Patcher Bot...")

    app = create_app()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
