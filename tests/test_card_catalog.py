from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.card_catalog import (
    card_class_id,
    card_pack,
    get_card_name,
    is_card_allowed,
    latest_card_pack,
    load_card_catalog,
)
from shadowverse_tracker.card_effects import (
    get_card_effect,
    inferred_hand_additions,
    is_spell,
    magic_boost_amount,
    related_token_ids,
)


class CardCatalogTests(unittest.TestCase):
    def test_card_effect_data_contains_token_relations(self) -> None:
        effect = get_card_effect(10052110)
        self.assertIsNotNone(effect)
        self.assertIn(90051120, related_token_ids(10052110))
        self.assertIn("蝙蝠", effect.skill_text)
        self.assertIn((90051120, 1), inferred_hand_additions(10052110, "destroy"))
        self.assertTrue(is_spell(10031310))
        self.assertEqual(magic_boost_amount(10532120, "destroy"), 1)

    def test_loads_packaged_csv(self) -> None:
        catalog = load_card_catalog()
        # The CSV has 1047 rows; 143 ``base@style`` cosmetic rows are not
        # integer runtime IDs, leaving 904 directly addressable base/token IDs.
        self.assertEqual(len(catalog), 904)
        self.assertEqual(get_card_name(10953110), "激烈的副总长")

    def test_runtime_style_id_falls_back_to_base_card(self) -> None:
        self.assertEqual(get_card_name(10851131), "兔耳恶魔·莉蜜儿")
        self.assertEqual(get_card_name(90051121), "蝙蝠")

    def test_china_runtime_ids_resolve_to_global_catalog(self) -> None:
        # The China Windows client exposes the same cards through its 862…
        # namespace.  Names and effects must use the shared global catalog.
        self.assertEqual(get_card_name(86213130), get_card_name(10113130))
        self.assertEqual(get_card_name(86212310), get_card_name(10012310))

    def test_pack_and_class_digits(self) -> None:
        self.assertEqual(card_pack(10934110), 9)
        self.assertEqual(card_class_id(10934110), 3)

    def test_deck_restrictions(self) -> None:
        # The catalog currently reaches pack 9, so rotation keeps packs 4–9.
        self.assertEqual(latest_card_pack(), 9)
        self.assertTrue(is_card_allowed(10934110, class_id=3, format_version=1))
        self.assertTrue(is_card_allowed(10434110, class_id=3, format_version=1))
        self.assertFalse(is_card_allowed(10334110, class_id=3, format_version=1))
        self.assertTrue(is_card_allowed(10904110, class_id=3, format_version=1))
        self.assertFalse(is_card_allowed(10924110, class_id=3, format_version=1))
        self.assertTrue(is_card_allowed(10004110, class_id=3, format_version=2))


if __name__ == "__main__":
    unittest.main()
