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
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import sys
from typing import Iterable, Mapping

from .card_catalog import canonical_card_id


SCHEMA_VERSION = 1
DEFAULT_SOURCE_URL = "https://sva.hypd.asia/deck"
DEFAULT_META_REFRESH_VERSION = "class-recommendations-v1"

# The labels/order used by WBArts' Tier / Meta panel.  Keeping the fallback
# map locally means an older bundled cache (which predates the tier field) is
# still rendered in the same groups as the website.
META_TIER_ORDER = ("T1", "T2", "T3", "T4", "其他")
META_ARCHETYPE_TIERS = {
    "中速梦": "T1",
    "跳费龙": "T1",
    "护符教": "T2",
    "造物超": "T2",
    "连击妖": "T2",
    "实验法": "T2",
    "谢幕梦": "T2",
    "旗皇": "T3",
    "进化教": "T3",
    "财宝皇": "T3",
    "脸龙": "T3",
    "协作皇": "T3",
    "增幅法": "T3",
    "快梦": "T3",
    "骰子教": "T4",
    "验牌梦": "T4",
    "节奏妖": "T4",
    "OTK超": "T4",
    "进化超": "T4",
    "宇宙超": "T4",
    "节奏进化妖": "T4",
    "进化梦": "T4",
    "进化妖": "其他",
    "疾驰教": "其他",
    "魔神梦": "其他",
    "中速皇": "其他",
}

# WBArts currently serializes several archetype filters as ``local:<id>`` in
# its deck API even though the public Tier/Meta panel gives them Chinese
# labels.  Keep the current stable IDs as a first-pass translation; the card
# similarity fallback below still handles newly introduced IDs.
META_LOCAL_ARCHETYPE_LABELS = {
    "local:3": "中速梦",
    "local:5": "协作皇",
    "local:6": "跳费龙",
    "local:7": "实验法",
    "local:10": "节奏妖",
    "local:13": "财宝皇",
}


def meta_tier_label(value: object = "", archetype: object = "") -> str:
    """Normalize a WBArts tier/category value to ``T1``…``T4``/``其他``."""
    if isinstance(value, Mapping):
        value = value.get("name") or value.get("label") or value.get("tier") or value.get("value")
    raw = str(value or "").strip()
    normalized = raw.casefold().replace("_", " ").replace("-", " ")
    if normalized in {"t1", "tier 1", "tier1", "1"}:
        return "T1"
    if normalized in {"t2", "tier 2", "tier2", "2"}:
        return "T2"
    if normalized in {"t3", "tier 3", "tier3", "3"}:
        return "T3"
    if normalized in {"t4", "tier 4", "tier4", "4"}:
        return "T4"
    if normalized in {"other", "others", "other meta", "其他", "其余"}:
        return "其他"
    return META_ARCHETYPE_TIERS.get(str(archetype or "").strip(), "其他")


def meta_archetype_label(archetype: object = "", name: object = "") -> str:
    """Return a stable type label, stripping known sample suffixes implicitly."""
    explicit = str(archetype or "").strip()
    candidate = str(name or "").strip()
    for value in (explicit, candidate):
        mapped = META_LOCAL_ARCHETYPE_LABELS.get(value.casefold())
        if mapped:
            return mapped
    # The site sometimes puts the sample suffix in ``archetype`` and
    # sometimes only in the display name.  Normalize both fields so a
    # cached/API row such as ``中速梦·构筑 A`` never leaks the suffix into
    # history or the Meta list.
    for value in (explicit, candidate):
        for known in META_ARCHETYPE_TIERS:
            if value == known or value.startswith(f"{known}·") or value.startswith(f"{known} "):
                return known
    return explicit or candidate


def is_machine_meta_label(value: object) -> bool:
    """Return whether a source label is an internal, non-user-facing ID."""
    normalized = str(value or "").strip().casefold()
    return normalized.startswith(("local:", "archetype:", "deck:"))


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _played_card_ids(value: object) -> tuple[int, ...]:
    """Extract base card IDs from the reader's ``played_card_ids`` shape."""
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[int] = []
    for item in value:
        raw: object = item
        if isinstance(item, Mapping):
            raw = item.get("base_card_id") or item.get("card_id")
        elif isinstance(item, (list, tuple)) and item:
            raw = item[0]
        card_id = _int_or_none(raw)
        if card_id is None or card_id <= 0:
            continue
        result.append(canonical_card_id(card_id))
    return tuple(result)


def load_session_opponent_observations(
    path: Path | None = None,
) -> dict[str, tuple[int, ...]]:
    """Read terminal opponent-play observations from an app-session log.

    ``matches.json`` intentionally stores only the human-facing match summary.
    The address-free training stream cannot identify a summary row either, but
    the local app-session stream contains the terminal snapshot and therefore
    the same stable ``terminal:*`` ID used by :mod:`match_history`.  Reading
    this optional log lets existing rows benefit from the recognizer after an
    upgrade.  Malformed or partially-written lines are ignored because the
    polling thread may append to the file while this function is running.
    """
    source = Path(path) if path is not None else Path("logs") / "app_session.jsonl"
    if not source.is_file():
        return {}
    # Import lazily to keep the matcher usable by data-refresh scripts without
    # importing the history/UI modules at module import time.
    from .match_history import orient_player_order, result_label, terminal_match_id

    observations: dict[str, tuple[int, ...]] = {}
    try:
        handle = source.open("r", encoding="utf-8")
    except OSError:
        return {}
    with handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, Mapping):
                continue
            snapshot = payload.get("snapshot")
            if not isinstance(snapshot, Mapping):
                continue
            root = snapshot.get("root")
            players = root.get("players") if isinstance(root, Mapping) else None
            if not isinstance(players, (list, tuple)) or len(players) < 2:
                continue
            deck = snapshot.get("deck")
            expected_class = deck.get("class_id") if isinstance(deck, Mapping) else None
            players = orient_player_order(
                players,
                self_class_id=snapshot.get("self_class_id"),
                opponent_class_id=snapshot.get("opponent_class_id"),
                expected_self_class_id=expected_class,
            )
            mine, opponent = players[0], players[1]
            if not isinstance(mine, Mapping) or not isinstance(opponent, Mapping):
                continue
            result_code = _int_or_none(mine.get("result_code")) or 0
            self_life = _int_or_none(mine.get("life"))
            opponent_life = _int_or_none(opponent.get("life"))
            if result_label(result_code, self_life, opponent_life) not in {"胜利", "失败"}:
                continue
            address = str(snapshot.get("address") or payload.get("model") or "unknown")
            turn = _int_or_none(mine.get("turn"))
            deck_count = _int_or_none(mine.get("deck_count"))
            cemetery_count = _int_or_none(mine.get("cemetery_count"))
            played = mine.get("played_card_ids")
            destroyed = mine.get("destroyed_card_ids")
            match_id = terminal_match_id(
                address,
                result_code,
                turn,
                self_life,
                opponent_life,
                deck_count,
                cemetery_count,
                len(played) if isinstance(played, (list, tuple)) else 0,
                len(destroyed) if isinstance(destroyed, (list, tuple)) else 0,
            )
            observed = _played_card_ids(opponent.get("played_card_ids"))
            # A terminal snapshot can be emitted more than once.  Keep the
            # one with the most public evidence, never an earlier short one.
            if len(observed) > len(observations.get(match_id, ())):
                observations[match_id] = observed
    return observations


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
        for raw_entry in value:
            raw_id = raw_entry
            count = 1
            if isinstance(raw_entry, Mapping):
                raw_id = (
                    raw_entry.get("base_card_id")
                    or raw_entry.get("baseCardId")
                    or raw_entry.get("card_id")
                    or raw_entry.get("cardId")
                    or raw_entry.get("id")
                )
                raw_count = (
                    raw_entry.get("count")
                    or raw_entry.get("quantity")
                    or raw_entry.get("num")
                    or raw_entry.get("amount")
                    or raw_entry.get("qty")
                )
                try:
                    count = min(max(int(raw_count), 1), 3)
                except (TypeError, ValueError):
                    count = 1
            elif isinstance(raw_entry, (list, tuple)) and raw_entry:
                raw_id = raw_entry[0]
                if len(raw_entry) > 1:
                    try:
                        count = min(max(int(raw_entry[1]), 1), 3)
                    except (TypeError, ValueError):
                        count = 1
            try:
                card_id = canonical_card_id(int(raw_id))
            except (TypeError, ValueError):
                continue
            if card_id > 0:
                counts[card_id] += count
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
    tier: str = ""

    def __post_init__(self) -> None:
        # Runtime battle objects may carry style/evolution or CN-client IDs;
        # normalise profiles at construction too so hand-built/test profiles
        # behave exactly like JSON-loaded profiles.
        object.__setattr__(self, "cards", _normalise_cards(self.cards))
        canonical_archetype = meta_archetype_label(self.archetype, self.name)
        object.__setattr__(self, "archetype", canonical_archetype)
        object.__setattr__(self, "tier", meta_tier_label(self.tier, canonical_archetype))

    @property
    def display_name(self) -> str:
        """The stable website archetype label used in history/UI."""
        return str(self.archetype or self.name).strip()

    @property
    def card_ids(self) -> frozenset[int]:
        return frozenset(int(card_id) for card_id, count in self.cards.items() if int(count) > 0)

    @property
    def total_cards(self) -> int:
        return sum(max(0, int(count)) for count in self.cards.values())


def meta_profile_from_saved_deck(deck: object) -> MetaDeckProfile | None:
    """Convert one local ``SavedDeck`` into a Meta-page profile.

    The matcher intentionally accepts the repository object by duck typing so
    this module does not need to import the Qt-facing deck repository.  Local
    profiles are kept in memory and are never written into the WBArts cache;
    this keeps user decks available in Meta and opponent matching without
    mixing private data into the public cache.
    """
    key = str(getattr(deck, "key", "") or "").strip()
    name = str(getattr(deck, "name", "") or "").strip()
    if not key or not name:
        return None
    try:
        class_id = int(getattr(deck, "class_id", 0) or 0)
    except (TypeError, ValueError):
        return None
    if not 0 <= class_id <= 7:
        return None
    format_value = getattr(deck, "format_version", "rotation")
    try:
        format_number = int(format_value)
    except (TypeError, ValueError):
        format_number = 0
    format_name = {1: "rotation", 2: "unlimited"}.get(
        format_number,
        str(format_value or "rotation").strip() or "rotation",
    )
    raw_cards = getattr(deck, "cards", ())
    if isinstance(raw_cards, Mapping):
        cards = _normalise_cards(raw_cards)
    else:
        entries: list[dict[str, int]] = []
        for card in raw_cards if isinstance(raw_cards, (list, tuple)) else ():
            try:
                card_id = int(getattr(card, "card_id", 0) or 0)
                count = int(getattr(card, "count", 0) or 0)
            except (TypeError, ValueError):
                continue
            if card_id > 0 and count > 0:
                entries.append({"card_id": card_id, "count": count})
        cards = _normalise_cards(entries)
    if not cards or sum(cards.values()) != 40:
        return None
    return MetaDeckProfile(
        profile_id=f"local-deck:{key}",
        name=name,
        class_id=class_id,
        cards=cards,
        format=format_name,
        archetype=name,
        source_url="local",
        updated_at="本地牌组",
        tier="",
    )


def canonicalize_meta_deck_labels(
    profiles: Iterable[MetaDeckProfile],
    references: Iterable[MetaDeckProfile] = (),
) -> tuple[MetaDeckProfile, ...]:
    """Replace WBArts ``local:*`` labels using the bundled archetype cache.

    WBArts' public list may expose an internal archetype identifier while the
    rendered site has the corresponding Chinese label in its Tier/Meta panel.
    The bundled cache contains the same concrete builds with stable labels, so
    card-list similarity provides a safe offline bridge after a refresh.  A
    label is only copied when the best same-class build is a clear match; an
    uncertain build remains visible by its original name rather than being
    assigned a misleading archetype.
    """
    current = tuple(profiles)
    known = tuple(
        profile for profile in references
        if profile.display_name and not is_machine_meta_label(profile.display_name)
    )
    if not known:
        return current

    def similarity(left: MetaDeckProfile, right: MetaDeckProfile) -> float:
        left_cards = left.cards
        right_cards = right.cards
        union = set(left_cards) | set(right_cards)
        if not union:
            return 0.0
        matched = sum(min(int(left_cards.get(card_id, 0)), int(right_cards.get(card_id, 0))) for card_id in union)
        total = sum(max(int(left_cards.get(card_id, 0)), int(right_cards.get(card_id, 0))) for card_id in union)
        return matched / max(1, total)

    result: list[MetaDeckProfile] = []
    for profile in current:
        if not is_machine_meta_label(profile.display_name):
            result.append(profile)
            continue
        candidates = [
            reference for reference in known
            if int(reference.class_id) == int(profile.class_id)
            and str(reference.format or "").casefold() == str(profile.format or "").casefold()
        ]
        ranked = sorted(
            ((similarity(profile, reference), reference) for reference in candidates),
            key=lambda item: (-item[0], item[1].profile_id),
        )
        if not ranked:
            result.append(profile)
            continue
        best_score, best = ranked[0]
        next_score = ranked[1][0] if len(ranked) > 1 else 0.0
        # Exact/near-exact build matches need no margin; looser matches must
        # beat the next candidate so a local ID is not mislabeled.
        clear_match = best_score >= 0.72 or (best_score >= 0.52 and best_score - next_score >= 0.04)
        if clear_match:
            result.append(replace(profile, archetype=best.display_name, tier=best.tier))
        else:
            result.append(profile)
    return tuple(result)


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
    label_override: str = ""

    @property
    def label(self) -> str:
        return self.label_override or self.profile.name


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
        tier=meta_tier_label(item.get("tier") or item.get("category") or item.get("tier_name"), item.get("archetype")),
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
    checked_at: str = "",
    refresh_version: str = DEFAULT_META_REFRESH_VERSION,
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
            "tier": profile.tier,
        })
    temporary = target.with_suffix(target.suffix + ".tmp")
    document = {
        "schema_version": SCHEMA_VERSION,
        "source": source_url,
        "updated_at": updated_at,
        "profiles": items,
    }
    if checked_at:
        document["last_checked_at"] = checked_at
    if refresh_version:
        document["refresh_version"] = str(refresh_version)
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
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
            # Two cached builds can share every publicly played card.  In
            # that case an exact build would be a guess, but a shared
            # archetype is still useful to the match-history table.  Accept
            # the archetype only when the tied candidates all agree and the
            # next *different* archetype is clearly behind them.
            if not ranked:
                return None
            top = ranked[0]
            if top.observed_distinct < self.min_observed_distinct or top.confidence < self.min_confidence:
                return None
            archetype = str(top.profile.archetype or "").strip()
            if not archetype:
                return None
            tied = [
                item for item in ranked
                if abs(float(item.confidence) - float(top.confidence)) <= 0.0001
            ]
            if not tied or any(str(item.profile.archetype or "").strip() != archetype for item in tied):
                return None
            different = [
                item for item in ranked
                if str(item.profile.archetype or "").strip() != archetype
            ]
            next_score = max((float(item.confidence) for item in different), default=0.0)
            margin = round(float(top.confidence) - next_score, 4)
            if margin < self.min_margin:
                return None
            return replace(top, margin=margin, accepted=True, label_override=archetype)
        top = ranked[0]
        label = top.profile.display_name
        return replace(top, label_override=label) if label else top


__all__ = [
    "DEFAULT_SOURCE_URL",
    "DEFAULT_META_REFRESH_VERSION",
    "MetaDeckProfile",
    "meta_profile_from_saved_deck",
    "META_ARCHETYPE_TIERS",
    "META_LOCAL_ARCHETYPE_LABELS",
    "META_TIER_ORDER",
    "OpponentDeckMatch",
    "OpponentDeckMatcher",
    "canonicalize_meta_deck_labels",
    "default_meta_decks_path",
    "is_machine_meta_label",
    "load_session_opponent_observations",
    "load_meta_deck_profiles",
    "save_meta_deck_profiles",
    "meta_tier_label",
    "meta_archetype_label",
    "writable_meta_decks_path",
]
