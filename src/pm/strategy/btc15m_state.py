"""Local gitignored state for the BTC15m research strategy surface."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pm.strategy.btc15m_models import (
    Btc15mBoundaryDecisionRecord,
    Btc15mBoundaryDecisionsFile,
    Btc15mBoundaryObservationRecord,
    Btc15mPaperRunRecord,
    Btc15mPaperRunsFile,
    Btc15mReplayRecord,
    Btc15mReplaysFile,
    Btc15mWindowRecord,
)
from pm.strategy.registry import get_strategy_state_dir

BOUNDARY_OBSERVATIONS_FILENAME = "btc-15m-chainlink-boundary-observations.jsonl"
BOUNDARY_DECISIONS_FILENAME = "btc-15m-chainlink-boundary-decisions.json"
WINDOWS_FILENAME = "btc-15m-chainlink-windows.jsonl"
REPLAYS_FILENAME = "btc-15m-chainlink-replays.json"
PAPER_RUNS_FILENAME = "btc-15m-chainlink-paper-runs.json"

DocumentT = TypeVar(
    "DocumentT",
    Btc15mBoundaryDecisionsFile,
    Btc15mReplaysFile,
    Btc15mPaperRunsFile,
)


class Btc15mStateError(RuntimeError):
    """Raised when BTC15m strategy state cannot be read or written."""


class Btc15mStateService:
    """Append-only persistence helpers for BTC15m research artifacts."""

    def __init__(
        self,
        *,
        boundary_observations_path: Path | None = None,
        boundary_decisions_path: Path | None = None,
        windows_path: Path | None = None,
        replays_path: Path | None = None,
        paper_runs_path: Path | None = None,
    ) -> None:
        state_dir = get_strategy_state_dir()
        self._boundary_observations_path = boundary_observations_path or (
            state_dir / BOUNDARY_OBSERVATIONS_FILENAME
        )
        self._boundary_decisions_path = boundary_decisions_path or (
            state_dir / BOUNDARY_DECISIONS_FILENAME
        )
        self._windows_path = windows_path or (state_dir / WINDOWS_FILENAME)
        self._replays_path = replays_path or (state_dir / REPLAYS_FILENAME)
        self._paper_runs_path = paper_runs_path or (state_dir / PAPER_RUNS_FILENAME)

    def list_boundary_observations(self) -> list[Btc15mBoundaryObservationRecord]:
        """Return raw boundary observations in append order."""
        return self._read_jsonl(
            self._boundary_observations_path,
            Btc15mBoundaryObservationRecord,
        )

    def append_boundary_observations(
        self,
        records: list[Btc15mBoundaryObservationRecord],
    ) -> None:
        """Append raw boundary observations."""
        self._append_jsonl(self._boundary_observations_path, records)

    def list_boundary_decisions(self) -> list[Btc15mBoundaryDecisionRecord]:
        """Return canonical boundary decisions in append order."""
        document = self._load_document(
            self._boundary_decisions_path,
            Btc15mBoundaryDecisionsFile,
        )
        return document.items

    def append_boundary_decision(self, record: Btc15mBoundaryDecisionRecord) -> None:
        """Append one canonical boundary decision."""
        document = self._load_document(
            self._boundary_decisions_path,
            Btc15mBoundaryDecisionsFile,
        )
        document.items.append(record)
        self._write_document(self._boundary_decisions_path, document)

    def list_windows(self) -> list[Btc15mWindowRecord]:
        """Return recorded windows in append order."""
        return self._read_jsonl(self._windows_path, Btc15mWindowRecord)

    def append_windows(self, records: list[Btc15mWindowRecord]) -> None:
        """Append one or more recorded windows."""
        self._append_jsonl(self._windows_path, records)

    def list_replays(self) -> list[Btc15mReplayRecord]:
        """Return persisted replay batches in append order."""
        document = self._load_document(self._replays_path, Btc15mReplaysFile)
        return document.items

    def append_replay(self, record: Btc15mReplayRecord) -> None:
        """Append one replay batch."""
        document = self._load_document(self._replays_path, Btc15mReplaysFile)
        document.items.append(record)
        self._write_document(self._replays_path, document)

    def list_paper_runs(self) -> list[Btc15mPaperRunRecord]:
        """Return persisted paper-run batches in append order."""
        document = self._load_document(self._paper_runs_path, Btc15mPaperRunsFile)
        return document.items

    def append_paper_run(self, record: Btc15mPaperRunRecord) -> None:
        """Append one paper-run batch."""
        document = self._load_document(self._paper_runs_path, Btc15mPaperRunsFile)
        document.items.append(record)
        self._write_document(self._paper_runs_path, document)

    @property
    def windows_path(self) -> Path:
        """Return the resolved windows path."""
        return self._windows_path

    def _read_jsonl(self, path: Path, model_type: type[BaseModel]) -> list:
        if not path.exists():
            return []
        try:
            raw_lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise Btc15mStateError(f"Could not read BTC15m state at '{path}'.") from exc

        items: list = []
        try:
            for line in raw_lines:
                if not line.strip():
                    continue
                items.append(model_type.model_validate_json(line))
        except (ValidationError, ValueError) as exc:
            raise Btc15mStateError(f"BTC15m state at '{path}' is invalid.") from exc
        return items

    def _append_jsonl(self, path: Path, records: Sequence[BaseModel]) -> None:
        if not records:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    payload = json.dumps(record.model_dump(mode="json"), sort_keys=True)
                    handle.write(payload + "\n")
        except OSError as exc:
            raise Btc15mStateError(f"Could not write BTC15m state at '{path}'.") from exc

    def _load_document(self, path: Path, model_type: type[DocumentT]) -> DocumentT:
        if not path.exists():
            return model_type()
        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise Btc15mStateError(f"BTC15m state at '{path}' is invalid.") from exc

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
            temp_path.replace(path)
        except OSError as exc:
            raise Btc15mStateError(f"Could not write BTC15m state at '{path}'.") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
