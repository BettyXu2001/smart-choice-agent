from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from choice_agent.schemas import Candidate, Constraint, Criterion, DecisionState, Recommendation


@dataclass(frozen=True)
class DomainMetadata:
    key: str
    label: str
    description: str
    complete: bool = False


@dataclass(frozen=True)
class DomainRunResult:
    speech_text: str
    display_blocks: list[dict[str, Any]] = field(default_factory=list)


class DomainPlugin(ABC):
    metadata: DomainMetadata

    @abstractmethod
    def matches(self, message: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def understand(self, decision: DecisionState, message: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def clarify(self, decision: DecisionState, message: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def candidates(self, decision: DecisionState, message: str) -> list[Candidate]:
        raise NotImplementedError

    @abstractmethod
    def rank(self, decision: DecisionState, candidates: list[Candidate]) -> list[Candidate]:
        raise NotImplementedError

    @abstractmethod
    def explain(self, decision: DecisionState, ranked: list[Candidate]) -> Recommendation:
        raise NotImplementedError

    def display_blocks(self, decision: DecisionState) -> list[dict[str, Any]]:
        return [candidate.model_dump(mode="json", by_alias=True) for candidate in decision.candidates]

    @property
    def key(self) -> str:
        return self.metadata.key

    @property
    def label(self) -> str:
        return self.metadata.label

    @property
    def description(self) -> str:
        return self.metadata.description

    def default_constraints(self) -> list[Constraint]:
        return []

    def default_criteria(self) -> list[Criterion]:
        return []