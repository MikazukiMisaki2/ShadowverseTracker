#!/usr/bin/env python3
"""Decode a BattleRootMpo address captured during version validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.battle import read_battle_root
from shadowverse_tracker.memory.win32 import ProcessReader, find_process_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=lambda value: int(value, 0), help="BattleRootMpo address from RDX")
    parser.add_argument("--pid", type=int, help="target PID; auto-detected when omitted")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pid = args.pid or find_process_candidates(
        (
            "ShadowverseWB.exe",
            "MuMu模拟器x影之诗高清版.exe",
            "MuMu模拟器x影之诗高清版.o",
        )
    )[0].pid
    with ProcessReader(pid) as reader:
        root = read_battle_root(reader, args.root)
    print(json.dumps(root.to_public_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
