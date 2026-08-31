from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.opponent_hand import OpponentKnownHand


class OpponentKnownHandTests(unittest.TestCase):
    def test_known_last_words_and_unknown_spell(self) -> None:
        tracker = OpponentKnownHand()
        opponent = {
            "deck_count": 10,
            "played_card_ids": [(10052110, 0), (10574120, 0)],
            "destroyed_card_ids": [(10052110, 0)],
        }
        tracker.update({}, opponent)
        self.assertEqual(tracker.cards[90051120], 1)
        self.assertEqual(tracker.cards["unknown_spell"], 1)

    def test_self_replacing_last_words_token(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update(
            {},
            {
                "played_card_ids": [(10941110, 0)],
                "destroyed_card_ids": [(10941110, 0)],
            },
        )
        self.assertEqual(tracker.cards[10941110], 1)

    def test_public_draw_event_is_recorded_but_hidden_draw_is_not(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update(
            {
                "events": [
                    {
                        "type": "BattleResponseDrawOpen",
                        "sequence": 7,
                        "is_ally": False,
                        "cards": [{"base_card_id": 90051120}],
                    },
                    {
                        "type": "BattleResponseDrawHide",
                        "sequence": 8,
                        "is_ally": False,
                        "draw_num": 1,
                    },
                ]
            },
            {"deck_count": 10},
        )
        self.assertEqual(tracker.cards[90051120], 1)
        self.assertNotIn("unknown_spell", tracker.cards)

    def test_training_export_keeps_card_and_type_only_information_separate(self) -> None:
        tracker = OpponentKnownHand()
        tracker.cards[90051120] = 2
        tracker.cards["unknown_spell"] = 1
        tracker.cards["unknown_follower"] = 3
        self.assertEqual(
            tracker.to_training_dict(),
            {
                "known_cards": [{"card_id": 90051120, "count": 2}],
                "known_types": [
                    {"kind": "follower", "count": 3},
                    {"kind": "spell", "count": 1},
                ],
                "magic_boost": None,
                "turn_magic_boost": {},
                "evolution_count": 0,
                "current_turn": 0,
                "saint_daphen_turn": None,
                "saint_daphen_triggers": [],
                "liberation_count": 0,
                "recent_evolution_events": [],
                "recent_actions": [],
            },
        )

    def test_mage_spell_and_magic_boost_effect_are_counted(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update(
            {"opponent_class_id": 3},
            {
                "played_card_ids": [(10031310, 0), (10532120, 0)],
                "destroyed_card_ids": [(10532120, 0)],
            },
        )
        self.assertEqual(tracker.magic_boost, 2)

    def test_saint_daphen_only_triggers_from_invocation_draw(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update({}, {"turn": 7, "played_card_ids": [(10404110, 0)], "field": []})
        self.assertEqual(tracker.saint_daphen_triggers, [])
        tracker.update(
            {"events": [{"type": "BattleResponseDrawOpenWithEffect", "sequence": 1, "is_ally": False, "cards": [{"base_card_id": 10404110}]}]},
            {"turn": 7, "played_card_ids": [(10404110, 0)], "field": []},
        )
        self.assertEqual(tracker.saint_daphen_triggers, [(7, 0)])

    def test_direct_all_hand_boost_spell_is_counted_in_addition_to_spell_play(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update(
            {"opponent_class_id": 3},
            {
                "turn": 2,
                "played_card_ids": [(10031310, 0), (10031310, 0), (10832310, 0)],
                "destroyed_card_ids": [],
            },
        )
        # Three spells were played; 和睦欢聚 additionally boosts every card
        # in hand once, so the total is four.
        self.assertEqual(tracker.magic_boost, 4)
        self.assertEqual(tracker.turn_magic_boost, {2: 4})

    def test_registry_can_record_a_type_only_follower_draw(self) -> None:
        tracker = OpponentKnownHand()
        tracker._add_effect((("unknown_follower", 2),))
        self.assertEqual(tracker.cards["unknown_follower"], 2)

    def test_token_addition_is_rejected_when_opponent_hand_did_not_grow(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update({}, {"hand": [{}, {}, {}, {}, {}], "played_card_ids": [], "destroyed_card_ids": []})
        tracker.update({}, {"hand": [{}, {}, {}, {}], "played_card_ids": [(10052110, 0)], "destroyed_card_ids": []})
        self.assertNotIn(90051120, tracker.cards)


if __name__ == "__main__":
    unittest.main()
