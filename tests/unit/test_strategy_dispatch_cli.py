"""CLI tests for guarded strategy dispatch and risk policy commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.risk import RiskInitDefaultsResponse, RiskPolicy, RiskShowResponse
from pm.strategy import (
    StrategyCandidateIntent,
    StrategyDecisionRecord,
    StrategyDispatchPendingResponse,
    StrategyDispatchResponse,
    StrategyDispatchResultRecord,
    StrategyExecutionDetailResponse,
    StrategyExecutionLinkRecord,
    StrategyExecutionRequest,
    StrategyExecutionsResponse,
    StrategyIntentView,
    StrategyReasonBlock,
)

runner = CliRunner()


def _intent_view() -> StrategyIntentView:
    intent = StrategyCandidateIntent(
        intent_id="intent-123",
        strategy_name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        source_kind="wallet_shadow",
        market_slug="btc-15m",
        condition_id="0x" + ("a" * 64),
        token_id="100",
        side="BUY",
        outcome="Yes",
        decision="WAIT",
        reason_blocks=[],
        created_at="2026-03-19T00:00:00Z",
        source_refs=[],
    )
    latest = StrategyDecisionRecord(
        intent_id=intent.intent_id,
        decision="APPROVE",
        reason="manual operator approval",
        decided_at="2026-03-19T00:01:00Z",
    )
    return StrategyIntentView(
        intent=intent,
        current_decision="APPROVE",
        latest_decision=latest,
    )


def _dispatch_response(*, decision: str = "WOULD_POST") -> StrategyDispatchResponse:
    return StrategyDispatchResponse(
        intent=_intent_view(),
        link=StrategyExecutionLinkRecord(
            execution_id="strategy_exec_123456",
            intent_id="intent-123",
            strategy_name="wallet_shadow_copy",
            strategy_type="wallet_shadow_copy",
            mode="paper",
            created_at="2026-03-19T00:02:00Z",
            execution_plan_id="plan-123",
            execution_result_id="result-123",
        ),
        execution=StrategyDispatchResultRecord(
            execution_id="strategy_exec_123456",
            intent_id="intent-123",
            strategy_name="wallet_shadow_copy",
            strategy_type="wallet_shadow_copy",
            mode="paper",
            decision=decision,
            created_at="2026-03-19T00:02:00Z",
            market_slug="btc-15m",
            condition_id="0x" + ("a" * 64),
            token_id="100",
            outcome="Yes",
            side="BUY",
            execution_request=StrategyExecutionRequest(
                market_ref="0x" + ("a" * 64),
                market_slug="btc-15m",
                condition_id="0x" + ("a" * 64),
                token_id="100",
                outcome="yes",
                side="buy",
                price="0.56",
                size="44.642857",
                notional_usdc="25",
            ),
            risk_checks=[
                StrategyReasonBlock(
                    section="market_open",
                    status="pass",
                    message="Market is active and open.",
                )
            ],
            execution_reasons=[
                StrategyReasonBlock(
                    section="local_signing",
                    status="pass",
                    message="Order was built and signed locally without submission.",
                )
            ],
            execution_plan_id="plan-123",
            execution_result_id="result-123",
        ),
    )


def _risk_policy(strategy_name: str, dispatch_enabled: bool) -> RiskPolicy:
    return RiskPolicy(
        strategy_name=strategy_name,
        dispatch_enabled=dispatch_enabled,
        max_drift_pct="5",
        max_spread_pct="5",
        max_size_usdc_per_order="25",
        max_exposure_usdc_per_market="100",
        max_exposure_usdc_per_strategy="250",
        require_market_open=True,
        require_balance_ready=True,
        require_allowance_ready=True,
    )


class FakeRiskPolicyService:
    def show(self) -> RiskShowResponse:
        return RiskShowResponse(
            persisted=False,
            default_policy=_risk_policy("default", False),
            strategies=[
                _risk_policy("wallet_shadow_copy", True),
                _risk_policy("market_watch_reversion", False),
            ],
            total=2,
        )

    def init_defaults(self) -> RiskInitDefaultsResponse:
        shown = self.show()
        return RiskInitDefaultsResponse(
            initialized=True,
            persisted=True,
            default_policy=shown.default_policy,
            strategies=shown.strategies,
            total=shown.total,
        )


class FakeStrategyDispatchService:
    def dispatch_intent(self, intent_id: str, *, live: bool = False) -> StrategyDispatchResponse:
        _ = intent_id
        return _dispatch_response(decision="POSTED" if live else "WOULD_POST")

    def dispatch_pending(self, *, limit: int = 20) -> StrategyDispatchPendingResponse:
        _ = limit
        item = _dispatch_response()
        return StrategyDispatchPendingResponse(
            items=[item],
            total_candidates=1,
            total_dispatched=1,
            total_skipped=0,
        )

    def list_executions(self, *, limit: int = 20) -> StrategyExecutionsResponse:
        _ = limit
        return StrategyExecutionsResponse(items=[_dispatch_response().execution], total=1)

    def get_execution(self, execution_id: str) -> StrategyExecutionDetailResponse:
        _ = execution_id
        item = _dispatch_response()
        return StrategyExecutionDetailResponse(
            intent=item.intent,
            link=item.link,
            execution=item.execution,
        )


def test_root_help_lists_risk_namespace() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "risk" in result.stdout


def test_strategy_help_lists_dispatch_commands() -> None:
    result = runner.invoke(app, ["strategy", "--help"])

    assert result.exit_code == 0
    assert "dispatch" in result.stdout
    assert "executions" in result.stdout
    assert "execution" in result.stdout


def test_risk_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.risk.RiskPolicyService", FakeRiskPolicyService)

    show_result = runner.invoke(app, ["risk", "show", "--json"])
    init_result = runner.invoke(app, ["risk", "init-defaults", "--json"])

    assert show_result.exit_code == 0
    assert json.loads(show_result.stdout)["persisted"] is False
    assert init_result.exit_code == 0
    assert json.loads(init_result.stdout)["initialized"] is True


def test_strategy_dispatch_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy.StrategyDispatchService", FakeStrategyDispatchService)

    dispatch_result = runner.invoke(
        app,
        ["strategy", "dispatch", "--intent-id", "intent-123", "--json"],
    )
    pending_result = runner.invoke(
        app,
        ["strategy", "dispatch", "pending", "--limit", "5", "--json"],
    )
    executions_result = runner.invoke(
        app,
        ["strategy", "executions", "--limit", "5", "--json"],
    )
    execution_result = runner.invoke(
        app,
        ["strategy", "execution", "get", "--execution-id", "strategy_exec_123456", "--json"],
    )

    assert dispatch_result.exit_code == 0
    assert json.loads(dispatch_result.stdout)["execution"]["decision"] == "WOULD_POST"
    assert pending_result.exit_code == 0
    assert json.loads(pending_result.stdout)["total_dispatched"] == 1
    assert executions_result.exit_code == 0
    assert (
        json.loads(executions_result.stdout)["items"][0]["execution_id"]
        == "strategy_exec_123456"
    )
    assert execution_result.exit_code == 0
    assert json.loads(execution_result.stdout)["link"]["execution_id"] == "strategy_exec_123456"


def test_strategy_dispatch_live_requires_confirm() -> None:
    result = runner.invoke(
        app,
        ["strategy", "dispatch", "--intent-id", "intent-123", "--live", "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_argument",
            "message": "Live strategy dispatch requires both --live and --confirm.",
            "resource": "strategy",
        },
        "ok": False,
    }


def test_root_output_json_works_for_risk(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.risk.RiskPolicyService", FakeRiskPolicyService)

    result = runner.invoke(app, ["--output", "json", "risk", "show"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["strategies"][0]["strategy_name"] == "wallet_shadow_copy"


def test_strategy_executions_human_table(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy.StrategyDispatchService", FakeStrategyDispatchService)

    result = runner.invoke(app, ["strategy", "executions", "--limit", "5"])

    assert result.exit_code == 0
    assert "Strategy Executions" in result.stdout
    assert "Execution ID" in result.stdout
    assert "WOULD_POST" in result.stdout
