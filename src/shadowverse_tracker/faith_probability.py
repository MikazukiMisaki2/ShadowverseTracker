"""Probability helpers for 天晶深渊's faith allocation effect."""

from __future__ import annotations

from math import comb, fsum


def calculate_faith_damage_probability(faith_total: int, minimum_damage: int) -> float:
    """Return ``P(Z >= minimum_damage)`` for ``N = X + Y + Z`` faith points.

    Each faith point is independently assigned to X, Y, or Z with probability
    ``1/3``.  Therefore the damage component is ``Z ~ Binomial(N, 1/3)`` and
    the tail probability is the sum of the corresponding binomial masses.
    """
    if not isinstance(faith_total, int) or isinstance(faith_total, bool):
        raise ValueError("信仰总值必须是整数")
    if not isinstance(minimum_damage, int) or isinstance(minimum_damage, bool):
        raise ValueError("Z下限必须是整数")
    if faith_total < 0:
        raise ValueError("信仰总值不能为负数")
    if minimum_damage < 0:
        raise ValueError("Z下限不能为负数")
    if minimum_damage == 0:
        return 1.0
    if minimum_damage > faith_total:
        return 0.0

    probability = fsum(
        comb(faith_total, z)
        * (1.0 / 3.0) ** z
        * (2.0 / 3.0) ** (faith_total - z)
        for z in range(minimum_damage, faith_total + 1)
    )
    # Round-off can put a tail a few ulps outside the probability interval.
    return min(1.0, max(0.0, probability))


__all__ = ["calculate_faith_damage_probability"]
