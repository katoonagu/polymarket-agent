"""CLI tests for the read-only market and CLOB command surface."""

from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from pm.cli.app import app
from pm.market.models import WatchedMarket
from pm.market.state import MarketStateService

runner = CliRunner()
GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"
MARKET_SLUG = "btc-above-100k"
EVENT_SLUG = "bitcoin-event"
CONDITION_ID = "0x" + ("a" * 64)
TOKEN_IDS = ["100", "101"]
OUTCOMES = ["Yes", "No"]


def test_root_help_lists_namespaces_and_output_contract() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "POLYMARKET AGENT" in result.stdout
    assert "setup" in result.stdout
    assert "auth" in result.stdout
    assert "approve" in result.stdout
    assert "market" in result.stdout
    assert "clob" in result.stdout
    assert "data" in result.stdout
    assert "arkham" in result.stdout
    assert "wallet" in result.stdout
    assert "stream" in result.stdout
    assert "risk" in result.stdout
    assert "strategy" in result.stdout
    assert "ops" in result.stdout
    assert "portfolio" in result.stdout
    assert "exec" in result.stdout
    assert "status" in result.stdout
    assert "shell" in result.stdout
    assert "--output" in result.stdout
    assert "--json" in result.stdout


def test_market_help_lists_watch_and_recurring() -> None:
    result = runner.invoke(app, ["market", "--help"])

    assert result.exit_code == 0
    assert "search" in result.stdout
    assert "show" in result.stdout
    assert "event" in result.stdout
    assert "watch" in result.stdout
    assert "recurring" in result.stdout
    assert "Deprecated alias" in result.stdout


def test_clob_help_lists_public_read_commands() -> None:
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
                        "slug": EVENT_SLUG,
                        "title": "Bitcoin event",
                        "markets": [_market_payload()],
                    }
                ]
            },
        )
    )

    result = runner.invoke(
        app,
        ["--output", "json", "market", "search", "--query", "btc", "--limit", "1"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "query": "btc",
        "results": [
            {
                "active": True,
                "closed": False,
                "condition_id": CONDITION_ID,
                "enable_order_book": True,
                "event_slug": EVENT_SLUG,
                "event_title": "Bitcoin event",
                "market_slug": MARKET_SLUG,
                "min_order_size": 5,
                "min_tick": 0.01,
                "outcomes": OUTCOMES,
                "question": "Will BTC reach 100k?",
                "token_ids": TOKEN_IDS,
            }
        ],
        "total": 1,
    }


@respx.mock
def test_market_show_human_output_includes_outcome_token_map() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload())
    )

    result = runner.invoke(app, ["market", "show", "--slug", MARKET_SLUG])

    assert result.exit_code == 0
    assert "Token IDs:" in result.stdout
    assert "Yes: 100" in result.stdout
    assert "No: 101" in result.stdout
    assert "Next: pm clob book --token-id <id>" in result.stdout


@respx.mock
def test_market_show_event_slug_hint_human() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/{EVENT_SLUG}").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{GAMMA_URL}/events/slug/{EVENT_SLUG}").mock(
        return_value=httpx.Response(200, json=_event_payload())
    )

    result = runner.invoke(app, ["market", "show", "--slug", EVENT_SLUG])

    assert result.exit_code == 1
    combined_output = result.stdout + getattr(result, "stderr", "")
    assert "This looks like an event slug." in combined_output
    assert f"pm market event --slug {EVENT_SLUG}" in combined_output
    assert MARKET_SLUG in combined_output


@respx.mock
def test_market_show_event_slug_hint_json() -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/{EVENT_SLUG}").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{GAMMA_URL}/events/slug/{EVENT_SLUG}").mock(
        return_value=httpx.Response(200, json=_event_payload())
    )

    result = runner.invoke(app, ["market", "show", "--slug", EVENT_SLUG, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "event_slug_hint",
            "identifier": EVENT_SLUG,
            "message": (
                "This looks like an event slug. "
                f"Use `pm market event --slug {EVENT_SLUG}` or choose one of the returned "
                f"market_slug values: {MARKET_SLUG}."
            ),
            "resource": "market",
        },
        "hint": {
            "event_slug": EVENT_SLUG,
            "market_slugs": [MARKET_SLUG],
            "suggested_command": f"pm market event --slug {EVENT_SLUG}",
        },
        "ok": False,
    }


@respx.mock
def test_clob_book_json() -> None:
    route = respx.get(f"{CLOB_URL}/book").mock(
        return_value=httpx.Response(
            200,
            json={
                "asset_id": TOKEN_IDS[0],
                "bids": [{"price": "0.45", "size": "10"}],
                "asks": [{"price": "0.47", "size": "12"}],
                "tick_size": "0.01",
                "min_order_size": "5",
            },
        )
    )

    result = runner.invoke(app, ["clob", "book", "--token-id", TOKEN_IDS[0], "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": TOKEN_IDS[0]}
    assert json.loads(result.stdout) == {
        "asks": [{"price": "0.47", "size": "12"}],
        "bids": [{"price": "0.45", "size": "10"}],
        "min_order_size": "5",
        "tick_size": "0.01",
        "token_id": TOKEN_IDS[0],
    }


@respx.mock
def test_clob_price_json() -> None:
    route = respx.post(f"{CLOB_URL}/prices").mock(
        return_value=httpx.Response(
            200,
            json={TOKEN_IDS[0]: {"BUY": "0.45", "SELL": "0.47"}},
        )
    )

    result = runner.invoke(app, ["clob", "price", "--token-id", TOKEN_IDS[0], "--json"])

    assert result.exit_code == 0
    assert route.called
    assert route.calls.last.request.content == (
        b'[{"token_id":"100","side":"BUY"},{"token_id":"100","side":"SELL"}]'
    )
    assert json.loads(result.stdout) == {
        "buy_price": "0.45",
        "sell_price": "0.47",
        "token_id": TOKEN_IDS[0],
    }


@respx.mock
def test_clob_midpoint_json() -> None:
    route = respx.get(f"{CLOB_URL}/midpoint").mock(
        return_value=httpx.Response(200, json={"mid": "0.46"})
    )

    result = runner.invoke(app, ["clob", "midpoint", "--token-id", TOKEN_IDS[0], "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": TOKEN_IDS[0]}
    assert json.loads(result.stdout) == {
        "midpoint": "0.46",
        "token_id": TOKEN_IDS[0],
    }


@respx.mock
def test_clob_spread_json() -> None:
    route = respx.get(f"{CLOB_URL}/spread").mock(
        return_value=httpx.Response(200, json={"spread": "0.02"})
    )

    result = runner.invoke(app, ["clob", "spread", "--token-id", TOKEN_IDS[0], "--json"])

    assert result.exit_code == 0
    assert route.called
    assert dict(route.calls.last.request.url.params) == {"token_id": TOKEN_IDS[0]}
    assert json.loads(result.stdout) == {
        "spread": "0.02",
        "token_id": TOKEN_IDS[0],
    }


@respx.mock
def test_market_book_alias_matches_clob_book() -> None:
    route = respx.get(f"{CLOB_URL}/book").mock(
        return_value=httpx.Response(
            200,
            json={
                "asset_id": TOKEN_IDS[0],
                "bids": [{"price": "0.45", "size": "10"}],
                "asks": [{"price": "0.47", "size": "12"}],
                "tick_size": "0.01",
                "min_order_size": "5",
            },
        )
    )

    alias_result = runner.invoke(app, ["market", "book", "--token-id", TOKEN_IDS[0], "--json"])
    canonical_result = runner.invoke(app, ["clob", "book", "--token-id", TOKEN_IDS[0], "--json"])

    assert alias_result.exit_code == 0
    assert canonical_result.exit_code == 0
    assert route.call_count == 2
    assert json.loads(alias_result.stdout) == json.loads(canonical_result.stdout)


@respx.mock
def test_market_price_alias_matches_clob_price() -> None:
    route = respx.post(f"{CLOB_URL}/prices").mock(
        return_value=httpx.Response(
            200,
            json={TOKEN_IDS[0]: {"BUY": "0.45", "SELL": "0.47"}},
        )
    )

    alias_result = runner.invoke(app, ["market", "price", "--token-id", TOKEN_IDS[0], "--json"])
    canonical_result = runner.invoke(app, ["clob", "price", "--token-id", TOKEN_IDS[0], "--json"])

    assert alias_result.exit_code == 0
    assert canonical_result.exit_code == 0
    assert route.call_count == 2
    assert json.loads(alias_result.stdout) == json.loads(canonical_result.stdout)


@respx.mock
def test_market_watch_add_list_remove_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PM_MARKET_STATE_DIR", str(tmp_path))
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload())
    )

    add_result = runner.invoke(
        app,
        [
            "market",
            "watch",
            "add",
            "--slug",
            MARKET_SLUG,
            "--label",
            "Primary",
            "--tag",
            "btc",
            "--tag",
            "high-priority",
            "--json",
        ],
    )
    list_result = runner.invoke(app, ["market", "watch", "list", "--json"])
    remove_result = runner.invoke(
        app,
        ["market", "watch", "remove", "--slug", MARKET_SLUG, "--json"],
    )

    assert add_result.exit_code == 0
    added_payload = json.loads(add_result.stdout)
    assert added_payload["market"]["market_slug"] == MARKET_SLUG
    assert added_payload["market"]["label"] == "Primary"
    assert added_payload["market"]["tags"] == ["btc", "high-priority"]

    assert list_result.exit_code == 0
    assert json.loads(list_result.stdout)["total"] == 1

    assert remove_result.exit_code == 0
    assert json.loads(remove_result.stdout)["market"]["market_slug"] == MARKET_SLUG


@respx.mock
def test_market_watch_snapshot_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PM_MARKET_STATE_DIR", str(tmp_path))
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload())
    )
    respx.get(f"{GAMMA_URL}/events/slug/{EVENT_SLUG}").mock(
        return_value=httpx.Response(200, json=_event_payload())
    )
    respx.get(f"{CLOB_URL}/midpoint").mock(
        side_effect=[
            httpx.Response(200, json={"mid": "0.45"}),
            httpx.Response(200, json={"mid": "0.55"}),
        ]
    )
    respx.get(f"{CLOB_URL}/spread").mock(
        side_effect=[
            httpx.Response(200, json={"spread": "0.02"}),
            httpx.Response(200, json={"spread": "0.03"}),
        ]
    )
    respx.get(f"{CLOB_URL}/book").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "asset_id": TOKEN_IDS[0],
                    "bids": [{"price": "0.44", "size": "10"}],
                    "asks": [{"price": "0.46", "size": "12"}],
                },
            ),
            httpx.Response(
                200,
                json={
                    "asset_id": TOKEN_IDS[1],
                    "bids": [{"price": "0.54", "size": "8"}],
                    "asks": [{"price": "0.56", "size": "9"}],
                },
            ),
        ]
    )
    respx.get(f"{DATA_URL}/oi").mock(
        return_value=httpx.Response(200, json=[{"market": CONDITION_ID, "value": "123.45"}])
    )
    respx.get(f"{DATA_URL}/holders").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "token": TOKEN_IDS[0],
                    "holders": [
                        {
                            "proxyWallet": "0x1111111111111111111111111111111111111111",
                            "amount": "5",
                            "outcomeIndex": 0,
                        }
                    ],
                }
            ],
        )
    )

    result = runner.invoke(
        app,
        ["market", "watch", "snapshot", "--slug", MARKET_SLUG, "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["snapshot"]["market_slug"] == MARKET_SLUG
    assert payload["snapshot"]["event_slug"] == EVENT_SLUG
    assert payload["snapshot"]["open_interest"] == "123.45"
    assert payload["snapshot"]["tokens"][0]["best_bid"] == "0.44"
    assert payload["snapshot"]["tokens"][1]["best_ask"] == "0.56"
    assert payload["snapshot"]["holders_total_returned"] == 1


@respx.mock
def test_market_watch_refresh_json_keeps_partial_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PM_MARKET_STATE_DIR", str(tmp_path))
    state = MarketStateService()
    state.add_watched_market(
        WatchedMarket(
            market_slug=MARKET_SLUG,
            event_slug=EVENT_SLUG,
            question="Will BTC reach 100k?",
            label="Tracked",
            tags=["btc"],
            added_at="2026-03-18T00:00:00Z",
        )
    )
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(404)
    )

    result = runner.invoke(app, ["market", "watch", "refresh", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "items": [
            {
                "active": None,
                "closed": None,
                "condition_id": None,
                "errors": [
                    {
                        "code": "not_found",
                        "message": f"market '{MARKET_SLUG}' was not found",
                        "section": "market",
                    }
                ],
                "event_slug": EVENT_SLUG,
                "event_title": None,
                "holders_total_returned": 0,
                "market_slug": MARKET_SLUG,
                "open_interest": None,
                "outcomes": [],
                "question": "Will BTC reach 100k?",
                "snapshot_at": json.loads(result.stdout)["items"][0]["snapshot_at"],
                "token_ids": [],
                "tokens": [],
                "top_holders": [],
                "watch_metadata": {
                    "added_at": "2026-03-18T00:00:00Z",
                    "event_slug": EVENT_SLUG,
                    "label": "Tracked",
                    "market_slug": MARKET_SLUG,
                    "question": "Will BTC reach 100k?",
                    "tags": ["btc"],
                },
            }
        ],
        "total": 1,
    }


@respx.mock
def test_market_recurring_latest_json() -> None:
    respx.get(f"{GAMMA_URL}/public-search").mock(
        return_value=httpx.Response(200, json=_recurring_search_payload())
    )

    result = runner.invoke(
        app,
        [
            "--output",
            "json",
            "market",
            "recurring",
            "latest",
            "--query",
            "btc",
            "--interval",
            "15m",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["interval"] == "15m"
    assert payload["item"]["market_slug"] == "btc-15m-newer"
    assert payload["item"]["rank"] == 1


@respx.mock
def test_market_recurring_list_json() -> None:
    respx.get(f"{GAMMA_URL}/public-search").mock(
        return_value=httpx.Response(200, json=_recurring_search_payload())
    )

    result = runner.invoke(
        app,
        [
            "market",
            "recurring",
            "list",
            "--query",
            "btc",
            "--interval",
            "15m",
            "--limit",
            "3",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total"] == 3
    assert [item["market_slug"] for item in payload["items"]] == [
        "btc-15m-newer",
        "btc-15m-older",
        "btc-15m-closed",
    ]
    assert payload["items"][0]["recency_source"] == "endDate"


def test_market_recurring_invalid_interval_json_error() -> None:
    result = runner.invoke(
        app,
        [
            "market",
            "recurring",
            "latest",
            "--query",
            "btc",
            "--interval",
            "30m",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_argument",
            "identifier": "30m",
            "message": "Interval must be one of: 5m, 15m, 1h.",
            "resource": "recurring",
        },
        "ok": False,
    }


def _market_payload(
    *,
    slug: str = MARKET_SLUG,
    question: str = "Will BTC reach 100k?",
    active: bool = True,
    closed: bool = False,
    end_date: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "slug": slug,
        "question": question,
        "active": active,
        "closed": closed,
        "enableOrderBook": True,
        "conditionId": CONDITION_ID,
        "clobTokenIds": TOKEN_IDS,
        "outcomes": OUTCOMES,
        "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5,
        "events": [{"slug": EVENT_SLUG, "title": "Bitcoin event"}],
    }
    if end_date is not None:
        payload["endDate"] = end_date
    return payload


def _event_payload() -> dict[str, object]:
    return {
        "slug": EVENT_SLUG,
        "title": "Bitcoin event",
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "markets": [_market_payload()],
    }


def _recurring_search_payload() -> dict[str, object]:
    return {
        "events": [
            {
                "slug": EVENT_SLUG,
                "title": "Bitcoin 15 minute markets",
                "markets": [
                    _market_payload(
                        slug="btc-15m-older",
                        question="Bitcoin Up or Down - 15 min",
                        end_date="2026-03-18T12:15:00Z",
                    ),
                    _market_payload(
                        slug="btc-15m-newer",
                        question="Bitcoin Up or Down - 15 min",
                        end_date="2026-03-18T12:30:00Z",
                    ),
                    _market_payload(
                        slug="btc-15m-closed",
                        question="Bitcoin Up or Down - 15 min",
                        closed=True,
                        end_date="2026-03-18T12:45:00Z",
                    ),
                    _market_payload(
                        slug="btc-5m",
                        question="Bitcoin Up or Down - 5 min",
                        end_date="2026-03-18T12:30:00Z",
                    ),
                ],
            }
        ]
    }
