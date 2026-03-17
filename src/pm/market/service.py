"""Read-only market service scaffold."""

from __future__ import annotations

from pm.market.models import MarketSearchResponse


def search_markets(query: str) -> MarketSearchResponse:
    """Return a deterministic empty response until live market discovery is added."""
    normalized_query = query.strip()
    return MarketSearchResponse(query=normalized_query, results=[], total=0)
