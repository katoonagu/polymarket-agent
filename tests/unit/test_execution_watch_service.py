from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pm.auth.models import AuthContext
from pm.execution import (
    CapturedExecutionEvent,
    ExecutionNotFoundError,
    ExecutionStateError,
    ExecutionStateService,
    ExecutionWatchService,
    NormalizedOrder,
    OpenOrdersResponse,
    OrderGetResponse,
    normalize_user_message,
)
from pm.execution.watch import ExecutionBoundedRunResult, ExecutionUserWebSocketClient
from pm.stream.models import BoundedStreamSession


class FakeWebSocket:
    def __init__(self, messages: list[object]) -> None:
        self._messages = list(messages)
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self) -> str:
        if self._messages:
            item = self._messages.pop(0)
            if isinstance(item, Exception):
                raise item
            return str(item)
        await asyncio.sleep(1)
        return "PONG"


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self._websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self._websocket

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeWatchAuthService:
    def require_valid_config(self) -> object:
        return object()

    def get_api_credentials(self, settings: object | None = None) -> object:
        return type(
            "FakeCreds",
            (),
            {
                "api_key": "derived-key",
                "api_secret": "derived-secret",
                "api_passphrase": "derived-passphrase",
            },
        )()


class FakeLifecycleService:
    def __init__(
        self,
        *,
        open_orders: list[NormalizedOrder] | None = None,
        orders_by_id: dict[str, NormalizedOrder] | None = None,
    ) -> None:
        self._open_orders = open_orders or []
        self._orders_by_id = orders_by_id or {}

    def orders_open(
        self,
        *,
        market: str | None = None,
        token_id: str | None = None,
    ) -> OpenOrdersResponse:
        items = self._open_orders
        if market is not None:
            items = [item for item in items if item.market == market]
        if token_id is not None:
            items = [item for item in items if item.asset_id == token_id]
        return OpenOrdersResponse(auth=_auth_context(), items=items, total=len(items))

    def order_get(self, *, order_id: str) -> OrderGetResponse:
        order = self._orders_by_id.get(order_id)
        if order is None:
            raise ExecutionNotFoundError(f"Order '{order_id}' was not found.")
        return OrderGetResponse(auth=_auth_context(), order=order)


class FakeExecutionWatchClient:
    def __init__(self, result: ExecutionBoundedRunResult) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    async def watch_conditions(
        self,
        condition_ids: list[str],
        *,
        seconds: int,
        max_events: int | None = None,
        order_id: str | None = None,
    ) -> ExecutionBoundedRunResult:
        self.calls.append(
            {
                "condition_ids": condition_ids,
                "seconds": seconds,
                "max_events": max_events,
                "order_id": order_id,
            }
        )
        return self._result


def test_normalize_user_placement_event() -> None:
    payload = {
        "event_type": "PLACEMENT",
        "market": "0x" + ("a" * 64),
        "asset_id": "100",
        "order_id": "order-1",
        "side": "BUY",
        "price": "0.55",
        "size": "10",
        "status": "OPEN",
        "timestamp": 1710000000,
    }

    events = normalize_user_message(payload)

    assert len(events) == 1
    assert events[0].event_type == "PLACEMENT"
    assert events[0].condition_id == "0x" + ("a" * 64)
    assert events[0].order_id == "order-1"


def test_normalize_user_trade_status_maps_to_update() -> None:
    payload = {
        "trades": [
            {
                "market": "0x" + ("a" * 64),
                "asset_id": "100",
                "order_id": "order-1",
                "status": "MATCHED",
                "price": "0.55",
                "size": "5",
                "timestamp": 1710000001,
            }
        ]
    }

    events = normalize_user_message(payload)

    assert len(events) == 1
    assert events[0].event_type == "UPDATE"
    assert events[0].trade_status == "MATCHED"


def test_execution_user_ws_persists_events_and_stops_by_max_events(tmp_path: Path) -> None:
    state = _state_service(tmp_path)
    websocket = FakeWebSocket(
        [
            json.dumps(
                {
                    "event_type": "PLACEMENT",
                    "market": "0x" + ("a" * 64),
                    "asset_id": "100",
                    "order_id": "order-1",
                }
            ),
            json.dumps(
                {
                    "event_type": "UPDATE",
                    "market": "0x" + ("a" * 64),
                    "asset_id": "100",
                    "order_id": "order-1",
                    "status": "MATCHED",
                }
            ),
            json.dumps(
                {
                    "event_type": "CANCELLATION",
                    "market": "0x" + ("a" * 64),
                    "asset_id": "100",
                    "order_id": "order-1",
                }
            ),
        ]
    )
    client = ExecutionUserWebSocketClient(
        auth_service=FakeWatchAuthService(),
        state_service=state,
        connect=lambda *args, **kwargs: FakeConnection(websocket),
    )

    async def run() -> None:
        result = await client.watch_conditions(
            ["0x" + ("a" * 64)],
            seconds=5,
            max_events=2,
        )
        assert result.session.captured_event_count == 2
        assert len(result.events) == 2

    asyncio.run(run())

    persisted = state.list_execution_events()
    assert len(persisted) == 2
    assert persisted[0].event_type == "PLACEMENT"


def test_execution_user_ws_returns_partial_error_after_reconnect_exhaustion(
    tmp_path: Path,
) -> None:
    state = _state_service(tmp_path)
    connections = [
        FakeConnection(
            FakeWebSocket(
                [
                    json.dumps(
                        {
                            "event_type": "UPDATE",
                            "market": "0x" + ("a" * 64),
                            "asset_id": "100",
                            "order_id": "order-1",
                        }
                    ),
                    RuntimeError("socket dropped"),
                ]
            )
        )
    ]

    def connect(*args: object, **kwargs: object) -> FakeConnection:
        if connections:
            return connections.pop(0)
        raise RuntimeError("socket dropped")

    client = ExecutionUserWebSocketClient(
        auth_service=FakeWatchAuthService(),
        state_service=state,
        connect=connect,
        sleep=lambda delay: asyncio.sleep(0),
    )

    async def run() -> None:
        result = await client.watch_conditions(
            ["0x" + ("a" * 64)],
            seconds=1,
            max_events=5,
        )
        assert result.session.captured_event_count == 1
        assert result.session.reconnect_count == 2
        assert result.errors
        assert result.errors[0].section == "execution_watch"

    asyncio.run(run())


def test_order_wait_returns_terminal_on_cancellation(tmp_path: Path) -> None:
    order = _order("order-1", status="OPEN")
    watch_client = FakeExecutionWatchClient(
        _run_result(
            [
                _event(order_id="order-1", event_type="PLACEMENT"),
                _event(order_id="order-1", event_type="CANCELLATION"),
            ]
        )
    )
    service = ExecutionWatchService(
        lifecycle_service=FakeLifecycleService(orders_by_id={"order-1": order}),
        state_service=_state_service(tmp_path),
        watch_client=watch_client,
    )

    result = service.wait_for_order(order_id="order-1", seconds=2)

    assert result.terminal is True
    assert result.timed_out is False
    assert result.terminal_outcome == "CANCELLATION"
    assert watch_client.calls[0]["order_id"] == "order-1"


def test_order_wait_timeout_fetches_final_rest_order(tmp_path: Path) -> None:
    order = _order("order-1", status="OPEN")
    service = ExecutionWatchService(
        lifecycle_service=FakeLifecycleService(orders_by_id={"order-1": order}),
        state_service=_state_service(tmp_path),
        watch_client=FakeExecutionWatchClient(_run_result([_event(order_id="order-1")])),
    )

    result = service.wait_for_order(order_id="order-1", seconds=2)

    assert result.terminal is False
    assert result.timed_out is True
    assert result.final_order is not None
    assert result.final_order.status == "OPEN"


def test_reconcile_classifies_orders_and_persists_summary(tmp_path: Path) -> None:
    state = _state_service(tmp_path)
    state.append_execution_events(
        [
            _event(order_id="order-open", event_type="UPDATE"),
            _event(order_id="order-closed", event_type="CANCELLATION"),
            _event(order_id="order-mid", event_type="UPDATE", trade_status="MATCHED"),
            _event(order_id="order-mismatch", event_type="PLACEMENT"),
        ]
    )
    lifecycle = FakeLifecycleService(
        open_orders=[_order("order-open", status="OPEN"), _order("order-mid", status="OPEN")],
        orders_by_id={
            "order-open": _order("order-open", status="OPEN"),
            "order-closed": _order("order-closed", status="CANCELED"),
            "order-mid": _order("order-mid", status="OPEN"),
        },
    )
    service = ExecutionWatchService(
        lifecycle_service=lifecycle,
        state_service=state,
        watch_client=FakeExecutionWatchClient(_run_result([])),
    )

    result = service.reconcile()

    assert result.summary.total_orders == 4
    assert result.summary.consistent_open == 1
    assert result.summary.consistent_closed == 1
    assert result.summary.inconclusive == 1
    assert result.summary.mismatch == 1
    assert len(state.list_reconciliations()) == 1


def test_execution_state_invalid_event_log_raises(tmp_path: Path) -> None:
    state = _state_service(tmp_path)
    (tmp_path / "execution-events.jsonl").write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ExecutionStateError):
        state.list_execution_events()


def test_execution_state_invalid_reconciliations_raises(tmp_path: Path) -> None:
    state = _state_service(tmp_path)
    (tmp_path / "execution-reconciliations.json").write_text(
        '{"version":1,"reconciliations":"bad"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ExecutionStateError):
        state.list_reconciliations()


def _state_service(tmp_path: Path) -> ExecutionStateService:
    return ExecutionStateService(
        approval_plans_path=tmp_path / "approval-plans.json",
        approval_results_path=tmp_path / "approval-results.json",
        order_plans_path=tmp_path / "execution-order-plans.json",
        order_results_path=tmp_path / "execution-order-results.json",
        events_path=tmp_path / "execution-events.jsonl",
        reconciliations_path=tmp_path / "execution-reconciliations.json",
    )


def _run_result(events: list[CapturedExecutionEvent]) -> ExecutionBoundedRunResult:
    return ExecutionBoundedRunResult(
        session=BoundedStreamSession(
            session_id="session-1",
            stream_kind="execution_user",
            source="polymarket_user_ws",
            started_at="2026-03-18T00:00:00Z",
            ended_at="2026-03-18T00:00:02Z",
            duration_seconds=2,
            requested_seconds=2,
            max_events=None,
            captured_event_count=len(events),
            reconnect_count=0,
        ),
        events=events,
        errors=[],
    )


def _event(
    *,
    order_id: str,
    event_type: str = "UPDATE",
    trade_status: str | None = None,
) -> CapturedExecutionEvent:
    return CapturedExecutionEvent(
        session_id="session-1",
        source="polymarket_user_ws",
        captured_at="2026-03-18T00:00:01Z",
        condition_id="0x" + ("a" * 64),
        order_id=order_id,
        asset_id="100",
        event_type=event_type,
        trade_status=trade_status,
        side="BUY",
        price="0.55",
        size="10",
        status="OPEN",
        timestamp=1710000000,
    )


def _order(order_id: str, *, status: str) -> NormalizedOrder:
    return NormalizedOrder(
        order_id=order_id,
        market="0x" + ("a" * 64),
        asset_id="100",
        side="BUY",
        status=status,
        price="0.55",
        size="10",
    )


def _auth_context() -> AuthContext:
    return AuthContext(
        signer_address="0x" + ("3" * 40),
        funder_address=None,
        signature_type=0,
        signature_type_name="EOA",
        clob_host="https://clob.polymarket.com",
        chain_id=137,
        private_key_present=True,
        api_key_derivation_possible=True,
    )
