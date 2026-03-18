"""Optional live smoke test for the public CLOB adapter."""

from __future__ import annotations

import os

import pytest

from pm.market import ClobClient, GammaClient

pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_CLOB_SMOKE") != "1",
    reason="Set PM_RUN_CLOB_SMOKE=1 to run live CLOB smoke tests.",
)


def test_clob_smoke_reads_public_token_data() -> None:
    with GammaClient() as gamma_client:
        search_result = gamma_client.search_markets("bitcoin", limit=1)

        if not search_result.results:
            pytest.skip("Gamma search returned no markets for the smoke query.")

        token_ids = search_result.results[0].token_ids
        if not token_ids:
            pytest.skip("Gamma market did not include token IDs.")

    token_id = token_ids[0]

    with ClobClient() as clob_client:
        book = clob_client.get_book(token_id)
        prices = clob_client.get_prices(token_id)
        midpoint = clob_client.get_midpoint(token_id)
        spread = clob_client.get_spread(token_id)

    assert book.token_id == token_id
    assert prices.token_id == token_id
    assert midpoint.token_id == token_id
    assert spread.token_id == token_id
