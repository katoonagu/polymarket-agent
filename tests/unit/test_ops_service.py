"""Unit tests for the local-first operator control plane service."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pm.execution import CapturedExecutionEvent, ExecutionStateService
from pm.ops import (
    OpsService,
    OpsSessionEventRecord,
    OpsSessionNotFoundError,
    OpsSessionSummarySnapshot,
    OpsStateError,
    OpsStateService,
    OpsValidationError,
)
from pm.risk import RiskPolicyService, RiskStateService
from pm.strategy import StrategyCandidateIntent, StrategyDecisionRecord, StrategyStateService
from pm.strategy.models import (
    StrategyDispatchPendingResponse,
    StrategyDispatchResponse,
    StrategyDispatchResultRecord,
    StrategyExecutionLinkRecord,
    StrategyExecutionRequest,
    StrategyIntentView,
    StrategyReasonBlock,
)
from pm.strategy.registry import StrategyRegistryService

CONDITION_ID = "0x" + ("a" * 64)
TOKEN_ID = "100"


@dataclass
class OpsFixture:
    service: OpsService
    strategy_state: StrategyStateService
    execution_state: ExecutionStateService
    ops_state: OpsStateService


def _fixture(tmp_path, *, dispatch_service=None) -> OpsFixture:
    strategy_state = StrategyStateService(
        intents_path=tmp_path / "strategy-intents.json",
        decisions_path=tmp_path / "strategy-decisions.json",
        execution_links_path=tmp_path / "strategy-execution-links.json",
        dispatch_results_path=tmp_path / "strategy-dispatch-results.json",
    )
    execution_state = ExecutionStateService(
        approval_plans_path=tmp_path / "approval-plans.json",
        approval_results_path=tmp_path / "approval-results.json",
        order_plans_path=tmp_path / "execution-order-plans.json",
        order_results_path=tmp_path / "execution-order-results.json",
        events_path=tmp_path / "execution-events.jsonl",
        reconciliations_path=tmp_path / "execution-reconciliations.json",
    )
    ops_state = OpsStateService(sessions_path=tmp_path / "ops-sessions.json")
    risk_service = RiskPolicyService(
        state=RiskStateService(policies_path=tmp_path / "risk-policies.json"),
        registry=StrategyRegistryService(path=tmp_path / "strategies.json"),
    )
    service = OpsService(
        ops_state=ops_state,
        strategy_state=strategy_state,
        risk_service=risk_service,
        execution_state=execution_state,
        dispatch_service=dispatch_service,
    )
    return OpsFixture(
        service=service,
        strategy_state=strategy_state,
        execution_state=execution_state,
        ops_state=ops_state,
    )


def _append_intent(
    fixture: OpsFixture,
    *,
    intent_id: str,
    created_at: str,
    decision: str = "WAIT",
    manual_decision: str | None = None,
    strategy_name: str = "wallet_shadow_copy",
) -> StrategyCandidateIntent:
    intent = StrategyCandidateIntent(
        intent_id=intent_id,
        strategy_name=strategy_name,
        strategy_type=strategy_name,
        source_kind="wallet_shadow",
        market_slug="btc-15m",
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        side="BUY",
        outcome="Yes",
        decision=decision,
        reason_blocks=[],
        created_at=created_at,
        source_refs=[],
    )
    fixture.strategy_state.append_intents([intent])
    if manual_decision is not None:
        fixture.strategy_state.append_decision(
            StrategyDecisionRecord(
                intent_id=intent_id,
                decision=manual_decision,
                reason="manual review",
                decided_at=created_at.replace("00:00", "00:10"),
            )
        )
    return intent


def _append_dispatch_result(
    fixture: OpsFixture,
    *,
    execution_id: str,
    intent_id: str,
    created_at: str,
    decision: str = "WOULD_POST",
) -> None:
    fixture.strategy_state.append_execution_link(
        StrategyExecutionLinkRecord(
            execution_id=execution_id,
            intent_id=intent_id,
            strategy_name="wallet_shadow_copy",
            strategy_type="wallet_shadow_copy",
            mode="paper",
            created_at=created_at,
            execution_plan_id="plan-123",
            execution_result_id="result-123",
        )
    )
    fixture.strategy_state.append_dispatch_result(
        StrategyDispatchResultRecord(
            execution_id=execution_id,
            intent_id=intent_id,
            strategy_name="wallet_shadow_copy",
            strategy_type="wallet_shadow_copy",
            mode="paper",
            decision=decision,
            created_at=created_at,
            market_slug="btc-15m",
            condition_id=CONDITION_ID,
            token_id=TOKEN_ID,
            outcome="Yes",
            side="BUY",
            execution_request=StrategyExecutionRequest(
                market_ref=CONDITION_ID,
                market_slug="btc-15m",
                condition_id=CONDITION_ID,
                token_id=TOKEN_ID,
                outcome="yes",
                side="buy",
                price="0.56",
                size="10",
                notional_usdc="5.6",
            ),
            risk_checks=[
                StrategyReasonBlock(
                    section="market_open",
                    status="pass",
                    message="Market is active and open.",
                )
            ],
            execution_plan_id="plan-123",
            execution_result_id="result-123",
        )
    )


def _append_execution_event(fixture: OpsFixture, *, captured_at: str) -> None:
    fixture.execution_state.append_execution_event(
        CapturedExecutionEvent(
            session_id="session-1",
            source="polymarket_user_ws",
            captured_at=captured_at,
            condition_id=CONDITION_ID,
            order_id="order-123",
            asset_id=TOKEN_ID,
            event_type="UPDATE",
            trade_status="MATCHED",
            side="BUY",
            price="0.56",
            size="10",
            status="OPEN",
            timestamp=1710806400,
        )
    )


class FakeStrategyDispatchService:
    def __init__(self) -> None:
        self.last_limit: int | None = None

    def dispatch_pending(self, *, limit: int = 20) -> StrategyDispatchPendingResponse:
        self.last_limit = limit
        intent = StrategyCandidateIntent(
            intent_id="intent-approved",
            strategy_name="wallet_shadow_copy",
            strategy_type="wallet_shadow_copy",
            source_kind="wallet_shadow",
            market_slug="btc-15m",
            condition_id=CONDITION_ID,
            token_id=TOKEN_ID,
            side="BUY",
            outcome="Yes",
            decision="WAIT",
            reason_blocks=[],
            created_at="2026-03-19T00:00:00Z",
            source_refs=[],
        )
        view = StrategyIntentView(intent=intent, current_decision="APPROVE", latest_decision=None)
        item = StrategyDispatchResponse(
            intent=view,
            link=StrategyExecutionLinkRecord(
                execution_id="strategy_exec_123",
                intent_id=intent.intent_id,
                strategy_name=intent.strategy_name,
                strategy_type=intent.strategy_type,
                mode="paper",
                created_at="2026-03-19T00:01:00Z",
                execution_plan_id="plan-123",
                execution_result_id="result-123",
            ),
            execution=StrategyDispatchResultRecord(
                execution_id="strategy_exec_123",
                intent_id=intent.intent_id,
                strategy_name=intent.strategy_name,
                strategy_type=intent.strategy_type,
                mode="paper",
                decision="WOULD_POST",
                created_at="2026-03-19T00:01:00Z",
                market_slug="btc-15m",
                condition_id=CONDITION_ID,
                token_id=TOKEN_ID,
                outcome="Yes",
                side="BUY",
            ),
        )
        return StrategyDispatchPendingResponse(
            items=[item],
            total_candidates=1,
            total_dispatched=1,
            total_skipped=0,
        )


def test_status_summary_local_first(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_intent(
        fixture,
        intent_id="intent-wait",
        created_at="2026-03-19T00:01:00Z",
        decision="WAIT",
    )
    _append_intent(
        fixture,
        intent_id="intent-observe",
        created_at="2026-03-19T00:02:00Z",
        decision="OBSERVE",
    )
    _append_intent(
        fixture,
        intent_id="intent-approved",
        created_at="2026-03-19T00:03:00Z",
        decision="WAIT",
        manual_decision="APPROVE",
    )
    _append_intent(
        fixture,
        intent_id="intent-dispatched",
        created_at="2026-03-19T00:04:00Z",
        decision="WAIT",
        manual_decision="APPROVE",
    )
    _append_dispatch_result(
        fixture,
        execution_id="strategy_exec_done",
        intent_id="intent-dispatched",
        created_at="2026-03-19T00:05:00Z",
    )
    _append_execution_event(fixture, captured_at="2026-03-19T00:06:00Z")
    fixture.ops_state.append_session_event(
        OpsSessionEventRecord(
            event_type="start",
            session_id="ops_session_1",
            occurred_at="2026-03-19T00:07:00Z",
            started_at="2026-03-19T00:07:00Z",
            label="desk",
        )
    )

    result = fixture.service.status()

    assert result.active_session is not None
    assert result.active_session.session_id == "ops_session_1"
    assert result.pending_review_count == 2
    assert result.approved_dispatch_ready_count == 1
    assert result.recent_strategy_execution_count == 1
    assert result.recent_execution_event_count == 1
    assert result.risk_policies_persisted is False
    assert result.latest_activity.latest_session_activity_at == "2026-03-19T00:07:00Z"


def test_queue_and_review_next_ordering(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_intent(
        fixture,
        intent_id="intent-wait-older",
        created_at="2026-03-19T00:01:00Z",
        decision="WAIT",
    )
    _append_intent(
        fixture,
        intent_id="intent-observe-newest",
        created_at="2026-03-19T00:04:00Z",
        decision="OBSERVE",
    )
    _append_intent(
        fixture,
        intent_id="intent-wait-newest",
        created_at="2026-03-19T00:05:00Z",
        decision="WAIT",
    )
    _append_intent(
        fixture,
        intent_id="intent-approved",
        created_at="2026-03-19T00:06:00Z",
        decision="WAIT",
        manual_decision="APPROVE",
    )

    queue = fixture.service.queue(limit=10)
    next_item = fixture.service.review_next()

    assert queue.counts.total == 4
    assert queue.counts.review_total == 3
    assert queue.counts.dispatch_total == 1
    assert [item.intent.intent.intent_id for item in queue.items] == [
        "intent-wait-newest",
        "intent-wait-older",
        "intent-observe-newest",
        "intent-approved",
    ]
    assert next_item.queue_empty is False
    assert next_item.item is not None
    assert next_item.item.intent.intent.intent_id == "intent-wait-newest"


def test_session_start_end_single_active(tmp_path, monkeypatch) -> None:
    fixture = _fixture(tmp_path)
    timestamps = iter(["2026-03-19T00:00:00Z", "2026-03-19T00:10:00Z"])
    monkeypatch.setattr("pm.ops.service._utc_now", lambda: next(timestamps))

    started = fixture.service.start_session(label="desk")
    assert started.session.active is True

    with pytest.raises(OpsValidationError):
        fixture.service.start_session(label="second")

    ended = fixture.service.end_session()
    assert ended.session.active is False
    assert ended.session.summary_snapshot is not None

    with pytest.raises(OpsSessionNotFoundError):
        fixture.service.end_session()


def test_dispatch_approved_reuses_paper_dispatch(tmp_path) -> None:
    fake_dispatch = FakeStrategyDispatchService()
    fixture = _fixture(tmp_path, dispatch_service=fake_dispatch)
    fixture.ops_state.append_session_event(
        OpsSessionEventRecord(
            event_type="start",
            session_id="ops_session_1",
            occurred_at="2026-03-19T00:00:00Z",
            started_at="2026-03-19T00:00:00Z",
            label="desk",
        )
    )

    result = fixture.service.dispatch_approved(limit=5)

    assert fake_dispatch.last_limit == 5
    assert result.active_session is not None
    assert result.total_dispatched == 1
    assert result.items[0].execution.decision == "WOULD_POST"


def test_report_uses_latest_completed_session(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_intent(
        fixture,
        intent_id="intent-before",
        created_at="2026-03-19T00:00:30Z",
        decision="WAIT",
    )
    _append_intent(
        fixture,
        intent_id="intent-during",
        created_at="2026-03-19T00:01:30Z",
        decision="WAIT",
        manual_decision="APPROVE",
    )
    _append_dispatch_result(
        fixture,
        execution_id="strategy_exec_1",
        intent_id="intent-during",
        created_at="2026-03-19T00:02:00Z",
    )
    _append_execution_event(fixture, captured_at="2026-03-19T00:02:30Z")
    fixture.ops_state.append_session_event(
        OpsSessionEventRecord(
            event_type="start",
            session_id="ops_session_1",
            occurred_at="2026-03-19T00:01:00Z",
            started_at="2026-03-19T00:01:00Z",
            label="desk",
        )
    )
    fixture.ops_state.append_session_event(
        OpsSessionEventRecord(
            event_type="end",
            session_id="ops_session_1",
            occurred_at="2026-03-19T00:03:00Z",
            ended_at="2026-03-19T00:03:00Z",
            summary_snapshot=OpsSessionSummarySnapshot(),
        )
    )

    report = fixture.service.report()

    assert report.session is not None
    assert report.session.session_id == "ops_session_1"
    assert report.summary.approval_count == 1
    assert report.summary.dispatch_attempt_count == 1
    assert report.summary.execution_event_count == 1
    assert len(report.recent_strategy_executions) == 1
    assert len(report.recent_execution_events) == 1


def test_invalid_ops_state_raises(tmp_path) -> None:
    path = tmp_path / "ops-sessions.json"
    path.write_text("{bad json", encoding="utf-8")
    service = OpsStateService(sessions_path=path)

    with pytest.raises(OpsStateError):
        service.list_sessions()
