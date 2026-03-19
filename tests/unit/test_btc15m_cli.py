"""CLI tests for the BTC15m research-strategy surface."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.strategy import (
    Btc15mPaperEvaluation,
    Btc15mPaperRunRecord,
    Btc15mPaperRunResponse,
    Btc15mRecordStartResponse,
    Btc15mRecordWindowResponse,
    Btc15mReplayRecord,
    Btc15mReplayResponse,
    Btc15mReportResponse,
    Btc15mReportSummary,
    Btc15mWindowIdentity,
    Btc15mWindowRecord,
)

runner = CliRunner()


class FakeBtc15mStrategyService:
    def record_start(self, *, seconds: int = 60) -> Btc15mRecordStartResponse:
        _ = seconds
        return Btc15mRecordStartResponse(
            session_id="record-session",
            started_at="2026-03-19T00:00:00Z",
            ended_at="2026-03-19T00:01:00Z",
            requested_seconds=60,
            items=[_window_record()],
            total=1,
            errors=[],
        )

    def record_window(self, *, slug: str) -> Btc15mRecordWindowResponse:
        return Btc15mRecordWindowResponse(
            session_id="record-session",
            slug=slug,
            started_at="2026-03-19T00:00:00Z",
            ended_at="2026-03-19T00:16:00Z",
            requested_seconds=960,
            items=[_window_record()],
            total=1,
            errors=[],
        )

    def replay(self, *, from_at: str, to_at: str) -> Btc15mReplayResponse:
        _ = from_at
        _ = to_at
        return Btc15mReplayResponse(
            replay=Btc15mReplayRecord(
                replay_id="replay-1",
                created_at="2026-03-19T01:00:00Z",
                from_at="2026-03-19T00:00:00Z",
                to_at="2026-03-20T00:00:00Z",
                items=[_evaluation()],
                total=1,
                errors=[],
            )
        )

    def paper_run(self, *, limit: int = 20) -> Btc15mPaperRunResponse:
        return Btc15mPaperRunResponse(
            run=Btc15mPaperRunRecord(
                run_id="run-1",
                created_at="2026-03-19T01:00:00Z",
                limit=limit,
                items=[_evaluation()],
                total_considered=1,
                total_evaluated=1,
                total_skipped=0,
                total_realized_pnl_usdc="241.6666662",
                errors=[],
            )
        )

    def report(self) -> Btc15mReportResponse:
        return Btc15mReportResponse(
            summary=Btc15mReportSummary(
                recorded_window_count=1,
                completed_window_count=1,
                replay_batch_count=1,
                paper_run_count=1,
                evaluated_window_count=1,
                total_realized_pnl_usdc="241.6666662",
                average_realized_pnl_usdc="241.6666662",
                win_count=1,
                loss_count=0,
                tie_count=0,
                skip_count=0,
            ),
            latest_active_window=None,
            recent_replays=[self.replay(from_at="", to_at="").replay],
            recent_runs=[self.paper_run().run],
            recent_evaluations=[_evaluation()],
            errors=[],
        )


def test_strategy_help_lists_btc15m() -> None:
    result = runner.invoke(app, ["strategy", "--help"])

    assert result.exit_code == 0
    assert "btc15m" in result.stdout


def test_btc15m_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    record_result = runner.invoke(app, ["strategy", "btc15m", "record", "start", "--json"])
    replay_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "replay",
            "--from",
            "2026-03-19T00:00:00Z",
            "--to",
            "2026-03-20T00:00:00Z",
            "--json",
        ],
    )
    paper_result = runner.invoke(app, ["strategy", "btc15m", "paper-run", "--limit", "5", "--json"])
    report_result = runner.invoke(app, ["strategy", "btc15m", "report", "--json"])

    assert record_result.exit_code == 0
    assert json.loads(record_result.stdout)["total"] == 1
    assert replay_result.exit_code == 0
    assert json.loads(replay_result.stdout)["replay"]["total"] == 1
    assert paper_result.exit_code == 0
    assert json.loads(paper_result.stdout)["run"]["total_evaluated"] == 1
    assert report_result.exit_code == 0
    assert json.loads(report_result.stdout)["summary"]["recorded_window_count"] == 1


def test_btc15m_root_output_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["--output", "json", "strategy", "btc15m", "report"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["summary"]["paper_run_count"] == 1


def _window_record() -> Btc15mWindowRecord:
    return Btc15mWindowRecord(
        window=Btc15mWindowIdentity(
            strategy_name="btc_15m_chainlink_directional_ladder_v1",
            window_id="btc15m:window-1",
            condition_id="0x" + ("a" * 64),
            market_slug="btc-15m-up-down-1",
            token_ids=["100", "101"],
            outcomes=["Up", "Down"],
            window_start_at="2026-03-19T00:00:00Z",
            window_end_at="2026-03-19T00:15:00Z",
            market_open_time="2026-03-19T00:00:00Z",
        ),
        recorded_at="2026-03-19T00:16:00Z",
        recorder_session_id="record-session",
        status="complete",
        boundary_status="complete",
        start_price_proxy_v1="100",
        end_price_proxy_v1="102",
        decision="UP",
        decision_at="2026-03-19T00:05:00Z",
        resolution_result="UP",
    )


def _evaluation() -> Btc15mPaperEvaluation:
    return Btc15mPaperEvaluation(
        window_id="btc15m:window-1",
        market_slug="btc-15m-up-down-1",
        condition_id="0x" + ("a" * 64),
        window_start_at="2026-03-19T00:00:00Z",
        window_end_at="2026-03-19T00:15:00Z",
        target_token_id="100",
        target_outcome="Up",
        decision="UP",
        decision_at="2026-03-19T00:05:00Z",
        resolution_result="UP",
        skip_reasons=[],
        reason_blocks=[],
        start_price_proxy_v1="100",
        end_price_proxy_v1="102",
        rungs=[],
        filled_rung_count=3,
        cancelled_rung_count=0,
        first_fill_at="2026-03-19T00:06:00Z",
        total_cost_usdc="49.9999998",
        settlement_value_usdc="291.666666",
        realized_pnl_usdc="241.6666662",
        mfe_usdc="0",
        mae_usdc="0",
    )
