"""CLI tests for the read-only market and CLOB commands."""

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
MIDPOINT_PAYLOAD = {"mid": "0.223"}
SPREAD_PAYLOAD = {"spread": "0.002"}


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--output" in result.stdout
    assert "--json" in result.stdout
    assert "market" in result.stdout
    assert "clob" in result.stdout


def test_market_help() -> None:
    result = runner.invoke(app, ["market", "--help"])

    assert result.exit_code == 0
    assert "search" in result.stdout
    assert "show" in result.stdout
    assert "event" in result.stdout
    assert "book" in result.stdout
    assert "price" in result.stdout
    assert "Deprecated alias" in result.stdout
    assert "Series commands are deferred" in result.stdout


def test_clob_help() -> None:
    result = runner.invoke(app, ["clob", "--help"])

    assert result.exit_code == 0
    assert "book" in result.stdout
    assert "price" in result.stdout
    assert "midpoint" in result.stdout
    assert "spread" in result.stdout


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
def test_root_global_output_json_for_market_show() -> None:
    route = respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
    )

    result = runner.invoke(
        app,
        ["--output", "json", "market", "show", "--slug", "bitboy-convicted"],
    )

    assert result.exit_code == 0
    assert route.called
    assert json.loads(result.stdout)["market_slug"] == "bitboy-convicted"


@respx.mock
def test_leaf_local_output_json_for_market_show() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
    )

    result = runner.invoke(
        app,
        ["market", "show", "--slug", "bitboy-convicted", "--output", "json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["market_slug"] == "bitboy-convicted"


@respx.mock
def test_leaf_output_overrides_root_output_mode() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
    )

    result = runner.invoke(
        app,
        [
            "--output",
            "json",
            "market",
            "show",
            "--slug",
            "bitboy-convicted",
            "--output",
            "table",
        ],
    )

    assert result.exit_code == 0
    assert "Market: bitboy-convicted" in result.stdout


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
def test_clob_book_json() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(200, json=BOOK_PAYLOAD),
    )

    result = runner.invoke(app, ["clob", "book", "--token-id", "1", "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "1"}
    assert json.loads(result.stdout) == {
        "asks": [{"price": "0.20", "size": "4"}],
        "bids": [{"price": "0.10", "size": "5"}, {"price": "0.09", "size": "3"}],
        "min_order_size": "5",
        "tick_size": "0.001",
        "token_id": "1",
    }


@respx.mock
def test_clob_price_json() -> None:
    route = respx.post(f"{DEFAULT_CLOB_URL}/prices").mock(
        return_value=Response(200, json=PRICES_PAYLOAD),
    )

    result = runner.invoke(app, ["clob", "price", "--token-id", "1", "--json"])

    assert result.exit_code == 0
    assert route.called
    assert route.calls.last.request.content == (
        b'[{"token_id":"1","side":"BUY"},{"token_id":"1","side":"SELL"}]'
    )
    assert json.loads(result.stdout) == {
        "buy_price": "0.214",
        "sell_price": "0.234",
        "token_id": "1",
    }


@respx.mock
def test_clob_midpoint_json() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/midpoint").mock(
        return_value=Response(200, json=MIDPOINT_PAYLOAD),
    )

    result = runner.invoke(app, ["clob", "midpoint", "--token-id", "1", "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "1"}
    assert json.loads(result.stdout) == {"midpoint": "0.223", "token_id": "1"}


@respx.mock
def test_clob_spread_json() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/spread").mock(
        return_value=Response(200, json=SPREAD_PAYLOAD),
    )

    result = runner.invoke(app, ["clob", "spread", "--token-id", "1", "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "1"}
    assert json.loads(result.stdout) == {"spread": "0.002", "token_id": "1"}


@respx.mock
def test_market_book_alias_matches_clob_book() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(200, json=BOOK_PAYLOAD),
    )

    alias_result = runner.invoke(app, ["market", "book", "--token-id", "1", "--json"])
    canonical_result = runner.invoke(app, ["clob", "book", "--token-id", "1", "--json"])

    assert alias_result.exit_code == 0
    assert canonical_result.exit_code == 0
    assert json.loads(alias_result.stdout) == json.loads(canonical_result.stdout)


@respx.mock
def test_market_price_alias_matches_clob_price() -> None:
    respx.post(f"{DEFAULT_CLOB_URL}/prices").mock(
        return_value=Response(200, json=PRICES_PAYLOAD),
    )

    alias_result = runner.invoke(app, ["market", "price", "--token-id", "1", "--json"])
    canonical_result = runner.invoke(app, ["clob", "price", "--token-id", "1", "--json"])

    assert alias_result.exit_code == 0
    assert canonical_result.exit_code == 0
    assert json.loads(alias_result.stdout) == json.loads(canonical_result.stdout)


@respx.mock
def test_market_show_not_found_human_error() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/missing-market").mock(
        return_value=Response(404, json={"error": "slug not found", "type": "not found error"}),
    )

    result = runner.invoke(app, ["market", "show", "--slug", "missing-market"])

    assert result.exit_code == 1
    assert "Error: market 'missing-market' was not found" in result.stdout


@respx.mock
def test_clob_book_not_found_json_error() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(
            404,
            json={"error": "No orderbook exists for the requested token id"},
        ),
    )

    result = runner.invoke(app, ["clob", "book", "--token-id", "missing", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "identifier": "missing",
            "message": "book for token_id 'missing' was not found",
            "resource": "book",
        },
        "ok": False,
    }


def test_unknown_command_json_error() -> None:
    result = runner.invoke(app, ["--json", "unknown"])

    assert result.exit_code == 2
    assert json.loads(result.stdout) == {
        "error": {
            "code": "unknown_command",
            "identifier": "unknown",
            "message": "No such command 'unknown'.",
            "resource": "command",
        },
        "ok": False,
    }


def test_invalid_output_mode_json_error() -> None:
    result = runner.invoke(
        app,
        ["--json", "market", "show", "--slug", "bitboy-convicted", "--output", "yaml"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_argument"
    assert payload["error"]["identifier"] == "output"
    assert payload["error"]["resource"] == "option"
