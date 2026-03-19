"""Operator control plane and workflow session CLI commands."""

from __future__ import annotations

import typer
from rich.console import RenderableType

from pm.cli.support import (
    LOCAL_JSON_OPTION,
    emit_command_error,
    emit_command_output,
    resolve_live_confirmation,
)
from pm.common.tables import (
    empty_message,
    format_bool,
    render_group,
    row_table,
    section_panel,
    shorten_identifier,
    summary_table,
)
from pm.execution.models import CapturedExecutionEvent
from pm.ops import (
    OpsBootstrapResponse,
    OpsCycleQueueResponse,
    OpsCycleReportResponse,
    OpsDispatchApprovedResponse,
    OpsQueueItem,
    OpsQueueResponse,
    OpsReportResponse,
    OpsReviewNextResponse,
    OpsService,
    OpsSessionMutationResponse,
    OpsSessionNotFoundError,
    OpsSessionSummarySnapshot,
    OpsStateError,
    OpsStatusResponse,
    OpsValidationError,
    OpsVerboseStatusResponse,
)
from pm.strategy.models import StrategyDispatchResultRecord

app = typer.Typer(
    add_completion=False,
    help="Local-first operator control plane and workflow session commands.",
    no_args_is_help=True,
)
session_app = typer.Typer(
    add_completion=False,
    help="Workflow session lifecycle commands.",
)
review_app = typer.Typer(
    add_completion=False,
    help="Review workflow helper commands.",
)
dispatch_app = typer.Typer(
    add_completion=False,
    help="Paper dispatch helpers for approved strategy intents.",
)
cycle_app = typer.Typer(
    add_completion=False,
    help="Bounded one-cycle operator runbook commands.",
)

LIMIT_OPTION = typer.Option(
    20,
    "--limit",
    min=1,
    help="Maximum number of rows to return or dispatch.",
)
LABEL_OPTION = typer.Option(
    None,
    "--label",
    help="Optional operator label for the session.",
)
JSON_OPTION = LOCAL_JSON_OPTION
PAPER_OPTION = typer.Option(False, "--paper", help="Explicit paper mode. This is the default.")
LIVE_OPTION = typer.Option(
    False,
    "--live",
    help="Run the bounded cycle against live guarded execution paths.",
)
CONFIRM_OPTION = typer.Option(
    False,
    "--confirm",
    help="Required confirmation flag for live bounded cycle execution.",
)


def status(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Include queue and recent activity previews.",
    ),
    json_output: bool = JSON_OPTION,
) -> None:
    """Show a compact local operator summary."""
    try:
        service = OpsService()
        result = service.verbose_status() if verbose else service.status()
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, resource="status", json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_status(result),
        renderable=_render_status(result),
        local_json_output=json_output,
    )


@app.command("bootstrap")
def bootstrap(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Initialize bounded runbook prerequisites and ensure one active session exists."""
    try:
        result = OpsService().bootstrap()
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_bootstrap(result),
        renderable=_render_bootstrap(result),
        local_json_output=json_output,
    )


@app.command("queue")
def queue(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show the combined review and dispatch queue."""
    try:
        result = OpsService().queue(limit=limit)
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_queue(result),
        renderable=_render_queue(response=result),
        local_json_output=json_output,
    )


@cycle_app.command("queue")
def cycle_queue(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run one bounded evaluation pass across all seeded strategies."""
    try:
        result = OpsService().cycle_queue(limit=limit)
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_cycle_queue(result),
        renderable=_render_cycle_queue(result),
        local_json_output=json_output,
    )


@session_app.command("start")
def start_session(
    ctx: typer.Context,
    label: str | None = LABEL_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Start one local operator workflow session."""
    try:
        result = OpsService().start_session(label=label)
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_mutation(result),
        local_json_output=json_output,
    )


@session_app.command("end")
def end_session(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """End the active local operator workflow session."""
    try:
        result = OpsService().end_session()
    except (OpsSessionNotFoundError, OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_session_mutation(result),
        local_json_output=json_output,
    )


@review_app.command("next")
def review_next(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show the next reviewable strategy intent, if one exists."""
    try:
        result = OpsService().review_next()
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_review_next(result),
        local_json_output=json_output,
    )


@dispatch_app.command("approved")
def dispatch_approved(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    paper: bool = PAPER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Paper-dispatch approved intents through the existing guarded bridge."""
    _ = paper
    try:
        result = OpsService().dispatch_approved(limit=limit)
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_dispatch_approved(result),
        renderable=_render_dispatch_approved(result),
        local_json_output=json_output,
    )


@cycle_app.command("approved")
def cycle_approved(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    paper: bool = PAPER_OPTION,
    live: bool = LIVE_OPTION,
    confirm: bool = CONFIRM_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run one bounded dispatch cycle for approved intents."""
    if paper and live:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="Paper and live modes are mutually exclusive.",
            resource="ops",
            identifier="mode",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    confirm = resolve_live_confirmation(
        ctx,
        live=live,
        confirm=confirm,
        local_json_output=json_output,
        resource="ops",
        missing_confirm_message="Live mode requires --confirm.",
        prompt_message="Dispatch approved intents through live guarded execution now?",
        declined_message="Live approved-dispatch cycle cancelled.",
    )

    try:
        result = OpsService().cycle_approved(limit=limit, live=live and confirm)
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_dispatch_approved(result),
        renderable=_render_dispatch_approved(result),
        local_json_output=json_output,
    )


@app.command("report")
def report(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show an operator report for the active or latest completed session."""
    try:
        result = OpsService().report()
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_report(result),
        local_json_output=json_output,
    )


@cycle_app.command("report")
def cycle_report(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show the current bounded runbook summary from persisted local state."""
    try:
        result = OpsService().cycle_report()
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_cycle_report(result),
        renderable=_render_cycle_report(result),
        local_json_output=json_output,
    )


app.add_typer(session_app, name="session")
app.add_typer(review_app, name="review")
app.add_typer(dispatch_app, name="dispatch")
app.add_typer(cycle_app, name="cycle")


def _emit_ops_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    json_output: bool,
    resource: str = "ops",
) -> None:
    if isinstance(exc, OpsValidationError):
        code = "invalid_argument"
    elif isinstance(exc, OpsSessionNotFoundError):
        code = "not_found"
    elif isinstance(exc, OpsStateError):
        code = "state_error"
    else:
        code = "request_failed"
    emit_command_error(
        ctx,
        code=code,
        message=str(exc),
        resource=resource,
        local_json_output=json_output,
    )


def _format_status(response: OpsStatusResponse) -> str:
    lines = [
        f"Active session: {response.active_session.session_id if response.active_session else '-'}",
        f"Pending review: {response.pending_review_count}",
        f"Dispatch ready: {response.approved_dispatch_ready_count}",
        f"Recent strategy executions: {response.recent_strategy_execution_count}",
        f"Recent execution events: {response.recent_execution_event_count}",
        f"Risk policies persisted: {response.risk_policies_persisted}",
        "Latest activity:",
        f"  Intent created: {response.latest_activity.latest_intent_created_at or '-'}",
        f"  Manual decision: {response.latest_activity.latest_manual_decision_at or '-'}",
        f"  Dispatch: {response.latest_activity.latest_dispatch_at or '-'}",
        f"  Execution event: {response.latest_activity.latest_execution_event_at or '-'}",
        f"  Session activity: {response.latest_activity.latest_session_activity_at or '-'}",
    ]
    if isinstance(response, OpsVerboseStatusResponse):
        lines.extend(
            [
                f"Queue preview: {len(response.queue.items)}",
                f"Recent strategy executions preview: {len(response.recent_strategy_executions)}",
                f"Recent execution events preview: {len(response.recent_execution_events)}",
            ]
        )
    return "\n".join(lines)


def _format_queue(response: OpsQueueResponse) -> str:
    lines = [
        f"Total queue items: {response.counts.total}",
        f"Review items: {response.counts.review_total}",
        f"Dispatch items: {response.counts.dispatch_total}",
    ]
    for item in response.items:
        lines.extend(["", _format_queue_item(item)])
    return "\n".join(lines)


def _format_bootstrap(response: OpsBootstrapResponse) -> str:
    return "\n".join(
        [
            f"Ready: {response.ready}",
            f"Risk initialized: {response.risk_initialized}",
            f"Risk policies persisted: {response.risk_policies_persisted}",
            f"Session started: {response.session_started}",
            (
                "Active session: "
                f"{response.active_session.session_id if response.active_session else '-'}"
            ),
        ]
    )


def _format_cycle_queue(response: OpsCycleQueueResponse) -> str:
    lines = [
        f"Active session: {response.active_session.session_id if response.active_session else '-'}",
        f"Limit per strategy: {response.limit_per_strategy}",
        f"Total new intents: {response.total_new_intents}",
        f"Queue review: {response.queue_counts.review_total}",
        f"Queue dispatch: {response.queue_counts.dispatch_total}",
    ]
    for item in response.items:
        lines.extend(
            [
                "",
                f"Strategy: {item.strategy_name}",
                f"Type: {item.strategy_type}",
                f"New intents: {item.total_new_intents}",
                f"Errors: {item.total_errors}",
            ]
        )
    return "\n".join(lines)


def _render_status(response: OpsStatusResponse) -> RenderableType:
    summary = summary_table(
        title="Operator Status",
        rows=[
            (
                "Active session",
                response.active_session.session_id if response.active_session else "-",
            ),
            ("Pending review", str(response.pending_review_count)),
            ("Dispatch ready", str(response.approved_dispatch_ready_count)),
            (
                "Recent strategy executions",
                str(response.recent_strategy_execution_count),
            ),
            ("Recent execution events", str(response.recent_execution_event_count)),
            ("Risk policies persisted", format_bool(response.risk_policies_persisted)),
            ("Latest intent", response.latest_activity.latest_intent_created_at or "-"),
            (
                "Latest manual decision",
                response.latest_activity.latest_manual_decision_at or "-",
            ),
            ("Latest dispatch", response.latest_activity.latest_dispatch_at or "-"),
            (
                "Latest execution event",
                response.latest_activity.latest_execution_event_at or "-",
            ),
        ],
    )
    if not isinstance(response, OpsVerboseStatusResponse):
        return section_panel("Operator Status", summary)
    return render_group(
        section_panel("Operator Status", summary),
        _render_queue(response=response.queue),
        _render_status_executions(response.recent_strategy_executions),
        _render_status_events(response.recent_execution_events),
    )


def _render_bootstrap(response: OpsBootstrapResponse) -> RenderableType:
    summary = summary_table(
        title="Runbook Bootstrap",
        rows=[
            ("Ready", format_bool(response.ready)),
            ("Risk initialized", format_bool(response.risk_initialized)),
            ("Risk policies persisted", format_bool(response.risk_policies_persisted)),
            ("Session started", format_bool(response.session_started)),
            (
                "Active session",
                response.active_session.session_id if response.active_session else "-",
            ),
        ],
    )
    return render_group(
        section_panel("Runbook Bootstrap", summary),
        _render_status(response.status),
    )


def _render_queue(*, response: OpsQueueResponse) -> RenderableType:
    summary = summary_table(
        title="Queue Summary",
        rows=[
            ("Total", str(response.counts.total)),
            ("Review", str(response.counts.review_total)),
            ("Dispatch", str(response.counts.dispatch_total)),
        ],
    )
    if not response.items:
        return render_group(
            section_panel("Queue Summary", summary),
            section_panel("Operator Queue", empty_message("No queue items.")),
        )
    table = row_table(
        title="Operator Queue",
        columns=[
            "Kind",
            "Intent ID",
            "Strategy",
            "Current",
            "Market",
            "Outcome",
            "Created",
        ],
        rows=[
            [
                item.kind,
                shorten_identifier(item.intent.intent.intent_id),
                item.intent.intent.strategy_name,
                item.intent.current_decision,
                item.intent.intent.market_slug or "-",
                item.intent.intent.outcome or "-",
                item.intent.intent.created_at,
            ]
            for item in response.items
        ],
    )
    return render_group(
        section_panel("Queue Summary", summary),
        section_panel("Operator Queue", table),
    )


def _render_cycle_queue(response: OpsCycleQueueResponse) -> RenderableType:
    summary = summary_table(
        title="Cycle Queue Summary",
        rows=[
            (
                "Active session",
                response.active_session.session_id if response.active_session else "-",
            ),
            ("Limit per strategy", str(response.limit_per_strategy)),
            ("Total new intents", str(response.total_new_intents)),
            ("Queue review", str(response.queue_counts.review_total)),
            ("Queue dispatch", str(response.queue_counts.dispatch_total)),
        ],
    )
    table = row_table(
        title="Strategy Evaluation Pass",
        columns=["Strategy", "Type", "New Intents", "Errors"],
        rows=[
            [
                item.strategy_name,
                item.strategy_type,
                str(item.total_new_intents),
                str(item.total_errors),
            ]
            for item in response.items
        ],
    )
    return render_group(
        section_panel("Cycle Queue Summary", summary),
        section_panel("Strategy Evaluation Pass", table),
    )


def _render_status_executions(
    items: list[StrategyDispatchResultRecord],
) -> RenderableType:
    if not items:
        return section_panel(
            "Recent Strategy Executions",
            empty_message("No recent strategy executions."),
        )
    return section_panel(
        "Recent Strategy Executions",
        row_table(
            title="Recent Strategy Executions",
            columns=[
                "Execution ID",
                "Intent ID",
                "Decision",
                "Mode",
                "Market",
                "Created",
            ],
            rows=[
                [
                    shorten_identifier(item.execution_id),
                    shorten_identifier(item.intent_id),
                    item.decision,
                    item.mode,
                    item.market_slug or "-",
                    item.created_at,
                ]
                for item in items
            ],
        ),
    )


def _render_dispatch_approved(response: OpsDispatchApprovedResponse) -> RenderableType:
    summary = summary_table(
        title="Dispatch Cycle Summary",
        rows=[
            (
                "Active session",
                response.active_session.session_id if response.active_session else "-",
            ),
            ("Mode", response.mode),
            ("No-op", format_bool(response.noop)),
            ("Candidates", str(response.total_candidates)),
            ("Dispatched", str(response.total_dispatched)),
            ("Skipped", str(response.total_skipped)),
        ],
    )
    if not response.items:
        return render_group(
            section_panel("Dispatch Cycle Summary", summary),
            section_panel(
                "Dispatch Results",
                empty_message("No approved intents were dispatched."),
            ),
        )
    table = row_table(
        title="Dispatch Results",
        columns=["Execution ID", "Intent ID", "Decision", "Mode", "Order ID", "Created"],
        rows=[
            [
                shorten_identifier(item.execution.execution_id),
                shorten_identifier(item.intent.intent.intent_id),
                item.execution.decision,
                item.execution.mode,
                shorten_identifier(item.execution.order_id),
                item.execution.created_at,
            ]
            for item in response.items
        ],
    )
    return render_group(
        section_panel("Dispatch Cycle Summary", summary),
        section_panel("Dispatch Results", table),
    )


def _render_status_events(items: list[CapturedExecutionEvent]) -> RenderableType:
    if not items:
        return section_panel(
            "Recent Execution Events",
            empty_message("No recent execution events."),
        )
    return section_panel(
        "Recent Execution Events",
        row_table(
            title="Recent Execution Events",
            columns=[
                "Captured",
                "Order ID",
                "Condition",
                "Event",
                "Trade",
                "Status",
            ],
            rows=[
                [
                    item.captured_at,
                    shorten_identifier(item.order_id),
                    shorten_identifier(item.condition_id),
                    item.event_type,
                    item.trade_status or "-",
                    item.status or "-",
                ]
                for item in items
            ],
        ),
    )


def _format_review_next(response: OpsReviewNextResponse) -> str:
    if response.queue_empty or response.item is None:
        return "Queue empty: true"
    return "\n".join(["Queue empty: false", "", _format_queue_item(response.item)])


def _format_dispatch_approved(response: OpsDispatchApprovedResponse) -> str:
    lines = [
        f"Active session: {response.active_session.session_id if response.active_session else '-'}",
        f"Mode: {response.mode}",
        f"No-op: {response.noop}",
        f"Candidates: {response.total_candidates}",
        f"Dispatched: {response.total_dispatched}",
        f"Skipped: {response.total_skipped}",
    ]
    for item in response.items:
        lines.extend(
            [
                "",
                f"Execution ID: {item.execution.execution_id}",
                f"Intent ID: {item.intent.intent.intent_id}",
                f"Decision: {item.execution.decision}",
                f"Mode: {item.execution.mode}",
                f"Order ID: {item.execution.order_id or '-'}",
            ]
        )
    return "\n".join(lines)


def _format_session_mutation(response: OpsSessionMutationResponse) -> str:
    lines = [
        f"Action: {response.action}",
        f"Session ID: {response.session.session_id}",
        f"Label: {response.session.label or '-'}",
        f"Started at: {response.session.started_at}",
        f"Ended at: {response.session.ended_at or '-'}",
        f"Active: {response.session.active}",
    ]
    if response.session.summary_snapshot is not None:
        lines.extend(["Summary:", _format_summary(response.session.summary_snapshot)])
    return "\n".join(lines)


def _format_report(response: OpsReportResponse) -> str:
    lines = [
        f"Session ID: {response.session.session_id if response.session else '-'}",
        f"Queue total: {response.queue_counts.total}",
        f"Queue review: {response.queue_counts.review_total}",
        f"Queue dispatch: {response.queue_counts.dispatch_total}",
        "Summary:",
        _format_summary(response.summary),
        f"Recent strategy executions: {len(response.recent_strategy_executions)}",
        f"Recent execution events: {len(response.recent_execution_events)}",
    ]
    return "\n".join(lines)


def _format_cycle_report(response: OpsCycleReportResponse) -> str:
    latest_reconciliation = (
        response.latest_reconciliation.reconciliation_id
        if response.latest_reconciliation is not None
        else "-"
    )
    return "\n".join(
        [
            f"Session ID: {response.session.session_id if response.session else '-'}",
            f"Queue total: {response.queue_counts.total}",
            f"Queue review: {response.queue_counts.review_total}",
            f"Queue dispatch: {response.queue_counts.dispatch_total}",
            f"Approved intents: {response.approved_intent_count}",
            f"Dispatch-ready intents: {response.dispatch_ready_intent_count}",
            f"Recent strategy executions: {len(response.recent_strategy_executions)}",
            f"Recent execution events: {len(response.recent_execution_events)}",
            f"Latest reconciliation: {latest_reconciliation}",
        ]
    )


def _format_summary(summary: OpsSessionSummarySnapshot) -> str:
    return "\n".join(
        [
            f"  Pending review: {summary.pending_review_count}",
            f"  Dispatch ready: {summary.approved_dispatch_ready_count}",
            f"  Manual reviews: {summary.manual_review_count}",
            f"  Approvals: {summary.approval_count}",
            f"  Rejections: {summary.rejection_count}",
            f"  Dispatch attempts: {summary.dispatch_attempt_count}",
            f"  WOULD_POST: {summary.would_post_count}",
            f"  POSTED: {summary.posted_count}",
            f"  SKIP: {summary.skipped_count}",
            f"  Execution events: {summary.execution_event_count}",
        ]
    )


def _format_queue_item(item: OpsQueueItem) -> str:
    intent = item.intent.intent
    return "\n".join(
        [
            f"Kind: {item.kind}",
            f"Note: {item.note}",
            f"Intent ID: {intent.intent_id}",
            f"Strategy: {intent.strategy_name}",
            f"Current decision: {item.intent.current_decision}",
            f"Derived decision: {intent.decision}",
            f"Market slug: {intent.market_slug or '-'}",
            f"Condition ID: {intent.condition_id or '-'}",
            f"Outcome: {intent.outcome or '-'}",
            f"Side: {intent.side or '-'}",
            f"Created at: {intent.created_at}",
        ]
    )


def _render_cycle_report(response: OpsCycleReportResponse) -> RenderableType:
    summary = summary_table(
        title="Cycle Report",
        rows=[
            ("Session", response.session.session_id if response.session else "-"),
            ("Queue total", str(response.queue_counts.total)),
            ("Queue review", str(response.queue_counts.review_total)),
            ("Queue dispatch", str(response.queue_counts.dispatch_total)),
            ("Approved intents", str(response.approved_intent_count)),
            ("Dispatch-ready intents", str(response.dispatch_ready_intent_count)),
            (
                "Latest reconciliation",
                (
                    response.latest_reconciliation.reconciliation_id
                    if response.latest_reconciliation is not None
                    else "-"
                ),
            ),
        ],
    )
    return render_group(
        section_panel("Cycle Report", summary),
        _render_status_executions(response.recent_strategy_executions),
        _render_status_events(response.recent_execution_events),
        _render_latest_reconciliation(response),
    )


def _render_latest_reconciliation(response: OpsCycleReportResponse) -> RenderableType:
    if response.latest_reconciliation is None:
        return section_panel(
            "Latest Reconciliation",
            empty_message("No persisted reconciliation state."),
        )
    reconciliation = response.latest_reconciliation
    return section_panel(
        "Latest Reconciliation",
        summary_table(
            title="Latest Reconciliation",
            rows=[
                ("Reconciliation ID", reconciliation.reconciliation_id),
                ("Created", reconciliation.created_at),
                ("Window events", str(reconciliation.summary.window_event_count)),
                ("Total orders", str(reconciliation.summary.total_orders)),
                ("Consistent open", str(reconciliation.summary.consistent_open)),
                ("Consistent closed", str(reconciliation.summary.consistent_closed)),
                ("Inconclusive", str(reconciliation.summary.inconclusive)),
                ("Mismatch", str(reconciliation.summary.mismatch)),
            ],
        ),
    )
