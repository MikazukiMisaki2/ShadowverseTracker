#!/usr/bin/env python3
"""Locate live BattleViewServerData instances and print plausible player roots."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.battle import read_il2cpp_type_name, read_reference_collection
from shadowverse_tracker.memory.discovery import find_il2cpp_classes, find_pointer_references_many
from shadowverse_tracker.memory.win32 import ProcessReader, find_process


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    pid = args.pid or find_process("ShadowverseWB.exe").pid
    with ProcessReader(pid) as reader:
        classes = find_il2cpp_classes(reader, "BattleViewServerData", "Wizard2.View")
        found = 0
        for candidate, _class_address in find_pointer_references_many(
            reader, classes, maximum_hits=4096
        ):
            try:
                if read_il2cpp_type_name(reader, candidate) != "Wizard2.View.BattleViewServerData":
                    continue
                players_address = reader.read_u64(candidate + 0x10)
                players = read_reference_collection(reader, players_address, maximum=2)
                if len(players) != 2 or not all(
                    read_il2cpp_type_name(reader, player).endswith("BattleStatePlayerMpo")
                    for player in players
                ):
                    continue
            except (OSError, ValueError):
                continue
            found += 1
            print(f"0x{candidate:016X} players=" + ",".join(f"0x{x:016X}" for x in players))
        return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
