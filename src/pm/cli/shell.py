"""Interactive bounded operator shell over the existing CLI surface."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence

import click
from rich.console import Console, RenderableType
from typer.main import get_command

from pm.cli.support import render_click_exception
from pm.common.tables import render_group, row_table

SHELL_ALIASES: dict[str, tuple[str, ...]] = {
    "search": ("market", "search"),
    "show": ("market", "show"),
    "watch": ("stream", "watch"),
    "wallet-summary": ("wallet", "summary"),
    "wallet-score": ("wallet", "score"),
    "queue": ("ops", "queue"),
    "review-next": ("ops", "review", "next"),
    "dispatch-approved": ("ops", "dispatch", "approved"),
    "orders": ("exec", "orders", "open"),
    "events": ("exec", "events"),
    "reconcile": ("exec", "reconcile"),
    "status": ("status", "--verbose"),
    "guide": ("setup", "guide"),
}
EXIT_COMMANDS = {"exit", "quit"}


class OperatorShell:
    """Interactive bounded command loop for common operator workflows."""

    def __init__(
        self,
        *,
        console: Console | None = None,
        executor: Callable[[list[str]], int] | None = None,
    ) -> None:
        self._console = console or Console(color_system=None, force_terminal=False, width=120)
        self._executor = executor or run_shell_command

    def run(self) -> None:
        """Run the bounded operator shell until explicit exit."""
        self._console.print(_shell_banner())
        while True:
            try:
                raw = self._console.input("pm> ")
            except EOFError:
                self._console.print("Shell ended.")
                return
            except KeyboardInterrupt:
                self._console.print("\nShell interrupted.")
                return

            line = raw.strip()
            if not line:
                continue
            if line.lower() in EXIT_COMMANDS:
                self._console.print("Shell ended.")
                return
            if line.lower() == "help":
                self._console.print(_shell_banner())
                continue

            try:
                tokens = normalize_shell_tokens(shlex.split(line))
            except ValueError as exc:
                self._console.print(f"Parse error: {exc}")
                continue

            try:
                self._executor(tokens)
            except KeyboardInterrupt:
                self._console.print("\nShell interrupted.")
                return


def shell() -> None:
    """Run the bounded interactive operator shell."""
    OperatorShell().run()


def normalize_shell_tokens(tokens: Sequence[str]) -> list[str]:
    """Normalize shell input into a CLI argument list."""
    normalized = list(tokens)
    if normalized and normalized[0] == "pm":
        normalized = normalized[1:]
    if not normalized:
        return []
    alias = SHELL_ALIASES.get(normalized[0])
    if alias is None:
        return normalized
    return [*alias, *normalized[1:]]


def run_shell_command(tokens: list[str]) -> int:
    """Execute one shell command against the existing root CLI."""
    if not tokens:
        return 0

    from pm.cli.app import app

    command = get_command(app)
    try:
        result = command.main(args=tokens, prog_name="pm", standalone_mode=False)
    except click.ClickException as exc:
        render_click_exception(exc, args=tokens)
        return 1
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1

    return int(result) if isinstance(result, int) else 0


def _shell_banner() -> RenderableType:
    alias_table = row_table(
        title="Shell Shortcuts",
        columns=["Alias", "Runs"],
        rows=[[alias, " ".join(target)] for alias, target in SHELL_ALIASES.items()],
    )
    return render_group(
        "Bounded operator shell. Type commands without the `pm` prefix.",
        "Use `help` to reprint shortcuts. Use `exit` or `quit` to leave.",
        alias_table,
    )
