"""CLI tests for the operator control plane and workflow session commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.ops import (
    OpsDispatchApprovedResponse,
    OpsLatestActivity,
    OpsQueueCounts,
    OpsQueueItem,
    OpsQueueResponse,
    OpsReportResponse,
    OpsReviewNextResponse,
    OpsSessionMutationResponse,
    OpsSessionSummarySnapshot,
    OpsSessionView,
    OpsStatusResponse,
)
from pm.strategy.models import (
    StrategyCandidateIntent,
    StrategyDispatchResponse,
    StrategyDispatchResultRecord,
    StrategyExecutionLinkRecord,
    StrategyIntentView,
)

runner = CliRunner()


def _intent_view(
    *,
    intent_id: str = "intent-123",
    current_decision: str = "WAIT",
) -> StrategyIntentView:
    intent = StrategyCandidateIntent(
        intent_id=intent_id,
        strategy_name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        source_kind="wallet_shadow",
        market_slug="btc-15m",
        condition_id="0x" + ("a" * 64),
        token_id="100",
        side="BUY",
        outcome="Yes",
        decision="WAIT",
        reason_blocks=[],
        created_at="2026-03-19T00:00:00Z",
        source_refs=[],
    )
    return StrategyIntentView(
        intent=intent,
        current_decision=current_decision,
        latest_decision=None,
    )


def _session(active: bool = True) -> OpsSessionView:
    return OpsSessionView(
        session_id="ops_session_123",
        label="desk",
        started_at="2026-03-19T00:00:00Z",
        ended_at=None if active else "2026-03-19T00:10:00Z",
        active=active,
        summary_snapshot=None,
    )


class FakeOpsService:
    def status(self) -> OpsStatusResponse:
        return OpsStatusResponse(
            active_session=_session(),
            pending_review_count=2,
            approved_dispatch_ready_count=1,
            recent_strategy_execution_count=1,
            recent_execution_event_count=1,
            risk_policies_persisted=False,
            latest_activity=OpsLatestActivity(
                latest_intent_created_at="2026-03-19T00:01:00Z",
                latest_manual_decision_at="2026-03-19T00:02:00Z",
                latest_dispatch_at="2026-03-19T00:03:00Z",
                latest_execution_event_at="2026-03-19T00:04:00Z",
                latest_session_activity_at="2026-03-19T00:05:00Z",
            ),
        )

    def queue(self, *, limit: int = 20) -> OpsQueueResponse:
        _ = limit
        return OpsQueueResponse(
            items=[
                OpsQueueItem(
                    kind="review",
                    note="Unreviewed WAIT intent is ready for operator review.",
                    intent=_intent_view(intent_id="intent-review", current_decision="WAIT"),
                ),
                OpsQueueItem(
                    kind="dispatch",
                    note="Approved intent is dispatch-ready.",
                    intent=_intent_view(intent_id="intent-dispatch", current_decision="APPROVE"),
                ),
            ],
            counts=OpsQueueCounts(total=2, review_total=1, dispatch_total=1),
        )

    def start_session(self, *, label: str | None = None) -> OpsSessionMutationResponse:
        session = _session()
        return OpsSessionMutationResponse(
            action="started",
            session=session.model_copy(update={"label": label or session.label}),
        )

    def end_session(self) -> OpsSessionMutationResponse:
        return OpsSessionMutationResponse(
            action="ended",
            session=_session(active=False).model_copy(
                update={
                    "summary_snapshot": OpsSessionSummarySnapshot(
                        pending_review_count=1,
                        approved_dispatch_ready_count=1,
                        manual_review_count=2,
                        approval_count=1,
                        rejection_count=1,
                        dispatch_attempt_count=1,
                        would_post_count=1,
                        posted_count=0,
                        skipped_count=0,
                        execution_event_count=2,
                    )
                }
            ),
        )

    def review_next(self) -> OpsReviewNextResponse:
        return OpsReviewNextResponse(
            queue_empty=False,
            item=OpsQueueItem(
                kind="review",
                note="Unreviewed WAIT intent is ready for operator review.",
                intent=_intent_view(intent_id="intent-next", current_decision="WAIT"),
            ),
        )

    def dispatch_approved(self, *, limit: int = 20) -> OpsDispatchApprovedResponse:
        _ = limit
        intent = _intent_view(intent_id="intent-dispatch", current_decision="APPROVE")
        item = StrategyDispatchResponse(
            intent=intent,
            link=StrategyExecutionLinkRecord(
                execution_id="strategy_exec_123",
                intent_id=intent.intent.intent_id,
                strategy_name=intent.intent.strategy_name,
                strategy_type=intent.intent.strategy_type,
                mode="paper",
                created_at="2026-03-19T00:01:00Z",
                execution_plan_id="plan-123",
                execution_result_id="result-123",
            ),
            execution=StrategyDispatchResultRecord(
                execution_id="strategy_exec_123",
                intent_id=intent.intent.intent_id,
                strategy_name=intent.intent.strategy_name,
                strategy_type=intent.intent.strategy_type,
                mode="paper",
                decision="WOULD_POST",
                created_at="2026-03-19T00:01:00Z",
                market_slug="btc-15m",
                condition_id="0x" + ("a" * 64),
                token_id="100",
                outcome="Yes",
                side="BUY",
            ),
        )
        return OpsDispatchApprovedResponse(
            active_session=_session(),
            items=[item],
            total_candidates=1,
            total_dispatched=1,
            total_skipped=0,
        )

    def report(self) -> OpsReportResponse:
        return OpsReportResponse(
            session=_session(active=False),
            queue_counts=OpsQueueCounts(total=2, review_total=1, dispatch_total=1),
            summary=OpsSessionSummarySnapshot(
                pending_review_count=1,
                approved_dispatch_ready_count=1,
                manual_review_count=2,
                approval_count=1,
                rejection_count=1,
                dispatch_attempt_count=1,
                would_post_count=1,
                posted_count=0,
                skipped_count=0,
                execution_event_count=2,
            ),
            recent_strategy_executions=[
                StrategyDispatchResultRecord(
                    execution_id="strategy_exec_123",
                    intent_id="intent-dispatch",
                    strategy_name="wallet_shadow_copy",
                    strategy_type="wallet_shadow_copy",
                    mode="paper",
                    decision="WOULD_POST",
                    created_at="2026-03-19T00:01:00Z",
                )
            ],
            recent_execution_events=[],
        )


def test_root_help_lists_status_and_ops() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "ops" in result.stdout


def test_ops_help_lists_session_review_dispatch() -> None:
    result = runner.invoke(app, ["ops", "--help"])

    assert result.exit_code == 0
    assert "queue" in result.stdout
    assert "session" in result.stdout
    assert "review" in result.stdout
    assert "dispatch" in result.stdout
    assert "report" in result.stdout


def test_status_and_ops_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    status_result = runner.invoke(app, ["status", "--json"])
    queue_result = runner.invoke(app, ["ops", "queue", "--limit", "5", "--json"])
    start_result = runner.invoke(
        app,
        ["ops", "session", "start", "--label", "desk", "--json"],
    )
    end_result = runner.invoke(app, ["ops", "session", "end", "--json"])
    review_result = runner.invoke(app, ["ops", "review", "next", "--json"])
    dispatch_result = runner.invoke(
        app,
        ["ops", "dispatch", "approved", "--limit", "5", "--json"],
    )
    report_result = runner.invoke(app, ["ops", "report", "--json"])

    assert status_result.exit_code == 0
    assert json.loads(status_result.stdout)["pending_review_count"] == 2

    assert queue_result.exit_code == 0
    assert json.loads(queue_result.stdout)["counts"]["dispatch_total"] == 1

    assert start_result.exit_code == 0
    assert json.loads(start_result.stdout)["action"] == "started"

    assert end_result.exit_code == 0
    assert json.loads(end_result.stdout)["session"]["active"] is False

    assert review_result.exit_code == 0
    assert (
        json.loads(review_result.stdout)["item"]["intent"]["intent"]["intent_id"]
        == "intent-next"
    )

    assert dispatch_result.exit_code == 0
    assert json.loads(dispatch_result.stdout)["total_dispatched"] == 1

    assert report_result.exit_code == 0
    assert json.loads(report_result.stdout)["summary"]["manual_review_count"] == 2


def test_root_output_json_works_for_status(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    result = runner.invoke(app, ["--output", "json", "status"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["approved_dispatch_ready_count"] == 1
