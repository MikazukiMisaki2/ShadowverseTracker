"""Validation and repair helpers for the in-memory IL2CPP metadata header."""

from __future__ import annotations

from dataclasses import dataclass
import struct


IL2CPP_SANITY = 0xFAB11BAF


@dataclass(frozen=True)
class MetadataRange:
    index: int
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size


@dataclass(frozen=True)
class MetadataHeader:
    encoded_sanity: int
    encoded_version: int
    header_size: int
    ranges: tuple[MetadataRange, ...]

    @property
    def estimated_file_size(self) -> int:
        return max((item.end for item in self.ranges), default=self.header_size)


def parse_obfuscated_header(data: bytes) -> MetadataHeader:
    if len(data) < 16:
        raise ValueError("metadata header is too short")
    encoded_sanity, encoded_version, first_offset, _ = struct.unpack_from("<IIII", data)
    if first_offset < 0x20 or first_offset > len(data) or first_offset % 8:
        raise ValueError(f"implausible metadata header size: 0x{first_offset:X}")

    ranges: list[MetadataRange] = []
    for pair_offset in range(8, first_offset, 8):
        offset, size = struct.unpack_from("<II", data, pair_offset)
        item = MetadataRange(index=(pair_offset - 8) // 8, offset=offset, size=size)
        if offset > 0x40000000 or size > 0x40000000 or item.end > 0x40000000:
            raise ValueError(f"implausible metadata range {item.index}: 0x{offset:X}+0x{size:X}")
        ranges.append(item)

    nonempty = [item for item in ranges if item.size]
    if not nonempty:
        raise ValueError("metadata header contains no non-empty ranges")
    if nonempty[0].offset != first_offset:
        raise ValueError("first metadata data range does not begin after the header")

    return MetadataHeader(
        encoded_sanity=encoded_sanity,
        encoded_version=encoded_version,
        header_size=first_offset,
        ranges=tuple(ranges),
    )


def repair_header(data: bytes, metadata_version: int) -> bytes:
    if len(data) < 8:
        raise ValueError("metadata is too short")
    repaired = bytearray(data)
    struct.pack_into("<II", repaired, 0, IL2CPP_SANITY, metadata_version)
    return bytes(repaired)

