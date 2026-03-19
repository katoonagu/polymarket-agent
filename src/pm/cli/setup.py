"""Authenticated setup doctor CLI commands."""

from __future__ import annotations

import typer
from rich.console import RenderableType
from rich.text import Text

from pm.auth import (
    FUNDER_ENV,
    PRIVATE_KEY_ENV,
    SIGNATURE_TYPE_ENV,
    AuthService,
    SetupDoctorResponse,
    SetupGuideResponse,
    SetupWizardResponse,
)
from pm.cli.support import LOCAL_JSON_OPTION, emit_command_output, interactive_allowed
from pm.common.output import (
    is_interactive_terminal,
    operator_banner,
    prompt_secret,
    prompt_text,
    prompt_yes_no,
    render_renderable,
)
from pm.common.tables import (
    empty_message,
    render_group,
    section_panel,
    summary_table,
)

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
        renderable=_render_guide(result, include_banner=True),
        local_json_output=json_output,
    )


@app.command("wizard")
def setup_wizard(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Run a bounded interactive setup wizard without persisting secrets."""
    interactive = interactive_allowed(ctx, local_json_output=json_output)
    if interactive:
        typer.echo(
            render_renderable(
                operator_banner(
                    subtitle="Interactive setup wizard. Secrets stay env-only by default."
                ),
                force_terminal=is_interactive_terminal(),
            )
        )
        typer.echo(
            "This wizard never prints raw private keys and never writes "
            "plaintext secrets to local config."
        )

    result = _build_wizard_response(interactive=interactive)

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wizard(result),
        renderable=_render_wizard(result, include_banner=not interactive),
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


def _format_wizard(response: SetupWizardResponse) -> str:
    lines = [
        f"Interactive: {'yes' if response.interactive else 'no'}",
        f"Has private key: {'yes' if response.has_private_key else 'no'}",
        f"Private key source: {response.private_key_source}",
        f"Session-only used: {'yes' if response.session_only_used else 'no'}",
        _format_guide(response),
    ]
    return "\n".join(lines)


def _render_guide(
    response: SetupGuideResponse,
    *,
    include_banner: bool,
) -> RenderableType:
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
    items: list[RenderableType] = []
    if include_banner:
        items.append(
            operator_banner(
                subtitle="Env-only setup guide for authenticated dry runs and guarded execution."
            )
        )
    items.extend(
        [
            section_panel("Environment", environment),
            section_panel("Checkpoints", checkpoints),
            section_panel("Secret Policy", reminder),
            section_panel("Next Steps", next_steps),
        ]
    )
    return render_group(*items)


def _render_wizard(
    response: SetupWizardResponse,
    *,
    include_banner: bool,
) -> RenderableType:
    summary = summary_table(
        title="Wizard Summary",
        rows=[
            ("Interactive", "yes" if response.interactive else "no"),
            ("Has private key", "yes" if response.has_private_key else "no"),
            ("Private key source", response.private_key_source),
            ("Session-only used", "yes" if response.session_only_used else "no"),
            ("Doctor ready", "yes" if response.doctor.ready else "no"),
        ],
    )
    items: list[RenderableType] = []
    if include_banner:
        items.append(
            operator_banner(
                subtitle="Interactive setup wizard. Secrets stay env-only by default."
            )
        )
    items.extend(
        [
            section_panel("Wizard Summary", summary),
            _render_guide(response, include_banner=False),
        ]
    )
    return render_group(*items)


def _build_wizard_response(*, interactive: bool) -> SetupWizardResponse:
    if not interactive:
        with AuthService() as service:
            auth = service.show().auth
            return service.wizard(
                interactive=False,
                private_key_source="env" if auth.private_key_present else "missing",
                session_only_used=False,
            )

    session_only_used = False
    private_key_source = "missing"
    env_overrides: dict[str, str | None] = {}

    with AuthService() as service:
        current_auth = service.show().auth

    has_env_key = current_auth.private_key_present
    has_private_key = prompt_yes_no(
        "Do you already have a Polymarket private key available?",
        default=has_env_key,
    )
    if not has_private_key:
        with AuthService() as service:
            return service.wizard(
                interactive=True,
                private_key_source="missing",
                session_only_used=False,
            )

    if has_env_key and prompt_yes_no(
        "Use the existing environment-backed private key for this wizard run?",
        default=True,
    ):
        private_key_source = "env"
    else:
        if prompt_yes_no(
            "Use a session-only private key just for this wizard run?",
            default=not has_env_key,
        ):
            env_overrides[PRIVATE_KEY_ENV] = prompt_secret("Session-only private key")
            private_key_source = "session"
            session_only_used = True
        else:
            private_key_source = "missing"

    signature_raw = current_auth.signature_type_name or ""
    if private_key_source != "missing" and not signature_raw:
        env_overrides[SIGNATURE_TYPE_ENV] = prompt_text(
            "Signature type",
            default="EOA",
        )
        signature_raw = env_overrides[SIGNATURE_TYPE_ENV] or ""

    normalized_signature = signature_raw.strip().upper()
    requires_funder = normalized_signature not in {"", "0", "EOA"}
    if private_key_source != "missing" and requires_funder and not current_auth.funder_address:
        env_overrides[FUNDER_ENV] = prompt_text("Funder address")

    with AuthService(env_overrides=env_overrides) as service:
        return service.wizard(
            interactive=True,
            private_key_source=private_key_source,
            session_only_used=session_only_used,
        )
