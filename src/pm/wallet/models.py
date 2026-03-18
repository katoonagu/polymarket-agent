"""Models for local tracked-wallet registry and wallet intelligence."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.data.models import (
    NormalizedActivity,
    NormalizedCurrentPosition,
    NormalizedTrade,
)
from pm.market.models import NormalizedBook


class TrackedWallet(BaseModel):
    """Locally tracked wallet metadata."""

    address: str
    label: str | None = None
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    added_at: str


class WalletRegistryFile(BaseModel):
    """On-disk wallet registry document."""

    version: int = 1
    wallets: list[TrackedWallet] = Field(default_factory=list)


class WalletListResponse(BaseModel):
    """Deterministic wallet list payload."""

    wallets: list[TrackedWallet] = Field(default_factory=list)
    total: int = 0


class WalletMutationResponse(BaseModel):
    """Add/remove response payload."""

    wallet: TrackedWallet


class WalletTradesResponse(BaseModel):
    """Tracked-wallet trade view."""

    wallet: TrackedWallet
    items: list[NormalizedTrade] = Field(default_factory=list)
    total: int = 0


class WalletActivityResponse(BaseModel):
    """Tracked-wallet activity view."""

    wallet: TrackedWallet
    items: list[NormalizedActivity] = Field(default_factory=list)
    total: int = 0


class WalletPositionsResponse(BaseModel):
    """Tracked-wallet current-position view."""

    wallet: TrackedWallet
    items: list[NormalizedCurrentPosition] = Field(default_factory=list)
    total: int = 0


class WalletSummaryMetrics(BaseModel):
    """Compact wallet metrics used by summary and snapshot."""

    holdings_value: str | None = None
    traded_count: int | None = None
    current_positions_count: int | None = None
    closed_positions_count: int | None = None


class WalletSectionError(BaseModel):
    """Partial failure captured during aggregation."""

    section: str
    code: str
    message: str


class WalletRecentTrades(BaseModel):
    """Recent trades section for wallet summary."""

    items: list[NormalizedTrade] = Field(default_factory=list)
    total: int = 0


class WalletRecentActivity(BaseModel):
    """Recent activity section for wallet summary."""

    items: list[NormalizedActivity] = Field(default_factory=list)
    total: int = 0


class WalletSummaryResponse(BaseModel):
    """Tracked-wallet summary payload."""

    wallet: TrackedWallet
    metrics: WalletSummaryMetrics = Field(default_factory=WalletSummaryMetrics)
    recent_trades: WalletRecentTrades = Field(default_factory=WalletRecentTrades)
    recent_activity: WalletRecentActivity = Field(default_factory=WalletRecentActivity)
    errors: list[WalletSectionError] = Field(default_factory=list)


class WalletSnapshotItem(BaseModel):
    """Compact tracked-wallet overview row."""

    wallet: TrackedWallet
    metrics: WalletSummaryMetrics = Field(default_factory=WalletSummaryMetrics)
    errors: list[WalletSectionError] = Field(default_factory=list)


class WalletSnapshotResponse(BaseModel):
    """Compact tracked-wallet snapshot payload."""

    items: list[WalletSnapshotItem] = Field(default_factory=list)
    total: int = 0


class WalletDiscoveryTokenExposure(BaseModel):
    """Per-token holder exposure for wallet discovery."""

    token_id: str
    amount: str
    outcome_index: int | None = None


class WalletDiscoveryItem(BaseModel):
    """Normalized wallet-discovery candidate."""

    address: str
    source: str
    tracked: bool
    tracked_wallet: TrackedWallet | None = None
    display_name: str | None = None
    user_name: str | None = None
    rank: int | None = None
    pnl: str | None = None
    volume: str | None = None
    market_slug: str | None = None
    condition_id: str | None = None
    token_exposures: list[WalletDiscoveryTokenExposure] = Field(default_factory=list)


class WalletLeaderboardDiscoveryResponse(BaseModel):
    """Leaderboard-backed wallet discovery response."""

    items: list[WalletDiscoveryItem] = Field(default_factory=list)
    total: int = 0
    errors: list[WalletSectionError] = Field(default_factory=list)


class WalletHoldersDiscoveryResponse(BaseModel):
    """Holder-backed wallet discovery response."""

    market_slug: str | None = None
    condition_id: str | None = None
    items: list[WalletDiscoveryItem] = Field(default_factory=list)
    total: int = 0
    errors: list[WalletSectionError] = Field(default_factory=list)


class WalletScoreComponent(BaseModel):
    """Explainable score component."""

    weight: float
    score: float | None = None
    available: bool
    inputs: dict[str, object] = Field(default_factory=dict)


class WalletScoreResponse(BaseModel):
    """Deterministic wallet score response."""

    address: str
    tracked: bool
    tracked_wallet: TrackedWallet | None = None
    total_score: float | None = None
    available_weight: float = 0.0
    components: dict[str, WalletScoreComponent] = Field(default_factory=dict)
    errors: list[WalletSectionError] = Field(default_factory=list)


class WalletRankItem(BaseModel):
    """Ranked tracked-wallet score row."""

    rank: int
    score: WalletScoreResponse


class WalletRankTrackedResponse(BaseModel):
    """Tracked-wallet ranking payload."""

    items: list[WalletRankItem] = Field(default_factory=list)
    total: int = 0


class WalletCompareResponse(BaseModel):
    """Pairwise wallet score comparison payload."""

    left: WalletScoreResponse
    right: WalletScoreResponse
    winner_address: str | None = None
    score_delta: float | None = None
    component_deltas: dict[str, float | None] = Field(default_factory=dict)


class WalletEvent(BaseModel):
    """Normalized tracked-wallet event persisted from public feeds."""

    source_wallet: str
    transaction_hash: str | None = None
    timestamp: int | None = None
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    side: str | None = None
    outcome: str | None = None
    source_price: str | None = None
    source_size: str | None = None
    source_kind: str
    source_activity_type: str | None = None
    dedupe_key: str
    classification: str


class WalletSignal(BaseModel):
    """Derived read-only wallet signal persisted for later review."""

    source_wallet: str
    transaction_hash: str | None = None
    timestamp: int | None = None
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    side: str | None = None
    outcome: str | None = None
    source_price: str | None = None
    source_size: str | None = None
    source_kind: str
    source_activity_type: str | None = None
    dedupe_key: str
    classification: str


class WalletEventsFile(BaseModel):
    """On-disk wallet-events state document."""

    version: int = 1
    events: list[WalletEvent] = Field(default_factory=list)


class WalletSignalsFile(BaseModel):
    """On-disk wallet-signals state document."""

    version: int = 1
    signals: list[WalletSignal] = Field(default_factory=list)


class WalletShadowCandidateIntent(BaseModel):
    """Read-only candidate copy intent produced by shadow simulation."""

    source_wallet: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    side: str | None = None
    outcome: str | None = None
    source_price: str | None = None
    current_price: str | None = None
    drift: str | None = None
    spread: str | None = None
    spread_pct: str | None = None
    simulated_size_usdc: str
    decision: str
    skip_reason: str | None = None
    classification: str
    transaction_hash: str | None = None
    timestamp: int | None = None
    dedupe_key: str
    book: NormalizedBook | None = None


class WalletShadowRunParameters(BaseModel):
    """Fixed shadow-simulation parameters stored with each run."""

    fixed_size_usdc: str
    max_drift_pct: str
    max_spread_pct: str
    entry_only: bool
    limit: int


class WalletShadowRun(BaseModel):
    """Persisted read-only shadow-simulation run."""

    source_wallet: str
    run_at: str
    parameters: WalletShadowRunParameters
    new_signal_count: int = 0
    duplicate_event_count: int = 0
    would_copy_count: int = 0
    skip_count: int = 0
    candidate_intents: list[WalletShadowCandidateIntent] = Field(default_factory=list)
    errors: list[WalletSectionError] = Field(default_factory=list)


class WalletShadowRunsFile(BaseModel):
    """On-disk wallet shadow-run state document."""

    version: int = 1
    runs: list[WalletShadowRun] = Field(default_factory=list)


class WalletMonitorRunResponse(BaseModel):
    """Response returned by a manual monitor ingestion pass."""

    wallet: TrackedWallet
    fetched_trades_count: int = 0
    fetched_activity_count: int = 0
    new_events_count: int = 0
    duplicate_events_count: int = 0
    new_signals: list[WalletSignal] = Field(default_factory=list)
    errors: list[WalletSectionError] = Field(default_factory=list)


class WalletSignalsResponse(BaseModel):
    """Persisted signal view for a tracked wallet."""

    wallet: TrackedWallet
    items: list[WalletSignal] = Field(default_factory=list)
    total: int = 0


class WalletShadowSimulationResponse(BaseModel):
    """Response returned by a read-only shadow simulation run."""

    wallet: TrackedWallet
    run: WalletShadowRun


class WalletShadowReportResponse(BaseModel):
    """Read-only summary of stored shadow simulation runs."""

    wallet: TrackedWallet
    run_count: int = 0
    would_copy_count: int = 0
    skip_count: int = 0
    latest_run: WalletShadowRun | None = None
