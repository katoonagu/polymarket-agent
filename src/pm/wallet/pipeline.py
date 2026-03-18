"""Read-only wallet monitoring, signal derivation, and shadow simulation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TypeVar

from pm.data import (
    DataClient,
    DataClientError,
    DataNotFoundError,
    DataValidationError,
    NormalizedActivity,
    NormalizedTrade,
)
from pm.market import (
    ClobClient,
    ClobClientError,
    ClobNotFoundError,
    GammaClient,
    GammaClientError,
    GammaNotFoundError,
    NormalizedBook,
    NormalizedMarket,
    NormalizedPriceQuote,
)
from pm.wallet.models import (
    TrackedWallet,
    WalletEvent,
    WalletMonitorRunResponse,
    WalletSectionError,
    WalletShadowCandidateIntent,
    WalletShadowReportResponse,
    WalletShadowRun,
    WalletShadowRunParameters,
    WalletShadowSimulationResponse,
    WalletSignal,
    WalletSignalsResponse,
)
from pm.wallet.state import WalletPipelineStateService

T = TypeVar("T")

ENTRY_CLASSIFICATIONS = {"new_entry", "add"}


class WalletPipelineValidationError(RuntimeError):
    """Raised when wallet shadow CLI arguments are invalid."""


@dataclass(slots=True)
class MonitorPipelineResult:
    """Internal monitor-pipeline result used by simulation and CLI commands."""

    response: WalletMonitorRunResponse
    duplicate_events: list[WalletEvent]


class WalletShadowPipelineService:
    """Read-only wallet event ingestion, signals, and shadow simulation."""

    def __init__(self, state: WalletPipelineStateService | None = None) -> None:
        self._state = state or WalletPipelineStateService()

    def run_monitor(self, wallet: TrackedWallet, *, limit: int) -> WalletMonitorRunResponse:
        """Fetch recent public wallet activity, persist new events, and derive signals."""
        return self._run_monitor_pipeline(wallet, limit=limit).response

    def get_signals(self, wallet: TrackedWallet, *, limit: int) -> WalletSignalsResponse:
        """Return persisted wallet signals in deterministic reverse-chronological order."""
        signals = self._state.list_signals(wallet.address)
        ordered = sorted(signals, key=_signal_sort_key, reverse=True)
        return WalletSignalsResponse(wallet=wallet, items=ordered[:limit], total=len(signals))

    def simulate_shadow(
        self,
        wallet: TrackedWallet,
        *,
        fixed_size_usdc: str,
        max_drift_pct: str,
        max_spread_pct: str,
        entry_only: bool,
        limit: int,
    ) -> WalletShadowSimulationResponse:
        """Run a manual monitor pass and produce read-only copy candidate intents."""
        fixed_size = _parse_positive_decimal(
            fixed_size_usdc,
            field_name="fixed size",
            allow_zero=False,
        )
        max_drift = _parse_positive_decimal(
            max_drift_pct,
            field_name="max drift",
            allow_zero=True,
        )
        max_spread = _parse_positive_decimal(
            max_spread_pct,
            field_name="max spread",
            allow_zero=True,
        )

        monitor_result = self._run_monitor_pipeline(wallet, limit=limit)
        errors = list(monitor_result.response.errors)
        candidate_intents = [
            _build_duplicate_candidate(event, fixed_size_usdc=_decimal_to_string(fixed_size))
            for event in monitor_result.duplicate_events
        ]

        with GammaClient() as gamma_client, ClobClient() as clob_client:
            for signal in monitor_result.response.new_signals:
                candidate_intents.append(
                    self._build_signal_candidate(
                        signal,
                        gamma_client=gamma_client,
                        clob_client=clob_client,
                        fixed_size_usdc=fixed_size,
                        max_drift_pct=max_drift,
                        max_spread_pct=max_spread,
                        entry_only=entry_only,
                        errors=errors,
                    )
                )

        would_copy_count = sum(1 for item in candidate_intents if item.decision == "WOULD_COPY")
        skip_count = len(candidate_intents) - would_copy_count
        run = WalletShadowRun(
            source_wallet=wallet.address,
            run_at=_utc_now_iso(),
            parameters=WalletShadowRunParameters(
                fixed_size_usdc=_decimal_to_string(fixed_size),
                max_drift_pct=_decimal_to_string(max_drift),
                max_spread_pct=_decimal_to_string(max_spread),
                entry_only=entry_only,
                limit=limit,
            ),
            new_signal_count=len(monitor_result.response.new_signals),
            duplicate_event_count=monitor_result.response.duplicate_events_count,
            would_copy_count=would_copy_count,
            skip_count=skip_count,
            candidate_intents=candidate_intents,
            errors=errors,
        )
        self._state.append_shadow_run(run)
        return WalletShadowSimulationResponse(wallet=wallet, run=run)

    def get_shadow_report(self, wallet: TrackedWallet) -> WalletShadowReportResponse:
        """Return cumulative shadow-run counts plus the latest run details."""
        runs = self._state.list_shadow_runs(wallet.address)
        latest_run = runs[-1] if runs else None
        return WalletShadowReportResponse(
            wallet=wallet,
            run_count=len(runs),
            would_copy_count=sum(run.would_copy_count for run in runs),
            skip_count=sum(run.skip_count for run in runs),
            latest_run=latest_run,
        )

    def _run_monitor_pipeline(self, wallet: TrackedWallet, *, limit: int) -> MonitorPipelineResult:
        errors: list[WalletSectionError] = []

        with DataClient() as client:
            trades = self._capture_data_error(
                section="trades",
                errors=errors,
                operation=lambda: client.get_user_trades(wallet.address, limit=limit),
            )
            activity = self._capture_data_error(
                section="activity",
                errors=errors,
                operation=lambda: client.get_user_activity(wallet.address, limit=limit),
            )

        trade_events = (
            [_trade_to_event(item) for item in trades.items] if trades is not None else []
        )
        activity_events = (
            [_activity_to_event(item) for item in activity.items] if activity is not None else []
        )
        fetched_events = _classify_events(_sort_event_window([*trade_events, *activity_events]))
        existing_keys = {event.dedupe_key for event in self._state.list_events(wallet.address)}
        new_events: list[WalletEvent] = []
        duplicate_events: list[WalletEvent] = []
        batch_keys: set[str] = set()

        for event in fetched_events:
            if event.dedupe_key in existing_keys or event.dedupe_key in batch_keys:
                duplicate_events.append(event)
                continue
            batch_keys.add(event.dedupe_key)
            new_events.append(event)

        new_signals = [_event_to_signal(event) for event in new_events]
        self._state.append_events(new_events)
        self._state.append_signals(new_signals)
        response = WalletMonitorRunResponse(
            wallet=wallet,
            fetched_trades_count=trades.total if trades is not None else 0,
            fetched_activity_count=activity.total if activity is not None else 0,
            new_events_count=len(new_events),
            duplicate_events_count=len(duplicate_events),
            new_signals=new_signals,
            errors=errors,
        )
        return MonitorPipelineResult(response=response, duplicate_events=duplicate_events)

    def _build_signal_candidate(
        self,
        signal: WalletSignal,
        *,
        gamma_client: GammaClient,
        clob_client: ClobClient,
        fixed_size_usdc: Decimal,
        max_drift_pct: Decimal,
        max_spread_pct: Decimal,
        entry_only: bool,
        errors: list[WalletSectionError],
    ) -> WalletShadowCandidateIntent:
        market = self._capture_upstream_error(
            section=f"market_context:{signal.dedupe_key}",
            errors=errors,
            operation=lambda: _resolve_market_context(signal, gamma_client=gamma_client),
        )
        if market is None:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=_decimal_to_string(fixed_size_usdc),
                market_slug=signal.market_slug,
                condition_id=signal.condition_id,
                outcome=signal.outcome,
                decision="SKIP",
                skip_reason="context_unavailable",
            )

        resolved_outcome = _resolve_outcome(signal, market)
        price_quote = self._capture_upstream_error(
            section=f"clob_price:{signal.token_id or signal.dedupe_key}",
            errors=errors,
            operation=lambda: _require_token_id(signal, clob_client.get_prices),
        )
        spread_quote = self._capture_upstream_error(
            section=f"clob_spread:{signal.token_id or signal.dedupe_key}",
            errors=errors,
            operation=lambda: _require_token_id(signal, clob_client.get_spread),
        )
        book = self._capture_upstream_error(
            section=f"clob_book:{signal.token_id or signal.dedupe_key}",
            errors=errors,
            operation=lambda: _require_token_id(signal, clob_client.get_book),
        )

        current_price = _select_current_price(signal, price_quote)
        spread_value = spread_quote.spread if spread_quote is not None else None
        simulated_size = _decimal_to_string(fixed_size_usdc)

        if price_quote is None or current_price is None:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                spread=spread_value,
                decision="SKIP",
                skip_reason="price_unavailable",
                book=book,
            )

        if spread_quote is None or spread_value is None:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                decision="SKIP",
                skip_reason="spread_unavailable",
                book=book,
            )

        if book is None:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                spread=spread_value,
                decision="SKIP",
                skip_reason="book_unavailable",
            )

        if signal.classification == "noise":
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                spread=spread_value,
                decision="SKIP",
                skip_reason="noise",
                book=book,
            )

        if not market.active or market.closed:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                spread=spread_value,
                decision="SKIP",
                skip_reason="market_inactive",
                book=book,
            )

        if entry_only and signal.classification not in ENTRY_CLASSIFICATIONS:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                spread=spread_value,
                decision="SKIP",
                skip_reason="entry_only_filtered",
                book=book,
            )

        drift_value = _calculate_drift(signal.source_price, current_price)
        spread_pct_value = _calculate_spread_pct(spread_value, current_price)
        if drift_value is None or spread_pct_value is None:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                spread=spread_value,
                decision="SKIP",
                skip_reason="price_unavailable",
                book=book,
            )

        if drift_value > max_drift_pct:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                drift=_decimal_to_string(drift_value),
                spread=spread_value,
                spread_pct=_decimal_to_string(spread_pct_value),
                decision="SKIP",
                skip_reason="drift_threshold",
                book=book,
            )

        if spread_pct_value > max_spread_pct:
            return _build_signal_candidate(
                signal,
                simulated_size_usdc=simulated_size,
                market_slug=market.market_slug,
                condition_id=market.condition_id,
                outcome=resolved_outcome,
                current_price=current_price,
                drift=_decimal_to_string(drift_value),
                spread=spread_value,
                spread_pct=_decimal_to_string(spread_pct_value),
                decision="SKIP",
                skip_reason="spread_threshold",
                book=book,
            )

        return _build_signal_candidate(
            signal,
            simulated_size_usdc=simulated_size,
            market_slug=market.market_slug,
            condition_id=market.condition_id,
            outcome=resolved_outcome,
            current_price=current_price,
            drift=_decimal_to_string(drift_value),
            spread=spread_value,
            spread_pct=_decimal_to_string(spread_pct_value),
            decision="WOULD_COPY",
            skip_reason=None,
            book=book,
        )

    @staticmethod
    def _capture_data_error(
        *,
        section: str,
        errors: list[WalletSectionError],
        operation: Callable[[], T],
    ) -> T | None:
        try:
            return operation()
        except (DataValidationError, DataNotFoundError, DataClientError) as exc:
            errors.append(
                WalletSectionError(
                    section=section,
                    code=_data_error_code(exc),
                    message=str(exc),
                )
            )
            return None

    @staticmethod
    def _capture_upstream_error(
        *,
        section: str,
        errors: list[WalletSectionError],
        operation: Callable[[], T],
    ) -> T | None:
        try:
            return operation()
        except (
            DataValidationError,
            DataNotFoundError,
            DataClientError,
            GammaNotFoundError,
            GammaClientError,
            ClobNotFoundError,
            ClobClientError,
        ) as exc:
            errors.append(
                WalletSectionError(
                    section=section,
                    code=_upstream_error_code(exc),
                    message=str(exc),
                )
            )
            return None


def _trade_to_event(item: NormalizedTrade) -> WalletEvent:
    side = _normalize_side(item.side)
    return WalletEvent(
        source_wallet=item.user.lower(),
        transaction_hash=item.transaction_hash,
        timestamp=item.timestamp,
        market_slug=item.market_slug,
        condition_id=item.condition_id,
        token_id=item.token_id,
        side=side,
        outcome=item.outcome,
        source_price=item.price,
        source_size=item.size,
        source_kind="trade",
        source_activity_type=None,
        dedupe_key=_build_dedupe_key(
            transaction_hash=item.transaction_hash,
            token_id=item.token_id,
            side=side,
            timestamp=item.timestamp,
        ),
        classification="noise",
    )


def _activity_to_event(item: NormalizedActivity) -> WalletEvent:
    side = _normalize_side(item.side)
    return WalletEvent(
        source_wallet=item.user.lower(),
        transaction_hash=item.transaction_hash,
        timestamp=item.timestamp,
        market_slug=item.market_slug,
        condition_id=item.condition_id,
        token_id=item.token_id,
        side=side,
        outcome=item.outcome,
        source_price=item.price,
        source_size=item.size,
        source_kind="activity",
        source_activity_type=item.activity_type,
        dedupe_key=_build_dedupe_key(
            transaction_hash=item.transaction_hash,
            token_id=item.token_id,
            side=side,
            timestamp=item.timestamp,
        ),
        classification="noise",
    )


def _event_to_signal(event: WalletEvent) -> WalletSignal:
    return WalletSignal.model_validate(event.model_dump(mode="python"))


def _sort_event_window(events: list[WalletEvent]) -> list[WalletEvent]:
    return sorted(
        events,
        key=lambda event: (
            event.timestamp or 0,
            event.transaction_hash or "",
            event.token_id or "",
            event.side or "",
            event.source_kind,
            event.dedupe_key,
        ),
    )


def _classify_events(events: list[WalletEvent]) -> list[WalletEvent]:
    positions: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for event in events:
        if not _is_trade_like(event):
            event.classification = "noise"
            continue

        size = _parse_decimal(event.source_size)
        if size is None or size <= Decimal("0"):
            event.classification = "noise"
            continue

        token_key = "|".join([event.condition_id or event.market_slug or "", event.token_id or ""])
        position_size = positions[token_key]
        if event.side == "BUY":
            event.classification = "new_entry" if position_size <= Decimal("0") else "add"
            positions[token_key] = position_size + size
            continue

        if event.side == "SELL":
            event.classification = "reduce" if position_size > size else "close"
            next_size = position_size - size
            positions[token_key] = next_size if next_size > Decimal("0") else Decimal("0")
            continue

        event.classification = "noise"

    grouped_tokens: dict[tuple[str, str], set[str]] = defaultdict(set)
    for event in events:
        if (
            event.classification == "noise"
            or event.transaction_hash is None
            or event.condition_id is None
            or event.token_id is None
        ):
            continue
        grouped_tokens[(event.transaction_hash, event.condition_id)].add(event.token_id)

    hedge_groups = {group for group, token_ids in grouped_tokens.items() if len(token_ids) > 1}
    for event in events:
        group = (event.transaction_hash or "", event.condition_id or "")
        if event.classification != "noise" and group in hedge_groups:
            event.classification = "hedge_candidate"

    return events


def _is_trade_like(event: WalletEvent) -> bool:
    if (
        event.transaction_hash is None
        or event.timestamp is None
        or event.token_id is None
        or event.side not in {"BUY", "SELL"}
        or event.source_price is None
    ):
        return False

    if event.source_kind == "activity":
        return (event.source_activity_type or "").upper() == "TRADE"
    return True


def _build_dedupe_key(
    *,
    transaction_hash: str | None,
    token_id: str | None,
    side: str | None,
    timestamp: int | None,
) -> str:
    return "|".join(
        [
            transaction_hash or "",
            token_id or "",
            side or "",
            str(timestamp or ""),
        ]
    )


def _normalize_side(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _resolve_market_context(
    signal: WalletSignal,
    *,
    gamma_client: GammaClient,
) -> NormalizedMarket:
    if signal.market_slug:
        return gamma_client.get_market_by_slug(signal.market_slug)
    if signal.condition_id:
        return gamma_client.get_market_by_condition_id(signal.condition_id)
    raise DataValidationError("Signal did not include a market slug or condition ID.")


def _resolve_outcome(signal: WalletSignal, market: NormalizedMarket) -> str | None:
    if signal.outcome is not None:
        return signal.outcome
    if signal.token_id and market.token_ids and len(market.token_ids) == len(market.outcomes):
        try:
            index = market.token_ids.index(signal.token_id)
        except ValueError:
            return None
        return market.outcomes[index]
    return None


def _require_token_id(
    signal: WalletSignal,
    operation: Callable[[str], T],
) -> T:
    if signal.token_id is None:
        raise DataValidationError("Signal did not include a token ID.")
    return operation(signal.token_id)


def _select_current_price(
    signal: WalletSignal,
    quote: NormalizedPriceQuote | None,
) -> str | None:
    if quote is None:
        return None
    if signal.side == "SELL":
        return quote.sell_price
    return quote.buy_price


def _build_duplicate_candidate(
    event: WalletEvent,
    *,
    fixed_size_usdc: str,
) -> WalletShadowCandidateIntent:
    return WalletShadowCandidateIntent(
        source_wallet=event.source_wallet,
        market_slug=event.market_slug,
        condition_id=event.condition_id,
        token_id=event.token_id,
        side=event.side,
        outcome=event.outcome,
        source_price=event.source_price,
        current_price=None,
        drift=None,
        spread=None,
        spread_pct=None,
        simulated_size_usdc=fixed_size_usdc,
        decision="SKIP",
        skip_reason="duplicate_event",
        classification=event.classification,
        transaction_hash=event.transaction_hash,
        timestamp=event.timestamp,
        dedupe_key=event.dedupe_key,
        book=None,
    )


def _build_signal_candidate(
    signal: WalletSignal,
    *,
    simulated_size_usdc: str,
    market_slug: str | None,
    condition_id: str | None,
    outcome: str | None,
    current_price: str | None = None,
    drift: str | None = None,
    spread: str | None = None,
    spread_pct: str | None = None,
    decision: str,
    skip_reason: str | None,
    book: NormalizedBook | None = None,
) -> WalletShadowCandidateIntent:
    return WalletShadowCandidateIntent(
        source_wallet=signal.source_wallet,
        market_slug=market_slug,
        condition_id=condition_id,
        token_id=signal.token_id,
        side=signal.side,
        outcome=outcome,
        source_price=signal.source_price,
        current_price=current_price,
        drift=drift,
        spread=spread,
        spread_pct=spread_pct,
        simulated_size_usdc=simulated_size_usdc,
        decision=decision,
        skip_reason=skip_reason,
        classification=signal.classification,
        transaction_hash=signal.transaction_hash,
        timestamp=signal.timestamp,
        dedupe_key=signal.dedupe_key,
        book=book,
    )


def _calculate_drift(source_price: str | None, current_price: str | None) -> Decimal | None:
    source_decimal = _parse_decimal(source_price)
    current_decimal = _parse_decimal(current_price)
    if source_decimal is None or current_decimal is None or source_decimal <= Decimal("0"):
        return None
    return ((current_decimal - source_decimal).copy_abs() / source_decimal) * Decimal("100")


def _calculate_spread_pct(spread: str | None, current_price: str | None) -> Decimal | None:
    spread_decimal = _parse_decimal(spread)
    current_decimal = _parse_decimal(current_price)
    if spread_decimal is None or current_decimal is None or current_decimal <= Decimal("0"):
        return None
    return (spread_decimal / current_decimal) * Decimal("100")


def _parse_positive_decimal(
    value: str,
    *,
    field_name: str,
    allow_zero: bool,
) -> Decimal:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise WalletPipelineValidationError(
            f"{field_name.title()} must be a decimal number."
        )
    if allow_zero:
        if parsed < Decimal("0"):
            raise WalletPipelineValidationError(f"{field_name.title()} must be zero or greater.")
    elif parsed <= Decimal("0"):
        raise WalletPipelineValidationError(f"{field_name.title()} must be greater than zero.")
    return parsed


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _decimal_to_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f").split(".")[0]
    return format(normalized, "f")


def _signal_sort_key(signal: WalletSignal) -> tuple[int, str, str, str]:
    return (
        signal.timestamp or 0,
        signal.dedupe_key,
        signal.transaction_hash or "",
        signal.source_kind,
    )


def _data_error_code(exc: Exception) -> str:
    if isinstance(exc, DataValidationError):
        return "invalid_argument"
    if isinstance(exc, DataNotFoundError):
        return "not_found"
    return "request_failed"


def _upstream_error_code(exc: Exception) -> str:
    if isinstance(exc, DataValidationError):
        return "invalid_argument"
    if isinstance(exc, (DataNotFoundError, GammaNotFoundError, ClobNotFoundError)):
        return "not_found"
    return "request_failed"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
