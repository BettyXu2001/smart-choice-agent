from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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