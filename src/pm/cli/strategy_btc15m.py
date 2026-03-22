"""BTC15m research-strategy CLI surface."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import typer
from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.common.output import prompt_yes_no
from pm.common.tables import empty_message, render_group, row_table, section_panel, summary_table
from pm.strategy import (
    Btc15mAutoRollResponse,
    Btc15mCampaignNextWindowResponse,
    Btc15mCampaignReportResponse,
    Btc15mCampaignRunResponse,
    Btc15mDashboardResponse,
    Btc15mDashboardSnapshotRecord,
    Btc15mLiquiditySampleResponse,
    Btc15mLiveCheckResponse,
    Btc15mLiveResponse,
    Btc15mPaperRunResponse,
    Btc15mRecordStartResponse,
    Btc15mRecordWindowResponse,
    Btc15mReplayResponse,
    Btc15mReportResponse,
    Btc15mResolveCurrentResponse,
    Btc15mSessionArmResponse,
    Btc15mSessionBundleResponse,
    Btc15mSessionLatestResponse,
    Btc15mSessionReportResponse,
    Btc15mSessionRunResponse,
    Btc15mSessionStatusResponse,
    Btc15mSessionStopResponse,
    Btc15mStateError,
    Btc15mStrategyService,
    Btc15mTerminalDisplayTruth,
    Btc15mTerminalMarketTruth,
    Btc15mTerminalPageMirror,
    Btc15mTerminalPresenter,
    Btc15mTerminalReplayResponse,
    Btc15mTerminalReportResponse,
    Btc15mTerminalResponse,
    Btc15mValidationError,
)

app = typer.Typer(
    add_completion=False,
    help="BTC 15-minute Chainlink directional ladder research commands.",
    no_args_is_help=True,
)
record_app = typer.Typer(
    add_completion=False,
    help="Bounded BTC15m recorder commands.",
    no_args_is_help=True,
)
campaign_app = typer.Typer(
    add_completion=False,
    help="Bounded BTC15m campaign commands.",
    no_args_is_help=True,
)
liquidity_app = typer.Typer(
    add_completion=False,
    help="BTC15m liquidity sampling commands.",
    no_args_is_help=True,
)
terminal_app = typer.Typer(
    add_completion=False,
    help="Dense BTC15m operator terminal commands.",
    invoke_without_command=True,
    no_args_is_help=False,
)
session_app = typer.Typer(
    add_completion=False,
    help="Bounded BTC15m one-window session-controller commands.",
    no_args_is_help=True,
)

SECONDS_OPTION = typer.Option(
    60,
    "--seconds",
    min=1,
    help="Bounded recorder duration in seconds.",
)
SLUG_OPTION = typer.Option(
    ...,
    "--slug",
    help="Exact BTC15m market slug to record.",
)
FROM_OPTION = typer.Option(
    ...,
    "--from",
    help="Inclusive replay range start in ISO-8601 format.",
)
TO_OPTION = typer.Option(
    ...,
    "--to",
    help="Exclusive replay range end in ISO-8601 format.",
)
LIMIT_OPTION = typer.Option(
    20,
    "--limit",
    min=1,
    help="Maximum number of windows to paper-evaluate.",
)
HOURS_OPTION = typer.Option(
    ...,
    "--hours",
    help="Bounded campaign duration in hours.",
)
OPTIONAL_HOURS_OPTION = typer.Option(
    None,
    "--hours",
    help="Optional bounded current-window duration in hours.",
)
OPTIONAL_SLUG_OPTION = typer.Option(
    None,
    "--slug",
    help="Explicit BTC15m market slug target for direct paper runs and campaigns.",
)
MODE_OPTION = typer.Option(
    "paper",
    "--mode",
    help="BTC15m run mode: paper or live. Live remains reserved in this step.",
)
CURRENT_OPTION = typer.Option(
    False,
    "--current",
    help="Compatibility alias for --follow-current.",
)
FOLLOW_CURRENT_OPTION = typer.Option(
    False,
    "--follow-current",
    help="Follow the current active BTC15m window and auto-roll across slugs.",
)
ARM_NEXT_OPTION = typer.Option(
    False,
    "--arm-next",
    help="After the current BTC15m window, arm and trade the next eligible window too.",
)
WAIT_NEXT_OPTION = typer.Option(
    False,
    "--wait-next",
    help="Observe the current window and arm the next BTC15m window when capture opens.",
)
NEXT_OPTION = typer.Option(
    False,
    "--next",
    help="Arm the next eligible BTC15m window. Required for session arm in this step.",
)
OBSERVE_ONLY_OPTION = typer.Option(
    False,
    "--observe-only",
    help="Stay attached in observe-only mode instead of arming the current BTC15m window.",
)
CONFIRM_OPTION = typer.Option(
    False,
    "--confirm",
    help="Required for BTC15m live terminal mode.",
)
TERMINAL_BUDGET_OPTION = typer.Option(
    None,
    "--budget-usdc",
    help="Total terminal ladder budget in USDC. Defaults to 50 when omitted.",
)
TERMINAL_RUNGS_OPTION = typer.Option(
    None,
    "--rungs",
    help="Comma-separated terminal rung notionals in USDC, for example 20,15,15.",
)
SESSION_ID_OPTION = typer.Option(
    ...,
    "--session-id",
    help="Persisted BTC15m terminal session identifier.",
)
CONTROLLER_SESSION_ID_OPTION = typer.Option(
    ...,
    "--session-id",
    help="Persisted BTC15m controller session identifier.",
)
OPTIONAL_CONTROLLER_SESSION_ID_OPTION = typer.Option(
    None,
    "--session-id",
    help="Optional persisted BTC15m controller session identifier.",
)
LATEST_OPTION = typer.Option(
    False,
    "--latest",
    help="Resolve the newest actionable BTC15m controller session for this command.",
)
OPTIONAL_SESSION_ID_OPTION = typer.Option(
    None,
    "--session-id",
    help="Optional persisted BTC15m terminal session identifier.",
)
JSON_OPTION = LOCAL_JSON_OPTION


@record_app.command("start")
def record_start(
    ctx: typer.Context,
    seconds: int = SECONDS_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run one bounded BTC15m recorder session for the latest recurring market."""
    try:
        result = Btc15mStrategyService().record_start(seconds=seconds)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_record_response(result),
        renderable=_render_record_response(result),
        local_json_output=json_output,
    )


@record_app.command("window")
def record_window(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Record one specific BTC15m window through end-boundary capture or timeout."""
    try:
        result = Btc15mStrategyService().record_window(slug=slug)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, identifier=slug.strip(), json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_record_response(result),
        renderable=_render_record_response(result),
        local_json_output=json_output,
    )


@app.command("replay")
def replay(
    ctx: typer.Context,
    from_at: str = FROM_OPTION,
    to_at: str = TO_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Replay recorded BTC15m windows across a time range."""
    try:
        result = Btc15mStrategyService().replay(from_at=from_at, to_at=to_at)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_replay_response(result),
        renderable=_render_replay_response(result),
        local_json_output=json_output,
    )


@app.command("resolve-current")
def resolve_current(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Resolve the current BTC15m live or upcoming recurring window."""
    try:
        result = Btc15mStrategyService().resolve_current()
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_resolve_current_response(result),
        renderable=_render_resolve_current_response(result),
        local_json_output=json_output,
    )


@app.command("live")
def live_current(
    ctx: typer.Context,
    current: bool = CURRENT_OPTION,
    mode: str = MODE_OPTION,
    hours: str | None = OPTIONAL_HOURS_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run one bounded current-window BTC15m live-data paper session."""
    if not current:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="BTC15m live requires --current in this bounded current-window step.",
            resource="btc15m",
            identifier="current",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    try:
        result = Btc15mStrategyService().live_current(mode=mode, hours=hours)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_live_response(result),
        renderable=_render_live_response(result),
        local_json_output=json_output,
    )


@app.command("dashboard")
def dashboard_current(
    ctx: typer.Context,
    current: bool = CURRENT_OPTION,
    seconds: int = typer.Option(
        30,
        "--seconds",
        min=1,
        help="Bounded BTC15m dashboard duration in seconds.",
    ),
    json_output: bool = JSON_OPTION,
) -> None:
    """Run a bounded BTC15m current-window terminal dashboard."""
    if not current:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="BTC15m dashboard requires --current in this bounded current-window step.",
            resource="btc15m",
            identifier="current",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    try:
        if json_output:
            result = Btc15mStrategyService().dashboard_current(seconds=seconds)
        else:
            console = Console()
            latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
            with Live(empty_message("Starting BTC15m dashboard..."), console=console) as live:
                def _on_snapshot(snapshot: Btc15mDashboardSnapshotRecord) -> None:
                    nonlocal latest_snapshot
                    latest_snapshot = snapshot
                    live.update(_render_dashboard_snapshot(snapshot))

                result = Btc15mStrategyService().dashboard_current(
                    seconds=seconds,
                    on_snapshot=_on_snapshot,
                )
                if latest_snapshot is None and result.latest_snapshot is not None:
                    live.update(_render_dashboard_snapshot(result.latest_snapshot))
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_dashboard_response(result),
        renderable=_render_dashboard_response(result),
        local_json_output=json_output,
    )


@terminal_app.callback(invoke_without_command=True)
def terminal_current(
    ctx: typer.Context,
    current: bool = CURRENT_OPTION,
    follow_current: bool = FOLLOW_CURRENT_OPTION,
    arm_next: bool = ARM_NEXT_OPTION,
    wait_next: bool = WAIT_NEXT_OPTION,
    observe_only: bool = OBSERVE_ONLY_OPTION,
    mode: str = MODE_OPTION,
    confirm: bool = CONFIRM_OPTION,
    budget_usdc: str | None = TERMINAL_BUDGET_OPTION,
    rungs: str | None = TERMINAL_RUNGS_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run one dense BTC15m operator terminal session for the current window."""
    if ctx.invoked_subcommand is not None:
        return
    current_requested = current or follow_current
    if current_requested == wait_next:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message=(
                "BTC15m terminal requires exactly one of "
                "--follow-current/--current or --wait-next."
            ),
            resource="btc15m",
            identifier="mode",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    if wait_next and observe_only:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="BTC15m terminal --observe-only is only supported with --current.",
            resource="btc15m",
            identifier="observe_only",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    if wait_next and arm_next:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="BTC15m terminal --arm-next is only supported with --follow-current/--current.",
            resource="btc15m",
            identifier="arm_next",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    if json_output and mode.strip().lower() == "live":
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="BTC15m terminal JSON mode is only available in paper mode.",
            resource="btc15m",
            identifier="mode",
            local_json_output=json_output,
            hint={"next_steps": ["Run human terminal mode for live inline confirmations."]},
        )
        raise typer.Exit(1)
    if mode.strip().lower() == "live" and not confirm:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="BTC15m live terminal requires --mode live --confirm.",
            resource="btc15m",
            identifier="confirm",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    try:
        service = Btc15mStrategyService()
        if json_output:
            result = (
                service.terminal_current(
                    mode=mode,
                    confirm=confirm,
                    observe_only=observe_only,
                    arm_next=arm_next,
                    budget_usdc=budget_usdc,
                    rungs=rungs,
                    snapshot_only=True,
                    session_window_limit=1,
                )
                if current_requested
                else service.terminal_wait_next(
                    mode=mode,
                    confirm=confirm,
                    budget_usdc=budget_usdc,
                    rungs=rungs,
                    snapshot_only=True,
                    session_window_limit=1,
                )
            )
        else:
            console = Console()
            latest_snapshot: Btc15mDashboardSnapshotRecord | None = None

            def _confirm_action(message: str) -> bool | None:
                return prompt_yes_no(message, default=False)

            with Live(empty_message("Starting BTC15m terminal..."), console=console) as live_view:

                def _on_snapshot(snapshot: Btc15mDashboardSnapshotRecord) -> None:
                    nonlocal latest_snapshot
                    latest_snapshot = snapshot
                    live_view.update(_render_terminal_snapshot(snapshot))

                result = (
                    service.terminal_current(
                        mode=mode,
                        confirm=confirm,
                        observe_only=observe_only,
                        arm_next=arm_next,
                        budget_usdc=budget_usdc,
                        rungs=rungs,
                        session_window_limit=None,
                        on_snapshot=_on_snapshot,
                        confirm_action=_confirm_action if mode.strip().lower() == "live" else None,
                    )
                    if current_requested
                    else service.terminal_wait_next(
                        mode=mode,
                        confirm=confirm,
                        budget_usdc=budget_usdc,
                        rungs=rungs,
                        session_window_limit=1,
                        on_snapshot=_on_snapshot,
                        confirm_action=_confirm_action if mode.strip().lower() == "live" else None,
                    )
                )
                if latest_snapshot is None and result.latest_snapshot is not None:
                    live_view.update(_render_terminal_snapshot(result.latest_snapshot))
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_terminal_response(result),
        renderable=_render_terminal_response(result),
        local_json_output=json_output,
    )


@terminal_app.command("replay")
def terminal_replay(
    ctx: typer.Context,
    session_id: str = SESSION_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Replay one persisted BTC15m terminal session from stored snapshots only."""
    try:
        service = Btc15mStrategyService()
        if json_output:
            result = service.terminal_replay(session_id=session_id)
        else:
            console = Console()
            latest_snapshot: Btc15mDashboardSnapshotRecord | None = None
            with Live(
                empty_message("Replaying BTC15m terminal session..."),
                console=console,
            ) as live_view:

                def _on_snapshot(snapshot: Btc15mDashboardSnapshotRecord) -> None:
                    nonlocal latest_snapshot
                    latest_snapshot = snapshot
                    live_view.update(_render_terminal_snapshot(snapshot))

                result = service.terminal_replay(session_id=session_id, on_snapshot=_on_snapshot)
                if latest_snapshot is None and result.latest_snapshot is not None:
                    live_view.update(_render_terminal_snapshot(result.latest_snapshot))
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, identifier=session_id, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_terminal_replay_response(result),
        renderable=_render_terminal_replay_response(result),
        local_json_output=json_output,
    )


@terminal_app.command("report")
def terminal_report(
    ctx: typer.Context,
    session_id: str | None = OPTIONAL_SESSION_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show aggregate BTC15m terminal-session history."""
    try:
        result = Btc15mStrategyService().terminal_report(session_id=session_id)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, identifier=session_id, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_terminal_report_response(result),
        renderable=_render_terminal_report_response(result),
        local_json_output=json_output,
    )


@session_app.command("arm")
def session_arm(
    ctx: typer.Context,
    next_window: bool = NEXT_OPTION,
    mode: str = MODE_OPTION,
    budget_usdc: str | None = TERMINAL_BUDGET_OPTION,
    rungs: str | None = TERMINAL_RUNGS_OPTION,
    confirm: bool = CONFIRM_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Arm one bounded BTC15m controller session for the next window."""
    try:
        result = Btc15mStrategyService().session_arm(
            next_window=next_window,
            mode=mode,
            budget_usdc=budget_usdc,
            rungs=rungs,
            confirm=confirm,
        )
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_arm_response(result),
        renderable=_render_session_arm_response(result),
        local_json_output=json_output,
    )


@session_app.command("status")
def session_status(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show the compact BTC15m controller queue and active-session snapshot."""
    try:
        result = Btc15mStrategyService().session_status()
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_status_response(result),
        renderable=_render_session_status_response(result),
        local_json_output=json_output,
    )


@session_app.command("latest")
def session_latest(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show the latest persisted BTC15m controller session."""
    try:
        result = Btc15mStrategyService().session_latest()
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_latest_response(result),
        renderable=_render_session_latest_response(result),
        local_json_output=json_output,
    )


@session_app.command("run")
def session_run(
    ctx: typer.Context,
    session_id: str | None = OPTIONAL_CONTROLLER_SESSION_ID_OPTION,
    latest: bool = LATEST_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run one armed BTC15m controller session end-to-end."""
    try:
        if session_id is None and not latest:
            raise Btc15mValidationError("BTC15m session run requires --session-id or --latest.")
        result = Btc15mStrategyService().session_run(session_id=session_id, latest=latest)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, identifier=session_id, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_run_response(result),
        renderable=_render_session_run_response(result),
        local_json_output=json_output,
    )


@session_app.command("stop")
def session_stop(
    ctx: typer.Context,
    session_id: str = CONTROLLER_SESSION_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Request a safe stop for one bounded BTC15m controller session."""
    try:
        result = Btc15mStrategyService().session_stop(session_id=session_id)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, identifier=session_id, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_stop_response(result),
        renderable=_render_session_stop_response(result),
        local_json_output=json_output,
    )


@session_app.command("report")
def session_report(
    ctx: typer.Context,
    session_id: str | None = OPTIONAL_CONTROLLER_SESSION_ID_OPTION,
    latest: bool = LATEST_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show one persisted BTC15m controller-session report."""
    try:
        if session_id is None and not latest:
            raise Btc15mValidationError(
                "BTC15m session report requires --session-id or --latest."
            )
        result = Btc15mStrategyService().session_report(session_id=session_id, latest=latest)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, identifier=session_id, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_report_response(result),
        renderable=_render_session_report_response(result),
        local_json_output=json_output,
    )


@app.command("live-check")
def live_check(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run a read-only BTC15m live-readiness checklist."""
    try:
        result = Btc15mStrategyService().live_check()
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_live_check_response(result),
        renderable=_render_live_check_response(result),
        local_json_output=json_output,
    )


@app.command("bundle")
def bundle(
    ctx: typer.Context,
    session_id: str = CONTROLLER_SESSION_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show one local persisted BTC15m post-session bundle."""
    try:
        result = Btc15mStrategyService().bundle(session_id=session_id)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, identifier=session_id, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_bundle_response(result),
        renderable=_render_bundle_response(result),
        local_json_output=json_output,
    )


@app.command("auto-roll")
def auto_roll(
    ctx: typer.Context,
    hours: str = HOURS_OPTION,
    mode: str = MODE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run one bounded BTC15m current-window auto-roll session."""
    try:
        result = Btc15mStrategyService().auto_roll(hours=hours, mode=mode)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_auto_roll_response(result),
        renderable=_render_auto_roll_response(result),
        local_json_output=json_output,
    )


@app.command("paper-run")
def paper_run(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    slug: str | None = OPTIONAL_SLUG_OPTION,
    mode: str = MODE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Paper-evaluate completed BTC15m windows chronologically."""
    normalized_slug = slug.strip() if slug is not None else None
    limit_source = ctx.get_parameter_source("limit")
    if normalized_slug:
        if getattr(limit_source, "name", "") == "COMMANDLINE" and limit != 1:
            emit_command_error(
                ctx,
                code="invalid_argument",
                message="When --slug is provided, --limit must be exactly 1 for BTC15m paper runs.",
                resource="btc15m",
                identifier="limit",
                local_json_output=json_output,
            )
            raise typer.Exit(1)
        limit = 1
    try:
        result = Btc15mStrategyService().paper_run(limit=limit, slug=slug, mode=mode)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_paper_run_response(result),
        renderable=_render_paper_run_response(result),
        local_json_output=json_output,
    )


@liquidity_app.command("sample")
def liquidity_sample(
    ctx: typer.Context,
    seconds: int = typer.Option(
        30,
        "--seconds",
        min=1,
        help="Bounded BTC15m liquidity-sampling duration in seconds.",
    ),
    json_output: bool = JSON_OPTION,
) -> None:
    """Sample BTC15m Binance and Polymarket liquidity context for the current window."""
    try:
        result = Btc15mStrategyService().liquidity_sample(seconds=seconds)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_liquidity_response(result),
        renderable=_render_liquidity_response(result),
        local_json_output=json_output,
    )


@campaign_app.command("next-window")
def campaign_next_window(
    ctx: typer.Context,
    slug: str | None = OPTIONAL_SLUG_OPTION,
    mode: str = MODE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Return the current unresolved or next distinct BTC15m campaign window."""
    try:
        result = Btc15mStrategyService().campaign_next_window(slug=slug, mode=mode)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_campaign_next_window_response(result),
        renderable=_render_campaign_next_window_response(result),
        local_json_output=json_output,
    )


@campaign_app.command("run")
def campaign_run(
    ctx: typer.Context,
    hours: str = HOURS_OPTION,
    slug: str | None = OPTIONAL_SLUG_OPTION,
    mode: str = MODE_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run a bounded sequential BTC15m campaign."""
    try:
        result = Btc15mStrategyService().campaign_run(hours=hours, slug=slug, mode=mode)
    except (Btc15mValidationError, Btc15mStateError) as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_campaign_run_response(result),
        renderable=_render_campaign_run_response(result),
        local_json_output=json_output,
    )


@campaign_app.command("report")
def campaign_report(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show an aggregate BTC15m campaign report."""
    try:
        result = Btc15mStrategyService().campaign_report()
    except Btc15mStateError as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_campaign_report_response(result),
        renderable=_render_campaign_report_response(result),
        local_json_output=json_output,
    )


@app.command("report")
def report(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show an aggregate BTC15m research report from persisted state."""
    try:
        result = Btc15mStrategyService().report()
    except Btc15mStateError as exc:
        _emit_btc15m_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_report(result),
        renderable=_render_report(result),
        local_json_output=json_output,
    )


def _emit_btc15m_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    identifier: str | None = None,
    json_output: bool,
) -> None:
    code = "state_error" if isinstance(exc, Btc15mStateError) else "invalid_argument"
    emit_command_error(
        ctx,
        code=code,
        message=str(exc),
        resource="btc15m",
        identifier=identifier or getattr(exc, "identifier", None),
        local_json_output=json_output,
        hint=getattr(exc, "hint", None),
    )


def _format_record_response(
    response: Btc15mRecordStartResponse | Btc15mRecordWindowResponse,
) -> str:
    if not response.items:
        return "No BTC15m windows were recorded."
    latest = response.items[-1]
    return "\n".join(
        [
            f"Recorder session: {response.session_id}",
            f"Recorded windows: {response.total}",
            f"Latest market: {latest.window.market_slug}",
            f"Boundary status: {latest.boundary_status}",
            f"Decision: {latest.decision}",
            f"Resolution: {latest.resolution_result}",
        ]
    )


def _render_record_response(
    response: Btc15mRecordStartResponse | Btc15mRecordWindowResponse,
) -> RenderableType:
    summary = summary_table(
        title="Recorder Summary",
        rows=[
            ("Session", response.session_id),
            ("Windows", str(response.total)),
            ("Requested seconds", str(response.requested_seconds or "-")),
            ("Errors", str(len(response.errors))),
        ],
    )
    if not response.items:
        return section_panel("BTC15m Recorder", render_group(summary, empty_message("No windows.")))
    rows = (
        (
            item.window.market_slug,
            item.status,
            item.boundary_status,
            item.decision,
            item.resolution_result,
        )
        for item in response.items
    )
    table = row_table(
        title="Recorded Windows",
        columns=("Market", "Status", "Boundaries", "Decision", "Resolution"),
        rows=rows,
    )
    return section_panel("BTC15m Recorder", render_group(summary, table))


def _format_replay_response(response: Btc15mReplayResponse) -> str:
    return "\n".join(
        [
            f"Replay id: {response.replay.replay_id}",
            f"Windows replayed: {response.replay.total}",
            f"Range: {response.replay.from_at} -> {response.replay.to_at}",
        ]
    )


def _render_replay_response(response: Btc15mReplayResponse) -> RenderableType:
    items = response.replay.items
    table = (
        row_table(
            title="Replay Windows",
            columns=("Market", "Decision", "Resolution", "PnL"),
            rows=(
                (
                    item.market_slug,
                    item.decision,
                    item.resolution_result,
                    item.realized_pnl_usdc,
                )
                for item in items
            ),
        )
        if items
        else empty_message("No replay windows.")
    )
    return section_panel("BTC15m Replay", table)


def _format_resolve_current_response(response: Btc15mResolveCurrentResponse) -> str:
    if response.window is None:
        return "No current BTC15m window was resolved."
    seconds_to_start = response.seconds_to_start
    seconds_to_end = response.seconds_to_end
    return "\n".join(
        [
            f"Market: {response.window.market_slug}",
            f"Status: {response.status}",
            f"Timing source: {response.timing_source}",
            f"Seconds to start: {seconds_to_start if seconds_to_start is not None else '-'}",
            f"Seconds to end: {seconds_to_end if seconds_to_end is not None else '-'}",
        ]
    )


def _render_resolve_current_response(response: Btc15mResolveCurrentResponse) -> RenderableType:
    if response.window is None:
        return section_panel("BTC15m Resolve", empty_message("No current BTC15m window."))
    return section_panel(
        "BTC15m Resolve",
        summary_table(
            title="Current Window",
            rows=[
                ("Market", response.window.market_slug),
                ("Status", response.status),
                ("Timing source", response.timing_source),
                ("Selection source", response.selection_source),
                ("Window start", response.window.window_start_at or "-"),
                ("Window end", response.window.window_end_at or "-"),
                ("Seconds to start", str(response.seconds_to_start or 0)),
                ("Seconds to end", str(response.seconds_to_end or 0)),
            ],
        ),
    )


def _format_live_response(response: Btc15mLiveResponse) -> str:
    realized_pnl = (
        response.evaluation.realized_pnl_usdc if response.evaluation is not None else "-"
    )
    return "\n".join(
        [
            f"Live run: {response.run_id}",
            f"Mode: {response.mode}",
            f"Stop reason: {response.stop_reason}",
            f"Market: {response.window.market_slug if response.window is not None else '-'}",
            f"Realized PnL: {realized_pnl}",
        ]
    )


def _render_live_response(response: Btc15mLiveResponse) -> RenderableType:
    return section_panel(
        "BTC15m Live Paper",
        render_group(
            summary_table(
                title="Run Summary",
                rows=[
                    ("Run", response.run_id),
                    ("Mode", str(response.mode)),
                    ("Stop reason", response.stop_reason),
                    ("Market", response.window.market_slug if response.window is not None else "-"),
                    (
                        "Window start",
                        (response.window.window_start_at or "-") if response.window else "-",
                    ),
                    (
                        "Window end",
                        (response.window.window_end_at or "-") if response.window else "-",
                    ),
                ],
            ),
            (
                row_table(
                    title="Evaluation",
                    columns=("Decision", "Resolution", "Fills", "PnL"),
                    rows=[
                        (
                            response.evaluation.decision,
                            response.evaluation.resolution_result,
                            str(response.evaluation.filled_rung_count),
                            response.evaluation.realized_pnl_usdc,
                        )
                    ],
                )
                if response.evaluation is not None
                else empty_message("No evaluation was produced.")
            ),
        ),
    )


def _format_paper_run_response(response: Btc15mPaperRunResponse) -> str:
    return "\n".join(
        [
            f"Paper run: {response.run.run_id}",
            f"Mode: {response.run.mode}",
            f"Target slug: {response.run.target_slug or '-'}",
            f"Evaluated windows: {response.run.total_evaluated}",
            f"Skipped windows: {response.run.total_skipped}",
            f"Total realized PnL: {response.run.total_realized_pnl_usdc}",
        ]
    )


def _format_liquidity_response(response: Btc15mLiquiditySampleResponse) -> str:
    return "\n".join(
        [
            f"Liquidity session: {response.session_id}",
            f"Samples: {response.total}",
            f"Requested seconds: {response.requested_seconds}",
            f"Errors: {len(response.errors)}",
        ]
    )


def _render_paper_run_response(response: Btc15mPaperRunResponse) -> RenderableType:
    summary = summary_table(
        title="Paper Run Summary",
        rows=[
            ("Run", response.run.run_id),
            ("Mode", response.run.mode),
            ("Target slug", response.run.target_slug or "-"),
            ("Evaluated", str(response.run.total_evaluated)),
            ("Skipped", str(response.run.total_skipped)),
            ("Realized PnL", response.run.total_realized_pnl_usdc),
        ],
    )
    items = response.run.items
    table = (
        row_table(
            title="Paper Evaluations",
            columns=("Market", "Decision", "Fills", "Resolution", "PnL"),
            rows=(
                (
                    item.market_slug,
                    item.decision,
                    str(item.filled_rung_count),
                    item.resolution_result,
                    item.realized_pnl_usdc,
                )
                for item in items
            ),
        )
        if items
        else empty_message("No eligible completed windows.")
    )
    return section_panel("BTC15m Paper Run", render_group(summary, table))


def _render_liquidity_response(response: Btc15mLiquiditySampleResponse) -> RenderableType:
    summary = summary_table(
        title="Liquidity Summary",
        rows=[
            ("Session", response.session_id),
            ("Samples", str(response.total)),
            ("Requested seconds", str(response.requested_seconds)),
            ("Errors", str(len(response.errors))),
        ],
    )
    items = (
        row_table(
            title="Liquidity Samples",
            columns=("Sample", "Market", "Kind", "1m vol bps", "3m vol bps"),
            rows=(
                (
                    item.sample_id,
                    item.market_slug,
                    item.sample_kind,
                    item.binance.realized_vol_1m_bps or "-",
                    item.binance.realized_vol_3m_bps or "-",
                )
                for item in response.items
            ),
        )
        if response.items
        else empty_message("No liquidity samples.")
    )
    return section_panel("BTC15m Liquidity", render_group(summary, items))


def _format_dashboard_response(response: Btc15mDashboardResponse) -> str:
    return "\n".join(
        [
            f"Dashboard session: {response.session_id}",
            f"Snapshots: {response.total_snapshots}",
            f"Market: {response.window.market_slug if response.window is not None else '-'}",
        ]
    )


def _render_dashboard_snapshot(snapshot: Btc15mDashboardSnapshotRecord) -> RenderableType:
    rung_rows = [
        (
            rung.price,
            rung.state,
            rung.visible_liquidity or "-",
            rung.fill_at or "-",
        )
        for rung in snapshot.rungs
    ]
    rung_table = row_table(
        title="Ladder",
        columns=("Price", "State", "Visible liquidity", "Fill at"),
        rows=rung_rows,
    )
    summary = summary_table(
        title="Snapshot",
        rows=[
            ("Market", snapshot.market_slug),
            ("Sampled at", snapshot.sampled_at),
            ("Window", f"{snapshot.window_start_at or '-'} -> {snapshot.window_end_at or '-'}"),
            ("Chainlink", snapshot.current_chainlink_price or "-"),
            ("Binance", snapshot.current_binance_price or "-"),
            ("Start proxy", snapshot.start_price_proxy_v1 or "-"),
            ("Direction", snapshot.direction_lock_status),
            ("Midpoint", snapshot.current_midpoint or "-"),
            ("Spread", snapshot.current_spread or "-"),
            ("Flags", ", ".join(snapshot.manipulation_flags) or "-"),
            ("MFE / MAE", f"{snapshot.mfe_usdc or '-'} / {snapshot.mae_usdc or '-'}"),
        ],
    )
    return section_panel("BTC15m Dashboard", render_group(summary, rung_table))


def _render_dashboard_response(response: Btc15mDashboardResponse) -> RenderableType:
    if response.latest_snapshot is None:
        return section_panel("BTC15m Dashboard", empty_message("No dashboard snapshots."))
    summary = summary_table(
        title="Session Summary",
        rows=[
            ("Session", response.session_id),
            ("Snapshots", str(response.total_snapshots)),
            ("Requested seconds", str(response.requested_seconds)),
            ("Market", response.window.market_slug if response.window is not None else "-"),
        ],
    )
    return section_panel(
        "BTC15m Dashboard",
        render_group(summary, _render_dashboard_snapshot(response.latest_snapshot)),
    )


def _format_terminal_response(response: Btc15mTerminalResponse) -> str:
    state = response.session.final_state if response.session is not None else "-"
    return "\n".join(
        [
            f"Terminal session: {response.session_id}",
            f"Mode: {response.mode}",
            f"Attach mode: {response.attach_mode}",
            f"Stop reason: {response.stop_reason}",
            f"Final state: {state}",
            f"Market: {response.window.market_slug if response.window is not None else '-'}",
        ]
    )


def _format_cents_label(value: str | None) -> str:
    if value is None:
        return "-"
    normalized = value.strip()
    if not normalized:
        return "-"
    try:
        cents = (Decimal(normalized) * Decimal("100")).quantize(Decimal("1"))
    except InvalidOperation:
        return f"{normalized}\u00a2"
    return f"{cents}\u00a2"


def _terminal_rung_counts(snapshot: Btc15mDashboardSnapshotRecord) -> str:
    filled = sum(1 for item in snapshot.rungs if item.state == "filled")
    posted = sum(1 for item in snapshot.rungs if item.state == "posted")
    cancelled = sum(1 for item in snapshot.rungs if item.state == "cancelled")
    return f"{filled} / {posted} / {cancelled}"


def _snapshot_display_truth(snapshot: Btc15mDashboardSnapshotRecord) -> Btc15mTerminalDisplayTruth:
    if snapshot.page_mirror is not None:
        return snapshot.page_mirror
    if snapshot.display is not None:
        return snapshot.display
    return Btc15mTerminalPageMirror(
        display_price_to_beat=snapshot.price_to_beat,
        display_current_btc=snapshot.current_live_btc_price,
        display_up_price=snapshot.up_price,
        display_down_price=snapshot.down_price,
        display_countdown=(
            _format_countdown(snapshot.countdown_seconds)
            if snapshot.countdown_seconds is not None
            else None
        ),
        display_volume=snapshot.display_volume,
        display_source=snapshot.page_parity_source,
        display_window_label=snapshot.current_window_label,
        display_url=snapshot.page_parity_url,
        display_notes=[],
    )


def _snapshot_market_truth(snapshot: Btc15mDashboardSnapshotRecord) -> Btc15mTerminalMarketTruth:
    if snapshot.market_truth is not None:
        return snapshot.market_truth
    return Btc15mTerminalMarketTruth(
        market_slug=snapshot.market_slug,
        window_start_at=snapshot.window_start_at,
        window_end_at=snapshot.window_end_at,
        countdown_seconds=snapshot.countdown_seconds,
        countdown=_format_countdown(snapshot.countdown_seconds),
        boundary_status=snapshot.boundary_status,
        direction_lock_status=snapshot.direction_lock_status,
        selected_side=snapshot.selected_side,
        target_token_id=snapshot.target_token_id,
        target_outcome=snapshot.target_outcome,
        current_chainlink_price=snapshot.current_chainlink_price,
        start_price_proxy_v1=snapshot.start_price_proxy_v1,
        paper_budget_usdc=snapshot.paper_budget_usdc,
        rung_notionals_usdc=list(snapshot.rung_notionals_usdc),
        avg_entry_price=snapshot.avg_entry_price,
        exposure_quantity=snapshot.exposure_quantity,
        exposure_notional_usdc=snapshot.exposure_notional_usdc,
        current_midpoint=snapshot.current_midpoint,
        current_spread=snapshot.current_spread,
        market_open_interest=snapshot.market_open_interest,
        market_volume=snapshot.market_volume,
        visible_liquidity_030=snapshot.visible_liquidity_030,
        visible_liquidity_020=snapshot.visible_liquidity_020,
        visible_liquidity_010=snapshot.visible_liquidity_010,
        derived_up_price=getattr(snapshot, "derived_up_price", None),
        derived_up_price_source=getattr(snapshot, "derived_up_price_source", None),
        derived_down_price=getattr(snapshot, "derived_down_price", None),
        derived_down_price_source=getattr(snapshot, "derived_down_price_source", None),
        up_side=snapshot.up_side,
        down_side=snapshot.down_side,
        rungs=list(snapshot.rungs),
        manipulation_flags=list(snapshot.manipulation_flags),
    )


def _snapshot_terminal_presenter(
    snapshot: Btc15mDashboardSnapshotRecord,
) -> Btc15mTerminalPresenter:
    if snapshot.terminal_presenter is not None:
        return snapshot.terminal_presenter
    display = _snapshot_display_truth(snapshot)
    market_truth = _snapshot_market_truth(snapshot)
    page_state = "unavailable"
    if display.display_stale and display.display_source == "page_unavailable":
        page_state = "stale"
    elif display.display_source == "page_exact":
        page_state = "exact"
    show_binance = page_state != "exact" or any(
        "binance" in flag or "divergence" in flag for flag in market_truth.manipulation_flags
    )
    return Btc15mTerminalPresenter(
        primary_block_state=page_state,
        show_binance_diagnostics=show_binance,
    )


def _record_display_truth(record: object) -> Btc15mTerminalDisplayTruth:
    page_mirror = getattr(record, "page_mirror", None)
    if isinstance(page_mirror, Btc15mTerminalDisplayTruth):
        return page_mirror
    display = getattr(record, "display", None)
    if isinstance(display, Btc15mTerminalDisplayTruth):
        return display
    countdown_seconds = getattr(record, "countdown_seconds", None)
    return Btc15mTerminalPageMirror(
        display_price_to_beat=getattr(record, "price_to_beat", None),
        display_current_btc=getattr(record, "current_live_btc_price", None),
        display_up_price=getattr(record, "up_price", None),
        display_down_price=getattr(record, "down_price", None),
        display_countdown=_format_countdown(countdown_seconds),
        display_volume=getattr(record, "display_volume", None),
        display_source=getattr(record, "page_parity_source", None),
        display_window_label=getattr(record, "current_window_label", None),
        display_url=getattr(record, "page_parity_url", None),
        display_observed_at=None,
        display_stale=False,
        display_notes=[],
    )


def _record_market_truth(record: object) -> Btc15mTerminalMarketTruth:
    market_truth = getattr(record, "market_truth", None)
    if isinstance(market_truth, Btc15mTerminalMarketTruth):
        return market_truth
    countdown_seconds = getattr(record, "countdown_seconds", None)
    return Btc15mTerminalMarketTruth(
        market_slug=getattr(record, "market_slug", "-"),
        window_start_at=getattr(record, "window_start_at", None),
        window_end_at=getattr(record, "window_end_at", None),
        countdown_seconds=countdown_seconds,
        countdown=_format_countdown(countdown_seconds),
        boundary_status=getattr(record, "boundary_status", "pending"),
        direction_lock_status=getattr(record, "direction_lock_status", "pending"),
        selected_side=getattr(record, "selected_side", None),
        target_token_id=getattr(record, "target_token_id", None),
        target_outcome=getattr(record, "target_outcome", None),
        current_chainlink_price=getattr(record, "current_chainlink_price", None),
        start_price_proxy_v1=getattr(record, "start_price_proxy_v1", None),
        end_price_proxy_v1=getattr(record, "end_price_proxy_v1", None),
        paper_budget_usdc=getattr(record, "paper_budget_usdc", None),
        rung_notionals_usdc=list(getattr(record, "rung_notionals_usdc", [])),
        avg_entry_price=getattr(record, "avg_entry_price", None),
        exposure_quantity=getattr(record, "exposure_quantity", None),
        exposure_notional_usdc=getattr(record, "exposure_notional_usdc", None),
        current_midpoint=getattr(record, "current_midpoint", None),
        current_spread=getattr(record, "current_spread", None),
        market_open_interest=getattr(record, "market_open_interest", None),
        market_volume=getattr(record, "market_volume", None),
        visible_liquidity_030=getattr(record, "visible_liquidity_030", None),
        visible_liquidity_020=getattr(record, "visible_liquidity_020", None),
        visible_liquidity_010=getattr(record, "visible_liquidity_010", None),
        derived_up_price=getattr(record, "derived_up_price", None),
        derived_up_price_source=getattr(record, "derived_up_price_source", None),
        derived_down_price=getattr(record, "derived_down_price", None),
        derived_down_price_source=getattr(record, "derived_down_price_source", None),
        up_side=getattr(record, "up_side", None),
        down_side=getattr(record, "down_side", None),
        rungs=list(getattr(record, "rungs", [])),
        manipulation_flags=list(getattr(record, "manipulation_flags", [])),
    )


def _record_terminal_presenter(record: object) -> Btc15mTerminalPresenter:
    presenter = getattr(record, "terminal_presenter", None)
    if isinstance(presenter, Btc15mTerminalPresenter):
        return presenter
    display = _record_display_truth(record)
    market_truth = _record_market_truth(record)
    page_state = "unavailable"
    if display.display_stale and display.display_source == "page_unavailable":
        page_state = "stale"
    elif display.display_source == "page_exact":
        page_state = "exact"
    show_binance = page_state != "exact" or any(
        "binance" in flag or "divergence" in flag for flag in market_truth.manipulation_flags
    )
    return Btc15mTerminalPresenter(
        primary_block_state=page_state,
        show_binance_diagnostics=show_binance,
    )


def _format_countdown(countdown_seconds: int | None) -> str | None:
    if countdown_seconds is None:
        return None
    if countdown_seconds < 0:
        countdown_seconds = 0
    minutes, seconds = divmod(countdown_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_market_truth_price(value: str | None, source: str | None) -> str:
    if value is None:
        return "-"
    if source is None:
        return value
    return f"{value} ({source})"


def _render_terminal_snapshot_legacy(snapshot: Btc15mDashboardSnapshotRecord) -> RenderableType:
    display = _snapshot_display_truth(snapshot)
    market_truth = _snapshot_market_truth(snapshot)
    presenter = _snapshot_terminal_presenter(snapshot)
    show_binance = presenter.show_binance_diagnostics
    header = summary_table(
        title="Session",
        rows=[
            ("Market", snapshot.market_slug),
            ("Window label", display.display_window_label or "-"),
            ("Mode", str(snapshot.mode)),
            ("State", snapshot.window_status),
            ("Countdown", display.display_countdown or market_truth.countdown or "-"),
            ("Attach", snapshot.attach_mode),
            ("Observe only", "yes" if snapshot.observe_only else "no"),
        ],
    )
    market_focus = summary_table(
        title=presenter.page_block_title,
        rows=[
            ("Price to beat", display.display_price_to_beat or "-"),
            ("Current price", display.display_current_btc or "-"),
            ("Up", display.display_up_price or "-"),
            ("Down", display.display_down_price or "-"),
            ("Countdown", display.display_countdown or "-"),
            ("Window", display.display_window_label or snapshot.market_slug),
            ("Display source", display.display_source or "-"),
            ("Observed", display.display_observed_at or "-"),
            ("Stale", "yes" if display.display_stale else "no"),
        ],
    )
    strategy = summary_table(
        title=presenter.strategy_block_title,
        rows=[
            ("Selected side", market_truth.selected_side or "-"),
            ("Status", market_truth.direction_lock_status),
            ("Boundary", market_truth.boundary_status),
            ("Chainlink start", market_truth.start_price_proxy_v1 or "-"),
            ("Budget", market_truth.paper_budget_usdc or "-"),
            ("Avg entry", market_truth.avg_entry_price or "-"),
            ("Exposure", market_truth.exposure_notional_usdc or "-"),
            ("Filled / posted / cancelled", _terminal_rung_counts(snapshot)),
        ],
    )
    ladder = row_table(
        title="Ladder",
        columns=("Level", "State", "Notional", "Qty", "Fill"),
        rows=[
            (
                _format_cents_label(rung.price),
                rung.state,
                rung.notional_usdc or "-",
                rung.quantity or "-",
                rung.fill_at or rung.cancellation_at or "-",
            )
            for rung in snapshot.rungs
        ],
    )
    market_context = row_table(
        title="Polymarket",
        columns=("Side", "Bid", "Ask", "Mid", "Spread", "30¢", "20¢", "10¢"),
        rows=[
            (
                "Up",
                snapshot.up_side.best_bid or "-" if snapshot.up_side is not None else "-",
                snapshot.up_side.best_ask or "-" if snapshot.up_side is not None else "-",
                snapshot.up_side.midpoint or "-" if snapshot.up_side is not None else "-",
                snapshot.up_side.spread or "-" if snapshot.up_side is not None else "-",
                snapshot.up_side.visible_liquidity_030 or "-"
                if snapshot.up_side is not None
                else "-",
                snapshot.up_side.visible_liquidity_020 or "-"
                if snapshot.up_side is not None
                else "-",
                snapshot.up_side.visible_liquidity_010 or "-"
                if snapshot.up_side is not None
                else "-",
            ),
            (
                "Down",
                snapshot.down_side.best_bid or "-" if snapshot.down_side is not None else "-",
                snapshot.down_side.best_ask or "-" if snapshot.down_side is not None else "-",
                snapshot.down_side.midpoint or "-" if snapshot.down_side is not None else "-",
                snapshot.down_side.spread or "-" if snapshot.down_side is not None else "-",
                snapshot.down_side.visible_liquidity_030 or "-"
                if snapshot.down_side is not None
                else "-",
                snapshot.down_side.visible_liquidity_020 or "-"
                if snapshot.down_side is not None
                else "-",
                snapshot.down_side.visible_liquidity_010 or "-"
                if snapshot.down_side is not None
                else "-",
            ),
        ],
    )
    context_summary = summary_table(
        title="Market Context",
        rows=[
            (
                "Spread / midpoint",
                f"{snapshot.current_spread or '-'} / {snapshot.current_midpoint or '-'}",
            ),
            ("Visible @30¢", snapshot.visible_liquidity_030 or "-"),
            ("Visible @20¢", snapshot.visible_liquidity_020 or "-"),
            ("Visible @10¢", snapshot.visible_liquidity_010 or "-"),
            ("Open interest", snapshot.market_open_interest or "-"),
            ("Volume", display.display_volume or "-"),
            ("Flags", ", ".join(snapshot.manipulation_flags) or "-"),
            ("Notes", ", ".join(display.display_notes) or "-"),
        ],
    )
    binance = summary_table(
        title="Binance Diagnostics",
        rows=[
            ("Spot", snapshot.current_binance_price or "-"),
            (
                "Best bid / ask",
                f"{snapshot.binance_best_bid or '-'} / {snapshot.binance_best_ask or '-'}",
            ),
            (
                "Near-touch depth",
                (
                    f"{snapshot.binance_near_touch_bid_depth or '-'} / "
                    f"{snapshot.binance_near_touch_ask_depth or '-'}"
                ),
            ),
            ("Imbalance", snapshot.binance_near_touch_imbalance or "-"),
        ],
    )
    events = row_table(
        title="Event Tape",
        columns=("At", "Kind", "Status", "Message"),
        rows=[
            (event.event_at, event.kind, event.status, event.message)
            for event in snapshot.latest_events
        ],
    ) if snapshot.latest_events else empty_message("No terminal events yet.")
    layout = Layout()
    layout.split_column(
        Layout(Panel(header, title="BTC15m Terminal"), size=8),
        Layout(name="body"),
        Layout(Panel(events, title="Event Tape"), size=9),
    )
    layout["body"].split_row(
        Layout(
            render_group(
                Panel(market_focus, title="Page"),
                Panel(strategy, title="Strategy"),
                Panel(ladder, title="Ladder"),
            ),
            name="left",
            ratio=2,
        ),
        Layout(
            render_group(
                Panel(market_context, title="Polymarket"),
                Panel(context_summary, title="Market"),
                Panel(binance, title="Binance") if show_binance else empty_message(""),
            ),
            name="right",
            ratio=2,
        ),
    )
    return layout


def _render_terminal_snapshot(snapshot: Btc15mDashboardSnapshotRecord) -> RenderableType:
    display = _snapshot_display_truth(snapshot)
    market_truth = _snapshot_market_truth(snapshot)
    presenter = _snapshot_terminal_presenter(snapshot)
    show_binance = presenter.show_binance_diagnostics
    header = summary_table(
        title="Session",
        rows=[
            ("Market", snapshot.market_slug),
            ("Window label", display.display_window_label or "-"),
            ("Mode", str(snapshot.mode)),
            ("State", snapshot.window_status),
            ("Countdown", display.display_countdown or market_truth.countdown or "-"),
            ("Attach", snapshot.attach_mode),
            ("Observe only", "yes" if snapshot.observe_only else "no"),
        ],
    )
    market_focus = summary_table(
        title=presenter.page_block_title,
        rows=[
            ("Price to beat", display.display_price_to_beat or "-"),
            ("Current price", display.display_current_btc or "-"),
            ("Up", display.display_up_price or "-"),
            ("Down", display.display_down_price or "-"),
            ("Countdown", display.display_countdown or market_truth.countdown or "-"),
            ("Window", display.display_window_label or snapshot.market_slug),
            ("Display source", display.display_source or "-"),
            ("Observed", display.display_observed_at or "-"),
            ("Stale", "yes" if display.display_stale else "no"),
        ],
    )
    strategy = summary_table(
        title=presenter.strategy_block_title,
        rows=[
            ("Selected side", market_truth.selected_side or "-"),
            ("Status", market_truth.direction_lock_status),
            ("Boundary", market_truth.boundary_status),
            ("Chainlink start", market_truth.start_price_proxy_v1 or "-"),
            ("Budget", market_truth.paper_budget_usdc or "-"),
            ("Avg entry", market_truth.avg_entry_price or "-"),
            ("Exposure", market_truth.exposure_notional_usdc or "-"),
            ("Filled / posted / cancelled", _terminal_rung_counts(snapshot)),
        ],
    )
    ladder = row_table(
        title="Ladder",
        columns=("Level", "State", "Notional", "Qty", "Fill"),
        rows=[
            (
                _format_cents_label(rung.price),
                rung.state,
                rung.notional_usdc or "-",
                rung.quantity or "-",
                rung.fill_at or rung.cancellation_at or "-",
            )
            for rung in snapshot.rungs
        ],
    )
    market_context = row_table(
        title=presenter.market_block_title,
        columns=("Side", "Bid", "Ask", "Mid", "Spread", "30¢", "20¢", "10¢"),
        rows=[
            (
                "Up",
                market_truth.up_side.best_bid or "-"
                if market_truth.up_side is not None
                else "-",
                market_truth.up_side.best_ask or "-"
                if market_truth.up_side is not None
                else "-",
                market_truth.up_side.midpoint or "-"
                if market_truth.up_side is not None
                else "-",
                market_truth.up_side.spread or "-"
                if market_truth.up_side is not None
                else "-",
                market_truth.up_side.visible_liquidity_030 or "-"
                if market_truth.up_side is not None
                else "-",
                market_truth.up_side.visible_liquidity_020 or "-"
                if market_truth.up_side is not None
                else "-",
                market_truth.up_side.visible_liquidity_010 or "-"
                if market_truth.up_side is not None
                else "-",
            ),
            (
                "Down",
                market_truth.down_side.best_bid or "-"
                if market_truth.down_side is not None
                else "-",
                market_truth.down_side.best_ask or "-"
                if market_truth.down_side is not None
                else "-",
                market_truth.down_side.midpoint or "-"
                if market_truth.down_side is not None
                else "-",
                market_truth.down_side.spread or "-"
                if market_truth.down_side is not None
                else "-",
                market_truth.down_side.visible_liquidity_030 or "-"
                if market_truth.down_side is not None
                else "-",
                market_truth.down_side.visible_liquidity_020 or "-"
                if market_truth.down_side is not None
                else "-",
                market_truth.down_side.visible_liquidity_010 or "-"
                if market_truth.down_side is not None
                else "-",
            ),
        ],
    )
    context_summary = summary_table(
        title=presenter.market_block_title,
        rows=[
            ("Spread", market_truth.current_spread or "-"),
            ("Midpoint", market_truth.current_midpoint or "-"),
            (
                "Derived Up",
                _format_market_truth_price(
                    market_truth.derived_up_price,
                    market_truth.derived_up_price_source,
                ),
            ),
            (
                "Derived Down",
                _format_market_truth_price(
                    market_truth.derived_down_price,
                    market_truth.derived_down_price_source,
                ),
            ),
            ("Visible @30¢", market_truth.visible_liquidity_030 or "-"),
            ("Visible @20¢", market_truth.visible_liquidity_020 or "-"),
            ("Visible @10¢", market_truth.visible_liquidity_010 or "-"),
            ("Open interest", market_truth.market_open_interest or "-"),
            ("Market volume", market_truth.market_volume or "-"),
            ("Volume", display.display_volume or "-"),
            ("Flags", ", ".join(market_truth.manipulation_flags) or "-"),
            ("Notes", ", ".join(display.display_notes) or "-"),
        ],
    )
    binance = summary_table(
        title="Binance Diagnostics",
        rows=[
            ("Spot", snapshot.current_binance_price or "-"),
            (
                "Best bid / ask",
                f"{snapshot.binance_best_bid or '-'} / {snapshot.binance_best_ask or '-'}",
            ),
            (
                "Near-touch depth",
                (
                    f"{snapshot.binance_near_touch_bid_depth or '-'} / "
                    f"{snapshot.binance_near_touch_ask_depth or '-'}"
                ),
            ),
            ("Imbalance", snapshot.binance_near_touch_imbalance or "-"),
        ],
    )
    events = (
        row_table(
            title=presenter.event_tape_title,
            columns=("At", "Kind", "Status", "Message"),
            rows=[
                (event.event_at, event.kind, event.status, event.message)
                for event in snapshot.latest_events
            ],
        )
        if snapshot.latest_events
        else empty_message("No terminal events yet.")
    )
    layout = Layout()
    layout.split_column(
        Layout(Panel(header, title="BTC15m Terminal"), size=8),
        Layout(name="body"),
        Layout(Panel(events, title=presenter.event_tape_title), size=9),
    )
    layout["body"].split_row(
        Layout(
            render_group(
                Panel(market_focus, title=presenter.page_block_title),
                Panel(strategy, title=presenter.strategy_block_title),
                Panel(ladder, title="Ladder"),
            ),
            name="left",
            ratio=2,
        ),
        Layout(
            render_group(
                Panel(market_context, title="Depth"),
                Panel(context_summary, title=presenter.market_block_title),
                Panel(binance, title="Binance") if show_binance else empty_message(""),
            ),
            name="right",
            ratio=2,
        ),
    )
    return layout


def _render_terminal_response(response: Btc15mTerminalResponse) -> RenderableType:
    if response.latest_snapshot is None:
        return section_panel("BTC15m Terminal", empty_message("No terminal snapshot."))
    latest_sheet = (
        response.session.window_tear_sheets[-1]
        if response.session is not None and response.session.window_tear_sheets
        else None
    )
    session_display = (
        _record_display_truth(response.session) if response.session is not None else None
    )
    latest_sheet_display = (
        _record_display_truth(latest_sheet) if latest_sheet is not None else None
    )
    summary = summary_table(
        title="Terminal Summary",
        rows=[
            ("Session", response.session_id),
            ("Mode", str(response.mode)),
            ("Attach mode", response.attach_mode),
            ("Stop reason", response.stop_reason),
            ("Snapshots", str(response.total_snapshots)),
            ("Market", response.window.market_slug if response.window is not None else "-"),
            (
                "Rollovers",
                str(response.session.rollover_count if response.session is not None else 0),
            ),
        ],
    )
    final_summary = (
        summary_table(
            title="Final Session",
            rows=[
                ("Final state", str(response.session.final_state)),
                ("Observe only", "yes" if response.session.observe_only else "no"),
                ("Side", response.session.selected_side or "-"),
                ("Boundary", response.session.boundary_status),
                (
                    "Window label",
                    session_display.display_window_label or "-" if session_display else "-",
                ),
                (
                    "Filled / posted / cancelled",
                    (
                        f"{response.session.filled_rung_count} / "
                        f"{response.session.posted_rung_count} / "
                        f"{response.session.cancelled_rung_count}"
                    ),
                ),
                ("Budget", response.session.paper_budget_usdc or "-"),
                ("Exposure", response.session.exposure_notional_usdc or "-"),
                ("Snapshots", str(response.session.total_snapshots)),
                (
                    "Realized PnL",
                    (
                        response.session.latest_evaluation.realized_pnl_usdc
                        if response.session
                        and response.session.latest_evaluation is not None
                        else "-"
                    ),
                ),
            ],
        )
        if response.session is not None
        else empty_message("No final session summary.")
    )
    tear_sheet = (
        summary_table(
            title="Latest Tear Sheet",
            rows=[
                ("Market", latest_sheet.window.market_slug),
                ("Final state", str(latest_sheet.final_state)),
                (
                    "Price to beat",
                    latest_sheet_display.display_price_to_beat or "-"
                    if latest_sheet_display
                    else "-",
                ),
                (
                    "Live BTC",
                    latest_sheet_display.display_current_btc or "-"
                    if latest_sheet_display
                    else "-",
                ),
                (
                    "Volume",
                    latest_sheet_display.display_volume or "-"
                    if latest_sheet_display
                    else "-",
                ),
                (
                    "Up / Down",
                    (
                        f"{latest_sheet_display.display_up_price or '-'} / "
                        f"{latest_sheet_display.display_down_price or '-'}"
                    )
                    if latest_sheet_display is not None
                    else "- / -"
                ),
                (
                    "Realized PnL",
                    latest_sheet.latest_evaluation.realized_pnl_usdc
                    if latest_sheet.latest_evaluation is not None
                    else "-",
                ),
            ],
        )
        if latest_sheet is not None
        else empty_message("No completed terminal window yet.")
    )
    return section_panel(
        "BTC15m Terminal",
        render_group(
            summary,
            final_summary,
            tear_sheet,
            _render_terminal_snapshot(response.latest_snapshot),
        ),
    )


def _format_terminal_report_response(response: Btc15mTerminalReportResponse) -> str:
    if response.session is not None:
        return "\n".join(
            [
                f"Terminal session: {response.session.session_id}",
                f"Mode: {response.session.mode}",
                f"Attach mode: {response.session.attach_mode}",
                f"Final state: {response.session.final_state}",
                f"Stop reason: {response.session.stop_reason}",
            ]
        )
    return "\n".join(
        [
            f"Terminal sessions: {response.summary.terminal_session_count}",
            f"Paper sessions: {response.summary.paper_session_count}",
            f"Live sessions: {response.summary.live_session_count}",
            f"Observe-only sessions: {response.summary.observe_only_session_count}",
            f"Resolved sessions: {response.summary.resolved_session_count}",
            f"Skipped sessions: {response.summary.skipped_session_count}",
        ]
    )


def _render_terminal_report_response(
    response: Btc15mTerminalReportResponse,
) -> RenderableType:
    if response.session is not None:
        latest_sheet = (
            response.session.window_tear_sheets[-1]
            if response.session.window_tear_sheets
            else None
        )
        session_display = _record_display_truth(response.session)
        summary = summary_table(
            title="Terminal Tear Sheet",
            rows=[
                ("Session", response.session.session_id),
                ("Mode", response.session.mode),
                ("Attach mode", response.session.attach_mode),
                ("Final state", response.session.final_state),
                ("Stop reason", response.session.stop_reason),
                ("Side", response.session.selected_side or "-"),
                ("Snapshots", str(response.session.total_snapshots)),
                ("Rollovers", str(response.session.rollover_count)),
                (
                    "Realized PnL",
                    response.session.latest_evaluation.realized_pnl_usdc
                    if response.session.latest_evaluation is not None
                    else "-",
                ),
            ],
        )
        windows = (
            row_table(
                title="Session Windows",
                columns=("Market", "State", "Price To Beat", "Up", "Down", "PnL"),
                rows=[
                    (
                        item.window.market_slug,
                        item.final_state,
                        _record_display_truth(item).display_price_to_beat or "-",
                        _record_display_truth(item).display_up_price or "-",
                        _record_display_truth(item).display_down_price or "-",
                        item.latest_evaluation.realized_pnl_usdc
                        if item.latest_evaluation is not None
                        else "-",
                    )
                    for item in response.session.window_tear_sheets
                ],
            )
            if response.session.window_tear_sheets
            else empty_message("No completed session windows yet.")
        )
        details_snapshot = (
            latest_sheet.latest_snapshot
            if latest_sheet is not None and latest_sheet.latest_snapshot is not None
            else response.session.latest_snapshot
        )
        details = (
            _render_terminal_snapshot(details_snapshot)
            if details_snapshot is not None
            else empty_message("No terminal snapshot for this session.")
        )
        return section_panel(
            "BTC15m Terminal Tear Sheet",
            render_group(
                summary,
                summary_table(
                    title="Display Truth",
                    rows=[
                        ("Window label", session_display.display_window_label or "-"),
                        ("Price to beat", session_display.display_price_to_beat or "-"),
                        ("Current BTC", session_display.display_current_btc or "-"),
                        (
                            "Up / Down",
                            f"{session_display.display_up_price or '-'} / "
                            f"{session_display.display_down_price or '-'}",
                        ),
                        ("Volume", session_display.display_volume or "-"),
                        ("Display source", session_display.display_source or "-"),
                    ],
                ),
                windows,
                details,
            ),
        )
    summary = summary_table(
        title="Terminal Summary",
        rows=[
            ("Sessions", str(response.summary.terminal_session_count)),
            (
                "Paper / live",
                (
                    f"{response.summary.paper_session_count} / "
                    f"{response.summary.live_session_count}"
                ),
            ),
            ("Observe only", str(response.summary.observe_only_session_count)),
            (
                "Resolved / skipped",
                (
                    f"{response.summary.resolved_session_count} / "
                    f"{response.summary.skipped_session_count}"
                ),
            ),
            ("Total PnL", response.summary.total_realized_pnl_usdc),
            ("Average PnL", response.summary.average_realized_pnl_usdc),
        ],
    )
    recent = (
        row_table(
            title="Recent Sessions",
            columns=("Market", "Mode", "State", "Side", "PnL"),
            rows=[
                (
                    item.window.market_slug if item.window is not None else "-",
                    item.mode,
                    item.final_state,
                    item.selected_side or "-",
                    item.latest_evaluation.realized_pnl_usdc
                    if item.latest_evaluation is not None
                    else "-",
                )
                for item in response.recent_sessions
            ],
        )
        if response.recent_sessions
        else empty_message("No terminal sessions yet.")
    )
    return section_panel("BTC15m Terminal Report", render_group(summary, recent))


def _format_terminal_replay_response(response: Btc15mTerminalReplayResponse) -> str:
    market_slug = (
        response.session.window.market_slug
        if response.session is not None and response.session.window is not None
        else "-"
    )
    return "\n".join(
        [
            f"Replay session: {response.session_id}",
            f"Snapshots: {response.total_snapshots}",
            f"Market: {market_slug}",
            f"Final state: {response.session.final_state if response.session is not None else '-'}",
        ]
    )


def _render_terminal_replay_response(response: Btc15mTerminalReplayResponse) -> RenderableType:
    summary = summary_table(
        title="Replay Summary",
        rows=[
            ("Session", response.session_id),
            ("Snapshots", str(response.total_snapshots)),
            (
                "Market",
                response.session.window.market_slug
                if response.session is not None and response.session.window is not None
                else "-",
            ),
            ("Final state", response.session.final_state if response.session is not None else "-"),
        ],
    )
    details = (
        _render_terminal_snapshot(response.latest_snapshot)
        if response.latest_snapshot is not None
        else empty_message("No stored terminal snapshots for this session.")
    )
    return section_panel("BTC15m Terminal Replay", render_group(summary, details))


def _format_session_arm_response(response: Btc15mSessionArmResponse) -> str:
    session = response.session
    return "\n".join(
        [
            f"Session: {session.session_id}",
            f"State: {session.state}",
            f"Mode: {session.mode}",
            f"Market: {session.window.market_slug if session.window is not None else '-'}",
            f"Budget: {session.paper_budget_usdc or '-'}",
            f"Rungs: {', '.join(session.rung_notionals_usdc) or '-'}",
            f"Reused: {'yes' if response.reused_existing else 'no'}",
        ]
    )


def _render_session_arm_response(response: Btc15mSessionArmResponse) -> RenderableType:
    session = response.session
    return section_panel(
        "BTC15m Session",
        summary_table(
            title="Armed Session",
            rows=[
                ("Session", session.session_id),
                ("State", session.state),
                ("Mode", session.mode),
                ("Market", session.window.market_slug if session.window is not None else "-"),
                ("Budget", session.paper_budget_usdc or "-"),
                ("Rungs", ", ".join(session.rung_notionals_usdc) or "-"),
                ("Reused", "yes" if response.reused_existing else "no"),
            ],
        ),
    )


def _format_session_status_response(response: Btc15mSessionStatusResponse) -> str:
    active = response.active_session.session_id if response.active_session is not None else "-"
    latest = (
        response.latest_completed_report.session_id
        if response.latest_completed_report is not None
        else "-"
    )
    return "\n".join(
        [
            f"Checked at: {response.checked_at}",
            f"Armed sessions: {len(response.armed_sessions)}",
            f"Active session: {active}",
            f"Latest completed report: {latest}",
        ]
    )


def _format_session_latest_response(response: Btc15mSessionLatestResponse) -> str:
    session = response.session
    return "\n".join(
        [
            f"Checked at: {response.checked_at}",
            f"Session: {session.session_id}",
            f"State: {session.state}",
            f"Mode: {session.mode}",
            f"Market: {session.window.market_slug if session.window is not None else '-'}",
            f"Report: {response.report.session_id if response.report is not None else '-'}",
        ]
    )


def _render_session_latest_response(response: Btc15mSessionLatestResponse) -> RenderableType:
    session = response.session
    report = response.report
    canary = response.canary_limits
    return section_panel(
        "BTC15m Session",
        render_group(
            summary_table(
                title="Latest Session",
                rows=[
                    ("Checked at", response.checked_at),
                    ("Session", session.session_id),
                    ("State", session.state),
                    ("Mode", session.mode),
                    ("Market", session.window.market_slug if session.window is not None else "-"),
                    ("Updated", session.updated_at),
                    ("Report", report.session_id if report is not None else "-"),
                ],
            ),
            summary_table(
                title="Canary Live Caps",
                rows=[
                    ("Max live USDC", canary.max_live_usdc),
                    ("Max rung USDC", canary.max_rung_usdc),
                    ("One window only", "yes" if canary.one_window_only else "no"),
                    ("Default sizing fits", "yes" if canary.default_sizing_fits else "no"),
                ],
            ),
        ),
    )


def _render_session_status_response(response: Btc15mSessionStatusResponse) -> RenderableType:
    summary = summary_table(
        title="Controller Status",
        rows=[
            ("Checked at", response.checked_at),
            ("Armed sessions", str(len(response.armed_sessions))),
            (
                "Active session",
                response.active_session.session_id if response.active_session is not None else "-",
            ),
            (
                "Latest report",
                response.latest_completed_report.session_id
                if response.latest_completed_report is not None
                else "-",
            ),
        ],
    )
    armed = (
        row_table(
            title="Armed Sessions",
            columns=("Session", "Mode", "Market", "Budget", "State"),
            rows=[
                (
                    item.session_id,
                    item.mode,
                    item.window.market_slug if item.window is not None else "-",
                    item.paper_budget_usdc or "-",
                    item.state,
                )
                for item in response.armed_sessions
            ],
        )
        if response.armed_sessions
        else empty_message("No armed BTC15m sessions.")
    )
    active = (
        summary_table(
            title="Active Session",
            rows=[
                ("Session", response.active_session.session_id),
                ("Mode", response.active_session.mode),
                ("State", response.active_session.state),
                (
                    "Market",
                    response.active_session.window.market_slug
                    if response.active_session.window is not None
                    else "-",
                ),
                ("Budget", response.active_session.paper_budget_usdc or "-"),
            ],
        )
        if response.active_session is not None
        else empty_message("No active BTC15m session.")
    )
    return section_panel("BTC15m Session", render_group(summary, active, armed))


def _format_session_run_response(response: Btc15mSessionRunResponse) -> str:
    report = response.report
    market_slug = (
        response.session.window.market_slug if response.session.window is not None else "-"
    )
    return "\n".join(
        [
            f"Session: {response.session.session_id}",
            f"State: {response.session.state}",
            f"Market: {market_slug}",
            f"Stop reason: {response.session.stop_reason or '-'}",
            f"Final state: {report.final_state if report is not None else '-'}",
            (
                f"Reconcile: {report.execution_reconciliation_id}"
                if report is not None and report.execution_reconciliation_id is not None
                else "Reconcile: -"
            ),
            f"Realized PnL: {report.realized_pnl_usdc if report is not None else '-'}",
        ]
    )


def _render_session_run_response(response: Btc15mSessionRunResponse) -> RenderableType:
    report = response.report
    summary = summary_table(
        title="Run Result",
        rows=[
            ("Session", response.session.session_id),
            ("State", response.session.state),
            ("Mode", response.session.mode),
            (
                "Market",
                response.session.window.market_slug if response.session.window is not None else "-",
            ),
            ("Stop reason", response.session.stop_reason or "-"),
            ("Budget", response.session.paper_budget_usdc or "-"),
            ("Rungs", ", ".join(response.session.rung_notionals_usdc) or "-"),
        ],
    )
    final_report = (
        summary_table(
            title="Final Report",
            rows=[
                ("Controller state", report.state),
                ("Final state", report.final_state or "-"),
                ("Traded", "yes" if report.traded else "no"),
                ("Observe only", "yes" if report.observe_only else "no"),
                ("Side", report.selected_side or "-"),
                ("Boundary", report.boundary_status),
                ("Reconcile", report.execution_reconciliation_id or "-"),
                ("PnL", report.realized_pnl_usdc or "-"),
                ("MFE / MAE", f"{report.mfe_usdc or '-'} / {report.mae_usdc or '-'}"),
            ],
        )
        if report is not None
        else empty_message("No final report.")
    )
    return section_panel("BTC15m Session", render_group(summary, final_report))


def _format_session_stop_response(response: Btc15mSessionStopResponse) -> str:
    session = response.session
    return "\n".join(
        [
            f"Session: {session.session_id}",
            f"State: {session.state}",
            f"Stop reason: {session.stop_reason or '-'}",
        ]
    )


def _render_session_stop_response(response: Btc15mSessionStopResponse) -> RenderableType:
    session = response.session
    return section_panel(
        "BTC15m Session",
        summary_table(
            title="Stop Request",
            rows=[
                ("Session", session.session_id),
                ("State", session.state),
                ("Stop requested at", session.stop_requested_at or "-"),
                ("Stop reason", session.stop_reason or "-"),
            ],
        ),
    )


def _format_session_report_response(response: Btc15mSessionReportResponse) -> str:
    report = response.report
    return "\n".join(
        [
            f"Session: {report.session_id}",
            f"State: {report.state}",
            f"Final state: {report.final_state or '-'}",
            f"Market: {report.window.market_slug if report.window is not None else '-'}",
            f"Reconcile: {report.execution_reconciliation_id or '-'}",
            f"PnL: {report.realized_pnl_usdc or '-'}",
        ]
    )


def _format_live_check_response(response: Btc15mLiveCheckResponse) -> str:
    target = response.target_window.market_slug if response.target_window is not None else "-"
    active = response.active_session.session_id if response.active_session is not None else "-"
    canary_caps = (
        "Canary max live / rung: "
        f"{response.canary_limits.max_live_usdc} / "
        f"{response.canary_limits.max_rung_usdc}"
    )
    return "\n".join(
        [
            f"Checked at: {response.checked_at}",
            f"Ready: {'yes' if response.ready else 'no'}",
            f"Target window: {target}",
            f"Active conflict: {active}",
            canary_caps,
        ]
    )


def _render_live_check_response(response: Btc15mLiveCheckResponse) -> RenderableType:
    signer = response.auth.signer_address if response.auth is not None else None
    funder = response.auth.funder_address if response.auth is not None else None
    checks = row_table(
        title="Checks",
        columns=("Section", "Status", "Message"),
        rows=[(item.section, item.status, item.message) for item in response.checks],
    )
    summary = summary_table(
        title="Live Readiness",
        rows=[
            ("Checked at", response.checked_at),
            ("Ready", "yes" if response.ready else "no"),
            ("Signer", signer or "-"),
            ("Funder", funder or "-"),
            (
                "Target window",
                response.target_window.market_slug if response.target_window is not None else "-",
            ),
            (
                "Active session",
                response.active_session.session_id if response.active_session is not None else "-",
            ),
            ("Max live USDC", response.canary_limits.max_live_usdc),
            ("Max rung USDC", response.canary_limits.max_rung_usdc),
        ],
    )
    return section_panel("BTC15m Live Check", render_group(summary, checks))


def _render_session_report_response(response: Btc15mSessionReportResponse) -> RenderableType:
    report = response.report
    return section_panel(
        "BTC15m Session Report",
        render_group(
            summary_table(
                title="Report",
                rows=[
                    ("Session", report.session_id),
                    ("State", report.state),
                    ("Final state", report.final_state or "-"),
                    ("Mode", report.mode),
                    ("Market", report.window.market_slug if report.window is not None else "-"),
                    ("Stop reason", report.stop_reason or "-"),
                    ("Traded", "yes" if report.traded else "no"),
                    ("Observe only", "yes" if report.observe_only else "no"),
                    ("Side", report.selected_side or "-"),
                    ("Budget", report.paper_budget_usdc or "-"),
                    ("Rungs", ", ".join(report.rung_notionals_usdc) or "-"),
                    ("Reconcile", report.execution_reconciliation_id or "-"),
                    ("Realized PnL", report.realized_pnl_usdc or "-"),
                ],
            ),
            row_table(
                title="Rung Outcomes",
                columns=("Price", "State", "Order", "Notional", "Qty", "Fill"),
                rows=[
                    (
                        item.price,
                        item.state,
                        item.order_id or "-",
                        item.notional_usdc or "-",
                        item.quantity or "-",
                        item.fill_price or "-",
                    )
                    for item in report.rung_outcomes
                ],
            )
            if report.rung_outcomes
            else empty_message("No rung outcomes recorded."),
        ),
    )


def _format_bundle_response(response: Btc15mSessionBundleResponse) -> str:
    return "\n".join(
        [
            f"Session: {response.session.session_id}",
            f"Report: {response.report.session_id}",
            f"Order plans: {len(response.order_plans)}",
            f"Execution events: {len(response.execution_events)}",
            (
                "Reconcile: "
                f"{response.execution_reconciliation.reconciliation_id}"
                if response.execution_reconciliation is not None
                else "Reconcile: -"
            ),
        ]
    )


def _render_bundle_response(response: Btc15mSessionBundleResponse) -> RenderableType:
    market_slug = response.report.window.market_slug if response.report.window is not None else "-"
    summary = summary_table(
        title="Bundle",
        rows=[
            ("Session", response.session.session_id),
            ("Report", response.report.session_id),
            ("Mode", response.report.mode),
            ("Market", market_slug),
            ("Order plans", str(len(response.order_plans))),
            ("Order results", str(len(response.order_results))),
            ("Execution events", str(len(response.execution_events))),
            (
                "Reconcile",
                response.execution_reconciliation.reconciliation_id
                if response.execution_reconciliation is not None
                else "-",
            ),
            (
                "Portfolio reconcile",
                response.portfolio_reconciliation.reconciliation_id
                if response.portfolio_reconciliation is not None
                else "-",
            ),
            ("Notes", ", ".join(response.notes) or "-"),
        ],
    )
    plans = (
        row_table(
            title="Order Plans",
            columns=("Plan", "Action", "Order", "Mode", "Decision"),
            rows=[
                (item.plan_id, item.action, item.order_id or "-", item.mode, item.decision)
                for item in response.order_plans
            ],
        )
        if response.order_plans
        else empty_message("No linked execution order plans.")
    )
    events = (
        row_table(
            title="Execution Events",
            columns=("At", "Order", "Type", "Status"),
            rows=[
                (item.captured_at, item.order_id or "-", item.event_type, item.status or "-")
                for item in response.execution_events
            ],
        )
        if response.execution_events
        else empty_message("No linked execution events.")
    )
    return section_panel("BTC15m Bundle", render_group(summary, plans, events))


def _format_campaign_next_window_response(response: Btc15mCampaignNextWindowResponse) -> str:
    if response.window is None:
        return "No campaign window became available before the wait limit."
    return "\n".join(
        [
            f"Mode: {response.mode}",
            f"Target slug: {response.target_slug or '-'}",
            f"Market: {response.window.market_slug}",
            f"Condition: {response.window.condition_id or '-'}",
            f"Waited seconds: {response.waited_seconds}",
            f"Polls: {response.poll_count}",
        ]
    )


def _render_campaign_next_window_response(
    response: Btc15mCampaignNextWindowResponse,
) -> RenderableType:
    if response.window is None:
        return section_panel("BTC15m Campaign", empty_message("No window became available."))
    return section_panel(
        "BTC15m Campaign",
        summary_table(
            title="Next Window",
            rows=[
                ("Mode", response.mode),
                ("Target slug", response.target_slug or "-"),
                ("Market", response.window.market_slug),
                ("Condition", response.window.condition_id or "-"),
                ("Waited seconds", str(response.waited_seconds)),
                ("Polls", str(response.poll_count)),
            ],
        ),
    )


def _format_campaign_run_response(response: Btc15mCampaignRunResponse) -> str:
    return "\n".join(
        [
            f"Campaign run: {response.campaign.run_id}",
            f"Mode: {response.campaign.mode}",
            f"Target slug: {response.campaign.target_slug or '-'}",
            f"Stop reason: {response.campaign.stop_reason or '-'}",
            f"Evaluated windows: {response.campaign.total_windows}",
            f"Skipped windows: {response.campaign.total_skipped}",
            f"Total realized PnL: {response.campaign.total_realized_pnl_usdc}",
        ]
    )


def _render_campaign_run_response(response: Btc15mCampaignRunResponse) -> RenderableType:
    summary = summary_table(
        title="Campaign Summary",
        rows=[
            ("Run", response.campaign.run_id),
            ("Hours", response.campaign.requested_hours),
            ("Mode", response.campaign.mode),
            ("Target slug", response.campaign.target_slug or "-"),
            ("Stop reason", response.campaign.stop_reason or "-"),
            ("Windows", str(response.campaign.total_windows)),
            ("Skipped", str(response.campaign.total_skipped)),
            ("Realized PnL", response.campaign.total_realized_pnl_usdc),
        ],
    )
    items = (
        row_table(
            title="Campaign Windows",
            columns=("Market", "Decision", "Resolution", "Spread", "PnL"),
            rows=(
                (
                    item.market_slug,
                    item.decision,
                    item.resolution_result,
                    item.decision_spread or "-",
                    item.realized_pnl_usdc,
                )
                for item in response.campaign.items
            ),
        )
        if response.campaign.items
        else empty_message("No campaign windows were evaluated.")
    )
    return section_panel("BTC15m Campaign", render_group(summary, items))


def _format_campaign_report_response(response: Btc15mCampaignReportResponse) -> str:
    return "\n".join(
        [
            f"Campaign runs: {response.summary.campaign_run_count}",
            f"Evaluated windows: {response.summary.evaluated_window_count}",
            f"Skips: {response.summary.skip_count}",
            f"Total realized PnL: {response.summary.total_realized_pnl_usdc}",
        ]
    )


def _render_campaign_report_response(response: Btc15mCampaignReportResponse) -> RenderableType:
    summary = summary_table(
        title="Campaign Summary",
        rows=[
            ("Campaign runs", str(response.summary.campaign_run_count)),
            ("Evaluated windows", str(response.summary.evaluated_window_count)),
            (
                "Wins / losses / ties",
                (
                    f"{response.summary.win_count} / "
                    f"{response.summary.loss_count} / "
                    f"{response.summary.tie_count}"
                ),
            ),
            ("Skips", str(response.summary.skip_count)),
            ("Average spread", response.summary.average_decision_spread or "-"),
            ("Average 1m vol bps", response.summary.average_realized_vol_1m_bps or "-"),
            ("Average 3m vol bps", response.summary.average_realized_vol_3m_bps or "-"),
            ("Total realized PnL", response.summary.total_realized_pnl_usdc),
        ],
    )
    recent = (
        row_table(
            title="Recent Campaign Evaluations",
            columns=("Market", "Decision", "Flags", "Spread", "PnL"),
            rows=(
                (
                    item.market_slug,
                    item.decision,
                    ", ".join(item.manipulation_flags) or "-",
                    item.decision_spread or "-",
                    item.realized_pnl_usdc,
                )
                for item in response.recent_evaluations
            ),
        )
        if response.recent_evaluations
        else empty_message("No campaign evaluations yet.")
    )
    return section_panel("BTC15m Campaign Report", render_group(summary, recent))


def _format_auto_roll_response(response: Btc15mAutoRollResponse) -> str:
    return "\n".join(
        [
            f"Auto-roll run: {response.run.run_id}",
            f"Hours: {response.run.requested_hours}",
            f"Mode: {response.run.mode}",
            f"Stop reason: {response.run.stop_reason}",
            f"Windows: {response.run.total_windows}",
            f"PnL: {response.run.total_realized_pnl_usdc}",
        ]
    )


def _render_auto_roll_response(response: Btc15mAutoRollResponse) -> RenderableType:
    summary = summary_table(
        title="Auto-Roll Summary",
        rows=[
            ("Run", response.run.run_id),
            ("Hours", response.run.requested_hours),
            ("Mode", str(response.run.mode)),
            ("Stop reason", response.run.stop_reason),
            ("Windows", str(response.run.total_windows)),
            ("Skipped", str(response.run.total_skipped)),
            ("Realized PnL", response.run.total_realized_pnl_usdc),
        ],
    )
    items = (
        row_table(
            title="Auto-Roll Windows",
            columns=("Market", "Decision", "Resolution", "PnL"),
            rows=(
                (
                    item.market_slug,
                    item.decision,
                    item.resolution_result,
                    item.realized_pnl_usdc,
                )
                for item in response.run.items
            ),
        )
        if response.run.items
        else empty_message("No auto-roll evaluations were produced.")
    )
    return section_panel("BTC15m Auto-Roll", render_group(summary, items))


def _format_report(response: Btc15mReportResponse) -> str:
    return "\n".join(
        [
            f"Recorded windows: {response.summary.recorded_window_count}",
            f"Completed windows: {response.summary.completed_window_count}",
            f"Paper runs: {response.summary.paper_run_count}",
            f"Campaign runs: {response.summary.campaign_run_count}",
            f"Evaluated windows: {response.summary.evaluated_window_count}",
            f"Total realized PnL: {response.summary.total_realized_pnl_usdc}",
        ]
    )


def _render_report(response: Btc15mReportResponse) -> RenderableType:
    summary = summary_table(
        title="BTC15m Summary",
        rows=[
            ("Recorded windows", str(response.summary.recorded_window_count)),
            ("Completed windows", str(response.summary.completed_window_count)),
            ("Replay batches", str(response.summary.replay_batch_count)),
            ("Paper runs", str(response.summary.paper_run_count)),
            ("Campaign runs", str(response.summary.campaign_run_count)),
            ("Evaluated windows", str(response.summary.evaluated_window_count)),
            (
                "Wins / losses / ties",
                (
                    f"{response.summary.win_count} / "
                    f"{response.summary.loss_count} / "
                    f"{response.summary.tie_count}"
                ),
            ),
            ("Skips", str(response.summary.skip_count)),
            ("Total realized PnL", response.summary.total_realized_pnl_usdc),
            ("Average realized PnL", response.summary.average_realized_pnl_usdc),
        ],
    )
    latest_window = (
        summary_table(
            title="Latest Partial Window",
            rows=[
                ("Market", response.latest_active_window.window.market_slug),
                ("Status", response.latest_active_window.status),
                ("Boundaries", response.latest_active_window.boundary_status),
                ("Decision", response.latest_active_window.decision),
            ],
        )
        if response.latest_active_window is not None
        else empty_message("No active or partial window.")
    )
    recent_evaluations = (
        row_table(
            title="Recent Evaluations",
            columns=("Market", "Decision", "Resolution", "Fills", "PnL"),
            rows=(
                (
                    item.market_slug,
                    item.decision,
                    item.resolution_result,
                    str(item.filled_rung_count),
                    item.realized_pnl_usdc,
                )
                for item in response.recent_evaluations
            ),
        )
        if response.recent_evaluations
        else empty_message("No evaluations yet.")
    )
    campaign = (
        summary_table(
            title="Campaign Summary",
            rows=[
                ("Runs", str(response.campaign_summary.campaign_run_count)),
                ("Windows", str(response.campaign_summary.evaluated_window_count)),
                ("Average spread", response.campaign_summary.average_decision_spread or "-"),
                (
                    "Average 1m vol bps",
                    response.campaign_summary.average_realized_vol_1m_bps or "-",
                ),
            ],
        )
        if response.campaign_summary is not None
        else empty_message("No campaign activity yet.")
    )
    return section_panel(
        "BTC15m Report",
        render_group(summary, campaign, latest_window, recent_evaluations),
    )


app.add_typer(record_app, name="record")
app.add_typer(campaign_app, name="campaign")
app.add_typer(liquidity_app, name="liquidity")
app.add_typer(terminal_app, name="terminal")
app.add_typer(session_app, name="session")
