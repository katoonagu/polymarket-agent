"""CLI tests for read-only Gamma market discovery."""

from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from pm.cli.app import app

runner = CliRunner()
BASE_URL = "https://gamma-api.polymarket.com"


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


@respx.mock
def test_market_search_json() -> None:
    respx.get(f"{BASE_URL}/public-search").mock(
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
        ["market", "search", "--query", "btc", "--limit", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "query": "btc",
        "results": [
            {
                "active": True,
                "closed": False,
                "condition_id": "0xcondition",
                "enable_order_book": True,
                "event_slug": "bitcoin-event",
                "event_title": "Bitcoin event",
                "market_slug": "btc-above-100k",
                "outcomes": ["Yes", "No"],
                "question": "Will BTC reach 100k?",
                "token_ids": ["100", "101"],
            }
        ],
        "total": 1,
    }


@respx.mock
def test_market_show_json() -> None:
    respx.get(f"{BASE_URL}/markets/slug/btc-above-100k").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": "btc-above-100k",
                "question": "Will BTC reach 100k?",
                "active": True,
                "closed": False,
                "enableOrderBook": True,
                "conditionId": "0xcondition",
                "clobTokenIds": "[\"100\", \"101\"]",
                "outcomes": "[\"Yes\", \"No\"]",
                "events": [{"slug": "bitcoin-event", "title": "Bitcoin event"}],
            },
        )
    )

    result = runner.invoke(app, ["market", "show", "--slug", "btc-above-100k", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "active": True,
        "closed": False,
        "condition_id": "0xcondition",
        "enable_order_book": True,
        "event_slug": "bitcoin-event",
        "event_title": "Bitcoin event",
        "market_slug": "btc-above-100k",
        "outcomes": ["Yes", "No"],
        "question": "Will BTC reach 100k?",
        "token_ids": ["100", "101"],
    }


@respx.mock
def test_market_event_json() -> None:
    respx.get(f"{BASE_URL}/events/slug/bitcoin-event").mock(
        return_value=httpx.Response(
            200,
            json={
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
            },
        )
    )

    result = runner.invoke(app, ["market", "event", "--slug", "bitcoin-event", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "active": True,
        "closed": False,
        "enable_order_book": True,
        "event_slug": "bitcoin-event",
        "markets": [
            {
                "active": True,
                "closed": False,
                "condition_id": "0xcondition",
                "enable_order_book": True,
                "event_slug": "bitcoin-event",
                "event_title": "Bitcoin event",
                "market_slug": "btc-above-100k",
                "outcomes": ["Yes", "No"],
                "question": "Will BTC reach 100k?",
                "token_ids": ["100", "101"],
            }
        ],
        "title": "Bitcoin event",
    }


@respx.mock
def test_market_show_json_not_found() -> None:
    respx.get(f"{BASE_URL}/markets/slug/missing-market").mock(return_value=httpx.Response(404))

    result = runner.invoke(app, ["market", "show", "--slug", "missing-market", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "error": {
            "code": "not_found",
            "identifier": "missing-market",
            "message": "market 'missing-market' was not found.",
            "resource": "market",
        },
        "ok": False,
    }
