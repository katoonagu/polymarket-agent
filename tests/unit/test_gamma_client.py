"""Unit tests for the Gamma market discovery client."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from pm import __version__
from pm.market import GammaClient, GammaNotFoundError, NormalizedEvent, NormalizedMarket

DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"


def make_market_payload(
    *,
    slug: str,
    question: str,
    event_slug: str | None = None,
    event_title: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "slug": slug,
        "question": question,
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "conditionId": f"condition-{slug}",
        "clobTokenIds": "[\"1\", \"2\"]",
        "outcomes": "[\"Yes\", \"No\"]",
        "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5,
    }
    if event_slug is not None:
        payload["events"] = [{"slug": event_slug, "title": event_title}]
    return payload


def test_package_version_is_available() -> None:
    assert __version__ == "0.1.0"


@respx.mock
def test_list_active_markets_uses_expected_query_params() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/markets").mock(
        return_value=Response(
            200,
            json=[
                make_market_payload(
                    slug="bitboy-convicted",
                    question="BitBoy convicted?",
                    event_slug="bitboy-convicted",
                    event_title="BitBoy convicted?",
                )
            ],
        ),
    )

    with GammaClient() as client:
        result = client.list_active_markets(limit=1, offset=2)

    assert route.called
    assert dict(route.calls.last.request.url.params) == {
        "active": "true",
        "closed": "false",
        "limit": "1",
        "offset": "2",
    }
    assert result == [
        NormalizedMarket(
            market_slug="bitboy-convicted",
            event_slug="bitboy-convicted",
            question="BitBoy convicted?",
            event_title="BitBoy convicted?",
            active=True,
            closed=False,
            enable_order_book=True,
            condition_id="condition-bitboy-convicted",
            token_ids=["1", "2"],
            outcomes=["Yes", "No"],
            min_tick=0.01,
            min_order_size=5,
        )
    ]


@respx.mock
def test_search_markets_flattens_dedupes_and_caps_results() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/public-search").mock(
        return_value=Response(
            200,
            json={
                "events": [
                    {
                        "slug": "event-one",
                        "title": "Event One",
                        "active": True,
                        "closed": False,
                        "enableOrderBook": True,
                        "markets": [
                            make_market_payload(
                                slug="market-a",
                                question="Question A?",
                            ),
                            make_market_payload(
                                slug="market-a",
                                question="Question A duplicate?",
                            ),
                            make_market_payload(
                                slug="market-b",
                                question="Question B?",
                            ),
                        ],
                    }
                ],
                "pagination": {},
            },
        ),
    )

    with GammaClient() as client:
        result = client.search_markets("btc", limit=2)

    assert route.called
    assert dict(route.calls.last.request.url.params) == {
        "limit_per_type": "2",
        "q": "btc",
        "search_profiles": "false",
        "search_tags": "false",
    }
    assert [market.market_slug for market in result] == ["market-a", "market-b"]
    assert all(market.event_slug == "event-one" for market in result)
    assert all(market.event_title == "Event One" for market in result)


@respx.mock
def test_get_market_by_slug_returns_normalized_market() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(
            200,
            json=make_market_payload(
                slug="bitboy-convicted",
                question="BitBoy convicted?",
                event_slug="bitboy-convicted",
                event_title="BitBoy convicted?",
            ),
        ),
    )

    with GammaClient() as client:
        result = client.get_market_by_slug("bitboy-convicted")

    assert route.called
    assert result.market_slug == "bitboy-convicted"
    assert result.token_ids == ["1", "2"]
    assert result.outcomes == ["Yes", "No"]


@respx.mock
def test_get_event_by_slug_returns_normalized_event() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/events/slug/event-one").mock(
        return_value=Response(
            200,
            json={
                "slug": "event-one",
                "title": "Event One",
                "active": True,
                "closed": False,
                "enableOrderBook": True,
                "markets": [
                    make_market_payload(slug="market-a", question="Question A?"),
                    make_market_payload(slug="market-b", question="Question B?"),
                ],
            },
        ),
    )

    with GammaClient() as client:
        result = client.get_event_by_slug("event-one")

    assert route.called
    assert isinstance(result, NormalizedEvent)
    assert result.event_slug == "event-one"
    assert [market.market_slug for market in result.markets] == ["market-a", "market-b"]
    assert all(market.event_slug == "event-one" for market in result.markets)


@respx.mock
def test_market_slug_404_maps_to_not_found() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/missing-market").mock(
        return_value=Response(404, json={"error": "slug not found", "type": "not found error"}),
    )

    with GammaClient() as client:
        with pytest.raises(GammaNotFoundError):
            client.get_market_by_slug("missing-market")
