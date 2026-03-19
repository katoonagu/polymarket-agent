"""Local gitignored singleton state for the non-secret operator profile."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from pm.auth.exceptions import AuthProfileStateError
from pm.auth.models import OperatorProfile, OperatorProfileFile

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_AUTH_STATE_DIR"
PROFILE_FILENAME = "operator-profile.json"


class OperatorProfileStateService:
    """Versioned file-backed store for the non-secret operator profile."""

    def __init__(self, *, profile_path: Path | None = None) -> None:
        state_dir = get_auth_state_dir()
        self._profile_path = profile_path or (state_dir / PROFILE_FILENAME)

    @property
    def profile_path(self) -> Path:
        """Return the resolved operator-profile path."""
        return self._profile_path

    def load_profile(self) -> OperatorProfile | None:
        """Return the stored operator profile, if one exists."""
        if not self._profile_path.exists():
            return None
        return self._load_document().profile

    def save_profile(self, profile: OperatorProfile) -> None:
        """Persist one operator profile."""
        self._write_document(OperatorProfileFile(profile=profile))

    def clear_profile(self) -> bool:
        """Remove the stored operator profile, if it exists."""
        if not self._profile_path.exists():
            return False
        try:
            self._profile_path.unlink()
        except OSError as exc:
            raise AuthProfileStateError(
                f"Could not clear operator profile state at '{self._profile_path}'."
            ) from exc
        return True

    def _load_document(self) -> OperatorProfileFile:
        try:
            return OperatorProfileFile.model_validate_json(
                self._profile_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AuthProfileStateError(
                f"Operator profile state at '{self._profile_path}' is invalid."
            ) from exc

    def _write_document(self, document: OperatorProfileFile) -> None:
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._profile_path.parent,
                delete=False,
                prefix=f"{self._profile_path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)
            os.replace(temp_path, self._profile_path)
        except OSError as exc:
            raise AuthProfileStateError(
                f"Could not write operator profile state at '{self._profile_path}'."
            ) from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_auth_state_dir() -> Path:
    """Resolve the gitignored auth state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
