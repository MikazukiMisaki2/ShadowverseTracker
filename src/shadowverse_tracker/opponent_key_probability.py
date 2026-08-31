"""Opponent key-card probability for a 40-card tracker.

The model has two modes:

* ``known``: condition on a deterministic mulligan policy.  ``keep1_types``
  is the number of card types for which at most one copy is kept, and
  ``keep2_types`` is the number for which at most two copies are kept.
* ``unknown``: ignore mulligan information and use the exchangeable
  hypergeometric baseline over the opponent's remaining deck and hidden hand.

Important input semantics
-------------------------
``seen_*`` means deck-origin cards that have LEFT the opponent's hand and were
observed (played, discarded, banished, etc.).  A card merely revealed while it
remains in hand must not be counted.  ``hand_size`` must be the number of
unknown deck-origin cards currently in hand; subtract known generated/token
cards before calling this module.

In known mode, the queried key type is included in ``keep1_types`` when
``key_keep_limit == 1`` and in ``keep2_types`` when
``key_keep_limit == 2``.  The implementation removes it internally so it is
not double-counted.  Every other keep type is assumed to have three deck
copies by default.

The known-mode calculation correctly separates the mulligan replacement draw
from later deck draws: replacements are drawn from the 36 cards left after the
initial four cards are set aside, and swapped cards return only afterwards.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import comb
from typing import DefaultDict, Dict, Iterator, Literal, Tuple


Strategy = Literal["known", "unknown"]


@dataclass(frozen=True)
class KeyProbabilityResult:
    probability: float | None
    valid: bool
    reason: str
    compatible_weight: int = 0

    @property
    def percent(self) -> float | None:
        return None if self.probability is None else 100.0 * self.probability


def _compositions(total: int, limits: Tuple[int, ...]) -> Iterator[Tuple[int, ...]]:
    """Yield non-negative vectors summing to total within component limits."""

    current = [0] * len(limits)

    def visit(index: int, remaining: int) -> Iterator[Tuple[int, ...]]:
        if index == len(limits) - 1:
            if 0 <= remaining <= limits[index]:
                current[index] = remaining
                yield tuple(current)
            return

        for value in range(min(remaining, limits[index]) + 1):
            current[index] = value
            yield from visit(index + 1, remaining - value)

    if total >= 0 and limits:
        yield from visit(0, total)


def _multi_choose(available: Tuple[int, ...], selected: Tuple[int, ...]) -> int:
    result = 1
    for population, sample in zip(available, selected):
        if sample < 0 or sample > population:
            return 0
        result *= comb(population, sample)
    return result


def _initial_states(
    other_keep1_types: int,
    other_keep2_types: int,
    key_copies: int,
    key_keep_limit: int,
    rest_cards: int,
) -> Dict[Tuple[int, int, int, int, int, int], int]:
    """Return weighted initial-four states.

    State key:
      (initial_key, initial_keep1, initial_keep2,
       kept_key, kept_keep1, kept_keep2)

    Values are combination counts.  The common C(40, 4) denominator is
    intentionally omitted because it cancels during posterior normalization.
    """

    # Each entry is (category_index, copies, per-type keep cap).
    # Categories: 0=key, 1=other keep-one, 2=other keep-two, 3=rest.
    card_types = [(0, key_copies, key_keep_limit)]
    card_types.extend((1, 3, 1) for _ in range(other_keep1_types))
    card_types.extend((2, 3, 2) for _ in range(other_keep2_types))
    if rest_cards:
        card_types.append((3, rest_cards, 0))

    # DP key: (cards_drawn, init_key, init_x, init_y, kept_key, kept_x, kept_y)
    dp: Dict[Tuple[int, int, int, int, int, int, int], int] = {
        (0, 0, 0, 0, 0, 0, 0): 1
    }
    for category, copies, keep_cap in card_types:
        next_dp: DefaultDict[Tuple[int, int, int, int, int, int, int], int] = defaultdict(int)
        for state, weight in dp.items():
            drawn, init_k, init_x, init_y, kept_k, kept_x, kept_y = state
            for amount in range(min(copies, 4 - drawn) + 1):
                new_init_k = init_k + (amount if category == 0 else 0)
                new_init_x = init_x + (amount if category == 1 else 0)
                new_init_y = init_y + (amount if category == 2 else 0)
                kept_amount = min(amount, keep_cap)
                new_kept_k = kept_k + (kept_amount if category == 0 else 0)
                new_kept_x = kept_x + (kept_amount if category == 1 else 0)
                new_kept_y = kept_y + (kept_amount if category == 2 else 0)
                new_state = (
                    drawn + amount,
                    new_init_k,
                    new_init_x,
                    new_init_y,
                    new_kept_k,
                    new_kept_x,
                    new_kept_y,
                )
                next_dp[new_state] += weight * comb(copies, amount)
        dp = dict(next_dp)

    result: DefaultDict[Tuple[int, int, int, int, int, int], int] = defaultdict(int)
    for state, weight in dp.items():
        drawn, init_k, init_x, init_y, kept_k, kept_x, kept_y = state
        if drawn == 4:
            result[(init_k, init_x, init_y, kept_k, kept_x, kept_y)] += weight
    return dict(result)


def calculate_key_probability(
    *,
    deck_remaining: int,
    hand_size: int,
    mulligan_swapped: int,
    keep1_types: int,
    keep2_types: int,
    seen_keep1: int,
    seen_keep2: int,
    key_copies: int,
    strategy: Strategy = "known",
    key_keep_limit: int = 1,
    key_seen: int = 0,
    copies_per_other_keep_type: int = 3,
) -> KeyProbabilityResult:
    """Calculate P(at least one queried key card is currently in hand).

    Args:
        deck_remaining: Current opponent deck size; 36 immediately after mulligan.
        hand_size: Current unknown, deck-origin hand size.
        mulligan_swapped: Number of opening cards swapped (0..4).
        keep1_types: Total number of keep-at-most-one types.  Includes the key
            type when ``key_keep_limit == 1``.
        keep2_types: Total number of keep-at-most-two types.  Includes the key
            type when ``key_keep_limit == 2``.
        seen_keep1: Observed keep-one-group cards that left hand.  Includes
            ``key_seen`` when the key belongs to this group.
        seen_keep2: Same meaning for the keep-two group.
        key_copies: Number of queried key copies in the original deck (1..3).
        strategy: ``known`` uses mulligan information; ``unknown`` ignores it.
        key_keep_limit: 0 means never keep; 1/2 means keep up to that many;
            values up to ``key_copies`` are accepted.
        key_seen: Queried key copies already observed leaving hand.
        copies_per_other_keep_type: Deck copies for every non-key keep type.

    The known-mode posterior treats observed plays as state transitions rather
    than trying to model the opponent's strategic choice of which playable card
    to use.  It does not model generated cards, tutors, cards drawn directly
    from specific subsets, returns to deck, transformations, or burns.
    """

    if strategy not in ("known", "unknown"):
        return KeyProbabilityResult(None, False, "strategy 必须是 'known' 或 'unknown'")
    if not 0 <= deck_remaining <= 36:
        return KeyProbabilityResult(None, False, "deck_remaining 必须在 0..36")
    if hand_size < 0:
        return KeyProbabilityResult(None, False, "hand_size 不能为负数")
    if not 0 <= mulligan_swapped <= 4:
        return KeyProbabilityResult(None, False, "mulligan_swapped 必须在 0..4")
    if keep1_types < 0 or keep2_types < 0:
        return KeyProbabilityResult(None, False, "keep1_types/keep2_types 不能为负数")
    if seen_keep1 < 0 or seen_keep2 < 0 or key_seen < 0:
        return KeyProbabilityResult(None, False, "seen 数量不能为负数")
    if not 1 <= key_copies <= 3:
        return KeyProbabilityResult(None, False, "key_copies 必须在 1..3")
    if not 0 <= key_keep_limit <= key_copies:
        return KeyProbabilityResult(None, False, "key_keep_limit 必须在 0..key_copies")
    if copies_per_other_keep_type <= 0:
        return KeyProbabilityResult(None, False, "copies_per_other_keep_type 必须为正数")
    if key_seen > key_copies:
        return KeyProbabilityResult(None, False, "key_seen 不能超过 key_copies")

    remaining_key = key_copies - key_seen
    if hand_size == 0 or remaining_key == 0:
        return KeyProbabilityResult(0.0, True, "手牌为空或 Key 已全部出现")

    # With no usable mulligan-policy model, every remaining key copy is
    # exchangeable between the current deck and hidden deck-origin hand.
    if strategy == "unknown":
        unknown_pool = deck_remaining + hand_size
        if remaining_key > unknown_pool:
            return KeyProbabilityResult(None, False, "剩余 Key 数超过牌库与未知手牌总容量")
        p_zero = comb(deck_remaining, remaining_key) / comb(unknown_pool, remaining_key)
        return KeyProbabilityResult(1.0 - p_zero, True, "未知留牌策略：无偏超几何基准")

    key_is_keep1 = key_keep_limit == 1
    key_is_keep2 = key_keep_limit == 2
    other_keep1_types = keep1_types - int(key_is_keep1)
    other_keep2_types = keep2_types - int(key_is_keep2)
    if other_keep1_types < 0 or other_keep2_types < 0:
        return KeyProbabilityResult(
            None,
            False,
            "若 Key 的保留上限是1/2，对应 keep1_types/keep2_types 必须包含该 Key 类型",
        )

    # Group-level seen counts include the queried key if it belongs to that group.
    seen_other_keep1 = seen_keep1 - (key_seen if key_is_keep1 else 0)
    seen_other_keep2 = seen_keep2 - (key_seen if key_is_keep2 else 0)
    if seen_other_keep1 < 0 or seen_other_keep2 < 0:
        return KeyProbabilityResult(None, False, "seen_keep 数量与 key_seen/Key 分组矛盾")

    total_other_keep1 = other_keep1_types * copies_per_other_keep_type
    total_other_keep2 = other_keep2_types * copies_per_other_keep_type
    rest_cards = 40 - key_copies - total_other_keep1 - total_other_keep2
    if rest_cards < 0:
        return KeyProbabilityResult(None, False, "Key 与留牌类型占用张数超过40张")
    if seen_other_keep1 > total_other_keep1 or seen_other_keep2 > total_other_keep2:
        return KeyProbabilityResult(None, False, "已看到的留牌组张数超过卡组投入量")

    totals = (key_copies, total_other_keep1, total_other_keep2, rest_cards)
    initial_states = _initial_states(
        other_keep1_types,
        other_keep2_types,
        key_copies,
        key_keep_limit,
        rest_cards,
    )

    # Aggregate all post-mulligan hidden states.  State contains final opening
    # hand counts followed by the 36-card deck counts, both in K/X/Y/R order.
    post_mulligan: DefaultDict[Tuple[int, ...], int] = defaultdict(int)
    m = mulligan_swapped
    for state, initial_weight in initial_states.items():
        init_k, init_x, init_y, kept_k, kept_x, kept_y = state
        kept = (kept_k, kept_x, kept_y, 0)
        if 4 - sum(kept) != m:
            continue

        initial = (init_k, init_x, init_y, 4 - init_k - init_x - init_y)
        replacement_pool = tuple(total - drawn for total, drawn in zip(totals, initial))
        for replacement in _compositions(m, replacement_pool):
            replacement_weight = _multi_choose(replacement_pool, replacement)
            if replacement_weight == 0:
                continue
            opening_hand = tuple(a + b for a, b in zip(kept, replacement))
            # Swapped cards have now returned.  Hence deck = original totals -
            # kept cards - replacement cards, always totaling 36.
            deck = tuple(total - a - b for total, a, b in zip(totals, kept, replacement))
            post_mulligan[opening_hand + deck] += initial_weight * replacement_weight

    draws_after_mulligan = 36 - deck_remaining
    compatible_weight = 0
    key_in_hand_weight = 0

    for state, post_weight in post_mulligan.items():
        opening_hand = state[:4]
        deck = state[4:]
        for drawn in _compositions(draws_after_mulligan, deck):
            draw_weight = _multi_choose(deck, drawn)
            if draw_weight == 0:
                continue

            acquired = tuple(a + b for a, b in zip(opening_hand, drawn))
            key_in_hand = acquired[0] - key_seen
            keep1_in_hand = acquired[1] - seen_other_keep1
            keep2_in_hand = acquired[2] - seen_other_keep2
            if key_in_hand < 0 or keep1_in_hand < 0 or keep2_in_hand < 0:
                continue

            # Every otherwise-unidentified deck-origin hand card is assigned to
            # Rest.  Rest cards not in hand are the unclassified observed plays.
            rest_in_hand = hand_size - key_in_hand - keep1_in_hand - keep2_in_hand
            if rest_in_hand < 0 or rest_in_hand > acquired[3]:
                continue

            joint_weight = post_weight * draw_weight
            compatible_weight += joint_weight
            if key_in_hand >= 1:
                key_in_hand_weight += joint_weight

    if compatible_weight == 0:
        return KeyProbabilityResult(
            None,
            False,
            "没有与输入证据兼容的状态；请检查手牌、牌库、换牌和已见牌数量",
        )

    return KeyProbabilityResult(
        key_in_hand_weight / compatible_weight,
        True,
        "已知留牌策略：分阶段精确枚举",
        compatible_weight,
    )


if __name__ == "__main__":
    # Example: five keep-one types and one keep-two type in total.  The queried
    # three-copy key is one of the five keep-one types.
    example = calculate_key_probability(
        deck_remaining=29,
        hand_size=6,
        mulligan_swapped=2,
        keep1_types=5,
        keep2_types=1,
        seen_keep1=2,
        seen_keep2=1,
        key_copies=3,
        strategy="known",
        key_keep_limit=1,
        key_seen=0,
    )
    if example.valid:
        print(f"Key in hand: {example.percent:.2f}% ({example.reason})")
    else:
        print(f"Invalid input: {example.reason}")
