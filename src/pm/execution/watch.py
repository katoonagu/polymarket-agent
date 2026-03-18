"""Authenticated bounded user-websocket watch and reconciliation helpers."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from pm.auth import AuthClientError, AuthService, AuthValidationError
from pm.execution.exceptions import ExecutionNotFoundError, ExecutionValidationError
from pm.execution.lifecycle import OrderLifecycleService
from pm.execution.models import (
    CapturedExecutionEvent,
    ExecutionEventsResponse,
    ExecutionReconciliationItem,
    ExecutionReconciliationRecord,
    ExecutionReconciliationResponse,
    ExecutionReconciliationSummary,
    ExecutionWatchResponse,
    ExecutionWatchSummary,
    NormalizedExecutionEvent,
    NormalizedOrder,
    OrderWaitResponse,
)
from pm.execution.state import ExecutionStateError, ExecutionStateService
from pm.stream.models import BoundedStreamSession, StreamSectionError
from pm.stream.runner import (
    StreamClientError,
    StreamValidationError,
    run_bounded_websocket_session,
)

DEFAULT_EXECUTION_USER_STREAM_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
SUPPORTED_EVENT_TYPES = ("PLACEMENT", "UPDATE", "CANCELLATION")
SUPPORTED_TRADE_STATUSES = ("MATCHED", "MINED", "CONFIRMED", "RETRYING", "FAILED")
DEFAULT_WATCH_SECONDS = 10
DEFAULT_EVENTS_LIMIT = 20
RECONCILIATION_WINDOW = 100


@dataclass(slots=True)
class ExecutionBoundedRunResult:
    """Typed bounded user-channel session result."""

    session: BoundedStreamSession
    events: list[CapturedExecutionEvent]
    errors: list[StreamSectionError]


class ExecutionWatchService:
    """High-level authenticated execution-watch and reconciliation service."""

    def __init__(
        self,
        *,
        auth_service: AuthService | None = None,
        lifecycle_service: OrderLifecycleService | None = None,
        state_service: ExecutionStateService | None = None,
        watch_client: ExecutionUserWebSocketClient | None = None,
    ) -> None:
        shared_auth = auth_service or AuthService()
        shared_state = state_service or ExecutionStateService()
        self._state_service = shared_state
        self._lifecycle_service = lifecycle_service or OrderLifecycleService(
            auth_service=shared_auth,
            state_service=shared_state,
        )
        self._watch_client = watch_client or ExecutionUserWebSocketClient(
            auth_service=shared_auth,
            state_service=shared_state,
        )

    def watch(
        self,
        *,
        market: str | None = None,
        seconds: int = DEFAULT_WATCH_SECONDS,
        max_events: int | None = None,
    ) -> ExecutionWatchResponse:
        """Run one bounded authenticated execution-watch session."""
        condition_ids = self._resolve_watch_condition_ids(market)
        result = asyncio.run(
            self._watch_client.watch_conditions(
                condition_ids,
                seconds=seconds,
                max_events=max_events,
            )
        )
        return ExecutionWatchResponse(
            session=result.session,
            summary=_build_watch_summary(condition_ids, result),
            events=result.events,
            errors=result.errors,
        )

    def wait_for_order(
        self,
        *,
        order_id: str,
        seconds: int,
    ) -> OrderWaitResponse:
        """Wait for one order to reach a terminal observed event or time out."""
        normalized_order_id = order_id.strip()
        if not normalized_order_id:
            raise ExecutionValidationError("Order id is required.")

        order = self._lifecycle_service.order_get(order_id=normalized_order_id).order
        condition_id = (order.market or "").strip()
        if not condition_id:
            raise ExecutionValidationError(
                "The requested order does not expose a condition id for websocket watching."
            )

        result = asyncio.run(
            self._watch_client.watch_conditions(
                [condition_id],
                seconds=seconds,
                max_events=None,
                order_id=normalized_order_id,
            )
        )

        final_event = _latest_terminal_event(result.events)
        timed_out = final_event is None
        terminal_outcome = (
            final_event.trade_status or final_event.event_type if final_event is not None else None
        )
        errors = list(result.errors)
        final_order = self._safe_order_get(normalized_order_id, errors=errors)

        return OrderWaitResponse(
            order_id=normalized_order_id,
            condition_id=condition_id,
            session=result.session,
            terminal=final_event is not None,
            timed_out=timed_out,
            terminal_outcome=terminal_outcome,
            final_event=final_event,
            final_order=final_order,
            events=result.events,
            errors=errors,
        )

    def list_events(self, *, limit: int = DEFAULT_EVENTS_LIMIT) -> ExecutionEventsResponse:
        """Return recent persisted execution-watch events newest first."""
        if limit <= 0:
            raise ExecutionValidationError("Limit must be greater than zero.")

        items = list(reversed(self._state_service.list_execution_events()))[:limit]
        return ExecutionEventsResponse(items=items, total=len(items))

    def reconcile(self) -> ExecutionReconciliationResponse:
        """Compare recent websocket events against current authenticated REST views."""
        created_at = _utc_now()
        reconciliation_id = _make_id("execution_reconciliation")
        recent_events = self._state_service.list_execution_events()[-RECONCILIATION_WINDOW:]
        latest_by_order: OrderedDict[str, CapturedExecutionEvent] = OrderedDict()
        for event in recent_events:
            if event.order_id:
                latest_by_order[event.order_id] = event

        open_orders = self._lifecycle_service.orders_open().items
        open_order_ids = {item.order_id for item in open_orders if item.order_id}
        items: list[ExecutionReconciliationItem] = []
        errors: list[StreamSectionError] = []

        ordered_events = sorted(
            latest_by_order.values(),
            key=lambda item: (item.captured_at, item.order_id or ""),
            reverse=True,
        )
        for latest_event in ordered_events:
            rest_order = self._safe_order_get(latest_event.order_id or "", errors=errors)
            classification, message = _classify_reconciliation(
                latest_event=latest_event,
                rest_order=rest_order,
                open_order_ids=open_order_ids,
            )
            items.append(
                ExecutionReconciliationItem(
                    order_id=latest_event.order_id or "",
                    condition_id=latest_event.condition_id,
                    latest_event=latest_event,
                    latest_event_type=latest_event.event_type,
                    latest_trade_status=latest_event.trade_status,
                    classification=classification,
                    message=message,
                    rest_order=rest_order,
                )
            )

        summary = ExecutionReconciliationSummary(
            window_event_count=len(recent_events),
            total_orders=len(items),
            consistent_open=sum(1 for item in items if item.classification == "consistent_open"),
            consistent_closed=sum(
                1 for item in items if item.classification == "consistent_closed"
            ),
            inconclusive=sum(1 for item in items if item.classification == "inconclusive"),
            mismatch=sum(1 for item in items if item.classification == "mismatch"),
        )
        record = ExecutionReconciliationRecord(
            reconciliation_id=reconciliation_id,
            created_at=created_at,
            summary=summary,
            items=items,
            errors=errors,
        )
        self._state_service.append_reconciliation(record)
        return ExecutionReconciliationResponse(
            reconciliation_id=reconciliation_id,
            created_at=created_at,
            summary=summary,
            items=items,
            errors=errors,
        )

    def _resolve_watch_condition_ids(self, market: str | None) -> list[str]:
        if market is not None and market.strip():
            return [market.strip()]

        open_orders = self._lifecycle_service.orders_open().items
        condition_ids = list(
            OrderedDict.fromkeys(
                item.market.strip()
                for item in open_orders
                if item.market is not None and item.market.strip()
            )
        )
        if not condition_ids:
            raise ExecutionNotFoundError(
                "No open-order condition ids were found. Pass --market <condition_id>."
            )
        return condition_ids

    def _safe_order_get(
        self,
        order_id: str,
        *,
        errors: list[StreamSectionError],
    ) -> NormalizedOrder | None:
        if not order_id:
            return None
        try:
            return self._lifecycle_service.order_get(order_id=order_id).order
        except Exception as exc:
            errors.append(
                StreamSectionError(
                    section="order_get",
                    code=_error_code_for(exc),
                    message=str(exc),
                )
            )
            return None


class ExecutionUserWebSocketClient:
    """Bounded authenticated websocket client for Polymarket user-channel events."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_EXECUTION_USER_STREAM_URL,
        auth_service: AuthService | None = None,
        state_service: ExecutionStateService | None = None,
        connect: Callable[..., Any] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        max_retries: int = 2,
    ) -> None:
        self._endpoint = endpoint
        self._auth_service = auth_service or AuthService()
        self._state_service = state_service or ExecutionStateService()
        self._connect = connect
        self._sleep = sleep or asyncio.sleep
        self._max_retries = max_retries

    async def watch_conditions(
        self,
        condition_ids: list[str],
        *,
        seconds: int,
        max_events: int | None = None,
        order_id: str | None = None,
    ) -> ExecutionBoundedRunResult:
        """Run one bounded authenticated user-channel session."""
        normalized_conditions = [item.strip() for item in condition_ids if item.strip()]
        if not normalized_conditions:
            raise StreamValidationError("At least one condition id is required.")

        settings = self._auth_service.require_valid_config()
        creds = self._auth_service.get_api_credentials(settings)
        subscribe_payload = json.dumps(
            {
                "type": "user",
                "auth": {
                    "apiKey": creds.api_key,
                    "secret": creds.api_secret,
                    "passphrase": creds.api_passphrase,
                },
                "markets": normalized_conditions,
            },
            separators=(",", ":"),
        )
        filtered_order_id = order_id.strip() if order_id is not None else None

        def normalize(payload: dict[str, Any]) -> list[NormalizedExecutionEvent]:
            return _filter_execution_events(
                normalize_user_message(payload),
                condition_ids=normalized_conditions,
                order_id=filtered_order_id,
            )

        raw_result = await cast(Any, run_bounded_websocket_session)(
            endpoint=self._endpoint,
            stream_kind="execution_user",
            source="polymarket_user_ws",
            subscribe_payload=subscribe_payload,
            normalize_message=normalize,
            wrap_event=_wrap_execution_event,
            persist_event=self._state_service.append_execution_event,
            seconds=seconds,
            max_events=max_events,
            section="execution_watch",
            connect=self._connect,
            sleep=self._sleep,
            max_retries=self._max_retries,
        )
        return ExecutionBoundedRunResult(
            session=raw_result.session,
            events=cast(list[CapturedExecutionEvent], raw_result.events),
            errors=raw_result.errors,
        )


def normalize_user_message(payload: dict[str, Any]) -> list[NormalizedExecutionEvent]:
    """Normalize one authenticated user-channel payload into execution events."""
    rows = list(_iter_execution_rows(payload))
    events: list[NormalizedExecutionEvent] = []
    for row in rows:
        event = _normalize_execution_row(row, payload)
        if event is not None:
            events.append(event)
    return events


def _iter_execution_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("events", "orders", "trades", "data"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return [payload]


def _normalize_execution_row(
    row: dict[str, Any],
    parent: dict[str, Any],
) -> NormalizedExecutionEvent | None:
    condition_id = _first_string(row, parent, "market", "condition_id", "conditionId")
    order_id = _first_string(row, parent, "order_id", "orderID", "id")
    asset_id = _first_string(row, parent, "asset_id", "assetId", "token_id", "tokenId")
    trade_status = _normalize_trade_status(
        _first_string(row, parent, "trade_status", "tradeStatus", "status", "state")
    )
    status = _normalize_status(
        _first_string(row, parent, "status", "state", "order_status", "orderStatus")
    )
    event_type = _normalize_event_type(
        _first_string(row, parent, "event_type", "eventType", "type"),
        trade_status=trade_status,
        status=status,
        has_order_fields=any([condition_id, order_id, asset_id]),
    )
    if event_type is None:
        return None

    return NormalizedExecutionEvent(
        condition_id=condition_id,
        order_id=order_id,
        asset_id=asset_id,
        event_type=event_type,
        trade_status=trade_status,
        side=_normalize_side(_first_string(row, parent, "side")),
        price=_stringified_value(_first_value(row, parent, "price")),
        size=_stringified_value(_first_value(row, parent, "size", "amount")),
        status=status,
        timestamp=_int_or_none(_first_value(row, parent, "timestamp", "createdAt", "created_at")),
    )


def _filter_execution_events(
    events: list[NormalizedExecutionEvent],
    *,
    condition_ids: list[str],
    order_id: str | None,
) -> list[NormalizedExecutionEvent]:
    condition_id_set = {item.lower() for item in condition_ids}
    filtered: list[NormalizedExecutionEvent] = []
    for event in events:
        if event.condition_id is not None and event.condition_id.lower() not in condition_id_set:
            continue
        if order_id is not None and event.order_id != order_id:
            continue
        filtered.append(event)
    return filtered


def _wrap_execution_event(
    event: NormalizedExecutionEvent,
    session_id: str,
    source: str,
    captured_at: str,
) -> CapturedExecutionEvent:
    return CapturedExecutionEvent(
        session_id=session_id,
        source=source,
        captured_at=captured_at,
        condition_id=event.condition_id,
        order_id=event.order_id,
        asset_id=event.asset_id,
        event_type=event.event_type,
        trade_status=event.trade_status,
        side=event.side,
        price=event.price,
        size=event.size,
        status=event.status,
        timestamp=event.timestamp,
    )


def _build_watch_summary(
    condition_ids: list[str],
    result: ExecutionBoundedRunResult,
) -> ExecutionWatchSummary:
    event_counts = OrderedDict((item, 0) for item in SUPPORTED_EVENT_TYPES)
    trade_status_counts = OrderedDict((item, 0) for item in SUPPORTED_TRADE_STATUSES)
    order_ids: set[str] = set()
    for event in result.events:
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
        if event.trade_status is not None:
            trade_status_counts[event.trade_status] = (
                trade_status_counts.get(event.trade_status, 0) + 1
            )
        if event.order_id:
            order_ids.add(event.order_id)
    return ExecutionWatchSummary(
        watched_condition_ids=condition_ids,
        event_counts=dict(event_counts),
        trade_status_counts=dict(trade_status_counts),
        distinct_order_count=len(order_ids),
        reconnect_count=result.session.reconnect_count,
    )


def _latest_terminal_event(
    events: list[CapturedExecutionEvent],
) -> CapturedExecutionEvent | None:
    for event in reversed(events):
        if event.event_type == "CANCELLATION":
            return event
        if event.trade_status in {"CONFIRMED", "FAILED"}:
            return event
    return None


def _classify_reconciliation(
    *,
    latest_event: CapturedExecutionEvent,
    rest_order: NormalizedOrder | None,
    open_order_ids: set[str],
) -> tuple[str, str]:
    is_open = _is_open_order(latest_event.order_id, rest_order, open_order_ids)
    if latest_event.trade_status in {"MATCHED", "MINED", "RETRYING", "FAILED"}:
        return (
            "inconclusive",
            "Latest trade status is intermediate or ambiguous without a clear contradiction.",
        )
    if latest_event.event_type in {"PLACEMENT", "UPDATE"} and is_open:
        return ("consistent_open", "Latest websocket event still matches an open order view.")
    if (
        latest_event.event_type == "CANCELLATION"
        or latest_event.trade_status == "CONFIRMED"
    ) and not is_open:
        return (
            "consistent_closed",
            "Latest websocket event matches a closed or absent REST order view.",
        )
    return ("mismatch", "Latest websocket event does not match the current REST order view.")


def _is_open_order(
    order_id: str | None,
    rest_order: NormalizedOrder | None,
    open_order_ids: set[str],
) -> bool:
    if order_id and order_id in open_order_ids:
        return True
    if rest_order is None:
        return False
    status = (rest_order.status or "").strip().upper()
    return status in {"OPEN", "PLACED", "LIVE", "PENDING"}


def _normalize_event_type(
    raw_value: str | None,
    *,
    trade_status: str | None,
    status: str | None,
    has_order_fields: bool,
) -> str | None:
    normalized = (raw_value or "").strip().upper()
    if normalized in SUPPORTED_EVENT_TYPES:
        return normalized
    if normalized in {"PLACED"}:
        return "PLACEMENT"
    if normalized in {"CANCELLED", "CANCELED"}:
        return "CANCELLATION"
    if status in {"CANCELLED", "CANCELED"}:
        return "CANCELLATION"
    if trade_status in SUPPORTED_TRADE_STATUSES:
        return "UPDATE"
    if has_order_fields:
        return "UPDATE"
    return None


def _normalize_trade_status(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if normalized in SUPPORTED_TRADE_STATUSES:
        return normalized
    return None


def _normalize_side(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if normalized in {"BUY", "SELL"}:
        return normalized
    return _string_or_none(value)


def _normalize_status(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if normalized:
        return normalized
    return None


def _first_string(
    primary: dict[str, Any],
    secondary: dict[str, Any],
    *keys: str,
) -> str | None:
    return _string_or_none(_first_value(primary, secondary, *keys))


def _first_value(
    primary: dict[str, Any],
    secondary: dict[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in primary and primary.get(key) is not None:
            return primary.get(key)
        if key in secondary and secondary.get(key) is not None:
            return secondary.get(key)
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _stringified_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                return None
            return int(parsed.astimezone(UTC).timestamp())
    return None


def _error_code_for(exc: Exception) -> str:
    if isinstance(exc, (AuthValidationError, ExecutionValidationError, StreamValidationError)):
        return "invalid_argument"
    if isinstance(exc, ExecutionNotFoundError):
        return "not_found"
    if isinstance(exc, ExecutionStateError):
        return "state_error"
    if isinstance(exc, (AuthClientError, StreamClientError)):
        return "request_failed"
    return "request_failed"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
