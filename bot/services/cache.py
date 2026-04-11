"""
Cache service — check / store patched outputs using SHA-256 keys.
"""

from __future__ import annotations

import logging

from bot.database import Database
from bot.utils.helpers import compute_cache_key

logger = logging.getLogger(__name__)


async def check_cache(
    db: Database, patch_hash: str, rom_file_id: str
) -> dict | None:
    """
    Return the cached record if this patch+ROM combo was processed before,
    otherwise ``None``.
    """
    key = compute_cache_key(patch_hash, rom_file_id)
    cached = await db.find_cache(key)
    if cached:
        logger.info("Cache HIT for key %s", key[:16])
    return cached


async def store_in_cache(
    db: Database,
    patch_hash: str,
    rom_file_id: str,
    output_file_id: str,
    output_message_id: int,
    rom_name: str,
    patch_type: str,
) -> None:
    """Persist a patched output in the cache collection."""
    key = compute_cache_key(patch_hash, rom_file_id)
    await db.store_cache(
        cache_key=key,
        output_file_id=output_file_id,
        output_message_id=output_message_id,
        patch_hash=patch_hash,
        rom_name=rom_name,
        patch_type=patch_type,
    )
    logger.info("Cached output for key %s", key[:16])
