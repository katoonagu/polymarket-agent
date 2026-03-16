"""Optional live Gamma smoke test."""

from __future__ import annotations

import os

import pytest

from pm.market import GammaClient

pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_GAMMA_SMOKE") != "1",
    reason="Set PM_RUN_GAMMA_SMOKE=1 to run the live Gamma smoke test.",
)


def test_gamma_smoke_round_trip() -> None:
    with GammaClient() as client:
        markets = client.list_active_markets(limit=1)

        assert markets

        market = client.get_market_by_slug(markets[0].market_slug)

        assert market.market_slug == markets[0].market_slug

        if market.event_slug is not None:
            event = client.get_event_by_slug(market.event_slug)
            assert event.event_slug == market.event_slug
