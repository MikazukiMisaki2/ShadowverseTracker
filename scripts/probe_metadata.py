#!/usr/bin/env python3
"""Probe or dump Shadowverse WB's IL2CPP metadata using read-only access."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.metadata import parse_obfuscated_header, repair_header
from shadowverse_tracker.memory.win32 import ProcessReader, find_process


def load_config(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "configs" / "versions" / "1.9.0.17891.json",
    )
    parser.add_argument("--pid", type=int, help="target PID; auto-detected when omitted")
    parser.add_argument("--dump", action="store_true", help="export raw and repaired metadata")
    parser.add_argument("--output-dir", type=Path, help="override the local artifact directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    process_name = str(config["process_name"])
    module_name = str(config["module_name"])
    expected_hash = str(config["gameassembly_sha256"]).upper()
    pointer_rva = int(str(config["metadata_pointer_rva"]), 0)
    metadata_version = int(config["metadata_version"])
    version = str(config["game_version"])

    pid = args.pid or find_process(process_name).pid
    with ProcessReader(pid) as reader:
        module = reader.module(module_name)
        actual_hash = sha256_file(Path(module.path))
        if actual_hash != expected_hash:
            raise RuntimeError(
                "GameAssembly.dll version mismatch; refusing to use stale offsets\n"
                f"expected: {expected_hash}\nactual:   {actual_hash}"
            )

        pointer_slot = module.base_address + pointer_rva
        metadata_address = reader.read_u64(pointer_slot)
        if not metadata_address:
            raise RuntimeError("metadata pointer is null; wait until the game finishes IL2CPP startup")

        probe = reader.read(metadata_address, 0x1000)
        header = parse_obfuscated_header(probe)
        file_size = header.estimated_file_size

        report = {
            "game_version": version,
            "pid": pid,
            "module_path": module.path,
            "module_base": f"0x{module.base_address:016X}",
            "metadata_pointer_slot": f"0x{pointer_slot:016X}",
            "metadata_address": f"0x{metadata_address:016X}",
            "encoded_sanity": f"0x{header.encoded_sanity:08X}",
            "encoded_version": f"0x{header.encoded_version:08X}",
            "header_size": f"0x{header.header_size:X}",
            "estimated_file_size": file_size,
            "estimated_file_size_hex": f"0x{file_size:X}",
            "range_count": len(header.ranges),
            "nonempty_range_count": sum(1 for item in header.ranges if item.size),
            "gameassembly_sha256": actual_hash,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))

        if args.dump:
            output_dir = args.output_dir or REPO_ROOT / "reverse" / "versions" / version
            output_dir.mkdir(parents=True, exist_ok=True)
            raw_path = output_dir / "global-metadata.raw"
            repaired_path = output_dir / "global-metadata.dat"

            with raw_path.open("wb") as raw_file, repaired_path.open("wb") as repaired_file:
                first = True
                for chunk in reader.iter_read(metadata_address, file_size):
                    raw_file.write(chunk)
                    if first:
                        repaired_file.write(repair_header(chunk, metadata_version))
                        first = False
                    else:
                        repaired_file.write(chunk)
            print(f"raw metadata:      {raw_path}")
            print(f"repaired metadata: {repaired_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

