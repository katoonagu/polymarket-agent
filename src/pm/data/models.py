"""Pydantic models for public Data API reads."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizedTrade(BaseModel):
    """Normalized trade shape exposed by the CLI."""

    user: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    side: str | None = None
    outcome: str | None = None
    price: str | None = None
    size: str | None = None
    timestamp: int | None = None
    transaction_hash: str | None = None


class NormalizedActivity(BaseModel):
    """Normalized activity shape exposed by the CLI."""

    user: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    activity_type: str
    side: str | None = None
    outcome: str | None = None
    price: str | None = None
    size: str | None = None
    usdc_size: str | None = None
    timestamp: int | None = None
    transaction_hash: str | None = None


class NormalizedCurrentPosition(BaseModel):
    """Normalized current position shape exposed by the CLI."""

    user: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    outcome: str | None = None
    size: str | None = None
    average_price: str | None = None
    initial_value: str | None = None
    current_value: str | None = None
    cash_pnl: str | None = None
    percent_pnl: str | None = None


class NormalizedClosedPosition(BaseModel):
    """Normalized closed position shape exposed by the CLI."""

    user: str
    market_slug: str | None = None
    condition_id: str | None = None
    token_id: str | None = None
    outcome: str | None = None
    average_price: str | None = None
    total_bought: str | None = None
    realized_pnl: str | None = None
    current_price: str | None = None
    timestamp: int | None = None


class NormalizedHolder(BaseModel):
    """Normalized holder row exposed by the CLI."""

    market_slug: str | None = None
    condition_id: str
    token_id: str
    holder_address: str
    amount: str
    name: str | None = None
    pseudonym: str | None = None
    outcome_index: int | None = None
    rank: int | None = None


class NormalizedOpenInterest(BaseModel):
    """Normalized open-interest summary exposed by the CLI."""

    market_slug: str | None = None
    condition_id: str
    open_interest: str


class NormalizedHoldingsValue(BaseModel):
    """Normalized holdings value exposed by the CLI."""

    user: str
    value: str


class NormalizedTradedCount(BaseModel):
    """Normalized traded-count summary exposed by the CLI."""

    user: str
    traded: int


class NormalizedLeaderboardEntry(BaseModel):
    """Normalized public leaderboard row."""

    address: str
    rank: int | None = None
    display_name: str | None = None
    user_name: str | None = None
    pnl: str | None = None
    volume: str | None = None


class TradesResponse(BaseModel):
    """Normalized trades response."""

    user: str
    items: list[NormalizedTrade] = Field(default_factory=list)
    total: int = 0


class ActivityResponse(BaseModel):
    """Normalized activity response."""

    user: str
    items: list[NormalizedActivity] = Field(default_factory=list)
    total: int = 0


class PositionsResponse(BaseModel):
    """Normalized current positions response."""

    user: str
    items: list[NormalizedCurrentPosition] = Field(default_factory=list)
    total: int = 0


class ClosedPositionsResponse(BaseModel):
    """Normalized closed positions response."""

    user: str
    items: list[NormalizedClosedPosition] = Field(default_factory=list)
    total: int = 0


class HoldersResponse(BaseModel):
    """Normalized holders response."""

    market_slug: str | None = None
    condition_id: str
    items: list[NormalizedHolder] = Field(default_factory=list)
    total: int = 0


class LeaderboardResponse(BaseModel):
    """Normalized leaderboard response."""

    items: list[NormalizedLeaderboardEntry] = Field(default_factory=list)
    total: int = 0
