"""Portfolio truth, exposure, PnL, and reconciliation CLI commands."""

from __future__ import annotations

from collections.abc import Sequence

import typer
from rich.console import RenderableType

from pm.auth import AuthProfileStateError, AuthService, AuthValidationError
from pm.cli.support import (
    FUNDER_OPTION,
    LOCAL_JSON_OPTION,
    SIGNER_OPTION,
    build_account_overrides,
    emit_command_error,
    emit_command_output,
)
from pm.common.tables import (
    empty_message,
    render_group,
    row_table,
    section_panel,
    shorten_identifier,
    summary_table,
)
from pm.portfolio import (
    DEFAULT_CLOSED_LIMIT,
    PortfolioClosedPositionItem,
    PortfolioClosedResponse,
    PortfolioCurrentPositionItem,
    PortfolioError,
    PortfolioExposureResponse,
    PortfolioMarketResponse,
    PortfolioNotFoundError,
    PortfolioPnlResponse,
    PortfolioPositionsResponse,
    PortfolioReconciliationResponse,
    PortfolioService,
    PortfolioStateError,
    PortfolioSummaryResponse,
    PortfolioValidationError,
)

app = typer.Typer(
    add_completion=False,
    help="Portfolio truth, exposure, PnL, and reconciliation commands.",
    no_args_is_help=True,
)

LIMIT_OPTION = typer.Option(
    DEFAULT_CLOSED_LIMIT,
    "--limit",
    min=1,
    help="Maximum number of closed positions to return.",
)
MARKET_OPTION = typer.Option(..., "--market", help="Condition id filter.")
JSON_OPTION = LOCAL_JSON_OPTION


def _auth_service(*, signer: str | None, funder: str | None) -> AuthService:
    return AuthService(
        account_overrides=build_account_overrides(
            signer=signer,
            funder=funder,
        )
    )


def _portfolio_service(*, signer: str | None, funder: str | None) -> PortfolioService:
    if signer is None and funder is None:
        return PortfolioService()
    return PortfolioService(auth_service=_auth_service(signer=signer, funder=funder))


@app.command("summary")
def summary(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show a compact account-level portfolio summary."""
    try:
        result = _portfolio_service(signer=signer, funder=funder).summary()
    except (
        PortfolioError,
        PortfolioStateError,
        AuthValidationError,
        AuthProfileStateError,
    ) as exc:
        _emit_portfolio_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_summary(result),
        renderable=_render_summary(result),
        local_json_output=json_output,
    )


@app.command("positions")
def positions(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show current attributed positions."""
    try:
        result = _portfolio_service(signer=signer, funder=funder).positions()
    except (
        PortfolioError,
        PortfolioStateError,
        AuthValidationError,
        AuthProfileStateError,
    ) as exc:
        _emit_portfolio_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_positions(result),
        renderable=_render_positions(result),
        local_json_output=json_output,
    )


@app.command("closed")
def closed(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show closed positions newest-first."""
    try:
        result = _portfolio_service(signer=signer, funder=funder).closed(limit=limit)
    except (
        PortfolioError,
        PortfolioStateError,
        AuthValidationError,
        AuthProfileStateError,
    ) as exc:
        _emit_portfolio_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_closed(result),
        renderable=_render_closed(result),
        local_json_output=json_output,
    )


@app.command("market")
def market(
    ctx: typer.Context,
    market: str = MARKET_OPTION,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show a market-scoped portfolio view."""
    try:
        result = _portfolio_service(signer=signer, funder=funder).market(market=market)
    except (
        PortfolioError,
        PortfolioStateError,
        AuthValidationError,
        AuthProfileStateError,
    ) as exc:
        _emit_portfolio_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_market(result),
        renderable=_render_market(result),
        local_json_output=json_output,
    )


@app.command("exposure")
def exposure(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show gross/net exposure with market and linked strategy slices."""
    try:
        result = _portfolio_service(signer=signer, funder=funder).exposure()
    except (
        PortfolioError,
        PortfolioStateError,
        AuthValidationError,
        AuthProfileStateError,
    ) as exc:
        _emit_portfolio_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_exposure(result),
        renderable=_render_exposure(result),
        local_json_output=json_output,
    )


@app.command("pnl")
def pnl(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show realized, unrealized, and total PnL."""
    try:
        result = _portfolio_service(signer=signer, funder=funder).pnl()
    except (
        PortfolioError,
        PortfolioStateError,
        AuthValidationError,
        AuthProfileStateError,
    ) as exc:
        _emit_portfolio_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_pnl(result),
        renderable=_render_pnl(result),
        local_json_output=json_output,
    )


@app.command("reconcile")
def reconcile(
    ctx: typer.Context,
    signer: str | None = SIGNER_OPTION,
    funder: str | None = FUNDER_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Compare fresh portfolio state against execution reconciliation state."""
    try:
        result = _portfolio_service(signer=signer, funder=funder).reconcile()
    except (
        PortfolioError,
        PortfolioStateError,
        AuthValidationError,
        AuthProfileStateError,
    ) as exc:
        _emit_portfolio_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_reconcile(result),
        renderable=_render_reconcile(result),
        local_json_output=json_output,
    )


def _emit_portfolio_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    json_output: bool,
) -> None:
    hint: dict[str, object] | None = None
    if (
        isinstance(exc, (PortfolioValidationError, AuthValidationError))
        and "No operator account address" in str(exc)
    ):
        hint = {
            "suggested_commands": [
                "pm auth show --json",
                "pm auth profile doctor --json",
                "pm setup guide --json",
            ]
        }

    if isinstance(exc, (PortfolioStateError, AuthProfileStateError)):
        code = "state_error"
    elif isinstance(exc, (PortfolioValidationError, AuthValidationError)):
        code = "invalid_argument"
    elif isinstance(exc, PortfolioNotFoundError):
        code = "not_found"
    else:
        code = "request_failed"
    emit_command_error(
        ctx,
        code=code,
        message=str(exc),
        resource="portfolio",
        local_json_output=json_output,
        hint=hint,
    )


def _summary_rows(response: PortfolioSummaryResponse) -> list[tuple[str, str]]:
    summary = response.summary
    return [
        ("Account", response.account_address),
        ("Snapshot ID", response.snapshot_id),
        ("Created", response.created_at),
        ("Holdings value", summary.holdings_value or "-"),
        ("Realized PnL", summary.realized_pnl_total),
        ("Unrealized PnL", summary.unrealized_pnl_total),
        ("Total PnL", summary.total_pnl),
        ("Gross exposure", summary.gross_exposure),
        ("Net exposure", summary.net_exposure),
        ("Current positions", str(summary.current_positions_count)),
        ("Closed positions", str(summary.closed_positions_count)),
    ]


def _format_summary(response: PortfolioSummaryResponse) -> str:
    return "\n".join(f"{label}: {value}" for label, value in _summary_rows(response))


def _render_summary(response: PortfolioSummaryResponse) -> RenderableType:
    return render_group(
        section_panel(
            "Portfolio Summary",
            summary_table(title="Portfolio Summary", rows=_summary_rows(response)),
        ),
        _render_error_panel(response.errors),
    )


def _format_positions(response: PortfolioPositionsResponse) -> str:
    lines = _format_summary(
        PortfolioSummaryResponse(
            account_address=response.account_address,
            snapshot_id=response.snapshot_id,
            created_at=response.created_at,
            summary=response.summary,
            errors=response.errors,
        )
    ).splitlines()
    lines.append(f"Items: {len(response.items)}")
    return "\n".join(lines)


def _render_positions(response: PortfolioPositionsResponse) -> RenderableType:
    if not response.items:
        table_renderable: RenderableType = empty_message("No current positions.")
    else:
        table_renderable = row_table(
            title="Current Positions",
            columns=[
                "Market",
                "Outcome",
                "Token",
                "Size",
                "Current",
                "Cash PnL",
                "Attribution",
            ],
            rows=[
                [
                    item.position.market_slug or shorten_identifier(item.position.condition_id),
                    item.position.outcome or "-",
                    shorten_identifier(item.position.token_id),
                    item.position.size or "-",
                    item.position.current_value or "-",
                    item.position.cash_pnl or "-",
                    _attribution_label(item),
                ]
                for item in response.items
            ],
        )
    return render_group(
        _render_summary(
            PortfolioSummaryResponse(
                account_address=response.account_address,
                snapshot_id=response.snapshot_id,
                created_at=response.created_at,
                summary=response.summary,
                errors=response.errors,
            )
        ),
        section_panel("Current Positions", table_renderable),
    )


def _format_closed(response: PortfolioClosedResponse) -> str:
    return "\n".join(
        [
            f"Account: {response.account_address}",
            f"Snapshot ID: {response.snapshot_id}",
            f"Created: {response.created_at}",
            f"Closed positions total: {response.total}",
            f"Limit: {response.limit}",
        ]
    )


def _render_closed(response: PortfolioClosedResponse) -> RenderableType:
    if not response.items:
        body: RenderableType = empty_message("No closed positions.")
    else:
        body = row_table(
            title="Closed Positions",
            columns=[
                "Timestamp",
                "Market",
                "Outcome",
                "Token",
                "Realized PnL",
                "Attribution",
            ],
            rows=[
                [
                    str(item.position.timestamp or "-"),
                    item.position.market_slug or shorten_identifier(item.position.condition_id),
                    item.position.outcome or "-",
                    shorten_identifier(item.position.token_id),
                    item.position.realized_pnl or "-",
                    _attribution_label(item),
                ]
                for item in response.items
            ],
        )
    return render_group(
        section_panel(
            "Closed Positions",
            summary_table(
                title="Closed Positions",
                rows=[
                    ("Account", response.account_address),
                    ("Snapshot ID", response.snapshot_id),
                    ("Created", response.created_at),
                    ("Closed positions total", str(response.total)),
                    ("Limit", str(response.limit)),
                ],
            ),
        ),
        section_panel("Closed Position Items", body),
        _render_error_panel(response.errors),
    )


def _format_market(response: PortfolioMarketResponse) -> str:
    market = response.market
    return "\n".join(
        [
            f"Account: {response.account_address}",
            f"Snapshot ID: {response.snapshot_id}",
            f"Condition ID: {market.condition_id}",
            f"Market slug: {market.market_slug or '-'}",
            f"Gross exposure: {market.gross_exposure}",
            f"Net exposure: {market.net_exposure}",
            f"Realized PnL: {market.realized_pnl}",
            f"Unrealized PnL: {market.unrealized_pnl}",
            f"Total PnL: {market.total_pnl}",
        ]
    )


def _render_market(response: PortfolioMarketResponse) -> RenderableType:
    market = response.market
    return render_group(
        section_panel(
            "Market Portfolio",
            summary_table(
                title="Market Portfolio",
                rows=[
                    ("Condition ID", market.condition_id),
                    ("Market slug", market.market_slug or "-"),
                    ("Gross exposure", market.gross_exposure),
                    ("Net exposure", market.net_exposure),
                    ("Realized PnL", market.realized_pnl),
                    ("Unrealized PnL", market.unrealized_pnl),
                    ("Total PnL", market.total_pnl),
                    ("Current positions", str(market.current_positions_count)),
                    ("Closed positions", str(market.closed_positions_count)),
                ],
            ),
        ),
        section_panel(
            "Current Market Positions",
            _positions_table(response.current_positions, title="Current Market Positions"),
        ),
        section_panel(
            "Closed Market Positions",
            _closed_table(response.closed_positions, title="Closed Market Positions"),
        ),
        _render_error_panel(response.errors),
    )


def _format_exposure(response: PortfolioExposureResponse) -> str:
    return "\n".join(
        [
            f"Gross exposure: {response.summary.gross_exposure}",
            f"Net exposure: {response.summary.net_exposure}",
            f"Markets: {len(response.per_market)}",
            f"Strategies: {len(response.per_strategy)}",
        ]
    )


def _render_exposure(response: PortfolioExposureResponse) -> RenderableType:
    return render_group(
        section_panel(
            "Exposure Summary",
            summary_table(
                title="Exposure Summary",
                rows=[
                    ("Account", response.account_address),
                    ("Snapshot ID", response.snapshot_id),
                    ("Gross exposure", response.summary.gross_exposure),
                    ("Net exposure", response.summary.net_exposure),
                    ("Markets", str(len(response.per_market))),
                    ("Strategies", str(len(response.per_strategy))),
                ],
            ),
        ),
        section_panel("Per-Market Exposure", _market_summary_table(response)),
        section_panel("Per-Strategy Exposure", _strategy_summary_table(response)),
        _render_error_panel(response.errors),
    )


def _format_pnl(response: PortfolioPnlResponse) -> str:
    return "\n".join(
        [
            f"Realized PnL: {response.summary.realized_pnl_total}",
            f"Unrealized PnL: {response.summary.unrealized_pnl_total}",
            f"Total PnL: {response.summary.total_pnl}",
            f"Markets: {len(response.per_market)}",
            f"Strategies: {len(response.per_strategy)}",
        ]
    )


def _render_pnl(response: PortfolioPnlResponse) -> RenderableType:
    return render_group(
        section_panel(
            "PnL Summary",
            summary_table(
                title="PnL Summary",
                rows=[
                    ("Account", response.account_address),
                    ("Snapshot ID", response.snapshot_id),
                    ("Realized PnL", response.summary.realized_pnl_total),
                    ("Unrealized PnL", response.summary.unrealized_pnl_total),
                    ("Total PnL", response.summary.total_pnl),
                ],
            ),
        ),
        section_panel("Per-Market PnL", _market_summary_table(response)),
        section_panel("Per-Strategy PnL", _strategy_summary_table(response)),
        _render_error_panel(response.errors),
    )


def _format_reconcile(response: PortfolioReconciliationResponse) -> str:
    return "\n".join(
        [
            f"Reconciliation ID: {response.reconciliation_id}",
            f"Snapshot ID: {response.snapshot_id}",
            f"Execution reconciliation ID: {response.execution_reconciliation_id or '-'}",
            f"Account: {response.account_address}",
            f"Created: {response.created_at}",
            f"Health: {response.summary.health}",
            f"Discrepancies: {response.summary.discrepancy_count}",
        ]
    )


def _render_reconcile(response: PortfolioReconciliationResponse) -> RenderableType:
    summary = summary_table(
        title="Portfolio Reconciliation",
        rows=[
            ("Reconciliation ID", response.reconciliation_id),
            ("Snapshot ID", response.snapshot_id),
            ("Execution reconciliation ID", response.execution_reconciliation_id or "-"),
            ("Account", response.account_address),
            ("Created", response.created_at),
            ("Health", response.summary.health),
            ("Discrepancies", str(response.summary.discrepancy_count)),
            (
                "Execution mismatches",
                str(response.summary.execution_state_mismatch_count),
            ),
            (
                "Unlinked current positions",
                str(response.summary.unlinked_current_position_count),
            ),
            (
                "Missing linked executions",
                str(response.summary.linked_execution_missing_from_positions_count),
            ),
            (
                "Ambiguous strategy links",
                str(response.summary.ambiguous_strategy_link_count),
            ),
        ],
    )
    if not response.discrepancies:
        discrepancy_body: RenderableType = empty_message("No reconciliation discrepancies.")
    else:
        discrepancy_body = row_table(
            title="Reconciliation Discrepancies",
            columns=["Kind", "Severity", "Market", "Token", "Strategy", "Message"],
            rows=[
                [
                    item.kind,
                    item.severity,
                    shorten_identifier(item.condition_id),
                    shorten_identifier(item.token_id),
                    item.strategy_name or "-",
                    item.message,
                ]
                for item in response.discrepancies
            ],
        )
    return render_group(
        section_panel("Portfolio Reconciliation", summary),
        section_panel("Reconciliation Discrepancies", discrepancy_body),
        _render_error_panel(response.errors),
    )


def _positions_table(
    items: list[PortfolioCurrentPositionItem],
    *,
    title: str,
) -> RenderableType:
    if not items:
        return empty_message("No current positions.")
    return row_table(
        title=title,
        columns=["Market", "Outcome", "Token", "Current", "Cash PnL", "Attribution"],
        rows=[
            [
                item.position.market_slug or shorten_identifier(item.position.condition_id),
                item.position.outcome or "-",
                shorten_identifier(item.position.token_id),
                item.position.current_value or "-",
                item.position.cash_pnl or "-",
                _attribution_label(item),
            ]
            for item in items
        ],
    )


def _closed_table(
    items: list[PortfolioClosedPositionItem],
    *,
    title: str,
) -> RenderableType:
    if not items:
        return empty_message("No closed positions.")
    return row_table(
        title=title,
        columns=["Timestamp", "Market", "Outcome", "Token", "Realized PnL", "Attribution"],
        rows=[
            [
                str(item.position.timestamp or "-"),
                item.position.market_slug or shorten_identifier(item.position.condition_id),
                item.position.outcome or "-",
                shorten_identifier(item.position.token_id),
                item.position.realized_pnl or "-",
                _attribution_label(item),
            ]
            for item in items
        ],
    )


def _market_summary_table(
    response: PortfolioExposureResponse | PortfolioPnlResponse,
) -> RenderableType:
    if not response.per_market:
        return empty_message("No market exposure available.")
    return row_table(
        title="Per-Market Summary",
        columns=[
            "Condition",
            "Market",
            "Gross",
            "Net",
            "Realized",
            "Unrealized",
            "Total",
        ],
        rows=[
            [
                shorten_identifier(item.condition_id),
                item.market_slug or "-",
                item.gross_exposure,
                item.net_exposure,
                item.realized_pnl,
                item.unrealized_pnl,
                item.total_pnl,
            ]
            for item in response.per_market
        ],
    )


def _strategy_summary_table(
    response: PortfolioExposureResponse | PortfolioPnlResponse,
) -> RenderableType:
    if not response.per_strategy:
        return empty_message("No linked strategy exposure available.")
    return row_table(
        title="Per-Strategy Summary",
        columns=[
            "Strategy",
            "Type",
            "Gross",
            "Net",
            "Realized",
            "Unrealized",
            "Total",
        ],
        rows=[
            [
                item.strategy_name,
                item.strategy_type or "-",
                item.gross_exposure,
                item.net_exposure,
                item.realized_pnl,
                item.unrealized_pnl,
                item.total_pnl,
            ]
            for item in response.per_strategy
        ],
    )


def _render_error_panel(errors: Sequence[object]) -> RenderableType | None:
    if not errors:
        return None
    return section_panel(
        "Portfolio Errors",
        row_table(
            title="Portfolio Errors",
            columns=["Section", "Code", "Message"],
            rows=[
                [
                    str(getattr(item, "section", "-")),
                    str(getattr(item, "code", "-")),
                    str(getattr(item, "message", "-")),
                ]
                for item in errors
            ],
        ),
    )


def _attribution_label(
    item: PortfolioCurrentPositionItem | PortfolioClosedPositionItem,
) -> str:
    attribution = item.attribution
    if attribution.status == "linked":
        return attribution.strategy_name or "linked"
    if attribution.status == "ambiguous":
        return "ambiguous"
    return "unlinked"
