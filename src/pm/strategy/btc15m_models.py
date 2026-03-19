"""Models for the BTC 15-minute Chainlink directional ladder research surface."""

from __future__ import annotations

from pydantic import BaseModel, Field

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


class Btc15mWindowIdentity(BaseModel):
    """Normalized BTC15m recurring-market identity."""

    strategy_name: str
    window_id: str
    condition_id: str | None = None
    market_slug: str
    token_ids: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
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
    bids: list[NormalizedBookLevel] = Field(default_factory=list)
    asks: list[NormalizedBookLevel] = Field(default_factory=list)


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
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
    notes: list[str] = Field(default_factory=list)


class Btc15mWindowRecord(BaseModel):
    """Append-only recorded BTC15m market window."""

    window: Btc15mWindowIdentity
    recorded_at: str
    recorder_session_id: str
    status: str
    market_source_session_id: str | None = None
    chainlink_source_session_id: str | None = None
    binance_source_session_id: str | None = None
    chainlink_ticks: list[Btc15mPriceTick] = Field(default_factory=list)
    binance_ticks: list[Btc15mPriceTick] = Field(default_factory=list)
    market_samples: list[Btc15mMarketSample] = Field(default_factory=list)
    boundary_status: str
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
    decision: str = "PENDING"
    decision_at: str | None = None
    resolution_result: str = "PENDING"
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
    target_token_id: str | None = None
    target_outcome: str | None = None
    decision: str
    decision_at: str | None = None
    resolution_result: str
    skip_reasons: list[str] = Field(default_factory=list)
    reason_blocks: list[Btc15mReasonBlock] = Field(default_factory=list)
    start_price_proxy_v1: str | None = None
    end_price_proxy_v1: str | None = None
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
    items: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    total_considered: int = 0
    total_evaluated: int = 0
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


class Btc15mRecordStartResponse(Btc15mWindowsIndexResponse):
    """Bounded recorder-start response."""


class Btc15mRecordWindowResponse(Btc15mWindowsIndexResponse):
    """Single-window recorder response."""

    slug: str


class Btc15mReplayResponse(BaseModel):
    """Replay command response payload."""

    replay: Btc15mReplayRecord


class Btc15mPaperRunResponse(BaseModel):
    """Paper-run command response payload."""

    run: Btc15mPaperRunRecord


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


class Btc15mReportResponse(BaseModel):
    """Aggregate BTC15m research report."""

    summary: Btc15mReportSummary
    latest_active_window: Btc15mWindowRecord | None = None
    recent_replays: list[Btc15mReplayRecord] = Field(default_factory=list)
    recent_runs: list[Btc15mPaperRunRecord] = Field(default_factory=list)
    recent_evaluations: list[Btc15mPaperEvaluation] = Field(default_factory=list)
    errors: list[Btc15mSectionError] = Field(default_factory=list)
