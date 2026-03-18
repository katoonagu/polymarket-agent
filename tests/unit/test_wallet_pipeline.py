"""Unit tests for read-only wallet monitoring and shadow simulation."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from pm.data.models import NormalizedActivity, NormalizedTrade
from pm.wallet import WalletRegistryService, WalletShadowService, WalletStateError
from pm.wallet.pipeline import (
    _activity_to_event,
    _classify_events,
    _sort_event_window,
    _trade_to_event,
)
from pm.wallet.state import WalletPipelineStateService

DATA_URL = "https://data-api.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
USER = "0x1111111111111111111111111111111111111111"
MARKET_SLUG = "btc-above-100k"
CONDITION_ID = "0x" + ("a" * 64)


def test_event_classification_covers_expected_categories() -> None:
    events = _classify_events(
        _sort_event_window(
            [
                _trade_to_event(_trade_model(timestamp=1, transaction_hash="0x01", size="10")),
                _trade_to_event(_trade_model(timestamp=2, transaction_hash="0x02", size="5")),
                _trade_to_event(
                    _trade_model(
                        timestamp=3,
                        transaction_hash="0x03",
                        side="SELL",
                        size="4",
                    )
                ),
                _trade_to_event(
                    _trade_model(
                        timestamp=4,
                        transaction_hash="0x04",
                        side="SELL",
                        size="20",
                    )
                ),
                _trade_to_event(
                    _trade_model(
                        timestamp=5,
                        transaction_hash="0xhedge",
                        token_id="200",
                    )
                ),
                _trade_to_event(
                    _trade_model(
                        timestamp=5,
                        transaction_hash="0xhedge",
                        token_id="201",
                        outcome="No",
                    )
                ),
                _activity_to_event(
                    NormalizedActivity(
                        user=USER,
                        market_slug=MARKET_SLUG,
                        condition_id=CONDITION_ID,
                        token_id="300",
                        activity_type="CANCEL",
                        side="BUY",
                        outcome="Yes",
                        price="0.40",
                        size="1",
                        usdc_size="0.40",
                        timestamp=6,
                        transaction_hash="0xnoise",
                    )
                ),
            ]
        )
    )

    assert [event.classification for event in events] == [
        "new_entry",
        "add",
        "reduce",
        "close",
        "hedge_candidate",
        "hedge_candidate",
        "noise",
    ]


@respx.mock
def test_monitor_creates_state_files_and_dedupes_existing_window(tmp_path) -> None:
    service, state = _service_with_state(tmp_path)
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_trade_payload(transaction_hash="0xtrade")])
    )
    respx.get(f"{DATA_URL}/activity").mock(
        return_value=httpx.Response(
            200,
            json=[
                _activity_payload(
                    transaction_hash="0xtrade",
                    activity_type="TRADE",
                )
            ],
        )
    )

    result = service.run_monitor(USER, limit=5)

    assert result.fetched_trades_count == 1
    assert result.fetched_activity_count == 1
    assert result.new_events_count == 1
    assert result.duplicate_events_count == 1
    assert len(result.new_signals) == 1
    assert state.events_path.exists()
    assert state.signals_path.exists()
    assert json.loads(state.events_path.read_text(encoding="utf-8"))["version"] == 1
    assert json.loads(state.signals_path.read_text(encoding="utf-8"))["version"] == 1


def test_corrupted_signal_state_raises_wallet_state_error(tmp_path) -> None:
    service, state = _service_with_state(tmp_path)
    state.signals_path.parent.mkdir(parents=True, exist_ok=True)
    state.signals_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(WalletStateError):
        service.get_signals(USER, limit=5)


@respx.mock
def test_shadow_simulation_would_copy_when_thresholds_pass(tmp_path) -> None:
    service, state = _service_with_state(tmp_path)
    _mock_monitor_routes(transaction_hash="0xcopy")
    _mock_market_routes(active=True, closed=False)
    _mock_clob_routes(price="0.42", spread="0.01")

    result = service.simulate_shadow(
        USER,
        fixed_size_usdc="25",
        max_drift_pct="10",
        max_spread_pct="5",
        entry_only=False,
        limit=5,
    )

    candidate = result.run.candidate_intents[0]
    assert candidate.decision == "WOULD_COPY"
    assert candidate.skip_reason is None
    assert candidate.current_price == "0.42"
    assert candidate.book is not None
    assert state.shadow_runs_path.exists()


@respx.mock
def test_shadow_simulation_skips_duplicate_event(tmp_path) -> None:
    service, _ = _service_with_state(tmp_path)
    _mock_monitor_routes(transaction_hash="0xdup")

    first_run = service.run_monitor(USER, limit=5)
    shadow_run = service.simulate_shadow(
        USER,
        fixed_size_usdc="25",
        max_drift_pct="10",
        max_spread_pct="5",
        entry_only=False,
        limit=5,
    )

    assert first_run.new_events_count == 1
    candidate = shadow_run.run.candidate_intents[0]
    assert candidate.decision == "SKIP"
    assert candidate.skip_reason == "duplicate_event"
    assert shadow_run.run.duplicate_event_count == 1


@respx.mock
def test_shadow_simulation_skips_inactive_market(tmp_path) -> None:
    service, _ = _service_with_state(tmp_path)
    _mock_monitor_routes(transaction_hash="0xinactive")
    _mock_market_routes(active=False, closed=False)
    _mock_clob_routes(price="0.42", spread="0.01")

    result = service.simulate_shadow(
        USER,
        fixed_size_usdc="25",
        max_drift_pct="10",
        max_spread_pct="5",
        entry_only=False,
        limit=5,
    )

    candidate = result.run.candidate_intents[0]
    assert candidate.decision == "SKIP"
    assert candidate.skip_reason == "market_inactive"


@respx.mock
def test_shadow_simulation_skips_on_drift_threshold(tmp_path) -> None:
    service, _ = _service_with_state(tmp_path)
    _mock_monitor_routes(transaction_hash="0xdrift")
    _mock_market_routes(active=True, closed=False)
    _mock_clob_routes(price="0.60", spread="0.01")

    result = service.simulate_shadow(
        USER,
        fixed_size_usdc="25",
        max_drift_pct="5",
        max_spread_pct="10",
        entry_only=False,
        limit=5,
    )

    candidate = result.run.candidate_intents[0]
    assert candidate.decision == "SKIP"
    assert candidate.skip_reason == "drift_threshold"
    assert candidate.drift == "50"


@respx.mock
def test_shadow_simulation_skips_on_spread_threshold(tmp_path) -> None:
    service, _ = _service_with_state(tmp_path)
    _mock_monitor_routes(transaction_hash="0xspread")
    _mock_market_routes(active=True, closed=False)
    _mock_clob_routes(price="0.41", spread="0.05")

    result = service.simulate_shadow(
        USER,
        fixed_size_usdc="25",
        max_drift_pct="50",
        max_spread_pct="5",
        entry_only=False,
        limit=5,
    )

    candidate = result.run.candidate_intents[0]
    assert candidate.decision == "SKIP"
    assert candidate.skip_reason == "spread_threshold"
    assert candidate.spread == "0.05"


@respx.mock
def test_shadow_simulation_skips_non_entry_in_entry_only_mode(tmp_path) -> None:
    service, _ = _service_with_state(tmp_path)
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(
            200,
            json=[_trade_payload(transaction_hash="0xreduce", side="SELL", size="5")],
        )
    )
    respx.get(f"{DATA_URL}/activity").mock(return_value=httpx.Response(200, json=[]))
    _mock_market_routes(active=True, closed=False)
    _mock_clob_routes(price="0.39", spread="0.01")

    result = service.simulate_shadow(
        USER,
        fixed_size_usdc="25",
        max_drift_pct="50",
        max_spread_pct="10",
        entry_only=True,
        limit=5,
    )

    candidate = result.run.candidate_intents[0]
    assert candidate.classification == "close"
    assert candidate.decision == "SKIP"
    assert candidate.skip_reason == "entry_only_filtered"


@respx.mock
def test_shadow_simulation_records_partial_upstream_errors(tmp_path) -> None:
    service, _ = _service_with_state(tmp_path)
    _mock_monitor_routes(transaction_hash="0xbookfail")
    _mock_market_routes(active=True, closed=False)
    respx.post(f"{CLOB_URL}/prices").mock(
        return_value=httpx.Response(200, json={"100": {"BUY": "0.42", "SELL": "0.43"}})
    )
    respx.get(f"{CLOB_URL}/spread").mock(return_value=httpx.Response(200, json={"spread": "0.01"}))
    respx.get(f"{CLOB_URL}/book").mock(return_value=httpx.Response(500))

    result = service.simulate_shadow(
        USER,
        fixed_size_usdc="25",
        max_drift_pct="10",
        max_spread_pct="5",
        entry_only=False,
        limit=5,
    )

    candidate = result.run.candidate_intents[0]
    assert candidate.decision == "SKIP"
    assert candidate.skip_reason == "book_unavailable"
    assert any(error.section.startswith("clob_book:") for error in result.run.errors)


def _service_with_state(tmp_path) -> tuple[WalletShadowService, WalletPipelineStateService]:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(USER, label="Desk", added_at="2026-03-18T00:00:00Z")
    state = WalletPipelineStateService(
        events_path=tmp_path / "wallet-events.json",
        signals_path=tmp_path / "wallet-signals.json",
        shadow_runs_path=tmp_path / "wallet-shadow-runs.json",
    )
    return WalletShadowService(registry=registry, state=state), state


def _trade_model(
    *,
    timestamp: int,
    transaction_hash: str,
    token_id: str = "100",
    side: str = "BUY",
    size: str = "10",
    outcome: str = "Yes",
) -> NormalizedTrade:
    return NormalizedTrade(
        user=USER,
        market_slug=MARKET_SLUG,
        condition_id=CONDITION_ID,
        token_id=token_id,
        side=side,
        outcome=outcome,
        price="0.40",
        size=size,
        timestamp=timestamp,
        transaction_hash=transaction_hash,
    )


def _mock_monitor_routes(*, transaction_hash: str) -> None:
    respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(200, json=[_trade_payload(transaction_hash=transaction_hash)])
    )
    respx.get(f"{DATA_URL}/activity").mock(return_value=httpx.Response(200, json=[]))


def _mock_market_routes(*, active: bool, closed: bool) -> None:
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload(active=active, closed=closed))
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


def _trade_payload(
    *,
    transaction_hash: str,
    side: str = "BUY",
    size: str = "10",
) -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": "100",
        "side": side,
        "outcome": "Yes",
        "price": "0.40",
        "size": size,
        "timestamp": 1710000000,
        "transactionHash": transaction_hash,
    }


def _activity_payload(
    *,
    transaction_hash: str,
    activity_type: str,
) -> dict[str, object]:
    return {
        "proxyWallet": USER,
        "slug": MARKET_SLUG,
        "conditionId": CONDITION_ID,
        "asset": "100",
        "type": activity_type,
        "side": "BUY",
        "outcome": "Yes",
        "price": "0.40",
        "size": "10",
        "usdcSize": "4.00",
        "timestamp": 1710000000,
        "transactionHash": transaction_hash,
    }


def _market_payload(*, active: bool, closed: bool) -> dict[str, object]:
    return {
        "slug": MARKET_SLUG,
        "question": "Will BTC reach 100k?",
        "active": active,
        "closed": closed,
        "enableOrderBook": True,
        "conditionId": CONDITION_ID,
        "clobTokenIds": ["100", "101"],
        "outcomes": ["Yes", "No"],
    }
