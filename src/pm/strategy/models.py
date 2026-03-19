"""Models for the read-only strategy registry and orchestrator."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StrategyReasonBlock(BaseModel):
    """Explainable reason emitted during validation and evaluation."""

    section: str
    status: str
    message: str


class StrategySectionError(BaseModel):
    """Partial failure captured during strategy evaluation."""

    section: str
    code: str
    message: str


class StrategySourceReference(BaseModel):
    """Reference back to a source artifact used to derive an intent."""

    source_kind: str
    reference_id: str
    label: str | None = None


class StrategyDefinition(BaseModel):
    """Seeded local strategy definition."""

    name: str
    strategy_type: str
    description: str
    required_state_files: list[str] = Field(default_factory=list)
    settings: dict[str, str | int | float | bool] = Field(default_factory=dict)


class StrategyRegistryFile(BaseModel):
    """On-disk strategy registry document."""

    version: int = 1
    strategies: list[StrategyDefinition] = Field(default_factory=list)


class StrategyListResponse(BaseModel):
    """Deterministic strategy list payload."""

    items: list[StrategyDefinition] = Field(default_factory=list)
    total: int = 0


class StrategyShowResponse(BaseModel):
    """Single strategy payload."""

    strategy: StrategyDefinition


class StrategyValidationResult(BaseModel):
    """Validation payload for one seeded strategy."""

    strategy: StrategyDefinition
    valid: bool
    reason_blocks: list[StrategyReasonBlock] = Field(default_factory=list)
    errors: list[StrategySectionError] = Field(default_factory=list)


class StrategyCandidateIntent(BaseModel):
    """Read-only candidate intent emitted by the strategy orchestrator."""

    intent_id: str
    strategy_name: str
    strategy_type: str
    source_kind: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    side: str | None = None
    outcome: str | None = None
    decision: str
    reason_blocks: list[StrategyReasonBlock] = Field(default_factory=list)
    created_at: str
    source_refs: list[StrategySourceReference] = Field(default_factory=list)


class StrategyIntentsFile(BaseModel):
    """On-disk candidate-intents state document."""

    version: int = 1
    intents: list[StrategyCandidateIntent] = Field(default_factory=list)


class StrategyDecisionRecord(BaseModel):
    """Append-only review decision for a candidate intent."""

    intent_id: str
    decision: str
    reason: str | None = None
    decided_at: str
    actor: str = "operator"


class StrategyDecisionsFile(BaseModel):
    """On-disk review-decisions state document."""

    version: int = 1
    decisions: list[StrategyDecisionRecord] = Field(default_factory=list)


class StrategyIntentView(BaseModel):
    """Intent plus its latest derived current decision."""

    intent: StrategyCandidateIntent
    current_decision: str
    latest_decision: StrategyDecisionRecord | None = None


class StrategyEvaluateResponse(BaseModel):
    """Evaluation result for a seeded strategy."""

    strategy: StrategyDefinition
    items: list[StrategyCandidateIntent] = Field(default_factory=list)
    total: int = 0
    errors: list[StrategySectionError] = Field(default_factory=list)


class StrategyIntentsResponse(BaseModel):
    """Persisted candidate-intent listing payload."""

    items: list[StrategyIntentView] = Field(default_factory=list)
    total: int = 0


class StrategyReviewResponse(BaseModel):
    """Single intent review payload."""

    intent: StrategyIntentView
    decision_history: list[StrategyDecisionRecord] = Field(default_factory=list)
    errors: list[StrategySectionError] = Field(default_factory=list)


class StrategyDecisionMutationResponse(BaseModel):
    """Manual approve/reject response payload."""

    intent: StrategyIntentView


class StrategyExecutionRequest(BaseModel):
    """Deterministic execution request derived from an approved strategy intent."""

    market_ref: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    outcome: str
    side: str
    price: str
    size: str
    notional_usdc: str
    order_type: str = "gtc"
    post_only: bool = False


class StrategyExecutionLinkRecord(BaseModel):
    """Append-only link between an intent and execution lifecycle records."""

    execution_id: str
    intent_id: str
    strategy_name: str
    strategy_type: str
    mode: str
    created_at: str
    execution_plan_id: str | None = None
    execution_result_id: str | None = None
    order_id: str | None = None


class StrategyDispatchResultRecord(BaseModel):
    """Append-only dispatch audit record for one manual strategy handoff."""

    execution_id: str
    intent_id: str
    strategy_name: str
    strategy_type: str
    mode: str
    decision: str
    created_at: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    outcome: str | None = None
    side: str | None = None
    execution_request: StrategyExecutionRequest | None = None
    risk_checks: list[StrategyReasonBlock] = Field(default_factory=list)
    execution_reasons: list[StrategyReasonBlock] = Field(default_factory=list)
    execution_plan_id: str | None = None
    execution_result_id: str | None = None
    order_id: str | None = None
    execution_response: dict[str, Any] | None = None


class StrategyExecutionLinksFile(BaseModel):
    """On-disk strategy-execution link state document."""

    version: int = 1
    links: list[StrategyExecutionLinkRecord] = Field(default_factory=list)


class StrategyDispatchResultsFile(BaseModel):
    """On-disk strategy dispatch-result state document."""

    version: int = 1
    results: list[StrategyDispatchResultRecord] = Field(default_factory=list)


class StrategyDispatchResponse(BaseModel):
    """Single manual strategy-dispatch response."""

    intent: StrategyIntentView
    link: StrategyExecutionLinkRecord
    execution: StrategyDispatchResultRecord


class StrategyDispatchPendingResponse(BaseModel):
    """Batch paper dispatch response for pending approved intents."""

    items: list[StrategyDispatchResponse] = Field(default_factory=list)
    total_candidates: int = 0
    total_dispatched: int = 0
    total_skipped: int = 0


class StrategyExecutionsResponse(BaseModel):
    """Persisted strategy dispatch-result listing payload."""

    items: list[StrategyDispatchResultRecord] = Field(default_factory=list)
    total: int = 0


class StrategyExecutionDetailResponse(BaseModel):
    """Single persisted strategy execution detail payload."""

    intent: StrategyIntentView | None = None
    link: StrategyExecutionLinkRecord
    execution: StrategyDispatchResultRecord
