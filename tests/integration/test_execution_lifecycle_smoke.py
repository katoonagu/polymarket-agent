from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from pm.cli.app import app

runner = CliRunner()


pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_EXEC_LIFECYCLE_SMOKE") != "1",
    reason="Set PM_RUN_EXEC_LIFECYCLE_SMOKE=1 to run execution lifecycle smoke tests.",
)


def test_execution_lifecycle_smoke_surface() -> None:
    required = ["POLYMARKET_PRIVATE_KEY", "POLYMARKET_SIGNATURE_TYPE"]
    for key in required:
        if not os.getenv(key):
            pytest.skip(f"Missing required env var {key}")

    approve_check = runner.invoke(app, ["approve", "check", "--json"])
    preview_set = runner.invoke(app, ["approve", "set", "--asset", "usdc", "--json"])
    open_orders = runner.invoke(app, ["exec", "orders", "open", "--json"])

    market_search = runner.invoke(
        app,
        ["market", "search", "--query", "btc", "--limit", "1", "--json"],
    )
    if market_search.exit_code != 0:
        pytest.skip("Could not discover a live market for execution lifecycle smoke.")
    market_payload = json.loads(market_search.stdout)
    if not market_payload["results"]:
        pytest.skip("Public Gamma search returned no markets for execution lifecycle smoke.")
    market_slug = market_payload["results"][0]["market_slug"]
    condition_id = market_payload["results"][0]["condition_id"]

    paper_post = runner.invoke(
        app,
        [
            "exec",
            "post",
            "--market",
            market_slug,
            "--outcome",
            "yes",
            "--side",
            "buy",
            "--price",
            "0.55",
            "--size",
            "10",
            "--json",
        ],
    )
    cancel_all = runner.invoke(app, ["exec", "cancel-all", "--json"])
    cancel_market = runner.invoke(
        app,
        ["exec", "cancel-market", "--market", condition_id, "--json"],
    )

    assert approve_check.exit_code == 0
    assert preview_set.exit_code == 0
    assert open_orders.exit_code == 0
    assert paper_post.exit_code == 0
    assert cancel_all.exit_code == 0
    assert cancel_market.exit_code == 0
    assert json.loads(paper_post.stdout)["decision"] in {"WOULD_POST", "SKIP"}

    if os.getenv("PM_RUN_EXEC_LIVE_WRITE_SMOKE") != "1":
        pytest.skip("Set PM_RUN_EXEC_LIVE_WRITE_SMOKE=1 to run live-gated write smoke tests.")

    live_set = runner.invoke(
        app,
        ["approve", "set", "--asset", "usdc", "--live", "--confirm", "--json"],
    )
    live_post = runner.invoke(
        app,
        [
            "exec",
            "post",
            "--market",
            market_slug,
            "--outcome",
            "yes",
            "--side",
            "buy",
            "--price",
            "0.55",
            "--size",
            "10",
            "--live",
            "--confirm",
            "--json",
        ],
    )

    assert live_set.exit_code == 0
    assert live_post.exit_code == 0
    live_post_payload = json.loads(live_post.stdout)
    assert live_post_payload["decision"] in {"POSTED", "SKIP"}

    if live_post_payload["decision"] == "POSTED":
        order_id = live_post_payload["live_response"]["order"]["order_id"]
        get_order = runner.invoke(app, ["exec", "order", "get", "--order-id", order_id, "--json"])
        cancel_one = runner.invoke(
            app,
            ["exec", "cancel", "--order-id", order_id, "--live", "--confirm", "--json"],
        )
        assert get_order.exit_code == 0
        assert cancel_one.exit_code == 0
