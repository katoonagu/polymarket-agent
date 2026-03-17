"""Market-related CLI commands."""

from __future__ import annotations

import typer

from pm.common.output import emit_output
from pm.market import search_markets

app = typer.Typer(
    add_completion=False,
    help="Read-only market discovery commands.",
    no_args_is_help=True,
)
QUERY_OPTION = typer.Option(
    ...,
    "--query",
    help="Free-text market query for the future discovery adapter.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
)


@app.command("search")
def search_market(
    query: str = QUERY_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Search markets with the initial deterministic scaffold."""
    result = search_markets(query)

    if result.results:
        text = "\n".join(f"{item.market_slug}: {item.question}" for item in result.results)
    else:
        text = (
            f"No markets found for query '{result.query}'. "
            "Market discovery is scaffolded but not connected to Polymarket yet."
        )

    emit_output(result.model_dump(mode="json"), json_output=json_output, text=text)
