"""Read-only public market and crypto streaming CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.market import GammaNotFoundError
from pm.stream import (
    CryptoStreamResponse,
    MarketStreamResponse,
    MarketWatchStreamResponse,
    RecurringStreamResponse,
    StreamClientError,
    StreamService,
    StreamStateError,
    StreamValidationError,
)

app = typer.Typer(
    add_completion=False,
    help="Bounded read-only public market and crypto stream commands.",
    no_args_is_help=True,
)

TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
    help="Polymarket token ID to subscribe to on the public market websocket.",
)
SECONDS_OPTION = typer.Option(
    ...,
    "--seconds",
    min=1,
    help="Bounded session duration in seconds.",
)
MAX_EVENTS_OPTION = typer.Option(
    None,
    "--max-events",
    min=1,
    help="Optional hard cap on captured normalized events.",
)
SYMBOL_OPTION = typer.Option(
    ...,
    "--symbol",
    help="Crypto base asset, for example BTC, ETH, or SOL.",
)
SOURCE_OPTION = typer.Option(
    ...,
    "--source",
    help="Public RTDS source: binance or chainlink.",
)
SLUG_OPTION = typer.Option(
    ...,
    "--slug",
    help="Market slug resolved through public Gamma discovery.",
)
QUERY_OPTION = typer.Option(
    ...,
    "--query",
    help="Recurring market discovery query.",
)
INTERVAL_OPTION = typer.Option(
    ...,
    "--interval",
    help="Recurring interval. Supported values: 5m, 15m, 1h.",
)


@app.command("market")
def stream_market(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    seconds: int = SECONDS_OPTION,
    max_events: int | None = MAX_EVENTS_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Run a bounded public market websocket session for one token."""
    try:
        result = StreamService().stream_market(token_id, seconds=seconds, max_events=max_events)
    except (StreamValidationError, StreamClientError, StreamStateError) as exc:
        _emit_stream_error(
            ctx,
            exc=exc,
            resource="stream",
            identifier=token_id.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_market_stream(result),
        local_json_output=json_output,
    )


@app.command("crypto")
def stream_crypto(
    ctx: typer.Context,
    symbol: str = SYMBOL_OPTION,
    source: str = SOURCE_OPTION,
    seconds: int = SECONDS_OPTION,
    max_events: int | None = MAX_EVENTS_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Run a bounded public RTDS crypto price session."""
    try:
        result = StreamService().stream_crypto(
            symbol,
            source=source,
            seconds=seconds,
            max_events=max_events,
        )
    except (StreamValidationError, StreamClientError, StreamStateError) as exc:
        _emit_stream_error(
            ctx,
            exc=exc,
            resource="stream",
            identifier=f"{symbol.strip()}:{source.strip()}",
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_crypto_stream(result),
        local_json_output=json_output,
    )


@app.command("watch")
def stream_watch(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    seconds: int = SECONDS_OPTION,
    max_events: int | None = MAX_EVENTS_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Run a bounded public market websocket session across a market's token IDs."""
    try:
        result = StreamService().stream_watch(slug, seconds=seconds, max_events=max_events)
    except (GammaNotFoundError, StreamValidationError, StreamClientError, StreamStateError) as exc:
        _emit_stream_error(
            ctx,
            exc=exc,
            resource="market",
            identifier=slug.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_watch_stream(result),
        local_json_output=json_output,
    )


@app.command("recurring")
def stream_recurring(
    ctx: typer.Context,
    query: str = QUERY_OPTION,
    interval: str = INTERVAL_OPTION,
    seconds: int = SECONDS_OPTION,
    max_events: int | None = MAX_EVENTS_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Run a bounded recurring market stream plus Binance RTDS context session."""
    try:
        result = StreamService().stream_recurring(
            query,
            interval=interval,
            seconds=seconds,
            max_events=max_events,
        )
    except (StreamValidationError, StreamClientError, StreamStateError) as exc:
        _emit_stream_error(
            ctx,
            exc=exc,
            resource="recurring",
            identifier=interval.strip().lower(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_recurring_stream(result),
        local_json_output=json_output,
    )


def _emit_stream_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    resource: str,
    identifier: str | None,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code=_stream_error_code(exc),
        message=str(exc),
        resource=resource,
        identifier=identifier,
        local_json_output=json_output,
    )


def _stream_error_code(exc: Exception) -> str:
    if isinstance(exc, GammaNotFoundError):
        return "not_found"
    if isinstance(exc, StreamValidationError):
        return "invalid_argument"
    if isinstance(exc, StreamStateError):
        return "state_error"
    return "request_failed"


def _format_market_stream(response: MarketStreamResponse) -> str:
    return "\n".join(
        [
            f"Token ID: {response.summary.token_id}",
            f"Duration: {response.session.duration_seconds}s",
            f"Captured events: {response.session.captured_event_count}",
            f"Reconnects: {response.session.reconnect_count}",
            f"Best bid: {response.summary.latest_best_bid or '-'}",
            f"Best ask: {response.summary.latest_best_ask or '-'}",
            f"Midpoint: {response.summary.latest_midpoint or '-'}",
            f"Spread: {response.summary.latest_spread or '-'}",
            f"Last trade price: {response.summary.latest_last_trade_price or '-'}",
            f"Tick size: {response.summary.latest_tick_size or '-'}",
        ]
    )


def _format_crypto_stream(response: CryptoStreamResponse) -> str:
    return "\n".join(
        [
            f"Symbol: {response.summary.symbol}",
            f"Source: {response.summary.source}",
            f"Duration: {response.session.duration_seconds}s",
            f"Captured events: {response.session.captured_event_count}",
            f"Reconnects: {response.session.reconnect_count}",
            f"Latest value: {response.summary.latest_value or '-'}",
            f"First timestamp: {response.summary.first_timestamp or '-'}",
            f"Last timestamp: {response.summary.last_timestamp or '-'}",
        ]
    )


def _format_watch_stream(response: MarketWatchStreamResponse) -> str:
    lines = [
        f"Market slug: {response.summary.market_slug}",
        f"Condition ID: {response.summary.condition_id or '-'}",
        f"Active: {response.summary.active}",
        f"Closed: {response.summary.closed}",
        f"Aggregate event count: {response.summary.aggregate_event_count}",
        "Tokens:",
    ]
    if response.summary.tokens:
        for token in response.summary.tokens:
            lines.extend(
                [
                    f"  Token ID: {token.token_id}",
                    f"    Outcome: {token.outcome or '-'}",
                    f"    Event count: {token.event_count}",
                    f"    Best bid: {token.latest_best_bid or '-'}",
                    f"    Best ask: {token.latest_best_ask or '-'}",
                    f"    Midpoint: {token.latest_midpoint or '-'}",
                    f"    Spread: {token.latest_spread or '-'}",
                ]
            )
    else:
        lines.append("  -")
    return "\n".join(lines)


def _format_recurring_stream(response: RecurringStreamResponse) -> str:
    lines = [
        f"Recurring market: {response.summary.recurring_market.market_slug}",
        f"Interval: {response.summary.recurring_market.matched_interval}",
        f"Merged event count: {response.summary.merged_event_count}",
    ]
    if response.summary.market is not None:
        lines.extend(
            [
                f"Market aggregate event count: {response.summary.market.aggregate_event_count}",
                f"Market active: {response.summary.market.active}",
                f"Market closed: {response.summary.market.closed}",
            ]
        )
    else:
        lines.extend(["Market aggregate event count: -", "Market active: -", "Market closed: -"])
    if response.summary.crypto is not None:
        lines.extend(
            [
                f"Crypto symbol: {response.summary.crypto.symbol}",
                f"Crypto latest value: {response.summary.crypto.latest_value or '-'}",
            ]
        )
    else:
        lines.extend(["Crypto symbol: -", "Crypto latest value: -"])
    if response.errors:
        lines.append("Warnings:")
        lines.extend(
            f"  {error.section}: {error.code} - {error.message}"
            for error in response.errors
        )
    return "\n".join(lines)
