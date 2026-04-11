"""
Pure-Python IPS (International Patching System) patch applier.

Format reference:
    Header: b"PATCH" (5 bytes)
    Hunks:  offset(3B) + size(2B) + data(sizeB)
            If size == 0 → RLE hunk: run_length(2B) + value(1B)
    Footer: b"EOF" (3 bytes)
"""

from __future__ import annotations

import logging

from bot.utils.constants import IPS_HEADER, IPS_EOF

logger = logging.getLogger(__name__)


class IPSError(Exception):
    """Raised when an IPS patch is invalid or cannot be applied."""


def apply_ips(rom_data: bytes, patch_data: bytes) -> bytearray:
    """
    Apply an IPS patch to *rom_data* and return the patched result.

    Parameters
    ----------
    rom_data : bytes
        The original ROM file contents.
    patch_data : bytes
        The raw IPS patch file contents.

    Returns
    -------
    bytearray
        Patched ROM data.

    Raises
    ------
    IPSError
        If the patch header is invalid or the patch is malformed.
    """
    if not patch_data.startswith(IPS_HEADER):
        raise IPSError("Invalid IPS header — expected b'PATCH'")

    output = bytearray(rom_data)
    offset = len(IPS_HEADER)  # skip past "PATCH"
    patch_len = len(patch_data)
    hunks_applied = 0

    while offset < patch_len:
        # Check for EOF marker
        if patch_data[offset : offset + 3] == IPS_EOF:
            logger.debug("IPS EOF reached after %d hunks", hunks_applied)
            # Optional: truncation extension (3 bytes after EOF)
            trunc_offset = offset + 3
            if trunc_offset + 3 <= patch_len:
                trunc_size = int.from_bytes(
                    patch_data[trunc_offset : trunc_offset + 3], "big"
                )
                if trunc_size < len(output):
                    output = output[:trunc_size]
                    logger.debug("IPS truncation applied → %d bytes", trunc_size)
            break

        # Read hunk offset (3 bytes, big-endian)
        if offset + 3 > patch_len:
            raise IPSError("Unexpected end of patch reading hunk offset")
        hunk_offset = int.from_bytes(patch_data[offset : offset + 3], "big")
        offset += 3

        # Read hunk size (2 bytes, big-endian)
        if offset + 2 > patch_len:
            raise IPSError("Unexpected end of patch reading hunk size")
        hunk_size = int.from_bytes(patch_data[offset : offset + 2], "big")
        offset += 2

        if hunk_size == 0:
            # ---- RLE hunk ----
            if offset + 3 > patch_len:
                raise IPSError("Unexpected end of patch in RLE hunk")
            run_length = int.from_bytes(patch_data[offset : offset + 2], "big")
            offset += 2
            value = patch_data[offset : offset + 1]
            offset += 1

            # Expand output if necessary
            end = hunk_offset + run_length
            if end > len(output):
                output.extend(b"\x00" * (end - len(output)))
            output[hunk_offset : hunk_offset + run_length] = value * run_length
        else:
            # ---- Normal hunk ----
            if offset + hunk_size > patch_len:
                raise IPSError("Unexpected end of patch in data hunk")
            data = patch_data[offset : offset + hunk_size]
            offset += hunk_size

            # Expand output if necessary
            end = hunk_offset + hunk_size
            if end > len(output):
                output.extend(b"\x00" * (end - len(output)))
            output[hunk_offset : hunk_offset + hunk_size] = data

        hunks_applied += 1

    logger.info("IPS patch applied: %d hunks, output %d bytes", hunks_applied, len(output))
    return output
