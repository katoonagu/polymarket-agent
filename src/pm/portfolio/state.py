"""Local gitignored state for portfolio snapshots and reconciliations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pm.portfolio.models import (
    PortfolioReconciliationRecord,
    PortfolioReconciliationsFile,
    PortfolioSnapshotRecord,
    PortfolioSnapshotsFile,
)

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_PORTFOLIO_STATE_DIR"
SNAPSHOTS_FILENAME = "portfolio-snapshots.json"
RECONCILIATIONS_FILENAME = "portfolio-reconciliations.json"

DocumentT = TypeVar(
    "DocumentT",
    PortfolioSnapshotsFile,
    PortfolioReconciliationsFile,
)


class PortfolioStateError(RuntimeError):
    """Raised when portfolio state cannot be read or written."""


class PortfolioStateService:
    """Append-only file-backed store for portfolio snapshots and reconciliations."""

    def __init__(
        self,
        *,
        snapshots_path: Path | None = None,
        reconciliations_path: Path | None = None,
    ) -> None:
        state_dir = get_portfolio_state_dir()
        self._snapshots_path = snapshots_path or (state_dir / SNAPSHOTS_FILENAME)
        self._reconciliations_path = reconciliations_path or (
            state_dir / RECONCILIATIONS_FILENAME
        )

    def list_snapshots(self) -> list[PortfolioSnapshotRecord]:
        """Return persisted portfolio snapshots in append order."""
        document = self._load_document(self._snapshots_path, PortfolioSnapshotsFile)
        return document.snapshots

    def append_snapshot(self, record: PortfolioSnapshotRecord) -> None:
        """Append one portfolio snapshot record."""
        document = self._load_document(self._snapshots_path, PortfolioSnapshotsFile)
        document.snapshots.append(record)
        self._write_document(self._snapshots_path, document)

    def list_reconciliations(self) -> list[PortfolioReconciliationRecord]:
        """Return persisted portfolio reconciliations in append order."""
        document = self._load_document(
            self._reconciliations_path,
            PortfolioReconciliationsFile,
        )
        return document.reconciliations

    def append_reconciliation(self, record: PortfolioReconciliationRecord) -> None:
        """Append one portfolio reconciliation record."""
        document = self._load_document(
            self._reconciliations_path,
            PortfolioReconciliationsFile,
        )
        document.reconciliations.append(record)
        self._write_document(self._reconciliations_path, document)

    def _load_document(self, path: Path, model_type: type[DocumentT]) -> DocumentT:
        if not path.exists():
            return model_type()
        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise PortfolioStateError(f"Portfolio state at '{path}' is invalid.") from exc

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
            raise PortfolioStateError(f"Could not write portfolio state at '{path}'.") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_portfolio_state_dir() -> Path:
    """Resolve the gitignored portfolio state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
