"""Shared CLI output helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

import typer
from rich.console import Console


class OutputMode(StrEnum):
    """Canonical CLI output modes."""

    TABLE = "table"
    JSON = "json"


def emit_output(
    payload: Mapping[str, Any],
    *,
    output_mode: OutputMode,
    text: str,
) -> None:
    """Render deterministic JSON or a small human-readable message."""
    if output_mode is OutputMode.JSON:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    if text:
        Console().print(text)
