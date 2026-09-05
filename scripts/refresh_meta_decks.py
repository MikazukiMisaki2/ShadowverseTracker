"""Refresh the offline opponent-deck matcher cache from WBArts.

Example::

    python scripts/refresh_meta_decks.py 13337 150502

The command is intentionally separate from the tracker process.  If WBArts
returns a browser/Cloudflare challenge, the existing cache is left untouched.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shadowverse_tracker.meta_deck_source import MetaDeckSourceError, refresh_wbarts_cache


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新 WBArts 主流卡组缓存")
    parser.add_argument("deck_ids", nargs="+", help="WBArts 卡组编号或 /deck/<id> 链接")
    parser.add_argument("--output", type=Path, help="覆盖缓存文件路径")
    parser.add_argument("--timeout", type=float, default=15.0, help="单个请求超时秒数")
    args = parser.parse_args()
    try:
        profiles = refresh_wbarts_cache(args.deck_ids, path=args.output, timeout=args.timeout)
    except MetaDeckSourceError as exc:
        print(f"刷新失败：{exc}", file=sys.stderr)
        return 2
    print(f"已保存 {len(profiles)} 套卡组：{args.output or '默认缓存'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
