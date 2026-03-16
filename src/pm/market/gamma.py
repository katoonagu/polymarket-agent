"""Read-only Gamma REST client for market discovery."""

from __future__ import annotations

import os
from typing import Any, Self

import httpx

from pm import __version__
from pm.market.exceptions import GammaClientError, GammaNotFoundError
from pm.market.models import (
    GammaEventWire,
    GammaMarketWire,
    GammaSearchResponseWire,
    NormalizedEvent,
    NormalizedMarket,
)

DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GammaClient:
    """Sync read-only client for the public Gamma API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        resolved_base_url = (
            base_url or os.getenv("POLYMARKET_GAMMA_URL") or DEFAULT_GAMMA_URL
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

    def list_active_markets(self, limit: int, offset: int = 0) -> list[NormalizedMarket]:
        """List active markets from Gamma."""
        payload = self._get_json(
            "/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": limit,
                "offset": offset,
            },
        )
        markets = [GammaMarketWire.model_validate(item) for item in self._expect_list(payload)]
        return [NormalizedMarket.from_wire(market) for market in markets]

    def search_markets(self, query: str, limit: int) -> list[NormalizedMarket]:
        """Search markets via Gamma's public search endpoint."""
        normalized_query = query.strip()
        payload = self._get_json(
            "/public-search",
            params={
                "q": normalized_query,
                "limit_per_type": limit,
                "search_tags": "false",
                "search_profiles": "false",
            },
        )
        search_response = GammaSearchResponseWire.model_validate(payload)
        results: list[NormalizedMarket] = []
        seen_slugs: set[str] = set()

        for event in search_response.events:
            for market in event.markets:
                normalized_market = NormalizedMarket.from_wire(
                    market,
                    event_slug=event.slug,
                    event_title=event.title,
                )
                if normalized_market.market_slug in seen_slugs:
                    continue
                results.append(normalized_market)
                seen_slugs.add(normalized_market.market_slug)
                if len(results) >= limit:
                    return results

        return results

    def get_market_by_slug(self, slug: str) -> NormalizedMarket:
        """Fetch a single market by slug."""
        payload = self._get_json(f"/markets/slug/{slug}", not_found=("market", slug))
        market = GammaMarketWire.model_validate(payload)
        return NormalizedMarket.from_wire(market)

    def get_event_by_slug(self, slug: str) -> NormalizedEvent:
        """Fetch a single event by slug."""
        payload = self._get_json(f"/events/slug/{slug}", not_found=("event", slug))
        event = GammaEventWire.model_validate(payload)
        return NormalizedEvent.from_wire(event)

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        not_found: tuple[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            msg = f"Gamma request failed for '{path}'"
            raise GammaClientError(msg) from exc

        if response.status_code == 404 and not_found is not None:
            raise GammaNotFoundError(resource=not_found[0], identifier=not_found[1])

        if response.is_error:
            msg = f"Gamma request returned status {response.status_code} for '{path}'"
            raise GammaClientError(msg)

        try:
            return response.json()
        except ValueError as exc:
            msg = f"Gamma returned invalid JSON for '{path}'"
            raise GammaClientError(msg) from exc

    def _expect_list(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        msg = "Gamma returned an unexpected payload shape."
        raise GammaClientError(msg)
