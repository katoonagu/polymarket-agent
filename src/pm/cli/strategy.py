"""Read-only strategy registry and orchestrator CLI commands."""

from __future__ import annotations

import typer
from rich.console import RenderableType

from pm.cli.strategy_btc15m import app as btc15m_app
from pm.cli.support import (
    LOCAL_JSON_OPTION,
    emit_command_error,
    emit_command_output,
    resolve_live_confirmation,
)
from pm.common.tables import empty_message, row_table, section_panel, shorten_identifier
from pm.strategy import (
    StrategyCandidateIntent,
    StrategyDecisionMutationResponse,
    StrategyDecisionRecord,
    StrategyDefinition,
    StrategyDispatchPendingResponse,
    StrategyDispatchResponse,
    StrategyDispatchResultRecord,
    StrategyEvaluateResponse,
    StrategyExecutionDetailResponse,
    StrategyExecutionNotFoundError,
    StrategyExecutionRequest,
    StrategyExecutionsResponse,
    StrategyIntentNotFoundError,
    StrategyIntentsResponse,
    StrategyIntentView,
    StrategyListResponse,
    StrategyNotFoundError,
    StrategyReasonBlock,
    StrategyRegistryError,
    StrategyReviewResponse,
    StrategySectionError,
    StrategyService,
    StrategyShowResponse,
    StrategySourceReference,
    StrategyStateError,
    StrategyValidationError,
    StrategyValidationResult,
)
from pm.strategy.dispatch import StrategyDispatchService, StrategyDispatchValidationError

app = typer.Typer(
    add_completion=False,
    help="Seeded strategy registry, manual review, and guarded dispatch commands.",
    no_args_is_help=True,
)
dispatch_app = typer.Typer(
    add_completion=False,
    help="Guarded manual strategy dispatch commands.",
    invoke_without_command=True,
    no_args_is_help=False,
)
execution_app = typer.Typer(
    add_completion=False,
    help="Persisted strategy execution detail commands.",
)

NAME_OPTION = typer.Option(
    ...,
    "--name",
    help="Seeded strategy name.",
)
INTENT_ID_OPTION = typer.Option(
    ...,
    "--intent-id",
    help="Persisted strategy intent id.",
)
LIMIT_OPTION = typer.Option(
    20,
    "--limit",
    min=1,
    help="Maximum number of source artifacts or persisted rows to inspect.",
)
REASON_OPTION = typer.Option(
    ...,
    "--reason",
    help="Required operator reason for a manual reject decision.",
)
JSON_OPTION = LOCAL_JSON_OPTION
PAPER_OPTION = typer.Option(False, "--paper", help="Explicit paper mode. This is the default.")
LIVE_OPTION = typer.Option(False, "--live", help="Allow a live strategy dispatch.")
CONFIRM_OPTION = typer.Option(False, "--confirm", help="Required together with --live.")
EXECUTION_ID_OPTION = typer.Option(
    ...,
    "--execution-id",
    help="Persisted strategy execution id.",
)


@app.command("list")
def list_strategies(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """List seeded strategies in registry order."""
    try:
        result = StrategyService().list_strategies()
    except StrategyRegistryError as exc:
        _emit_strategy_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_list(result),
        local_json_output=json_output,
    )


@app.command("show")
def show_strategy(
    ctx: typer.Context,
    name: str = NAME_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show one seeded strategy definition."""
    try:
        result = StrategyService().show_strategy(name)
    except (StrategyNotFoundError, StrategyRegistryError) as exc:
        _emit_strategy_error(ctx, exc=exc, identifier=name.strip().lower(), json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_show(result),
        local_json_output=json_output,
    )


@app.command("validate")
def validate_strategy(
    ctx: typer.Context,
    name: str = NAME_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Validate one seeded strategy plus required local inputs."""
    try:
        result = StrategyService().validate_strategy(name)
    except (StrategyNotFoundError, StrategyRegistryError, StrategyStateError) as exc:
        _emit_strategy_error(ctx, exc=exc, identifier=name.strip().lower(), json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_validation(result),
        local_json_output=json_output,
    )


@app.command("evaluate")
def evaluate_strategy(
    ctx: typer.Context,
    name: str = NAME_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Evaluate one seeded strategy and persist any new candidate intents."""
    try:
        result = StrategyService().evaluate_strategy(name, limit=limit)
    except (
        StrategyNotFoundError,
        StrategyRegistryError,
        StrategyStateError,
        StrategyValidationError,
    ) as exc:
        _emit_strategy_error(ctx, exc=exc, identifier=name.strip().lower(), json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_evaluate(result),
        local_json_output=json_output,
    )


@app.command("intents")
def list_intents(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """List persisted candidate intents in reverse-chronological order."""
    try:
        result = StrategyService().list_intents(limit=limit)
    except (StrategyRegistryError, StrategyStateError, StrategyValidationError) as exc:
        _emit_strategy_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_intents(result),
        renderable=_render_strategy_intents(result),
        local_json_output=json_output,
    )


@app.command("review")
def review_intent(
    ctx: typer.Context,
    intent_id: str = INTENT_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Review one persisted candidate intent and its manual decision history."""
    try:
        result = StrategyService().review_intent(intent_id)
    except (StrategyIntentNotFoundError, StrategyRegistryError, StrategyStateError) as exc:
        _emit_strategy_error(
            ctx,
            exc=exc,
            resource="intent",
            identifier=intent_id.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_review(result),
        local_json_output=json_output,
    )


@app.command("approve")
def approve_intent(
    ctx: typer.Context,
    intent_id: str = INTENT_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Append a manual APPROVE decision for one candidate intent."""
    try:
        result = StrategyService().approve_intent(intent_id)
    except (StrategyIntentNotFoundError, StrategyRegistryError, StrategyStateError) as exc:
        _emit_strategy_error(
            ctx,
            exc=exc,
            resource="intent",
            identifier=intent_id.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_mutation("Approved", result),
        local_json_output=json_output,
    )


@app.command("reject")
def reject_intent(
    ctx: typer.Context,
    intent_id: str = INTENT_ID_OPTION,
    reason: str = REASON_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Append a manual REJECT decision for one candidate intent."""
    try:
        result = StrategyService().reject_intent(intent_id, reason=reason)
    except (
        StrategyIntentNotFoundError,
        StrategyRegistryError,
        StrategyStateError,
        StrategyValidationError,
    ) as exc:
        _emit_strategy_error(
            ctx,
            exc=exc,
            resource="intent",
            identifier=intent_id.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_mutation("Rejected", result),
        local_json_output=json_output,
    )


@dispatch_app.callback()
def dispatch_intent(
    ctx: typer.Context,
    intent_id: str | None = typer.Option(None, "--intent-id", help="Persisted strategy intent id."),
    paper: bool = PAPER_OPTION,
    live: bool = LIVE_OPTION,
    confirm: bool = CONFIRM_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Dispatch one approved strategy intent into the execution layer."""
    if ctx.invoked_subcommand is not None:
        return
    if intent_id is None or not intent_id.strip():
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="Intent id is required.",
            resource="strategy",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    confirm = _guard_dispatch_flags(
        ctx,
        paper=paper,
        live=live,
        confirm=confirm,
        json_output=json_output,
    )
    try:
        result = StrategyDispatchService().dispatch_intent(intent_id, live=live)
    except (
        StrategyDispatchValidationError,
        StrategyIntentNotFoundError,
        StrategyRegistryError,
        StrategyStateError,
    ) as exc:
        _emit_strategy_error(
            ctx,
            exc=exc,
            resource="intent",
            identifier=intent_id.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_dispatch(result),
        local_json_output=json_output,
    )


@dispatch_app.command("pending")
def dispatch_pending(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    paper: bool = PAPER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Paper-dispatch newest approved, undispatched strategy intents."""
    _ = paper
    try:
        result = StrategyDispatchService().dispatch_pending(limit=limit)
    except (
        StrategyDispatchValidationError,
        StrategyRegistryError,
        StrategyStateError,
    ) as exc:
        _emit_strategy_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_dispatch_pending(result),
        local_json_output=json_output,
    )


@app.command("executions")
def list_executions(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """List persisted strategy dispatch results newest-first."""
    try:
        result = StrategyDispatchService().list_executions(limit=limit)
    except (
        StrategyDispatchValidationError,
        StrategyRegistryError,
        StrategyStateError,
    ) as exc:
        _emit_strategy_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_executions(result),
        renderable=_render_strategy_executions(result),
        local_json_output=json_output,
    )


@execution_app.command("get")
def get_execution(
    ctx: typer.Context,
    execution_id: str = EXECUTION_ID_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show one persisted strategy execution detail payload."""
    try:
        result = StrategyDispatchService().get_execution(execution_id)
    except (
        StrategyDispatchValidationError,
        StrategyExecutionNotFoundError,
        StrategyRegistryError,
        StrategyStateError,
    ) as exc:
        _emit_strategy_error(
            ctx,
            exc=exc,
            resource="execution",
            identifier=execution_id.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_strategy_execution_detail(result),
        local_json_output=json_output,
    )


app.add_typer(dispatch_app, name="dispatch")
app.add_typer(execution_app, name="execution")
app.add_typer(btc15m_app, name="btc15m")


def _emit_strategy_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    identifier: str | None = None,
    resource: str = "strategy",
    json_output: bool = False,
) -> None:
    emit_command_error(
        ctx,
        code=_strategy_error_code(exc),
        message=str(exc),
        resource=resource,
        identifier=identifier,
        local_json_output=json_output,
    )


def _strategy_error_code(exc: Exception) -> str:
    if isinstance(exc, (StrategyValidationError, StrategyDispatchValidationError)):
        return "invalid_argument"
    if isinstance(
        exc,
        (StrategyNotFoundError, StrategyIntentNotFoundError, StrategyExecutionNotFoundError),
    ):
        return "not_found"
    if isinstance(exc, (StrategyRegistryError, StrategyStateError)):
        return "state_error"
    return "request_failed"


def _guard_dispatch_flags(
    ctx: typer.Context,
    *,
    paper: bool,
    live: bool,
    confirm: bool = False,
    json_output: bool,
) -> bool:
    if paper and live:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="Use either --paper or --live, not both.",
            resource="strategy",
            local_json_output=json_output,
        )
        raise typer.Exit(1)
    return resolve_live_confirmation(
        ctx,
        live=live,
        confirm=confirm,
        local_json_output=json_output,
        resource="strategy",
        missing_confirm_message="Live strategy dispatch requires both --live and --confirm.",
        prompt_message="Dispatch this approved strategy intent to live execution now?",
        declined_message="Live strategy dispatch cancelled.",
    )


def _format_strategy_list(response: StrategyListResponse) -> str:
    if not response.items:
        return "No seeded strategies."
    return "\n\n".join(_format_strategy_definition(item) for item in response.items)


def _format_strategy_show(response: StrategyShowResponse) -> str:
    return _format_strategy_definition(response.strategy)


def _format_strategy_validation(response: StrategyValidationResult) -> str:
    lines = [
        _format_strategy_definition(response.strategy),
        f"Valid: {'yes' if response.valid else 'no'}",
        "Checks:",
        "\n".join(_format_reason_block(item) for item in response.reason_blocks)
        if response.reason_blocks
        else "-",
    ]
    if response.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in response.errors)
    return "\n".join(lines)


def _format_strategy_evaluate(response: StrategyEvaluateResponse) -> str:
    lines = [
        _format_strategy_definition(response.strategy),
        f"New intents: {response.total}",
        "Items:",
        "\n\n".join(_format_intent(intent) for intent in response.items) if response.items else "-",
    ]
    if response.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in response.errors)
    return "\n".join(lines)


def _format_strategy_intents(response: StrategyIntentsResponse) -> str:
    if not response.items:
        return "No persisted strategy intents."
    return "\n\n".join(_format_intent_view(item) for item in response.items)


def _render_strategy_intents(response: StrategyIntentsResponse) -> RenderableType:
    if not response.items:
        return section_panel("Strategy Intents", empty_message("No persisted strategy intents."))
    return section_panel(
        "Strategy Intents",
        row_table(
            title="Strategy Intents",
            columns=[
                "Intent ID",
                "Strategy",
                "Current",
                "Derived",
                "Market",
                "Outcome",
                "Created",
            ],
            rows=[
                [
                    shorten_identifier(item.intent.intent_id),
                    item.intent.strategy_name,
                    item.current_decision,
                    item.intent.decision,
                    item.intent.market_slug or "-",
                    item.intent.outcome or "-",
                    item.intent.created_at,
                ]
                for item in response.items
            ],
        ),
    )


def _format_strategy_review(response: StrategyReviewResponse) -> str:
    lines = [
        _format_intent_view(response.intent),
        "Decision history:",
        "\n".join(_format_decision(item) for item in response.decision_history)
        if response.decision_history
        else "-",
    ]
    if response.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in response.errors)
    return "\n".join(lines)


def _format_strategy_mutation(action: str, response: StrategyDecisionMutationResponse) -> str:
    return "\n".join([f"{action} strategy intent.", _format_intent_view(response.intent)])


def _format_strategy_dispatch(response: StrategyDispatchResponse) -> str:
    lines = [
        _format_intent_view(response.intent),
        "",
        f"Execution ID: {response.execution.execution_id}",
        f"Mode: {response.execution.mode}",
        f"Decision: {response.execution.decision}",
        f"Execution plan ID: {response.execution.execution_plan_id or '-'}",
        f"Execution result ID: {response.execution.execution_result_id or '-'}",
        f"Order ID: {response.execution.order_id or '-'}",
        "Risk checks:",
        "\n".join(_format_reason_block(item) for item in response.execution.risk_checks)
        if response.execution.risk_checks
        else "-",
    ]
    if response.execution.execution_request is not None:
        lines.extend(
            [
                "Execution request:",
                _format_execution_request(response.execution.execution_request),
            ]
        )
    if response.execution.execution_reasons:
        lines.extend(
            [
                "Execution reasons:",
                "\n".join(
                    _format_reason_block(item) for item in response.execution.execution_reasons
                ),
            ]
        )
    return "\n".join(lines)


def _format_strategy_dispatch_pending(response: StrategyDispatchPendingResponse) -> str:
    lines = [
        f"Candidates: {response.total_candidates}",
        f"Dispatched: {response.total_dispatched}",
        f"Skipped: {response.total_skipped}",
    ]
    for item in response.items:
        lines.extend(["", _format_strategy_dispatch(item)])
    return "\n".join(lines)


def _format_strategy_executions(response: StrategyExecutionsResponse) -> str:
    if not response.items:
        return "No persisted strategy executions."
    return "\n\n".join(_format_execution_record(item) for item in response.items)


def _render_strategy_executions(response: StrategyExecutionsResponse) -> RenderableType:
    if not response.items:
        return section_panel(
            "Strategy Executions",
            empty_message("No persisted strategy executions."),
        )
    return section_panel(
        "Strategy Executions",
        row_table(
            title="Strategy Executions",
            columns=[
                "Execution ID",
                "Intent ID",
                "Decision",
                "Mode",
                "Market",
                "Order ID",
                "Created",
            ],
            rows=[
                [
                    shorten_identifier(item.execution_id),
                    shorten_identifier(item.intent_id),
                    item.decision,
                    item.mode,
                    item.market_slug or "-",
                    shorten_identifier(item.order_id),
                    item.created_at,
                ]
                for item in response.items
            ],
        ),
    )


def _format_strategy_execution_detail(response: StrategyExecutionDetailResponse) -> str:
    lines = [
        _format_execution_record(response.execution),
        "",
        f"Linked intent ID: {response.link.intent_id}",
        f"Linked execution plan ID: {response.link.execution_plan_id or '-'}",
        f"Linked execution result ID: {response.link.execution_result_id or '-'}",
    ]
    if response.intent is not None:
        lines.extend(["", _format_intent_view(response.intent)])
    return "\n".join(lines)


def _format_strategy_definition(item: StrategyDefinition) -> str:
    settings = ", ".join(f"{key}={value}" for key, value in item.settings.items())
    return "\n".join(
        [
            f"Name: {item.name}",
            f"Type: {item.strategy_type}",
            f"Description: {item.description}",
            "Required state files: "
            f"{', '.join(item.required_state_files) if item.required_state_files else '-'}",
            f"Settings: {settings if item.settings else '-'}",
        ]
    )


def _format_intent_view(item: StrategyIntentView) -> str:
    lines = [
        _format_intent(item.intent),
        f"Current decision: {item.current_decision}",
        "Latest manual decision: "
        f"{item.latest_decision.decision if item.latest_decision is not None else '-'}",
    ]
    if item.latest_decision is not None:
        lines.extend(
            [
                f"Latest decided at: {item.latest_decision.decided_at}",
                f"Latest reason: {item.latest_decision.reason or '-'}",
            ]
        )
    return "\n".join(lines)


def _format_intent(item: StrategyCandidateIntent) -> str:
    lines = [
        f"Intent ID: {item.intent_id}",
        f"Strategy name: {item.strategy_name}",
        f"Strategy type: {item.strategy_type}",
        f"Source kind: {item.source_kind}",
        f"Market slug: {item.market_slug or '-'}",
        f"Condition ID: {item.condition_id or '-'}",
        f"Token ID: {item.token_id or '-'}",
        f"Side: {item.side or '-'}",
        f"Outcome: {item.outcome or '-'}",
        f"Decision: {item.decision}",
        f"Created at: {item.created_at}",
        "Reason blocks:",
        "\n".join(_format_reason_block(reason) for reason in item.reason_blocks)
        if item.reason_blocks
        else "-",
        "Source refs:",
        "\n".join(_format_source_ref(ref) for ref in item.source_refs) if item.source_refs else "-",
    ]
    return "\n".join(lines)


def _format_reason_block(item: StrategyReasonBlock) -> str:
    return f"  {item.section}: {item.status} - {item.message}"


def _format_section_error(item: StrategySectionError) -> str:
    return f"  {item.section}: {item.code} - {item.message}"


def _format_source_ref(item: StrategySourceReference) -> str:
    return f"  {item.source_kind}: {item.reference_id} ({item.label or '-'})"


def _format_decision(item: StrategyDecisionRecord) -> str:
    return "\n".join(
        [
            f"  Decision: {item.decision}",
            f"  Decided at: {item.decided_at}",
            f"  Reason: {item.reason or '-'}",
        ]
    )


def _format_execution_record(item: StrategyDispatchResultRecord) -> str:
    lines = [
        f"Execution ID: {item.execution_id}",
        f"Intent ID: {item.intent_id}",
        f"Strategy name: {item.strategy_name}",
        f"Mode: {item.mode}",
        f"Decision: {item.decision}",
        f"Created at: {item.created_at}",
        f"Market slug: {item.market_slug or '-'}",
        f"Condition ID: {item.condition_id or '-'}",
        f"Token ID: {item.token_id or '-'}",
        f"Outcome: {item.outcome or '-'}",
        f"Side: {item.side or '-'}",
        f"Execution plan ID: {item.execution_plan_id or '-'}",
        f"Execution result ID: {item.execution_result_id or '-'}",
        f"Order ID: {item.order_id or '-'}",
    ]
    if item.execution_request is not None:
        lines.extend(["Execution request:", _format_execution_request(item.execution_request)])
    lines.extend(
        [
            "Risk checks:",
            "\n".join(_format_reason_block(reason) for reason in item.risk_checks)
            if item.risk_checks
            else "-",
        ]
    )
    if item.execution_reasons:
        lines.extend(
            [
                "Execution reasons:",
                "\n".join(_format_reason_block(reason) for reason in item.execution_reasons),
            ]
        )
    return "\n".join(lines)


def _format_execution_request(item: StrategyExecutionRequest) -> str:
    return "\n".join(
        [
            f"  Market ref: {item.market_ref}",
            f"  Price: {item.price}",
            f"  Size: {item.size}",
            f"  Notional USDC: {item.notional_usdc}",
            f"  Order type: {item.order_type}",
            f"  Post only: {item.post_only}",
        ]
    )
