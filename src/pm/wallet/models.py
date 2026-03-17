"""Models for local tracked-wallet registry and wallet intelligence."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.data.models import (
    NormalizedActivity,
    NormalizedCurrentPosition,
    NormalizedTrade,
)


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
