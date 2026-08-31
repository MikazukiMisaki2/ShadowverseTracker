from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.deck_ledger import DeckLedger
from shadowverse_tracker.memory.deck import DeckCard, DeckInfoSnapshot


def snapshot(
    deck_count: int,
    hand: list[dict[str, int]],
    events=(),
    *,
    turn: int = 1,
    field: list[dict[str, int]] | None = None,
    played=(),
) -> dict[str, object]:
    return {
        "root": {
            "players": [
                {
                    "deck_count": deck_count,
                    "turn": turn,
                    "hand": hand,
                    "field": list(field or ()),
                    "played_card_ids": list(played),
                },
                {},
            ]
        },
        "events": list(events),
    }


class DeckLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.deck = DeckInfoSnapshot(
            "0x1",
            6,
            "test",
            5,
            1,
            tuple([DeckCard(10000010 + index * 10, 1) for index in range(40)]),
        )

    def test_initial_hand_and_later_draw_decrement_once(self) -> None:
        ledger = DeckLedger(self.deck)
        first = ledger.update(snapshot(39, [{"unique_id": 10, "base_card_id": 10000010}]))
        self.assertEqual(first["identified_removed"], 1)
        second = ledger.update(snapshot(38, [
            {"unique_id": 10, "base_card_id": 10000010},
            {"unique_id": 11, "base_card_id": 10000020},
        ]))
        self.assertEqual(second["identified_removed"], 2)
        again = ledger.update(snapshot(38, [
            {"unique_id": 10, "base_card_id": 10000010},
            {"unique_id": 11, "base_card_id": 10000020},
        ]))
        self.assertEqual(again["identified_removed"], 2)

    def test_generated_card_does_not_reduce_ledger(self) -> None:
        ledger = DeckLedger(self.deck)
        ledger.update(snapshot(40, []))
        value = ledger.update(snapshot(40, [{"unique_id": 90, "base_card_id": 10000010}]))
        self.assertEqual(value["identified_removed"], 0)

    def test_generated_field_card_with_a_deck_id_does_not_reduce_ledger(self) -> None:
        ledger = DeckLedger(self.deck)
        ledger.update(snapshot(40, []))
        value = ledger.update(snapshot(
            39,
            [],
            events=[{"type": "BattleResponsePutToken", "is_ally": True}],
            field=[{"unique_id": 90, "base_card_id": 10000010}],
        ))
        self.assertEqual(value["identified_removed"], 0)
        self.assertEqual(value["unknown_removed"], 1)

    def test_direct_deck_summon_on_field_reduces_its_named_row(self) -> None:
        ledger = DeckLedger(self.deck)
        ledger.update(snapshot(40, []))
        value = ledger.update(snapshot(
            39,
            [],
            field=[{"unique_id": 91, "base_card_id": 10000010}],
        ))
        row = next(row for row in value["rows"] if row["card_id"] == 10000010)
        self.assertEqual(row["remaining"], 0)
        self.assertEqual(value["identified_removed"], 1)

    def test_unseen_removal_is_reported_unknown(self) -> None:
        ledger = DeckLedger(self.deck)
        value = ledger.update(snapshot(37, []))
        self.assertEqual(value["unknown_removed"], 3)

    def test_mulligan_replacement_does_not_steal_first_turn_draw(self) -> None:
        tuji = 10754110
        other_ids = [11000010 + index * 10 for index in range(37)]
        deck = DeckInfoSnapshot(
            "0x2",
            7,
            "mulligan",
            5,
            1,
            (DeckCard(tuji, 3), *(DeckCard(card_id, 1) for card_id in other_ids)),
        )
        ledger = DeckLedger(deck)

        # UID 2 is returned during mulligan.  UID 5 is its replacement and UID
        # 6 is the normal turn-one draw; both can first appear in the same read.
        mulligan = ledger.update(snapshot(36, [
            {"unique_id": 1, "base_card_id": other_ids[0]},
            {"unique_id": 2, "base_card_id": other_ids[1]},
            {"unique_id": 3, "base_card_id": tuji},
            {"unique_id": 4, "base_card_id": other_ids[2]},
        ], turn=0))
        self.assertEqual(mulligan["identified_removed"], 0)
        self.assertEqual(mulligan["unknown_removed"], 4)

        first_turn = ledger.update(snapshot(35, [
            {"unique_id": 1, "base_card_id": other_ids[0]},
            {"unique_id": 5, "base_card_id": other_ids[3]},
            {"unique_id": 3, "base_card_id": tuji},
            {"unique_id": 4, "base_card_id": other_ids[2]},
            {"unique_id": 6, "base_card_id": tuji},
        ], turn=1))
        row = next(row for row in first_turn["rows"] if row["card_id"] == tuji)
        self.assertEqual(row["remaining"], 1)
        self.assertEqual(first_turn["identified_removed"], 5)
        self.assertEqual(first_turn["unknown_removed"], 0)

        # A foil runtime ID (ending in 1) shares the same three-copy inventory.
        third_draw = ledger.update(snapshot(34, [
            {"unique_id": 3, "base_card_id": tuji},
            {"unique_id": 6, "base_card_id": tuji},
            {"unique_id": 7, "card_id": tuji + 1, "base_card_id": tuji},
        ], turn=2))
        row = next(row for row in third_draw["rows"] if row["card_id"] == tuji)
        self.assertEqual(row["remaining"], 0)

        # Playing one changes zones but must neither restore nor double-charge it.
        after_play = ledger.update(snapshot(
            34,
            [
                {"unique_id": 3, "base_card_id": tuji},
                {"unique_id": 6, "base_card_id": tuji},
            ],
            turn=2,
            field=[{"unique_id": 7, "card_id": tuji + 1}],
            played=[(tuji + 1, 0)],
        ))
        row = next(row for row in after_play["rows"] if row["card_id"] == tuji)
        self.assertEqual(row["remaining"], 0)

    def test_midmatch_initialization_does_not_count_field_and_history_twice(self) -> None:
        ledger = DeckLedger(self.deck)
        value = ledger.update(snapshot(
            38,
            [{"unique_id": 1, "base_card_id": 10000010}],
            turn=4,
            field=[{"unique_id": 2, "card_id": 10000020}],
            played=[(10000020, 0)],
        ))
        self.assertEqual(value["identified_removed"], 2)
        self.assertEqual(value["unknown_removed"], 0)


if __name__ == "__main__":
    unittest.main()
