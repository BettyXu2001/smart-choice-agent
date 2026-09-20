from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class EvaluationModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


ErrorType = Literal[
    "理解错误",
    "约束处理错误",
    "候选获取错误",
    "Evidence 错误",
    "排序错误",
    "解释不一致",
    "多轮状态丢失",
    "Fallback 异常",
]

CaseStatus = Literal["open", "diagnosed", "fix_pending", "awaiting_regression", "verified", "reopened"]
RunStatus = Literal["running", "completed", "failed", "partial"]


class EvaluationAssertion(EvaluationModel):
    metric_id: str
    path: str | None = None
    operator: Literal[
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "includes_all",
        "excludes_all",
        "non_empty",
        "empty",
        "changed",
        "unchanged",
        "manual",
    ] = "equals"
    expected: Any = None
    before_path: str | None = None
    actual_path: str | None = None
    note: str | None = None
    required: bool = True


class EvaluationCaseData(EvaluationModel):
    domain: str = "generic"
    setup: dict[str, Any] = Field(default_factory=dict)
    messages: list[str] = Field(default_factory=list, max_length=10)
    commands: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    assertions: list[EvaluationAssertion] = Field(default_factory=list)
    expected_trace_id: str | None = None
    fixture_actual: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class EvaluationCaseCreate(EvaluationModel):
    title: str = Field(min_length=1, max_length=256)
    original_question: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    actual_behavior: str | None = None
    error_type: ErrorType = "理解错误"
    diagnosis: str | None = None
    modules: list[str] = Field(default_factory=list)
    fix_plan: str | None = None
    fix_version: str | None = None
    status: CaseStatus = "open"
    case_data: EvaluationCaseData = Field(default_factory=EvaluationCaseData)
    source_run_id: str | None = None
    source_trace_id: str | None = None

    @field_validator("modules", mode="before")
    @classmethod
    def clean_modules(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))[:12]


class EvaluationCaseUpdate(EvaluationModel):
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=256)
    expected_behavior: str | None = None
    actual_behavior: str | None = None
    error_type: ErrorType | None = None
    diagnosis: str | None = None
    modules: list[str] | None = None
    fix_plan: str | None = None
    fix_version: str | None = None
    status: CaseStatus | None = None
    case_data: EvaluationCaseData | None = None


class EvaluationDatasetCreate(EvaluationModel):
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    description: str | None = None
    case_ids: list[str] = Field(default_factory=list, min_length=1)


CURRENT_PROMPT_VERSION = "prompt-v1"
CURRENT_RULE_VERSION = "rule-v1"


class EvaluationRunConfiguration(EvaluationModel):
    model: str = Field(min_length=1, max_length=128)
    provider: Literal["configured", "disabled"]
    prompt_version: str = Field(min_length=1, max_length=64)
    rule_version: str = Field(min_length=1, max_length=64)
    run_label: Literal["baseline", "candidate"]

    @model_validator(mode="after")
    def validate_supported_versions(self) -> "EvaluationRunConfiguration":
        if self.prompt_version != CURRENT_PROMPT_VERSION:
            raise ValueError(f"不支持的 promptVersion：{self.prompt_version}")
        if self.rule_version != CURRENT_RULE_VERSION:
            raise ValueError(f"不支持的 ruleVersion：{self.rule_version}")
        return self


class EvaluationRunCreate(EvaluationModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    dataset_id: str | None = None
    version_label: str = Field(default="local", min_length=1, max_length=128)
    mode: Literal["fixture", "historical", "live_model"] = "fixture"
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    run_configuration: EvaluationRunConfiguration | None = None
    limit: int = Field(default=20, ge=1, le=20)
    repeat: int = Field(default=1, ge=1, le=3)
    include_observations: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model_compatibility(self) -> "EvaluationRunCreate":
        if self.run_configuration and self.model_name and self.run_configuration.model != self.model_name:
            raise ValueError("modelName 与 runConfiguration.model 冲突")
        return self


class EvaluationReviewUpdate(EvaluationModel):
    reviews: dict[str, Any] = Field(default_factory=dict)
