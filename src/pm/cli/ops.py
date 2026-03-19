"""Operator control plane and workflow session CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.ops import (
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
)

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


def status(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show a compact local operator summary."""
    try:
        result = OpsService().status()
    except (OpsStateError, OpsValidationError) as exc:
        _emit_ops_error(ctx, exc=exc, resource="status", json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_status(result),
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


app.add_typer(session_app, name="session")
app.add_typer(review_app, name="review")
app.add_typer(dispatch_app, name="dispatch")


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


def _format_review_next(response: OpsReviewNextResponse) -> str:
    if response.queue_empty or response.item is None:
        return "Queue empty: true"
    return "\n".join(["Queue empty: false", "", _format_queue_item(response.item)])


def _format_dispatch_approved(response: OpsDispatchApprovedResponse) -> str:
    lines = [
        f"Active session: {response.active_session.session_id if response.active_session else '-'}",
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
