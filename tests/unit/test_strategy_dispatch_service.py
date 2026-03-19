"""Unit tests for the guarded strategy-to-execution bridge."""

from __future__ import annotations

from dataclasses import dataclass

from pm.auth.models import AuthContext
from pm.execution import (
    DryRunPostContext,
    ExecutionReasonBlock,
    PostOrderRequest,
    PostOrderResponse,
)
from pm.market.models import NormalizedBook, NormalizedBookLevel, NormalizedMarket
from pm.risk import RiskPoliciesFile, RiskPolicyService, RiskStateService
from pm.strategy import (
    StrategyCandidateIntent,
    StrategyDecisionRecord,
    StrategyStateService,
)
from pm.strategy.dispatch import StrategyDispatchService
from pm.strategy.models import StrategySourceReference
from pm.strategy.registry import StrategyRegistryService
from pm.wallet.models import (
    WalletShadowCandidateIntent,
    WalletShadowRun,
    WalletShadowRunParameters,
)
from pm.wallet.state import WalletPipelineStateService

CONDITION_ID = "0x" + ("a" * 64)
TOKEN_ID = "100"


@dataclass
class DispatchFixture:
    service: StrategyDispatchService
    state: StrategyStateService
    wallet_state: WalletPipelineStateService
    risk_state: RiskStateService


class FakeDryRunService:
    def __init__(
        self,
        *,
        market: NormalizedMarket | None = None,
        book: NormalizedBook | None = None,
        midpoint: str | None = "0.55",
        spread: str | None = "0.02",
    ) -> None:
        self.market = market or NormalizedMarket(
            market_slug="btc-15m",
            event_slug="bitcoin-event",
            question="BTC 15m",
            active=True,
            closed=False,
            enable_order_book=True,
            condition_id=CONDITION_ID,
            token_ids=[TOKEN_ID],
            outcomes=["Yes"],
            min_tick=0.01,
            min_order_size=1,
        )
        self.book = book or NormalizedBook(
            token_id=TOKEN_ID,
            bids=[NormalizedBookLevel(price="0.54", size="50")],
            asks=[NormalizedBookLevel(price="0.56", size="50")],
            tick_size="0.01",
            min_order_size="1",
        )
        self.midpoint = midpoint
        self.spread = spread

    def resolve_market(self, market_ref: str) -> NormalizedMarket | None:
        _ = market_ref
        return self.market

    def load_public_book_context(
        self,
        token_id: str,
    ) -> tuple[NormalizedBook, str | None, str | None]:
        assert token_id == TOKEN_ID
        return self.book, self.midpoint, self.spread


class FakeOrderLifecycleService:
    def __init__(
        self,
        *,
        balance_status: str = "pass",
        allowance_status: str = "pass",
    ) -> None:
        self.balance_status = balance_status
        self.allowance_status = allowance_status
        self.post_calls: list[dict[str, object]] = []

    def balance_allowance_reasons(
        self,
        *,
        token_id: str | None,
        side: str,
        price: str,
        size: str,
    ) -> list[ExecutionReasonBlock]:
        _ = token_id
        _ = side
        _ = price
        _ = size
        return [
            ExecutionReasonBlock(
                section="balance",
                status=self.balance_status,
                message="Balance covers required amount."
                if self.balance_status == "pass"
                else "Insufficient collateral balance.",
            ),
            ExecutionReasonBlock(
                section="allowance",
                status=self.allowance_status,
                message="Allowance covers required amount."
                if self.allowance_status == "pass"
                else "Insufficient collateral allowance.",
            ),
        ]

    def post(
        self,
        *,
        market_ref: str,
        outcome: str,
        side: str,
        price: str,
        size: str,
        order_type: str,
        post_only: bool,
        live: bool,
        confirm: bool,
    ) -> PostOrderResponse:
        self.post_calls.append(
            {
                "market_ref": market_ref,
                "outcome": outcome,
                "side": side,
                "price": price,
                "size": size,
                "order_type": order_type,
                "post_only": post_only,
                "live": live,
                "confirm": confirm,
            }
        )
        return PostOrderResponse(
            request=PostOrderRequest(
                market_ref=market_ref,
                outcome=outcome,
                side=side,
                price=price,
                size=size,
                order_type=order_type,
                post_only=post_only,
                live=live,
                confirm=confirm,
            ),
            auth=AuthContext(
                signer_address="0x" + ("3" * 40),
                funder_address=None,
                signature_type=0,
                signature_type_name="EOA",
                clob_host="https://clob.polymarket.com",
                chain_id=137,
                private_key_present=True,
                api_key_derivation_possible=True,
            ),
            mode="live" if live else "paper",
            decision="POSTED" if live else "WOULD_POST",
            plan_id="plan-123",
            result_id="result-123",
            live_response={"order": {"order_id": "order-123"}} if live else None,
            post_context=DryRunPostContext(
                order_type=order_type.upper(),
                post_only=post_only,
                submit_mode="live" if live else "paper",
            ),
            reasons=[
                ExecutionReasonBlock(
                    section="local_signing",
                    status="pass",
                    message="Order was built and signed locally without submission.",
                )
            ],
        )


def _fixture(
    tmp_path,
    *,
    dry_run_service: FakeDryRunService | None = None,
    order_lifecycle: FakeOrderLifecycleService | None = None,
) -> DispatchFixture:
    registry = StrategyRegistryService(path=tmp_path / "strategies.json")
    state = StrategyStateService(
        intents_path=tmp_path / "strategy-intents.json",
        decisions_path=tmp_path / "strategy-decisions.json",
        execution_links_path=tmp_path / "strategy-execution-links.json",
        dispatch_results_path=tmp_path / "strategy-dispatch-results.json",
    )
    wallet_state = WalletPipelineStateService(
        events_path=tmp_path / "wallet-events.json",
        signals_path=tmp_path / "wallet-signals.json",
        shadow_runs_path=tmp_path / "wallet-shadow-runs.json",
    )
    risk_state = RiskStateService(policies_path=tmp_path / "risk-policies.json")
    risk_service = RiskPolicyService(state=risk_state, registry=registry)
    service = StrategyDispatchService(
        state=state,
        wallet_state=wallet_state,
        risk_service=risk_service,
        dry_run_service=dry_run_service or FakeDryRunService(),
        order_lifecycle=order_lifecycle or FakeOrderLifecycleService(),
    )
    return DispatchFixture(
        service=service,
        state=state,
        wallet_state=wallet_state,
        risk_state=risk_state,
    )


def _append_wallet_shadow_intent(
    fixture: DispatchFixture,
    *,
    intent_id: str = "intent-1",
    strategy_name: str = "wallet_shadow_copy",
    strategy_type: str = "wallet_shadow_copy",
    approved: bool = True,
    source_price: str = "0.55",
    current_price: str = "0.55",
    simulated_size_usdc: str = "25",
) -> StrategyCandidateIntent:
    run_at = (
        f"2026-03-19T00:00:0{intent_id[-1]}Z"
        if intent_id[-1].isdigit()
        else "2026-03-19T00:00:00Z"
    )
    candidate = WalletShadowCandidateIntent(
        source_wallet="0x" + ("1" * 40),
        market_slug="btc-15m",
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        side="BUY",
        outcome="Yes",
        source_price=source_price,
        current_price=current_price,
        drift="1.0",
        spread="0.02",
        spread_pct="3.64",
        simulated_size_usdc=simulated_size_usdc,
        decision="WOULD_COPY",
        classification="new_entry",
        transaction_hash="0xhash",
        timestamp=1710806400,
        dedupe_key=f"dedupe-{intent_id}",
    )
    fixture.wallet_state.append_shadow_run(
        WalletShadowRun(
            source_wallet=candidate.source_wallet,
            run_at=run_at,
            parameters=WalletShadowRunParameters(
                fixed_size_usdc=simulated_size_usdc,
                max_drift_pct="5",
                max_spread_pct="5",
                entry_only=True,
                limit=20,
            ),
            candidate_intents=[candidate],
        )
    )
    intent = StrategyCandidateIntent(
        intent_id=intent_id,
        strategy_name=strategy_name,
        strategy_type=strategy_type,
        source_kind="wallet_shadow",
        market_slug="btc-15m",
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        side="BUY",
        outcome="Yes",
        decision="WAIT",
        reason_blocks=[],
        created_at="2026-03-19T00:00:00Z",
        source_refs=[
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
        ],
    )
    fixture.state.append_intents([intent])
    if approved:
        fixture.state.append_decision(
            StrategyDecisionRecord(
                intent_id=intent.intent_id,
                decision="APPROVE",
                reason="manual operator approval",
                decided_at="2026-03-19T00:01:00Z",
            )
        )
    return intent


def _write_wallet_policy(fixture: DispatchFixture, **overrides) -> None:
    service = RiskPolicyService(
        state=fixture.risk_state,
        registry=StrategyRegistryService(
            path=fixture.state.intents_path.parent / "strategies.json"
        ),
    )
    shown = service.show()
    strategies = []
    for policy in shown.strategies:
        if policy.strategy_name == "wallet_shadow_copy":
            strategies.append(policy.model_copy(update=overrides))
        else:
            strategies.append(policy)
    fixture.risk_state.write(
        RiskPoliciesFile(
            default_policy=shown.default_policy,
            strategies=strategies,
        )
    )


def test_dispatch_requires_manual_approval(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture, approved=False)

    result = fixture.service.dispatch_intent("intent-1")

    assert result.execution.decision == "SKIP"
    assert result.execution.risk_checks[0].section == "approval_gate"
    assert fixture.state.list_dispatch_results()[0].decision == "SKIP"


def test_paper_dispatch_persists_link_and_result(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture)

    result = fixture.service.dispatch_intent("intent-1")

    assert result.execution.decision == "WOULD_POST"
    assert result.execution.execution_request is not None
    assert result.execution.execution_request.price == "0.56"
    assert result.execution.execution_request.size == "44.642857"
    assert len(fixture.state.list_execution_links()) == 1
    assert len(fixture.state.list_dispatch_results()) == 1


def test_non_wallet_strategy_returns_dispatch_disabled_skip(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    intent = StrategyCandidateIntent(
        intent_id="intent-market-1",
        strategy_name="market_watch_reversion",
        strategy_type="market_watch_reversion",
        source_kind="market_snapshot",
        market_slug="btc-15m",
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        side=None,
        outcome="Yes",
        decision="WAIT",
        reason_blocks=[],
        created_at="2026-03-19T00:00:00Z",
        source_refs=[],
    )
    fixture.state.append_intents([intent])
    fixture.state.append_decision(
        StrategyDecisionRecord(
            intent_id=intent.intent_id,
            decision="APPROVE",
            reason="manual operator approval",
            decided_at="2026-03-19T00:01:00Z",
        )
    )

    result = fixture.service.dispatch_intent(intent.intent_id)

    assert result.execution.decision == "SKIP"
    assert result.execution.risk_checks[0].section == "strategy_dispatch"


def test_prior_non_skip_dispatch_blocks_duplicate(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture)

    first = fixture.service.dispatch_intent("intent-1")
    second = fixture.service.dispatch_intent("intent-1")

    assert first.execution.decision == "WOULD_POST"
    assert second.execution.decision == "SKIP"
    assert second.execution.risk_checks[0].section == "dispatch_gate"
    assert len(fixture.state.list_dispatch_results()) == 2


def test_prior_skip_dispatch_can_retry_explicitly(tmp_path) -> None:
    failing = _fixture(
        tmp_path,
        order_lifecycle=FakeOrderLifecycleService(balance_status="fail"),
    )
    _append_wallet_shadow_intent(failing)

    first = failing.service.dispatch_intent("intent-1")
    assert first.execution.decision == "SKIP"

    retried = _fixture(tmp_path)
    second = retried.service.dispatch_intent("intent-1")

    assert second.execution.decision == "WOULD_POST"
    assert len(retried.state.list_dispatch_results()) == 2


def test_dispatch_respects_drift_threshold(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture, source_price="0.40")
    _write_wallet_policy(fixture, max_drift_pct="1")

    result = fixture.service.dispatch_intent("intent-1")

    assert result.execution.decision == "SKIP"
    assert any(
        item.section == "drift_threshold" and item.status == "fail"
        for item in result.execution.risk_checks
    )


def test_dispatch_respects_spread_threshold(tmp_path) -> None:
    fixture = _fixture(
        tmp_path,
        dry_run_service=FakeDryRunService(spread="0.10"),
    )
    _append_wallet_shadow_intent(fixture)
    _write_wallet_policy(fixture, max_spread_pct="5")

    result = fixture.service.dispatch_intent("intent-1")

    assert result.execution.decision == "SKIP"
    assert any(
        item.section == "spread_threshold" and item.status == "fail"
        for item in result.execution.risk_checks
    )


def test_dispatch_respects_max_order_notional(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture, simulated_size_usdc="25")
    _write_wallet_policy(fixture, max_size_usdc_per_order="10")

    result = fixture.service.dispatch_intent("intent-1")

    assert result.execution.decision == "SKIP"
    assert any(
        item.section == "max_size_per_order" and item.status == "fail"
        for item in result.execution.risk_checks
    )


def test_dispatch_respects_max_market_exposure(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture, intent_id="intent-1")
    first = fixture.service.dispatch_intent("intent-1")
    assert first.execution.decision == "WOULD_POST"

    _append_wallet_shadow_intent(fixture, intent_id="intent-2")
    _write_wallet_policy(fixture, max_exposure_usdc_per_market="40")

    second = fixture.service.dispatch_intent("intent-2")

    assert second.execution.decision == "SKIP"
    assert any(
        item.section == "max_exposure_per_market" and item.status == "fail"
        for item in second.execution.risk_checks
    )


def test_dispatch_respects_max_strategy_exposure(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture, intent_id="intent-1")
    first = fixture.service.dispatch_intent("intent-1")
    assert first.execution.decision == "WOULD_POST"

    _append_wallet_shadow_intent(fixture, intent_id="intent-2")
    _write_wallet_policy(fixture, max_exposure_usdc_per_strategy="40")

    second = fixture.service.dispatch_intent("intent-2")

    assert second.execution.decision == "SKIP"
    assert any(
        item.section == "max_exposure_per_strategy" and item.status == "fail"
        for item in second.execution.risk_checks
    )


def test_dispatch_respects_balance_and_allowance_readiness(tmp_path) -> None:
    fixture = _fixture(
        tmp_path,
        order_lifecycle=FakeOrderLifecycleService(
            balance_status="fail",
            allowance_status="fail",
        ),
    )
    _append_wallet_shadow_intent(fixture)

    result = fixture.service.dispatch_intent("intent-1")

    assert result.execution.decision == "SKIP"
    assert any(
        item.section == "balance" and item.status == "fail"
        for item in result.execution.risk_checks
    )
    assert any(
        item.section == "allowance" and item.status == "fail"
        for item in result.execution.risk_checks
    )


def test_dispatch_pending_and_get_execution(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture, intent_id="intent-1")
    _append_wallet_shadow_intent(fixture, intent_id="intent-2")

    pending = fixture.service.dispatch_pending(limit=1)
    execution_id = pending.items[0].execution.execution_id
    detail = fixture.service.get_execution(execution_id)

    assert pending.total_candidates == 1
    assert pending.total_dispatched == 1
    assert detail.execution.execution_id == execution_id
    assert detail.link.intent_id == pending.items[0].intent.intent.intent_id


def test_list_executions_returns_newest_first(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    _append_wallet_shadow_intent(fixture, intent_id="intent-1")
    _append_wallet_shadow_intent(fixture, intent_id="intent-2")

    fixture.service.dispatch_intent("intent-1")
    fixture.service.dispatch_intent("intent-2")
    listed = fixture.service.list_executions(limit=10)

    assert listed.total == 2
    assert [item.intent_id for item in listed.items] == ["intent-2", "intent-1"]
