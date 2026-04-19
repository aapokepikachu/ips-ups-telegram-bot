"""
Pure-Python BPS (Beat Patching System) patch applier.

Format reference:
    Header : b"BPS1" (4 bytes)
    Sizes  : source_size (VWI) + target_size (VWI) + metadata_size (VWI)
    Meta   : metadata (metadata_size bytes)
    Actions: repeated until 12 bytes before end
        data = readVWI()
        type = data & 3,  length = (data >> 2) + 1
        0 = SourceRead  — copy from source at outputOffset
        1 = TargetRead  — read bytes from patch stream
        2 = SourceCopy  — copy from source at sourceRelativeOffset
        3 = TargetCopy  — copy from target at targetRelativeOffset
    Footer : source_crc32(4B LE) + target_crc32(4B LE) + patch_crc32(4B LE)
"""

from __future__ import annotations

import logging
import struct
import zlib

from bot.utils.constants import BPS_HEADER

logger = logging.getLogger(__name__)


class BPSError(Exception):
    """Raised when a BPS patch is invalid or cannot be applied."""


class _BPSReader:
    """Stateful reader over raw BPS patch bytes."""

    __slots__ = ("data", "offset")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read_byte(self) -> int:
        if self.offset >= len(self.data):
            raise BPSError("Unexpected end of BPS patch")
        b = self.data[self.offset]
        self.offset += 1
        return b

    def read_bytes(self, count: int) -> bytes:
        if self.offset + count > len(self.data):
            raise BPSError("Unexpected end of BPS patch")
        result = self.data[self.offset : self.offset + count]
        self.offset += count
        return result

    def read_vwi(self) -> int:
        """Decode a variable-width integer (same encoding as UPS)."""
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


def apply_bps(rom_data: bytes, patch_data: bytes) -> bytearray:
    """
    Apply a BPS patch to *rom_data* and return the patched result.

    Parameters
    ----------
    rom_data : bytes
        The original (source) ROM file contents.
    patch_data : bytes
        The raw BPS patch file contents.

    Returns
    -------
    bytearray
        Patched ROM data.

    Raises
    ------
    BPSError
        If the patch is malformed or CRC-32 checks fail.
    """
    if not patch_data.startswith(BPS_HEADER):
        raise BPSError("Invalid BPS header — expected b'BPS1'")

    if len(patch_data) < 16:
        raise BPSError("BPS patch too short")

    # ---- Parse footer checksums (last 12 bytes) ----
    expected_src_crc = struct.unpack_from("<I", patch_data, len(patch_data) - 12)[0]
    expected_dst_crc = struct.unpack_from("<I", patch_data, len(patch_data) - 8)[0]
    expected_patch_crc = struct.unpack_from("<I", patch_data, len(patch_data) - 4)[0]

    # Verify patch CRC (covers everything except the last 4 bytes)
    actual_patch_crc = _crc32(patch_data[:-4])
    if actual_patch_crc != expected_patch_crc:
        raise BPSError(
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

    # ---- Parse header fields ----
    reader = _BPSReader(patch_data)
    reader.offset = len(BPS_HEADER)

    source_size = reader.read_vwi()
    target_size = reader.read_vwi()
    metadata_size = reader.read_vwi()

    if metadata_size > 0:
        _metadata = reader.read_bytes(metadata_size)
        logger.debug("BPS metadata (%d bytes)", metadata_size)

    if source_size != len(rom_data):
        logger.warning(
            "Source size mismatch: patch expects %d, ROM is %d",
            source_size,
            len(rom_data),
        )

    # ---- Build output buffer ----
    output = bytearray(target_size)
    output_offset = 0
    source_relative_offset = 0
    target_relative_offset = 0

    action_end = len(patch_data) - 12  # 12 bytes of checksums at end
    hunks_applied = 0

    while reader.offset < action_end:
        data = reader.read_vwi()
        action_type = data & 3
        length = (data >> 2) + 1

        if action_type == 0:
            # SourceRead — copy from source at current outputOffset
            for _ in range(length):
                if output_offset < target_size:
                    src_byte = rom_data[output_offset] if output_offset < len(rom_data) else 0
                    output[output_offset] = src_byte
                output_offset += 1

        elif action_type == 1:
            # TargetRead — read bytes directly from patch stream
            patch_bytes = reader.read_bytes(length)
            for b in patch_bytes:
                if output_offset < target_size:
                    output[output_offset] = b
                output_offset += 1

        elif action_type == 2:
            # SourceCopy — copy from source at sourceRelativeOffset
            offset_data = reader.read_vwi()
            offset_val = offset_data >> 1
            if offset_data & 1:
                offset_val = -offset_val
            source_relative_offset += offset_val
            for _ in range(length):
                if output_offset < target_size:
                    src_byte = (
                        rom_data[source_relative_offset]
                        if 0 <= source_relative_offset < len(rom_data)
                        else 0
                    )
                    output[output_offset] = src_byte
                output_offset += 1
                source_relative_offset += 1

        elif action_type == 3:
            # TargetCopy — copy from target (output) at targetRelativeOffset
            offset_data = reader.read_vwi()
            offset_val = offset_data >> 1
            if offset_data & 1:
                offset_val = -offset_val
            target_relative_offset += offset_val
            for _ in range(length):
                if output_offset < target_size:
                    # Must read one byte at a time (sliding window)
                    t_byte = (
                        output[target_relative_offset]
                        if 0 <= target_relative_offset < target_size
                        else 0
                    )
                    output[output_offset] = t_byte
                output_offset += 1
                target_relative_offset += 1

        hunks_applied += 1

    # ---- Verify destination CRC ----
    actual_dst_crc = _crc32(bytes(output))
    if actual_dst_crc != expected_dst_crc:
        raise BPSError(
            f"Destination CRC mismatch: expected {expected_dst_crc:#010x}, "
            f"got {actual_dst_crc:#010x}. The patch may not match this ROM."
        )

    logger.info(
        "BPS patch applied: %d hunks, output %d bytes", hunks_applied, len(output)
    )
    return output
