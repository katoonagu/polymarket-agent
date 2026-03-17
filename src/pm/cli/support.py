"""Shared CLI support helpers."""

from __future__ import annotations

from typing import Literal, TypedDict

import typer

from pm.common.output import emit_error, emit_output

OutputMode = Literal["table", "json"]


class CliState(TypedDict):
    """Shared root CLI state carried through Typer contexts."""

    output_mode: OutputMode


def set_root_output_mode(
    ctx: typer.Context,
    *,
    output: OutputMode,
    json_output: bool,
) -> None:
    """Store the resolved root output mode on the Typer context."""
    ctx.obj = CliState(output_mode="json" if json_output else output)


def resolve_output_mode(
    ctx: typer.Context,
    *,
    local_json_output: bool = False,
) -> OutputMode:
    """Resolve output mode with local flags overriding root configuration."""
    if local_json_output:
        return "json"

    state = ctx.obj if isinstance(ctx.obj, dict) else {}
    output_mode = state.get("output_mode")
    if output_mode in ("table", "json"):
        return output_mode
    return "table"


def emit_command_output(
    ctx: typer.Context,
    payload: dict[str, object],
    *,
    text: str,
    local_json_output: bool = False,
) -> None:
    """Render command output using the shared output contract."""
    emit_output(
        payload,
        json_output=resolve_output_mode(ctx, local_json_output=local_json_output) == "json",
        text=text,
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
    """Render a deterministic CLI error using the shared output contract."""
    emit_error(
        code=code,
        message=message,
        json_output=resolve_output_mode(ctx, local_json_output=local_json_output) == "json",
        resource=resource,
        identifier=identifier,
        hint=hint,
    )
