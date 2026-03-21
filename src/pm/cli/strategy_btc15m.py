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
    Btc15mLiveResponse,
    Btc15mPaperRunResponse,
    Btc15mRecordStartResponse,
    Btc15mRecordWindowResponse,
    Btc15mReplayResponse,
    Btc15mReportResponse,
    Btc15mResolveCurrentResponse,
    Btc15mStateError,
    Btc15mStrategyService,
    Btc15mTerminalDisplayTruth,
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
WAIT_NEXT_OPTION = typer.Option(
    False,
    "--wait-next",
    help="Observe the current window and arm the next BTC15m window when capture opens.",
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
SESSION_ID_OPTION = typer.Option(
    ...,
    "--session-id",
    help="Persisted BTC15m terminal session identifier.",
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
    wait_next: bool = WAIT_NEXT_OPTION,
    observe_only: bool = OBSERVE_ONLY_OPTION,
    mode: str = MODE_OPTION,
    confirm: bool = CONFIRM_OPTION,
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
                    snapshot_only=True,
                    session_window_limit=1,
                )
                if current_requested
                else service.terminal_wait_next(
                    mode=mode,
                    confirm=confirm,
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
                        session_window_limit=None,
                        on_snapshot=_on_snapshot,
                        confirm_action=_confirm_action if mode.strip().lower() == "live" else None,
                    )
                    if current_requested
                    else service.terminal_wait_next(
                        mode=mode,
                        confirm=confirm,
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


def _snapshot_display_truth(snapshot: Btc15mDashboardSnapshotRecord) -> Btc15mTerminalDisplayTruth:
    if snapshot.display is not None:
        return snapshot.display
    return Btc15mTerminalDisplayTruth(
        display_price_to_beat=snapshot.price_to_beat,
        display_current_btc=snapshot.current_live_btc_price,
        display_up_price=snapshot.up_price,
        display_down_price=snapshot.down_price,
        display_countdown=(
            _format_countdown(snapshot.countdown_seconds)
            if snapshot.countdown_seconds is not None
            else None
        ),
        display_source=snapshot.page_parity_source,
        display_window_label=snapshot.current_window_label,
        display_url=snapshot.page_parity_url,
        display_notes=[],
    )


def _record_display_truth(record: object) -> Btc15mTerminalDisplayTruth:
    display = getattr(record, "display", None)
    if isinstance(display, Btc15mTerminalDisplayTruth):
        return display
    countdown_seconds = getattr(record, "countdown_seconds", None)
    return Btc15mTerminalDisplayTruth(
        display_price_to_beat=getattr(record, "price_to_beat", None),
        display_current_btc=getattr(record, "current_live_btc_price", None),
        display_up_price=getattr(record, "up_price", None),
        display_down_price=getattr(record, "down_price", None),
        display_countdown=_format_countdown(countdown_seconds),
        display_source=getattr(record, "page_parity_source", None),
        display_window_label=getattr(record, "current_window_label", None),
        display_url=getattr(record, "page_parity_url", None),
        display_notes=[],
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


def _render_terminal_snapshot(snapshot: Btc15mDashboardSnapshotRecord) -> RenderableType:
    display = _snapshot_display_truth(snapshot)
    parity_healthy = (display.display_source or "unavailable") not in {
        "degraded",
        "unavailable",
    }
    binance_compact = parity_healthy and not any(
        "binance" in flag or "divergence" in flag for flag in snapshot.manipulation_flags
    )
    header = summary_table(
        title="Session",
        rows=[
            ("Market", snapshot.market_slug),
            ("Window label", display.display_window_label or "-"),
            ("Mode", str(snapshot.mode)),
            ("Attach", snapshot.attach_mode),
            ("State", snapshot.window_status),
            ("Countdown", display.display_countdown or str(snapshot.countdown_seconds or 0)),
            ("Observe only", "yes" if snapshot.observe_only else "no"),
            ("Window", f"{snapshot.window_start_at or '-'} -> {snapshot.window_end_at or '-'}"),
        ],
    )
    market_focus = summary_table(
        title="Market",
        rows=[
            ("Price to beat", display.display_price_to_beat or "-"),
            (
                "Live BTC",
                display.display_current_btc or snapshot.current_chainlink_price or "-",
            ),
            ("Up price", display.display_up_price or "-"),
            ("Down price", display.display_down_price or "-"),
            ("Side", snapshot.selected_side or "-"),
            ("Session result", snapshot.window_status),
            (
                "Midpoint / spread",
                f"{snapshot.current_midpoint or '-'} / {snapshot.current_spread or '-'}",
            ),
            ("Display source", display.display_source or "-"),
        ],
    )
    boundary = summary_table(
        title="Boundary / Lock",
        rows=[
            ("Boundary status", snapshot.boundary_status),
            ("Start proxy", snapshot.start_price_proxy_v1 or "-"),
            ("Chainlink", snapshot.current_chainlink_price or "-"),
            ("Direction", snapshot.direction_lock_status),
            ("Selected side", snapshot.selected_side or "-"),
        ],
    )
    strategy = row_table(
        title="Ladder",
        columns=("Price", "State", "Qty", "Order", "Fill", "Visible"),
        rows=[
            (
                _format_cents_label(rung.price),
                rung.state,
                rung.quantity or "-",
                rung.order_id or "-",
                rung.fill_at or rung.cancellation_at or "-",
                rung.visible_liquidity or "-",
            )
            for rung in snapshot.rungs
        ],
    )
    exposure = summary_table(
        title="Exposure / PnL",
        rows=[
            ("Avg entry", snapshot.avg_entry_price or "-"),
            ("Exposure qty", snapshot.exposure_quantity or "-"),
            ("Exposure USDC", snapshot.exposure_notional_usdc or "-"),
            ("MFE", snapshot.mfe_usdc or "-"),
            ("MAE", snapshot.mae_usdc or "-"),
            ("Peak price", snapshot.max_favorable_price or "-"),
            ("Time to peak", str(snapshot.time_to_peak_seconds or 0)),
        ],
    )
    both_sides = row_table(
        title="Both Sides",
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
    market_context = summary_table(
        title="Market Context",
        rows=[
            ("Target", snapshot.target_outcome or "-"),
            ("Visible @30¢", snapshot.visible_liquidity_030 or "-"),
            ("Visible @20¢", snapshot.visible_liquidity_020 or "-"),
            ("Visible @10¢", snapshot.visible_liquidity_010 or "-"),
            ("Open interest", snapshot.market_open_interest or "-"),
            ("Volume", snapshot.market_volume or "-"),
        ],
    )
    binance = (
        summary_table(
            title="Binance",
            rows=[
                ("Spot", snapshot.current_binance_price or "-"),
                (
                    "Bid / ask",
                    f"{snapshot.binance_best_bid or '-'} / {snapshot.binance_best_ask or '-'}",
                ),
                ("Imbalance", snapshot.binance_near_touch_imbalance or "-"),
            ],
        )
        if binance_compact
        else summary_table(
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
                (
                    "Vol 1m / 3m",
                    (
                        f"{snapshot.binance_realized_vol_1m_bps or '-'} / "
                        f"{snapshot.binance_realized_vol_3m_bps or '-'}"
                    ),
                ),
                (
                    "Volume 1m / 3m",
                    f"{snapshot.binance_volume_1m or '-'} / {snapshot.binance_volume_3m or '-'}",
                ),
            ],
        )
    )
    flags = summary_table(
        title="Flags",
        rows=[
            ("Flags", ", ".join(snapshot.manipulation_flags) or "-"),
            ("Parity URL", display.display_url or "-"),
            ("Display notes", ", ".join(display.display_notes) or "-"),
            ("Errors", str(len(snapshot.errors))),
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
                Panel(market_focus, title="Page Parity"),
                Panel(strategy, title="Strategy"),
                Panel(both_sides, title="Both Sides"),
            ),
            name="left",
            ratio=2,
        ),
        Layout(
            render_group(
                Panel(boundary, title="Boundary"),
                Panel(exposure, title="Exposure"),
                Panel(market_context, title="Polymarket"),
            ),
            name="center",
            ratio=2,
        ),
        Layout(
            render_group(
                Panel(binance, title="Binance"),
                Panel(flags, title="Flags"),
            ),
            name="right",
            ratio=1,
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
