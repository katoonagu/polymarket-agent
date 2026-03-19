"""Local-first operator control plane and workflow-session service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pm.execution import ExecutionStateService
from pm.execution.models import CapturedExecutionEvent
from pm.ops.models import (
    OpsBootstrapResponse,
    OpsCycleQueueItem,
    OpsCycleQueueResponse,
    OpsCycleReportResponse,
    OpsDispatchApprovedResponse,
    OpsLatestActivity,
    OpsQueueCounts,
    OpsQueueItem,
    OpsQueueResponse,
    OpsReportResponse,
    OpsReviewNextResponse,
    OpsSessionEventRecord,
    OpsSessionMutationResponse,
    OpsSessionSummarySnapshot,
    OpsSessionView,
    OpsStatusResponse,
    OpsVerboseStatusResponse,
)
from pm.ops.state import OpsSessionNotFoundError, OpsStateService
from pm.risk import RiskPolicyService
from pm.strategy.dispatch import NON_SKIP_DECISIONS, StrategyDispatchService
from pm.strategy.models import (
    StrategyCandidateIntent,
    StrategyDispatchResultRecord,
    StrategyIntentView,
)
from pm.strategy.service import StrategyService
from pm.strategy.state import StrategyStateService

DEFAULT_LIMIT = 20
RECENT_ITEMS_LIMIT = 20
VERBOSE_PREVIEW_LIMIT = 10


class OpsValidationError(RuntimeError):
    """Raised when ops command inputs or session actions are invalid."""


@dataclass(slots=True)
class QueueState:
    """Internal materialized queue state."""

    review_items: list[OpsQueueItem]
    dispatch_items: list[OpsQueueItem]
    counts: OpsQueueCounts


class OpsService:
    """Aggregate local operator workflow state across strategy, risk, and execution."""

    def __init__(
        self,
        *,
        ops_state: OpsStateService | None = None,
        strategy_state: StrategyStateService | None = None,
        risk_service: RiskPolicyService | None = None,
        execution_state: ExecutionStateService | None = None,
        dispatch_service: StrategyDispatchService | None = None,
        strategy_service: StrategyService | None = None,
    ) -> None:
        self._ops_state = ops_state or OpsStateService()
        self._strategy_state = strategy_state or StrategyStateService()
        self._risk_service = risk_service or RiskPolicyService()
        self._execution_state = execution_state or ExecutionStateService()
        self._dispatch_service = dispatch_service or StrategyDispatchService()
        self._strategy_service = strategy_service or StrategyService(
            state=self._strategy_state
        )

    def bootstrap(self) -> OpsBootstrapResponse:
        """Initialize local risk defaults and ensure one active ops session exists."""
        risk_init = self._risk_service.init_defaults()
        active_session = self._ops_state.get_active_session()
        session_started = False
        if active_session is None:
            active_session = self.start_session().session
            session_started = True
        status = self.status()
        return OpsBootstrapResponse(
            ready=status.risk_policies_persisted and status.active_session is not None,
            risk_initialized=risk_init.initialized,
            risk_policies_persisted=risk_init.persisted,
            session_started=session_started,
            active_session=active_session,
            status=status,
        )

    def status(self) -> OpsStatusResponse:
        """Return a compact local-first operator summary."""
        queue_state = self._queue_state()
        dispatch_results = self._strategy_state.list_dispatch_results()
        execution_events = self._execution_state.list_execution_events()
        return OpsStatusResponse(
            active_session=self._ops_state.get_active_session(),
            pending_review_count=queue_state.counts.review_total,
            approved_dispatch_ready_count=queue_state.counts.dispatch_total,
            recent_strategy_execution_count=min(len(dispatch_results), RECENT_ITEMS_LIMIT),
            recent_execution_event_count=min(len(execution_events), RECENT_ITEMS_LIMIT),
            risk_policies_persisted=self._risk_service.show().persisted,
            latest_activity=self._latest_activity(
                dispatch_count=len(dispatch_results),
                execution_event_count=len(execution_events),
            ),
        )

    def verbose_status(self) -> OpsVerboseStatusResponse:
        """Return an expanded local-first operator summary."""
        base = self.status()
        return OpsVerboseStatusResponse(
            **base.model_dump(mode="json"),
            queue=self.queue(limit=VERBOSE_PREVIEW_LIMIT),
            recent_strategy_executions=list(
                reversed(self._strategy_state.list_dispatch_results())
            )[:VERBOSE_PREVIEW_LIMIT],
            recent_execution_events=list(
                reversed(self._execution_state.list_execution_events())
            )[:VERBOSE_PREVIEW_LIMIT],
        )

    def queue(self, *, limit: int = DEFAULT_LIMIT) -> OpsQueueResponse:
        """Return the combined actionable operator queue."""
        if limit < 1:
            raise OpsValidationError("Limit must be greater than zero.")
        queue_state = self._queue_state()
        items = queue_state.review_items + queue_state.dispatch_items
        return OpsQueueResponse(items=items[:limit], counts=queue_state.counts)

    def start_session(self, *, label: str | None = None) -> OpsSessionMutationResponse:
        """Start one local operator workflow session."""
        if self._ops_state.get_active_session() is not None:
            raise OpsValidationError("An ops session is already active.")
        started_at = _utc_now()
        session = OpsSessionView(
            session_id=_make_session_id(),
            label=_normalize_label(label),
            started_at=started_at,
            ended_at=None,
            active=True,
            summary_snapshot=None,
        )
        self._ops_state.append_session_event(
            OpsSessionEventRecord(
                event_type="start",
                session_id=session.session_id,
                occurred_at=started_at,
                label=session.label,
                started_at=started_at,
            )
        )
        return OpsSessionMutationResponse(action="started", session=session)

    def end_session(self) -> OpsSessionMutationResponse:
        """End the active local operator workflow session."""
        active = self._ops_state.get_active_session()
        if active is None:
            raise OpsSessionNotFoundError("No active ops session was found.")
        ended_at = _utc_now()
        summary = self._summary_for_scope(started_at=active.started_at, ended_at=ended_at)
        self._ops_state.append_session_event(
            OpsSessionEventRecord(
                event_type="end",
                session_id=active.session_id,
                occurred_at=ended_at,
                label=active.label,
                ended_at=ended_at,
                summary_snapshot=summary,
            )
        )
        ended_session = active.model_copy(
            update={
                "ended_at": ended_at,
                "active": False,
                "summary_snapshot": summary,
            }
        )
        return OpsSessionMutationResponse(action="ended", session=ended_session)

    def review_next(self) -> OpsReviewNextResponse:
        """Return the next reviewable strategy intent, if one exists."""
        review_items = self._queue_state().review_items
        if not review_items:
            return OpsReviewNextResponse(queue_empty=True, item=None)
        return OpsReviewNextResponse(queue_empty=False, item=review_items[0])

    def cycle_queue(self, *, limit: int = DEFAULT_LIMIT) -> OpsCycleQueueResponse:
        """Run one bounded evaluation pass across the seeded strategy catalog."""
        if limit < 1:
            raise OpsValidationError("Limit must be greater than zero.")

        items: list[OpsCycleQueueItem] = []
        total_new_intents = 0
        for strategy in self._strategy_service.list_strategies().items:
            result = self._strategy_service.evaluate_strategy(strategy.name, limit=limit)
            items.append(
                OpsCycleQueueItem(
                    strategy_name=result.strategy.name,
                    strategy_type=result.strategy.strategy_type,
                    total_new_intents=result.total,
                    total_errors=len(result.errors),
                    errors=result.errors,
                )
            )
            total_new_intents += result.total

        return OpsCycleQueueResponse(
            active_session=self._ops_state.get_active_session(),
            limit_per_strategy=limit,
            items=items,
            total_new_intents=total_new_intents,
            queue_counts=self._queue_state().counts,
        )

    def dispatch_approved(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> OpsDispatchApprovedResponse:
        """Paper-dispatch approved intents through the existing bridge."""
        return self.cycle_approved(limit=limit, live=False)

    def cycle_approved(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        live: bool = False,
    ) -> OpsDispatchApprovedResponse:
        """Run one bounded paper or live dispatch cycle for approved intents."""
        if limit < 1:
            raise OpsValidationError("Limit must be greater than zero.")
        result = self._dispatch_service.dispatch_pending(limit=limit, live=live)
        return OpsDispatchApprovedResponse(
            active_session=self._ops_state.get_active_session(),
            mode="live" if live else "paper",
            noop=result.total_candidates == 0,
            items=result.items,
            total_candidates=result.total_candidates,
            total_dispatched=result.total_dispatched,
            total_skipped=result.total_skipped,
        )

    def report(self) -> OpsReportResponse:
        """Return a local operator report for the active or latest completed session."""
        active = self._ops_state.get_active_session()
        latest_completed = self._ops_state.get_latest_completed_session()
        session = active or latest_completed
        if session is None:
            summary = self._summary_for_scope(started_at=None, ended_at=None)
            recent_dispatches = list(
                reversed(self._strategy_state.list_dispatch_results())
            )[:RECENT_ITEMS_LIMIT]
            recent_events = list(
                reversed(self._execution_state.list_execution_events())
            )[:RECENT_ITEMS_LIMIT]
        else:
            scope_end = _utc_now() if session.active else session.ended_at
            summary = self._summary_for_scope(
                started_at=session.started_at,
                ended_at=scope_end,
            )
            recent_dispatches = self._recent_dispatches_for_scope(
                started_at=session.started_at,
                ended_at=scope_end,
            )
            recent_events = self._recent_execution_events_for_scope(
                started_at=session.started_at,
                ended_at=scope_end,
            )

        return OpsReportResponse(
            session=session,
            queue_counts=self._queue_state().counts,
            summary=summary,
            recent_strategy_executions=recent_dispatches,
            recent_execution_events=recent_events,
        )

    def cycle_report(self) -> OpsCycleReportResponse:
        """Return a local-only runbook summary without live reads or reconcile calls."""
        queue_state = self._queue_state()
        dispatches = list(reversed(self._strategy_state.list_dispatch_results()))[
            :RECENT_ITEMS_LIMIT
        ]
        execution_events = list(reversed(self._execution_state.list_execution_events()))[
            :RECENT_ITEMS_LIMIT
        ]
        reconciliations = self._execution_state.list_reconciliations()
        approved_intent_count = sum(
            1
            for item in self._intent_views_newest_first()
            if item.current_decision == "APPROVE"
        )
        return OpsCycleReportResponse(
            session=self._active_or_latest_session(),
            queue_counts=queue_state.counts,
            approved_intent_count=approved_intent_count,
            dispatch_ready_intent_count=queue_state.counts.dispatch_total,
            recent_strategy_executions=dispatches,
            recent_execution_events=execution_events,
            latest_reconciliation=reconciliations[-1] if reconciliations else None,
        )

    def _queue_state(self) -> QueueState:
        intent_views = self._intent_views_newest_first()
        review_wait: list[OpsQueueItem] = []
        review_observe: list[OpsQueueItem] = []
        dispatch_items: list[OpsQueueItem] = []

        for intent_view in intent_views:
            intent = intent_view.intent
            if intent_view.latest_decision is None and intent.decision == "WAIT":
                review_wait.append(
                    OpsQueueItem(
                        kind="review",
                        note="Unreviewed WAIT intent is ready for operator review.",
                        intent=intent_view,
                    )
                )
            elif intent_view.latest_decision is None and intent.decision == "OBSERVE":
                review_observe.append(
                    OpsQueueItem(
                        kind="review",
                        note="Unreviewed OBSERVE intent is queued after WAIT items.",
                        intent=intent_view,
                    )
                )

            if intent_view.current_decision != "APPROVE":
                continue
            policy = self._risk_service.get_policy(intent.strategy_name)
            if not policy.dispatch_enabled:
                continue
            prior_results = self._strategy_state.list_dispatch_results(intent_id=intent.intent_id)
            if any(item.decision in NON_SKIP_DECISIONS for item in prior_results):
                continue
            dispatch_note = (
                "Approved intent is dispatch-ready."
                if not prior_results
                else "Approved intent is dispatch-ready and prior SKIP results are retryable."
            )
            dispatch_items.append(
                OpsQueueItem(
                    kind="dispatch",
                    note=dispatch_note,
                    intent=intent_view,
                )
            )

        review_items = review_wait + review_observe
        counts = OpsQueueCounts(
            total=len(review_items) + len(dispatch_items),
            review_total=len(review_items),
            dispatch_total=len(dispatch_items),
        )
        return QueueState(
            review_items=review_items,
            dispatch_items=dispatch_items,
            counts=counts,
        )

    def _intent_views_newest_first(self) -> list[StrategyIntentView]:
        return [
            self._build_intent_view(intent)
            for intent in reversed(self._strategy_state.list_intents())
        ]

    def _active_or_latest_session(self) -> OpsSessionView | None:
        return (
            self._ops_state.get_active_session()
            or self._ops_state.get_latest_completed_session()
        )

    def _build_intent_view(self, intent: StrategyCandidateIntent) -> StrategyIntentView:
        decisions = self._strategy_state.list_decisions(intent.intent_id)
        latest = decisions[-1] if decisions else None
        current_decision = latest.decision if latest is not None else intent.decision
        return StrategyIntentView(
            intent=intent,
            current_decision=current_decision,
            latest_decision=latest,
        )

    def _latest_activity(
        self,
        *,
        dispatch_count: int,
        execution_event_count: int,
    ) -> OpsLatestActivity:
        intents = self._strategy_state.list_intents()
        decisions = self._strategy_state.list_decisions()
        dispatches = self._strategy_state.list_dispatch_results()
        session_events = self._ops_state.list_session_events()
        return OpsLatestActivity(
            latest_intent_created_at=intents[-1].created_at if intents else None,
            latest_manual_decision_at=decisions[-1].decided_at if decisions else None,
            latest_dispatch_at=dispatches[-1].created_at if dispatch_count else None,
            latest_execution_event_at=(
                self._execution_state.list_execution_events()[-1].captured_at
                if execution_event_count
                else None
            ),
            latest_session_activity_at=(
                session_events[-1].occurred_at if session_events else None
            ),
        )

    def _summary_for_scope(
        self,
        *,
        started_at: str | None,
        ended_at: str | None,
    ) -> OpsSessionSummarySnapshot:
        decisions = [
            item
            for item in self._strategy_state.list_decisions()
            if _within_scope(item.decided_at, started_at=started_at, ended_at=ended_at)
        ]
        dispatches = [
            item
            for item in self._strategy_state.list_dispatch_results()
            if _within_scope(item.created_at, started_at=started_at, ended_at=ended_at)
        ]
        execution_events = [
            item
            for item in self._execution_state.list_execution_events()
            if _within_scope(item.captured_at, started_at=started_at, ended_at=ended_at)
        ]
        queue_counts = self._queue_state().counts
        return OpsSessionSummarySnapshot(
            pending_review_count=queue_counts.review_total,
            approved_dispatch_ready_count=queue_counts.dispatch_total,
            manual_review_count=len(decisions),
            approval_count=sum(1 for item in decisions if item.decision == "APPROVE"),
            rejection_count=sum(1 for item in decisions if item.decision == "REJECT"),
            dispatch_attempt_count=len(dispatches),
            would_post_count=sum(1 for item in dispatches if item.decision == "WOULD_POST"),
            posted_count=sum(1 for item in dispatches if item.decision == "POSTED"),
            skipped_count=sum(1 for item in dispatches if item.decision == "SKIP"),
            execution_event_count=len(execution_events),
        )

    def _recent_dispatches_for_scope(
        self,
        *,
        started_at: str,
        ended_at: str | None,
    ) -> list[StrategyDispatchResultRecord]:
        items = [
            item
            for item in self._strategy_state.list_dispatch_results()
            if _within_scope(item.created_at, started_at=started_at, ended_at=ended_at)
        ]
        return list(reversed(items))[:RECENT_ITEMS_LIMIT]

    def _recent_execution_events_for_scope(
        self,
        *,
        started_at: str,
        ended_at: str | None,
    ) -> list[CapturedExecutionEvent]:
        items = [
            item
            for item in self._execution_state.list_execution_events()
            if _within_scope(item.captured_at, started_at=started_at, ended_at=ended_at)
        ]
        return list(reversed(items))[:RECENT_ITEMS_LIMIT]


def _normalize_label(label: str | None) -> str | None:
    if label is None:
        return None
    stripped = label.strip()
    return stripped or None


def _within_scope(
    timestamp: str,
    *,
    started_at: str | None,
    ended_at: str | None,
) -> bool:
    point = _parse_timestamp(timestamp)
    if started_at is not None and point < _parse_timestamp(started_at):
        return False
    if ended_at is not None and point > _parse_timestamp(ended_at):
        return False
    return True


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _make_session_id() -> str:
    return f"ops_session_{uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
