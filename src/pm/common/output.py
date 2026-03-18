"""Shared CLI output helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import typer
from rich.console import Console


def emit_output(payload: Mapping[str, Any], *, json_output: bool, text: str) -> None:
    """Render deterministic JSON or a small human-readable message."""
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    Console().print(text)


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

    Console(stderr=True).print(message)
