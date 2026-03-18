"""Read-only Gamma client for market discovery."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from pm import __version__
from pm.market.exceptions import GammaClientError, GammaNotFoundError
from pm.market.models import MarketSearchResponse, NormalizedEvent, NormalizedMarket

DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"
DEFAULT_TIMEOUT = 10.0
QueryValue = str | int | float | bool | None
QueryMapping = dict[str, QueryValue]


@dataclass(frozen=True, slots=True)
class GammaSearchCandidate:
    """Internal normalized search candidate with raw timing context."""

    market: NormalizedMarket
    search_index: int
    start_date: str | None = None
    end_date: str | None = None
    resolution_date: str | None = None


class GammaClient:
    """Small sync client for the public Gamma API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=(
                base_url or os.getenv("POLYMARKET_GAMMA_URL") or DEFAULT_GAMMA_URL
            ).rstrip("/"),
            timeout=timeout,
            headers={"User-Agent": f"polymarket-agent/{__version__}"},
        )

    def __enter__(self) -> GammaClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_client:
            self._client.close()

    def search_markets(self, query: str, limit: int) -> MarketSearchResponse:
        """Search Gamma markets by free-text query."""
        normalized_query = query.strip()
        candidates = self.search_market_candidates(normalized_query, limit=limit)
        results = [candidate.market for candidate in candidates]
        return MarketSearchResponse(query=normalized_query, results=results, total=len(results))

    def search_market_candidates(self, query: str, limit: int) -> list[GammaSearchCandidate]:
        """Return normalized search candidates with raw timing context."""
        payload = self._get_json(
            "/public-search",
            params={
                "q": query.strip(),
                "limit_per_type": limit,
                "search_tags": "false",
                "search_profiles": "false",
            },
        )
        events = payload.get("events")
        if not isinstance(events, list):
            raise GammaClientError("Gamma search response did not include an events list.")

        seen: set[str] = set()
        results: list[GammaSearchCandidate] = []
        search_index = 0
        for event_payload in events:
            if not isinstance(event_payload, dict):
                continue
            event_slug = _string_or_none(event_payload.get("slug"))
            event_title = _string_or_none(event_payload.get("title"))
            fallback_start = _first_time_field(event_payload, "startDate", "start_date")
            fallback_end = _first_time_field(event_payload, "endDate", "end_date")
            fallback_resolution = _first_time_field(
                event_payload,
                "resolutionDate",
                "resolution_date",
            )

            for market_payload in _iter_markets(event_payload.get("markets")):
                market = _normalize_market(
                    market_payload,
                    fallback_event_slug=event_slug,
                    fallback_event_title=event_title,
                )
                if market.market_slug in seen:
                    continue

                seen.add(market.market_slug)
                results.append(
                    GammaSearchCandidate(
                        market=market,
                        search_index=search_index,
                        start_date=_first_time_field(
                            market_payload,
                            "startDate",
                            "start_date",
                        )
                        or fallback_start,
                        end_date=_first_time_field(
                            market_payload,
                            "endDate",
                            "end_date",
                        )
                        or fallback_end,
                        resolution_date=_first_time_field(
                            market_payload,
                            "resolutionDate",
                            "resolution_date",
                        )
                        or fallback_resolution,
                    )
                )
                search_index += 1
                if len(results) >= limit:
                    return results

        return results

    def get_market_by_slug(self, slug: str) -> NormalizedMarket:
        """Fetch a single market by slug."""
        payload = self._get_json(
            f"/markets/slug/{slug}",
            resource="market",
            identifier=slug,
        )
        if not isinstance(payload, dict):
            raise GammaClientError("Gamma market response was not an object.")
        return _normalize_market(payload)

    def get_market_by_condition_id(self, condition_id: str) -> NormalizedMarket:
        """Fetch a single market by condition ID."""
        payload = self._get_json(
            "/markets",
            params={"condition_ids": condition_id, "limit": 1},
            resource="market",
            identifier=condition_id,
        )
        if not isinstance(payload, list):
            raise GammaClientError("Gamma market-by-condition response was not a list.")
        if not payload:
            raise GammaNotFoundError(resource="market", identifier=condition_id)
        first_market = payload[0]
        if not isinstance(first_market, dict):
            raise GammaClientError("Gamma market-by-condition response item was not an object.")
        return _normalize_market(first_market)

    def get_event_by_slug(self, slug: str) -> NormalizedEvent:
        """Fetch a single event by slug."""
        payload = self._get_json(
            f"/events/slug/{slug}",
            resource="event",
            identifier=slug,
        )
        if not isinstance(payload, dict):
            raise GammaClientError("Gamma event response was not an object.")
        return _normalize_event(payload)

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
            raise GammaClientError("Gamma request failed.") from exc

        if response.status_code == 404 and resource is not None and identifier is not None:
            raise GammaNotFoundError(resource=resource, identifier=identifier)

        if response.status_code >= 400:
            raise GammaClientError(
                f"Gamma request failed with status {response.status_code} for {path}."
            )

        try:
            return response.json()
        except ValueError as exc:
            raise GammaClientError("Gamma response body was not valid JSON.") from exc


def _normalize_event(payload: dict[str, Any]) -> NormalizedEvent:
    event_slug = _require_string(payload.get("slug"), field_name="event.slug")
    title = _require_string(payload.get("title"), field_name="event.title")

    markets = [
        _normalize_market(
            market_payload,
            fallback_event_slug=event_slug,
            fallback_event_title=title,
        )
        for market_payload in _iter_markets(payload.get("markets"))
    ]

    enable_order_book = payload.get("enableOrderBook")
    if enable_order_book is None:
        enable_order_book = any(market.enable_order_book for market in markets)

    return NormalizedEvent(
        event_slug=event_slug,
        title=title,
        active=_bool_from_value(payload.get("active")),
        closed=_bool_from_value(payload.get("closed")),
        enable_order_book=bool(enable_order_book),
        markets=markets,
    )


def _normalize_market(
    payload: dict[str, Any],
    *,
    fallback_event_slug: str | None = None,
    fallback_event_title: str | None = None,
) -> NormalizedMarket:
    market_slug = _require_string(payload.get("slug"), field_name="market.slug")
    question = _require_string(payload.get("question"), field_name="market.question")

    nested_event_slug, nested_event_title = _extract_event_context(payload.get("events"))

    return NormalizedMarket(
        market_slug=market_slug,
        event_slug=nested_event_slug or fallback_event_slug,
        question=question,
        event_title=nested_event_title or fallback_event_title,
        active=_bool_from_value(payload.get("active")),
        closed=_bool_from_value(payload.get("closed")),
        enable_order_book=_bool_from_value(payload.get("enableOrderBook")),
        condition_id=_string_or_none(payload.get("conditionId")),
        token_ids=_parse_string_list(payload.get("clobTokenIds")),
        outcomes=_parse_string_list(payload.get("outcomes")),
        min_tick=_number_or_none(payload.get("orderPriceMinTickSize")),
        min_order_size=_number_or_none(payload.get("orderMinSize")),
    )


def _extract_event_context(events_payload: Any) -> tuple[str | None, str | None]:
    if not isinstance(events_payload, list) or not events_payload:
        return None, None
    first_event = events_payload[0]
    if not isinstance(first_event, dict):
        return None, None
    return _string_or_none(first_event.get("slug")), _string_or_none(first_event.get("title"))


def _iter_markets(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, list):
        return ()
    return (item for item in value if isinstance(item, dict))


def _parse_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [stripped]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _require_string(value: Any, *, field_name: str) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    raise GammaClientError(f"Gamma response missing required field '{field_name}'.")


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _bool_from_value(value: Any) -> bool:
    return bool(value)


def _first_time_field(payload: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = _string_or_none(payload.get(name))
        if value is not None:
            return value
    return None
