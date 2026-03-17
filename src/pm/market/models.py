"""Pydantic models for read-only Gamma market discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
