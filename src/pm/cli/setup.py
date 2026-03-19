"""Authenticated setup doctor CLI commands."""

from __future__ import annotations

import typer
from rich.console import RenderableType
from rich.text import Text

from pm.auth import AuthService, SetupDoctorResponse, SetupGuideResponse
from pm.cli.support import LOCAL_JSON_OPTION, emit_command_output
from pm.common.tables import empty_message, render_group, summary_table

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


@app.command("guide")
def setup_guide(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show a non-mutating env-only setup guide for operators."""
    with AuthService() as service:
        result = service.guide()

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_guide(result),
        renderable=_render_guide(result),
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


def _format_guide(response: SetupGuideResponse) -> str:
    lines = [
        "Environment:",
        *[
            "  "
            f"{item.name}: {item.safe_value or '-'} "
            f"({'required' if item.required else 'optional'})"
            for item in response.environment_items
        ],
        "Checkpoints:",
        *[
            f"  {item.section}: {item.status} - {item.message}"
            for item in response.checkpoints
        ],
        "Next steps:",
        *[f"  {item}" for item in response.next_steps],
    ]
    return "\n".join(lines)


def _render_guide(response: SetupGuideResponse) -> RenderableType:
    environment = summary_table(
        title="Environment Variables",
        rows=[
            (
                item.name,
                f"{item.safe_value or '-'} ({'required' if item.required else 'optional'})",
            )
            for item in response.environment_items
        ],
    )
    checkpoints = summary_table(
        title="Setup Checkpoints",
        rows=[
            (
                item.section,
                f"{item.status}: {item.message}",
            )
            for item in response.checkpoints
        ],
    )
    next_steps = (
        summary_table(
            title="Suggested Next Commands",
            rows=[
                (f"Step {index}", value)
                for index, value in enumerate(response.next_steps, start=1)
            ],
        )
        if response.next_steps
        else empty_message("No next steps.")
    )
    reminder = Text(
        "Secrets stay env-only. Raw private keys are never printed or written to local config."
    )
    return render_group(environment, checkpoints, reminder, next_steps)
