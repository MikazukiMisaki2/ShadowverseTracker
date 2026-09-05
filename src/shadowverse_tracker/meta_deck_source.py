"""Import concrete deck builds from the WBArts deck-square API.

The API is useful for refreshing the offline matcher cache, but it must not be
called from the 50 ms game polling loop.  WBArts is protected by Cloudflare on
some networks, so callers get a precise error and can keep using the last
known cache instead.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from typing import Iterable, Mapping

from .opponent_deck_matcher import (
    DEFAULT_META_REFRESH_VERSION,
    DEFAULT_SOURCE_URL,
    META_TIER_ORDER,
    MetaDeckProfile,
    _normalise_cards,
    canonicalize_meta_deck_labels,
    default_meta_decks_path,
    load_meta_deck_profiles,
    meta_tier_label,
    save_meta_deck_profiles,
    writable_meta_decks_path,
)


class MetaDeckSourceError(RuntimeError):
    """A refresh failed without invalidating the existing local cache."""


META_LIST_URLS = (
    # Do not pin the environment in the preferred requests; WBArts changes
    # the active environment over time.  The env=10009 variants remain as a
    # compatibility fallback for older deployments of the site.
    "https://sva.hypd.asia/api/decks?format=rotation&sort=recommended&days=7",
    "https://sva.hypd.asia/api/decks?format=rotation&sort=recommended",
    "https://sva.hypd.asia/api/deck?format=rotation&sort=recommended&days=7",
    "https://sva.hypd.asia/api/deck?format=rotation&sort=recommended",
    "https://sva.hypd.asia/api/decks?format=rotation&env=10009&sort=recommended&days=7",
    "https://sva.hypd.asia/api/decks?format=rotation&env=10009&sort=recommended",
    "https://sva.hypd.asia/api/deck?format=rotation&env=10009&sort=recommended&days=7",
    "https://sva.hypd.asia/api/deck?format=rotation&env=10009&sort=recommended",
    "https://sva.hypd.asia/api/decks?format=1&env=10009&sort=recommended&days=7",
    "https://sva.hypd.asia/api/decks?format=1&env=10009&sort=recommended",
)

META_CLASS_IDS = tuple(range(1, 8))
RECOMMENDED_DECKS_PER_CLASS = 3
META_REFRESH_VERSION = DEFAULT_META_REFRESH_VERSION

_CLASS_ALIASES = {
    "forest": 1,
    "forestcraft": 1,
    "elf": 1,
    "精灵": 1,
    "sword": 2,
    "swordcraft": 2,
    "royal": 2,
    "皇家护卫": 2,
    "rune": 3,
    "runecraft": 3,
    "witch": 3,
    "巫师": 3,
    "dragon": 4,
    "dragoncraft": 4,
    "龙族": 4,
    "nightmare": 5,
    "abyss": 5,
    "abysscraft": 5,
    "梦魇": 5,
    "haven": 6,
    "havencraft": 6,
    "bishop": 6,
    "主教": 6,
    "portal": 7,
    "portalcraft": 7,
    "nemesis": 7,
    "超越者": 7,
}


def _class_id(value: object) -> int | None:
    if isinstance(value, Mapping):
        value = value.get("id") or value.get("class_id") or value.get("name")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = _CLASS_ALIASES.get(str(value or "").strip().casefold())
    return parsed if isinstance(parsed, int) and 0 <= parsed <= 7 else None


def _deck_id(value: str | int) -> str:
    raw = str(value).strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        parts = [part for part in urlsplit(raw).path.split("/") if part]
        if len(parts) < 2 or parts[0].casefold() != "deck":
            raise MetaDeckSourceError("WBArts 链接应为 /deck/<id>")
        raw = parts[1]
    if not raw.isdigit() or int(raw) <= 0:
        raise MetaDeckSourceError(f"无效的 WBArts 卡组编号：{raw or '(空)'}")
    return raw


def _request_json(url: str, *, timeout: float) -> object:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            "Referer": DEFAULT_SOURCE_URL,
            "Origin": "https://sva.hypd.asia",
            "User-Agent": "ShadowverseTracker meta-deck cache refresh",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise MetaDeckSourceError(f"WBArts 卡组请求失败：{exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise MetaDeckSourceError(
            "WBArts 未返回 JSON（可能需要浏览器通过 Cloudflare 验证）；保留现有缓存"
        ) from exc


def _iter_deck_records(value: object) -> Iterable[Mapping[str, object]]:
    """Find deck records in the several list shapes used by WBArts builds."""
    if isinstance(value, Mapping):
        has_id = any(value.get(key) not in (None, "") for key in ("id", "deck_id", "deckId", "deck_code"))
        # List endpoints commonly return ID-only rows.  Keep those rows so
        # ``fetch_wbarts_meta_decks`` can request the concrete 40-card build
        # from the detail endpoint; wrappers without a deck identity are
        # traversed below instead of being mistaken for a profile.
        if has_id:
            yield value
        for key in ("deck", "decks", "items", "data", "results", "rows", "profiles"):
            child = value.get(key)
            if child is not None:
                yield from _iter_deck_records(child)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_deck_records(item)


def _record_id(value: Mapping[str, object]) -> str:
    for key in ("id", "deck_id", "deckId", "deck_code"):
        raw = value.get(key)
        if raw not in (None, ""):
            try:
                return _deck_id(str(raw))
            except MetaDeckSourceError:
                continue
    return ""


def _record_archetype(value: Mapping[str, object]) -> str:
    raw = (
        value.get("archetype")
        or value.get("archetype_name")
        or value.get("archetypeName")
        or value.get("deck_type")
        or value.get("deckType")
        or value.get("deck_category")
        or value.get("deckCategory")
        or value.get("meta_type")
        or value.get("metaType")
        or value.get("category_name")
        or value.get("categoryName")
        or value.get("meta_name")
        or value.get("metaName")
        or ""
    )
    if isinstance(raw, Mapping):
        raw = raw.get("name") or raw.get("label") or raw.get("title") or ""
    return str(raw or "").strip()


def _record_tier(value: Mapping[str, object]) -> str:
    raw = (
        value.get("tier")
        or value.get("tier_name")
        or value.get("tierName")
        or value.get("category")
        or value.get("category_name")
        or value.get("tier_id")
        or value.get("tierId")
        or value.get("rank")
        or value.get("meta_tier")
        or ""
    )
    if isinstance(raw, Mapping):
        raw = raw.get("name") or raw.get("label") or raw.get("tier") or raw.get("value") or ""
    return meta_tier_label(raw, _record_archetype(value))


def _record_class_id(value: Mapping[str, object]) -> int | None:
    raw = (
        value.get("class_id")
        or value.get("classId")
        or value.get("craft_id")
        or value.get("craftId")
        or value.get("craft")
        or value.get("class")
    )
    return _class_id(raw)


def _meta_list_urls(class_id: int | None = None) -> tuple[str, ...]:
    """Return API candidates, adding WBArts' class filter when requested."""
    if class_id is None:
        return META_LIST_URLS
    result: list[str] = []
    for url in META_LIST_URLS:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["class_id"] = str(int(class_id))
        query["limit"] = str(RECOMMENDED_DECKS_PER_CLASS)
        result.append(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)))
    return tuple(result)


def _fetch_meta_deck_list(
    *,
    timeout: float,
    class_id: int | None = None,
) -> tuple[Mapping[str, object], ...]:
    last_error: MetaDeckSourceError | None = None
    for url in _meta_list_urls(class_id):
        try:
            payload = _request_json(url, timeout=timeout)
        except MetaDeckSourceError as exc:
            last_error = exc
            continue
        records: list[Mapping[str, object]] = []
        seen: set[str] = set()
        for item in _iter_deck_records(payload):
            deck_id = _record_id(item)
            if not deck_id or deck_id in seen:
                continue
            seen.add(deck_id)
            records.append(item)
        if records:
            return tuple(records)
    raise last_error or MetaDeckSourceError("WBArts 未返回可用的 Meta 卡组列表")


def parse_wbarts_deck_payload(
    payload: object,
    *,
    fallback_id: str | int = "",
    source_url: str = DEFAULT_SOURCE_URL,
    name: str = "",
    tier: str = "",
) -> MetaDeckProfile:
    """Convert ``GET /api/decks/<id>`` JSON into a matcher profile."""
    if not isinstance(payload, dict):
        raise MetaDeckSourceError("WBArts 返回的卡组数据不是 JSON 对象")
    deck = payload.get("deck", payload)
    for _ in range(3):
        if not isinstance(deck, dict) or any(
            deck.get(key) not in (None, "")
            for key in ("id", "deck_id", "deckId", "cards", "deck_cards", "card_list")
        ):
            break
        nested = next(
            (deck.get(key) for key in ("deck", "data", "result", "item") if isinstance(deck.get(key), dict)),
            None,
        )
        if not isinstance(nested, dict):
            break
        deck = nested
    if not isinstance(deck, dict):
        raise MetaDeckSourceError("WBArts 返回中缺少 deck 对象")
    profile_id = str(
        deck.get("id") or deck.get("deck_id") or deck.get("deckId") or fallback_id or ""
    ).strip()
    archetype = str(
        _record_archetype(deck)
        or deck.get("archetype")
        or deck.get("deck_type")
        or deck.get("category_name")
        or ""
    ).strip()
    deck_name = str(
        name
        or deck.get("name")
        or deck.get("title")
        or deck.get("label")
        or archetype
        or deck.get("source_name")
        or ""
    ).strip()
    class_id = _class_id(deck.get("class_id") or deck.get("classId") or deck.get("craft") or deck.get("class"))
    if class_id is None:
        raise MetaDeckSourceError("WBArts 卡组缺少有效职业编号")
    if not profile_id or not deck_name:
        raise MetaDeckSourceError("WBArts 卡组基本字段不完整")
    cards = (
        deck.get("cards")
        or deck.get("deck_cards")
        or deck.get("card_list")
        or deck.get("main_deck")
        or deck.get("decklist")
    )
    if isinstance(cards, Mapping):
        nested_cards = cards.get("cards") or cards.get("items") or cards.get("list")
        if isinstance(nested_cards, (dict, list, tuple)):
            cards = nested_cards
    if not isinstance(cards, (dict, list, tuple)):
        raise MetaDeckSourceError("WBArts 卡组缺少 cards 字段")
    profile = MetaDeckProfile(
        profile_id=f"wbarts-{profile_id}",
        name=deck_name,
        class_id=class_id,
        cards=_normalise_cards(cards),
        format=str(deck.get("format") or deck.get("format_id") or "rotation"),
        archetype=archetype or name,
        source_url=source_url,
        official_url=str(deck.get("official_url") or deck.get("portal_url") or ""),
        updated_at=str(deck.get("updated_at") or ""),
        tier=meta_tier_label(
            tier
            or deck.get("tier")
            or deck.get("tier_name")
            or deck.get("tierName")
            or deck.get("category")
            or deck.get("rank"),
            archetype or name,
        ),
    )
    if profile.total_cards != 40:
        raise MetaDeckSourceError(f"WBArts 卡组应为 40 张，实际为 {profile.total_cards} 张")
    return profile


def fetch_wbarts_deck(
    value: str | int,
    *,
    timeout: float = 15.0,
    name: str = "",
    tier: str = "",
) -> MetaDeckProfile:
    """Fetch one profile for a cache-refresh command, never for live polling."""
    deck_id = _deck_id(value)
    source_url = f"{DEFAULT_SOURCE_URL}/{deck_id}"
    last_error: MetaDeckSourceError | None = None
    for endpoint in (f"https://sva.hypd.asia/api/decks/{deck_id}", f"https://sva.hypd.asia/api/deck/{deck_id}"):
        try:
            payload = _request_json(endpoint, timeout=timeout)
            return parse_wbarts_deck_payload(
                payload,
                fallback_id=deck_id,
                source_url=source_url,
                name=name,
                tier=tier,
            )
        except MetaDeckSourceError as exc:
            last_error = exc
    raise last_error or MetaDeckSourceError("WBArts 卡组详情请求失败")


def fetch_wbarts_meta_decks(
    *,
    timeout: float = 15.0,
    max_profiles: int = 120,
    recommended_per_class: int = RECOMMENDED_DECKS_PER_CLASS,
    class_ids: Iterable[int] = META_CLASS_IDS,
) -> tuple[MetaDeckProfile, ...]:
    """Fetch the recommended concrete builds for every SVWB class.

    WBArts applies the class buttons with ``class_id=1`` … ``class_id=7``.
    Querying those seven lists gives the same top recommendations a user sees
    after clicking each class, while keeping the local cache small (three
    concrete builds per class).  The list endpoint has changed response
    wrappers over time, so the parser accepts both embedded full deck objects
    and ID-only rows.  A single broken row is skipped; the caller can keep the
    previous cache unless no valid profile was returned at all.
    """
    profiles: list[MetaDeckProfile] = []
    seen: set[str] = set()
    failures: list[MetaDeckSourceError] = []
    covered_classes: set[int] = set()
    per_class = max(1, int(recommended_per_class))
    limit = max(1, int(max_profiles))

    def add_records(records: Iterable[Mapping[str, object]], expected_class: int | None) -> None:
        added_for_class = 0
        # Keep a little headroom when an ID-only list contains rows from more
        # than one class; the detail response is the final class authority.
        for item in records:
            if len(profiles) >= limit or added_for_class >= per_class:
                break
            listed_class = _record_class_id(item)
            if expected_class is not None and listed_class is not None and listed_class != expected_class:
                continue
            deck_id = _record_id(item)
            if not deck_id or deck_id in seen:
                continue
            try:
                profile = parse_wbarts_deck_payload(
                    item,
                    fallback_id=deck_id,
                    source_url=f"{DEFAULT_SOURCE_URL}/{deck_id}",
                    name=_record_archetype(item),
                    tier=_record_tier(item),
                )
            except MetaDeckSourceError:
                try:
                    profile = fetch_wbarts_deck(
                        deck_id,
                        timeout=timeout,
                        name=_record_archetype(item),
                        tier=_record_tier(item),
                    )
                except MetaDeckSourceError:
                    continue
            if expected_class is not None and int(profile.class_id) != int(expected_class):
                continue
            seen.add(deck_id)
            profiles.append(profile)
            added_for_class += 1
            if expected_class is not None:
                covered_classes.add(int(expected_class))

    normalized_classes: list[int] = []
    for value in class_ids:
        try:
            class_id = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= class_id <= 7 and class_id not in normalized_classes:
            normalized_classes.append(class_id)
    for class_id in normalized_classes:
        if len(profiles) >= limit:
            break
        try:
            records = _fetch_meta_deck_list(timeout=timeout, class_id=class_id)
        except MetaDeckSourceError as exc:
            failures.append(exc)
            continue
        add_records(records, class_id)

    # Older deployments exposed only an unfiltered list endpoint.  Use it as
    # a compatibility fallback and retain only the first recommended rows per
    # class; this path also lets a partial class-query failure still populate
    # the remaining classes when the service is available.
    if normalized_classes and (
        not profiles or any(class_id not in covered_classes for class_id in normalized_classes)
    ):
        try:
            records = _fetch_meta_deck_list(timeout=timeout)
        except MetaDeckSourceError as exc:
            failures.append(exc)
        else:
            for class_id in normalized_classes:
                if len(profiles) >= limit:
                    break
                add_records(records, class_id)

    if not profiles:
        raise failures[-1] if failures else MetaDeckSourceError(
            "WBArts Meta 列表中没有可用的 40 张牌组"
        )
    return tuple(sorted(profiles, key=lambda profile: (profile.class_id, profile.name, profile.profile_id)))


def _preserve_minimum_class_coverage(
    fresh: Iterable[MetaDeckProfile],
    existing: Iterable[MetaDeckProfile],
    *,
    minimum: int = 2,
) -> tuple[MetaDeckProfile, ...]:
    """Keep at least two concrete builds per class during partial refreshes."""
    result = list(fresh)
    seen = {profile.profile_id for profile in result}
    minimum = max(1, int(minimum))
    for class_id in range(1, 8):
        current = sum(1 for profile in result if int(profile.class_id) == class_id)
        if current >= minimum:
            continue
        for profile in existing:
            if profile.profile_id in seen or int(profile.class_id) != class_id:
                continue
            result.append(profile)
            seen.add(profile.profile_id)
            current += 1
            if current >= minimum:
                break
    return tuple(sorted(result, key=lambda profile: (META_TIER_ORDER.index(profile.tier) if profile.tier in META_TIER_ORDER else len(META_TIER_ORDER), profile.class_id, profile.display_name, profile.profile_id)))


def refresh_wbarts_cache(
    deck_ids: list[str | int],
    *,
    path: Path | None = None,
    timeout: float = 15.0,
) -> tuple[MetaDeckProfile, ...]:
    """Refresh selected IDs and atomically save them beside the app cache."""
    existing = {profile.profile_id: profile for profile in load_meta_deck_profiles(path)}
    for deck_id in deck_ids:
        profile = fetch_wbarts_deck(deck_id, timeout=timeout)
        existing[profile.profile_id] = profile
    profiles = tuple(existing[key] for key in sorted(existing))
    save_meta_deck_profiles(
        profiles,
        path,
        source_url=DEFAULT_SOURCE_URL,
        refresh_version="",
    )
    return profiles


def _cache_document(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def refresh_wbarts_meta_cache_daily(
    *,
    path: Path | None = None,
    timeout: float = 15.0,
    max_profiles: int = 120,
    now: datetime | None = None,
) -> tuple[tuple[MetaDeckProfile, ...], str]:
    """Refresh the Meta cache at most once per local calendar day.

    Returns ``(profiles, status)``.  ``status`` is ``updated``, ``skipped`` or
    a human-readable failure string.  A failed attempt is timestamped too, so
    repeatedly opening the app during a Cloudflare/network outage does not
    hammer WBArts; the previous cache remains available.
    """
    # The once-per-day boundary follows the user's local calendar rather than
    # UTC (otherwise an app opened around midnight could refresh twice on the
    # same local day or skip a day entirely).
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    target = Path(path) if path is not None else writable_meta_decks_path()
    source = target if target.is_file() else default_meta_decks_path()
    existing = load_meta_deck_profiles(source)
    bundled_path = Path(__file__).resolve().parent / "data" / "meta_decks.json"
    references = load_meta_deck_profiles(bundled_path) if bundled_path.is_file() else ()
    labelled_existing = canonicalize_meta_deck_labels(existing, references)
    document = _cache_document(source)
    today = current.date().isoformat()
    last_checked = str(document.get("last_checked_at") or "")
    refresh_version = str(document.get("refresh_version") or "")
    if last_checked[:10] == today and refresh_version == META_REFRESH_VERSION:
        if labelled_existing != existing:
            save_meta_deck_profiles(
                labelled_existing,
                target,
                source_url=DEFAULT_SOURCE_URL,
                updated_at=str(document.get("updated_at") or ""),
                checked_at=last_checked,
                refresh_version=META_REFRESH_VERSION,
            )
        return labelled_existing, "skipped"

    checked_at = current.astimezone(timezone.utc).isoformat()
    old_updated = str(document.get("updated_at") or "")
    # Persist the check marker before networking.  If the request fails, this
    # file still contains the prior profiles and will not retry until tomorrow.
    save_meta_deck_profiles(
        labelled_existing,
        target,
        source_url=DEFAULT_SOURCE_URL,
        updated_at=old_updated,
        checked_at=checked_at,
        refresh_version=META_REFRESH_VERSION,
    )
    try:
        profiles = _preserve_minimum_class_coverage(
            canonicalize_meta_deck_labels(
                fetch_wbarts_meta_decks(timeout=timeout, max_profiles=max_profiles),
                references or labelled_existing,
            ),
            labelled_existing,
        )
    except MetaDeckSourceError as exc:
        return labelled_existing, f"failed: {exc}"
    save_meta_deck_profiles(
        profiles,
        target,
        source_url=DEFAULT_SOURCE_URL,
        updated_at=today,
        checked_at=checked_at,
        refresh_version=META_REFRESH_VERSION,
    )
    return profiles, "updated"


__all__ = [
    "META_CLASS_IDS",
    "META_REFRESH_VERSION",
    "RECOMMENDED_DECKS_PER_CLASS",
    "MetaDeckSourceError",
    "fetch_wbarts_deck",
    "fetch_wbarts_meta_decks",
    "parse_wbarts_deck_payload",
    "refresh_wbarts_cache",
    "refresh_wbarts_meta_cache_daily",
]
