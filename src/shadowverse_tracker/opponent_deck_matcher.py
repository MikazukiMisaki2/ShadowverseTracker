"""Conservative opponent-deck identification from public play history.

The game does not expose an opponent's complete deck while a match is in
progress.  This module therefore treats identification as a candidate match,
not as an oracle: only cards that have actually been played are considered and
an automatic label is returned after enough evidence separates one profile
from the others.

Profiles are deliberately stored as a small JSON cache instead of being
downloaded in the polling thread.  The source site is client-rendered and can
require a browser challenge; a stale cache is preferable to blocking or
changing match tracking when the site is unavailable.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Iterable, Mapping

from .card_catalog import canonical_card_id


SCHEMA_VERSION = 1
DEFAULT_SOURCE_URL = "https://sva.hypd.asia/deck"


def _runtime_roots() -> tuple[Path, ...]:
    package_root = Path(__file__).resolve().parent
    runtime_root = Path(getattr(sys, "_MEIPASS", package_root.parent))
    executable_root = Path(sys.executable).resolve().parent
    return (package_root, runtime_root, executable_root, executable_root / "_internal")


def default_meta_decks_path() -> Path:
    """Return the user-editable cache path, falling back to packaged data."""
    override = os.environ.get("SHADOWVERSE_TRACKER_META_DECKS", "").strip()
    if override:
        return Path(override)
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        user_path = Path(local_app_data) / "ShadowverseTracker" / "meta_decks.json"
        if user_path.is_file():
            return user_path
    for root in _runtime_roots():
        packaged = root / "data" / "meta_decks.json"
        if packaged.is_file():
            return packaged
        packaged = root / "shadowverse_tracker" / "data" / "meta_decks.json"
        if packaged.is_file():
            return packaged
    return Path(__file__).resolve().parent / "data" / "meta_decks.json"


def writable_meta_decks_path() -> Path:
    """Return the per-user destination used by cache refreshes."""
    override = os.environ.get("SHADOWVERSE_TRACKER_META_DECKS", "").strip()
    if override:
        return Path(override)
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "ShadowverseTracker" / "meta_decks.json"
    return default_meta_decks_path()


def _normalise_cards(value: object) -> dict[int, int]:
    """Read either ``{card_id: count}`` or a list of IDs from JSON."""
    counts: Counter[int] = Counter()
    if isinstance(value, Mapping):
        items = value.items()
        for raw_id, raw_count in items:
            try:
                card_id = canonical_card_id(int(raw_id))
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if card_id > 0 and count > 0:
                counts[card_id] += min(count, 3)
    elif isinstance(value, (list, tuple)):
        for raw_id in value:
            try:
                card_id = canonical_card_id(int(raw_id))
            except (TypeError, ValueError):
                continue
            if card_id > 0:
                counts[card_id] += 1
    return dict(counts)


@dataclass(frozen=True)
class MetaDeckProfile:
    """One concrete 40-card build from a meta-deck source."""

    profile_id: str
    name: str
    class_id: int
    cards: Mapping[int, int]
    format: str = "rotation"
    archetype: str = ""
    source_url: str = DEFAULT_SOURCE_URL
    official_url: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        # Runtime battle objects may carry style/evolution or CN-client IDs;
        # normalise profiles at construction too so hand-built/test profiles
        # behave exactly like JSON-loaded profiles.
        object.__setattr__(self, "cards", _normalise_cards(self.cards))

    @property
    def card_ids(self) -> frozenset[int]:
        return frozenset(int(card_id) for card_id, count in self.cards.items() if int(count) > 0)

    @property
    def total_cards(self) -> int:
        return sum(max(0, int(count)) for count in self.cards.values())


@dataclass(frozen=True)
class OpponentDeckMatch:
    """A ranked profile result for the cards observed so far."""

    profile: MetaDeckProfile
    confidence: float
    margin: float
    matched_cards: int
    observed_cards: int
    matched_distinct: int
    observed_distinct: int
    accepted: bool

    @property
    def label(self) -> str:
        return self.profile.name


def _profile_from_payload(item: object, index: int) -> MetaDeckProfile | None:
    if not isinstance(item, Mapping):
        return None
    raw_id = str(item.get("id") or item.get("profile_id") or f"profile-{index}").strip()
    name = str(item.get("name") or item.get("label") or "").strip()
    if not raw_id or not name:
        return None
    try:
        class_id = int(item.get("class_id"))
    except (TypeError, ValueError):
        return None
    if not 0 <= class_id <= 7:
        return None
    cards = _normalise_cards(item.get("cards"))
    if not cards or sum(cards.values()) <= 0:
        return None
    return MetaDeckProfile(
        profile_id=raw_id,
        name=name,
        class_id=class_id,
        cards=cards,
        format=str(item.get("format") or "rotation").strip() or "rotation",
        archetype=str(item.get("archetype") or "").strip(),
        source_url=str(item.get("source_url") or DEFAULT_SOURCE_URL).strip() or DEFAULT_SOURCE_URL,
        official_url=str(item.get("official_url") or "").strip(),
        updated_at=str(item.get("updated_at") or "").strip(),
    )


def load_meta_deck_profiles(path: Path | None = None) -> tuple[MetaDeckProfile, ...]:
    """Load and validate cached profiles; malformed entries are ignored."""
    source = path or default_meta_decks_path()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ()
    raw_profiles = payload.get("profiles", ()) if isinstance(payload, Mapping) else payload
    if not isinstance(raw_profiles, list):
        return ()
    result: list[MetaDeckProfile] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_profiles):
        profile = _profile_from_payload(item, index)
        if profile is None or profile.profile_id in seen:
            continue
        seen.add(profile.profile_id)
        result.append(profile)
    return tuple(result)


def save_meta_deck_profiles(
    profiles: Iterable[MetaDeckProfile],
    path: Path | None = None,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    updated_at: str = "",
) -> Path:
    """Write a validated cache suitable for a later offline match."""
    target = path or writable_meta_decks_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    items = []
    for profile in profiles:
        items.append({
            "id": profile.profile_id,
            "name": profile.name,
            "class_id": profile.class_id,
            "format": profile.format,
            "archetype": profile.archetype,
            "cards": {str(int(card_id)): int(count) for card_id, count in profile.cards.items() if int(count) > 0},
            "source_url": profile.source_url or source_url,
            "official_url": profile.official_url,
            "updated_at": profile.updated_at or updated_at,
        })
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "source": source_url,
        "updated_at": updated_at,
        "profiles": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
    return target


class OpponentDeckMatcher:
    """Rank cached profiles using only public opponent play events."""

    def __init__(
        self,
        profiles: Iterable[MetaDeckProfile] = (),
        *,
        min_observed_distinct: int = 3,
        min_confidence: float = 0.78,
        min_margin: float = 0.08,
    ) -> None:
        self.profiles = tuple(profiles)
        self.min_observed_distinct = max(1, int(min_observed_distinct))
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.min_margin = max(0.0, min(1.0, float(min_margin)))

    @staticmethod
    def _score(profile: MetaDeckProfile, observed: Counter[int]) -> tuple[float, int, int]:
        matched = 0
        matched_distinct = 0
        for card_id, observed_count in observed.items():
            available = max(0, int(profile.cards.get(card_id, 0)))
            matched_count = min(observed_count, available)
            matched += matched_count
            if matched_count > 0:
                matched_distinct += 1
        observed_total = sum(observed.values())
        observed_distinct = len(observed)
        if observed_total <= 0:
            return 0.0, matched, matched_distinct
        # Public plays can include generated cards and can contain style IDs;
        # keep the score tolerant while still penalising a non-profile card.
        coverage = matched / observed_total
        distinct_coverage = matched_distinct / max(1, observed_distinct)
        score = 0.72 * coverage + 0.28 * distinct_coverage
        return score, matched, matched_distinct

    def rank(
        self,
        observed_card_ids: Iterable[int],
        opponent_class_id: int | None = None,
    ) -> tuple[OpponentDeckMatch, ...]:
        observed: Counter[int] = Counter()
        for raw_id in observed_card_ids:
            try:
                card_id = canonical_card_id(int(raw_id))
            except (TypeError, ValueError):
                continue
            if card_id > 0:
                observed[card_id] += 1
        candidates = [
            profile for profile in self.profiles
            if opponent_class_id is None or profile.class_id == int(opponent_class_id)
        ]
        ranked: list[OpponentDeckMatch] = []
        ordered = sorted(
            ((self._score(profile, observed), profile) for profile in candidates),
            key=lambda value: (-value[0][0], value[1].profile_id),
        )
        observed_total = sum(observed.values())
        observed_distinct = len(observed)
        for index, (score_data, profile) in enumerate(ordered):
            score = float(score_data[0])
            matched = int(score_data[1])
            matched_distinct = int(score_data[2])
            next_score = ordered[index + 1][0][0] if index + 1 < len(ordered) else 0.0
            ranked.append(OpponentDeckMatch(
                profile=profile,
                confidence=round(max(0.0, min(1.0, score)), 4),
                margin=round(max(0.0, float(score) - float(next_score)), 4),
                matched_cards=matched,
                observed_cards=observed_total,
                matched_distinct=matched_distinct,
                observed_distinct=observed_distinct,
                accepted=(
                    observed_distinct >= self.min_observed_distinct
                    and score >= self.min_confidence
                    and score - next_score >= self.min_margin
                ),
            ))
        return tuple(ranked)

    def match(
        self,
        observed_card_ids: Iterable[int],
        opponent_class_id: int | None = None,
    ) -> OpponentDeckMatch | None:
        ranked = self.rank(observed_card_ids, opponent_class_id)
        if not ranked or not ranked[0].accepted:
            return None
        return ranked[0]


__all__ = [
    "DEFAULT_SOURCE_URL",
    "MetaDeckProfile",
    "OpponentDeckMatch",
    "OpponentDeckMatcher",
    "default_meta_decks_path",
    "load_meta_deck_profiles",
    "save_meta_deck_profiles",
    "writable_meta_decks_path",
]
