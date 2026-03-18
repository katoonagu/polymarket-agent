<<<<<<< HEAD
"""Public read-only CLOB client for books, prices, midpoint, and spread."""
=======
"""Read-only public CLOB client."""
>>>>>>> feat/02a-python-scaffold

from __future__ import annotations

import os
<<<<<<< HEAD
from typing import Any, Self
=======
from collections.abc import Mapping
from typing import Any
>>>>>>> feat/02a-python-scaffold

import httpx

from pm import __version__
<<<<<<< HEAD
from pm.market.exceptions import ClobClientError, ClobNotFoundError
from pm.market.models import (
    ClobBookWire,
    NormalizedBook,
=======
from pm.market.models import (
    NormalizedBook,
    NormalizedBookLevel,
>>>>>>> feat/02a-python-scaffold
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

DEFAULT_CLOB_URL = "https://clob.polymarket.com"
<<<<<<< HEAD
DEFAULT_TIMEOUT_SECONDS = 10.0


class ClobClient:
    """Sync public client for read-only CLOB market data."""
=======
DEFAULT_TIMEOUT = 10.0
QueryValue = str | int | float | bool | None
QueryMapping = dict[str, QueryValue]


class ClobClientError(RuntimeError):
    """Raised when the public CLOB API returns an unexpected response."""


class ClobNotFoundError(ClobClientError):
    """Raised when a token lookup returns 404 or an empty payload."""


class ClobClient:
    """Small sync client for the public CLOB API."""
>>>>>>> feat/02a-python-scaffold

    def __init__(
        self,
        *,
        base_url: str | None = None,
<<<<<<< HEAD
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
=======
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=(base_url or os.getenv("POLYMARKET_CLOB_URL") or DEFAULT_CLOB_URL).rstrip("/"),
>>>>>>> feat/02a-python-scaffold
            timeout=timeout,
            headers={"User-Agent": f"polymarket-agent/{__version__}"},
        )

<<<<<<< HEAD
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP client."""
=======
    def __enter__(self) -> ClobClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
>>>>>>> feat/02a-python-scaffold
        if self._owns_client:
            self._client.close()

    def get_book(self, token_id: str) -> NormalizedBook:
<<<<<<< HEAD
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
=======
        """Fetch a public order book for a token ID."""
        payload = self._get_json(
            "/book",
            params={"token_id": token_id},
            resource="token",
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
            resource="token",
            identifier=token_id,
        )
        if not isinstance(payload, dict) or token_id not in payload:
            raise ClobNotFoundError(f"token '{token_id}' was not found.")

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
            resource="token",
            identifier=token_id,
        )
        if not isinstance(payload, dict):
            raise ClobClientError("CLOB midpoint response was not an object.")

        midpoint = _string_or_none(payload.get("mid")) or _string_or_none(payload.get("mid_price"))
        if midpoint is None:
            raise ClobClientError("CLOB midpoint response did not include a midpoint value.")

>>>>>>> feat/02a-python-scaffold
        return NormalizedMidpointQuote(token_id=token_id, midpoint=midpoint)

    def get_spread(self, token_id: str) -> NormalizedSpreadQuote:
        """Fetch the public spread for a token ID."""
<<<<<<< HEAD
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
=======
        payload = self._get_json(
            "/spread",
            params={"token_id": token_id},
            resource="token",
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
        resource: str | None = None,
        identifier: str | None = None,
    ) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ClobClientError("CLOB request failed.") from exc

        return _decode_json_response(
            response,
            resource=resource,
            identifier=identifier,
        )

    def _post_json(
        self,
        path: str,
        *,
        body: list[dict[str, str]],
        resource: str | None = None,
        identifier: str | None = None,
    ) -> Any:
        try:
            response = self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise ClobClientError("CLOB request failed.") from exc

        return _decode_json_response(
            response,
            resource=resource,
            identifier=identifier,
        )


def _decode_json_response(
    response: httpx.Response,
    *,
    resource: str | None,
    identifier: str | None,
) -> Any:
    if response.status_code == 404 and resource is not None and identifier is not None:
        raise ClobNotFoundError(f"{resource} '{identifier}' was not found.")

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
    return None


def _string_or_default(value: Any, default: str) -> str:
    return _string_or_none(value) or default
>>>>>>> feat/02a-python-scaffold
