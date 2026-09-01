"""Supported-game-version loading and safe automatic profile updates."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

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
    auto_compatible: bool = False

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
    profiles: dict[str, VersionProfile] = {}
    for item in package.iterdir():
        if item.name.endswith(".json"):
            profile = VersionProfile.from_dict(json.loads(item.read_text(encoding="utf-8")))
            profiles[profile.gameassembly_sha256] = profile
    cache = profile_cache_dir()
    if cache.is_dir():
        for item in cache.glob("*.json"):
            try:
                profile = VersionProfile.from_dict(json.loads(item.read_text(encoding="utf-8")))
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            profiles[profile.gameassembly_sha256] = profile
    return tuple(profiles.values())


def profile_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "ShadowverseTracker" / "version_profiles"
    return Path.home() / ".shadowverse_tracker" / "version_profiles"


PROFILE_API_URL = (
    "https://api.github.com/repos/MikazukiMisaki2/ShadowverseTracker/contents/"
    "src/shadowverse_tracker/version_profiles"
)


def sync_remote_profiles(*, timeout: float = 5.0) -> int:
    """Download vetted profile JSON files from the project repository."""
    request = Request(
        PROFILE_API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ShadowverseTracker"},
    )
    with urlopen(request, timeout=timeout) as response:
        listing = json.loads(response.read().decode("utf-8"))
    if not isinstance(listing, list):
        raise ValueError("版本配置服务器返回了无效目录")
    cache = profile_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    updated = 0
    for item in listing:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        download_url = item.get("download_url")
        if not name.endswith(".json") or not isinstance(download_url, str):
            continue
        with urlopen(Request(download_url, headers={"User-Agent": "ShadowverseTracker"}), timeout=timeout) as response:
            raw = response.read()
        value = json.loads(raw.decode("utf-8"))
        VersionProfile.from_dict(value)
        target = cache / name
        if target.is_file() and target.read_bytes() == raw:
            continue
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, target)
        updated += 1
    return updated


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


_CLASS_IDENTITIES = (
    ("battle_model_class_pointer_rva", "Wizard2.Presentation.Battle", "BattleModel"),
    ("deck_info_class_pointer_rva", "Wizard2.Domain.DeckInfoData", "DeckInfo"),
    ("practice_battle_model_class_pointer_rva", "Wizard2.Presentation.Practice", "PracticeBattleModel"),
)


def _version_key(profile: VersionProfile) -> tuple[int, ...]:
    return tuple(int(value) for value in re.findall(r"\d+", profile.game_version))


def _core_classes_match(reader: ProcessReader, module, profile: VersionProfile) -> bool:
    """Confirm that the latest profile's three global class pointers are intact."""
    try:
        for field, expected_namespace, expected_name in _CLASS_IDENTITIES:
            class_address = reader.read_u64(module.base_address + getattr(profile, field))
            if not class_address:
                return False
            name = reader.read_c_string(reader.read_u64(class_address + 0x10))
            namespace = reader.read_c_string(reader.read_u64(class_address + 0x18))
            if name != expected_name or namespace != expected_namespace:
                return False
    except (OSError, ValueError):
        return False
    return True


def _auto_compatible_profile(
    reader: ProcessReader,
    module,
    profiles: tuple[VersionProfile, ...],
    actual_hash: str,
) -> VersionProfile | None:
    """Reuse a recent profile only after exact IL2CPP class identity checks."""
    for profile in sorted(profiles, key=_version_key, reverse=True):
        if _core_classes_match(reader, module, profile):
            return replace(
                profile,
                game_version=f"自动兼容 {actual_hash[:12]}",
                gameassembly_sha256=actual_hash,
                auto_compatible=True,
            )
    return None


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
    update_error = ""
    try:
        sync_remote_profiles()
        refreshed = load_profiles()
        for profile in refreshed:
            if profile.gameassembly_sha256 == actual_hash:
                return profile
        profiles = refreshed
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        update_error = f"；自动更新失败：{exc}"
    compatible = _auto_compatible_profile(reader, module, profiles, actual_hash)
    if compatible is not None:
        return compatible
    raise UnsupportedGameVersion(
        f"不支持当前 GameAssembly.dll（SHA-256: {actual_hash}）{update_error}"
    )
