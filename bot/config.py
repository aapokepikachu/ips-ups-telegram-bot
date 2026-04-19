"""
Bot configuration — loads environment variables via python-dotenv.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    """Immutable application settings populated from environment variables."""

    BOT_TOKEN: str
    MONGO_URI: str
    DB_NAME: str
    ADMIN_ID: int
    CHANNEL_ID: int
    CACHE_CHANNEL_ID: int
    MAX_QUEUE_SIZE: int
    MAX_FILE_SIZE: int
    LOG_LEVEL: str
    OWNER_NAME: str
    PORT: Optional[int]
    LOCAL_API_URL: Optional[str]       # e.g. http://localhost:8081
    LOCAL_API_FILE_URL: Optional[str]  # e.g. http://localhost:8081/file


def load_settings() -> Settings:
    """
    Build a Settings instance from the environment.
    Raises ``RuntimeError`` for missing required vars.
    """
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    mongo_uri = os.environ.get("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI environment variable is required")

    admin_id = os.environ.get("ADMIN_ID")
    if not admin_id:
        raise RuntimeError("ADMIN_ID environment variable is required")

    channel_id = os.environ.get("CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("CHANNEL_ID environment variable is required")

    port_str = os.environ.get("PORT")
    local_api = os.environ.get("LOCAL_API_URL")

    return Settings(
        BOT_TOKEN=bot_token,
        MONGO_URI=mongo_uri,
        DB_NAME=os.getenv("DB_NAME", "ips_ups_bot"),
        ADMIN_ID=int(admin_id),
        CHANNEL_ID=int(channel_id),
        CACHE_CHANNEL_ID=int(os.getenv("CACHE_CHANNEL_ID", channel_id)),
        MAX_QUEUE_SIZE=int(os.getenv("MAX_QUEUE_SIZE", "10")),
        MAX_FILE_SIZE=int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024))),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        OWNER_NAME=os.getenv("OWNER_NAME", "Bot Owner"),
        PORT=int(port_str) if port_str else None,
        LOCAL_API_URL=local_api,
        LOCAL_API_FILE_URL=os.environ.get(
            "LOCAL_API_FILE_URL",
            f"{local_api}/file" if local_api else None,
        ),
    )


# Singleton — imported everywhere as ``from bot.config import settings``
settings = load_settings()
