"""Import concrete deck builds from the WBArts deck-square API.

The API is useful for refreshing the offline matcher cache, but it must not be
called from the 50 ms game polling loop.  WBArts is protected by Cloudflare on
some networks, so callers get a precise error and can keep using the last
known cache instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .opponent_deck_matcher import (
    DEFAULT_SOURCE_URL,
    MetaDeckProfile,
    _normalise_cards,
    load_meta_deck_profiles,
    save_meta_deck_profiles,
)


class MetaDeckSourceError(RuntimeError):
    """A refresh failed without invalidating the existing local cache."""


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


def parse_wbarts_deck_payload(
    payload: object,
    *,
    fallback_id: str | int = "",
    source_url: str = DEFAULT_SOURCE_URL,
    name: str = "",
) -> MetaDeckProfile:
    """Convert ``GET /api/decks/<id>`` JSON into a matcher profile."""
    if not isinstance(payload, dict):
        raise MetaDeckSourceError("WBArts 返回的卡组数据不是 JSON 对象")
    deck = payload.get("deck", payload)
    if not isinstance(deck, dict):
        raise MetaDeckSourceError("WBArts 返回中缺少 deck 对象")
    profile_id = str(deck.get("id") or fallback_id or "").strip()
    deck_name = str(name or deck.get("name") or deck.get("archetype") or "").strip()
    try:
        class_id = int(deck.get("class_id"))
    except (TypeError, ValueError) as exc:
        raise MetaDeckSourceError("WBArts 卡组缺少有效职业编号") from exc
    if not profile_id or not deck_name or not 0 <= class_id <= 7:
        raise MetaDeckSourceError("WBArts 卡组基本字段不完整")
    cards = deck.get("cards")
    if not isinstance(cards, (dict, list, tuple)):
        raise MetaDeckSourceError("WBArts 卡组缺少 cards 字段")
    profile = MetaDeckProfile(
        profile_id=f"wbarts-{profile_id}",
        name=deck_name,
        class_id=class_id,
        cards=_normalise_cards(cards),
        format=str(deck.get("format") or "rotation"),
        archetype=str(deck.get("archetype") or ""),
        source_url=source_url,
        official_url=str(deck.get("official_url") or deck.get("portal_url") or ""),
        updated_at=str(deck.get("updated_at") or ""),
    )
    if profile.total_cards != 40:
        raise MetaDeckSourceError(f"WBArts 卡组应为 40 张，实际为 {profile.total_cards} 张")
    return profile


def fetch_wbarts_deck(
    value: str | int,
    *,
    timeout: float = 15.0,
) -> MetaDeckProfile:
    """Fetch one profile for a cache-refresh command, never for live polling."""
    deck_id = _deck_id(value)
    source_url = f"{DEFAULT_SOURCE_URL}/{deck_id}"
    request = Request(
        f"https://sva.hypd.asia/api/decks/{deck_id}",
        headers={
            "Accept": "application/json",
            "User-Agent": "ShadowverseTracker meta-deck cache refresh",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise MetaDeckSourceError(f"WBArts 卡组请求失败：{exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise MetaDeckSourceError(
            "WBArts 未返回 JSON（可能需要浏览器通过 Cloudflare 验证）；保留现有缓存"
        ) from exc
    return parse_wbarts_deck_payload(payload, fallback_id=deck_id, source_url=source_url)


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
    save_meta_deck_profiles(profiles, path, source_url=DEFAULT_SOURCE_URL)
    return profiles


__all__ = [
    "MetaDeckSourceError",
    "fetch_wbarts_deck",
    "parse_wbarts_deck_payload",
    "refresh_wbarts_cache",
]
