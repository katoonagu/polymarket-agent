"""Unit tests for the read-only strategy registry and orchestrator."""

from __future__ import annotations

from pm.market.models import (
    MarketSnapshotRecord,
    MarketSnapshotTokenSummary,
    RecurringMarketCandidate,
    WatchedMarket,
)
from pm.market.state import MarketStateService
from pm.strategy import (
    StrategyCandidateIntent,
    StrategyRegistryService,
    StrategyService,
    StrategyStateError,
    StrategyStateService,
)
from pm.stream.models import (
    CapturedStreamEvent,
    NormalizedCryptoPriceEvent,
    NormalizedMarketStreamEvent,
)
from pm.stream.state import StreamEventStore
from pm.wallet.models import WalletShadowCandidateIntent, WalletShadowRun, WalletShadowRunParameters
from pm.wallet.state import WalletPipelineStateService

MARKET_SLUG = "btc-15m"
CONDITION_ID = "0x" + ("a" * 64)
TOKEN_ID = "100"


class FakeMarketIntelService:
    """Small injected market service double for strategy tests."""

    def __init__(
        self,
        *,
        current_snapshot: MarketSnapshotRecord | None = None,
        recurring_candidate: RecurringMarketCandidate | None = None,
    ) -> None:
        self._current_snapshot = current_snapshot
        self._recurring_candidate = recurring_candidate

    def _build_snapshot_record(self, **_: object) -> MarketSnapshotRecord:
        assert self._current_snapshot is not None
        return self._current_snapshot

    def recurring_latest(self, query: str, *, interval: str):
        class _Response:
            def __init__(self, query: str, interval: str, item) -> None:
                self.query = query
                self.interval = interval
                self.item = item

        return _Response(query, interval, self._recurring_candidate)


def _build_strategy_service(tmp_path, **kwargs) -> StrategyService:
    registry = StrategyRegistryService(path=tmp_path / "strategies.json")
    state = StrategyStateService(
        intents_path=tmp_path / "strategy-intents.json",
        decisions_path=tmp_path / "strategy-decisions.json",
    )
    wallet_state = WalletPipelineStateService(
        events_path=tmp_path / "wallet-events.json",
        signals_path=tmp_path / "wallet-signals.json",
        shadow_runs_path=tmp_path / "wallet-shadow-runs.json",
    )
    market_state = MarketStateService(
        watchlist_path=tmp_path / "market-watchlist.json",
        snapshots_path=tmp_path / "market-snapshots.json",
    )
    stream_store = StreamEventStore(path=tmp_path / "stream-events.jsonl")
    return StrategyService(
        registry=registry,
        state=state,
        wallet_state=wallet_state,
        market_state=market_state,
        stream_store=stream_store,
        **kwargs,
    )


def test_seeded_registry_loads_deterministically(tmp_path) -> None:
    service = _build_strategy_service(tmp_path)

    listed = service.list_strategies()
    shown = service.show_strategy("wallet_shadow_copy")

    assert listed.total == 3
    assert [item.name for item in listed.items] == [
        "wallet_shadow_copy",
        "market_watch_reversion",
        "recurring_crypto_interval_observe",
    ]
    assert shown.strategy.strategy_type == "wallet_shadow_copy"
    assert (tmp_path / "strategies.json").exists()


def test_validate_strategy_reports_missing_required_inputs(tmp_path) -> None:
    service = _build_strategy_service(tmp_path)

    result = service.validate_strategy("wallet_shadow_copy")

    assert result.valid is False
    assert [item.status for item in result.reason_blocks] == ["pass", "fail", "fail"]


def test_wallet_shadow_copy_evaluate_generates_wait_observe_and_reject(tmp_path) -> None:
    service = _build_strategy_service(tmp_path)
    wallet_state = service._wallet_state  # type: ignore[attr-defined]
    wallet_state.append_shadow_run(
        WalletShadowRun(
            source_wallet="0x1111111111111111111111111111111111111111",
            run_at="2026-03-18T12:00:00Z",
            parameters=WalletShadowRunParameters(
                fixed_size_usdc="25",
                max_drift_pct="5",
                max_spread_pct="5",
                entry_only=True,
                limit=20,
            ),
            candidate_intents=[
                WalletShadowCandidateIntent(
                    source_wallet="0x1111111111111111111111111111111111111111",
                    market_slug=MARKET_SLUG,
                    condition_id=CONDITION_ID,
                    token_id=TOKEN_ID,
                    side="BUY",
                    outcome="Yes",
                    source_price="0.45",
                    current_price="0.46",
                    drift="2.2",
                    spread="0.02",
                    spread_pct="4.34",
                    simulated_size_usdc="25",
                    decision="WOULD_COPY",
                    skip_reason=None,
                    classification="new_entry",
                    transaction_hash="0xhash1",
                    timestamp=1710753600,
                    dedupe_key="dedupe-1",
                ),
                WalletShadowCandidateIntent(
                    source_wallet="0x1111111111111111111111111111111111111111",
                    market_slug=MARKET_SLUG,
                    condition_id=CONDITION_ID,
                    token_id=TOKEN_ID,
                    side="BUY",
                    outcome="Yes",
                    source_price="0.45",
                    current_price=None,
                    drift=None,
                    spread="0.02",
                    spread_pct=None,
                    simulated_size_usdc="25",
                    decision="WOULD_COPY",
                    skip_reason=None,
                    classification="new_entry",
                    transaction_hash="0xhash2",
                    timestamp=None,
                    dedupe_key="dedupe-2",
                ),
                WalletShadowCandidateIntent(
                    source_wallet="0x1111111111111111111111111111111111111111",
                    market_slug=MARKET_SLUG,
                    condition_id=CONDITION_ID,
                    token_id=TOKEN_ID,
                    side="BUY",
                    outcome="Yes",
                    source_price="0.45",
                    current_price="0.46",
                    drift="2.2",
                    spread="0.02",
                    spread_pct="4.34",
                    simulated_size_usdc="25",
                    decision="SKIP",
                    skip_reason="spread_threshold",
                    classification="new_entry",
                    transaction_hash="0xhash3",
                    timestamp=1710753601,
                    dedupe_key="dedupe-3",
                ),
            ],
        )
    )

    result = service.evaluate_strategy("wallet_shadow_copy", limit=3)

    assert result.total == 3
    assert [item.decision for item in result.items] == ["WAIT", "OBSERVE", "REJECT"]
    assert len(service.list_intents(limit=10).items) == 3


def test_market_watch_reversion_evaluate_waits_on_large_drift_and_spread(tmp_path) -> None:
    baseline = MarketSnapshotRecord(
        snapshot_at="2026-03-18T12:00:00Z",
        market_slug=MARKET_SLUG,
        event_slug="bitcoin-event",
        question="Bitcoin 15m up?",
        condition_id=CONDITION_ID,
        token_ids=[TOKEN_ID],
        outcomes=["Yes"],
        active=True,
        closed=False,
        tokens=[
            MarketSnapshotTokenSummary(
                token_id=TOKEN_ID,
                outcome="Yes",
                midpoint="0.40",
                spread="0.01",
            )
        ],
    )
    current = MarketSnapshotRecord(
        snapshot_at="2026-03-18T12:05:00Z",
        market_slug=MARKET_SLUG,
        event_slug="bitcoin-event",
        question="Bitcoin 15m up?",
        condition_id=CONDITION_ID,
        token_ids=[TOKEN_ID],
        outcomes=["Yes"],
        active=True,
        closed=False,
        tokens=[
            MarketSnapshotTokenSummary(
                token_id=TOKEN_ID,
                outcome="Yes",
                midpoint="0.50",
                spread="0.03",
            )
        ],
    )
    fake_market = FakeMarketIntelService(current_snapshot=current)
    service = _build_strategy_service(tmp_path, market_intel_service=fake_market)
    service._market_state.add_watched_market(  # type: ignore[attr-defined]
        WatchedMarket(
            market_slug=MARKET_SLUG,
            event_slug="bitcoin-event",
            question="Bitcoin 15m up?",
            label="btc",
            tags=["btc"],
            added_at="2026-03-18T11:55:00Z",
        )
    )
    service._market_state.append_snapshot(baseline)  # type: ignore[attr-defined]

    result = service.evaluate_strategy("market_watch_reversion", limit=1)

    assert result.total == 1
    assert result.items[0].decision == "WAIT"
    assert result.items[0].token_id == TOKEN_ID


def test_recurring_strategy_uses_stream_alignment(tmp_path) -> None:
    recurring = RecurringMarketCandidate(
        rank=1,
        match_score=120,
        matched_interval="15m",
        recency_source="endDate",
        market_slug=MARKET_SLUG,
        event_slug="bitcoin-event",
        question="Bitcoin Up or Down - 15 min",
        event_title="Bitcoin 15 minute markets",
        active=True,
        closed=False,
        enable_order_book=True,
        condition_id=CONDITION_ID,
        token_ids=[TOKEN_ID],
        outcomes=["Yes"],
        min_tick=0.01,
        min_order_size=5,
    )
    fake_market = FakeMarketIntelService(recurring_candidate=recurring)
    service = _build_strategy_service(tmp_path, market_intel_service=fake_market)
    service._stream_store.append_events(  # type: ignore[attr-defined]
        [
            CapturedStreamEvent(
                session_id="market-session",
                stream_kind="market",
                source="polymarket_market_ws",
                captured_at="2026-03-18T12:00:00Z",
                event_type="best_bid_ask",
                market_event=NormalizedMarketStreamEvent(
                    event_type="best_bid_ask",
                    token_id=TOKEN_ID,
                    midpoint="0.40",
                ),
            ),
            CapturedStreamEvent(
                session_id="market-session",
                stream_kind="market",
                source="polymarket_market_ws",
                captured_at="2026-03-18T12:01:00Z",
                event_type="best_bid_ask",
                market_event=NormalizedMarketStreamEvent(
                    event_type="best_bid_ask",
                    token_id=TOKEN_ID,
                    midpoint="0.45",
                ),
            ),
            CapturedStreamEvent(
                session_id="crypto-session",
                stream_kind="crypto",
                source="binance",
                captured_at="2026-03-18T12:00:00Z",
                event_type="crypto_price",
                crypto_event=NormalizedCryptoPriceEvent(
                    symbol="BTC",
                    source="binance",
                    value="60000",
                ),
            ),
            CapturedStreamEvent(
                session_id="crypto-session",
                stream_kind="crypto",
                source="binance",
                captured_at="2026-03-18T12:01:00Z",
                event_type="crypto_price",
                crypto_event=NormalizedCryptoPriceEvent(
                    symbol="BTC",
                    source="binance",
                    value="60500",
                ),
            ),
        ]
    )

    result = service.evaluate_strategy("recurring_crypto_interval_observe", limit=10)

    assert result.total == 1
    assert result.items[0].decision == "WAIT"
    assert result.items[0].market_slug == MARKET_SLUG


def test_review_approve_reject_lifecycle_uses_latest_decision(tmp_path) -> None:
    service = _build_strategy_service(tmp_path)
    intent = StrategyCandidateIntent(
        intent_id="intent-review-1",
        strategy_name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        source_kind="wallet_shadow",
        market_slug=MARKET_SLUG,
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        side="BUY",
        outcome="Yes",
        decision="WAIT",
        reason_blocks=[],
        created_at="2026-03-18T12:00:00Z",
        source_refs=[],
    )
    service._state.append_intents([intent])  # type: ignore[attr-defined]

    initial = service.review_intent(intent.intent_id)
    approved = service.approve_intent(intent.intent_id)
    rejected = service.reject_intent(intent.intent_id, reason="operator veto")
    reviewed = service.review_intent(intent.intent_id)

    assert initial.intent.current_decision == "WAIT"
    assert initial.decision_history == []
    assert approved.intent.current_decision == "APPROVE"
    assert approved.intent.latest_decision is not None
    assert approved.intent.latest_decision.decision == "APPROVE"
    assert rejected.intent.current_decision == "REJECT"
    assert rejected.intent.latest_decision is not None
    assert rejected.intent.latest_decision.reason == "operator veto"
    assert [item.decision for item in reviewed.decision_history] == ["APPROVE", "REJECT"]
    assert reviewed.intent.current_decision == "REJECT"


def test_invalid_strategy_state_raises_deterministic_error(tmp_path) -> None:
    broken_intents_path = tmp_path / "strategy-intents.json"
    broken_intents_path.write_text('{"version": "bad"}\n', encoding="utf-8")
    service = _build_strategy_service(tmp_path)

    try:
        service.list_intents(limit=5)
    except StrategyStateError as exc:
        assert "Strategy state" in str(exc)
    else:
        raise AssertionError("Expected StrategyStateError for invalid strategy state.")
