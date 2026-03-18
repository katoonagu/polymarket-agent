"""High-level market watchlist, snapshot, and recurring resolver service."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from pm.data import DataClient, DataClientError, DataNotFoundError, DataValidationError
from pm.data.models import HoldersResponse, NormalizedOpenInterest
from pm.market.clob import ClobClient
from pm.market.exceptions import (
    ClobClientError,
    ClobNotFoundError,
    GammaClientError,
    GammaNotFoundError,
)
from pm.market.gamma import GammaClient, GammaSearchCandidate
from pm.market.models import (
    MarketSectionError,
    MarketSnapshotRecord,
    MarketSnapshotResponse,
    MarketSnapshotTokenSummary,
    MarketWatchListResponse,
    MarketWatchMutationResponse,
    MarketWatchRefreshResponse,
    NormalizedBook,
    NormalizedEvent,
    NormalizedMarket,
    NormalizedMidpointQuote,
    NormalizedSpreadQuote,
    RecurringMarketCandidate,
    RecurringMarketLatestResponse,
    RecurringMarketListResponse,
    WatchedMarket,
)
from pm.market.state import MarketStateService

T = TypeVar("T")
TOP_HOLDERS_LIMIT = 5
QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
INTERVAL_MARKERS = {
    "5m": ("5m", "5 min", "5 minute", "5 minutes"),
    "15m": ("15m", "15 min", "15 minute", "15 minutes"),
    "1h": ("1h", "1 hour", "60 min", "60 minutes"),
}


class MarketValidationError(RuntimeError):
    """Raised when market-intelligence inputs fail deterministic validation."""


class MarketIntelService:
    """High-level read-only market watchlist and recurring resolver service."""

    def __init__(self, state: MarketStateService | None = None) -> None:
        self._state = state or MarketStateService()

    def add_watch(
        self,
        slug: str,
        *,
        label: str | None = None,
        tags: list[str] | None = None,
    ) -> MarketWatchMutationResponse:
        """Add a market to the local watchlist after resolving it via Gamma."""
        with GammaClient() as gamma_client:
            market = gamma_client.get_market_by_slug(slug.strip())

        watched_market = WatchedMarket(
            market_slug=market.market_slug,
            event_slug=market.event_slug,
            question=market.question,
            label=_normalize_text(label),
            tags=_normalize_tags(tags),
            added_at=_utc_now_iso(),
        )
        self._state.add_watched_market(watched_market)
        return MarketWatchMutationResponse(market=watched_market)

    def list_watchlist(self) -> MarketWatchListResponse:
        """Return watched markets in registry order."""
        items = self._state.list_watchlist()
        return MarketWatchListResponse(items=items, total=len(items))

    def remove_watch(self, slug: str) -> MarketWatchMutationResponse:
        """Remove a market from the local watchlist."""
        market = self._state.remove_watched_market(slug)
        return MarketWatchMutationResponse(market=market)

    def snapshot_market(self, slug: str) -> MarketSnapshotResponse:
        """Build and persist a single market snapshot by slug."""
        snapshot = self._build_snapshot_record(slug=slug.strip(), allow_missing_market=False)
        self._state.append_snapshot(snapshot)
        return MarketSnapshotResponse(snapshot=snapshot)

    def refresh_watchlist(self) -> MarketWatchRefreshResponse:
        """Snapshot every watched market in watchlist order."""
        items: list[MarketSnapshotRecord] = []

        for watched_market in self._state.list_watchlist():
            snapshot = self._build_snapshot_record(
                slug=watched_market.market_slug,
                allow_missing_market=True,
                watched_market=watched_market,
            )
            self._state.append_snapshot(snapshot)
            items.append(snapshot)

        return MarketWatchRefreshResponse(items=items, total=len(items))

    def recurring_list(
        self,
        query: str,
        *,
        interval: str,
        limit: int,
    ) -> RecurringMarketListResponse:
        """Return ranked recurring-market candidates from public Gamma search."""
        normalized_query = _validate_query(query)
        normalized_interval = validate_recurring_interval(interval)
        ranked_items = self._resolve_recurring_candidates(
            normalized_query,
            interval=normalized_interval,
            limit=limit,
        )
        return RecurringMarketListResponse(
            query=normalized_query,
            interval=normalized_interval,
            items=ranked_items,
            total=len(ranked_items),
        )

    def recurring_latest(self, query: str, *, interval: str) -> RecurringMarketLatestResponse:
        """Return the single highest-ranked recurring-market candidate."""
        normalized_query = _validate_query(query)
        normalized_interval = validate_recurring_interval(interval)
        ranked_items = self._resolve_recurring_candidates(
            normalized_query,
            interval=normalized_interval,
            limit=1,
        )
        return RecurringMarketLatestResponse(
            query=normalized_query,
            interval=normalized_interval,
            item=ranked_items[0] if ranked_items else None,
        )

    def _build_snapshot_record(
        self,
        *,
        slug: str,
        allow_missing_market: bool,
        watched_market: WatchedMarket | None = None,
    ) -> MarketSnapshotRecord:
        snapshot_at = _utc_now_iso()
        watch_metadata = watched_market or self._state.find_watched_market(slug)
        errors: list[MarketSectionError] = []

        try:
            with GammaClient() as gamma_client:
                market = gamma_client.get_market_by_slug(slug)
                event_title = market.event_title
                if market.event_slug is not None:
                    event_slug = market.event_slug

                    def load_event() -> NormalizedEvent:
                        return gamma_client.get_event_by_slug(event_slug)

                    event = self._capture_partial(
                        section="event",
                        errors=errors,
                        operation=load_event,
                    )
                    if event is not None:
                        event_title = event.title
        except GammaNotFoundError as exc:
            if not allow_missing_market:
                raise

            errors.append(MarketSectionError(section="market", code="not_found", message=str(exc)))
            return MarketSnapshotRecord(
                snapshot_at=snapshot_at,
                market_slug=watch_metadata.market_slug if watch_metadata is not None else slug,
                event_slug=watch_metadata.event_slug if watch_metadata is not None else None,
                question=watch_metadata.question if watch_metadata is not None else None,
                watch_metadata=watch_metadata,
                errors=errors,
            )

        token_summaries = self._build_token_summaries(market, errors=errors)
        open_interest: str | None = None
        top_holders = []
        holders_total_returned = 0

        with DataClient() as data_client:
            def load_open_interest() -> NormalizedOpenInterest:
                return data_client.get_open_interest(market.market_slug)

            open_interest_result = self._capture_partial(
                section="open_interest",
                errors=errors,
                operation=load_open_interest,
            )
            if open_interest_result is not None:
                open_interest = open_interest_result.open_interest

            def load_holders() -> HoldersResponse:
                return data_client.get_holders(market.market_slug, limit=TOP_HOLDERS_LIMIT)

            holders_result = self._capture_partial(
                section="holders",
                errors=errors,
                operation=load_holders,
            )
            if holders_result is not None:
                top_holders = holders_result.items[:TOP_HOLDERS_LIMIT]
                holders_total_returned = holders_result.total

        return MarketSnapshotRecord(
            snapshot_at=snapshot_at,
            market_slug=market.market_slug,
            event_slug=market.event_slug,
            question=market.question,
            event_title=event_title,
            condition_id=market.condition_id,
            token_ids=market.token_ids,
            outcomes=market.outcomes,
            active=market.active,
            closed=market.closed,
            watch_metadata=watch_metadata,
            tokens=token_summaries,
            open_interest=open_interest,
            top_holders=top_holders,
            holders_total_returned=holders_total_returned,
            errors=errors,
        )

    def _build_token_summaries(
        self,
        market: NormalizedMarket,
        *,
        errors: list[MarketSectionError],
    ) -> list[MarketSnapshotTokenSummary]:
        tokens: list[MarketSnapshotTokenSummary] = []
        if not market.token_ids:
            return tokens

        with ClobClient() as clob_client:
            for index, token_id in enumerate(market.token_ids):
                token_summary = MarketSnapshotTokenSummary(
                    token_id=token_id,
                    outcome=market.outcomes[index] if index < len(market.outcomes) else None,
                )

                def load_midpoint(*, token_id: str = token_id) -> NormalizedMidpointQuote:
                    return clob_client.get_midpoint(token_id)

                midpoint = self._capture_partial(
                    section=f"token:{token_id}:midpoint",
                    errors=errors,
                    operation=load_midpoint,
                )
                if midpoint is not None:
                    token_summary.midpoint = midpoint.midpoint

                def load_spread(*, token_id: str = token_id) -> NormalizedSpreadQuote:
                    return clob_client.get_spread(token_id)

                spread = self._capture_partial(
                    section=f"token:{token_id}:spread",
                    errors=errors,
                    operation=load_spread,
                )
                if spread is not None:
                    token_summary.spread = spread.spread

                def load_book(*, token_id: str = token_id) -> NormalizedBook:
                    return clob_client.get_book(token_id)

                book = self._capture_partial(
                    section=f"token:{token_id}:book",
                    errors=errors,
                    operation=load_book,
                )
                if book is not None:
                    token_summary.best_bid = book.bids[0].price if book.bids else None
                    token_summary.best_ask = book.asks[0].price if book.asks else None
                    token_summary.bid_level_count = len(book.bids)
                    token_summary.ask_level_count = len(book.asks)

                tokens.append(token_summary)

        return tokens

    def _resolve_recurring_candidates(
        self,
        query: str,
        *,
        interval: str,
        limit: int,
    ) -> list[RecurringMarketCandidate]:
        search_limit = max(limit * 3, 20)
        with GammaClient() as gamma_client:
            candidates = gamma_client.search_market_candidates(query, limit=search_limit)

        ranked: list[tuple[RecurringMarketCandidate, tuple[object, ...]]] = []
        for search_candidate in candidates:
            interval_strength = _interval_match_strength(search_candidate.market, interval)
            if interval_strength == 0:
                continue

            query_score = _query_match_score(query, search_candidate.market)
            recency_source, recency_value = _candidate_recency(search_candidate)
            recurring_candidate = RecurringMarketCandidate(
                rank=0,
                match_score=(interval_strength * 100) + query_score,
                matched_interval=interval,
                recency_source=recency_source,
                **search_candidate.market.model_dump(mode="json"),
            )
            sort_key = (
                not search_candidate.market.active,
                search_candidate.market.closed,
                -interval_strength,
                -query_score,
                -recency_value.timestamp() if recency_value is not None else float("inf"),
                search_candidate.search_index if recency_value is None else 0,
                search_candidate.market.market_slug,
            )
            ranked.append((recurring_candidate, sort_key))

        ranked.sort(key=lambda item: item[1])
        items: list[RecurringMarketCandidate] = []
        for index, (recurring_candidate, _sort_key) in enumerate(ranked[:limit], start=1):
            items.append(recurring_candidate.model_copy(update={"rank": index}))
        return items

    @staticmethod
    def _capture_partial(
        *,
        section: str,
        errors: list[MarketSectionError],
        operation: Callable[[], T],
    ) -> T | None:
        try:
            return operation()
        except (
            GammaNotFoundError,
            GammaClientError,
            ClobNotFoundError,
            ClobClientError,
            DataValidationError,
            DataNotFoundError,
            DataClientError,
        ) as exc:
            errors.append(
                MarketSectionError(
                    section=section,
                    code=_error_code_for(exc),
                    message=str(exc),
                )
            )
            return None


def validate_recurring_interval(interval: str) -> str:
    """Validate recurring interval against the supported deterministic set."""
    normalized_interval = interval.strip().lower()
    if normalized_interval not in INTERVAL_MARKERS:
        raise MarketValidationError("Interval must be one of: 5m, 15m, 1h.")
    return normalized_interval


def _validate_query(query: str) -> str:
    normalized_query = query.strip()
    if not normalized_query:
        raise MarketValidationError("Recurring query is required.")
    return normalized_query


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return sorted({tag.strip() for tag in tags if tag.strip()})


def _query_match_score(query: str, market: NormalizedMarket) -> int:
    haystack = " ".join(
        [
            market.question,
            market.event_title or "",
            market.market_slug,
            market.event_slug or "",
        ]
    ).lower()
    query_tokens = set(QUERY_TOKEN_RE.findall(query.lower()))
    if not query_tokens:
        return 0
    return sum(1 for token in query_tokens if token in haystack)


def _interval_match_strength(market: NormalizedMarket, interval: str) -> int:
    haystack = " ".join(
        [
            market.question,
            market.event_title or "",
            market.market_slug,
            market.event_slug or "",
        ]
    ).lower()

    if interval in haystack:
        return 2

    for alias in INTERVAL_MARKERS[interval]:
        if alias.lower() in haystack:
            return 1
    return 0


def _candidate_recency(candidate: GammaSearchCandidate) -> tuple[str | None, datetime | None]:
    for field_name, value in (
        ("endDate", candidate.end_date),
        ("resolutionDate", candidate.resolution_date),
        ("startDate", candidate.start_date),
    ):
        parsed = _parse_time(value)
        if parsed is not None:
            return field_name, parsed
    return None, None


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized_value = value.strip()
    if not normalized_value:
        return None
    try:
        if normalized_value.endswith("Z"):
            normalized_value = normalized_value[:-1] + "+00:00"
        return datetime.fromisoformat(normalized_value)
    except ValueError:
        return None


def _error_code_for(exc: Exception) -> str:
    if isinstance(exc, (DataValidationError, MarketValidationError)):
        return "invalid_argument"
    if isinstance(exc, (GammaNotFoundError, ClobNotFoundError, DataNotFoundError)):
        return "not_found"
    return "request_failed"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
