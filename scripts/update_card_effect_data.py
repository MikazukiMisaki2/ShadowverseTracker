#!/usr/bin/env python3
"""Download the official simplified-Chinese card library for local analysis.

The generated file intentionally retains only the fields useful to the
tracker and offline training tools: card identity, type, token relations and
ability text.  It does not attempt to guess whether a conditional effect
actually resolved during a match.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "src" / "shadowverse_tracker" / "data" / "card_effects_chs.json"
ENDPOINT = "https://shadowverse-wb.com/web/CardList/cardList"
PAGE_STEP = 30


def fetch_page(offset: int) -> dict[str, object]:
    query = urlencode(
        {
            "offset": offset,
            "class": "0,1,2,3,4,5,6,7",
            "cost": "0,1,2,3,4,5,6,7,8,9,10",
            "lang": "chs",
        }
    )
    request = Request(
        f"{ENDPOINT}?{query}",
        headers={
            "User-Agent": "ShadowverseTracker/0.1 (+local card-effect cache)",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://shadowverse-wb.com/en/deck/cardslist/",
            "lang": "chs",
        },
    )
    with urlopen(request, timeout=30) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"unexpected response at offset {offset}")
    return value


def compact_page(
    response: dict[str, object],
    cards: dict[str, dict[str, object]],
) -> int:
    data = response.get("data")
    if not isinstance(data, dict):
        return 0
    relations = data.get("cards")
    details = data.get("card_details")
    if not isinstance(relations, dict):
        relations = {}
    if not isinstance(details, dict):
        return 0
    for raw_id, item in details.items():
        if not isinstance(item, dict):
            continue
        common = item.get("common")
        if not isinstance(common, dict):
            continue
        try:
            card_id = int(common["card_id"])
        except (KeyError, TypeError, ValueError):
            continue
        relation = relations.get(str(card_id), {})
        if not isinstance(relation, dict):
            relation = {}
        cards[str(card_id)] = {
            "card_id": card_id,
            "base_card_id": int(common.get("base_card_id") or card_id),
            "name": str(common.get("name") or ""),
            "skill_text": str(common.get("skill_text") or ""),
            "evo_skill_text": str((item.get("evo") or {}).get("skill_text") or ""),
            "type": int(common.get("type") or 0),
            "class_id": int(common.get("class") or 0),
            "cost": int(common.get("cost") or 0),
            "is_token": bool(common.get("is_token")),
            "related_card_ids": [
                int(value)
                for value in relation.get("related_card_ids", [])
                if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
            ],
            "specific_effect_card_ids": [
                int(value)
                for value in relation.get("specific_effect_card_ids", [])
                if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
            ],
        }
    return len(details)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=0.2, help="seconds between requests")
    args = parser.parse_args()
    if args.delay < 0:
        raise SystemExit("--delay must be non-negative")

    cards: dict[str, dict[str, object]] = {}
    empty_pages = 0
    offset = 0
    while empty_pages < 3:
        response = fetch_page(offset)
        count = compact_page(response, cards)
        print(f"offset={offset}: {count} records, {len(cards)} unique cards")
        empty_pages = empty_pages + 1 if count == 0 else 0
        offset += PAGE_STEP
        if empty_pages < 3:
            time.sleep(args.delay)

    output = {
        "source": ENDPOINT,
        "language": "chs",
        "cards": cards,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(cards)} cards to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
