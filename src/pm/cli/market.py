"""Market-related CLI commands."""

from __future__ import annotations

import typer

from pm.common.output import emit_error, emit_output
from pm.market import (
    GammaClient,
    GammaClientError,
    GammaNotFoundError,
    NormalizedEvent,
    NormalizedMarket,
)

app = typer.Typer(
    add_completion=False,
    help="Read-only market discovery commands.",
    no_args_is_help=True,
)
QUERY_OPTION = typer.Option(
    ...,
    "--query",
    help="Free-text market query for the public Gamma adapter.",
)
LIMIT_OPTION = typer.Option(
    10,
    "--limit",
    min=1,
    help="Maximum number of normalized market rows to return.",
)
SLUG_OPTION = typer.Option(
    ...,
    "--slug",
    help="Market or event slug.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
)


@app.command("search")
def search_market(
    query: str = QUERY_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Search public Gamma markets by free-text query."""
    try:
        with GammaClient() as client:
            result = client.search_markets(query, limit=limit)
    except GammaClientError as exc:
        _handle_error(
            str(exc),
            code="request_failed",
            json_output=json_output,
            resource="search",
            identifier=query.strip(),
        )
        raise typer.Exit(1) from exc

    emit_output(
        result.model_dump(mode="json"),
        json_output=json_output,
        text=_format_search_output(result.query, result.results),
    )


@app.command("show")
def show_market(
    slug: str = SLUG_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch a single public market by slug."""
    try:
        with GammaClient() as client:
            market = client.get_market_by_slug(slug)
    except GammaNotFoundError as exc:
        _handle_error(
            str(exc),
            code="not_found",
            json_output=json_output,
            resource="market",
            identifier=slug,
        )
        raise typer.Exit(1) from exc
    except GammaClientError as exc:
        _handle_error(
            str(exc),
            code="request_failed",
            json_output=json_output,
            resource="market",
            identifier=slug,
        )
        raise typer.Exit(1) from exc

    emit_output(
        market.model_dump(mode="json"),
        json_output=json_output,
        text=_format_market_block(market),
    )


@app.command("event")
def show_event(
    slug: str = SLUG_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch a single public event by slug."""
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError as exc:
        _handle_error(
            str(exc),
            code="not_found",
            json_output=json_output,
            resource="event",
            identifier=slug,
        )
        raise typer.Exit(1) from exc
    except GammaClientError as exc:
        _handle_error(
            str(exc),
            code="request_failed",
            json_output=json_output,
            resource="event",
            identifier=slug,
        )
        raise typer.Exit(1) from exc

    emit_output(
        event.model_dump(mode="json"),
        json_output=json_output,
        text=_format_event_block(event),
    )


def _handle_error(
    message: str,
    *,
    code: str,
    json_output: bool,
    resource: str,
    identifier: str,
) -> None:
    emit_error(
        code=code,
        message=message,
        json_output=json_output,
        resource=resource,
        identifier=identifier,
    )


def _format_search_output(query: str, markets: list[NormalizedMarket]) -> str:
    if not markets:
        return f"No markets found for query '{query}'."
    return "\n\n".join(_format_market_block(market) for market in markets)


def _format_market_block(market: NormalizedMarket) -> str:
    lines = [
        f"Market slug: {market.market_slug}",
        f"Event slug: {market.event_slug or '-'}",
        f"Question: {market.question}",
        f"Event title: {market.event_title or '-'}",
        f"Active: {market.active}",
        f"Closed: {market.closed}",
        f"Enable order book: {market.enable_order_book}",
        f"Condition ID: {market.condition_id or '-'}",
        f"Token IDs: {', '.join(market.token_ids) if market.token_ids else '-'}",
        f"Outcomes: {', '.join(market.outcomes) if market.outcomes else '-'}",
    ]
    return "\n".join(lines)


def _format_event_block(event: NormalizedEvent) -> str:
    lines = [
        f"Event slug: {event.event_slug}",
        f"Title: {event.title}",
        f"Active: {event.active}",
        f"Closed: {event.closed}",
        f"Enable order book: {event.enable_order_book}",
    ]
    if event.markets:
        lines.extend(
            ["Markets:", "\n\n".join(_format_market_block(market) for market in event.markets)]
        )
    else:
        lines.extend(["Markets:", "-"])
    return "\n".join(lines)
