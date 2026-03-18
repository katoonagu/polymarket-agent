"""Unit tests for the public CLOB client."""

from __future__ import annotations

import httpx
import respx

from pm.market import ClobClient, ClobNotFoundError

CLOB_URL = "https://clob.polymarket.com"


@respx.mock
def test_get_book_uses_token_query_param() -> None:
    route = respx.get(f"{CLOB_URL}/book").mock(
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

    with ClobClient(base_url=CLOB_URL) as client:
        book = client.get_book("100")

    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "100"}
    assert book.token_id == "100"
    assert book.tick_size == "0.01"
    assert book.bids[0].price == "0.45"


@respx.mock
def test_get_prices_posts_buy_and_sell_for_same_token() -> None:
    route = respx.post(f"{CLOB_URL}/prices").mock(
        return_value=httpx.Response(200, json={"100": {"BUY": "0.45", "SELL": "0.47"}})
    )

    with ClobClient(base_url=CLOB_URL) as client:
        quote = client.get_prices("100")

    assert route.called
    assert route.calls.last.request.content == (
        b'[{"token_id":"100","side":"BUY"},{"token_id":"100","side":"SELL"}]'
    )
    assert quote.buy_price == "0.45"
    assert quote.sell_price == "0.47"


@respx.mock
def test_get_midpoint_accepts_mid_or_mid_price() -> None:
    route = respx.get(f"{CLOB_URL}/midpoint").mock(
        side_effect=[
            httpx.Response(200, json={"mid": "0.46"}),
            httpx.Response(200, json={"mid_price": "0.47"}),
        ]
    )

    with ClobClient(base_url=CLOB_URL) as client:
        first = client.get_midpoint("100")
        second = client.get_midpoint("100")

    assert route.call_count == 2
    assert first.midpoint == "0.46"
    assert second.midpoint == "0.47"


@respx.mock
def test_get_spread_returns_normalized_quote() -> None:
    respx.get(f"{CLOB_URL}/spread").mock(return_value=httpx.Response(200, json={"spread": "0.02"}))

    with ClobClient(base_url=CLOB_URL) as client:
        spread = client.get_spread("100")

    assert spread.token_id == "100"
    assert spread.spread == "0.02"


@respx.mock
def test_book_404_maps_to_not_found() -> None:
    respx.get(f"{CLOB_URL}/book").mock(return_value=httpx.Response(404))

    with ClobClient(base_url=CLOB_URL) as client:
        try:
            client.get_book("missing")
        except ClobNotFoundError as exc:
            assert str(exc) == "book for token_id 'missing' was not found"
        else:
            raise AssertionError("ClobNotFoundError was not raised")
