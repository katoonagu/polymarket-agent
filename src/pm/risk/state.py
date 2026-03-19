"""Local gitignored state for strategy dispatch risk policies."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from pm.risk.models import RiskPoliciesFile

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_RISK_STATE_DIR"
POLICIES_FILENAME = "risk-policies.json"


class RiskStateError(RuntimeError):
    """Raised when risk policy state cannot be read or written."""


class RiskStateService:
    """File-backed store for effective risk policy configuration."""

    def __init__(self, *, policies_path: Path | None = None) -> None:
        state_dir = get_risk_state_dir()
        self._policies_path = policies_path or (state_dir / POLICIES_FILENAME)

    @property
    def policies_path(self) -> Path:
        """Return the resolved risk policy state path."""
        return self._policies_path

    def exists(self) -> bool:
        """Return whether the risk policy file exists."""
        return self._policies_path.exists()

    def load(self) -> RiskPoliciesFile:
        """Load a persisted risk policy file."""
        try:
            return RiskPoliciesFile.model_validate_json(
                self._policies_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise RiskStateError(
                f"Risk policy state at '{self._policies_path}' was not found."
            ) from exc
        except (OSError, ValidationError, ValueError) as exc:
            raise RiskStateError(
                f"Risk policy state at '{self._policies_path}' is invalid."
            ) from exc

    def write(self, document: RiskPoliciesFile) -> None:
        """Persist one versioned risk policy document atomically."""
        self._policies_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._policies_path.parent,
                delete=False,
                prefix=f"{self._policies_path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)
            os.replace(temp_path, self._policies_path)
        except OSError as exc:
            raise RiskStateError(
                f"Could not write risk policy state at '{self._policies_path}'."
            ) from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_risk_state_dir() -> Path:
    """Resolve the default gitignored risk state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
