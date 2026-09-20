from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class ProviderCallMetadata:
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    retry_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "promptVersion": self.prompt_version,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.total_tokens,
            "estimatedCost": self.estimated_cost,
            "retryCount": self.retry_count,
        }


class ModelCompletion(dict[str, Any]):
    def __init__(self, value: dict[str, Any], metadata: ProviderCallMetadata):
        super().__init__(value)
        self.metadata = metadata


@dataclass(frozen=True)
class ProviderCallResult(Generic[T]):
    value: T
    metadata: ProviderCallMetadata


class ProviderResponseError(ValueError):
    def __init__(self, message: str, metadata: ProviderCallMetadata):
        super().__init__(message)
        self.metadata = metadata


def prompt_fingerprint(template: str) -> str:
    return "sha256:" + sha256(template.encode("utf-8")).hexdigest()[:16]


def metadata_from_usage(
    usage: Any,
    *,
    provider: str | None,
    model: str | None,
    prompt_version: str | None,
    pricing: dict[str, dict[str, float]] | None = None,
    retry_count: int = 0,
    input_key: str = "input_tokens",
    output_key: str = "output_tokens",
    total_key: str = "total_tokens",
) -> ProviderCallMetadata:
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _token_value(usage.get(input_key))
    output_tokens = _token_value(usage.get(output_key))
    total_tokens = _token_value(usage.get(total_key))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return ProviderCallMetadata(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimate_cost(model, input_tokens, output_tokens, pricing or {}),
        retry_count=max(0, retry_count),
    )


def estimate_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    pricing: dict[str, dict[str, float]],
) -> float | None:
    if not model or input_tokens is None or output_tokens is None:
        return None
    price = pricing.get(model)
    if not isinstance(price, dict):
        return None
    input_price = price.get("inputPer1MTokens")
    output_price = price.get("outputPer1MTokens")
    if input_price is None or output_price is None:
        return None
    cost = (
        Decimal(input_tokens) * Decimal(str(input_price))
        + Decimal(output_tokens) * Decimal(str(output_price))
    ) / Decimal(1_000_000)
    return float(cost.quantize(Decimal("0.000000000001")))


def result_metadata(value: Any) -> ProviderCallMetadata | None:
    metadata = getattr(value, "metadata", None)
    return metadata if isinstance(metadata, ProviderCallMetadata) else None


def _token_value(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
