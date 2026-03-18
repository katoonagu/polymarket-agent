"""Unit tests for public stream normalization and bounded session behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pm.stream.market import normalize_market_message
from pm.stream.models import CapturedStreamEvent
from pm.stream.rtds import normalize_crypto_message
from pm.stream.runner import StreamClientError, run_bounded_websocket_session
from pm.stream.state import StreamEventStore


class FakeWebSocket:
    """Small async websocket fake for bounded-session tests."""

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
    """Async context manager wrapper for a fake websocket."""

    def __init__(self, websocket: FakeWebSocket) -> None:
        self._websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self._websocket

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_normalize_market_book_event() -> None:
    payload = {
        "event_type": "book",
        "asset_id": "100",
        "timestamp": 1710000000,
        "bids": [{"price": "0.44", "size": "10"}],
        "asks": [{"price": "0.46", "size": "12"}],
    }

    events = normalize_market_message(payload)

    assert len(events) == 1
    assert events[0].event_type == "book"
    assert events[0].token_id == "100"
    assert events[0].best_bid == "0.44"
    assert events[0].best_ask == "0.46"
    assert events[0].midpoint == "0.45"
    assert events[0].spread == "0.02"


def test_normalize_market_price_change_flattens_rows() -> None:
    payload = {
        "event_type": "price_change",
        "price_changes": [
            {
                "asset_id": "100",
                "price": "0.45",
                "size": "10",
                "side": "BUY",
                "hash": "0xabc",
                "timestamp": 1710000000,
            },
            {
                "asset_id": "101",
                "price": "0.55",
                "size": "11",
                "side": "SELL",
                "hash": "0xdef",
                "timestamp": 1710000001,
            },
        ],
    }

    events = normalize_market_message(payload)

    assert [item.token_id for item in events] == ["100", "101"]
    assert [item.price for item in events] == ["0.45", "0.55"]


def test_normalize_market_tick_size_change() -> None:
    payload = {
        "event_type": "tick_size_change",
        "asset_id": "100",
        "old_tick_size": "0.01",
        "new_tick_size": "0.005",
    }

    events = normalize_market_message(payload)

    assert len(events) == 1
    assert events[0].old_tick_size == "0.01"
    assert events[0].new_tick_size == "0.005"


def test_normalize_crypto_binance_payload() -> None:
    payload = {
        "data": [{"symbol": "btcusdt", "price": "67321.1", "timestamp": 1710000000}],
    }

    events = normalize_crypto_message(payload, source="binance")

    assert len(events) == 1
    assert events[0].symbol == "BTC"
    assert events[0].source == "binance"
    assert events[0].value == "67321.1"


def test_normalize_crypto_chainlink_payload() -> None:
    payload = {
        "data": [{"symbol": "eth/usd", "value": "3321.1", "ts": 1710000000}],
    }

    events = normalize_crypto_message(payload, source="chainlink")

    assert len(events) == 1
    assert events[0].symbol == "ETH"
    assert events[0].source == "chainlink"
    assert events[0].value == "3321.1"


def test_bounded_runner_stops_by_max_events_and_persists(tmp_path: Path) -> None:
    store = StreamEventStore(path=tmp_path / "stream-events.jsonl")
    websocket = FakeWebSocket(
        [
            json.dumps({"kind": "event", "price": "1"}),
            json.dumps({"kind": "event", "price": "2"}),
            json.dumps({"kind": "event", "price": "3"}),
        ]
    )

    async def run() -> None:
        result = await run_bounded_websocket_session(
            endpoint="wss://example.test",
            stream_kind="crypto",
            source="binance",
            subscribe_payload='{"subscribe":true}',
            normalize_message=lambda payload: [payload] if payload.get("kind") == "event" else [],
            wrap_event=lambda payload, session_id, source, captured_at: CapturedStreamEvent(
                session_id=session_id,
                stream_kind="crypto",
                source=source,
                captured_at=captured_at,
                event_type="crypto_price",
            ),
            persist_event=store.append_event,
            seconds=5,
            max_events=2,
            section="crypto_stream",
            connect=lambda *args, **kwargs: FakeConnection(websocket),
        )
        assert result.session.captured_event_count == 2
        assert len(result.events) == 2

    asyncio.run(run())

    persisted = store.list_events()
    assert len(persisted) == 2
    assert persisted[0].stream_kind == "crypto"


def test_bounded_runner_returns_partial_error_after_reconnect_exhaustion(tmp_path: Path) -> None:
    store = StreamEventStore(path=tmp_path / "stream-events.jsonl")
    connections = [
        FakeConnection(
            FakeWebSocket([json.dumps({"kind": "event"}), RuntimeError("socket dropped")])
        ),
    ]

    def connect(*args: object, **kwargs: object) -> FakeConnection:
        if connections:
            return connections.pop(0)
        raise RuntimeError("socket dropped")

    async def run() -> None:
        result = await run_bounded_websocket_session(
            endpoint="wss://example.test",
            stream_kind="market",
            source="polymarket_market_ws",
            subscribe_payload='{"subscribe":true}',
            normalize_message=lambda payload: [payload] if payload.get("kind") == "event" else [],
            wrap_event=lambda payload, session_id, source, captured_at: CapturedStreamEvent(
                session_id=session_id,
                stream_kind="market",
                source=source,
                captured_at=captured_at,
                event_type="price_change",
            ),
            persist_event=store.append_event,
            seconds=1,
            max_events=5,
            section="market_stream",
            connect=connect,
            sleep=lambda delay: asyncio.sleep(0),
        )
        assert result.session.captured_event_count == 1
        assert result.session.reconnect_count == 2
        assert result.errors
        assert result.errors[0].section == "market_stream"

    asyncio.run(run())


def test_bounded_runner_raises_when_no_connection_established() -> None:
    async def run() -> None:
        with pytest.raises(StreamClientError):
            await run_bounded_websocket_session(
                endpoint="wss://example.test",
                stream_kind="market",
                source="polymarket_market_ws",
                subscribe_payload='{"subscribe":true}',
                normalize_message=lambda payload: [payload],
                wrap_event=lambda payload, session_id, source, captured_at: CapturedStreamEvent(
                    session_id=session_id,
                    stream_kind="market",
                    source=source,
                    captured_at=captured_at,
                    event_type="book",
                ),
                persist_event=lambda event: None,
                seconds=1,
                max_events=1,
                section="market_stream",
                connect=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
                sleep=lambda delay: asyncio.sleep(0),
            )

    asyncio.run(run())
