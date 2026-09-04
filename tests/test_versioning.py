from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.versioning import (
    UnsupportedGameVersion,
    VersionProfile,
    _auto_compatible_profile,
    load_profiles,
    verify_process_version,
)


def profile() -> VersionProfile:
    return VersionProfile(
        game_version="1.0.0.1",
        unity_version="u",
        process_name="game.exe",
        module_name="GameAssembly.dll",
        gameassembly_sha256="OLD",
        battle_model_class_pointer_rva=0x100,
        deck_info_class_pointer_rva=0x108,
        practice_battle_model_class_pointer_rva=0x110,
    )


class FakeReader:
    def __init__(self, *, valid: bool = True) -> None:
        self._module = SimpleNamespace(base_address=0x1000, path="GameAssembly.dll")
        self._u64 = {
            0x1100: 0x2000,
            0x1108: 0x3000,
            0x1110: 0x4000,
            0x2010: 0x5000,
            0x2018: 0x5008,
            0x3010: 0x5010,
            0x3018: 0x5018,
            0x4010: 0x5020,
            0x4018: 0x5028,
        }
        self._strings = {
            0x5000: "WrongModel" if not valid else "BattleModel",
            0x5008: "Wizard2.Presentation.Battle",
            0x5010: "DeckInfo",
            0x5018: "Wizard2.Domain.DeckInfoData",
            0x5020: "PracticeBattleModel",
            0x5028: "Wizard2.Presentation.Practice",
        }

    def module(self, _name: str):
        return self._module

    def read_u64(self, address: int) -> int:
        return self._u64[address]

    def read_c_string(self, address: int) -> str:
        return self._strings[address]


class VersioningTests(unittest.TestCase):
    def test_bundled_china_profile_uses_dynamic_discovery(self) -> None:
        profiles = load_profiles()
        value = next(
            profile
            for profile in profiles
            if profile.gameassembly_sha256
            == "79BD3884CFA1B4989FDFF6273F64E5985D92E8A9FF702685E60936CC804E53E4"
        )
        self.assertTrue(value.dynamic_discovery)
        self.assertEqual(value.process_name, "MuMu模拟器x影之诗高清版.exe")
        self.assertEqual(value.battle_model_class_pointer_rva, 0)

    def test_unknown_hash_can_reuse_profile_after_core_class_validation(self) -> None:
        value = _auto_compatible_profile(FakeReader(), FakeReader()._module, (profile(),), "NEW")
        self.assertIsNotNone(value)
        self.assertTrue(value.auto_compatible)
        self.assertEqual(value.gameassembly_sha256, "NEW")

    def test_unknown_hash_rejects_changed_core_class(self) -> None:
        reader = FakeReader(valid=False)
        self.assertIsNone(_auto_compatible_profile(reader, reader._module, (profile(),), "NEW"))

    @patch("shadowverse_tracker.versioning.sync_remote_profiles", side_effect=OSError("offline"))
    @patch("shadowverse_tracker.versioning.sha256_file", return_value="NEW")
    @patch("shadowverse_tracker.versioning.load_profiles", return_value=(profile(),))
    def test_verify_uses_validated_fallback_when_profile_server_is_offline(
        self, _load, _hash, _sync
    ) -> None:
        value = verify_process_version(FakeReader())
        self.assertTrue(value.auto_compatible)

    @patch("shadowverse_tracker.versioning.sync_remote_profiles", side_effect=OSError("offline"))
    @patch("shadowverse_tracker.versioning.sha256_file", return_value="NEW")
    @patch("shadowverse_tracker.versioning.load_profiles", return_value=(profile(),))
    def test_verify_still_rejects_incompatible_update(self, _load, _hash, _sync) -> None:
        with self.assertRaises(UnsupportedGameVersion):
            verify_process_version(FakeReader(valid=False))


if __name__ == "__main__":
    unittest.main()
