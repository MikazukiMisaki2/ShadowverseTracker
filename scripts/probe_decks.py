#!/usr/bin/env python3
"""List complete 40-card DeckInfo objects found in the running client."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.deck import find_deck_infos
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
        decks = find_deck_infos(
            reader,
            class_pointer_rva=profile.deck_info_class_pointer_rva or None,
            module_name=profile.module_name,
        )
    print(f"PID {pid}; found {len(decks)} unique deck(s) in {time.perf_counter() - started:.2f}s")
    for deck in decks:
        cards = ", ".join(f"{card.card_id}x{card.count}" for card in deck.cards)
        print(f"deck={deck.deck_id} class={deck.class_id} format={deck.deck_format} name={deck.deck_name!r}: {cards}")
    return 0 if decks else 1


if __name__ == "__main__":
    raise SystemExit(main())
