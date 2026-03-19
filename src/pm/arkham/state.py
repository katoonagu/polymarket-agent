"""Local gitignored state for Arkham enrichment cache."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ValidationError

from pm.arkham.exceptions import ArkhamError
from pm.arkham.models import ArkhamEnrichmentRecord, ArkhamEnrichmentsFile

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_ARKHAM_STATE_DIR"
ENRICHMENTS_FILENAME = "arkham-enrichments.json"


class ArkhamStateError(ArkhamError):
    """Raised when Arkham state cannot be read or written."""


class ArkhamStateService:
    """File-backed cache for latest Arkham enrichments."""

    def __init__(self, *, enrichments_path: Path | None = None) -> None:
        state_dir = get_arkham_state_dir()
        self._enrichments_path = enrichments_path or (state_dir / ENRICHMENTS_FILENAME)

    @property
    def enrichments_path(self) -> Path:
        """Return the resolved enrichment cache path."""
        return self._enrichments_path

    def list_enrichments(self) -> list[ArkhamEnrichmentRecord]:
        """Return cached enrichments in append order."""
        return self._load_document(self._enrichments_path, ArkhamEnrichmentsFile).enrichments

    def get_enrichment(self, address: str) -> ArkhamEnrichmentRecord | None:
        """Return one cached enrichment by address when present."""
        for record in reversed(self.list_enrichments()):
            if record.address == address:
                return record
        return None

    def upsert_enrichment(self, record: ArkhamEnrichmentRecord) -> ArkhamEnrichmentRecord:
        """Replace the latest record for one address and append it to the end."""
        document = self._load_document(self._enrichments_path, ArkhamEnrichmentsFile)
        document.enrichments = [
            item for item in document.enrichments if item.address != record.address
        ]
        document.enrichments.append(record)
        self._write_document(self._enrichments_path, document)
        return record

    def _load_document(
        self,
        path: Path,
        model_type: type[ArkhamEnrichmentsFile],
    ) -> ArkhamEnrichmentsFile:
        if not path.exists():
            return model_type()
        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise ArkhamStateError(f"Arkham state at '{path}' is invalid.") from exc

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
            raise ArkhamStateError(f"Could not write Arkham state at '{path}'.") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_arkham_state_dir() -> Path:
    """Resolve the default Arkham state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
