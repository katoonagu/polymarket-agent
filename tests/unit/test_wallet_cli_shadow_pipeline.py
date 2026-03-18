"""CLI tests for wallet monitoring, signals, and shadow-copy simulation."""

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
CLOB_URL = "https://clob.polymarket.com"
USER = "0x1111111111111111111111111111111111111111"
MARKET_SLUG = "btc-above-100k"
CONDITION_ID = "0x" + ("a" * 64)


def test_wallet_monitor_help() -> None:
    result = runner.invoke(app, ["wallet", "monitor", "--help"])

    assert result.exit_code == 0
    assert "run" in result.stdout


def test_wallet_shadow_help() -> None:
    result = runner.invoke(app, ["wallet", "shadow", "--help"])

    assert result.exit_code == 0
    assert "simulate" in result.stdout
    assert "report" in result.stdout


@respx.mock
def test_wallet_monitor_run_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch)
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_trade_payload(transaction_hash="0xmonitor")])
    )
    respx.get(f"{DATA_URL}/activity").mock(return_value=httpx.Response(200, json=[]))

    result = runner.invoke(
        app,
        ["wallet", "monitor", "run", "--address", USER, "--limit", "5", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["fetched_trades_count"] == 1
    assert payload["new_events_count"] == 1
    assert payload["duplicate_events_count"] == 0
    assert payload["new_signals"][0]["classification"] == "new_entry"


@respx.mock
def test_wallet_signals_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch)
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_trade_payload(transaction_hash="0xsignals")])
    )
    respx.get(f"{DATA_URL}/activity").mock(return_value=httpx.Response(200, json=[]))

    monitor_result = runner.invoke(
        app,
        ["wallet", "monitor", "run", "--address", USER, "--limit", "5", "--json"],
    )
    signals_result = runner.invoke(
        app,
        ["--output", "json", "wallet", "signals", "--address", USER, "--limit", "5"],
    )

    assert monitor_result.exit_code == 0
    assert signals_result.exit_code == 0
    payload = json.loads(signals_result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["total"] == 1
    assert payload["items"][0]["transaction_hash"] == "0xsignals"


@respx.mock
def test_wallet_shadow_simulate_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch)
    _mock_monitor_routes(transaction_hash="0xsimulate")
    _mock_market_routes(active=True, closed=False)
    _mock_clob_routes(price="0.42", spread="0.01")

    result = runner.invoke(
        app,
        [
            "wallet",
            "shadow",
            "simulate",
            "--address",
            USER,
            "--fixed-size",
            "25",
            "--max-drift",
            "10",
            "--max-spread",
            "5",
            "--limit",
            "5",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["run"]["would_copy_count"] == 1
    assert payload["run"]["candidate_intents"][0]["decision"] == "WOULD_COPY"
    assert payload["run"]["candidate_intents"][0]["book"]["token_id"] == "100"


@respx.mock
def test_wallet_shadow_report_json(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch)
    _mock_monitor_routes(transaction_hash="0xreport")
    _mock_market_routes(active=True, closed=False)
    _mock_clob_routes(price="0.42", spread="0.01")

    simulate_result = runner.invoke(
        app,
        [
            "wallet",
            "shadow",
            "simulate",
            "--address",
            USER,
            "--fixed-size",
            "25",
            "--max-drift",
            "10",
            "--max-spread",
            "5",
            "--limit",
            "5",
            "--json",
        ],
    )
    report_result = runner.invoke(app, ["wallet", "shadow", "report", "--address", USER, "--json"])

    assert simulate_result.exit_code == 0
    assert report_result.exit_code == 0
    payload = json.loads(report_result.stdout)
    assert payload["wallet"]["address"] == USER
    assert payload["run_count"] == 1
    assert payload["latest_run"]["source_wallet"] == USER
    assert payload["latest_run"]["candidate_intents"][0]["decision"] == "WOULD_COPY"


def test_wallet_monitor_untracked_json_error(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "wallets.json"
    monkeypatch.setenv("PM_WALLET_REGISTRY_PATH", str(registry_path))

    result = runner.invoke(
        app,
        ["wallet", "monitor", "run", "--address", USER, "--json"],
    )

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


def test_wallet_shadow_simulate_invalid_numeric_json_error(tmp_path, monkeypatch) -> None:
    _seed_tracked_wallet(tmp_path, monkeypatch)

    result = runner.invoke(
        app,
        [
            "wallet",
            "shadow",
            "simulate",
            "--address",
            USER,
            "--fixed-size",
            "bad",
            "--max-drift",
            "10",
            "--max-spread",
            "5",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_argument",
            "identifier": USER,
            "message": "Fixed Size must be a decimal number.",
            "resource": "wallet",
        },
        "ok": False,
    }


def _seed_tracked_wallet(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "wallets.json"
    monkeypatch.setenv("PM_WALLET_REGISTRY_PATH", str(registry_path))
    registry = WalletRegistryService(path=registry_path)
    registry.add_wallet(USER, label="Desk", added_at="2026-03-18T00:00:00Z")


def _mock_monitor_routes(*, transaction_hash: str) -> None:
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_trade_payload(transaction_hash=transaction_hash)])
    )
    respx.get(f"{DATA_URL}/activity").mock(return_value=httpx.Response(200, json=[]))


def _mock_market_routes(*, active: bool, closed: bool) -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": MARKET_SLUG,
                "question": "Will BTC reach 100k?",
                "active": active,
                "closed": closed,
                "enableOrderBook": True,
                "conditionId": CONDITION_ID,
                "clobTokenIds": ["100", "101"],
                "outcomes": ["Yes", "No"],
            },
        )
    )


def _mock_clob_routes(*, price: str, spread: str) -> None:
    respx.post(f"{CLOB_URL}/prices").mock(
        return_value=httpx.Response(200, json={"100": {"BUY": price, "SELL": "0.43"}})
    )
    respx.get(f"{CLOB_URL}/spread").mock(return_value=httpx.Response(200, json={"spread": spread}))
    respx.get(f"{CLOB_URL}/book").mock(
        return_value=httpx.Response(
            200,
            json={
                "asset_id": "100",
                "tick_size": "0.01",
                "min_order_size": "5",
                "bids": [{"price": "0.41", "size": "10"}],
                "asks": [{"price": "0.42", "size": "12"}],
            },
        )
    )


def _trade_payload(*, transaction_hash: str) -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": "100",
        "side": "BUY",
        "outcome": "Yes",
        "price": "0.40",
        "size": "10",
        "timestamp": 1710000000,
        "transactionHash": transaction_hash,
    }
