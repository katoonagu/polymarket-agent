"""Local gitignored append-only state for operator workflow sessions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from pm.ops.models import OpsSessionEventRecord, OpsSessionsFile, OpsSessionView

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_OPS_STATE_DIR"
SESSIONS_FILENAME = "ops-sessions.json"


class OpsStateError(RuntimeError):
    """Raised when ops session state cannot be read or written."""


class OpsSessionNotFoundError(OpsStateError):
    """Raised when the requested active or completed session does not exist."""


class OpsStateService:
    """Append-only file-backed store for operator workflow session events."""

    def __init__(self, *, sessions_path: Path | None = None) -> None:
        state_dir = get_ops_state_dir()
        self._sessions_path = sessions_path or (state_dir / SESSIONS_FILENAME)

    @property
    def sessions_path(self) -> Path:
        """Return the resolved ops-session state path."""
        return self._sessions_path

    def list_session_events(self) -> list[OpsSessionEventRecord]:
        """Return append-only session lifecycle events in stored order."""
        return self._load_document().events

    def append_session_event(self, record: OpsSessionEventRecord) -> None:
        """Append one session lifecycle event."""
        document = self._load_document()
        document.events.append(record)
        self._write_document(document)

    def list_sessions(self) -> list[OpsSessionView]:
        """Materialize session views from lifecycle events."""
        events = self.list_session_events()
        sessions: dict[str, OpsSessionView] = {}
        order: list[str] = []
        for event in events:
            if event.event_type == "start":
                sessions[event.session_id] = OpsSessionView(
                    session_id=event.session_id,
                    label=event.label,
                    started_at=event.started_at or event.occurred_at,
                    ended_at=None,
                    active=True,
                    summary_snapshot=None,
                )
                order.append(event.session_id)
                continue
            if event.event_type == "end":
                session = sessions.get(event.session_id)
                if session is None:
                    raise OpsStateError(
                        f"Ops session state at '{self._sessions_path}' is invalid."
                    )
                sessions[event.session_id] = session.model_copy(
                    update={
                        "ended_at": event.ended_at or event.occurred_at,
                        "active": False,
                        "summary_snapshot": event.summary_snapshot,
                    }
                )
                continue
            raise OpsStateError(f"Ops session state at '{self._sessions_path}' is invalid.")
        return [sessions[session_id] for session_id in order]

    def get_active_session(self) -> OpsSessionView | None:
        """Return the single active session, if one exists."""
        active = [session for session in self.list_sessions() if session.active]
        if len(active) > 1:
            raise OpsStateError(f"Ops session state at '{self._sessions_path}' is invalid.")
        return active[0] if active else None

    def get_latest_completed_session(self) -> OpsSessionView | None:
        """Return the latest completed session, if one exists."""
        completed = [session for session in self.list_sessions() if not session.active]
        return completed[-1] if completed else None

    def _load_document(self) -> OpsSessionsFile:
        if not self._sessions_path.exists():
            return OpsSessionsFile()
        try:
            return OpsSessionsFile.model_validate_json(
                self._sessions_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise OpsStateError(
                f"Ops session state at '{self._sessions_path}' is invalid."
            ) from exc

    def _write_document(self, document: OpsSessionsFile) -> None:
        self._sessions_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._sessions_path.parent,
                delete=False,
                prefix=f"{self._sessions_path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)
            os.replace(temp_path, self._sessions_path)
        except OSError as exc:
            raise OpsStateError(
                f"Could not write ops session state at '{self._sessions_path}'."
            ) from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_ops_state_dir() -> Path:
    """Resolve the gitignored ops state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
