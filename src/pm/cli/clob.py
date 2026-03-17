"""Public read-only CLOB CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import LOCAL_JSON_OPTION, emit_cli_error, emit_command_output
from pm.market import (
    ClobClient,
    ClobClientError,
    ClobNotFoundError,
    NormalizedBook,
    NormalizedBookLevel,
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

app = typer.Typer(
    add_completion=False,
    help="Public read-only CLOB commands for books, prices, midpoint, and spread.",
    no_args_is_help=True,
)
TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
    help="Outcome token ID from `pm market show`.",
)


def _format_optional(value: object | None) -> str:
    return "-" if value is None else str(value)


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


def _render_midpoint_block(midpoint_quote: NormalizedMidpointQuote) -> str:
    lines = [
        f"Token ID: {midpoint_quote.token_id}",
        f"Midpoint: {midpoint_quote.midpoint}",
    ]
    return "\n".join(lines)


def _render_spread_block(spread_quote: NormalizedSpreadQuote) -> str:
    lines = [
        f"Token ID: {spread_quote.token_id}",
        f"Spread: {spread_quote.spread}",
    ]
    return "\n".join(lines)


def run_book_command(
    *,
    ctx: typer.Context,
    token_id: str,
    json_output: bool,
) -> None:
    """Execute the canonical book command."""
    try:
        with ClobClient() as client:
            book = client.get_book(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            ctx=ctx,
            code="not_found",
            message=str(exc),
            resource="book",
            identifier=token_id,
            json_output=json_output,
        )
    except ClobClientError as exc:
        emit_cli_error(
            ctx=ctx,
            code="request_failed",
            message=str(exc),
            resource="book",
            identifier=token_id,
            json_output=json_output,
        )

    emit_command_output(
        ctx=ctx,
        payload=book.model_dump(mode="json"),
        json_output=json_output,
        text=_render_book_block(book),
    )


def run_price_command(
    *,
    ctx: typer.Context,
    token_id: str,
    json_output: bool,
) -> None:
    """Execute the canonical price command."""
    try:
        with ClobClient() as client:
            price_quote = client.get_prices(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            ctx=ctx,
            code="not_found",
            message=str(exc),
            resource="price",
            identifier=token_id,
            json_output=json_output,
        )
    except ClobClientError as exc:
        emit_cli_error(
            ctx=ctx,
            code="request_failed",
            message=str(exc),
            resource="price",
            identifier=token_id,
            json_output=json_output,
        )

    emit_command_output(
        ctx=ctx,
        payload=price_quote.model_dump(mode="json"),
        json_output=json_output,
        text=_render_price_block(price_quote),
    )


def run_midpoint_command(
    *,
    ctx: typer.Context,
    token_id: str,
    json_output: bool,
) -> None:
    """Execute the canonical midpoint command."""
    try:
        with ClobClient() as client:
            midpoint_quote = client.get_midpoint(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            ctx=ctx,
            code="not_found",
            message=str(exc),
            resource="midpoint",
            identifier=token_id,
            json_output=json_output,
        )
    except ClobClientError as exc:
        emit_cli_error(
            ctx=ctx,
            code="request_failed",
            message=str(exc),
            resource="midpoint",
            identifier=token_id,
            json_output=json_output,
        )

    emit_command_output(
        ctx=ctx,
        payload=midpoint_quote.model_dump(mode="json"),
        json_output=json_output,
        text=_render_midpoint_block(midpoint_quote),
    )


def run_spread_command(
    *,
    ctx: typer.Context,
    token_id: str,
    json_output: bool,
) -> None:
    """Execute the canonical spread command."""
    try:
        with ClobClient() as client:
            spread_quote = client.get_spread(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            ctx=ctx,
            code="not_found",
            message=str(exc),
            resource="spread",
            identifier=token_id,
            json_output=json_output,
        )
    except ClobClientError as exc:
        emit_cli_error(
            ctx=ctx,
            code="request_failed",
            message=str(exc),
            resource="spread",
            identifier=token_id,
            json_output=json_output,
        )

    emit_command_output(
        ctx=ctx,
        payload=spread_quote.model_dump(mode="json"),
        json_output=json_output,
        text=_render_spread_block(spread_quote),
    )


@app.command("book")
def show_book(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a public order book for a token ID."""
    run_book_command(ctx=ctx, token_id=token_id, json_output=json_output)


@app.command("price")
def show_price(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show public BUY and SELL prices for a token ID."""
    run_price_command(ctx=ctx, token_id=token_id, json_output=json_output)


@app.command("midpoint")
def show_midpoint(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the public midpoint for a token ID."""
    run_midpoint_command(ctx=ctx, token_id=token_id, json_output=json_output)


@app.command("spread")
def show_spread(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the public spread for a token ID."""
    run_spread_command(ctx=ctx, token_id=token_id, json_output=json_output)
