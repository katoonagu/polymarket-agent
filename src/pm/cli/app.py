"""Top-level Typer application."""

from __future__ import annotations

import typer

from pm.cli.clob import app as clob_app
from pm.cli.market import app as market_app
from pm.cli.support import (
    ROOT_JSON_OPTION,
    ROOT_OUTPUT_OPTION,
    JSONAwareTyperGroup,
    OutputMode,
    configure_cli_settings,
)

app = typer.Typer(
    add_completion=False,
    cls=JSONAwareTyperGroup,
    help="Read-only Polymarket CLI for Gamma discovery and public CLOB reads.",
    no_args_is_help=True,
)


@app.callback()
def root_callback(
    ctx: typer.Context,
    output: OutputMode = ROOT_OUTPUT_OPTION,
    json_output: bool = ROOT_JSON_OPTION,
) -> None:
    """Configure root-level CLI settings."""
    configure_cli_settings(ctx, output=output, json_output=json_output)


app.add_typer(market_app, name="market")
app.add_typer(clob_app, name="clob")


def main() -> None:
    """Run the CLI application."""
    app()
