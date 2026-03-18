"""CLI tests for the read-only public stream surface."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.stream import StreamValidationError
from pm.stream.models import (
    BoundedStreamSession,
    CapturedStreamEvent,
    CryptoStreamResponse,
    CryptoStreamSummary,
    MarketStreamResponse,
    MarketTokenStreamSummary,
    MarketWatchStreamResponse,
    MarketWatchStreamSummary,
    MarketWatchTokenSummary,
    RecurringStreamResponse,
    RecurringStreamSummary,
)

runner = CliRunner()


def test_stream_help_lists_commands() -> None:
    result = runner.invoke(app, ["stream", "--help"])

    assert result.exit_code == 0
    assert "market" in result.stdout
    assert "crypto" in result.stdout
    assert "watch" in result.stdout
    assert "recurring" in result.stdout


def test_stream_market_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.stream.StreamService.stream_market",
        lambda self, token_id, seconds, max_events=None: MarketStreamResponse(
            session=_session(stream_kind="market", source="polymarket_market_ws"),
            summary=MarketTokenStreamSummary(
                token_id=token_id,
                event_count=1,
                latest_best_bid="0.44",
                latest_best_ask="0.46",
                latest_midpoint="0.45",
                latest_spread="0.02",
                event_counts={"book": 1},
            ),
            events=[_event(stream_kind="market", source="polymarket_market_ws", event_type="book")],
        ),
    )

    result = runner.invoke(
        app,
        ["stream", "market", "--token-id", "100", "--seconds", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["token_id"] == "100"
    assert payload["summary"]["latest_midpoint"] == "0.45"


def test_stream_crypto_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.stream.StreamService.stream_crypto",
        lambda self, symbol, source, seconds, max_events=None: CryptoStreamResponse(
            session=_session(stream_kind="crypto", source=source),
            summary=CryptoStreamSummary(
                symbol=symbol.upper(),
                source=source,
                event_count=1,
                latest_value="67321.1",
                first_timestamp=1710000000,
                last_timestamp=1710000000,
            ),
            events=[_event(stream_kind="crypto", source=source, event_type="crypto_price")],
        ),
    )

    result = runner.invoke(
        app,
        [
            "--output",
            "json",
            "stream",
            "crypto",
            "--symbol",
            "btc",
            "--source",
            "binance",
            "--seconds",
            "2",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["symbol"] == "BTC"
    assert payload["summary"]["source"] == "binance"


def test_stream_watch_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.stream.StreamService.stream_watch",
        lambda self, slug, seconds, max_events=None: MarketWatchStreamResponse(
            session=_session(stream_kind="market", source="polymarket_market_ws"),
            summary=MarketWatchStreamSummary(
                market_slug=slug,
                condition_id="0x" + ("a" * 64),
                token_ids=["100", "101"],
                outcomes=["Yes", "No"],
                active=True,
                closed=False,
                tokens=[
                    MarketWatchTokenSummary(
                        token_id="100",
                        outcome="Yes",
                        event_count=1,
                        latest_best_bid="0.44",
                        latest_best_ask="0.46",
                        latest_midpoint="0.45",
                        latest_spread="0.02",
                    )
                ],
                aggregate_event_count=1,
            ),
            events=[
                _event(
                    stream_kind="market",
                    source="polymarket_market_ws",
                    event_type="best_bid_ask",
                )
            ],
        ),
    )

    result = runner.invoke(
        app,
        ["stream", "watch", "--slug", "btc-market", "--seconds", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["market_slug"] == "btc-market"
    assert payload["summary"]["tokens"][0]["token_id"] == "100"


def test_stream_recurring_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.stream.StreamService.stream_recurring",
        lambda self, query, interval, seconds, max_events=None: RecurringStreamResponse(
            session=_session(stream_kind="recurring", source="market+binance"),
            summary=RecurringStreamSummary(
                recurring_market={
                    "rank": 1,
                    "match_score": 201,
                    "matched_interval": interval,
                    "recency_source": "endDate",
                    "market_slug": "btc-15m",
                    "event_slug": "bitcoin-event",
                    "question": "Bitcoin Up or Down - 15 min",
                    "event_title": "Bitcoin 15 minute markets",
                    "active": True,
                    "closed": False,
                    "enable_order_book": True,
                    "condition_id": "0x" + ("a" * 64),
                    "token_ids": ["100", "101"],
                    "outcomes": ["Yes", "No"],
                    "min_tick": 0.01,
                    "min_order_size": 5,
                },
                market=MarketWatchStreamSummary(
                    market_slug="btc-15m",
                    condition_id="0x" + ("a" * 64),
                    token_ids=["100", "101"],
                    outcomes=["Yes", "No"],
                    active=True,
                    closed=False,
                    aggregate_event_count=2,
                ),
                crypto=CryptoStreamSummary(
                    symbol="BTC",
                    source="binance",
                    event_count=2,
                    latest_value="67000",
                ),
                merged_event_count=4,
            ),
            events=[
                _event(
                    stream_kind="market",
                    source="polymarket_market_ws",
                    event_type="price_change",
                ),
                _event(stream_kind="crypto", source="binance", event_type="crypto_price"),
            ],
        ),
    )

    result = runner.invoke(
        app,
        ["stream", "recurring", "--query", "btc", "--interval", "15m", "--seconds", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["recurring_market"]["market_slug"] == "btc-15m"
    assert payload["summary"]["crypto"]["symbol"] == "BTC"


def test_stream_invalid_argument_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "pm.cli.stream.StreamService.stream_crypto",
        lambda self, symbol, source, seconds, max_events=None: (_ for _ in ()).throw(
            StreamValidationError("Source must be one of: binance, chainlink.")
        ),
    )

    result = runner.invoke(
        app,
        ["stream", "crypto", "--symbol", "btc", "--source", "bogus", "--seconds", "2", "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_argument",
            "identifier": "btc:bogus",
            "message": "Source must be one of: binance, chainlink.",
            "resource": "stream",
        },
        "ok": False,
    }


def _session(*, stream_kind: str, source: str) -> BoundedStreamSession:
    return BoundedStreamSession(
        session_id="session-1",
        stream_kind=stream_kind,
        source=source,
        started_at="2026-03-18T00:00:00Z",
        ended_at="2026-03-18T00:00:02Z",
        duration_seconds=2,
        requested_seconds=2,
        max_events=10,
        captured_event_count=1,
        reconnect_count=0,
    )


def _event(*, stream_kind: str, source: str, event_type: str) -> CapturedStreamEvent:
    return CapturedStreamEvent(
        session_id="session-1",
        stream_kind=stream_kind,
        source=source,
        captured_at="2026-03-18T00:00:01Z",
        event_type=event_type,
    )
