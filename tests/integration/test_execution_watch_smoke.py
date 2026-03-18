from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from pm.cli.app import app

runner = CliRunner()


pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_EXEC_WATCH_SMOKE") != "1",
    reason="Set PM_RUN_EXEC_WATCH_SMOKE=1 to run execution watch smoke tests.",
)


def test_execution_watch_smoke_surface() -> None:
    required = ["POLYMARKET_PRIVATE_KEY", "POLYMARKET_SIGNATURE_TYPE"]
    for key in required:
        if not os.getenv(key):
            pytest.skip(f"Missing required env var {key}")

    condition_id = os.getenv("PM_EXEC_WATCH_SMOKE_MARKET", "").strip()
    open_order_id: str | None = None
    if not condition_id:
        open_orders = runner.invoke(app, ["exec", "orders", "open", "--json"])
        if open_orders.exit_code != 0:
            pytest.skip("Could not read authenticated open orders for watch smoke.")
        open_payload = json.loads(open_orders.stdout)
        if open_payload["items"]:
            condition_id = (open_payload["items"][0].get("market") or "").strip()
            open_order_id = open_payload["items"][0].get("order_id")

    if not condition_id:
        pytest.skip(
            "Set PM_EXEC_WATCH_SMOKE_MARKET or ensure at least one live open order exists."
        )

    watch = runner.invoke(
        app,
        [
            "exec",
            "watch",
            "--market",
            condition_id,
            "--seconds",
            "2",
            "--max-events",
            "2",
            "--json",
        ],
    )
    events = runner.invoke(app, ["exec", "events", "--limit", "5", "--json"])
    reconcile = runner.invoke(app, ["exec", "reconcile", "--json"])

    assert watch.exit_code == 0
    assert events.exit_code == 0
    assert reconcile.exit_code == 0
    assert json.loads(watch.stdout)["session"]["stream_kind"] == "execution_user"
    assert json.loads(events.stdout)["total"] >= 0
    assert "summary" in json.loads(reconcile.stdout)

    if not open_order_id:
        pytest.skip("No live open order id available for exec order wait smoke.")

    wait = runner.invoke(
        app,
        [
            "exec",
            "order",
            "wait",
            "--order-id",
            open_order_id,
            "--seconds",
            "2",
            "--json",
        ],
    )

    assert wait.exit_code == 0
    wait_payload = json.loads(wait.stdout)
    assert wait_payload["order_id"] == open_order_id
