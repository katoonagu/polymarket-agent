"""High-level helpers for public Binance liquidity sampling."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from math import sqrt
from typing import TypeVar

from pm.binance.client import (
    BinanceClient,
    BinanceClientError,
    BinanceValidationError,
    parse_depth_levels,
    string_or_none,
    validate_symbol,
)
from pm.binance.models import (
    BinanceBookTicker,
    BinanceDepthLevel,
    BinanceDepthSnapshot,
    BinanceKline,
    BinanceLiquiditySnapshot,
    BinanceSectionError,
)

NEAR_TOUCH_BPS = Decimal("5")
T = TypeVar("T")


class BinanceService:
    """Compose public Binance endpoints into deterministic liquidity snapshots."""

    def __init__(
        self,
        *,
        client_cls: type[BinanceClient] = BinanceClient,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._client_cls = client_cls
        self._now = now or _utc_now

    def sample_liquidity(
        self,
        symbol: str = "BTCUSDT",
        *,
        depth_limit: int = 20,
        kline_interval: str = "1m",
        kline_limit: int = 4,
    ) -> BinanceLiquiditySnapshot:
        """Build one public Binance liquidity snapshot."""
        normalized_symbol = validate_symbol(symbol)
        errors: list[BinanceSectionError] = []
        sampled_at = _isoformat(self._now())

        with self._client_cls() as client:
            book_ticker_payload = self._capture_section(
                section="book_ticker",
                errors=errors,
                operation=lambda: client.get_book_ticker(normalized_symbol),
            )
            depth_payload = self._capture_section(
                section="depth",
                errors=errors,
                operation=lambda: client.get_depth(normalized_symbol, limit=depth_limit),
            )
            kline_payload = self._capture_section(
                section="klines",
                errors=errors,
                operation=lambda: client.get_klines(
                    normalized_symbol,
                    interval=kline_interval,
                    limit=kline_limit,
                ),
            )

        if book_ticker_payload is None:
            raise BinanceClientError("Could not fetch Binance bookTicker data.")

        book_ticker = _normalize_book_ticker(normalized_symbol, book_ticker_payload)
        depth = _normalize_depth(normalized_symbol, depth_payload or {})
        klines = _normalize_klines(normalized_symbol, kline_interval, kline_payload or [])
        realized_vol_1m_bps = _realized_vol_1m_bps(klines)
        realized_vol_3m_bps = _realized_vol_3m_bps(klines)
        near_touch_bid_depth, near_touch_ask_depth = _near_touch_depth(depth)

        return BinanceLiquiditySnapshot(
            symbol=normalized_symbol,
            sampled_at=sampled_at,
            book_ticker=book_ticker,
            depth=depth,
            klines=klines,
            realized_vol_1m_bps=realized_vol_1m_bps,
            realized_vol_3m_bps=realized_vol_3m_bps,
            near_touch_bid_depth=near_touch_bid_depth,
            near_touch_ask_depth=near_touch_ask_depth,
            errors=errors,
        )

    def _capture_section(
        self,
        *,
        section: str,
        errors: list[BinanceSectionError],
        operation: Callable[[], T],
    ) -> T | None:
        try:
            return operation()
        except (BinanceClientError, BinanceValidationError) as exc:
            code = (
                "invalid_argument" if isinstance(exc, BinanceValidationError) else "request_failed"
            )
            errors.append(BinanceSectionError(section=section, code=code, message=str(exc)))
            return None


def _normalize_book_ticker(symbol: str, payload: dict[str, object]) -> BinanceBookTicker:
    bid_price = string_or_none(payload.get("bidPrice"))
    bid_quantity = string_or_none(payload.get("bidQty"))
    ask_price = string_or_none(payload.get("askPrice"))
    ask_quantity = string_or_none(payload.get("askQty"))
    if bid_price is None or bid_quantity is None or ask_price is None or ask_quantity is None:
        raise BinanceClientError("Binance bookTicker payload was incomplete.")

    bid_decimal = _decimal(bid_price)
    ask_decimal = _decimal(ask_price)
    midpoint = (bid_decimal + ask_decimal) / Decimal("2")
    spread = ask_decimal - bid_decimal
    return BinanceBookTicker(
        symbol=symbol,
        bid_price=bid_price,
        bid_quantity=bid_quantity,
        ask_price=ask_price,
        ask_quantity=ask_quantity,
        midpoint=_decimal_text(midpoint),
        spread=_decimal_text(spread),
    )


def _normalize_depth(symbol: str, payload: dict[str, object]) -> BinanceDepthSnapshot:
    bids = [
        BinanceDepthLevel(price=price, quantity=quantity)
        for price, quantity in parse_depth_levels(payload.get("bids"))
    ]
    asks = [
        BinanceDepthLevel(price=price, quantity=quantity)
        for price, quantity in parse_depth_levels(payload.get("asks"))
    ]
    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    midpoint: str | None = None
    spread: str | None = None
    if best_bid is not None and best_ask is not None:
        bid_decimal = _decimal(best_bid)
        ask_decimal = _decimal(best_ask)
        midpoint = _decimal_text((bid_decimal + ask_decimal) / Decimal("2"))
        spread = _decimal_text(ask_decimal - bid_decimal)
    last_update_id = payload.get("lastUpdateId")
    if not isinstance(last_update_id, int):
        last_update_id = 0
    return BinanceDepthSnapshot(
        symbol=symbol,
        last_update_id=last_update_id,
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=midpoint,
        spread=spread,
    )


def _normalize_klines(
    symbol: str, interval: str, payload: list[list[object]]
) -> list[BinanceKline]:
    items: list[BinanceKline] = []
    for row in payload:
        if len(row) < 9:
            continue
        open_time = _int_or_none(row[0])
        open_price = string_or_none(row[1])
        high_price = string_or_none(row[2])
        low_price = string_or_none(row[3])
        close_price = string_or_none(row[4])
        volume = string_or_none(row[5])
        close_time = _int_or_none(row[6])
        quote_volume = string_or_none(row[7])
        trade_count = _int_or_none(row[8])
        if (
            open_time is None
            or close_time is None
            or open_price is None
            or high_price is None
            or low_price is None
            or close_price is None
            or volume is None
            or quote_volume is None
            or trade_count is None
        ):
            continue
        items.append(
            BinanceKline(
                symbol=symbol,
                interval=interval,
                open_time=open_time,
                close_time=close_time,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                quote_volume=quote_volume,
                trade_count=trade_count,
                is_closed=True,
            )
        )
    return items


def _near_touch_depth(depth: BinanceDepthSnapshot) -> tuple[str, str]:
    if depth.midpoint is None:
        return "0", "0"

    midpoint = _decimal(depth.midpoint)
    window = midpoint * (NEAR_TOUCH_BPS / Decimal("10000"))
    lower_bound = midpoint - window
    upper_bound = midpoint + window

    bid_total = Decimal("0")
    for level in depth.bids:
        try:
            price = _decimal(level.price)
            quantity = _decimal(level.quantity)
        except InvalidOperation:
            continue
        if price >= lower_bound:
            bid_total += quantity

    ask_total = Decimal("0")
    for level in depth.asks:
        try:
            price = _decimal(level.price)
            quantity = _decimal(level.quantity)
        except InvalidOperation:
            continue
        if price <= upper_bound:
            ask_total += quantity

    return _decimal_text(bid_total), _decimal_text(ask_total)


def _realized_vol_1m_bps(klines: list[BinanceKline]) -> str | None:
    if not klines:
        return None
    latest = klines[-1]
    try:
        open_price = float(latest.open_price)
        close_price = float(latest.close_price)
    except ValueError:
        return None
    if open_price <= 0 or close_price <= 0:
        return None
    import math

    value = abs(math.log(close_price / open_price)) * 10000
    return _float_text(value)


def _realized_vol_3m_bps(klines: list[BinanceKline]) -> str | None:
    if len(klines) < 3:
        return None
    import math

    latest = klines[-3:]
    returns: list[float] = []
    previous_close: float | None = None
    for item in latest:
        try:
            open_price = float(item.open_price)
            close_price = float(item.close_price)
        except ValueError:
            return None
        if open_price <= 0 or close_price <= 0:
            return None
        base_price = previous_close if previous_close is not None else open_price
        if base_price <= 0:
            return None
        returns.append(math.log(close_price / base_price))
        previous_close = close_price
    value = sqrt(sum(component * component for component in returns)) * 10000
    return _float_text(value)


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _decimal(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _float_text(value: float) -> str:
    return _decimal_text(Decimal(str(value)))


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)
