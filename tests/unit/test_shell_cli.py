"""Tests for the bounded operator shell."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from typer.testing import CliRunner

from pm.cli.app import app
from pm.cli.shell import OperatorShell, normalize_shell_tokens

runner = CliRunner()


@dataclass
class FakeConsole:
    """Tiny console double for shell-loop tests."""

    inputs: list[object]
    printed: list[str] = field(default_factory=list)

    def input(self, prompt: str) -> str:
        self.printed.append(prompt)
        item = self.inputs.pop(0)
        if isinstance(item, BaseException):
            raise item
        return str(item)

    def print(self, value: object) -> None:
        if isinstance(value, str):
            self.printed.append(value)
            return
        console = Console(color_system=None, force_terminal=False, width=120, record=True)
        console.print(value)
        self.printed.append(console.export_text())


def test_root_help_lists_shell() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "shell" in result.stdout


def test_normalize_shell_tokens_alias_and_passthrough() -> None:
    assert normalize_shell_tokens(["status", "--json"]) == ["status", "--verbose", "--json"]
    assert normalize_shell_tokens(["pm", "orders", "--json"]) == [
        "exec",
        "orders",
        "open",
        "--json",
    ]
    assert normalize_shell_tokens(["market", "show", "--slug", "btc"]) == [
        "market",
        "show",
        "--slug",
        "btc",
    ]


def test_shell_loop_executes_commands_and_exits_on_quit() -> None:
    executed: list[list[str]] = []
    console = FakeConsole(inputs=["queue --json", "market show --slug btc", "quit"])

    shell = OperatorShell(
        console=console,  # type: ignore[arg-type]
        executor=lambda tokens: executed.append(tokens) or 0,
    )
    shell.run()

    assert executed == [
        ["ops", "queue", "--json"],
        ["market", "show", "--slug", "btc"],
    ]
    assert any("Shell Shortcuts" in item for item in console.printed)
    assert any("Shell ended." in item for item in console.printed)


def test_shell_loop_exits_on_eof() -> None:
    console = FakeConsole(inputs=[EOFError()])
    shell = OperatorShell(console=console, executor=lambda tokens: 0)  # type: ignore[arg-type]

    shell.run()

    assert any("Shell ended." in item for item in console.printed)
