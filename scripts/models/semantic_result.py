from typing import Any, Literal
from pydantic import BaseModel, Field

SemanticMode = Literal[
    "llm",
    "heuristic",
    "heuristic_degraded",
    "guarded_metadata",
    "unprocessed",
]

class SemanticResult(BaseModel):
    semantic_mode: SemanticMode
    field_sources: dict[str, str]
    category: str | None
    domain: str | None
    intent: str | None
    lifecycle: str | None
    evidence: list[str]
    confidence: float | None
    deadline: str | None
    action_required: bool
    action_type: str | None
    action_summary: str | None
    required_materials: list[str]
    sensitive: bool
    sensitive_types: list[str]
    review_required: bool
    risk_flags: list[str]
    content: str
    summary: str
    attachments: list[dict[str, Any]]

    tags: list[str]
    llm: dict[str, Any]
    raw_field_presence: dict[str, bool] = Field(default_factory=dict)
    llm_failure: dict[str, Any] | None = None
