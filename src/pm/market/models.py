"""Pydantic models for Gamma market discovery and normalized CLI output."""

from __future__ import annotations

import json
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

Number = int | float


def _parse_string_list(value: Any) -> list[str]:
    """Parse Gamma list-like fields that may arrive as JSON strings."""
    if value is None:
        return []

    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            msg = "Expected a JSON array string."
            raise ValueError(msg)
        return [str(item) for item in parsed]

    if isinstance(value, list):
        return [str(item) for item in value]

    msg = "Expected a list or JSON array string."
    raise ValueError(msg)


class GammaEventReferenceWire(BaseModel):
    """Minimal nested event shape returned on market payloads."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    slug: str
    title: str | None = None


class GammaMarketWire(BaseModel):
    """Raw market payload from Gamma."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    slug: str
    question: str
    active: bool = False
    closed: bool = False
    enable_order_book: bool = Field(default=False, alias="enableOrderBook")
    condition_id: str | None = Field(default=None, alias="conditionId")
    clob_token_ids: list[str] = Field(default_factory=list, alias="clobTokenIds")
    outcomes: list[str] = Field(default_factory=list)
    min_tick: Number | None = Field(default=None, alias="orderPriceMinTickSize")
    min_order_size: Number | None = Field(default=None, alias="orderMinSize")
    events: list[GammaEventReferenceWire] = Field(default_factory=list)

    @field_validator("clob_token_ids", "outcomes", mode="before")
    @classmethod
    def parse_list_like_fields(cls, value: Any) -> list[str]:
        """Handle Gamma fields that sometimes arrive as JSON-encoded strings."""
        return _parse_string_list(value)


class GammaEventWire(BaseModel):
    """Raw event payload from Gamma."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    slug: str
    title: str
    active: bool = False
    closed: bool = False
    enable_order_book: bool = Field(default=False, alias="enableOrderBook")
    markets: list[GammaMarketWire] = Field(default_factory=list)


class GammaSearchResponseWire(BaseModel):
    """Raw search response payload from Gamma."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    events: list[GammaEventWire] = Field(default_factory=list)
    pagination: dict[str, Any] = Field(default_factory=dict)


class NormalizedMarket(BaseModel):
    """Normalized market payload exposed by the CLI and adapter."""

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

    @classmethod
    def from_wire(
        cls,
        market: GammaMarketWire,
        *,
        event_slug: str | None = None,
        event_title: str | None = None,
    ) -> Self:
        """Normalize a raw market payload."""
        nested_event = market.events[0] if market.events else None

        return cls(
            market_slug=market.slug,
            event_slug=event_slug or (nested_event.slug if nested_event else None),
            question=market.question,
            event_title=event_title or (nested_event.title if nested_event else None),
            active=market.active,
            closed=market.closed,
            enable_order_book=market.enable_order_book,
            condition_id=market.condition_id,
            token_ids=market.clob_token_ids,
            outcomes=market.outcomes,
            min_tick=market.min_tick,
            min_order_size=market.min_order_size,
        )


class NormalizedEvent(BaseModel):
    """Normalized event payload exposed by the CLI and adapter."""

    event_slug: str
    title: str
    active: bool
    closed: bool
    enable_order_book: bool
    markets: list[NormalizedMarket] = Field(default_factory=list)

    @classmethod
    def from_wire(cls, event: GammaEventWire) -> Self:
        """Normalize a raw event payload, including child markets."""
        markets = [
            NormalizedMarket.from_wire(
                market,
                event_slug=event.slug,
                event_title=event.title,
            )
            for market in event.markets
        ]
        return cls(
            event_slug=event.slug,
            title=event.title,
            active=event.active,
            closed=event.closed,
            enable_order_book=event.enable_order_book,
            markets=markets,
        )


class MarketSearchResponse(BaseModel):
    """Normalized search response for CLI output."""

    query: str
    results: list[NormalizedMarket] = Field(default_factory=list)
    total: int = 0


class ClobBookLevelWire(BaseModel):
    """Raw price level returned by the public CLOB book endpoint."""

    model_config = ConfigDict(extra="ignore")

    price: str
    size: str


class ClobBookWire(BaseModel):
    """Raw book payload from the public CLOB API."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    token_id: str = Field(alias="asset_id")
    bids: list[ClobBookLevelWire] = Field(default_factory=list)
    asks: list[ClobBookLevelWire] = Field(default_factory=list)
    tick_size: str | None = None
    min_order_size: str | None = None


class NormalizedBookLevel(BaseModel):
    """Normalized book level exposed by the CLI and CLOB adapter."""

    price: str
    size: str

    @classmethod
    def from_wire(cls, level: ClobBookLevelWire) -> Self:
        """Normalize a raw CLOB price level."""
        return cls(price=level.price, size=level.size)


class NormalizedBook(BaseModel):
    """Normalized book payload exposed by the CLI and CLOB adapter."""

    token_id: str
    bids: list[NormalizedBookLevel] = Field(default_factory=list)
    asks: list[NormalizedBookLevel] = Field(default_factory=list)
    tick_size: str | None = None
    min_order_size: str | None = None

    @classmethod
    def from_wire(cls, book: ClobBookWire) -> Self:
        """Normalize a raw CLOB book payload."""
        return cls(
            token_id=book.token_id,
            bids=[NormalizedBookLevel.from_wire(level) for level in book.bids],
            asks=[NormalizedBookLevel.from_wire(level) for level in book.asks],
            tick_size=book.tick_size,
            min_order_size=book.min_order_size,
        )


class NormalizedPriceQuote(BaseModel):
    """Normalized BUY and SELL quote summary for a token."""

    token_id: str
    buy_price: str | None = None
    sell_price: str | None = None
