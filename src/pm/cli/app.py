"""Top-level Typer application."""

from __future__ import annotations

import typer

from pm.cli.market import app as market_app

app = typer.Typer(
    add_completion=False,
    help="Read-only Polymarket market discovery CLI.",
    no_args_is_help=True,
)
app.add_typer(market_app, name="market")


def main() -> None:
    """Run the CLI application."""
    app()
