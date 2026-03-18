<<<<<<< HEAD
"""CLI tests for the read-only market and CLOB commands."""
=======
"""CLI tests for read-only Gamma and public CLOB commands."""
>>>>>>> feat/02a-python-scaffold

from __future__ import annotations

import json

<<<<<<< HEAD
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
=======
import httpx
import pytest
import respx
from typer.testing import CliRunner

from pm.cli.app import app
from pm.wallet import WalletRegistryService

runner = CliRunner()
GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"
USER = "0x1111111111111111111111111111111111111111"
USER_TWO = "0x2222222222222222222222222222222222222222"
CONDITION_ID = "0x" + ("a" * 64)
MARKET_SLUG = "btc-above-100k"
>>>>>>> feat/02a-python-scaffold


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "market" in result.stdout
    assert "clob" in result.stdout
<<<<<<< HEAD
    assert "--output" in result.stdout
    assert "--json" in result.stdout


def test_market_help_mentions_deprecated_aliases() -> None:
=======
    assert "data" in result.stdout
    assert "wallet" in result.stdout


def test_market_help() -> None:
>>>>>>> feat/02a-python-scaffold
    result = runner.invoke(app, ["market", "--help"])

    assert result.exit_code == 0
    assert "search" in result.stdout
    assert "show" in result.stdout
    assert "event" in result.stdout
    assert "book" in result.stdout
    assert "price" in result.stdout
<<<<<<< HEAD
    assert "deprecated" in result.stdout.lower()
=======
    assert "Deprecated alias" in result.stdout
>>>>>>> feat/02a-python-scaffold


def test_clob_help() -> None:
    result = runner.invoke(app, ["clob", "--help"])

    assert result.exit_code == 0
    assert "book" in result.stdout
    assert "price" in result.stdout
    assert "midpoint" in result.stdout
    assert "spread" in result.stdout


<<<<<<< HEAD
@respx.mock
def test_root_output_json_market_show() -> None:
    respx.get(f"{DEFAULT_GAMMA_URL}/markets/slug/bitboy-convicted").mock(
        return_value=Response(200, json=MARKET_PAYLOAD),
=======
def test_data_help() -> None:
    result = runner.invoke(app, ["data", "--help"])

    assert result.exit_code == 0
    assert "trades" in result.stdout
    assert "activity" in result.stdout
    assert "positions" in result.stdout
    assert "closed-positions" in result.stdout
    assert "holders" in result.stdout
    assert "open-interest" in result.stdout
    assert "value" in result.stdout
    assert "traded" in result.stdout


def test_wallet_help() -> None:
    result = runner.invoke(app, ["wallet", "--help"])

    assert result.exit_code == 0
    assert "add" in result.stdout
    assert "discover" in result.stdout
    assert "list" in result.stdout
    assert "monitor" in result.stdout
    assert "remove" in result.stdout
    assert "score" in result.stdout
    assert "rank" in result.stdout
    assert "compare" in result.stdout
    assert "shadow" in result.stdout
    assert "signals" in result.stdout
    assert "summary" in result.stdout
    assert "trades" in result.stdout
    assert "activity" in result.stdout
    assert "positions" in result.stdout
    assert "snapshot" in result.stdout


@respx.mock
def test_root_output_json_for_market_search() -> None:
    respx.get(f"{GAMMA_URL}/public-search").mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "slug": "bitcoin-event",
                        "title": "Bitcoin event",
                        "markets": [
                            {
                                "slug": "btc-above-100k",
                                "question": "Will BTC reach 100k?",
                                "active": True,
                                "closed": False,
                                "enableOrderBook": True,
                                "conditionId": "0xcondition",
                                "clobTokenIds": ["100", "101"],
                                "outcomes": ["Yes", "No"],
                            }
                        ],
                    }
                ]
            },
        )
>>>>>>> feat/02a-python-scaffold
    )

    result = runner.invoke(
        app,
<<<<<<< HEAD
        ["--output", "json", "market", "show", "--slug", "bitboy-convicted"],
=======
        ["--output", "json", "market", "search", "--query", "btc", "--limit", "2"],
>>>>>>> feat/02a-python-scaffold
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
<<<<<<< HEAD
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
=======
    assert payload["query"] == "btc"
    assert payload["results"][0]["market_slug"] == "btc-above-100k"


@respx.mock
def test_root_json_alias_for_clob_book() -> None:
    respx.get(f"{CLOB_URL}/book").mock(
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

    result = runner.invoke(app, ["--json", "clob", "book", "--token-id", "100"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "asks": [{"price": "0.47", "size": "12"}],
        "bids": [{"price": "0.45", "size": "10"}],
        "min_order_size": "5",
        "tick_size": "0.01",
        "token_id": "100",
>>>>>>> feat/02a-python-scaffold
    }


@respx.mock
<<<<<<< HEAD
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
=======
def test_local_json_overrides_root_table() -> None:
    respx.get(f"{CLOB_URL}/spread").mock(return_value=httpx.Response(200, json={"spread": "0.02"}))

    result = runner.invoke(
        app,
        ["--output", "table", "clob", "spread", "--token-id", "100", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"spread": "0.02", "token_id": "100"}


@respx.mock
def test_clob_price_json() -> None:
    respx.post(f"{CLOB_URL}/prices").mock(
        return_value=httpx.Response(
            200,
            json={"100": {"BUY": "0.45", "SELL": "0.47"}},
        )
    )

    result = runner.invoke(app, ["clob", "price", "--token-id", "100", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "buy_price": "0.45",
        "sell_price": "0.47",
        "token_id": "100",
>>>>>>> feat/02a-python-scaffold
    }


@respx.mock
def test_clob_midpoint_json() -> None:
<<<<<<< HEAD
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
=======
    respx.get(f"{CLOB_URL}/midpoint").mock(return_value=httpx.Response(200, json={"mid": "0.46"}))

    result = runner.invoke(app, ["clob", "midpoint", "--token-id", "100", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "midpoint": "0.46",
        "token_id": "100",
>>>>>>> feat/02a-python-scaffold
    }


@respx.mock
def test_clob_spread_json() -> None:
<<<<<<< HEAD
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
=======
    respx.get(f"{CLOB_URL}/spread").mock(return_value=httpx.Response(200, json={"spread": "0.02"}))

    result = runner.invoke(app, ["clob", "spread", "--token-id", "100", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "spread": "0.02",
        "token_id": "100",
>>>>>>> feat/02a-python-scaffold
    }


@respx.mock
def test_market_book_alias_matches_clob_book() -> None:
<<<<<<< HEAD
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
=======
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

    alias_result = runner.invoke(app, ["market", "book", "--token-id", "100", "--json"])
    canonical_result = runner.invoke(app, ["clob", "book", "--token-id", "100", "--json"])

    assert route.call_count == 2
    assert alias_result.exit_code == 0
    assert canonical_result.exit_code == 0
    assert json.loads(alias_result.stdout) == json.loads(canonical_result.stdout)
>>>>>>> feat/02a-python-scaffold


@respx.mock
def test_market_price_alias_matches_clob_price() -> None:
<<<<<<< HEAD
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
=======
    route = respx.post(f"{CLOB_URL}/prices").mock(
        return_value=httpx.Response(
            200,
            json={"100": {"BUY": "0.45", "SELL": "0.47"}},
        )
    )

    alias_result = runner.invoke(app, ["market", "price", "--token-id", "100", "--json"])
    canonical_result = runner.invoke(app, ["clob", "price", "--token-id", "100", "--json"])

    assert route.call_count == 2
    assert alias_result.exit_code == 0
    assert canonical_result.exit_code == 0
    assert json.loads(alias_result.stdout) == json.loads(canonical_result.stdout)


@respx.mock
def test_market_show_event_slug_hint_human() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/bitcoin-event").mock(return_value=httpx.Response(404))
    respx.get(f"{GAMMA_URL}/events/slug/bitcoin-event").mock(
        return_value=httpx.Response(200, json=_event_payload())
    )

    result = runner.invoke(app, ["market", "show", "--slug", "bitcoin-event"])

    assert result.exit_code == 1
    combined_output = result.stdout + getattr(result, "stderr", "")
    assert "This looks like an event slug." in combined_output
    assert "pm market event --slug bitcoin-event" in combined_output
    assert "btc-above-100k" in combined_output


@respx.mock
def test_market_show_event_slug_hint_json() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/bitcoin-event").mock(return_value=httpx.Response(404))
    respx.get(f"{GAMMA_URL}/events/slug/bitcoin-event").mock(
        return_value=httpx.Response(200, json=_event_payload())
    )

    result = runner.invoke(app, ["market", "show", "--slug", "bitcoin-event", "--json"])
>>>>>>> feat/02a-python-scaffold

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
<<<<<<< HEAD
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
=======
        "error": {
            "code": "event_slug_hint",
            "identifier": "bitcoin-event",
            "message": (
                "This looks like an event slug. Use `pm market event --slug bitcoin-event` "
                "or choose one of the returned market_slug values: btc-above-100k."
            ),
            "resource": "market",
        },
        "hint": {
            "event_slug": "bitcoin-event",
            "market_slugs": ["btc-above-100k"],
            "suggested_command": "pm market event --slug bitcoin-event",
        },
        "ok": False,
    }


@respx.mock
def test_data_trades_json() -> None:
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "side": "BUY",
                    "outcome": "Yes",
                    "price": "0.45",
                    "size": "10",
                    "timestamp": 1710000000,
                    "transactionHash": "0xtrade",
                }
            ],
        )
    )

    result = runner.invoke(app, ["data", "trades", "--user", USER, "--limit", "1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "items": [
            {
                "condition_id": CONDITION_ID,
                "market_slug": MARKET_SLUG,
                "outcome": "Yes",
                "price": "0.45",
                "side": "BUY",
                "size": "10",
                "timestamp": 1710000000,
                "token_id": "100",
                "transaction_hash": "0xtrade",
                "user": USER,
            }
        ],
        "total": 1,
        "user": USER,
    }


@respx.mock
def test_data_activity_json() -> None:
    respx.get(f"{DATA_URL}/activity").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "type": "TRADE",
                    "side": "SELL",
                    "outcome": "No",
                    "price": "0.55",
                    "size": "7",
                    "usdcSize": "3.85",
                    "timestamp": 1710000100,
                    "transactionHash": "0xactivity",
                }
            ],
        )
    )

    result = runner.invoke(app, ["data", "activity", "--user", USER, "--limit", "1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["activity_type"] == "TRADE"
    assert payload["items"][0]["usdc_size"] == "3.85"


@respx.mock
def test_data_positions_json() -> None:
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "outcome": "Yes",
                    "size": "12",
                    "avgPrice": "0.41",
                    "initialValue": "4.92",
                    "currentValue": "5.52",
                    "cashPnl": "0.60",
                    "percentPnl": "12.19",
                }
            ],
        )
    )

    result = runner.invoke(app, ["data", "positions", "--user", USER, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["current_value"] == "5.52"
    assert payload["items"][0]["percent_pnl"] == "12.19"


@respx.mock
def test_data_closed_positions_json() -> None:
    respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "outcome": "Yes",
                    "avgPrice": "0.40",
                    "totalBought": "10",
                    "realizedPnl": "1.25",
                    "curPrice": "0.53",
                    "timestamp": 1710000200,
                }
            ],
        )
    )

    result = runner.invoke(app, ["data", "closed-positions", "--user", USER, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["realized_pnl"] == "1.25"
    assert payload["items"][0]["current_price"] == "0.53"


@respx.mock
def test_data_holders_json_with_slug_resolution() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(
            200,
            json=_market_payload(slug=MARKET_SLUG, question="Will BTC reach 100k?"),
        )
    )
    respx.get(f"{DATA_URL}/holders").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "token": "100",
                    "holders": [
                        {
                            "proxyWallet": USER,
                            "amount": "5",
                            "name": "Alice",
                            "pseudonym": "alice",
                            "outcomeIndex": 0,
                        }
                    ],
                }
            ],
        )
    )

    result = runner.invoke(
        app,
        ["data", "holders", "--market", MARKET_SLUG, "--limit", "1", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "condition_id": CONDITION_ID,
        "items": [
            {
                "amount": "5",
                "condition_id": CONDITION_ID,
                "holder_address": USER,
                "market_slug": MARKET_SLUG,
                "name": "Alice",
                "outcome_index": 0,
                "pseudonym": "alice",
                "rank": 1,
                "token_id": "100",
            }
        ],
        "market_slug": MARKET_SLUG,
        "total": 1,
    }


@respx.mock
def test_data_open_interest_json_with_condition_id() -> None:
    respx.get(f"{GAMMA_URL}/markets").mock(
        return_value=httpx.Response(
            200,
            json=[_market_payload(slug=MARKET_SLUG, question="Will BTC reach 100k?")],
        )
    )
    respx.get(f"{DATA_URL}/oi").mock(
        return_value=httpx.Response(200, json=[{"market": CONDITION_ID, "value": "123.45"}])
    )

    result = runner.invoke(app, ["data", "open-interest", "--market", CONDITION_ID, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "condition_id": CONDITION_ID,
        "market_slug": MARKET_SLUG,
        "open_interest": "123.45",
    }


@respx.mock
def test_data_value_and_traded_json() -> None:
    respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "100.50"})
    )
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )

    value_result = runner.invoke(app, ["data", "value", "--user", USER, "--json"])
    traded_result = runner.invoke(app, ["data", "traded", "--user", USER, "--json"])

    assert value_result.exit_code == 0
    assert traded_result.exit_code == 0
    assert json.loads(value_result.stdout) == {"user": USER, "value": "100.50"}
    assert json.loads(traded_result.stdout) == {"traded": 17, "user": USER}


@respx.mock
def test_root_output_json_for_data_command() -> None:
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )

    result = runner.invoke(app, ["--output", "json", "data", "traded", "--user", USER])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"traded": 17, "user": USER}


def test_data_invalid_wallet_json_error() -> None:
    result = runner.invoke(app, ["data", "trades", "--user", "bad-wallet", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_argument",
            "identifier": "bad-wallet",
            "message": "Wallet addresses must use 0x followed by 40 hex characters.",
            "resource": "user",
        },
        "ok": False,
    }


def test_data_invalid_condition_id_json_error() -> None:
    result = runner.invoke(app, ["data", "holders", "--market", "0x1234", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_argument",
            "identifier": "0x1234",
            "message": "Condition IDs must use 0x followed by 64 hex characters.",
            "resource": "market",
        },
        "ok": False,
    }


def test_wallet_add_list_and_remove_json(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "wallets.json"
    monkeypatch.setenv("PM_WALLET_REGISTRY_PATH", str(registry_path))

    add_result = runner.invoke(
        app,
        [
            "--output",
            "json",
            "wallet",
            "add",
            "--address",
            USER,
            "--label",
            "Alpha",
            "--tag",
            "beta",
            "--tag",
            "alpha",
            "--note",
            "Shadow",
        ],
    )
    list_result = runner.invoke(app, ["wallet", "list", "--json"])
    remove_result = runner.invoke(
        app,
        ["--output", "json", "wallet", "remove", "--address", USER],
    )

    assert add_result.exit_code == 0
    added_payload = json.loads(add_result.stdout)
    assert added_payload["wallet"]["address"] == USER
    assert added_payload["wallet"]["label"] == "Alpha"
    assert added_payload["wallet"]["tags"] == ["alpha", "beta"]
    assert added_payload["wallet"]["note"] == "Shadow"

    assert list_result.exit_code == 0
    assert json.loads(list_result.stdout)["total"] == 1

    assert remove_result.exit_code == 0
    assert json.loads(remove_result.stdout)["wallet"]["address"] == USER


def test_wallet_duplicate_add_json_error(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "wallets.json"
    monkeypatch.setenv("PM_WALLET_REGISTRY_PATH", str(registry_path))
    runner.invoke(app, ["wallet", "add", "--address", USER])

    duplicate_result = runner.invoke(
        app,
        [
            "--output",
            "json",
            "wallet",
            "add",
            "--address",
            USER[:2] + USER[2:].upper(),
        ],
    )

    assert duplicate_result.exit_code == 1
    assert json.loads(duplicate_result.stdout) == {
        "error": {
            "code": "already_tracked",
            "identifier": USER,
            "message": f"wallet '{USER}' is already tracked.",
            "resource": "wallet",
        },
        "ok": False,
    }


def test_wallet_invalid_address_json_error() -> None:
    result = runner.invoke(
        app,
        ["--output", "json", "wallet", "add", "--address", "bad-wallet"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_argument",
            "identifier": "bad-wallet",
            "message": "Wallet addresses must use 0x followed by 40 hex characters.",
            "resource": "wallet",
        },
        "ok": False,
    }


@pytest.mark.parametrize("command", ["summary", "trades", "activity", "positions"])
def test_wallet_tracked_only_json_error(command: str, tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "wallets.json"
    monkeypatch.setenv("PM_WALLET_REGISTRY_PATH", str(registry_path))

    result = runner.invoke(app, ["wallet", command, "--address", USER, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_tracked",
            "identifier": USER,
            "message": (
                f"wallet '{USER}' is not tracked. "
                f"Use `pm wallet add --address {USER}` first."
            ),
            "resource": "wallet",
        },
        "ok": False,
    }


@respx.mock
def test_wallet_summary_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER, label="Alpha")
    respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "100.50"})
    )
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(200, json=[_wallet_position_payload()])
    )
    respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(200, json=[_wallet_closed_position_payload()])
    )
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_wallet_trade_payload()])
    )
    respx.get(f"{DATA_URL}/activity").mock(
        return_value=httpx.Response(200, json=[_wallet_activity_payload()])
    )

    result = runner.invoke(app, ["wallet", "summary", "--address", USER, "--limit", "1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["wallet"]["label"] == "Alpha"
    assert payload["metrics"] == {
        "closed_positions_count": 1,
        "current_positions_count": 1,
        "holdings_value": "100.50",
        "traded_count": 17,
    }
    assert payload["recent_trades"]["total"] == 1
    assert payload["recent_activity"]["total"] == 1
    assert payload["errors"] == []


@respx.mock
def test_wallet_trades_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER)
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_wallet_trade_payload()])
    )

    result = runner.invoke(app, ["wallet", "trades", "--address", USER, "--limit", "1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["items"][0]["market_slug"] == MARKET_SLUG
    assert payload["total"] == 1


@respx.mock
def test_wallet_activity_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER)
    respx.get(f"{DATA_URL}/activity").mock(
        return_value=httpx.Response(200, json=[_wallet_activity_payload()])
    )

    result = runner.invoke(app, ["wallet", "activity", "--address", USER, "--limit", "1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["items"][0]["activity_type"] == "TRADE"
    assert payload["total"] == 1


@respx.mock
def test_wallet_positions_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER)
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(200, json=[_wallet_position_payload()])
    )

    result = runner.invoke(app, ["wallet", "positions", "--address", USER, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["items"][0]["current_value"] == "5.52"
    assert payload["total"] == 1


@respx.mock
def test_wallet_snapshot_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER, label="First")
    _seed_tracked_wallet(tmp_path, monkeypatch, USER_TWO, label="Second")
    respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "100.50"})
    )
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(200, json=[_wallet_position_payload()])
    )
    respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(200, json=[_wallet_closed_position_payload()])
    )

    result = runner.invoke(app, ["wallet", "snapshot", "--limit", "1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total"] == 1
    assert payload["items"][0]["wallet"]["address"] == USER
    assert payload["items"][0]["wallet"]["label"] == "First"
    assert payload["items"][0]["metrics"]["holdings_value"] == "100.50"


@respx.mock
def test_wallet_summary_partial_errors_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER)
    respx.get(f"{DATA_URL}/value").mock(return_value=httpx.Response(500))
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )
    respx.get(f"{DATA_URL}/positions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/closed-positions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/trades").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/activity").mock(return_value=httpx.Response(200, json=[]))

    result = runner.invoke(app, ["wallet", "summary", "--address", USER, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["metrics"]["holdings_value"] is None
    assert payload["errors"][0]["section"] == "holdings_value"
    assert payload["errors"][0]["code"] == "request_failed"


def _market_payload(*, slug: str, question: str) -> dict[str, object]:
    return {
        "slug": slug,
        "question": question,
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "conditionId": CONDITION_ID,
        "clobTokenIds": ["100", "101"],
        "outcomes": ["Yes", "No"],
    }


def _event_payload() -> dict[str, object]:
    return {
        "slug": "bitcoin-event",
        "title": "Bitcoin event",
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "markets": [
            _market_payload(slug="btc-above-100k", question="Will BTC reach 100k?"),
        ],
    }


def _seed_tracked_wallet(tmp_path, monkeypatch, address: str, *, label: str | None = None) -> None:
    registry_path = tmp_path / "wallets.json"
    monkeypatch.setenv("PM_WALLET_REGISTRY_PATH", str(registry_path))
    registry = WalletRegistryService(path=registry_path)
    registry.add_wallet(address, label=label, added_at="2026-03-18T00:00:00Z")


def _wallet_trade_payload() -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": "100",
        "side": "BUY",
        "outcome": "Yes",
        "price": "0.45",
        "size": "10",
        "timestamp": 1710000000,
        "transactionHash": "0xtrade",
    }


def _wallet_activity_payload() -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": "100",
        "type": "TRADE",
        "side": "SELL",
        "outcome": "No",
        "price": "0.55",
        "size": "7",
        "usdcSize": "3.85",
        "timestamp": 1710000100,
        "transactionHash": "0xactivity",
    }


def _wallet_position_payload() -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": "100",
        "outcome": "Yes",
        "size": "12",
        "avgPrice": "0.41",
        "initialValue": "4.92",
        "currentValue": "5.52",
        "cashPnl": "0.60",
        "percentPnl": "12.19",
    }


def _wallet_closed_position_payload() -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": "100",
        "outcome": "Yes",
        "avgPrice": "0.40",
        "totalBought": "10",
        "realizedPnl": "1.25",
        "curPrice": "0.53",
        "timestamp": 1710000200,
    }
>>>>>>> feat/02a-python-scaffold
