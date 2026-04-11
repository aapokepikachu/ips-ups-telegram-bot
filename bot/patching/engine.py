"""
Unified patching interface — detect format and apply.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from bot.patching.ips import apply_ips, IPSError
from bot.patching.ups import apply_ups, UPSError
from bot.utils.constants import IPS_HEADER, UPS_HEADER

logger = logging.getLogger(__name__)


class PatchError(Exception):
    """Umbrella error for any patching failure."""


PatchType = Literal["IPS", "UPS"]


def detect_patch_type(data: bytes) -> PatchType:
    """
    Inspect the first bytes of *data* and return the format name.

    Raises
    ------
    ValueError
        If the data does not match any known patch header.
    """
    if data[:5] == IPS_HEADER:
        return "IPS"
    if data[:4] == UPS_HEADER:
        return "UPS"
    raise ValueError(
        "Unrecognised patch format. "
        "Expected IPS (b'PATCH') or UPS (b'UPS1') header."
    )


async def apply_patch(
    rom_data: bytes,
    patch_data: bytes,
    patch_type: PatchType,
) -> bytes:
    """
    Apply *patch_data* to *rom_data* in a thread executor (non-blocking).

    Returns the patched bytes.

    Raises
    ------
    PatchError
        Wraps any IPS / UPS specific error.
    """
    loop = asyncio.get_running_loop()

    def _apply() -> bytes:
        try:
            if patch_type == "IPS":
                return bytes(apply_ips(rom_data, patch_data))
            elif patch_type == "UPS":
                return bytes(apply_ups(rom_data, patch_data))
            else:
                raise PatchError(f"Unknown patch type: {patch_type}")
        except (IPSError, UPSError) as exc:
            raise PatchError(str(exc)) from exc

    try:
        return await loop.run_in_executor(None, _apply)
    except PatchError:
        raise
    except Exception as exc:
        raise PatchError(f"Unexpected patching error: {exc}") from exc
