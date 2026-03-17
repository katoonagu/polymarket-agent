"""CLI tests for read-only Gamma and public CLOB commands."""

from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from pm.cli.app import app

runner = CliRunner()
GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
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


def test_clob_help() -> None:
    result = runner.invoke(app, ["clob", "--help"])

    assert result.exit_code == 0
    assert "book" in result.stdout
    assert "price" in result.stdout
    assert "midpoint" in result.stdout
    assert "spread" in result.stdout


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
    )

    result = runner.invoke(
        app,
        ["--output", "json", "market", "search", "--query", "btc", "--limit", "2"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
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
    }


@respx.mock
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
    }


@respx.mock
def test_clob_midpoint_json() -> None:
    respx.get(f"{CLOB_URL}/midpoint").mock(return_value=httpx.Response(200, json={"mid": "0.46"}))

    result = runner.invoke(app, ["clob", "midpoint", "--token-id", "100", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "midpoint": "0.46",
        "token_id": "100",
    }


@respx.mock
def test_clob_spread_json() -> None:
    respx.get(f"{CLOB_URL}/spread").mock(return_value=httpx.Response(200, json={"spread": "0.02"}))

    result = runner.invoke(app, ["clob", "spread", "--token-id", "100", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "spread": "0.02",
        "token_id": "100",
    }


@respx.mock
def test_market_book_alias_matches_clob_book() -> None:
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


@respx.mock
def test_market_price_alias_matches_clob_price() -> None:
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

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
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


def _event_payload() -> dict[str, object]:
    return {
        "slug": "bitcoin-event",
        "title": "Bitcoin event",
        "active": True,
        "closed": False,
        "enableOrderBook": True,
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
