"""Bounded async websocket session runner utilities."""

from __future__ import annotations

import asyncio
import importlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any, TypeVar
from uuid import uuid4

from pm.stream.models import BoundedStreamSession, CapturedStreamEvent, StreamSectionError
from pm.stream.state import StreamStateError

NormalizedEventT = TypeVar("NormalizedEventT")
ConnectCallable = Callable[..., Any]
NormalizeCallable = Callable[[dict[str, Any]], list[NormalizedEventT]]
WrapCallable = Callable[[NormalizedEventT, str, str, str], CapturedStreamEvent]
PersistCallable = Callable[[CapturedStreamEvent], None]
ClockCallable = Callable[[], str]
SleepCallable = Callable[[float], Awaitable[None]]

DEFAULT_BACKOFFS = (1.0, 2.0)
DEFAULT_PING_INTERVAL = 10.0
DEFAULT_PING_TIMEOUT = 10.0
DEFAULT_OPEN_TIMEOUT = 10.0
DEFAULT_CLOSE_TIMEOUT = 5.0


class StreamClientError(RuntimeError):
    """Raised when a bounded public stream session cannot be established or completed."""


class StreamValidationError(RuntimeError):
    """Raised when stream inputs fail deterministic validation."""


@dataclass(slots=True)
class BoundedRunResult:
    """Internal bounded-session result."""

    session: BoundedStreamSession
    events: list[CapturedStreamEvent]
    errors: list[StreamSectionError]


async def run_bounded_websocket_session(
    *,
    endpoint: str,
    stream_kind: str,
    source: str,
    subscribe_payload: str,
    normalize_message: NormalizeCallable[NormalizedEventT],
    wrap_event: WrapCallable[NormalizedEventT],
    persist_event: PersistCallable,
    seconds: int,
    max_events: int | None,
    section: str,
    connect: ConnectCallable | None = None,
    sleep: SleepCallable = asyncio.sleep,
    now_iso: ClockCallable | None = None,
    max_retries: int = 2,
    ping_interval: float = DEFAULT_PING_INTERVAL,
    ping_timeout: float = DEFAULT_PING_TIMEOUT,
    open_timeout: float = DEFAULT_OPEN_TIMEOUT,
    close_timeout: float = DEFAULT_CLOSE_TIMEOUT,
) -> BoundedRunResult:
    """Run a bounded async websocket session with limited reconnects."""
    if seconds <= 0:
        raise StreamValidationError("Stream duration must be greater than zero seconds.")
    if max_events is not None and max_events <= 0:
        raise StreamValidationError("Max events must be greater than zero when provided.")

    connect_callable = connect or _default_connect
    resolved_now_iso = now_iso or _utc_now_iso
    session_id = uuid4().hex
    started_at = resolved_now_iso()
    started_monotonic = monotonic()
    events: list[CapturedStreamEvent] = []
    errors: list[StreamSectionError] = []
    reconnect_count = 0
    attempts = 0

    while True:
        remaining_seconds = seconds - (monotonic() - started_monotonic)
        if remaining_seconds <= 0:
            break

        try:
            async with connect_callable(
                endpoint,
                ping_interval=ping_interval,
                ping_timeout=ping_timeout,
                open_timeout=open_timeout,
                close_timeout=close_timeout,
            ) as websocket:
                await websocket.send(subscribe_payload)
                while True:
                    elapsed = monotonic() - started_monotonic
                    if elapsed >= seconds:
                        break
                    if max_events is not None and len(events) >= max_events:
                        break

                    timeout = max(0.05, min(0.25, seconds - elapsed))
                    try:
                        raw_message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                    except TimeoutError:
                        continue

                    parsed_message = _parse_message(raw_message)
                    if parsed_message is None:
                        continue

                    normalized_events = normalize_message(parsed_message)
                    for item in normalized_events:
                        captured_at = resolved_now_iso()
                        captured = wrap_event(item, session_id, source, captured_at)
                        persist_event(captured)
                        events.append(captured)
                        if max_events is not None and len(events) >= max_events:
                            break

                if monotonic() - started_monotonic >= seconds:
                    break
                if max_events is not None and len(events) >= max_events:
                    break

        except StreamStateError:
            raise
        except Exception as exc:
            if attempts >= max_retries:
                if events:
                    errors.append(
                        StreamSectionError(
                            section=section,
                            code="request_failed",
                            message=f"Reconnect limit reached: {exc}",
                        )
                    )
                    break
                raise StreamClientError(f"Could not establish {section} stream session.") from exc

            reconnect_count += 1
            attempts += 1
            await sleep(DEFAULT_BACKOFFS[min(attempts - 1, len(DEFAULT_BACKOFFS) - 1)])
            continue
        else:
            break

    ended_at = resolved_now_iso()
    duration = max(0, int(round(monotonic() - started_monotonic)))
    session = BoundedStreamSession(
        session_id=session_id,
        stream_kind=stream_kind,
        source=source,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration,
        requested_seconds=seconds,
        max_events=max_events,
        captured_event_count=len(events),
        reconnect_count=reconnect_count,
    )
    return BoundedRunResult(session=session, events=events, errors=errors)


def _default_connect(*args: Any, **kwargs: Any) -> Any:
    module = importlib.import_module("websockets")
    connect = getattr(module, "connect", None)
    if connect is None:
        raise StreamClientError("The 'websockets' dependency is required for stream commands.")
    return connect(*args, **kwargs)


def _parse_message(raw_message: str | bytes) -> dict[str, Any] | None:
    if isinstance(raw_message, bytes):
        raw_text = raw_message.decode("utf-8", errors="ignore")
    else:
        raw_text = raw_message

    stripped = raw_text.strip()
    if not stripped or stripped in {"PING", "PONG"}:
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, dict):
        return parsed
    return None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
