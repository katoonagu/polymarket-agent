"""Public read-only CLOB client for books, prices, midpoint, and spread."""

from __future__ import annotations

import os
from typing import Any, Self

import httpx

from pm import __version__
from pm.market.exceptions import ClobClientError, ClobNotFoundError
from pm.market.models import (
    ClobBookWire,
    NormalizedBook,
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

DEFAULT_CLOB_URL = "https://clob.polymarket.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class ClobClient:
    """Sync public client for read-only CLOB market data."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        resolved_base_url = (
            base_url or os.getenv("POLYMARKET_CLOB_URL") or DEFAULT_CLOB_URL
        ).rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=resolved_base_url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": f"polymarket-agent/{__version__}"},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            self._client.close()

    def get_book(self, token_id: str) -> NormalizedBook:
        """Fetch a public book for a token ID."""
        payload = self._request_json(
            "GET",
            "/book",
            params={"token_id": token_id},
            not_found=("book", token_id),
        )
        book = ClobBookWire.model_validate(payload)
        return NormalizedBook.from_wire(book)

    def get_prices(self, token_id: str) -> NormalizedPriceQuote:
        """Fetch public BUY and SELL prices for a token ID."""
        payload = self._request_json(
            "POST",
            "/prices",
            json=[
                {"token_id": token_id, "side": "BUY"},
                {"token_id": token_id, "side": "SELL"},
            ],
        )
        token_prices = self._extract_prices(payload, token_id)
        return NormalizedPriceQuote(
            token_id=token_id,
            buy_price=token_prices.get("BUY"),
            sell_price=token_prices.get("SELL"),
        )

    def get_midpoint(self, token_id: str) -> NormalizedMidpointQuote:
        """Fetch the public midpoint for a token ID."""
        payload = self._request_json(
            "GET",
            "/midpoint",
            params={"token_id": token_id},
            not_found=("midpoint", token_id),
        )
        midpoint = self._extract_scalar_field(
            payload,
            field_name="mid",
            resource="midpoint",
            token_id=token_id,
        )
        return NormalizedMidpointQuote(token_id=token_id, midpoint=midpoint)

    def get_spread(self, token_id: str) -> NormalizedSpreadQuote:
        """Fetch the public spread for a token ID."""
        payload = self._request_json(
            "GET",
            "/spread",
            params={"token_id": token_id},
            not_found=("spread", token_id),
        )
        spread = self._extract_scalar_field(
            payload,
            field_name="spread",
            resource="spread",
            token_id=token_id,
        )
        return NormalizedSpreadQuote(token_id=token_id, spread=spread)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        not_found: tuple[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            msg = f"CLOB request failed for '{path}'"
            raise ClobClientError(msg) from exc

        if response.status_code == 404 and not_found is not None:
            raise ClobNotFoundError(resource=not_found[0], identifier=not_found[1])

        if response.is_error:
            msg = f"CLOB request returned status {response.status_code} for '{path}'"
            raise ClobClientError(msg)

        try:
            return response.json()
        except ValueError as exc:
            msg = f"CLOB returned invalid JSON for '{path}'"
            raise ClobClientError(msg) from exc

    def _extract_prices(self, payload: Any, token_id: str) -> dict[str, str]:
        if not isinstance(payload, dict):
            msg = "CLOB returned an unexpected price payload shape."
            raise ClobClientError(msg)

        token_payload = payload.get(token_id)
        if not isinstance(token_payload, dict) or not token_payload:
            raise ClobNotFoundError(resource="price", identifier=token_id)

        prices: dict[str, str] = {}
        for side in ("BUY", "SELL"):
            value = token_payload.get(side)
            if value is not None:
                prices[side] = str(value)
        return prices

    def _extract_scalar_field(
        self,
        payload: Any,
        *,
        field_name: str,
        resource: str,
        token_id: str,
    ) -> str:
        if not isinstance(payload, dict):
            msg = f"CLOB returned an unexpected {resource} payload shape."
            raise ClobClientError(msg)

        value = payload.get(field_name)
        if value is None:
            raise ClobNotFoundError(resource=resource, identifier=token_id)

        return str(value)
