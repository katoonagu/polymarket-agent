"""Env-gated live smoke tests for public RTDS crypto feeds."""

from __future__ import annotations

import os

import pytest

from pm.stream import StreamService

pytest.importorskip("websockets")

RUN_SMOKE = os.getenv("PM_RUN_STREAM_SMOKE") == "1"


@pytest.mark.skipif(not RUN_SMOKE, reason="set PM_RUN_STREAM_SMOKE=1")
def test_rtds_binance_smoke() -> None:
    result = StreamService().stream_crypto("BTC", source="binance", seconds=2, max_events=2)

    assert result.summary.symbol == "BTC"
    assert result.summary.source == "binance"


@pytest.mark.skipif(not RUN_SMOKE, reason="set PM_RUN_STREAM_SMOKE=1")
def test_rtds_chainlink_smoke() -> None:
    result = StreamService().stream_crypto("BTC", source="chainlink", seconds=2, max_events=2)

    assert result.summary.symbol == "BTC"
    assert result.summary.source == "chainlink"
