"""CLI tests for the Gamma market discovery commands."""

from __future__ import annotations

import json

import respx
from httpx import Response
from typer.testing import CliRunner

from pm.cli.app import app

runner = CliRunner()
DEFAULT_CLOB_URL = "https://clob.polymarket.com"
DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"
MARKET_PAYLOAD = {
    "slug": "bitboy-convicted",
    "question": "BitBoy convicted?",
    "active": True,
    "closed": False,
    "enableOrderBook": True,
    "conditionId": "0xabc",
    "clobTokenIds": "[\"1\", \"2\"]",
    "outcomes": "[\"Yes\", \"No\"]",
    "orderPriceMinTickSize": 0.001,
    "orderMinSize": 5,
    "events": [{"slug": "bitboy-convicted", "title": "BitBoy convicted?"}],
}
EVENT_PAYLOAD = {
    "slug": "bitcoin-above-on-march-16",
    "title": "Bitcoin above ___ on March 16?",
    "active": True,
    "closed": False,
    "enableOrderBook": True,
    "markets": [
        {
            "slug": "btc-above-60000-on-march-16",
            "question": "Will the price of Bitcoin be above $60,000 on March 16?",
            "active": True,
            "closed": False,
            "enableOrderBook": True,
            "conditionId": "0xdef",
            "clobTokenIds": ["10", "20"],
            "outcomes": ["Yes", "No"],
            "orderPriceMinTickSize": 0.01,
            "orderMinSize": 1,
        }
    ],
}
SEARCH_PAYLOAD = {
    "events": [
        {
            "slug": "bitcoin-above-on-march-16",
            "title": "Bitcoin above ___ on March 16?",
            "active": True,
            "closed": False,
            "enableOrderBook": True,
            "markets": [
                {
                    "slug": "btc-above-60000-on-march-16",
                    "question": "Will the price of Bitcoin be above $60,000 on March 16?",
                    "active": True,
                    "closed": False,
                    "enableOrderBook": True,
                    "conditionId": "0xdef",
                    "clobTokenIds": "[\"10\", \"20\"]",
                    "outcomes": "[\"Yes\", \"No\"]",
                    "orderPriceMinTickSize": 0.01,
                    "orderMinSize": 1,
                },
                {
                    "slug": "btc-above-65000-on-march-16",
                    "question": "Will the price of Bitcoin be above $65,000 on March 16?",
                    "active": True,
                    "closed": False,
                    "enableOrderBook": True,
                    "conditionId": "0xghi",
                    "clobTokenIds": "[\"30\", \"40\"]",
                    "outcomes": "[\"Yes\", \"No\"]",
                    "orderPriceMinTickSize": 0.01,
                    "orderMinSize": 1,
                },
            ],
        }
    ],
    "pagination": {},
}
BOOK_PAYLOAD = {
    "asset_id": "1",
    "bids": [{"price": "0.10", "size": "5"}, {"price": "0.09", "size": "3"}],
    "asks": [{"price": "0.20", "size": "4"}],
    "tick_size": "0.001",
    "min_order_size": "5",
}
PRICES_PAYLOAD = {"1": {"BUY": "0.214", "SELL": "0.234"}}


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "market" in result.stdout


def test_market_help() -> None:
    result = runner.invoke(app, ["market", "--help"])

    assert result.exit_code == 0
    assert "search" in result.stdout
    assert "show" in result.stdout
    assert "event" in result.stdout
    assert "book" in result.stdout
    assert "price" in result.stdout


@respx.mock
def test_market_search_json() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/public-search").mock(
        return_value=Response(200, json=SEARCH_PAYLOAD),
    )
    result = runner.invoke(
        app,
        ["market", "search", "--query", "btc", "--limit", "2", "--json"],
    )

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {
        "limit_per_type": "2",
        "q": "btc",
        "search_profiles": "false",
        "search_tags": "false",
    }

    payload = json.loads(result.stdout)
    assert payload == {
        "query": "btc",
        "results": [
            {
                "active": True,
                "closed": False,
                "condition_id": "0xdef",
                "enable_order_book": True,
                "event_slug": "bitcoin-above-on-march-16",
                "event_title": "Bitcoin above ___ on March 16?",
                "market_slug": "btc-above-60000-on-march-16",
                "min_order_size": 1,
                "min_tick": 0.01,
                "outcomes": ["Yes", "No"],
                "question": "Will the price of Bitcoin be above $60,000 on March 16?",
                "token_ids": ["10", "20"],
            },
            {
                "active": True,
                "closed": False,
                "condition_id": "0xghi",
                "enable_order_book": True,
                "event_slug": "bitcoin-above-on-march-16",
                "event_title": "Bitcoin above ___ on March 16?",
                "market_slug": "btc-above-65000-on-march-16",
                "min_order_size": 1,
                "min_tick": 0.01,
                "outcomes": ["Yes", "No"],
                "question": "Will the price of Bitcoin be above $65,000 on March 16?",
                "token_ids": ["30", "40"],
            },
        ],
        "total": 2,
    }


@respx.mock
def test_market_show_json() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
    )

    result = runner.invoke(app, ["market", "show", "--slug", "bitboy-convicted", "--json"])

    assert result.exit_code == 0
    assert route.called

    payload = json.loads(result.stdout)
    assert payload == {
        "active": True,
        "closed": False,
        "condition_id": "0xabc",
        "enable_order_book": True,
        "event_slug": "bitboy-convicted",
        "event_title": "BitBoy convicted?",
        "market_slug": "bitboy-convicted",
        "min_order_size": 5,
        "min_tick": 0.001,
        "outcomes": ["Yes", "No"],
        "question": "BitBoy convicted?",
        "token_ids": ["1", "2"],
    }


@respx.mock
def test_market_show_human_includes_outcome_tokens() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
    )

    result = runner.invoke(app, ["market", "show", "--slug", "bitboy-convicted"])

    assert result.exit_code == 0
    assert "Outcome Tokens: Yes=1, No=2" in result.stdout


@respx.mock
def test_market_event_json() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/events/slug/bitcoin-above-on-march-16").mock(
        return_value=Response(200, json=EVENT_PAYLOAD),
    )

    result = runner.invoke(
        app,
        ["market", "event", "--slug", "bitcoin-above-on-march-16", "--json"],
    )

    assert result.exit_code == 0
    assert route.called

    payload = json.loads(result.stdout)
    assert payload == {
        "active": True,
        "closed": False,
        "enable_order_book": True,
        "event_slug": "bitcoin-above-on-march-16",
        "markets": [
            {
                "active": True,
                "closed": False,
                "condition_id": "0xdef",
                "enable_order_book": True,
                "event_slug": "bitcoin-above-on-march-16",
                "event_title": "Bitcoin above ___ on March 16?",
                "market_slug": "btc-above-60000-on-march-16",
                "min_order_size": 1,
                "min_tick": 0.01,
                "outcomes": ["Yes", "No"],
                "question": "Will the price of Bitcoin be above $60,000 on March 16?",
                "token_ids": ["10", "20"],
            }
        ],
        "title": "Bitcoin above ___ on March 16?",
    }


@respx.mock
def test_market_book_json() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(200, json=BOOK_PAYLOAD),
    )

    result = runner.invoke(app, ["market", "book", "--token-id", "1", "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "1"}

    payload = json.loads(result.stdout)
    assert payload == {
        "asks": [{"price": "0.20", "size": "4"}],
        "bids": [{"price": "0.10", "size": "5"}, {"price": "0.09", "size": "3"}],
        "min_order_size": "5",
        "tick_size": "0.001",
        "token_id": "1",
    }


@respx.mock
def test_market_price_json() -> None:
    route = respx.post(f"{DEFAULT_CLOB_URL}/prices").mock(
        return_value=Response(200, json=PRICES_PAYLOAD),
    )

    result = runner.invoke(app, ["market", "price", "--token-id", "1", "--json"])

    assert result.exit_code == 0
    assert route.called
    assert route.calls.last.request.content == (
        b'[{"token_id":"1","side":"BUY"},{"token_id":"1","side":"SELL"}]'
    )

    payload = json.loads(result.stdout)
    assert payload == {
        "buy_price": "0.214",
        "sell_price": "0.234",
        "token_id": "1",
    }


@respx.mock
def test_market_show_not_found_human_error() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/missing-market").mock(
        return_value=Response(404, json={"error": "slug not found", "type": "not found error"}),
    )

    result = runner.invoke(app, ["market", "show", "--slug", "missing-market"])

    assert result.exit_code == 1
    assert "Error: market 'missing-market' was not found" in result.stdout


@respx.mock
def test_market_book_not_found_json_error() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(
            404,
            json={"error": "No orderbook exists for the requested token id"},
        ),
    )

    result = runner.invoke(app, ["market", "book", "--token-id", "missing", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "error": "not_found",
        "message": "book for token_id 'missing' was not found",
        "resource": "book",
        "slug": "missing",
    }
