"""Shared CLI output helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from rich.console import Console


def emit_output(payload: Mapping[str, Any], *, json_output: bool, text: str) -> None:
    """Render deterministic JSON or a small human-readable message."""
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    Console().print(text)
