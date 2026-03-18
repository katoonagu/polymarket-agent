"""Authenticated execution planning and order lifecycle CLI commands."""

from __future__ import annotations

import typer

from pm.auth import AuthClientError, AuthValidationError
from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.execution import (
    DryRunResponse,
    DryRunService,
    ExecutionMutationResponse,
    ExecutionValidationError,
    OpenOrdersResponse,
    OrderGetResponse,
    OrderLifecycleService,
    PostOrderResponse,
)

app = typer.Typer(
    add_completion=False,
    help="Authenticated execution planning and order lifecycle commands.",
    no_args_is_help=True,
)
orders_app = typer.Typer(add_completion=False, help="Authenticated order listing commands.")
order_app = typer.Typer(add_completion=False, help="Authenticated single-order commands.")

MARKET_OPTION = typer.Option(..., "--market", help="Market slug or condition id.")
OUTCOME_OPTION = typer.Option(..., "--outcome", help="Outcome side: yes or no.")
SIDE_OPTION = typer.Option(..., "--side", help="Order side: buy or sell.")
PRICE_OPTION = typer.Option(..., "--price", help="Limit price.")
SIZE_OPTION = typer.Option(..., "--size", help="Order size.")


@app.command("dry-run")
def dry_run(
    ctx: typer.Context,
    market: str = MARKET_OPTION,
    outcome: str = OUTCOME_OPTION,
    side: str = SIDE_OPTION,
    price: str = PRICE_OPTION,
    size: str = SIZE_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Build and sign a local order plan without submitting it."""
    try:
        result = DryRunService().dry_run(
            market_ref=market,
            outcome=outcome,
            side=side,
            price=price,
            size=size,
        )
    except ExecutionValidationError as exc:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message=str(exc),
            resource="execution",
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_dry_run(result),
        local_json_output=json_output,
    )


@app.command("post")
def post_order(
    ctx: typer.Context,
    market: str = MARKET_OPTION,
    outcome: str = OUTCOME_OPTION,
    side: str = SIDE_OPTION,
    price: str = PRICE_OPTION,
    size: str = SIZE_OPTION,
    order_type: str = typer.Option("gtc", "--order-type", help="Order type: gtc, gtd, fok."),
    expires_at: str | None = typer.Option(None, "--expires-at", help="Required for gtd."),
    post_only: bool = typer.Option(False, "--post-only", help="Only valid for gtc and gtd."),
    paper: bool = typer.Option(False, "--paper", help="Explicit paper mode. This is the default."),
    live: bool = typer.Option(False, "--live", help="Allow a real order submission."),
    confirm: bool = typer.Option(False, "--confirm", help="Required together with --live."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or submit one order."""
    if paper and live:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="Use either --paper or --live, not both.",
            resource="execution",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    try:
        result = OrderLifecycleService().post(
            market_ref=market,
            outcome=outcome,
            side=side,
            price=price,
            size=size,
            order_type=order_type,
            expires_at=expires_at,
            post_only=post_only,
            live=live,
            confirm=confirm,
        )
    except (AuthValidationError, AuthClientError, ExecutionValidationError) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_post(result),
        local_json_output=json_output,
    )


@orders_app.command("open")
def open_orders(
    ctx: typer.Context,
    market: str | None = typer.Option(None, "--market", help="Condition id filter."),
    token_id: str | None = typer.Option(None, "--token-id", help="Asset id filter."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """List authenticated open orders."""
    try:
        result = OrderLifecycleService().orders_open(market=market, token_id=token_id)
    except (AuthValidationError, AuthClientError, ExecutionValidationError) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_open_orders(result),
        local_json_output=json_output,
    )


@order_app.command("get")
def get_order(
    ctx: typer.Context,
    order_id: str = typer.Option(..., "--order-id", help="Exchange order id."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Get one authenticated order by id."""
    try:
        result = OrderLifecycleService().order_get(order_id=order_id)
    except (AuthValidationError, AuthClientError, ExecutionValidationError) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_order_get(result),
        local_json_output=json_output,
    )


@app.command("cancel")
def cancel(
    ctx: typer.Context,
    order_id: str = typer.Option(..., "--order-id", help="Exchange order id."),
    paper: bool = typer.Option(False, "--paper", help="Explicit paper mode. This is the default."),
    live: bool = typer.Option(False, "--live", help="Allow a real exchange cancellation."),
    confirm: bool = typer.Option(False, "--confirm", help="Required together with --live."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or cancel one order."""
    _guard_mode_flags(ctx, paper=paper, live=live, json_output=json_output)
    try:
        result = OrderLifecycleService().cancel(order_id=order_id, live=live, confirm=confirm)
    except (AuthValidationError, AuthClientError, ExecutionValidationError) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_mutation(result),
        local_json_output=json_output,
    )


@app.command("cancel-all")
def cancel_all(
    ctx: typer.Context,
    paper: bool = typer.Option(False, "--paper", help="Explicit paper mode. This is the default."),
    live: bool = typer.Option(False, "--live", help="Allow real exchange cancellations."),
    confirm: bool = typer.Option(False, "--confirm", help="Required together with --live."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or cancel all open orders."""
    _guard_mode_flags(ctx, paper=paper, live=live, json_output=json_output)
    try:
        result = OrderLifecycleService().cancel_all(live=live, confirm=confirm)
    except (AuthValidationError, AuthClientError, ExecutionValidationError) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_mutation(result),
        local_json_output=json_output,
    )


@app.command("cancel-market")
def cancel_market(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", help="Condition id filter."),
    token_id: str | None = typer.Option(None, "--token-id", help="Optional asset id filter."),
    paper: bool = typer.Option(False, "--paper", help="Explicit paper mode. This is the default."),
    live: bool = typer.Option(False, "--live", help="Allow real exchange cancellations."),
    confirm: bool = typer.Option(False, "--confirm", help="Required together with --live."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or cancel market-scoped orders."""
    _guard_mode_flags(ctx, paper=paper, live=live, json_output=json_output)
    try:
        result = OrderLifecycleService().cancel_market(
            market=market,
            token_id=token_id,
            live=live,
            confirm=confirm,
        )
    except (AuthValidationError, AuthClientError, ExecutionValidationError) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_mutation(result),
        local_json_output=json_output,
    )


app.add_typer(orders_app, name="orders")
app.add_typer(order_app, name="order")


def _guard_mode_flags(
    ctx: typer.Context,
    *,
    paper: bool,
    live: bool,
    json_output: bool,
) -> None:
    if paper and live:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="Use either --paper or --live, not both.",
            resource="execution",
            local_json_output=json_output,
        )
        raise typer.Exit(1)


def _emit_exec_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code="invalid_argument"
        if isinstance(exc, (AuthValidationError, ExecutionValidationError))
        else "request_failed",
        message=str(exc),
        resource="execution",
        local_json_output=json_output,
    )


def _format_dry_run(response: DryRunResponse) -> str:
    fee_rate_text = (
        str(response.market.fee_rate_bps)
        if response.market is not None and response.market.fee_rate_bps is not None
        else "-"
    )
    lines = [
        f"Decision: {response.decision}",
        f"Market ref: {response.request.market_ref}",
        f"Outcome: {response.request.outcome}",
        f"Side: {response.request.side}",
        f"Price: {response.request.price}",
        f"Size: {response.request.size}",
        f"Signer: {response.auth.signer_address or '-'}",
    ]
    if response.market is not None:
        lines.extend(
            [
                f"Market slug: {response.market.market_slug}",
                f"Condition ID: {response.market.condition_id or '-'}",
                f"Token ID: {response.market.token_id or '-'}",
                f"Tick size: {response.market.tick_size or '-'}",
                f"Fee rate bps: {fee_rate_text}",
                f"Active/Closed: {response.market.active}/{response.market.closed}",
            ]
        )
    if response.book_context is not None:
        lines.extend(
            [
                f"Best bid: {response.book_context.best_bid or '-'}",
                f"Best ask: {response.book_context.best_ask or '-'}",
                f"Midpoint: {response.book_context.midpoint or '-'}",
                f"Spread: {response.book_context.spread or '-'}",
            ]
        )
    lines.append("Reasons:")
    lines.extend(f"  {item.section}: {item.status} - {item.message}" for item in response.reasons)
    if response.signed_order is not None:
        lines.append("Signed order payload included in JSON output.")
    return "\n".join(lines)


def _format_post(response: PostOrderResponse) -> str:
    lines = [
        f"Decision: {response.decision}",
        f"Mode: {response.mode}",
        f"Market ref: {response.request.market_ref}",
        f"Outcome: {response.request.outcome}",
        f"Side: {response.request.side}",
        f"Price: {response.request.price}",
        f"Size: {response.request.size}",
        f"Order type: {response.post_context.order_type}",
        f"Post only: {response.post_context.post_only}",
        f"Expires at: {response.post_context.expires_at or '-'}",
        f"Plan ID: {response.plan_id}",
        f"Result ID: {response.result_id or '-'}",
    ]
    if response.market is not None:
        lines.extend(
            [
                f"Market slug: {response.market.market_slug}",
                f"Condition ID: {response.market.condition_id or '-'}",
                f"Token ID: {response.market.token_id or '-'}",
            ]
        )
    lines.append("Reasons:")
    lines.extend(f"  {item.section}: {item.status} - {item.message}" for item in response.reasons)
    if response.live_response is not None:
        lines.append("Live exchange response included in JSON output.")
    elif response.signed_order is not None:
        lines.append("Signed order payload included in JSON output.")
    return "\n".join(lines)


def _format_open_orders(response: OpenOrdersResponse) -> str:
    lines = [
        f"Signer: {response.auth.signer_address or '-'}",
        f"Total open orders: {response.total}",
    ]
    for item in response.items:
        lines.extend(
            [
                "",
                f"Order ID: {item.order_id or '-'}",
                f"Market: {item.market or '-'}",
                f"Asset ID: {item.asset_id or '-'}",
                f"Side: {item.side or '-'}",
                f"Price: {item.price or '-'}",
                f"Size: {item.size or '-'}",
                f"Status: {item.status or '-'}",
            ]
        )
    return "\n".join(lines)


def _format_order_get(response: OrderGetResponse) -> str:
    order = response.order
    return "\n".join(
        [
            f"Signer: {response.auth.signer_address or '-'}",
            f"Order ID: {order.order_id or '-'}",
            f"Market: {order.market or '-'}",
            f"Asset ID: {order.asset_id or '-'}",
            f"Side: {order.side or '-'}",
            f"Price: {order.price or '-'}",
            f"Size: {order.size or '-'}",
            f"Status: {order.status or '-'}",
        ]
    )


def _format_mutation(response: ExecutionMutationResponse) -> str:
    lines = [
        f"Decision: {response.decision}",
        f"Action: {response.action}",
        f"Mode: {response.mode}",
        f"Signer: {response.auth.signer_address or '-'}",
        f"Plan ID: {response.plan_id}",
        f"Result ID: {response.result_id or '-'}",
        f"Order ID: {response.order_id or '-'}",
        f"Market: {response.market or '-'}",
        f"Token ID: {response.token_id or '-'}",
        "Reasons:",
    ]
    lines.extend(f"  {item.section}: {item.status} - {item.message}" for item in response.reasons)
    if response.response is not None:
        lines.append("Exchange response included in JSON output.")
    return "\n".join(lines)
