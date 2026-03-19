"""Shared support for CLI output and error handling."""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import click
import typer
from rich.console import RenderableType
from typer.core import TyperGroup

from pm.common.output import (
    emit_error,
    emit_output,
    is_interactive_terminal,
    operator_banner,
    prompt_yes_no,
    render_renderable,
)


class OutputMode(StrEnum):
    """Canonical CLI output modes."""

    TABLE = "table"
    JSON = "json"


@dataclass(slots=True, frozen=True)
class CLISettings:
    """Resolved root CLI settings shared across subcommands."""

    output_mode: OutputMode = OutputMode.TABLE


ROOT_OUTPUT_OPTION = typer.Option(
    OutputMode.TABLE,
    "--output",
    case_sensitive=False,
    help="Global output mode: table or json.",
)
ROOT_JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Alias for --output json.",
)
LOCAL_JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output. Compatibility alias for the global output mode.",
)
SIGNER_OPTION = typer.Option(
    None,
    "--signer",
    help="Override the resolved signer address.",
)
FUNDER_OPTION = typer.Option(
    None,
    "--funder",
    help="Override the resolved funder address.",
)
SIGNATURE_TYPE_OPTION = typer.Option(
    None,
    "--signature-type",
    min=0,
    max=2,
    help="Override the resolved signature type: 0, 1, or 2.",
)
CHAIN_ID_OPTION = typer.Option(
    None,
    "--chain-id",
    help="Override the resolved chain id.",
)
_UNKNOWN_COMMAND_PATTERN = re.compile(r"No such command ['\"](?P<command>[^'\"]+)['\"]")


def configure_cli_settings(
    ctx: typer.Context,
    *,
    output: OutputMode,
    json_output: bool,
) -> None:
    """Store root-level CLI settings on the root context."""
    resolved_output = OutputMode.JSON if json_output else output
    ctx.obj = CLISettings(output_mode=resolved_output)


def resolve_output_mode(
    ctx: typer.Context,
    *,
    local_json_output: bool = False,
) -> OutputMode:
    """Resolve command output mode with local compatibility overrides."""
    if local_json_output:
        return OutputMode.JSON

    root_context = ctx.find_root()
    if isinstance(root_context.obj, CLISettings):
        return root_context.obj.output_mode

    return OutputMode.TABLE


def interactive_allowed(
    ctx: typer.Context,
    *,
    local_json_output: bool = False,
) -> bool:
    """Return whether an interactive prompt is allowed for this command."""
    return (
        resolve_output_mode(ctx, local_json_output=local_json_output) is OutputMode.TABLE
        and is_interactive_terminal()
    )


def emit_command_output(
    ctx: typer.Context,
    payload: dict[str, Any],
    *,
    text: str = "",
    renderable: RenderableType | None = None,
    local_json_output: bool = False,
) -> None:
    """Render a successful command response."""
    emit_output(
        payload,
        json_output=resolve_output_mode(ctx, local_json_output=local_json_output)
        is OutputMode.JSON,
        text=text,
        renderable=renderable,
    )


def emit_command_error(
    ctx: typer.Context,
    *,
    code: str,
    message: str,
    resource: str | None = None,
    identifier: str | None = None,
    local_json_output: bool = False,
    hint: dict[str, object] | None = None,
) -> None:
    """Render a structured command error using the shared output contract."""
    emit_error(
        code=code,
        message=message,
        json_output=resolve_output_mode(ctx, local_json_output=local_json_output)
        is OutputMode.JSON,
        resource=resource,
        identifier=identifier,
        hint=hint,
    )


def resolve_live_confirmation(
    ctx: typer.Context,
    *,
    live: bool,
    confirm: bool,
    local_json_output: bool,
    resource: str,
    missing_confirm_message: str,
    prompt_message: str,
    declined_message: str,
) -> bool:
    """Resolve live confirmation with interactive prompting when allowed."""
    if not live or confirm:
        return confirm

    if interactive_allowed(ctx, local_json_output=local_json_output):
        if prompt_yes_no(prompt_message, default=False):
            return True
        emit_output({"cancelled": True}, json_output=False, text=declined_message)
        raise typer.Exit(0)

    emit_command_error(
        ctx,
        code="invalid_argument",
        message=missing_confirm_message,
        resource=resource,
        identifier="confirm",
        local_json_output=local_json_output,
    )
    raise typer.Exit(1)


def build_account_overrides(
    *,
    signer: str | None = None,
    funder: str | None = None,
    signature_type: int | None = None,
    chain_id: int | None = None,
) -> dict[str, str | int | None]:
    """Build non-secret account overrides for auth-backed commands."""
    return {
        "signer_address": signer,
        "funder_address": funder,
        "signature_type": signature_type,
        "chain_id": chain_id,
    }


def _wants_json(args: list[str]) -> bool:
    if "--json" in args:
        return True

    for index, arg in enumerate(args):
        if arg == "--output" and index + 1 < len(args):
            return args[index + 1].lower() == OutputMode.JSON.value
        if arg.startswith("--output="):
            return arg.split("=", 1)[1].lower() == OutputMode.JSON.value

    return False


def _get_param_identifier(exc: click.BadParameter) -> str:
    param = exc.param
    if param is None:
        return ""

    if getattr(param, "name", None):
        return str(param.name)
    if getattr(param, "human_readable_name", None):
        return str(param.human_readable_name)

    return ""


def _classify_click_exception(exc: click.ClickException) -> tuple[str, str, str]:
    message = exc.format_message()

    if isinstance(exc, click.BadParameter):
        return ("invalid_argument", "option", _get_param_identifier(exc))

    if isinstance(exc, click.NoSuchOption):
        return ("invalid_argument", "option", exc.option_name or "")

    match = _UNKNOWN_COMMAND_PATTERN.search(message)
    if match is not None:
        return ("unknown_command", "command", match.group("command"))

    return ("usage_error", "cli", "")


def render_click_exception(exc: click.ClickException, *, args: list[str]) -> None:
    """Render parser-level errors in human or JSON form."""
    message = exc.format_message()

    if not _wants_json(args):
        typer.echo(f"Error: {message}", err=True)
        return

    code, resource, identifier = _classify_click_exception(exc)
    emit_output(
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "resource": resource,
                "identifier": identifier,
            },
        },
        json_output=True,
        text="",
    )


class JSONAwareTyperGroup(TyperGroup):
    """Typer group that normalizes parser errors for CLI and tests."""

    def get_help(self, ctx: click.Context) -> str:
        help_text = super().get_help(ctx)
        if ctx.parent is not None:
            return help_text

        banner = render_renderable(
            operator_banner(
                subtitle="Operator-grade intelligence, guarded execution, and workflow control."
            ),
            force_terminal=is_interactive_terminal(),
        )
        return f"{banner}\n\n{help_text}"

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        raw_args = list(sys.argv[1:] if args is None else args)

        try:
            result = super().main(
                args=raw_args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
            if standalone_mode and isinstance(result, int):
                raise SystemExit(result) from None
            return result
        except click.ClickException as exc:
            if not standalone_mode:
                raise

            render_click_exception(exc, args=raw_args)
            raise SystemExit(1) from None
        except click.exceptions.Exit as exc:
            if not standalone_mode:
                raise

            raise SystemExit(exc.exit_code) from None
        except click.Abort:
            if not standalone_mode:
                raise

            raise SystemExit(1) from None
