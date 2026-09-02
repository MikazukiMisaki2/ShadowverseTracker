"""Optional loader for the sibling LethalCalculator project.

The tracker remains usable without the calculator.  When a checkout of
``LethalCalculator`` is available, this module loads its public
``TrackerLethalSession`` boundary and generated catalog/rules without making
the tracker package depend on a second distribution.  A UI caller can show
the returned message when the optional solver is unavailable or malformed.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any


@dataclass(frozen=True)
class LethalBridge:
    """Loaded calculator session plus the source checkout used for it."""

    session: Any
    root: Path

    def refresh(self, snapshot: dict[str, object]) -> Any:
        return self.session.refresh(snapshot)


def _candidate_roots(explicit_root: str | os.PathLike[str] | None = None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if explicit_root:
        # An explicit root is an override, not merely a hint.  This keeps a
        # typo or an intentionally isolated test from silently loading a
        # different checkout discovered through the environment/defaults.
        return (Path(explicit_root).resolve(),)
    for env_name in ("SHADOWVERSE_LETHAL_ROOT", "LETHAL_CALCULATOR_ROOT"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))
    # ``.../Github/ShadowverseTracker/src/shadowverse_tracker`` -> sibling
    # checkout ``.../Github/LethalCalculator``.
    candidates.append(Path(__file__).resolve().parents[3] / "LethalCalculator")
    candidates.append(Path.cwd() / "LethalCalculator")
    return tuple(dict.fromkeys(path.resolve() for path in candidates))


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def create_lethal_bridge(
    *,
    root: str | os.PathLike[str] | None = None,
    max_depth: int = 12,
) -> tuple[LethalBridge | None, str]:
    """Try to construct the optional calculator session.

    Returns ``(bridge, message)``.  The message is intentionally suitable for
    a status panel and does not raise on a missing checkout or malformed
    generated data.
    """
    errors: list[str] = []
    for candidate in _candidate_roots(root):
        integration = candidate / "tracker_integration.py"
        if not integration.is_file():
            continue
        catalog_path = next(
            (
                path
                for path in (
                    candidate / "data" / "generated" / "card_catalog.json",
                    candidate / "card_catalog.json",
                )
                if path.is_file()
            ),
            None,
        )
        rules_path = next(
            (
                path
                for path in (
                    candidate / "data" / "generated" / "card_rules_v2.json",
                    candidate / "card_rules.json",
                )
                if path.is_file()
            ),
            None,
        )
        if catalog_path is None or rules_path is None:
            errors.append(f"{candidate}: missing generated catalog/rules")
            continue
        try:
            # LethalCalculator modules use absolute intra-project imports
            # (``lethal_engine``, ``snapshot_adapter``), so its checkout must
            # be first on sys.path while importing the integration boundary.
            candidate_text = str(candidate)
            if candidate_text not in sys.path:
                sys.path.insert(0, candidate_text)
            module = importlib.import_module("tracker_integration")
            session_type = getattr(module, "TrackerLethalSession")
            catalog = _load_json(catalog_path)
            rules = _load_json(rules_path)
            session = session_type(catalog=catalog, rules=rules, max_depth=max_depth)
            return LethalBridge(session=session, root=candidate), f"已加载斩杀计算器：{candidate}"
        except Exception as exc:  # optional integration must fail closed
            errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
    if errors:
        return None, "斩杀计算器不可用；" + "；".join(errors)
    return None, "未找到 LethalCalculator（可设置 SHADOWVERSE_LETHAL_ROOT）"


__all__ = ["LethalBridge", "create_lethal_bridge"]
