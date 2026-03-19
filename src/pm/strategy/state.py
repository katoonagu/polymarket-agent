"""Local gitignored state for strategy intents and review decisions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pm.strategy.models import (
    StrategyCandidateIntent,
    StrategyDecisionRecord,
    StrategyDecisionsFile,
    StrategyDispatchResultRecord,
    StrategyDispatchResultsFile,
    StrategyExecutionLinkRecord,
    StrategyExecutionLinksFile,
    StrategyIntentsFile,
)
from pm.strategy.registry import StrategyRegistryError, get_strategy_state_dir

INTENTS_FILENAME = "strategy-intents.json"
DECISIONS_FILENAME = "strategy-decisions.json"
EXECUTION_LINKS_FILENAME = "strategy-execution-links.json"
DISPATCH_RESULTS_FILENAME = "strategy-dispatch-results.json"

DocumentT = TypeVar(
    "DocumentT",
    StrategyIntentsFile,
    StrategyDecisionsFile,
    StrategyExecutionLinksFile,
    StrategyDispatchResultsFile,
)


class StrategyStateError(StrategyRegistryError):
    """Raised when strategy intent or decision state cannot be read or written."""


class StrategyIntentNotFoundError(StrategyStateError):
    """Raised when a candidate intent id is unknown."""


class StrategyExecutionNotFoundError(StrategyStateError):
    """Raised when a strategy dispatch execution id is unknown."""


class StrategyStateService:
    """Small append-only file-backed store for strategy intents and decisions."""

    def __init__(
        self,
        *,
        intents_path: Path | None = None,
        decisions_path: Path | None = None,
        execution_links_path: Path | None = None,
        dispatch_results_path: Path | None = None,
    ) -> None:
        state_dir = get_strategy_state_dir()
        self._intents_path = intents_path or (state_dir / INTENTS_FILENAME)
        self._decisions_path = decisions_path or (state_dir / DECISIONS_FILENAME)
        self._execution_links_path = execution_links_path or (
            state_dir / EXECUTION_LINKS_FILENAME
        )
        self._dispatch_results_path = dispatch_results_path or (
            state_dir / DISPATCH_RESULTS_FILENAME
        )

    @property
    def intents_path(self) -> Path:
        """Return the resolved candidate-intent state path."""
        return self._intents_path

    @property
    def decisions_path(self) -> Path:
        """Return the resolved decision state path."""
        return self._decisions_path

    @property
    def execution_links_path(self) -> Path:
        """Return the resolved strategy-execution link state path."""
        return self._execution_links_path

    @property
    def dispatch_results_path(self) -> Path:
        """Return the resolved strategy dispatch-result state path."""
        return self._dispatch_results_path

    def list_intents(self, strategy_name: str | None = None) -> list[StrategyCandidateIntent]:
        """Return persisted candidate intents in append order."""
        intents = self._load_document(self._intents_path, StrategyIntentsFile).intents
        if strategy_name is None:
            return intents
        return [intent for intent in intents if intent.strategy_name == strategy_name]

    def get_intent(self, intent_id: str) -> StrategyCandidateIntent:
        """Return a single candidate intent by id."""
        for intent in self.list_intents():
            if intent.intent_id == intent_id:
                return intent
        raise StrategyIntentNotFoundError(f"intent '{intent_id}' was not found")

    def append_intents(
        self,
        intents: list[StrategyCandidateIntent],
    ) -> list[StrategyCandidateIntent]:
        """Append only new candidate intents and return the ones that were persisted."""
        if not intents:
            return []
        document = self._load_document(self._intents_path, StrategyIntentsFile)
        existing_ids = {item.intent_id for item in document.intents}
        appended: list[StrategyCandidateIntent] = []
        for intent in intents:
            if intent.intent_id in existing_ids:
                continue
            document.intents.append(intent)
            existing_ids.add(intent.intent_id)
            appended.append(intent)
        if appended:
            self._write_document(self._intents_path, document)
        return appended

    def list_decisions(self, intent_id: str | None = None) -> list[StrategyDecisionRecord]:
        """Return persisted review decisions in append order."""
        decisions = self._load_document(self._decisions_path, StrategyDecisionsFile).decisions
        if intent_id is None:
            return decisions
        return [decision for decision in decisions if decision.intent_id == intent_id]

    def append_decision(self, decision: StrategyDecisionRecord) -> None:
        """Append one review decision."""
        document = self._load_document(self._decisions_path, StrategyDecisionsFile)
        document.decisions.append(decision)
        self._write_document(self._decisions_path, document)

    def list_execution_links(
        self,
        *,
        intent_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[StrategyExecutionLinkRecord]:
        """Return persisted strategy-execution links in append order."""
        links = self._load_document(
            self._execution_links_path,
            StrategyExecutionLinksFile,
        ).links
        if intent_id is not None:
            links = [item for item in links if item.intent_id == intent_id]
        if execution_id is not None:
            links = [item for item in links if item.execution_id == execution_id]
        return links

    def get_execution_link(self, execution_id: str) -> StrategyExecutionLinkRecord:
        """Return one persisted strategy-execution link by execution id."""
        for link in self.list_execution_links(execution_id=execution_id):
            return link
        raise StrategyExecutionNotFoundError(
            f"strategy execution '{execution_id}' was not found"
        )

    def append_execution_link(self, link: StrategyExecutionLinkRecord) -> None:
        """Append one strategy-execution link record."""
        document = self._load_document(
            self._execution_links_path,
            StrategyExecutionLinksFile,
        )
        document.links.append(link)
        self._write_document(self._execution_links_path, document)

    def list_dispatch_results(
        self,
        *,
        intent_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[StrategyDispatchResultRecord]:
        """Return persisted strategy dispatch results in append order."""
        results = self._load_document(
            self._dispatch_results_path,
            StrategyDispatchResultsFile,
        ).results
        if intent_id is not None:
            results = [item for item in results if item.intent_id == intent_id]
        if execution_id is not None:
            results = [item for item in results if item.execution_id == execution_id]
        return results

    def get_dispatch_result(self, execution_id: str) -> StrategyDispatchResultRecord:
        """Return one persisted strategy dispatch result by execution id."""
        for result in self.list_dispatch_results(execution_id=execution_id):
            return result
        raise StrategyExecutionNotFoundError(
            f"strategy execution '{execution_id}' was not found"
        )

    def append_dispatch_result(self, result: StrategyDispatchResultRecord) -> None:
        """Append one strategy dispatch result record."""
        document = self._load_document(
            self._dispatch_results_path,
            StrategyDispatchResultsFile,
        )
        document.results.append(result)
        self._write_document(self._dispatch_results_path, document)

    def _load_document(self, path: Path, model_type: type[DocumentT]) -> DocumentT:
        if not path.exists():
            return model_type()
        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise StrategyStateError(f"Strategy state at '{path}' is invalid.") from exc

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
            raise StrategyStateError(f"Could not write strategy state at '{path}'.") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
