"""Local gitignored state for approval and execution lifecycle audit records."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pm.execution.exceptions import ExecutionError
from pm.execution.models import (
    ApprovalPlanRecord,
    ApprovalPlansFile,
    ApprovalResultRecord,
    ApprovalResultsFile,
    CapturedExecutionEvent,
    ExecutionOrderPlanRecord,
    ExecutionOrderPlansFile,
    ExecutionOrderResultRecord,
    ExecutionOrderResultsFile,
    ExecutionReconciliationRecord,
    ExecutionReconciliationsFile,
)

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_EXECUTION_STATE_DIR"
APPROVAL_PLANS_FILENAME = "approval-plans.json"
APPROVAL_RESULTS_FILENAME = "approval-results.json"
ORDER_PLANS_FILENAME = "execution-order-plans.json"
ORDER_RESULTS_FILENAME = "execution-order-results.json"
EVENTS_FILENAME = "execution-events.jsonl"
RECONCILIATIONS_FILENAME = "execution-reconciliations.json"

DocumentT = TypeVar(
    "DocumentT",
    ApprovalPlansFile,
    ApprovalResultsFile,
    ExecutionReconciliationsFile,
    ExecutionOrderPlansFile,
    ExecutionOrderResultsFile,
)


class ExecutionStateError(ExecutionError):
    """Raised when execution audit state cannot be read or written."""


class ExecutionStateService:
    """Append-only file-backed store for approval and order audit records."""

    def __init__(
        self,
        *,
        approval_plans_path: Path | None = None,
        approval_results_path: Path | None = None,
        order_plans_path: Path | None = None,
        order_results_path: Path | None = None,
        events_path: Path | None = None,
        reconciliations_path: Path | None = None,
    ) -> None:
        state_dir = get_execution_state_dir()
        self._approval_plans_path = approval_plans_path or (state_dir / APPROVAL_PLANS_FILENAME)
        self._approval_results_path = approval_results_path or (
            state_dir / APPROVAL_RESULTS_FILENAME
        )
        self._order_plans_path = order_plans_path or (state_dir / ORDER_PLANS_FILENAME)
        self._order_results_path = order_results_path or (state_dir / ORDER_RESULTS_FILENAME)
        self._events_path = events_path or (state_dir / EVENTS_FILENAME)
        self._reconciliations_path = reconciliations_path or (
            state_dir / RECONCILIATIONS_FILENAME
        )

    def list_approval_plans(self) -> list[ApprovalPlanRecord]:
        """Return approval plans in append order."""
        return self._load_document(self._approval_plans_path, ApprovalPlansFile).plans

    def append_approval_plan(self, record: ApprovalPlanRecord) -> None:
        """Append one approval plan record."""
        document = self._load_document(self._approval_plans_path, ApprovalPlansFile)
        document.plans.append(record)
        self._write_document(self._approval_plans_path, document)

    def list_approval_results(self) -> list[ApprovalResultRecord]:
        """Return approval results in append order."""
        return self._load_document(self._approval_results_path, ApprovalResultsFile).results

    def append_approval_result(self, record: ApprovalResultRecord) -> None:
        """Append one approval result record."""
        document = self._load_document(self._approval_results_path, ApprovalResultsFile)
        document.results.append(record)
        self._write_document(self._approval_results_path, document)

    def list_order_plans(self) -> list[ExecutionOrderPlanRecord]:
        """Return order lifecycle plans in append order."""
        return self._load_document(self._order_plans_path, ExecutionOrderPlansFile).plans

    def append_order_plan(self, record: ExecutionOrderPlanRecord) -> None:
        """Append one order lifecycle plan record."""
        document = self._load_document(self._order_plans_path, ExecutionOrderPlansFile)
        document.plans.append(record)
        self._write_document(self._order_plans_path, document)

    def list_order_results(self) -> list[ExecutionOrderResultRecord]:
        """Return order lifecycle results in append order."""
        return self._load_document(self._order_results_path, ExecutionOrderResultsFile).results

    def append_order_result(self, record: ExecutionOrderResultRecord) -> None:
        """Append one order lifecycle result record."""
        document = self._load_document(self._order_results_path, ExecutionOrderResultsFile)
        document.results.append(record)
        self._write_document(self._order_results_path, document)

    def list_execution_events(
        self,
        *,
        session_id: str | None = None,
    ) -> list[CapturedExecutionEvent]:
        """Read execution-watch events in append order."""
        if not self._events_path.exists():
            return []

        try:
            raw_lines = self._events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ExecutionStateError(
                f"Could not read execution state at '{self._events_path}'."
            ) from exc

        items: list[CapturedExecutionEvent] = []
        try:
            for line in raw_lines:
                if not line.strip():
                    continue
                item = CapturedExecutionEvent.model_validate_json(line)
                if session_id is None or item.session_id == session_id:
                    items.append(item)
        except (ValidationError, ValueError) as exc:
            raise ExecutionStateError(
                f"Execution state at '{self._events_path}' is invalid."
            ) from exc
        return items

    def append_execution_event(self, record: CapturedExecutionEvent) -> None:
        """Append one normalized execution event as JSONL."""
        self.append_execution_events([record])

    def append_execution_events(self, records: list[CapturedExecutionEvent]) -> None:
        """Append normalized execution events in deterministic order."""
        if not records:
            return

        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._events_path.open("a", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    payload = json.dumps(record.model_dump(mode="json"), sort_keys=True)
                    handle.write(payload + "\n")
        except OSError as exc:
            raise ExecutionStateError(
                f"Could not write execution state at '{self._events_path}'."
            ) from exc

    def list_reconciliations(self) -> list[ExecutionReconciliationRecord]:
        """Return persisted reconciliation runs in append order."""
        document = self._load_document(
            self._reconciliations_path,
            ExecutionReconciliationsFile,
        )
        return document.reconciliations

    def append_reconciliation(self, record: ExecutionReconciliationRecord) -> None:
        """Append one reconciliation run record."""
        document = self._load_document(
            self._reconciliations_path,
            ExecutionReconciliationsFile,
        )
        document.reconciliations.append(record)
        self._write_document(self._reconciliations_path, document)

    def _load_document(self, path: Path, model_type: type[DocumentT]) -> DocumentT:
        if not path.exists():
            return model_type()
        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise ExecutionStateError(f"Execution state at '{path}' is invalid.") from exc

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
            raise ExecutionStateError(f"Could not write execution state at '{path}'.") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_execution_state_dir() -> Path:
    """Resolve the gitignored execution state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
