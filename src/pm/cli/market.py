"""Market-related CLI commands."""

from __future__ import annotations

import typer

from pm.common.output import emit_output
from pm.market import (
    ClobClient,
    ClobClientError,
    ClobNotFoundError,
    GammaClient,
    GammaClientError,
    GammaNotFoundError,
    MarketSearchResponse,
    NormalizedBook,
    NormalizedBookLevel,
    NormalizedEvent,
    NormalizedMarket,
    NormalizedPriceQuote,
)

app = typer.Typer(
    add_completion=False,
    help="Read-only market discovery commands.",
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
TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
    help="Outcome token ID from `pm market show`.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
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


def _render_book_levels(title: str, levels: list[NormalizedBookLevel]) -> str:
    lines = [f"{title}:"]
    if not levels:
        lines.append("  -")
        return "\n".join(lines)

    lines.extend(f"  price={level.price} size={level.size}" for level in levels)
    return "\n".join(lines)


def _render_book_block(book: NormalizedBook) -> str:
    sections = [
        f"Token ID: {book.token_id}",
        f"Tick Size: {_format_optional(book.tick_size)}",
        f"Min Order Size: {_format_optional(book.min_order_size)}",
        _render_book_levels("Bids", book.bids),
        _render_book_levels("Asks", book.asks),
    ]
    return "\n".join(sections)


def _render_price_block(price_quote: NormalizedPriceQuote) -> str:
    lines = [
        f"Token ID: {price_quote.token_id}",
        f"Buy Price: {_format_optional(price_quote.buy_price)}",
        f"Sell Price: {_format_optional(price_quote.sell_price)}",
    ]
    return "\n".join(lines)


def _emit_cli_error(
    *,
    resource: str,
    identifier: str,
    error: str,
    message: str,
    json_output: bool,
) -> None:
    payload = {
        "error": error,
        "message": message,
        "resource": resource,
        "slug": identifier,
    }
    emit_output(
        payload,
        json_output=json_output,
        text=f"Error: {message}",
    )
    raise typer.Exit(code=1)


@app.command("search")
def search_market(
    query: str = QUERY_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Search markets using Gamma public search."""
    try:
        with GammaClient() as client:
            results = client.search_markets(query, limit)
    except GammaClientError as exc:
        payload = {
            "error": "request_failed",
            "message": str(exc),
            "query": query.strip(),
            "resource": "market_search",
        }
        emit_output(payload, json_output=json_output, text=f"Error: {exc}")
        raise typer.Exit(code=1) from exc

    result = MarketSearchResponse(query=query.strip(), results=results, total=len(results))
    if json_output:
        emit_output(result.model_dump(mode="json"), json_output=True, text="")
        return

    if not result.results:
        emit_output(
            {"query": result.query, "total": result.total},
            json_output=False,
            text=f"No markets found for query '{result.query}'.",
        )
        return

    emit_output(
        result.model_dump(mode="json"),
        json_output=False,
        text="\n\n".join(_render_market_block(market) for market in result.results),
    )


@app.command("show")
def show_market(
    slug: str = SLUG_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show a normalized market by slug."""
    try:
        with GammaClient() as client:
            market = client.get_market_by_slug(slug)
    except GammaNotFoundError as exc:
        _emit_cli_error(
            resource="market",
            identifier=slug,
            error="not_found",
            message=str(exc),
            json_output=json_output,
        )
    except GammaClientError as exc:
        _emit_cli_error(
            resource="market",
            identifier=slug,
            error="request_failed",
            message=str(exc),
            json_output=json_output,
        )

    emit_output(
        market.model_dump(mode="json"),
        json_output=json_output,
        text=_render_market_block(market),
    )


@app.command("event")
def show_event(
    slug: str = SLUG_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show a normalized event and its child markets by slug."""
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError as exc:
        _emit_cli_error(
            resource="event",
            identifier=slug,
            error="not_found",
            message=str(exc),
            json_output=json_output,
        )
    except GammaClientError as exc:
        _emit_cli_error(
            resource="event",
            identifier=slug,
            error="request_failed",
            message=str(exc),
            json_output=json_output,
        )

    market_blocks = "\n\n".join(_render_market_block(market) for market in event.markets)
    text = _render_event_block(event)
    if market_blocks:
        text = f"{text}\n\n{market_blocks}"

    emit_output(
        event.model_dump(mode="json"),
        json_output=json_output,
        text=text,
    )


@app.command("book")
def show_book(
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show a public order book for a token ID."""
    try:
        with ClobClient() as client:
            book = client.get_book(token_id)
    except ClobNotFoundError as exc:
        _emit_cli_error(
            resource="book",
            identifier=token_id,
            error="not_found",
            message=str(exc),
            json_output=json_output,
        )
    except ClobClientError as exc:
        _emit_cli_error(
            resource="book",
            identifier=token_id,
            error="request_failed",
            message=str(exc),
            json_output=json_output,
        )

    emit_output(
        book.model_dump(mode="json"),
        json_output=json_output,
        text=_render_book_block(book),
    )


@app.command("price")
def show_price(
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show public BUY and SELL prices for a token ID."""
    try:
        with ClobClient() as client:
            price_quote = client.get_prices(token_id)
    except ClobNotFoundError as exc:
        _emit_cli_error(
            resource="price",
            identifier=token_id,
            error="not_found",
            message=str(exc),
            json_output=json_output,
        )
    except ClobClientError as exc:
        _emit_cli_error(
            resource="price",
            identifier=token_id,
            error="request_failed",
            message=str(exc),
            json_output=json_output,
        )

    emit_output(
        price_quote.model_dump(mode="json"),
        json_output=json_output,
        text=_render_price_block(price_quote),
    )
