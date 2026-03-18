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
    ExecutionOrderPlanRecord,
    ExecutionOrderPlansFile,
    ExecutionOrderResultRecord,
    ExecutionOrderResultsFile,
)

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_EXECUTION_STATE_DIR"
APPROVAL_PLANS_FILENAME = "approval-plans.json"
APPROVAL_RESULTS_FILENAME = "approval-results.json"
ORDER_PLANS_FILENAME = "execution-order-plans.json"
ORDER_RESULTS_FILENAME = "execution-order-results.json"

DocumentT = TypeVar(
    "DocumentT",
    ApprovalPlansFile,
    ApprovalResultsFile,
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
    ) -> None:
        state_dir = get_execution_state_dir()
        self._approval_plans_path = approval_plans_path or (state_dir / APPROVAL_PLANS_FILENAME)
        self._approval_results_path = approval_results_path or (
            state_dir / APPROVAL_RESULTS_FILENAME
        )
        self._order_plans_path = order_plans_path or (state_dir / ORDER_PLANS_FILENAME)
        self._order_results_path = order_results_path or (state_dir / ORDER_RESULTS_FILENAME)

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
