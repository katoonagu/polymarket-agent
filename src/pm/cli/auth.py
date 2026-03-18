"""Authenticated account inspection CLI commands."""

from __future__ import annotations

import typer

from pm.auth import (
    AuthClientError,
    AuthDeriveApiKeyResponse,
    AuthService,
    AuthShowResponse,
    AuthValidationError,
    BalanceAllowanceView,
)
from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output

app = typer.Typer(
    add_completion=False,
    help="Authenticated non-live account inspection commands.",
    no_args_is_help=True,
)


@app.command("show")
def auth_show(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the current authenticated environment context."""
    with AuthService() as service:
        result = service.show()

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_auth_show(result),
        local_json_output=json_output,
    )


@app.command("derive-api-key")
def derive_api_key(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Derive ephemeral Level 2 API credentials without persisting them."""
    try:
        with AuthService() as service:
            result = service.derive_api_key()
    except (AuthValidationError, AuthClientError) as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_api_creds(result),
        local_json_output=json_output,
    )


@app.command("balances")
def balances(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show authenticated collateral balance information."""
    try:
        with AuthService() as service:
            result = service.balances()
    except (AuthValidationError, AuthClientError) as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_balance_view("Balance", result.auth.signer_address, result.balance_view),
        local_json_output=json_output,
    )


@app.command("allowances")
def allowances(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show authenticated collateral allowance information."""
    try:
        with AuthService() as service:
            result = service.allowances()
    except (AuthValidationError, AuthClientError) as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_balance_view(
            "Allowance", result.auth.signer_address, result.allowance_view
        ),
        local_json_output=json_output,
    )


def _emit_auth_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code="invalid_argument" if isinstance(exc, AuthValidationError) else "request_failed",
        message=str(exc),
        resource="auth",
        local_json_output=json_output,
    )


def _format_auth_show(response: AuthShowResponse) -> str:
    lines = [
        f"Signer: {response.auth.signer_address or '-'}",
        f"Funder: {response.auth.funder_address or '-'}",
        f"Signature type: {response.auth.signature_type_name or '-'}",
        f"CLOB host: {response.auth.clob_host}",
        f"Chain ID: {response.auth.chain_id if response.auth.chain_id is not None else '-'}",
        f"Private key present: {response.auth.private_key_present}",
        f"API-key derivation possible: {response.auth.api_key_derivation_possible}",
    ]
    if response.errors:
        lines.append("Warnings:")
        lines.extend(
            f"  {item.section}: {item.code} - {item.message}" for item in response.errors
        )
    return "\n".join(lines)


def _format_api_creds(response: AuthDeriveApiKeyResponse) -> str:
    return "\n".join(
        [
            f"Signer: {response.auth.signer_address or '-'}",
            f"API key: {response.api_credentials.api_key}",
            f"API secret: {response.api_credentials.api_secret}",
            f"API passphrase: {response.api_credentials.api_passphrase}",
        ]
    )


def _format_balance_view(
    label: str,
    signer: str | None,
    view: BalanceAllowanceView,
) -> str:
    return "\n".join(
        [
            f"Signer: {signer or '-'}",
            f"{label}: {view.balance or view.allowance or '-'}",
            f"Asset type: {view.asset_type}",
            f"Token ID: {view.token_id or '-'}",
            f"Signature type: {view.signature_type}",
            f"Balance: {view.balance or '-'}",
            f"Allowance: {view.allowance or '-'}",
        ]
    )
