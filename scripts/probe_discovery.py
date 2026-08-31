#!/usr/bin/env python3
"""Find active BattleModel objects without x64dbg."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.discovery import find_battle_models
from shadowverse_tracker.memory.win32 import ProcessReader, find_process


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    pid = args.pid or find_process("ShadowverseWB.exe").pid
    profile = json.loads((REPO_ROOT / "configs" / "versions" / "1.9.0.17891.json").read_text(encoding="utf-8"))
    class_pointer_rva = int(profile["battle_model_class_pointer_rva"], 0)
    started = time.perf_counter()
    with ProcessReader(pid) as reader:
        models = find_battle_models(reader, class_pointer_rva=class_pointer_rva)
    print(f"PID {pid}; found {len(models)} model(s) in {time.perf_counter() - started:.2f}s")
    for model in models:
        print(f"0x{model:016X}")
    return 0 if models else 1


if __name__ == "__main__":
    raise SystemExit(main())
