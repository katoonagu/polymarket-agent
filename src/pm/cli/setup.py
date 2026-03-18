"""Authenticated setup doctor CLI commands."""

from __future__ import annotations

import typer

from pm.auth import AuthService, SetupDoctorResponse
from pm.cli.support import LOCAL_JSON_OPTION, emit_command_output

app = typer.Typer(
    add_completion=False,
    help="Authenticated non-mutating setup readiness commands.",
    no_args_is_help=True,
)


@app.command("doctor")
def setup_doctor(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Run a non-mutating authenticated dry-run readiness check."""
    with AuthService() as service:
        result = service.doctor()

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_doctor(result),
        local_json_output=json_output,
    )


def _format_doctor(response: SetupDoctorResponse) -> str:
    lines = [
        f"Ready: {'yes' if response.ready else 'no'}",
        f"Signer: {response.auth.signer_address or '-'}",
        f"Funder: {response.auth.funder_address or '-'}",
        f"Signature type: {response.auth.signature_type_name or '-'}",
        f"CLOB host: {response.auth.clob_host}",
        f"Chain ID: {response.auth.chain_id if response.auth.chain_id is not None else '-'}",
        f"Geoblock: {response.geoblock.message or '-'}",
        "Checks:",
    ]
    lines.extend(f"  {item.section}: {item.status} - {item.message}" for item in response.checks)
    if response.errors:
        lines.append("Warnings:")
        lines.extend(
            f"  {item.section}: {item.code} - {item.message}" for item in response.errors
        )
    return "\n".join(lines)
