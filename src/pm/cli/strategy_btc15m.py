"""BTC15m research-strategy CLI surface."""

from __future__ import annotations

import typer
from rich.console import RenderableType

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.common.tables import empty_message, render_group, row_table, section_panel, summary_table
from pm.strategy import (
    Btc15mCampaignNextWindowResponse,
    Btc15mCampaignReportResponse,
    Btc15mCampaignRunResponse,
    Btc15mLiquiditySampleResponse,
    Btc15mPaperRunResponse,
    Btc15mRecordStartResponse,
    Btc15mRecordWindowResponse,
    Btc15mReplayResponse,
    Btc15mReportResponse,
    Btc15mStateError,
    Btc15mStrategyService,
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
