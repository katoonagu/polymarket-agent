"""Market-related CLI commands."""

from __future__ import annotations

import typer

from pm.cli.clob import run_book_command, run_price_command
from pm.cli.support import (
    LOCAL_JSON_OPTION,
    LOCAL_OUTPUT_OPTION,
    emit_cli_error,
    resolve_output_mode,
)
from pm.common import OutputMode, emit_output
from pm.market import (
    GammaClient,
    GammaClientError,
    GammaNotFoundError,
    MarketSearchResponse,
    NormalizedEvent,
    NormalizedMarket,
)

app = typer.Typer(
    add_completion=False,
    help=(
        "Read-only Gamma market discovery commands. "
        "Series commands are deferred until a normalized Gamma series adapter exists."
    ),
    no_args_is_help=True,
)
QUERY_OPTION = typer.Option(
    ...,
    "--query",
    help="Free-text market query for Gamma public search.",
)
LIMIT_OPTION = typer.Option(
    10,
    "--limit",
    min=1,
    help="Maximum number of normalized market results to return.",
)
SLUG_OPTION = typer.Option(
    ...,
    "--slug",
    help="Gamma market or event slug.",
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


@app.command("search")
def search_market(
    ctx: typer.Context,
    query: str = QUERY_OPTION,
    limit: int = LIMIT_OPTION,
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Search markets using Gamma public search."""
    output_mode = resolve_output_mode(ctx, output=output, json_output=json_output)
    normalized_query = query.strip()
    try:
        with GammaClient() as client:
            results = client.search_markets(normalized_query, limit)
    except GammaClientError as exc:
        emit_cli_error(
            code="request_failed",
            message=str(exc),
            resource="market_search",
            identifier=normalized_query,
            output_mode=output_mode,
        )

    result = MarketSearchResponse(query=normalized_query, results=results, total=len(results))
    if not result.results:
        emit_output(
            result.model_dump(mode="json"),
            output_mode=output_mode,
            text=f"No markets found for query '{result.query}'.",
        )
        return

    emit_output(
        result.model_dump(mode="json"),
        output_mode=output_mode,
        text="\n\n".join(_render_market_block(market) for market in result.results),
    )


@app.command("show")
def show_market(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a normalized market by slug."""
    output_mode = resolve_output_mode(ctx, output=output, json_output=json_output)
    try:
        with GammaClient() as client:
            market = client.get_market_by_slug(slug)
    except GammaNotFoundError as exc:
        emit_cli_error(
            code="not_found",
            message=str(exc),
            resource="market",
            identifier=slug,
            output_mode=output_mode,
        )
    except GammaClientError as exc:
        emit_cli_error(
            code="request_failed",
            message=str(exc),
            resource="market",
            identifier=slug,
            output_mode=output_mode,
        )

    emit_output(
        market.model_dump(mode="json"),
        output_mode=output_mode,
        text=_render_market_block(market),
    )


@app.command("event")
def show_event(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a normalized event and its child markets by slug."""
    output_mode = resolve_output_mode(ctx, output=output, json_output=json_output)
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError as exc:
        emit_cli_error(
            code="not_found",
            message=str(exc),
            resource="event",
            identifier=slug,
            output_mode=output_mode,
        )
    except GammaClientError as exc:
        emit_cli_error(
            code="request_failed",
            message=str(exc),
            resource="event",
            identifier=slug,
            output_mode=output_mode,
        )

    market_blocks = "\n\n".join(_render_market_block(market) for market in event.markets)
    text = _render_event_block(event)
    if market_blocks:
        text = f"{text}\n\n{market_blocks}"

    emit_output(
        event.model_dump(mode="json"),
        output_mode=output_mode,
        text=text,
    )


@app.command("book", help="Deprecated alias for `pm clob book`.")
def show_book_alias(
    ctx: typer.Context,
    token_id: str = typer.Option(
        ...,
        "--token-id",
        help="Outcome token ID from `pm market show`.",
    ),
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob book`."""
    run_book_command(ctx=ctx, token_id=token_id, output=output, json_output=json_output)


@app.command("price", help="Deprecated alias for `pm clob price`.")
def show_price_alias(
    ctx: typer.Context,
    token_id: str = typer.Option(
        ...,
        "--token-id",
        help="Outcome token ID from `pm market show`.",
    ),
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob price`."""
    run_price_command(ctx=ctx, token_id=token_id, output=output, json_output=json_output)
