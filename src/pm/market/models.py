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
