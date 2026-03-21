"""Models for the BTC 15-minute Chainlink directional ladder research surface."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from pm.binance.models import BinanceLiquiditySnapshot
from pm.market.models import NormalizedBookLevel


class Btc15mSectionError(BaseModel):
    """Partial recorder, replay, or paper-evaluation failure detail."""

    section: str
    code: str
    message: str


class Btc15mReasonBlock(BaseModel):
    """Deterministic decision or skip explanation."""

    section: str
    status: str
    message: str


class Btc15mRunMode(StrEnum):
    """Supported BTC15m run modes."""

    PAPER = "paper"
    LIVE = "live"


class Btc15mTerminalState(StrEnum):
    """Explicit operator-terminal session states."""

    WAITING_FOR_NEXT_WINDOW = "WAITING_FOR_NEXT_WINDOW"
    PRE_START_CAPTURE = "PRE_START_CAPTURE"
    BOUNDARY_PENDING = "BOUNDARY_PENDING"
    DIRECTION_LOCK_PENDING = "DIRECTION_LOCK_PENDING"
    ENTRY_WINDOW_OPEN = "ENTRY_WINDOW_OPEN"
    HOLD_TO_EXPIRY = "HOLD_TO_EXPIRY"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    RESOLVED = "RESOLVED"
    SKIPPED = "SKIPPED"


class Btc15mTimingControls(BaseModel):
    """Explicit per-window timing controls for BTC15m evaluation."""

    pre_start_capture_window_seconds: int = 60
    post_start_grace_window_seconds: int = 60
    pre_end_capture_window_seconds: int = 60
    post_end_grace_window_seconds: int = 60
    direction_lock_offset_seconds: int = 300
    entry_window_start_offset_seconds: int = 300
    entry_window_end_offset_seconds: int = 600
    cancel_open_entries_offset_seconds: int = 600


class Btc15mWindowIdentity(BaseModel):
    """Normalized BTC15m recurring-market identity."""

    strategy_name: str
    window_id: str
    condition_id: str | None = None
    market_slug: str
    token_ids: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    slug_start_unix: int | None = None
    timing_source: str = "fallback"
    timing_notes: list[str] = Field(default_factory=list)
    window_start_at: str | None = None
    window_end_at: str | None = None
    market_open_time: str | None = None


class Btc15mPriceTick(BaseModel):
    """One normalized price-tick sample kept in BTC15m research state."""

    source: str
    captured_at: str
    observed_at: str
    value: str


class Btc15mMarketSample(BaseModel):
    """One normalized market-microstructure sample."""

    token_id: str
    outcome: str | None = None
    event_type: str
    source: str
    captured_at: str
    observed_at: str
    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    last_trade_price: str | None = None
    bids: list[NormalizedBookLevel] = Field(default_factory=list)
    asks: list[NormalizedBookLevel] = Field(default_factory=list)


class Btc15mPolymarketLiquidityLevel(BaseModel):
    """One compact Polymarket token liquidity summary for a sample instant."""

    token_id: str
    outcome: str | None = None
    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    bid_level_count: int = 0
    ask_level_count: int = 0
    bids: list[NormalizedBookLevel] = Field(default_factory=list)
    asks: list[NormalizedBookLevel] = Field(default_factory=list)
    visible_liquidity_030: str = "0"
    visible_liquidity_020: str = "0"
    visible_liquidity_010: str = "0"


class Btc15mLiquiditySampleRecord(BaseModel):
    """One bounded Binance plus Polymarket liquidity sample."""

    sample_id: str
    window_id: str
    condition_id: str | None = None
    market_slug: str
    sample_kind: str
    sampled_at: str
    scheduled_at: str | None = None
    late_by_seconds: int | None = None
    binance: BinanceLiquiditySnapshot
    polymarket: list[Btc15mPolymarketLiquidityLevel] = Field(default_factory=list)
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mBoundaryObservationRecord(BaseModel):
    """Append-only raw boundary observation for one window edge."""

    window_id: str
    condition_id: str | None = None
    market_slug: str
    boundary_kind: str
    captured_at: str
    source_timestamp: str | None = None
    source_value: str | None = None
    source: str = "chainlink_rtds"
    session_id: str
    accepted: bool
    selected: bool
    selection_status: str
    notes: str | None = None


class Btc15mBoundaryDecisionRecord(BaseModel):
    """Canonicalized boundary-selection summary for one recorded window."""

    window_id: str
    condition_id: str | None = None
    market_slug: str
    created_at: str
    status: str
    pre_start: Btc15mPriceTick | None = None
    post_start: Btc15mPriceTick | None = None
    pre_end: Btc15mPriceTick | None = None
    post_end: Btc15mPriceTick | None = None
    timing_source: str = "fallback"
    timing_controls: Btc15mTimingControls = Field(default_factory=Btc15mTimingControls)
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
    notes: list[str] = Field(default_factory=list)


class Btc15mWindowRecord(BaseModel):
    """Append-only recorded BTC15m market window."""

    window: Btc15mWindowIdentity
    recorded_at: str
    recorder_session_id: str
    status: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    target_slug: str | None = None
    selection_source: str = "recurring"
    market_source_session_id: str | None = None
    chainlink_source_session_id: str | None = None
    binance_source_session_id: str | None = None
    chainlink_ticks: list[Btc15mPriceTick] = Field(default_factory=list)
    binance_ticks: list[Btc15mPriceTick] = Field(default_factory=list)
    binance_pre_start_tick: Btc15mPriceTick | None = None
    binance_post_start_tick: Btc15mPriceTick | None = None
    binance_pre_end_tick: Btc15mPriceTick | None = None
    binance_post_end_tick: Btc15mPriceTick | None = None
    market_samples: list[Btc15mMarketSample] = Field(default_factory=list)
    liquidity_samples: list[Btc15mLiquiditySampleRecord] = Field(default_factory=list)
    boundary_status: str
    timing_controls: Btc15mTimingControls = Field(default_factory=Btc15mTimingControls)
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
    paper_budget_usdc: str | None = None
    rung_notionals_usdc: list[str] = Field(default_factory=list)
    decision: str = "PENDING"
    decision_at: str | None = None
    resolution_result: str = "PENDING"
    manipulation_flags: list[str] = Field(default_factory=list)
    skip_reasons: list[str] = Field(default_factory=list)
    reason_blocks: list[Btc15mReasonBlock] = Field(default_factory=list)
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mWindowsIndexResponse(BaseModel):
    """Compact recorder response payload."""

    session_id: str
    started_at: str
    ended_at: str
    requested_seconds: int | None = None
    items: list[Btc15mWindowRecord] = Field(default_factory=list)
    total: int = 0
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mLadderRungResult(BaseModel):
    """One simulated paper ladder rung."""

    price: str
    notional_usdc: str
    quantity: str
    status: str
    fill_at: str | None = None
    fill_price: str | None = None
    cancellation_at: str | None = None


class Btc15mPriceMark(BaseModel):
    """One marked-to-midpoint sample used for favorable-path analytics."""

    observed_at: str
    midpoint: str
    pnl_usdc: str


class Btc15mPaperEvaluation(BaseModel):
    """Deterministic replay or paper-evaluation result for one recorded window."""

    window_id: str
    market_slug: str
    condition_id: str | None = None
    window_start_at: str | None = None
    window_end_at: str | None = None
    source_kind: str = "manual"
    campaign_run_id: str | None = None
    target_token_id: str | None = None
    target_outcome: str | None = None
    decision: str
    decision_at: str | None = None
    resolution_result: str
    decision_liquidity_sample: Btc15mLiquiditySampleRecord | None = None
    decision_spread: str | None = None
    realized_vol_1m_bps: str | None = None
    realized_vol_3m_bps: str | None = None
    visible_liquidity_030: str | None = None
    visible_liquidity_020: str | None = None
    visible_liquidity_010: str | None = None
    manipulation_flags: list[str] = Field(default_factory=list)
    skip_reasons: list[str] = Field(default_factory=list)
    reason_blocks: list[Btc15mReasonBlock] = Field(default_factory=list)
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
    paper_budget_usdc: str | None = None
    rung_notionals_usdc: list[str] = Field(default_factory=list)
    rungs: list[Btc15mLadderRungResult] = Field(default_factory=list)
    filled_rung_count: int = 0
    cancelled_rung_count: int = 0
    first_fill_at: str | None = None
    total_cost_usdc: str
    settlement_value_usdc: str
    realized_pnl_usdc: str
    mfe_usdc: str
    mae_usdc: str
    max_favorable_price: str | None = None
    time_to_peak_seconds: int | None = None
    max_favorable_path: list[Btc15mPriceMark] = Field(default_factory=list)


class Btc15mReplayRecord(BaseModel):
    """Append-only replay-batch record."""

    replay_id: str
    created_at: str
    from_at: str
    to_at: str
    items: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    total: int = 0
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mPaperRunRecord(BaseModel):
    """Append-only paper-run batch record."""

    run_id: str
    created_at: str
    limit: int
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    target_slug: str | None = None
    selection_source: str = "recorded"
    source_kind: str = "manual"
    campaign_run_id: str | None = None
    items: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    total_considered: int = 0
    total_evaluated: int = 0
    total_skipped: int = 0
    total_realized_pnl_usdc: str = "0"
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mCampaignRunRecord(BaseModel):
    """Append-only bounded campaign batch record."""

    run_id: str
    created_at: str
    started_at: str
    ended_at: str
    requested_hours: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    target_slug: str | None = None
    selection_source: str = "recurring"
    stop_reason: str | None = None
    items: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    total_windows: int = 0
    total_skipped: int = 0
    total_realized_pnl_usdc: str = "0"
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mBoundaryDecisionsFile(BaseModel):
    """Versioned state document for canonical boundary decisions."""

    version: int = 1
    items: list[Btc15mBoundaryDecisionRecord] = Field(default_factory=list)


class Btc15mReplaysFile(BaseModel):
    """Versioned state document for persisted replay batches."""

    version: int = 1
    items: list[Btc15mReplayRecord] = Field(default_factory=list)


class Btc15mPaperRunsFile(BaseModel):
    """Versioned state document for persisted paper-run batches."""

    version: int = 1
    items: list[Btc15mPaperRunRecord] = Field(default_factory=list)


class Btc15mCampaignRunsFile(BaseModel):
    """Versioned state document for persisted campaign batches."""

    version: int = 1
    items: list[Btc15mCampaignRunRecord] = Field(default_factory=list)


class Btc15mDashboardRungState(BaseModel):
    """One ladder rung state rendered in a BTC15m dashboard snapshot."""

    price: str
    state: str
    notional_usdc: str | None = None
    quantity: str | None = None
    visible_liquidity: str | None = None
    order_id: str | None = None
    fill_at: str | None = None
    fill_price: str | None = None
    cancellation_at: str | None = None


class Btc15mTerminalEventRecord(BaseModel):
    """Compact terminal-session event record."""

    event_at: str
    kind: str
    status: str
    message: str


class Btc15mDashboardSideState(BaseModel):
    """Compact two-sided Polymarket summary for BTC15m terminal views."""

    token_id: str | None = None
    outcome: str | None = None
    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    last_trade_price: str | None = None
    visible_liquidity_030: str | None = None
    visible_liquidity_020: str | None = None
    visible_liquidity_010: str | None = None


class Btc15mTerminalDisplayTruth(BaseModel):
    """Operator-facing display layer kept separate from strategy state."""

    display_price_to_beat: str | None = None
    display_current_btc: str | None = None
    display_up_price: str | None = None
    display_down_price: str | None = None
    display_countdown: str | None = None
    display_volume: str | None = None
    display_source: str | None = None
    display_window_label: str | None = None
    display_url: str | None = None
    display_notes: list[str] = Field(default_factory=list)


class Btc15mDashboardSnapshotRecord(BaseModel):
    """One persisted BTC15m dashboard snapshot."""

    snapshot_id: str
    session_id: str
    window_id: str
    market_slug: str
    sampled_at: str
    view_kind: str = "dashboard"
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    attach_mode: str = "current"
    observe_only: bool = False
    window_status: str
    boundary_status: str = "pending"
    window_start_at: str | None = None
    window_end_at: str | None = None
    countdown_seconds: int | None = None
    display: Btc15mTerminalDisplayTruth | None = None
    current_window_label: str | None = None
    page_parity_source: str | None = None
    page_parity_url: str | None = None
    current_live_btc_price: str | None = None
    up_price: str | None = None
    down_price: str | None = None
    display_volume: str | None = None
    selected_side: str | None = None
    current_chainlink_price: str | None = None
    current_binance_price: str | None = None
    start_price_proxy_v1: str | None = None
    price_to_beat: str | None = None
    direction_lock_status: str = "pending"
    target_token_id: str | None = None
    target_outcome: str | None = None
    paper_budget_usdc: str | None = None
    rung_notionals_usdc: list[str] = Field(default_factory=list)
    avg_entry_price: str | None = None
    exposure_quantity: str | None = None
    exposure_notional_usdc: str | None = None
    current_midpoint: str | None = None
    current_spread: str | None = None
    market_open_interest: str | None = None
    market_volume: str | None = None
    binance_best_bid: str | None = None
    binance_best_ask: str | None = None
    binance_near_touch_bid_depth: str | None = None
    binance_near_touch_ask_depth: str | None = None
    binance_realized_vol_1m_bps: str | None = None
    binance_realized_vol_3m_bps: str | None = None
    binance_volume_1m: str | None = None
    binance_volume_3m: str | None = None
    binance_near_touch_imbalance: str | None = None
    visible_liquidity_030: str | None = None
    visible_liquidity_020: str | None = None
    visible_liquidity_010: str | None = None
    manipulation_flags: list[str] = Field(default_factory=list)
    polymarket_levels: list[Btc15mPolymarketLiquidityLevel] = Field(default_factory=list)
    up_side: Btc15mDashboardSideState | None = None
    down_side: Btc15mDashboardSideState | None = None
    rungs: list[Btc15mDashboardRungState] = Field(default_factory=list)
    latest_events: list[Btc15mTerminalEventRecord] = Field(default_factory=list)
    mfe_usdc: str | None = None
    mae_usdc: str | None = None
    max_favorable_price: str | None = None
    time_to_peak_seconds: int | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mTerminalWindowTearSheet(BaseModel):
    """One finalized BTC15m terminal window within a longer attached session."""

    window: Btc15mWindowIdentity
    started_at: str
    ended_at: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    attach_mode: str = "current"
    observe_only: bool = False
    stop_reason: str
    final_state: Btc15mTerminalState
    boundary_status: str = "pending"
    display: Btc15mTerminalDisplayTruth | None = None
    current_window_label: str | None = None
    page_parity_source: str | None = None
    page_parity_url: str | None = None
    price_to_beat: str | None = None
    current_live_btc_price: str | None = None
    up_price: str | None = None
    down_price: str | None = None
    display_volume: str | None = None
    selected_side: str | None = None
    target_token_id: str | None = None
    target_outcome: str | None = None
    paper_budget_usdc: str | None = None
    rung_notionals_usdc: list[str] = Field(default_factory=list)
    avg_entry_price: str | None = None
    exposure_quantity: str | None = None
    exposure_notional_usdc: str | None = None
    filled_rung_count: int = 0
    posted_rung_count: int = 0
    cancelled_rung_count: int = 0
    total_snapshots: int = 0
    market_open_interest: str | None = None
    market_volume: str | None = None
    manipulation_flags: list[str] = Field(default_factory=list)
    skip_reasons: list[str] = Field(default_factory=list)
    latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
    latest_evaluation: Btc15mPaperEvaluation | None = None
    rungs: list[Btc15mDashboardRungState] = Field(default_factory=list)
    operator_events: list[Btc15mTerminalEventRecord] = Field(default_factory=list)
    mfe_usdc: str | None = None
    mae_usdc: str | None = None
    max_favorable_price: str | None = None
    time_to_peak_seconds: int | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mTerminalSessionRecord(BaseModel):
    """Append-only bounded BTC15m terminal session summary."""

    session_id: str
    created_at: str
    started_at: str
    ended_at: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    attach_mode: str = "current"
    observe_only: bool = False
    follow_current: bool = False
    stop_reason: str
    final_state: Btc15mTerminalState
    current_requested: bool = True
    window: Btc15mWindowIdentity | None = None
    boundary_status: str = "pending"
    display: Btc15mTerminalDisplayTruth | None = None
    current_window_label: str | None = None
    page_parity_source: str | None = None
    page_parity_url: str | None = None
    price_to_beat: str | None = None
    current_live_btc_price: str | None = None
    up_price: str | None = None
    down_price: str | None = None
    display_volume: str | None = None
    selected_side: str | None = None
    target_token_id: str | None = None
    target_outcome: str | None = None
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
    paper_budget_usdc: str | None = None
    rung_notionals_usdc: list[str] = Field(default_factory=list)
    avg_entry_price: str | None = None
    exposure_quantity: str | None = None
    exposure_notional_usdc: str | None = None
    filled_rung_count: int = 0
    posted_rung_count: int = 0
    cancelled_rung_count: int = 0
    total_snapshots: int = 0
    market_open_interest: str | None = None
    market_volume: str | None = None
    manipulation_flags: list[str] = Field(default_factory=list)
    latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
    latest_evaluation: Btc15mPaperEvaluation | None = None
    rungs: list[Btc15mDashboardRungState] = Field(default_factory=list)
    window_tear_sheets: list[Btc15mTerminalWindowTearSheet] = Field(default_factory=list)
    rollover_history: list[str] = Field(default_factory=list)
    rollover_count: int = 0
    operator_events: list[Btc15mTerminalEventRecord] = Field(default_factory=list)
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mTerminalSessionsFile(BaseModel):
    """Versioned state document for persisted terminal sessions."""

    version: int = 1
    items: list[Btc15mTerminalSessionRecord] = Field(default_factory=list)


class Btc15mAutoRollRunRecord(BaseModel):
    """Append-only bounded BTC15m auto-roll session record."""

    run_id: str
    created_at: str
    started_at: str
    ended_at: str
    requested_hours: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    stop_reason: str
    items: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    total_windows: int = 0
    total_skipped: int = 0
    total_realized_pnl_usdc: str = "0"
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mAutoRollRunsFile(BaseModel):
    """Versioned state document for persisted auto-roll sessions."""

    version: int = 1
    items: list[Btc15mAutoRollRunRecord] = Field(default_factory=list)


class Btc15mRecordStartResponse(Btc15mWindowsIndexResponse):
    """Bounded recorder-start response."""


class Btc15mRecordWindowResponse(Btc15mWindowsIndexResponse):
    """Single-window recorder response."""

    slug: str


class Btc15mReplayResponse(BaseModel):
    """Replay command response payload."""

    replay: Btc15mReplayRecord


class Btc15mResolveCurrentResponse(BaseModel):
    """Current BTC15m window resolution response."""

    checked_at: str
    timing_source: str = "fallback"
    selection_source: str = "current_exact"
    status: str
    seconds_to_start: int | None = None
    seconds_to_end: int | None = None
    window: Btc15mWindowIdentity | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mPaperRunResponse(BaseModel):
    """Paper-run command response payload."""

    run: Btc15mPaperRunRecord


class Btc15mLiveResponse(BaseModel):
    """Bounded live-data paper run response."""

    run_id: str
    started_at: str
    ended_at: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    requested_hours: str | None = None
    stop_reason: str
    window: Btc15mWindowIdentity | None = None
    evaluation: Btc15mPaperEvaluation | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mLiquiditySampleResponse(BaseModel):
    """Bounded operator liquidity-sampling response."""

    session_id: str
    started_at: str
    ended_at: str
    requested_seconds: int
    items: list[Btc15mLiquiditySampleRecord] = Field(default_factory=list)
    total: int = 0
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mDashboardResponse(BaseModel):
    """Bounded dashboard session response."""

    session_id: str
    started_at: str
    ended_at: str
    requested_seconds: int
    window: Btc15mWindowIdentity | None = None
    total_snapshots: int = 0
    latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
    latest_evaluation: Btc15mPaperEvaluation | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mCampaignNextWindowResponse(BaseModel):
    """Current or next BTC15m campaign window response."""

    checked_at: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    target_slug: str | None = None
    selection_source: str = "recurring"
    waited_seconds: int = 0
    timed_out: bool = False
    poll_count: int = 0
    window: Btc15mWindowIdentity | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mCampaignRunResponse(BaseModel):
    """Bounded campaign-run response."""

    campaign: Btc15mCampaignRunRecord


class Btc15mAutoRollResponse(BaseModel):
    """Bounded auto-roll response."""

    run: Btc15mAutoRollRunRecord


class Btc15mTerminalResponse(BaseModel):
    """BTC15m operator-terminal response."""

    session_id: str
    started_at: str
    ended_at: str
    mode: Btc15mRunMode = Btc15mRunMode.PAPER
    attach_mode: str = "current"
    stop_reason: str
    window: Btc15mWindowIdentity | None = None
    total_snapshots: int = 0
    latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
    session: Btc15mTerminalSessionRecord | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mTerminalReportSummary(BaseModel):
    """Aggregate terminal-session summary."""

    terminal_session_count: int = 0
    paper_session_count: int = 0
    live_session_count: int = 0
    observe_only_session_count: int = 0
    waiting_session_count: int = 0
    resolved_session_count: int = 0
    skipped_session_count: int = 0
    total_realized_pnl_usdc: str = "0"
    average_realized_pnl_usdc: str = "0"


class Btc15mTerminalReportResponse(BaseModel):
    """Aggregate terminal-session report."""

    summary: Btc15mTerminalReportSummary
    session: Btc15mTerminalSessionRecord | None = None
    recent_sessions: list[Btc15mTerminalSessionRecord] = Field(default_factory=list)
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mTerminalReplayResponse(BaseModel):
    """Replay metadata and snapshots for one stored BTC15m terminal session."""

    session_id: str
    total_snapshots: int = 0
    session: Btc15mTerminalSessionRecord | None = None
    first_snapshot: Btc15mDashboardSnapshotRecord | None = None
    latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mCampaignReportSummary(BaseModel):
    """Aggregate campaign-only summary."""

    campaign_run_count: int = 0
    evaluated_window_count: int = 0
    total_realized_pnl_usdc: str = "0"
    average_realized_pnl_usdc: str = "0"
    win_count: int = 0
    loss_count: int = 0
    tie_count: int = 0
    skip_count: int = 0
    average_decision_spread: str | None = None
    average_realized_vol_1m_bps: str | None = None
    average_realized_vol_3m_bps: str | None = None
    skip_reason_counts: dict[str, int] = Field(default_factory=dict)


class Btc15mCampaignReportResponse(BaseModel):
    """Aggregate campaign-only report."""

    summary: Btc15mCampaignReportSummary
    recent_runs: list[Btc15mCampaignRunRecord] = Field(default_factory=list)
    recent_evaluations: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    errors: list[Btc15mSectionError] = Field(default_factory=list)


class Btc15mReportSummary(BaseModel):
    """Compact BTC15m research summary."""

    recorded_window_count: int = 0
    completed_window_count: int = 0
    replay_batch_count: int = 0
    paper_run_count: int = 0
    evaluated_window_count: int = 0
    total_realized_pnl_usdc: str = "0"
    average_realized_pnl_usdc: str = "0"
    win_count: int = 0
    loss_count: int = 0
    tie_count: int = 0
    skip_count: int = 0
    skip_reason_counts: dict[str, int] = Field(default_factory=dict)
    campaign_run_count: int = 0


class Btc15mReportResponse(BaseModel):
    """Aggregate BTC15m research report."""

    summary: Btc15mReportSummary
    latest_active_window: Btc15mWindowRecord | None = None
    campaign_summary: Btc15mCampaignReportSummary | None = None
    recent_replays: list[Btc15mReplayRecord] = Field(default_factory=list)
    recent_runs: list[Btc15mPaperRunRecord] = Field(default_factory=list)
    recent_evaluations: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    errors: list[Btc15mSectionError] = Field(default_factory=list)
