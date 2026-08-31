"""Parse official Shadowverse WB deck-detail links and hashes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from urllib.parse import parse_qs, urlsplit

from .memory.deck import DeckCard, EXPECTED_DECK_SIZE, MAX_DECK_COPIES


SHORTCODE_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
OFFICIAL_HOSTS = {"shadowverse-wb.com", "www.shadowverse-wb.com"}


class OfficialDeckError(ValueError):
    pass


@dataclass(frozen=True)
class OfficialDeck:
    format_version: int
    class_id: int
    cards: tuple[DeckCard, ...]
    source: str

    @property
    def total_cards(self) -> int:
        return sum(card.count for card in self.cards)


def decode_shortcode(value: str) -> int:
    token = str(value or "").strip()
    if len(token) != 4 or any(character not in SHORTCODE_ALPHABET for character in token):
        raise OfficialDeckError(f"无效的卡牌短码：{token or '(空)'}")
    result = 0
    for character in token:
        result = (result << 6) | SHORTCODE_ALPHABET.index(character)
    return result


def _extract_hash(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        raise OfficialDeckError("请粘贴官方牌组链接或 hash")
    if "://" not in raw:
        return (raw[5:].strip() if raw.startswith("hash=") else raw), raw
    parsed = urlsplit(raw)
    if str(parsed.hostname or "").casefold() not in OFFICIAL_HOSTS:
        raise OfficialDeckError("只支持 shadowverse-wb.com 官方牌组链接")
    if not parsed.path.rstrip("/").casefold().endswith("/deck/detail"):
        raise OfficialDeckError("该链接不是官方牌组详情页")
    hashes = parse_qs(parsed.query, keep_blank_values=False).get("hash", ())
    if not hashes:
        raise OfficialDeckError("官方牌组链接缺少 hash 参数")
    return str(hashes[0]).strip(), raw


def build_official_deck(
    format_version: int, class_id: int, card_ids: tuple[int, ...], source: str
) -> OfficialDeck:
    if format_version <= 0 or not 0 <= class_id <= 7:
        raise OfficialDeckError("官方牌组版本或职业编号无效")
    if len(card_ids) != EXPECTED_DECK_SIZE:
        raise OfficialDeckError(
            f"官方构筑应为 {EXPECTED_DECK_SIZE} 张，链接中实际有 {len(card_ids)} 张"
        )
    counts = Counter(card_ids)
    excessive = [card_id for card_id, count in counts.items() if count > MAX_DECK_COPIES]
    if excessive:
        raise OfficialDeckError(f"卡牌 {excessive[0]} 超过三张上限")
    cards: list[DeckCard] = []
    seen: set[int] = set()
    for card_id in card_ids:
        if card_id <= 0:
            raise OfficialDeckError("牌组中存在无效 CardId")
        if card_id not in seen:
            seen.add(card_id)
            cards.append(DeckCard(card_id=card_id, count=counts[card_id]))
    return OfficialDeck(
        format_version=format_version,
        class_id=class_id,
        cards=tuple(cards),
        source=source,
    )


def parse_official_deck(value: str) -> OfficialDeck:
    deck_hash, source = _extract_hash(value)
    parts = deck_hash.split(".")
    if len(parts) < 3:
        raise OfficialDeckError("官方牌组 hash 格式不完整")
    try:
        format_version = int(parts[0])
        class_id = int(parts[1])
    except ValueError as exc:
        raise OfficialDeckError("官方牌组 hash 头部无效") from exc
    return build_official_deck(
        format_version, class_id, tuple(decode_shortcode(part) for part in parts[2:]), source
    )


def _find_card_id_list(value: object) -> tuple[int, ...] | None:
    if isinstance(value, list):
        ids = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("card_id") or item.get("cardId")
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                ids = []
                break
        if len(ids) == EXPECTED_DECK_SIZE and all(item > 0 for item in ids):
            return tuple(ids)
        for item in value:
            found = _find_card_id_list(item)
            if found:
                return found
    elif isinstance(value, dict):
        for item in value.values():
            found = _find_card_id_list(item)
            if found:
                return found
    return None


def _expand_deck_card_num(value: object) -> tuple[int, ...] | None:
    """Turn the official API's {card_id: copies} object into its 40 cards."""
    if not isinstance(value, dict):
        return None
    card_ids: list[int] = []
    try:
        for raw_card_id, raw_count in value.items():
            card_id = int(raw_card_id)
            count = int(raw_count)
            if card_id <= 0 or count <= 0:
                return None
            card_ids.extend([card_id] * count)
    except (TypeError, ValueError):
        return None
    return tuple(card_ids) if len(card_ids) == EXPECTED_DECK_SIZE else None


def import_deck_code(value: str) -> OfficialDeck:
    """Resolve a short-lived four-character official deck code online."""
    code = str(value or "").strip()
    if len(code) != 4 or any(character not in SHORTCODE_ALPHABET for character in code):
        raise OfficialDeckError("牌组代码应为 4 位字母、数字或 -_ 字符")
    builder_url = "https://shadowverse-wb.com/chs/deck/build/"
    api_url = "https://shadowverse-wb.com/web/DeckCode/getDeck"
    # The web client sends this request as a form POST.  A GET returns the
    # generic 1000 response even for a valid code, which made short codes look
    # as though they had expired.
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    request = Request(
        api_url,
        data=urlencode({"deck_code": code}).encode("ascii"),
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Lang": "chs",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": builder_url,
            "User-Agent": "ShadowverseTracker/1.0",
        },
        method="POST",
    )
    try:
        # Visiting the builder first establishes the same session context as
        # the official page.  The endpoint accepts an empty CSRF token today,
        # but keeping the session makes this resilient to that changing.
        with opener.open(Request(builder_url, headers={"User-Agent": "ShadowverseTracker/1.0"}), timeout=10):
            pass
        with opener.open(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, HTTPError, URLError) as exc:
        raise OfficialDeckError(f"牌组代码查询失败：{exc}") from exc
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    headers = payload.get("data_headers", {}) if isinstance(payload, dict) else {}
    if not isinstance(data, dict) or int(headers.get("result_code", 0)) != 1:
        raise OfficialDeckError("牌组代码无效或已过期，请在生成后 3 分钟内导入")
    card_ids = _expand_deck_card_num(data.get("deck_card_num")) or _find_card_id_list(data)
    if card_ids is None:
        raise OfficialDeckError("官方临时代码未返回完整牌表，请改用官方链接")
    try:
        return build_official_deck(
            int(data.get("battle_format") or data.get("format_version")),
            int(data.get("class_id")),
            card_ids,
            f"deck-code:{code}",
        )
    except (TypeError, ValueError) as exc:
        raise OfficialDeckError("官方临时代码返回格式无法识别") from exc
