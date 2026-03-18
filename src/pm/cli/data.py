"""Public read-only Polymarket Data API commands."""

from __future__ import annotations

import typer

from pm.cli.support import emit_command_error, emit_command_output
from pm.data import (
    ActivityResponse,
    ClosedPositionsResponse,
    DataClient,
    DataClientError,
    DataNotFoundError,
    DataValidationError,
    HoldersResponse,
    NormalizedActivity,
    NormalizedClosedPosition,
    NormalizedCurrentPosition,
    NormalizedHolder,
    NormalizedHoldingsValue,
    NormalizedOpenInterest,
    NormalizedTrade,
    NormalizedTradedCount,
    PositionsResponse,
    TradesResponse,
)

app = typer.Typer(
    add_completion=False,
    help="Public read-only Data API commands.",
    no_args_is_help=True,
)
USER_OPTION = typer.Option(
    ...,
    "--user",
    help="Public 0x-prefixed EVM wallet address.",
)
MARKET_OPTION = typer.Option(
    ...,
    "--market",
    help="Market slug or 0x-prefixed condition ID.",
)
LIMIT_OPTION = typer.Option(
    20,
    "--limit",
    min=1,
    help="Maximum number of rows to return.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
)


@app.command("trades")
def trades_command(
    ctx: typer.Context,
    user: str = USER_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch public trades for a user."""
    try:
        with DataClient() as client:
            result = client.get_user_trades(user, limit=limit)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_user_error(ctx, exc=exc, user=user, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_trades_response(result),
        local_json_output=json_output,
    )


@app.command("activity")
def activity_command(
    ctx: typer.Context,
    user: str = USER_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch public activity for a user."""
    try:
        with DataClient() as client:
            result = client.get_user_activity(user, limit=limit)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_user_error(ctx, exc=exc, user=user, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_activity_response(result),
        local_json_output=json_output,
    )


@app.command("positions")
def positions_command(
    ctx: typer.Context,
    user: str = USER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch current public positions for a user."""
    try:
        with DataClient() as client:
            result = client.get_current_positions(user)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_user_error(ctx, exc=exc, user=user, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_positions_response(result),
        local_json_output=json_output,
    )


@app.command("closed-positions")
def closed_positions_command(
    ctx: typer.Context,
    user: str = USER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch public closed positions for a user."""
    try:
        with DataClient() as client:
            result = client.get_closed_positions(user)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_user_error(ctx, exc=exc, user=user, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_closed_positions_response(result),
        local_json_output=json_output,
    )


@app.command("holders")
def holders_command(
    ctx: typer.Context,
    market: str = MARKET_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch public holder rows for a market slug or condition ID."""
    try:
        with DataClient() as client:
            result = client.get_holders(market, limit=limit)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_market_error(ctx, exc=exc, market=market, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_holders_response(result),
        local_json_output=json_output,
    )


@app.command("open-interest")
def open_interest_command(
    ctx: typer.Context,
    market: str = MARKET_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch public open interest for a market slug or condition ID."""
    try:
        with DataClient() as client:
            result = client.get_open_interest(market)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_market_error(ctx, exc=exc, market=market, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_open_interest(result),
        local_json_output=json_output,
    )


@app.command("value")
def value_command(
    ctx: typer.Context,
    user: str = USER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch current public holdings value for a user."""
    try:
        with DataClient() as client:
            result = client.get_holdings_value(user)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_user_error(ctx, exc=exc, user=user, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_holdings_value(result),
        local_json_output=json_output,
    )


@app.command("traded")
def traded_command(
    ctx: typer.Context,
    user: str = USER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch public traded-market count for a user."""
    try:
        with DataClient() as client:
            result = client.get_traded_count(user)
    except (DataValidationError, DataNotFoundError, DataClientError) as exc:
        _handle_user_error(ctx, exc=exc, user=user, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_traded_count(result),
        local_json_output=json_output,
    )


def _handle_user_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    user: str,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code=_error_code_for(exc),
        message=str(exc),
        resource="user",
        identifier=user.strip(),
        local_json_output=json_output,
    )


def _handle_market_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    market: str,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code=_error_code_for(exc),
        message=str(exc),
        resource="market",
        identifier=market.strip(),
        local_json_output=json_output,
    )


def _error_code_for(exc: Exception) -> str:
    if isinstance(exc, DataValidationError):
        return "invalid_argument"
    if isinstance(exc, DataNotFoundError):
        return "not_found"
    return "request_failed"


def _format_trades_response(response: TradesResponse) -> str:
    return _format_item_response(
        heading_lines=[f"User: {response.user}", f"Total trades: {response.total}"],
        items=[_format_trade(item) for item in response.items],
    )


def _format_activity_response(response: ActivityResponse) -> str:
    return _format_item_response(
        heading_lines=[f"User: {response.user}", f"Total activity rows: {response.total}"],
        items=[_format_activity(item) for item in response.items],
    )


def _format_positions_response(response: PositionsResponse) -> str:
    return _format_item_response(
        heading_lines=[f"User: {response.user}", f"Open positions: {response.total}"],
        items=[_format_position(item) for item in response.items],
    )


def _format_closed_positions_response(response: ClosedPositionsResponse) -> str:
    return _format_item_response(
        heading_lines=[f"User: {response.user}", f"Closed positions: {response.total}"],
        items=[_format_closed_position(item) for item in response.items],
    )


def _format_holders_response(response: HoldersResponse) -> str:
    return _format_item_response(
        heading_lines=[
            f"Market slug: {response.market_slug or '-'}",
            f"Condition ID: {response.condition_id}",
            f"Holders: {response.total}",
        ],
        items=[_format_holder(item) for item in response.items],
    )


def _format_item_response(*, heading_lines: list[str], items: list[str]) -> str:
    lines = [*heading_lines, "Items:"]
    lines.append("\n\n".join(items) if items else "-")
    return "\n".join(lines)


def _format_trade(item: NormalizedTrade) -> str:
    return "\n".join(
        [
            f"User: {item.user}",
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id or '-'}",
            f"Token ID: {item.token_id or '-'}",
            f"Side: {item.side or '-'}",
            f"Outcome: {item.outcome or '-'}",
            f"Price: {item.price or '-'}",
            f"Size: {item.size or '-'}",
            f"Timestamp: {item.timestamp if item.timestamp is not None else '-'}",
            f"Transaction hash: {item.transaction_hash or '-'}",
        ]
    )


def _format_activity(item: NormalizedActivity) -> str:
    return "\n".join(
        [
            f"User: {item.user}",
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id or '-'}",
            f"Token ID: {item.token_id or '-'}",
            f"Activity type: {item.activity_type}",
            f"Side: {item.side or '-'}",
            f"Outcome: {item.outcome or '-'}",
            f"Price: {item.price or '-'}",
            f"Size: {item.size or '-'}",
            f"USDC size: {item.usdc_size or '-'}",
            f"Timestamp: {item.timestamp if item.timestamp is not None else '-'}",
            f"Transaction hash: {item.transaction_hash or '-'}",
        ]
    )


def _format_position(item: NormalizedCurrentPosition) -> str:
    return "\n".join(
        [
            f"User: {item.user}",
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id or '-'}",
            f"Token ID: {item.token_id or '-'}",
            f"Outcome: {item.outcome or '-'}",
            f"Size: {item.size or '-'}",
            f"Average price: {item.average_price or '-'}",
            f"Initial value: {item.initial_value or '-'}",
            f"Current value: {item.current_value or '-'}",
            f"Cash PnL: {item.cash_pnl or '-'}",
            f"Percent PnL: {item.percent_pnl or '-'}",
        ]
    )


def _format_closed_position(item: NormalizedClosedPosition) -> str:
    return "\n".join(
        [
            f"User: {item.user}",
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id or '-'}",
            f"Token ID: {item.token_id or '-'}",
            f"Outcome: {item.outcome or '-'}",
            f"Average price: {item.average_price or '-'}",
            f"Total bought: {item.total_bought or '-'}",
            f"Realized PnL: {item.realized_pnl or '-'}",
            f"Current price: {item.current_price or '-'}",
            f"Timestamp: {item.timestamp if item.timestamp is not None else '-'}",
        ]
    )


def _format_holder(item: NormalizedHolder) -> str:
    return "\n".join(
        [
            f"Rank: {item.rank if item.rank is not None else '-'}",
            f"Holder address: {item.holder_address}",
            f"Token ID: {item.token_id or '-'}",
            f"Amount: {item.amount}",
            f"Name: {item.name or '-'}",
            f"Pseudonym: {item.pseudonym or '-'}",
            f"Outcome index: {item.outcome_index if item.outcome_index is not None else '-'}",
        ]
    )


def _format_open_interest(item: NormalizedOpenInterest) -> str:
    return "\n".join(
        [
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id}",
            f"Open interest: {item.open_interest}",
        ]
    )


def _format_holdings_value(item: NormalizedHoldingsValue) -> str:
    return "\n".join(
        [
            f"User: {item.user}",
            f"Holdings value: {item.value}",
        ]
    )


def _format_traded_count(item: NormalizedTradedCount) -> str:
    return "\n".join(
        [
            f"User: {item.user}",
            f"Traded markets: {item.traded}",
        ]
    )
