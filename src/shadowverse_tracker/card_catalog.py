"""Packaged Shadowverse WB card-id to Chinese-name catalog."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import sys


@dataclass(frozen=True)
class CardMetadata:
    card_id: int
    cost: int
    name: str


@lru_cache(maxsize=1)
def load_card_catalog() -> dict[int, CardMetadata]:
    catalog: dict[int, CardMetadata] = {}
    sources = _catalog_sources()
    source = next((path for path in sources if path.is_file()), None)
    if source is None:
        expected = "；".join(str(path) for path in sources[:3])
        raise FileNotFoundError(f"未找到卡牌数据 CSV（已检查：{expected}）")
    with source.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                card_id = int(str(row.get("card_id", "")).strip())
                cost = int(str(row.get("cost", "0")).strip() or 0)
            except ValueError:
                continue
            name = str(row.get("name", "")).strip()
            if card_id > 0 and name:
                catalog[card_id] = CardMetadata(card_id=card_id, cost=cost, name=name)
    return catalog


def _catalog_sources() -> tuple[Path, ...]:
    """Locate the catalog in source runs and PyInstaller builds.

    The card art bundle is explicitly placed beside the frozen application as
    ``SV_WB_Cards``.  Using that CSV first avoids relying on a dynamically
    imported package, which PyInstaller can otherwise omit.
    """
    package_root = Path(__file__).resolve().parent
    runtime_root = Path(getattr(sys, "_MEIPASS", package_root.parent))
    executable_root = Path(sys.executable).resolve().parent
    return (
        runtime_root / "SV_WB_Cards" / "SV_WB_Cards.csv",
        executable_root / "SV_WB_Cards" / "SV_WB_Cards.csv",
        executable_root / "_internal" / "SV_WB_Cards" / "SV_WB_Cards.csv",
        package_root / "data" / "SV_WB_Cards.csv",
    )


@lru_cache(maxsize=1)
def load_cn_card_id_map() -> dict[int, int]:
    """Load the China-client runtime IDs used by the Windows Unity build.

    The China client keeps a second ID namespace (currently ``862…``) for a
    number of cards.  The battle objects expose those IDs correctly, but the
    shared WB catalog is keyed by the printed/global IDs.  Keep this mapping
    in a small packaged JSON file so both source runs and PyInstaller builds
    resolve the same card names and effects without depending on a sibling
    project or a network request.
    """
    source = next((path for path in _cn_card_id_sources() if path.is_file()), None)
    if source is None:
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    raw_ids = payload.get("ids", payload) if isinstance(payload, dict) else None
    if not isinstance(raw_ids, dict):
        return {}
    result: dict[int, int] = {}
    for raw_runtime_id, raw_catalog_id in raw_ids.items():
        try:
            runtime_id = int(raw_runtime_id)
            catalog_id = int(raw_catalog_id)
        except (TypeError, ValueError):
            continue
        if runtime_id > 0 and catalog_id > 0:
            result[runtime_id] = catalog_id
    return result


def _cn_card_id_sources() -> tuple[Path, ...]:
    package_root = Path(__file__).resolve().parent
    runtime_root = Path(getattr(sys, "_MEIPASS", package_root.parent))
    executable_root = Path(sys.executable).resolve().parent
    return (
        runtime_root / "shadowverse_tracker" / "data" / "cn_card_ids.json",
        executable_root / "_internal" / "shadowverse_tracker" / "data" / "cn_card_ids.json",
        package_root / "data" / "cn_card_ids.json",
    )


def canonical_card_id(card_id: int) -> int:
    """Return the printed/global ID for a runtime style/evolution variant.

    Steam-style IDs only need the trailing style/evolution digit removed.  CN
    IDs are first translated through ``cn_card_ids.json`` and then receive the
    same normalization, so all downstream deck/effect/history code sees one
    stable ID namespace.
    """
    value = int(card_id)
    base = value // 10 * 10
    aliases = load_cn_card_id_map()
    mapped = aliases.get(value) or aliases.get(base)
    if mapped:
        return int(mapped) // 10 * 10
    return base


def get_card_metadata(card_id: int) -> CardMetadata | None:
    catalog = load_card_catalog()
    value = int(card_id)
    return catalog.get(value) or catalog.get(canonical_card_id(value))


def get_card_name(card_id: int, default: str = "未知卡牌") -> str:
    metadata = get_card_metadata(card_id)
    return metadata.name if metadata is not None else default


def card_pack(card_id: int) -> int:
    """Return the card-pack digit encoded in a Shadowverse WB card id.

    WB ids use an eight-digit layout where the third digit identifies the
    expansion.  Runtime ids may have a trailing style/evolution digit, so
    only the stable eight-digit prefix is considered here.
    """
    digits = str(abs(int(card_id))).zfill(8)
    return int(digits[2])


def card_class_id(card_id: int) -> int:
    """Return the class digit encoded in a Shadowverse WB card id."""
    digits = str(abs(int(card_id))).zfill(8)
    return int(digits[3])


def latest_card_pack() -> int:
    """Return the newest expansion represented by the packaged catalog."""
    catalog = load_card_catalog()
    return max((card_pack(card_id) for card_id in catalog), default=0)


def is_card_allowed(
    card_id: int,
    class_id: int,
    format_version: int,
    *,
    latest_pack: int | None = None,
) -> bool:
    """Whether a card may be added to a deck with the selected restrictions.

    Class 0 is neutral.  Format version 1 is treated as rotation and keeps
    the newest six packs; version 2 (and unknown future versions) is treated
    as unlimited for the purpose of the editor.
    """
    value = int(card_id)
    if card_class_id(value) not in (0, int(class_id)):
        return False
    if int(format_version) == 1:
        newest = latest_card_pack() if latest_pack is None else int(latest_pack)
        return card_pack(value) >= newest - 5
    return True
