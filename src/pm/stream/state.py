"""Append-only local JSONL persistence for captured public stream events."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from pm.stream.models import CapturedStreamEvent

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_STREAM_STATE_DIR"
EVENTS_FILENAME = "stream-events.jsonl"


class StreamStateError(RuntimeError):
    """Raised when local stream state cannot be read or written."""


class StreamEventStore:
    """Small append-only JSONL store for normalized stream events."""

    def __init__(self, *, path: Path | None = None) -> None:
        state_dir = get_stream_state_dir()
        self._path = path or (state_dir / EVENTS_FILENAME)

    @property
    def path(self) -> Path:
        """Return the resolved stream event log path."""
        return self._path

    def append_event(self, event: CapturedStreamEvent) -> None:
        """Append one normalized event as a JSON line."""
        self.append_events([event])

    def append_events(self, events: list[CapturedStreamEvent]) -> None:
        """Append normalized events in deterministic order."""
        if not events:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("a", encoding="utf-8", newline="\n") as handle:
                for event in events:
                    payload = json.dumps(event.model_dump(mode="json"), sort_keys=True)
                    handle.write(payload + "\n")
        except OSError as exc:
            raise StreamStateError(f"Could not write stream state at '{self._path}'.") from exc

    def list_events(self, *, session_id: str | None = None) -> list[CapturedStreamEvent]:
        """Read persisted events in append order."""
        if not self._path.exists():
            return []

        try:
            raw_lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise StreamStateError(f"Could not read stream state at '{self._path}'.") from exc

        items: list[CapturedStreamEvent] = []
        try:
            for line in raw_lines:
                if not line.strip():
                    continue
                item = CapturedStreamEvent.model_validate_json(line)
                if session_id is None or item.session_id == session_id:
                    items.append(item)
        except (ValidationError, ValueError) as exc:
            raise StreamStateError(f"Stream state at '{self._path}' is invalid.") from exc

        return items


def get_stream_state_dir() -> Path:
    """Resolve the default gitignored stream state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH
