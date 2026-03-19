"""BTC15m research-strategy CLI surface."""

from __future__ import annotations

import typer
from rich.console import RenderableType

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.common.tables import empty_message, render_group, row_table, section_panel, summary_table
from pm.strategy import (
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
    json_output: bool = JSON_OPTION,
) -> None:
    """Paper-evaluate completed BTC15m windows chronologically."""
    try:
        result = Btc15mStrategyService().paper_run(limit=limit)
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
        identifier=identifier,
        local_json_output=json_output,
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
            f"Evaluated windows: {response.run.total_evaluated}",
            f"Skipped windows: {response.run.total_skipped}",
            f"Total realized PnL: {response.run.total_realized_pnl_usdc}",
        ]
    )


def _render_paper_run_response(response: Btc15mPaperRunResponse) -> RenderableType:
    summary = summary_table(
        title="Paper Run Summary",
        rows=[
            ("Run", response.run.run_id),
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


def _format_report(response: Btc15mReportResponse) -> str:
    return "\n".join(
        [
            f"Recorded windows: {response.summary.recorded_window_count}",
            f"Completed windows: {response.summary.completed_window_count}",
            f"Paper runs: {response.summary.paper_run_count}",
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
    return section_panel(
        "BTC15m Report",
        render_group(summary, latest_window, recent_evaluations),
    )


app.add_typer(record_app, name="record")
