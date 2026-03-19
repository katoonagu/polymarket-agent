"""Guarded bridge from approved strategy intents into the execution layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from pm.auth import AuthClientError, AuthValidationError
from pm.execution import (
    DryRunService,
    ExecutionReasonBlock,
    ExecutionValidationError,
    OrderLifecycleService,
)
from pm.market import ClobClientError
from pm.market.models import NormalizedBook, NormalizedMarket
from pm.risk import RiskPolicy, RiskPolicyService
from pm.strategy.models import (
    StrategyCandidateIntent,
    StrategyDispatchPendingResponse,
    StrategyDispatchResponse,
    StrategyDispatchResultRecord,
    StrategyExecutionDetailResponse,
    StrategyExecutionLinkRecord,
    StrategyExecutionRequest,
    StrategyExecutionsResponse,
    StrategyIntentView,
    StrategyReasonBlock,
    StrategySourceReference,
)
from pm.strategy.state import StrategyStateService
from pm.wallet.models import WalletShadowCandidateIntent, WalletShadowRun
from pm.wallet.state import WalletPipelineStateService

DEFAULT_LIMIT = 20
DISPATCHABLE_STRATEGY = "wallet_shadow_copy"
NON_SKIP_DECISIONS = {"WOULD_POST", "POSTED"}


class StrategyDispatchValidationError(RuntimeError):
    """Raised when strategy dispatch inputs are invalid."""


@dataclass(slots=True, frozen=True)
class DispatchContext:
    """Resolved upstream context used to build one execution request."""

    candidate: WalletShadowCandidateIntent
    market: NormalizedMarket
    book: NormalizedBook
    midpoint: str | None
    spread: str | None
    price: str
    size: str
    notional_usdc: str


class StrategyDispatchService:
    """Manual strategy-dispatch bridge into the existing execution lifecycle."""

    def __init__(
        self,
        *,
        state: StrategyStateService | None = None,
        wallet_state: WalletPipelineStateService | None = None,
        risk_service: RiskPolicyService | None = None,
        dry_run_service: DryRunService | None = None,
        order_lifecycle: OrderLifecycleService | None = None,
    ) -> None:
        self._state = state or StrategyStateService()
        self._wallet_state = wallet_state or WalletPipelineStateService()
        self._risk_service = risk_service or RiskPolicyService()
        self._dry_run_service = dry_run_service or DryRunService()
        self._order_lifecycle = order_lifecycle or OrderLifecycleService()

    def dispatch_intent(
        self,
        intent_id: str,
        *,
        live: bool = False,
    ) -> StrategyDispatchResponse:
        """Dispatch one approved intent into paper or live execution."""
        normalized_intent_id = intent_id.strip()
        if not normalized_intent_id:
            raise StrategyDispatchValidationError("Intent id is required.")

        intent = self._state.get_intent(normalized_intent_id)
        intent_view = self._build_intent_view(intent)
        policy = self._risk_service.get_policy(intent.strategy_name)
        mode = "live" if live else "paper"

        prior_results = self._state.list_dispatch_results(intent_id=intent.intent_id)
        if any(item.decision in NON_SKIP_DECISIONS for item in prior_results):
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="dispatch_gate",
                        status="fail",
                        message="Intent already has a non-skip strategy dispatch result.",
                    )
                ],
            )

        if intent_view.current_decision != "APPROVE":
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="approval_gate",
                        status="fail",
                        message="Only manually approved strategy intents may dispatch.",
                    )
                ],
            )

        if not policy.dispatch_enabled:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="strategy_dispatch",
                        status="fail",
                        message=(
                            f"Strategy '{intent.strategy_name}' is not dispatch-enabled "
                            "under the effective risk policy."
                        ),
                    )
                ],
            )

        if intent.strategy_name != DISPATCHABLE_STRATEGY:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="strategy_dispatch",
                        status="fail",
                        message="This strategy is not dispatchable in the current phase.",
                    )
                ],
            )

        context_or_skip = self._resolve_dispatch_context(intent_view=intent_view, mode=mode)
        if isinstance(context_or_skip, StrategyDispatchResponse):
            return context_or_skip
        context = context_or_skip

        resolved_outcome = (intent.outcome or context.candidate.outcome or "").lower()
        resolved_side = (intent.side or context.candidate.side or "").lower()
        if resolved_outcome not in {"yes", "no"} or resolved_side not in {"buy", "sell"}:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="execution_request",
                        status="fail",
                        message=(
                            "Approved intent did not contain executable outcome "
                            "and side context."
                        ),
                    )
                ],
            )

        execution_request = StrategyExecutionRequest(
            market_ref=context.market.condition_id or context.market.market_slug,
            market_slug=context.market.market_slug,
            condition_id=context.market.condition_id,
            token_id=context.candidate.token_id,
            outcome=resolved_outcome,
            side=resolved_side,
            price=context.price,
            size=context.size,
            notional_usdc=context.notional_usdc,
        )
        risk_checks = self._evaluate_risk(
            intent=intent_view,
            policy=policy,
            context=context,
            execution_request=execution_request,
        )
        if any(item.status == "fail" for item in risk_checks):
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                execution_request=execution_request,
                risk_checks=risk_checks,
            )

        execution_response = self._order_lifecycle.post(
            market_ref=execution_request.market_ref,
            outcome=execution_request.outcome,
            side=execution_request.side,
            price=execution_request.price,
            size=execution_request.size,
            order_type=execution_request.order_type,
            post_only=execution_request.post_only,
            live=live,
            confirm=live,
        )
        live_response = execution_response.live_response
        order_id = _extract_live_order_id(live_response)
        return self._persist_dispatch(
            intent=intent_view,
            mode=mode,
            decision=execution_response.decision,
            execution_request=execution_request,
            risk_checks=risk_checks,
            execution_reasons=_convert_execution_reasons(execution_response.reasons),
            execution_plan_id=execution_response.plan_id,
            execution_result_id=execution_response.result_id,
            order_id=order_id,
            execution_response=live_response,
        )

    def dispatch_pending(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        live: bool = False,
    ) -> StrategyDispatchPendingResponse:
        """Dispatch newest approved and undispatched eligible intents."""
        if limit < 1:
            raise StrategyDispatchValidationError("Limit must be greater than zero.")

        selected: list[str] = []
        for intent in reversed(self._state.list_intents()):
            if len(selected) >= limit:
                break
            prior_results = self._state.list_dispatch_results(intent_id=intent.intent_id)
            if any(item.decision in NON_SKIP_DECISIONS for item in prior_results):
                continue
            if self._risk_service.get_policy(intent.strategy_name).dispatch_enabled is False:
                continue
            if self._build_intent_view(intent).current_decision != "APPROVE":
                continue
            selected.append(intent.intent_id)

        items = [self.dispatch_intent(intent_id, live=live) for intent_id in selected]
        dispatched = sum(1 for item in items if item.execution.decision in NON_SKIP_DECISIONS)
        skipped = sum(1 for item in items if item.execution.decision == "SKIP")
        return StrategyDispatchPendingResponse(
            items=items,
            total_candidates=len(selected),
            total_dispatched=dispatched,
            total_skipped=skipped,
        )

    def list_executions(self, *, limit: int = DEFAULT_LIMIT) -> StrategyExecutionsResponse:
        """Return persisted strategy dispatch results newest-first."""
        if limit < 1:
            raise StrategyDispatchValidationError("Limit must be greater than zero.")
        results = self._state.list_dispatch_results()
        items = list(reversed(results))[:limit]
        return StrategyExecutionsResponse(items=items, total=len(results))

    def get_execution(self, execution_id: str) -> StrategyExecutionDetailResponse:
        """Return one persisted strategy dispatch execution by id."""
        normalized_execution_id = execution_id.strip()
        if not normalized_execution_id:
            raise StrategyDispatchValidationError("Execution id is required.")
        result = self._state.get_dispatch_result(normalized_execution_id)
        link = self._state.get_execution_link(normalized_execution_id)
        intent = self._state.get_intent(result.intent_id)
        return StrategyExecutionDetailResponse(
            intent=self._build_intent_view(intent),
            link=link,
            execution=result,
        )

    def _resolve_dispatch_context(
        self,
        *,
        intent_view: StrategyIntentView,
        mode: str,
    ) -> DispatchContext | StrategyDispatchResponse:
        intent = intent_view.intent
        candidate = self._resolve_wallet_shadow_candidate(intent.source_refs)
        if candidate is None:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="source_resolution",
                        status="fail",
                        message="Upstream wallet shadow candidate could not be resolved.",
                    )
                ],
            )

        market_ref = candidate.condition_id or candidate.market_slug
        if market_ref is None:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="source_resolution",
                        status="fail",
                        message=(
                            "Resolved wallet shadow candidate did not include a "
                            "market reference."
                        ),
                    )
                ],
            )

        market = self._dry_run_service.resolve_market(market_ref)
        if market is None:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="market_context",
                        status="fail",
                        message=f"Market '{market_ref}' could not be resolved.",
                    )
                ],
            )

        if candidate.token_id is None:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="source_resolution",
                        status="fail",
                        message="Resolved wallet shadow candidate did not include a token id.",
                    )
                ],
            )

        try:
            book, midpoint, spread = self._dry_run_service.load_public_book_context(
                candidate.token_id
            )
        except (ClobClientError, ExecutionValidationError) as exc:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="book_context",
                        status="fail",
                        message=str(exc),
                    )
                ],
            )

        price = _select_dispatch_price(
            intent=intent,
            book=book,
            midpoint=midpoint,
            candidate=candidate,
        )
        if price is None:
            return self._persist_dispatch(
                intent=intent_view,
                mode=mode,
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="dispatch_price",
                        status="fail",
                        message="Dispatch price could not be derived from book or source context.",
                    )
                ],
            )

        size = _derive_size(candidate.simulated_size_usdc, price)
        if size is None:
            return self._persist_dispatch(
                intent=intent_view,
                mode="paper",
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="dispatch_size",
                        status="fail",
                        message=(
                            "Dispatch size could not be derived from simulated "
                            "notional and price."
                        ),
                    )
                ],
            )

        notional = _notional_usdc(price, size)
        if notional is None:
            return self._persist_dispatch(
                intent=intent_view,
                mode="paper",
                decision="SKIP",
                risk_checks=[
                    StrategyReasonBlock(
                        section="dispatch_size",
                        status="fail",
                        message="Dispatch notional could not be derived from price and size.",
                    )
                ],
            )

        return DispatchContext(
            candidate=candidate,
            market=market,
            book=book,
            midpoint=midpoint,
            spread=spread,
            price=price,
            size=size,
            notional_usdc=notional,
        )

    def _resolve_wallet_shadow_candidate(
        self,
        refs: list[StrategySourceReference],
    ) -> WalletShadowCandidateIntent | None:
        run_ref = _find_ref(refs, "wallet_shadow_run")
        candidate_ref = _find_ref(refs, "wallet_shadow_candidate")
        if run_ref is None or candidate_ref is None:
            return None

        for run in self._wallet_state.list_shadow_runs():
            if run.run_at != run_ref.reference_id:
                continue
            candidate = _find_wallet_shadow_candidate(run, candidate_ref.reference_id)
            if candidate is not None:
                return candidate
        return None

    def _evaluate_risk(
        self,
        *,
        intent: StrategyIntentView,
        policy: RiskPolicy,
        context: DispatchContext,
        execution_request: StrategyExecutionRequest,
    ) -> list[StrategyReasonBlock]:
        checks = [
            _market_open_check(policy, context.market),
            _drift_check(policy, context.candidate.source_price, context.price),
            _spread_check(policy, context.spread, context.price),
            _max_order_check(policy, context.notional_usdc),
        ]

        market_exposure = self._current_exposure(condition_id=context.market.condition_id)
        strategy_exposure = self._current_exposure(strategy_name=intent.intent.strategy_name)
        checks.extend(
            [
                _max_exposure_check(
                    section="max_exposure_per_market",
                    current_exposure=market_exposure,
                    additional_notional=context.notional_usdc,
                    threshold=policy.max_exposure_usdc_per_market,
                    identifier=context.market.condition_id or context.market.market_slug,
                ),
                _max_exposure_check(
                    section="max_exposure_per_strategy",
                    current_exposure=strategy_exposure,
                    additional_notional=context.notional_usdc,
                    threshold=policy.max_exposure_usdc_per_strategy,
                    identifier=intent.intent.strategy_name,
                ),
            ]
        )

        try:
            readiness = self._order_lifecycle.balance_allowance_reasons(
                token_id=context.candidate.token_id,
                side=execution_request.side,
                price=execution_request.price,
                size=execution_request.size,
            )
            checks.extend(
                _convert_readiness_reasons(
                    readiness,
                    require_balance=policy.require_balance_ready,
                    require_allowance=policy.require_allowance_ready,
                )
            )
        except (
            AuthValidationError,
            AuthClientError,
            ExecutionValidationError,
        ) as exc:
            checks.append(
                StrategyReasonBlock(
                    section="funding_readiness",
                    status="fail",
                    message=str(exc),
                )
            )

        return checks

    def _current_exposure(
        self,
        *,
        condition_id: str | None = None,
        strategy_name: str | None = None,
    ) -> str:
        total = Decimal("0")
        for result in self._state.list_dispatch_results():
            if result.decision not in NON_SKIP_DECISIONS:
                continue
            if result.execution_request is None:
                continue
            if condition_id is not None and result.condition_id != condition_id:
                continue
            if strategy_name is not None and result.strategy_name != strategy_name:
                continue
            amount = _parse_decimal(result.execution_request.notional_usdc)
            if amount is not None:
                total += amount
        return _decimal_to_string(total)

    def _persist_dispatch(
        self,
        *,
        intent: StrategyIntentView,
        mode: str,
        decision: str,
        execution_request: StrategyExecutionRequest | None = None,
        risk_checks: list[StrategyReasonBlock] | None = None,
        execution_reasons: list[StrategyReasonBlock] | None = None,
        execution_plan_id: str | None = None,
        execution_result_id: str | None = None,
        order_id: str | None = None,
        execution_response: dict[str, Any] | None = None,
    ) -> StrategyDispatchResponse:
        execution_id = _make_execution_id()
        created_at = _utc_now_iso()
        link = StrategyExecutionLinkRecord(
            execution_id=execution_id,
            intent_id=intent.intent.intent_id,
            strategy_name=intent.intent.strategy_name,
            strategy_type=intent.intent.strategy_type,
            mode=mode,
            created_at=created_at,
            execution_plan_id=execution_plan_id,
            execution_result_id=execution_result_id,
            order_id=order_id,
        )
        result = StrategyDispatchResultRecord(
            execution_id=execution_id,
            intent_id=intent.intent.intent_id,
            strategy_name=intent.intent.strategy_name,
            strategy_type=intent.intent.strategy_type,
            mode=mode,
            decision=decision,
            created_at=created_at,
            market_slug=intent.intent.market_slug,
            condition_id=intent.intent.condition_id,
            token_id=intent.intent.token_id,
            outcome=intent.intent.outcome,
            side=intent.intent.side,
            execution_request=execution_request,
            risk_checks=risk_checks or [],
            execution_reasons=execution_reasons or [],
            execution_plan_id=execution_plan_id,
            execution_result_id=execution_result_id,
            order_id=order_id,
            execution_response=execution_response,
        )
        self._state.append_execution_link(link)
        self._state.append_dispatch_result(result)
        return StrategyDispatchResponse(intent=intent, link=link, execution=result)

    def _build_intent_view(self, intent: StrategyCandidateIntent) -> StrategyIntentView:
        decisions = self._state.list_decisions(intent.intent_id)
        latest = decisions[-1] if decisions else None
        current_decision = latest.decision if latest is not None else intent.decision
        return StrategyIntentView(
            intent=intent,
            current_decision=current_decision,
            latest_decision=latest,
        )


def _find_ref(
    refs: list[StrategySourceReference],
    source_kind: str,
) -> StrategySourceReference | None:
    for ref in refs:
        if ref.source_kind == source_kind:
            return ref
    return None


def _find_wallet_shadow_candidate(
    run: WalletShadowRun,
    dedupe_key: str,
) -> WalletShadowCandidateIntent | None:
    for candidate in run.candidate_intents:
        if candidate.dedupe_key == dedupe_key:
            return candidate
    return None


def _select_dispatch_price(
    *,
    intent: StrategyCandidateIntent,
    book: NormalizedBook,
    midpoint: str | None,
    candidate: WalletShadowCandidateIntent,
) -> str | None:
    side = (intent.side or candidate.side or "").strip().lower()
    if side == "buy":
        if book.asks:
            return book.asks[0].price
        if midpoint is not None:
            return midpoint
        return candidate.current_price
    if side == "sell":
        if book.bids:
            return book.bids[0].price
        if midpoint is not None:
            return midpoint
        return candidate.current_price
    return None


def _derive_size(simulated_size_usdc: str, price: str) -> str | None:
    notional = _parse_decimal(simulated_size_usdc)
    price_value = _parse_decimal(price)
    if notional is None or price_value is None or price_value <= Decimal("0"):
        return None
    size = (notional / price_value).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    if size <= Decimal("0"):
        return None
    return _decimal_to_string(size)


def _notional_usdc(price: str, size: str) -> str | None:
    price_value = _parse_decimal(price)
    size_value = _parse_decimal(size)
    if price_value is None or size_value is None:
        return None
    return _decimal_to_string(price_value * size_value)


def _market_open_check(policy: RiskPolicy, market: NormalizedMarket) -> StrategyReasonBlock:
    if not policy.require_market_open:
        return StrategyReasonBlock(
            section="market_open",
            status="pass",
            message="Market-open requirement is disabled by policy.",
        )
    if market.active and not market.closed:
        return StrategyReasonBlock(
            section="market_open",
            status="pass",
            message="Market is active and open.",
        )
    return StrategyReasonBlock(
        section="market_open",
        status="fail",
        message="Market is inactive or closed.",
    )


def _drift_check(
    policy: RiskPolicy,
    source_price: str | None,
    dispatch_price: str,
) -> StrategyReasonBlock:
    threshold = _parse_decimal(policy.max_drift_pct)
    source_value = _parse_decimal(source_price)
    dispatch_value = _parse_decimal(dispatch_price)
    if threshold is None or source_value is None or dispatch_value is None or source_value <= 0:
        return StrategyReasonBlock(
            section="drift_threshold",
            status="fail",
            message="Fresh dispatch drift could not be evaluated from source and dispatch prices.",
        )
    drift = ((dispatch_value - source_value).copy_abs() / source_value) * Decimal("100")
    if drift <= threshold:
        return StrategyReasonBlock(
            section="drift_threshold",
            status="pass",
            message=(
                f"Dispatch drift { _decimal_to_string(drift) }% is within the "
                f"{policy.max_drift_pct}% limit."
            ),
        )
    return StrategyReasonBlock(
        section="drift_threshold",
        status="fail",
        message=(
            f"Dispatch drift { _decimal_to_string(drift) }% exceeds the "
            f"{policy.max_drift_pct}% limit."
        ),
    )


def _spread_check(
    policy: RiskPolicy,
    spread: str | None,
    dispatch_price: str,
) -> StrategyReasonBlock:
    threshold = _parse_decimal(policy.max_spread_pct)
    spread_value = _parse_decimal(spread)
    price_value = _parse_decimal(dispatch_price)
    if threshold is None or spread_value is None or price_value is None or price_value <= 0:
        return StrategyReasonBlock(
            section="spread_threshold",
            status="fail",
            message="Fresh dispatch spread percentage could not be evaluated.",
        )
    spread_pct = (spread_value / price_value) * Decimal("100")
    if spread_pct <= threshold:
        return StrategyReasonBlock(
            section="spread_threshold",
            status="pass",
            message=(
                f"Dispatch spread { _decimal_to_string(spread_pct) }% is within the "
                f"{policy.max_spread_pct}% limit."
            ),
        )
    return StrategyReasonBlock(
        section="spread_threshold",
        status="fail",
        message=(
            f"Dispatch spread { _decimal_to_string(spread_pct) }% exceeds the "
            f"{policy.max_spread_pct}% limit."
        ),
    )


def _max_order_check(policy: RiskPolicy, notional_usdc: str) -> StrategyReasonBlock:
    threshold = _parse_decimal(policy.max_size_usdc_per_order)
    notional = _parse_decimal(notional_usdc)
    if threshold is None or notional is None:
        return StrategyReasonBlock(
            section="max_size_per_order",
            status="fail",
            message="Dispatch notional could not be compared against the max order size policy.",
        )
    if notional <= threshold:
        return StrategyReasonBlock(
            section="max_size_per_order",
            status="pass",
            message=(
                f"Dispatch notional {notional_usdc} is within the "
                f"{policy.max_size_usdc_per_order} USDC limit."
            ),
        )
    return StrategyReasonBlock(
        section="max_size_per_order",
        status="fail",
        message=(
            f"Dispatch notional {notional_usdc} exceeds the "
            f"{policy.max_size_usdc_per_order} USDC limit."
        ),
    )


def _max_exposure_check(
    *,
    section: str,
    current_exposure: str,
    additional_notional: str,
    threshold: str,
    identifier: str | None,
) -> StrategyReasonBlock:
    current_value = _parse_decimal(current_exposure)
    additional_value = _parse_decimal(additional_notional)
    threshold_value = _parse_decimal(threshold)
    if current_value is None or additional_value is None or threshold_value is None:
        return StrategyReasonBlock(
            section=section,
            status="fail",
            message="Exposure could not be evaluated against the configured threshold.",
        )
    combined = current_value + additional_value
    if combined <= threshold_value:
        return StrategyReasonBlock(
            section=section,
            status="pass",
            message=(
                f"Combined exposure { _decimal_to_string(combined) } stays within the "
                f"{threshold} USDC limit for {identifier or 'this scope'}."
            ),
        )
    return StrategyReasonBlock(
        section=section,
        status="fail",
        message=(
            f"Combined exposure { _decimal_to_string(combined) } exceeds the "
            f"{threshold} USDC limit for {identifier or 'this scope'}."
        ),
    )


def _convert_readiness_reasons(
    reasons: list[ExecutionReasonBlock],
    *,
    require_balance: bool,
    require_allowance: bool,
) -> list[StrategyReasonBlock]:
    converted: list[StrategyReasonBlock] = []
    for item in reasons:
        status = item.status
        if item.section == "balance" and item.status == "fail" and not require_balance:
            status = "warn"
        if item.section == "allowance" and item.status == "fail" and not require_allowance:
            status = "warn"
        converted.append(
            StrategyReasonBlock(
                section=item.section,
                status=status,
                message=item.message,
            )
        )
    return converted


def _convert_execution_reasons(
    reasons: list[ExecutionReasonBlock],
) -> list[StrategyReasonBlock]:
    return [
        StrategyReasonBlock(
            section=item.section,
            status=item.status,
            message=item.message,
        )
        for item in reasons
    ]


def _extract_live_order_id(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    order = payload.get("order")
    if isinstance(order, dict):
        value = order.get("order_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _decimal_to_string(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _make_execution_id() -> str:
    return f"strategy_exec_{uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
