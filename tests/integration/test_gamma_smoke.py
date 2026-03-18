"""Optional live smoke test for the public Gamma adapter."""

from __future__ import annotations

import os

import pytest

from pm.market import GammaClient

pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_GAMMA_SMOKE") != "1",
    reason="Set PM_RUN_GAMMA_SMOKE=1 to run live Gamma smoke tests.",
)


def test_gamma_smoke_search_show_and_event() -> None:
    with GammaClient() as client:
        search_result = client.search_markets("bitcoin", limit=1)

        if not search_result.results:
            pytest.skip("Gamma search returned no markets for the smoke query.")

        market_slug = search_result.results[0].market_slug
        market = client.get_market_by_slug(market_slug)

        assert market.market_slug == market_slug

        if market.event_slug:
            event = client.get_event_by_slug(market.event_slug)
            assert event.event_slug == market.event_slug
