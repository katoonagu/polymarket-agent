"""Top-level Typer application."""

from __future__ import annotations

import typer

from pm.cli.clob import app as clob_app
from pm.cli.market import app as market_app
from pm.cli.support import (
    ROOT_JSON_OPTION,
    ROOT_OUTPUT_OPTION,
    JsonAwareTyperGroup,
    configure_root_output,
)
from pm.common import OutputMode

app = typer.Typer(
    add_completion=False,
    cls=JsonAwareTyperGroup,
    help="Read-only Polymarket CLI for market discovery and public CLOB data.",
    no_args_is_help=True,
)
app.add_typer(market_app, name="market")
app.add_typer(clob_app, name="clob")


@app.callback()
def root_callback(
    ctx: typer.Context,
    output: OutputMode = ROOT_OUTPUT_OPTION,
    json_output: bool = ROOT_JSON_OPTION,
) -> None:
    """Configure global CLI behavior."""
    configure_root_output(ctx, output, json_output)


def main() -> None:
    """Run the CLI application."""
    app()
