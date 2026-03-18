"""Public read-only CLOB CLI commands."""

from __future__ import annotations

import typer

<<<<<<< HEAD
from pm.cli.support import LOCAL_JSON_OPTION, emit_cli_error, emit_command_output
=======
from pm.cli.support import emit_command_error, emit_command_output
>>>>>>> feat/02a-python-scaffold
from pm.market import (
    ClobClient,
    ClobClientError,
    ClobNotFoundError,
    NormalizedBook,
<<<<<<< HEAD
    NormalizedBookLevel,
=======
>>>>>>> feat/02a-python-scaffold
    NormalizedMidpointQuote,
    NormalizedPriceQuote,
    NormalizedSpreadQuote,
)

app = typer.Typer(
    add_completion=False,
<<<<<<< HEAD
    help="Public read-only CLOB commands for books, prices, midpoint, and spread.",
=======
    help="Public read-only CLOB commands.",
>>>>>>> feat/02a-python-scaffold
    no_args_is_help=True,
)
TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
<<<<<<< HEAD
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
=======
    help="Polymarket token ID returned by market discovery commands.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
)


@app.command("book")
def book_command(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch the public order book for a token ID."""
    _run_book(ctx, token_id=token_id, json_output=json_output)


@app.command("price")
def price_command(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch public buy and sell prices for a token ID."""
    _run_price(ctx, token_id=token_id, json_output=json_output)


@app.command("midpoint")
def midpoint_command(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = JSON_OPTION,
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
    json_output: bool = JSON_OPTION,
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
>>>>>>> feat/02a-python-scaffold
    try:
        with ClobClient() as client:
            book = client.get_book(token_id)
    except ClobNotFoundError as exc:
<<<<<<< HEAD
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
=======
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
>>>>>>> feat/02a-python-scaffold
