"""CLI tests for portfolio truth and reconciliation commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.data.models import NormalizedClosedPosition, NormalizedCurrentPosition
from pm.portfolio.models import (
    PortfolioAttribution,
    PortfolioClosedPositionItem,
    PortfolioClosedResponse,
    PortfolioCurrentPositionItem,
    PortfolioDiscrepancy,
    PortfolioExposureResponse,
    PortfolioMarketResponse,
    PortfolioMarketSummary,
    PortfolioPnlResponse,
    PortfolioPositionsResponse,
    PortfolioReconciliationResponse,
    PortfolioReconciliationSummary,
    PortfolioSectionError,
    PortfolioSnapshotSummary,
    PortfolioStrategySummary,
    PortfolioSummaryResponse,
)

runner = CliRunner()
CONDITION_ID = "0x" + ("a" * 64)
TOKEN_ID = "100"


class FakePortfolioService:
    def summary(self) -> PortfolioSummaryResponse:
        return PortfolioSummaryResponse(
            account_address="0x" + ("1" * 40),
            snapshot_id="portfolio_snapshot_1",
            created_at="2026-03-19T00:00:00Z",
            summary=_summary(),
            errors=[],
        )

    def positions(self) -> PortfolioPositionsResponse:
        return PortfolioPositionsResponse(
            account_address="0x" + ("1" * 40),
            snapshot_id="portfolio_snapshot_1",
            created_at="2026-03-19T00:00:00Z",
            summary=_summary(),
            items=[
                PortfolioCurrentPositionItem(
                    position=NormalizedCurrentPosition(
                        user="0x" + ("1" * 40),
                        market_slug="btc-market",
                        condition_id=CONDITION_ID,
                        token_id=TOKEN_ID,
                        outcome="Yes",
                        size="10",
                        current_value="30",
                        cash_pnl="5",
                    ),
                    attribution=PortfolioAttribution(
                        status="linked",
                        strategy_name="wallet_shadow_copy",
                        strategy_names=["wallet_shadow_copy"],
                        execution_ids=["strategy_exec_1"],
                    ),
                )
            ],
            total=1,
            errors=[],
        )

    def closed(self, *, limit: int = 20) -> PortfolioClosedResponse:
        return PortfolioClosedResponse(
            account_address="0x" + ("1" * 40),
            snapshot_id="portfolio_snapshot_1",
            created_at="2026-03-19T00:00:00Z",
            summary=_summary(),
            items=[
                PortfolioClosedPositionItem(
                    position=NormalizedClosedPosition(
                        user="0x" + ("1" * 40),
                        market_slug="btc-market",
                        condition_id=CONDITION_ID,
                        token_id=TOKEN_ID,
                        outcome="Yes",
                        realized_pnl="7",
                        timestamp=1710806400,
                    ),
                    attribution=PortfolioAttribution(
                        status="linked",
                        strategy_name="wallet_shadow_copy",
                        strategy_names=["wallet_shadow_copy"],
                        execution_ids=["strategy_exec_1"],
                    ),
                )
            ],
            total=1,
            limit=limit,
            errors=[],
        )

    def market(self, *, market: str) -> PortfolioMarketResponse:
        return PortfolioMarketResponse(
            account_address="0x" + ("1" * 40),
            snapshot_id="portfolio_snapshot_1",
            created_at="2026-03-19T00:00:00Z",
            market=PortfolioMarketSummary(
                condition_id=market,
                market_slug="btc-market",
                gross_exposure="30",
                net_exposure="30",
                realized_pnl="7",
                unrealized_pnl="5",
                total_pnl="12",
                current_positions_count=1,
                closed_positions_count=1,
            ),
            current_positions=self.positions().items,
            closed_positions=self.closed().items,
            errors=[],
        )

    def exposure(self) -> PortfolioExposureResponse:
        return PortfolioExposureResponse(
            account_address="0x" + ("1" * 40),
            snapshot_id="portfolio_snapshot_1",
            created_at="2026-03-19T00:00:00Z",
            summary=_summary(),
            per_market=[
                PortfolioMarketSummary(
                    condition_id=CONDITION_ID,
                    market_slug="btc-market",
                    gross_exposure="30",
                    net_exposure="30",
                    realized_pnl="7",
                    unrealized_pnl="5",
                    total_pnl="12",
                    current_positions_count=1,
                    closed_positions_count=1,
                )
            ],
            per_strategy=[
                PortfolioStrategySummary(
                    strategy_name="wallet_shadow_copy",
                    strategy_type="wallet_shadow_copy",
                    gross_exposure="30",
                    net_exposure="30",
                    realized_pnl="7",
                    unrealized_pnl="5",
                    total_pnl="12",
                    current_positions_count=1,
                    closed_positions_count=1,
                    execution_ids=["strategy_exec_1"],
                )
            ],
            errors=[],
        )

    def pnl(self) -> PortfolioPnlResponse:
        exposure = self.exposure()
        return PortfolioPnlResponse(
            account_address=exposure.account_address,
            snapshot_id=exposure.snapshot_id,
            created_at=exposure.created_at,
            summary=exposure.summary,
            per_market=exposure.per_market,
            per_strategy=exposure.per_strategy,
            errors=[],
        )

    def reconcile(self) -> PortfolioReconciliationResponse:
        return PortfolioReconciliationResponse(
            reconciliation_id="portfolio_reconciliation_1",
            snapshot_id="portfolio_snapshot_1",
            execution_reconciliation_id="execution_reconciliation_1",
            account_address="0x" + ("1" * 40),
            created_at="2026-03-19T00:10:00Z",
            summary=PortfolioReconciliationSummary(
                health="warning",
                discrepancy_count=1,
                unlinked_current_position_count=1,
            ),
            discrepancies=[
                PortfolioDiscrepancy(
                    kind="unlinked_current_position",
                    severity="medium",
                    condition_id=CONDITION_ID,
                    token_id=TOKEN_ID,
                    message="Current position has no explicit local linkage.",
                )
            ],
            errors=[
                PortfolioSectionError(
                    section="execution_reconcile.order_get",
                    code="request_failed",
                    message="temporary upstream issue",
                )
            ],
        )


def test_root_help_lists_portfolio_namespace() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "portfolio" in result.stdout


def test_portfolio_help_lists_commands() -> None:
    result = runner.invoke(app, ["portfolio", "--help"])

    assert result.exit_code == 0
    assert "summary" in result.stdout
    assert "positions" in result.stdout
    assert "closed" in result.stdout
    assert "market" in result.stdout
    assert "exposure" in result.stdout
    assert "pnl" in result.stdout
    assert "reconcile" in result.stdout


def test_portfolio_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.portfolio.PortfolioService", FakePortfolioService)

    summary_result = runner.invoke(app, ["portfolio", "summary", "--json"])
    positions_result = runner.invoke(app, ["portfolio", "positions", "--json"])
    closed_result = runner.invoke(app, ["portfolio", "closed", "--limit", "5", "--json"])
    market_result = runner.invoke(
        app,
        ["portfolio", "market", "--market", CONDITION_ID, "--json"],
    )
    exposure_result = runner.invoke(app, ["portfolio", "exposure", "--json"])
    pnl_result = runner.invoke(app, ["portfolio", "pnl", "--json"])
    reconcile_result = runner.invoke(app, ["portfolio", "reconcile", "--json"])

    assert json.loads(summary_result.stdout)["summary"]["gross_exposure"] == "30"
    assert json.loads(positions_result.stdout)["items"][0]["attribution"]["status"] == "linked"
    assert json.loads(closed_result.stdout)["limit"] == 5
    assert json.loads(market_result.stdout)["market"]["condition_id"] == CONDITION_ID
    assert json.loads(exposure_result.stdout)["per_market"][0]["gross_exposure"] == "30"
    assert json.loads(pnl_result.stdout)["summary"]["total_pnl"] == "12"
    assert json.loads(reconcile_result.stdout)["summary"]["health"] == "warning"


def test_portfolio_root_output_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.portfolio.PortfolioService", FakePortfolioService)

    result = runner.invoke(app, ["--output", "json", "portfolio", "summary"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["snapshot_id"] == "portfolio_snapshot_1"


def test_portfolio_human_output_contains_sections(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.portfolio.PortfolioService", FakePortfolioService)

    positions_result = runner.invoke(app, ["portfolio", "positions"])
    exposure_result = runner.invoke(app, ["portfolio", "exposure"])
    reconcile_result = runner.invoke(app, ["portfolio", "reconcile"])

    assert positions_result.exit_code == 0
    assert "Current Positions" in positions_result.stdout
    assert exposure_result.exit_code == 0
    assert "Per-Market Exposure" in exposure_result.stdout
    assert reconcile_result.exit_code == 0
    assert "Reconciliation Discrepancies" in reconcile_result.stdout


def _summary() -> PortfolioSnapshotSummary:
    return PortfolioSnapshotSummary(
        holdings_value="120",
        realized_pnl_total="7",
        unrealized_pnl_total="5",
        total_pnl="12",
        gross_exposure="30",
        net_exposure="30",
        current_positions_count=1,
        closed_positions_count=1,
        linked_current_positions_count=1,
        unlinked_current_positions_count=0,
        ambiguous_current_positions_count=0,
        linked_closed_positions_count=1,
        unlinked_closed_positions_count=0,
        ambiguous_closed_positions_count=0,
    )
