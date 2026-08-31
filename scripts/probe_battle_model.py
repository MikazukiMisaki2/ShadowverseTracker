#!/usr/bin/env python3
"""Decode a BattleModel address captured from RCX during version validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.battle import read_battle_model
from shadowverse_tracker.memory.win32 import ProcessReader, find_process


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=lambda value: int(value, 0), help="BattleModel address from RCX")
    parser.add_argument("--pid", type=int, help="target PID; auto-detected when omitted")
    parser.add_argument(
        "--server-data",
        type=lambda value: int(value, 0),
        help="optional BattleViewServerData address for current legal actions",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pid = args.pid or find_process("ShadowverseWB.exe").pid
    with ProcessReader(pid) as reader:
        snapshot = read_battle_model(
            reader,
            args.model,
            battle_view_server_data_address=args.server_data,
        )
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
