"""Normalized models for bounded public stream sessions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.market.models import NormalizedBookLevel, RecurringMarketCandidate


class StreamSectionError(BaseModel):
    """Partial stream-session failure captured without aborting the whole command."""

    section: str
    code: str
    message: str


class NormalizedMarketStreamEvent(BaseModel):
    """Normalized public market websocket event."""

    event_type: str
    token_id: str | None = None
    market: str | None = None
    timestamp: int | None = None
    hash: str | None = None
    price: str | None = None
    size: str | None = None
    side: str | None = None
    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    old_tick_size: str | None = None
    new_tick_size: str | None = None
    bids: list[NormalizedBookLevel] = Field(default_factory=list)
    asks: list[NormalizedBookLevel] = Field(default_factory=list)


class NormalizedCryptoPriceEvent(BaseModel):
    """Normalized public crypto price stream event."""

    event_type: str = "crypto_price"
    symbol: str
    source: str
    timestamp: int | None = None
    value: str


class CapturedStreamEvent(BaseModel):
    """Persisted captured stream event envelope."""

    session_id: str
    stream_kind: str
    source: str
    captured_at: str
    event_type: str
    market_event: NormalizedMarketStreamEvent | None = None
    crypto_event: NormalizedCryptoPriceEvent | None = None


class BoundedStreamSession(BaseModel):
    """Metadata describing a single bounded public stream session."""

    session_id: str
    stream_kind: str
    source: str
    started_at: str
    ended_at: str
    duration_seconds: int
    requested_seconds: int
    max_events: int | None = None
    captured_event_count: int = 0
    reconnect_count: int = 0


class MarketTokenStreamSummary(BaseModel):
    """Compact single-token market stream summary."""

    token_id: str
    event_count: int = 0
    latest_best_bid: str | None = None
    latest_best_ask: str | None = None
    latest_midpoint: str | None = None
    latest_spread: str | None = None
    latest_last_trade_price: str | None = None
    latest_tick_size: str | None = None
    event_counts: dict[str, int] = Field(default_factory=dict)


class CryptoStreamSummary(BaseModel):
    """Compact crypto price session summary."""

    symbol: str
    source: str
    event_count: int = 0
    latest_value: str | None = None
    first_timestamp: int | None = None
    last_timestamp: int | None = None


class MarketWatchTokenSummary(BaseModel):
    """Per-token compact watch session summary."""

    token_id: str
    outcome: str | None = None
    event_count: int = 0
    latest_best_bid: str | None = None
    latest_best_ask: str | None = None
    latest_midpoint: str | None = None
    latest_spread: str | None = None


class MarketWatchStreamSummary(BaseModel):
    """Compact market watch session summary."""

    market_slug: str
    condition_id: str | None = None
    token_ids: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    active: bool
    closed: bool
    tokens: list[MarketWatchTokenSummary] = Field(default_factory=list)
    aggregate_event_count: int = 0


class MarketStreamResponse(BaseModel):
    """Single-token market stream response."""

    session: BoundedStreamSession
    summary: MarketTokenStreamSummary
    events: list[CapturedStreamEvent] = Field(default_factory=list)
    errors: list[StreamSectionError] = Field(default_factory=list)


class CryptoStreamResponse(BaseModel):
    """Crypto stream response."""

    session: BoundedStreamSession
    summary: CryptoStreamSummary
    events: list[CapturedStreamEvent] = Field(default_factory=list)
    errors: list[StreamSectionError] = Field(default_factory=list)


class MarketWatchStreamResponse(BaseModel):
    """Market watch stream response."""

    session: BoundedStreamSession
    summary: MarketWatchStreamSummary
    events: list[CapturedStreamEvent] = Field(default_factory=list)
    errors: list[StreamSectionError] = Field(default_factory=list)


class RecurringStreamSummary(BaseModel):
    """Combined recurring market and RTDS session summary."""

    recurring_market: RecurringMarketCandidate
    market: MarketWatchStreamSummary | None = None
    crypto: CryptoStreamSummary | None = None
    merged_event_count: int = 0


class RecurringStreamResponse(BaseModel):
    """Combined recurring stream response."""

    session: BoundedStreamSession
    summary: RecurringStreamSummary
    events: list[CapturedStreamEvent] = Field(default_factory=list)
    errors: list[StreamSectionError] = Field(default_factory=list)
