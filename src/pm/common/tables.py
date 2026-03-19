"""Shared Rich table helpers for operator-facing CLI output."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_group(*items: RenderableType | None) -> Group:
    """Return a grouped renderable without ``None`` items."""
    return Group(*[item for item in items if item is not None])


def summary_table(
    *,
    title: str,
    rows: Sequence[tuple[str, str]],
) -> Table:
    """Render a compact two-column summary table."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_lines=False,
        border_style="bright_blue",
        header_style="bold bright_blue",
        title_style="bold bright_blue",
        expand=False,
        pad_edge=False,
    )
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")
    for label, value in rows:
        table.add_row(label, value)
    return table


def row_table(
    *,
    title: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[str]],
) -> Table:
    """Render a compact row table."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_lines=False,
        border_style="bright_blue",
        header_style="bold bright_blue",
        title_style="bold bright_blue",
        expand=False,
        pad_edge=False,
    )
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*row)
    return table


def empty_message(message: str) -> Text:
    """Render a short empty-state message."""
    return Text(message, style="dim")


def section_panel(
    title: str,
    body: RenderableType,
    *,
    subtitle: str | None = None,
) -> Panel:
    """Wrap a renderable in a framed operator section."""
    return Panel(
        body,
        title=title,
        subtitle=subtitle,
        border_style="bright_blue",
        padding=(0, 1),
        expand=False,
    )


def format_bool(value: bool) -> str:
    """Render a stable yes/no flag."""
    return "yes" if value else "no"


def shorten_identifier(
    value: str | None,
    *,
    head: int = 8,
    tail: int = 6,
) -> str:
    """Shorten a long identifier for human table display."""
    if value is None:
        return "-"
    if len(value) <= head + tail + 3:
        return value
    return f"{value[:head]}...{value[-tail:]}"
