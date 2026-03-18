"""Public RTDS crypto price stream normalization and client helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pm.stream.models import (
    CapturedStreamEvent,
    CryptoStreamResponse,
    CryptoStreamSummary,
    NormalizedCryptoPriceEvent,
)
from pm.stream.runner import StreamValidationError, run_bounded_websocket_session
from pm.stream.state import StreamEventStore

DEFAULT_RTDS_URL = "wss://ws-live-data.polymarket.com"
SUPPORTED_RTDS_SOURCES = {"binance", "chainlink"}


class RTDSClient:
    """Bounded read-only RTDS client for crypto prices."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_RTDS_URL,
        store: StreamEventStore | None = None,
        connect: Callable[..., Any] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._store = store or StreamEventStore()
        self._connect = connect

    async def stream_symbol(
        self,
        symbol: str,
        *,
        source: str,
        seconds: int,
        max_events: int | None = None,
    ) -> CryptoStreamResponse:
        """Run a bounded RTDS crypto price session."""
        normalized_source = normalize_rtds_source(source)
        canonical_symbol = normalize_requested_symbol(symbol)
        topic, event_source, filter_value = _subscription_parts(canonical_symbol, normalized_source)

        result = await run_bounded_websocket_session(
            endpoint=self._endpoint,
            stream_kind="crypto",
            source=event_source,
            subscribe_payload=json.dumps(
                {
                    "action": "subscribe",
                    "subscriptions": [
                        {
                            "topic": topic,
                            "type": "update",
                            "filters": filter_value,
                        }
                    ],
                },
                separators=(",", ":"),
            ),
            normalize_message=lambda payload: normalize_crypto_message(
                payload,
                source=normalized_source,
            ),
            wrap_event=_wrap_crypto_event,
            persist_event=self._store.append_event,
            seconds=seconds,
            max_events=max_events,
            section="crypto_stream",
            connect=self._connect,
        )

        summary = CryptoStreamSummary(
            symbol=canonical_symbol,
            source=normalized_source,
            event_count=len(result.events),
            latest_value=_latest_value(result.events),
            first_timestamp=_first_timestamp(result.events),
            last_timestamp=_last_timestamp(result.events),
        )
        return CryptoStreamResponse(
            session=result.session,
            summary=summary,
            events=result.events,
            errors=result.errors,
        )


def normalize_rtds_source(source: str) -> str:
    """Validate and normalize the public RTDS source name."""
    normalized = source.strip().lower()
    if normalized not in SUPPORTED_RTDS_SOURCES:
        raise StreamValidationError("Source must be one of: binance, chainlink.")
    return normalized


def normalize_requested_symbol(symbol: str) -> str:
    """Normalize operator-friendly crypto symbol input to a canonical base asset."""
    normalized = symbol.strip().upper().replace("-", "").replace("_", "").replace("/", "")
    if not normalized:
        raise StreamValidationError("Symbol is required.")
    for suffix in ("USDT", "USD"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def normalize_crypto_message(
    payload: dict[str, Any],
    *,
    source: str,
) -> list[NormalizedCryptoPriceEvent]:
    """Normalize an RTDS payload into one or more crypto price events."""
    items = payload.get("data")
    if isinstance(items, list):
        data_items = items
    else:
        data_items = [payload]

    events: list[NormalizedCryptoPriceEvent] = []
    for item in data_items:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_incoming_symbol(_first_string(item, "symbol", "pair", "market"))
        value = _first_string(item, "value", "price")
        if symbol is None or value is None:
            continue
        events.append(
            NormalizedCryptoPriceEvent(
                symbol=symbol,
                source=source,
                timestamp=_int_or_none(item.get("timestamp"))
                or _int_or_none(item.get("ts")),
                value=value,
            )
        )
    return events


def _subscription_parts(symbol: str, source: str) -> tuple[str, str, str]:
    if source == "binance":
        return ("crypto_prices", "binance", f"{symbol.lower()}usdt")
    return (
        "crypto_prices_chainlink",
        "chainlink",
        json.dumps({"symbol": f"{symbol.lower()}/usd"}, separators=(",", ":")),
    )


def _wrap_crypto_event(
    event: NormalizedCryptoPriceEvent,
    session_id: str,
    source: str,
    captured_at: str,
) -> CapturedStreamEvent:
    return CapturedStreamEvent(
        session_id=session_id,
        stream_kind="crypto",
        source=source,
        captured_at=captured_at,
        event_type=event.event_type,
        crypto_event=event,
    )


def _latest_value(events: list[CapturedStreamEvent]) -> str | None:
    for event in reversed(events):
        if event.crypto_event is not None:
            return event.crypto_event.value
    return None


def _first_timestamp(events: list[CapturedStreamEvent]) -> int | None:
    for event in events:
        if event.crypto_event is not None:
            return event.crypto_event.timestamp
    return None


def _last_timestamp(events: list[CapturedStreamEvent]) -> int | None:
    for event in reversed(events):
        if event.crypto_event is not None:
            return event.crypto_event.timestamp
    return None


def _normalize_incoming_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_requested_symbol(value)


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
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
