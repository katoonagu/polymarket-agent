"""Unit tests for the Gamma client."""

from __future__ import annotations

import httpx
import respx

from pm.market import (
    GammaClient,
    GammaNotFoundError,
    MarketSearchResponse,
    NormalizedEvent,
    NormalizedMarket,
)

BASE_URL = "https://gamma-api.polymarket.com"


def _market_payload(*, slug: str, question: str) -> dict[str, object]:
    return {
        "slug": slug,
        "question": question,
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "conditionId": "0xcondition",
        "clobTokenIds": "[\"100\", \"101\"]",
        "outcomes": ["Yes", "No"],
    }


@respx.mock
def test_search_markets_calls_public_search_and_normalizes_results() -> None:
    route = respx.get(f"{BASE_URL}/public-search").mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "slug": "bitcoin-event",
                        "title": "Bitcoin event",
                        "markets": [
                            _market_payload(slug="btc-above-100k", question="Will BTC reach 100k?"),
                            _market_payload(
                                slug="btc-above-100k",
                                question="Duplicate market slug",
                            ),
                            {
                                "slug": "btc-below-90k",
                                "question": "Will BTC stay below 90k?",
                                "active": True,
                                "closed": False,
                                "enableOrderBook": False,
                                "conditionId": None,
                                "clobTokenIds": ["200", "201"],
                                "outcomes": "[\"Yes\", \"No\"]",
                            },
                        ],
                    }
                ]
            },
        )
    )

    with GammaClient() as client:
        result = client.search_markets(" btc ", limit=2)

    assert route.called
    request = route.calls[0].request
    assert request.url.params["q"] == "btc"
    assert request.url.params["limit_per_type"] == "2"
    assert request.url.params["search_tags"] == "false"
    assert request.url.params["search_profiles"] == "false"
    assert result == MarketSearchResponse(
        query="btc",
        results=[
            NormalizedMarket(
                market_slug="btc-above-100k",
                event_slug="bitcoin-event",
                question="Will BTC reach 100k?",
                event_title="Bitcoin event",
                active=True,
                closed=False,
                enable_order_book=True,
                condition_id="0xcondition",
                token_ids=["100", "101"],
                outcomes=["Yes", "No"],
            ),
            NormalizedMarket(
                market_slug="btc-below-90k",
                event_slug="bitcoin-event",
                question="Will BTC stay below 90k?",
                event_title="Bitcoin event",
                active=True,
                closed=False,
                enable_order_book=False,
                condition_id=None,
                token_ids=["200", "201"],
                outcomes=["Yes", "No"],
            ),
        ],
        total=2,
    )


@respx.mock
def test_get_market_by_slug_normalizes_nested_event_context() -> None:
    route = respx.get(f"{BASE_URL}/markets/slug/btc-above-100k").mock(
        return_value=httpx.Response(
            200,
            json={
                **_market_payload(slug="btc-above-100k", question="Will BTC reach 100k?"),
                "events": [{"slug": "bitcoin-event", "title": "Bitcoin event"}],
                "outcomes": "[\"Yes\", \"No\"]",
            },
        )
    )

    with GammaClient() as client:
        market = client.get_market_by_slug("btc-above-100k")

    assert route.called
    assert market == NormalizedMarket(
        market_slug="btc-above-100k",
        event_slug="bitcoin-event",
        question="Will BTC reach 100k?",
        event_title="Bitcoin event",
        active=True,
        closed=False,
        enable_order_book=True,
        condition_id="0xcondition",
        token_ids=["100", "101"],
        outcomes=["Yes", "No"],
    )


@respx.mock
def test_get_event_by_slug_normalizes_nested_markets() -> None:
    route = respx.get(f"{BASE_URL}/events/slug/bitcoin-event").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": "bitcoin-event",
                "title": "Bitcoin event",
                "active": True,
                "closed": False,
                "markets": [
                    _market_payload(slug="btc-above-100k", question="Will BTC reach 100k?"),
                ],
            },
        )
    )

    with GammaClient() as client:
        event = client.get_event_by_slug("bitcoin-event")

    assert route.called
    assert event == NormalizedEvent(
        event_slug="bitcoin-event",
        title="Bitcoin event",
        active=True,
        closed=False,
        enable_order_book=True,
        markets=[
            NormalizedMarket(
                market_slug="btc-above-100k",
                event_slug="bitcoin-event",
                question="Will BTC reach 100k?",
                event_title="Bitcoin event",
                active=True,
                closed=False,
                enable_order_book=True,
                condition_id="0xcondition",
                token_ids=["100", "101"],
                outcomes=["Yes", "No"],
            )
        ],
    )


@respx.mock
def test_get_market_by_slug_maps_404_to_not_found() -> None:
    respx.get(f"{BASE_URL}/markets/slug/missing-market").mock(return_value=httpx.Response(404))

    with GammaClient() as client:
        try:
            client.get_market_by_slug("missing-market")
        except GammaNotFoundError as exc:
            assert str(exc) == "market 'missing-market' was not found."
        else:
            raise AssertionError("GammaNotFoundError was not raised")
