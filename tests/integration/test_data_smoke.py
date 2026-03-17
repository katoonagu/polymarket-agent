"""Optional live smoke test for the public Polymarket Data API adapter."""

from __future__ import annotations

import os

import pytest

from pm.data import DataClient
from pm.market import GammaClient

pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_DATA_SMOKE") != "1",
    reason="Set PM_RUN_DATA_SMOKE=1 to run live Data API smoke tests.",
)


def test_data_smoke_reads_public_user_and_market_data() -> None:
    user = os.getenv("PM_DATA_SMOKE_USER")
    if not user:
        pytest.skip("Set PM_DATA_SMOKE_USER to run user-scoped Data API smoke tests.")

    with GammaClient() as gamma_client:
        search_result = gamma_client.search_markets("bitcoin", limit=1)

        if not search_result.results:
            pytest.skip("Gamma search returned no markets for the smoke query.")

        market = search_result.results[0]
        market_ref = market.condition_id or market.market_slug
        if not market_ref:
            pytest.skip("Gamma market did not include a slug or condition ID.")

    with DataClient() as data_client:
        trades = data_client.get_user_trades(user, limit=1)
        activity = data_client.get_user_activity(user, limit=1)
        positions = data_client.get_current_positions(user)
        closed_positions = data_client.get_closed_positions(user)
        value = data_client.get_holdings_value(user)
        traded = data_client.get_traded_count(user)
        holders = data_client.get_holders(market_ref, limit=1)
        open_interest = data_client.get_open_interest(market_ref)

    assert trades.user == user
    assert activity.user == user
    assert positions.user == user
    assert closed_positions.user == user
    assert value.user == user
    assert traded.user == user
    assert holders.condition_id
    assert open_interest.condition_id
