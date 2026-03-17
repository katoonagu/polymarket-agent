"""CLI tests for the initial market discovery scaffold."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app

runner = CliRunner()


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "market" in result.stdout


def test_market_help() -> None:
    result = runner.invoke(app, ["market", "--help"])

    assert result.exit_code == 0
    assert "search" in result.stdout


def test_market_search_json() -> None:
    result = runner.invoke(app, ["market", "search", "--query", "btc", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "query": "btc",
        "results": [],
        "total": 0,
    }
