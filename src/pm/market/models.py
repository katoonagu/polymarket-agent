"""Pydantic models for read-only market discovery and market intelligence."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.data.models import NormalizedHolder

Number = int | float


class NormalizedMarket(BaseModel):
    """Normalized market fields exposed by the CLI."""

    market_slug: str
    event_slug: str | None = None
    question: str
    event_title: str | None = None
    active: bool
    closed: bool
    enable_order_book: bool
    condition_id: str | None = None
    token_ids: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    min_tick: Number | None = None
    min_order_size: Number | None = None


class NormalizedEvent(BaseModel):
    """Normalized event fields exposed by the CLI."""

    event_slug: str
    title: str
    active: bool
    closed: bool
    enable_order_book: bool
    markets: list[NormalizedMarket] = Field(default_factory=list)


class MarketSearchResponse(BaseModel):
    """Deterministic response returned by Gamma-backed market search."""

    query: str
    results: list[NormalizedMarket] = Field(default_factory=list)
    total: int = 0


class NormalizedBookLevel(BaseModel):
    """Normalized book level for public CLOB reads."""

    price: str
    size: str


class NormalizedBook(BaseModel):
    """Normalized order book payload exposed by the CLI."""

    token_id: str
    bids: list[NormalizedBookLevel] = Field(default_factory=list)
    asks: list[NormalizedBookLevel] = Field(default_factory=list)
    tick_size: str | None = None
    min_order_size: str | None = None


class NormalizedPriceQuote(BaseModel):
    """Normalized buy and sell price quote for a token."""

    token_id: str
    buy_price: str | None = None
    sell_price: str | None = None


class NormalizedMidpointQuote(BaseModel):
    """Normalized midpoint quote for a token."""

    token_id: str
    midpoint: str


class NormalizedSpreadQuote(BaseModel):
    """Normalized spread quote for a token."""

    token_id: str
    spread: str


class MarketSectionError(BaseModel):
    """Partial upstream failure captured during snapshot assembly."""

    section: str
    code: str
    message: str


class WatchedMarket(BaseModel):
    """Locally watched market metadata."""

    market_slug: str
    event_slug: str | None = None
    question: str
    label: str | None = None
    tags: list[str] = Field(default_factory=list)
    added_at: str


class MarketWatchlistFile(BaseModel):
    """On-disk watched-markets document."""

    version: int = 1
    markets: list[WatchedMarket] = Field(default_factory=list)


class MarketWatchListResponse(BaseModel):
    """Watched-market listing payload."""

    items: list[WatchedMarket] = Field(default_factory=list)
    total: int = 0


class MarketWatchMutationResponse(BaseModel):
    """Add/remove watchlist response payload."""

    market: WatchedMarket


class MarketSnapshotTokenSummary(BaseModel):
    """Compact token-level snapshot summary."""

    token_id: str
    outcome: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    best_bid: str | None = None
    best_ask: str | None = None
    bid_level_count: int = 0
    ask_level_count: int = 0


class MarketSnapshotRecord(BaseModel):
    """Append-only saved market snapshot."""

    snapshot_at: str
    market_slug: str
    event_slug: str | None = None
    question: str | None = None
    event_title: str | None = None
    condition_id: str | None = None
    token_ids: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    active: bool | None = None
    closed: bool | None = None
    watch_metadata: WatchedMarket | None = None
    tokens: list[MarketSnapshotTokenSummary] = Field(default_factory=list)
    open_interest: str | None = None
    top_holders: list[NormalizedHolder] = Field(default_factory=list)
    holders_total_returned: int = 0
    errors: list[MarketSectionError] = Field(default_factory=list)


class MarketSnapshotsFile(BaseModel):
    """On-disk saved market snapshots document."""

    version: int = 1
    snapshots: list[MarketSnapshotRecord] = Field(default_factory=list)


class MarketSnapshotResponse(BaseModel):
    """Single saved snapshot response."""

    snapshot: MarketSnapshotRecord


class MarketWatchRefreshResponse(BaseModel):
    """Batch watchlist refresh response."""

    items: list[MarketSnapshotRecord] = Field(default_factory=list)
    total: int = 0


class RecurringMarketCandidate(BaseModel):
    """Deterministically ranked recurring-market candidate."""

    rank: int
    match_score: int
    matched_interval: str
    recency_source: str | None = None
    market_slug: str
    event_slug: str | None = None
    question: str
    event_title: str | None = None
    active: bool
    closed: bool
    enable_order_book: bool
    condition_id: str | None = None
    token_ids: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    min_tick: Number | None = None
    min_order_size: Number | None = None


class RecurringMarketListResponse(BaseModel):
    """Recurring-market candidate list response."""

    query: str
    interval: str
    items: list[RecurringMarketCandidate] = Field(default_factory=list)
    total: int = 0


class RecurringMarketLatestResponse(BaseModel):
    """Single top-ranked recurring-market response."""

    query: str
    interval: str
    item: RecurringMarketCandidate | None = None
