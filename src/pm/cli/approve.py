"""Authenticated approval inspection and guarded mutation CLI commands."""

from __future__ import annotations

import typer

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
from pm.execution import (
    ApprovalCheckResponse,
    ApprovalSetResponse,
    ExecutionValidationError,
    OrderLifecycleService,
)

app = typer.Typer(
    add_completion=False,
    help="Authenticated approval inspection and guarded approval commands.",
    no_args_is_help=True,
)


def _lifecycle_service(
    *,
    signer: str | None,
    funder: str | None,
    signature_type: int | None,
    chain_id: int | None,
) -> OrderLifecycleService:
    if all(value is None for value in (signer, funder, signature_type, chain_id)):
        return OrderLifecycleService()
    return OrderLifecycleService(
        auth_service=AuthService(
            account_overrides=build_account_overrides(
                signer=signer,
                funder=funder,
                signature_type=signature_type,
                chain_id=chain_id,
            )
        )
    )


@app.command("check")
def approve_check(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show current approval readiness for collateral and conditional tokens."""
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).check_approvals()
    except (AuthValidationError, AuthClientError, AuthProfileStateError) as exc:
        _emit_approve_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_approval_check(result),
        local_json_output=json_output,
    )


@app.command("set")
def approve_set(
    ctx: typer.Context,
    asset: str = typer.Option(..., "--asset", help="Approval asset: usdc or ctf."),
    live: bool = typer.Option(False, "--live", help="Allow a real approval write."),
    confirm: bool = typer.Option(False, "--confirm", help="Required together with --live."),
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Preview or perform an approval write."""
    confirm = resolve_live_confirmation(
        ctx,
        live=live,
        confirm=confirm,
        local_json_output=json_output,
        resource="approve",
        missing_confirm_message="Live approval writes require both --live and --confirm.",
        prompt_message=f"Approve live {asset.strip().lower()} allowance update now?",
        declined_message="Live approval update cancelled.",
    )
    try:
        result = _lifecycle_service(
            signer=signer,
            funder=funder,
            signature_type=signature_type,
            chain_id=chain_id,
        ).set_approval(
            asset=asset,
            live=live,
            confirm=confirm,
        )
    except (
        AuthValidationError,
        AuthClientError,
        AuthProfileStateError,
        ExecutionValidationError,
    ) as exc:
        _emit_approve_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_approval_set(result),
        local_json_output=json_output,
    )


def _emit_approve_error(
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
            else "invalid_argument"
            if isinstance(exc, (AuthValidationError, ExecutionValidationError))
            else "request_failed"
        ),
        message=str(exc),
        resource="approve",
        local_json_output=json_output,
    )


def _format_approval_check(response: ApprovalCheckResponse) -> str:
    lines = [
        f"Signer: {response.auth.signer_address or '-'}",
        f"Funder: {response.auth.funder_address or '-'}",
        f"Total assets: {response.total}",
    ]
    for item in response.items:
        lines.extend(
            [
                "",
                f"Asset: {item.asset}",
                f"Asset type: {item.asset_type}",
                f"Target contract: {item.target_contract_address or '-'}",
                f"Exchange address: {item.exchange_address or '-'}",
                f"Ready: {item.ready}",
                f"Balance: {item.balance_view.balance or '-'}",
                f"Allowance: {item.balance_view.allowance or '-'}",
            ]
        )
    return "\n".join(lines)


def _format_approval_set(response: ApprovalSetResponse) -> str:
    lines = [
        f"Decision: {response.decision}",
        f"Mode: {response.mode}",
        f"Asset: {response.request.asset}",
        f"Signer: {response.auth.signer_address or '-'}",
        f"Plan ID: {response.plan_id}",
        f"Result ID: {response.result_id or '-'}",
    ]
    if response.asset_status is not None:
        lines.extend(
            [
                f"Target contract: {response.asset_status.target_contract_address or '-'}",
                f"Exchange address: {response.asset_status.exchange_address or '-'}",
                f"Balance: {response.asset_status.balance_view.balance or '-'}",
                f"Allowance: {response.asset_status.balance_view.allowance or '-'}",
            ]
        )
    lines.append("Reasons:")
    lines.extend(f"  {item.section}: {item.status} - {item.message}" for item in response.reasons)
    if response.live_response is not None:
        lines.append("Live approval response included in JSON output.")
    return "\n".join(lines)
