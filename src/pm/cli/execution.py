"""Authenticated execution planning and order lifecycle CLI commands."""

from __future__ import annotations

import typer
from rich.console import RenderableType

from pm.auth import AuthClientError, AuthProfileStateError, AuthService, AuthValidationError
from pm.cli.support import (
    CHAIN_ID_OPTION,
    FUNDER_OPTION,
    LOCAL_JSON_OPTION,
    SIGNATURE_TYPE_OPTION,
    SIGNER_OPTION,
    build_account_overrides,
    emit_command_error,
    emit_command_output,
    resolve_live_confirmation,
)
from pm.common.tables import empty_message, row_table, section_panel, shorten_identifier
from pm.execution import (
    DryRunResponse,
    DryRunService,
    ExecutionEventsResponse,
    ExecutionMutationResponse,
    ExecutionNotFoundError,
    ExecutionReconciliationResponse,
    ExecutionStateError,
    ExecutionValidationError,
    ExecutionWatchResponse,
    ExecutionWatchService,
    OpenOrdersResponse,
    OrderGetResponse,
    OrderLifecycleService,
    OrderWaitResponse,
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


def _auth_service(
    *,
    signer: str | None,
    funder: str | None,
    signature_type: int | None,
    chain_id: int | None,
) -> AuthService:
    return AuthService(
        account_overrides=build_account_overrides(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        )
    )


def _has_auth_overrides(
    *,
    signer: str | None,
    funder: str | None,
    signature_type: int | None,
    chain_id: int | None,
) -> bool:
    return any(value is not None for value in (signer, funder, signature_type, chain_id))


def _dry_run_service(
    *,
    signer: str | None,
    funder: str | None,
    signature_type: int | None,
    chain_id: int | None,
) -> DryRunService:
    if not _has_auth_overrides(
        signer=signer,
        funder=funder,
        signature_type=signature_type,
        chain_id=chain_id,
    ):
        return DryRunService()
    return DryRunService(
        auth_service=_auth_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        )
    )


def _lifecycle_service(
    *,
    signer: str | None,
    funder: str | None,
    signature_type: int | None,
    chain_id: int | None,
) -> OrderLifecycleService:
    if not _has_auth_overrides(
        signer=signer,
        funder=funder,
        signature_type=signature_type,
        chain_id=chain_id,
    ):
        return OrderLifecycleService()
    return OrderLifecycleService(
        auth_service=_auth_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        )
    )


def _watch_service(
    *,
    signer: str | None,
    funder: str | None,
    signature_type: int | None,
    chain_id: int | None,
) -> ExecutionWatchService:
    if not _has_auth_overrides(
        signer=signer,
        funder=funder,
        signature_type=signature_type,
        chain_id=chain_id,
    ):
        return ExecutionWatchService()
    return ExecutionWatchService(
        auth_service=_auth_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        )
    )


@app.command("dry-run")
def dry_run(
    ctx: typer.Context,
    market: str = MARKET_OPTION,
    outcome: str = OUTCOME_OPTION,
    side: str = SIDE_OPTION,
    price: str = PRICE_OPTION,
    size: str = SIZE_OPTION,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Build and sign a local order plan without submitting it."""
    try:
        result = _dry_run_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).dry_run(
            market_ref=market,
            outcome=outcome,
            side=side,
            price=price,
            size=size,
        )
    except (ExecutionValidationError, AuthProfileStateError) as exc:
        emit_command_error(
            ctx,
            code="state_error" if isinstance(exc, AuthProfileStateError) else "invalid_argument",
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
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
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
    confirm = resolve_live_confirmation(
        ctx,
        live=live,
        confirm=confirm,
        local_json_output=json_output,
        resource="execution",
        missing_confirm_message="Live order posting requires both --live and --confirm.",
        prompt_message="Post this order through the live guarded execution path now?",
        declined_message="Live order post cancelled.",
    )
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).post(
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
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionValidationError,
    ) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_post(result),
        local_json_output=json_output,
    )


@app.command("watch")
def watch(
    ctx: typer.Context,
    market: str | None = typer.Option(None, "--market", help="Condition id filter."),
    seconds: int = typer.Option(10, "--seconds", help="Bounded watch duration in seconds."),
    max_events: int | None = typer.Option(None, "--max-events", help="Optional event cap."),
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Run one bounded authenticated execution-watch session."""
    try:
        result = _watch_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).watch(
            market=market,
            seconds=seconds,
            max_events=max_events,
        )
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionNotFoundError,
        ExecutionStateError,
        ExecutionValidationError,
    ) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_watch(result),
        local_json_output=json_output,
    )


@orders_app.command("open")
def open_orders(
    ctx: typer.Context,
    market: str | None = typer.Option(None, "--market", help="Condition id filter."),
    token_id: str | None = typer.Option(None, "--token-id", help="Asset id filter."),
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """List authenticated open orders."""
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).orders_open(market=market, token_id=token_id)
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionValidationError,
    ) as exc:
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
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Get one authenticated order by id."""
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).order_get(order_id=order_id)
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionValidationError,
    ) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_order_get(result),
        local_json_output=json_output,
    )


@order_app.command("wait")
def wait_for_order(
    ctx: typer.Context,
    order_id: str = typer.Option(..., "--order-id", help="Exchange order id."),
    seconds: int = typer.Option(..., "--seconds", help="Bounded wait duration in seconds."),
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Observe one order until a terminal event or timeout."""
    try:
        result = _watch_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).wait_for_order(order_id=order_id, seconds=seconds)
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionNotFoundError,
        ExecutionStateError,
        ExecutionValidationError,
    ) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_order_wait(result),
        local_json_output=json_output,
    )


@app.command("events")
def events(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", help="Maximum number of events to return."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """List recent persisted execution-watch events."""
    try:
        result = ExecutionWatchService().list_events(limit=limit)
    except (ExecutionStateError, ExecutionValidationError) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_events(result),
        renderable=_render_events(result),
        local_json_output=json_output,
    )


@app.command("reconcile")
def reconcile(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Compare recent websocket execution events against authenticated REST views."""
    try:
        result = _watch_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).reconcile()
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionNotFoundError,
        ExecutionStateError,
        ExecutionValidationError,
    ) as exc:
        _emit_exec_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_reconcile(result),
        local_json_output=json_output,
    )


@app.command("cancel")
def cancel(
    ctx: typer.Context,
    order_id: str = typer.Option(..., "--order-id", help="Exchange order id."),
    paper: bool = typer.Option(False, "--paper", help="Explicit paper mode. This is the default."),
    live: bool = typer.Option(False, "--live", help="Allow a real exchange cancellation."),
    confirm: bool = typer.Option(False, "--confirm", help="Required together with --live."),
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or cancel one order."""
    confirm = _guard_mode_flags(
        ctx,
        paper=paper,
        live=live,
        confirm=confirm,
        json_output=json_output,
        missing_confirm_message="Live order cancellation requires both --live and --confirm.",
        prompt_message="Cancel this order through the live guarded execution path now?",
        declined_message="Live order cancellation cancelled.",
    )
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).cancel(order_id=order_id, live=live, confirm=confirm)
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionValidationError,
    ) as exc:
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
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or cancel all open orders."""
    confirm = _guard_mode_flags(
        ctx,
        paper=paper,
        live=live,
        confirm=confirm,
        json_output=json_output,
        missing_confirm_message="Live order cancellation requires both --live and --confirm.",
        prompt_message="Cancel all open orders through the live guarded execution path now?",
        declined_message="Live order cancellation cancelled.",
    )
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).cancel_all(live=live, confirm=confirm)
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionValidationError,
    ) as exc:
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
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or cancel market-scoped orders."""
    confirm = _guard_mode_flags(
        ctx,
        paper=paper,
        live=live,
        confirm=confirm,
        json_output=json_output,
        missing_confirm_message="Live order cancellation requires both --live and --confirm.",
        prompt_message="Cancel market-scoped orders through the live guarded execution path now?",
        declined_message="Live order cancellation cancelled.",
    )
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).cancel_market(
            market=market,
            token_id=token_id,
            live=live,
            confirm=confirm,
        )
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionValidationError,
    ) as exc:
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
    confirm: bool,
    json_output: bool,
    missing_confirm_message: str,
    prompt_message: str,
    declined_message: str,
) -> bool:
    if paper and live:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="Use either --paper or --live, not both.",
            resource="execution",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    return resolve_live_confirmation(
        ctx,
        live=live,
        confirm=confirm,
        local_json_output=json_output,
        resource="execution",
        missing_confirm_message=missing_confirm_message,
        prompt_message=prompt_message,
        declined_message=declined_message,
    )


def _emit_exec_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code=(
            "state_error"
            if isinstance(exc, AuthProfileStateError)
            else
            "not_found"
            if isinstance(exc, ExecutionNotFoundError)
            else "invalid_argument"
            if isinstance(exc, (AuthValidationError, ExecutionValidationError))
            else "request_failed"
        ),
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


def _format_watch(response: ExecutionWatchResponse) -> str:
    lines = [
        f"Session ID: {response.session.session_id}",
        f"Duration: {response.session.duration_seconds}s",
        f"Requested: {response.session.requested_seconds}s",
        f"Captured events: {response.session.captured_event_count}",
        f"Reconnects: {response.summary.reconnect_count}",
        (
            "Watched conditions: "
            + (", ".join(response.summary.watched_condition_ids) or "-")
        ),
        f"Distinct orders: {response.summary.distinct_order_count}",
        "Event counts:",
    ]
    lines.extend(f"  {key}: {value}" for key, value in response.summary.event_counts.items())
    lines.append("Trade statuses:")
    lines.extend(
        f"  {key}: {value}" for key, value in response.summary.trade_status_counts.items()
    )
    if response.errors:
        lines.append("Errors:")
        lines.extend(f"  {item.section}: {item.code} - {item.message}" for item in response.errors)
    return "\n".join(lines)


def _format_order_wait(response: OrderWaitResponse) -> str:
    lines = [
        f"Order ID: {response.order_id}",
        f"Condition ID: {response.condition_id or '-'}",
        f"Timed out: {response.timed_out}",
        f"Terminal: {response.terminal}",
        f"Terminal outcome: {response.terminal_outcome or '-'}",
        f"Captured events: {len(response.events)}",
        f"Reconnects: {response.session.reconnect_count}",
    ]
    if response.final_order is not None:
        lines.extend(
            [
                f"Final REST status: {response.final_order.status or '-'}",
                f"Final REST market: {response.final_order.market or '-'}",
            ]
        )
    if response.final_event is not None:
        lines.extend(
            [
                f"Final event type: {response.final_event.event_type}",
                f"Final trade status: {response.final_event.trade_status or '-'}",
            ]
        )
    if response.errors:
        lines.append("Errors:")
        lines.extend(f"  {item.section}: {item.code} - {item.message}" for item in response.errors)
    return "\n".join(lines)


def _format_events(response: ExecutionEventsResponse) -> str:
    lines = [f"Total events: {response.total}"]
    for item in response.items:
        lines.extend(
            [
                "",
                f"Captured at: {item.captured_at}",
                f"Order ID: {item.order_id or '-'}",
                f"Condition ID: {item.condition_id or '-'}",
                f"Event type: {item.event_type}",
                f"Trade status: {item.trade_status or '-'}",
                f"Status: {item.status or '-'}",
                f"Price: {item.price or '-'}",
                f"Size: {item.size or '-'}",
            ]
        )
    return "\n".join(lines)


def _render_events(response: ExecutionEventsResponse) -> RenderableType:
    if not response.items:
        return section_panel(
            "Execution Events",
            empty_message("No persisted execution events."),
        )
    return section_panel(
        "Execution Events",
        row_table(
            title="Execution Events",
            columns=[
                "Captured",
                "Order ID",
                "Condition",
                "Event",
                "Trade",
                "Status",
                "Price",
                "Size",
            ],
            rows=[
                [
                    item.captured_at,
                    shorten_identifier(item.order_id),
                    shorten_identifier(item.condition_id),
                    item.event_type,
                    item.trade_status or "-",
                    item.status or "-",
                    item.price or "-",
                    item.size or "-",
                ]
                for item in response.items
            ],
        ),
    )


def _format_reconcile(response: ExecutionReconciliationResponse) -> str:
    lines = [
        f"Reconciliation ID: {response.reconciliation_id}",
        f"Created at: {response.created_at}",
        f"Window events: {response.summary.window_event_count}",
        f"Orders: {response.summary.total_orders}",
        f"Consistent open: {response.summary.consistent_open}",
        f"Consistent closed: {response.summary.consistent_closed}",
        f"Inconclusive: {response.summary.inconclusive}",
        f"Mismatch: {response.summary.mismatch}",
    ]
    for item in response.items:
        lines.extend(
            [
                "",
                f"Order ID: {item.order_id}",
                f"Classification: {item.classification}",
                f"Latest event: {item.latest_event_type}",
                f"Latest trade status: {item.latest_trade_status or '-'}",
                f"Message: {item.message}",
            ]
        )
    if response.errors:
        lines.append("Errors:")
        lines.extend(f"  {item.section}: {item.code} - {item.message}" for item in response.errors)
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
