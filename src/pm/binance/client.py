"""Public read-only Binance market-data client."""

from __future__ import annotations

from typing import Any

import httpx

from pm import __version__

DEFAULT_BINANCE_URL = "https://api.binance.com/api/v3"
DEFAULT_TIMEOUT = 10.0
QueryValue = str | int | float | bool | None
QueryMapping = dict[str, QueryValue]
SUPPORTED_KLINE_INTERVALS = {"1m"}


class BinanceClientError(RuntimeError):
    """Raised when Binance returns an unexpected response."""


class BinanceValidationError(BinanceClientError):
    """Raised when Binance CLI-facing arguments fail validation."""


class BinanceClient:
    """Small sync client for public Binance market-data endpoints."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BINANCE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"User-Agent": f"polymarket-agent/{__version__}"},
        )

    def __enter__(self) -> BinanceClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_client:
            self._client.close()

    def get_book_ticker(self, symbol: str) -> dict[str, Any]:
        """Fetch the best bid and ask for one symbol."""
        normalized_symbol = validate_symbol(symbol)
        payload = self._get_json("/ticker/bookTicker", params={"symbol": normalized_symbol})
        if not isinstance(payload, dict):
            raise BinanceClientError("Binance bookTicker response was not an object.")
        return payload

    def get_depth(self, symbol: str, *, limit: int = 20) -> dict[str, Any]:
        """Fetch public depth for one symbol."""
        normalized_symbol = validate_symbol(symbol)
        normalized_limit = validate_depth_limit(limit)
        payload = self._get_json(
            "/depth",
            params={"symbol": normalized_symbol, "limit": normalized_limit},
        )
        if not isinstance(payload, dict):
            raise BinanceClientError("Binance depth response was not an object.")
        return payload

    def get_klines(
        self,
        symbol: str,
        *,
        interval: str = "1m",
        limit: int = 4,
    ) -> list[list[Any]]:
        """Fetch public klines for one symbol."""
        normalized_symbol = validate_symbol(symbol)
        normalized_interval = validate_kline_interval(interval)
        normalized_limit = validate_kline_limit(limit)
        payload = self._get_json(
            "/klines",
            params={
                "symbol": normalized_symbol,
                "interval": normalized_interval,
                "limit": normalized_limit,
            },
        )
        if not isinstance(payload, list):
            raise BinanceClientError("Binance kline response was not a list.")
        return [item for item in payload if isinstance(item, list)]

    def _get_json(self, path: str, *, params: QueryMapping | None = None) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise BinanceClientError("Binance request failed.") from exc

        if response.status_code >= 400:
            raise BinanceClientError(
                "Binance request failed with status "
                f"{response.status_code} for {response.request.url.path}."
            )

        try:
            return response.json()
        except ValueError as exc:
            raise BinanceClientError("Binance response body was not valid JSON.") from exc


def validate_symbol(symbol: str) -> str:
    """Validate and normalize a Binance symbol."""
    normalized = symbol.strip().upper().replace("-", "").replace("_", "").replace("/", "")
    if not normalized:
        raise BinanceValidationError("Symbol is required.")
    return normalized


def validate_depth_limit(limit: int) -> int:
    """Validate a Binance depth limit."""
    if limit <= 0:
        raise BinanceValidationError("Depth limit must be greater than zero.")
    if limit > 100:
        raise BinanceValidationError("Depth limit must be at most 100.")
    return limit


def validate_kline_interval(interval: str) -> str:
    """Validate a supported Binance kline interval."""
    normalized = interval.strip()
    if normalized not in SUPPORTED_KLINE_INTERVALS:
        raise BinanceValidationError("Kline interval must be 1m.")
    return normalized


def validate_kline_limit(limit: int) -> int:
    """Validate a Binance kline limit."""
    if limit <= 0:
        raise BinanceValidationError("Kline limit must be greater than zero.")
    if limit > 500:
        raise BinanceValidationError("Kline limit must be at most 500.")
    return limit


def string_or_none(value: Any) -> str | None:
    """Coerce a Binance value to string when possible."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def parse_depth_levels(value: Any) -> list[tuple[str, str]]:
    """Parse Binance depth levels into string tuples."""
    if not isinstance(value, list):
        return []

    levels: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) < 2:
            continue
        price = string_or_none(item[0])
        quantity = string_or_none(item[1])
        if price is None or quantity is None:
            continue
        levels.append((price, quantity))
    return levels
