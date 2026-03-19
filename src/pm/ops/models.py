"""Models for the local-first operator control plane and workflow sessions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.execution.models import (
    CapturedExecutionEvent,
    ExecutionReconciliationRecord,
)
from pm.strategy.models import (
    StrategyDispatchResponse,
    StrategyDispatchResultRecord,
    StrategyIntentView,
    StrategySectionError,
)


class OpsQueueCounts(BaseModel):
    """Compact queue counters for review and dispatch work."""

    total: int = 0
    review_total: int = 0
    dispatch_total: int = 0


class OpsQueueItem(BaseModel):
    """One actionable operator queue row."""

    kind: str
    note: str
    intent: StrategyIntentView


class OpsQueueResponse(BaseModel):
    """Combined operator queue payload."""

    items: list[OpsQueueItem] = Field(default_factory=list)
    counts: OpsQueueCounts = Field(default_factory=OpsQueueCounts)


class OpsLatestActivity(BaseModel):
    """Latest local activity timestamps across operator subsystems."""

    latest_intent_created_at: str | None = None
    latest_manual_decision_at: str | None = None
    latest_dispatch_at: str | None = None
    latest_execution_event_at: str | None = None
    latest_session_activity_at: str | None = None


class OpsSessionSummarySnapshot(BaseModel):
    """Frozen or live summary counters for one operator session scope."""

    pending_review_count: int = 0
    approved_dispatch_ready_count: int = 0
    manual_review_count: int = 0
    approval_count: int = 0
    rejection_count: int = 0
    dispatch_attempt_count: int = 0
    would_post_count: int = 0
    posted_count: int = 0
    skipped_count: int = 0
    execution_event_count: int = 0


class OpsSessionEventRecord(BaseModel):
    """Append-only session lifecycle event."""

    event_type: str
    session_id: str
    occurred_at: str
    label: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    summary_snapshot: OpsSessionSummarySnapshot | None = None


class OpsSessionsFile(BaseModel):
    """Versioned local ops-session state document."""

    version: int = 1
    events: list[OpsSessionEventRecord] = Field(default_factory=list)


class OpsSessionView(BaseModel):
    """Materialized operator session view."""

    session_id: str
    label: str | None = None
    started_at: str
    ended_at: str | None = None
    active: bool
    summary_snapshot: OpsSessionSummarySnapshot | None = None


class OpsSessionMutationResponse(BaseModel):
    """Session start or end response."""

    action: str
    session: OpsSessionView


class OpsStatusResponse(BaseModel):
    """Compact operator status summary."""

    active_session: OpsSessionView | None = None
    pending_review_count: int = 0
    approved_dispatch_ready_count: int = 0
    recent_strategy_execution_count: int = 0
    recent_execution_event_count: int = 0
    risk_policies_persisted: bool = False
    latest_activity: OpsLatestActivity = Field(default_factory=OpsLatestActivity)


class OpsVerboseStatusResponse(OpsStatusResponse):
    """Expanded operator status summary with queue and recents."""

    queue: OpsQueueResponse = Field(default_factory=OpsQueueResponse)
    recent_strategy_executions: list[StrategyDispatchResultRecord] = Field(
        default_factory=list
    )
    recent_execution_events: list[CapturedExecutionEvent] = Field(default_factory=list)


class OpsReviewNextResponse(BaseModel):
    """Next reviewable intent payload."""

    queue_empty: bool
    item: OpsQueueItem | None = None


class OpsBootstrapResponse(BaseModel):
    """Readiness response for one local ops bootstrap pass."""

    ready: bool
    risk_initialized: bool
    risk_policies_persisted: bool
    session_started: bool
    active_session: OpsSessionView | None = None
    status: OpsStatusResponse


class OpsCycleQueueItem(BaseModel):
    """Per-strategy summary for one bounded queue-evaluation pass."""

    strategy_name: str
    strategy_type: str
    total_new_intents: int = 0
    total_errors: int = 0
    errors: list[StrategySectionError] = Field(default_factory=list)


class OpsCycleQueueResponse(BaseModel):
    """Aggregate response for one bounded queue-evaluation cycle."""

    active_session: OpsSessionView | None = None
    limit_per_strategy: int
    items: list[OpsCycleQueueItem] = Field(default_factory=list)
    total_new_intents: int = 0
    queue_counts: OpsQueueCounts = Field(default_factory=OpsQueueCounts)


class OpsDispatchApprovedResponse(BaseModel):
    """Bounded dispatch response for approved intents."""

    active_session: OpsSessionView | None = None
    mode: str = "paper"
    noop: bool = False
    items: list[StrategyDispatchResponse] = Field(default_factory=list)
    total_candidates: int = 0
    total_dispatched: int = 0
    total_skipped: int = 0


class OpsReportResponse(BaseModel):
    """Operator report across sessions, queue state, and recent activity."""

    session: OpsSessionView | None = None
    queue_counts: OpsQueueCounts = Field(default_factory=OpsQueueCounts)
    summary: OpsSessionSummarySnapshot = Field(default_factory=OpsSessionSummarySnapshot)
    recent_strategy_executions: list[StrategyDispatchResultRecord] = Field(
        default_factory=list
    )
    recent_execution_events: list[CapturedExecutionEvent] = Field(default_factory=list)


class OpsCycleReportResponse(BaseModel):
    """Current local runbook summary for one-cycle operator workflows."""

    session: OpsSessionView | None = None
    queue_counts: OpsQueueCounts = Field(default_factory=OpsQueueCounts)
    approved_intent_count: int = 0
    dispatch_ready_intent_count: int = 0
    recent_strategy_executions: list[StrategyDispatchResultRecord] = Field(
        default_factory=list
    )
    recent_execution_events: list[CapturedExecutionEvent] = Field(default_factory=list)
    latest_reconciliation: ExecutionReconciliationRecord | None = None
