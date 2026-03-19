"""CLI tests for the read-only strategy registry and orchestrator namespace."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.strategy import (
    StrategyCandidateIntent,
    StrategyDecisionMutationResponse,
    StrategyDecisionRecord,
    StrategyDefinition,
    StrategyEvaluateResponse,
    StrategyIntentsResponse,
    StrategyIntentView,
    StrategyListResponse,
    StrategyNotFoundError,
    StrategyReasonBlock,
    StrategyReviewResponse,
    StrategyShowResponse,
    StrategyValidationResult,
)

runner = CliRunner()


def _definition() -> StrategyDefinition:
    return StrategyDefinition(
        name="wallet_shadow_copy",
        strategy_type="wallet_shadow_copy",
        description="Promote wallet shadow candidates into manual review intents.",
        required_state_files=["wallet-shadow-runs.json"],
        settings={"decision_filter": "WOULD_COPY", "max_source_age_seconds": 86400},
    )


def _intent() -> StrategyCandidateIntent:
    return StrategyCandidateIntent(
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
        reason_blocks=[
            StrategyReasonBlock(
                section="manual_gate",
                status="pass",
                message="Copyable candidate promoted to WAIT pending manual approval.",
            )
        ],
        created_at="2026-03-18T12:00:00Z",
        source_refs=[],
    )


def _intent_view(
    *,
    current_decision: str = "WAIT",
    latest_decision: StrategyDecisionRecord | None = None,
) -> StrategyIntentView:
    return StrategyIntentView(
        intent=_intent(),
        current_decision=current_decision,
        latest_decision=latest_decision,
    )


class FakeStrategyService:
    """Small service double for strategy CLI tests."""

    def list_strategies(self) -> StrategyListResponse:
        return StrategyListResponse(items=[_definition()], total=1)

    def show_strategy(self, name: str) -> StrategyShowResponse:
        if name != "wallet_shadow_copy":
            raise StrategyNotFoundError(f"strategy '{name}' was not found")
        return StrategyShowResponse(strategy=_definition())

    def validate_strategy(self, name: str) -> StrategyValidationResult:
        _ = name
        return StrategyValidationResult(
            strategy=_definition(),
            valid=True,
            reason_blocks=[
                StrategyReasonBlock(
                    section="strategy_definition",
                    status="pass",
                    message="Seeded strategy definition is internally consistent.",
                )
            ],
            errors=[],
        )

    def evaluate_strategy(self, name: str, *, limit: int = 20) -> StrategyEvaluateResponse:
        _ = name
        _ = limit
        return StrategyEvaluateResponse(
            strategy=_definition(),
            items=[_intent()],
            total=1,
            errors=[],
        )

    def list_intents(self, *, limit: int = 20) -> StrategyIntentsResponse:
        _ = limit
        return StrategyIntentsResponse(items=[_intent_view()], total=1)

    def review_intent(self, intent_id: str) -> StrategyReviewResponse:
        latest = StrategyDecisionRecord(
            intent_id=intent_id,
            decision="APPROVE",
            reason="manual operator approval",
            decided_at="2026-03-18T12:05:00Z",
        )
        return StrategyReviewResponse(
            intent=_intent_view(current_decision="APPROVE", latest_decision=latest),
            decision_history=[latest],
            errors=[],
        )

    def approve_intent(self, intent_id: str) -> StrategyDecisionMutationResponse:
        latest = StrategyDecisionRecord(
            intent_id=intent_id,
            decision="APPROVE",
            reason="manual operator approval",
            decided_at="2026-03-18T12:05:00Z",
        )
        return StrategyDecisionMutationResponse(
            intent=_intent_view(current_decision="APPROVE", latest_decision=latest)
        )

    def reject_intent(self, intent_id: str, *, reason: str) -> StrategyDecisionMutationResponse:
        latest = StrategyDecisionRecord(
            intent_id=intent_id,
            decision="REJECT",
            reason=reason,
            decided_at="2026-03-18T12:06:00Z",
        )
        return StrategyDecisionMutationResponse(
            intent=_intent_view(current_decision="REJECT", latest_decision=latest)
        )


def test_root_help_lists_strategy_namespace() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "strategy" in result.stdout


def test_strategy_help_lists_commands() -> None:
    result = runner.invoke(app, ["strategy", "--help"])

    assert result.exit_code == 0
    assert "list" in result.stdout
    assert "show" in result.stdout
    assert "validate" in result.stdout
    assert "evaluate" in result.stdout
    assert "intents" in result.stdout
    assert "review" in result.stdout
    assert "approve" in result.stdout
    assert "reject" in result.stdout


def test_strategy_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy.StrategyService", FakeStrategyService)

    list_result = runner.invoke(app, ["strategy", "list", "--json"])
    show_result = runner.invoke(
        app,
        ["strategy", "show", "--name", "wallet_shadow_copy", "--json"],
    )
    validate_result = runner.invoke(
        app,
        ["strategy", "validate", "--name", "wallet_shadow_copy", "--json"],
    )
    evaluate_result = runner.invoke(
        app,
        ["strategy", "evaluate", "--name", "wallet_shadow_copy", "--limit", "5", "--json"],
    )
    intents_result = runner.invoke(app, ["strategy", "intents", "--limit", "5", "--json"])
    review_result = runner.invoke(
        app,
        ["strategy", "review", "--intent-id", "intent-123", "--json"],
    )
    approve_result = runner.invoke(
        app,
        ["strategy", "approve", "--intent-id", "intent-123", "--json"],
    )
    reject_result = runner.invoke(
        app,
        [
            "strategy",
            "reject",
            "--intent-id",
            "intent-123",
            "--reason",
            "operator veto",
            "--json",
        ],
    )

    assert list_result.exit_code == 0
    assert json.loads(list_result.stdout)["total"] == 1
    assert show_result.exit_code == 0
    assert json.loads(show_result.stdout)["strategy"]["name"] == "wallet_shadow_copy"
    assert validate_result.exit_code == 0
    assert json.loads(validate_result.stdout)["valid"] is True
    assert evaluate_result.exit_code == 0
    assert json.loads(evaluate_result.stdout)["items"][0]["decision"] == "WAIT"
    assert intents_result.exit_code == 0
    assert json.loads(intents_result.stdout)["items"][0]["current_decision"] == "WAIT"
    assert review_result.exit_code == 0
    assert json.loads(review_result.stdout)["intent"]["current_decision"] == "APPROVE"
    assert approve_result.exit_code == 0
    assert json.loads(approve_result.stdout)["intent"]["current_decision"] == "APPROVE"
    assert reject_result.exit_code == 0
    assert json.loads(reject_result.stdout)["intent"]["current_decision"] == "REJECT"


def test_root_output_json_works_for_strategy(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy.StrategyService", FakeStrategyService)

    result = runner.invoke(
        app,
        ["--output", "json", "strategy", "list"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "items": [
            {
                "description": "Promote wallet shadow candidates into manual review intents.",
                "name": "wallet_shadow_copy",
                "required_state_files": ["wallet-shadow-runs.json"],
                "settings": {
                    "decision_filter": "WOULD_COPY",
                    "max_source_age_seconds": 86400,
                },
                "strategy_type": "wallet_shadow_copy",
            }
        ],
        "total": 1,
    }


def test_strategy_show_not_found_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy.StrategyService", FakeStrategyService)

    result = runner.invoke(
        app,
        ["strategy", "show", "--name", "unknown", "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "identifier": "unknown",
            "message": "strategy 'unknown' was not found",
            "resource": "strategy",
        },
        "ok": False,
    }


def test_strategy_intents_human_table(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy.StrategyService", FakeStrategyService)

    result = runner.invoke(app, ["strategy", "intents", "--limit", "5"])

    assert result.exit_code == 0
    assert "Strategy Intents" in result.stdout
    assert "Intent ID" in result.stdout
    assert "wallet_shadow_copy" in result.stdout
