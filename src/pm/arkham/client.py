"""Minimal Arkham REST client for documented enrichment endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from pm.arkham.exceptions import ArkhamClientError, ArkhamNotFoundError

DEFAULT_BASE_URL = "https://api.arkm.com"
DEFAULT_TIMEOUT = 10.0


class ArkhamClient:
    """Small wrapper around documented Arkham REST endpoints."""

    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._owns_http_client = http_client is None
        self._headers = {"API-Key": api_key}
        self._http_client = http_client or httpx.Client(
            base_url=base_url,
            timeout=DEFAULT_TIMEOUT,
            headers=self._headers,
        )

    def __enter__(self) -> ArkhamClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http_client:
            self._http_client.close()

    def get_chains(self) -> Any:
        """Fetch the documented chain list."""
        return self._request_json("GET", "/chains")

    def get_address_intelligence(self, address: str) -> dict[str, Any]:
        """Fetch basic address intelligence."""
        return self._request_json("GET", f"/intelligence/address/{address}")

    def get_address_enriched(self, address: str) -> dict[str, Any]:
        """Fetch enriched address intelligence."""
        return self._request_json("GET", f"/intelligence/address_enriched/{address}")

    def get_entity_intelligence(self, entity_id: str) -> dict[str, Any]:
        """Fetch intelligence for one entity id."""
        return self._request_json("GET", f"/intelligence/entity/{entity_id}")

    def get_counterparties(
        self,
        address: str,
        *,
        limit: int = 10,
        time_last: str = "30d",
    ) -> dict[str, Any]:
        """Fetch top address counterparties with stable defaults."""
        return self._request_json(
            "GET",
            f"/counterparties/address/{address}",
            params={"limit": str(limit), "timeLast": time_last},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        try:
            response = self._http_client.request(
                method,
                path,
                params=params,
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise ArkhamClientError(f"Arkham request failed for '{path}'.") from exc

        if response.status_code == 404:
            raise ArkhamNotFoundError(f"Arkham resource was not found for '{path}'.")
        if response.status_code >= 400:
            raise ArkhamClientError(
                f"Arkham request failed for '{path}' with status {response.status_code}."
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ArkhamClientError(
                f"Arkham returned invalid JSON for '{path}'."
            ) from exc
