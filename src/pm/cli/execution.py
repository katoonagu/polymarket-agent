"""Authenticated dry-run execution CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.execution import DryRunResponse, DryRunService, ExecutionValidationError

app = typer.Typer(
    add_completion=False,
    help="Authenticated non-live execution planning commands.",
    no_args_is_help=True,
)

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
                "Active/Closed: "
                f"{response.market.active}/{response.market.closed}",
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
