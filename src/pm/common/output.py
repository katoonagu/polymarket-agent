"""Shared CLI output helpers."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any

import click
import typer
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.text import Text

OPERATOR_TITLE = "POLYMARKET AGENT"


def _console(
    *,
    stderr: bool = False,
    force_terminal: bool | None = None,
    record: bool = False,
) -> Console:
    """Return a Rich console for CLI rendering and tests."""
    return Console(
        stderr=stderr,
        force_terminal=force_terminal,
        record=record,
        width=120,
    )


def is_interactive_terminal() -> bool:
    """Return whether stdin and stdout look interactive."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def prompt_yes_no(message: str, *, default: bool = False) -> bool:
    """Prompt for a yes/no answer."""
    return bool(click.confirm(message, default=default, show_default=True))


def prompt_text(message: str, *, default: str | None = None) -> str:
    """Prompt for visible text input."""
    prompt_default = default if default is not None and default != "" else None
    return str(
        click.prompt(
            message,
            default=prompt_default,
            show_default=prompt_default is not None,
        )
    )


def prompt_secret(message: str) -> str:
    """Prompt for hidden text input."""
    return str(click.prompt(message, hide_input=True, show_default=False))


def render_renderable(
    renderable: RenderableType,
    *,
    stderr: bool = False,
    force_terminal: bool | None = None,
) -> str:
    """Render a Rich renderable into plain or ANSI-styled text."""
    console = _console(stderr=stderr, force_terminal=force_terminal, record=True)
    console.print(renderable)
    return console.export_text(styles=bool(force_terminal)).rstrip()


def operator_banner(*, subtitle: str | None = None) -> RenderableType:
    """Return a branded operator banner for entry/setup flows."""
    subtitle_text = subtitle or (
        "Intelligence, guarded execution, and operator workflows."
    )
    accent = Text("env-only secrets | paper default | live gated", style="cyan")
    return Panel.fit(
        Group(
            Text(OPERATOR_TITLE, style="bold white"),
            Text(subtitle_text, style="bold bright_blue"),
            accent,
        ),
        border_style="bright_blue",
        title="Desk",
        padding=(0, 1),
    )


def emit_output(
    payload: Mapping[str, Any],
    *,
    json_output: bool,
    text: str = "",
    renderable: RenderableType | None = None,
) -> None:
    """Render deterministic JSON or a small human-readable message."""
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    if renderable is not None:
        _console().print(renderable)
        return

    _console().print(text)


def emit_error(
    *,
    code: str,
    message: str,
    json_output: bool,
    resource: str | None = None,
    identifier: str | None = None,
    hint: Mapping[str, Any] | None = None,
) -> None:
    """Render a deterministic error payload or a small human-readable message."""
    if json_output:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if resource is not None:
            payload["error"]["resource"] = resource
        if identifier is not None:
            payload["error"]["identifier"] = identifier
        if hint is not None:
            payload["hint"] = dict(hint)
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    _console(stderr=True).print(message)
