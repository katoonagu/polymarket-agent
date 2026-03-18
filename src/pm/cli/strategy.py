"""Read-only strategy registry and orchestrator CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.strategy import (
    StrategyCandidateIntent,
    StrategyDecisionMutationResponse,
    StrategyDecisionRecord,
    StrategyDefinition,
    StrategyEvaluateResponse,
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

app = typer.Typer(
    add_completion=False,
    help="Read-only seeded strategy registry and manual orchestrator review commands.",
    no_args_is_help=True,
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
    if isinstance(exc, (StrategyValidationError,)):
        return "invalid_argument"
    if isinstance(exc, (StrategyNotFoundError, StrategyIntentNotFoundError)):
        return "not_found"
    if isinstance(exc, (StrategyRegistryError, StrategyStateError)):
        return "state_error"
    return "request_failed"


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
        "\n".join(_format_source_ref(ref) for ref in item.source_refs)
        if item.source_refs
        else "-",
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
