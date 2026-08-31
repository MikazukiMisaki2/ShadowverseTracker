"""Supported-game-version loading and strict GameAssembly verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
from pathlib import Path

from .memory.win32 import ProcessReader


class UnsupportedGameVersion(RuntimeError):
    pass


@dataclass(frozen=True)
class VersionProfile:
    game_version: str
    unity_version: str
    process_name: str
    module_name: str
    gameassembly_sha256: str
    battle_model_class_pointer_rva: int
    deck_info_class_pointer_rva: int
    practice_battle_model_class_pointer_rva: int

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "VersionProfile":
        return cls(
            game_version=str(value["game_version"]),
            unity_version=str(value["unity_version"]),
            process_name=str(value["process_name"]),
            module_name=str(value["module_name"]),
            gameassembly_sha256=str(value["gameassembly_sha256"]).upper(),
            battle_model_class_pointer_rva=int(str(value["battle_model_class_pointer_rva"]), 0),
            deck_info_class_pointer_rva=int(str(value["deck_info_class_pointer_rva"]), 0),
            practice_battle_model_class_pointer_rva=int(
                str(value["practice_battle_model_class_pointer_rva"]), 0
            ),
        )


def load_profiles() -> tuple[VersionProfile, ...]:
    package = resources.files("shadowverse_tracker.version_profiles")
    profiles: list[VersionProfile] = []
    for item in package.iterdir():
        if item.name.endswith(".json"):
            profiles.append(VersionProfile.from_dict(json.loads(item.read_text(encoding="utf-8"))))
    return tuple(profiles)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def verify_process_version(reader: ProcessReader) -> VersionProfile:
    profiles = load_profiles()
    module_names = {profile.module_name.casefold() for profile in profiles}
    if len(module_names) != 1:
        raise RuntimeError("version profiles disagree on module name")
    module = reader.module(profiles[0].module_name)
    actual_hash = sha256_file(module.path)
    for profile in profiles:
        if profile.gameassembly_sha256 == actual_hash:
            return profile
    raise UnsupportedGameVersion(
        f"不支持当前 GameAssembly.dll（SHA-256: {actual_hash}）"
    )
