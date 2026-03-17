"""Unit tests for the initial market service scaffold."""

from __future__ import annotations

from pm.market import MarketSearchResponse, search_markets


def test_search_markets_returns_deterministic_empty_response() -> None:
    result = search_markets("  btc  ")

    assert result == MarketSearchResponse(
        query="btc",
        results=[],
        total=0,
    )
