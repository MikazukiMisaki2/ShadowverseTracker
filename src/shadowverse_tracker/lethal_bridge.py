"""Optional loader for the sibling LethalCalculator project.

The tracker remains usable without the calculator.  When a checkout of
``LethalCalculator`` is available, this module loads its public
``TrackerLethalSession`` boundary and generated catalog/rules without making
the tracker package depend on a second distribution.  The default backend is
CardRules v2; an explicit ``swb_rl_shadow`` backend can hydrate the visible
snapshot into SWB-RL while conservatively reporting missing hidden state.
A UI caller can show the returned message when the optional solver is
unavailable or malformed.
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
    backend: str = "card_rules_v2"

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
    node_limit: int = 10_000,
    backend: str | None = None,
    swb_rl_root: str | os.PathLike[str] | None = None,
) -> tuple[LethalBridge | None, str]:
    """Try to construct the optional calculator session.

    Returns ``(bridge, message)``.  The message is intentionally suitable for
    a status panel and does not raise on a missing checkout or malformed
    generated data.  ``backend`` defaults to ``SHADOWVERSE_LETHAL_BACKEND``
    (or ``card_rules_v2`` when unset).  The shadow backend additionally reads
    ``SHADOWVERSE_SWB_RL_ROOT`` when no explicit root is supplied.
    """
    errors: list[str] = []
    selected_backend = str(
        backend
        if backend is not None
        else os.environ.get("SHADOWVERSE_LETHAL_BACKEND", "card_rules_v2")
    ).strip().casefold().replace("-", "_")
    backend_aliases = {
        "card_rules_v2": "card_rules_v2",
        "card_rules": "card_rules_v2",
        "rules": "card_rules_v2",
        "default": "card_rules_v2",
        "swb_rl_shadow": "swb_rl_shadow",
        "swb_rl": "swb_rl_shadow",
        "shadow": "swb_rl_shadow",
        "shadow_state": "swb_rl_shadow",
    }
    selected_backend = backend_aliases.get(selected_backend, "")
    if not selected_backend:
        return None, (
            "斩杀计算器不可用；未知后端："
            f"{backend!r}（可选 card_rules_v2 或 swb_rl_shadow）"
        )
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
        if selected_backend == "card_rules_v2" and (catalog_path is None or rules_path is None):
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
            if selected_backend == "swb_rl_shadow":
                session_type = getattr(module, "TrackerShadowLethalSession")
            else:
                session_type = getattr(module, "TrackerLethalSession")
            # The shadow backend executes SWB-RL definitions directly.  The
            # generated v2 files are still useful for Tracker names/evolution
            # aliases, but are optional so an old/incomplete calculator
            # checkout does not prevent a native-rule experiment.
            catalog = _load_json(catalog_path) if catalog_path is not None else {}
            rules = _load_json(rules_path) if rules_path is not None else {}
            session_kwargs: dict[str, Any] = {
                "catalog": catalog,
                "rules": rules,
                "max_depth": max_depth,
            }
            if selected_backend == "swb_rl_shadow":
                resolved_swb_root = swb_rl_root
                if resolved_swb_root is None:
                    env_root = os.environ.get("SHADOWVERSE_SWB_RL_ROOT") or os.environ.get("SWB_RL_ROOT")
                    resolved_swb_root = env_root or candidate.parent / "SWB-RL"
                session_kwargs.update(
                    {
                        "node_limit": max(1, int(node_limit)),
                        "swb_rl_root": resolved_swb_root,
                    }
                )
            session = session_type(**session_kwargs)
            if selected_backend == "swb_rl_shadow":
                message = (
                    "已加载 SWB-RL 影子斩杀计算器："
                    f"{candidate}（隐藏牌库/顺序缺失时结果为 INCOMPLETE）"
                )
                if catalog_path is None or rules_path is None:
                    message += "；未找到 v2 catalog/rules，部分名称/旧快照兼容性有限"
            else:
                message = f"已加载斩杀计算器：{candidate}"
            return LethalBridge(session=session, root=candidate, backend=selected_backend), message
        except Exception as exc:  # optional integration must fail closed
            errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
    if errors:
        return None, "斩杀计算器不可用；" + "；".join(errors)
    return None, "未找到 LethalCalculator（可设置 SHADOWVERSE_LETHAL_ROOT）"


__all__ = ["LethalBridge", "create_lethal_bridge"]
