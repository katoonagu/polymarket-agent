"""Optional live smoke test for the public CLOB adapter."""

from __future__ import annotations

import os

import pytest

from pm.market import ClobClient, ClobClientError, ClobNotFoundError, GammaClient
from pm.market.models import NormalizedMarket

pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_CLOB_SMOKE") != "1",
    reason="Set PM_RUN_CLOB_SMOKE=1 to run live CLOB smoke tests.",
)


def test_clob_smoke_reads_public_token_data() -> None:
    with GammaClient() as gamma_client:
        search_result = gamma_client.search_markets("bitcoin", limit=10)

        if not search_result.results:
            pytest.skip("Gamma search returned no markets for the smoke query.")

        candidates = sorted(
            [market for market in search_result.results if market.token_ids],
            key=_market_priority_key,
        )
        if not candidates:
            pytest.skip("Gamma search returned no active orderbook candidates with token IDs.")

    missing_candidates: list[str] = []
    unexpected_errors: list[str] = []

    with ClobClient() as clob_client:
        for market in candidates:
            for token_id in market.token_ids:
                try:
                    book = clob_client.get_book(token_id)
                    prices = clob_client.get_prices(token_id)
                    midpoint = clob_client.get_midpoint(token_id)
                    spread = clob_client.get_spread(token_id)
                except ClobNotFoundError as exc:
                    missing_candidates.append(
                        f"{market.market_slug}:{token_id} ({exc.resource})"
                    )
                    continue
                except ClobClientError as exc:
                    unexpected_errors.append(f"{market.market_slug}:{token_id} ({exc})")
                    continue
                else:
                    assert book.token_id == token_id
                    assert prices.token_id == token_id
                    assert midpoint.token_id == token_id
                    assert spread.token_id == token_id
                    return

    if unexpected_errors:
        pytest.fail(
            "CLOB smoke exhausted fallback candidates after unexpected public CLOB errors: "
            + "; ".join(unexpected_errors[:5])
        )

    pytest.skip(
        "No usable public orderbook token found among discovered candidates. "
        + ("Tried: " + "; ".join(missing_candidates[:5]) if missing_candidates else "")
    )


def _market_priority_key(market: NormalizedMarket) -> tuple[int, int, int, str]:
    """Prefer active, open, orderbook-enabled markets while keeping ordering deterministic."""
    return (
        0 if market.active else 1,
        0 if not market.closed else 1,
        0 if market.enable_order_book else 1,
        market.market_slug,
    )
