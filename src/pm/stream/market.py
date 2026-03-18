"""Public Polymarket market websocket normalization and client helpers."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from pm.market.models import NormalizedBookLevel
from pm.stream.models import (
    CapturedStreamEvent,
    MarketStreamResponse,
    MarketTokenStreamSummary,
    NormalizedMarketStreamEvent,
)
from pm.stream.runner import (
    BoundedRunResult,
    StreamValidationError,
    run_bounded_websocket_session,
)
from pm.stream.state import StreamEventStore

DEFAULT_MARKET_STREAM_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class MarketWebSocketClient:
    """Bounded read-only client for the public market websocket."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_MARKET_STREAM_URL,
        store: StreamEventStore | None = None,
        connect: Callable[..., Any] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._store = store or StreamEventStore()
        self._connect = connect

    async def stream_token(
        self,
        token_id: str,
        *,
        seconds: int,
        max_events: int | None = None,
    ) -> MarketStreamResponse:
        """Run a bounded single-token market stream session."""
        normalized_token_id = token_id.strip()
        if not normalized_token_id:
            raise StreamValidationError("Token ID is required.")

        result = await self.stream_tokens(
            [normalized_token_id],
            seconds=seconds,
            max_events=max_events,
        )
        summary = MarketTokenStreamSummary(
            token_id=normalized_token_id,
            event_count=len(
                [
                    event
                    for event in result.events
                    if event.market_event is not None
                    and event.market_event.token_id == normalized_token_id
                ]
            ),
            latest_best_bid=_latest_market_value(result.events, normalized_token_id, "best_bid"),
            latest_best_ask=_latest_market_value(result.events, normalized_token_id, "best_ask"),
            latest_midpoint=_latest_market_value(result.events, normalized_token_id, "midpoint"),
            latest_spread=_latest_market_value(result.events, normalized_token_id, "spread"),
            latest_last_trade_price=_latest_last_trade_price(result.events, normalized_token_id),
            latest_tick_size=_latest_tick_size(result.events, normalized_token_id),
            event_counts=_event_counts(result.events, normalized_token_id),
        )
        return MarketStreamResponse(
            session=result.session,
            summary=summary,
            events=result.events,
            errors=result.errors,
        )

    async def stream_tokens(
        self,
        token_ids: list[str],
        *,
        seconds: int,
        max_events: int | None = None,
    ) -> BoundedRunResult:
        """Run a bounded multi-token market stream session."""
        normalized_token_ids = [token_id.strip() for token_id in token_ids if token_id.strip()]
        if not normalized_token_ids:
            raise StreamValidationError("At least one token ID is required.")

        return await run_bounded_websocket_session(
            endpoint=self._endpoint,
            stream_kind="market",
            source="polymarket_market_ws",
            subscribe_payload=json.dumps(
                {
                    "assets_ids": normalized_token_ids,
                    "type": "market",
                    "custom_feature_enabled": True,
                },
                separators=(",", ":"),
            ),
            normalize_message=normalize_market_message,
            wrap_event=_wrap_market_event,
            persist_event=self._store.append_event,
            seconds=seconds,
            max_events=max_events,
            section="market_stream",
            connect=self._connect,
        )


def normalize_market_message(payload: dict[str, Any]) -> list[NormalizedMarketStreamEvent]:
    """Normalize a public market websocket payload into one or more events."""
    event_type = _string_or_none(payload.get("event_type")) or _string_or_none(payload.get("type"))
    if event_type is None:
        return []

    if event_type == "book":
        bids = _parse_book_levels(payload.get("bids"))
        asks = _parse_book_levels(payload.get("asks"))
        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None
        return [
            NormalizedMarketStreamEvent(
                event_type=event_type,
                token_id=_first_string(payload, "asset_id", "token_id"),
                market=_first_string(payload, "market", "market_id"),
                timestamp=_int_or_none(payload.get("timestamp")),
                best_bid=best_bid,
                best_ask=best_ask,
                midpoint=_derive_midpoint(best_bid, best_ask),
                spread=_derive_spread(best_bid, best_ask),
                bids=bids,
                asks=asks,
            )
        ]

    if event_type == "best_bid_ask":
        best_bid = _first_string(payload, "best_bid", "bid")
        best_ask = _first_string(payload, "best_ask", "ask")
        return [
            NormalizedMarketStreamEvent(
                event_type=event_type,
                token_id=_first_string(payload, "asset_id", "token_id"),
                market=_first_string(payload, "market", "market_id"),
                timestamp=_int_or_none(payload.get("timestamp")),
                best_bid=best_bid,
                best_ask=best_ask,
                midpoint=_derive_midpoint(best_bid, best_ask),
                spread=_derive_spread(best_bid, best_ask),
            )
        ]

    if event_type == "price_change":
        changes = payload.get("price_changes")
        if not isinstance(changes, list):
            changes = [payload]
        items: list[NormalizedMarketStreamEvent] = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            best_bid = _first_string(change, "best_bid")
            best_ask = _first_string(change, "best_ask")
            items.append(
                NormalizedMarketStreamEvent(
                    event_type=event_type,
                    token_id=_first_string(change, "asset_id", "token_id")
                    or _first_string(payload, "asset_id", "token_id"),
                    market=_first_string(change, "market", "market_id")
                    or _first_string(payload, "market", "market_id"),
                    timestamp=_int_or_none(change.get("timestamp"))
                    or _int_or_none(payload.get("timestamp")),
                    hash=_first_string(change, "hash", "transaction_hash"),
                    price=_first_string(change, "price"),
                    size=_first_string(change, "size"),
                    side=_first_string(change, "side"),
                    best_bid=best_bid,
                    best_ask=best_ask,
                    midpoint=_derive_midpoint(best_bid, best_ask),
                    spread=_derive_spread(best_bid, best_ask),
                )
            )
        return items

    if event_type == "last_trade_price":
        return [
            NormalizedMarketStreamEvent(
                event_type=event_type,
                token_id=_first_string(payload, "asset_id", "token_id"),
                market=_first_string(payload, "market", "market_id"),
                timestamp=_int_or_none(payload.get("timestamp")),
                hash=_first_string(payload, "hash", "transaction_hash"),
                price=_first_string(payload, "price", "last_trade_price"),
                size=_first_string(payload, "size"),
                side=_first_string(payload, "side"),
            )
        ]

    if event_type == "tick_size_change":
        return [
            NormalizedMarketStreamEvent(
                event_type=event_type,
                token_id=_first_string(payload, "asset_id", "token_id"),
                market=_first_string(payload, "market", "market_id"),
                timestamp=_int_or_none(payload.get("timestamp")),
                old_tick_size=_first_string(payload, "old_tick_size"),
                new_tick_size=_first_string(payload, "new_tick_size", "tick_size"),
            )
        ]

    return []


def _wrap_market_event(
    event: NormalizedMarketStreamEvent,
    session_id: str,
    source: str,
    captured_at: str,
) -> CapturedStreamEvent:
    return CapturedStreamEvent(
        session_id=session_id,
        stream_kind="market",
        source=source,
        captured_at=captured_at,
        event_type=event.event_type,
        market_event=event,
    )


def _latest_market_value(
    events: list[CapturedStreamEvent],
    token_id: str,
    field_name: str,
) -> str | None:
    for event in reversed(events):
        if event.market_event is None or event.market_event.token_id != token_id:
            continue
        value = getattr(event.market_event, field_name)
        if value is not None:
            return value
    return None


def _latest_last_trade_price(events: list[CapturedStreamEvent], token_id: str) -> str | None:
    for event in reversed(events):
        if event.market_event is None or event.market_event.token_id != token_id:
            continue
        if (
            event.market_event.event_type == "last_trade_price"
            and event.market_event.price is not None
        ):
            return event.market_event.price
    return None


def _latest_tick_size(events: list[CapturedStreamEvent], token_id: str) -> str | None:
    for event in reversed(events):
        if event.market_event is None or event.market_event.token_id != token_id:
            continue
        if event.market_event.new_tick_size is not None:
            return event.market_event.new_tick_size
    return None


def _event_counts(events: list[CapturedStreamEvent], token_id: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        if event.market_event is None or event.market_event.token_id != token_id:
            continue
        counts[event.market_event.event_type] += 1
    return dict(sorted(counts.items()))


def _parse_book_levels(value: Any) -> list[NormalizedBookLevel]:
    if not isinstance(value, list):
        return []
    items: list[NormalizedBookLevel] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        price = _first_string(item, "price")
        size = _first_string(item, "size")
        if price is None or size is None:
            continue
        items.append(NormalizedBookLevel(price=price, size=size))
    return items


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _string_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _derive_midpoint(best_bid: str | None, best_ask: str | None) -> str | None:
    if best_bid is None or best_ask is None:
        return None
    try:
        midpoint = (float(best_bid) + float(best_ask)) / 2
    except ValueError:
        return None
    return _format_decimal(midpoint)


def _derive_spread(best_bid: str | None, best_ask: str | None) -> str | None:
    if best_bid is None or best_ask is None:
        return None
    try:
        spread = float(best_ask) - float(best_bid)
    except ValueError:
        return None
    return _format_decimal(spread)


def _format_decimal(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"
