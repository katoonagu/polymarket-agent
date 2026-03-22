"""CLI tests for the BTC15m research-strategy surface."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.cli.app import app
from pm.cli.strategy_btc15m import _format_cents_label
from pm.strategy import (
    Btc15mAutoRollResponse,
    Btc15mAutoRollRunRecord,
    Btc15mCampaignNextWindowResponse,
    Btc15mCampaignReportResponse,
    Btc15mCampaignReportSummary,
    Btc15mCampaignRunRecord,
    Btc15mCampaignRunResponse,
    Btc15mDashboardResponse,
    Btc15mDashboardRungState,
    Btc15mDashboardSideState,
    Btc15mDashboardSnapshotRecord,
    Btc15mLiquiditySampleResponse,
    Btc15mLiveResponse,
    Btc15mPaperEvaluation,
    Btc15mPaperRunRecord,
    Btc15mPaperRunResponse,
    Btc15mRecordStartResponse,
    Btc15mRecordWindowResponse,
    Btc15mReplayRecord,
    Btc15mReplayResponse,
    Btc15mReportResponse,
    Btc15mReportSummary,
    Btc15mResolveCurrentResponse,
    Btc15mRunMode,
    Btc15mTerminalDisplayTruth,
    Btc15mTerminalMarketTruth,
    Btc15mTerminalPageMirror,
    Btc15mTerminalPresenter,
    Btc15mTerminalReplayResponse,
    Btc15mTerminalReportResponse,
    Btc15mTerminalReportSummary,
    Btc15mTerminalResponse,
    Btc15mTerminalSessionRecord,
    Btc15mTerminalState,
    Btc15mTerminalWindowTearSheet,
    Btc15mWindowIdentity,
    Btc15mWindowRecord,
)
from pm.strategy.btc15m_service import Btc15mOperatorHintError

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

    def resolve_current(self) -> Btc15mResolveCurrentResponse:
        return Btc15mResolveCurrentResponse(
            checked_at="2026-03-20T10:36:00Z",
            timing_source="slug_timestamp",
            selection_source="current_exact",
            status="live",
            seconds_to_start=0,
            seconds_to_end=540,
            window=_window_record().window,
            errors=[],
        )

    def live_current(
        self,
        *,
        mode: str = "paper",
        hours: str | None = None,
    ) -> Btc15mLiveResponse:
        return Btc15mLiveResponse(
            run_id="live-1",
            started_at="2026-03-20T10:36:00Z",
            ended_at="2026-03-20T10:45:30Z",
            mode=mode,
            requested_hours=hours,
            stop_reason="completed_current_window",
            window=_window_record().window,
            evaluation=_evaluation(),
            errors=[],
        )

    def dashboard_current(
        self,
        *,
        seconds: int = 30,
        on_snapshot=None,
    ) -> Btc15mDashboardResponse:
        snapshot = Btc15mDashboardSnapshotRecord(
            snapshot_id="snapshot-1",
            session_id="dashboard-1",
            window_id="btc15m:window-1",
            market_slug="btc-updown-15m-1774002600",
            sampled_at="2026-03-20T10:36:00Z",
            window_status="current_monitor",
            window_start_at="2026-03-20T10:30:00Z",
            window_end_at="2026-03-20T10:45:00Z",
            display=_display_truth(),
            page_mirror=_page_mirror(),
            market_truth=_market_truth(),
            terminal_presenter=_presenter(),
            current_window_label="10:30 - 10:45 UTC",
            page_parity_source="page_exact",
            current_live_btc_price="100",
            up_price="0.31",
            down_price="0.69",
            current_chainlink_price="100",
            current_binance_price="100.1",
            start_price_proxy_v1="99.5",
            price_to_beat="99.5",
            direction_lock_status="UP",
            current_midpoint="0.28",
            current_spread="0.03",
            visible_liquidity_030="80",
            visible_liquidity_020="100",
            visible_liquidity_010="200",
            derived_up_price="0.28",
            derived_up_price_source="midpoint",
            derived_down_price="0.72",
            derived_down_price_source="midpoint",
            manipulation_flags=[],
            up_side=_side_state("0.30", "0.32", "0.31", "0.02", "80", "100", "200"),
            down_side=_side_state("0.68", "0.70", "0.69", "0.02", "70", "90", "120"),
            rungs=[
                Btc15mDashboardRungState(price="0.30", state="armed", visible_liquidity="80"),
                Btc15mDashboardRungState(price="0.20", state="armed", visible_liquidity="100"),
                Btc15mDashboardRungState(price="0.10", state="armed", visible_liquidity="200"),
            ],
            errors=[],
        )
        if on_snapshot is not None:
            on_snapshot(snapshot)
        return Btc15mDashboardResponse(
            session_id="dashboard-1",
            started_at="2026-03-20T10:36:00Z",
            ended_at="2026-03-20T10:36:30Z",
            requested_seconds=seconds,
            window=_window_record().window,
            total_snapshots=1,
            latest_snapshot=snapshot,
            latest_evaluation=None,
            errors=[],
        )

    def auto_roll(
        self,
        *,
        hours: str,
        mode: str = "paper",
    ) -> Btc15mAutoRollResponse:
        return Btc15mAutoRollResponse(
            run=Btc15mAutoRollRunRecord(
                run_id="auto-roll-1",
                created_at="2026-03-20T10:36:00Z",
                started_at="2026-03-20T10:36:00Z",
                ended_at="2026-03-20T12:36:00Z",
                requested_hours=hours,
                mode=mode,
                stop_reason="insufficient_remaining_time",
                items=[],
                total_windows=0,
                total_skipped=0,
                total_realized_pnl_usdc="0",
                errors=[],
            )
        )

    def terminal_current(
        self,
        *,
        mode: str = "paper",
        confirm: bool = False,
        observe_only: bool = False,
        arm_next: bool = False,
        budget_usdc: str | None = None,
        rungs: str | None = None,
        snapshot_only: bool = False,
        session_window_limit: int | None = 1,
        on_snapshot=None,
        confirm_action=None,
    ) -> Btc15mTerminalResponse:
        _ = confirm
        _ = confirm_action
        _ = session_window_limit
        _ = arm_next
        resolved_budget = budget_usdc or "50"
        resolved_rungs = (rungs.split(",") if rungs is not None else ["20", "15", "15"])
        snapshot = self.dashboard_current().latest_snapshot
        assert snapshot is not None
        snapshot = snapshot.model_copy(
            update={
                "view_kind": "terminal",
                "mode": Btc15mRunMode(mode),
                "attach_mode": "current_observe_only" if observe_only else "current",
                "observe_only": observe_only,
                "window_status": "OBSERVE_ONLY" if observe_only else "ENTRY_WINDOW_OPEN",
                "selected_side": None if observe_only else "UP",
                "paper_budget_usdc": resolved_budget,
                "rung_notionals_usdc": resolved_rungs,
                "latest_events": [],
            }
        )
        if on_snapshot is not None and not snapshot_only:
            on_snapshot(snapshot)
        session = (
            None
            if snapshot_only
            else Btc15mTerminalSessionRecord(
                session_id="terminal-1",
                created_at="2026-03-20T10:45:00Z",
                started_at="2026-03-20T10:36:00Z",
                ended_at="2026-03-20T10:45:00Z",
                mode=mode,
                attach_mode="current_observe_only" if observe_only else "current",
                observe_only=observe_only,
                follow_current=True,
                stop_reason="observe_only_complete" if observe_only else "window_complete",
                final_state=(
                    Btc15mTerminalState.OBSERVE_ONLY
                    if observe_only
                    else Btc15mTerminalState.RESOLVED
                ),
                window=_window_record().window,
                boundary_status="complete",
                display=_display_truth(),
                current_window_label="10:30 - 10:45 UTC",
                page_parity_source="page_exact",
                price_to_beat="99.5",
                current_live_btc_price="100",
                up_price="0.31",
                down_price="0.69",
                display_volume="120K",
                paper_budget_usdc=resolved_budget,
                rung_notionals_usdc=resolved_rungs,
                selected_side=None if observe_only else "UP",
                latest_snapshot=snapshot,
                latest_evaluation=None if observe_only else _evaluation(),
                total_snapshots=1,
                window_tear_sheets=[
                    Btc15mTerminalWindowTearSheet(
                        window=_window_record().window,
                        started_at="2026-03-20T10:36:00Z",
                        ended_at="2026-03-20T10:45:00Z",
                        mode=Btc15mRunMode(mode),
                        attach_mode="current_observe_only" if observe_only else "current",
                        observe_only=observe_only,
                        stop_reason="observe_only_complete" if observe_only else "window_complete",
                        final_state=(
                            Btc15mTerminalState.OBSERVE_ONLY
                            if observe_only
                            else Btc15mTerminalState.RESOLVED
                        ),
                        boundary_status="complete",
                        display=_display_truth(),
                        current_window_label="10:30 - 10:45 UTC",
                        page_parity_source="page_exact",
                        price_to_beat="99.5",
                        current_live_btc_price="100",
                        up_price="0.31",
                        down_price="0.69",
                        display_volume="120K",
                        paper_budget_usdc=resolved_budget,
                        rung_notionals_usdc=resolved_rungs,
                        selected_side=None if observe_only else "UP",
                        latest_snapshot=snapshot,
                        latest_evaluation=None if observe_only else _evaluation(),
                        total_snapshots=1,
                    )
                ],
            )
        )
        return Btc15mTerminalResponse(
            session_id="terminal-1",
            started_at="2026-03-20T10:36:00Z",
            ended_at="2026-03-20T10:45:00Z",
            mode=Btc15mRunMode(mode),
            attach_mode="current_observe_only" if observe_only else "current",
            stop_reason=(
                "snapshot_only"
                if snapshot_only
                else "observe_only_complete"
                if observe_only
                else "window_complete"
            ),
            window=_window_record().window,
            total_snapshots=1,
            latest_snapshot=snapshot,
            session=session,
            errors=[],
        )

    def terminal_wait_next(
        self,
        *,
        mode: str = "paper",
        confirm: bool = False,
        budget_usdc: str | None = None,
        rungs: str | None = None,
        snapshot_only: bool = False,
        session_window_limit: int | None = 1,
        on_snapshot=None,
        confirm_action=None,
    ) -> Btc15mTerminalResponse:
        _ = confirm
        _ = confirm_action
        _ = session_window_limit
        resolved_budget = budget_usdc or "50"
        resolved_rungs = (rungs.split(",") if rungs is not None else ["20", "15", "15"])
        snapshot = self.dashboard_current().latest_snapshot
        assert snapshot is not None
        snapshot = snapshot.model_copy(
            update={
                "view_kind": "terminal",
                "mode": Btc15mRunMode(mode),
                "attach_mode": "wait_next",
                "observe_only": True,
                "window_status": "WAITING_FOR_NEXT_WINDOW",
                "paper_budget_usdc": resolved_budget,
                "rung_notionals_usdc": resolved_rungs,
                "latest_events": [],
            }
        )
        if on_snapshot is not None and not snapshot_only:
            on_snapshot(snapshot)
        session = None if snapshot_only else Btc15mTerminalSessionRecord(
            session_id="terminal-wait-1",
            created_at="2026-03-20T11:15:00Z",
            started_at="2026-03-20T10:36:00Z",
            ended_at="2026-03-20T11:15:00Z",
            mode=mode,
            attach_mode="wait_next",
            observe_only=False,
            stop_reason="window_complete",
            final_state=Btc15mTerminalState.RESOLVED,
            window=_window_record().window,
            display=_display_truth(),
            current_window_label="10:30 - 10:45 UTC",
            page_parity_source="page_exact",
            price_to_beat="99.5",
            current_live_btc_price="100",
            up_price="0.31",
            down_price="0.69",
            display_volume="120K",
            paper_budget_usdc=resolved_budget,
            rung_notionals_usdc=resolved_rungs,
            selected_side="UP",
            latest_snapshot=snapshot,
            latest_evaluation=_evaluation(),
            total_snapshots=2,
            window_tear_sheets=[
                Btc15mTerminalWindowTearSheet(
                    window=_window_record().window,
                    started_at="2026-03-20T10:36:00Z",
                    ended_at="2026-03-20T11:15:00Z",
                    mode=Btc15mRunMode(mode),
                    attach_mode="wait_next",
                    observe_only=False,
                    stop_reason="window_complete",
                    final_state=Btc15mTerminalState.RESOLVED,
                    boundary_status="complete",
                    display=_display_truth(),
                    current_window_label="10:30 - 10:45 UTC",
                    page_parity_source="page_exact",
                    price_to_beat="99.5",
                    current_live_btc_price="100",
                    up_price="0.31",
                    down_price="0.69",
                    display_volume="120K",
                    paper_budget_usdc=resolved_budget,
                    rung_notionals_usdc=resolved_rungs,
                    selected_side="UP",
                    latest_snapshot=snapshot,
                    latest_evaluation=_evaluation(),
                    total_snapshots=2,
                )
            ],
        )
        return Btc15mTerminalResponse(
            session_id="terminal-wait-1",
            started_at="2026-03-20T10:36:00Z",
            ended_at="2026-03-20T11:15:00Z",
            mode=Btc15mRunMode(mode),
            attach_mode="wait_next",
            stop_reason="window_complete" if not snapshot_only else "snapshot_only",
            window=_window_record().window,
            total_snapshots=1 if snapshot_only else 2,
            latest_snapshot=snapshot,
            session=session,
            errors=[],
        )

    def terminal_replay(self, *, session_id: str, on_snapshot=None) -> Btc15mTerminalReplayResponse:
        snapshot = self.dashboard_current().latest_snapshot
        assert snapshot is not None
        snapshot = snapshot.model_copy(
            update={"view_kind": "terminal", "attach_mode": "current", "window_status": "RESOLVED"}
        )
        if on_snapshot is not None:
            on_snapshot(snapshot)
        return Btc15mTerminalReplayResponse(
            session_id=session_id,
            total_snapshots=2,
            session=Btc15mTerminalSessionRecord(
                session_id=session_id,
                created_at="2026-03-20T10:45:00Z",
                started_at="2026-03-20T10:36:00Z",
                ended_at="2026-03-20T10:45:00Z",
                mode=Btc15mRunMode.PAPER,
                attach_mode="current",
                stop_reason="window_complete",
                final_state=Btc15mTerminalState.RESOLVED,
                window=_window_record().window,
                display=_display_truth(),
                current_window_label="10:30 - 10:45 UTC",
                page_parity_source="api",
                price_to_beat="99.5",
                current_live_btc_price="100",
                up_price="0.31",
                down_price="0.69",
                latest_snapshot=snapshot,
                latest_evaluation=_evaluation(),
                window_tear_sheets=[
                    Btc15mTerminalWindowTearSheet(
                        window=_window_record().window,
                        started_at="2026-03-20T10:36:00Z",
                        ended_at="2026-03-20T10:45:00Z",
                        mode=Btc15mRunMode.PAPER,
                        attach_mode="current",
                        observe_only=False,
                        stop_reason="window_complete",
                        final_state=Btc15mTerminalState.RESOLVED,
                        boundary_status="complete",
                        display=_display_truth(),
                        current_window_label="10:30 - 10:45 UTC",
                        page_parity_source="api",
                        price_to_beat="99.5",
                        current_live_btc_price="100",
                        up_price="0.31",
                        down_price="0.69",
                        selected_side="UP",
                        latest_snapshot=snapshot,
                        latest_evaluation=_evaluation(),
                        total_snapshots=2,
                    )
                ],
            ),
            first_snapshot=snapshot,
            latest_snapshot=snapshot,
            errors=[],
        )

    def terminal_report(self, *, session_id: str | None = None) -> Btc15mTerminalReportResponse:
        return Btc15mTerminalReportResponse(
            summary=Btc15mTerminalReportSummary(
                terminal_session_count=1,
                paper_session_count=1,
                live_session_count=0,
                observe_only_session_count=0,
                waiting_session_count=0,
                resolved_session_count=1,
                skipped_session_count=0,
                total_realized_pnl_usdc="241.6666662",
                average_realized_pnl_usdc="241.6666662",
            ),
            session=(
                Btc15mTerminalSessionRecord(
                    session_id=session_id,
                    created_at="2026-03-20T10:45:00Z",
                    started_at="2026-03-20T10:36:00Z",
                    ended_at="2026-03-20T10:45:00Z",
                    mode=Btc15mRunMode.PAPER,
                    attach_mode="current",
                    stop_reason="window_complete",
                    final_state=Btc15mTerminalState.RESOLVED,
                    window=_window_record().window,
                    display=_display_truth(),
                    current_window_label="10:30 - 10:45 UTC",
                    page_parity_source="api",
                    price_to_beat="99.5",
                    current_live_btc_price="100",
                    up_price="0.31",
                    down_price="0.69",
                    selected_side="UP",
                    latest_snapshot=self.dashboard_current().latest_snapshot,
                    latest_evaluation=_evaluation(),
                    window_tear_sheets=[
                        Btc15mTerminalWindowTearSheet(
                            window=_window_record().window,
                            started_at="2026-03-20T10:36:00Z",
                            ended_at="2026-03-20T10:45:00Z",
                            mode=Btc15mRunMode.PAPER,
                            attach_mode="current",
                            observe_only=False,
                            stop_reason="window_complete",
                            final_state=Btc15mTerminalState.RESOLVED,
                            boundary_status="complete",
                            display=_display_truth(),
                            current_window_label="10:30 - 10:45 UTC",
                            page_parity_source="api",
                            price_to_beat="99.5",
                            current_live_btc_price="100",
                            up_price="0.31",
                            down_price="0.69",
                            selected_side="UP",
                            latest_snapshot=self.dashboard_current().latest_snapshot,
                            latest_evaluation=_evaluation(),
                            total_snapshots=1,
                        )
                    ],
                )
                if session_id is not None
                else None
            ),
            recent_sessions=[
                Btc15mTerminalSessionRecord(
                    session_id="terminal-1",
                    created_at="2026-03-20T10:45:00Z",
                    started_at="2026-03-20T10:36:00Z",
                    ended_at="2026-03-20T10:45:00Z",
                    mode=Btc15mRunMode.PAPER,
                    attach_mode="current",
                    stop_reason="window_complete",
                    final_state=Btc15mTerminalState.RESOLVED,
                    window=_window_record().window,
                    display=_display_truth(),
                    current_window_label="10:30 - 10:45 UTC",
                    page_parity_source="api",
                    price_to_beat="99.5",
                    current_live_btc_price="100",
                    up_price="0.31",
                    down_price="0.69",
                    selected_side="UP",
                    latest_evaluation=_evaluation(),
                )
            ],
            errors=[],
        )

    def paper_run(
        self,
        *,
        limit: int = 20,
        slug: str | None = None,
        mode: str = "paper",
    ) -> Btc15mPaperRunResponse:
        return Btc15mPaperRunResponse(
            run=Btc15mPaperRunRecord(
                run_id="run-1",
                created_at="2026-03-19T01:00:00Z",
                limit=limit,
                mode=mode,
                target_slug=slug,
                selection_source="slug" if slug is not None else "recorded",
                source_kind="manual",
                items=[_evaluation()],
                total_considered=1,
                total_evaluated=1,
                total_skipped=0,
                total_realized_pnl_usdc="241.6666662",
                errors=[],
            )
        )

    def liquidity_sample(self, *, seconds: int = 30) -> Btc15mLiquiditySampleResponse:
        return Btc15mLiquiditySampleResponse(
            session_id="liquidity-1",
            started_at="2026-03-19T00:00:00Z",
            ended_at="2026-03-19T00:00:30Z",
            requested_seconds=seconds,
            items=[],
            total=0,
            errors=[],
        )

    def campaign_next_window(
        self,
        *,
        slug: str | None = None,
        mode: str = "paper",
    ) -> Btc15mCampaignNextWindowResponse:
        return Btc15mCampaignNextWindowResponse(
            checked_at="2026-03-19T00:00:00Z",
            mode=mode,
            target_slug=slug,
            selection_source="slug" if slug is not None else "recurring",
            waited_seconds=0,
            timed_out=False,
            poll_count=0,
            window=_window_record().window,
            errors=[],
        )

    def campaign_run(
        self,
        *,
        hours: str,
        slug: str | None = None,
        mode: str = "paper",
    ) -> Btc15mCampaignRunResponse:
        _ = hours
        return Btc15mCampaignRunResponse(
            campaign=Btc15mCampaignRunRecord(
                run_id="campaign-1",
                created_at="2026-03-19T00:00:00Z",
                started_at="2026-03-19T00:00:00Z",
                ended_at="2026-03-19T02:00:00Z",
                requested_hours="2",
                mode=mode,
                target_slug=slug,
                selection_source="slug" if slug is not None else "recurring",
                stop_reason="completed_target_window" if slug is not None else "deadline_reached",
                items=[_evaluation()],
                total_windows=1,
                total_skipped=0,
                total_realized_pnl_usdc="241.6666662",
                errors=[],
            )
        )

    def campaign_report(self) -> Btc15mCampaignReportResponse:
        return Btc15mCampaignReportResponse(
            summary=Btc15mCampaignReportSummary(
                campaign_run_count=1,
                evaluated_window_count=1,
                total_realized_pnl_usdc="241.6666662",
                average_realized_pnl_usdc="241.6666662",
                win_count=1,
                loss_count=0,
                tie_count=0,
                skip_count=0,
                average_decision_spread="0.02",
                average_realized_vol_1m_bps="100",
                average_realized_vol_3m_bps="150",
            ),
            recent_runs=[self.campaign_run(hours="2").campaign],
            recent_evaluations=[_evaluation()],
            errors=[],
        )

    def report(self) -> Btc15mReportResponse:
        return Btc15mReportResponse(
            summary=Btc15mReportSummary(
                recorded_window_count=1,
                completed_window_count=1,
                replay_batch_count=1,
                paper_run_count=1,
                campaign_run_count=1,
                evaluated_window_count=1,
                total_realized_pnl_usdc="241.6666662",
                average_realized_pnl_usdc="241.6666662",
                win_count=1,
                loss_count=0,
                tie_count=0,
                skip_count=0,
            ),
            latest_active_window=None,
            campaign_summary=self.campaign_report().summary,
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
    resolve_current_result = runner.invoke(
        app,
        ["strategy", "btc15m", "resolve-current", "--json"],
    )
    live_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "live",
            "--current",
            "--mode",
            "paper",
            "--json",
        ],
    )
    dashboard_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "dashboard",
            "--current",
            "--seconds",
            "1",
            "--json",
        ],
    )
    terminal_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "terminal",
            "--current",
            "--json",
        ],
    )
    terminal_wait_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "terminal",
            "--wait-next",
            "--json",
        ],
    )
    terminal_report_result = runner.invoke(
        app,
        ["strategy", "btc15m", "terminal", "report", "--json"],
    )
    terminal_report_session_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "terminal",
            "report",
            "--session-id",
            "terminal-1",
            "--json",
        ],
    )
    terminal_replay_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "terminal",
            "replay",
            "--session-id",
            "terminal-1",
            "--json",
        ],
    )
    auto_roll_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "auto-roll",
            "--hours",
            "2",
            "--mode",
            "paper",
            "--json",
        ],
    )
    paper_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "paper-run",
            "--slug",
            "btc-15m-up-down-1",
            "--mode",
            "paper",
            "--json",
        ],
    )
    report_result = runner.invoke(app, ["strategy", "btc15m", "report", "--json"])
    liquidity_result = runner.invoke(
        app, ["strategy", "btc15m", "liquidity", "sample", "--json"]
    )
    campaign_next_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "campaign",
            "next-window",
            "--slug",
            "btc-15m-up-down-1",
            "--mode",
            "paper",
            "--json",
        ],
    )
    campaign_run_result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "campaign",
            "run",
            "--hours",
            "2",
            "--slug",
            "btc-15m-up-down-1",
            "--mode",
            "paper",
            "--json",
        ],
    )
    campaign_report_result = runner.invoke(
        app, ["strategy", "btc15m", "campaign", "report", "--json"]
    )

    assert record_result.exit_code == 0
    assert json.loads(record_result.stdout)["total"] == 1
    assert replay_result.exit_code == 0
    assert json.loads(replay_result.stdout)["replay"]["total"] == 1
    assert resolve_current_result.exit_code == 0
    assert json.loads(resolve_current_result.stdout)["window"]["market_slug"] == "btc-15m-up-down-1"
    assert live_result.exit_code == 0
    assert json.loads(live_result.stdout)["stop_reason"] == "completed_current_window"
    assert dashboard_result.exit_code == 0
    dashboard_payload = json.loads(dashboard_result.stdout)
    assert dashboard_payload["latest_snapshot"]["market_slug"] == "btc-updown-15m-1774002600"
    assert terminal_result.exit_code == 0
    terminal_payload = json.loads(terminal_result.stdout)
    assert terminal_payload["latest_snapshot"]["view_kind"] == "terminal"
    assert terminal_wait_result.exit_code == 0
    assert json.loads(terminal_wait_result.stdout)["attach_mode"] == "wait_next"
    assert terminal_report_result.exit_code == 0
    assert json.loads(terminal_report_result.stdout)["summary"]["terminal_session_count"] == 1
    assert terminal_report_session_result.exit_code == 0
    assert (
        json.loads(terminal_report_session_result.stdout)["session"]["session_id"]
        == "terminal-1"
    )
    assert terminal_replay_result.exit_code == 0
    assert json.loads(terminal_replay_result.stdout)["session_id"] == "terminal-1"
    assert auto_roll_result.exit_code == 0
    auto_roll_payload = json.loads(auto_roll_result.stdout)
    assert auto_roll_payload["run"]["stop_reason"] == "insufficient_remaining_time"
    assert paper_result.exit_code == 0
    assert json.loads(paper_result.stdout)["run"]["target_slug"] == "btc-15m-up-down-1"
    assert json.loads(paper_result.stdout)["run"]["total_evaluated"] == 1
    assert report_result.exit_code == 0
    assert json.loads(report_result.stdout)["summary"]["recorded_window_count"] == 1
    assert liquidity_result.exit_code == 0
    assert json.loads(liquidity_result.stdout)["total"] == 0
    assert campaign_next_result.exit_code == 0
    assert json.loads(campaign_next_result.stdout)["window"]["market_slug"] == "btc-15m-up-down-1"
    assert json.loads(campaign_next_result.stdout)["target_slug"] == "btc-15m-up-down-1"
    assert campaign_run_result.exit_code == 0
    assert json.loads(campaign_run_result.stdout)["campaign"]["target_slug"] == "btc-15m-up-down-1"
    assert json.loads(campaign_run_result.stdout)["campaign"]["total_windows"] == 1
    assert campaign_report_result.exit_code == 0
    assert json.loads(campaign_report_result.stdout)["summary"]["campaign_run_count"] == 1


def test_btc15m_slug_limit_conflict_returns_error(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "paper-run",
            "--slug",
            "btc-15m-up-down-1",
            "--limit",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["identifier"] == "limit"


def test_btc15m_live_mode_returns_hint(monkeypatch) -> None:
    class LiveModeService(FakeBtc15mStrategyService):
        def paper_run(
            self,
            *,
            limit: int = 20,
            slug: str | None = None,
            mode: str = "paper",
        ) -> Btc15mPaperRunResponse:
            _ = limit
            _ = slug
            _ = mode
            raise Btc15mOperatorHintError(
                "BTC15m live mode is reserved and not implemented in this paper-first step.",
                identifier="mode",
                hint={"next_steps": ["Use --mode paper for live-data paper testing."]},
            )

    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", LiveModeService)

    result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "paper-run",
            "--slug",
            "btc-15m-up-down-1",
            "--mode",
            "live",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["identifier"] == "mode"
    assert payload["hint"]["next_steps"] == ["Use --mode paper for live-data paper testing."]


def test_btc15m_no_candidate_error_includes_hint(monkeypatch) -> None:
    class NoCandidateService(FakeBtc15mStrategyService):
        def campaign_next_window(
            self,
            *,
            slug: str | None = None,
            mode: str = "paper",
        ) -> Btc15mCampaignNextWindowResponse:
            _ = slug
            _ = mode
            raise Btc15mOperatorHintError(
                "No recurring BTC 15m market candidate was found.",
                hint={
                    "next_steps": [
                        "pm market recurring list --query btc --interval 15m",
                        "pm strategy btc15m paper-run --slug <market_slug> --mode paper",
                    ]
                },
            )

    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", NoCandidateService)

    result = runner.invoke(app, ["strategy", "btc15m", "campaign", "next-window", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["message"] == "No recurring BTC 15m market candidate was found."
    assert payload["hint"]["next_steps"][0] == "pm market recurring list --query btc --interval 15m"


def test_btc15m_root_output_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["--output", "json", "strategy", "btc15m", "report"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["summary"]["paper_run_count"] == 1


def test_btc15m_terminal_live_json_requires_interactive_mode(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "terminal",
            "--current",
            "--mode",
            "live",
            "--confirm",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["identifier"] == "mode"


def test_btc15m_terminal_current_observe_only_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["strategy", "btc15m", "terminal", "--current", "--observe-only", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["attach_mode"] == "current_observe_only"
    assert payload["latest_snapshot"]["observe_only"] is True


def test_btc15m_terminal_follow_current_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["strategy", "btc15m", "terminal", "--follow-current", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["attach_mode"] == "current"
    assert payload["latest_snapshot"]["current_window_label"] == "10:30 - 10:45 UTC"
    assert payload["latest_snapshot"]["up_price"] == "0.31"
    assert payload["latest_snapshot"]["down_price"] == "0.69"
    assert payload["latest_snapshot"]["display"]["display_source"] == "page_exact"
    assert payload["latest_snapshot"]["page_mirror"]["display_source"] == "page_exact"
    assert payload["latest_snapshot"]["market_truth"]["derived_up_price_source"] == "midpoint"
    assert payload["latest_snapshot"]["terminal_presenter"]["strategy_source"] == "market_truth"


def test_btc15m_terminal_follow_current_arm_next_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "terminal",
            "--follow-current",
            "--arm-next",
            "--budget-usdc",
            "100",
            "--rungs",
            "40,30,30",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["latest_snapshot"]["paper_budget_usdc"] == "100"
    assert payload["latest_snapshot"]["rung_notionals_usdc"] == ["40", "30", "30"]
    assert payload["latest_snapshot"]["display"]["display_volume"] == "120K"


def test_btc15m_terminal_wait_next_json_accepts_budget_controls(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        [
            "strategy",
            "btc15m",
            "terminal",
            "--wait-next",
            "--budget-usdc",
            "60",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["attach_mode"] == "wait_next"
    assert payload["latest_snapshot"]["paper_budget_usdc"] == "60"


def test_btc15m_terminal_requires_exactly_one_session_target(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(app, ["strategy", "btc15m", "terminal", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["identifier"] == "mode"


def _legacy_test_btc15m_terminal_human_mode_runs(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["strategy", "btc15m", "terminal", "--current", "--mode", "paper"],
    )

    assert result.exit_code == 0
    assert "BTC15m Terminal" in result.stdout
    assert _format_cents_label("0.30") == "30¢"


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


def _display_truth() -> Btc15mTerminalDisplayTruth:
    return Btc15mTerminalDisplayTruth(
        display_price_to_beat="99.5",
        display_current_btc="100",
        display_up_price="0.31",
        display_down_price="0.69",
        display_countdown="09:00",
        display_volume="120K",
        display_source="page_exact",
        display_window_label="10:30 - 10:45 UTC",
    )


def _page_mirror() -> Btc15mTerminalPageMirror:
    return Btc15mTerminalPageMirror(**_display_truth().model_dump())


def _side_state(
    best_bid: str,
    best_ask: str,
    midpoint: str,
    spread: str,
    visible_liquidity_030: str,
    visible_liquidity_020: str,
    visible_liquidity_010: str,
) -> Btc15mDashboardSideState:
    return Btc15mDashboardSideState(
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=midpoint,
        spread=spread,
        visible_liquidity_030=visible_liquidity_030,
        visible_liquidity_020=visible_liquidity_020,
        visible_liquidity_010=visible_liquidity_010,
    )


def _market_truth() -> Btc15mTerminalMarketTruth:
    return Btc15mTerminalMarketTruth(
        market_slug="btc-updown-15m-1774002600",
        window_start_at="2026-03-20T10:30:00Z",
        window_end_at="2026-03-20T10:45:00Z",
        countdown_seconds=540,
        countdown="09:00",
        boundary_status="complete",
        direction_lock_status="UP",
        selected_side="UP",
        target_token_id="100",
        target_outcome="Up",
        current_chainlink_price="100",
        start_price_proxy_v1="99.5",
        paper_budget_usdc="50",
        rung_notionals_usdc=["20", "15", "15"],
        current_midpoint="0.28",
        current_spread="0.03",
        market_open_interest="150K",
        market_volume="120K",
        visible_liquidity_030="80",
        visible_liquidity_020="100",
        visible_liquidity_010="200",
        derived_up_price="0.28",
        derived_up_price_source="midpoint",
        derived_down_price="0.72",
        derived_down_price_source="midpoint",
        up_side=_side_state("0.30", "0.32", "0.31", "0.02", "80", "100", "200"),
        down_side=_side_state("0.68", "0.70", "0.69", "0.02", "70", "90", "120"),
        rungs=[
            Btc15mDashboardRungState(price="0.30", state="armed", visible_liquidity="80"),
            Btc15mDashboardRungState(price="0.20", state="armed", visible_liquidity="100"),
            Btc15mDashboardRungState(price="0.10", state="armed", visible_liquidity="200"),
        ],
        manipulation_flags=[],
    )


def _presenter() -> Btc15mTerminalPresenter:
    return Btc15mTerminalPresenter(
        primary_block_source="page_mirror",
        primary_block_state="exact",
        market_context_source="market_truth",
        strategy_source="market_truth",
        show_binance_diagnostics=False,
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


def _legacy_terminal_human_mode_runs_render_v2(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["strategy", "btc15m", "terminal", "--current", "--mode", "paper"],
    )

    assert result.exit_code == 0
    assert "BTC15m Terminal" in result.stdout
    assert "30¢" in result.stdout
    assert "Strategy" in result.stdout
    assert "Paper start" not in result.stdout


def test_btc15m_terminal_human_mode_runs(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["strategy", "btc15m", "terminal", "--current", "--mode", "paper"],
    )

    assert result.exit_code == 0
    assert "BTC15m Terminal" in result.stdout
    assert result.stdout.strip()
    assert "Paper start" not in result.stdout


def _legacy_terminal_human_mode_runs_render(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.strategy_btc15m.Btc15mStrategyService", FakeBtc15mStrategyService)

    result = runner.invoke(
        app,
        ["strategy", "btc15m", "terminal", "--current", "--mode", "paper"],
    )

    assert result.exit_code == 0
    assert "BTC15m Terminal" in result.stdout
    assert "30¢" in result.stdout
    assert "Derived Up" in result.stdout
    assert "Paper start" not in result.stdout
