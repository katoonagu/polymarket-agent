"""Top-level Typer application."""

from __future__ import annotations

import typer

from pm.cli.approve import app as approve_app
from pm.cli.auth import app as auth_app
from pm.cli.clob import app as clob_app
from pm.cli.data import app as data_app
from pm.cli.execution import app as execution_app
from pm.cli.market import app as market_app
from pm.cli.ops import app as ops_app
from pm.cli.ops import status as status_command
from pm.cli.risk import app as risk_app
from pm.cli.setup import app as setup_app
from pm.cli.shell import shell as shell_command
from pm.cli.strategy import app as strategy_app
from pm.cli.stream import app as stream_app
from pm.cli.support import (
    ROOT_JSON_OPTION,
    ROOT_OUTPUT_OPTION,
    JSONAwareTyperGroup,
    OutputMode,
    configure_cli_settings,
)
from pm.cli.wallet import app as wallet_app

app = typer.Typer(
    add_completion=False,
    cls=JSONAwareTyperGroup,
    help=(
        "Polymarket intelligence, guarded execution, and operator control plane CLI."
    ),
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    output: OutputMode = ROOT_OUTPUT_OPTION,
    json_output: bool = ROOT_JSON_OPTION,
) -> None:
    """Configure root-level CLI settings."""
    configure_cli_settings(ctx, output=output, json_output=json_output)


app.add_typer(setup_app, name="setup")
app.add_typer(auth_app, name="auth")
app.add_typer(approve_app, name="approve")
app.add_typer(market_app, name="market")
app.add_typer(clob_app, name="clob")
app.add_typer(data_app, name="data")
app.add_typer(wallet_app, name="wallet")
app.add_typer(stream_app, name="stream")
app.add_typer(risk_app, name="risk")
app.add_typer(strategy_app, name="strategy")
app.add_typer(ops_app, name="ops")
app.add_typer(execution_app, name="exec")
app.command("status")(status_command)
app.command("shell")(shell_command)


def main() -> None:
    """Run the CLI application."""
    app()
