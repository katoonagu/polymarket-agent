"""Local gitignored state for wallet events, signals, and shadow runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pm.wallet.models import (
    WalletEvent,
    WalletEventsFile,
    WalletShadowRun,
    WalletShadowRunsFile,
    WalletSignal,
    WalletSignalsFile,
)
from pm.wallet.registry import REGISTRY_ENV_VAR, WalletRegistryError

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_WALLET_STATE_DIR"
EVENTS_FILENAME = "wallet-events.json"
SIGNALS_FILENAME = "wallet-signals.json"
SHADOW_RUNS_FILENAME = "wallet-shadow-runs.json"

DocumentT = TypeVar(
    "DocumentT",
    WalletEventsFile,
    WalletSignalsFile,
    WalletShadowRunsFile,
)


class WalletStateError(WalletRegistryError):
    """Raised when local wallet shadow state cannot be read or written."""


class WalletPipelineStateService:
    """Small file-backed store for wallet events, signals, and shadow runs."""

    def __init__(
        self,
        *,
        events_path: Path | None = None,
        signals_path: Path | None = None,
        shadow_runs_path: Path | None = None,
    ) -> None:
        state_dir = get_wallet_state_dir()
        self._events_path = events_path or (state_dir / EVENTS_FILENAME)
        self._signals_path = signals_path or (state_dir / SIGNALS_FILENAME)
        self._shadow_runs_path = shadow_runs_path or (state_dir / SHADOW_RUNS_FILENAME)

    @property
    def events_path(self) -> Path:
        """Return the resolved wallet-events state path."""
        return self._events_path

    @property
    def signals_path(self) -> Path:
        """Return the resolved wallet-signals state path."""
        return self._signals_path

    @property
    def shadow_runs_path(self) -> Path:
        """Return the resolved wallet shadow-run state path."""
        return self._shadow_runs_path

    def list_events(self, address: str | None = None) -> list[WalletEvent]:
        """Return persisted wallet events in append order."""
        events = self._load_document(
            self._events_path,
            WalletEventsFile,
            WalletEventsFile,
        ).events
        if address is None:
            return events
        return [event for event in events if event.source_wallet == address]

    def append_events(self, events: list[WalletEvent]) -> None:
        """Append normalized events in deterministic order."""
        if not events:
            return
        document = self._load_document(self._events_path, WalletEventsFile, WalletEventsFile)
        document.events.extend(events)
        self._write_document(self._events_path, document)

    def list_signals(self, address: str | None = None) -> list[WalletSignal]:
        """Return persisted signals in append order."""
        signals = self._load_document(
            self._signals_path,
            WalletSignalsFile,
            WalletSignalsFile,
        ).signals
        if address is None:
            return signals
        return [signal for signal in signals if signal.source_wallet == address]

    def append_signals(self, signals: list[WalletSignal]) -> None:
        """Append derived signals in deterministic order."""
        if not signals:
            return
        document = self._load_document(self._signals_path, WalletSignalsFile, WalletSignalsFile)
        document.signals.extend(signals)
        self._write_document(self._signals_path, document)

    def list_shadow_runs(self, address: str | None = None) -> list[WalletShadowRun]:
        """Return persisted shadow runs in append order."""
        runs = self._load_document(
            self._shadow_runs_path,
            WalletShadowRunsFile,
            WalletShadowRunsFile,
        ).runs
        if address is None:
            return runs
        return [run for run in runs if run.source_wallet == address]

    def append_shadow_run(self, run: WalletShadowRun) -> None:
        """Append a single shadow run in deterministic order."""
        document = self._load_document(
            self._shadow_runs_path,
            WalletShadowRunsFile,
            WalletShadowRunsFile,
        )
        document.runs.append(run)
        self._write_document(self._shadow_runs_path, document)

    def _load_document(
        self,
        path: Path,
        model_type: type[DocumentT],
        empty_factory: type[DocumentT],
    ) -> DocumentT:
        if not path.exists():
            return empty_factory()

        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise WalletStateError(f"Wallet state at '{path}' is invalid.") from exc

    def _write_document(self, path: Path, document: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temp_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
                prefix=f"{path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)

            os.replace(temp_path, path)
        except OSError as exc:
            raise WalletStateError(f"Could not write wallet state at '{path}'.") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_wallet_state_dir() -> Path:
    """Resolve the default gitignored wallet state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    registry_override = os.getenv(REGISTRY_ENV_VAR)
    if registry_override:
        return Path(registry_override).expanduser().parent
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
