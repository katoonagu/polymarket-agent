"""Top-level Typer application."""

from __future__ import annotations

from typing import Literal

import typer

from pm.cli.clob import app as clob_app
from pm.cli.data import app as data_app
from pm.cli.market import app as market_app
from pm.cli.support import set_root_output_mode

OutputMode = Literal["table", "json"]

app = typer.Typer(
    add_completion=False,
    help="Read-only Polymarket public market, CLOB, and data CLI.",
    no_args_is_help=True,
)
OUTPUT_OPTION = typer.Option(
    "table",
    "--output",
    help="Output mode for read-only commands.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Convenience alias for --output json.",
)
app.add_typer(market_app, name="market")
app.add_typer(clob_app, name="clob")
app.add_typer(data_app, name="data")


@app.callback()
def main_callback(
    ctx: typer.Context,
    output: OutputMode = OUTPUT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Store root CLI options for subcommands."""
    set_root_output_mode(ctx, output=output, json_output=json_output)


def main() -> None:
    """Run the CLI application."""
    app()
