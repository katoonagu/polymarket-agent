from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from pm.cli.app import app

runner = CliRunner()


pytestmark = pytest.mark.skipif(
    os.getenv("PM_RUN_AUTH_SMOKE") != "1",
    reason="Set PM_RUN_AUTH_SMOKE=1 to run authenticated dry-run smoke tests.",
)


def test_auth_smoke_surface() -> None:
    required = ["POLYMARKET_PRIVATE_KEY", "POLYMARKET_SIGNATURE_TYPE"]
    for key in required:
        if not os.getenv(key):
            pytest.skip(f"Missing required env var {key}")

    doctor = runner.invoke(app, ["setup", "doctor", "--json"])
    show = runner.invoke(app, ["auth", "show", "--json"])
    derive = runner.invoke(app, ["auth", "derive-api-key", "--json"])
    balances = runner.invoke(app, ["auth", "balances", "--json"])
    allowances = runner.invoke(app, ["auth", "allowances", "--json"])

    market_search = runner.invoke(
        app,
        ["market", "search", "--query", "btc", "--limit", "1", "--json"],
    )
    if market_search.exit_code != 0:
        pytest.skip("Could not discover a live market for auth dry-run smoke.")
    market_payload = json.loads(market_search.stdout)
    if not market_payload["results"]:
        pytest.skip("Public Gamma search returned no markets for auth dry-run smoke.")
    market_slug = market_payload["results"][0]["market_slug"]

    dry_run = runner.invoke(
        app,
        [
            "exec",
            "dry-run",
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

    assert doctor.exit_code == 0
    assert show.exit_code == 0
    assert derive.exit_code == 0
    assert balances.exit_code == 0
    assert allowances.exit_code == 0
    assert dry_run.exit_code == 0
    assert json.loads(dry_run.stdout)["decision"] in {"WOULD_POST", "SKIP"}
