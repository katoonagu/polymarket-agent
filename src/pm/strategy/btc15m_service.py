"""BTC 15-minute Chainlink directional ladder recorder and paper simulator."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from pm.market.clob import ClobClient
from pm.market.exceptions import ClobClientError, ClobNotFoundError
from pm.market.gamma import GammaClient, GammaSearchCandidate
from pm.market.models import NormalizedBookLevel, RecurringMarketCandidate
from pm.market.service import MarketIntelService, MarketValidationError, validate_recurring_interval
from pm.strategy.btc15m_models import (
    Btc15mBoundaryDecisionRecord,
    Btc15mBoundaryObservationRecord,
    Btc15mLadderRungResult,
    Btc15mMarketSample,
    Btc15mPaperEvaluation,
    Btc15mPaperRunRecord,
    Btc15mPaperRunResponse,
    Btc15mPriceMark,
    Btc15mPriceTick,
    Btc15mReasonBlock,
    Btc15mRecordStartResponse,
    Btc15mRecordWindowResponse,
    Btc15mReplayRecord,
    Btc15mReplayResponse,
    Btc15mReportResponse,
    Btc15mReportSummary,
    Btc15mSectionError,
    Btc15mWindowIdentity,
    Btc15mWindowRecord,
)
from pm.strategy.btc15m_state import Btc15mStateError, Btc15mStateService
from pm.stream.market import MarketWebSocketClient
from pm.stream.models import (
    CapturedStreamEvent,
    CryptoStreamResponse,
    MarketWatchStreamResponse,
    StreamSectionError,
)
from pm.stream.rtds import RTDSClient
from pm.stream.runner import BoundedRunResult, StreamValidationError

DEFAULT_RECORD_SECONDS = 60
DEFAULT_RECORD_QUERY = "btc"
DEFAULT_RECORD_INTERVAL = "15m"
DEFAULT_POST_END_WAIT_SECONDS = 60
DEFAULT_DECISION_STALE_SECONDS = 15
DEFAULT_MARKET_STALE_SECONDS = 5
DEFAULT_PAPER_RUN_LIMIT = 20
WINDOW_DURATION = timedelta(minutes=15)
MINUTE_FIVE_OFFSET = timedelta(minutes=5)
MINUTE_TEN_OFFSET = timedelta(minutes=10)
RUNG_PRICES = (
    Decimal("0.30"),
    Decimal("0.20"),
    Decimal("0.10"),
)
RUNG_NOTIONALS = (
    Decimal("20"),
    Decimal("15"),
    Decimal("15"),
)


class Btc15mValidationError(RuntimeError):
    """Raised when BTC15m CLI or service inputs are invalid."""


@dataclass(slots=True)
class _ResolvedWindow:
    candidate: RecurringMarketCandidate
    window: Btc15mWindowIdentity
    window_start_dt: datetime | None
    window_end_dt: datetime | None


class Btc15mStrategyService:
    """Recorder, replay, and paper-evaluation service for BTC15m research."""

    def __init__(
        self,
        *,
        state: Btc15mStateService | None = None,
        market_intel_service: MarketIntelService | None = None,
        market_client: MarketWebSocketClient | None = None,
        crypto_client: RTDSClient | None = None,
        gamma_client_cls: type[GammaClient] = GammaClient,
        clob_client_cls: type[ClobClient] = ClobClient,
        now: Any | None = None,
    ) -> None:
        self._state = state or Btc15mStateService()
        self._market_intel_service = market_intel_service or MarketIntelService()
        self._market_client = market_client or MarketWebSocketClient()
        self._crypto_client = crypto_client or RTDSClient()
        self._gamma_client_cls = gamma_client_cls
        self._clob_client_cls = clob_client_cls
        self._now = now or _utc_now

    def record_start(self, *, seconds: int = DEFAULT_RECORD_SECONDS) -> Btc15mRecordStartResponse:
        """Run one bounded BTC15m recorder session for the latest recurring market."""
        if seconds <= 0:
            raise Btc15mValidationError("Recorder duration must be greater than zero seconds.")

        session_id = _make_id("btc15m_record")
        started_at = _isoformat(self._now())
        cursor = self._now()
        global_end = cursor + timedelta(seconds=seconds)
        items: list[Btc15mWindowRecord] = []
        errors: list[Btc15mSectionError] = []
        seen_window_ids: set[str] = set()

        while cursor < global_end:
            resolved = self._resolve_latest_window()
            if resolved.window.window_id in seen_window_ids:
                break
            seen_window_ids.add(resolved.window.window_id)

            chunk_end = global_end
            if resolved.window_end_dt is not None:
                chunk_end = min(
                    chunk_end,
                    resolved.window_end_dt + timedelta(seconds=DEFAULT_POST_END_WAIT_SECONDS),
                )
            chunk_seconds = max(1, int((chunk_end - cursor).total_seconds()))
            record = self._record_resolved_window(
                resolved,
                seconds=chunk_seconds,
                recorder_session_id=session_id,
            )
            items.append(record)
            errors.extend(record.errors)
            cursor = chunk_end

        ended_at = _isoformat(min(self._now(), global_end))
        return Btc15mRecordStartResponse(
            session_id=session_id,
            started_at=started_at,
            ended_at=ended_at,
            requested_seconds=seconds,
            items=items,
            total=len(items),
            errors=errors,
        )

    def record_window(self, *, slug: str) -> Btc15mRecordWindowResponse:
        """Record one specific BTC15m window until end-boundary capture or timeout."""
        normalized_slug = slug.strip()
        if not normalized_slug:
            raise Btc15mValidationError("Market slug is required.")

        session_id = _make_id("btc15m_record")
        started_at = _isoformat(self._now())
        resolved = self._resolve_window_by_slug(normalized_slug)
        now = self._now()
        if resolved.window_end_dt is not None:
            timeout_at = resolved.window_end_dt + timedelta(seconds=DEFAULT_POST_END_WAIT_SECONDS)
            seconds = max(1, int((timeout_at - now).total_seconds()))
        else:
            seconds = DEFAULT_RECORD_SECONDS
        record = self._record_resolved_window(
            resolved,
            seconds=seconds,
            recorder_session_id=session_id,
        )
        ended_at = _isoformat(self._now())
        return Btc15mRecordWindowResponse(
            session_id=session_id,
            slug=normalized_slug,
            started_at=started_at,
            ended_at=ended_at,
            requested_seconds=seconds,
            items=[record],
            total=1,
            errors=record.errors,
        )

    def replay(self, *, from_at: str, to_at: str) -> Btc15mReplayResponse:
        """Replay recorded BTC15m windows across a time range."""
        from_dt = _parse_iso_timestamp(from_at)
        to_dt = _parse_iso_timestamp(to_at)
        if from_dt >= to_dt:
            raise Btc15mValidationError("--from must be earlier than --to.")

        items: list[Btc15mPaperEvaluation] = []
        for record in self._iter_latest_windows():
            window_start = _parse_iso_optional(record.window.window_start_at)
            if window_start is None or window_start < from_dt or window_start >= to_dt:
                continue
            items.append(self._evaluate_window(record))
        replay = Btc15mReplayRecord(
            replay_id=_make_id("btc15m_replay"),
            created_at=_isoformat(self._now()),
            from_at=_isoformat(from_dt),
            to_at=_isoformat(to_dt),
            items=items,
            total=len(items),
            errors=[],
        )
        self._state.append_replay(replay)
        return Btc15mReplayResponse(replay=replay)

    def paper_run(self, *, limit: int = DEFAULT_PAPER_RUN_LIMIT) -> Btc15mPaperRunResponse:
        """Evaluate oldest completed, unevaluated recorded windows chronologically."""
        if limit <= 0:
            raise Btc15mValidationError("Paper-run limit must be greater than zero.")

        evaluated_ids = {
            item.window_id for run in self._state.list_paper_runs() for item in run.items
        }
        candidates = [
            record
            for record in self._iter_latest_windows()
            if record.status == "complete" and record.window.window_id not in evaluated_ids
        ]
        candidates.sort(
            key=lambda item: (_sort_time(item.window.window_start_at), item.window.window_id)
        )
        selected = candidates[:limit]
        items = [self._evaluate_window(record) for record in selected]
        total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in items), Decimal("0"))
        run = Btc15mPaperRunRecord(
            run_id=_make_id("btc15m_paper_run"),
            created_at=_isoformat(self._now()),
            limit=limit,
            items=items,
            total_considered=len(candidates),
            total_evaluated=len(items),
            total_skipped=sum(1 for item in items if item.decision == "SKIP"),
            total_realized_pnl_usdc=_decimal_text(total_pnl),
        )
        self._state.append_paper_run(run)
        return Btc15mPaperRunResponse(run=run)

    def report(self) -> Btc15mReportResponse:
        """Return an aggregate BTC15m recorder and paper-evaluation report."""
        windows = list(self._iter_latest_windows())
        replays = self._state.list_replays()
        runs = self._state.list_paper_runs()
        evaluations = [item for run in runs for item in run.items]
        total_pnl = sum((_decimal(item.realized_pnl_usdc) for item in evaluations), Decimal("0"))
        realized_average = total_pnl / Decimal(len(evaluations)) if evaluations else Decimal("0")
        skip_reason_counts: Counter[str] = Counter()
        wins = losses = ties = skips = 0
        for item in evaluations:
            if item.decision == "SKIP":
                skips += 1
                skip_reason_counts.update(item.skip_reasons)
                continue
            if item.resolution_result == "UNRESOLVED_TIE":
                ties += 1
                continue
            pnl = _decimal(item.realized_pnl_usdc)
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            else:
                ties += 1

        latest_active = None
        for window in reversed(self._state.list_windows()):
            if window.status != "complete":
                latest_active = window
                break

        summary = Btc15mReportSummary(
            recorded_window_count=len(self._state.list_windows()),
            completed_window_count=sum(1 for item in windows if item.status == "complete"),
            replay_batch_count=len(replays),
            paper_run_count=len(runs),
            evaluated_window_count=len(evaluations),
            total_realized_pnl_usdc=_decimal_text(total_pnl),
            average_realized_pnl_usdc=_decimal_text(realized_average),
            win_count=wins,
            loss_count=losses,
            tie_count=ties,
            skip_count=skips,
            skip_reason_counts=dict(sorted(skip_reason_counts.items())),
        )
        return Btc15mReportResponse(
            summary=summary,
            latest_active_window=latest_active,
            recent_replays=list(reversed(replays))[:5],
            recent_runs=list(reversed(runs))[:5],
            recent_evaluations=list(reversed(evaluations))[:10],
        )

    def _resolve_latest_window(self) -> _ResolvedWindow:
        try:
            latest = self._market_intel_service.recurring_latest(
                DEFAULT_RECORD_QUERY,
                interval=DEFAULT_RECORD_INTERVAL,
            )
        except MarketValidationError as exc:
            raise Btc15mValidationError(str(exc)) from exc

        if latest.item is None:
            raise Btc15mValidationError("No recurring BTC 15m market candidate was found.")
        return self._resolve_window_from_candidate(latest.item)

    def _resolve_window_by_slug(self, slug: str) -> _ResolvedWindow:
        with self._gamma_client_cls() as gamma_client:
            market = gamma_client.get_market_by_slug(slug)
        candidate = RecurringMarketCandidate(
            rank=1,
            match_score=0,
            matched_interval=validate_recurring_interval(DEFAULT_RECORD_INTERVAL),
            recency_source=None,
            market_slug=market.market_slug,
            event_slug=market.event_slug,
            question=market.question,
            event_title=market.event_title,
            active=market.active,
            closed=market.closed,
            enable_order_book=market.enable_order_book,
            condition_id=market.condition_id,
            token_ids=market.token_ids,
            outcomes=market.outcomes,
            min_tick=market.min_tick,
            min_order_size=market.min_order_size,
        )
        return self._resolve_window_from_candidate(candidate)

    def _resolve_window_from_candidate(
        self, candidate: RecurringMarketCandidate
    ) -> _ResolvedWindow:
        matched_search = self._find_search_candidate(candidate.market_slug)
        start_dt = _parse_iso_optional(matched_search.start_date) if matched_search else None
        end_dt = _parse_iso_optional(matched_search.end_date) if matched_search else None
        if start_dt is None and end_dt is not None:
            start_dt = end_dt - WINDOW_DURATION
        if end_dt is None and start_dt is not None:
            end_dt = start_dt + WINDOW_DURATION

        condition_id = candidate.condition_id
        window_suffix = condition_id or candidate.market_slug
        window = Btc15mWindowIdentity(
            strategy_name="btc_15m_chainlink_directional_ladder_v1",
            window_id=f"btc15m:{window_suffix}",
            condition_id=condition_id,
            market_slug=candidate.market_slug,
            token_ids=list(candidate.token_ids),
            outcomes=list(candidate.outcomes),
            window_start_at=_isoformat(start_dt) if start_dt is not None else None,
            window_end_at=_isoformat(end_dt) if end_dt is not None else None,
            market_open_time=_isoformat(start_dt) if start_dt is not None else None,
        )
        return _ResolvedWindow(
            candidate=candidate,
            window=window,
            window_start_dt=start_dt,
            window_end_dt=end_dt,
        )

    def _find_search_candidate(self, market_slug: str) -> GammaSearchCandidate | None:
        with self._gamma_client_cls() as gamma_client:
            candidates = gamma_client.search_market_candidates(DEFAULT_RECORD_QUERY, limit=60)
        for candidate in candidates:
            if candidate.market.market_slug == market_slug:
                return candidate
        return None

    def _record_resolved_window(
        self,
        resolved: _ResolvedWindow,
        *,
        seconds: int,
        recorder_session_id: str,
    ) -> Btc15mWindowRecord:
        errors: list[Btc15mSectionError] = []
        initial_samples = self._build_initial_market_samples(resolved, errors=errors)
        if resolved.window_start_dt is None or resolved.window_end_dt is None:
            record = Btc15mWindowRecord(
                window=resolved.window,
                recorded_at=_isoformat(self._now()),
                recorder_session_id=recorder_session_id,
                status="partial",
                market_samples=initial_samples,
                boundary_status="missing_timing",
                reason_blocks=[
                    Btc15mReasonBlock(
                        section="window_timing",
                        status="fail",
                        message="Could not resolve both window start and end times.",
                    )
                ],
                errors=errors
                + [
                    Btc15mSectionError(
                        section="window_timing",
                        code="invalid_argument",
                        message="Could not resolve both window start and end times.",
                    )
                ],
            )
            self._state.append_windows([record])
            return record

        run_result = asyncio.run(self._stream_window(resolved, seconds=seconds))
        errors.extend(run_result["errors"])
        market_events = run_result["market_events"]
        chainlink_events = run_result["chainlink_events"]
        binance_events = run_result["binance_events"]
        chainlink_ticks = self._to_price_ticks(chainlink_events, source="chainlink")
        binance_ticks = self._to_price_ticks(binance_events, source="binance")
        market_samples = initial_samples + self._to_market_samples(
            market_events,
            token_outcomes=_token_outcome_map(resolved.window.token_ids, resolved.window.outcomes),
        )
        market_samples.sort(key=lambda item: (item.observed_at, item.token_id, item.event_type))
        boundary_observations, boundary_decision = self._build_boundaries(
            resolved,
            chainlink_ticks=chainlink_ticks,
            recorder_session_id=recorder_session_id,
        )
        self._state.append_boundary_observations(boundary_observations)
        self._state.append_boundary_decision(boundary_decision)
        decision, decision_at, skip_reasons, reason_blocks = self._decide_window(
            resolved,
            boundary_decision=boundary_decision,
            chainlink_ticks=chainlink_ticks,
            binance_ticks=binance_ticks,
        )
        resolution = self._resolve_market_outcome(boundary_decision)
        record = Btc15mWindowRecord(
            window=resolved.window,
            recorded_at=_isoformat(self._now()),
            recorder_session_id=recorder_session_id,
            status="complete" if boundary_decision.status == "complete" else "partial",
            market_source_session_id=run_result["market_session_id"],
            chainlink_source_session_id=run_result["chainlink_session_id"],
            binance_source_session_id=run_result["binance_session_id"],
            chainlink_ticks=chainlink_ticks,
            binance_ticks=binance_ticks,
            market_samples=market_samples,
            boundary_status=boundary_decision.status,
            start_price_proxy_v1=boundary_decision.start_price_proxy_v1,
            end_price_proxy_v1=boundary_decision.end_price_proxy_v1,
            decision=decision,
            decision_at=decision_at,
            resolution_result=resolution,
            skip_reasons=skip_reasons,
            reason_blocks=reason_blocks,
            errors=errors,
        )
        self._state.append_windows([record])
        return record

    async def _stream_window(self, resolved: _ResolvedWindow, *, seconds: int) -> dict[str, Any]:
        errors: list[Btc15mSectionError] = []
        market_events: list[CapturedStreamEvent] = []
        chainlink_events: list[CapturedStreamEvent] = []
        binance_events: list[CapturedStreamEvent] = []
        market_session_id: str | None = None
        chainlink_session_id: str | None = None
        binance_session_id: str | None = None

        results = await asyncio.gather(
            self._market_client.stream_tokens(
                resolved.window.token_ids,
                seconds=seconds,
            ),
            self._crypto_client.stream_symbol(
                "BTC",
                source="chainlink",
                seconds=seconds,
            ),
            self._crypto_client.stream_symbol(
                "BTC",
                source="binance",
                seconds=seconds,
            ),
            return_exceptions=True,
        )

        market_result, chainlink_result, binance_result = results
        if isinstance(market_result, Exception):
            errors.append(_section_error("market_stream", market_result))
        else:
            bounded_result = _coerce_market_result(market_result)
            market_events.extend(bounded_result.events)
            market_session_id = bounded_result.session.session_id
            errors.extend(_convert_stream_errors(bounded_result.errors))

        if isinstance(chainlink_result, Exception):
            errors.append(_section_error("chainlink_stream", chainlink_result))
        else:
            response = _coerce_crypto_result(chainlink_result)
            chainlink_events.extend(response.events)
            chainlink_session_id = response.session.session_id
            errors.extend(_convert_stream_errors(response.errors))

        if isinstance(binance_result, Exception):
            errors.append(_section_error("binance_stream", binance_result))
        else:
            response = _coerce_crypto_result(binance_result)
            binance_events.extend(response.events)
            binance_session_id = response.session.session_id
            errors.extend(_convert_stream_errors(response.errors))

        return {
            "market_events": market_events,
            "chainlink_events": chainlink_events,
            "binance_events": binance_events,
            "market_session_id": market_session_id,
            "chainlink_session_id": chainlink_session_id,
            "binance_session_id": binance_session_id,
            "errors": errors,
        }

    def _build_initial_market_samples(
        self,
        resolved: _ResolvedWindow,
        *,
        errors: list[Btc15mSectionError],
    ) -> list[Btc15mMarketSample]:
        observed_at = _isoformat(self._now())
        samples: list[Btc15mMarketSample] = []
        outcome_map = _token_outcome_map(resolved.window.token_ids, resolved.window.outcomes)
        try:
            with self._clob_client_cls() as clob_client:
                for token_id in resolved.window.token_ids:
                    try:
                        book = clob_client.get_book(token_id)
                    except (ClobClientError, ClobNotFoundError) as exc:
                        errors.append(_section_error(f"clob_book:{token_id}", exc))
                        continue
                    midpoint = None
                    spread = None
                    try:
                        midpoint = clob_client.get_midpoint(token_id).midpoint
                    except (ClobClientError, ClobNotFoundError) as exc:
                        errors.append(_section_error(f"clob_midpoint:{token_id}", exc))
                    try:
                        spread = clob_client.get_spread(token_id).spread
                    except (ClobClientError, ClobNotFoundError) as exc:
                        errors.append(_section_error(f"clob_spread:{token_id}", exc))
                    samples.append(
                        Btc15mMarketSample(
                            token_id=token_id,
                            outcome=outcome_map.get(token_id),
                            event_type="clob_snapshot",
                            source="clob_snapshot",
                            captured_at=observed_at,
                            observed_at=observed_at,
                            best_bid=book.bids[0].price if book.bids else None,
                            best_ask=book.asks[0].price if book.asks else None,
                            midpoint=midpoint,
                            spread=spread,
                            bids=book.bids,
                            asks=book.asks,
                        )
                    )
        except TypeError:
            errors.append(
                Btc15mSectionError(
                    section="clob_snapshot",
                    code="request_failed",
                    message="Could not construct the public CLOB client.",
                )
            )
        return samples

    def _to_price_ticks(
        self,
        events: list[CapturedStreamEvent],
        *,
        source: str,
    ) -> list[Btc15mPriceTick]:
        items: list[Btc15mPriceTick] = []
        for event in events:
            if event.crypto_event is None:
                continue
            observed_at = _event_timestamp_to_iso(
                event.crypto_event.timestamp, fallback=event.captured_at
            )
            items.append(
                Btc15mPriceTick(
                    source=source,
                    captured_at=event.captured_at,
                    observed_at=observed_at,
                    value=event.crypto_event.value,
                )
            )
        items.sort(key=lambda item: item.observed_at)
        return items

    def _to_market_samples(
        self,
        events: list[CapturedStreamEvent],
        *,
        token_outcomes: dict[str, str],
    ) -> list[Btc15mMarketSample]:
        items: list[Btc15mMarketSample] = []
        for event in events:
            if event.market_event is None or event.market_event.token_id is None:
                continue
            observed_at = _event_timestamp_to_iso(
                event.market_event.timestamp, fallback=event.captured_at
            )
            items.append(
                Btc15mMarketSample(
                    token_id=event.market_event.token_id,
                    outcome=token_outcomes.get(event.market_event.token_id),
                    event_type=event.market_event.event_type,
                    source=event.source,
                    captured_at=event.captured_at,
                    observed_at=observed_at,
                    best_bid=event.market_event.best_bid,
                    best_ask=event.market_event.best_ask,
                    midpoint=event.market_event.midpoint,
                    spread=event.market_event.spread,
                    bids=event.market_event.bids,
                    asks=event.market_event.asks,
                )
            )
        return items

    def _build_boundaries(
        self,
        resolved: _ResolvedWindow,
        *,
        chainlink_ticks: list[Btc15mPriceTick],
        recorder_session_id: str,
    ) -> tuple[list[Btc15mBoundaryObservationRecord], Btc15mBoundaryDecisionRecord]:
        assert resolved.window_start_dt is not None
        assert resolved.window_end_dt is not None
        pre_start = _latest_tick_before(chainlink_ticks, resolved.window_start_dt)
        post_start = _first_tick_after(chainlink_ticks, resolved.window_start_dt)
        pre_end = _latest_tick_before(chainlink_ticks, resolved.window_end_dt)
        post_end = _first_tick_after(chainlink_ticks, resolved.window_end_dt)

        observations = [
            _boundary_observation(
                resolved.window,
                boundary_kind="start",
                tick=pre_start,
                session_id=recorder_session_id,
                selection_status="selected_pre_start"
                if pre_start is not None
                else "missing_pre_start",
            ),
            _boundary_observation(
                resolved.window,
                boundary_kind="start",
                tick=post_start,
                session_id=recorder_session_id,
                selection_status="selected_post_start"
                if post_start is not None
                else "missing_post_start",
            ),
            _boundary_observation(
                resolved.window,
                boundary_kind="end",
                tick=pre_end,
                session_id=recorder_session_id,
                selection_status="selected_pre_end" if pre_end is not None else "missing_pre_end",
            ),
            _boundary_observation(
                resolved.window,
                boundary_kind="end",
                tick=post_end,
                session_id=recorder_session_id,
                selection_status="selected_post_end"
                if post_end is not None
                else "missing_post_end",
            ),
        ]

        notes: list[str] = []
        start_proxy = (
            _midpoint_text(pre_start.value, post_start.value) if pre_start and post_start else None
        )
        end_proxy = _midpoint_text(pre_end.value, post_end.value) if pre_end and post_end else None
        if start_proxy is None:
            notes.append("Could not compute start_price_proxy_v1.")
        if end_proxy is None:
            notes.append("Could not compute end_price_proxy_v1.")
        decision = Btc15mBoundaryDecisionRecord(
            window_id=resolved.window.window_id,
            condition_id=resolved.window.condition_id,
            market_slug=resolved.window.market_slug,
            created_at=_isoformat(self._now()),
            status="complete" if start_proxy is not None and end_proxy is not None else "partial",
            pre_start=pre_start,
            post_start=post_start,
            pre_end=pre_end,
            post_end=post_end,
            start_price_proxy_v1=start_proxy,
            end_price_proxy_v1=end_proxy,
            notes=notes,
        )
        return observations, decision

    def _decide_window(
        self,
        resolved: _ResolvedWindow,
        *,
        boundary_decision: Btc15mBoundaryDecisionRecord,
        chainlink_ticks: list[Btc15mPriceTick],
        binance_ticks: list[Btc15mPriceTick],
    ) -> tuple[str, str | None, list[str], list[Btc15mReasonBlock]]:
        assert resolved.window_start_dt is not None
        decision_time = resolved.window_start_dt + MINUTE_FIVE_OFFSET
        decision_at = _isoformat(decision_time)
        reasons: list[Btc15mReasonBlock] = []
        skip_reasons: list[str] = []

        if boundary_decision.start_price_proxy_v1 is None:
            skip_reasons.append("missing_start_proxy")
            reasons.append(
                Btc15mReasonBlock(
                    section="start_proxy",
                    status="fail",
                    message="Could not derive the start-price proxy.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons

        chainlink_tick = _latest_tick_before(chainlink_ticks, decision_time)
        binance_tick = _latest_tick_before(binance_ticks, decision_time)
        if chainlink_tick is None:
            skip_reasons.append("missing_chainlink_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="chainlink_decision",
                    status="fail",
                    message="No Chainlink tick was available by the minute-5 decision point.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons
        if binance_tick is None:
            skip_reasons.append("missing_binance_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="binance_decision",
                    status="fail",
                    message="No Binance tick was available by the minute-5 decision point.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons

        if _is_stale_tick(chainlink_tick, decision_time, DEFAULT_DECISION_STALE_SECONDS):
            skip_reasons.append("stale_chainlink_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="chainlink_decision",
                    status="fail",
                    message="Chainlink decision tick was stale at minute 5.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons
        if _is_stale_tick(binance_tick, decision_time, DEFAULT_DECISION_STALE_SECONDS):
            skip_reasons.append("stale_binance_decision_tick")
            reasons.append(
                Btc15mReasonBlock(
                    section="binance_decision",
                    status="fail",
                    message="Binance decision tick was stale at minute 5.",
                )
            )
            return "SKIP", decision_at, skip_reasons, reasons

        start_proxy = _decimal(boundary_decision.start_price_proxy_v1)
        chainlink_price = _decimal(chainlink_tick.value)
        binance_price = _decimal(binance_tick.value)
        if chainlink_price > start_proxy and binance_price > start_proxy:
            reasons.append(
                Btc15mReasonBlock(
                    section="direction_lock",
                    status="pass",
                    message="Chainlink and Binance were both above the start proxy at minute 5.",
                )
            )
            return "UP", decision_at, skip_reasons, reasons
        if chainlink_price < start_proxy and binance_price < start_proxy:
            reasons.append(
                Btc15mReasonBlock(
                    section="direction_lock",
                    status="pass",
                    message="Chainlink and Binance were both below the start proxy at minute 5.",
                )
            )
            return "DOWN", decision_at, skip_reasons, reasons

        skip_reasons.append("mixed_direction_at_minute_five")
        reasons.append(
            Btc15mReasonBlock(
                section="direction_lock",
                status="fail",
                message="Chainlink and Binance did not agree on direction at minute 5.",
            )
        )
        return "SKIP", decision_at, skip_reasons, reasons

    def _resolve_market_outcome(self, boundary_decision: Btc15mBoundaryDecisionRecord) -> str:
        if (
            boundary_decision.start_price_proxy_v1 is None
            or boundary_decision.end_price_proxy_v1 is None
        ):
            return "PENDING"
        start_price = _decimal(boundary_decision.start_price_proxy_v1)
        end_price = _decimal(boundary_decision.end_price_proxy_v1)
        if end_price > start_price:
            return "UP"
        if end_price < start_price:
            return "DOWN"
        return "UNRESOLVED_TIE"

    def _evaluate_window(self, record: Btc15mWindowRecord) -> Btc15mPaperEvaluation:
        reasons = list(record.reason_blocks)
        if record.decision == "SKIP":
            return _skip_evaluation(record, reasons)
        if record.decision not in {"UP", "DOWN"}:
            return _skip_evaluation(
                record,
                reasons
                + [
                    Btc15mReasonBlock(
                        section="direction_lock",
                        status="fail",
                        message="No valid direction lock was available for paper evaluation.",
                    )
                ],
                extra_skip_reason="missing_direction_lock",
            )

        target_token = _resolve_target_token(
            record.window.token_ids, record.window.outcomes, record.decision
        )
        if target_token is None:
            return _skip_evaluation(
                record,
                reasons
                + [
                    Btc15mReasonBlock(
                        section="outcome_mapping",
                        status="fail",
                        message="Could not map the chosen direction to a token and outcome.",
                    )
                ],
                extra_skip_reason="unresolved_outcome_mapping",
            )
        target_token_id, target_outcome = target_token

        window_start = _parse_iso_optional(record.window.window_start_at)
        if window_start is None:
            return _skip_evaluation(
                record,
                reasons
                + [
                    Btc15mReasonBlock(
                        section="window_timing",
                        status="fail",
                        message="Window start time was not available for paper evaluation.",
                    )
                ],
                extra_skip_reason="missing_window_start",
            )

        activation_at = window_start + MINUTE_FIVE_OFFSET
        cancellation_at = window_start + MINUTE_TEN_OFFSET
        samples = [
            sample
            for sample in record.market_samples
            if sample.token_id == target_token_id
            and _parse_iso_optional(sample.observed_at) is not None
        ]
        samples.sort(key=lambda item: item.observed_at)
        rung_results: list[Btc15mLadderRungResult] = []
        filled_quantities: list[Decimal] = []
        total_cost = Decimal("0")
        first_fill_at: str | None = None

        for price, notional in zip(RUNG_PRICES, RUNG_NOTIONALS, strict=True):
            quantity = (notional / price).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            rung = Btc15mLadderRungResult(
                price=_decimal_text(price),
                notional_usdc=_decimal_text(notional),
                quantity=_decimal_text(quantity),
                status="cancelled",
                cancellation_at=_isoformat(cancellation_at),
            )
            for sample in samples:
                observed_at = _parse_iso_timestamp(sample.observed_at)
                if observed_at < activation_at or observed_at >= cancellation_at:
                    continue
                if _is_stale_sample(sample, observed_at, DEFAULT_MARKET_STALE_SECONDS):
                    continue
                best_ask = _decimal_optional(sample.best_ask)
                available = _ask_liquidity_at_or_better(sample.asks, price)
                if best_ask is None or best_ask > price or available < quantity:
                    continue
                rung.status = "filled"
                rung.fill_at = sample.observed_at
                rung.fill_price = _decimal_text(price)
                rung.cancellation_at = None
                filled_quantities.append(quantity)
                total_cost += quantity * price
                if first_fill_at is None:
                    first_fill_at = sample.observed_at
                break
            rung_results.append(rung)

        total_quantity = sum(filled_quantities, Decimal("0"))
        resolution = record.resolution_result
        if total_quantity == 0:
            settlement_value = Decimal("0")
            realized_pnl = Decimal("0")
        elif resolution == "UNRESOLVED_TIE":
            settlement_value = total_cost
            realized_pnl = Decimal("0")
        elif resolution == record.decision:
            settlement_value = total_quantity
            realized_pnl = settlement_value - total_cost
        elif resolution in {"UP", "DOWN"}:
            settlement_value = Decimal("0")
            realized_pnl = settlement_value - total_cost
        else:
            settlement_value = Decimal("0")
            realized_pnl = Decimal("0")

        mfe = Decimal("0")
        mae = Decimal("0")
        max_favorable_price: str | None = None
        time_to_peak_seconds: int | None = None
        path: list[Btc15mPriceMark] = []
        if first_fill_at is not None and total_quantity > 0:
            first_fill_dt = _parse_iso_timestamp(first_fill_at)
            peak_time: datetime | None = None
            for sample in samples:
                observed_at = _parse_iso_timestamp(sample.observed_at)
                if observed_at < first_fill_dt:
                    continue
                midpoint = _decimal_optional(sample.midpoint)
                if midpoint is None:
                    continue
                pnl = (total_quantity * midpoint) - total_cost
                path.append(
                    Btc15mPriceMark(
                        observed_at=sample.observed_at,
                        midpoint=_decimal_text(midpoint),
                        pnl_usdc=_decimal_text(pnl),
                    )
                )
                if len(path) == 1 or pnl > mfe:
                    mfe = pnl
                    max_favorable_price = _decimal_text(midpoint)
                    peak_time = observed_at
                if len(path) == 1 or pnl < mae:
                    mae = pnl
            if peak_time is not None:
                time_to_peak_seconds = int((peak_time - first_fill_dt).total_seconds())

        return Btc15mPaperEvaluation(
            window_id=record.window.window_id,
            market_slug=record.window.market_slug,
            condition_id=record.window.condition_id,
            window_start_at=record.window.window_start_at,
            window_end_at=record.window.window_end_at,
            target_token_id=target_token_id,
            target_outcome=target_outcome,
            decision=record.decision,
            decision_at=record.decision_at,
            resolution_result=resolution,
            skip_reasons=list(record.skip_reasons),
            reason_blocks=reasons,
            start_price_proxy_v1=record.start_price_proxy_v1,
            end_price_proxy_v1=record.end_price_proxy_v1,
            rungs=rung_results,
            filled_rung_count=sum(1 for rung in rung_results if rung.status == "filled"),
            cancelled_rung_count=sum(1 for rung in rung_results if rung.status == "cancelled"),
            first_fill_at=first_fill_at,
            total_cost_usdc=_decimal_text(total_cost),
            settlement_value_usdc=_decimal_text(settlement_value),
            realized_pnl_usdc=_decimal_text(realized_pnl),
            mfe_usdc=_decimal_text(mfe),
            mae_usdc=_decimal_text(mae),
            max_favorable_price=max_favorable_price,
            time_to_peak_seconds=time_to_peak_seconds,
            max_favorable_path=path,
        )

    def _iter_latest_windows(self) -> list[Btc15mWindowRecord]:
        latest: dict[str, Btc15mWindowRecord] = {}
        rank = {"partial": 0, "complete": 1}
        for record in self._state.list_windows():
            current = latest.get(record.window.window_id)
            if current is None:
                latest[record.window.window_id] = record
                continue
            current_rank = rank.get(current.status, 0)
            record_rank = rank.get(record.status, 0)
            if record_rank > current_rank:
                latest[record.window.window_id] = record
                continue
            if record_rank == current_rank and _sort_time(record.recorded_at) >= _sort_time(
                current.recorded_at
            ):
                latest[record.window.window_id] = record
        return sorted(
            latest.values(),
            key=lambda item: (_sort_time(item.window.window_start_at), item.window.window_id),
        )


def _boundary_observation(
    window: Btc15mWindowIdentity,
    *,
    boundary_kind: str,
    tick: Btc15mPriceTick | None,
    session_id: str,
    selection_status: str,
) -> Btc15mBoundaryObservationRecord:
    return Btc15mBoundaryObservationRecord(
        window_id=window.window_id,
        condition_id=window.condition_id,
        market_slug=window.market_slug,
        boundary_kind=boundary_kind,
        captured_at=tick.captured_at if tick is not None else _isoformat(_utc_now()),
        source_timestamp=tick.observed_at if tick is not None else None,
        source_value=tick.value if tick is not None else None,
        session_id=session_id,
        accepted=tick is not None,
        selected=tick is not None,
        selection_status=selection_status,
    )


def _skip_evaluation(
    record: Btc15mWindowRecord,
    reasons: list[Btc15mReasonBlock],
    *,
    extra_skip_reason: str | None = None,
) -> Btc15mPaperEvaluation:
    skip_reasons = list(record.skip_reasons)
    if extra_skip_reason is not None and extra_skip_reason not in skip_reasons:
        skip_reasons.append(extra_skip_reason)
    return Btc15mPaperEvaluation(
        window_id=record.window.window_id,
        market_slug=record.window.market_slug,
        condition_id=record.window.condition_id,
        window_start_at=record.window.window_start_at,
        window_end_at=record.window.window_end_at,
        decision="SKIP",
        decision_at=record.decision_at,
        resolution_result=record.resolution_result,
        skip_reasons=skip_reasons,
        reason_blocks=reasons,
        start_price_proxy_v1=record.start_price_proxy_v1,
        end_price_proxy_v1=record.end_price_proxy_v1,
        total_cost_usdc="0",
        settlement_value_usdc="0",
        realized_pnl_usdc="0",
        mfe_usdc="0",
        mae_usdc="0",
    )


def _resolve_target_token(
    token_ids: list[str],
    outcomes: list[str],
    direction: str,
) -> tuple[str, str] | None:
    for token_id, outcome in zip(token_ids, outcomes, strict=False):
        normalized = outcome.strip().lower()
        if direction == "UP" and normalized in {"up", "yes"}:
            return token_id, outcome
        if direction == "DOWN" and normalized in {"down", "no"}:
            return token_id, outcome
    return None


def _token_outcome_map(token_ids: list[str], outcomes: list[str]) -> dict[str, str]:
    return {token_id: outcome for token_id, outcome in zip(token_ids, outcomes, strict=False)}


def _coerce_market_result(result: Any) -> BoundedRunResult:
    if isinstance(result, BoundedRunResult):
        return result
    if isinstance(result, MarketWatchStreamResponse):
        return BoundedRunResult(
            session=result.session,
            events=result.events,
            errors=result.errors,
        )
    raise TypeError("Unexpected market stream result.")


def _coerce_crypto_result(result: Any) -> CryptoStreamResponse:
    if isinstance(result, CryptoStreamResponse):
        return result
    raise TypeError("Unexpected crypto stream result.")


def _convert_stream_errors(errors: list[StreamSectionError]) -> list[Btc15mSectionError]:
    return [
        Btc15mSectionError(section=item.section, code=item.code, message=item.message)
        for item in errors
    ]


def _section_error(section: str, exc: Exception) -> Btc15mSectionError:
    code = "request_failed"
    if isinstance(exc, (Btc15mValidationError, StreamValidationError, MarketValidationError)):
        code = "invalid_argument"
    elif isinstance(exc, Btc15mStateError):
        code = "state_error"
    elif isinstance(exc, ClobNotFoundError):
        code = "not_found"
    return Btc15mSectionError(section=section, code=code, message=str(exc))


def _latest_tick_before(items: list[Btc15mPriceTick], when: datetime) -> Btc15mPriceTick | None:
    matching = [item for item in items if _parse_iso_timestamp(item.observed_at) <= when]
    if not matching:
        return None
    return max(matching, key=lambda item: item.observed_at)


def _first_tick_after(items: list[Btc15mPriceTick], when: datetime) -> Btc15mPriceTick | None:
    matching = [item for item in items if _parse_iso_timestamp(item.observed_at) > when]
    if not matching:
        return None
    return min(matching, key=lambda item: item.observed_at)


def _midpoint_text(left: str, right: str) -> str:
    midpoint = (_decimal(left) + _decimal(right)) / Decimal("2")
    return _decimal_text(midpoint)


def _event_timestamp_to_iso(timestamp: int | None, *, fallback: str) -> str:
    if timestamp is None:
        return fallback
    seconds = timestamp / 1000 if timestamp > 1_000_000_000_000 else timestamp
    return _isoformat(datetime.fromtimestamp(seconds, tz=UTC))


def _is_stale_tick(item: Btc15mPriceTick, when: datetime, limit_seconds: int) -> bool:
    return (when - _parse_iso_timestamp(item.observed_at)).total_seconds() > limit_seconds


def _is_stale_sample(item: Btc15mMarketSample, when: datetime, limit_seconds: int) -> bool:
    return (when - _parse_iso_timestamp(item.observed_at)).total_seconds() > limit_seconds


def _ask_liquidity_at_or_better(asks: list[NormalizedBookLevel], price: Decimal) -> Decimal:
    total = Decimal("0")
    for level in asks:
        try:
            level_price = _decimal(level.price)
            level_size = _decimal(level.size)
        except InvalidOperation:
            continue
        if level_price <= price:
            total += level_size
    return total


def _decimal(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_optional(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return _decimal(value)
    except InvalidOperation:
        return None


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _parse_iso_optional(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _parse_iso_timestamp(value)


def _parse_iso_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized).astimezone(UTC)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sort_time(value: str | None) -> str:
    return value or ""


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)
