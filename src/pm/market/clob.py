"""Public read-only CLOB client for books, prices, midpoint, and spread."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from pm import __version__
from pm.market.exceptions import ClobClientError, ClobNotFoundError
from pm.market.models import (
    NormalizedBook,
    NormalizedBookLevel,
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

DEFAULT_CLOB_URL = "https://clob.polymarket.com"
DEFAULT_TIMEOUT = 10.0
QueryValue = str | int | float | bool | None
QueryMapping = dict[str, QueryValue]


class ClobClient:
    """Small sync client for the public CLOB API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=(base_url or os.getenv("POLYMARKET_CLOB_URL") or DEFAULT_CLOB_URL).rstrip(
                "/"
            ),
            timeout=timeout,
            headers={"User-Agent": f"polymarket-agent/{__version__}"},
        )

    def __enter__(self) -> ClobClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_client:
            self._client.close()

    def get_book(self, token_id: str) -> NormalizedBook:
        """Fetch a public order book for a token ID."""
        payload = self._get_json(
            "/book",
            params={"token_id": token_id},
            resource="book",
            identifier=token_id,
        )
        if not isinstance(payload, dict):
            raise ClobClientError("CLOB book response was not an object.")

        return NormalizedBook(
            token_id=_string_or_default(payload.get("asset_id"), token_id),
            bids=_parse_book_levels(payload.get("bids")),
            asks=_parse_book_levels(payload.get("asks")),
            tick_size=_string_or_none(payload.get("tick_size")),
            min_order_size=_string_or_none(payload.get("min_order_size")),
        )

    def get_prices(self, token_id: str) -> NormalizedPriceQuote:
        """Fetch public buy and sell prices for a token ID."""
        payload = self._post_json(
            "/prices",
            body=[
                {"token_id": token_id, "side": "BUY"},
                {"token_id": token_id, "side": "SELL"},
            ],
            resource="price",
            identifier=token_id,
        )
        if not isinstance(payload, dict) or token_id not in payload:
            raise ClobNotFoundError(resource="price", identifier=token_id)

        token_payload = payload[token_id]
        if not isinstance(token_payload, dict):
            raise ClobClientError("CLOB price response was not an object.")

        return NormalizedPriceQuote(
            token_id=token_id,
            buy_price=_string_or_none(token_payload.get("BUY")),
            sell_price=_string_or_none(token_payload.get("SELL")),
        )

    def get_midpoint(self, token_id: str) -> NormalizedMidpointQuote:
        """Fetch the public midpoint price for a token ID."""
        payload = self._get_json(
            "/midpoint",
            params={"token_id": token_id},
            resource="midpoint",
            identifier=token_id,
        )
        if not isinstance(payload, dict):
            raise ClobClientError("CLOB midpoint response was not an object.")

        midpoint = _string_or_none(payload.get("mid")) or _string_or_none(payload.get("mid_price"))
        if midpoint is None:
            raise ClobClientError("CLOB midpoint response did not include a midpoint value.")

        return NormalizedMidpointQuote(token_id=token_id, midpoint=midpoint)

    def get_spread(self, token_id: str) -> NormalizedSpreadQuote:
        """Fetch the public spread for a token ID."""
        payload = self._get_json(
            "/spread",
            params={"token_id": token_id},
            resource="spread",
            identifier=token_id,
        )
        if not isinstance(payload, dict):
            raise ClobClientError("CLOB spread response was not an object.")

        spread = _string_or_none(payload.get("spread"))
        if spread is None:
            raise ClobClientError("CLOB spread response did not include a spread value.")

        return NormalizedSpreadQuote(token_id=token_id, spread=spread)

    def _get_json(
        self,
        path: str,
        *,
        params: QueryMapping | None = None,
        resource: str,
        identifier: str,
    ) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ClobClientError("CLOB request failed.") from exc

        return _decode_json_response(response, resource=resource, identifier=identifier)

    def _post_json(
        self,
        path: str,
        *,
        body: list[dict[str, str]],
        resource: str,
        identifier: str,
    ) -> Any:
        try:
            response = self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise ClobClientError("CLOB request failed.") from exc

        return _decode_json_response(response, resource=resource, identifier=identifier)


def _decode_json_response(
    response: httpx.Response,
    *,
    resource: str,
    identifier: str,
) -> Any:
    if response.status_code == 404:
        raise ClobNotFoundError(resource=resource, identifier=identifier)

    if response.status_code >= 400:
        raise ClobClientError(
            "CLOB request failed with status "
            f"{response.status_code} for {response.request.url.path}."
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ClobClientError("CLOB response body was not valid JSON.") from exc


def _parse_book_levels(value: Any) -> list[NormalizedBookLevel]:
    if not isinstance(value, list):
        return []

    levels: list[NormalizedBookLevel] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        price = _string_or_none(item.get("price"))
        size = _string_or_none(item.get("size"))
        if price is None or size is None:
            continue
        levels.append(NormalizedBookLevel(price=price, size=size))
    return levels


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _string_or_default(value: Any, default: str) -> str:
    return _string_or_none(value) or default
