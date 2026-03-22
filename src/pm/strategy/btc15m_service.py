"""BTC 15-minute Chainlink directional ladder recorder and paper simulator."""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from time import sleep as time_sleep
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from pm.auth import AuthClientError, AuthService, AuthValidationError
from pm.binance import BinanceClientError, BinanceService
from pm.execution import (
    DryRunService,
    ExecutionValidationError,
    ExecutionWatchService,
    OrderLifecycleService,
)
from pm.execution.state import ExecutionStateError, ExecutionStateService
from pm.market.clob import ClobClient
from pm.market.exceptions import ClobClientError, ClobNotFoundError
from pm.market.gamma import GammaClient, GammaSearchCandidate
from pm.market.models import NormalizedBookLevel, NormalizedMarket, RecurringMarketCandidate
from pm.market.service import (
    MarketIntelService,
    MarketValidationError,
    validate_recurring_interval,
)
from pm.risk import RiskPolicyService, RiskStateError
from pm.strategy.btc15m_models import (
    Btc15mAutoRollResponse,
    Btc15mAutoRollRunRecord,
    Btc15mBoundaryDecisionRecord,
    Btc15mBoundaryObservationRecord,
    Btc15mCampaignNextWindowResponse,
    Btc15mCampaignReportResponse,
    Btc15mCampaignReportSummary,
    Btc15mCampaignRunRecord,
    Btc15mCampaignRunResponse,
    Btc15mCanaryLiveProfile,
    Btc15mDashboardResponse,
    Btc15mDashboardRungState,
    Btc15mDashboardSideState,
    Btc15mDashboardSnapshotRecord,
    Btc15mLadderRungResult,
    Btc15mLiquiditySampleRecord,
    Btc15mLiquiditySampleResponse,
    Btc15mLiveCheckResponse,
    Btc15mLiveResponse,
    Btc15mMarketSample,
    Btc15mPaperEvaluation,
    Btc15mPaperRunRecord,
    Btc15mPaperRunResponse,
    Btc15mPolymarketLiquidityLevel,
    Btc15mPriceMark,
    Btc15mPriceTick,
    Btc15mReasonBlock,
    Btc15mRecordStartResponse,
    Btc15mRecordWindowResponse,
    Btc15mReplayRecord,
    Btc15mReplayResponse,
    Btc15mReportResponse,
    Btc15mReportSummary,
    Btc15mResolveCurrentResponse,
    Btc15mRunMode,
    Btc15mSectionError,
    Btc15mSessionArmResponse,
    Btc15mSessionBundleResponse,
    Btc15mSessionLatestResponse,
    Btc15mSessionRecord,
    Btc15mSessionReportRecord,
    Btc15mSessionReportResponse,
    Btc15mSessionRunResponse,
    Btc15mSessionState,
    Btc15mSessionStatusResponse,
    Btc15mSessionStopResponse,
    Btc15mTerminalDisplayTruth,
    Btc15mTerminalEventRecord,
    Btc15mTerminalMarketTruth,
    Btc15mTerminalPageMirror,
    Btc15mTerminalPresenter,
    Btc15mTerminalReplayResponse,
    Btc15mTerminalReportResponse,
    Btc15mTerminalReportSummary,
    Btc15mTerminalResponse,
    Btc15mTerminalSessionRecord,
    Btc15mTerminalState,
    Btc15mTerminalWindowTearSheet,
    Btc15mTimingControls,
    Btc15mWindowIdentity,
    Btc15mWindowRecord,
)
from pm.strategy.btc15m_page import Btc15mPageParityData, Btc15mPageParityService
from pm.strategy.btc15m_state import Btc15mStateError, Btc15mStateService
from pm.stream.market import MarketWebSocketClient
from pm.stream.models import (
    CapturedStreamEvent,
    CryptoStreamResponse,
    MarketWatchStreamResponse,
    StreamSectionError,
)
from pm.stream.rtds import RTDSClient
from pm.stream.runner import BoundedRunResult, StreamValidationError

if TYPE_CHECKING:
    from pm.portfolio.state import PortfolioStateService

DEFAULT_RECORD_SECONDS = 60
DEFAULT_RECORD_QUERY = "btc"
DEFAULT_RECORD_INTERVAL = "15m"
DEFAULT_POST_END_WAIT_SECONDS = 60
DEFAULT_PRE_START_CAPTURE_WINDOW_SECONDS = 60
DEFAULT_POST_START_GRACE_WINDOW_SECONDS = 60
DEFAULT_PRE_END_CAPTURE_WINDOW_SECONDS = 60
DEFAULT_POST_END_GRACE_WINDOW_SECONDS = 60
DEFAULT_DECISION_STALE_SECONDS = 15
DEFAULT_MARKET_STALE_SECONDS = 5
DEFAULT_PAPER_RUN_LIMIT = 20
DEFAULT_LIQUIDITY_SAMPLE_SECONDS = 30
DEFAULT_LIQUIDITY_SAMPLE_CADENCE_SECONDS = 5
DEFAULT_DASHBOARD_SECONDS = 30
DEFAULT_DASHBOARD_REFRESH_SECONDS = 1
DEFAULT_LIVE_TICK_CAPTURE_SECONDS = 1
DEFAULT_TERMINAL_EVENT_LOG_LIMIT = 12
DEFAULT_TERMINAL_SNAPSHOT_LOG_LIMIT = 8
DEFAULT_TERMINAL_CONTEXT_REFRESH_SECONDS = 30
DEFAULT_TERMINAL_PAGE_PARITY_REFRESH_SECONDS = 5
DEFAULT_TERMINAL_REPLAY_REFRESH_SECONDS = 0.15
DEFAULT_TERMINAL_SESSION_EVENT_LOG_LIMIT = 48
DEFAULT_CAMPAIGN_WAIT_SECONDS = 15
DEFAULT_CAMPAIGN_MAX_WAIT_SECONDS = 20 * 60
DEFAULT_CAMPAIGN_SAMPLE_CADENCE_SECONDS = 30
DEFAULT_FALLBACK_SEARCH_LIMIT = 60
BTC15M_FALLBACK_QUERIES = ("btc", "bitcoin", "btc 15m")
BTC15M_INTERVAL_ALIASES = ("15m", "15 min", "15 minute", "15 minutes")
BTC15M_BTC_MARKERS = ("btc", "bitcoin")
BTC15M_DIRECTION_MARKERS = ("up", "down")
BTC15M_CANONICAL_SLUG_RE = re.compile(r"^btc-updown-15m-(\d{10})$")
WINDOW_DURATION = timedelta(minutes=15)
MINUTE_FIVE_OFFSET = timedelta(minutes=5)
MINUTE_TEN_OFFSET = timedelta(minutes=10)
ONE_MINUTE = timedelta(minutes=1)
THREE_MINUTES = timedelta(minutes=3)
MAX_POLYMARKET_SPREAD = Decimal("0.08")
FIRST_RUNG_MIN_LIQUIDITY = Decimal("66.666666")
MAX_BINANCE_CHAINLINK_DIVERGENCE_BPS = Decimal("15")
MAX_POLYMARKET_UNDERLYING_DIVERGENCE_BPS = Decimal("8")
RUNG_PRICES = (
    Decimal("0.30"),
    Decimal("0.20"),
    Decimal("0.10"),
)
RUNG_NOTIONALS = (
    Decimal("20"),
    Decimal("15"),
    Decimal("15"),
)
DEFAULT_TERMINAL_BUDGET_USDC = sum(RUNG_NOTIONALS, Decimal("0"))
BTC15M_STRATEGY_NAME = "btc_15m_chainlink_directional_ladder_v1"
BTC15M_CANARY_MAX_LIVE_USDC = Decimal("15")
BTC15M_CANARY_MAX_RUNG_USDC = Decimal("5")


class Btc15mValidationError(RuntimeError):
    """Raised when BTC15m CLI or service inputs are invalid."""


class Btc15mOperatorHintError(Btc15mValidationError):
    """Validation error with structured operator guidance."""

    def __init__(
        self,
        message: str,
        *,
        identifier: str | None = None,
        hint: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.identifier = identifier
        self.hint = hint


@dataclass(slots=True)
class _ResolvedWindow:
    candidate: RecurringMarketCandidate
    window: Btc15mWindowIdentity
    window_start_dt: datetime | None
    window_end_dt: datetime | None
    selection_source: str
    target_slug: str | None = None


@dataclass(slots=True)
class _RecordedWindowArtifacts:
    record: Btc15mWindowRecord
    evaluation: Btc15mPaperEvaluation | None


@dataclass(slots=True)
class _CurrentWindowResolution:
    resolved: _ResolvedWindow
    status: str
    seconds_to_start: int | None
    seconds_to_end: int | None


@dataclass(slots=True)
class _TerminalRungRuntime:
    price: Decimal
    notional_usdc: Decimal
    quantity: Decimal
    state: str = "armed"
    order_id: str | None = None
    fill_at: str | None = None
    fill_price: str | None = None
    cancellation_at: str | None = None
    post_attempted: bool = False
    cancel_attempted: bool = False


@dataclass(slots=True)
class _TerminalRuntime:
    session_id: str
    resolved: _ResolvedWindow
    mode: Btc15mRunMode
    started_at_dt: datetime
    state: Btc15mTerminalState
    attach_mode: str = "current"
    observe_only: bool = False
    follow_current: bool = False
    arm_next: bool = False
    wait_next_target_start_dt: datetime | None = None
    stop_reason: str = "running"
    paper_budget_usdc: Decimal = DEFAULT_TERMINAL_BUDGET_USDC
    rung_notionals_usdc: tuple[Decimal, Decimal, Decimal] = RUNG_NOTIONALS
    events: list[Btc15mTerminalEventRecord] = field(default_factory=list)
    session_events: list[Btc15mTerminalEventRecord] = field(default_factory=list)
    errors: list[Btc15mSectionError] = field(default_factory=list)
    chainlink_ticks: list[Btc15mPriceTick] = field(default_factory=list)
    binance_ticks: list[Btc15mPriceTick] = field(default_factory=list)
    liquidity_samples: list[Btc15mLiquiditySampleRecord] = field(default_factory=list)
    market_samples: list[Btc15mMarketSample] = field(default_factory=list)
    boundary_pre_start: Btc15mPriceTick | None = None
    boundary_post_start: Btc15mPriceTick | None = None
    boundary_pre_end: Btc15mPriceTick | None = None
    boundary_post_end: Btc15mPriceTick | None = None
    boundary_status: str = "pending"
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
    selected_side: str | None = None
    decision_at: str | None = None
    target_token_id: str | None = None
    target_outcome: str | None = None
    rungs: list[_TerminalRungRuntime] = field(default_factory=list)
    market_open_interest: str | None = None
    market_volume: str | None = None
    last_market_context_refresh_at: datetime | None = None
    last_page_parity_refresh_at: datetime | None = None
    current_market: NormalizedMarket | None = None
    page_parity_fallback: Btc15mPageParityData | None = None
    manipulation_flags: list[str] = field(default_factory=list)
    skip_reasons: list[str] = field(default_factory=list)
    reason_blocks: list[Btc15mReasonBlock] = field(default_factory=list)
    latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
    favorable_marks: list[Btc15mPriceMark] = field(default_factory=list)
    mfe: Decimal = Decimal("0")
    mae: Decimal = Decimal("0")
    max_favorable_price: str | None = None
    time_to_peak_seconds: int | None = None
    first_fill_at: str | None = None
    total_snapshots: int = 0
    current_window_snapshots: int = 0
    window_started_at_dt: datetime | None = None
    tear_sheets: list[Btc15mTerminalWindowTearSheet] = field(default_factory=list)
    rollover_history: list[str] = field(default_factory=list)
    window_finalized: bool = False


class Btc15mStrategyService:
    """Recorder, replay, and paper-evaluation service for BTC15m research."""

    def __init__(
        self,
        *,
        state: Btc15mStateService | None = None,
        market_intel_service: MarketIntelService | None = None,
        market_client: MarketWebSocketClient | None = None,
        crypto_client: RTDSClient | None = None,
        binance_service: BinanceService | None = None,
        page_parity_service: Btc15mPageParityService | None = None,
        order_lifecycle: OrderLifecycleService | None = None,
        execution_watch_service: ExecutionWatchService | None = None,
        dry_run_service: DryRunService | None = None,
        auth_service: AuthService | None = None,
        risk_service: RiskPolicyService | None = None,
        execution_state_service: ExecutionStateService | None = None,
        portfolio_state_service: PortfolioStateService | None = None,
        gamma_client_cls: type[GammaClient] = GammaClient,
        clob_client_cls: type[ClobClient] = ClobClient,
        now: Any | None = None,
        sleep: Callable[[float], None] | None = None,
        async_sleep: Callable[[float], Any] | None = None,
    ) -> None:
        self._state = state or Btc15mStateService()
        self._market_intel_service = market_intel_service or MarketIntelService()
        self._market_client = market_client or MarketWebSocketClient()
        self._crypto_client = crypto_client or RTDSClient()
        self._binance_service = binance_service or BinanceService()
        self._page_parity_service = page_parity_service or Btc15mPageParityService()
        self._order_lifecycle = order_lifecycle or OrderLifecycleService()
        self._dry_run_service = dry_run_service or DryRunService()
        self._auth_service = auth_service or AuthService()
        self._risk_service = risk_service or RiskPolicyService()
        self._execution_state = execution_state_service or ExecutionStateService()
        if portfolio_state_service is None:
            from pm.portfolio.state import PortfolioStateService as _PortfolioStateService

            portfolio_state_service = _PortfolioStateService()
        self._portfolio_state = portfolio_state_service
        self._execution_watch_service = execution_watch_service or ExecutionWatchService(
            lifecycle_service=self._order_lifecycle
        )
        self._gamma_client_cls = gamma_client_cls
        self._clob_client_cls = clob_client_cls
        self._now = now or _utc_now
        self._sleep = sleep or time_sleep
        self._async_sleep = async_sleep or asyncio.sleep

    def record_start(self, *, seconds: int = DEFAULT_RECORD_SECONDS) -> Btc15mRecordStartResponse:
        """Run one bounded BTC15m recorder session for the latest recurring market."""
        if seconds <= 0:
            raise Btc15mValidationError("Recorder duration must be greater than zero seconds.")

        session_id = _make_id("btc15m_record")
        started_at = _isoformat(self._now())
        cursor = self._now()
        global_end = cursor + timedelta(seconds=seconds)
        items: list[Btc15mWindowRecord] = []
        errors: list[Btc15mSectionError] = []
        seen_window_ids: set[str] = set()

        while cursor < global_end:
            resolved = self._resolve_latest_window()
            if resolved.window.window_id in seen_window_ids:
                break
            seen_window_ids.add(resolved.window.window_id)

            chunk_end = global_end
            if resolved.window_end_dt is not None:
                chunk_end = min(
                    chunk_end,
                    resolved.window_end_dt + timedelta(seconds=DEFAULT_POST_END_WAIT_SECONDS),
                )
            chunk_seconds = max(1, int((chunk_end - cursor).total_seconds()))
            record = self._record_resolved_window(
                resolved,
                seconds=chunk_seconds,
                recorder_session_id=session_id,
            )
            items.append(record)
            errors.extend(record.errors)
            cursor = chunk_end

        ended_at = _isoformat(min(self._now(), global_end))
        return Btc15mRecordStartResponse(
            session_id=session_id,
            started_at=started_at,
            ended_at=ended_at,
            requested_seconds=seconds,
            items=items,
            total=len(items),
            errors=errors,
        )

    def record_window(self, *, slug: str) -> Btc15mRecordWindowResponse:
        """Record one specific BTC15m window until end-boundary capture or timeout."""
        normalized_slug = slug.strip()
        if not normalized_slug:
            raise Btc15mValidationError("Market slug is required.")

        session_id = _make_id("btc15m_record")
        started_at = _isoformat(self._now())
        resolved = self._resolve_window_by_slug(normalized_slug)
        seconds = self._targeted_record_seconds(resolved)
        record = self._record_resolved_window(
            resolved,
            seconds=seconds,
            recorder_session_id=session_id,
        )
        ended_at = _isoformat(self._now())
        return Btc15mRecordWindowResponse(
            session_id=session_id,
            slug=normalized_slug,
            started_at=started_at,
            ended_at=ended_at,
            requested_seconds=seconds,
            items=[record],
            total=1,
            errors=record.errors,
        )

    def replay(self, *, from_at: str, to_at: str) -> Btc15mReplayResponse:
        """Replay recorded BTC15m windows across a time range."""
        from_dt = _parse_iso_timestamp(from_at)
        to_dt = _parse_iso_timestamp(to_at)
        if from_dt >= to_dt:
            raise Btc15mValidationError("--from must be earlier than --to.")

        items: list[Btc15mPaperEvaluation] = []
        for record in self._iter_latest_windows():
            window_start = _parse_iso_optional(record.window.window_start_at)
            if window_start is None or window_start < from_dt or window_start >= to_dt:
                continue
            items.append(self._evaluate_window(record))
        replay = Btc15mReplayRecord(
            replay_id=_make_id("btc15m_replay"),
            created_at=_isoformat(self._now()),
            from_at=_isoformat(from_dt),
            to_at=_isoformat(to_dt),
            items=items,
            total=len(items),
            errors=[],
        )
        self._state.append_replay(replay)
        return Btc15mReplayResponse(replay=replay)

    def resolve_current(self) -> Btc15mResolveCurrentResponse:
        """Resolve the current live, settling, or upcoming BTC15m window."""
        current = self._resolve_current_window()
        return Btc15mResolveCurrentResponse(
            checked_at=_isoformat(self._now()),
            timing_source=current.resolved.window.timing_source,
            selection_source=current.resolved.selection_source,
            status=current.status,
            seconds_to_start=current.seconds_to_start,
            seconds_to_end=current.seconds_to_end,
            window=current.resolved.window,
        )

    def live_current(
        self,
        *,
        mode: str = "paper",
        hours: str | None = None,
    ) -> Btc15mLiveResponse:
        """Run one bounded current-window live-data paper session."""
        normalized_mode = _require_paper_mode(mode)
        started_at_dt = self._now()
        current = self._resolve_current_window()
        resolved = current.resolved
        requested_hours: str | None = None
        if hours is not None:
            requested = _decimal(hours)
            if requested <= 0:
                raise Btc15mValidationError("Live hours must be greater than zero.")
            requested_hours = _decimal_text(requested)
            deadline = started_at_dt + timedelta(seconds=float(requested * Decimal("3600")))
            if not self._can_complete_window_before(resolved, deadline):
                return Btc15mLiveResponse(
                    run_id=_make_id("btc15m_live"),
                    started_at=_isoformat(started_at_dt),
                    ended_at=_isoformat(self._now()),
                    mode=normalized_mode,
                    requested_hours=requested_hours,
                    stop_reason="insufficient_remaining_time",
                    window=resolved.window,
                )

        artifacts = self._record_and_evaluate_window(
            resolved,
            seconds=self._targeted_record_seconds(resolved),
            recorder_session_id=_make_id("btc15m_record"),
            evaluation_source_kind="live_current",
            persist_paper_run=True,
            mode=normalized_mode,
        )
        return Btc15mLiveResponse(
            run_id=_make_id("btc15m_live"),
            started_at=_isoformat(started_at_dt),
            ended_at=_isoformat(self._now()),
            mode=normalized_mode,
            requested_hours=requested_hours,
            stop_reason="completed_current_window",
            window=artifacts.record.window,
            evaluation=artifacts.evaluation,
            errors=artifacts.record.errors,
        )

    def dashboard_current(
        self,
        *,
        seconds: int = DEFAULT_DASHBOARD_SECONDS,
        on_snapshot: Callable[[Btc15mDashboardSnapshotRecord], None] | None = None,
    ) -> Btc15mDashboardResponse:
        """Run a bounded BTC15m current-window dashboard session."""
        if seconds <= 0:
            raise Btc15mValidationError("Dashboard duration must be greater than zero seconds.")
        current = self._resolve_current_window()
        session_id = _make_id("btc15m_dashboard")
        started_at_dt = self._now()
        snapshots: list[Btc15mDashboardSnapshotRecord] = []
        errors: list[Btc15mSectionError] = []

        for index in range(seconds):
            snapshot = self._build_dashboard_snapshot(
                current.resolved,
                session_id=session_id,
            )
            snapshots.append(snapshot)
            errors.extend(snapshot.errors)
            if on_snapshot is not None:
                on_snapshot(snapshot)
            if index < seconds - 1:
                self._sleep(DEFAULT_DASHBOARD_REFRESH_SECONDS)

        self._state.append_dashboard_snapshots(snapshots)
        return Btc15mDashboardResponse(
            session_id=session_id,
            started_at=_isoformat(started_at_dt),
            ended_at=_isoformat(self._now()),
            requested_seconds=seconds,
            window=current.resolved.window,
            total_snapshots=len(snapshots),
            latest_snapshot=snapshots[-1] if snapshots else None,
            latest_evaluation=self._latest_evaluation_for_window(current.resolved.window.window_id),
            errors=errors,
        )

    def terminal_current(
        self,
        *,
        mode: str = "paper",
        confirm: bool = False,
        observe_only: bool = False,
        arm_next: bool = False,
        budget_usdc: str | None = None,
        rungs: str | None = None,
        snapshot_only: bool = False,
        session_window_limit: int | None = 1,
        on_snapshot: Callable[[Btc15mDashboardSnapshotRecord], None] | None = None,
        confirm_action: Callable[[str], bool | None] | None = None,
    ) -> Btc15mTerminalResponse:
        """Run one bounded BTC15m operator-terminal session or emit one snapshot."""
        normalized_mode = _normalize_terminal_mode(mode)
        if snapshot_only and normalized_mode is Btc15mRunMode.LIVE:
            raise Btc15mOperatorHintError(
                "BTC15m terminal JSON snapshots are only available in paper mode.",
                identifier="mode",
                hint={"next_steps": ["Run human terminal mode for live inline confirmations."]},
            )
        if normalized_mode is Btc15mRunMode.LIVE and not confirm:
            raise Btc15mValidationError("BTC15m live terminal requires --mode live --confirm.")
        if normalized_mode is Btc15mRunMode.LIVE and confirm_action is None and not snapshot_only:
            raise Btc15mValidationError(
                "BTC15m live terminal requires an attached interactive confirmer."
            )

        current = self._resolve_current_window()
        paper_budget_usdc, rung_notionals_usdc = _resolve_terminal_paper_sizing(
            budget_usdc=budget_usdc,
            rungs=rungs,
        )
        session_id = _make_id("btc15m_terminal")
        started_at_dt = self._now()
        runtime = self._create_terminal_runtime(
            session_id=session_id,
            resolved=current.resolved,
            mode=normalized_mode,
            started_at_dt=started_at_dt,
            attach_mode="current_observe_only" if observe_only else "current",
            observe_only=observe_only,
            arm_next=arm_next,
            follow_current=not snapshot_only,
            paper_budget_usdc=paper_budget_usdc,
            rung_notionals_usdc=rung_notionals_usdc,
        )
        if snapshot_only:
            snapshot = self._advance_terminal_runtime(runtime)
            self._state.append_dashboard_snapshots([snapshot])
            return Btc15mTerminalResponse(
                session_id=session_id,
                started_at=_isoformat(started_at_dt),
                ended_at=_isoformat(self._now()),
                mode=normalized_mode,
                attach_mode=runtime.attach_mode,
                stop_reason="snapshot_only",
                window=runtime.resolved.window,
                total_snapshots=1,
                latest_snapshot=snapshot,
                errors=snapshot.errors,
            )
        return self._run_terminal_session(
            runtime,
            session_window_limit=session_window_limit,
            on_snapshot=on_snapshot,
            confirm_action=confirm_action,
        )

    def terminal_wait_next(
        self,
        *,
        mode: str = "paper",
        confirm: bool = False,
        budget_usdc: str | None = None,
        rungs: str | None = None,
        snapshot_only: bool = False,
        session_window_limit: int | None = 1,
        on_snapshot: Callable[[Btc15mDashboardSnapshotRecord], None] | None = None,
        confirm_action: Callable[[str], bool | None] | None = None,
    ) -> Btc15mTerminalResponse:
        """Wait for and arm the next BTC15m window, monitoring the current window meanwhile."""
        normalized_mode = _normalize_terminal_mode(mode)
        if snapshot_only and normalized_mode is Btc15mRunMode.LIVE:
            raise Btc15mOperatorHintError(
                "BTC15m terminal JSON snapshots are only available in paper mode.",
                identifier="mode",
                hint={"next_steps": ["Run human terminal mode for live inline confirmations."]},
            )
        if normalized_mode is Btc15mRunMode.LIVE and not confirm:
            raise Btc15mValidationError("BTC15m live terminal requires --mode live --confirm.")
        if normalized_mode is Btc15mRunMode.LIVE and confirm_action is None and not snapshot_only:
            raise Btc15mValidationError(
                "BTC15m live terminal requires an attached interactive confirmer."
            )

        now = self._now()
        current = self._resolve_current_window()
        paper_budget_usdc, rung_notionals_usdc = _resolve_terminal_paper_sizing(
            budget_usdc=budget_usdc,
            rungs=rungs,
        )
        current_bucket_start = _floor_btc15m_window_start(now)
        next_bucket_start = current_bucket_start + WINDOW_DURATION
        next_capture_at = next_bucket_start - timedelta(
            seconds=DEFAULT_PRE_START_CAPTURE_WINDOW_SECONDS
        )

        resolved = current.resolved
        attach_mode = "wait_next"
        observe_only = False
        wait_target_start_dt: datetime | None = None

        if (
            current.resolved.window_start_dt is not None
            and current.resolved.window_start_dt >= next_capture_at
            and current.status == "upcoming"
        ):
            resolved = current.resolved
        else:
            observe_only = True
            wait_target_start_dt = next_bucket_start

        session_id = _make_id("btc15m_terminal")
        started_at_dt = self._now()
        runtime = self._create_terminal_runtime(
            session_id=session_id,
            resolved=resolved,
            mode=normalized_mode,
            started_at_dt=started_at_dt,
            attach_mode=attach_mode,
            observe_only=observe_only,
            wait_next_target_start_dt=wait_target_start_dt,
            follow_current=False,
            paper_budget_usdc=paper_budget_usdc,
            rung_notionals_usdc=rung_notionals_usdc,
        )

        if snapshot_only:
            snapshot = self._advance_terminal_runtime(runtime)
            self._state.append_dashboard_snapshots([snapshot])
            return Btc15mTerminalResponse(
                session_id=session_id,
                started_at=_isoformat(started_at_dt),
                ended_at=_isoformat(self._now()),
                mode=normalized_mode,
                attach_mode=runtime.attach_mode,
                stop_reason="snapshot_only",
                window=runtime.resolved.window,
                total_snapshots=1,
                latest_snapshot=snapshot,
                errors=snapshot.errors,
            )
        return self._run_terminal_session(
            runtime,
            session_window_limit=session_window_limit,
            on_snapshot=on_snapshot,
            confirm_action=confirm_action,
        )

    def terminal_replay(
        self,
        *,
        session_id: str,
        on_snapshot: Callable[[Btc15mDashboardSnapshotRecord], None] | None = None,
    ) -> Btc15mTerminalReplayResponse:
        """Replay one stored BTC15m terminal session from persisted snapshots only."""
        normalized_session_id = session_id.strip()
        session = self._terminal_session_by_id(normalized_session_id)
        if session is None:
            raise Btc15mValidationError(
                f"BTC15m terminal session '{normalized_session_id}' was not found."
            )
        snapshots = self._terminal_snapshots_for_session(normalized_session_id)
        if on_snapshot is not None:
            for index, snapshot in enumerate(snapshots):
                on_snapshot(snapshot)
                if index < len(snapshots) - 1:
                    self._sleep(DEFAULT_TERMINAL_REPLAY_REFRESH_SECONDS)
        return Btc15mTerminalReplayResponse(
            session_id=normalized_session_id,
            total_snapshots=len(snapshots),
            session=session,
            first_snapshot=snapshots[0] if snapshots else None,
            latest_snapshot=snapshots[-1] if snapshots else None,
        )

    def terminal_report(
        self,
        *,
        session_id: str | None = None,
    ) -> Btc15mTerminalReportResponse:
        """Return persisted BTC15m terminal sessions newest-first or one tear sheet."""
        sessions = self._state.list_terminal_sessions()
        summary = self._build_terminal_report_summary(sessions)
        if session_id is not None:
            normalized_session_id = session_id.strip()
            session = self._terminal_session_by_id(normalized_session_id)
            if session is None:
                raise Btc15mValidationError(
                    f"BTC15m terminal session '{normalized_session_id}' was not found."
                )
            return Btc15mTerminalReportResponse(summary=summary, session=session)
        return Btc15mTerminalReportResponse(
            summary=summary,
            recent_sessions=list(reversed(sessions))[:10],
        )

    def session_arm(
        self,
        *,
        next_window: bool = False,
        mode: str = "paper",
        budget_usdc: str | None = None,
        rungs: str | None = None,
        confirm: bool = False,
    ) -> Btc15mSessionArmResponse:
        """Arm one bounded BTC15m controller session for the next eligible window."""
        if not next_window:
            raise Btc15mValidationError("BTC15m session arm currently requires --next.")
        normalized_mode = _normalize_terminal_mode(mode)
        if normalized_mode is Btc15mRunMode.LIVE and not confirm:
            raise Btc15mValidationError(
                "BTC15m live session arming requires --mode live --confirm."
            )
        active_session = self._active_controller_session()
        if active_session is not None:
            raise Btc15mValidationError(
                f"BTC15m session '{active_session.session_id}' is already active."
            )
        paper_budget_usdc, rung_notionals_usdc = _resolve_terminal_paper_sizing(
            budget_usdc=budget_usdc,
            rungs=rungs,
        )
        resolved = self._resolve_next_session_window()
        existing = self._armed_session_for_window(resolved.window.window_id)
        if existing is not None:
            if (
                existing.mode is not normalized_mode
                or existing.paper_budget_usdc != _decimal_text(paper_budget_usdc)
                or existing.rung_notionals_usdc
                != [_decimal_text(item) for item in rung_notionals_usdc]
            ):
                raise Btc15mValidationError(
                    "An armed BTC15m session already exists for that target window with "
                    "different mode or sizing."
                )
            return Btc15mSessionArmResponse(session=existing, reused_existing=True)
        conflicting_armed = self._conflicting_armed_session(resolved.window.window_id)
        if conflicting_armed is not None:
            raise Btc15mValidationError(
                f"BTC15m session '{conflicting_armed.session_id}' is already armed."
            )
        if normalized_mode is Btc15mRunMode.LIVE:
            self._enforce_live_canary_limits(
                paper_budget_usdc=paper_budget_usdc,
                rung_notionals_usdc=rung_notionals_usdc,
                resolved=resolved,
            )
            self._validate_live_session_arming(resolved)
        created_at = _isoformat(self._now())
        session = Btc15mSessionRecord(
            session_id=_make_id("btc15m_session"),
            created_at=created_at,
            updated_at=created_at,
            mode=normalized_mode,
            state=Btc15mSessionState.ARMED,
            live_confirmed=normalized_mode is Btc15mRunMode.LIVE and confirm,
            window=resolved.window,
            target_slug=resolved.target_slug,
            selection_source=resolved.selection_source,
            paper_budget_usdc=_decimal_text(paper_budget_usdc),
            rung_notionals_usdc=[_decimal_text(item) for item in rung_notionals_usdc],
        )
        self._state.upsert_session(session)
        return Btc15mSessionArmResponse(session=session)

    def session_status(self) -> Btc15mSessionStatusResponse:
        """Return the current BTC15m controller queue and active-session snapshot."""
        sessions = self._state.list_sessions()
        latest_completed_report: Btc15mSessionReportRecord | None = None
        for item in reversed(sessions):
            if item.state in {Btc15mSessionState.COMPLETED, Btc15mSessionState.STOPPED}:
                latest_completed_report = item.final_report
                break
        return Btc15mSessionStatusResponse(
            checked_at=_isoformat(self._now()),
            armed_sessions=[
                item for item in sessions if item.state is Btc15mSessionState.ARMED
            ],
            active_session=self._active_controller_session(),
            latest_completed_report=latest_completed_report,
        )

    def session_latest(self) -> Btc15mSessionLatestResponse:
        """Return the latest persisted BTC15m controller session by updated time."""
        session = self._latest_session_any()
        if session is None:
            raise Btc15mValidationError("No persisted BTC15m sessions were found.")
        return Btc15mSessionLatestResponse(
            checked_at=_isoformat(self._now()),
            session=session,
            report=session.final_report,
            canary_limits=_btc15m_canary_live_profile(),
        )

    def session_run(
        self,
        *,
        session_id: str | None = None,
        latest: bool = False,
    ) -> Btc15mSessionRunResponse:
        """Run one armed BTC15m session through exactly one window and then stop."""
        session = (
            self._session_by_id(session_id)
            if session_id is not None
            else self._latest_session_for_run()
            if latest
            else None
        )
        if session is None:
            if latest:
                raise Btc15mValidationError("No armed BTC15m session is available for --latest.")
            raise Btc15mValidationError(f"BTC15m session '{session_id}' was not found.")
        if session.state is not Btc15mSessionState.ARMED:
            raise Btc15mValidationError(
                f"BTC15m session '{session.session_id}' is not armable from state "
                f"'{session.state.value}'."
            )
        if session.mode is Btc15mRunMode.LIVE and not session.live_confirmed:
            raise Btc15mValidationError(
                f"BTC15m live session '{session.session_id}' was not confirmed at arm time."
            )
        active_session = self._active_controller_session()
        if active_session is not None and active_session.session_id != session.session_id:
            raise Btc15mValidationError(
                f"BTC15m session '{active_session.session_id}' is already active."
            )
        target_slug = session.target_slug or (
            session.window.market_slug if session.window is not None else None
        )
        if target_slug is None or not target_slug.strip():
            raise Btc15mValidationError(
                f"BTC15m session '{session_id}' does not have a target market slug."
            )
        resolved = self._resolve_window_by_slug(target_slug)
        started_at = _isoformat(self._now())
        session = session.model_copy(
            update={
                "started_at": started_at,
                "updated_at": started_at,
                "state": Btc15mSessionState.RUNNING,
            }
        )
        self._state.upsert_session(session)
        runtime = self._create_terminal_runtime(
            session_id=session.session_id,
            resolved=resolved,
            mode=session.mode,
            started_at_dt=_parse_iso_timestamp(started_at),
            attach_mode="session",
            observe_only=False,
            follow_current=False,
            arm_next=False,
            paper_budget_usdc=_decimal(session.paper_budget_usdc or "0"),
            rung_notionals_usdc=cast(
                tuple[Decimal, Decimal, Decimal],
                tuple(_decimal(item) for item in session.rung_notionals_usdc),
            ),
        )
        result = self._run_terminal_session(
            runtime,
            session_window_limit=1,
            confirm_action=(
                (lambda _message: True) if session.mode is Btc15mRunMode.LIVE else None
            ),
            should_stop=lambda: self._session_stop_requested(session.session_id),
        )
        reconcile_id: str | None = None
        reconcile_summary: dict[str, int] = {}
        report_errors = list(result.errors)
        if session.mode is Btc15mRunMode.LIVE:
            try:
                reconciliation = self._execution_watch_service.reconcile()
                reconcile_id = reconciliation.reconciliation_id
                reconcile_summary = reconciliation.summary.model_dump(mode="json")
            except Exception as exc:
                report_errors.append(_section_error("session_reconcile", exc))
        terminal_session = result.session
        latest_session = self._session_by_id(session.session_id) or session
        report = self._build_controller_session_report(
            session=latest_session,
            terminal_session=terminal_session,
            fallback_stop_reason=result.stop_reason,
            reconcile_id=reconcile_id,
            reconcile_summary=reconcile_summary,
            extra_errors=report_errors,
        )
        ended_at = _isoformat(self._now())
        final_state = report.state
        final_session = session.model_copy(
            update={
                "updated_at": ended_at,
                "ended_at": ended_at,
                "state": final_state,
                "stop_reason": report.stop_reason,
                "final_report": report,
                "errors": list(report.errors),
            }
        )
        self._state.upsert_session(final_session)
        return Btc15mSessionRunResponse(
            session=final_session,
            report=report,
            errors=list(report.errors),
        )

    def session_stop(
        self,
        *,
        session_id: str,
    ) -> Btc15mSessionStopResponse:
        """Request a safe stop for one armed or running BTC15m session."""
        session = self._session_by_id(session_id)
        if session is None:
            raise Btc15mValidationError(f"BTC15m session '{session_id}' was not found.")
        now = _isoformat(self._now())
        if session.state is Btc15mSessionState.ARMED:
            report = Btc15mSessionReportRecord(
                session_id=session.session_id,
                created_at=now,
                mode=session.mode,
                state=Btc15mSessionState.STOPPED,
                final_state="STOPPED",
                window=session.window,
                target_slug=session.target_slug,
                selection_source=session.selection_source,
                traded=False,
                observe_only=False,
                boundary_status="pending",
                stop_reason="operator_stop_before_run",
                paper_budget_usdc=session.paper_budget_usdc,
                rung_notionals_usdc=list(session.rung_notionals_usdc),
            )
            session = session.model_copy(
                update={
                    "updated_at": now,
                    "ended_at": now,
                    "state": Btc15mSessionState.STOPPED,
                    "stop_requested_at": now,
                    "stop_reason": report.stop_reason,
                    "final_report": report,
                }
            )
            self._state.upsert_session(session)
            return Btc15mSessionStopResponse(session=session)
        if session.state in {Btc15mSessionState.COMPLETED, Btc15mSessionState.STOPPED}:
            return Btc15mSessionStopResponse(session=session)
        session = session.model_copy(
            update={
                "updated_at": now,
                "state": Btc15mSessionState.STOP_REQUESTED,
                "stop_requested_at": now,
                "stop_reason": "operator_stop_requested",
            }
        )
        self._state.upsert_session(session)
        return Btc15mSessionStopResponse(session=session)

    def session_report(
        self,
        *,
        session_id: str | None = None,
        latest: bool = False,
    ) -> Btc15mSessionReportResponse:
        """Return one persisted BTC15m controller-session report."""
        session = (
            self._session_by_id(session_id)
            if session_id is not None
            else self._latest_session_for_report()
            if latest
            else None
        )
        if session is None:
            if latest:
                raise Btc15mValidationError(
                    "No completed BTC15m session with a final report is available for --latest."
                )
            raise Btc15mValidationError(f"BTC15m session '{session_id}' was not found.")
        if session.final_report is None:
            raise Btc15mValidationError(
                f"BTC15m session '{session.session_id}' has not produced a final report yet."
            )
        return Btc15mSessionReportResponse(report=session.final_report)

    def live_check(self) -> Btc15mLiveCheckResponse:
        """Run a read-only BTC15m canary live-readiness checklist."""
        checked_at = _isoformat(self._now())
        canary_limits = _btc15m_canary_live_profile()
        checks: list[Btc15mReasonBlock] = []
        errors: list[Btc15mSectionError] = []

        auth = self._auth_service.show().auth
        balance_view = None
        allowance_view = None
        geoblock = self._auth_service.check_geoblock()
        risk_policy = None
        target_window = None
        active_session = self._active_controller_session()

        if auth.signer_address is not None:
            checks.append(
                Btc15mReasonBlock(
                    section="signer_profile",
                    status="pass",
                    message=(
                        f"Signer {auth.signer_address} resolved with funder "
                        f"{auth.funder_address or '-'}."
                    ),
                )
            )
        else:
            checks.append(
                Btc15mReasonBlock(
                    section="signer_profile",
                    status="fail",
                    message="Signer and profile context could not be resolved.",
                )
            )
            errors.append(
                Btc15mSectionError(
                    section="signer_profile",
                    code="invalid_argument",
                    message="Signer and profile context could not be resolved.",
                )
            )

        try:
            balance_view = self._auth_service.balances().balance_view
            checks.append(
                Btc15mReasonBlock(
                    section="balances",
                    status="pass",
                    message=(
                        "Authenticated balance read succeeded"
                        f" ({balance_view.balance or '-'} available)."
                    ),
                )
            )
        except (AuthValidationError, AuthClientError) as exc:
            checks.append(
                Btc15mReasonBlock(section="balances", status="fail", message=str(exc))
            )
            errors.append(_section_error("balances", exc))

        try:
            allowance_view = self._auth_service.allowances().allowance_view
            checks.append(
                Btc15mReasonBlock(
                    section="allowances",
                    status="pass",
                    message=(
                        "Authenticated allowance read succeeded"
                        f" ({allowance_view.allowance or '-'} ready)."
                    ),
                )
            )
        except (AuthValidationError, AuthClientError) as exc:
            checks.append(
                Btc15mReasonBlock(section="allowances", status="fail", message=str(exc))
            )
            errors.append(_section_error("allowances", exc))

        if geoblock.checked and geoblock.blocked is False:
            checks.append(
                Btc15mReasonBlock(
                    section="geoblock",
                    status="pass",
                    message=geoblock.message or "Official geoblock check reported allowed access.",
                )
            )
        elif geoblock.checked and geoblock.blocked is True:
            message = geoblock.message or "Official geoblock check reported blocked access."
            checks.append(Btc15mReasonBlock(section="geoblock", status="fail", message=message))
            errors.append(
                Btc15mSectionError(section="geoblock", code="geoblocked", message=message)
            )
        else:
            message = geoblock.message or "Official geoblock check could not be verified."
            checks.append(Btc15mReasonBlock(section="geoblock", status="warn", message=message))
            errors.append(
                Btc15mSectionError(section="geoblock", code="request_failed", message=message)
            )

        if active_session is None:
            checks.append(
                Btc15mReasonBlock(
                    section="session_conflict",
                    status="pass",
                    message="No active BTC15m controller session is blocking live arming.",
                )
            )
        else:
            conflict_message = (
                f"Active BTC15m session '{active_session.session_id}' is already running."
            )
            checks.append(
                Btc15mReasonBlock(
                    section="session_conflict",
                    status="fail",
                    message=conflict_message,
                )
            )
            errors.append(
                Btc15mSectionError(
                    section="session_conflict",
                    code="conflict",
                    message=conflict_message,
                )
            )

        try:
            risk_policy = self._risk_service.get_policy(BTC15M_STRATEGY_NAME)
            checks.append(
                Btc15mReasonBlock(
                    section="risk_policy",
                    status="pass",
                    message=(
                        "Effective BTC15m risk policy resolved"
                        f" ({risk_policy.strategy_name})."
                    ),
                )
            )
        except (RiskStateError, Exception) as exc:
            checks.append(Btc15mReasonBlock(section="risk_policy", status="fail", message=str(exc)))
            errors.append(_section_error("risk_policy", exc))

        try:
            target_window = self._resolve_next_session_window().window
            checks.append(
                Btc15mReasonBlock(
                    section="target_window",
                    status="pass",
                    message=f"Next eligible BTC15m window resolved as {target_window.market_slug}.",
                )
            )
        except Exception as exc:
            checks.append(
                Btc15mReasonBlock(section="target_window", status="fail", message=str(exc))
            )
            errors.append(_section_error("target_window", exc))

        checks.append(
            Btc15mReasonBlock(
                section="canary_limits",
                status="pass" if canary_limits.default_sizing_fits else "warn",
                message=(
                    "Default sizing fits the BTC15m canary live profile."
                    if canary_limits.default_sizing_fits
                    else "Default BTC15m sizing exceeds the canary live profile; pass smaller "
                    "--budget-usdc/--rungs for live arming."
                ),
            )
        )

        ready = (
            auth.signer_address is not None
            and balance_view is not None
            and allowance_view is not None
            and geoblock.checked
            and geoblock.blocked is False
            and active_session is None
            and risk_policy is not None
            and target_window is not None
        )
        return Btc15mLiveCheckResponse(
            checked_at=checked_at,
            ready=ready,
            auth=auth,
            balance_view=balance_view,
            allowance_view=allowance_view,
            geoblock=geoblock,
            risk_policy=risk_policy,
            checks=checks,
            target_window=target_window,
            canary_limits=canary_limits,
            active_session=active_session,
            errors=errors,
        )

    def bundle(self, *, session_id: str) -> Btc15mSessionBundleResponse:
        """Assemble one local persisted post-session BTC15m controller bundle."""
        from pm.portfolio.state import PortfolioStateError

        session = self._session_by_id(session_id)
        if session is None:
            raise Btc15mValidationError(f"BTC15m session '{session_id}' was not found.")
        if session.final_report is None:
            raise Btc15mValidationError(
                f"BTC15m session '{session_id}' has not produced a final report yet."
            )
        report = session.final_report
        notes: list[str] = []
        errors: list[Btc15mSectionError] = []
        try:
            order_plans_all = self._execution_state.list_order_plans()
            order_results_all = self._execution_state.list_order_results()
            execution_events_all = self._execution_state.list_execution_events()
            reconciliations = self._execution_state.list_reconciliations()
        except ExecutionStateError as exc:
            raise Btc15mStateError(str(exc)) from exc
        try:
            portfolio_reconciliations = self._portfolio_state.list_reconciliations()
        except PortfolioStateError as exc:
            raise Btc15mStateError(str(exc)) from exc

        order_ids = {
            item.order_id.strip()
            for item in report.rung_outcomes
            if item.order_id is not None and item.order_id.strip()
        }
        if not order_ids:
            notes.append("No rung order ids were recorded for this session.")
        target_market = report.window.condition_id if report.window is not None else None
        target_token_id = report.target_token_id
        order_plans = [
            item
            for item in order_plans_all
            if (
                (item.order_id is not None and item.order_id in order_ids)
                or (
                    item.action == "cancel_market"
                    and target_market is not None
                    and item.market == target_market
                    and target_token_id is not None
                    and item.token_id == target_token_id
                )
            )
        ]
        plan_ids = {item.plan_id for item in order_plans}
        order_results = [item for item in order_results_all if item.plan_id in plan_ids]
        execution_events = [
            item
            for item in execution_events_all
            if item.order_id is not None and item.order_id in order_ids
        ]
        execution_reconciliation = (
            next(
                (
                    item
                    for item in reversed(reconciliations)
                    if item.reconciliation_id == report.execution_reconciliation_id
                ),
                None,
            )
            if report.execution_reconciliation_id is not None
            else None
        )
        if report.execution_reconciliation_id is not None and execution_reconciliation is None:
            notes.append(
                "Execution reconciliation "
                f"'{report.execution_reconciliation_id}' was not found locally."
            )
        portfolio_reconciliation = (
            next(
                (
                    item
                    for item in reversed(portfolio_reconciliations)
                    if item.execution_reconciliation_id == report.execution_reconciliation_id
                ),
                None,
            )
            if report.execution_reconciliation_id is not None
            else None
        )
        if portfolio_reconciliation is None:
            notes.append(
                "No matching persisted portfolio reconciliation was found for this session."
            )
        return Btc15mSessionBundleResponse(
            session=session,
            report=report,
            order_plans=order_plans,
            order_results=order_results,
            execution_events=execution_events,
            execution_reconciliation=execution_reconciliation,
            portfolio_reconciliation=portfolio_reconciliation,
            notes=notes,
            errors=errors,
        )

    def _build_terminal_report_summary(
        self,
        sessions: list[Btc15mTerminalSessionRecord],
    ) -> Btc15mTerminalReportSummary:
        """Summarize persisted terminal sessions."""
        total_pnl = Decimal("0")
        resolved_count = 0
        skipped_count = 0
        paper_count = 0
        live_count = 0
        observe_only_count = 0
        waiting_count = 0
        pnl_items = 0
        for item in sessions:
            if item.mode is Btc15mRunMode.PAPER:
                paper_count += 1
            else:
                live_count += 1
            if item.observe_only:
                observe_only_count += 1
            if item.attach_mode == "wait_next":
                waiting_count += 1
            if item.final_state is Btc15mTerminalState.RESOLVED:
                resolved_count += 1
            if item.final_state is Btc15mTerminalState.SKIPPED:
                skipped_count += 1
            if item.latest_evaluation is not None:
                total_pnl += _decimal(item.latest_evaluation.realized_pnl_usdc)
                pnl_items += 1
        average_pnl = total_pnl / Decimal(pnl_items) if pnl_items else Decimal("0")
        return Btc15mTerminalReportSummary(
            terminal_session_count=len(sessions),
            paper_session_count=paper_count,
            live_session_count=live_count,
            observe_only_session_count=observe_only_count,
            waiting_session_count=waiting_count,
            resolved_session_count=resolved_count,
            skipped_session_count=skipped_count,
            total_realized_pnl_usdc=_decimal_text(total_pnl),
            average_realized_pnl_usdc=_decimal_text(average_pnl),
        )

    def _run_terminal_session(
        self,
        runtime: _TerminalRuntime,
        *,
        session_window_limit: int | None = 1,
        on_snapshot: Callable[[Btc15mDashboardSnapshotRecord], None] | None = None,
        confirm_action: Callable[[str], bool | None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Btc15mTerminalResponse:
        """Run a bounded terminal session until the active phase completes."""
        snapshots: list[Btc15mDashboardSnapshotRecord] = []

        try:
            while True:
                iteration_started = self._now()
                snapshot = self._advance_terminal_runtime(runtime, confirm_action=confirm_action)
                snapshots.append(snapshot)
                self._state.append_dashboard_snapshots([snapshot])
                if on_snapshot is not None:
                    on_snapshot(snapshot)
                if self._terminal_runtime_complete(runtime, iteration_started):
                    if not runtime.window_finalized:
                        runtime.tear_sheets.append(
                            self._finalize_terminal_window(
                                runtime,
                                total_snapshots=runtime.current_window_snapshots,
                            )
                        )
                    should_continue = runtime.follow_current and (
                        session_window_limit is None
                        or len(runtime.tear_sheets) < session_window_limit
                    )
                    if should_continue and self._roll_terminal_session_forward(runtime):
                        continue
                    if runtime.stop_reason == "running":
                        runtime.stop_reason = "session_complete"
                    break
                if should_stop is not None and should_stop():
                    if runtime.stop_reason == "running":
                        runtime.stop_reason = "session_stop_requested"
                    self._record_terminal_event(
                        runtime,
                        kind="session",
                        status="info",
                        message="BTC15m session stop requested at a safe checkpoint.",
                    )
                    break
                remaining = DEFAULT_DASHBOARD_REFRESH_SECONDS - max(
                    0.0,
                    (self._now() - iteration_started).total_seconds(),
                )
                if remaining > 0:
                    self._sleep(remaining)
        except KeyboardInterrupt:
            runtime.stop_reason = "operator_interrupt"
            self._record_terminal_event(
                runtime,
                kind="session",
                status="info",
                message="Operator interrupted the BTC15m terminal session.",
            )
            if runtime.current_window_snapshots > 0 and not runtime.window_finalized:
                runtime.tear_sheets.append(
                    self._finalize_terminal_window(
                        runtime,
                        total_snapshots=runtime.current_window_snapshots,
                    )
                )

        session = self._finalize_terminal_session(runtime)
        self._state.append_terminal_session(session)
        return Btc15mTerminalResponse(
            session_id=runtime.session_id,
            started_at=_isoformat(runtime.started_at_dt),
            ended_at=_isoformat(self._now()),
            mode=runtime.mode,
            attach_mode=runtime.attach_mode,
            stop_reason=session.stop_reason,
            window=session.window,
            total_snapshots=runtime.total_snapshots,
            latest_snapshot=snapshots[-1] if snapshots else None,
            session=session,
            errors=session.errors,
        )

    def _terminal_session_by_id(self, session_id: str) -> Btc15mTerminalSessionRecord | None:
        """Return one persisted terminal session by identifier."""
        for item in reversed(self._state.list_terminal_sessions()):
            if item.session_id == session_id:
                return item
        return None

    def _session_by_id(self, session_id: str) -> Btc15mSessionRecord | None:
        """Return one persisted controller session by identifier."""
        normalized = session_id.strip()
        for item in reversed(self._state.list_sessions()):
            if item.session_id == normalized:
                return item
        return None

    def _active_controller_session(self) -> Btc15mSessionRecord | None:
        """Return the currently active controller session, if any."""
        for item in reversed(self._state.list_sessions()):
            if item.state in {Btc15mSessionState.RUNNING, Btc15mSessionState.STOP_REQUESTED}:
                return item
        return None

    def _armed_session_for_window(self, window_id: str) -> Btc15mSessionRecord | None:
        """Return an armed controller session for one target window, if any."""
        for item in reversed(self._state.list_sessions()):
            if item.state is not Btc15mSessionState.ARMED or item.window is None:
                continue
            if item.window.window_id == window_id:
                return item
        return None

    def _conflicting_armed_session(self, window_id: str) -> Btc15mSessionRecord | None:
        """Return an armed controller session for a different target window, if any."""
        for item in reversed(self._state.list_sessions()):
            if item.state is not Btc15mSessionState.ARMED or item.window is None:
                continue
            if item.window.window_id != window_id:
                return item
        return None

    def _session_stop_requested(self, session_id: str) -> bool:
        """Return whether one controller session has a persisted stop request."""
        session = self._session_by_id(session_id)
        if session is None:
            return False
        return session.state is Btc15mSessionState.STOP_REQUESTED

    def _resolve_next_session_window(self) -> _ResolvedWindow:
        """Resolve the exact next BTC15m bucket that can be armed pre-start."""
        now = self._now()
        next_bucket_start = _floor_btc15m_window_start(now) + WINDOW_DURATION
        resolved = self._resolve_window_by_bucket_start(
            next_bucket_start,
            selection_source="session_next_exact",
        )
        if resolved is None:
            raise Btc15mOperatorHintError(
                "Could not resolve the next eligible BTC15m market for session arming.",
                hint={
                    "next_steps": [
                        "pm market recurring list --query btc --interval 15m",
                        "pm strategy btc15m session arm --next --mode paper",
                    ]
                },
            )
        if resolved.window_start_dt is None or resolved.window_start_dt <= now:
            raise Btc15mValidationError("BTC15m session arming is pre-start only.")
        return resolved

    def _validate_live_session_arming(self, resolved: _ResolvedWindow) -> None:
        """Run non-mutating live-execution readiness checks for one BTC15m session arm."""
        market_ref = (resolved.window.condition_id or resolved.window.market_slug).strip()
        if not market_ref:
            raise Btc15mValidationError(
                "BTC15m live session arming requires a resolved condition id or market slug."
            )
        for outcome in ("up", "down"):
            try:
                preview = self._dry_run_service.plan_order(
                    market_ref=market_ref,
                    outcome=outcome,
                    side="buy",
                    price="0.30",
                    size="1",
                )
            except ExecutionValidationError as exc:
                raise Btc15mValidationError(
                    f"BTC15m live session preflight failed for {outcome}: {exc}"
                ) from exc
            except Exception as exc:
                raise Btc15mValidationError(
                    "BTC15m live session preflight could not validate the existing "
                    f"execution stack for {outcome}: {exc}"
                ) from exc
            if preview.decision != "WOULD_POST":
                failing_reason = next(
                    (
                        item.message
                        for item in preview.reasons
                        if getattr(item, "status", "") == "fail"
                    ),
                    "Live execution preflight did not approve order posting.",
                )
                raise Btc15mValidationError(
                    f"BTC15m live session preflight failed for {outcome}: {failing_reason}"
                )
        try:
            self._order_lifecycle.orders_open(market=resolved.window.condition_id)
        except ExecutionValidationError as exc:
            raise Btc15mValidationError(
                f"BTC15m live session preflight could not verify authenticated open-order "
                f"reads: {exc}"
            ) from exc
        except Exception as exc:
            raise Btc15mValidationError(
                "BTC15m live session preflight could not verify authenticated open-order "
                f"reads: {exc}"
            ) from exc

    def _enforce_live_canary_limits(
        self,
        *,
        paper_budget_usdc: Decimal,
        rung_notionals_usdc: tuple[Decimal, Decimal, Decimal],
        resolved: _ResolvedWindow,
    ) -> None:
        """Apply the fixed low-risk live caps for BTC15m controller sessions."""
        if paper_budget_usdc > BTC15M_CANARY_MAX_LIVE_USDC:
            raise Btc15mValidationError(
                "BTC15m live session budget exceeds the canary cap of "
                f"{_decimal_text(BTC15M_CANARY_MAX_LIVE_USDC)} USDC."
            )
        for rung in rung_notionals_usdc:
            if rung > BTC15M_CANARY_MAX_RUNG_USDC:
                raise Btc15mValidationError(
                    "BTC15m live rung notional exceeds the canary cap of "
                    f"{_decimal_text(BTC15M_CANARY_MAX_RUNG_USDC)} USDC."
                )
        if resolved.window_start_dt is None or resolved.window_start_dt <= self._now():
            raise Btc15mValidationError(
                "BTC15m live canary sessions remain bounded to one pre-start window only."
            )

    def _latest_session_any(self) -> Btc15mSessionRecord | None:
        sessions = self._state.list_sessions()
        if not sessions:
            return None
        return max(
            sessions,
            key=lambda item: _parse_iso_timestamp(item.updated_at or item.created_at),
        )

    def _latest_session_for_run(self) -> Btc15mSessionRecord | None:
        sessions = [
            item for item in self._state.list_sessions() if item.state is Btc15mSessionState.ARMED
        ]
        if not sessions:
            return None
        return max(
            sessions,
            key=lambda item: _parse_iso_timestamp(item.updated_at or item.created_at),
        )

    def _latest_session_for_report(self) -> Btc15mSessionRecord | None:
        sessions = [
            item
            for item in self._state.list_sessions()
            if item.final_report is not None
            and item.state in {Btc15mSessionState.COMPLETED, Btc15mSessionState.STOPPED}
        ]
        if not sessions:
            return None
        return max(
            sessions,
            key=lambda item: _parse_iso_timestamp(item.updated_at or item.created_at),
        )

    def _build_controller_session_report(
        self,
        *,
        session: Btc15mSessionRecord,
        terminal_session: Btc15mTerminalSessionRecord | None,
        fallback_stop_reason: str,
        reconcile_id: str | None,
        reconcile_summary: dict[str, int],
        extra_errors: list[Btc15mSectionError],
    ) -> Btc15mSessionReportRecord:
        """Project one completed runtime into the controller-session report shape."""
        latest_window = (
            terminal_session.window_tear_sheets[-1]
            if terminal_session is not None and terminal_session.window_tear_sheets
            else None
        )
        latest_evaluation = (
            latest_window.latest_evaluation
            if latest_window is not None
            else terminal_session.latest_evaluation
            if terminal_session is not None
            else None
        )
        stop_requested = self._session_stop_requested(session.session_id)
        final_state = (
            Btc15mSessionState.STOPPED if stop_requested else Btc15mSessionState.COMPLETED
        )
        stop_reason = (
            session.stop_reason
            if stop_requested and session.stop_reason is not None
            else fallback_stop_reason
        )
        traded = latest_evaluation is not None and latest_evaluation.decision in {"UP", "DOWN"}
        return Btc15mSessionReportRecord(
            session_id=session.session_id,
            created_at=_isoformat(self._now()),
            mode=session.mode,
            state=final_state,
            final_state=(
                latest_window.final_state.value
                if latest_window is not None
                else terminal_session.final_state.value
                if terminal_session is not None
                else None
            ),
            window=session.window,
            target_slug=session.target_slug,
            selection_source=session.selection_source,
            traded=traded,
            observe_only=(
                latest_window.observe_only
                if latest_window is not None
                else terminal_session.observe_only
                if terminal_session is not None
                else False
            ),
            boundary_status=(
                latest_window.boundary_status
                if latest_window is not None
                else terminal_session.boundary_status
                if terminal_session is not None
                else "pending"
            ),
            stop_reason=stop_reason,
            selected_side=(
                latest_window.selected_side
                if latest_window is not None
                else terminal_session.selected_side
                if terminal_session is not None
                else None
            ),
            target_token_id=(
                latest_window.target_token_id
                if latest_window is not None
                else terminal_session.target_token_id
                if terminal_session is not None
                else None
            ),
            target_outcome=(
                latest_window.target_outcome
                if latest_window is not None
                else terminal_session.target_outcome
                if terminal_session is not None
                else None
            ),
            paper_budget_usdc=session.paper_budget_usdc,
            rung_notionals_usdc=list(session.rung_notionals_usdc),
            avg_entry_price=(
                latest_window.avg_entry_price
                if latest_window is not None
                else terminal_session.avg_entry_price
                if terminal_session is not None
                else None
            ),
            exposure_quantity=(
                latest_window.exposure_quantity
                if latest_window is not None
                else terminal_session.exposure_quantity
                if terminal_session is not None
                else None
            ),
            exposure_notional_usdc=(
                latest_window.exposure_notional_usdc
                if latest_window is not None
                else terminal_session.exposure_notional_usdc
                if terminal_session is not None
                else None
            ),
            realized_pnl_usdc=(
                latest_evaluation.realized_pnl_usdc if latest_evaluation is not None else None
            ),
            mfe_usdc=(
                latest_window.mfe_usdc
                if latest_window is not None
                else terminal_session.latest_evaluation.mfe_usdc
                if terminal_session is not None and terminal_session.latest_evaluation is not None
                else None
            ),
            mae_usdc=(
                latest_window.mae_usdc
                if latest_window is not None
                else terminal_session.latest_evaluation.mae_usdc
                if terminal_session is not None and terminal_session.latest_evaluation is not None
                else None
            ),
            skip_reasons=(
                list(latest_window.skip_reasons)
                if latest_window is not None
                else list(
                    terminal_session.manipulation_flags
                    if terminal_session is not None
                    else []
                )
            ),
            rung_outcomes=(
                list(latest_window.rungs)
                if latest_window is not None
                else list(terminal_session.rungs if terminal_session is not None else [])
            ),
            latest_evaluation=latest_evaluation,
            execution_reconciliation_id=reconcile_id,
            execution_reconciliation_summary=reconcile_summary,
            errors=list(extra_errors),
        )

    def _terminal_snapshots_for_session(
        self,
        session_id: str,
    ) -> list[Btc15mDashboardSnapshotRecord]:
        """Return terminal snapshots for one persisted session."""
        return [
            item
            for item in self._state.list_dashboard_snapshots()
            if item.session_id == session_id and item.view_kind == "terminal"
        ]

    def auto_roll(
        self,
        *,
        hours: str,
        mode: str = "paper",
    ) -> Btc15mAutoRollResponse:
        """Run one bounded current-window BTC15m auto-roll session."""
        normalized_mode = _require_paper_mode(mode)
        requested = _decimal(hours)
        if requested <= 0:
            raise Btc15mValidationError("Auto-roll hours must be greater than zero.")
        started_at_dt = self._now()
        deadline = started_at_dt + timedelta(seconds=float(requested * Decimal("3600")))
        run_id = _make_id("btc15m_auto_roll")
        items: list[Btc15mPaperEvaluation] = []
        errors: list[Btc15mSectionError] = []
        seen_window_ids: set[str] = set()
        stop_reason = "deadline_reached"

        while True:
            if self._now() >= deadline:
                stop_reason = "deadline_reached"
                break
            try:
                current = self._resolve_current_window()
            except Btc15mOperatorHintError as exc:
                errors.append(
                    Btc15mSectionError(
                        section="resolve_current",
                        code="invalid_argument",
                        message=str(exc),
                    )
                )
                stop_reason = "no_candidate"
                break
            resolved = current.resolved
            if resolved.window.window_id in seen_window_ids:
                remaining = int((deadline - self._now()).total_seconds())
                if remaining <= DEFAULT_CAMPAIGN_WAIT_SECONDS:
                    stop_reason = "deadline_reached"
                    break
                self._sleep(min(DEFAULT_CAMPAIGN_WAIT_SECONDS, remaining))
                continue
            if not self._can_complete_window_before(resolved, deadline):
                stop_reason = "insufficient_remaining_time"
                break

            seen_window_ids.add(resolved.window.window_id)
            artifacts = self._record_and_evaluate_window(
                resolved,
                seconds=self._targeted_record_seconds(resolved),
                recorder_session_id=_make_id("btc15m_record"),
                evaluation_source_kind="auto_roll",
                persist_paper_run=True,
                mode=normalized_mode,
            )
            if artifacts.evaluation is not None:
                items.append(artifacts.evaluation)
            errors.extend(artifacts.record.errors)

        total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in items), Decimal("0"))
        run = Btc15mAutoRollRunRecord(
            run_id=run_id,
            created_at=_isoformat(started_at_dt),
            started_at=_isoformat(started_at_dt),
            ended_at=_isoformat(self._now()),
            requested_hours=_decimal_text(requested),
            mode=normalized_mode,
            stop_reason=stop_reason,
            items=items,
            total_windows=len(items),
            total_skipped=sum(1 for item in items if item.decision == "SKIP"),
            total_realized_pnl_usdc=_decimal_text(total_pnl),
            errors=errors,
        )
        self._state.append_auto_roll_run(run)
        return Btc15mAutoRollResponse(run=run)

    def liquidity_sample(
        self,
        *,
        seconds: int = DEFAULT_LIQUIDITY_SAMPLE_SECONDS,
    ) -> Btc15mLiquiditySampleResponse:
        """Collect bounded BTC15m Binance and Polymarket liquidity samples."""
        if seconds <= 0:
            raise Btc15mValidationError(
                "Liquidity sample duration must be greater than zero seconds."
            )

        session_id = _make_id("btc15m_liquidity")
        started_at_dt = self._now()
        started_at = _isoformat(started_at_dt)
        resolved = self._resolve_latest_window()
        items: list[Btc15mLiquiditySampleRecord] = []
        errors: list[Btc15mSectionError] = []

        elapsed = 0
        while elapsed < seconds:
            scheduled_at_dt = started_at_dt + timedelta(seconds=elapsed)
            sample = self._capture_liquidity_sample(
                resolved,
                sample_kind="operator",
                scheduled_at_dt=scheduled_at_dt,
            )
            items.append(sample)
            errors.extend(sample.errors)
            elapsed += DEFAULT_LIQUIDITY_SAMPLE_CADENCE_SECONDS
            if elapsed < seconds:
                self._sleep(DEFAULT_LIQUIDITY_SAMPLE_CADENCE_SECONDS)

        self._state.append_liquidity_samples(items)
        return Btc15mLiquiditySampleResponse(
            session_id=session_id,
            started_at=started_at,
            ended_at=_isoformat(self._now()),
            requested_seconds=seconds,
            items=items,
            total=len(items),
            errors=errors,
        )

    def paper_run(
        self,
        *,
        limit: int = DEFAULT_PAPER_RUN_LIMIT,
        slug: str | None = None,
        mode: str = "paper",
    ) -> Btc15mPaperRunResponse:
        """Evaluate recorded windows or run one explicit live-data paper window."""
        normalized_mode = _require_paper_mode(mode)
        normalized_slug = _normalize_optional_slug(slug)
        if limit <= 0:
            raise Btc15mValidationError("Paper-run limit must be greater than zero.")

        if normalized_slug is not None:
            resolved = self._resolve_window_by_slug(normalized_slug)
            evaluation, errors = self._run_targeted_paper_window(
                resolved,
                recorder_session_id=_make_id("btc15m_record"),
                source_kind="manual",
            )
            items = [evaluation] if evaluation is not None else []
            total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in items), Decimal("0"))
            run = Btc15mPaperRunRecord(
                run_id=_make_id("btc15m_paper_run"),
                created_at=_isoformat(self._now()),
                limit=1,
                mode=normalized_mode,
                target_slug=normalized_slug,
                selection_source=resolved.selection_source,
                source_kind="manual",
                items=items,
                total_considered=1,
                total_evaluated=len(items),
                total_skipped=1 if not items or items[0].decision == "SKIP" else 0,
                total_realized_pnl_usdc=_decimal_text(total_pnl),
                errors=errors,
            )
            self._state.append_paper_run(run)
            return Btc15mPaperRunResponse(run=run)

        evaluated_ids = {
            item.window_id for run in self._state.list_paper_runs() for item in run.items
        }
        candidates = [
            record
            for record in self._iter_latest_windows()
            if record.status == "complete" and record.window.window_id not in evaluated_ids
        ]
        candidates.sort(
            key=lambda item: (_sort_time(item.window.window_start_at), item.window.window_id)
        )
        selected = candidates[:limit]
        items = [self._evaluate_window(record) for record in selected]
        total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in items), Decimal("0"))
        run = Btc15mPaperRunRecord(
            run_id=_make_id("btc15m_paper_run"),
            created_at=_isoformat(self._now()),
            limit=limit,
            mode=normalized_mode,
            target_slug=None,
            selection_source="recorded",
            source_kind="manual",
            items=items,
            total_considered=len(candidates),
            total_evaluated=len(items),
            total_skipped=sum(1 for item in items if item.decision == "SKIP"),
            total_realized_pnl_usdc=_decimal_text(total_pnl),
        )
        self._state.append_paper_run(run)
        return Btc15mPaperRunResponse(run=run)

    def campaign_next_window(
        self,
        *,
        previous_condition_id: str | None = None,
        slug: str | None = None,
        mode: str = "paper",
        max_wait_seconds: int = DEFAULT_CAMPAIGN_MAX_WAIT_SECONDS,
    ) -> Btc15mCampaignNextWindowResponse:
        """Return the current unresolved BTC15m window or wait for the next distinct one."""
        normalized_mode = _require_paper_mode(mode)
        normalized_slug = _normalize_optional_slug(slug)
        checked_at = _isoformat(self._now())
        wait_started = self._now()
        poll_count = 0
        if normalized_slug is not None:
            resolved = self._resolve_window_by_slug(normalized_slug)
            if resolved.window_end_dt is not None and self._now() > resolved.window_end_dt:
                raise Btc15mOperatorHintError(
                    (
                        "The targeted BTC15m market window is already expired. "
                        "Use a current market slug or run a bounded paper record first."
                    ),
                    identifier=normalized_slug,
                    hint={
                        "next_steps": [
                            "pm market recurring list --query btc --interval 15m",
                            "pm strategy btc15m paper-run --slug <market_slug> --mode paper",
                        ]
                    },
                )
            return Btc15mCampaignNextWindowResponse(
                checked_at=checked_at,
                mode=normalized_mode,
                target_slug=normalized_slug,
                selection_source=resolved.selection_source,
                waited_seconds=0,
                timed_out=False,
                poll_count=poll_count,
                window=resolved.window,
            )

        current = self._resolve_latest_window()
        if (
            self._is_unresolved_window(current)
            and current.window.condition_id != previous_condition_id
        ):
            return Btc15mCampaignNextWindowResponse(
                checked_at=checked_at,
                mode=normalized_mode,
                target_slug=None,
                selection_source=current.selection_source,
                waited_seconds=0,
                timed_out=False,
                poll_count=poll_count,
                window=current.window,
            )

        anchor_condition_id = current.window.condition_id
        while (self._now() - wait_started).total_seconds() < max_wait_seconds:
            remaining = max_wait_seconds - int((self._now() - wait_started).total_seconds())
            self._sleep(min(DEFAULT_CAMPAIGN_WAIT_SECONDS, max(1, remaining)))
            poll_count += 1
            current = self._resolve_latest_window()
            if not self._is_unresolved_window(current):
                continue
            if current.window.condition_id in {previous_condition_id, anchor_condition_id}:
                continue
            return Btc15mCampaignNextWindowResponse(
                checked_at=_isoformat(self._now()),
                mode=normalized_mode,
                target_slug=None,
                selection_source=current.selection_source,
                waited_seconds=int((self._now() - wait_started).total_seconds()),
                timed_out=False,
                poll_count=poll_count,
                window=current.window,
            )

        return Btc15mCampaignNextWindowResponse(
            checked_at=_isoformat(self._now()),
            mode=normalized_mode,
            target_slug=None,
            selection_source="recurring",
            waited_seconds=int((self._now() - wait_started).total_seconds()),
            timed_out=True,
            poll_count=poll_count,
            window=None,
            errors=[
                Btc15mSectionError(
                    section="campaign_next_window",
                    code="timed_out",
                    message=(
                        "No next distinct BTC15m window became available before the wait limit."
                    ),
                )
            ],
        )

    def campaign_run(
        self,
        *,
        hours: str,
        slug: str | None = None,
        mode: str = "paper",
    ) -> Btc15mCampaignRunResponse:
        """Run a bounded sequential BTC15m campaign."""
        normalized_mode = _require_paper_mode(mode)
        normalized_slug = _normalize_optional_slug(slug)
        requested_hours = _decimal(hours)
        if requested_hours <= 0:
            raise Btc15mValidationError("Campaign hours must be greater than zero.")

        started_at_dt = self._now()
        deadline = started_at_dt + timedelta(seconds=float(requested_hours * Decimal("3600")))
        run_id = _make_id("btc15m_campaign")
        items: list[Btc15mPaperEvaluation] = []
        errors: list[Btc15mSectionError] = []
        previous_condition_id: str | None = None
        stop_reason = "deadline_reached"

        while True:
            remaining_seconds = int((deadline - self._now()).total_seconds())
            if remaining_seconds <= 0:
                stop_reason = "deadline_reached"
                break
            next_window = self.campaign_next_window(
                previous_condition_id=previous_condition_id,
                slug=normalized_slug,
                mode=normalized_mode,
                max_wait_seconds=min(DEFAULT_CAMPAIGN_MAX_WAIT_SECONDS, remaining_seconds),
            )
            errors.extend(next_window.errors)
            if next_window.window is None:
                stop_reason = "no_candidate"
                break
            resolved = self._resolve_window_by_slug(next_window.window.market_slug)
            if resolved.window_end_dt is None:
                errors.append(
                    Btc15mSectionError(
                        section="campaign_run",
                        code="invalid_argument",
                        message="Could not resolve the campaign window end time.",
                    )
                )
                stop_reason = "missing_timing"
                break
            required_end = resolved.window_end_dt + timedelta(seconds=DEFAULT_POST_END_WAIT_SECONDS)
            if required_end > deadline:
                stop_reason = "insufficient_remaining_time"
                break

            artifacts = self._record_and_evaluate_window(
                resolved,
                seconds=max(1, int((required_end - self._now()).total_seconds())),
                recorder_session_id=run_id,
                evaluation_source_kind="campaign",
                campaign_run_id=run_id,
                persist_paper_run=True,
            )
            previous_condition_id = artifacts.record.window.condition_id
            if artifacts.evaluation is not None:
                items.append(artifacts.evaluation)
            if normalized_slug is not None:
                stop_reason = "completed_target_window"
                break

        if not items and normalized_slug is not None and stop_reason == "deadline_reached":
            stop_reason = "insufficient_remaining_time"

        total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in items), Decimal("0"))
        campaign = Btc15mCampaignRunRecord(
            run_id=run_id,
            created_at=_isoformat(started_at_dt),
            started_at=_isoformat(started_at_dt),
            ended_at=_isoformat(self._now()),
            requested_hours=_decimal_text(requested_hours),
            mode=normalized_mode,
            target_slug=normalized_slug,
            selection_source="slug" if normalized_slug is not None else "recurring",
            stop_reason=stop_reason,
            items=items,
            total_windows=len(items),
            total_skipped=sum(1 for item in items if item.decision == "SKIP"),
            total_realized_pnl_usdc=_decimal_text(total_pnl),
            errors=errors,
        )
        self._state.append_campaign_run(campaign)
        return Btc15mCampaignRunResponse(campaign=campaign)

    def campaign_report(self) -> Btc15mCampaignReportResponse:
        """Return a campaign-only BTC15m report."""
        campaigns = self._state.list_campaign_runs()
        evaluations = [item for run in campaigns for item in run.items]
        return Btc15mCampaignReportResponse(
            summary=self._build_campaign_summary(campaigns=campaigns, evaluations=evaluations),
            recent_runs=list(reversed(campaigns))[:5],
            recent_evaluations=list(reversed(evaluations))[:10],
        )

    def report(self) -> Btc15mReportResponse:
        """Return an aggregate BTC15m recorder and paper-evaluation report."""
        windows = list(self._iter_latest_windows())
        replays = self._state.list_replays()
        runs = self._state.list_paper_runs()
        campaigns = self._state.list_campaign_runs()
        evaluations = [item for run in runs for item in run.items]
        total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in evaluations), Decimal("0"))
        realized_average = total_pnl / Decimal(len(evaluations)) if evaluations else Decimal("0")
        skip_reason_counts: Counter[str] = Counter()
        wins = losses = ties = skips = 0
        for item in evaluations:
            if item.decision == "SKIP":
                skips += 1
                skip_reason_counts.update(item.skip_reasons)
                continue
            if item.resolution_result == "UNRESOLVED_TIE":
                ties += 1
                continue
            pnl = _decimal(item.realized_pnl_usdc)
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            else:
                ties += 1

        latest_active = None
        for window in reversed(self._state.list_windows()):
            if window.status != "complete":
                latest_active = window
                break

        summary = Btc15mReportSummary(
            recorded_window_count=len(self._state.list_windows()),
            completed_window_count=sum(1 for item in windows if item.status == "complete"),
            replay_batch_count=len(replays),
            paper_run_count=len(runs),
            evaluated_window_count=len(evaluations),
            total_realized_pnl_usdc=_decimal_text(total_pnl),
            average_realized_pnl_usdc=_decimal_text(realized_average),
            win_count=wins,
            loss_count=losses,
            tie_count=ties,
            skip_count=skips,
            skip_reason_counts=dict(sorted(skip_reason_counts.items())),
            campaign_run_count=len(campaigns),
        )
        return Btc15mReportResponse(
            summary=summary,
            latest_active_window=latest_active,
            campaign_summary=self._build_campaign_summary(
                campaigns=campaigns,
                evaluations=[item for run in campaigns for item in run.items],
            ),
            recent_replays=list(reversed(replays))[:5],
            recent_runs=list(reversed(runs))[:5],
            recent_evaluations=list(reversed(evaluations))[:10],
        )

    def _resolve_latest_window(self) -> _ResolvedWindow:
        try:
            latest = self._market_intel_service.recurring_latest(
                DEFAULT_RECORD_QUERY,
                interval=DEFAULT_RECORD_INTERVAL,
            )
        except MarketValidationError as exc:
            raise Btc15mValidationError(str(exc)) from exc

        if latest.item is not None:
            return self._resolve_window_from_candidate(latest.item, selection_source="recurring")

        fallback = self._resolve_fallback_latest_candidate()
        if fallback is not None:
            return self._resolve_window_from_candidate(fallback, selection_source="recurring")
        raise Btc15mOperatorHintError(
            "No recurring BTC 15m market candidate was found.",
            hint={
                "next_steps": [
                    "pm market recurring list --query btc --interval 15m",
                    "pm strategy btc15m paper-run --slug <market_slug> --mode paper",
                ]
            },
        )

    def _resolve_window_by_slug(self, slug: str) -> _ResolvedWindow:
        with self._gamma_client_cls() as gamma_client:
            market = gamma_client.get_market_by_slug(slug)
        candidate = RecurringMarketCandidate(
            rank=1,
            match_score=0,
            matched_interval=validate_recurring_interval(DEFAULT_RECORD_INTERVAL),
            recency_source=None,
            market_slug=market.market_slug,
            event_slug=market.event_slug,
            question=market.question,
            event_title=market.event_title,
            active=market.active,
            closed=market.closed,
            enable_order_book=market.enable_order_book,
            condition_id=market.condition_id,
            token_ids=market.token_ids,
            outcomes=market.outcomes,
            min_tick=market.min_tick,
            min_order_size=market.min_order_size,
        )
        return self._resolve_window_from_candidate(
            candidate,
            selection_source="slug",
            target_slug=slug,
        )

    def _resolve_window_from_candidate(
        self,
        candidate: RecurringMarketCandidate,
        *,
        selection_source: str,
        target_slug: str | None = None,
    ) -> _ResolvedWindow:
        matched_search = self._find_search_candidate(candidate)
        slug_start_dt = _parse_btc15m_slug_start(candidate.market_slug)
        slug_start_unix = int(slug_start_dt.timestamp()) if slug_start_dt is not None else None
        timing_notes: list[str] = []
        timing_source = "fallback"

        gamma_start_dt = _parse_iso_optional(matched_search.start_date) if matched_search else None
        gamma_end_dt = _parse_iso_optional(matched_search.end_date) if matched_search else None
        if gamma_start_dt is None and gamma_end_dt is not None:
            gamma_start_dt = gamma_end_dt - WINDOW_DURATION
        if gamma_end_dt is None and gamma_start_dt is not None:
            gamma_end_dt = gamma_start_dt + WINDOW_DURATION
        start_dt: datetime | None
        end_dt: datetime | None

        if slug_start_dt is not None:
            start_dt = slug_start_dt
            end_dt = slug_start_dt + WINDOW_DURATION
            timing_source = "slug_timestamp"
            if gamma_start_dt is not None and abs((gamma_start_dt - start_dt).total_seconds()) > 60:
                timing_notes.append(
                    "Slug-derived BTC15m start time overrode materially different Gamma timing."
                )
            if gamma_end_dt is not None and abs((gamma_end_dt - end_dt).total_seconds()) > 60:
                timing_notes.append(
                    "Slug-derived BTC15m end time overrode materially different Gamma timing."
                )
        else:
            start_dt = gamma_start_dt
            end_dt = gamma_end_dt
            if start_dt is not None or end_dt is not None:
                timing_source = "gamma_timing"

        condition_id = candidate.condition_id
        window_suffix = condition_id or candidate.market_slug
        window = Btc15mWindowIdentity(
            strategy_name="btc_15m_chainlink_directional_ladder_v1",
            window_id=f"btc15m:{window_suffix}",
            condition_id=condition_id,
            market_slug=candidate.market_slug,
            token_ids=list(candidate.token_ids),
            outcomes=list(candidate.outcomes),
            slug_start_unix=slug_start_unix,
            timing_source=timing_source,
            timing_notes=timing_notes,
            window_start_at=_isoformat(start_dt) if start_dt is not None else None,
            window_end_at=_isoformat(end_dt) if end_dt is not None else None,
            market_open_time=_isoformat(start_dt) if start_dt is not None else None,
        )
        return _ResolvedWindow(
            candidate=candidate,
            window=window,
            window_start_dt=start_dt,
            window_end_dt=end_dt,
            selection_source=selection_source,
            target_slug=target_slug,
        )

    def _resolve_current_window(self) -> _CurrentWindowResolution:
        now = self._now()
        current_start = _floor_btc15m_window_start(now)
        previous_start = current_start - WINDOW_DURATION
        next_start = current_start + WINDOW_DURATION
        candidates: list[tuple[datetime, str, str]] = []

        if current_start <= now < current_start + WINDOW_DURATION:
            candidates.append((current_start, "current_exact", "live"))
        if now < current_start + timedelta(seconds=DEFAULT_POST_END_GRACE_WINDOW_SECONDS):
            candidates.append((previous_start, "previous_exact", "settling"))
        if now >= next_start - timedelta(seconds=DEFAULT_PRE_START_CAPTURE_WINDOW_SECONDS):
            candidates.append((next_start, "next_exact", "upcoming"))

        for bucket_start, selection_source, status in candidates:
            resolved = self._resolve_window_by_bucket_start(
                bucket_start,
                selection_source=selection_source,
            )
            if resolved is None:
                continue
            assert resolved.window_end_dt is not None
            seconds_to_start = max(0, int((bucket_start - now).total_seconds()))
            seconds_to_end = max(0, int((resolved.window_end_dt - now).total_seconds()))
            return _CurrentWindowResolution(
                resolved=resolved,
                status=status,
                seconds_to_start=seconds_to_start,
                seconds_to_end=seconds_to_end,
            )

        raise Btc15mOperatorHintError(
            "No live BTC 15m current-window candidate was found.",
            hint={
                "next_steps": [
                    "pm market recurring list --query btc --interval 15m",
                    "pm strategy btc15m paper-run --slug <market_slug> --mode paper",
                ]
            },
        )

    def _resolve_window_by_bucket_start(
        self,
        bucket_start: datetime,
        *,
        selection_source: str,
    ) -> _ResolvedWindow | None:
        slug = _canonical_btc15m_slug(bucket_start)
        market = self._get_market_by_slug_or_none(slug)
        if market is not None and self._is_usable_current_market(market, bucket_start):
            return self._resolve_window_from_candidate(
                _recurring_candidate_from_market(market),
                selection_source=selection_source,
                target_slug=slug,
            )

        for search_candidate in self._search_btc15m_candidates():
            market = search_candidate.market
            if not self._is_usable_current_market(market, bucket_start):
                continue
            return self._resolve_window_from_candidate(
                _recurring_candidate_from_market(market),
                selection_source=selection_source.replace("_exact", "_search"),
                target_slug=market.market_slug,
            )
        return None

    def _get_market_by_slug_or_none(self, slug: str) -> NormalizedMarket | None:
        try:
            with self._gamma_client_cls() as gamma_client:
                return gamma_client.get_market_by_slug(slug)
        except Exception:
            return None

    def _is_usable_current_market(self, market: NormalizedMarket, bucket_start: datetime) -> bool:
        slug_start = _parse_btc15m_slug_start(market.market_slug)
        if slug_start is None or slug_start != bucket_start:
            return False
        if market.closed or not market.enable_order_book:
            return False
        if _btc15m_btc_identity_score(market) == 0 or _btc15m_direction_score(market) == 0:
            return False
        if _btc15m_interval_match_strength(market) == 0 and "15m" not in market.market_slug.lower():
            return False
        return True

    def _find_search_candidate(
        self,
        candidate: RecurringMarketCandidate,
    ) -> GammaSearchCandidate | None:
        condition_id = candidate.condition_id
        for search_candidate in self._search_btc15m_candidates():
            market = search_candidate.market
            if market.market_slug == candidate.market_slug:
                return search_candidate
            if condition_id is not None and market.condition_id == condition_id:
                return search_candidate
        return None

    def _search_btc15m_candidates(self) -> list[GammaSearchCandidate]:
        seen: set[str] = set()
        items: list[GammaSearchCandidate] = []
        with self._gamma_client_cls() as gamma_client:
            for query in BTC15M_FALLBACK_QUERIES:
                for candidate in gamma_client.search_market_candidates(
                    query,
                    limit=DEFAULT_FALLBACK_SEARCH_LIMIT,
                ):
                    slug = candidate.market.market_slug
                    if slug in seen:
                        continue
                    seen.add(slug)
                    items.append(candidate)
        return items

    def _resolve_fallback_latest_candidate(self) -> RecurringMarketCandidate | None:
        ranked: list[tuple[RecurringMarketCandidate, tuple[object, ...]]] = []
        for search_candidate in self._search_btc15m_candidates():
            market = search_candidate.market
            interval_strength = _btc15m_interval_match_strength(market)
            btc_score = _btc15m_btc_identity_score(market)
            direction_score = _btc15m_direction_score(market)
            if interval_strength == 0 or btc_score == 0 or direction_score == 0:
                continue
            recency_source, recency_value = _gamma_candidate_recency(search_candidate)
            recurring_candidate = RecurringMarketCandidate(
                rank=0,
                match_score=(interval_strength * 100) + (btc_score * 10) + direction_score,
                matched_interval=validate_recurring_interval(DEFAULT_RECORD_INTERVAL),
                recency_source=recency_source,
                **market.model_dump(mode="json"),
            )
            sort_key = (
                not market.active,
                market.closed,
                -interval_strength,
                -btc_score,
                -direction_score,
                recency_value is None,
                -recency_value.timestamp() if recency_value is not None else float("inf"),
                search_candidate.search_index if recency_value is None else 0,
                market.market_slug,
            )
            ranked.append((recurring_candidate, sort_key))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[1])
        return ranked[0][0]

    def _targeted_record_seconds(self, resolved: _ResolvedWindow) -> int:
        now = self._now()
        if resolved.window_end_dt is not None:
            timeout_at = resolved.window_end_dt + timedelta(seconds=DEFAULT_POST_END_WAIT_SECONDS)
            return max(1, int((timeout_at - now).total_seconds()))
        if resolved.window_start_dt is not None:
            window_open = resolved.window_start_dt + WINDOW_DURATION
            timeout_at = window_open + timedelta(seconds=DEFAULT_POST_END_WAIT_SECONDS)
            return max(1, int((timeout_at - now).total_seconds()))
        return DEFAULT_RECORD_SECONDS

    def _record_resolved_window(
        self,
        resolved: _ResolvedWindow,
        *,
        seconds: int,
        recorder_session_id: str,
        mode: Btc15mRunMode = Btc15mRunMode.PAPER,
    ) -> Btc15mWindowRecord:
        errors: list[Btc15mSectionError] = []
        initial_samples = self._build_initial_market_samples(resolved, errors=errors)
        timing_controls = _default_timing_controls()
        if resolved.window_start_dt is None or resolved.window_end_dt is None:
            record = Btc15mWindowRecord(
                window=resolved.window,
                recorded_at=_isoformat(self._now()),
                recorder_session_id=recorder_session_id,
                status="partial",
                mode=mode,
                target_slug=resolved.target_slug,
                selection_source=resolved.selection_source,
                market_samples=initial_samples,
                boundary_status="missing_timing",
                timing_controls=timing_controls,
                reason_blocks=[
                    Btc15mReasonBlock(
                        section="window_timing",
                        status="fail",
                        message="Could not resolve both window start and end times.",
                    )
                ],
                errors=errors
                + [
                    Btc15mSectionError(
                        section="window_timing",
                        code="invalid_argument",
                        message="Could not resolve both window start and end times.",
                    )
                ],
            )
            self._state.append_windows([record])
            return record

        run_result = asyncio.run(self._stream_window(resolved, seconds=seconds))
        errors.extend(run_result["errors"])
        market_events = run_result["market_events"]
        chainlink_events = run_result["chainlink_events"]
        binance_events = run_result["binance_events"]
        liquidity_samples = run_result["liquidity_samples"]
        chainlink_ticks = self._to_price_ticks(chainlink_events, source="chainlink")
        binance_ticks = self._to_price_ticks(binance_events, source="binance")
        market_samples = initial_samples + self._to_market_samples(
            market_events,
            token_outcomes=_token_outcome_map(resolved.window.token_ids, resolved.window.outcomes),
        )
        market_samples.sort(key=lambda item: (item.observed_at, item.token_id, item.event_type))
        boundary_observations, boundary_decision = self._build_boundaries(
            resolved,
            chainlink_ticks=chainlink_ticks,
            recorder_session_id=recorder_session_id,
        )
        self._state.append_boundary_observations(boundary_observations)
        self._state.append_boundary_decision(boundary_decision)
        if liquidity_samples:
            self._state.append_liquidity_samples(liquidity_samples)
        decision, decision_at, skip_reasons, reason_blocks = self._decide_window(
            resolved,
            boundary_decision=boundary_decision,
            chainlink_ticks=chainlink_ticks,
            binance_ticks=binance_ticks,
        )
        resolution = self._resolve_market_outcome(boundary_decision)
        record = Btc15mWindowRecord(
            window=resolved.window,
            recorded_at=_isoformat(self._now()),
            recorder_session_id=recorder_session_id,
            status="complete" if boundary_decision.status == "complete" else "partial",
            mode=mode,
            target_slug=resolved.target_slug,
            selection_source=resolved.selection_source,
            market_source_session_id=run_result["market_session_id"],
            chainlink_source_session_id=run_result["chainlink_session_id"],
            binance_source_session_id=run_result["binance_session_id"],
            chainlink_ticks=chainlink_ticks,
            binance_ticks=binance_ticks,
            binance_pre_start_tick=_latest_tick_before_or_at_within(
                binance_ticks,
                resolved.window_start_dt,
                timing_controls.pre_start_capture_window_seconds,
            ),
            binance_post_start_tick=_first_tick_at_or_after_within(
                binance_ticks,
                resolved.window_start_dt,
                timing_controls.post_start_grace_window_seconds,
            ),
            binance_pre_end_tick=_latest_tick_before_or_at_within(
                binance_ticks,
                resolved.window_end_dt,
                timing_controls.pre_end_capture_window_seconds,
            ),
            binance_post_end_tick=_first_tick_at_or_after_within(
                binance_ticks,
                resolved.window_end_dt,
                timing_controls.post_end_grace_window_seconds,
            ),
            market_samples=market_samples,
            liquidity_samples=liquidity_samples,
            boundary_status=boundary_decision.status,
            timing_controls=timing_controls,
            start_price_proxy_v1=boundary_decision.start_price_proxy_v1,
            end_price_proxy_v1=boundary_decision.end_price_proxy_v1,
            decision=decision,
            decision_at=decision_at,
            resolution_result=resolution,
            manipulation_flags=_derive_manipulation_flags(liquidity_samples),
            skip_reasons=skip_reasons,
            reason_blocks=reason_blocks,
            errors=errors,
        )
        self._state.append_windows([record])
        return record

    def _record_and_evaluate_window(
        self,
        resolved: _ResolvedWindow,
        *,
        seconds: int,
        recorder_session_id: str,
        evaluation_source_kind: str,
        campaign_run_id: str | None = None,
        persist_paper_run: bool,
        mode: Btc15mRunMode = Btc15mRunMode.PAPER,
    ) -> _RecordedWindowArtifacts:
        record = self._record_resolved_window(
            resolved,
            seconds=seconds,
            recorder_session_id=recorder_session_id,
            mode=mode,
        )
        evaluation = self._evaluate_window(
            record,
            source_kind=evaluation_source_kind,
            campaign_run_id=campaign_run_id,
        )
        if persist_paper_run:
            paper_run = Btc15mPaperRunRecord(
                run_id=_make_id("btc15m_paper_run"),
                created_at=_isoformat(self._now()),
                limit=1,
                mode=mode,
                target_slug=resolved.target_slug,
                selection_source=resolved.selection_source,
                source_kind=evaluation_source_kind,
                campaign_run_id=campaign_run_id,
                items=[evaluation],
                total_considered=1,
                total_evaluated=1,
                total_skipped=1 if evaluation.decision == "SKIP" else 0,
                total_realized_pnl_usdc=evaluation.realized_pnl_usdc,
            )
            self._state.append_paper_run(paper_run)
        return _RecordedWindowArtifacts(record=record, evaluation=evaluation)

    def _run_targeted_paper_window(
        self,
        resolved: _ResolvedWindow,
        *,
        recorder_session_id: str,
        source_kind: str,
    ) -> tuple[Btc15mPaperEvaluation | None, list[Btc15mSectionError]]:
        seconds = self._targeted_record_seconds(resolved)
        record = self._record_resolved_window(
            resolved,
            seconds=seconds,
            recorder_session_id=recorder_session_id,
            mode=Btc15mRunMode.PAPER,
        )
        evaluation = self._evaluate_window(record, source_kind=source_kind)
        errors = list(record.errors)
        return evaluation, errors

    async def _stream_window(self, resolved: _ResolvedWindow, *, seconds: int) -> dict[str, Any]:
        errors: list[Btc15mSectionError] = []
        market_events: list[CapturedStreamEvent] = []
        chainlink_events: list[CapturedStreamEvent] = []
        binance_events: list[CapturedStreamEvent] = []
        liquidity_samples: list[Btc15mLiquiditySampleRecord] = []
        market_session_id: str | None = None
        chainlink_session_id: str | None = None
        binance_session_id: str | None = None

        results = await asyncio.gather(
            self._market_client.stream_tokens(
                resolved.window.token_ids,
                seconds=seconds,
            ),
            self._crypto_client.stream_symbol(
                "BTC",
                source="chainlink",
                seconds=seconds,
            ),
            self._crypto_client.stream_symbol(
                "BTC",
                source="binance",
                seconds=seconds,
            ),
            self._sample_window_liquidity(resolved, seconds=seconds),
            return_exceptions=True,
        )

        market_result, chainlink_result, binance_result, liquidity_result = results
        if isinstance(market_result, Exception):
            errors.append(_section_error("market_stream", market_result))
        else:
            bounded_result = _coerce_market_result(market_result)
            market_events.extend(bounded_result.events)
            market_session_id = bounded_result.session.session_id
            errors.extend(_convert_stream_errors(bounded_result.errors))

        if isinstance(chainlink_result, Exception):
            errors.append(_section_error("chainlink_stream", chainlink_result))
        else:
            response = _coerce_crypto_result(chainlink_result)
            chainlink_events.extend(response.events)
            chainlink_session_id = response.session.session_id
            errors.extend(_convert_stream_errors(response.errors))

        if isinstance(binance_result, Exception):
            errors.append(_section_error("binance_stream", binance_result))
        else:
            response = _coerce_crypto_result(binance_result)
            binance_events.extend(response.events)
            binance_session_id = response.session.session_id
            errors.extend(_convert_stream_errors(response.errors))

        if isinstance(liquidity_result, Exception):
            errors.append(_section_error("liquidity_sample", liquidity_result))
        else:
            liquidity_samples.extend(cast(list[Btc15mLiquiditySampleRecord], liquidity_result))

        return {
            "market_events": market_events,
            "chainlink_events": chainlink_events,
            "binance_events": binance_events,
            "liquidity_samples": liquidity_samples,
            "market_session_id": market_session_id,
            "chainlink_session_id": chainlink_session_id,
            "binance_session_id": binance_session_id,
            "errors": errors,
        }

    async def _sample_window_liquidity(
        self,
        resolved: _ResolvedWindow,
        *,
        seconds: int,
    ) -> list[Btc15mLiquiditySampleRecord]:
        samples: list[Btc15mLiquiditySampleRecord] = []
        started_at = self._now()
        schedule = _build_liquidity_schedule(
            started_at=started_at,
            seconds=seconds,
            baseline_seconds=DEFAULT_CAMPAIGN_SAMPLE_CADENCE_SECONDS,
            mandatory_points=self._liquidity_checkpoints(resolved),
        )
        loop = asyncio.get_running_loop()
        started_monotonic = loop.time()

        for sample_kind, scheduled_at in schedule:
            target_delay = max(0.0, (scheduled_at - started_at).total_seconds())
            elapsed = loop.time() - started_monotonic
            if target_delay > elapsed:
                await self._async_sleep(target_delay - elapsed)
            sample = await asyncio.to_thread(
                self._capture_liquidity_sample,
                resolved,
                sample_kind=sample_kind,
                scheduled_at_dt=scheduled_at,
            )
            samples.append(sample)

        return samples

    def _capture_liquidity_sample(
        self,
        resolved: _ResolvedWindow,
        *,
        sample_kind: str,
        scheduled_at_dt: datetime | None = None,
    ) -> Btc15mLiquiditySampleRecord:
        sampled_at_dt = self._now()
        errors: list[Btc15mSectionError] = []
        try:
            binance_snapshot = self._binance_service.sample_liquidity("BTCUSDT")
        except (BinanceClientError, Btc15mValidationError) as exc:
            raise Btc15mValidationError(str(exc)) from exc

        polymarket = self._build_polymarket_liquidity_levels(resolved, errors=errors)
        late_by_seconds: int | None = None
        if scheduled_at_dt is not None:
            late_by_seconds = max(0, int((sampled_at_dt - scheduled_at_dt).total_seconds()))
        return Btc15mLiquiditySampleRecord(
            sample_id=_make_id("btc15m_liquidity_sample"),
            window_id=resolved.window.window_id,
            condition_id=resolved.window.condition_id,
            market_slug=resolved.window.market_slug,
            sample_kind=sample_kind,
            sampled_at=_isoformat(sampled_at_dt),
            scheduled_at=_isoformat(scheduled_at_dt) if scheduled_at_dt is not None else None,
            late_by_seconds=late_by_seconds,
            binance=binance_snapshot,
            polymarket=polymarket,
            errors=errors,
        )

    def _build_polymarket_liquidity_levels(
        self,
        resolved: _ResolvedWindow,
        *,
        errors: list[Btc15mSectionError],
    ) -> list[Btc15mPolymarketLiquidityLevel]:
        items: list[Btc15mPolymarketLiquidityLevel] = []
        outcome_map = _token_outcome_map(resolved.window.token_ids, resolved.window.outcomes)
        try:
            with self._clob_client_cls() as clob_client:
                for token_id in resolved.window.token_ids:
                    try:
                        book = clob_client.get_book(token_id)
                    except (ClobClientError, ClobNotFoundError) as exc:
                        errors.append(_section_error(f"clob_liquidity:{token_id}", exc))
                        continue
                    best_bid = book.bids[0].price if book.bids else None
                    best_ask = book.asks[0].price if book.asks else None
                    midpoint = _midpoint_optional_text(best_bid, best_ask)
                    spread = _spread_optional_text(best_bid, best_ask)
                    items.append(
                        Btc15mPolymarketLiquidityLevel(
                            token_id=token_id,
                            outcome=outcome_map.get(token_id),
                            best_bid=best_bid,
                            best_ask=best_ask,
                            midpoint=midpoint,
                            spread=spread,
                            bid_level_count=len(book.bids),
                            ask_level_count=len(book.asks),
                            bids=list(book.bids),
                            asks=list(book.asks),
                            visible_liquidity_030=_decimal_text(
                                _ask_liquidity_at_or_better(book.asks, Decimal("0.30"))
                            ),
                            visible_liquidity_020=_decimal_text(
                                _ask_liquidity_at_or_better(book.asks, Decimal("0.20"))
                            ),
                            visible_liquidity_010=_decimal_text(
                                _ask_liquidity_at_or_better(book.asks, Decimal("0.10"))
                            ),
                        )
                    )
        except TypeError:
            errors.append(
                Btc15mSectionError(
                    section="clob_liquidity",
                    code="request_failed",
                    message="Could not construct the public CLOB client.",
                )
            )
        return items

    def _liquidity_checkpoints(self, resolved: _ResolvedWindow) -> list[tuple[str, datetime]]:
        timing_controls = _default_timing_controls()
        checkpoints: list[tuple[str, datetime]] = []
        if resolved.window_start_dt is not None:
            checkpoints.append(("start_boundary", resolved.window_start_dt))
            checkpoints.append(
                (
                    "minute_five",
                    resolved.window_start_dt
                    + timedelta(seconds=timing_controls.direction_lock_offset_seconds),
                )
            )
            checkpoints.append(
                (
                    "minute_ten",
                    resolved.window_start_dt
                    + timedelta(seconds=timing_controls.entry_window_end_offset_seconds),
                )
            )
        if resolved.window_end_dt is not None:
            checkpoints.append(("end_boundary", resolved.window_end_dt))
        return checkpoints

    def _is_unresolved_window(self, resolved: _ResolvedWindow) -> bool:
        return resolved.window_end_dt is not None and resolved.window_end_dt > self._now()

    def _latest_boundary_decision(self, window_id: str) -> Btc15mBoundaryDecisionRecord | None:
        for item in reversed(self._state.list_boundary_decisions()):
            if item.window_id == window_id:
                return item
        return None

    def _latest_window_record(self, window_id: str) -> Btc15mWindowRecord | None:
        for item in reversed(self._state.list_windows()):
            if item.window.window_id == window_id:
                return item
        return None

    def _latest_evaluation_for_window(self, window_id: str) -> Btc15mPaperEvaluation | None:
        for paper_run in reversed(self._state.list_paper_runs()):
            for item in reversed(paper_run.items):
                if item.window_id == window_id:
                    return item
        for campaign_run in reversed(self._state.list_campaign_runs()):
            for item in reversed(campaign_run.items):
                if item.window_id == window_id:
                    return item
        for auto_roll_run in reversed(self._state.list_auto_roll_runs()):
            for item in reversed(auto_roll_run.items):
                if item.window_id == window_id:
                    return item
        return None

    def _can_complete_window_before(self, resolved: _ResolvedWindow, deadline: datetime) -> bool:
        if resolved.window_end_dt is None:
            return False
        completion_deadline = resolved.window_end_dt + timedelta(
            seconds=DEFAULT_POST_END_WAIT_SECONDS
        )
        return completion_deadline <= deadline

    def _create_terminal_runtime(
        self,
        *,
        session_id: str,
        resolved: _ResolvedWindow,
        mode: Btc15mRunMode,
        started_at_dt: datetime,
        attach_mode: str = "current",
        observe_only: bool = False,
        follow_current: bool = False,
        arm_next: bool = False,
        wait_next_target_start_dt: datetime | None = None,
        paper_budget_usdc: Decimal = DEFAULT_TERMINAL_BUDGET_USDC,
        rung_notionals_usdc: tuple[Decimal, Decimal, Decimal] = RUNG_NOTIONALS,
    ) -> _TerminalRuntime:
        runtime = _TerminalRuntime(
            session_id=session_id,
            resolved=resolved,
            mode=mode,
            started_at_dt=started_at_dt,
            state=(
                Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW
                if attach_mode == "wait_next" and wait_next_target_start_dt is not None
                else Btc15mTerminalState.OBSERVE_ONLY
                if observe_only
                else Btc15mTerminalState.PRE_START_CAPTURE
            ),
            attach_mode=attach_mode,
            observe_only=observe_only,
            follow_current=follow_current,
            arm_next=arm_next,
            wait_next_target_start_dt=wait_next_target_start_dt,
            paper_budget_usdc=paper_budget_usdc,
            rung_notionals_usdc=rung_notionals_usdc,
            window_started_at_dt=started_at_dt,
        )
        self._hydrate_terminal_runtime_for_window(runtime, resolved)
        self._update_terminal_state(runtime, started_at_dt)
        if runtime.state is Btc15mTerminalState.SKIPPED:
            runtime.stop_reason = runtime.skip_reasons[-1] if runtime.skip_reasons else "skipped"
        self._record_terminal_event(
            runtime,
            kind="session",
            status="info",
            message=f"Attached BTC15m terminal session in {mode.value} mode.",
        )
        if attach_mode == "wait_next" and wait_next_target_start_dt is not None:
            self._record_terminal_event(
                runtime,
                kind="wait_next",
                status="info",
                message=(
                    "Waiting to arm next BTC15m window at "
                    f"{_isoformat(wait_next_target_start_dt)}."
                ),
            )
        elif observe_only:
            self._record_terminal_event(
                runtime,
                kind="observe",
                status="info",
                message="Running BTC15m terminal in observe-only mode for the current window.",
            )
        if arm_next:
            self._record_terminal_event(
                runtime,
                kind="arm_next",
                status="info",
                message="Will arm and trade the next eligible BTC15m window after the current one.",
            )
        return runtime

    def _hydrate_terminal_runtime_for_window(
        self,
        runtime: _TerminalRuntime,
        resolved: _ResolvedWindow,
    ) -> None:
        """Load persisted window-specific BTC15m terminal state into a runtime."""
        latest_boundary = self._latest_boundary_decision(resolved.window.window_id)
        latest_window = self._latest_window_record(resolved.window.window_id)
        runtime.resolved = resolved
        runtime.boundary_pre_start = (
            latest_boundary.pre_start if latest_boundary is not None else None
        )
        runtime.boundary_post_start = (
            latest_boundary.post_start if latest_boundary is not None else None
        )
        runtime.boundary_pre_end = latest_boundary.pre_end if latest_boundary is not None else None
        runtime.boundary_post_end = (
            latest_boundary.post_end if latest_boundary is not None else None
        )
        runtime.boundary_status = (
            latest_boundary.status
            if latest_boundary is not None
            else latest_window.boundary_status
            if latest_window is not None
            else "pending"
        )
        runtime.start_price_proxy_v1 = (
            latest_boundary.start_price_proxy_v1
            if latest_boundary is not None
            else latest_window.start_price_proxy_v1
            if latest_window is not None
            else None
        )
        runtime.end_price_proxy_v1 = (
            latest_boundary.end_price_proxy_v1
            if latest_boundary is not None
            else latest_window.end_price_proxy_v1
            if latest_window is not None
            else None
        )
        runtime.selected_side = (
            latest_window.decision
            if latest_window is not None and latest_window.decision in {"UP", "DOWN"}
            else None
        )
        runtime.decision_at = latest_window.decision_at if latest_window is not None else None
        runtime.target_token_id = None
        runtime.target_outcome = None
        runtime.rungs = []
        if latest_window is not None and len(latest_window.rung_notionals_usdc) == 3:
            runtime.rung_notionals_usdc = _record_rung_notionals(latest_window)
            runtime.paper_budget_usdc = _decimal(_record_paper_budget(latest_window))
        runtime.market_open_interest = getattr(latest_window, "market_open_interest", None)
        runtime.market_volume = getattr(latest_window, "market_volume", None)
        runtime.manipulation_flags = []
        runtime.skip_reasons = []
        runtime.reason_blocks = []
        runtime.chainlink_ticks = []
        runtime.binance_ticks = []
        runtime.market_samples = []
        runtime.liquidity_samples = []
        runtime.favorable_marks = []
        runtime.mfe = Decimal("0")
        runtime.mae = Decimal("0")
        runtime.max_favorable_price = None
        runtime.time_to_peak_seconds = None
        runtime.first_fill_at = None
        runtime.last_market_context_refresh_at = None
        runtime.last_page_parity_refresh_at = None
        runtime.current_market = None
        runtime.page_parity_fallback = None
        runtime.current_window_snapshots = 0
        runtime.window_started_at_dt = self._now()
        runtime.window_finalized = False
        if runtime.selected_side in {"UP", "DOWN"}:
            target = _resolve_target_token(
                resolved.window.token_ids,
                resolved.window.outcomes,
                runtime.selected_side,
            )
            if target is not None:
                runtime.target_token_id, runtime.target_outcome = target
            runtime.rungs = [
                _TerminalRungRuntime(
                    price=price,
                    notional_usdc=notional,
                    quantity=(notional / price).quantize(
                        Decimal("0.000001"),
                        rounding=ROUND_DOWN,
                    ),
                )
                for price, notional in zip(
                    RUNG_PRICES,
                    runtime.rung_notionals_usdc,
                    strict=True,
                )
            ]
        if latest_window is not None:
            runtime.manipulation_flags.extend(
                flag
                for flag in latest_window.manipulation_flags
                if flag not in runtime.manipulation_flags
            )
            runtime.skip_reasons.extend(
                reason
                for reason in latest_window.skip_reasons
                if reason not in runtime.skip_reasons
            )
            runtime.reason_blocks.extend(latest_window.reason_blocks)
            runtime.chainlink_ticks.extend(latest_window.chainlink_ticks)
            runtime.binance_ticks.extend(latest_window.binance_ticks)
            runtime.market_samples.extend(latest_window.market_samples)
            runtime.liquidity_samples.extend(latest_window.liquidity_samples)
        latest_evaluation = self._latest_evaluation_for_window(resolved.window.window_id)
        if latest_evaluation is not None:
            if len(latest_evaluation.rung_notionals_usdc) == 3:
                runtime.rung_notionals_usdc = cast(
                    tuple[Decimal, Decimal, Decimal],
                    tuple(_decimal(value) for value in latest_evaluation.rung_notionals_usdc),
                )
            if latest_evaluation.paper_budget_usdc is not None:
                runtime.paper_budget_usdc = _decimal(latest_evaluation.paper_budget_usdc)
            runtime.selected_side = latest_evaluation.decision
            runtime.decision_at = latest_evaluation.decision_at
            runtime.target_token_id = latest_evaluation.target_token_id
            runtime.target_outcome = latest_evaluation.target_outcome
            runtime.favorable_marks.extend(latest_evaluation.max_favorable_path)
            runtime.mfe = _decimal(latest_evaluation.mfe_usdc)
            runtime.mae = _decimal(latest_evaluation.mae_usdc)
            runtime.max_favorable_price = latest_evaluation.max_favorable_price
            runtime.time_to_peak_seconds = latest_evaluation.time_to_peak_seconds
            runtime.first_fill_at = latest_evaluation.first_fill_at
            runtime.rungs = [
                _TerminalRungRuntime(
                    price=_decimal(rung.price),
                    notional_usdc=_decimal(rung.notional_usdc),
                    quantity=_decimal(rung.quantity),
                    state=rung.status,
                    fill_at=rung.fill_at,
                    fill_price=rung.fill_price,
                    cancellation_at=rung.cancellation_at,
                )
                for rung in latest_evaluation.rungs
            ]

    def _switch_terminal_runtime_to_window(
        self,
        runtime: _TerminalRuntime,
        resolved: _ResolvedWindow,
        *,
        observe_only: bool,
    ) -> None:
        """Switch one terminal runtime to a newly armed BTC15m window."""
        previous_slug = runtime.resolved.window.market_slug
        runtime.observe_only = observe_only
        runtime.wait_next_target_start_dt = None
        runtime.events = []
        self._hydrate_terminal_runtime_for_window(runtime, resolved)
        runtime.rollover_history.append(f"{previous_slug}->{resolved.window.market_slug}")
        self._record_terminal_event(
            runtime,
            kind="rollover",
            status="info",
            message=f"Armed BTC15m terminal on {resolved.window.market_slug}.",
        )

    def _roll_terminal_session_forward(self, runtime: _TerminalRuntime) -> bool:
        try:
            current = self._resolve_current_window()
        except Btc15mOperatorHintError:
            next_start = None
            if runtime.resolved.window_start_dt is not None:
                next_start = runtime.resolved.window_start_dt + WINDOW_DURATION
            runtime.wait_next_target_start_dt = next_start
            runtime.state = Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW
            runtime.observe_only = True
            runtime.events = []
            runtime.current_window_snapshots = 0
            self._record_terminal_event(
                runtime,
                kind="wait_next",
                status="info",
                message="Waiting for the next live BTC15m market to appear.",
            )
            return True
        next_resolved = current.resolved
        if next_resolved.window.window_id == runtime.resolved.window.window_id:
            if runtime.resolved.window_start_dt is not None:
                direct_next = self._resolve_window_by_bucket_start(
                    runtime.resolved.window_start_dt + WINDOW_DURATION,
                    selection_source="next_exact",
                )
                if direct_next is not None:
                    self._switch_terminal_runtime_to_window(
                        runtime,
                        direct_next,
                        observe_only=False,
                    )
                    runtime.stop_reason = "running"
                    self._update_terminal_state(runtime, self._now())
                    return True
            runtime.state = Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW
            runtime.observe_only = True
            runtime.wait_next_target_start_dt = (
                runtime.resolved.window_start_dt + WINDOW_DURATION
                if runtime.resolved.window_start_dt is not None
                else None
            )
            return True
        self._switch_terminal_runtime_to_window(runtime, next_resolved, observe_only=False)
        runtime.stop_reason = "running"
        self._update_terminal_state(runtime, self._now())
        return True

    def _advance_terminal_runtime(
        self,
        runtime: _TerminalRuntime,
        *,
        confirm_action: Callable[[str], bool | None] | None = None,
    ) -> Btc15mDashboardSnapshotRecord:
        sampled_at_dt = self._now()
        chainlink_tick, binance_tick, tick_errors = self._capture_current_ticks()
        runtime.errors.extend(tick_errors)
        if chainlink_tick is not None:
            _append_tick_if_new(runtime.chainlink_ticks, chainlink_tick)
        if binance_tick is not None:
            _append_tick_if_new(runtime.binance_ticks, binance_tick)
        self._maybe_arm_wait_next_window(runtime, sampled_at_dt)
        self._maybe_refresh_terminal_market_context(runtime, sampled_at_dt)
        self._maybe_refresh_terminal_page_parity(runtime, sampled_at_dt)
        self._update_terminal_boundaries(runtime)
        if runtime.state is not Btc15mTerminalState.SKIPPED:
            self._update_terminal_state(runtime, sampled_at_dt)
        if (
            runtime.state
            not in {
                Btc15mTerminalState.SKIPPED,
                Btc15mTerminalState.OBSERVE_ONLY,
                Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW,
            }
            and not runtime.observe_only
        ):
            self._maybe_apply_terminal_decision(runtime, sampled_at_dt)
        if (
            runtime.state
            not in {
                Btc15mTerminalState.SKIPPED,
                Btc15mTerminalState.OBSERVE_ONLY,
                Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW,
            }
            and not runtime.observe_only
            and runtime.selected_side in {"UP", "DOWN"}
        ):
            if runtime.mode is Btc15mRunMode.PAPER:
                self._apply_terminal_paper_rungs(runtime, sampled_at_dt)
            else:
                self._apply_terminal_live_rungs(
                    runtime,
                    sampled_at_dt,
                    confirm_action=confirm_action,
                )
        self._update_terminal_favorable_metrics(runtime, sampled_at_dt)
        if runtime.state is not Btc15mTerminalState.SKIPPED:
            self._update_terminal_state(runtime, sampled_at_dt)
        snapshot = self._build_terminal_snapshot(runtime, sampled_at_dt)
        runtime.latest_snapshot = snapshot
        runtime.total_snapshots += 1
        if not runtime.window_finalized:
            runtime.current_window_snapshots += 1
        return snapshot

    def _maybe_arm_wait_next_window(
        self,
        runtime: _TerminalRuntime,
        now: datetime,
    ) -> None:
        """Switch a wait-next terminal session onto the next eligible BTC15m window."""
        if runtime.wait_next_target_start_dt is None:
            return
        capture_opens_at = runtime.wait_next_target_start_dt - timedelta(
            seconds=DEFAULT_PRE_START_CAPTURE_WINDOW_SECONDS
        )
        if now < capture_opens_at:
            runtime.state = Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW
            return
        next_resolved = self._resolve_window_by_bucket_start(
            runtime.wait_next_target_start_dt,
            selection_source="wait_next_exact",
        )
        if next_resolved is None:
            deadline = runtime.wait_next_target_start_dt + timedelta(
                seconds=DEFAULT_POST_START_GRACE_WINDOW_SECONDS
            )
            runtime.state = Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW
            if now > deadline:
                self._mark_terminal_skipped(
                    runtime,
                    stop_reason="no_wait_next_candidate",
                    message=(
                        "Could not resolve the next BTC15m window before the "
                        "start grace expired."
                    ),
                )
            return
        if runtime.resolved.window.window_id == next_resolved.window.window_id:
            runtime.wait_next_target_start_dt = None
            runtime.observe_only = False
            return
        self._switch_terminal_runtime_to_window(
            runtime,
            next_resolved,
            observe_only=False,
        )

    def _maybe_refresh_terminal_market_context(
        self,
        runtime: _TerminalRuntime,
        sampled_at_dt: datetime,
    ) -> None:
        refresh_due = runtime.last_market_context_refresh_at is None or (
            sampled_at_dt - runtime.last_market_context_refresh_at
        ).total_seconds() >= DEFAULT_TERMINAL_CONTEXT_REFRESH_SECONDS
        if runtime.latest_snapshot is None:
            refresh_due = True
        if not refresh_due:
            return
        try:
            sample = self._capture_liquidity_sample(
                runtime.resolved,
                sample_kind="terminal",
                scheduled_at_dt=sampled_at_dt,
            )
        except Exception as exc:
            runtime.errors.append(_section_error("terminal_liquidity", exc))
            return
        runtime.liquidity_samples.append(sample)
        runtime.market_samples.extend(_market_samples_from_liquidity(sample))
        runtime.market_open_interest = runtime.market_open_interest or None
        runtime.market_volume = runtime.market_volume or _binance_volume_proxy(sample, minutes=3)
        runtime.last_market_context_refresh_at = sampled_at_dt

    def _maybe_refresh_terminal_page_parity(
        self,
        runtime: _TerminalRuntime,
        sampled_at_dt: datetime,
    ) -> None:
        refresh_due = runtime.last_page_parity_refresh_at is None or (
            sampled_at_dt - runtime.last_page_parity_refresh_at
        ).total_seconds() >= DEFAULT_TERMINAL_PAGE_PARITY_REFRESH_SECONDS
        if runtime.page_parity_fallback is not None and not refresh_due:
            return
        market = self._get_market_by_slug_or_none(runtime.resolved.window.market_slug)
        runtime.current_market = market
        if market is None:
            if (
                runtime.page_parity_fallback is not None
                and runtime.page_parity_fallback.has_fields()
            ):
                runtime.page_parity_fallback = runtime.page_parity_fallback.stale_copy(
                    "market_lookup_unavailable"
                )
            else:
                runtime.page_parity_fallback = Btc15mPageParityData(
                    stale=True,
                    notes=["market_lookup_unavailable"],
                )
            runtime.last_page_parity_refresh_at = sampled_at_dt
            return
        try:
            fetch_terminal_current = getattr(
                self._page_parity_service,
                "fetch_terminal_current",
                None,
            )
            if callable(fetch_terminal_current):
                runtime.page_parity_fallback = fetch_terminal_current(
                    market,
                    previous=runtime.page_parity_fallback,
                )
            else:
                runtime.page_parity_fallback = self._page_parity_service.fetch(market)
        except Exception as exc:
            runtime.errors.append(_section_error("terminal_page_parity", exc))
            if (
                runtime.page_parity_fallback is not None
                and runtime.page_parity_fallback.has_fields()
            ):
                runtime.page_parity_fallback = runtime.page_parity_fallback.stale_copy(str(exc))
            else:
                runtime.page_parity_fallback = Btc15mPageParityData(
                    stale=True,
                    notes=[str(exc)],
                )
        runtime.last_page_parity_refresh_at = sampled_at_dt

    def _update_terminal_boundaries(self, runtime: _TerminalRuntime) -> None:
        resolved = runtime.resolved
        if resolved.window_start_dt is None or resolved.window_end_dt is None:
            self._mark_terminal_skipped(
                runtime,
                stop_reason="missing_window_timing",
                message="Current BTC15m window timing could not be resolved.",
            )
            return
        timing_controls = _default_timing_controls()
        runtime.boundary_pre_start = runtime.boundary_pre_start or _latest_tick_before_or_at_within(
            runtime.chainlink_ticks,
            resolved.window_start_dt,
            timing_controls.pre_start_capture_window_seconds,
        )
        runtime.boundary_post_start = runtime.boundary_post_start or _first_tick_at_or_after_within(
            runtime.chainlink_ticks,
            resolved.window_start_dt,
            timing_controls.post_start_grace_window_seconds,
        )
        runtime.boundary_pre_end = runtime.boundary_pre_end or _latest_tick_before_or_at_within(
            runtime.chainlink_ticks,
            resolved.window_end_dt,
            timing_controls.pre_end_capture_window_seconds,
        )
        runtime.boundary_post_end = runtime.boundary_post_end or _first_tick_at_or_after_within(
            runtime.chainlink_ticks,
            resolved.window_end_dt,
            timing_controls.post_end_grace_window_seconds,
        )
        runtime.start_price_proxy_v1 = (
            runtime.boundary_post_start.value if runtime.boundary_post_start is not None else None
        )
        runtime.end_price_proxy_v1 = (
            runtime.boundary_post_end.value if runtime.boundary_post_end is not None else None
        )
        now = self._now()
        post_start_deadline = resolved.window_start_dt + timedelta(
            seconds=timing_controls.post_start_grace_window_seconds
        )
        post_end_deadline = resolved.window_end_dt + timedelta(
            seconds=timing_controls.post_end_grace_window_seconds
        )
        if runtime.start_price_proxy_v1 is None and now > post_start_deadline:
            if runtime.attach_mode in {"current", "current_observe_only", "wait_next"}:
                if "missing_start_proxy" not in runtime.skip_reasons:
                    runtime.skip_reasons.append("missing_start_proxy")
                if not runtime.observe_only:
                    runtime.observe_only = True
                    runtime.stop_reason = "observe_only_missing_start_proxy"
                    self._record_terminal_event(
                        runtime,
                        kind="observe",
                        status="info",
                        message="Start boundary grace expired; continuing in observe-only mode.",
                    )
                runtime.boundary_status = (
                    "partial" if runtime.boundary_pre_start is not None else "pending"
                )
            else:
                self._mark_terminal_skipped(
                    runtime,
                    stop_reason="missing_start_proxy",
                    message="No Chainlink tick arrived within the post-start grace window.",
                )
            return
        if runtime.end_price_proxy_v1 is None and now > post_end_deadline:
            if not runtime.observe_only:
                self._mark_terminal_skipped(
                    runtime,
                    stop_reason="missing_end_proxy",
                    message="No Chainlink tick arrived within the post-end grace window.",
                )
            return
        if runtime.start_price_proxy_v1 is not None and runtime.end_price_proxy_v1 is not None:
            runtime.boundary_status = "complete"
        elif runtime.start_price_proxy_v1 is not None:
            runtime.boundary_status = "partial"
        else:
            runtime.boundary_status = "pending"

    def _update_terminal_state(
        self,
        runtime: _TerminalRuntime,
        now: datetime,
    ) -> None:
        if runtime.state in {Btc15mTerminalState.SKIPPED, Btc15mTerminalState.RESOLVED}:
            return
        resolved = runtime.resolved
        if resolved.window_start_dt is None or resolved.window_end_dt is None:
            runtime.state = Btc15mTerminalState.SKIPPED
            return
        timing_controls = _default_timing_controls()
        start_dt = resolved.window_start_dt
        end_dt = resolved.window_end_dt
        minute_five = start_dt + timedelta(seconds=timing_controls.direction_lock_offset_seconds)
        minute_ten = start_dt + timedelta(seconds=timing_controls.entry_window_end_offset_seconds)
        end_grace = end_dt + timedelta(seconds=timing_controls.post_end_grace_window_seconds)
        effective_start_proxy = runtime.start_price_proxy_v1
        if runtime.wait_next_target_start_dt is not None:
            runtime.state = Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW
            return
        if runtime.observe_only:
            runtime.state = Btc15mTerminalState.OBSERVE_ONLY
            if now >= end_grace and runtime.stop_reason == "running":
                runtime.stop_reason = "observe_only_complete"
            return
        if now < start_dt:
            runtime.state = Btc15mTerminalState.PRE_START_CAPTURE
        elif effective_start_proxy is None:
            runtime.state = Btc15mTerminalState.BOUNDARY_PENDING
        elif runtime.selected_side is None and now < minute_five:
            runtime.state = Btc15mTerminalState.DIRECTION_LOCK_PENDING
        elif runtime.selected_side is None and now >= minute_five:
            runtime.state = Btc15mTerminalState.DIRECTION_LOCK_PENDING
        elif now < minute_ten:
            runtime.state = Btc15mTerminalState.ENTRY_WINDOW_OPEN
        elif now < end_grace:
            runtime.state = Btc15mTerminalState.HOLD_TO_EXPIRY
        elif runtime.end_price_proxy_v1 is not None:
            runtime.state = Btc15mTerminalState.RESOLVED
            runtime.stop_reason = "window_complete"
        else:
            runtime.state = Btc15mTerminalState.BOUNDARY_PENDING

    def _record_terminal_event(
        self,
        runtime: _TerminalRuntime,
        *,
        kind: str,
        status: str,
        message: str,
        event_at: datetime | None = None,
    ) -> None:
        runtime.events.append(
            Btc15mTerminalEventRecord(
                event_at=_isoformat(event_at or self._now()),
                kind=kind,
                status=status,
                message=message,
            )
        )
        runtime.session_events.append(runtime.events[-1])
        if len(runtime.events) > DEFAULT_TERMINAL_EVENT_LOG_LIMIT:
            runtime.events[:] = runtime.events[-DEFAULT_TERMINAL_EVENT_LOG_LIMIT:]
        if len(runtime.session_events) > DEFAULT_TERMINAL_SESSION_EVENT_LOG_LIMIT:
            runtime.session_events[:] = runtime.session_events[
                -DEFAULT_TERMINAL_SESSION_EVENT_LOG_LIMIT:
            ]

    def _mark_terminal_skipped(
        self,
        runtime: _TerminalRuntime,
        *,
        stop_reason: str,
        message: str,
    ) -> None:
        if stop_reason not in runtime.skip_reasons:
            runtime.skip_reasons.append(stop_reason)
        runtime.state = Btc15mTerminalState.SKIPPED
        runtime.stop_reason = stop_reason
        self._record_terminal_event(runtime, kind="skip", status="fail", message=message)

    def _terminal_runtime_complete(
        self,
        runtime: _TerminalRuntime,
        observed_at: datetime,
    ) -> bool:
        """Decide when a bounded terminal session should stop."""
        if runtime.state in {Btc15mTerminalState.RESOLVED, Btc15mTerminalState.SKIPPED}:
            return True
        if runtime.state is Btc15mTerminalState.OBSERVE_ONLY:
            window_end_dt = runtime.resolved.window_end_dt
            if window_end_dt is None:
                return False
            end_grace = window_end_dt + timedelta(
                seconds=_default_timing_controls().post_end_grace_window_seconds
            )
            if observed_at >= end_grace:
                if runtime.stop_reason == "running":
                    runtime.stop_reason = "observe_only_complete"
                return True
        return False

    def _maybe_apply_terminal_decision(
        self,
        runtime: _TerminalRuntime,
        now: datetime,
    ) -> None:
        if runtime.selected_side in {"UP", "DOWN"}:
            return
        resolved = runtime.resolved
        if resolved.window_start_dt is None or runtime.start_price_proxy_v1 is None:
            return
        decision_time = resolved.window_start_dt + MINUTE_FIVE_OFFSET
        if now < decision_time:
            return
        boundary_decision = self._build_terminal_boundary_decision(runtime)
        decision, decision_at, skip_reasons, reason_blocks = self._decide_window(
            resolved,
            boundary_decision=boundary_decision,
            chainlink_ticks=runtime.chainlink_ticks,
            binance_ticks=runtime.binance_ticks,
        )
        runtime.decision_at = decision_at
        runtime.reason_blocks.extend(reason_blocks)
        for reason in skip_reasons:
            if reason not in runtime.skip_reasons:
                runtime.skip_reasons.append(reason)
        if decision == "SKIP":
            self._mark_terminal_skipped(
                runtime,
                stop_reason=skip_reasons[0] if skip_reasons else "direction_lock_skip",
                message="BTC15m direction lock failed at minute 5.",
            )
            return

        runtime.selected_side = decision
        target = _resolve_target_token(
            resolved.window.token_ids,
            resolved.window.outcomes,
            decision,
        )
        if target is None:
            self._mark_terminal_skipped(
                runtime,
                stop_reason="unresolved_outcome_mapping",
                message="Could not map the BTC15m direction to a target token.",
            )
            return
        runtime.target_token_id, runtime.target_outcome = target
        if not runtime.rungs:
            runtime.rungs = [
                _TerminalRungRuntime(
                    price=price,
                    notional_usdc=notional,
                    quantity=(notional / price).quantize(
                        Decimal("0.000001"),
                        rounding=ROUND_DOWN,
                    ),
                )
                for price, notional in zip(
                    RUNG_PRICES,
                    runtime.rung_notionals_usdc,
                    strict=True,
                )
            ]

        decision_record = self._build_terminal_window_record(runtime, recorded_at=now)
        decision_sample = _select_decision_liquidity_sample(
            decision_record.liquidity_samples,
            decision_time,
        )
        if decision_sample is None:
            self._mark_terminal_skipped(
                runtime,
                stop_reason="missing_decision_liquidity_sample",
                message="No decision-time liquidity sample was available within five seconds.",
            )
            return
        guard_skip_reasons, guard_reasons, manipulation_flags = _evaluate_liquidity_guards(
            record=decision_record,
            decision_sample=decision_sample,
            direction=decision,
        )
        runtime.reason_blocks.extend(guard_reasons)
        for flag in manipulation_flags:
            if flag not in runtime.manipulation_flags:
                runtime.manipulation_flags.append(flag)
        if guard_skip_reasons:
            for reason in guard_skip_reasons:
                if reason not in runtime.skip_reasons:
                    runtime.skip_reasons.append(reason)
            self._mark_terminal_skipped(
                runtime,
                stop_reason=guard_skip_reasons[0],
                message="BTC15m liquidity or manipulation guard rejected the window.",
            )
            return
        self._record_terminal_event(
            runtime,
            kind="direction_lock",
            status="pass",
            message=f"Locked BTC15m direction to {decision}.",
        )

    def _apply_terminal_paper_rungs(
        self,
        runtime: _TerminalRuntime,
        now: datetime,
    ) -> None:
        resolved = runtime.resolved
        if resolved.window_start_dt is None or runtime.target_token_id is None:
            return
        minute_five = resolved.window_start_dt + MINUTE_FIVE_OFFSET
        minute_ten = resolved.window_start_dt + MINUTE_TEN_OFFSET
        if now < minute_five:
            return
        selected_level = None
        for sample in reversed(runtime.liquidity_samples):
            level = _polymarket_level(sample, runtime.target_token_id)
            if level is not None:
                selected_level = level
                break
        for rung in runtime.rungs:
            if rung.state == "filled":
                continue
            if now >= minute_ten:
                if rung.state != "cancelled":
                    rung.state = "cancelled"
                    rung.cancellation_at = _isoformat(now)
                    self._record_terminal_event(
                        runtime,
                        kind="rung_cancel",
                        status="info",
                        message=f"Cancelled paper rung {rung.price} at entry-window close.",
                    )
                continue
            if rung.state != "armed" or selected_level is None:
                continue
            best_ask = _decimal_optional(selected_level.best_ask)
            visible = _ask_liquidity_at_or_better(selected_level.asks, rung.price)
            if best_ask is None or best_ask > rung.price or visible < rung.quantity:
                continue
            rung.state = "filled"
            rung.fill_at = _isoformat(now)
            rung.fill_price = _decimal_text(rung.price)
            if runtime.first_fill_at is None:
                runtime.first_fill_at = rung.fill_at
            self._record_terminal_event(
                runtime,
                kind="rung_fill",
                status="pass",
                message=f"Filled paper rung {rung.price} on live public market data.",
            )

    def _apply_terminal_live_rungs(
        self,
        runtime: _TerminalRuntime,
        now: datetime,
        *,
        confirm_action: Callable[[str], bool | None] | None,
    ) -> None:
        resolved = runtime.resolved
        if resolved.window_start_dt is None:
            return
        minute_five = resolved.window_start_dt + MINUTE_FIVE_OFFSET
        minute_ten = resolved.window_start_dt + MINUTE_TEN_OFFSET
        for rung in runtime.rungs:
            if rung.state == "posted" and rung.order_id is not None:
                self._poll_live_rung_orders(runtime, rung)
        if now < minute_five:
            return
        if now >= minute_ten:
            for rung in runtime.rungs:
                if rung.state == "armed" and rung.cancellation_at is None:
                    rung.state = "cancelled"
                    rung.cancellation_at = _isoformat(now)
            remaining_posted = [item for item in runtime.rungs if item.state == "posted"]
            if remaining_posted and not any(item.cancel_attempted for item in remaining_posted):
                self._attempt_live_cancel(runtime, now, confirm_action=confirm_action)
            return
        for rung in runtime.rungs:
            if rung.state != "armed" or rung.post_attempted:
                continue
            rung.post_attempted = True
            prompt = (
                f"Post BTC15m {runtime.selected_side} rung at {rung.price} "
                f"for {rung.quantity} shares?"
            )
            decision = confirm_action(prompt) if confirm_action is not None else None
            if decision is not True:
                rung.state = "cancelled"
                rung.cancellation_at = _isoformat(now)
                self._record_terminal_event(
                    runtime,
                    kind="confirm",
                    status="skip",
                    message=f"Operator declined live rung {rung.price}.",
                )
                continue
            self._attempt_live_rung_post(runtime, rung, now)

    def _attempt_live_rung_post(
        self,
        runtime: _TerminalRuntime,
        rung: _TerminalRungRuntime,
        now: datetime,
    ) -> None:
        market_ref = runtime.resolved.window.condition_id or runtime.resolved.window.market_slug
        try:
            response = self._order_lifecycle.post(
                market_ref=market_ref,
                outcome=(runtime.selected_side or "").lower(),
                side="buy",
                price=_decimal_text(rung.price),
                size=_decimal_text(rung.quantity),
                live=True,
                confirm=True,
            )
        except (ExecutionValidationError, Exception) as exc:
            runtime.errors.append(_section_error("terminal_live_post", exc))
            rung.state = "cancelled"
            rung.cancellation_at = _isoformat(now)
            self._record_terminal_event(
                runtime,
                kind="rung_post",
                status="fail",
                message=f"Live rung {rung.price} failed: {exc}",
            )
            return
        order_id = _extract_live_order_id(response.live_response)
        if response.decision == "POSTED" and order_id is not None:
            rung.state = "posted"
            rung.order_id = order_id
            self._record_terminal_event(
                runtime,
                kind="rung_post",
                status="pass",
                message=f"Posted live rung {rung.price} as order {order_id}.",
            )
            return
        rung.state = "cancelled"
        rung.cancellation_at = _isoformat(now)
        self._record_terminal_event(
            runtime,
            kind="rung_post",
            status="fail",
            message=f"Live rung {rung.price} was not accepted for posting.",
        )

    def _poll_live_rung_orders(
        self,
        runtime: _TerminalRuntime,
        rung: _TerminalRungRuntime,
    ) -> None:
        if rung.order_id is None:
            return
        try:
            order_response = self._order_lifecycle.order_get(order_id=rung.order_id)
        except (ExecutionValidationError, Exception) as exc:
            runtime.errors.append(_section_error("terminal_live_order_get", exc))
            return
        order = order_response.order
        status = (order.status or "").strip().lower()
        remaining = order.remaining_size
        if _order_status_is_filled(status, remaining):
            if rung.state != "filled":
                rung.state = "filled"
                rung.fill_at = order.created_at or _isoformat(self._now())
                rung.fill_price = _decimal_text(rung.price)
                if runtime.first_fill_at is None:
                    runtime.first_fill_at = rung.fill_at
                self._record_terminal_event(
                    runtime,
                    kind="rung_fill",
                    status="pass",
                    message=f"Live rung {rung.price} filled.",
                )
        elif _order_status_is_cancelled(status):
            if rung.state != "cancelled":
                rung.state = "cancelled"
                rung.cancellation_at = order.created_at or _isoformat(self._now())
                self._record_terminal_event(
                    runtime,
                    kind="rung_cancel",
                    status="info",
                    message=f"Live rung {rung.price} was cancelled.",
                )

    def _attempt_live_cancel(
        self,
        runtime: _TerminalRuntime,
        now: datetime,
        *,
        confirm_action: Callable[[str], bool | None] | None,
    ) -> None:
        remaining_posted = [item for item in runtime.rungs if item.state == "posted"]
        if not remaining_posted:
            return
        for item in remaining_posted:
            item.cancel_attempted = True
        decision = (
            confirm_action("Cancel remaining open BTC15m live rungs at minute 10?")
            if confirm_action is not None
            else None
        )
        if decision is not True:
            self._record_terminal_event(
                runtime,
                kind="confirm",
                status="skip",
                message="Operator declined live BTC15m cancel at minute 10.",
            )
            runtime.stop_reason = "operator_declined_cancel"
            return
        market_ref = runtime.resolved.window.condition_id or runtime.resolved.window.market_slug
        try:
            response = self._order_lifecycle.cancel_market(
                market=market_ref,
                token_id=runtime.target_token_id,
                live=True,
                confirm=True,
            )
        except (ExecutionValidationError, Exception) as exc:
            runtime.errors.append(_section_error("terminal_live_cancel", exc))
            self._record_terminal_event(
                runtime,
                kind="rung_cancel",
                status="fail",
                message=f"Live cancel failed: {exc}",
            )
            return
        if response.decision == "CANCELLED":
            for item in remaining_posted:
                item.state = "cancelled"
                item.cancellation_at = _isoformat(now)
            self._record_terminal_event(
                runtime,
                kind="rung_cancel",
                status="pass",
                message="Cancelled remaining BTC15m live rung orders.",
            )

    def _update_terminal_favorable_metrics(
        self,
        runtime: _TerminalRuntime,
        now: datetime,
    ) -> None:
        if runtime.first_fill_at is None:
            return
        total_quantity, total_cost, _ = _terminal_position_summary(runtime.rungs)
        if total_quantity <= 0:
            return
        midpoint = None
        if runtime.target_token_id is not None:
            for sample in reversed(runtime.market_samples):
                if sample.token_id == runtime.target_token_id and sample.midpoint is not None:
                    midpoint = _decimal_optional(sample.midpoint)
                    if midpoint is not None:
                        break
        if midpoint is None:
            return
        pnl = (total_quantity * midpoint) - total_cost
        runtime.favorable_marks.append(
            Btc15mPriceMark(
                observed_at=_isoformat(now),
                midpoint=_decimal_text(midpoint),
                pnl_usdc=_decimal_text(pnl),
            )
        )
        if len(runtime.favorable_marks) > DEFAULT_TERMINAL_SNAPSHOT_LOG_LIMIT:
            runtime.favorable_marks[:] = runtime.favorable_marks[
                -DEFAULT_TERMINAL_SNAPSHOT_LOG_LIMIT :
            ]
        if len(runtime.favorable_marks) == 1 or pnl > runtime.mfe:
            runtime.mfe = pnl
            runtime.max_favorable_price = _decimal_text(midpoint)
            first_fill_dt = _parse_iso_timestamp(runtime.first_fill_at)
            runtime.time_to_peak_seconds = int((now - first_fill_dt).total_seconds())
        if len(runtime.favorable_marks) == 1 or pnl < runtime.mae:
            runtime.mae = pnl

    def _build_terminal_snapshot(
        self,
        runtime: _TerminalRuntime,
        sampled_at_dt: datetime,
    ) -> Btc15mDashboardSnapshotRecord:
        selected_level = None
        up_level = None
        down_level = None
        if runtime.target_token_id is not None:
            for sample in reversed(runtime.liquidity_samples):
                selected_level = _polymarket_level(sample, runtime.target_token_id)
                if selected_level is not None:
                    break
        total_quantity, total_cost, avg_entry = _terminal_position_summary(runtime.rungs)
        countdown = _terminal_countdown_seconds(runtime, sampled_at_dt)
        latest_liquidity = runtime.liquidity_samples[-1] if runtime.liquidity_samples else None
        binance = latest_liquidity.binance if latest_liquidity is not None else None
        if latest_liquidity is not None:
            up_level = _polymarket_level_by_outcome(latest_liquidity, "up")
            down_level = _polymarket_level_by_outcome(latest_liquidity, "down")
        current_chainlink_price = (
            runtime.chainlink_ticks[-1].value if runtime.chainlink_ticks else None
        )
        current_binance_price = (
            runtime.binance_ticks[-1].value if runtime.binance_ticks else None
        )
        page_mirror = self._build_terminal_display_truth(
            runtime,
            countdown_seconds=countdown,
        )
        market_truth = self._build_terminal_market_truth(
            runtime,
            countdown_seconds=countdown,
            current_chainlink_price=current_chainlink_price,
            up_level=up_level,
            down_level=down_level,
        )
        presenter = self._build_terminal_presenter(
            market_truth=market_truth,
            page_mirror=page_mirror,
        )
        return Btc15mDashboardSnapshotRecord(
            snapshot_id=_make_id("btc15m_terminal_snapshot"),
            session_id=runtime.session_id,
            window_id=runtime.resolved.window.window_id,
            market_slug=runtime.resolved.window.market_slug,
            sampled_at=_isoformat(sampled_at_dt),
            view_kind="terminal",
            mode=runtime.mode,
            attach_mode=runtime.attach_mode,
            observe_only=runtime.observe_only,
            window_status=runtime.state.value,
            boundary_status=runtime.boundary_status,
            window_start_at=runtime.resolved.window.window_start_at,
            window_end_at=runtime.resolved.window.window_end_at,
            countdown_seconds=countdown,
            display=page_mirror,
            page_mirror=page_mirror,
            market_truth=market_truth,
            terminal_presenter=presenter,
            current_window_label=page_mirror.display_window_label,
            page_parity_source=page_mirror.display_source,
            page_parity_url=page_mirror.display_url,
            current_live_btc_price=page_mirror.display_current_btc,
            up_price=page_mirror.display_up_price,
            down_price=page_mirror.display_down_price,
            display_volume=page_mirror.display_volume,
            selected_side=market_truth.selected_side,
            current_chainlink_price=market_truth.current_chainlink_price,
            current_binance_price=current_binance_price,
            start_price_proxy_v1=market_truth.start_price_proxy_v1,
            price_to_beat=page_mirror.display_price_to_beat,
            direction_lock_status=market_truth.direction_lock_status,
            target_token_id=market_truth.target_token_id,
            target_outcome=market_truth.target_outcome,
            paper_budget_usdc=market_truth.paper_budget_usdc,
            rung_notionals_usdc=list(market_truth.rung_notionals_usdc),
            avg_entry_price=market_truth.avg_entry_price,
            exposure_quantity=market_truth.exposure_quantity,
            exposure_notional_usdc=market_truth.exposure_notional_usdc,
            current_midpoint=market_truth.current_midpoint,
            current_spread=market_truth.current_spread,
            market_open_interest=market_truth.market_open_interest,
            market_volume=market_truth.market_volume,
            binance_best_bid=binance.book_ticker.bid_price if binance is not None else None,
            binance_best_ask=binance.book_ticker.ask_price if binance is not None else None,
            binance_near_touch_bid_depth=(
                binance.near_touch_bid_depth if binance is not None else None
            ),
            binance_near_touch_ask_depth=(
                binance.near_touch_ask_depth if binance is not None else None
            ),
            binance_realized_vol_1m_bps=(
                binance.realized_vol_1m_bps if binance is not None else None
            ),
            binance_realized_vol_3m_bps=(
                binance.realized_vol_3m_bps if binance is not None else None
            ),
            binance_volume_1m=_binance_volume_proxy(latest_liquidity, minutes=1),
            binance_volume_3m=_binance_volume_proxy(latest_liquidity, minutes=3),
            binance_near_touch_imbalance=_binance_near_touch_imbalance(binance),
            visible_liquidity_030=market_truth.visible_liquidity_030,
            visible_liquidity_020=market_truth.visible_liquidity_020,
            visible_liquidity_010=market_truth.visible_liquidity_010,
            manipulation_flags=list(market_truth.manipulation_flags),
            polymarket_levels=(latest_liquidity.polymarket if latest_liquidity is not None else []),
            up_side=market_truth.up_side,
            down_side=market_truth.down_side,
            rungs=list(market_truth.rungs),
            latest_events=list(runtime.events),
            mfe_usdc=_decimal_text(runtime.mfe) if runtime.favorable_marks else None,
            mae_usdc=_decimal_text(runtime.mae) if runtime.favorable_marks else None,
            max_favorable_price=runtime.max_favorable_price,
            time_to_peak_seconds=runtime.time_to_peak_seconds,
            errors=list(runtime.errors)
            + (latest_liquidity.errors if latest_liquidity is not None else []),
        )

    def _build_terminal_display_truth(
        self,
        runtime: _TerminalRuntime,
        *,
        countdown_seconds: int | None,
    ) -> Btc15mTerminalPageMirror:
        fallback = runtime.page_parity_fallback or Btc15mPageParityData()
        notes = list(fallback.notes)
        market = runtime.current_market
        if market is None:
            market = self._get_market_by_slug_or_none(runtime.resolved.window.market_slug)
            runtime.current_market = market
        field_sources: dict[str, str] = {}
        display_window_label = fallback.current_window_label or _window_label(
            runtime.resolved.window
        )
        display_price_to_beat = _page_exact_field_value(fallback, "price_to_beat")
        if display_price_to_beat is not None:
            field_sources["price_to_beat"] = "page_exact"
        else:
            notes.append("price_to_beat_page_exact_unavailable")
        display_current_btc = _page_exact_field_value(fallback, "current_live_btc_price")
        if display_current_btc is not None:
            field_sources["current_live_btc_price"] = "page_exact"
        else:
            notes.append("current_btc_page_exact_unavailable")
        display_up_price = _page_exact_field_value(fallback, "up_price")
        if display_up_price is not None:
            field_sources["up_price"] = "page_exact"
        else:
            notes.append("up_price_page_exact_unavailable")
        display_down_price = _page_exact_field_value(fallback, "down_price")
        if display_down_price is not None:
            field_sources["down_price"] = "page_exact"
        else:
            notes.append("down_price_page_exact_unavailable")
        display_volume = _page_exact_field_value(fallback, "volume")
        if display_volume is not None:
            field_sources["volume"] = "page_exact"
        else:
            notes.append("display_volume_page_exact_unavailable")
        display_source = (
            "page_exact"
            if not fallback.stale and _terminal_display_has_full_exact_fields(field_sources)
            else "page_unavailable"
        )
        return Btc15mTerminalPageMirror(
            display_price_to_beat=display_price_to_beat,
            display_current_btc=display_current_btc,
            display_up_price=display_up_price,
            display_down_price=display_down_price,
            display_countdown=_format_terminal_countdown(countdown_seconds),
            display_volume=display_volume,
            display_source=display_source,
            display_window_label=display_window_label,
            display_url=fallback.event_url or _market_page_url(market),
            display_observed_at=fallback.observed_at,
            display_stale=fallback.stale,
            display_notes=notes,
        )

    def _build_terminal_market_truth(
        self,
        runtime: _TerminalRuntime,
        *,
        countdown_seconds: int | None,
        current_chainlink_price: str | None,
        up_level: Btc15mPolymarketLiquidityLevel | None,
        down_level: Btc15mPolymarketLiquidityLevel | None,
    ) -> Btc15mTerminalMarketTruth:
        selected_level = None
        if runtime.target_token_id is not None:
            for sample in reversed(runtime.liquidity_samples):
                selected_level = _polymarket_level(sample, runtime.target_token_id)
                if selected_level is not None:
                    break
        total_quantity, total_cost, avg_entry = _terminal_position_summary(runtime.rungs)
        derived_up_price, derived_up_price_source = _derive_market_context_price(
            up_level,
            market_samples=runtime.market_samples,
        )
        derived_down_price, derived_down_price_source = _derive_market_context_price(
            down_level,
            market_samples=runtime.market_samples,
        )
        return Btc15mTerminalMarketTruth(
            market_slug=runtime.resolved.window.market_slug,
            window_start_at=runtime.resolved.window.window_start_at,
            window_end_at=runtime.resolved.window.window_end_at,
            countdown_seconds=countdown_seconds,
            countdown=_format_terminal_countdown(countdown_seconds),
            boundary_status=runtime.boundary_status,
            direction_lock_status=(
                runtime.selected_side if runtime.selected_side is not None else runtime.state.value
            ),
            selected_side=runtime.selected_side,
            target_token_id=runtime.target_token_id,
            target_outcome=runtime.target_outcome,
            current_chainlink_price=current_chainlink_price,
            start_price_proxy_v1=runtime.start_price_proxy_v1,
            end_price_proxy_v1=runtime.end_price_proxy_v1,
            paper_budget_usdc=_decimal_text(runtime.paper_budget_usdc),
            rung_notionals_usdc=[
                _decimal_text(notional) for notional in runtime.rung_notionals_usdc
            ],
            avg_entry_price=avg_entry,
            exposure_quantity=_decimal_text(total_quantity) if total_quantity > 0 else None,
            exposure_notional_usdc=_decimal_text(total_cost) if total_cost > 0 else None,
            current_midpoint=selected_level.midpoint if selected_level is not None else None,
            current_spread=selected_level.spread if selected_level is not None else None,
            market_open_interest=runtime.market_open_interest,
            market_volume=runtime.market_volume,
            visible_liquidity_030=(
                selected_level.visible_liquidity_030 if selected_level is not None else None
            ),
            visible_liquidity_020=(
                selected_level.visible_liquidity_020 if selected_level is not None else None
            ),
            visible_liquidity_010=(
                selected_level.visible_liquidity_010 if selected_level is not None else None
            ),
            derived_up_price=derived_up_price,
            derived_up_price_source=derived_up_price_source,
            derived_down_price=derived_down_price,
            derived_down_price_source=derived_down_price_source,
            up_side=_dashboard_side_state(
                up_level,
                last_trade_price=_latest_market_sample_last_trade_price(
                    runtime.market_samples,
                    up_level.token_id if up_level is not None else None,
                ),
            ),
            down_side=_dashboard_side_state(
                down_level,
                last_trade_price=_latest_market_sample_last_trade_price(
                    runtime.market_samples,
                    down_level.token_id if down_level is not None else None,
                ),
            ),
            rungs=[
                Btc15mDashboardRungState(
                    price=_decimal_text(item.price),
                    state=item.state,
                    notional_usdc=_decimal_text(item.notional_usdc),
                    quantity=_decimal_text(item.quantity),
                    visible_liquidity=(
                        _terminal_rung_visible_liquidity(selected_level, item.price)
                        if selected_level is not None
                        else None
                    ),
                    order_id=item.order_id,
                    fill_at=item.fill_at,
                    fill_price=item.fill_price,
                    cancellation_at=item.cancellation_at,
                )
                for item in runtime.rungs
            ],
            manipulation_flags=sorted(set(runtime.manipulation_flags + runtime.skip_reasons)),
        )

    def _build_terminal_presenter(
        self,
        *,
        market_truth: Btc15mTerminalMarketTruth,
        page_mirror: Btc15mTerminalPageMirror,
    ) -> Btc15mTerminalPresenter:
        page_state = "unavailable"
        if page_mirror.display_stale and page_mirror.display_source == "page_unavailable":
            page_state = "stale"
        elif page_mirror.display_source == "page_exact":
            page_state = "exact"
        show_binance = page_state != "exact" or any(
            "binance" in flag or "divergence" in flag for flag in market_truth.manipulation_flags
        )
        return Btc15mTerminalPresenter(
            primary_block_source="page_mirror",
            primary_block_state=page_state,
            market_context_source="market_truth",
            strategy_source="market_truth",
            show_binance_diagnostics=show_binance,
        )

    def _build_terminal_boundary_decision(
        self,
        runtime: _TerminalRuntime,
    ) -> Btc15mBoundaryDecisionRecord:
        notes: list[str] = []
        if runtime.start_price_proxy_v1 is None:
            notes.append("Missing post-start Chainlink boundary tick.")
        if runtime.end_price_proxy_v1 is None:
            notes.append("Missing post-end Chainlink boundary tick.")
        return Btc15mBoundaryDecisionRecord(
            window_id=runtime.resolved.window.window_id,
            condition_id=runtime.resolved.window.condition_id,
            market_slug=runtime.resolved.window.market_slug,
            created_at=_isoformat(self._now()),
            status=runtime.boundary_status,
            pre_start=runtime.boundary_pre_start,
            post_start=runtime.boundary_post_start,
            pre_end=runtime.boundary_pre_end,
            post_end=runtime.boundary_post_end,
            timing_source=runtime.resolved.window.timing_source,
            timing_controls=_default_timing_controls(),
            start_price_proxy_v1=runtime.start_price_proxy_v1,
            end_price_proxy_v1=runtime.end_price_proxy_v1,
            notes=notes,
        )

    def _build_terminal_window_record(
        self,
        runtime: _TerminalRuntime,
        *,
        recorded_at: datetime,
    ) -> Btc15mWindowRecord:
        resolution_result = "PENDING"
        if runtime.start_price_proxy_v1 is not None and runtime.end_price_proxy_v1 is not None:
            resolution_result = self._resolve_market_outcome(
                self._build_terminal_boundary_decision(runtime)
            )
        decision = "PENDING"
        if runtime.selected_side in {"UP", "DOWN"}:
            decision = runtime.selected_side
        elif runtime.state is Btc15mTerminalState.SKIPPED:
            decision = "SKIP"
        return Btc15mWindowRecord(
            window=runtime.resolved.window,
            recorded_at=_isoformat(recorded_at),
            recorder_session_id=runtime.session_id,
            status=(
                "complete"
                if runtime.boundary_status == "complete"
                and runtime.state in {Btc15mTerminalState.RESOLVED, Btc15mTerminalState.SKIPPED}
                else "partial"
            ),
            mode=runtime.mode,
            target_slug=runtime.resolved.target_slug,
            selection_source=runtime.resolved.selection_source,
            chainlink_ticks=list(runtime.chainlink_ticks),
            binance_ticks=list(runtime.binance_ticks),
            market_samples=list(runtime.market_samples),
            liquidity_samples=list(runtime.liquidity_samples),
            boundary_status=runtime.boundary_status,
            timing_controls=_default_timing_controls(),
            start_price_proxy_v1=runtime.start_price_proxy_v1,
            end_price_proxy_v1=runtime.end_price_proxy_v1,
            paper_budget_usdc=_decimal_text(runtime.paper_budget_usdc),
            rung_notionals_usdc=[
                _decimal_text(notional) for notional in runtime.rung_notionals_usdc
            ],
            decision=decision,
            decision_at=runtime.decision_at,
            resolution_result=resolution_result,
            manipulation_flags=list(runtime.manipulation_flags),
            skip_reasons=list(runtime.skip_reasons),
            reason_blocks=list(runtime.reason_blocks),
            errors=list(runtime.errors),
        )

    def _finalize_terminal_window(
        self,
        runtime: _TerminalRuntime,
        *,
        total_snapshots: int = 0,
    ) -> Btc15mTerminalWindowTearSheet:
        finalized_at = self._now()
        boundary_decision = self._build_terminal_boundary_decision(runtime)
        self._state.append_boundary_observations(_terminal_boundary_observations(runtime))
        self._state.append_boundary_decision(boundary_decision)
        if runtime.liquidity_samples:
            self._state.append_liquidity_samples(runtime.liquidity_samples)
        window_record = self._build_terminal_window_record(runtime, recorded_at=finalized_at)
        self._state.append_windows([window_record])
        evaluation = None
        if window_record.decision in {"UP", "DOWN", "SKIP"}:
            evaluation = self._evaluate_window(window_record, source_kind="terminal")
            if runtime.mode is Btc15mRunMode.PAPER:
                self._state.append_paper_run(
                    Btc15mPaperRunRecord(
                        run_id=_make_id("btc15m_paper_run"),
                        created_at=_isoformat(finalized_at),
                        limit=1,
                        mode=runtime.mode,
                        target_slug=runtime.resolved.target_slug,
                        selection_source=runtime.resolved.selection_source,
                        source_kind="terminal",
                        items=[evaluation],
                        total_considered=1,
                        total_evaluated=1,
                        total_skipped=1 if evaluation.decision == "SKIP" else 0,
                        total_realized_pnl_usdc=evaluation.realized_pnl_usdc,
                    )
                )
        total_quantity, total_cost, avg_entry = _terminal_position_summary(runtime.rungs)
        latest_snapshot = runtime.latest_snapshot
        latest_display = _snapshot_display_truth(latest_snapshot)
        latest_page_mirror = _snapshot_page_mirror(latest_snapshot)
        latest_market_truth = _snapshot_market_truth(latest_snapshot)
        latest_presenter = _snapshot_terminal_presenter(latest_snapshot)
        tear_sheet = Btc15mTerminalWindowTearSheet(
            window=runtime.resolved.window,
            started_at=_isoformat(runtime.window_started_at_dt or runtime.started_at_dt),
            ended_at=_isoformat(finalized_at),
            mode=runtime.mode,
            attach_mode=runtime.attach_mode,
            observe_only=runtime.observe_only,
            stop_reason=runtime.stop_reason,
            final_state=runtime.state,
            boundary_status=runtime.boundary_status,
            display=latest_display,
            page_mirror=latest_page_mirror,
            market_truth=latest_market_truth,
            terminal_presenter=latest_presenter,
            current_window_label=(
                latest_display.display_window_label if latest_display is not None else None
            ),
            page_parity_source=(
                latest_display.display_source if latest_display is not None else None
            ),
            page_parity_url=(
                latest_display.display_url if latest_display is not None else None
            ),
            price_to_beat=(
                latest_display.display_price_to_beat if latest_display is not None else None
            ),
            current_live_btc_price=(
                latest_display.display_current_btc if latest_display is not None else None
            ),
            up_price=latest_display.display_up_price if latest_display is not None else None,
            down_price=latest_display.display_down_price if latest_display is not None else None,
            display_volume=latest_display.display_volume if latest_display is not None else None,
            selected_side=runtime.selected_side,
            target_token_id=runtime.target_token_id,
            target_outcome=runtime.target_outcome,
            paper_budget_usdc=_decimal_text(runtime.paper_budget_usdc),
            rung_notionals_usdc=[
                _decimal_text(notional) for notional in runtime.rung_notionals_usdc
            ],
            avg_entry_price=avg_entry,
            exposure_quantity=_decimal_text(total_quantity) if total_quantity > 0 else None,
            exposure_notional_usdc=_decimal_text(total_cost) if total_cost > 0 else None,
            filled_rung_count=sum(1 for item in runtime.rungs if item.state == "filled"),
            posted_rung_count=sum(1 for item in runtime.rungs if item.state == "posted"),
            cancelled_rung_count=sum(1 for item in runtime.rungs if item.state == "cancelled"),
            total_snapshots=total_snapshots,
            market_open_interest=runtime.market_open_interest,
            market_volume=runtime.market_volume,
            manipulation_flags=sorted(set(runtime.manipulation_flags + runtime.skip_reasons)),
            skip_reasons=list(runtime.skip_reasons),
            latest_snapshot=latest_snapshot,
            latest_evaluation=evaluation,
            rungs=[
                Btc15mDashboardRungState(
                    price=_decimal_text(item.price),
                    state=item.state,
                    notional_usdc=_decimal_text(item.notional_usdc),
                    quantity=_decimal_text(item.quantity),
                    order_id=item.order_id,
                    fill_at=item.fill_at,
                    fill_price=item.fill_price,
                    cancellation_at=item.cancellation_at,
                )
                for item in runtime.rungs
            ],
            operator_events=list(runtime.events),
            mfe_usdc=_decimal_text(runtime.mfe) if runtime.favorable_marks else None,
            mae_usdc=_decimal_text(runtime.mae) if runtime.favorable_marks else None,
            max_favorable_price=runtime.max_favorable_price,
            time_to_peak_seconds=runtime.time_to_peak_seconds,
            errors=list(runtime.errors),
        )
        runtime.window_finalized = True
        return tear_sheet

    def _finalize_terminal_session(self, runtime: _TerminalRuntime) -> Btc15mTerminalSessionRecord:
        finalized_at = self._now()
        latest_window = runtime.tear_sheets[-1] if runtime.tear_sheets else None
        return Btc15mTerminalSessionRecord(
            session_id=runtime.session_id,
            created_at=_isoformat(finalized_at),
            started_at=_isoformat(runtime.started_at_dt),
            ended_at=_isoformat(finalized_at),
            mode=runtime.mode,
            attach_mode=runtime.attach_mode,
            observe_only=runtime.observe_only,
            follow_current=runtime.follow_current,
            stop_reason=runtime.stop_reason,
            final_state=runtime.state,
            current_requested=runtime.attach_mode != "wait_next",
            window=latest_window.window if latest_window is not None else runtime.resolved.window,
            boundary_status=(
                latest_window.boundary_status
                if latest_window is not None
                else runtime.boundary_status
            ),
            display=latest_window.display if latest_window is not None else None,
            page_mirror=latest_window.page_mirror if latest_window is not None else None,
            market_truth=latest_window.market_truth if latest_window is not None else None,
            terminal_presenter=(
                latest_window.terminal_presenter if latest_window is not None else None
            ),
            current_window_label=(
                latest_window.current_window_label if latest_window is not None else None
            ),
            page_parity_source=(
                latest_window.page_parity_source if latest_window is not None else None
            ),
            page_parity_url=(
                latest_window.page_parity_url if latest_window is not None else None
            ),
            price_to_beat=latest_window.price_to_beat if latest_window is not None else None,
            current_live_btc_price=(
                latest_window.current_live_btc_price if latest_window is not None else None
            ),
            up_price=latest_window.up_price if latest_window is not None else None,
            down_price=latest_window.down_price if latest_window is not None else None,
            display_volume=latest_window.display_volume if latest_window is not None else None,
            selected_side=latest_window.selected_side if latest_window is not None else None,
            target_token_id=latest_window.target_token_id if latest_window is not None else None,
            target_outcome=latest_window.target_outcome if latest_window is not None else None,
            start_price_proxy_v1=runtime.start_price_proxy_v1,
            end_price_proxy_v1=runtime.end_price_proxy_v1,
            paper_budget_usdc=_decimal_text(runtime.paper_budget_usdc),
            rung_notionals_usdc=[
                _decimal_text(notional) for notional in runtime.rung_notionals_usdc
            ],
            avg_entry_price=latest_window.avg_entry_price if latest_window is not None else None,
            exposure_quantity=(
                latest_window.exposure_quantity if latest_window is not None else None
            ),
            exposure_notional_usdc=(
                latest_window.exposure_notional_usdc if latest_window is not None else None
            ),
            filled_rung_count=latest_window.filled_rung_count if latest_window is not None else 0,
            posted_rung_count=latest_window.posted_rung_count if latest_window is not None else 0,
            cancelled_rung_count=(
                latest_window.cancelled_rung_count if latest_window is not None else 0
            ),
            total_snapshots=runtime.total_snapshots,
            market_open_interest=latest_window.market_open_interest if latest_window else None,
            market_volume=latest_window.market_volume if latest_window else None,
            manipulation_flags=(
                latest_window.manipulation_flags if latest_window is not None else []
            ),
            latest_snapshot=runtime.latest_snapshot,
            latest_evaluation=(
                latest_window.latest_evaluation if latest_window is not None else None
            ),
            rungs=latest_window.rungs if latest_window is not None else [],
            window_tear_sheets=list(runtime.tear_sheets),
            rollover_history=list(runtime.rollover_history),
            rollover_count=max(0, len(runtime.tear_sheets) - 1),
            operator_events=list(runtime.session_events),
            errors=list(runtime.errors),
        )

    def _build_dashboard_snapshot(
        self,
        resolved: _ResolvedWindow,
        *,
        session_id: str,
    ) -> Btc15mDashboardSnapshotRecord:
        sampled_at_dt = self._now()
        errors: list[Btc15mSectionError] = []
        current_chainlink_tick, current_binance_tick, tick_errors = self._capture_current_ticks()
        errors.extend(tick_errors)
        try:
            liquidity_sample = self._capture_liquidity_sample(
                resolved,
                sample_kind="dashboard",
                scheduled_at_dt=sampled_at_dt,
            )
        except Exception as exc:
            liquidity_sample = None
            errors.append(_section_error("dashboard_liquidity", exc))

        latest_window = self._latest_window_record(resolved.window.window_id)
        latest_evaluation = self._latest_evaluation_for_window(resolved.window.window_id)
        boundary_decision = self._latest_boundary_decision(resolved.window.window_id)
        start_proxy = None
        if boundary_decision is not None:
            start_proxy = boundary_decision.start_price_proxy_v1
        if start_proxy is None and latest_window is not None:
            start_proxy = latest_window.start_price_proxy_v1

        direction_status = "pending"
        target_token_id: str | None = None
        target_outcome: str | None = None
        if latest_evaluation is not None:
            direction_status = latest_evaluation.decision
            target_token_id = latest_evaluation.target_token_id
            target_outcome = latest_evaluation.target_outcome
        elif latest_window is not None and latest_window.decision != "PENDING":
            direction_status = latest_window.decision
        elif (
            resolved.window_start_dt is not None
            and start_proxy is not None
            and sampled_at_dt
            >= resolved.window_start_dt
            + timedelta(seconds=_default_timing_controls().direction_lock_offset_seconds)
        ):
            direction_status = _direction_from_prices(
                start_proxy=start_proxy,
                chainlink_value=current_chainlink_tick.value if current_chainlink_tick else None,
                binance_value=current_binance_tick.value if current_binance_tick else None,
            )

        if direction_status in {"UP", "DOWN"}:
            target = _resolve_target_token(
                resolved.window.token_ids,
                resolved.window.outcomes,
                direction_status,
            )
            if target is not None:
                target_token_id, target_outcome = target

        selected_level = _select_dashboard_level(
            liquidity_sample,
            target_token_id=target_token_id,
        )
        rung_states = _dashboard_rung_states(
            evaluation=latest_evaluation,
            sampled_at=sampled_at_dt,
            resolved=resolved,
            selected_level=selected_level,
            direction_status=direction_status,
        )
        manipulation_flags = list(
            latest_window.manipulation_flags if latest_window is not None else []
        )
        if liquidity_sample is not None:
            for flag in _derive_manipulation_flags([liquidity_sample]):
                if flag not in manipulation_flags:
                    manipulation_flags.append(flag)
        total_quantity = Decimal("0")
        total_cost = Decimal("0")
        avg_entry = None
        up_snapshot = (
            _polymarket_level_by_outcome(liquidity_sample, "up")
            if liquidity_sample is not None
            else None
        )
        down_snapshot = (
            _polymarket_level_by_outcome(liquidity_sample, "down")
            if liquidity_sample is not None
            else None
        )
        if latest_evaluation is not None:
            for rung in latest_evaluation.rungs:
                if rung.status != "filled":
                    continue
                quantity = _decimal(rung.quantity)
                fill_price = _decimal(rung.fill_price or rung.price)
                total_quantity += quantity
                total_cost += quantity * fill_price
            if total_quantity > 0:
                avg_entry = _decimal_text(total_cost / total_quantity)
        latest_liquidity = liquidity_sample.binance if liquidity_sample is not None else None

        return Btc15mDashboardSnapshotRecord(
            snapshot_id=_make_id("btc15m_dashboard_snapshot"),
            session_id=session_id,
            window_id=resolved.window.window_id,
            market_slug=resolved.window.market_slug,
            sampled_at=_isoformat(sampled_at_dt),
            view_kind="dashboard",
            mode=Btc15mRunMode.PAPER,
            window_status=(
                latest_window.status if latest_window is not None else "current_monitor"
            ),
            boundary_status=(
                latest_window.boundary_status if latest_window is not None else "pending"
            ),
            window_start_at=resolved.window.window_start_at,
            window_end_at=resolved.window.window_end_at,
            countdown_seconds=_terminal_countdown_seconds(
                _TerminalRuntime(
                    session_id=session_id,
                    resolved=resolved,
                    mode=Btc15mRunMode.PAPER,
                    started_at_dt=sampled_at_dt,
                    state=Btc15mTerminalState.DIRECTION_LOCK_PENDING,
                ),
                sampled_at_dt,
            ),
            current_window_label=_window_label(resolved.window),
            page_parity_source="api",
            current_live_btc_price=(
                current_chainlink_tick.value if current_chainlink_tick is not None else None
            ),
            up_price=(
                _coalesce_price(
                    up_snapshot.midpoint if up_snapshot is not None else None,
                    up_snapshot.best_ask if up_snapshot is not None else None,
                )
            ),
            down_price=(
                _coalesce_price(
                    down_snapshot.midpoint if down_snapshot is not None else None,
                    down_snapshot.best_ask if down_snapshot is not None else None,
                )
            ),
            selected_side=direction_status if direction_status in {"UP", "DOWN"} else None,
            current_chainlink_price=(
                current_chainlink_tick.value if current_chainlink_tick else None
            ),
            current_binance_price=current_binance_tick.value if current_binance_tick else None,
            start_price_proxy_v1=start_proxy,
            price_to_beat=start_proxy,
            direction_lock_status=direction_status,
            target_token_id=target_token_id,
            target_outcome=target_outcome,
            avg_entry_price=avg_entry,
            exposure_quantity=_decimal_text(total_quantity) if total_quantity > 0 else None,
            exposure_notional_usdc=_decimal_text(total_cost) if total_cost > 0 else None,
            current_midpoint=selected_level.midpoint if selected_level is not None else None,
            current_spread=selected_level.spread if selected_level is not None else None,
            market_open_interest=getattr(latest_window, "market_open_interest", None),
            market_volume=getattr(latest_window, "market_volume", None),
            binance_best_bid=latest_liquidity.book_ticker.bid_price if latest_liquidity else None,
            binance_best_ask=latest_liquidity.book_ticker.ask_price if latest_liquidity else None,
            binance_near_touch_bid_depth=(
                latest_liquidity.near_touch_bid_depth if latest_liquidity else None
            ),
            binance_near_touch_ask_depth=(
                latest_liquidity.near_touch_ask_depth if latest_liquidity else None
            ),
            binance_realized_vol_1m_bps=(
                latest_liquidity.realized_vol_1m_bps if latest_liquidity else None
            ),
            binance_realized_vol_3m_bps=(
                latest_liquidity.realized_vol_3m_bps if latest_liquidity else None
            ),
            binance_volume_1m=_binance_volume_proxy(liquidity_sample, minutes=1),
            binance_volume_3m=_binance_volume_proxy(liquidity_sample, minutes=3),
            visible_liquidity_030=(
                selected_level.visible_liquidity_030 if selected_level is not None else None
            ),
            visible_liquidity_020=(
                selected_level.visible_liquidity_020 if selected_level is not None else None
            ),
            visible_liquidity_010=(
                selected_level.visible_liquidity_010 if selected_level is not None else None
            ),
            manipulation_flags=sorted(manipulation_flags),
            polymarket_levels=liquidity_sample.polymarket if liquidity_sample is not None else [],
            rungs=rung_states,
            latest_events=[],
            mfe_usdc=latest_evaluation.mfe_usdc if latest_evaluation is not None else None,
            mae_usdc=latest_evaluation.mae_usdc if latest_evaluation is not None else None,
            max_favorable_price=(
                latest_evaluation.max_favorable_price if latest_evaluation is not None else None
            ),
            time_to_peak_seconds=(
                latest_evaluation.time_to_peak_seconds if latest_evaluation is not None else None
            ),
            errors=errors + (liquidity_sample.errors if liquidity_sample is not None else []),
        )

    def _capture_current_ticks(
        self,
    ) -> tuple[Btc15mPriceTick | None, Btc15mPriceTick | None, list[Btc15mSectionError]]:
        async def _capture() -> tuple[
            Btc15mPriceTick | None,
            Btc15mPriceTick | None,
            list[Btc15mSectionError],
        ]:
            errors: list[Btc15mSectionError] = []
            results = await asyncio.gather(
                self._crypto_client.stream_symbol(
                    "BTC",
                    source="chainlink",
                    seconds=DEFAULT_LIVE_TICK_CAPTURE_SECONDS,
                    max_events=1,
                ),
                self._crypto_client.stream_symbol(
                    "BTC",
                    source="binance",
                    seconds=DEFAULT_LIVE_TICK_CAPTURE_SECONDS,
                    max_events=1,
                ),
                return_exceptions=True,
            )
            chainlink_result, binance_result = results
            chainlink_tick: Btc15mPriceTick | None = None
            binance_tick: Btc15mPriceTick | None = None
            if isinstance(chainlink_result, Exception):
                errors.append(_section_error("dashboard_chainlink", chainlink_result))
            else:
                assert isinstance(chainlink_result, CryptoStreamResponse)
                chainlink_tick = _last_price_tick(
                    self._to_price_ticks(chainlink_result.events, source="chainlink")
                )
            if isinstance(binance_result, Exception):
                errors.append(_section_error("dashboard_binance", binance_result))
            else:
                assert isinstance(binance_result, CryptoStreamResponse)
                binance_tick = _last_price_tick(
                    self._to_price_ticks(binance_result.events, source="binance")
                )
            return chainlink_tick, binance_tick, errors

        return asyncio.run(_capture())

    def _build_campaign_summary(
        self,
        *,
        campaigns: list[Btc15mCampaignRunRecord],
        evaluations: list[Btc15mPaperEvaluation],
    ) -> Btc15mCampaignReportSummary:
        total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in evaluations), Decimal("0"))
        average_pnl = total_pnl / Decimal(len(evaluations)) if evaluations else Decimal("0")
        spread_values = [_decimal_optional(item.decision_spread) for item in evaluations]
        spread_values = [item for item in spread_values if item is not None]
        vol_1m_values = [_decimal_optional(item.realized_vol_1m_bps) for item in evaluations]
        vol_1m_values = [item for item in vol_1m_values if item is not None]
        vol_3m_values = [_decimal_optional(item.realized_vol_3m_bps) for item in evaluations]
        vol_3m_values = [item for item in vol_3m_values if item is not None]
        skip_reason_counts: Counter[str] = Counter()
        wins = losses = ties = skips = 0
        for item in evaluations:
            if item.decision == "SKIP":
                skips += 1
                skip_reason_counts.update(item.skip_reasons)
                continue
            if item.resolution_result == "UNRESOLVED_TIE":
                ties += 1
                continue
            pnl = _decimal(item.realized_pnl_usdc)
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            else:
                ties += 1
        return Btc15mCampaignReportSummary(
            campaign_run_count=len(campaigns),
            evaluated_window_count=len(evaluations),
            total_realized_pnl_usdc=_decimal_text(total_pnl),
            average_realized_pnl_usdc=_decimal_text(average_pnl),
            win_count=wins,
            loss_count=losses,
            tie_count=ties,
            skip_count=skips,
            average_decision_spread=_average_decimal_text(spread_values),
            average_realized_vol_1m_bps=_average_decimal_text(vol_1m_values),
            average_realized_vol_3m_bps=_average_decimal_text(vol_3m_values),
            skip_reason_counts=dict(sorted(skip_reason_counts.items())),
        )

    def _build_initial_market_samples(
        self,
        resolved: _ResolvedWindow,
        *,
        errors: list[Btc15mSectionError],
    ) -> list[Btc15mMarketSample]:
        observed_at = _isoformat(self._now())
        samples: list[Btc15mMarketSample] = []
        outcome_map = _token_outcome_map(resolved.window.token_ids, resolved.window.outcomes)
        try:
            with self._clob_client_cls() as clob_client:
                for token_id in resolved.window.token_ids:
                    try:
                        book = clob_client.get_book(token_id)
                    except (ClobClientError, ClobNotFoundError) as exc:
                        errors.append(_section_error(f"clob_book:{token_id}", exc))
                        continue
                    midpoint = None
                    spread = None
                    try:
                        midpoint = clob_client.get_midpoint(token_id).midpoint
                    except (ClobClientError, ClobNotFoundError) as exc:
                        errors.append(_section_error(f"clob_midpoint:{token_id}", exc))
                    try:
                        spread = clob_client.get_spread(token_id).spread
                    except (ClobClientError, ClobNotFoundError) as exc:
                        errors.append(_section_error(f"clob_spread:{token_id}", exc))
                    samples.append(
                        Btc15mMarketSample(
                            token_id=token_id,
                            outcome=outcome_map.get(token_id),
                            event_type="clob_snapshot",
                            source="clob_snapshot",
                            captured_at=observed_at,
                            observed_at=observed_at,
                            best_bid=book.bids[0].price if book.bids else None,
                            best_ask=book.asks[0].price if book.asks else None,
                            midpoint=midpoint,
                            spread=spread,
                            bids=book.bids,
                            asks=book.asks,
                        )
                    )
        except TypeError:
            errors.append(
                Btc15mSectionError(
                    section="clob_snapshot",
                    code="request_failed",
                    message="Could not construct the public CLOB client.",
                )
            )
        return samples

    def _to_price_ticks(
        self,
        events: list[CapturedStreamEvent],
        *,
        source: str,
    ) -> list[Btc15mPriceTick]:
        items: list[Btc15mPriceTick] = []
        for event in events:
            if event.crypto_event is None:
                continue
            observed_at = _event_timestamp_to_iso(
                event.crypto_event.timestamp, fallback=event.captured_at
            )
            items.append(
                Btc15mPriceTick(
                    source=source,
                    captured_at=event.captured_at,
                    observed_at=observed_at,
                    value=event.crypto_event.value,
                )
            )
        items.sort(key=lambda item: item.observed_at)
        return items

    def _to_market_samples(
        self,
        events: list[CapturedStreamEvent],
        *,
        token_outcomes: dict[str, str],
    ) -> list[Btc15mMarketSample]:
        items: list[Btc15mMarketSample] = []
        for event in events:
            if event.market_event is None or event.market_event.token_id is None:
                continue
            observed_at = _event_timestamp_to_iso(
                event.market_event.timestamp, fallback=event.captured_at
            )
            items.append(
                Btc15mMarketSample(
                    token_id=event.market_event.token_id,
                    outcome=token_outcomes.get(event.market_event.token_id),
                    event_type=event.market_event.event_type,
                    source=event.source,
                    captured_at=event.captured_at,
                    observed_at=observed_at,
                    best_bid=event.market_event.best_bid,
                    best_ask=event.market_event.best_ask,
                    midpoint=event.market_event.midpoint,
                    spread=event.market_event.spread,
                    last_trade_price=event.market_event.price,
                    bids=event.market_event.bids,
                    asks=event.market_event.asks,
                )
            )
        return items

    def _build_boundaries(
        self,
        resolved: _ResolvedWindow,
        *,
        chainlink_ticks: list[Btc15mPriceTick],
        recorder_session_id: str,
    ) -> tuple[list[Btc15mBoundaryObservationRecord], Btc15mBoundaryDecisionRecord]:
        assert resolved.window_start_dt is not None
        assert resolved.window_end_dt is not None
        timing_controls = _default_timing_controls()
        pre_start = _latest_tick_before_or_at_within(
            chainlink_ticks,
            resolved.window_start_dt,
            timing_controls.pre_start_capture_window_seconds,
        )
        post_start = _first_tick_at_or_after_within(
            chainlink_ticks,
            resolved.window_start_dt,
            timing_controls.post_start_grace_window_seconds,
        )
        pre_end = _latest_tick_before_or_at_within(
            chainlink_ticks,
            resolved.window_end_dt,
            timing_controls.pre_end_capture_window_seconds,
        )
        post_end = _first_tick_at_or_after_within(
            chainlink_ticks,
            resolved.window_end_dt,
            timing_controls.post_end_grace_window_seconds,
        )
        persisted_decision = self._latest_boundary_decision(resolved.window.window_id)
        if persisted_decision is not None:
            pre_start = pre_start or persisted_decision.pre_start
            post_start = post_start or persisted_decision.post_start
            pre_end = pre_end or persisted_decision.pre_end
            post_end = post_end or persisted_decision.post_end

        observations = [
            _boundary_observation(
                resolved.window,
                boundary_kind="start",
                tick=pre_start,
                session_id=recorder_session_id,
                selection_status="selected_pre_start"
                if pre_start is not None
                else "missing_pre_start_capture_window",
            ),
            _boundary_observation(
                resolved.window,
                boundary_kind="start",
                tick=post_start,
                session_id=recorder_session_id,
                selection_status="selected_post_start"
                if post_start is not None
                else "missing_post_start_grace_expired",
            ),
            _boundary_observation(
                resolved.window,
                boundary_kind="end",
                tick=pre_end,
                session_id=recorder_session_id,
                selection_status="selected_pre_end"
                if pre_end is not None
                else "missing_pre_end_capture_window",
            ),
            _boundary_observation(
                resolved.window,
                boundary_kind="end",
                tick=post_end,
                session_id=recorder_session_id,
                selection_status="selected_post_end"
                if post_end is not None
                else "missing_post_end_grace_expired",
            ),
        ]

        notes: list[str] = []
        start_proxy = post_start.value if post_start is not None else None
        end_proxy = post_end.value if post_end is not None else None
        if start_proxy is None:
            notes.append(
                "Could not compute start_price_proxy_v1 because no "
                "Chainlink tick arrived within the post-start grace window."
            )
        if end_proxy is None:
            notes.append(
                "Could not compute end_price_proxy_v1 because no "
                "Chainlink tick arrived within the post-end grace window."
            )
        decision = Btc15mBoundaryDecisionRecord(
            window_id=resolved.window.window_id,
            condition_id=resolved.window.condition_id,
            market_slug=resolved.window.market_slug,
            created_at=_isoformat(self._now()),
            status="complete" if start_proxy is not None and end_proxy is not None else "partial",
            pre_start=pre_start,
            post_start=post_start,
            pre_end=pre_end,
            post_end=post_end,
            timing_source=resolved.window.timing_source,
            timing_controls=timing_controls,
            start_price_proxy_v1=start_proxy,
            end_price_proxy_v1=end_proxy,
            notes=notes,
        )
        return observations, decision

    def _decide_window(
        self,
        resolved: _ResolvedWindow,
        *,
        boundary_decision: Btc15mBoundaryDecisionRecord,
        chainlink_ticks: list[Btc15mPriceTick],
        binance_ticks: list[Btc15mPriceTick],
    ) -> tuple[str, str | None, list[str], list[Btc15mReasonBlock]]:
        assert resolved.window_start_dt is not None
        decision_time = resolved.window_start_dt + timedelta(
            seconds=boundary_decision.timing_controls.direction_lock_offset_seconds
        )
        decision_at = _isoformat(decision_time)
        reasons: list[Btc15mReasonBlock] = []
        skip_reasons: list[str] = []
        effective_start_proxy = _boundary_effective_start_proxy(boundary_decision)

        if effective_start_proxy is None:
            skip_reasons.append("missing_start_proxy")
            reasons.append(
                Btc15mReasonBlock(
                    section="start_proxy",
                    status="fail",
                    message="Could not derive the start-price proxy.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons

        chainlink_tick = _latest_tick_before(chainlink_ticks, decision_time)
        binance_tick = _latest_tick_before(binance_ticks, decision_time)
        if chainlink_tick is None:
            skip_reasons.append("missing_chainlink_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="chainlink_decision",
                    status="fail",
                    message="No Chainlink tick was available by the minute-5 decision point.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons
        if binance_tick is None:
            skip_reasons.append("missing_binance_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="binance_decision",
                    status="fail",
                    message="No Binance tick was available by the minute-5 decision point.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons

        if _is_stale_tick(chainlink_tick, decision_time, DEFAULT_DECISION_STALE_SECONDS):
            skip_reasons.append("stale_chainlink_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="chainlink_decision",
                    status="fail",
                    message="Chainlink decision tick was stale at minute 5.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons
        if _is_stale_tick(binance_tick, decision_time, DEFAULT_DECISION_STALE_SECONDS):
            skip_reasons.append("stale_binance_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="binance_decision",
                    status="fail",
                    message="Binance decision tick was stale at minute 5.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons

        start_proxy = _decimal(effective_start_proxy)
        chainlink_price = _decimal(chainlink_tick.value)
        binance_price = _decimal(binance_tick.value)
        if chainlink_price > start_proxy and binance_price > start_proxy:
            reasons.append(
                Btc15mReasonBlock(
                    section="direction_lock",
                    status="pass",
                    message="Chainlink and Binance were both above the start proxy at minute 5.",
                )
            )
            return "UP", decision_at, skip_reasons, reasons
        if chainlink_price < start_proxy and binance_price < start_proxy:
            reasons.append(
                Btc15mReasonBlock(
                    section="direction_lock",
                    status="pass",
                    message="Chainlink and Binance were both below the start proxy at minute 5.",
                )
            )
            return "DOWN", decision_at, skip_reasons, reasons

        skip_reasons.append("mixed_direction_at_minute_five")
        reasons.append(
            Btc15mReasonBlock(
                section="direction_lock",
                status="fail",
                message="Chainlink and Binance did not agree on direction at minute 5.",
            )
        )
        return "SKIP", decision_at, skip_reasons, reasons

    def _resolve_market_outcome(self, boundary_decision: Btc15mBoundaryDecisionRecord) -> str:
        start_proxy = _boundary_effective_start_proxy(boundary_decision)
        if start_proxy is None or boundary_decision.end_price_proxy_v1 is None:
            return "PENDING"
        start_price = _decimal(start_proxy)
        end_price = _decimal(boundary_decision.end_price_proxy_v1)
        if end_price > start_price:
            return "UP"
        if end_price < start_price:
            return "DOWN"
        return "UNRESOLVED_TIE"

    def _evaluate_window(
        self,
        record: Btc15mWindowRecord,
        *,
        source_kind: str = "manual",
        campaign_run_id: str | None = None,
    ) -> Btc15mPaperEvaluation:
        reasons = list(record.reason_blocks)
        if record.decision == "SKIP":
            return _skip_evaluation(
                record,
                reasons,
                source_kind=source_kind,
                campaign_run_id=campaign_run_id,
            )
        if record.decision not in {"UP", "DOWN"}:
            return _skip_evaluation(
                record,
                reasons
                + [
                    Btc15mReasonBlock(
                        section="direction_lock",
                        status="fail",
                        message="No valid direction lock was available for paper evaluation.",
                    )
                ],
                extra_skip_reason="missing_direction_lock",
                source_kind=source_kind,
                campaign_run_id=campaign_run_id,
            )

        target_token = _resolve_target_token(
            record.window.token_ids, record.window.outcomes, record.decision
        )
        if target_token is None:
            return _skip_evaluation(
                record,
                reasons
                + [
                    Btc15mReasonBlock(
                        section="outcome_mapping",
                        status="fail",
                        message="Could not map the chosen direction to a token and outcome.",
                    )
                ],
                extra_skip_reason="unresolved_outcome_mapping",
                source_kind=source_kind,
                campaign_run_id=campaign_run_id,
            )
        target_token_id, target_outcome = target_token

        window_start = _parse_iso_optional(record.window.window_start_at)
        if window_start is None:
            return _skip_evaluation(
                record,
                reasons
                + [
                    Btc15mReasonBlock(
                        section="window_timing",
                        status="fail",
                        message="Window start time was not available for paper evaluation.",
                    )
                ],
                extra_skip_reason="missing_window_start",
                source_kind=source_kind,
                campaign_run_id=campaign_run_id,
            )

        activation_at = window_start + timedelta(
            seconds=record.timing_controls.entry_window_start_offset_seconds
        )
        cancellation_at = window_start + timedelta(
            seconds=record.timing_controls.cancel_open_entries_offset_seconds
        )
        decision_sample = _select_decision_liquidity_sample(record.liquidity_samples, activation_at)
        if decision_sample is None:
            return _skip_evaluation(
                record,
                reasons
                + [
                    Btc15mReasonBlock(
                        section="decision_liquidity",
                        status="fail",
                        message=(
                            "No decision-time liquidity sample was available within five seconds."
                        ),
                    )
                ],
                extra_skip_reason="missing_decision_liquidity_sample",
                source_kind=source_kind,
                campaign_run_id=campaign_run_id,
            )

        guard_skip_reasons, guard_reasons, manipulation_flags = _evaluate_liquidity_guards(
            record=record,
            decision_sample=decision_sample,
            direction=record.decision,
        )
        if guard_skip_reasons:
            return _skip_evaluation(
                record,
                reasons + guard_reasons,
                extra_skip_reasons=guard_skip_reasons,
                source_kind=source_kind,
                campaign_run_id=campaign_run_id,
                decision_liquidity_sample=decision_sample,
                manipulation_flags=manipulation_flags,
            )
        samples = [
            sample
            for sample in record.market_samples
            if sample.token_id == target_token_id
            and _parse_iso_optional(sample.observed_at) is not None
        ]
        samples.sort(key=lambda item: item.observed_at)
        rung_results: list[Btc15mLadderRungResult] = []
        filled_quantities: list[Decimal] = []
        total_cost = Decimal("0")
        first_fill_at: str | None = None
        rung_notionals = _record_rung_notionals(record)
        for price, notional in zip(RUNG_PRICES, rung_notionals, strict=True):
            quantity = (notional / price).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            rung = Btc15mLadderRungResult(
                price=_decimal_text(price),
                notional_usdc=_decimal_text(notional),
                quantity=_decimal_text(quantity),
                status="cancelled",
                cancellation_at=_isoformat(cancellation_at),
            )
            for sample in samples:
                observed_at = _parse_iso_timestamp(sample.observed_at)
                if observed_at < activation_at or observed_at >= cancellation_at:
                    continue
                if _is_stale_sample(sample, observed_at, DEFAULT_MARKET_STALE_SECONDS):
                    continue
                best_ask = _decimal_optional(sample.best_ask)
                available = _ask_liquidity_at_or_better(sample.asks, price)
                if best_ask is None or best_ask > price or available < quantity:
                    continue
                rung.status = "filled"
                rung.fill_at = sample.observed_at
                rung.fill_price = _decimal_text(price)
                rung.cancellation_at = None
                filled_quantities.append(quantity)
                total_cost += quantity * price
                if first_fill_at is None:
                    first_fill_at = sample.observed_at
                break
            rung_results.append(rung)

        total_quantity = sum(filled_quantities, Decimal("0"))
        resolution = record.resolution_result
        if total_quantity == 0:
            settlement_value = Decimal("0")
            realized_pnl = Decimal("0")
        elif resolution == "UNRESOLVED_TIE":
            settlement_value = total_cost
            realized_pnl = Decimal("0")
        elif resolution == record.decision:
            settlement_value = total_quantity
            realized_pnl = settlement_value - total_cost
        elif resolution in {"UP", "DOWN"}:
            settlement_value = Decimal("0")
            realized_pnl = settlement_value - total_cost
        else:
            settlement_value = Decimal("0")
            realized_pnl = Decimal("0")

        mfe = Decimal("0")
        mae = Decimal("0")
        max_favorable_price: str | None = None
        time_to_peak_seconds: int | None = None
        path: list[Btc15mPriceMark] = []
        if first_fill_at is not None and total_quantity > 0:
            first_fill_dt = _parse_iso_timestamp(first_fill_at)
            peak_time: datetime | None = None
            for sample in samples:
                observed_at = _parse_iso_timestamp(sample.observed_at)
                if observed_at < first_fill_dt:
                    continue
                midpoint = _decimal_optional(sample.midpoint)
                if midpoint is None:
                    continue
                pnl = (total_quantity * midpoint) - total_cost
                path.append(
                    Btc15mPriceMark(
                        observed_at=sample.observed_at,
                        midpoint=_decimal_text(midpoint),
                        pnl_usdc=_decimal_text(pnl),
                    )
                )
                if len(path) == 1 or pnl > mfe:
                    mfe = pnl
                    max_favorable_price = _decimal_text(midpoint)
                    peak_time = observed_at
                if len(path) == 1 or pnl < mae:
                    mae = pnl
            if peak_time is not None:
                time_to_peak_seconds = int((peak_time - first_fill_dt).total_seconds())

        return Btc15mPaperEvaluation(
            window_id=record.window.window_id,
            market_slug=record.window.market_slug,
            condition_id=record.window.condition_id,
            window_start_at=record.window.window_start_at,
            window_end_at=record.window.window_end_at,
            source_kind=source_kind,
            campaign_run_id=campaign_run_id,
            target_token_id=target_token_id,
            target_outcome=target_outcome,
            decision=record.decision,
            decision_at=record.decision_at,
            resolution_result=resolution,
            decision_liquidity_sample=decision_sample,
            decision_spread=_decision_target_spread(decision_sample, target_token_id),
            realized_vol_1m_bps=decision_sample.binance.realized_vol_1m_bps,
            realized_vol_3m_bps=decision_sample.binance.realized_vol_3m_bps,
            visible_liquidity_030=_decision_visible_liquidity(
                decision_sample, target_token_id, "030"
            ),
            visible_liquidity_020=_decision_visible_liquidity(
                decision_sample, target_token_id, "020"
            ),
            visible_liquidity_010=_decision_visible_liquidity(
                decision_sample, target_token_id, "010"
            ),
            manipulation_flags=manipulation_flags,
            skip_reasons=list(record.skip_reasons),
            reason_blocks=reasons + guard_reasons,
            start_price_proxy_v1=record.start_price_proxy_v1,
            end_price_proxy_v1=record.end_price_proxy_v1,
            paper_start_proxy_v1=record.paper_start_proxy_v1,
            paper_start_proxy_source=record.paper_start_proxy_source,
            paper_budget_usdc=_record_paper_budget(record),
            rung_notionals_usdc=[_decimal_text(value) for value in rung_notionals],
            rungs=rung_results,
            filled_rung_count=sum(1 for rung in rung_results if rung.status == "filled"),
            cancelled_rung_count=sum(1 for rung in rung_results if rung.status == "cancelled"),
            first_fill_at=first_fill_at,
            total_cost_usdc=_decimal_text(total_cost),
            settlement_value_usdc=_decimal_text(settlement_value),
            realized_pnl_usdc=_decimal_text(realized_pnl),
            mfe_usdc=_decimal_text(mfe),
            mae_usdc=_decimal_text(mae),
            max_favorable_price=max_favorable_price,
            time_to_peak_seconds=time_to_peak_seconds,
            max_favorable_path=path,
        )

    def _iter_latest_windows(self) -> list[Btc15mWindowRecord]:
        latest: dict[str, Btc15mWindowRecord] = {}
        rank = {"partial": 0, "complete": 1}
        for record in self._state.list_windows():
            current = latest.get(record.window.window_id)
            if current is None:
                latest[record.window.window_id] = record
                continue
            current_rank = rank.get(current.status, 0)
            record_rank = rank.get(record.status, 0)
            if record_rank > current_rank:
                latest[record.window.window_id] = record
                continue
            if record_rank == current_rank and _sort_time(record.recorded_at) >= _sort_time(
                current.recorded_at
            ):
                latest[record.window.window_id] = record
        return sorted(
            latest.values(),
            key=lambda item: (_sort_time(item.window.window_start_at), item.window.window_id),
        )


def _boundary_observation(
    window: Btc15mWindowIdentity,
    *,
    boundary_kind: str,
    tick: Btc15mPriceTick | None,
    session_id: str,
    selection_status: str,
) -> Btc15mBoundaryObservationRecord:
    return Btc15mBoundaryObservationRecord(
        window_id=window.window_id,
        condition_id=window.condition_id,
        market_slug=window.market_slug,
        boundary_kind=boundary_kind,
        captured_at=tick.captured_at if tick is not None else _isoformat(_utc_now()),
        source_timestamp=tick.observed_at if tick is not None else None,
        source_value=tick.value if tick is not None else None,
        session_id=session_id,
        accepted=tick is not None,
        selected=tick is not None,
        selection_status=selection_status,
    )


def _skip_evaluation(
    record: Btc15mWindowRecord,
    reasons: list[Btc15mReasonBlock],
    *,
    extra_skip_reason: str | None = None,
    extra_skip_reasons: list[str] | None = None,
    source_kind: str = "manual",
    campaign_run_id: str | None = None,
    decision_liquidity_sample: Btc15mLiquiditySampleRecord | None = None,
    manipulation_flags: list[str] | None = None,
) -> Btc15mPaperEvaluation:
    skip_reasons = list(record.skip_reasons)
    target_token_id: str | None = None
    if decision_liquidity_sample is not None and record.decision in {"UP", "DOWN"}:
        target = _resolve_target_token(
            record.window.token_ids,
            record.window.outcomes,
            record.decision,
        )
        if target is not None:
            target_token_id = target[0]
    if extra_skip_reason is not None and extra_skip_reason not in skip_reasons:
        skip_reasons.append(extra_skip_reason)
    for item in extra_skip_reasons or []:
        if item not in skip_reasons:
            skip_reasons.append(item)
    return Btc15mPaperEvaluation(
        window_id=record.window.window_id,
        market_slug=record.window.market_slug,
        condition_id=record.window.condition_id,
        window_start_at=record.window.window_start_at,
        window_end_at=record.window.window_end_at,
        source_kind=source_kind,
        campaign_run_id=campaign_run_id,
        decision="SKIP",
        decision_at=record.decision_at,
        resolution_result=record.resolution_result,
        skip_reasons=skip_reasons,
        reason_blocks=reasons,
        decision_liquidity_sample=decision_liquidity_sample,
        decision_spread=(
            _decision_target_spread(decision_liquidity_sample, target_token_id)
            if target_token_id is not None
            else None
        ),
        realized_vol_1m_bps=(
            decision_liquidity_sample.binance.realized_vol_1m_bps
            if decision_liquidity_sample is not None
            else None
        ),
        realized_vol_3m_bps=(
            decision_liquidity_sample.binance.realized_vol_3m_bps
            if decision_liquidity_sample is not None
            else None
        ),
        visible_liquidity_030=(
            _decision_visible_liquidity(decision_liquidity_sample, target_token_id, "030")
            if target_token_id is not None
            else None
        ),
        visible_liquidity_020=(
            _decision_visible_liquidity(decision_liquidity_sample, target_token_id, "020")
            if target_token_id is not None
            else None
        ),
        visible_liquidity_010=(
            _decision_visible_liquidity(decision_liquidity_sample, target_token_id, "010")
            if target_token_id is not None
            else None
        ),
        manipulation_flags=list(manipulation_flags or []),
        start_price_proxy_v1=record.start_price_proxy_v1,
        end_price_proxy_v1=record.end_price_proxy_v1,
        paper_start_proxy_v1=record.paper_start_proxy_v1,
        paper_start_proxy_source=record.paper_start_proxy_source,
        total_cost_usdc="0",
        settlement_value_usdc="0",
        realized_pnl_usdc="0",
        mfe_usdc="0",
        mae_usdc="0",
    )


def _resolve_target_token(
    token_ids: list[str],
    outcomes: list[str],
    direction: str,
) -> tuple[str, str] | None:
    for token_id, outcome in zip(token_ids, outcomes, strict=False):
        normalized = outcome.strip().lower()
        if direction == "UP" and normalized in {"up", "yes"}:
            return token_id, outcome
        if direction == "DOWN" and normalized in {"down", "no"}:
            return token_id, outcome
    return None


def _token_outcome_map(token_ids: list[str], outcomes: list[str]) -> dict[str, str]:
    return {token_id: outcome for token_id, outcome in zip(token_ids, outcomes, strict=False)}


def _coerce_market_result(result: Any) -> BoundedRunResult:
    if isinstance(result, BoundedRunResult):
        return result
    if isinstance(result, MarketWatchStreamResponse):
        return BoundedRunResult(
            session=result.session,
            events=result.events,
            errors=result.errors,
        )
    raise TypeError("Unexpected market stream result.")


def _coerce_crypto_result(result: Any) -> CryptoStreamResponse:
    if isinstance(result, CryptoStreamResponse):
        return result
    raise TypeError("Unexpected crypto stream result.")


def _convert_stream_errors(errors: list[StreamSectionError]) -> list[Btc15mSectionError]:
    return [
        Btc15mSectionError(section=item.section, code=item.code, message=item.message)
        for item in errors
    ]


def _section_error(section: str, exc: Exception) -> Btc15mSectionError:
    code = "request_failed"
    if isinstance(exc, (Btc15mValidationError, StreamValidationError, MarketValidationError)):
        code = "invalid_argument"
    elif isinstance(exc, Btc15mStateError):
        code = "state_error"
    elif isinstance(exc, ClobNotFoundError):
        code = "not_found"
    return Btc15mSectionError(section=section, code=code, message=str(exc))


def _latest_tick_before(items: list[Btc15mPriceTick], when: datetime) -> Btc15mPriceTick | None:
    matching = [item for item in items if _parse_iso_timestamp(item.observed_at) <= when]
    if not matching:
        return None
    return max(matching, key=lambda item: item.observed_at)


def _latest_tick_before_or_at_within(
    items: list[Btc15mPriceTick],
    when: datetime,
    capture_window_seconds: int,
) -> Btc15mPriceTick | None:
    lower_bound = when - timedelta(seconds=capture_window_seconds)
    matching = [
        item
        for item in items
        if lower_bound <= _parse_iso_timestamp(item.observed_at) <= when
    ]
    if not matching:
        return None
    return max(matching, key=lambda item: item.observed_at)


def _first_tick_at_or_after_within(
    items: list[Btc15mPriceTick],
    when: datetime,
    grace_window_seconds: int,
) -> Btc15mPriceTick | None:
    upper_bound = when + timedelta(seconds=grace_window_seconds)
    matching = [
        item
        for item in items
        if when <= _parse_iso_timestamp(item.observed_at) <= upper_bound
    ]
    if not matching:
        return None
    return min(matching, key=lambda item: item.observed_at)


def _midpoint_text(left: str, right: str) -> str:
    midpoint = (_decimal(left) + _decimal(right)) / Decimal("2")
    return _decimal_text(midpoint)


def _event_timestamp_to_iso(timestamp: int | None, *, fallback: str) -> str:
    if timestamp is None:
        return fallback
    seconds = timestamp / 1000 if timestamp > 1_000_000_000_000 else timestamp
    return _isoformat(datetime.fromtimestamp(seconds, tz=UTC))


def _is_stale_tick(item: Btc15mPriceTick, when: datetime, limit_seconds: int) -> bool:
    return (when - _parse_iso_timestamp(item.observed_at)).total_seconds() > limit_seconds


def _is_stale_sample(item: Btc15mMarketSample, when: datetime, limit_seconds: int) -> bool:
    return (when - _parse_iso_timestamp(item.observed_at)).total_seconds() > limit_seconds


def _ask_liquidity_at_or_better(asks: list[NormalizedBookLevel], price: Decimal) -> Decimal:
    total = Decimal("0")
    for level in asks:
        try:
            level_price = _decimal(level.price)
            level_size = _decimal(level.size)
        except InvalidOperation:
            continue
        if level_price <= price:
            total += level_size
    return total


def _select_decision_liquidity_sample(
    items: list[Btc15mLiquiditySampleRecord],
    decision_time: datetime,
) -> Btc15mLiquiditySampleRecord | None:
    matching = []
    for item in items:
        observed_at = _parse_iso_timestamp(item.sampled_at)
        if observed_at > decision_time:
            continue
        if (decision_time - observed_at).total_seconds() > DEFAULT_MARKET_STALE_SECONDS:
            continue
        matching.append(item)
    if not matching:
        return None
    return max(matching, key=lambda item: item.sampled_at)


def _evaluate_liquidity_guards(
    *,
    record: Btc15mWindowRecord,
    decision_sample: Btc15mLiquiditySampleRecord,
    direction: str,
) -> tuple[list[str], list[Btc15mReasonBlock], list[str]]:
    skip_reasons: list[str] = []
    reasons: list[Btc15mReasonBlock] = []
    manipulation_flags: list[str] = []
    target = _resolve_target_token(record.window.token_ids, record.window.outcomes, direction)
    if target is None:
        return skip_reasons, reasons, manipulation_flags
    target_token_id, _ = target
    target_level = _polymarket_level(decision_sample, target_token_id)
    if target_level is None or target_level.spread is None:
        skip_reasons.append("wide_polymarket_spread")
        reasons.append(
            Btc15mReasonBlock(
                section="liquidity_guard",
                status="fail",
                message="Decision-time Polymarket spread was missing for the target token.",
            )
        )
        manipulation_flags.append("wide_polymarket_spread")
    else:
        spread = _decimal_optional(target_level.spread)
        if spread is None or spread > MAX_POLYMARKET_SPREAD:
            skip_reasons.append("wide_polymarket_spread")
            reasons.append(
                Btc15mReasonBlock(
                    section="liquidity_guard",
                    status="fail",
                    message="Decision-time Polymarket spread exceeded the 0.08 guard.",
                )
            )
            manipulation_flags.append("wide_polymarket_spread")

    visible_030 = _decimal_optional(
        _decision_visible_liquidity(decision_sample, target_token_id, "030")
    )
    if visible_030 is None or visible_030 < FIRST_RUNG_MIN_LIQUIDITY:
        skip_reasons.append("thin_visible_liquidity")
        reasons.append(
            Btc15mReasonBlock(
                section="liquidity_guard",
                status="fail",
                message="Visible target-token ask liquidity at or better than 0.30 was too thin.",
            )
        )
        manipulation_flags.append("thin_visible_liquidity")

    if record.decision_at is not None:
        decision_time = _parse_iso_timestamp(record.decision_at)
        chainlink_tick = _latest_tick_before(record.chainlink_ticks, decision_time)
        binance_tick = _latest_tick_before(record.binance_ticks, decision_time)
        if chainlink_tick is not None and binance_tick is not None:
            chainlink_price = _decimal_optional(chainlink_tick.value)
            binance_price = _decimal_optional(binance_tick.value)
            if chainlink_price is not None and binance_price is not None and chainlink_price > 0:
                divergence_bps = abs((binance_price - chainlink_price) / chainlink_price) * Decimal(
                    "10000"
                )
                if divergence_bps > MAX_BINANCE_CHAINLINK_DIVERGENCE_BPS:
                    skip_reasons.append("binance_chainlink_directional_disagreement")
                    reasons.append(
                        Btc15mReasonBlock(
                            section="underlying_guard",
                            status="fail",
                            message=(
                                "Binance and Chainlink diverged by more than 15 bps at minute 5."
                            ),
                        )
                    )
                    manipulation_flags.append("binance_chainlink_directional_disagreement")

    start_proxy = _decimal_optional(_record_effective_start_proxy(record))
    midpoint = _decimal_optional(target_level.midpoint if target_level is not None else None)
    if start_proxy is not None and midpoint is not None:
        latest_underlying = _latest_tick_before(
            record.chainlink_ticks, _parse_iso_timestamp(decision_sample.sampled_at)
        )
        if latest_underlying is not None:
            current_underlying = _decimal_optional(latest_underlying.value)
            if current_underlying is not None and start_proxy > 0:
                move_bps = abs((current_underlying - start_proxy) / start_proxy) * Decimal("10000")
                if (
                    midpoint > Decimal("0.70")
                    and move_bps < MAX_POLYMARKET_UNDERLYING_DIVERGENCE_BPS
                ):
                    skip_reasons.append("abnormal_polymarket_underlying_divergence")
                    reasons.append(
                        Btc15mReasonBlock(
                            section="underlying_guard",
                            status="fail",
                            message=(
                                "Polymarket price implied outsized conviction "
                                "relative to the BTC move."
                            ),
                        )
                    )
                    manipulation_flags.append("abnormal_polymarket_underlying_divergence")

    return skip_reasons, reasons, manipulation_flags


def _derive_manipulation_flags(items: list[Btc15mLiquiditySampleRecord]) -> list[str]:
    flags: set[str] = set()
    for item in items:
        for level in item.polymarket:
            spread = _decimal_optional(level.spread)
            if spread is not None and spread > MAX_POLYMARKET_SPREAD:
                flags.add("wide_polymarket_spread")
            visible = _decimal_optional(level.visible_liquidity_030)
            if visible is not None and visible < FIRST_RUNG_MIN_LIQUIDITY:
                flags.add("thin_visible_liquidity")
        if any(section.section == "book_ticker" for section in item.binance.errors):
            flags.add("stale_data")
    return sorted(flags)


def _decision_visible_liquidity(
    sample: Btc15mLiquiditySampleRecord | None,
    token_id: str,
    level: str,
) -> str | None:
    if sample is None:
        return None
    item = _polymarket_level(sample, token_id)
    if item is None:
        return None
    mapping = {
        "030": item.visible_liquidity_030,
        "020": item.visible_liquidity_020,
        "010": item.visible_liquidity_010,
    }
    return mapping.get(level)


def _decision_target_spread(
    sample: Btc15mLiquiditySampleRecord | None,
    token_id: str,
) -> str | None:
    if sample is None:
        return None
    item = _polymarket_level(sample, token_id)
    return item.spread if item is not None else None


def _polymarket_level(
    sample: Btc15mLiquiditySampleRecord,
    token_id: str,
) -> Btc15mPolymarketLiquidityLevel | None:
    for item in sample.polymarket:
        if item.token_id == token_id:
            return item
    return None


def _midpoint_optional_text(left: str | None, right: str | None) -> str | None:
    left_decimal = _decimal_optional(left)
    right_decimal = _decimal_optional(right)
    if left_decimal is None or right_decimal is None:
        return None
    return _decimal_text((left_decimal + right_decimal) / Decimal("2"))


def _spread_optional_text(left: str | None, right: str | None) -> str | None:
    left_decimal = _decimal_optional(left)
    right_decimal = _decimal_optional(right)
    if left_decimal is None or right_decimal is None:
        return None
    return _decimal_text(right_decimal - left_decimal)


def _average_decimal_text(items: list[Decimal | None]) -> str | None:
    values = [item for item in items if item is not None]
    if not values:
        return None
    return _decimal_text(sum(values, Decimal("0")) / Decimal(len(values)))


def _build_liquidity_schedule(
    *,
    started_at: datetime,
    seconds: int,
    baseline_seconds: int,
    mandatory_points: list[tuple[str, datetime]],
) -> list[tuple[str, datetime]]:
    ended_at = started_at + timedelta(seconds=seconds)
    items: list[tuple[str, datetime]] = []
    baseline_cursor = started_at
    while baseline_cursor < ended_at:
        items.append(("baseline", baseline_cursor))
        baseline_cursor += timedelta(seconds=baseline_seconds)
    for sample_kind, scheduled_at in mandatory_points:
        effective = scheduled_at if scheduled_at >= started_at else started_at
        if effective <= ended_at:
            items.append((sample_kind, effective))
    items.sort(key=lambda item: (item[1], item[0]))
    return items


def _parse_btc15m_slug_start(slug: str) -> datetime | None:
    match = BTC15M_CANONICAL_SLUG_RE.fullmatch(slug.strip().lower())
    if match is None:
        return None
    return datetime.fromtimestamp(int(match.group(1)), tz=UTC)


def _canonical_btc15m_slug(start_dt: datetime) -> str:
    return f"btc-updown-15m-{int(start_dt.astimezone(UTC).timestamp())}"


def _floor_btc15m_window_start(value: datetime) -> datetime:
    normalized = value.astimezone(UTC).replace(second=0, microsecond=0)
    floored_minute = normalized.minute - (normalized.minute % 15)
    return normalized.replace(minute=floored_minute)


def _recurring_candidate_from_market(market: NormalizedMarket) -> RecurringMarketCandidate:
    return RecurringMarketCandidate(
        rank=1,
        match_score=0,
        matched_interval=validate_recurring_interval(DEFAULT_RECORD_INTERVAL),
        recency_source=None,
        market_slug=market.market_slug,
        event_slug=market.event_slug,
        question=market.question,
        event_title=market.event_title,
        active=market.active,
        closed=market.closed,
        enable_order_book=market.enable_order_book,
        condition_id=market.condition_id,
        token_ids=list(market.token_ids),
        outcomes=list(market.outcomes),
        min_tick=market.min_tick,
        min_order_size=market.min_order_size,
    )


def _last_price_tick(items: list[Btc15mPriceTick]) -> Btc15mPriceTick | None:
    if not items:
        return None
    return max(items, key=lambda item: item.observed_at)


def _direction_from_prices(
    *,
    start_proxy: str,
    chainlink_value: str | None,
    binance_value: str | None,
) -> str:
    start_decimal = _decimal_optional(start_proxy)
    chainlink_decimal = _decimal_optional(chainlink_value)
    binance_decimal = _decimal_optional(binance_value)
    if start_decimal is None or chainlink_decimal is None or binance_decimal is None:
        return "pending"
    if chainlink_decimal > start_decimal and binance_decimal > start_decimal:
        return "UP"
    if chainlink_decimal < start_decimal and binance_decimal < start_decimal:
        return "DOWN"
    return "SKIP"


def _select_dashboard_level(
    sample: Btc15mLiquiditySampleRecord | None,
    *,
    target_token_id: str | None,
) -> Btc15mPolymarketLiquidityLevel | None:
    if sample is None:
        return None
    if target_token_id is not None:
        target = _polymarket_level(sample, target_token_id)
        if target is not None:
            return target
    return sample.polymarket[0] if sample.polymarket else None


def _dashboard_rung_states(
    *,
    evaluation: Btc15mPaperEvaluation | None,
    sampled_at: datetime,
    resolved: _ResolvedWindow,
    selected_level: Btc15mPolymarketLiquidityLevel | None,
    direction_status: str,
) -> list[Btc15mDashboardRungState]:
    if evaluation is not None and evaluation.rungs:
        visible_mapping = {
            "0.30": selected_level.visible_liquidity_030 if selected_level is not None else None,
            "0.20": selected_level.visible_liquidity_020 if selected_level is not None else None,
            "0.10": selected_level.visible_liquidity_010 if selected_level is not None else None,
        }
        return [
            Btc15mDashboardRungState(
                price=rung.price,
                state=rung.status,
                visible_liquidity=visible_mapping.get(rung.price),
                fill_at=rung.fill_at,
                fill_price=rung.fill_price,
            )
            for rung in evaluation.rungs
        ]

    entry_end_at = None
    if resolved.window_start_dt is not None:
        entry_end_at = resolved.window_start_dt + MINUTE_TEN_OFFSET
    if direction_status in {"UP", "DOWN"}:
        default_state = "armed"
        if entry_end_at is not None and sampled_at >= entry_end_at:
            default_state = "cancelled"
    else:
        default_state = "pending"
    visible_mapping = {
        "0.30": selected_level.visible_liquidity_030 if selected_level is not None else None,
        "0.20": selected_level.visible_liquidity_020 if selected_level is not None else None,
        "0.10": selected_level.visible_liquidity_010 if selected_level is not None else None,
    }
    return [
        Btc15mDashboardRungState(
            price=price,
            state=default_state,
            visible_liquidity=visible_mapping.get(price),
        )
        for price in ("0.30", "0.20", "0.10")
    ]


def _normalize_optional_slug(slug: str | None) -> str | None:
    if slug is None:
        return None
    normalized = slug.strip()
    return normalized or None


def _normalize_terminal_mode(mode: str | Btc15mRunMode) -> Btc15mRunMode:
    normalized = str(mode).strip().lower()
    if normalized == Btc15mRunMode.PAPER.value:
        return Btc15mRunMode.PAPER
    if normalized == Btc15mRunMode.LIVE.value:
        return Btc15mRunMode.LIVE
    raise Btc15mValidationError("BTC15m mode must be one of: paper, live.")


def _require_paper_mode(mode: str | Btc15mRunMode) -> Btc15mRunMode:
    normalized = str(mode).strip().lower()
    if normalized == Btc15mRunMode.PAPER.value:
        return Btc15mRunMode.PAPER
    if normalized == Btc15mRunMode.LIVE.value:
        raise Btc15mOperatorHintError(
            "BTC15m live mode is reserved and not implemented in this paper-first step.",
            identifier="mode",
            hint={"next_steps": ["Use --mode paper for live-data paper testing."]},
        )
    raise Btc15mValidationError("BTC15m mode must be one of: paper, live.")


def _default_timing_controls() -> Btc15mTimingControls:
    return Btc15mTimingControls(
        pre_start_capture_window_seconds=DEFAULT_PRE_START_CAPTURE_WINDOW_SECONDS,
        post_start_grace_window_seconds=DEFAULT_POST_START_GRACE_WINDOW_SECONDS,
        pre_end_capture_window_seconds=DEFAULT_PRE_END_CAPTURE_WINDOW_SECONDS,
        post_end_grace_window_seconds=DEFAULT_POST_END_GRACE_WINDOW_SECONDS,
        direction_lock_offset_seconds=int(MINUTE_FIVE_OFFSET.total_seconds()),
        entry_window_start_offset_seconds=int(MINUTE_FIVE_OFFSET.total_seconds()),
        entry_window_end_offset_seconds=int(MINUTE_TEN_OFFSET.total_seconds()),
        cancel_open_entries_offset_seconds=int(MINUTE_TEN_OFFSET.total_seconds()),
    )


def _append_tick_if_new(items: list[Btc15mPriceTick], tick: Btc15mPriceTick) -> None:
    if any(
        item.source == tick.source
        and item.observed_at == tick.observed_at
        and item.value == tick.value
        for item in items
    ):
        return
    items.append(tick)
    items.sort(key=lambda item: item.observed_at)


def _market_samples_from_liquidity(
    sample: Btc15mLiquiditySampleRecord,
) -> list[Btc15mMarketSample]:
    items: list[Btc15mMarketSample] = []
    for level in sample.polymarket:
        items.append(
            Btc15mMarketSample(
                token_id=level.token_id,
                outcome=level.outcome,
                event_type=f"{sample.sample_kind}_liquidity",
                source="terminal_liquidity",
                captured_at=sample.sampled_at,
                observed_at=sample.sampled_at,
                best_bid=level.best_bid,
                best_ask=level.best_ask,
                midpoint=level.midpoint,
                spread=level.spread,
                bids=list(level.bids),
                asks=list(level.asks),
            )
        )
    return items


def _terminal_position_summary(
    rungs: list[_TerminalRungRuntime],
) -> tuple[Decimal, Decimal, str | None]:
    total_quantity = Decimal("0")
    total_cost = Decimal("0")
    for rung in rungs:
        if rung.state != "filled":
            continue
        fill_price = _decimal(rung.fill_price) if rung.fill_price is not None else rung.price
        total_quantity += rung.quantity
        total_cost += rung.quantity * fill_price
    if total_quantity <= 0:
        return Decimal("0"), Decimal("0"), None
    avg_entry = total_cost / total_quantity
    return total_quantity, total_cost, _decimal_text(avg_entry)


def _terminal_countdown_seconds(runtime: _TerminalRuntime, now: datetime) -> int | None:
    resolved = runtime.resolved
    if resolved.window_start_dt is None or resolved.window_end_dt is None:
        return None
    if (
        runtime.state is Btc15mTerminalState.WAITING_FOR_NEXT_WINDOW
        and runtime.wait_next_target_start_dt is not None
    ):
        return max(0, int((runtime.wait_next_target_start_dt - now).total_seconds()))
    if runtime.state is Btc15mTerminalState.PRE_START_CAPTURE:
        return max(0, int((resolved.window_start_dt - now).total_seconds()))
    if runtime.state is Btc15mTerminalState.OBSERVE_ONLY:
        return max(0, int((resolved.window_end_dt - now).total_seconds()))
    if runtime.state in {
        Btc15mTerminalState.BOUNDARY_PENDING,
        Btc15mTerminalState.DIRECTION_LOCK_PENDING,
    }:
        return max(0, int(((resolved.window_start_dt + MINUTE_FIVE_OFFSET) - now).total_seconds()))
    return max(0, int((resolved.window_end_dt - now).total_seconds()))


def _terminal_rung_visible_liquidity(
    level: Btc15mPolymarketLiquidityLevel | None,
    price: Decimal,
) -> str | None:
    if level is None:
        return None
    return _decimal_text(_ask_liquidity_at_or_better(level.asks, price))


def _polymarket_level_by_outcome(
    sample: Btc15mLiquiditySampleRecord,
    outcome: str,
) -> Btc15mPolymarketLiquidityLevel | None:
    target = outcome.strip().lower()
    for level in sample.polymarket:
        if (level.outcome or "").strip().lower() == target:
            return level
    return None


def _dashboard_side_state(
    level: Btc15mPolymarketLiquidityLevel | None,
    *,
    last_trade_price: str | None = None,
) -> Btc15mDashboardSideState | None:
    if level is None:
        return None
    return Btc15mDashboardSideState(
        token_id=level.token_id,
        outcome=level.outcome,
        best_bid=level.best_bid,
        best_ask=level.best_ask,
        midpoint=level.midpoint,
        spread=level.spread,
        last_trade_price=last_trade_price,
        visible_liquidity_030=level.visible_liquidity_030,
        visible_liquidity_020=level.visible_liquidity_020,
        visible_liquidity_010=level.visible_liquidity_010,
    )


def _snapshot_display_truth(
    snapshot: Btc15mDashboardSnapshotRecord | None,
) -> Btc15mTerminalDisplayTruth | None:
    if snapshot is None:
        return None
    if snapshot.page_mirror is not None:
        return snapshot.page_mirror
    if snapshot.display is not None:
        return snapshot.display
    return Btc15mTerminalDisplayTruth(
        display_price_to_beat=snapshot.price_to_beat,
        display_current_btc=snapshot.current_live_btc_price,
        display_up_price=snapshot.up_price,
        display_down_price=snapshot.down_price,
        display_countdown=_format_terminal_countdown(snapshot.countdown_seconds),
        display_volume=snapshot.display_volume,
        display_source=snapshot.page_parity_source,
        display_window_label=snapshot.current_window_label,
        display_url=snapshot.page_parity_url,
        display_observed_at=None,
        display_stale=False,
        display_notes=[],
    )


def _snapshot_page_mirror(
    snapshot: Btc15mDashboardSnapshotRecord | None,
) -> Btc15mTerminalPageMirror | None:
    display = _snapshot_display_truth(snapshot)
    if display is None:
        return None
    if isinstance(display, Btc15mTerminalPageMirror):
        return display
    return Btc15mTerminalPageMirror(**display.model_dump(mode="json"))


def _snapshot_market_truth(
    snapshot: Btc15mDashboardSnapshotRecord | None,
) -> Btc15mTerminalMarketTruth | None:
    if snapshot is None:
        return None
    if snapshot.market_truth is not None:
        return snapshot.market_truth
    return Btc15mTerminalMarketTruth(
        market_slug=snapshot.market_slug,
        window_start_at=snapshot.window_start_at,
        window_end_at=snapshot.window_end_at,
        countdown_seconds=snapshot.countdown_seconds,
        countdown=_format_terminal_countdown(snapshot.countdown_seconds),
        boundary_status=snapshot.boundary_status,
        direction_lock_status=snapshot.direction_lock_status,
        selected_side=snapshot.selected_side,
        target_token_id=snapshot.target_token_id,
        target_outcome=snapshot.target_outcome,
        current_chainlink_price=snapshot.current_chainlink_price,
        start_price_proxy_v1=snapshot.start_price_proxy_v1,
        end_price_proxy_v1=getattr(snapshot, "end_price_proxy_v1", None),
        paper_budget_usdc=snapshot.paper_budget_usdc,
        rung_notionals_usdc=list(snapshot.rung_notionals_usdc),
        avg_entry_price=snapshot.avg_entry_price,
        exposure_quantity=snapshot.exposure_quantity,
        exposure_notional_usdc=snapshot.exposure_notional_usdc,
        current_midpoint=snapshot.current_midpoint,
        current_spread=snapshot.current_spread,
        market_open_interest=snapshot.market_open_interest,
        market_volume=snapshot.market_volume,
        visible_liquidity_030=snapshot.visible_liquidity_030,
        visible_liquidity_020=snapshot.visible_liquidity_020,
        visible_liquidity_010=snapshot.visible_liquidity_010,
        derived_up_price=getattr(snapshot, "derived_up_price", None),
        derived_up_price_source=getattr(snapshot, "derived_up_price_source", None),
        derived_down_price=getattr(snapshot, "derived_down_price", None),
        derived_down_price_source=getattr(snapshot, "derived_down_price_source", None),
        up_side=snapshot.up_side,
        down_side=snapshot.down_side,
        rungs=list(snapshot.rungs),
        manipulation_flags=list(snapshot.manipulation_flags),
    )


def _snapshot_terminal_presenter(
    snapshot: Btc15mDashboardSnapshotRecord | None,
) -> Btc15mTerminalPresenter | None:
    if snapshot is None:
        return None
    if snapshot.terminal_presenter is not None:
        return snapshot.terminal_presenter
    page_mirror = _snapshot_page_mirror(snapshot)
    market_truth = _snapshot_market_truth(snapshot)
    if page_mirror is None or market_truth is None:
        return None
    page_state = "unavailable"
    if page_mirror.display_stale and page_mirror.display_source == "page_unavailable":
        page_state = "stale"
    elif page_mirror.display_source == "page_exact":
        page_state = "exact"
    show_binance = page_state != "exact" or any(
        "binance" in flag or "divergence" in flag for flag in market_truth.manipulation_flags
    )
    return Btc15mTerminalPresenter(
        primary_block_state=page_state,
        show_binance_diagnostics=show_binance,
    )


def _page_exact_field_value(
    page_data: Btc15mPageParityData | None,
    field_name: str,
) -> str | None:
    if page_data is None:
        return None
    if page_data.field_sources.get(field_name) != "page_exact":
        return None
    value = getattr(page_data, field_name, None)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _terminal_display_has_full_exact_fields(field_sources: dict[str, str]) -> bool:
    required = (
        "price_to_beat",
        "current_live_btc_price",
        "up_price",
        "down_price",
        "volume",
    )
    return all(field_sources.get(field_name) == "page_exact" for field_name in required)


def _effective_terminal_start_proxy(runtime: _TerminalRuntime) -> str | None:
    return runtime.start_price_proxy_v1


def _boundary_effective_start_proxy(
    boundary_decision: Btc15mBoundaryDecisionRecord,
) -> str | None:
    return boundary_decision.start_price_proxy_v1


def _record_effective_start_proxy(record: Btc15mWindowRecord) -> str | None:
    return record.start_price_proxy_v1


def _format_terminal_countdown(countdown_seconds: int | None) -> str | None:
    if countdown_seconds is None:
        return None
    if countdown_seconds < 0:
        countdown_seconds = 0
    hours, remainder = divmod(countdown_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _market_page_url(market: NormalizedMarket | None) -> str | None:
    if market is None:
        return None
    return f"https://polymarket.com/market/{market.market_slug}"


def _extract_display_price_to_beat_from_market(market: NormalizedMarket) -> str | None:
    for text in (market.question, market.event_title or "", market.event_slug or ""):
        parsed = _extract_display_price_to_beat_from_text(text)
        if parsed is not None:
            return parsed
    return None


def _extract_display_price_to_beat_from_text(text: str) -> str | None:
    patterns = (
        re.compile(r"price\s+to\s+beat[^0-9$]*\$?(?P<value>[0-9][0-9,\.]*)", re.I),
        re.compile(r"\b(?:above|below)\b[^0-9$]{0,12}\$?(?P<value>[0-9][0-9,\.]*)", re.I),
        re.compile(r"\$?(?P<value>[0-9][0-9,\.]*)[^a-z0-9]{0,8}(?:or higher|or lower)", re.I),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match is None:
            continue
        return match.group("value").replace(",", "")
    return None


def _latest_market_sample_last_trade_price(
    market_samples: list[Btc15mMarketSample],
    token_id: str | None,
) -> str | None:
    if token_id is None:
        return None
    for item in reversed(market_samples):
        if item.token_id != token_id:
            continue
        if item.event_type == "last_trade_price" and item.last_trade_price is not None:
            return item.last_trade_price
    return None


def _display_price_emulation_source(
    level: Btc15mPolymarketLiquidityLevel | None,
) -> Decimal | None:
    if level is None:
        return None
    spread = _decimal_optional(level.spread)
    if spread is not None:
        return spread
    bid = _decimal_optional(level.best_bid)
    ask = _decimal_optional(level.best_ask)
    if bid is None or ask is None:
        return None
    return ask - bid


def _derive_market_context_price(
    level: Btc15mPolymarketLiquidityLevel | None,
    *,
    market_samples: list[Btc15mMarketSample],
) -> tuple[str | None, str | None]:
    if level is None:
        return None, None
    spread = _display_price_emulation_source(level)
    if spread is not None and spread <= Decimal("0.10"):
        midpoint = _coalesce_price(
            level.midpoint,
            _midpoint_optional_text(level.best_bid, level.best_ask),
        )
        if midpoint is not None:
            return midpoint, "midpoint"
        return None, None
    if spread is not None and spread > Decimal("0.10"):
        last_trade_price = _latest_market_sample_last_trade_price(market_samples, level.token_id)
        if last_trade_price is not None:
            return last_trade_price, "last_trade"
        return None, None
    return None, None


def _emulate_terminal_display_price(
    level: Btc15mPolymarketLiquidityLevel | None,
    *,
    market_samples: list[Btc15mMarketSample],
    side_name: str,
    notes: list[str],
) -> tuple[str | None, str]:
    if level is None:
        notes.append(f"{side_name}_display_level_unavailable")
        return None, "page_unavailable"
    spread = _display_price_emulation_source(level)
    if spread is not None and spread <= Decimal("0.10"):
        midpoint = _coalesce_price(
            level.midpoint,
            _midpoint_optional_text(level.best_bid, level.best_ask),
        )
        if midpoint is not None:
            notes.append(f"{side_name}_display_midpoint_emulated")
            return midpoint, "clob_midpoint"
    if spread is not None and spread > Decimal("0.10"):
        last_trade_price = _latest_market_sample_last_trade_price(market_samples, level.token_id)
        if last_trade_price is not None:
            notes.append(f"{side_name}_display_last_trade_emulated")
            return last_trade_price, "clob_last_trade"
        notes.append(f"{side_name}_display_last_trade_unavailable")
        return None, "page_unavailable"
    notes.append(f"{side_name}_display_spread_unavailable")
    return None, "page_unavailable"


def _page_field_source(page_data: Btc15mPageParityData, field_name: str) -> str:
    source = page_data.field_sources.get(field_name)
    if source in {"page_exact", "page_estimated"}:
        return source
    return "page_unavailable"


def _display_source_from_field_sources(field_sources: dict[str, str]) -> str:
    critical_fields = (
        "price_to_beat",
        "current_live_btc_price",
        "up_price",
        "down_price",
    )
    exact_flags = [
        field_sources.get(field_name) == "page_exact" for field_name in critical_fields
    ]
    if all(exact_flags):
        return "page_exact"
    normalized = {value for value in field_sources.values() if value is not None}
    if "clob_midpoint" in normalized or "clob_last_trade" in normalized:
        return "clob_emulated"
    if "page_estimated" in normalized:
        return "page_estimated"
    return "page_unavailable"


def _resolve_terminal_paper_sizing(
    *,
    budget_usdc: str | None,
    rungs: str | None,
) -> tuple[Decimal, tuple[Decimal, Decimal, Decimal]]:
    if rungs is not None and not rungs.strip():
        rungs = None
    if budget_usdc is not None and not budget_usdc.strip():
        budget_usdc = None
    if rungs is None and budget_usdc is None:
        return DEFAULT_TERMINAL_BUDGET_USDC, RUNG_NOTIONALS

    try:
        explicit_budget = _decimal(budget_usdc) if budget_usdc is not None else None
    except InvalidOperation as exc:
        raise Btc15mValidationError(
            "BTC15m terminal --budget-usdc must be a decimal number."
        ) from exc
    if explicit_budget is not None and explicit_budget <= 0:
        raise Btc15mValidationError("BTC15m terminal budget must be greater than zero.")

    if rungs is None:
        assert explicit_budget is not None
        total_default = sum(RUNG_NOTIONALS, Decimal("0"))
        scaled = tuple(
            (explicit_budget * notional / total_default).quantize(Decimal("0.000001"))
            for notional in RUNG_NOTIONALS
        )
        diff = explicit_budget - sum(scaled, Decimal("0"))
        scaled_list = list(scaled)
        scaled_list[-1] += diff
        return explicit_budget, (scaled_list[0], scaled_list[1], scaled_list[2])

    try:
        parsed_rungs = tuple(_decimal(part.strip()) for part in rungs.split(","))
    except InvalidOperation as exc:
        raise Btc15mValidationError(
            "BTC15m terminal --rungs must be comma-separated decimal values."
        ) from exc
    if len(parsed_rungs) != 3:
        raise Btc15mValidationError("BTC15m terminal --rungs requires exactly three values.")
    if any(value <= 0 for value in parsed_rungs):
        raise Btc15mValidationError("BTC15m terminal rung notionals must be positive.")
    rung_total = sum(parsed_rungs, Decimal("0"))
    if explicit_budget is not None and rung_total != explicit_budget:
        raise Btc15mValidationError(
            "BTC15m terminal --rungs must sum exactly to --budget-usdc when both are set."
        )
    resolved_budget = explicit_budget if explicit_budget is not None else rung_total
    return resolved_budget, (parsed_rungs[0], parsed_rungs[1], parsed_rungs[2])


def _btc15m_canary_live_profile() -> Btc15mCanaryLiveProfile:
    default_budget = DEFAULT_TERMINAL_BUDGET_USDC
    default_rungs = [_decimal_text(item) for item in RUNG_NOTIONALS]
    default_fits = default_budget <= BTC15M_CANARY_MAX_LIVE_USDC and all(
        item <= BTC15M_CANARY_MAX_RUNG_USDC for item in RUNG_NOTIONALS
    )
    return Btc15mCanaryLiveProfile(
        max_live_usdc=_decimal_text(BTC15M_CANARY_MAX_LIVE_USDC),
        max_rung_usdc=_decimal_text(BTC15M_CANARY_MAX_RUNG_USDC),
        one_window_only=True,
        default_budget_usdc=_decimal_text(default_budget),
        default_rung_notionals_usdc=default_rungs,
        default_sizing_fits=default_fits,
    )


def _record_rung_notionals(record: Btc15mWindowRecord) -> tuple[Decimal, Decimal, Decimal]:
    if len(record.rung_notionals_usdc) == 3:
        values = tuple(_decimal(value) for value in record.rung_notionals_usdc)
        return values[0], values[1], values[2]
    return RUNG_NOTIONALS


def _record_paper_budget(record: Btc15mWindowRecord) -> str:
    if record.paper_budget_usdc is not None:
        return record.paper_budget_usdc
    return _decimal_text(sum(_record_rung_notionals(record), Decimal("0")))


def _binance_near_touch_imbalance(snapshot: Any | None) -> str | None:
    if snapshot is None:
        return None
    bid_depth = _decimal_optional(getattr(snapshot, "near_touch_bid_depth", None))
    ask_depth = _decimal_optional(getattr(snapshot, "near_touch_ask_depth", None))
    if bid_depth is None or ask_depth is None:
        return None
    denominator = bid_depth + ask_depth
    if denominator <= 0:
        return None
    imbalance = (bid_depth - ask_depth) / denominator
    return _decimal_text(imbalance)


def _binance_volume_proxy(
    sample: Btc15mLiquiditySampleRecord | None,
    *,
    minutes: int,
) -> str | None:
    if sample is None:
        return None
    total = Decimal("0")
    count = 0
    for kline in reversed(sample.binance.klines):
        if not kline.is_closed:
            continue
        volume = _decimal_optional(kline.volume)
        if volume is None:
            continue
        total += volume
        count += 1
        if count >= minutes:
            break
    return _decimal_text(total) if count else None


def _extract_live_order_id(live_response: dict[str, Any] | None) -> str | None:
    if not isinstance(live_response, dict):
        return None
    order_payload = live_response.get("order")
    if isinstance(order_payload, dict):
        order_id = order_payload.get("order_id") or order_payload.get("id")
        if isinstance(order_id, str) and order_id.strip():
            return order_id.strip()
    post_payload = live_response.get("post_result")
    if isinstance(post_payload, dict):
        order_id = (
            post_payload.get("orderID")
            or post_payload.get("orderId")
            or post_payload.get("id")
        )
        if isinstance(order_id, str) and order_id.strip():
            return order_id.strip()
    return None


def _order_status_is_cancelled(status: str | None) -> bool:
    normalized = (status or "").lower()
    return "cancel" in normalized


def _order_status_is_filled(status: str | None, remaining_size: str | None) -> bool:
    normalized = (status or "").lower()
    if any(marker in normalized for marker in ("filled", "matched", "executed")):
        return True
    remaining = _decimal_optional(remaining_size)
    return remaining is not None and remaining <= 0


def _terminal_boundary_observations(
    runtime: _TerminalRuntime,
) -> list[Btc15mBoundaryObservationRecord]:
    window = runtime.resolved.window
    return [
        _boundary_observation(
            window,
            boundary_kind="start",
            tick=runtime.boundary_pre_start,
            session_id=runtime.session_id,
            selection_status="selected_pre_start"
            if runtime.boundary_pre_start is not None
            else "missing_pre_start_capture_window",
        ),
        _boundary_observation(
            window,
            boundary_kind="start",
            tick=runtime.boundary_post_start,
            session_id=runtime.session_id,
            selection_status="selected_post_start"
            if runtime.boundary_post_start is not None
            else "missing_post_start_grace_expired",
        ),
        _boundary_observation(
            window,
            boundary_kind="end",
            tick=runtime.boundary_pre_end,
            session_id=runtime.session_id,
            selection_status="selected_pre_end"
            if runtime.boundary_pre_end is not None
            else "missing_pre_end_capture_window",
        ),
        _boundary_observation(
            window,
            boundary_kind="end",
            tick=runtime.boundary_post_end,
            session_id=runtime.session_id,
            selection_status="selected_post_end"
            if runtime.boundary_post_end is not None
            else "missing_post_end_grace_expired",
        ),
    ]


def _gamma_candidate_recency(candidate: GammaSearchCandidate) -> tuple[str | None, datetime | None]:
    for field_name, value in (
        ("endDate", candidate.end_date),
        ("resolutionDate", candidate.resolution_date),
        ("startDate", candidate.start_date),
    ):
        parsed = _parse_iso_optional(value)
        if parsed is not None:
            return field_name, parsed
    return None, None


def _btc15m_interval_match_strength(candidate: NormalizedMarket) -> int:
    haystack = _btc15m_search_haystack(candidate)
    if DEFAULT_RECORD_INTERVAL in haystack:
        return 2
    for alias in BTC15M_INTERVAL_ALIASES:
        if alias in haystack:
            return 1
    return 0


def _btc15m_btc_identity_score(candidate: NormalizedMarket) -> int:
    haystack = _btc15m_search_haystack(candidate)
    return sum(1 for marker in BTC15M_BTC_MARKERS if marker in haystack)


def _btc15m_direction_score(candidate: NormalizedMarket) -> int:
    haystack = _btc15m_search_haystack(candidate)
    if "up/down" in haystack or "up or down" in haystack:
        return 3
    return sum(1 for marker in BTC15M_DIRECTION_MARKERS if marker in haystack)


def _btc15m_search_haystack(candidate: NormalizedMarket) -> str:
    return " ".join(
        [
            candidate.question,
            candidate.event_title or "",
            candidate.market_slug,
            candidate.event_slug or "",
        ]
    ).lower()


def _window_label(window: Btc15mWindowIdentity) -> str | None:
    start_dt = _parse_iso_optional(window.window_start_at)
    end_dt = _parse_iso_optional(window.window_end_at)
    if start_dt is None or end_dt is None:
        return None
    return f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')} UTC"


def _coalesce_price(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _decimal(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_optional(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return _decimal(value)
    except InvalidOperation:
        return None


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _parse_iso_optional(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _parse_iso_timestamp(value)


def _parse_iso_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized).astimezone(UTC)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sort_time(value: str | None) -> str:
    return value or ""


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)
