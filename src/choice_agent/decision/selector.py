from __future__ import annotations

from dataclasses import dataclass, field
from random import random as default_random
from typing import Any, Callable

from choice_agent.schemas import SelectionStrategy


RandomFn = Callable[[], float]


@dataclass(frozen=True)
class SelectionCandidate:
    candidate_id: str
    name: str
    score: float = 0
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionInsights:
    strategy: SelectionStrategy
    candidate_count: int
    eligible_count: int
    recent_excluded_count: int
    selected_probability: float
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "candidateCount": self.candidate_count,
            "eligibleCount": self.eligible_count,
            "recentExcludedCount": self.recent_excluded_count,
            "selectedProbability": self.selected_probability,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class SelectionResult:
    selected_id: str | None
    ordered_ids: list[str]
    insights: SelectionInsights


_STRATEGY_ALIASES = {
    "least-recent": SelectionStrategy.LEAST_RECENT,
    "least_recent": SelectionStrategy.LEAST_RECENT,
}


def normalize_strategy(value: Any) -> SelectionStrategy:
    if isinstance(value, SelectionStrategy):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _STRATEGY_ALIASES:
            return _STRATEGY_ALIASES[normalized]
        for strategy in SelectionStrategy:
            if normalized == strategy.value:
                return strategy
    return SelectionStrategy.RANKED


def normalize_avoid_recent_count(value: Any, max_count: int = 20) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(max_count, count))


def select_candidates(
    candidates: list[SelectionCandidate],
    strategy: SelectionStrategy | str,
    recent_ids: list[str] | None = None,
    avoid_recent_count: int = 0,
    random_fn: RandomFn = default_random,
) -> SelectionResult:
    normalized_strategy = normalize_strategy(strategy)
    recent = [str(item) for item in (recent_ids or [])]
    recent_blocked = set(recent[-max(0, avoid_recent_count):]) if avoid_recent_count else set()
    eligible = [item for item in candidates if item.candidate_id not in recent_blocked]
    recent_excluded_count = len(candidates) - len(eligible)

    if not eligible:
        return SelectionResult(
            selected_id=None,
            ordered_ids=[],
            insights=SelectionInsights(
                strategy=normalized_strategy,
                candidate_count=len(candidates),
                eligible_count=0,
                recent_excluded_count=recent_excluded_count,
                selected_probability=0,
                tags=_tags(normalized_strategy, 0, recent_excluded_count, 0),
            ),
        )

    selected = _select(eligible, normalized_strategy, recent, random_fn)
    ordered = [selected, *[item for item in eligible if item.candidate_id != selected.candidate_id]]
    probability = _probability(selected, eligible, normalized_strategy, recent)

    return SelectionResult(
        selected_id=selected.candidate_id,
        ordered_ids=[item.candidate_id for item in ordered],
        insights=SelectionInsights(
            strategy=normalized_strategy,
            candidate_count=len(candidates),
            eligible_count=len(eligible),
            recent_excluded_count=recent_excluded_count,
            selected_probability=probability,
            tags=_tags(normalized_strategy, len(eligible), recent_excluded_count, probability),
        ),
    )


def _select(
    candidates: list[SelectionCandidate],
    strategy: SelectionStrategy,
    recent_ids: list[str],
    random_fn: RandomFn,
) -> SelectionCandidate:
    if strategy == SelectionStrategy.RANDOM:
        return _random_candidate(candidates, random_fn)
    if strategy == SelectionStrategy.WEIGHTED:
        return _weighted_candidate(candidates, random_fn)
    if strategy == SelectionStrategy.LEAST_RECENT:
        return _least_recent_candidate(candidates, recent_ids, random_fn)
    return candidates[0]


def _random_candidate(candidates: list[SelectionCandidate], random_fn: RandomFn) -> SelectionCandidate:
    index = min(len(candidates) - 1, int(random_fn() * len(candidates)))
    return candidates[index]


def _weighted_candidate(candidates: list[SelectionCandidate], random_fn: RandomFn) -> SelectionCandidate:
    total_weight = sum(max(0, item.score) for item in candidates)
    if total_weight <= 0:
        return _random_candidate(candidates, random_fn)

    remaining = random_fn() * total_weight
    for candidate in candidates:
        remaining -= max(0, candidate.score)
        if remaining < 0:
            return candidate
    return candidates[-1]


def _least_recent_candidate(
    candidates: list[SelectionCandidate], recent_ids: list[str], random_fn: RandomFn
) -> SelectionCandidate:
    last_seen = {candidate_id: index for index, candidate_id in enumerate(recent_ids)}
    oldest = min(last_seen.get(item.candidate_id, -1) for item in candidates)
    least_recent = [item for item in candidates if last_seen.get(item.candidate_id, -1) == oldest]
    return _random_candidate(least_recent, random_fn)


def _probability(
    selected: SelectionCandidate,
    candidates: list[SelectionCandidate],
    strategy: SelectionStrategy,
    recent_ids: list[str],
) -> float:
    if not candidates:
        return 0
    if strategy == SelectionStrategy.WEIGHTED:
        total_weight = sum(max(0, item.score) for item in candidates)
        return max(0, selected.score) / total_weight if total_weight > 0 else 1 / len(candidates)
    if strategy == SelectionStrategy.LEAST_RECENT:
        last_seen = {candidate_id: index for index, candidate_id in enumerate(recent_ids)}
        oldest = min(last_seen.get(item.candidate_id, -1) for item in candidates)
        eligible_count = sum(
            1 for item in candidates if last_seen.get(item.candidate_id, -1) == oldest
        )
        return 1 / eligible_count if eligible_count else 0
    if strategy == SelectionStrategy.RANDOM:
        return 1 / len(candidates)
    return 1


def _tags(
    strategy: SelectionStrategy,
    eligible_count: int,
    recent_excluded_count: int,
    probability: float,
) -> tuple[str, ...]:
    tags: list[str] = []
    if strategy == SelectionStrategy.RANKED:
        tags.append("按匹配度排序")
    elif strategy == SelectionStrategy.RANDOM:
        tags.append("有效候选中随机选择")
    elif strategy == SelectionStrategy.WEIGHTED:
        tags.append("按匹配度加权")
    elif strategy == SelectionStrategy.LEAST_RECENT:
        tags.append("优先很久没推荐")

    if eligible_count > 0:
        tags.append(f"从 {eligible_count} 个有效候选中选择")
        tags.append(f"本轮命中概率约 {round(probability * 100)}%")
    if recent_excluded_count > 0:
        tags.append(f"避开最近 {recent_excluded_count} 个已展示候选")
    return tuple(tags)