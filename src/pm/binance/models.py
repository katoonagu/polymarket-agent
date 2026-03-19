"""Normalized public Binance market-data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BinanceSectionError(BaseModel):
    """Partial Binance sampling failure detail."""

    section: str
    code: str
    message: str


class BinanceDepthLevel(BaseModel):
    """One normalized Binance depth level."""

    price: str
    quantity: str


class BinanceBookTicker(BaseModel):
    """Normalized Binance top-of-book snapshot."""

    symbol: str
    bid_price: str
    bid_quantity: str
    ask_price: str
    ask_quantity: str
    midpoint: str
    spread: str


class BinanceDepthSnapshot(BaseModel):
    """Normalized Binance depth response."""

    symbol: str
    last_update_id: int
    bids: list[BinanceDepthLevel] = Field(default_factory=list)
    asks: list[BinanceDepthLevel] = Field(default_factory=list)
    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None


class BinanceKline(BaseModel):
    """Normalized Binance kline row."""

    symbol: str
    interval: str
    open_time: int
    close_time: int
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: str
    quote_volume: str
    trade_count: int
    is_closed: bool


class BinanceLiquiditySnapshot(BaseModel):
    """Derived Binance liquidity and realized-volatility snapshot."""

    symbol: str
    sampled_at: str
    book_ticker: BinanceBookTicker
    depth: BinanceDepthSnapshot
    klines: list[BinanceKline] = Field(default_factory=list)
    realized_vol_1m_bps: str | None = None
    realized_vol_3m_bps: str | None = None
    near_touch_bid_depth: str = "0"
    near_touch_ask_depth: str = "0"
    errors: list[BinanceSectionError] = Field(default_factory=list)
