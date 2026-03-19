from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.execution import ExecutionNotFoundError
from pm.execution.models import (
    CapturedExecutionEvent,
    ExecutionEventsResponse,
    ExecutionReconciliationItem,
    ExecutionReconciliationResponse,
    ExecutionReconciliationSummary,
    ExecutionWatchResponse,
    ExecutionWatchSummary,
    NormalizedOrder,
    OrderWaitResponse,
)
from pm.stream.models import BoundedStreamSession

runner = CliRunner()


class FakeExecutionWatchCLIService:
    def watch(
        self,
        *,
        market: str | None = None,
        seconds: int = 10,
        max_events: int | None = None,
    ) -> ExecutionWatchResponse:
        return ExecutionWatchResponse(
            session=_session(),
            summary=ExecutionWatchSummary(
                watched_condition_ids=[market or "0x" + ("a" * 64)],
                event_counts={"PLACEMENT": 1, "UPDATE": 1, "CANCELLATION": 0},
                trade_status_counts={
                    "MATCHED": 1,
                    "MINED": 0,
                    "CONFIRMED": 0,
                    "RETRYING": 0,
                    "FAILED": 0,
                },
                distinct_order_count=1,
                reconnect_count=0,
            ),
            events=[_event()],
            errors=[],
        )

    def wait_for_order(self, *, order_id: str, seconds: int) -> OrderWaitResponse:
        return OrderWaitResponse(
            order_id=order_id,
            condition_id="0x" + ("a" * 64),
            session=_session(),
            terminal=True,
            timed_out=False,
            terminal_outcome="CONFIRMED",
            final_event=_event(order_id=order_id, trade_status="CONFIRMED"),
            final_order=NormalizedOrder(
                order_id=order_id,
                market="0x" + ("a" * 64),
                asset_id="100",
                side="BUY",
                status="FILLED",
                price="0.55",
                size="10",
            ),
            events=[_event(order_id=order_id, trade_status="MATCHED")],
            errors=[],
        )

    def list_events(self, *, limit: int = 20) -> ExecutionEventsResponse:
        return ExecutionEventsResponse(items=[_event()], total=1)

    def reconcile(self) -> ExecutionReconciliationResponse:
        latest_event = _event()
        return ExecutionReconciliationResponse(
            reconciliation_id="execution_reconciliation_1",
            created_at="2026-03-18T00:00:02Z",
            summary=ExecutionReconciliationSummary(
                window_event_count=4,
                total_orders=1,
                consistent_open=1,
                consistent_closed=0,
                inconclusive=0,
                mismatch=0,
            ),
            items=[
                ExecutionReconciliationItem(
                    order_id="order-1",
                    condition_id="0x" + ("a" * 64),
                    latest_event=latest_event,
                    latest_event_type="UPDATE",
                    latest_trade_status="MATCHED",
                    classification="consistent_open",
                    message="Latest websocket event still matches an open order view.",
                    rest_order=NormalizedOrder(
                        order_id="order-1",
                        market="0x" + ("a" * 64),
                        asset_id="100",
                        side="BUY",
                        status="OPEN",
                        price="0.55",
                        size="10",
                    ),
                )
            ],
            errors=[],
        )


def test_exec_help_lists_watch_surface() -> None:
    result = runner.invoke(app, ["exec", "--help"])

    assert result.exit_code == 0
    assert "watch" in result.stdout
    assert "events" in result.stdout
    assert "reconcile" in result.stdout


def test_exec_watch_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.execution.ExecutionWatchService",
        lambda: FakeExecutionWatchCLIService(),
    )

    result = runner.invoke(
        app,
        ["exec", "watch", "--market", "0x" + ("a" * 64), "--seconds", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["distinct_order_count"] == 1
    assert payload["events"][0]["event_type"] == "UPDATE"


def test_exec_order_wait_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.execution.ExecutionWatchService",
        lambda: FakeExecutionWatchCLIService(),
    )

    result = runner.invoke(
        app,
        ["exec", "order", "wait", "--order-id", "order-1", "--seconds", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["terminal_outcome"] == "CONFIRMED"
    assert payload["final_order"]["status"] == "FILLED"


def test_exec_events_and_reconcile_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.execution.ExecutionWatchService",
        lambda: FakeExecutionWatchCLIService(),
    )

    events_result = runner.invoke(app, ["exec", "events", "--limit", "5", "--json"])
    reconcile_result = runner.invoke(app, ["exec", "reconcile", "--json"])

    assert events_result.exit_code == 0
    assert reconcile_result.exit_code == 0
    assert json.loads(events_result.stdout)["total"] == 1
    assert json.loads(reconcile_result.stdout)["summary"]["consistent_open"] == 1


def test_exec_watch_root_output_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.execution.ExecutionWatchService",
        lambda: FakeExecutionWatchCLIService(),
    )

    result = runner.invoke(
        app,
        ["--output", "json", "exec", "watch", "--market", "0x" + ("a" * 64)],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["session"]["stream_kind"] == "execution_user"


def test_exec_watch_no_open_orders_returns_not_found(monkeypatch) -> None:
    class MissingWatchService(FakeExecutionWatchCLIService):
        def watch(self, **kwargs: object) -> ExecutionWatchResponse:
            raise ExecutionNotFoundError("No open-order condition ids were found.")

    monkeypatch.setattr("pm.cli.execution.ExecutionWatchService", lambda: MissingWatchService())

    result = runner.invoke(app, ["exec", "watch", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "not_found"


def test_exec_events_human_table(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.execution.ExecutionWatchService",
        lambda: FakeExecutionWatchCLIService(),
    )

    result = runner.invoke(app, ["exec", "events", "--limit", "5"])

    assert result.exit_code == 0
    assert "Execution Events" in result.stdout
    assert "Order ID" in result.stdout
    assert "MATCHED" in result.stdout


def _session() -> BoundedStreamSession:
    return BoundedStreamSession(
        session_id="session-1",
        stream_kind="execution_user",
        source="polymarket_user_ws",
        started_at="2026-03-18T00:00:00Z",
        ended_at="2026-03-18T00:00:02Z",
        duration_seconds=2,
        requested_seconds=2,
        max_events=None,
        captured_event_count=1,
        reconnect_count=0,
    )


def _event(
    *,
    order_id: str = "order-1",
    trade_status: str | None = "MATCHED",
) -> CapturedExecutionEvent:
    return CapturedExecutionEvent(
        session_id="session-1",
        source="polymarket_user_ws",
        captured_at="2026-03-18T00:00:01Z",
        condition_id="0x" + ("a" * 64),
        order_id=order_id,
        asset_id="100",
        event_type="UPDATE",
        trade_status=trade_status,
        side="BUY",
        price="0.55",
        size="10",
        status="OPEN",
        timestamp=1710000000,
    )
