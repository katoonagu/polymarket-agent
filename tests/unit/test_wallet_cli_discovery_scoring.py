"""CLI tests for wallet discovery and deterministic wallet scoring."""

from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from pm.cli.app import app
from pm.wallet import WalletRegistryService

runner = CliRunner()
DATA_URL = "https://data-api.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"
USER = "0x1111111111111111111111111111111111111111"
USER_TWO = "0x2222222222222222222222222222222222222222"
MARKET_SLUG = "btc-above-100k"
CONDITION_ID = "0x" + ("a" * 64)


def test_wallet_discover_help() -> None:
    result = runner.invoke(app, ["wallet", "discover", "--help"])

    assert result.exit_code == 0
    assert "leaderboard" in result.stdout
    assert "holders" in result.stdout


@respx.mock
def test_wallet_discover_leaderboard_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER, label="Tracked")
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"proxyWallet": USER, "rank": 5, "displayName": "Tracked"},
                {"proxyWallet": USER_TWO, "rank": 9, "displayName": "Second"},
            ],
        )
    )

    result = runner.invoke(
        app,
        ["wallet", "discover", "leaderboard", "--limit", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total"] == 2
    assert payload["items"][0]["address"] == USER
    assert payload["items"][0]["tracked"] is True
    assert payload["items"][0]["tracked_wallet"]["label"] == "Tracked"
    assert payload["items"][1]["address"] == USER_TWO


@respx.mock
def test_wallet_discover_holders_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER, label="Tracked")
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload())
    )
    respx.get(f"{DATA_URL}/holders").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "token": "100",
                    "holders": [
                        {"proxyWallet": USER, "amount": "5", "outcomeIndex": 0},
                        {"proxyWallet": USER_TWO, "amount": "2", "outcomeIndex": 0},
                    ],
                },
                {
                    "token": "101",
                    "holders": [
                        {"proxyWallet": USER, "amount": "3", "outcomeIndex": 1},
                    ],
                },
            ],
        )
    )

    result = runner.invoke(
        app,
        ["wallet", "discover", "holders", "--market", MARKET_SLUG, "--limit", "2", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["market_slug"] == MARKET_SLUG
    assert payload["condition_id"] == CONDITION_ID
    assert payload["items"][0]["address"] == USER
    assert len(payload["items"][0]["token_exposures"]) == 2
    assert payload["items"][1]["address"] == USER_TWO


@respx.mock
def test_wallet_score_json() -> None:
    _mock_score_routes()

    result = runner.invoke(app, ["wallet", "score", "--address", USER, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["address"] == USER
    assert payload["total_score"] == 67.5
    assert payload["available_weight"] == 1.0
    assert payload["components"]["leaderboard_component"]["score"] == 90.0


@respx.mock
def test_root_output_json_for_wallet_score() -> None:
    _mock_score_routes()

    result = runner.invoke(app, ["--output", "json", "wallet", "score", "--address", USER])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["address"] == USER
    assert payload["total_score"] == 67.5


@respx.mock
def test_wallet_rank_tracked_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch, USER, label="First")
    _seed_tracked_wallet(tmp_path, monkeypatch, USER_TWO, label="Second")
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(side_effect=_leaderboard_side_effect)
    respx.get(f"{DATA_URL}/closed-positions").mock(side_effect=_closed_positions_side_effect)
    respx.get(f"{DATA_URL}/traded").mock(side_effect=_traded_side_effect)
    respx.get(f"{DATA_URL}/value").mock(side_effect=_value_side_effect)
    respx.get(f"{DATA_URL}/positions").mock(side_effect=_positions_side_effect)

    result = runner.invoke(app, ["wallet", "rank", "tracked", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total"] == 2
    assert payload["items"][0]["score"]["address"] == USER
    assert payload["items"][1]["score"]["address"] == USER_TWO


@respx.mock
def test_wallet_compare_json() -> None:
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(side_effect=_compare_leaderboard_side_effect)
    respx.get(f"{DATA_URL}/closed-positions").mock(side_effect=_compare_closed_positions_side_effect)
    respx.get(f"{DATA_URL}/traded").mock(side_effect=_compare_traded_side_effect)
    respx.get(f"{DATA_URL}/value").mock(side_effect=_compare_value_side_effect)
    respx.get(f"{DATA_URL}/positions").mock(side_effect=_compare_positions_side_effect)

    result = runner.invoke(
        app,
        ["wallet", "compare", "--address", USER, "--address", USER_TWO, "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["left"]["address"] == USER
    assert payload["right"]["address"] == USER_TWO
    assert payload["winner_address"] == USER
    assert payload["score_delta"] == 79.5


def test_wallet_score_invalid_address_json_error() -> None:
    result = runner.invoke(app, ["wallet", "score", "--address", "bad-wallet", "--json"])

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


def _seed_tracked_wallet(tmp_path, monkeypatch, address: str, *, label: str | None = None) -> None:
    registry_path = tmp_path / "wallets.json"
    monkeypatch.setenv("PM_WALLET_REGISTRY_PATH", str(registry_path))
    registry = WalletRegistryService(path=registry_path)
    if not any(wallet.address == address for wallet in registry.list_wallets()):
        registry.add_wallet(address, label=label, added_at="2026-03-18T00:00:00Z")


def _market_payload() -> dict[str, object]:
    return {
        "slug": MARKET_SLUG,
        "question": "Will BTC reach 100k?",
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "conditionId": CONDITION_ID,
        "clobTokenIds": ["100", "101"],
        "outcomes": ["Yes", "No"],
    }


def _mock_score_routes() -> None:
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(
        return_value=httpx.Response(200, json=[{"proxyWallet": USER, "rank": 20}])
    )
    respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(200, json=[{"proxyWallet": USER, "realizedPnl": "600"}])
    )
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 30})
    )
    respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "1500"})
    )
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(
            200,
            json=[{"proxyWallet": USER, "asset": str(index)} for index in range(6)],
        )
    )


def _leaderboard_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    if user == USER:
        payload = [{"proxyWallet": USER, "rank": 20}]
    else:
        payload = [{"proxyWallet": USER_TWO, "rank": 100}]
    return httpx.Response(200, json=payload)


def _closed_positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    payload = [{"proxyWallet": user, "realizedPnl": "600" if user == USER else "2000"}]
    return httpx.Response(200, json=payload)


def _traded_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    return httpx.Response(200, json={"user": user, "traded": 5 if user == USER else 0})


def _value_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    return httpx.Response(200, json={"user": user, "value": "0" if user == USER else "50"})


def _positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    return httpx.Response(200, json=[{"proxyWallet": user, "asset": "100"}])


def _compare_leaderboard_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    return httpx.Response(200, json=[{"proxyWallet": user, "rank": 10 if user == USER else 500}])


def _compare_closed_positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    return httpx.Response(
        200,
        json=[{"proxyWallet": user, "realizedPnl": "5000" if user == USER else "0"}],
    )


def _compare_traded_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    return httpx.Response(200, json={"user": user, "traded": 100 if user == USER else 10})


def _compare_value_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    return httpx.Response(200, json={"user": user, "value": "20000" if user == USER else "0"})


def _compare_positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    if user == USER:
        payload = [{"proxyWallet": user, "asset": str(index)} for index in range(20)]
    else:
        payload = []
    return httpx.Response(200, json=payload)
