"""Unit tests for the public read-only CLOB client."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from pm.market import (
    ClobClient,
    ClobNotFoundError,
    NormalizedBook,
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

DEFAULT_CLOB_URL = "https://clob.polymarket.com"
BOOK_PAYLOAD = {
    "asset_id": "token-1",
    "bids": [{"price": "0.10", "size": "5"}, {"price": "0.09", "size": "3"}],
    "asks": [{"price": "0.20", "size": "4"}],
    "tick_size": "0.001",
    "min_order_size": "5",
}
PRICES_PAYLOAD = {"token-1": {"BUY": "0.214", "SELL": "0.234"}}
MIDPOINT_PAYLOAD = {"mid": "0.224"}
SPREAD_PAYLOAD = {"spread": "0.020"}


@respx.mock
def test_get_book_uses_expected_query_params() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(200, json=BOOK_PAYLOAD),
    )

    with ClobClient() as client:
        result = client.get_book("token-1")

    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "token-1"}
    assert result == NormalizedBook(
        token_id="token-1",
        bids=[{"price": "0.10", "size": "5"}, {"price": "0.09", "size": "3"}],
        asks=[{"price": "0.20", "size": "4"}],
        tick_size="0.001",
        min_order_size="5",
    )


@respx.mock
def test_get_prices_posts_buy_and_sell_requests() -> None:
    route = respx.post(f"{DEFAULT_CLOB_URL}/prices").mock(
        return_value=Response(200, json=PRICES_PAYLOAD),
    )

    with ClobClient() as client:
        result = client.get_prices("token-1")

    assert route.called
    assert route.calls.last.request.content == (
        b'[{"token_id":"token-1","side":"BUY"},{"token_id":"token-1","side":"SELL"}]'
    )
    assert result == NormalizedPriceQuote(
        token_id="token-1",
        buy_price="0.214",
        sell_price="0.234",
    )


@respx.mock
def test_get_midpoint_uses_expected_query_params() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/midpoint").mock(
        return_value=Response(200, json=MIDPOINT_PAYLOAD),
    )

    with ClobClient() as client:
        result = client.get_midpoint("token-1")

    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "token-1"}
    assert result == NormalizedMidpointQuote(token_id="token-1", midpoint="0.224")


@respx.mock
def test_get_spread_uses_expected_query_params() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/spread").mock(
        return_value=Response(200, json=SPREAD_PAYLOAD),
    )

    with ClobClient() as client:
        result = client.get_spread("token-1")

    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "token-1"}
    assert result == NormalizedSpreadQuote(token_id="token-1", spread="0.020")


@respx.mock
def test_book_404_maps_to_not_found() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(
            404,
            json={"error": "No orderbook exists for the requested token id"},
        ),
    )

    with ClobClient() as client:
        with pytest.raises(ClobNotFoundError):
            client.get_book("missing")


@respx.mock
def test_empty_prices_map_to_not_found() -> None:
    respx.post(f"{DEFAULT_CLOB_URL}/prices").mock(return_value=Response(200, json={}))

    with ClobClient() as client:
        with pytest.raises(ClobNotFoundError):
            client.get_prices("missing")


@respx.mock
def test_midpoint_404_maps_to_not_found() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/midpoint").mock(
        return_value=Response(404, json={"error": "midpoint not found"}),
    )

    with ClobClient() as client:
        with pytest.raises(ClobNotFoundError):
            client.get_midpoint("missing")


@respx.mock
def test_spread_404_maps_to_not_found() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/spread").mock(
        return_value=Response(404, json={"error": "spread not found"}),
    )

    with ClobClient() as client:
        with pytest.raises(ClobNotFoundError):
            client.get_spread("missing")
