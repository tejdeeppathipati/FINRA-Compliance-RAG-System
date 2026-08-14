"""Combine ranked retrieval lists with deterministic reciprocal rank fusion."""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedItem[T]:
    key: Hashable
    value: T


def reciprocal_rank_fusion[T](
    rankings: Sequence[Sequence[RankedItem[T]]],
    *,
    rrf_k: int = 60,
) -> list[tuple[T, float]]:
    """Fuse rankings deterministically, deduplicating by stable item key."""
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    scores: dict[Hashable, float] = {}
    values: dict[Hashable, T] = {}
    first_seen: dict[Hashable, int] = {}
    seen_index = 0

    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            if item.key not in first_seen:
                first_seen[item.key] = seen_index
                seen_index += 1
            values[item.key] = item.value
            # Each list contributes 1 / (k + rank); shared hits accumulate support.
            scores[item.key] = scores.get(item.key, 0.0) + 1.0 / (rrf_k + rank)

    ordered_keys = sorted(scores, key=lambda key: (-scores[key], first_seen[key]))
    return [(values[key], scores[key]) for key in ordered_keys]
