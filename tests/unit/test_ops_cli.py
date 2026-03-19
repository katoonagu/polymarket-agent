"""CLI tests for the operator control plane and workflow session commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.execution.models import (
    CapturedExecutionEvent,
    ExecutionReconciliationRecord,
    ExecutionReconciliationSummary,
)
from pm.ops import (
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
    OpsSessionMutationResponse,
    OpsSessionSummarySnapshot,
    OpsSessionView,
    OpsStatusResponse,
    OpsVerboseStatusResponse,
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


def _recent_event() -> CapturedExecutionEvent:
    return CapturedExecutionEvent(
        session_id="session-1",
        source="polymarket_user_ws",
        captured_at="2026-03-19T00:02:00Z",
        condition_id="0x" + ("a" * 64),
        order_id="order-1",
        asset_id="100",
        event_type="UPDATE",
        trade_status="MATCHED",
        side="BUY",
        price="0.55",
        size="10",
        status="OPEN",
        timestamp=1710806400,
    )


def _dispatch_item(*, mode: str = "paper") -> StrategyDispatchResponse:
    intent = _intent_view(intent_id="intent-dispatch", current_decision="APPROVE")
    return StrategyDispatchResponse(
        intent=intent,
        link=StrategyExecutionLinkRecord(
            execution_id="strategy_exec_123",
            intent_id=intent.intent.intent_id,
            strategy_name=intent.intent.strategy_name,
            strategy_type=intent.intent.strategy_type,
            mode=mode,
            created_at="2026-03-19T00:01:00Z",
            execution_plan_id="plan-123",
            execution_result_id="result-123",
        ),
        execution=StrategyDispatchResultRecord(
            execution_id="strategy_exec_123",
            intent_id=intent.intent.intent_id,
            strategy_name=intent.intent.strategy_name,
            strategy_type=intent.intent.strategy_type,
            mode=mode,
            decision="WOULD_POST",
            created_at="2026-03-19T00:01:00Z",
            market_slug="btc-15m",
            condition_id="0x" + ("a" * 64),
            token_id="100",
            outcome="Yes",
            side="BUY",
        ),
    )


class FakeOpsService:
    def bootstrap(self) -> OpsBootstrapResponse:
        return OpsBootstrapResponse(
            ready=True,
            risk_initialized=True,
            risk_policies_persisted=True,
            session_started=True,
            active_session=_session(),
            status=self.status(),
        )

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

    def verbose_status(self) -> OpsVerboseStatusResponse:
        return OpsVerboseStatusResponse(
            **self.status().model_dump(mode="json"),
            queue=self.queue(limit=10),
            recent_strategy_executions=[_dispatch_item().execution],
            recent_execution_events=[_recent_event()],
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
                    intent=_intent_view(
                        intent_id="intent-dispatch",
                        current_decision="APPROVE",
                    ),
                ),
            ],
            counts=OpsQueueCounts(total=2, review_total=1, dispatch_total=1),
        )

    def cycle_queue(self, *, limit: int = 20) -> OpsCycleQueueResponse:
        return OpsCycleQueueResponse(
            active_session=_session(),
            limit_per_strategy=limit,
            items=[
                OpsCycleQueueItem(
                    strategy_name="wallet_shadow_copy",
                    strategy_type="wallet_shadow_copy",
                    total_new_intents=2,
                    total_errors=0,
                    errors=[],
                ),
                OpsCycleQueueItem(
                    strategy_name="market_watch_reversion",
                    strategy_type="market_watch_reversion",
                    total_new_intents=0,
                    total_errors=0,
                    errors=[],
                ),
                OpsCycleQueueItem(
                    strategy_name="recurring_crypto_interval_observe",
                    strategy_type="recurring_crypto_interval_observe",
                    total_new_intents=0,
                    total_errors=1,
                    errors=[],
                ),
            ],
            total_new_intents=2,
            queue_counts=OpsQueueCounts(total=2, review_total=1, dispatch_total=1),
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
        return self.cycle_approved(limit=limit, live=False)

    def cycle_approved(
        self,
        *,
        limit: int = 20,
        live: bool = False,
    ) -> OpsDispatchApprovedResponse:
        _ = limit
        return OpsDispatchApprovedResponse(
            active_session=_session(),
            mode="live" if live else "paper",
            noop=False,
            items=[_dispatch_item(mode="live" if live else "paper")],
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
            recent_strategy_executions=[_dispatch_item().execution],
            recent_execution_events=[],
        )

    def cycle_report(self) -> OpsCycleReportResponse:
        return OpsCycleReportResponse(
            session=_session(active=False),
            queue_counts=OpsQueueCounts(total=2, review_total=1, dispatch_total=1),
            approved_intent_count=2,
            dispatch_ready_intent_count=1,
            recent_strategy_executions=[_dispatch_item().execution],
            recent_execution_events=[_recent_event()],
            latest_reconciliation=ExecutionReconciliationRecord(
                reconciliation_id="recon_123",
                created_at="2026-03-19T00:03:00Z",
                summary=ExecutionReconciliationSummary(
                    window_event_count=1,
                    total_orders=1,
                    consistent_open=1,
                    consistent_closed=0,
                    inconclusive=0,
                    mismatch=0,
                ),
                items=[],
                errors=[],
            ),
        )


def test_root_help_lists_status_and_ops() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "ops" in result.stdout


def test_ops_help_lists_session_review_dispatch_cycle() -> None:
    result = runner.invoke(app, ["ops", "--help"])

    assert result.exit_code == 0
    assert "bootstrap" in result.stdout
    assert "queue" in result.stdout
    assert "session" in result.stdout
    assert "review" in result.stdout
    assert "dispatch" in result.stdout
    assert "cycle" in result.stdout
    assert "report" in result.stdout


def test_ops_cycle_help_lists_queue_approved_report() -> None:
    result = runner.invoke(app, ["ops", "cycle", "--help"])

    assert result.exit_code == 0
    assert "queue" in result.stdout
    assert "approved" in result.stdout
    assert "report" in result.stdout


def test_status_and_ops_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    status_result = runner.invoke(app, ["status", "--json"])
    bootstrap_result = runner.invoke(app, ["ops", "bootstrap", "--json"])
    queue_result = runner.invoke(app, ["ops", "queue", "--limit", "5", "--json"])
    cycle_queue_result = runner.invoke(
        app,
        ["ops", "cycle", "queue", "--limit", "5", "--json"],
    )
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
    cycle_approved_result = runner.invoke(
        app,
        ["ops", "cycle", "approved", "--limit", "5", "--json"],
    )
    report_result = runner.invoke(app, ["ops", "report", "--json"])
    cycle_report_result = runner.invoke(app, ["ops", "cycle", "report", "--json"])

    assert status_result.exit_code == 0
    assert json.loads(status_result.stdout)["pending_review_count"] == 2

    assert bootstrap_result.exit_code == 0
    assert json.loads(bootstrap_result.stdout)["ready"] is True

    assert queue_result.exit_code == 0
    assert json.loads(queue_result.stdout)["counts"]["dispatch_total"] == 1

    assert cycle_queue_result.exit_code == 0
    assert json.loads(cycle_queue_result.stdout)["total_new_intents"] == 2

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

    assert cycle_approved_result.exit_code == 0
    assert json.loads(cycle_approved_result.stdout)["mode"] == "paper"

    assert report_result.exit_code == 0
    assert json.loads(report_result.stdout)["summary"]["manual_review_count"] == 2

    assert cycle_report_result.exit_code == 0
    assert json.loads(cycle_report_result.stdout)["latest_reconciliation"][
        "reconciliation_id"
    ] == "recon_123"


def test_status_verbose_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    result = runner.invoke(app, ["status", "--verbose", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["queue"]["counts"]["total"] == 2
    assert payload["recent_strategy_executions"][0]["execution_id"] == "strategy_exec_123"


def test_status_queue_human_tables(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    status_result = runner.invoke(app, ["status", "--verbose"])
    queue_result = runner.invoke(app, ["ops", "queue"])
    cycle_queue_result = runner.invoke(app, ["ops", "cycle", "queue"])
    cycle_report_result = runner.invoke(app, ["ops", "cycle", "report"])

    assert status_result.exit_code == 0
    assert "Operator Status" in status_result.stdout
    assert "Recent Strategy Executions" in status_result.stdout
    assert "Recent Execution Events" in status_result.stdout

    assert queue_result.exit_code == 0
    assert "Operator Queue" in queue_result.stdout
    assert "Intent ID" in queue_result.stdout

    assert cycle_queue_result.exit_code == 0
    assert "Cycle Queue Summary" in cycle_queue_result.stdout
    assert "Strategy Evaluation Pass" in cycle_queue_result.stdout

    assert cycle_report_result.exit_code == 0
    assert "Cycle Report" in cycle_report_result.stdout
    assert "Latest Reconciliation" in cycle_report_result.stdout


def test_cycle_approved_live_requires_confirm(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    result = runner.invoke(app, ["ops", "cycle", "approved", "--live", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_argument"
    assert payload["error"]["identifier"] == "confirm"


def test_cycle_approved_live_prompt_accepts(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)
    monkeypatch.setattr("pm.cli.support.interactive_allowed", lambda *args, **kwargs: True)

    result = runner.invoke(app, ["ops", "cycle", "approved", "--live"], input="y\n")

    assert result.exit_code == 0
    assert "live" in result.stdout
    assert "Dispatch Cycle Summary" in result.stdout


def test_root_output_json_works_for_status(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    result = runner.invoke(app, ["--output", "json", "status"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["approved_dispatch_ready_count"] == 1


def test_root_output_json_works_for_cycle_queue(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.ops.OpsService", FakeOpsService)

    result = runner.invoke(app, ["--output", "json", "ops", "cycle", "queue"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["limit_per_strategy"] == 20
