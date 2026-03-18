"""Unit tests for tracked-wallet shadow-intelligence aggregation."""

from __future__ import annotations

import httpx
import respx

from pm.wallet import WalletRegistryService, WalletShadowService

DATA_URL = "https://data-api.polymarket.com"
USER = "0x1111111111111111111111111111111111111111"
USER_TWO = "0x2222222222222222222222222222222222222222"
MARKET_SLUG = "btc-above-100k"
CONDITION_ID = "0x" + ("a" * 64)


@respx.mock
def test_summary_assembles_metadata_and_public_data(tmp_path) -> None:
    service = _service_with_wallet(tmp_path, USER, label="Alpha")
    respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "100.50"})
    )
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(
            200,
            json=[_position_payload(), _position_payload(token_id="101")],
        )
    )
    respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(200, json=[_closed_position_payload()])
    )
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_trade_payload()])
    )
    respx.get(f"{DATA_URL}/activity").mock(
        return_value=httpx.Response(200, json=[_activity_payload()])
    )

    summary = service.get_summary(USER, limit=1)

    assert summary.wallet.address == USER
    assert summary.wallet.label == "Alpha"
    assert summary.metrics.holdings_value == "100.50"
    assert summary.metrics.traded_count == 17
    assert summary.metrics.current_positions_count == 2
    assert summary.metrics.closed_positions_count == 1
    assert summary.recent_trades.total == 1
    assert summary.recent_activity.total == 1
    assert summary.errors == []


@respx.mock
def test_summary_records_partial_errors_without_failing(tmp_path) -> None:
    service = _service_with_wallet(tmp_path, USER)
    respx.get(f"{DATA_URL}/value").mock(return_value=httpx.Response(500))
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )
    respx.get(f"{DATA_URL}/positions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/closed-positions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/trades").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/activity").mock(return_value=httpx.Response(200, json=[]))

    summary = service.get_summary(USER, limit=5)

    assert summary.metrics.holdings_value is None
    assert summary.metrics.traded_count == 17
    assert len(summary.errors) == 1
    assert summary.errors[0].section == "holdings_value"
    assert summary.errors[0].code == "request_failed"


@respx.mock
def test_snapshot_is_compact_and_respects_registry_order_and_limit(tmp_path) -> None:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(USER, label="First", added_at="2026-03-18T00:00:00Z")
    registry.add_wallet(USER_TWO, label="Second", added_at="2026-03-18T00:01:00Z")
    service = WalletShadowService(registry=registry)

    respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "100.50"})
    )
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(200, json=[_position_payload()])
    )
    respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(200, json=[_closed_position_payload()])
    )

    snapshot = service.get_snapshot(limit=1)

    assert snapshot.total == 1
    assert snapshot.items[0].wallet.address == USER
    assert snapshot.items[0].wallet.label == "First"
    assert snapshot.items[0].metrics.holdings_value == "100.50"
    assert snapshot.items[0].metrics.traded_count == 17
    assert snapshot.items[0].metrics.current_positions_count == 1
    assert snapshot.items[0].metrics.closed_positions_count == 1
    assert snapshot.items[0].errors == []


def _service_with_wallet(
    tmp_path,
    address: str,
    *,
    label: str | None = None,
) -> WalletShadowService:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(address, label=label, added_at="2026-03-18T00:00:00Z")
    return WalletShadowService(registry=registry)


def _trade_payload() -> dict[str, object]:
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


def _activity_payload() -> dict[str, object]:
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


def _position_payload(*, token_id: str = "100") -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": token_id,
        "outcome": "Yes",
        "size": "12",
        "avgPrice": "0.41",
        "initialValue": "4.92",
        "currentValue": "5.52",
        "cashPnl": "0.60",
        "percentPnl": "12.19",
    }


def _closed_position_payload() -> dict[str, object]:
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
