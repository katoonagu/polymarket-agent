"""Optional live CLOB smoke test."""

from __future__ import annotations

import os

import pytest

from pm.market import ClobClient, GammaClient

pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_CLOB_SMOKE") != "1",
    reason="Set PM_RUN_CLOB_SMOKE=1 to run the live CLOB smoke test.",
)


def test_clob_smoke_round_trip() -> None:
    with GammaClient() as gamma_client:
        markets = gamma_client.list_active_markets(limit=1)

    assert markets
    assert markets[0].token_ids

    token_id = markets[0].token_ids[0]

    with ClobClient() as clob_client:
        book = clob_client.get_book(token_id)
        prices = clob_client.get_prices(token_id)
        midpoint = clob_client.get_midpoint(token_id)
        spread = clob_client.get_spread(token_id)

    assert book.token_id == token_id
    assert prices.token_id == token_id
    assert midpoint.token_id == token_id
    assert spread.token_id == token_id
