"""Unit tests for the BTC15m research strategy service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
    AUTO_ROLL_RUNS_FILENAME,
    BOUNDARY_DECISIONS_FILENAME,
    BOUNDARY_OBSERVATIONS_FILENAME,
    CAMPAIGN_RUNS_FILENAME,
    DASHBOARD_SNAPSHOTS_FILENAME,
    LIQUIDITY_SAMPLES_FILENAME,
    PAPER_RUNS_FILENAME,
    REPLAYS_FILENAME,
    TERMINAL_SESSIONS_FILENAME,
    WINDOWS_FILENAME,
    Btc15mBoundaryDecisionRecord,
    Btc15mLiquiditySampleRecord,
    Btc15mPaperRunRecord,
    Btc15mPolymarketLiquidityLevel,
    Btc15mRunMode,
    Btc15mStateError,
    Btc15mStateService,
    Btc15mStrategyService,
    Btc15mTerminalSessionRecord,
    Btc15mTerminalState,
    Btc15mWindowRecord,
)
from pm.strategy.btc15m_page import Btc15mPageParityData
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
    def __init__(self, candidate: RecurringMarketCandidate | None) -> None:
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
        if self.candidate is None:
            return []
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


class FakeOrderLifecycle:
    def __init__(self) -> None:
        self.posts: list[dict[str, str]] = []
        self.cancels: list[dict[str, str | None]] = []
        self.order_statuses: dict[str, dict[str, str | None]] = {}
        self.next_order_id = 1

    def post(
        self,
        *,
        market_ref: str,
        outcome: str,
        side: str,
        price: str,
        size: str,
        live: bool = False,
        confirm: bool = False,
        **_: object,
    ):
        self.posts.append(
            {
                "market_ref": market_ref,
                "outcome": outcome,
                "side": side,
                "price": price,
                "size": size,
                "mode": "live" if live else "paper",
                "confirm": str(confirm),
            }
        )
        order_id = f"order-{self.next_order_id}"
        self.next_order_id += 1
        self.order_statuses[order_id] = {
            "order_id": order_id,
            "status": "LIVE",
            "remaining_size": size,
            "created_at": "2026-03-20T10:35:00Z",
        }
        return type(
            "FakePostOrderResponse",
            (),
            {
                "decision": "POSTED",
                "live_response": {
                    "order": {"order_id": order_id},
                    "post_result": {"orderID": order_id},
                },
            },
        )()

    def order_get(self, *, order_id: str):
        payload = self.order_statuses[order_id]
        order = type("FakeOrder", (), payload)()
        return type("FakeOrderGetResponse", (), {"order": order})()

    def cancel_market(
        self,
        *,
        market: str,
        token_id: str | None = None,
        live: bool = False,
        confirm: bool = False,
    ):
        self.cancels.append(
            {
                "market": market,
                "token_id": token_id,
                "mode": "live" if live else "paper",
                "confirm": str(confirm),
            }
        )
        for payload in self.order_statuses.values():
            payload["status"] = "CANCELLED"
            payload["remaining_size"] = "0"
        return type("FakeCancelResponse", (), {"decision": "CANCELLED"})()


class FakePageParityService:
    def __init__(self, data: Btc15mPageParityData | None = None) -> None:
        self._data = data or Btc15mPageParityData()

    def fetch(self, market: NormalizedMarket) -> Btc15mPageParityData:
        _ = market
        return self._data

    def fetch_terminal_current(
        self,
        market: NormalizedMarket,
        *,
        previous: Btc15mPageParityData | None = None,
    ) -> Btc15mPageParityData:
        _ = previous
        return self.fetch(market)


class FakeTerminalPageParityService(FakePageParityService):
    def __init__(self, responses: list[Btc15mPageParityData]) -> None:
        super().__init__(responses[0] if responses else None)
        self._responses = list(responses)

    def fetch_terminal_current(
        self,
        market: NormalizedMarket,
        *,
        previous: Btc15mPageParityData | None = None,
    ) -> Btc15mPageParityData:
        _ = market
        if self._responses:
            response = self._responses.pop(0)
            if (
                previous is not None
                and previous.field_sources.get("price_to_beat") == "page_exact"
                and previous.field_sources.get("current_live_btc_price") == "page_exact"
                and previous.field_sources.get("up_price") == "page_exact"
                and previous.field_sources.get("down_price") == "page_exact"
                and previous.field_sources.get("volume") == "page_exact"
                and not response.has_fields()
            ):
                return previous.stale_copy(*response.notes)
            return response
        return self._data


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


def _service(
    tmp_path,
    *,
    now: datetime | None = None,
    candidate: RecurringMarketCandidate | None = None,
    search_candidate: GammaSearchCandidate | None = None,
    chainlink_events: list[CapturedStreamEvent] | None = None,
    binance_events: list[CapturedStreamEvent] | None = None,
    market_events: list[CapturedStreamEvent] | None = None,
    market_intel_candidate: RecurringMarketCandidate | None | object = ...,
    order_lifecycle: FakeOrderLifecycle | None = None,
    page_parity_data: Btc15mPageParityData | None = None,
    page_parity_service: FakePageParityService | None = None,
) -> Btc15mStrategyService:
    candidate = candidate or _candidate(COND_1, "btc-15m-up-down-1")
    FakeGammaClient.candidate = search_candidate or _search_candidate(candidate)
    FakeGammaClient.market = _normalized_market(candidate)
    clock = _Clock(now) if now is not None else None
    if market_intel_candidate is ...:
        resolved_market_intel_candidate = candidate
    else:
        resolved_market_intel_candidate = market_intel_candidate
    return Btc15mStrategyService(
        state=Btc15mStateService(
            boundary_observations_path=tmp_path / BOUNDARY_OBSERVATIONS_FILENAME,
            boundary_decisions_path=tmp_path / BOUNDARY_DECISIONS_FILENAME,
            windows_path=tmp_path / WINDOWS_FILENAME,
            replays_path=tmp_path / REPLAYS_FILENAME,
            paper_runs_path=tmp_path / PAPER_RUNS_FILENAME,
            liquidity_samples_path=tmp_path / LIQUIDITY_SAMPLES_FILENAME,
            campaign_runs_path=tmp_path / CAMPAIGN_RUNS_FILENAME,
            dashboard_snapshots_path=tmp_path / DASHBOARD_SNAPSHOTS_FILENAME,
            auto_roll_runs_path=tmp_path / AUTO_ROLL_RUNS_FILENAME,
            terminal_sessions_path=tmp_path / TERMINAL_SESSIONS_FILENAME,
        ),
        market_intel_service=FakeMarketIntelService(resolved_market_intel_candidate),
        market_client=FakeMarketClient(market_events or _market_events()),
        crypto_client=FakeCryptoClient(
            chainlink_events=chainlink_events or _chainlink_events(),
            binance_events=binance_events or _binance_events(),
        ),
        binance_service=FakeBinanceService(),
        page_parity_service=page_parity_service or FakePageParityService(page_parity_data),
        order_lifecycle=order_lifecycle or FakeOrderLifecycle(),
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
    assert result.items[0].timing_controls.post_start_grace_window_seconds == 60
    assert len(service._state.list_boundary_observations()) == 4  # type: ignore[attr-defined]
    assert service._state.list_boundary_decisions()[0].start_price_proxy_v1 == "100"  # type: ignore[attr-defined]
    assert (
        service._state.list_boundary_decisions()[0].timing_controls.post_end_grace_window_seconds
        == 60
    )  # type: ignore[attr-defined]
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


def test_paper_run_slug_records_and_evaluates_target_window(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))

    result = service.paper_run(slug="btc-15m-up-down-1", mode="paper")

    assert result.run.mode == "paper"
    assert result.run.target_slug == "btc-15m-up-down-1"
    assert result.run.selection_source == "slug"
    assert result.run.total_evaluated == 1
    assert result.run.items[0].market_slug == "btc-15m-up-down-1"


def test_paper_run_live_mode_is_rejected(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))

    with pytest.raises(Exception, match="paper-first step"):
        service.paper_run(slug="btc-15m-up-down-1", mode="live")


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


def test_campaign_slug_path_targets_single_window(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-19T00:00:00Z"))

    next_window = service.campaign_next_window(slug="btc-15m-up-down-1", mode="paper")
    result = service.campaign_run(hours="0.3", slug="btc-15m-up-down-1", mode="paper")

    assert next_window.mode == "paper"
    assert next_window.target_slug == "btc-15m-up-down-1"
    assert next_window.selection_source == "slug"
    assert result.campaign.target_slug == "btc-15m-up-down-1"
    assert result.campaign.selection_source == "slug"
    assert result.campaign.stop_reason == "completed_target_window"
    assert result.campaign.total_windows == 1


def test_slug_timing_overrides_conflicting_gamma_timing(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    search_candidate = GammaSearchCandidate(
        market=_normalized_market(candidate),
        search_index=0,
        start_date="2026-03-20T10:00:00Z",
        end_date="2026-03-20T10:15:00Z",
        resolution_date="2026-03-20T10:15:00Z",
    )
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:31:00Z"),
        candidate=candidate,
        search_candidate=search_candidate,
    )

    resolved = service._resolve_window_by_slug(candidate.market_slug)  # type: ignore[attr-defined]

    assert resolved.window.window_start_at == "2026-03-20T10:30:00Z"
    assert resolved.window.window_end_at == "2026-03-20T10:45:00Z"
    assert resolved.window.slug_start_unix == 1774002600
    assert resolved.window.timing_source == "slug_timestamp"
    assert resolved.window.timing_notes


def test_resolve_current_uses_exact_slug_bucket(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:36:00Z"),
        candidate=candidate,
    )

    result = service.resolve_current()

    assert result.window is not None
    assert result.window.market_slug == candidate.market_slug
    assert result.status == "live"
    assert result.timing_source == "slug_timestamp"
    assert result.seconds_to_end == 540


def test_resolve_current_no_candidate_includes_hint(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-20T10:36:00Z"))
    FakeGammaClient.market = None
    FakeGammaClient.candidate = None

    with pytest.raises(Exception, match="No live BTC 15m current-window candidate was found."):
        service.resolve_current()


def test_boundary_capture_uses_first_tick_at_or_after_t0(tmp_path) -> None:
    chainlink_events = [
        _crypto_event("chainlink", "2026-03-18T23:59:59Z", 99),
        _crypto_event("chainlink", "2026-03-19T00:00:00Z", 100),
        _crypto_event("chainlink", "2026-03-19T00:05:00Z", 101),
        _crypto_event("chainlink", "2026-03-19T00:14:59Z", 102),
        _crypto_event("chainlink", "2026-03-19T00:15:00Z", 103),
    ]
    service = _service(
        tmp_path,
        now=_dt("2026-03-19T00:00:00Z"),
        chainlink_events=chainlink_events,
    )

    result = service.record_start(seconds=60)

    assert result.items[0].start_price_proxy_v1 == "100"
    assert result.items[0].end_price_proxy_v1 == "103"


def test_missing_post_start_tick_within_grace_yields_partial_skip(tmp_path) -> None:
    chainlink_events = [
        _crypto_event("chainlink", "2026-03-18T23:59:59Z", 100),
        _crypto_event("chainlink", "2026-03-19T00:05:00Z", 101),
        _crypto_event("chainlink", "2026-03-19T00:15:01Z", 102),
    ]
    service = _service(
        tmp_path,
        now=_dt("2026-03-19T00:00:00Z"),
        chainlink_events=chainlink_events,
    )

    result = service.paper_run(slug="btc-15m-up-down-1", mode="paper")

    assert result.run.total_evaluated == 1
    assert result.run.items[0].decision == "SKIP"
    assert "missing_start_proxy" in result.run.items[0].skip_reasons
    latest_window = service._state.list_windows()[-1]  # type: ignore[attr-defined]
    assert latest_window.boundary_status == "partial"
    assert latest_window.start_price_proxy_v1 is None


def test_dashboard_current_persists_snapshot(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:36:00Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:36:00Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:36:00Z", 101)],
    )

    result = service.dashboard_current(seconds=1)

    assert result.total_snapshots == 1
    assert result.latest_snapshot is not None
    assert result.latest_snapshot.market_slug == candidate.market_slug
    assert len(service._state.list_dashboard_snapshots()) == 1  # type: ignore[attr-defined]


def test_terminal_snapshot_only_returns_terminal_view(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:39:00Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:39:00Z", 101)],
    )
    service._state.append_boundary_decision(  # type: ignore[attr-defined]
        Btc15mBoundaryDecisionRecord(
            window_id="btc15m:" + COND_1,
            condition_id=COND_1,
            market_slug=candidate.market_slug,
            created_at="2026-03-20T10:30:01Z",
            status="partial",
            post_start=_price_tick("chainlink", "2026-03-20T10:30:00Z", "100"),
            timing_source="slug_timestamp",
            start_price_proxy_v1="100",
        )
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.total_snapshots == 1
    assert result.latest_snapshot is not None
    assert result.latest_snapshot.view_kind == "terminal"
    assert result.latest_snapshot.start_price_proxy_v1 == "100"
    assert result.latest_snapshot.observe_only is False
    assert result.latest_snapshot.attach_mode == "current"
    assert result.latest_snapshot.window_status != Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW


def test_terminal_snapshot_late_attach_defaults_to_observe_only(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:31:05Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:31:05Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:31:05Z", 101)],
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.window_status == Btc15mTerminalState.OBSERVE_ONLY
    assert result.latest_snapshot.observe_only is True
    assert "missing_start_proxy" in result.latest_snapshot.manipulation_flags


def _legacy_terminal_snapshot_late_attach_page_fallback_start_anchor(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:31:05Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:31:05Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:31:05Z", 101)],
        page_parity_data=Btc15mPageParityData(
            event_url="https://polymarket.com/event/btc-15m-event",
            current_window_label="BTC 15m active",
            price_to_beat="101234.5",
            current_live_btc_price="101240.1",
            up_price="0.33",
            down_price="0.67",
            volume="120K",
            field_sources={
                "price_to_beat": "page_exact",
                "current_live_btc_price": "page_exact",
                "up_price": "page_exact",
                "down_price": "page_exact",
                "volume": "page_exact",
            },
            matched_market_slug="btc-updown-15m-1774002600",
            observed_at="2026-03-20T10:31:05Z",
        ),
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.observe_only is False
    assert result.latest_snapshot.paper_start_proxy_v1 == "101234.5"
    assert result.latest_snapshot.paper_start_proxy_source == "late_attach_page_fallback"
    assert result.latest_snapshot.start_price_proxy_v1 is None
    assert result.latest_snapshot.window_status == Btc15mTerminalState.DIRECTION_LOCK_PENDING


def _legacy_terminal_snapshot_page_parity_fallback_when_needed(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        chainlink_events=[],
        binance_events=[],
        page_parity_data=Btc15mPageParityData(
            event_url="https://polymarket.com/event/btc-15m-event",
            current_window_label="BTC 15m active",
            price_to_beat="101234.5",
            current_live_btc_price="101240.1",
            up_price="0.33",
            down_price="0.67",
            volume="120K",
            field_sources={
                "price_to_beat": "page_exact",
                "current_live_btc_price": "page_exact",
                "up_price": "page_exact",
                "down_price": "page_exact",
                "volume": "page_exact",
            },
            matched_market_slug="btc-updown-15m-1774002600",
        ),
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.display is not None
    assert result.latest_snapshot.page_parity_source == "page_exact"
    assert result.latest_snapshot.current_window_label == "BTC 15m active"
    assert result.latest_snapshot.current_live_btc_price == "101240.1"
    assert result.latest_snapshot.up_price == "0.33"
    assert result.latest_snapshot.down_price == "0.67"
    assert result.latest_snapshot.price_to_beat == "101234.5"
    assert result.latest_snapshot.paper_start_proxy_v1 == "101234.5"
    assert result.latest_snapshot.paper_start_proxy_source == "late_attach_page_fallback"
    assert result.latest_snapshot.start_price_proxy_v1 != result.latest_snapshot.price_to_beat
    assert result.latest_snapshot.display.display_price_to_beat == "101234.5"
    assert result.latest_snapshot.display.display_volume == "120K"
    assert result.latest_snapshot.display.display_source == "page_exact"
    assert result.latest_snapshot.display.display_stale is False


def test_terminal_snapshot_marks_non_exact_page_truth_unavailable(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        chainlink_events=[],
        binance_events=[],
        page_parity_data=Btc15mPageParityData(
            event_url="https://polymarket.com/event/btc-15m-event",
            price_to_beat="101234.5",
            up_price="0.33",
            down_price="0.67",
            field_sources={
                "price_to_beat": "page_estimated",
                "up_price": "page_estimated",
                "down_price": "page_estimated",
            },
        ),
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.display is not None
    assert result.latest_snapshot.display.display_source == "page_unavailable"
    assert result.latest_snapshot.display.display_current_btc is None
    assert result.latest_snapshot.display.display_price_to_beat is None


def test_terminal_snapshot_keeps_last_valid_page_truth_when_browser_stalls(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        page_parity_service=FakeTerminalPageParityService(
            [
                Btc15mPageParityData(
                    event_url="https://polymarket.com/event/btc-15m-event",
                    current_window_label="BTC 15m active",
                    price_to_beat="101234.5",
                    current_live_btc_price="101240.1",
                    up_price="0.33",
                    down_price="0.67",
                    volume="120K",
                    field_sources={
                        "price_to_beat": "page_exact",
                        "current_live_btc_price": "page_exact",
                        "up_price": "page_exact",
                        "down_price": "page_exact",
                        "volume": "page_exact",
                    },
                    matched_market_slug="btc-updown-15m-1774002600",
                    observed_at="2026-03-20T10:39:00Z",
                ),
                Btc15mPageParityData(notes=["browser_adapter_unavailable"]),
            ]
        ),
    )
    current = service._resolve_current_window()  # type: ignore[attr-defined]
    runtime = service._create_terminal_runtime(  # type: ignore[attr-defined]
        session_id="terminal-stale-parity-test",
        resolved=current.resolved,
        mode=Btc15mRunMode.PAPER,
        started_at_dt=_dt("2026-03-20T10:39:00Z"),
        attach_mode="current",
    )
    first_snapshot = service._advance_terminal_runtime(runtime)  # type: ignore[attr-defined]
    service._sleep(6)  # type: ignore[attr-defined]
    result_snapshot = service._advance_terminal_runtime(runtime)  # type: ignore[attr-defined]

    assert first_snapshot.display is not None
    assert result_snapshot.display is not None
    assert result_snapshot.display.display_source == "page_unavailable"
    assert result_snapshot.display.display_stale is True
    assert result_snapshot.display.display_price_to_beat == "101234.5"
    assert result_snapshot.display.display_current_btc == "101240.1"
    assert result_snapshot.display.display_up_price == "0.33"
    assert result_snapshot.display.display_down_price == "0.67"
    assert "stale_last_valid_snapshot" in result_snapshot.display.display_notes


def test_terminal_wait_next_snapshot_stays_waiting_until_next_capture_opens(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:31:05Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:31:05Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:31:05Z", 101)],
    )

    result = service.terminal_wait_next(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.attach_mode == "wait_next"
    assert result.latest_snapshot.window_status == Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW


def test_terminal_live_mode_requires_confirm(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(tmp_path, now=_dt("2026-03-20T10:39:00Z"), candidate=candidate)

    with pytest.raises(Exception, match="requires --mode live --confirm"):
        service.terminal_current(mode="live")


def test_terminal_live_declined_post_records_session(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    lifecycle = FakeOrderLifecycle()
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:58Z"),
        candidate=candidate,
        order_lifecycle=lifecycle,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:39:58Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:39:58Z", 101)],
    )
    service._state.append_boundary_decision(  # type: ignore[attr-defined]
        Btc15mBoundaryDecisionRecord(
            window_id="btc15m:" + COND_1,
            condition_id=COND_1,
            market_slug=candidate.market_slug,
            created_at="2026-03-20T10:30:01Z",
            status="partial",
            post_start=_price_tick("chainlink", "2026-03-20T10:30:00Z", "100"),
            timing_source="slug_timestamp",
            start_price_proxy_v1="100",
        )
    )
    service._state.append_windows(  # type: ignore[attr-defined]
        [
            _window_record(
                COND_1,
                candidate.market_slug,
                "2026-03-20T10:30:00Z",
                decision="UP",
            )
        ]
    )

    result = service.terminal_current(
        mode="live",
        confirm=True,
        confirm_action=lambda _: False,
    )

    assert result.session is not None
    assert result.session.mode == Btc15mRunMode.LIVE
    assert result.session.final_state in {
        Btc15mTerminalState.HOLD_TO_EXPIRY,
        Btc15mTerminalState.RESOLVED,
        Btc15mTerminalState.SKIPPED,
    }
    assert lifecycle.posts == []
    assert any(event.kind == "confirm" for event in result.session.operator_events)
    assert service._state.list_terminal_sessions()[-1].session_id == result.session_id  # type: ignore[attr-defined]


def test_terminal_current_observe_only_persists_multiple_snapshots(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:45:58Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:45:58Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:45:58Z", 101)],
    )

    result = service.terminal_current(observe_only=True)

    assert result.session is not None
    assert result.session.final_state is Btc15mTerminalState.OBSERVE_ONLY
    assert result.total_snapshots >= 2
    snapshots = [
        item
        for item in service._state.list_dashboard_snapshots()  # type: ignore[attr-defined]
        if item.session_id == result.session_id and item.view_kind == "terminal"
    ]
    assert len(snapshots) == result.total_snapshots


def test_terminal_wait_next_arms_next_window_when_capture_opens(tmp_path) -> None:
    current_candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    next_candidate = _candidate(COND_2, "btc-updown-15m-1774003500")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:44:59Z"),
        candidate=current_candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:44:59Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:44:59Z", 101)],
    )
    current_resolved = service._resolve_window_from_candidate(  # type: ignore[attr-defined]
        current_candidate,
        selection_source="current_exact",
        target_slug=current_candidate.market_slug,
    )
    next_resolved = service._resolve_window_from_candidate(  # type: ignore[attr-defined]
        next_candidate,
        selection_source="wait_next_exact",
        target_slug=next_candidate.market_slug,
    )
    runtime = service._create_terminal_runtime(  # type: ignore[attr-defined]
        session_id="terminal-wait-test",
        resolved=current_resolved,
        mode=Btc15mRunMode.PAPER,
        started_at_dt=_dt("2026-03-20T10:44:59Z"),
        attach_mode="wait_next",
        observe_only=True,
        wait_next_target_start_dt=_dt("2026-03-20T10:45:00Z"),
    )
    service._resolve_window_by_bucket_start = lambda bucket_start, selection_source: next_resolved  # type: ignore[attr-defined]

    service._advance_terminal_runtime(runtime)  # type: ignore[attr-defined]

    assert runtime.wait_next_target_start_dt is None
    assert runtime.resolved.window.market_slug == next_candidate.market_slug
    assert runtime.observe_only is False
    assert runtime.state in {
        Btc15mTerminalState.PRE_START_CAPTURE,
        Btc15mTerminalState.BOUNDARY_PENDING,
        Btc15mTerminalState.DIRECTION_LOCK_PENDING,
    }


def test_terminal_snapshot_scales_budget_across_default_rungs(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
    )

    result = service.terminal_current(snapshot_only=True, budget_usdc="100")

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.paper_budget_usdc == "100"
    assert result.latest_snapshot.rung_notionals_usdc == ["40", "30", "30"]


def test_terminal_snapshot_uses_explicit_rung_notionals(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
    )

    result = service.terminal_current(
        snapshot_only=True,
        budget_usdc="60",
        rungs="10,20,30",
    )

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.paper_budget_usdc == "60"
    assert result.latest_snapshot.rung_notionals_usdc == ["10", "20", "30"]


def test_terminal_follow_current_arm_next_late_attach_carries_budget_to_next_window(
    tmp_path,
) -> None:
    current_candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    next_candidate = _candidate(COND_2, "btc-updown-15m-1774003500")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:46:00Z"),
        candidate=current_candidate,
    )
    current_resolved = service._resolve_window_from_candidate(  # type: ignore[attr-defined]
        current_candidate,
        selection_source="current_exact",
        target_slug=current_candidate.market_slug,
    )
    next_resolved = service._resolve_window_from_candidate(  # type: ignore[attr-defined]
        next_candidate,
        selection_source="current_exact",
        target_slug=next_candidate.market_slug,
    )
    runtime = service._create_terminal_runtime(  # type: ignore[attr-defined]
        session_id="terminal-follow-arm-next-test",
        resolved=current_resolved,
        mode=Btc15mRunMode.PAPER,
        started_at_dt=_dt("2026-03-20T10:46:00Z"),
        attach_mode="current",
        observe_only=True,
        follow_current=True,
        arm_next=True,
        paper_budget_usdc=Decimal("100"),
        rung_notionals_usdc=(Decimal("40"), Decimal("30"), Decimal("30")),
    )
    runtime.window_finalized = True
    service._resolve_current_window = lambda: type(  # type: ignore[attr-defined]
        "CurrentResolution",
        (),
        {
            "resolved": next_resolved,
            "status": "live",
            "seconds_to_start": 0,
            "seconds_to_end": 840,
        },
    )()

    rolled = service._roll_terminal_session_forward(runtime)  # type: ignore[attr-defined]

    assert rolled is True
    assert runtime.resolved.window.market_slug == next_candidate.market_slug
    assert runtime.observe_only is False
    assert runtime.paper_budget_usdc == Decimal("100")
    assert runtime.rung_notionals_usdc == (Decimal("40"), Decimal("30"), Decimal("30"))


def test_terminal_follow_current_rolls_to_next_window(tmp_path) -> None:
    current_candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    next_candidate = _candidate(COND_2, "btc-updown-15m-1774003500")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:46:00Z"),
        candidate=current_candidate,
    )
    current_resolved = service._resolve_window_from_candidate(  # type: ignore[attr-defined]
        current_candidate,
        selection_source="current_exact",
        target_slug=current_candidate.market_slug,
    )
    next_resolved = service._resolve_window_from_candidate(  # type: ignore[attr-defined]
        next_candidate,
        selection_source="current_exact",
        target_slug=next_candidate.market_slug,
    )
    runtime = service._create_terminal_runtime(  # type: ignore[attr-defined]
        session_id="terminal-follow-test",
        resolved=current_resolved,
        mode=Btc15mRunMode.PAPER,
        started_at_dt=_dt("2026-03-20T10:46:00Z"),
        attach_mode="current",
        follow_current=True,
    )
    runtime.window_finalized = True
    service._resolve_current_window = lambda: type(  # type: ignore[attr-defined]
        "CurrentResolution",
        (),
        {
            "resolved": next_resolved,
            "status": "live",
            "seconds_to_start": 0,
            "seconds_to_end": 840,
        },
    )()

    rolled = service._roll_terminal_session_forward(runtime)  # type: ignore[attr-defined]

    assert rolled is True
    assert runtime.resolved.window.market_slug == next_candidate.market_slug
    assert runtime.rollover_history == [
        f"{current_candidate.market_slug}->{next_candidate.market_slug}"
    ]
    assert runtime.window_finalized is False


def test_terminal_snapshot_includes_both_market_sides(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:39:00Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:39:00Z", 101)],
    )
    service._state.append_boundary_decision(  # type: ignore[attr-defined]
        Btc15mBoundaryDecisionRecord(
            window_id="btc15m:" + COND_1,
            condition_id=COND_1,
            market_slug=candidate.market_slug,
            created_at="2026-03-20T10:30:01Z",
            status="partial",
            post_start=_price_tick("chainlink", "2026-03-20T10:30:00Z", "100"),
            timing_source="slug_timestamp",
            start_price_proxy_v1="100",
        )
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.up_side is not None
    assert result.latest_snapshot.down_side is not None


def test_terminal_replay_uses_stored_snapshots_only(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-20T10:36:00Z"))
    session = Btc15mTerminalSessionRecord(
        session_id="terminal-1",
        created_at="2026-03-20T10:45:00Z",
        started_at="2026-03-20T10:36:00Z",
        ended_at="2026-03-20T10:45:00Z",
        mode=Btc15mRunMode.PAPER,
        attach_mode="current",
        stop_reason="window_complete",
        final_state=Btc15mTerminalState.RESOLVED,
        window=_window_record(COND_1, "btc-updown-15m-1774002600", "2026-03-20T10:30:00Z").window,
    )
    service._state.append_terminal_session(session)  # type: ignore[attr-defined]
    snapshots = [
        service._build_dashboard_snapshot(  # type: ignore[attr-defined]
            service._resolve_window_from_candidate(  # type: ignore[attr-defined]
                _candidate(COND_1, "btc-updown-15m-1774002600"),
                selection_source="current_exact",
                target_slug="btc-updown-15m-1774002600",
            ),
            session_id="terminal-1",
        ).model_copy(update={"view_kind": "terminal"})
        for _ in range(2)
    ]
    service._state.append_dashboard_snapshots(snapshots)  # type: ignore[attr-defined]

    result = service.terminal_replay(session_id="terminal-1")

    assert result.total_snapshots == 2
    assert result.latest_snapshot is not None
    assert result.latest_snapshot.view_kind == "terminal"


def test_terminal_report_aggregates_sessions(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-20T10:36:00Z"))
    service._state.append_terminal_session(  # type: ignore[attr-defined]
        Btc15mTerminalSessionRecord(
            session_id="terminal-1",
            created_at="2026-03-20T10:45:00Z",
            started_at="2026-03-20T10:30:00Z",
            ended_at="2026-03-20T10:45:00Z",
            mode=Btc15mRunMode.PAPER,
            stop_reason="window_complete",
            final_state=Btc15mTerminalState.RESOLVED,
            window=_window_record(
                COND_1,
                "btc-updown-15m-1774002600",
                "2026-03-20T10:30:00Z",
            ).window,
        )
    )

    result = service.terminal_report()

    assert result.summary.terminal_session_count == 1
    assert result.summary.paper_session_count == 1
    assert result.summary.resolved_session_count == 1


def test_terminal_report_session_id_returns_single_tear_sheet(tmp_path) -> None:
    service = _service(tmp_path, now=_dt("2026-03-20T10:36:00Z"))
    service._state.append_terminal_session(  # type: ignore[attr-defined]
        Btc15mTerminalSessionRecord(
            session_id="terminal-1",
            created_at="2026-03-20T10:45:00Z",
            started_at="2026-03-20T10:36:00Z",
            ended_at="2026-03-20T10:45:00Z",
            mode=Btc15mRunMode.PAPER,
            attach_mode="current",
            stop_reason="window_complete",
            final_state=Btc15mTerminalState.RESOLVED,
            window=_window_record(
                COND_1,
                "btc-updown-15m-1774002600",
                "2026-03-20T10:30:00Z",
            ).window,
        )
    )

    result = service.terminal_report(session_id="terminal-1")

    assert result.session is not None
    assert result.session.session_id == "terminal-1"


def test_auto_roll_returns_insufficient_remaining_time(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:36:00Z"),
        candidate=candidate,
    )

    result = service.auto_roll(hours="0.01", mode="paper")

    assert result.run.stop_reason == "insufficient_remaining_time"
    assert service._state.list_auto_roll_runs()[-1].run_id == result.run.run_id  # type: ignore[attr-defined]


def test_recurring_resolution_falls_back_to_tolerant_gamma_search(tmp_path) -> None:
    candidate = _candidate(COND_1, "bitcoin-up-or-down-15-min")
    candidate = candidate.model_copy(
        update={
            "question": "Bitcoin up or down in 15 minutes?",
            "event_title": "Bitcoin recurring ladder market",
        }
    )
    search_candidate = _search_candidate(candidate)
    service = _service(
        tmp_path,
        now=_dt("2026-03-19T00:00:00Z"),
        candidate=candidate,
        search_candidate=search_candidate,
        market_intel_candidate=None,
    )

    result = service.record_start(seconds=60)

    assert result.total == 1
    assert result.items[0].window.market_slug == "bitcoin-up-or-down-15-min"


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
        ),
        CapturedStreamEvent(
            session_id="market-session",
            stream_kind="market",
            source="polymarket_market_ws",
            captured_at="2026-03-19T00:06:02Z",
            event_type="last_trade_price",
            market_event=NormalizedMarketStreamEvent(
                event_type="last_trade_price",
                token_id=TOKEN_UP,
                timestamp=int((observed_dt + timedelta(seconds=2)).timestamp()),
                price="0.31",
                size="10",
                side="buy",
            ),
        ),
        CapturedStreamEvent(
            session_id="market-session",
            stream_kind="market",
            source="polymarket_market_ws",
            captured_at="2026-03-19T00:06:03Z",
            event_type="last_trade_price",
            market_event=NormalizedMarketStreamEvent(
                event_type="last_trade_price",
                token_id=TOKEN_DOWN,
                timestamp=int((observed_dt + timedelta(seconds=3)).timestamp()),
                price="0.69",
                size="12",
                side="sell",
            ),
        ),
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


def _price_tick(source: str, observed_at: str, value: str):
    from pm.strategy import Btc15mPriceTick

    return Btc15mPriceTick(
        source=source,
        captured_at=observed_at,
        observed_at=observed_at,
        value=value,
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
        ),
        Btc15mMarketSample(
            token_id=TOKEN_UP,
            outcome="Up",
            event_type="last_trade_price",
            source="polymarket_market_ws",
            captured_at="2026-03-19T00:06:02Z",
            observed_at="2026-03-19T00:06:02Z",
            last_trade_price="0.31",
        ),
        Btc15mMarketSample(
            token_id=TOKEN_DOWN,
            outcome="Down",
            event_type="last_trade_price",
            source="polymarket_market_ws",
            captured_at="2026-03-19T00:06:03Z",
            observed_at="2026-03-19T00:06:03Z",
            last_trade_price="0.69",
        ),
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


def _wide_liquidity_sample(window_id: str, market_slug: str) -> Btc15mLiquiditySampleRecord:
    return Btc15mLiquiditySampleRecord(
        sample_id="sample-wide",
        window_id=window_id,
        condition_id=window_id.replace("btc15m:", ""),
        market_slug=market_slug,
        sample_kind="terminal",
        sampled_at="2026-03-19T00:06:00Z",
        scheduled_at="2026-03-19T00:06:00Z",
        late_by_seconds=0,
        binance=FakeBinanceService().sample_liquidity(),
        polymarket=[
            Btc15mPolymarketLiquidityLevel(
                token_id=TOKEN_UP,
                outcome="Up",
                best_bid="0.20",
                best_ask="0.35",
                midpoint="0.275",
                spread="0.15",
                visible_liquidity_030="80",
                visible_liquidity_020="50",
                visible_liquidity_010="10",
            ),
            Btc15mPolymarketLiquidityLevel(
                token_id=TOKEN_DOWN,
                outcome="Down",
                best_bid="0.60",
                best_ask="0.80",
                midpoint="0.70",
                spread="0.20",
                visible_liquidity_030="0",
                visible_liquidity_020="0",
                visible_liquidity_010="0",
            ),
        ],
        errors=[],
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_terminal_snapshot_late_attach_uses_paper_page_fallback_start_anchor(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:31:05Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:31:05Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:31:05Z", 101)],
        page_parity_data=Btc15mPageParityData(
            event_url="https://polymarket.com/event/btc-15m-event",
            current_window_label="BTC 15m active",
            price_to_beat="101234.5",
            current_live_btc_price="101240.1",
            up_price="0.33",
            down_price="0.67",
            volume="120K",
            field_sources={
                "price_to_beat": "page_exact",
                "current_live_btc_price": "page_exact",
                "up_price": "page_exact",
                "down_price": "page_exact",
                "volume": "page_exact",
            },
            matched_market_slug="btc-updown-15m-1774002600",
            observed_at="2026-03-20T10:31:05Z",
        ),
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.observe_only is True
    assert result.latest_snapshot.window_status == Btc15mTerminalState.OBSERVE_ONLY
    assert result.latest_snapshot.start_price_proxy_v1 is None
    assert result.latest_snapshot.paper_start_proxy_v1 is None
    assert result.latest_snapshot.paper_start_proxy_source is None
    assert result.latest_snapshot.display is not None
    assert result.latest_snapshot.display.display_source == "page_exact"
    assert result.latest_snapshot.display.display_price_to_beat == "101234.5"


def test_terminal_snapshot_uses_page_parity_fallback_when_needed(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        chainlink_events=[],
        binance_events=[],
        page_parity_data=Btc15mPageParityData(
            event_url="https://polymarket.com/event/btc-15m-event",
            current_window_label="BTC 15m active",
            price_to_beat="101234.5",
            current_live_btc_price="101240.1",
            up_price="0.33",
            down_price="0.67",
            volume="120K",
            field_sources={
                "price_to_beat": "page_exact",
                "current_live_btc_price": "page_exact",
                "up_price": "page_exact",
                "down_price": "page_exact",
                "volume": "page_exact",
            },
            matched_market_slug="btc-updown-15m-1774002600",
        ),
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.display is not None
    assert result.latest_snapshot.page_mirror is not None
    assert result.latest_snapshot.market_truth is not None
    assert result.latest_snapshot.terminal_presenter is not None
    assert result.latest_snapshot.page_parity_source == "page_exact"
    assert result.latest_snapshot.current_window_label == "BTC 15m active"
    assert result.latest_snapshot.current_live_btc_price == "101240.1"
    assert result.latest_snapshot.up_price == "0.33"
    assert result.latest_snapshot.down_price == "0.67"
    assert result.latest_snapshot.price_to_beat == "101234.5"
    assert result.latest_snapshot.paper_start_proxy_v1 is None
    assert result.latest_snapshot.paper_start_proxy_source is None
    assert result.latest_snapshot.start_price_proxy_v1 is None
    assert result.latest_snapshot.display.display_price_to_beat == "101234.5"
    assert result.latest_snapshot.display.display_volume == "120K"
    assert result.latest_snapshot.display.display_source == "page_exact"
    assert result.latest_snapshot.display.display_stale is False
    assert (
        result.latest_snapshot.market_truth.countdown
        == result.latest_snapshot.display.display_countdown
    )


def test_terminal_snapshot_exposes_nested_layers(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        chainlink_events=[_crypto_event("chainlink", "2026-03-20T10:39:00Z", 101)],
        binance_events=[_crypto_event("binance", "2026-03-20T10:39:00Z", 101)],
        page_parity_data=Btc15mPageParityData(
            event_url="https://polymarket.com/event/btc-15m-event",
            current_window_label="BTC 15m active",
            price_to_beat="101234.5",
            current_live_btc_price="101240.1",
            up_price="0.33",
            down_price="0.67",
            volume="120K",
            field_sources={
                "price_to_beat": "page_exact",
                "current_live_btc_price": "page_exact",
                "up_price": "page_exact",
                "down_price": "page_exact",
                "volume": "page_exact",
            },
            matched_market_slug="btc-updown-15m-1774002600",
        ),
    )
    service._state.append_boundary_decision(  # type: ignore[attr-defined]
        Btc15mBoundaryDecisionRecord(
            window_id="btc15m:" + COND_1,
            condition_id=COND_1,
            market_slug=candidate.market_slug,
            created_at="2026-03-20T10:30:01Z",
            status="partial",
            post_start=_price_tick("chainlink", "2026-03-20T10:30:00Z", "100"),
            timing_source="slug_timestamp",
            start_price_proxy_v1="100",
        )
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.page_mirror is not None
    assert result.latest_snapshot.market_truth is not None
    assert result.latest_snapshot.terminal_presenter is not None
    assert result.latest_snapshot.page_mirror.display_source == "page_exact"
    assert result.latest_snapshot.market_truth.start_price_proxy_v1 == "100"
    assert result.latest_snapshot.terminal_presenter.primary_block_source == "page_mirror"


def test_terminal_countdown_is_slug_derived_and_stable(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
        page_parity_data=Btc15mPageParityData(
            current_window_label="BTC 15m active",
            price_to_beat="101234.5",
            current_live_btc_price="101240.1",
            up_price="0.33",
            down_price="0.67",
            volume="120K",
            field_sources={
                "price_to_beat": "page_exact",
                "current_live_btc_price": "page_exact",
                "up_price": "page_exact",
                "down_price": "page_exact",
                "volume": "page_exact",
            },
            matched_market_slug="btc-updown-15m-1774002600",
        ),
    )
    current = service._resolve_current_window()  # type: ignore[attr-defined]
    runtime = service._create_terminal_runtime(  # type: ignore[attr-defined]
        session_id="terminal-countdown-test",
        resolved=current.resolved,
        mode=Btc15mRunMode.PAPER,
        started_at_dt=_dt("2026-03-20T10:39:00Z"),
        attach_mode="current",
    )

    first_snapshot = service._advance_terminal_runtime(runtime)  # type: ignore[attr-defined]
    service._sleep(5)  # type: ignore[attr-defined]
    second_snapshot = service._advance_terminal_runtime(runtime)  # type: ignore[attr-defined]

    assert first_snapshot.market_truth is not None
    assert first_snapshot.display is not None
    assert second_snapshot.market_truth is not None
    assert second_snapshot.display is not None
    assert first_snapshot.market_truth.countdown == first_snapshot.display.display_countdown
    assert second_snapshot.market_truth.countdown == second_snapshot.display.display_countdown
    assert first_snapshot.market_truth.countdown_seconds == 360
    assert second_snapshot.market_truth.countdown_seconds == 355


def test_terminal_market_truth_uses_midpoint_for_tight_spread(tmp_path) -> None:
    candidate = _candidate(COND_1, "btc-updown-15m-1774002600")
    service = _service(
        tmp_path,
        now=_dt("2026-03-20T10:39:00Z"),
        candidate=candidate,
    )
    service._state.append_boundary_decision(  # type: ignore[attr-defined]
        Btc15mBoundaryDecisionRecord(
            window_id="btc15m:" + COND_1,
            condition_id=COND_1,
            market_slug=candidate.market_slug,
            created_at="2026-03-20T10:30:01Z",
            status="partial",
            post_start=_price_tick("chainlink", "2026-03-20T10:30:00Z", "100"),
            timing_source="slug_timestamp",
            start_price_proxy_v1="100",
        )
    )

    result = service.terminal_current(snapshot_only=True)

    assert result.latest_snapshot is not None
    assert result.latest_snapshot.market_truth is not None
    assert result.latest_snapshot.market_truth.derived_up_price_source == "midpoint"
