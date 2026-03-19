"""Env-gated public smoke tests for the BTC15m research strategy surface."""

from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from pm.cli.app import app

pytest.importorskip("websockets")

RUN_SMOKE = os.getenv("PM_RUN_BTC15M_STRATEGY_SMOKE") == "1"
runner = CliRunner()


@pytest.mark.skipif(not RUN_SMOKE, reason="set PM_RUN_BTC15M_STRATEGY_SMOKE=1")
def test_btc15m_record_start_and_report_smoke(tmp_path) -> None:
    env = os.environ.copy()
    env["PM_STRATEGY_STATE_DIR"] = str(tmp_path)

    record_result = runner.invoke(
        app,
        ["strategy", "btc15m", "record", "start", "--seconds", "10", "--json"],
        env=env,
    )
    assert record_result.exit_code == 0
    record_payload = json.loads(record_result.stdout)
    assert record_payload["total"] >= 1
    first = record_payload["items"][0]
    assert len(first["chainlink_ticks"]) >= 1
    assert len(first["binance_ticks"]) >= 1
    assert len(first["market_samples"]) >= 1

    report_result = runner.invoke(app, ["strategy", "btc15m", "report", "--json"], env=env)
    assert report_result.exit_code == 0
    report_payload = json.loads(report_result.stdout)
    assert report_payload["summary"]["recorded_window_count"] >= 1
