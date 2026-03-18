"""Env-gated live smoke test for the public market websocket."""

from __future__ import annotations

import os

import pytest

from pm.stream import StreamService

pytest.importorskip("websockets")

RUN_SMOKE = os.getenv("PM_RUN_STREAM_SMOKE") == "1"
TOKEN_ID = os.getenv("PM_STREAM_SMOKE_TOKEN_ID")


@pytest.mark.skipif(
    not RUN_SMOKE or not TOKEN_ID,
    reason="set PM_RUN_STREAM_SMOKE=1 and PM_STREAM_SMOKE_TOKEN_ID",
)
def test_market_stream_smoke() -> None:
    result = StreamService().stream_market(TOKEN_ID or "", seconds=2, max_events=2)

    assert result.session.requested_seconds == 2
    assert result.summary.token_id == TOKEN_ID
