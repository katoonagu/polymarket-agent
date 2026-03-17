"""Public read-only CLOB CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import (
    LOCAL_JSON_OPTION,
    LOCAL_OUTPUT_OPTION,
    emit_cli_error,
    resolve_output_mode,
)
from pm.common import OutputMode, emit_output
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
    help="Read-only public CLOB commands for token IDs discovered from Gamma.",
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
    return "\n".join(
        [
            f"Token ID: {price_quote.token_id}",
            f"Buy Price: {_format_optional(price_quote.buy_price)}",
            f"Sell Price: {_format_optional(price_quote.sell_price)}",
        ],
    )


def _render_midpoint_block(midpoint_quote: NormalizedMidpointQuote) -> str:
    return "\n".join(
        [
            f"Token ID: {midpoint_quote.token_id}",
            f"Midpoint: {midpoint_quote.midpoint}",
        ],
    )


def _render_spread_block(spread_quote: NormalizedSpreadQuote) -> str:
    return "\n".join(
        [
            f"Token ID: {spread_quote.token_id}",
            f"Spread: {spread_quote.spread}",
        ],
    )


def run_book_command(
    *,
    ctx: typer.Context,
    token_id: str,
    output: OutputMode | None,
    json_output: bool,
) -> None:
    """Show a public order book for a token ID."""
    output_mode = resolve_output_mode(ctx, output=output, json_output=json_output)
    try:
        with ClobClient() as client:
            book = client.get_book(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            code="not_found",
            message=str(exc),
            resource="book",
            identifier=token_id,
            output_mode=output_mode,
        )
    except ClobClientError as exc:
        emit_cli_error(
            code="request_failed",
            message=str(exc),
            resource="book",
            identifier=token_id,
            output_mode=output_mode,
        )

    emit_output(
        book.model_dump(mode="json"),
        output_mode=output_mode,
        text=_render_book_block(book),
    )


def run_price_command(
    *,
    ctx: typer.Context,
    token_id: str,
    output: OutputMode | None,
    json_output: bool,
) -> None:
    """Show public BUY and SELL prices for a token ID."""
    output_mode = resolve_output_mode(ctx, output=output, json_output=json_output)
    try:
        with ClobClient() as client:
            price_quote = client.get_prices(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            code="not_found",
            message=str(exc),
            resource="price",
            identifier=token_id,
            output_mode=output_mode,
        )
    except ClobClientError as exc:
        emit_cli_error(
            code="request_failed",
            message=str(exc),
            resource="price",
            identifier=token_id,
            output_mode=output_mode,
        )

    emit_output(
        price_quote.model_dump(mode="json"),
        output_mode=output_mode,
        text=_render_price_block(price_quote),
    )


def run_midpoint_command(
    *,
    ctx: typer.Context,
    token_id: str,
    output: OutputMode | None,
    json_output: bool,
) -> None:
    """Show the public midpoint for a token ID."""
    output_mode = resolve_output_mode(ctx, output=output, json_output=json_output)
    try:
        with ClobClient() as client:
            midpoint_quote = client.get_midpoint(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            code="not_found",
            message=str(exc),
            resource="midpoint",
            identifier=token_id,
            output_mode=output_mode,
        )
    except ClobClientError as exc:
        emit_cli_error(
            code="request_failed",
            message=str(exc),
            resource="midpoint",
            identifier=token_id,
            output_mode=output_mode,
        )

    emit_output(
        midpoint_quote.model_dump(mode="json"),
        output_mode=output_mode,
        text=_render_midpoint_block(midpoint_quote),
    )


def run_spread_command(
    *,
    ctx: typer.Context,
    token_id: str,
    output: OutputMode | None,
    json_output: bool,
) -> None:
    """Show the public spread for a token ID."""
    output_mode = resolve_output_mode(ctx, output=output, json_output=json_output)
    try:
        with ClobClient() as client:
            spread_quote = client.get_spread(token_id)
    except ClobNotFoundError as exc:
        emit_cli_error(
            code="not_found",
            message=str(exc),
            resource="spread",
            identifier=token_id,
            output_mode=output_mode,
        )
    except ClobClientError as exc:
        emit_cli_error(
            code="request_failed",
            message=str(exc),
            resource="spread",
            identifier=token_id,
            output_mode=output_mode,
        )

    emit_output(
        spread_quote.model_dump(mode="json"),
        output_mode=output_mode,
        text=_render_spread_block(spread_quote),
    )


@app.command("book")
def show_book(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a public order book for a token ID."""
    run_book_command(ctx=ctx, token_id=token_id, output=output, json_output=json_output)


@app.command("price")
def show_price(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show public BUY and SELL prices for a token ID."""
    run_price_command(ctx=ctx, token_id=token_id, output=output, json_output=json_output)


@app.command("midpoint")
def show_midpoint(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the public midpoint for a token ID."""
    run_midpoint_command(ctx=ctx, token_id=token_id, output=output, json_output=json_output)


@app.command("spread")
def show_spread(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    output: OutputMode | None = LOCAL_OUTPUT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the public spread for a token ID."""
    run_spread_command(ctx=ctx, token_id=token_id, output=output, json_output=json_output)
