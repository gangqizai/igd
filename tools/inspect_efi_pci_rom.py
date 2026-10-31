#!/usr/bin/env python3
"""Inspect and optionally extract EFI images from a PCI option ROM."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def pe_file_size(data: bytes, offset: int) -> int:
    if data[offset : offset + 2] != b"MZ":
        raise ValueError(f"missing MZ signature at 0x{offset:x}")
    pe_offset = offset + u32(data, offset + 0x3C)
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"missing PE signature at 0x{pe_offset:x}")
    sections = u16(data, pe_offset + 6)
    optional_size = u16(data, pe_offset + 20)
    section_table = pe_offset + 24 + optional_size
    end = 0
    for index in range(sections):
        section = section_table + index * 40
        raw_size = u32(data, section + 16)
        raw_offset = u32(data, section + 20)
        end = max(end, raw_offset + raw_size)
    if end <= 0:
        raise ValueError(f"PE at 0x{offset:x} has no raw sections")
    return end


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--extract-dir", type=Path)
    args = parser.parse_args()

    data = args.rom.read_bytes()
    image_start = 0
    image_index = 0
    if args.extract_dir:
        args.extract_dir.mkdir(parents=True, exist_ok=True)

    while image_start < len(data):
        if data[image_start : image_start + 2] != b"\x55\xaa":
            raise ValueError(f"missing PCI ROM signature at 0x{image_start:x}")
        efi_offset = u16(data, image_start + 0x16)
        pcir_offset = u16(data, image_start + 0x18)
        pcir = image_start + pcir_offset
        if data[pcir : pcir + 4] != b"PCIR":
            raise ValueError(f"missing PCIR signature at 0x{pcir:x}")
        vendor = u16(data, pcir + 4)
        device = u16(data, pcir + 6)
        blocks = u16(data, pcir + 0x10)
        code_type = data[pcir + 0x14]
        indicator = data[pcir + 0x15]
        image_size = blocks * 512
        pe_start = image_start + efi_offset
        pe_size = pe_file_size(data, pe_start)
        print(
            f"image={image_index} start=0x{image_start:x} size={image_size} "
            f"vendor={vendor:04x} device={device:04x} code_type={code_type:02x} "
            f"indicator={indicator:02x} pe_start=0x{pe_start:x} pe_size={pe_size}"
        )
        if pe_start + pe_size > image_start + image_size:
            raise ValueError(f"PE {image_index} exceeds its PCI image")
        if args.extract_dir:
            output = args.extract_dir / f"image-{image_index}.efi"
            output.write_bytes(data[pe_start : pe_start + pe_size])
            print(f"extracted={output}")
        image_start += image_size
        image_index += 1
        if indicator & 0x80:
            break

    if image_start != len(data):
        raise ValueError(
            f"parsed 0x{image_start:x} bytes but ROM size is 0x{len(data):x}"
        )


if __name__ == "__main__":
    main()
