"""Interactive bounded operator shell over the existing CLI surface."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import click
from rich.console import Console, RenderableType
from rich.text import Text
from typer.main import get_command

from pm.cli.support import render_click_exception
from pm.common.output import operator_banner
from pm.common.tables import render_group, row_table, section_panel

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
MAIN_MENU: dict[str, tuple[str, str | None, tuple[str, ...] | None]] = {
    "1": ("Market workflows", "market", None),
    "2": ("Wallet workflows", "wallet", None),
    "3": ("Strategy workflows", "strategy", None),
    "4": ("Execution workflows", "execution", None),
    "5": ("Verbose status", None, ("status", "--verbose")),
    "6": ("Setup guide", None, ("setup", "guide")),
}
SUBMENU_LABELS = {
    "market": "Market Workflows",
    "wallet": "Wallet Workflows",
    "strategy": "Strategy Workflows",
    "execution": "Execution Workflows",
}
SUBMENU_ITEMS: dict[str, dict[str, str]] = {
    "market": {
        "1": "Market search",
        "2": "Market show",
        "3": "Market watch",
        "0": "Back",
    },
    "wallet": {
        "1": "Wallet summary",
        "2": "Wallet score",
        "0": "Back",
    },
    "strategy": {
        "1": "Queue",
        "2": "Review next",
        "3": "Dispatch approved",
        "0": "Back",
    },
    "execution": {
        "1": "Open orders",
        "2": "Events",
        "3": "Reconcile",
        "0": "Back",
    },
}


@dataclass(slots=True)
class ShellCommandSpec:
    """One menu-driven shell command."""

    label: str
    tokens: list[str]


class OperatorShell:
    """Interactive bounded command loop for common operator workflows."""

    def __init__(
        self,
        *,
        console: Console | None = None,
        executor: Callable[[list[str]], int] | None = None,
    ) -> None:
        self._console = console or Console(width=120)
        self._executor = executor or run_shell_command
        self._menu = "main"

    def run(self) -> None:
        """Run the bounded operator shell until explicit exit."""
        self._print_intro()
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
            lowered = line.lower()
            if lowered in EXIT_COMMANDS:
                self._console.print("Shell ended.")
                return
            if lowered in {"help", "menu"}:
                self._print_menu()
                continue
            if lowered == "back":
                if self._menu == "main":
                    self._console.print("Already at the main menu.")
                else:
                    self._menu = "main"
                    self._print_menu()
                continue

            if self._handle_menu_selection(line):
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

    def _print_intro(self) -> None:
        self._console.print(_shell_banner())
        self._print_menu()

    def _print_menu(self) -> None:
        self._console.print(_render_menu(self._menu))

    def _handle_menu_selection(self, line: str) -> bool:
        if not line.isdigit():
            return False

        if self._menu == "main":
            item = MAIN_MENU.get(line)
            if item is None:
                return False
            label, submenu, tokens = item
            if submenu is not None:
                self._menu = submenu
                self._console.print(f"Opened {label}. Use `back` to return.")
                self._print_menu()
                return True
            if tokens is not None:
                self._executor(list(tokens))
                return True
            return False

        if line == "0":
            self._menu = "main"
            self._print_menu()
            return True

        spec = self._resolve_menu_command(self._menu, line)
        if spec is None:
            return False

        self._console.print(f"Running {spec.label}...")
        self._executor(spec.tokens)
        return True

    def _resolve_menu_command(self, menu: str, selection: str) -> ShellCommandSpec | None:
        if menu == "market":
            if selection == "1":
                query = self._prompt_required("Search query")
                return ShellCommandSpec(
                    label="market search",
                    tokens=["market", "search", "--query", query],
                )
            if selection == "2":
                slug = self._prompt_required("Market slug")
                return ShellCommandSpec(
                    label="market show",
                    tokens=["market", "show", "--slug", slug],
                )
            if selection == "3":
                slug = self._prompt_required("Market slug")
                seconds = self._prompt_optional("Seconds", default="10")
                return ShellCommandSpec(
                    label="market watch",
                    tokens=["stream", "watch", "--slug", slug, "--seconds", seconds],
                )
            return None

        if menu == "wallet":
            if selection == "1":
                address = self._prompt_required("Wallet address")
                return ShellCommandSpec(
                    label="wallet summary",
                    tokens=["wallet", "summary", "--address", address],
                )
            if selection == "2":
                address = self._prompt_required("Wallet address")
                return ShellCommandSpec(
                    label="wallet score",
                    tokens=["wallet", "score", "--address", address],
                )
            return None

        if menu == "strategy":
            if selection == "1":
                return ShellCommandSpec(label="ops queue", tokens=["ops", "queue"])
            if selection == "2":
                return ShellCommandSpec(
                    label="ops review next",
                    tokens=["ops", "review", "next"],
                )
            if selection == "3":
                limit = self._prompt_optional("Limit", default="20")
                return ShellCommandSpec(
                    label="ops dispatch approved",
                    tokens=["ops", "dispatch", "approved", "--limit", limit],
                )
            return None

        if menu == "execution":
            if selection == "1":
                return ShellCommandSpec(
                    label="exec orders open",
                    tokens=["exec", "orders", "open"],
                )
            if selection == "2":
                limit = self._prompt_optional("Limit", default="20")
                return ShellCommandSpec(
                    label="exec events",
                    tokens=["exec", "events", "--limit", limit],
                )
            if selection == "3":
                return ShellCommandSpec(label="exec reconcile", tokens=["exec", "reconcile"])
            return None

        return None

    def _prompt_required(self, label: str) -> str:
        while True:
            value = self._console.input(f"{label}: ").strip()
            if value:
                return value
            self._console.print(f"{label} is required.")

    def _prompt_optional(self, label: str, *, default: str) -> str:
        value = self._console.input(f"{label} [{default}]: ").strip()
        return value or default


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
        title="Shell Aliases",
        columns=["Alias", "Runs"],
        rows=[[alias, " ".join(target)] for alias, target in SHELL_ALIASES.items()],
    )
    guidance = Text(
        "Bounded operator shell. Type commands without the `pm` prefix. "
        "Use `menu` to reopen shortcuts and `exit` or `quit` to leave.",
        style="bold",
    )
    return render_group(
        operator_banner(
            subtitle=(
                "Interactive operator shell. Bounded, paper-first, and "
                "non-daemonized."
            )
        ),
        section_panel("Shell Guidance", guidance),
        section_panel("Shell Aliases", alias_table),
    )


def _render_menu(menu: str) -> RenderableType:
    if menu == "main":
        rows = [
            [key, label, submenu or "direct command"]
            for key, (label, submenu, _) in MAIN_MENU.items()
        ]
        return section_panel(
            "Quick Menu",
            row_table(
                title="Main Menu",
                columns=["Key", "Workflow", "Mode"],
                rows=rows,
            ),
            subtitle="Type a number, `menu`, or any direct CLI command.",
        )

    items = SUBMENU_ITEMS[menu]
    rows = [[key, label] for key, label in items.items()]
    return section_panel(
        SUBMENU_LABELS[menu],
        row_table(
            title=SUBMENU_LABELS[menu],
            columns=["Key", "Action"],
            rows=rows,
        ),
        subtitle="Type a number or `back` to return to the main menu.",
    )
