"""Read-only strategy registry, evaluation, and manual review service."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TypedDict

from pm.market.models import MarketSnapshotRecord, RecurringMarketCandidate
from pm.market.service import MarketIntelService, MarketValidationError
from pm.market.state import MarketStateError, MarketStateService
from pm.strategy.models import (
    StrategyCandidateIntent,
    StrategyDecisionMutationResponse,
    StrategyDecisionRecord,
    StrategyDefinition,
    StrategyEvaluateResponse,
    StrategyIntentsResponse,
    StrategyIntentView,
    StrategyListResponse,
    StrategyReasonBlock,
    StrategyReviewResponse,
    StrategySectionError,
    StrategyShowResponse,
    StrategySourceReference,
    StrategyValidationResult,
)
from pm.strategy.registry import (
    StrategyNotFoundError,
    StrategyRegistryError,
    StrategyRegistryService,
)
from pm.strategy.state import (
    StrategyIntentNotFoundError,
    StrategyStateError,
    StrategyStateService,
)
from pm.stream import CapturedStreamEvent, StreamEventStore, infer_crypto_symbol
from pm.stream.state import StreamStateError
from pm.wallet.models import WalletShadowCandidateIntent
from pm.wallet.state import WalletPipelineStateService, WalletStateError

DEFAULT_LIMIT = 20
WALLET_SHADOW_STRATEGY = "wallet_shadow_copy"
MARKET_REVERSION_STRATEGY = "market_watch_reversion"
RECURRING_STRATEGY = "recurring_crypto_interval_observe"


class SnapshotTokenComparison(TypedDict):
    """Typed comparison result for baseline versus current token snapshots."""

    token_id: str | None
    outcome: str | None
    midpoint_drift_pct: Decimal | None
    spread_delta: Decimal | None


class StrategyValidationError(RuntimeError):
    """Raised when strategy CLI inputs are invalid."""


class StrategyService:
    """High-level read-only strategy registry and orchestrator service."""

    def __init__(
        self,
        *,
        registry: StrategyRegistryService | None = None,
        state: StrategyStateService | None = None,
        wallet_state: WalletPipelineStateService | None = None,
        market_state: MarketStateService | None = None,
        market_intel_service: MarketIntelService | None = None,
        stream_store: StreamEventStore | None = None,
    ) -> None:
        self._registry = registry or StrategyRegistryService()
        self._state = state or StrategyStateService()
        self._wallet_state = wallet_state or WalletPipelineStateService()
        self._market_state = market_state or MarketStateService()
        self._market_intel_service = market_intel_service or MarketIntelService(
            state=self._market_state
        )
        self._stream_store = stream_store or StreamEventStore()

    def list_strategies(self) -> StrategyListResponse:
        """Return all seeded strategies in deterministic order."""
        items = self._registry.list_strategies()
        return StrategyListResponse(items=items, total=len(items))

    def show_strategy(self, name: str) -> StrategyShowResponse:
        """Return one seeded strategy definition."""
        return StrategyShowResponse(strategy=self._registry.get_strategy(name))

    def validate_strategy(self, name: str) -> StrategyValidationResult:
        """Validate one seeded strategy plus required local inputs."""
        strategy = self._registry.get_strategy(name)
        reason_blocks = [_validate_definition(strategy)]
        errors: list[StrategySectionError] = []

        try:
            if strategy.name == WALLET_SHADOW_STRATEGY:
                reason_blocks.extend(self._validate_wallet_shadow_inputs())
            elif strategy.name == MARKET_REVERSION_STRATEGY:
                reason_blocks.extend(self._validate_market_watch_inputs())
            elif strategy.name == RECURRING_STRATEGY:
                reason_blocks.extend(self._validate_recurring_inputs(strategy))
        except (
            StrategyRegistryError,
            StrategyStateError,
            WalletStateError,
            MarketStateError,
            StreamStateError,
        ) as exc:
            errors.append(
                StrategySectionError(
                    section="state",
                    code="state_error",
                    message=str(exc),
                )
            )

        valid = not errors and all(item.status == "pass" for item in reason_blocks)
        return StrategyValidationResult(
            strategy=strategy,
            valid=valid,
            reason_blocks=reason_blocks,
            errors=errors,
        )

    def evaluate_strategy(
        self,
        name: str,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> StrategyEvaluateResponse:
        """Evaluate one seeded strategy and persist any new candidate intents."""
        strategy = self._registry.get_strategy(name)
        if limit < 1:
            raise StrategyValidationError("Limit must be greater than zero.")

        if strategy.name == WALLET_SHADOW_STRATEGY:
            items, errors = self._evaluate_wallet_shadow_copy(strategy, limit=limit)
        elif strategy.name == MARKET_REVERSION_STRATEGY:
            items, errors = self._evaluate_market_watch_reversion(strategy, limit=limit)
        elif strategy.name == RECURRING_STRATEGY:
            items, errors = self._evaluate_recurring_observe(strategy, limit=limit)
        else:
            raise StrategyNotFoundError(f"strategy '{strategy.name}' was not found")

        persisted = self._state.append_intents(items)
        return StrategyEvaluateResponse(
            strategy=strategy,
            items=persisted,
            total=len(persisted),
            errors=errors,
        )

    def list_intents(self, *, limit: int = DEFAULT_LIMIT) -> StrategyIntentsResponse:
        """Return persisted candidate intents in reverse-chronological order."""
        if limit < 1:
            raise StrategyValidationError("Limit must be greater than zero.")
        all_intents = self._state.list_intents()
        intents = list(reversed(all_intents))[:limit]
        return StrategyIntentsResponse(
            items=[self._build_intent_view(intent) for intent in intents],
            total=len(all_intents),
        )

    def review_intent(self, intent_id: str) -> StrategyReviewResponse:
        """Return one persisted candidate intent plus its review history."""
        intent = self._state.get_intent(intent_id.strip())
        history = self._state.list_decisions(intent.intent_id)
        return StrategyReviewResponse(
            intent=self._build_intent_view(intent),
            decision_history=history,
        )

    def approve_intent(self, intent_id: str) -> StrategyDecisionMutationResponse:
        """Append a manual APPROVE decision for one candidate intent."""
        intent = self._state.get_intent(intent_id.strip())
        self._state.append_decision(
            StrategyDecisionRecord(
                intent_id=intent.intent_id,
                decision="APPROVE",
                reason="manual operator approval",
                decided_at=_utc_now_iso(),
            )
        )
        return StrategyDecisionMutationResponse(intent=self._build_intent_view(intent))

    def reject_intent(
        self,
        intent_id: str,
        *,
        reason: str,
    ) -> StrategyDecisionMutationResponse:
        """Append a manual REJECT decision for one candidate intent."""
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise StrategyValidationError("Reject reason is required.")

        intent = self._state.get_intent(intent_id.strip())
        self._state.append_decision(
            StrategyDecisionRecord(
                intent_id=intent.intent_id,
                decision="REJECT",
                reason=normalized_reason,
                decided_at=_utc_now_iso(),
            )
        )
        return StrategyDecisionMutationResponse(intent=self._build_intent_view(intent))

    def _validate_wallet_shadow_inputs(self) -> list[StrategyReasonBlock]:
        shadow_runs = self._wallet_state.list_shadow_runs()
        candidate_intents = [
            candidate
            for run in shadow_runs
            for candidate in run.candidate_intents
            if candidate.decision == "WOULD_COPY"
        ]
        return [
            StrategyReasonBlock(
                section="wallet_shadow_runs",
                status="pass" if shadow_runs else "fail",
                message=(
                    f"Found {len(shadow_runs)} stored shadow runs."
                    if shadow_runs
                    else "No wallet shadow runs were found."
                ),
            ),
            StrategyReasonBlock(
                section="wallet_shadow_candidates",
                status="pass" if candidate_intents else "fail",
                message=(
                    f"Found {len(candidate_intents)} copyable shadow candidates."
                    if candidate_intents
                    else "No copyable wallet shadow candidates were found."
                ),
            ),
        ]

    def _validate_market_watch_inputs(self) -> list[StrategyReasonBlock]:
        watchlist = self._market_state.list_watchlist()
        snapshots = self._market_state.list_snapshots()
        return [
            StrategyReasonBlock(
                section="market_watchlist",
                status="pass" if watchlist else "fail",
                message=(
                    f"Found {len(watchlist)} watched markets."
                    if watchlist
                    else "No watched markets were found."
                ),
            ),
            StrategyReasonBlock(
                section="market_snapshots",
                status="pass" if snapshots else "fail",
                message=(
                    f"Found {len(snapshots)} saved market snapshots."
                    if snapshots
                    else "No saved market snapshots were found."
                ),
            ),
        ]

    def _validate_recurring_inputs(self, strategy: StrategyDefinition) -> list[StrategyReasonBlock]:
        events = self._stream_store.list_events()
        symbol = str(strategy.settings["symbol"])
        market_events = [item for item in events if item.market_event is not None]
        crypto_events = [
            item
            for item in events
            if item.crypto_event is not None and item.crypto_event.symbol == symbol
        ]
        return [
            StrategyReasonBlock(
                section="recurring_settings",
                status="pass",
                message=(
                    f"Recurring settings are seeded for query '{strategy.settings['query']}' "
                    f"and interval '{strategy.settings['interval']}'."
                ),
            ),
            StrategyReasonBlock(
                section="market_stream_events",
                status="pass" if market_events else "fail",
                message=(
                    f"Found {len(market_events)} persisted market stream events."
                    if market_events
                    else "No persisted market stream events were found."
                ),
            ),
            StrategyReasonBlock(
                section="crypto_stream_events",
                status="pass" if crypto_events else "fail",
                message=(
                    f"Found {len(crypto_events)} persisted {symbol} crypto stream events."
                    if crypto_events
                    else f"No persisted {symbol} crypto stream events were found."
                ),
            ),
        ]

    def _evaluate_wallet_shadow_copy(
        self,
        strategy: StrategyDefinition,
        *,
        limit: int,
    ) -> tuple[list[StrategyCandidateIntent], list[StrategySectionError]]:
        shadow_runs = list(reversed(self._wallet_state.list_shadow_runs()))
        if not shadow_runs:
            return [], [
                StrategySectionError(
                    section="wallet_shadow_runs",
                    code="not_found",
                    message="No wallet shadow runs were available for strategy evaluation.",
                )
            ]

        artifacts: list[tuple[str, WalletShadowCandidateIntent]] = []
        for run in shadow_runs:
            for candidate in run.candidate_intents:
                artifacts.append((run.run_at, candidate))
                if len(artifacts) >= limit:
                    break
            if len(artifacts) >= limit:
                break

        items = [
            self._build_wallet_shadow_intent(strategy, run_at=run_at, candidate=candidate)
            for run_at, candidate in artifacts
        ]
        return items, []

    def _evaluate_market_watch_reversion(
        self,
        strategy: StrategyDefinition,
        *,
        limit: int,
    ) -> tuple[list[StrategyCandidateIntent], list[StrategySectionError]]:
        watched_markets = self._market_state.list_watchlist()[:limit]
        if not watched_markets:
            return [], [
                StrategySectionError(
                    section="market_watchlist",
                    code="not_found",
                    message="No watched markets were available for strategy evaluation.",
                )
            ]

        items: list[StrategyCandidateIntent] = []
        errors: list[StrategySectionError] = []
        settings = strategy.settings
        drift_threshold = _parse_decimal(str(settings["min_midpoint_drift_pct"]))
        spread_threshold = _parse_decimal(str(settings["min_spread_change"]))
        assert drift_threshold is not None
        assert spread_threshold is not None

        for watched_market in watched_markets:
            baseline_snapshots = self._market_state.list_snapshots(watched_market.market_slug)
            if not baseline_snapshots:
                errors.append(
                    StrategySectionError(
                        section=f"snapshot:{watched_market.market_slug}",
                        code="not_found",
                        message=(
                            "No baseline snapshot exists for market "
                            f"'{watched_market.market_slug}'."
                        ),
                    )
                )
                continue

            baseline = baseline_snapshots[-1]
            try:
                current = self._market_intel_service._build_snapshot_record(
                    slug=watched_market.market_slug,
                    allow_missing_market=False,
                    watched_market=watched_market,
                )
            except Exception as exc:
                errors.append(
                    StrategySectionError(
                        section=f"current_snapshot:{watched_market.market_slug}",
                        code=_error_code_for(exc),
                        message=str(exc),
                    )
                )
                items.append(
                    self._build_market_reversion_intent(
                        strategy,
                        baseline=baseline,
                        current=None,
                        token_id=None,
                        outcome=None,
                        decision="OBSERVE",
                        reasons=[
                            StrategyReasonBlock(
                                section="current_snapshot",
                                status="warn",
                                message="Current market snapshot could not be built.",
                            )
                        ],
                    )
                )
                continue

            errors.extend(
                StrategySectionError(
                    section=f"{watched_market.market_slug}:{error.section}",
                    code=error.code,
                    message=error.message,
                )
                for error in current.errors
            )

            comparison = _compare_snapshot_tokens(baseline, current)
            token_id = comparison["token_id"]
            outcome = comparison["outcome"]
            midpoint_drift = comparison["midpoint_drift_pct"]
            spread_delta = comparison["spread_delta"]
            reasons = [
                StrategyReasonBlock(
                    section="baseline_snapshot",
                    status="pass",
                    message=f"Using baseline snapshot from {baseline.snapshot_at}.",
                ),
                StrategyReasonBlock(
                    section="current_snapshot",
                    status="pass" if not current.errors else "warn",
                    message=f"Built current snapshot at {current.snapshot_at}.",
                ),
            ]

            if not current.active or current.closed:
                reasons.append(
                    StrategyReasonBlock(
                        section="market_state",
                        status="fail",
                        message="Market is inactive or closed.",
                    )
                )
                decision = "REJECT"
            elif midpoint_drift is None or spread_delta is None:
                reasons.append(
                    StrategyReasonBlock(
                        section="reversion_signal",
                        status="warn",
                        message="Comparable midpoint or spread data is incomplete.",
                    )
                )
                decision = "OBSERVE"
            elif midpoint_drift >= drift_threshold and spread_delta >= spread_threshold:
                reasons.append(
                    StrategyReasonBlock(
                        section="reversion_signal",
                        status="pass",
                        message="Spread widened and midpoint drift exceeded the seeded thresholds.",
                    )
                )
                decision = "WAIT"
            else:
                reasons.append(
                    StrategyReasonBlock(
                        section="reversion_signal",
                        status="warn",
                        message="Reversion thresholds were not met strongly enough for WAIT.",
                    )
                )
                decision = "OBSERVE"

            items.append(
                self._build_market_reversion_intent(
                    strategy,
                    baseline=baseline,
                    current=current,
                    token_id=token_id if isinstance(token_id, str) else None,
                    outcome=outcome if isinstance(outcome, str) else None,
                    decision=decision,
                    reasons=reasons,
                )
            )

        return items, errors

    def _evaluate_recurring_observe(
        self,
        strategy: StrategyDefinition,
        *,
        limit: int,
    ) -> tuple[list[StrategyCandidateIntent], list[StrategySectionError]]:
        errors: list[StrategySectionError] = []
        query = str(strategy.settings["query"])
        interval = str(strategy.settings["interval"])
        symbol = str(strategy.settings["symbol"]).upper()

        try:
            recurring = self._market_intel_service.recurring_latest(query, interval=interval)
        except Exception as exc:
            return [], [
                StrategySectionError(
                    section="recurring_market",
                    code=_error_code_for(exc),
                    message=str(exc),
                )
            ]

        if recurring.item is None:
            return [], [
                StrategySectionError(
                    section="recurring_market",
                    code="not_found",
                    message=(
                        f"No recurring market candidate was found for query '{query}' "
                        f"and interval '{interval}'."
                    ),
                )
            ]

        recurring_market = recurring.item
        inferred_symbol = infer_crypto_symbol(recurring_market)
        if inferred_symbol is not None and inferred_symbol != symbol:
            errors.append(
                StrategySectionError(
                    section="crypto_symbol",
                    code="invalid_argument",
                    message=(
                        f"Seeded symbol '{symbol}' does not match inferred "
                        f"symbol '{inferred_symbol}'."
                    ),
                )
            )

        events = self._stream_store.list_events()
        relevant_market_events = [
            item
            for item in events
            if item.market_event is not None
            and item.market_event.token_id in recurring_market.token_ids
        ][-limit:]
        relevant_crypto_events = [
            item
            for item in events
            if item.crypto_event is not None and item.crypto_event.symbol == symbol
        ][-limit:]

        if not relevant_market_events and not relevant_crypto_events:
            return [], [
                *errors,
                StrategySectionError(
                    section="stream_events",
                    code="not_found",
                    message=(
                        "No relevant persisted stream events were available "
                        "for recurring evaluation."
                    ),
                ),
            ]

        reasons = [
            StrategyReasonBlock(
                section="recurring_market",
                status="pass",
                message=(
                    f"Resolved recurring market '{recurring_market.market_slug}' "
                    f"for query '{query}' and interval '{interval}'."
                ),
            ),
            StrategyReasonBlock(
                section="market_stream_context",
                status="pass" if relevant_market_events else "warn",
                message=(
                    f"Found {len(relevant_market_events)} matching market stream events."
                    if relevant_market_events
                    else "No matching market stream events were found."
                ),
            ),
            StrategyReasonBlock(
                section="crypto_stream_context",
                status="pass" if relevant_crypto_events else "warn",
                message=(
                    f"Found {len(relevant_crypto_events)} matching {symbol} crypto stream events."
                    if relevant_crypto_events
                    else f"No matching {symbol} crypto stream events were found."
                ),
            ),
        ]

        market_direction = _market_direction(relevant_market_events)
        crypto_direction = _crypto_direction(relevant_crypto_events)
        if not recurring_market.active or recurring_market.closed:
            reasons.append(
                StrategyReasonBlock(
                    section="market_state",
                    status="fail",
                    message="Recurring market is inactive or closed.",
                )
            )
            decision = "REJECT"
        elif (
            market_direction is not None
            and crypto_direction is not None
            and market_direction == crypto_direction
            and market_direction != 0
        ):
            reasons.append(
                StrategyReasonBlock(
                    section="alignment",
                    status="pass",
                    message=(
                        "Recurring market direction aligns with persisted "
                        "crypto stream direction."
                    ),
                )
            )
            decision = "WAIT"
        else:
            reasons.append(
                StrategyReasonBlock(
                    section="alignment",
                    status="warn",
                    message=(
                        "Recurring market and crypto stream context did not "
                        "align strongly enough for WAIT."
                    ),
                )
            )
            decision = "OBSERVE"

        latest_market_event = relevant_market_events[-1] if relevant_market_events else None
        latest_crypto_event = relevant_crypto_events[-1] if relevant_crypto_events else None
        token_id = (
            latest_market_event.market_event.token_id
            if latest_market_event is not None and latest_market_event.market_event is not None
            else None
        )
        outcome = _resolve_outcome_for_token(recurring_market, token_id)
        intent = StrategyCandidateIntent(
            intent_id=_make_intent_id(
                strategy.name,
                recurring_market.market_slug,
                latest_market_event.captured_at if latest_market_event is not None else "",
                latest_crypto_event.captured_at if latest_crypto_event is not None else "",
            ),
            strategy_name=strategy.name,
            strategy_type=strategy.strategy_type,
            source_kind="recurring_stream",
            market_slug=recurring_market.market_slug,
            condition_id=recurring_market.condition_id,
            token_id=token_id,
            side=None,
            outcome=outcome,
            decision=decision,
            reason_blocks=reasons,
            created_at=_utc_now_iso(),
            source_refs=_compact_refs(
                [
                    StrategySourceReference(
                        source_kind="recurring_market",
                        reference_id=recurring_market.market_slug,
                        label=interval,
                    ),
                    StrategySourceReference(
                        source_kind="stream_session",
                        reference_id=latest_market_event.session_id,
                        label="market",
                    )
                    if latest_market_event is not None
                    else None,
                    StrategySourceReference(
                        source_kind="stream_session",
                        reference_id=latest_crypto_event.session_id,
                        label="crypto",
                    )
                    if latest_crypto_event is not None
                    else None,
                ]
            ),
        )
        return [intent], errors

    def _build_wallet_shadow_intent(
        self,
        strategy: StrategyDefinition,
        *,
        run_at: str,
        candidate: WalletShadowCandidateIntent,
    ) -> StrategyCandidateIntent:
        reasons = [
            StrategyReasonBlock(
                section="shadow_source",
                status="pass" if candidate.decision == "WOULD_COPY" else "fail",
                message=(
                    "Upstream wallet shadow candidate was copyable."
                    if candidate.decision == "WOULD_COPY"
                    else "Upstream wallet shadow candidate was skipped."
                ),
            )
        ]
        if candidate.decision != "WOULD_COPY":
            reasons.append(
                StrategyReasonBlock(
                    section="manual_gate",
                    status="fail",
                    message="Skipped upstream candidates are rejected by the seeded strategy.",
                )
            )
            decision = "REJECT"
        elif _wallet_candidate_complete(candidate):
            reasons.extend(
                [
                    StrategyReasonBlock(
                        section="source_metadata",
                        status="pass",
                        message="Required market and token metadata is present.",
                    ),
                    StrategyReasonBlock(
                        section="manual_gate",
                        status="pass",
                        message="Copyable candidate promoted to WAIT pending manual approval.",
                    ),
                ]
            )
            decision = "WAIT"
        else:
            reasons.extend(
                [
                    StrategyReasonBlock(
                        section="source_metadata",
                        status="warn",
                        message="Candidate metadata is incomplete or missing timestamp context.",
                    ),
                    StrategyReasonBlock(
                        section="manual_gate",
                        status="warn",
                        message=(
                            "Candidate remains OBSERVE until the source "
                            "context is more complete."
                        ),
                    ),
                ]
            )
            decision = "OBSERVE"

        return StrategyCandidateIntent(
            intent_id=_make_intent_id(
                strategy.name,
                candidate.source_wallet,
                candidate.dedupe_key,
                candidate.decision,
            ),
            strategy_name=strategy.name,
            strategy_type=strategy.strategy_type,
            source_kind="wallet_shadow",
            market_slug=candidate.market_slug,
            condition_id=candidate.condition_id,
            token_id=candidate.token_id,
            side=candidate.side,
            outcome=candidate.outcome,
            decision=decision,
            reason_blocks=reasons,
            created_at=run_at,
            source_refs=_compact_refs(
                [
                    StrategySourceReference(
                        source_kind="wallet_shadow_run",
                        reference_id=run_at,
                        label=candidate.source_wallet,
                    ),
                    StrategySourceReference(
                        source_kind="wallet_shadow_candidate",
                        reference_id=candidate.dedupe_key,
                        label=candidate.transaction_hash,
                    ),
                ]
            ),
        )

    def _build_market_reversion_intent(
        self,
        strategy: StrategyDefinition,
        *,
        baseline: MarketSnapshotRecord,
        current: MarketSnapshotRecord | None,
        token_id: str | None,
        outcome: str | None,
        decision: str,
        reasons: list[StrategyReasonBlock],
    ) -> StrategyCandidateIntent:
        current_snapshot_at = current.snapshot_at if current is not None else "missing"
        return StrategyCandidateIntent(
            intent_id=_make_intent_id(
                strategy.name,
                baseline.market_slug,
                baseline.snapshot_at,
                current_snapshot_at,
            ),
            strategy_name=strategy.name,
            strategy_type=strategy.strategy_type,
            source_kind="market_snapshot",
            market_slug=baseline.market_slug,
            condition_id=current.condition_id if current is not None else baseline.condition_id,
            token_id=token_id,
            side=None,
            outcome=outcome,
            decision=decision,
            reason_blocks=reasons,
            created_at=_utc_now_iso(),
            source_refs=_compact_refs(
                [
                    StrategySourceReference(
                        source_kind="market_snapshot",
                        reference_id=baseline.snapshot_at,
                        label="baseline",
                    ),
                    StrategySourceReference(
                        source_kind="market_snapshot",
                        reference_id=current.snapshot_at,
                        label="current",
                    )
                    if current is not None
                    else None,
                ]
            ),
        )

    def _build_intent_view(self, intent: StrategyCandidateIntent) -> StrategyIntentView:
        decisions = self._state.list_decisions(intent.intent_id)
        latest = decisions[-1] if decisions else None
        current_decision = latest.decision if latest is not None else intent.decision
        return StrategyIntentView(
            intent=intent,
            current_decision=current_decision,
            latest_decision=latest,
        )


def _validate_definition(strategy: StrategyDefinition) -> StrategyReasonBlock:
    if strategy.name != strategy.strategy_type:
        return StrategyReasonBlock(
            section="strategy_definition",
            status="fail",
            message="Seeded strategy name must match the strategy type in v1.",
        )
    return StrategyReasonBlock(
        section="strategy_definition",
        status="pass",
        message="Seeded strategy definition is internally consistent.",
    )


def _wallet_candidate_complete(candidate: WalletShadowCandidateIntent) -> bool:
    required = [
        candidate.market_slug,
        candidate.condition_id,
        candidate.token_id,
        candidate.side,
        candidate.source_price,
        candidate.current_price,
        candidate.timestamp,
    ]
    return all(item is not None for item in required)


def _compare_snapshot_tokens(
    baseline: MarketSnapshotRecord,
    current: MarketSnapshotRecord,
) -> SnapshotTokenComparison:
    baseline_by_token = {token.token_id: token for token in baseline.tokens}
    best_token_id: str | None = None
    best_outcome: str | None = None
    best_midpoint_drift: Decimal | None = None
    best_spread_delta: Decimal | None = None

    for index, token in enumerate(current.tokens):
        prior = baseline_by_token.get(token.token_id)
        if prior is None:
            continue
        midpoint_drift = _pct_delta(prior.midpoint, token.midpoint)
        spread_delta = _abs_delta(prior.spread, token.spread)
        if midpoint_drift is None and spread_delta is None:
            continue
        if best_midpoint_drift is None or (
            midpoint_drift is not None and midpoint_drift > best_midpoint_drift
        ):
            best_token_id = token.token_id
            best_outcome = token.outcome or (
                current.outcomes[index] if index < len(current.outcomes) else None
            )
            best_midpoint_drift = midpoint_drift
            best_spread_delta = spread_delta

    return {
        "token_id": best_token_id,
        "outcome": best_outcome,
        "midpoint_drift_pct": best_midpoint_drift,
        "spread_delta": best_spread_delta,
    }


def _pct_delta(old_value: str | None, new_value: str | None) -> Decimal | None:
    old_decimal = _parse_decimal(old_value)
    new_decimal = _parse_decimal(new_value)
    if old_decimal is None or new_decimal is None or old_decimal <= Decimal("0"):
        return None
    return ((new_decimal - old_decimal).copy_abs() / old_decimal) * Decimal("100")


def _abs_delta(old_value: str | None, new_value: str | None) -> Decimal | None:
    old_decimal = _parse_decimal(old_value)
    new_decimal = _parse_decimal(new_value)
    if old_decimal is None or new_decimal is None:
        return None
    return (new_decimal - old_decimal).copy_abs()


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _market_direction(events: list[CapturedStreamEvent]) -> int | None:
    first_value = _first_market_value(events)
    last_value = _last_market_value(events)
    return _direction(first_value, last_value)


def _crypto_direction(events: list[CapturedStreamEvent]) -> int | None:
    first_value = (
        events[0].crypto_event.value
        if events and events[0].crypto_event is not None
        else None
    )
    last_value = (
        events[-1].crypto_event.value
        if events and events[-1].crypto_event is not None
        else None
    )
    return _direction(first_value, last_value)


def _first_market_value(events: list[CapturedStreamEvent]) -> str | None:
    for event in events:
        if event.market_event is None:
            continue
        if event.market_event.midpoint is not None:
            return event.market_event.midpoint
        if event.market_event.price is not None:
            return event.market_event.price
    return None


def _last_market_value(events: list[CapturedStreamEvent]) -> str | None:
    for event in reversed(events):
        if event.market_event is None:
            continue
        if event.market_event.midpoint is not None:
            return event.market_event.midpoint
        if event.market_event.price is not None:
            return event.market_event.price
    return None


def _direction(old_value: str | None, new_value: str | None) -> int | None:
    old_decimal = _parse_decimal(old_value)
    new_decimal = _parse_decimal(new_value)
    if old_decimal is None or new_decimal is None:
        return None
    if new_decimal > old_decimal:
        return 1
    if new_decimal < old_decimal:
        return -1
    return 0


def _resolve_outcome_for_token(
    market: RecurringMarketCandidate,
    token_id: str | None,
) -> str | None:
    if token_id is None:
        return None
    try:
        index = market.token_ids.index(token_id)
    except ValueError:
        return None
    return market.outcomes[index] if index < len(market.outcomes) else None


def _compact_refs(
    refs: Iterable[StrategySourceReference | None],
) -> list[StrategySourceReference]:
    return [item for item in refs if item is not None]


def _make_intent_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"intent-{digest[:12]}"


def _error_code_for(exc: Exception) -> str:
    if isinstance(exc, (StrategyValidationError, MarketValidationError)):
        return "invalid_argument"
    if isinstance(exc, (StrategyNotFoundError, StrategyIntentNotFoundError)):
        return "not_found"
    if isinstance(
        exc,
        (
            StrategyRegistryError,
            StrategyStateError,
            WalletStateError,
            MarketStateError,
            StreamStateError,
        ),
    ):
        return "state_error"
    return "request_failed"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
