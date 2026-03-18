<<<<<<< HEAD
"""Unit tests for the public read-only CLOB client."""

from __future__ import annotations

import pytest
import respx
from httpx import Response
=======
"""Unit tests for the public CLOB client."""

from __future__ import annotations

import httpx
import respx
>>>>>>> feat/02a-python-scaffold

from pm.market import (
    ClobClient,
    ClobNotFoundError,
    NormalizedBook,
<<<<<<< HEAD
=======
    NormalizedBookLevel,
>>>>>>> feat/02a-python-scaffold
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

<<<<<<< HEAD
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
=======
BASE_URL = "https://clob.polymarket.com"


@respx.mock
def test_get_book_calls_public_endpoint_and_normalizes_levels() -> None:
    route = respx.get(f"{BASE_URL}/book").mock(
        return_value=httpx.Response(
            200,
            json={
                "asset_id": "100",
                "tick_size": "0.01",
                "min_order_size": "5",
                "bids": [{"price": "0.45", "size": "10"}],
                "asks": [{"price": "0.47", "size": "12"}],
            },
        )
    )

    with ClobClient() as client:
        book = client.get_book("100")

    assert route.called
    assert route.calls[0].request.url.params["token_id"] == "100"
    assert book == NormalizedBook(
        token_id="100",
        bids=[NormalizedBookLevel(price="0.45", size="10")],
        asks=[NormalizedBookLevel(price="0.47", size="12")],
        tick_size="0.01",
>>>>>>> feat/02a-python-scaffold
        min_order_size="5",
    )


@respx.mock
<<<<<<< HEAD
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
=======
def test_get_prices_posts_buy_and_sell_and_normalizes_response() -> None:
    route = respx.post(f"{BASE_URL}/prices").mock(
        return_value=httpx.Response(
            200,
            json={"100": {"BUY": "0.45", "SELL": "0.47"}},
        )
    )

    with ClobClient() as client:
        quote = client.get_prices("100")

    assert route.called
    assert route.calls[0].request.content == (
        b'[{"token_id":"100","side":"BUY"},{"token_id":"100","side":"SELL"}]'
    )
    assert quote == NormalizedPriceQuote(
        token_id="100",
        buy_price="0.45",
        sell_price="0.47",
>>>>>>> feat/02a-python-scaffold
    )


@respx.mock
<<<<<<< HEAD
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
=======
def test_get_midpoint_accepts_mid_and_mid_price() -> None:
    mid_route = respx.get(f"{BASE_URL}/midpoint").mock(
        return_value=httpx.Response(200, json={"mid": "0.46"})
    )

    with ClobClient() as client:
        midpoint = client.get_midpoint("100")

    assert mid_route.called
    assert midpoint == NormalizedMidpointQuote(token_id="100", midpoint="0.46")

    respx.routes.clear()
    mid_price_route = respx.get(f"{BASE_URL}/midpoint").mock(
        return_value=httpx.Response(200, json={"mid_price": "0.48"})
    )

    with ClobClient() as client:
        midpoint = client.get_midpoint("100")

    assert mid_price_route.called
    assert midpoint == NormalizedMidpointQuote(token_id="100", midpoint="0.48")


@respx.mock
def test_get_spread_normalizes_response() -> None:
    route = respx.get(f"{BASE_URL}/spread").mock(
        return_value=httpx.Response(200, json={"spread": "0.02"})
    )

    with ClobClient() as client:
        spread = client.get_spread("100")

    assert route.called
    assert route.calls[0].request.url.params["token_id"] == "100"
    assert spread == NormalizedSpreadQuote(token_id="100", spread="0.02")


@respx.mock
def test_get_book_maps_404_to_not_found() -> None:
    respx.get(f"{BASE_URL}/book").mock(return_value=httpx.Response(404))

    with ClobClient() as client:
        try:
            client.get_book("100")
        except ClobNotFoundError as exc:
            assert str(exc) == "token '100' was not found."
        else:
            raise AssertionError("ClobNotFoundError was not raised")


@respx.mock
def test_get_prices_empty_response_maps_to_not_found() -> None:
    respx.post(f"{BASE_URL}/prices").mock(return_value=httpx.Response(200, json={}))

    with ClobClient() as client:
        try:
            client.get_prices("100")
        except ClobNotFoundError as exc:
            assert str(exc) == "token '100' was not found."
        else:
            raise AssertionError("ClobNotFoundError was not raised")
>>>>>>> feat/02a-python-scaffold
