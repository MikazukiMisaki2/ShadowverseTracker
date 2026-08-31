"""Standalone GUI for opponent key-card probability.

Run with ``python scripts/opponent_key_probability_app.py`` when Tracker is
not running. All fields are manual and use the same calculation module as the
integrated panel, so results remain reproducible.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shadowverse_tracker.opponent_key_probability import calculate_key_probability


def main() -> None:
    root = tk.Tk()
    root.title("Shadowverse 对手关键牌概率")
    root.geometry("650x260")
    fields = (
        ("牌库剩余", "29"), ("未知手牌", "6"), ("换牌数", "2"),
        ("留1类型", "5"), ("留2类型", "1"), ("已见留1", "2"),
        ("已见留2", "1"), ("Key投入", "3"), ("Key留牌上限", "1"), ("Key已见", "0"),
    )
    variables: dict[str, tk.StringVar] = {}
    frame = ttk.LabelFrame(root, text="手动输入")
    frame.pack(fill="x", padx=12, pady=12)
    for index, (label, default) in enumerate(fields):
        row, column = divmod(index, 5)
        ttk.Label(frame, text=label).grid(row=row * 2, column=column, padx=6, pady=(6, 0))
        variable = variables.setdefault(label, tk.StringVar(value=default))
        ttk.Entry(frame, textvariable=variable, width=10).grid(row=row * 2 + 1, column=column, padx=6, pady=(0, 6))
    strategy = tk.StringVar(value="unknown")
    ttk.Label(frame, text="策略").grid(row=4, column=0, padx=6, pady=(6, 0))
    ttk.Combobox(frame, textvariable=strategy, values=("known", "unknown"), state="readonly", width=8).grid(row=5, column=0, padx=6)
    result = tk.StringVar(value="填写参数后点击计算")

    def calculate() -> None:
        try:
            values = {label: int(variable.get()) for label, variable in variables.items()}
            answer = calculate_key_probability(
                deck_remaining=values["牌库剩余"], hand_size=values["未知手牌"], mulligan_swapped=values["换牌数"],
                keep1_types=values["留1类型"], keep2_types=values["留2类型"], seen_keep1=values["已见留1"],
                seen_keep2=values["已见留2"], key_copies=values["Key投入"], key_keep_limit=values["Key留牌上限"],
                key_seen=values["Key已见"], strategy=strategy.get(),
            )
        except ValueError:
            result.set("请输入整数")
            return
        result.set(f"{answer.percent:.2f}% — {answer.reason}" if answer.valid and answer.percent is not None else f"无法计算：{answer.reason}")

    ttk.Button(root, text="计算", command=calculate).pack(pady=(0, 8))
    ttk.Label(root, textvariable=result, wraplength=620).pack(fill="x", padx=12)
    root.mainloop()


if __name__ == "__main__":
    main()
