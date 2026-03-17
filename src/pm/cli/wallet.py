"""Tracked-wallet registry, discovery, and wallet-intelligence CLI commands."""

from __future__ import annotations

import typer

from pm.cli.support import emit_command_error, emit_command_output
from pm.data import DataClientError, DataNotFoundError, DataValidationError
from pm.data.models import NormalizedActivity, NormalizedCurrentPosition, NormalizedTrade
from pm.wallet import (
    TrackedWallet,
    WalletActivityResponse,
    WalletAlreadyTrackedError,
    WalletCompareResponse,
    WalletDiscoveryItem,
    WalletHoldersDiscoveryResponse,
    WalletLeaderboardDiscoveryResponse,
    WalletListResponse,
    WalletMutationResponse,
    WalletNotTrackedError,
    WalletPositionsResponse,
    WalletRankTrackedResponse,
    WalletRegistryError,
    WalletScoreComponent,
    WalletScoreResponse,
    WalletSectionError,
    WalletShadowService,
    WalletSnapshotItem,
    WalletSnapshotResponse,
    WalletSummaryResponse,
    WalletTradesResponse,
)

app = typer.Typer(
    add_completion=False,
    help="Local tracked-wallet registry plus read-only discovery and wallet intelligence.",
    no_args_is_help=True,
)
discover_app = typer.Typer(
    add_completion=False,
    help="Non-mutating wallet discovery from public holder and leaderboard data.",
    no_args_is_help=True,
)
rank_app = typer.Typer(
    add_completion=False,
    help="Deterministic tracked-wallet ranking commands.",
    no_args_is_help=True,
)
app.add_typer(discover_app, name="discover")
app.add_typer(rank_app, name="rank")

ADDRESS_OPTION = typer.Option(
    ...,
    "--address",
    help="Tracked 0x-prefixed EVM wallet address.",
)
COMPARE_ADDRESS_OPTION = typer.Option(
    ...,
    "--address",
    help="Provide exactly two public 0x-prefixed EVM wallet addresses.",
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
MARKET_OPTION = typer.Option(
    ...,
    "--market",
    help="Market slug or 0x-prefixed condition ID.",
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


@discover_app.command("leaderboard")
def discover_leaderboard(
    ctx: typer.Context,
    limit: int = REPORT_LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Discover wallet candidates from the public trader leaderboard."""
    try:
        result = WalletShadowService().discover_leaderboard(limit=limit)
    except WalletRegistryError as exc:
        _emit_wallet_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_leaderboard_discovery(result),
        local_json_output=json_output,
    )


@discover_app.command("holders")
def discover_holders(
    ctx: typer.Context,
    market: str = MARKET_OPTION,
    limit: int = REPORT_LIMIT_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Discover unique wallet candidates from a market's public holder rows."""
    try:
        result = WalletShadowService().discover_holders(market, limit=limit)
    except WalletRegistryError as exc:
        _emit_wallet_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    except DataValidationError as exc:
        _emit_market_error(ctx, exc=exc, market=market, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_holders_discovery(result),
        local_json_output=json_output,
    )


@app.command("score")
def score_wallet(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Calculate a deterministic public wallet score."""
    try:
        result = WalletShadowService().score_wallet(address)
    except (WalletRegistryError, DataValidationError) as exc:
        _emit_wallet_error(ctx, exc=exc, address=address, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_score(result),
        local_json_output=json_output,
    )


@rank_app.command("tracked")
def rank_tracked(
    ctx: typer.Context,
    json_output: bool = JSON_OPTION,
) -> None:
    """Rank all tracked wallets by deterministic public score."""
    try:
        result = WalletShadowService().rank_tracked_wallets()
    except WalletRegistryError as exc:
        _emit_wallet_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_rank(result),
        local_json_output=json_output,
    )


@app.command("compare")
def compare_wallets(
    ctx: typer.Context,
    address: list[str] = COMPARE_ADDRESS_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Compare exactly two public wallet scores."""
    if len(address) != 2:
        emit_command_error(
            ctx,
            code="invalid_argument",
            message="Provide exactly two --address values.",
            resource="wallet",
            local_json_output=json_output,
        )
        raise typer.Exit(1)

    try:
        result = WalletShadowService().compare_wallets(address[0], address[1])
    except (WalletRegistryError, DataValidationError) as exc:
        identifier = address[0] if len(address) == 1 else None
        _emit_wallet_error(ctx, exc=exc, address=identifier, json_output=json_output)
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_wallet_compare(result),
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


def _emit_market_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    market: str,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code="invalid_argument",
        message=str(exc),
        resource="market",
        identifier=market.strip(),
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


def _format_leaderboard_discovery(response: WalletLeaderboardDiscoveryResponse) -> str:
    lines = [f"Leaderboard candidates: {response.total}", "Items:"]
    lines.append(
        "\n\n".join(_format_discovery_item(item) for item in response.items)
        if response.items
        else "-"
    )
    if response.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in response.errors)
    return "\n".join(lines)


def _format_holders_discovery(response: WalletHoldersDiscoveryResponse) -> str:
    lines = [
        f"Market slug: {response.market_slug or '-'}",
        f"Condition ID: {response.condition_id or '-'}",
        f"Holder candidates: {response.total}",
        "Items:",
    ]
    lines.append(
        "\n\n".join(_format_discovery_item(item) for item in response.items)
        if response.items
        else "-"
    )
    if response.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in response.errors)
    return "\n".join(lines)


def _format_wallet_score(response: WalletScoreResponse) -> str:
    lines = [
        *_format_wallet_identity(response.address, response.tracked_wallet),
        f"Total score: {_format_float(response.total_score)}",
        f"Available weight: {_format_float(response.available_weight)}",
        "Components:",
    ]
    for component_name, component in response.components.items():
        lines.extend(_format_score_component(component_name, component))
    if response.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in response.errors)
    return "\n".join(lines)


def _format_wallet_rank(response: WalletRankTrackedResponse) -> str:
    if not response.items:
        return "No tracked wallets."
    return "\n\n".join(_format_rank_item(item.rank, item.score) for item in response.items)


def _format_wallet_compare(response: WalletCompareResponse) -> str:
    lines = [
        "Left:",
        _indent(_format_wallet_score(response.left)),
        "Right:",
        _indent(_format_wallet_score(response.right)),
        f"Winner: {response.winner_address or 'tie'}",
        f"Score delta: {_format_float(response.score_delta)}",
        "Component deltas:",
    ]
    for component_name, delta in response.component_deltas.items():
        lines.append(f"  {_component_label(component_name)}: {_format_float(delta)}")
    return "\n".join(lines)


def _format_rank_item(rank: int, score: WalletScoreResponse) -> str:
    lines = [f"Rank: {rank}", *_format_wallet_identity(score.address, score.tracked_wallet)]
    lines.append(f"Total score: {_format_float(score.total_score)}")
    lines.append(
        f"Leaderboard component: {_format_float(score.components['leaderboard_component'].score)}"
    )
    lines.append(
        "Realized performance component: "
        f"{_format_float(score.components['realized_performance_component'].score)}"
    )
    if score.errors:
        lines.append("Warnings:")
        lines.extend(_format_section_error(error) for error in score.errors)
    return "\n".join(lines)


def _format_discovery_item(item: WalletDiscoveryItem) -> str:
    lines = [
        *_format_wallet_identity(item.address, item.tracked_wallet),
        f"Source: {item.source}",
        f"Display name: {item.display_name or '-'}",
        f"User name: {item.user_name or '-'}",
        f"Rank: {item.rank if item.rank is not None else '-'}",
        f"PnL: {item.pnl or '-'}",
        f"Volume: {item.volume or '-'}",
        f"Market slug: {item.market_slug or '-'}",
        f"Condition ID: {item.condition_id or '-'}",
        "Token exposures:",
    ]
    if item.token_exposures:
        lines.extend(
            f"  Token ID: {exposure.token_id}, Amount: {exposure.amount}, "
            "Outcome index: "
            f"{exposure.outcome_index if exposure.outcome_index is not None else '-'}"
            for exposure in item.token_exposures
        )
    else:
        lines.append("  -")
    return "\n".join(lines)


def _format_score_component(name: str, component: WalletScoreComponent) -> list[str]:
    lines = [
        f"  {_component_label(name)}:",
        f"    Weight: {_format_float(component.weight)}",
        f"    Available: {'yes' if component.available else 'no'}",
        f"    Score: {_format_float(component.score)}",
        "    Inputs:",
    ]
    if component.inputs:
        lines.extend(f"      {key}: {value}" for key, value in component.inputs.items())
    else:
        lines.append("      -")
    return lines


def _component_label(name: str) -> str:
    return name.replace("_", " ").replace(" component", "").title()


def _format_section_error(error: WalletSectionError) -> str:
    return f"  {error.section}: {error.code} - {error.message}"


def _format_metric_line(label: str, value: int | None) -> str:
    return f"{label}: {value if value is not None else '-'}"


def _format_wallet_identity(address: str, tracked_wallet: TrackedWallet | None) -> list[str]:
    lines = [f"Address: {address}", f"Tracked: {'yes' if tracked_wallet is not None else 'no'}"]
    if tracked_wallet is not None:
        lines.extend(
            [
                f"Label: {tracked_wallet.label or '-'}",
                f"Tags: {', '.join(tracked_wallet.tags) if tracked_wallet.tags else '-'}",
                f"Note: {tracked_wallet.note or '-'}",
                f"Added at: {tracked_wallet.added_at}",
            ]
        )
    return lines


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


def _format_float(value: float | None) -> str:
    if value is None:
        return "-"
    text = f"{value:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())
