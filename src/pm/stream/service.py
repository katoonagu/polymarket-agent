"""High-level read-only stream service composing public market and RTDS feeds."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from pm.market import GammaClient, GammaNotFoundError, NormalizedMarket
from pm.market.models import RecurringMarketCandidate
from pm.market.service import MarketIntelService, MarketValidationError
from pm.stream.market import MarketWebSocketClient
from pm.stream.models import (
    BoundedStreamSession,
    CapturedStreamEvent,
    CryptoStreamResponse,
    MarketWatchStreamResponse,
    MarketWatchStreamSummary,
    MarketWatchTokenSummary,
    RecurringStreamResponse,
    RecurringStreamSummary,
    StreamSectionError,
)
from pm.stream.rtds import RTDSClient
from pm.stream.runner import BoundedRunResult, StreamClientError, StreamValidationError
from pm.stream.state import StreamEventStore, StreamStateError

SUPPORTED_RECURRING_SYMBOLS = ("BTC", "ETH", "SOL")


class StreamService:
    """High-level bounded public streaming service."""

    def __init__(
        self,
        *,
        market_client: MarketWebSocketClient | None = None,
        crypto_client: RTDSClient | None = None,
        market_intel_service: MarketIntelService | None = None,
        store: StreamEventStore | None = None,
    ) -> None:
        shared_store = store or StreamEventStore()
        self._market_client = market_client or MarketWebSocketClient(store=shared_store)
        self._crypto_client = crypto_client or RTDSClient(store=shared_store)
        self._market_intel_service = market_intel_service or MarketIntelService()

    def stream_market(
        self,
        token_id: str,
        *,
        seconds: int,
        max_events: int | None = None,
    ) -> Any:
        """Run a bounded single-token market stream session."""
        return asyncio.run(
            self._market_client.stream_token(token_id, seconds=seconds, max_events=max_events)
        )

    def stream_crypto(
        self,
        symbol: str,
        *,
        source: str,
        seconds: int,
        max_events: int | None = None,
    ) -> CryptoStreamResponse:
        """Run a bounded crypto RTDS session."""
        return asyncio.run(
            self._crypto_client.stream_symbol(
                symbol,
                source=source,
                seconds=seconds,
                max_events=max_events,
            )
        )

    def stream_watch(
        self,
        slug: str,
        *,
        seconds: int,
        max_events: int | None = None,
    ) -> MarketWatchStreamResponse:
        """Run a bounded market stream session across every token in a market."""
        normalized_slug = slug.strip()
        if not normalized_slug:
            raise StreamValidationError("Market slug is required.")

        with GammaClient() as gamma_client:
            market = gamma_client.get_market_by_slug(normalized_slug)

        result = asyncio.run(
            self._market_client.stream_tokens(
                market.token_ids,
                seconds=seconds,
                max_events=max_events,
            )
        )
        summary = _build_watch_summary(market, result.events)
        return MarketWatchStreamResponse(
            session=result.session,
            summary=summary,
            events=result.events,
            errors=result.errors,
        )

    def stream_recurring(
        self,
        query: str,
        *,
        interval: str,
        seconds: int,
        max_events: int | None = None,
    ) -> RecurringStreamResponse:
        """Run a bounded combined recurring market and RTDS session."""
        try:
            recurring = self._market_intel_service.recurring_latest(query, interval=interval)
        except MarketValidationError as exc:
            raise StreamValidationError(str(exc)) from exc

        if recurring.item is None:
            raise StreamValidationError(
                f"No recurring market candidates found for query '{query.strip()}' "
                f"and interval '{interval.strip()}'."
            )

        recurring_market = recurring.item
        crypto_symbol = infer_crypto_symbol(recurring_market)
        if crypto_symbol is None:
            raise StreamValidationError(
                "Could not infer a supported crypto symbol from the recurring market candidate."
            )

        return asyncio.run(
            self._stream_recurring_async(
                recurring_market,
                crypto_symbol=crypto_symbol,
                seconds=seconds,
                max_events=max_events,
            )
        )

    async def _stream_recurring_async(
        self,
        recurring_market: RecurringMarketCandidate,
        *,
        crypto_symbol: str,
        seconds: int,
        max_events: int | None = None,
    ) -> RecurringStreamResponse:
        errors: list[StreamSectionError] = []

        market_task = asyncio.create_task(
            self._market_client.stream_tokens(
                recurring_market.token_ids,
                seconds=seconds,
                max_events=max_events,
            )
        )
        crypto_task = asyncio.create_task(
            self._crypto_client.stream_symbol(
                crypto_symbol,
                source="binance",
                seconds=seconds,
                max_events=max_events,
            )
        )

        market_result, crypto_result = await asyncio.gather(
            market_task,
            crypto_task,
            return_exceptions=True,
        )
        market_exception = market_result if isinstance(market_result, Exception) else None
        crypto_exception = crypto_result if isinstance(crypto_result, Exception) else None

        market_summary: MarketWatchStreamSummary | None = None
        crypto_summary = None
        market_session: BoundedStreamSession | None = None
        crypto_session: BoundedStreamSession | None = None
        events: list[CapturedStreamEvent] = []

        if market_exception is not None:
            errors.append(_stream_error("market_stream", market_exception))
        else:
            market_response = cast(BoundedRunResult, market_result)
            market_summary = _build_watch_summary(
                _as_market(recurring_market),
                market_response.events,
            )
            market_session = market_response.session
            errors.extend(market_response.errors)
            events.extend(market_response.events)

        if crypto_exception is not None:
            errors.append(_stream_error("crypto_stream", crypto_exception))
        else:
            crypto_response = cast(CryptoStreamResponse, crypto_result)
            crypto_summary = crypto_response.summary
            crypto_session = crypto_response.session
            errors.extend(crypto_response.errors)
            events.extend(crypto_response.events)

        if market_session is None and crypto_session is None:
            if market_exception is not None:
                raise market_exception
            if crypto_exception is not None:
                raise crypto_exception
            raise StreamClientError("Could not establish recurring stream session.")

        session = _merge_sessions(
            market_session=market_session,
            crypto_session=crypto_session,
        )
        events.sort(key=lambda item: (item.captured_at, item.event_type, item.source))
        summary = RecurringStreamSummary(
            recurring_market=recurring_market,
            market=market_summary,
            crypto=crypto_summary,
            merged_event_count=len(events),
        )
        return RecurringStreamResponse(
            session=session,
            summary=summary,
            events=events,
            errors=errors,
        )


def infer_crypto_symbol(market: RecurringMarketCandidate) -> str | None:
    """Infer a supported crypto base asset from recurring market text."""
    haystack = " ".join(
        [
            market.market_slug,
            market.event_slug or "",
            market.question,
            market.event_title or "",
        ]
    ).upper()
    for symbol in SUPPORTED_RECURRING_SYMBOLS:
        if symbol in haystack:
            return symbol
    return None


def _build_watch_summary(
    market: NormalizedMarket,
    events: list[CapturedStreamEvent],
) -> MarketWatchStreamSummary:
    token_summaries: list[MarketWatchTokenSummary] = []
    aggregate_event_count = 0
    for index, token_id in enumerate(market.token_ids):
        matching = [
            event.market_event
            for event in events
            if event.market_event is not None and event.market_event.token_id == token_id
        ]
        aggregate_event_count += len(matching)
        token_summaries.append(
            MarketWatchTokenSummary(
                token_id=token_id,
                outcome=market.outcomes[index] if index < len(market.outcomes) else None,
                event_count=len(matching),
                latest_best_bid=_latest_market_value(matching, "best_bid"),
                latest_best_ask=_latest_market_value(matching, "best_ask"),
                latest_midpoint=_latest_market_value(matching, "midpoint"),
                latest_spread=_latest_market_value(matching, "spread"),
            )
        )

    return MarketWatchStreamSummary(
        market_slug=market.market_slug,
        condition_id=market.condition_id,
        token_ids=market.token_ids,
        outcomes=market.outcomes,
        active=market.active,
        closed=market.closed,
        tokens=token_summaries,
        aggregate_event_count=aggregate_event_count,
    )


def _latest_market_value(items: list[Any], field_name: str) -> str | None:
    for item in reversed(items):
        value = getattr(item, field_name, None)
        if value is not None:
            return value
    return None


def _stream_error(section: str, exc: Exception) -> StreamSectionError:
    return StreamSectionError(
        section=section,
        code=_error_code_for(exc),
        message=str(exc),
    )


def _error_code_for(exc: Exception) -> str:
    if isinstance(exc, (StreamValidationError, MarketValidationError)):
        return "invalid_argument"
    if isinstance(exc, GammaNotFoundError):
        return "not_found"
    if isinstance(exc, StreamStateError):
        return "state_error"
    return "request_failed"


def _as_market(item: RecurringMarketCandidate) -> NormalizedMarket:
    return NormalizedMarket(
        market_slug=item.market_slug,
        event_slug=item.event_slug,
        question=item.question,
        event_title=item.event_title,
        active=item.active,
        closed=item.closed,
        enable_order_book=item.enable_order_book,
        condition_id=item.condition_id,
        token_ids=item.token_ids,
        outcomes=item.outcomes,
        min_tick=item.min_tick,
        min_order_size=item.min_order_size,
    )


def _merge_sessions(
    *,
    market_session: BoundedStreamSession | None,
    crypto_session: BoundedStreamSession | None,
) -> BoundedStreamSession:
    primary = market_session or crypto_session
    assert primary is not None
    if market_session is None or crypto_session is None:
        return primary

    started_at = min(market_session.started_at, crypto_session.started_at)
    ended_at = max(market_session.ended_at, crypto_session.ended_at)
    return BoundedStreamSession(
        session_id=primary.session_id,
        stream_kind="recurring",
        source="market+binance",
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=max(market_session.duration_seconds, crypto_session.duration_seconds),
        requested_seconds=max(market_session.requested_seconds, crypto_session.requested_seconds),
        max_events=primary.max_events,
        captured_event_count=(
            market_session.captured_event_count + crypto_session.captured_event_count
        ),
        reconnect_count=market_session.reconnect_count + crypto_session.reconnect_count,
    )
