from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from choice_agent.agents.base import AgentContext
from choice_agent.domains.base import DomainMetadata


StageHandler = Callable[[AgentContext], dict[str, Any]]


@dataclass(frozen=True)
class DomainCapabilities:
    adjustment: bool = False
    composition: bool = False
    pre_safety: bool = False
    post_safety: bool = True


class DomainProfile(ABC):
    metadata: DomainMetadata
    capabilities = DomainCapabilities()

    @property
    def key(self) -> str:
        return self.metadata.key

    @property
    def label(self) -> str:
        return self.metadata.label

    @property
    def description(self) -> str:
        return self.metadata.description

    @abstractmethod
    def matches(self, message: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def intent(self, context: AgentContext) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def understand(self, context: AgentContext) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def clarify(self, context: AgentContext) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def source_and_rank(self, context: AgentContext) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def explain(self, context: AgentContext) -> dict[str, Any]:
        raise NotImplementedError

    def pre_safety(self, context: AgentContext) -> dict[str, Any]:
        return {"passed": True, "reasons": []}

    def adjust(self, context: AgentContext) -> dict[str, Any]:
        return {"excludedCandidateIds": []}

    def compose(self, context: AgentContext) -> dict[str, Any]:
        return self.source_and_rank(context)

    def rerank(self, context: AgentContext) -> dict[str, Any]:
        return self.source_and_rank(context)

    def critic(self, context: AgentContext) -> dict[str, Any]:
        return {"passed": True, "issues": []}

    def post_safety(self, context: AgentContext) -> dict[str, Any]:
        return {"passed": True, "reasons": []}

    def should_stop_after_understanding(self, context: AgentContext) -> bool:
        return False

    def should_run_pre_safety(self, context: AgentContext) -> bool:
        return False

    def should_adjust(self, context: AgentContext) -> bool:
        return False

    def should_clarify(self, context: AgentContext) -> bool:
        return True

    def is_clarifying(self, result: dict[str, Any], context: AgentContext) -> bool:
        return bool(result.get("questionToAsk") or result.get("question"))

    def should_compose(self, context: AgentContext) -> bool:
        return False

    def phase(self, context: AgentContext) -> str:
        return "RECOMMEND"

    def display_blocks(self, context: AgentContext) -> list[dict[str, Any]]:
        return [candidate.model_dump(mode="json", by_alias=True) for candidate in context.decision.candidates]