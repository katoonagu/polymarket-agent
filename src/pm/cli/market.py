"""Market-related CLI commands."""

from __future__ import annotations

import typer

<<<<<<< HEAD
from pm.cli.clob import run_book_command, run_price_command
from pm.cli.support import LOCAL_JSON_OPTION, emit_cli_error, emit_command_output
=======
from pm.cli.clob import _run_book, _run_price
from pm.cli.support import emit_command_error, emit_command_output
>>>>>>> feat/02a-python-scaffold
from pm.market import (
    GammaClient,
    GammaClientError,
    GammaNotFoundError,
<<<<<<< HEAD
    MarketSearchResponse,
=======
>>>>>>> feat/02a-python-scaffold
    NormalizedEvent,
    NormalizedMarket,
)

app = typer.Typer(
    add_completion=False,
<<<<<<< HEAD
    help=(
        "Gamma-backed read-only market discovery commands. "
        "Series support is deferred until a normalized Gamma series adapter exists."
    ),
=======
    help="Read-only market discovery commands. Series support is intentionally deferred.",
>>>>>>> feat/02a-python-scaffold
    no_args_is_help=True,
)
QUERY_OPTION = typer.Option(
    ...,
    "--query",
<<<<<<< HEAD
    help="Free-text market query for Gamma public search.",
=======
    help="Free-text market query for the public Gamma adapter.",
>>>>>>> feat/02a-python-scaffold
)
LIMIT_OPTION = typer.Option(
    10,
    "--limit",
    min=1,
<<<<<<< HEAD
    help="Maximum number of normalized market results to return.",
=======
    help="Maximum number of normalized market rows to return.",
>>>>>>> feat/02a-python-scaffold
)
SLUG_OPTION = typer.Option(
    ...,
    "--slug",
<<<<<<< HEAD
    help="Gamma market or event slug.",
=======
    help="Market or event slug.",
>>>>>>> feat/02a-python-scaffold
)
TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
<<<<<<< HEAD
    help="Outcome token ID from `pm market show`.",
)


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def _format_optional(value: object | None) -> str:
    return "-" if value is None else str(value)


def _render_market_block(market: NormalizedMarket) -> str:
    outcome_tokens = []
    if len(market.outcomes) == len(market.token_ids):
        outcome_tokens = [
            f"{outcome}={token_id}"
            for outcome, token_id in zip(
                market.outcomes,
                market.token_ids,
                strict=True,
            )
        ]

    lines = [
        f"Market: {market.market_slug}",
        f"Event: {_format_optional(market.event_slug)}",
        f"Question: {market.question}",
        f"Event Title: {_format_optional(market.event_title)}",
        f"Active: {_format_bool(market.active)}",
        f"Closed: {_format_bool(market.closed)}",
        f"Enable Order Book: {_format_bool(market.enable_order_book)}",
        f"Condition ID: {_format_optional(market.condition_id)}",
        f"Token IDs: {_format_list(market.token_ids)}",
        f"Outcomes: {_format_list(market.outcomes)}",
        f"Outcome Tokens: {_format_list(outcome_tokens)}",
        f"Min Tick: {_format_optional(market.min_tick)}",
        f"Min Order Size: {_format_optional(market.min_order_size)}",
    ]
    return "\n".join(lines)


def _render_event_block(event: NormalizedEvent) -> str:
    lines = [
        f"Event: {event.event_slug}",
        f"Title: {event.title}",
        f"Active: {_format_bool(event.active)}",
        f"Closed: {_format_bool(event.closed)}",
        f"Enable Order Book: {_format_bool(event.enable_order_book)}",
        f"Markets: {len(event.markets)}",
    ]
    return "\n".join(lines)
=======
    help="Polymarket token ID returned by market discovery commands.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
)
>>>>>>> feat/02a-python-scaffold


@app.command("search")
def search_market(
    ctx: typer.Context,
    query: str = QUERY_OPTION,
    limit: int = LIMIT_OPTION,
<<<<<<< HEAD
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Search markets using Gamma public search."""
    try:
        with GammaClient() as client:
            results = client.search_markets(query, limit)
    except GammaClientError as exc:
        emit_cli_error(
            ctx=ctx,
            code="request_failed",
            message=str(exc),
            resource="market_search",
            identifier=query.strip(),
            json_output=json_output,
        )

    result = MarketSearchResponse(query=query.strip(), results=results, total=len(results))

    if not result.results:
        emit_command_output(
            ctx=ctx,
            payload={"query": result.query, "total": result.total},
            json_output=json_output,
            text=f"No markets found for query '{result.query}'.",
        )
        return

    emit_command_output(
        ctx=ctx,
        payload=result.model_dump(mode="json"),
        json_output=json_output,
        text="\n\n".join(_render_market_block(market) for market in result.results),
=======
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
>>>>>>> feat/02a-python-scaffold
    )


@app.command("show")
def show_market(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
<<<<<<< HEAD
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a normalized market by slug."""
=======
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch a single public market by slug."""
>>>>>>> feat/02a-python-scaffold
    try:
        with GammaClient() as client:
            market = client.get_market_by_slug(slug)
    except GammaNotFoundError as exc:
<<<<<<< HEAD
        emit_cli_error(
            ctx=ctx,
            resource="market",
            identifier=slug,
            code="not_found",
            message=str(exc),
            json_output=json_output,
        )
    except GammaClientError as exc:
        emit_cli_error(
            ctx=ctx,
            resource="market",
            identifier=slug,
            code="request_failed",
            message=str(exc),
            json_output=json_output,
        )

    emit_command_output(
        ctx=ctx,
        payload=market.model_dump(mode="json"),
        json_output=json_output,
        text=_render_market_block(market),
=======
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
>>>>>>> feat/02a-python-scaffold
    )


@app.command("event")
def show_event(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
<<<<<<< HEAD
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a normalized event and its child markets by slug."""
=======
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch a single public event by slug."""
>>>>>>> feat/02a-python-scaffold
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError as exc:
<<<<<<< HEAD
        emit_cli_error(
            ctx=ctx,
            resource="event",
            identifier=slug,
            code="not_found",
            message=str(exc),
            json_output=json_output,
        )
    except GammaClientError as exc:
        emit_cli_error(
            ctx=ctx,
            resource="event",
            identifier=slug,
            code="request_failed",
            message=str(exc),
            json_output=json_output,
        )

    market_blocks = "\n\n".join(_render_market_block(market) for market in event.markets)
    text = _render_event_block(event)
    if market_blocks:
        text = f"{text}\n\n{market_blocks}"

    emit_command_output(
        ctx=ctx,
        payload=event.model_dump(mode="json"),
        json_output=json_output,
        text=text,
    )


@app.command("book", deprecated=True)
def show_book_alias(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob book`."""
    run_book_command(ctx=ctx, token_id=token_id, json_output=json_output)


@app.command("price", deprecated=True)
def show_price_alias(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob price`."""
    run_price_command(ctx=ctx, token_id=token_id, json_output=json_output)
=======
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
>>>>>>> feat/02a-python-scaffold
