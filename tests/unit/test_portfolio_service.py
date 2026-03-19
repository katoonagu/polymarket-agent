"""Unit tests for portfolio snapshot assembly and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pm.auth.models import AuthContext
from pm.data import DataClientError
from pm.data.models import (
    ClosedPositionsResponse,
    NormalizedClosedPosition,
    NormalizedCurrentPosition,
    NormalizedHoldingsValue,
    PositionsResponse,
)
from pm.execution import (
    CapturedExecutionEvent,
    ExecutionOrderResultRecord,
    ExecutionReconciliationItem,
    ExecutionReconciliationResponse,
    ExecutionReconciliationSummary,
    ExecutionStateService,
)
from pm.portfolio import (
    PortfolioNotFoundError,
    PortfolioService,
    PortfolioStateError,
    PortfolioStateService,
    PortfolioValidationError,
)
from pm.strategy import StrategyStateService
from pm.strategy.models import (
    StrategyDispatchResultRecord,
    StrategyExecutionLinkRecord,
    StrategyExecutionRequest,
)
from pm.stream.models import StreamSectionError

ADDRESS = "0x" + ("1" * 40)
FUNDER = "0x" + ("2" * 40)
SIGNER = "0x" + ("3" * 40)
CONDITION_A = "0x" + ("a" * 64)
CONDITION_B = "0x" + ("b" * 64)
CONDITION_C = "0x" + ("c" * 64)
TOKEN_YES = "100"
TOKEN_NO = "101"
TOKEN_ALT = "200"


@dataclass
class PortfolioFixture:
    service: PortfolioService
    portfolio_state: PortfolioStateService
    strategy_state: StrategyStateService
    execution_state: ExecutionStateService


class FakeAuthService:
    def __init__(
        self,
        *,
        funder_address: str | None = FUNDER,
        signer_address: str | None = SIGNER,
    ) -> None:
        self._auth = AuthContext(
            signer_address=signer_address,
            funder_address=funder_address,
            signature_type=0,
            signature_type_name="EOA",
            clob_host="https://clob.polymarket.com",
            chain_id=137,
            private_key_present=bool(signer_address),
            api_key_derivation_possible=bool(signer_address),
        )

    def show(self) -> object:
        return type("AuthShow", (), {"auth": self._auth})()


class FakeWatchService:
    def __init__(
        self,
        response: ExecutionReconciliationResponse | None = None,
    ) -> None:
        self._response = response or ExecutionReconciliationResponse(
            reconciliation_id="execution_reconciliation_1",
            created_at="2026-03-19T00:20:00Z",
            summary=ExecutionReconciliationSummary(),
            items=[],
            errors=[],
        )

    def reconcile(self) -> ExecutionReconciliationResponse:
        return self._response


def make_data_client(
    *,
    current_items: list[NormalizedCurrentPosition] | None = None,
    closed_items: list[NormalizedClosedPosition] | None = None,
    holdings_value: str | None = "100",
    current_error: Exception | None = None,
    closed_error: Exception | None = None,
    holdings_error: Exception | None = None,
) -> type[object]:
    class FakeDataClient:
        def __enter__(self) -> FakeDataClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def get_current_positions(self, user: str) -> PositionsResponse:
            if current_error is not None:
                raise current_error
            items = list(current_items or [])
            return PositionsResponse(user=user, items=items, total=len(items))

        def get_closed_positions(self, user: str) -> ClosedPositionsResponse:
            if closed_error is not None:
                raise closed_error
            items = list(closed_items or [])
            return ClosedPositionsResponse(user=user, items=items, total=len(items))

        def get_holdings_value(self, user: str) -> NormalizedHoldingsValue:
            if holdings_error is not None:
                raise holdings_error
            return NormalizedHoldingsValue(user=user, value=holdings_value or "0")

    return FakeDataClient


def _fixture(
    tmp_path: Path,
    *,
    auth_service: FakeAuthService | None = None,
    data_client_cls: type[object] | None = None,
    watch_service: FakeWatchService | None = None,
) -> PortfolioFixture:
    strategy_state = StrategyStateService(
        intents_path=tmp_path / "strategy-intents.json",
        decisions_path=tmp_path / "strategy-decisions.json",
        execution_links_path=tmp_path / "strategy-execution-links.json",
        dispatch_results_path=tmp_path / "strategy-dispatch-results.json",
    )
    execution_state = ExecutionStateService(
        approval_plans_path=tmp_path / "approval-plans.json",
        approval_results_path=tmp_path / "approval-results.json",
        order_plans_path=tmp_path / "execution-order-plans.json",
        order_results_path=tmp_path / "execution-order-results.json",
        events_path=tmp_path / "execution-events.jsonl",
        reconciliations_path=tmp_path / "execution-reconciliations.json",
    )
    portfolio_state = PortfolioStateService(
        snapshots_path=tmp_path / "portfolio-snapshots.json",
        reconciliations_path=tmp_path / "portfolio-reconciliations.json",
    )
    service = PortfolioService(
        auth_service=auth_service or FakeAuthService(),
        data_client_cls=data_client_cls or make_data_client(),
        strategy_state=strategy_state,
        execution_state=execution_state,
        portfolio_state=portfolio_state,
        watch_service=watch_service or FakeWatchService(),
    )
    return PortfolioFixture(
        service=service,
        portfolio_state=portfolio_state,
        strategy_state=strategy_state,
        execution_state=execution_state,
    )


def _append_live_posted_pair(
    fixture: PortfolioFixture,
    *,
    execution_id: str,
    strategy_name: str,
    strategy_type: str,
    condition_id: str,
    token_id: str,
    result_id: str | None = None,
) -> None:
    fixture.strategy_state.append_execution_link(
        StrategyExecutionLinkRecord(
            execution_id=execution_id,
            intent_id=f"intent-{execution_id}",
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            mode="live",
            created_at="2026-03-19T00:10:00Z",
            execution_plan_id=f"plan-{execution_id}",
            execution_result_id=result_id,
            order_id=f"order-{execution_id}",
        )
    )
    fixture.strategy_state.append_dispatch_result(
        StrategyDispatchResultRecord(
            execution_id=execution_id,
            intent_id=f"intent-{execution_id}",
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            mode="live",
            decision="POSTED",
            created_at="2026-03-19T00:10:00Z",
            market_slug=f"market-{condition_id[-4:]}",
            condition_id=condition_id,
            token_id=token_id,
            outcome="Yes",
            side="BUY",
            execution_request=StrategyExecutionRequest(
                market_ref=condition_id,
                market_slug=f"market-{condition_id[-4:]}",
                condition_id=condition_id,
                token_id=token_id,
                outcome="yes",
                side="buy",
                price="0.55",
                size="10",
                notional_usdc="5.5",
            ),
            execution_plan_id=f"plan-{execution_id}",
            execution_result_id=result_id,
            order_id=f"order-{execution_id}",
        )
    )
    if result_id is not None:
        fixture.execution_state.append_order_result(
            ExecutionOrderResultRecord(
                result_id=result_id,
                plan_id=f"plan-{execution_id}",
                action="post",
                mode="live",
                decision="POSTED",
                created_at="2026-03-19T00:10:10Z",
                response={"order_id": f"order-{execution_id}"},
            )
        )


def test_summary_prefers_funder_address(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        auth_service=FakeAuthService(funder_address=FUNDER, signer_address=SIGNER),
    )

    result = fixture.service.summary()

    assert result.account_address == FUNDER


def test_summary_uses_signer_when_funder_missing(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        auth_service=FakeAuthService(funder_address=None, signer_address=SIGNER),
    )

    result = fixture.service.summary()

    assert result.account_address == SIGNER


def test_missing_account_context_raises_validation_error(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        auth_service=FakeAuthService(funder_address=None, signer_address=None),
    )

    with pytest.raises(PortfolioValidationError):
        fixture.service.summary()


def test_build_snapshot_aggregates_exposure_pnl_and_linkage(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        data_client_cls=make_data_client(
            current_items=[
                NormalizedCurrentPosition(
                    user=ADDRESS,
                    market_slug="btc-market",
                    condition_id=CONDITION_A,
                    token_id=TOKEN_YES,
                    outcome="Yes",
                    size="10",
                    current_value="30",
                    cash_pnl="5",
                ),
                NormalizedCurrentPosition(
                    user=ADDRESS,
                    market_slug="btc-market",
                    condition_id=CONDITION_A,
                    token_id=TOKEN_NO,
                    outcome="No",
                    size="6",
                    current_value="10",
                    cash_pnl="-1",
                ),
            ],
            closed_items=[
                NormalizedClosedPosition(
                    user=ADDRESS,
                    market_slug="btc-market",
                    condition_id=CONDITION_A,
                    token_id=TOKEN_YES,
                    outcome="Yes",
                    realized_pnl="7",
                    timestamp=1710806400,
                )
            ],
            holdings_value="120",
        ),
    )
    _append_live_posted_pair(
        fixture,
        execution_id="exec-linked",
        strategy_name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        condition_id=CONDITION_A,
        token_id=TOKEN_YES,
        result_id="result-linked",
    )

    snapshot = fixture.service.build_snapshot()

    assert snapshot.summary.holdings_value == "120"
    assert snapshot.summary.realized_pnl_total == "7"
    assert snapshot.summary.unrealized_pnl_total == "4"
    assert snapshot.summary.total_pnl == "11"
    assert snapshot.summary.gross_exposure == "40"
    assert snapshot.summary.net_exposure == "20"
    assert snapshot.summary.linked_current_positions_count == 1
    assert snapshot.summary.unlinked_current_positions_count == 1
    assert snapshot.summary.linked_closed_positions_count == 1
    assert snapshot.per_market[0].gross_exposure == "40"
    assert snapshot.per_market[0].net_exposure == "20"
    assert len(snapshot.per_strategy) == 1
    assert snapshot.per_strategy[0].strategy_name == "wallet_shadow_copy"
    assert snapshot.per_strategy[0].gross_exposure == "30"
    assert snapshot.per_strategy[0].total_pnl == "12"
    assert len(fixture.portfolio_state.list_snapshots()) == 1


def test_snapshot_keeps_partial_data_api_errors(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        data_client_cls=make_data_client(
            current_items=[
                NormalizedCurrentPosition(
                    user=ADDRESS,
                    market_slug="btc-market",
                    condition_id=CONDITION_A,
                    token_id=TOKEN_YES,
                    outcome="Yes",
                    current_value="12",
                    cash_pnl="2",
                )
            ],
            closed_items=[],
            holdings_error=DataClientError("holdings unavailable"),
        ),
    )

    snapshot = fixture.service.build_snapshot()

    assert snapshot.summary.gross_exposure == "12"
    assert snapshot.errors[0].section == "holdings_value"
    assert snapshot.errors[0].code == "request_failed"


def test_ambiguous_strategy_links_are_reported_and_not_back_allocated(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        data_client_cls=make_data_client(
            current_items=[
                NormalizedCurrentPosition(
                    user=ADDRESS,
                    market_slug="eth-market",
                    condition_id=CONDITION_B,
                    token_id=TOKEN_ALT,
                    outcome="Yes",
                    current_value="15",
                    cash_pnl="1",
                )
            ],
            closed_items=[],
            holdings_value="15",
        ),
    )
    _append_live_posted_pair(
        fixture,
        execution_id="exec-1",
        strategy_name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        condition_id=CONDITION_B,
        token_id=TOKEN_ALT,
        result_id="result-1",
    )
    _append_live_posted_pair(
        fixture,
        execution_id="exec-2",
        strategy_name="market_watch_reversion",
        strategy_type="market_watch_reversion",
        condition_id=CONDITION_B,
        token_id=TOKEN_ALT,
        result_id="result-2",
    )

    snapshot = fixture.service.build_snapshot()

    assert snapshot.current_positions[0].attribution.status == "ambiguous"
    assert snapshot.summary.ambiguous_current_positions_count == 1
    assert snapshot.per_strategy == []


def test_market_view_not_found_raises(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    with pytest.raises(PortfolioNotFoundError):
        fixture.service.market(market=CONDITION_A)


def test_reconcile_reports_discrepancies_and_persists(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        data_client_cls=make_data_client(
            current_items=[
                NormalizedCurrentPosition(
                    user=ADDRESS,
                    market_slug="btc-market",
                    condition_id=CONDITION_A,
                    token_id=TOKEN_YES,
                    outcome="Yes",
                    current_value="9",
                    cash_pnl="1",
                ),
                NormalizedCurrentPosition(
                    user=ADDRESS,
                    market_slug="eth-market",
                    condition_id=CONDITION_B,
                    token_id=TOKEN_ALT,
                    outcome="Yes",
                    current_value="15",
                    cash_pnl="2",
                ),
            ],
            closed_items=[],
            holdings_value="24",
        ),
        watch_service=FakeWatchService(
            ExecutionReconciliationResponse(
                reconciliation_id="execution_reconciliation_1",
                created_at="2026-03-19T00:20:00Z",
                summary=ExecutionReconciliationSummary(mismatch=1, total_orders=1),
                items=[
                    ExecutionReconciliationItem(
                        order_id="order-mismatch",
                        condition_id=CONDITION_A,
                        latest_event=CapturedExecutionEvent(
                            session_id="session-1",
                            source="polymarket_user_ws",
                            captured_at="2026-03-19T00:19:00Z",
                            condition_id=CONDITION_A,
                            order_id="order-mismatch",
                            asset_id=TOKEN_YES,
                            event_type="UPDATE",
                        ),
                        latest_event_type="UPDATE",
                        latest_trade_status=None,
                        classification="mismatch",
                        message="REST and websocket state diverged.",
                    )
                ],
                errors=[
                    StreamSectionError(
                        section="order_get",
                        code="request_failed",
                        message="temporary upstream issue",
                    )
                ],
            )
        ),
    )
    _append_live_posted_pair(
        fixture,
        execution_id="exec-ambig-1",
        strategy_name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        condition_id=CONDITION_B,
        token_id=TOKEN_ALT,
        result_id="result-ambig-1",
    )
    _append_live_posted_pair(
        fixture,
        execution_id="exec-ambig-2",
        strategy_name="market_watch_reversion",
        strategy_type="market_watch_reversion",
        condition_id=CONDITION_B,
        token_id=TOKEN_ALT,
        result_id="result-ambig-2",
    )
    _append_live_posted_pair(
        fixture,
        execution_id="exec-missing",
        strategy_name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        condition_id=CONDITION_C,
        token_id=TOKEN_YES,
        result_id="result-missing",
    )

    result = fixture.service.reconcile()

    kinds = [item.kind for item in result.discrepancies]
    assert result.summary.health == "mismatch"
    assert "execution_state_mismatch" in kinds
    assert "unlinked_current_position" in kinds
    assert "ambiguous_strategy_link" in kinds
    assert "linked_execution_missing_from_positions" in kinds
    assert result.errors[-1].section == "execution_reconcile.order_get"
    assert len(fixture.portfolio_state.list_reconciliations()) == 1


def test_portfolio_state_invalid_documents_raise(tmp_path: Path) -> None:
    snapshots_path = tmp_path / "portfolio-snapshots.json"
    reconciliations_path = tmp_path / "portfolio-reconciliations.json"
    snapshots_path.write_text('{"version":1,"snapshots":"bad"}\n', encoding="utf-8")
    reconciliations_path.write_text(
        '{"version":1,"reconciliations":"bad"}\n',
        encoding="utf-8",
    )
    state = PortfolioStateService(
        snapshots_path=snapshots_path,
        reconciliations_path=reconciliations_path,
    )

    with pytest.raises(PortfolioStateError):
        state.list_snapshots()
    with pytest.raises(PortfolioStateError):
        state.list_reconciliations()
