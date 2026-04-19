"""
Cache helpers — thin wrappers around Database.find_cache / store_cache.
"""

from __future__ import annotations

import logging
from typing import Optional

from bot.database import Database
from bot.utils.helpers import compute_cache_key

logger = logging.getLogger(__name__)


async def check_cache(
    db: Database,
    patch_hash: str,
    rom_file_id: str,
) -> Optional[dict]:
    """
    Look up a cached patching result.

    Returns the cache document (with ``output_file_id``) or ``None``.
    Only returns *completed* entries — in-progress markers are invisible.
    """
    key = compute_cache_key(patch_hash, rom_file_id)
    return await db.find_cache(key)


async def store_in_cache(
    db: Database,
    patch_hash: str,
    rom_file_id: str,
    output_file_id: str,
    output_message_id: int,
    rom_name: str,
    patch_type: str,
) -> None:
    """
    Store a completed patching result in the cache.
    Overwrites any in-progress marker for the same key.
    """
    key = compute_cache_key(patch_hash, rom_file_id)
    await db.store_cache(
        cache_key=key,
        output_file_id=output_file_id,
        output_message_id=output_message_id,
        patch_hash=patch_hash,
        rom_name=rom_name,
        patch_type=patch_type,
    )
    logger.info("Cached result: %s (%s → %s)", key[:16], patch_type, rom_name)
