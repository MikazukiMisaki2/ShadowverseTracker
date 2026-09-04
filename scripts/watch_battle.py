#!/usr/bin/env python3
"""Continuously sample a live BattleModel and log public state changes.

This watcher is intentionally read-only.  It is useful while a game is running
under x64dbg, but does not require the debugger to be paused.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.battle import read_battle_model
from shadowverse_tracker.memory.win32 import ProcessReader, find_process_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=lambda value: int(value, 0), help="BattleModel address from RCX")
    parser.add_argument("--pid", type=int, help="target PID; auto-detected when omitted")
    parser.add_argument("--interval", type=float, default=0.25, help="sampling interval in seconds")
    parser.add_argument("--output", type=Path, help="optional JSONL log file")
    return parser.parse_args()


def _public_state(snapshot: dict[str, object]) -> dict[str, object] | None:
    root = snapshot.get("root")
    return root if isinstance(root, dict) else None


def _without_addresses(value: object) -> object:
    """Drop ephemeral managed-object addresses before comparing snapshots."""
    if isinstance(value, dict):
        return {key: _without_addresses(item) for key, item in value.items() if key != "address"}
    if isinstance(value, list):
        return [_without_addresses(item) for item in value]
    return value


def _delta(previous: dict[str, object] | None, current: dict[str, object]) -> dict[str, object]:
    if previous is None:
        return {"kind": "initial"}
    changes: dict[str, object] = {}
    for key in ("address", "is_ally_turn", "players"):
        before = _without_addresses(previous.get(key))
        after = _without_addresses(current.get(key))
        if before != after:
            changes[key] = {"before": before, "after": after}
    return {"kind": "change", "changes": changes}


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")
    pid = args.pid or find_process_candidates(
        (
            "ShadowverseWB.exe",
            "MuMu模拟器x影之诗高清版.exe",
            "MuMu模拟器x影之诗高清版.o",
        )
    )[0].pid
    output = args.output.open("a", encoding="utf-8", buffering=1) if args.output else None
    previous: dict[str, object] | None = None
    try:
        with ProcessReader(pid) as reader:
            while True:
                try:
                    snapshot = read_battle_model(reader, args.model)
                    root = _public_state(snapshot)
                    if root is not None:
                        change = _delta(previous, root)
                        if change["kind"] == "initial" or change["changes"]:
                            record = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "pid": pid,
                                "model": f"0x{args.model:016X}",
                                "delta": change,
                                "snapshot": snapshot,
                            }
                            line = json.dumps(record, ensure_ascii=False)
                            print(line, flush=True)
                            if output:
                                output.write(line + "\n")
                            previous = root
                except (OSError, ValueError, LookupError) as exc:
                    # A managed object can be replaced between two reads.  Keep
                    # sampling and report the transient failure instead of
                    # stopping the user's test.
                    print(json.dumps({"warning": str(exc)}, ensure_ascii=False), flush=True)
                time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        if output:
            output.close()


if __name__ == "__main__":
    raise SystemExit(main())
