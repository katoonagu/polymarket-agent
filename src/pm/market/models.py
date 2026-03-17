"""Pydantic models for the initial market discovery scaffold."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MarketSearchResult(BaseModel):
    """Minimal normalized market shape for future search results."""

    market_slug: str
    question: str


class MarketSearchResponse(BaseModel):
    """Deterministic response returned by the scaffolded search command."""

    query: str
    results: list[MarketSearchResult] = Field(default_factory=list)
    total: int = 0
