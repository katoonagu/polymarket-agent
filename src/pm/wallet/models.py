"""Models for local tracked-wallet registry and shadow intelligence."""

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
    """Partial failure captured during summary or snapshot aggregation."""

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
