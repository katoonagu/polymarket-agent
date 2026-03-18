"""Unit tests for the public Gamma client."""

from __future__ import annotations

import httpx
import respx

from pm.market import GammaClient, GammaNotFoundError

GAMMA_URL = "https://gamma-api.polymarket.com"


def _market_payload(*, slug: str, question: str, condition_id: str = "0xabc") -> dict[str, object]:
    return {
        "slug": slug,
        "question": question,
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "conditionId": condition_id,
        "clobTokenIds": "[\"100\", \"101\"]",
        "outcomes": "[\"Yes\", \"No\"]",
        "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5,
        "events": [{"slug": "bitcoin-event", "title": "Bitcoin event"}],
    }


@respx.mock
def test_search_markets_uses_public_search_and_flattens_markets() -> None:
    route = respx.get(f"{GAMMA_URL}/public-search").mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "slug": "bitcoin-event",
                        "title": "Bitcoin event",
                        "markets": [
                            _market_payload(slug="btc-above-100k", question="Will BTC reach 100k?"),
                            _market_payload(slug="btc-above-100k", question="Will BTC reach 100k?"),
                            _market_payload(slug="btc-above-110k", question="Will BTC reach 110k?"),
                        ],
                    }
                ]
            },
        )
    )

    with GammaClient(base_url=GAMMA_URL) as client:
        result = client.search_markets("btc", limit=2)

    assert route.called
    assert dict(route.calls.last.request.url.params) == {
        "limit_per_type": "2",
        "q": "btc",
        "search_profiles": "false",
        "search_tags": "false",
    }
    assert result.query == "btc"
    assert result.total == 2
    assert [market.market_slug for market in result.results] == [
        "btc-above-100k",
        "btc-above-110k",
    ]
    assert result.results[0].event_slug == "bitcoin-event"
    assert result.results[0].outcomes == ["Yes", "No"]


@respx.mock
def test_get_market_by_slug_normalizes_string_lists() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/btc-above-100k").mock(
        return_value=httpx.Response(
            200,
            json=_market_payload(slug="btc-above-100k", question="Will BTC reach 100k?"),
        )
    )

    with GammaClient(base_url=GAMMA_URL) as client:
        market = client.get_market_by_slug("btc-above-100k")

    assert market.market_slug == "btc-above-100k"
    assert market.condition_id == "0xabc"
    assert market.token_ids == ["100", "101"]
    assert market.outcomes == ["Yes", "No"]
    assert market.min_tick == 0.01
    assert market.min_order_size == 5


@respx.mock
def test_get_market_by_condition_id_uses_markets_endpoint() -> None:
    route = respx.get(f"{GAMMA_URL}/markets").mock(
        return_value=httpx.Response(
            200,
            json=[_market_payload(slug="btc-above-100k", question="Will BTC reach 100k?")],
        )
    )

    with GammaClient(base_url=GAMMA_URL) as client:
        market = client.get_market_by_condition_id("0xabc")

    assert route.called
    assert dict(route.calls.last.request.url.params) == {"condition_ids": "0xabc", "limit": "1"}
    assert market.market_slug == "btc-above-100k"


@respx.mock
def test_get_event_by_slug_normalizes_child_markets() -> None:
    respx.get(f"{GAMMA_URL}/events/slug/bitcoin-event").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": "bitcoin-event",
                "title": "Bitcoin event",
                "active": True,
                "closed": False,
                "enableOrderBook": True,
                "markets": [
                    _market_payload(slug="btc-above-100k", question="Will BTC reach 100k?")
                ],
            },
        )
    )

    with GammaClient(base_url=GAMMA_URL) as client:
        event = client.get_event_by_slug("bitcoin-event")

    assert event.event_slug == "bitcoin-event"
    assert event.markets[0].market_slug == "btc-above-100k"
    assert event.markets[0].event_slug == "bitcoin-event"


@respx.mock
def test_slug_lookup_maps_404_to_not_found_error() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/missing").mock(return_value=httpx.Response(404))

    with GammaClient(base_url=GAMMA_URL) as client:
        try:
            client.get_market_by_slug("missing")
        except GammaNotFoundError as exc:
            assert str(exc) == "market 'missing' was not found"
        else:
            raise AssertionError("GammaNotFoundError was not raised")
