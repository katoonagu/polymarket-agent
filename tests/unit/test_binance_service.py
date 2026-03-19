"""Unit tests for the public Binance liquidity package."""

from __future__ import annotations

import httpx
import respx

from pm.binance import (
    BinanceClient,
    BinanceClientError,
    BinanceService,
    BinanceValidationError,
)

BINANCE_URL = "https://api.binance.com/api/v3"


@respx.mock
def test_binance_client_normalizes_public_endpoints() -> None:
    book_ticker = respx.get(f"{BINANCE_URL}/ticker/bookTicker").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "bidPrice": "100",
                "bidQty": "5",
                "askPrice": "100.10",
                "askQty": "6",
            },
        )
    )
    depth = respx.get(f"{BINANCE_URL}/depth").mock(
        return_value=httpx.Response(
            200,
            json={
                "lastUpdateId": 1,
                "bids": [["100", "10"]],
                "asks": [["100.10", "12"]],
            },
        )
    )
    klines = respx.get(f"{BINANCE_URL}/klines").mock(
        return_value=httpx.Response(
            200,
            json=[
                [1, "100", "101", "99", "101", "10", 2, "1000", 10],
                [2, "101", "102", "100", "102", "10", 3, "1000", 10],
                [3, "102", "103", "101", "103", "10", 4, "1000", 10],
                [4, "103", "104", "102", "104", "10", 5, "1000", 10],
            ],
        )
    )

    with BinanceClient() as client:
        assert client.get_book_ticker(" btcusdt ")["askPrice"] == "100.10"
        assert client.get_depth("BTCUSDT", limit=20)["lastUpdateId"] == 1
        assert len(client.get_klines("BTCUSDT", interval="1m", limit=4)) == 4

    assert book_ticker.called
    assert depth.called
    assert klines.called


@respx.mock
def test_binance_service_builds_liquidity_snapshot() -> None:
    respx.get(f"{BINANCE_URL}/ticker/bookTicker").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "bidPrice": "100",
                "bidQty": "5",
                "askPrice": "100.10",
                "askQty": "6",
            },
        )
    )
    respx.get(f"{BINANCE_URL}/depth").mock(
        return_value=httpx.Response(
            200,
            json={
                "lastUpdateId": 1,
                "bids": [["100", "10"], ["99.99", "8"]],
                "asks": [["100.10", "12"], ["100.11", "9"]],
            },
        )
    )
    respx.get(f"{BINANCE_URL}/klines").mock(
        return_value=httpx.Response(
            200,
            json=[
                [1, "100", "101", "99", "101", "10", 2, "1000", 10],
                [2, "101", "102", "100", "102", "10", 3, "1000", 10],
                [3, "102", "103", "101", "103", "10", 4, "1000", 10],
                [4, "103", "104", "102", "104", "10", 5, "1000", 10],
            ],
        )
    )

    snapshot = BinanceService().sample_liquidity("BTCUSDT")

    assert snapshot.book_ticker.midpoint == "100.05"
    assert snapshot.depth.best_bid == "100"
    assert snapshot.realized_vol_1m_bps is not None
    assert snapshot.realized_vol_3m_bps is not None
    assert snapshot.near_touch_bid_depth == "10"
    assert snapshot.near_touch_ask_depth == "12"


def test_binance_client_validation_errors() -> None:
    with BinanceClient() as client:
        try:
            client.get_depth("", limit=20)
        except BinanceValidationError as exc:
            assert "Symbol is required." in str(exc)
        else:
            raise AssertionError("Expected BinanceValidationError for blank symbol.")


@respx.mock
def test_binance_service_raises_when_book_ticker_missing() -> None:
    respx.get(f"{BINANCE_URL}/ticker/bookTicker").mock(
        return_value=httpx.Response(200, json={"symbol": "BTCUSDT"})
    )
    respx.get(f"{BINANCE_URL}/depth").mock(
        return_value=httpx.Response(200, json={"lastUpdateId": 1, "bids": [], "asks": []})
    )
    respx.get(f"{BINANCE_URL}/klines").mock(return_value=httpx.Response(200, json=[]))

    try:
        BinanceService().sample_liquidity("BTCUSDT")
    except BinanceClientError as exc:
        assert "bookTicker" in str(exc)
    else:
        raise AssertionError("Expected BinanceClientError for incomplete bookTicker payload.")
