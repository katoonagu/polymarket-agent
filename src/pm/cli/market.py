"""Market-related CLI commands."""

from __future__ import annotations

import typer

from pm.cli.clob import _run_book, _run_price
from pm.cli.support import emit_command_error, emit_command_output
from pm.market import (
    GammaClient,
    GammaClientError,
    GammaNotFoundError,
    NormalizedEvent,
    NormalizedMarket,
)

app = typer.Typer(
    add_completion=False,
    help="Read-only market discovery commands. Series support is intentionally deferred.",
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
TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
    help="Polymarket token ID returned by market discovery commands.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
)


@app.command("search")
def search_market(
    ctx: typer.Context,
    query: str = QUERY_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Search public Gamma markets by free-text query."""
    try:
        with GammaClient() as client:
            result = client.search_markets(query, limit=limit)
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="search",
            identifier=query.strip(),
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_search_output(result.query, result.results),
        local_json_output=json_output,
    )


@app.command("show")
def show_market(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch a single public market by slug."""
    try:
        with GammaClient() as client:
            market = client.get_market_by_slug(slug)
    except GammaNotFoundError as exc:
        _handle_market_not_found(ctx, slug=slug, json_output=json_output, original_error=exc)
        raise typer.Exit(1) from exc
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="market",
            identifier=slug,
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        market.model_dump(mode="json"),
        text=_format_market_block(market),
        local_json_output=json_output,
    )


@app.command("event")
def show_event(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch a single public event by slug."""
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError as exc:
        emit_command_error(
            ctx,
            code="not_found",
            message=str(exc),
            resource="event",
            identifier=slug,
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="event",
            identifier=slug,
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        event.model_dump(mode="json"),
        text=_format_event_block(event),
        local_json_output=json_output,
    )


@app.command("book")
def market_book_alias(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob book`."""
    _run_book(ctx, token_id=token_id, json_output=json_output)


@app.command("price")
def market_price_alias(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob price`."""
    _run_price(ctx, token_id=token_id, json_output=json_output)


def _handle_market_not_found(
    ctx: typer.Context,
    *,
    slug: str,
    json_output: bool,
    original_error: GammaNotFoundError,
) -> None:
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError:
        emit_command_error(
            ctx,
            code="not_found",
            message=str(original_error),
            resource="market",
            identifier=slug,
            local_json_output=json_output,
        )
        return
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="event",
            identifier=slug,
            local_json_output=json_output,
        )
        return

    market_slugs = [market.market_slug for market in event.markets]
    market_list = ", ".join(market_slugs) if market_slugs else "no market_slugs returned"
    message = (
        f"This looks like an event slug. Use `pm market event --slug {slug}` "
        f"or choose one of the returned market_slug values: {market_list}."
    )
    emit_command_error(
        ctx,
        code="event_slug_hint",
        message=message,
        resource="market",
        identifier=slug,
        local_json_output=json_output,
        hint={
            "event_slug": event.event_slug,
            "suggested_command": f"pm market event --slug {slug}",
            "market_slugs": market_slugs,
        },
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
    ]

    if market.token_ids and market.outcomes and len(market.token_ids) == len(market.outcomes):
        lines.append("Token IDs:")
        lines.extend(
            f"  {outcome}: {token_id}"
            for outcome, token_id in zip(market.outcomes, market.token_ids, strict=True)
        )
    else:
        lines.append(f"Token IDs: {', '.join(market.token_ids) if market.token_ids else '-'}")

    lines.append(f"Outcomes: {', '.join(market.outcomes) if market.outcomes else '-'}")
    if market.token_ids:
        lines.append("Next: pm clob book --token-id <id>")
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
