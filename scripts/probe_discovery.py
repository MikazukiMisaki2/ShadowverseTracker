#!/usr/bin/env python3
"""Find active BattleModel objects without x64dbg."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.discovery import find_battle_models, find_battle_roots
from shadowverse_tracker.memory.win32 import ProcessReader, find_process_candidates
from shadowverse_tracker.versioning import verify_process_version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    pid = args.pid or find_process_candidates(
        (
            "ShadowverseWB.exe",
            "MuMu模拟器x影之诗高清版.exe",
            "MuMu模拟器x影之诗高清版.o",
        )
    )[0].pid
    started = time.perf_counter()
    with ProcessReader(pid) as reader:
        profile = verify_process_version(reader)
        models = find_battle_models(
            reader,
            class_pointer_rva=profile.battle_model_class_pointer_rva or None,
            module_name=profile.module_name,
            runtime_names_only=profile.dynamic_discovery,
        )
        roots = () if models else find_battle_roots(
            reader,
            module_name=profile.module_name,
            runtime_names_only=profile.dynamic_discovery,
        )
    print(
        f"PID {pid}; version {profile.game_version}; found "
        f"{len(models)} model(s), {len(roots)} root(s) in {time.perf_counter() - started:.2f}s"
    )
    for model in models:
        print(f"model=0x{model:016X}")
    for root in roots:
        print(f"root=0x{root:016X}")
    return 0 if models or roots else 1


if __name__ == "__main__":
    raise SystemExit(main())
