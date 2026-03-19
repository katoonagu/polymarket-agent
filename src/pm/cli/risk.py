"""Guarded risk policy CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.risk import (
    RiskInitDefaultsResponse,
    RiskPolicy,
    RiskPolicyService,
    RiskShowResponse,
    RiskStateError,
)

app = typer.Typer(
    add_completion=False,
    help="Guarded strategy dispatch risk policy commands.",
    no_args_is_help=True,
)


@app.command("show")
def show(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the effective risk policy set."""
    try:
        result = RiskPolicyService().show()
    except RiskStateError as exc:
        _emit_risk_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_risk_show(result),
        local_json_output=json_output,
    )


@app.command("init-defaults")
def init_defaults(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Persist the seeded default risk policy file once."""
    try:
        result = RiskPolicyService().init_defaults()
    except RiskStateError as exc:
        _emit_risk_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_risk_init(result),
        local_json_output=json_output,
    )


def _emit_risk_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code="state_error",
        message=str(exc),
        resource="risk",
        local_json_output=json_output,
    )


def _format_risk_show(response: RiskShowResponse) -> str:
    lines = [
        f"Persisted: {response.persisted}",
        f"Strategies: {response.total}",
        "",
        _format_policy(response.default_policy, label="Default policy"),
    ]
    for policy in response.strategies:
        lines.extend(["", _format_policy(policy)])
    return "\n".join(lines)


def _format_risk_init(response: RiskInitDefaultsResponse) -> str:
    lines = [
        f"Initialized: {response.initialized}",
        f"Persisted: {response.persisted}",
        f"Strategies: {response.total}",
    ]
    for policy in response.strategies:
        lines.extend(["", _format_policy(policy)])
    return "\n".join(lines)


def _format_policy(policy: RiskPolicy, *, label: str | None = None) -> str:
    header = label or f"Strategy: {policy.strategy_name}"
    if label is None:
        header = f"Strategy: {policy.strategy_name}"
    return "\n".join(
        [
            header,
            f"  Dispatch enabled: {policy.dispatch_enabled}",
            f"  Max drift pct: {policy.max_drift_pct}",
            f"  Max spread pct: {policy.max_spread_pct}",
            f"  Max size USDC per order: {policy.max_size_usdc_per_order}",
            f"  Max exposure USDC per market: {policy.max_exposure_usdc_per_market}",
            f"  Max exposure USDC per strategy: {policy.max_exposure_usdc_per_strategy}",
            f"  Require market open: {policy.require_market_open}",
            f"  Require balance ready: {policy.require_balance_ready}",
            f"  Require allowance ready: {policy.require_allowance_ready}",
        ]
    )
