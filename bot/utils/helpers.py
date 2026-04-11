"""
Small utility helpers used across the bot.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone


def format_size(size_bytes: int) -> str:
    """Return a human-readable file size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def compute_patch_hash(patch_data: bytes) -> str:
    """SHA-256 hex digest of raw patch bytes."""
    return hashlib.sha256(patch_data).hexdigest()


def compute_cache_key(patch_hash: str, rom_file_id: str) -> str:
    """Deterministic cache key from patch hash + ROM file_id."""
    return hashlib.sha256(f"{patch_hash}:{rom_file_id}".encode()).hexdigest()


def sanitize_filename(name: str) -> str:
    """Strip characters unsafe for filenames."""
    keep = " ._-()[]"
    return "".join(c for c in name if c.isalnum() or c in keep).strip()


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def measure_latency() -> float:
    """Return current monotonic time for latency measurement."""
    return time.monotonic()


def user_display_name(user) -> str:
    """Build a display name from a Telegram User object."""
    if user.username:
        return f"@{user.username}"
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    return name.strip() or str(user.id)
