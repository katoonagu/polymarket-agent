"""Tracked-wallet registry and shadow-intelligence CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import emit_command_error, emit_command_output
from pm.data import DataClientError, DataNotFoundError, DataValidationError
from pm.data.models import (
    NormalizedActivity,
    NormalizedCurrentPosition,
    NormalizedTrade,
)
from pm.wallet import (
    TrackedWallet,
    WalletActivityResponse,
    WalletAlreadyTrackedError,
    WalletListResponse,
    WalletMutationResponse,
    WalletNotTrackedError,
    WalletPositionsResponse,
    WalletRegistryError,
    WalletSectionError,
    WalletShadowService,
    WalletSnapshotItem,
    WalletSnapshotResponse,
    WalletSummaryResponse,
    WalletTradesResponse,
)

app = typer.Typer(
    add_completion=False,
    help="Local tracked-wallet registry and read-only shadow intelligence.",
    no_args_is_help=True,
)
ADDRESS_OPTION = typer.Option(
    ...,
    "--address",
    help="Tracked 0x-prefixed EVM wallet address.",
)
LABEL_OPTION = typer.Option(
    None,
    "--label",
    help="Optional local label for the tracked wallet.",
)
TAG_OPTION = typer.Option(
    None,
    "--tag",
    help="Repeatable local tag for the tracked wallet.",
)
NOTE_OPTION = typer.Option(
    None,
    "--note",
    help="Optional local note for the tracked wallet.",
)
JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Emit deterministic JSON output for automation and tests.",
)
SUMMARY_LIMIT_OPTION = typer.Option(
    5,
    "--limit",
    min=1,
    help="Maximum number of recent trades and activity rows to include.",
)
REPORT_LIMIT_OPTION = typer.Option(
    20,
    "--limit",
    min=1,
    help="Maximum number of rows to return.",
)


@app.command("add")
def add_wallet(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    label: str | None = LABEL_OPTION,
    tag: list[str] | None = TAG_OPTION,
    note: str | None = NOTE_OPTION,
) -> None:
    """Add a wallet to the local tracked-wallet registry."""
    try:
        result = WalletShadowService().add_wallet(address, label=label, tags=tag, note=note)
    except (WalletAlreadyTrackedError, WalletRegistryError, DataValidationError) as exc:
        _emit_wallet_error(ctx, exc=exc, address=address)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_mutation("Added", result),
    )


@app.command("list")
def list_wallets(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """List locally tracked wallets in registry order."""
    try:
        result = WalletShadowService().list_wallets()
    except WalletRegistryError as exc:
        _emit_wallet_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_list(result),
        local_json_output=json_output,
    )


@app.command("remove")
def remove_wallet(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
) -> None:
    """Remove a wallet from the local tracked-wallet registry."""
    try:
        result = WalletShadowService().remove_wallet(address)
    except (WalletNotTrackedError, WalletRegistryError, DataValidationError) as exc:
        _emit_wallet_error(ctx, exc=exc, address=address)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_mutation("Removed", result),
    )


@app.command("summary")
def wallet_summary(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    limit: int = SUMMARY_LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Build a tracked-wallet summary from public Data API reads."""
    try:
        result = WalletShadowService().get_summary(address, limit=limit)
    except (WalletNotTrackedError, WalletRegistryError, DataValidationError) as exc:
        _emit_wallet_error(ctx, exc=exc, address=address, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_summary(result),
        local_json_output=json_output,
    )


@app.command("trades")
def wallet_trades(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    limit: int = REPORT_LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch recent public trades for a tracked wallet."""
    try:
        result = WalletShadowService().get_trades(address, limit=limit)
    except (
        WalletNotTrackedError,
        WalletRegistryError,
        DataValidationError,
        DataNotFoundError,
        DataClientError,
    ) as exc:
        _emit_wallet_error(ctx, exc=exc, address=address, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_trades(result),
        local_json_output=json_output,
    )


@app.command("activity")
def wallet_activity(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    limit: int = REPORT_LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch recent public activity for a tracked wallet."""
    try:
        result = WalletShadowService().get_activity(address, limit=limit)
    except (
        WalletNotTrackedError,
        WalletRegistryError,
        DataValidationError,
        DataNotFoundError,
        DataClientError,
    ) as exc:
        _emit_wallet_error(ctx, exc=exc, address=address, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_activity(result),
        local_json_output=json_output,
    )


@app.command("positions")
def wallet_positions(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Fetch current public positions for a tracked wallet."""
    try:
        result = WalletShadowService().get_positions(address)
    except (
        WalletNotTrackedError,
        WalletRegistryError,
        DataValidationError,
        DataNotFoundError,
        DataClientError,
    ) as exc:
        _emit_wallet_error(ctx, exc=exc, address=address, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_positions(result),
        local_json_output=json_output,
    )


@app.command("snapshot")
def wallet_snapshot(
    ctx: typer.Context,
    limit: int = REPORT_LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Build a compact snapshot for tracked wallets in registry order."""
    try:
        result = WalletShadowService().get_snapshot(limit=limit)
    except WalletRegistryError as exc:
        _emit_wallet_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_snapshot(result),
        local_json_output=json_output,
    )


def _emit_wallet_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    address: str | None = None,
    json_output: bool = False,
) -> None:
    emit_command_error(
        ctx,
        code=_wallet_error_code(exc),
        message=str(exc),
        resource="wallet",
        identifier=address.strip().lower() if address is not None else None,
        local_json_output=json_output,
    )


def _wallet_error_code(exc: Exception) -> str:
    if isinstance(exc, WalletAlreadyTrackedError):
        return "already_tracked"
    if isinstance(exc, WalletNotTrackedError):
        return "not_tracked"
    if isinstance(exc, WalletRegistryError):
        return "registry_error"
    if isinstance(exc, DataValidationError):
        return "invalid_argument"
    if isinstance(exc, DataNotFoundError):
        return "not_found"
    return "request_failed"


def _format_wallet_mutation(action: str, response: WalletMutationResponse) -> str:
    return "\n".join([f"{action} tracked wallet.", _format_tracked_wallet(response.wallet)])


def _format_wallet_list(response: WalletListResponse) -> str:
    if not response.wallets:
        return "No tracked wallets."
    return "\n\n".join(_format_tracked_wallet(wallet) for wallet in response.wallets)


def _format_wallet_trades(response: WalletTradesResponse) -> str:
    return _format_wallet_items(
        wallet=response.wallet,
        heading=f"Recent trades: {response.total}",
        items=[_format_trade(item) for item in response.items],
    )


def _format_wallet_activity(response: WalletActivityResponse) -> str:
    return _format_wallet_items(
        wallet=response.wallet,
        heading=f"Recent activity rows: {response.total}",
        items=[_format_activity(item) for item in response.items],
    )


def _format_wallet_positions(response: WalletPositionsResponse) -> str:
    return _format_wallet_items(
        wallet=response.wallet,
        heading=f"Current positions: {response.total}",
        items=[_format_position(item) for item in response.items],
    )


def _format_wallet_items(*, wallet: TrackedWallet, heading: str, items: list[str]) -> str:
    lines = [_format_tracked_wallet(wallet), heading, "Items:"]
    lines.append("\n\n".join(items) if items else "-")
    return "\n".join(lines)


def _format_wallet_summary(response: WalletSummaryResponse) -> str:
    lines = [
        _format_tracked_wallet(response.wallet),
        "Metrics:",
        f"  Holdings value: {response.metrics.holdings_value or '-'}",
        _format_metric_line("  Traded count", response.metrics.traded_count),
        _format_metric_line(
            "  Current positions count",
            response.metrics.current_positions_count,
        ),
        _format_metric_line(
            "  Closed positions count",
            response.metrics.closed_positions_count,
        ),
        "Recent trades:",
        "\n\n".join(_format_trade(item) for item in response.recent_trades.items)
        if response.recent_trades.items
        else "-",
        "Recent activity:",
        "\n\n".join(_format_activity(item) for item in response.recent_activity.items)
        if response.recent_activity.items
        else "-",
    ]

    if response.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in response.errors)

    return "\n".join(lines)


def _format_wallet_snapshot(response: WalletSnapshotResponse) -> str:
    if not response.items:
        return "No tracked wallets."
    return "\n\n".join(_format_snapshot_item(item) for item in response.items)


def _format_snapshot_item(snapshot_item: WalletSnapshotItem) -> str:
    lines = [
        _format_tracked_wallet(snapshot_item.wallet),
        f"Holdings value: {snapshot_item.metrics.holdings_value or '-'}",
        _format_metric_line("Traded count", snapshot_item.metrics.traded_count),
        _format_metric_line(
            "Current positions count",
            snapshot_item.metrics.current_positions_count,
        ),
        _format_metric_line(
            "Closed positions count",
            snapshot_item.metrics.closed_positions_count,
        ),
    ]
    if snapshot_item.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in snapshot_item.errors)
    return "\n".join(lines)


def _format_section_error(error: WalletSectionError) -> str:
    return f"  {error.section}: {error.code} - {error.message}"


def _format_metric_line(label: str, value: int | None) -> str:
    return f"{label}: {value if value is not None else '-'}"


def _format_tracked_wallet(wallet: TrackedWallet) -> str:
    return "\n".join(
        [
            f"Address: {wallet.address}",
            f"Label: {wallet.label or '-'}",
            f"Tags: {', '.join(wallet.tags) if wallet.tags else '-'}",
            f"Note: {wallet.note or '-'}",
            f"Added at: {wallet.added_at}",
        ]
    )


def _format_trade(item: NormalizedTrade) -> str:
    return "\n".join(
        [
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id or '-'}",
            f"Token ID: {item.token_id or '-'}",
            f"Side: {item.side or '-'}",
            f"Outcome: {item.outcome or '-'}",
            f"Price: {item.price or '-'}",
            f"Size: {item.size or '-'}",
            f"Timestamp: {item.timestamp if item.timestamp is not None else '-'}",
            f"Transaction hash: {item.transaction_hash or '-'}",
        ]
    )


def _format_activity(item: NormalizedActivity) -> str:
    return "\n".join(
        [
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id or '-'}",
            f"Token ID: {item.token_id or '-'}",
            f"Activity type: {item.activity_type}",
            f"Side: {item.side or '-'}",
            f"Outcome: {item.outcome or '-'}",
            f"Price: {item.price or '-'}",
            f"Size: {item.size or '-'}",
            f"USDC size: {item.usdc_size or '-'}",
            f"Timestamp: {item.timestamp if item.timestamp is not None else '-'}",
            f"Transaction hash: {item.transaction_hash or '-'}",
        ]
    )


def _format_position(item: NormalizedCurrentPosition) -> str:
    return "\n".join(
        [
            f"Market slug: {item.market_slug or '-'}",
            f"Condition ID: {item.condition_id or '-'}",
            f"Token ID: {item.token_id or '-'}",
            f"Outcome: {item.outcome or '-'}",
            f"Size: {item.size or '-'}",
            f"Average price: {item.average_price or '-'}",
            f"Initial value: {item.initial_value or '-'}",
            f"Current value: {item.current_value or '-'}",
            f"Cash PnL: {item.cash_pnl or '-'}",
            f"Percent PnL: {item.percent_pnl or '-'}",
        ]
    )
