"""Shared CLI settings, output resolution, and parser-level error handling."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Sequence
from typing import Any

import click
import typer
from typer.core import TyperGroup

from pm.common import OutputMode, emit_output

OUTPUT_MODE_KEY = "output_mode"
UNKNOWN_COMMAND_PATTERN = re.compile(r"No such command ['\"](?P<command>.+?)['\"]")
ROOT_OUTPUT_OPTION = typer.Option(
    OutputMode.TABLE,
    "--output",
    help="Output mode: table or json.",
)
ROOT_JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Alias for --output json.",
)
LOCAL_OUTPUT_OPTION = typer.Option(
    None,
    "--output",
    help="Override output mode for this command.",
)
LOCAL_JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Alias for --output json.",
)


def configure_root_output(
    ctx: typer.Context,
    output: OutputMode,
    json_output: bool,
) -> None:
    """Store the global output mode on the Click context."""
    ctx.obj = dict(ctx.obj or {})
    ctx.obj[OUTPUT_MODE_KEY] = OutputMode.JSON if json_output else output


def resolve_output_mode(
    ctx: typer.Context,
    *,
    output: OutputMode | None,
    json_output: bool,
) -> OutputMode:
    """Resolve leaf-local output options against the root-global defaults."""
    if json_output:
        return OutputMode.JSON
    if output is not None:
        return output

    current = (ctx.obj or {}).get(OUTPUT_MODE_KEY)
    if isinstance(current, OutputMode):
        return current
    if isinstance(current, str):
        return OutputMode(current)
    return OutputMode.TABLE


def build_error_payload(
    *,
    code: str,
    message: str,
    resource: str,
    identifier: str,
) -> dict[str, Any]:
    """Build the canonical nested JSON error envelope."""
    return {
        "ok": False,
        "error": {
            "code": code,
            "identifier": identifier,
            "message": message,
            "resource": resource,
        },
    }


def emit_cli_error(
    *,
    code: str,
    message: str,
    resource: str,
    identifier: str,
    output_mode: OutputMode,
    exit_code: int = 1,
) -> None:
    """Emit a canonical CLI error and exit."""
    emit_output(
        build_error_payload(
            code=code,
            message=message,
            resource=resource,
            identifier=identifier,
        ),
        output_mode=output_mode,
        text=f"Error: {message}",
    )
    raise typer.Exit(code=exit_code)


def _json_requested(args: Sequence[str]) -> bool:
    for index, arg in enumerate(args):
        if arg == "--json":
            return True
        if arg.startswith("--output=") and arg.partition("=")[2].lower() == OutputMode.JSON:
            return True
        if (
            arg == "--output"
            and index + 1 < len(args)
            and args[index + 1].lower() == OutputMode.JSON
        ):
            return True
    return False


def _classify_click_exception(error: click.ClickException) -> tuple[str, str, str, str]:
    message = error.format_message()

    if isinstance(error, click.NoSuchOption):
        identifier = (error.option_name or "option").lstrip("-")
        return ("invalid_argument", "option", identifier, message)

    if isinstance(error, click.BadParameter):
        if error.param is not None:
            identifier = error.param.name or error.param.human_readable_name
            resource = "option" if isinstance(error.param, click.Option) else "argument"
        else:
            identifier = "argument"
            resource = "argument"
        return ("invalid_argument", resource, identifier, message)

    if isinstance(error, click.UsageError):
        match = UNKNOWN_COMMAND_PATTERN.search(message)
        if match is not None:
            return ("unknown_command", "command", match.group("command"), message)
        return ("usage_error", "cli", "cli", message)

    return ("usage_error", "cli", "cli", message)


class JsonAwareTyperGroup(TyperGroup):
    """Typer group that emits JSON parser errors when JSON mode was requested."""

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        raw_args = list(args) if args is not None else sys.argv[1:]
        if args is None and os.name == "nt" and windows_expand_args:
            raw_args = click.utils._expand_args(raw_args)

        try:
            result = super().main(
                args=raw_args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=False,
                **extra,
            )
            if standalone_mode and isinstance(result, int):
                raise SystemExit(result)
            return result
        except click.ClickException as error:
            if not standalone_mode:
                raise

            if _json_requested(raw_args):
                code, resource, identifier, message = _classify_click_exception(error)
                typer.echo(
                    json.dumps(
                        build_error_payload(
                            code=code,
                            message=message,
                            resource=resource,
                            identifier=identifier,
                        ),
                        indent=2,
                        sort_keys=True,
                    ),
                )
            else:
                error.show()
            raise SystemExit(error.exit_code) from error
        except click.Abort as error:
            if not standalone_mode:
                raise

            if _json_requested(raw_args):
                typer.echo(
                    json.dumps(
                        build_error_payload(
                            code="usage_error",
                            message="Aborted!",
                            resource="cli",
                            identifier="cli",
                        ),
                        indent=2,
                        sort_keys=True,
                    ),
                )
            else:
                click.echo("Aborted!", file=sys.stderr)
            raise SystemExit(1) from error
