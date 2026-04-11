"""
Pure-Python UPS (Universal Patching System) patch applier.

Format reference:
    Header : b"UPS1" (4 bytes)
    Sizes  : source_size (VWI) + dest_size (VWI)
    Hunks  : skip(VWI) + XOR data terminated by 0x00
    Footer : source_crc32(4B LE) + dest_crc32(4B LE) + patch_crc32(4B LE)
"""

from __future__ import annotations

import logging
import struct
import zlib

from bot.utils.constants import UPS_HEADER

logger = logging.getLogger(__name__)


class UPSError(Exception):
    """Raised when a UPS patch is invalid or cannot be applied."""


class _UPSReader:
    """Stateful reader over raw UPS patch bytes."""

    __slots__ = ("data", "offset")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read_byte(self) -> int:
        if self.offset >= len(self.data):
            raise UPSError("Unexpected end of UPS patch")
        b = self.data[self.offset]
        self.offset += 1
        return b

    def read_vwi(self) -> int:
        """Decode a variable-width integer as defined by the UPS spec."""
        value = 0
        shift = 1
        while True:
            byte = self.read_byte()
            value += (byte & 0x7F) * shift
            if byte & 0x80:
                break
            shift <<= 7
            value += shift
        return value


def _crc32(data: bytes) -> int:
    """Unsigned CRC-32."""
    return zlib.crc32(data) & 0xFFFFFFFF


def apply_ups(rom_data: bytes, patch_data: bytes) -> bytearray:
    """
    Apply a UPS patch to *rom_data* and return the patched result.

    Parameters
    ----------
    rom_data : bytes
        The original (source) ROM file contents.
    patch_data : bytes
        The raw UPS patch file contents.

    Returns
    -------
    bytearray
        Patched ROM data.

    Raises
    ------
    UPSError
        If the patch is malformed or CRC-32 checks fail.
    """
    if not patch_data.startswith(UPS_HEADER):
        raise UPSError("Invalid UPS header — expected b'UPS1'")

    # ---- Parse footer checksums (last 12 bytes) ----
    if len(patch_data) < 16:  # 4 header + 12 checksums at minimum
        raise UPSError("UPS patch too short")

    expected_src_crc = struct.unpack_from("<I", patch_data, len(patch_data) - 12)[0]
    expected_dst_crc = struct.unpack_from("<I", patch_data, len(patch_data) - 8)[0]
    expected_patch_crc = struct.unpack_from("<I", patch_data, len(patch_data) - 4)[0]

    # Verify patch CRC (covers everything except the last 4 bytes)
    actual_patch_crc = _crc32(patch_data[:-4])
    if actual_patch_crc != expected_patch_crc:
        raise UPSError(
            f"Patch CRC mismatch: expected {expected_patch_crc:#010x}, "
            f"got {actual_patch_crc:#010x}"
        )

    # Verify source CRC
    actual_src_crc = _crc32(rom_data)
    if actual_src_crc != expected_src_crc:
        logger.warning(
            "Source ROM CRC mismatch: expected %#010x, got %#010x. "
            "The ROM may not be the correct base file.",
            expected_src_crc,
            actual_src_crc,
        )
        # Continue anyway — some patches are lenient

    # ---- Parse header fields ----
    reader = _UPSReader(patch_data)
    reader.offset = len(UPS_HEADER)

    source_size = reader.read_vwi()
    dest_size = reader.read_vwi()

    if source_size != len(rom_data):
        logger.warning(
            "Source size mismatch: patch expects %d, ROM is %d",
            source_size,
            len(rom_data),
        )

    # Build output buffer
    output = bytearray(rom_data)
    if dest_size > len(output):
        output.extend(b"\x00" * (dest_size - len(output)))
    elif dest_size < len(output):
        output = output[:dest_size]

    # ---- Apply XOR hunks ----
    src_len = len(rom_data)
    write_pos = 0
    hunks_applied = 0
    # Hunk data ends 12 bytes before the end (checksums)
    hunk_end = len(patch_data) - 12

    while reader.offset < hunk_end:
        skip = reader.read_vwi()
        write_pos += skip

        # XOR bytes until we hit a 0x00 terminator
        while reader.offset < hunk_end:
            byte = reader.read_byte()
            if byte == 0x00:
                write_pos += 1
                break
            # XOR with source byte (or 0x00 if beyond source)
            src_byte = rom_data[write_pos] if write_pos < src_len else 0x00
            if write_pos < len(output):
                output[write_pos] = src_byte ^ byte
            write_pos += 1

        hunks_applied += 1

    # ---- Verify destination CRC ----
    actual_dst_crc = _crc32(bytes(output))
    if actual_dst_crc != expected_dst_crc:
        raise UPSError(
            f"Destination CRC mismatch: expected {expected_dst_crc:#010x}, "
            f"got {actual_dst_crc:#010x}. The patch may not match this ROM."
        )

    logger.info(
        "UPS patch applied: %d hunks, output %d bytes", hunks_applied, len(output)
    )
    return output
