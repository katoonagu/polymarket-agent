"""Public read-only CLOB CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.market import (
    ClobClient,
    ClobClientError,
    ClobNotFoundError,
    NormalizedBook,
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

app = typer.Typer(
    add_completion=False,
    help="Public read-only CLOB commands.",
    no_args_is_help=True,
)
TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
    help="Polymarket token ID returned by market discovery commands.",
)


@app.command("book")
def book_command(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Fetch the public order book for a token ID."""
    _run_book(ctx, token_id=token_id, json_output=json_output)


@app.command("price")
def price_command(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Fetch public buy and sell prices for a token ID."""
    _run_price(ctx, token_id=token_id, json_output=json_output)


@app.command("midpoint")
def midpoint_command(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Fetch the public midpoint for a token ID."""
    try:
        with ClobClient() as client:
            midpoint = client.get_midpoint(token_id)
    except ClobNotFoundError as exc:
        _handle_clob_error(
            ctx,
            code="not_found",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except ClobClientError as exc:
        _handle_clob_error(
            ctx,
            code="request_failed",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        midpoint.model_dump(mode="json"),
        text=_format_midpoint(midpoint),
        local_json_output=json_output,
    )


@app.command("spread")
def spread_command(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Fetch the public spread for a token ID."""
    try:
        with ClobClient() as client:
            spread = client.get_spread(token_id)
    except ClobNotFoundError as exc:
        _handle_clob_error(
            ctx,
            code="not_found",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except ClobClientError as exc:
        _handle_clob_error(
            ctx,
            code="request_failed",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        spread.model_dump(mode="json"),
        text=_format_spread(spread),
        local_json_output=json_output,
    )


def _run_book(
    ctx: typer.Context,
    *,
    token_id: str,
    json_output: bool,
) -> None:
    try:
        with ClobClient() as client:
            book = client.get_book(token_id)
    except ClobNotFoundError as exc:
        _handle_clob_error(
            ctx,
            code="not_found",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except ClobClientError as exc:
        _handle_clob_error(
            ctx,
            code="request_failed",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        book.model_dump(mode="json"),
        text=_format_book(book),
        local_json_output=json_output,
    )


def _run_price(
    ctx: typer.Context,
    *,
    token_id: str,
    json_output: bool,
) -> None:
    try:
        with ClobClient() as client:
            quote = client.get_prices(token_id)
    except ClobNotFoundError as exc:
        _handle_clob_error(
            ctx,
            code="not_found",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except ClobClientError as exc:
        _handle_clob_error(
            ctx,
            code="request_failed",
            message=str(exc),
            token_id=token_id,
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        quote.model_dump(mode="json"),
        text=_format_price(quote),
        local_json_output=json_output,
    )


def _handle_clob_error(
    ctx: typer.Context,
    *,
    code: str,
    message: str,
    token_id: str,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code=code,
        message=message,
        resource="token",
        identifier=token_id,
        local_json_output=json_output,
    )


def _format_book(book: NormalizedBook) -> str:
    lines = [
        f"Token ID: {book.token_id}",
        f"Tick size: {book.tick_size or '-'}",
        f"Min order size: {book.min_order_size or '-'}",
        "Bids:",
    ]
    if book.bids:
        lines.extend(f"  {level.price} x {level.size}" for level in book.bids)
    else:
        lines.append("  -")

    lines.append("Asks:")
    if book.asks:
        lines.extend(f"  {level.price} x {level.size}" for level in book.asks)
    else:
        lines.append("  -")

    return "\n".join(lines)


def _format_price(quote: NormalizedPriceQuote) -> str:
    return "\n".join(
        [
            f"Token ID: {quote.token_id}",
            f"Buy price: {quote.buy_price or '-'}",
            f"Sell price: {quote.sell_price or '-'}",
        ]
    )


def _format_midpoint(midpoint: NormalizedMidpointQuote) -> str:
    return "\n".join(
        [
            f"Token ID: {midpoint.token_id}",
            f"Midpoint: {midpoint.midpoint}",
        ]
    )


def _format_spread(spread: NormalizedSpreadQuote) -> str:
    return "\n".join(
        [
            f"Token ID: {spread.token_id}",
            f"Spread: {spread.spread}",
        ]
    )
