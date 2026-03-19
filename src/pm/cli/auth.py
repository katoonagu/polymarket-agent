"""Authenticated account inspection CLI commands."""

from __future__ import annotations

import typer

from pm.auth import (
    AuthClientError,
    AuthDeriveApiKeyResponse,
    AuthProfileClearResponse,
    AuthProfileDoctorResponse,
    AuthProfileFromEnvResponse,
    AuthProfileInitResponse,
    AuthProfileShowResponse,
    AuthProfileStateError,
    AuthService,
    AuthShowResponse,
    AuthValidationError,
    BalanceAllowanceView,
)
from pm.cli.support import (
    CHAIN_ID_OPTION,
    FUNDER_OPTION,
    LOCAL_JSON_OPTION,
    SIGNATURE_TYPE_OPTION,
    SIGNER_OPTION,
    build_account_overrides,
    emit_command_error,
    emit_command_output,
)

app = typer.Typer(
    add_completion=False,
    help="Authenticated non-live account inspection commands.",
    no_args_is_help=True,
)
profile_app = typer.Typer(
    add_completion=False,
    help="Non-secret operator profile commands.",
    no_args_is_help=True,
)


@app.command("show")
def auth_show(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the current authenticated environment context."""
    try:
        with AuthService(
            account_overrides=build_account_overrides(
                signer=signer,
                funder=funder,
                signature_type=signature_type,
                chain_id=chain_id,
            )
        ) as service:
            result = service.show()
    except AuthProfileStateError as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_auth_show(result),
        local_json_output=json_output,
    )


@app.command("derive-api-key")
def derive_api_key(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Derive ephemeral Level 2 API credentials without persisting them."""
    try:
        with AuthService(
            account_overrides=build_account_overrides(
                signer=signer,
                funder=funder,
                signature_type=signature_type,
                chain_id=chain_id,
            )
        ) as service:
            result = service.derive_api_key()
    except (AuthValidationError, AuthClientError, AuthProfileStateError) as exc:
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
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show authenticated collateral balance information."""
    try:
        with AuthService(
            account_overrides=build_account_overrides(
                signer=signer,
                funder=funder,
                signature_type=signature_type,
                chain_id=chain_id,
            )
        ) as service:
            result = service.balances()
    except (AuthValidationError, AuthClientError, AuthProfileStateError) as exc:
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
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    signature_type: int | None = SIGNATURE_TYPE_OPTION,
    chain_id: int | None = CHAIN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show authenticated collateral allowance information."""
    try:
        with AuthService(
            account_overrides=build_account_overrides(
                signer=signer,
                funder=funder,
                signature_type=signature_type,
                chain_id=chain_id,
            )
        ) as service:
            result = service.allowances()
    except (AuthValidationError, AuthClientError, AuthProfileStateError) as exc:
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


@profile_app.command("show")
def profile_show(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show the persisted non-secret operator profile, if one exists."""
    try:
        with AuthService() as service:
            result = service.profile_show()
    except AuthProfileStateError as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_profile_show(result),
        local_json_output=json_output,
    )


@profile_app.command("init")
def profile_init(
    ctx: typer.Context,
    signature_type: int = typer.Option(
        ...,
        "--signature-type",
        min=0,
        max=2,
        help="Profile signature type: 0, 1, or 2.",
    ),
    signer: str = typer.Option(..., "--signer", help="Profile signer address."),
    funder: str = typer.Option(..., "--funder", help="Profile funder address."),
    chain_id: int | None = CHAIN_ID_OPTION,
    label: str | None = typer.Option(None, "--label", help="Optional operator label."),
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Initialize one non-secret operator profile explicitly."""
    try:
        with AuthService() as service:
            result = service.profile_init(
                signature_type=signature_type,
                signer=signer,
                funder=funder,
                chain_id=chain_id,
                label=label,
            )
    except (AuthValidationError, AuthProfileStateError) as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_profile_init(result),
        local_json_output=json_output,
    )


@profile_app.command("from-env")
def profile_from_env(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Persist a non-secret operator profile from the current env config."""
    try:
        with AuthService() as service:
            result = service.profile_from_env()
    except (AuthValidationError, AuthProfileStateError) as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_profile_from_env(result),
        local_json_output=json_output,
    )


@profile_app.command("doctor")
def profile_doctor(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a compact local operator identity and readiness summary."""
    try:
        with AuthService() as service:
            result = service.profile_doctor()
    except AuthProfileStateError as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_profile_doctor(result),
        local_json_output=json_output,
    )


@profile_app.command("clear")
def profile_clear(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Remove the persisted non-secret operator profile."""
    try:
        with AuthService() as service:
            result = service.profile_clear()
    except AuthProfileStateError as exc:
        _emit_auth_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_profile_clear(result),
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
        code=(
            "state_error"
            if isinstance(exc, AuthProfileStateError)
            else "invalid_argument"
            if isinstance(exc, AuthValidationError)
            else "request_failed"
        ),
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


def _format_profile_show(response: AuthProfileShowResponse) -> str:
    if not response.present or response.profile is None:
        return "Operator profile: not initialized."
    return _format_profile_details(response.profile, heading="Operator profile")


def _format_profile_init(response: AuthProfileInitResponse) -> str:
    return _format_profile_details(response.profile, heading="Operator profile initialized")


def _format_profile_from_env(response: AuthProfileFromEnvResponse) -> str:
    return _format_profile_details(response.profile, heading="Operator profile imported from env")


def _format_profile_doctor(response: AuthProfileDoctorResponse) -> str:
    lines = [
        f"Ready: {response.ready}",
        f"Profile present: {response.present}",
        f"Signer: {response.auth.signer_address or '-'}",
        f"Funder: {response.auth.funder_address or '-'}",
        f"Signature type: {response.auth.signature_type_name or '-'}",
        f"Chain ID: {response.auth.chain_id if response.auth.chain_id is not None else '-'}",
        f"Auth env ready: {response.auth_env_ready}",
        f"Geoblock reminder: {response.geoblock_reminder}",
        "Checks:",
    ]
    lines.extend(f"  {item.section}: {item.status} - {item.message}" for item in response.checks)
    if response.errors:
        lines.append("Warnings:")
        lines.extend(
            f"  {item.section}: {item.code} - {item.message}" for item in response.errors
        )
    return "\n".join(lines)


def _format_profile_clear(response: AuthProfileClearResponse) -> str:
    return f"Operator profile cleared: {response.cleared}"


def _format_profile_details(profile: object, *, heading: str) -> str:
    signature_type = getattr(profile, "signature_type", None)
    signature_name = _signature_type_name(signature_type)
    return "\n".join(
        [
            heading,
            f"Signer: {getattr(profile, 'signer_address', '-') or '-'}",
            f"Funder: {getattr(profile, 'funder_address', '-') or '-'}",
            (
                f"Signature type: {signature_name} ({signature_type})"
                if signature_type is not None and signature_name is not None
                else f"Signature type: {signature_type if signature_type is not None else '-'}"
            ),
            f"Chain ID: {getattr(profile, 'chain_id', '-')}",
            f"Label: {getattr(profile, 'account_label', None) or '-'}",
            f"Source: {getattr(profile, 'source', '-')}",
        ]
    )


def _signature_type_name(value: int | None) -> str | None:
    if value == 0:
        return "EOA"
    if value == 1:
        return "POLY_PROXY"
    if value == 2:
        return "POLY_GNOSIS_SAFE"
    return None


app.add_typer(profile_app, name="profile")
