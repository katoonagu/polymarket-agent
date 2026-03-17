"""Unit tests for the public CLOB client."""

from __future__ import annotations

import httpx
import respx

from pm.market import (
    ClobClient,
    ClobNotFoundError,
    NormalizedBook,
    NormalizedBookLevel,
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

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
        min_order_size="5",
    )


@respx.mock
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
    )


@respx.mock
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
