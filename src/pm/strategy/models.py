"""Models for the read-only strategy registry and orchestrator."""

from __future__ import annotations

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
