"""Unit tests for the BTC15m research strategy service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pm.binance import (
    BinanceBookTicker,
    BinanceDepthLevel,
    BinanceDepthSnapshot,
    BinanceKline,
    BinanceLiquiditySnapshot,
)
from pm.market.gamma import GammaSearchCandidate
from pm.market.models import (
    NormalizedBook,
    NormalizedBookLevel,
    NormalizedMarket,
    NormalizedMidpointQuote,
    NormalizedSpreadQuote,
    RecurringMarketCandidate,
)
from pm.strategy import (
    BOUNDARY_DECISIONS_FILENAME,
    BOUNDARY_OBSERVATIONS_FILENAME,
    CAMPAIGN_RUNS_FILENAME,
    LIQUIDITY_SAMPLES_FILENAME,
    PAPER_RUNS_FILENAME,
    REPLAYS_FILENAME,
    WINDOWS_FILENAME,
    Btc15mBoundaryDecisionRecord,
    Btc15mLiquiditySampleRecord,
    Btc15mPaperRunRecord,
    Btc15mPolymarketLiquidityLevel,
    Btc15mStateError,
    Btc15mStateService,
    Btc15mStrategyService,
    Btc15mWindowRecord,
)
from pm.stream.models import (
    BoundedStreamSession,
    CapturedStreamEvent,
    CryptoStreamResponse,
    CryptoStreamSummary,
    NormalizedCryptoPriceEvent,
    NormalizedMarketStreamEvent,
)
from pm.stream.runner import BoundedRunResult

COND_1 = "0x" + ("a" * 64)
COND_2 = "0x" + ("b" * 64)
TOKEN_UP = "100"
TOKEN_DOWN = "101"


class _RecurringResponse:
    def __init__(self, item: RecurringMarketCandidate | None) -> None:
        self.item = item
        self.query = "btc"
        self.interval = "15m"


class FakeMarketIntelService:
    def __init__(self, candidate: RecurringMarketCandidate) -> None:
        self._candidate = candidate

    def recurring_latest(self, query: str, *, interval: str) -> _RecurringResponse:
        _ = query
        _ = interval
        return _RecurringResponse(self._candidate)


class FakeGammaClient:
    candidate: GammaSearchCandidate | None = None
    market: NormalizedMarket | None = None

    def __init__(self, *args, **kwargs) -> None:
        _ = args
        _ = kwargs

    def __enter__(self) -> FakeGammaClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type
        _ = exc
        _ = tb

    def search_market_candidates(self, query: str, limit: int) -> list[GammaSearchCandidate]:
        _ = query
        _ = limit
        assert self.candidate is not None
        return [self.candidate]

    def get_market_by_slug(self, slug: str) -> NormalizedMarket:
        _ = slug
        assert self.market is not None
        return self.market


class FakeClobClient:
    def __enter__(self) -> FakeClobClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type
        _ = exc
        _ = tb

    def get_book(self, token_id: str) -> NormalizedBook:
        return NormalizedBook(
            token_id=token_id,
            bids=[NormalizedBookLevel(price="0.08", size="300")],
            asks=[
                NormalizedBookLevel(price="0.10", size="200"),
                NormalizedBookLevel(price="0.20", size="100"),
                NormalizedBookLevel(price="0.30", size="80"),
            ],
        )

    def get_midpoint(self, token_id: str) -> NormalizedMidpointQuote:
        return NormalizedMidpointQuote(token_id=token_id, midpoint="0.12")

    def get_spread(self, token_id: str) -> NormalizedSpreadQuote:
        return NormalizedSpreadQuote(token_id=token_id, spread="0.02")


class FakeMarketClient:
    def __init__(self, events: list[CapturedStreamEvent]) -> None:
        self._events = events

    async def stream_tokens(
        self,
        token_ids: list[str],
        *,
        seconds: int,
        max_events: int | None = None,
    ) -> BoundedRunResult:
        _ = token_ids
        _ = seconds
        _ = max_events
        return BoundedRunResult(
            session=_stream_session("market-session", "market", "polymarket_market_ws"),
            events=self._events,
            errors=[],
        )


class FakeCryptoClient:
    def __init__(
        self,
        *,
        chainlink_events: list[CapturedStreamEvent],
        binance_events: list[CapturedStreamEvent],
    ) -> None:
        self._chainlink_events = chainlink_events
        self._binance_events = binance_events

    async def stream_symbol(
        self,
        symbol: str,
        *,
        source: str,
        seconds: int,
        max_events: int | None = None,
    ) -> CryptoStreamResponse:
        _ = symbol
        _ = seconds
        _ = max_events
        events = self._chainlink_events if source == "chainlink" else self._binance_events
        return CryptoStreamResponse(
            session=_stream_session(f"{source}-session", "crypto", source),
            summary=CryptoStreamSummary(
                symbol="BTC",
                source=source,
                event_count=len(events),
                latest_value=events[-1].crypto_event.value if events else None,
            ),
            events=events,
            errors=[],
        )


class FakeBinanceService:
    def sample_liquidity(
        self,
        symbol: str = "BTCUSDT",
        *,
        depth_limit: int = 20,
        kline_interval: str = "1m",
        kline_limit: int = 4,
    ) -> BinanceLiquiditySnapshot:
        _ = symbol
        _ = depth_limit
        _ = kline_interval
        _ = kline_limit
        return BinanceLiquiditySnapshot(
            symbol="BTCUSDT",
            sampled_at="2026-03-19T00:05:00Z",
            book_ticker=BinanceBookTicker(
                symbol="BTCUSDT",
                bid_price="101",
                bid_quantity="5",
                ask_price="101.01",
                ask_quantity="6",
                midpoint="101.005",
                spread="0.01",
            ),
            depth=BinanceDepthSnapshot(
                symbol="BTCUSDT",
                last_update_id=1,
                bids=[BinanceDepthLevel(price="101", quantity="20")],
                asks=[BinanceDepthLevel(price="101.01", quantity="22")],
                best_bid="101",
                best_ask="101.01",
                midpoint="101.005",
                spread="0.01",
            ),
            klines=[
                BinanceKline(
                    symbol="BTCUSDT",
                    interval="1m",
                    open_time=1,
                    close_time=2,
                    open_price="100",
                    high_price="101",
                    low_price="99",
                    close_price="101",
                    volume="10",
                    quote_volume="1000",
                    trade_count=10,
                    is_closed=True,
                )
            ]
            * 4,
            realized_vol_1m_bps="100",
            realized_vol_3m_bps="150",
            near_touch_bid_depth="20",
            near_touch_ask_depth="22",
            errors=[],
        )


async def _noop_async_sleep(seconds: float) -> None:
    _ = seconds


class _Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)

    async def async_sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def _service(tmp_path, *, now: datetime | None = None) -> Btc15mStrategyService:
    candidate = _candidate(COND_1, "btc-15m-up-down-1")
    FakeGammaClient.candidate = _search_candidate(candidate)
    FakeGammaClient.market = _normalized_market(candidate)
    clock = _Clock(now) if now is not None else None
    return Btc15mStrategyService(
        state=Btc15mStateService(
            boundary_observations_path=tmp_path / BOUNDARY_OBSERVATIONS_FILENAME,
            boundary_decisions_path=tmp_path / BOUNDARY_DECISIONS_FILENAME,
            windows_path=tmp_path / WINDOWS_FILENAME,
            replays_path=tmp_path / REPLAYS_FILENAME,
            paper_runs_path=tmp_path / PAPER_RUNS_FILENAME,
            liquidity_samples_path=tmp_path / LIQUIDITY_SAMPLES_FILENAME,
            campaign_runs_path=tmp_path / CAMPAIGN_RUNS_FILENAME,
        ),
        market_intel_service=FakeMarketIntelService(candidate),
        market_client=FakeMarketClient(_market_events()),
        crypto_client=FakeCryptoClient(
            chainlink_events=_chainlink_events(),
            binance_events=_binance_events(),
        ),
        binance_service=FakeBinanceService(),
        gamma_client_cls=FakeGammaClient,
        clob_client_cls=FakeClobClient,
        now=clock.now if clock is not None else None,
        sleep=clock.sleep if clock is not None else None,
        async_sleep=clock.async_sleep if clock is not None else _noop_async_sleep,
    )


def test_btc15m_state_missing_and_invalid(tmp_path) -> None:
    state = Btc15mStateService(
        boundary_observations_path=tmp_path / BOUNDARY_OBSERVATIONS_FILENAME,
        boundary_decisions_path=tmp_path / BOUNDARY_DECISIONS_FILENAME,
        windows_path=tmp_path / WINDOWS_FILENAME,
        replays_path=tmp_path / REPLAYS_FILENAME,
        paper_runs_path=tmp_path / PAPER_RUNS_FILENAME,
    )

    assert state.list_windows() == []
    (tmp_path / WINDOWS_FILENAME).write_text("{bad", encoding="utf-8")

    with pytest.raises(Btc15mStateError):
        state.list_windows()


def test_record_start_persists_complete_window_and_boundaries(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))

    result = service.record_start(seconds=60)

    assert result.total == 1
    assert result.items[0].status == "complete"
    assert result.items[0].boundary_status == "complete"
    assert result.items[0].decision == "UP"
    assert len(service._state.list_boundary_observations()) == 4  # type: ignore[attr-defined]
    assert service._state.list_boundary_decisions()[0].start_price_proxy_v1 == "100"  # type: ignore[attr-defined]
    assert len(service._state.list_liquidity_samples()) >= 2  # type: ignore[attr-defined]


def test_liquidity_sample_persists_operator_samples(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))

    result = service.liquidity_sample(seconds=10)

    assert result.total == 2
    assert result.items[0].sample_kind == "operator"
    assert result.items[0].binance.realized_vol_1m_bps == "100"
    assert len(service._state.list_liquidity_samples()) == 2  # type: ignore[attr-defined]


def test_paper_run_uses_oldest_completed_unevaluated_window(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))
    state = service._state  # type: ignore[attr-defined]
    state.append_boundary_decision(
        Btc15mBoundaryDecisionRecord(
            window_id="btc15m:" + COND_1,
            condition_id=COND_1,
            market_slug="btc-15m-up-down-1",
            created_at="2026-03-19T00:16:00Z",
            status="complete",
            start_price_proxy_v1="100",
            end_price_proxy_v1="102",
        )
    )
    state.append_windows(
        [
            _window_record(COND_1, "btc-15m-up-down-1", "2026-03-19T00:00:00Z"),
            _window_record(COND_2, "btc-15m-up-down-2", "2026-03-19T00:15:00Z"),
        ]
    )

    first = service.paper_run(limit=1)
    second = service.paper_run(limit=1)

    assert first.run.total_evaluated == 1
    assert first.run.items[0].window_id == "btc15m:" + COND_1
    assert first.run.items[0].filled_rung_count == 3
    assert second.run.total_evaluated == 1
    assert second.run.items[0].window_id == "btc15m:" + COND_2


def test_replay_filters_range_and_report_aggregates(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-20T00:00:00Z"))
    state = service._state  # type: ignore[attr-defined]
    state.append_windows(
        [
            _window_record(COND_1, "btc-15m-up-down-1", "2026-03-19T00:00:00Z"),
            _window_record(COND_2, "btc-15m-up-down-2", "2026-03-20T00:15:00Z", decision="SKIP"),
        ]
    )
    state.append_paper_run(
        Btc15mPaperRunRecord(
            run_id="run-1",
            created_at="2026-03-20T00:30:00Z",
            limit=20,
            items=[
                service._evaluate_window(
                    _window_record(COND_1, "btc-15m-up-down-1", "2026-03-19T00:00:00Z")
                ),
                service._evaluate_window(
                    _window_record(
                        COND_2, "btc-15m-up-down-2", "2026-03-20T00:15:00Z", decision="SKIP"
                    )
                ),
            ],
            total_considered=2,
            total_evaluated=2,
            total_skipped=1,
            total_realized_pnl_usdc="241.666665",
        )
    )

    replay = service.replay(from_at="2026-03-20T00:00:00Z", to_at="2026-03-21T00:00:00Z")
    report = service.report()

    assert replay.replay.total == 1
    assert replay.replay.items[0].window_id == "btc15m:" + COND_2
    assert report.summary.recorded_window_count == 2
    assert report.summary.paper_run_count == 1
    assert report.summary.skip_count == 1
    assert report.summary.total_realized_pnl_usdc == "241.6666662"


def test_campaign_run_persists_campaign_and_campaign_report(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))

    result = service.campaign_run(hours="0.3")
    report = service.campaign_report()

    assert result.campaign.total_windows == 1
    assert result.campaign.items[0].source_kind == "campaign"
    assert service._state.list_campaign_runs()[0].run_id == result.campaign.run_id  # type: ignore[attr-defined]
    assert report.summary.campaign_run_count == 1
    assert report.summary.evaluated_window_count == 1


def test_evaluate_window_skips_on_wide_spread_and_thin_liquidity(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))
    record = _window_record(COND_1, "btc-15m-up-down-1", "2026-03-19T00:00:00Z")
    record.liquidity_samples = [
        Btc15mLiquiditySampleRecord(
            sample_id="bad-sample",
            window_id=record.window.window_id,
            condition_id=record.window.condition_id,
            market_slug=record.window.market_slug,
            sample_kind="minute_five",
            sampled_at="2026-03-19T00:05:00Z",
            scheduled_at="2026-03-19T00:05:00Z",
            late_by_seconds=0,
            binance=FakeBinanceService().sample_liquidity(),
            polymarket=[
                Btc15mPolymarketLiquidityLevel(
                    token_id=TOKEN_UP,
                    outcome="Up",
                    best_bid="0.10",
                    best_ask="0.80",
                    midpoint="0.75",
                    spread="0.70",
                    visible_liquidity_030="10",
                    visible_liquidity_020="5",
                    visible_liquidity_010="0",
                )
            ],
            errors=[],
        )
    ]

    evaluation = service._evaluate_window(record)

    assert evaluation.decision == "SKIP"
    assert "wide_polymarket_spread" in evaluation.skip_reasons
    assert "thin_visible_liquidity" in evaluation.skip_reasons


def _candidate(condition_id: str, market_slug: str) -> RecurringMarketCandidate:
    return RecurringMarketCandidate(
        rank=1,
        match_score=120,
        matched_interval="15m",
        recency_source="endDate",
        market_slug=market_slug,
        event_slug="btc-15m-event",
        question="Bitcoin Up or Down - 15 min",
        event_title="Bitcoin 15 minute markets",
        active=True,
        closed=False,
        enable_order_book=True,
        condition_id=condition_id,
        token_ids=[TOKEN_UP, TOKEN_DOWN],
        outcomes=["Up", "Down"],
        min_tick=0.01,
        min_order_size=5,
    )


def _normalized_market(candidate: RecurringMarketCandidate) -> NormalizedMarket:
    return NormalizedMarket(
        market_slug=candidate.market_slug,
        event_slug=candidate.event_slug,
        question=candidate.question,
        event_title=candidate.event_title,
        active=candidate.active,
        closed=candidate.closed,
        enable_order_book=candidate.enable_order_book,
        condition_id=candidate.condition_id,
        token_ids=candidate.token_ids,
        outcomes=candidate.outcomes,
        min_tick=candidate.min_tick,
        min_order_size=candidate.min_order_size,
    )


def _search_candidate(candidate: RecurringMarketCandidate) -> GammaSearchCandidate:
    return GammaSearchCandidate(
        market=_normalized_market(candidate),
        search_index=0,
        start_date="2026-03-19T00:00:00Z",
        end_date="2026-03-19T00:15:00Z",
        resolution_date="2026-03-19T00:15:00Z",
    )


def _stream_session(session_id: str, stream_kind: str, source: str) -> BoundedStreamSession:
    return BoundedStreamSession(
        session_id=session_id,
        stream_kind=stream_kind,
        source=source,
        started_at="2026-03-19T00:00:00Z",
        ended_at="2026-03-19T00:01:00Z",
        duration_seconds=60,
        requested_seconds=60,
        captured_event_count=1,
        reconnect_count=0,
    )


def _chainlink_events() -> list[CapturedStreamEvent]:
    return [
        _crypto_event("chainlink", "2026-03-18T23:59:59Z", 100),
        _crypto_event("chainlink", "2026-03-19T00:00:01Z", 100),
        _crypto_event("chainlink", "2026-03-19T00:05:00Z", 101),
        _crypto_event("chainlink", "2026-03-19T00:14:59Z", 102),
        _crypto_event("chainlink", "2026-03-19T00:15:01Z", 102),
    ]


def _binance_events() -> list[CapturedStreamEvent]:
    return [
        _crypto_event("binance", "2026-03-19T00:04:59Z", 101),
        _crypto_event("binance", "2026-03-19T00:05:00Z", 101),
    ]


def _crypto_event(source: str, observed_at: str, value: int) -> CapturedStreamEvent:
    observed_dt = _dt(observed_at)
    return CapturedStreamEvent(
        session_id=f"{source}-session",
        stream_kind="crypto",
        source=source,
        captured_at=observed_at,
        event_type="crypto_price",
        crypto_event=NormalizedCryptoPriceEvent(
            symbol="BTC",
            source=source,
            timestamp=int(observed_dt.timestamp()),
            value=str(value),
        ),
    )


def _market_events() -> list[CapturedStreamEvent]:
    observed_dt = _dt("2026-03-19T00:06:00Z")
    return [
        CapturedStreamEvent(
            session_id="market-session",
            stream_kind="market",
            source="polymarket_market_ws",
            captured_at="2026-03-19T00:06:00Z",
            event_type="book",
            market_event=NormalizedMarketStreamEvent(
                event_type="book",
                token_id=TOKEN_UP,
                timestamp=int(observed_dt.timestamp()),
                best_bid="0.08",
                best_ask="0.10",
                midpoint="0.09",
                spread="0.02",
                bids=[NormalizedBookLevel(price="0.08", size="300")],
                asks=[
                    NormalizedBookLevel(price="0.10", size="200"),
                    NormalizedBookLevel(price="0.20", size="100"),
                    NormalizedBookLevel(price="0.30", size="80"),
                ],
            ),
        )
    ]


def _window_record(
    condition_id: str,
    market_slug: str,
    window_start_at: str,
    *,
    decision: str = "UP",
) -> Btc15mWindowRecord:
    from pm.strategy import Btc15mReasonBlock, Btc15mWindowIdentity

    start_dt = _dt(window_start_at)
    end_dt = start_dt + timedelta(minutes=15)
    return Btc15mWindowRecord(
        window=Btc15mWindowIdentity(
            strategy_name="btc_15m_chainlink_directional_ladder_v1",
            window_id="btc15m:" + condition_id,
            condition_id=condition_id,
            market_slug=market_slug,
            token_ids=[TOKEN_UP, TOKEN_DOWN],
            outcomes=["Up", "Down"],
            window_start_at=window_start_at,
            window_end_at=end_dt.isoformat().replace("+00:00", "Z"),
            market_open_time=window_start_at,
        ),
        recorded_at=end_dt.isoformat().replace("+00:00", "Z"),
        recorder_session_id="record-session",
        status="complete",
        boundary_status="complete",
        start_price_proxy_v1="100",
        end_price_proxy_v1="102" if decision != "SKIP" else "100",
        decision=decision,
        decision_at=(start_dt + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        resolution_result="UP" if decision != "SKIP" else "UNRESOLVED_TIE",
        skip_reasons=["mixed_direction_at_minute_five"] if decision == "SKIP" else [],
        reason_blocks=[
            Btc15mReasonBlock(
                section="direction_lock",
                status="pass" if decision != "SKIP" else "fail",
                message="locked" if decision != "SKIP" else "skipped",
            )
        ],
        market_samples=_market_events_to_samples(),
        liquidity_samples=[_liquidity_sample("btc15m:" + condition_id, market_slug)],
    )


def _market_events_to_samples():
    from pm.strategy import Btc15mMarketSample

    return [
        Btc15mMarketSample(
            token_id=TOKEN_UP,
            outcome="Up",
            event_type="book",
            source="polymarket_market_ws",
            captured_at="2026-03-19T00:06:00Z",
            observed_at="2026-03-19T00:06:00Z",
            best_bid="0.08",
            best_ask="0.10",
            midpoint="0.09",
            spread="0.02",
            bids=[NormalizedBookLevel(price="0.08", size="300")],
            asks=[
                NormalizedBookLevel(price="0.10", size="200"),
                NormalizedBookLevel(price="0.20", size="100"),
                NormalizedBookLevel(price="0.30", size="80"),
            ],
        )
    ]


def _liquidity_sample(window_id: str, market_slug: str) -> Btc15mLiquiditySampleRecord:
    return Btc15mLiquiditySampleRecord(
        sample_id="sample-1",
        window_id=window_id,
        condition_id=window_id.replace("btc15m:", ""),
        market_slug=market_slug,
        sample_kind="minute_five",
        sampled_at="2026-03-19T00:05:00Z",
        scheduled_at="2026-03-19T00:05:00Z",
        late_by_seconds=0,
        binance=FakeBinanceService().sample_liquidity(),
        polymarket=[
            Btc15mPolymarketLiquidityLevel(
                token_id=TOKEN_UP,
                outcome="Up",
                best_bid="0.08",
                best_ask="0.10",
                midpoint="0.09",
                spread="0.02",
                visible_liquidity_030="380",
                visible_liquidity_020="300",
                visible_liquidity_010="200",
            ),
            Btc15mPolymarketLiquidityLevel(
                token_id=TOKEN_DOWN,
                outcome="Down",
                best_bid="0.08",
                best_ask="0.72",
                midpoint="0.40",
                spread="0.64",
                visible_liquidity_030="10",
                visible_liquidity_020="5",
                visible_liquidity_010="0",
            ),
        ],
        errors=[],
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
