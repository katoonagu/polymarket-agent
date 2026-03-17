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
MIDPOINT_PAYLOAD = {"mid": "0.224"}
SPREAD_PAYLOAD = {"spread": "0.020"}


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "market" in result.stdout
    assert "clob" in result.stdout
    assert "--output" in result.stdout
    assert "--json" in result.stdout


def test_market_help_mentions_deprecated_aliases() -> None:
    result = runner.invoke(app, ["market", "--help"])

    assert result.exit_code == 0
    assert "search" in result.stdout
    assert "show" in result.stdout
    assert "event" in result.stdout
    assert "book" in result.stdout
    assert "price" in result.stdout
    assert "deprecated" in result.stdout.lower()


def test_clob_help() -> None:
    result = runner.invoke(app, ["clob", "--help"])

    assert result.exit_code == 0
    assert "book" in result.stdout
    assert "price" in result.stdout
    assert "midpoint" in result.stdout
    assert "spread" in result.stdout


@respx.mock
def test_root_output_json_market_show() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
    )

    result = runner.invoke(
        app,
        ["--output", "json", "market", "show", "--slug", "bitboy-convicted"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["market_slug"] == "bitboy-convicted"


@respx.mock
def test_root_json_alias_market_event() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/events/slug/bitcoin-above-on-march-16").mock(
        return_value=Response(200, json=EVENT_PAYLOAD),
    )

    result = runner.invoke(
        app,
        ["--json", "market", "event", "--slug", "bitcoin-above-on-march-16"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["event_slug"] == "bitcoin-above-on-march-16"


@respx.mock
def test_local_json_overrides_root_table_for_clob_book() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(200, json=BOOK_PAYLOAD),
    )

    result = runner.invoke(
        app,
        ["--output", "table", "clob", "book", "--token-id", "1", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["token_id"] == "1"


@respx.mock
def test_market_search_local_json_still_works() -> None:
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
    assert payload["query"] == "btc"
    assert payload["total"] == 2


@respx.mock
def test_market_show_human_includes_outcome_tokens() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
    )

    result = runner.invoke(app, ["market", "show", "--slug", "bitboy-convicted"])

    assert result.exit_code == 0
    assert "Outcome Tokens: Yes=1, No=2" in result.stdout


@respx.mock
def test_clob_book_json() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(200, json=BOOK_PAYLOAD),
    )

    result = runner.invoke(app, ["clob", "book", "--token-id", "1", "--json"])

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

    payload = json.loads(result.stdout)
    assert payload == {
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

    payload = json.loads(result.stdout)
    assert payload == {
        "midpoint": "0.224",
        "token_id": "1",
    }


@respx.mock
def test_clob_spread_json() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/spread").mock(
        return_value=Response(200, json=SPREAD_PAYLOAD),
    )

    result = runner.invoke(app, ["clob", "spread", "--token-id", "1", "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": "1"}

    payload = json.loads(result.stdout)
    assert payload == {
        "spread": "0.020",
        "token_id": "1",
    }


@respx.mock
def test_market_book_alias_matches_clob_book() -> None:
    route = respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        side_effect=[
            Response(200, json=BOOK_PAYLOAD),
            Response(200, json=BOOK_PAYLOAD),
        ],
    )

    canonical = runner.invoke(app, ["clob", "book", "--token-id", "1", "--json"])
    alias = runner.invoke(app, ["market", "book", "--token-id", "1", "--json"])

    assert canonical.exit_code == 0
    assert alias.exit_code == 0
    assert route.called
    assert json.loads(canonical.stdout) == json.loads(alias.stdout)


@respx.mock
def test_market_price_alias_matches_clob_price() -> None:
    route = respx.post(f"{DEFAULT_CLOB_URL}/prices").mock(
        side_effect=[
            Response(200, json=PRICES_PAYLOAD),
            Response(200, json=PRICES_PAYLOAD),
        ],
    )

    canonical = runner.invoke(app, ["clob", "price", "--token-id", "1", "--json"])
    alias = runner.invoke(app, ["market", "price", "--token-id", "1", "--json"])

    assert canonical.exit_code == 0
    assert alias.exit_code == 0
    assert route.called
    assert json.loads(canonical.stdout) == json.loads(alias.stdout)


@respx.mock
def test_not_found_resource_uses_json_error_contract() -> None:
    respx.get(f"{DEFAULT_CLOB_URL}/book").mock(
        return_value=Response(
            404,
            json={"error": "No orderbook exists for the requested token id"},
        ),
    )

    result = runner.invoke(app, ["--json", "clob", "book", "--token-id", "missing"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": False,
        "error": {
            "code": "not_found",
            "identifier": "missing",
            "message": "book for token_id 'missing' was not found",
            "resource": "book",
        },
    }


def test_unknown_command_uses_json_error_contract() -> None:
    result = runner.invoke(app, ["--json", "unknown"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": False,
        "error": {
            "code": "unknown_command",
            "identifier": "unknown",
            "message": "No such command 'unknown'.",
            "resource": "command",
        },
    }


def test_invalid_output_mode_human_error() -> None:
    result = runner.invoke(app, ["--output", "yaml", "market", "show", "--slug", "test"])

    assert result.exit_code == 1
    assert "Invalid value for '--output'" in result.stdout


def test_invalid_output_mode_json_error() -> None:
    result = runner.invoke(
        app,
        ["--json", "--output", "yaml", "market", "show", "--slug", "test"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_argument"
    assert payload["error"]["resource"] == "option"
    assert payload["error"]["identifier"] == "output"
