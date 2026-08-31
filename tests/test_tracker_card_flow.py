from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.deck_ledger import DeckLedger
from shadowverse_tracker.memory.deck import DeckCard, DeckInfoSnapshot
from shadowverse_tracker.tracker_service import TrackerConfig, TrackerService


class TrackerCardFlowTests(unittest.TestCase):
    def test_named_overdraw_is_recorded_and_consumed_from_deck(self) -> None:
        cat = 10752110
        other_ids = [11000010 + index * 10 for index in range(37)]
        deck = DeckInfoSnapshot(
            "0x1",
            1,
            "burn-test",
            5,
            1,
            (DeckCard(cat, 3), *(DeckCard(card_id, 1) for card_id in other_ids)),
        )
        ledger = DeckLedger(deck)
        service = TrackerService(TrackerConfig(selected_deck=deck), on_snapshot=lambda _snapshot: None)
        service._ledger = ledger

        full_hand = [{"unique_id": 1, "base_card_id": cat}]
        full_hand.extend(
            {"unique_id": index + 2, "base_card_id": other_ids[index]}
            for index in range(8)
        )
        previous = {
            "current_turn": 5,
            "root": {"players": [{"deck_count": 31, "turn": 5, "hand": full_hand}, {}]},
            "events": [],
        }
        ledger.update(previous)
        service._capture_self_draws_and_burns(previous, previous["root"]["players"][0])

        burned_card = {"unique_id": 99, "base_card_id": cat}
        current = {
            "current_turn": 6,
            "root": {"players": [{"deck_count": 30, "turn": 6, "hand": full_hand}, {}]},
            "events": [{
                "address": "0x99",
                "type": "BattleResponseDrawOpen",
                "sequence": 170,
                "is_ally": True,
                "is_turn_start_draw": True,
                "cards": [burned_card],
            }],
        }
        ledger.update(current)
        mine = current["root"]["players"][0]
        service._capture_self_draws_and_burns(current, mine)

        row = next(row for row in ledger.to_dict()["rows"] if row["card_id"] == cat)
        self.assertEqual(row["remaining"], 1)
        self.assertEqual(ledger.to_dict()["burned_card_ids"], [cat])
        self.assertEqual(mine["_draw_history"], [{"turn": 6, "kind": "爆牌", "card_id": cat, "count": 1}])


if __name__ == "__main__":
    unittest.main()
