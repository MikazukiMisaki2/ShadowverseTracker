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

    def test_draw_response_with_new_managed_address_is_not_recorded_twice(self) -> None:
        service = TrackerService(TrackerConfig(), on_snapshot=lambda _snapshot: None)
        card = {"unique_id": 22, "base_card_id": 10000010}
        previous = {
            "current_turn": 2,
            "root": {"players": [{"deck_count": 38, "turn": 2, "hand": [], "field": []}, {}]},
            "events": [],
        }
        current = {
            "current_turn": 2,
            "root": {"players": [{"deck_count": 37, "turn": 2, "hand": [card], "field": []}, {}]},
            "events": [{
                "address": "0x1", "type": "BattleResponseDrawOpen", "sequence": 9,
                "is_ally": True, "cards": [card],
            }],
        }
        repeated = {
            **current,
            "events": [{
                "address": "0x2", "type": "BattleResponseDrawOpen", "sequence": 9,
                "is_ally": True, "cards": [card],
            }],
        }
        service._capture_self_draws_and_burns(previous, previous["root"]["players"][0])
        service._capture_self_draws_and_burns(current, current["root"]["players"][0])
        service._capture_self_draws_and_burns(repeated, repeated["root"]["players"][0])
        self.assertEqual(repeated["root"]["players"][0]["_draw_history"], [
            {"turn": 2, "kind": "抽取", "card_id": 10000010},
        ])

    def test_play_response_with_new_managed_address_is_not_recorded_twice(self) -> None:
        service = TrackerService(TrackerConfig(), on_snapshot=lambda _snapshot: None)
        players = [{}, {}]
        first = {
            "current_turn": 3,
            "events": [{
                "address": "0x1", "type": "BattleResponsePlayOpen", "sequence": 11,
                "is_ally": True, "card_id": 10000010, "unique_id": 41,
            }],
        }
        second = {
            "current_turn": 3,
            "events": [{
                "address": "0x2", "type": "BattleResponsePlayOpen", "sequence": 11,
                "is_ally": True, "card_id": 10000010, "unique_id": 41,
            }],
        }
        service._capture_public_play_events(first, players)
        service._capture_public_play_events(second, players)
        self.assertEqual(players[0]["_event_played_cards"], [{"turn": 3, "card_id": 10000010}])
        self.assertEqual(len(players[0]["_training_events"]), 1)


if __name__ == "__main__":
    unittest.main()
