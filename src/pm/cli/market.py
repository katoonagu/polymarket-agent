"""Market-related CLI commands."""

from __future__ import annotations

import typer

from pm.cli.clob import _run_book, _run_price
from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.market import (
    GammaClient,
    GammaClientError,
    GammaNotFoundError,
    NormalizedEvent,
    NormalizedMarket,
)
from pm.market.models import (
    MarketSearchResponse,
    MarketSnapshotRecord,
    MarketSnapshotResponse,
    MarketSnapshotTokenSummary,
    MarketWatchListResponse,
    MarketWatchMutationResponse,
    MarketWatchRefreshResponse,
    RecurringMarketCandidate,
    RecurringMarketLatestResponse,
    RecurringMarketListResponse,
    WatchedMarket,
)
from pm.market.service import MarketIntelService, MarketValidationError
from pm.market.state import (
    MarketAlreadyWatchedError,
    MarketNotWatchedError,
    MarketStateError,
)

app = typer.Typer(
    add_completion=False,
    help="Gamma-backed read-only market discovery, watchlist, and recurring resolver commands.",
    no_args_is_help=True,
)
watch_app = typer.Typer(
    add_completion=False,
    help="Local gitignored market watchlist and snapshot commands.",
    no_args_is_help=True,
)
recurring_app = typer.Typer(
    add_completion=False,
    help="Deterministic recurring-market resolution using public Gamma discovery.",
    no_args_is_help=True,
)
app.add_typer(watch_app, name="watch")
app.add_typer(recurring_app, name="recurring")

QUERY_OPTION = typer.Option(
    ...,
    "--query",
    help="Free-text market query for the public Gamma adapter.",
)
LIMIT_OPTION = typer.Option(
    10,
    "--limit",
    min=1,
    help="Maximum number of normalized market rows to return.",
)
SLUG_OPTION = typer.Option(
    ...,
    "--slug",
    help="Market or event slug.",
)
TOKEN_ID_OPTION = typer.Option(
    ...,
    "--token-id",
    help="Polymarket token ID returned by market discovery commands.",
)
LABEL_OPTION = typer.Option(
    None,
    "--label",
    help="Optional local label for the watched market.",
)
TAG_OPTION = typer.Option(
    None,
    "--tag",
    help="Repeatable local tag for the watched market.",
)
INTERVAL_OPTION = typer.Option(
    ...,
    "--interval",
    help="Recurring interval. Supported values: 5m, 15m, 1h.",
)


@app.command("search")
def search_market(
    ctx: typer.Context,
    query: str = QUERY_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Search public Gamma markets by free-text query."""
    try:
        with GammaClient() as client:
            result = client.search_markets(query, limit=limit)
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="search",
            identifier=query.strip(),
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_search_output(result),
        local_json_output=json_output,
    )


@app.command("show")
def show_market(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Fetch a single public market by slug."""
    try:
        with GammaClient() as client:
            market = client.get_market_by_slug(slug)
    except GammaNotFoundError as exc:
        _handle_market_not_found(ctx, slug=slug, json_output=json_output, original_error=exc)
        raise typer.Exit(1) from exc
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="market",
            identifier=slug,
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        market.model_dump(mode="json"),
        text=_format_market_block(market),
        local_json_output=json_output,
    )


@app.command("event")
def show_event(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Fetch a single public event by slug."""
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError as exc:
        emit_command_error(
            ctx,
            code="not_found",
            message=str(exc),
            resource="event",
            identifier=slug,
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="event",
            identifier=slug,
            local_json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        event.model_dump(mode="json"),
        text=_format_event_block(event),
        local_json_output=json_output,
    )


@app.command("book")
def market_book_alias(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob book`."""
    _run_book(ctx, token_id=token_id, json_output=json_output)


@app.command("price")
def market_price_alias(
    ctx: typer.Context,
    token_id: str = TOKEN_ID_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Deprecated alias for `pm clob price`."""
    _run_price(ctx, token_id=token_id, json_output=json_output)


@watch_app.command("add")
def add_watch(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    label: str | None = LABEL_OPTION,
    tag: list[str] | None = TAG_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Add a market slug to the local watchlist."""
    try:
        result = MarketIntelService().add_watch(slug, label=label, tags=tag)
    except (MarketAlreadyWatchedError, MarketStateError, MarketValidationError) as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="watch",
            identifier=slug.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except (GammaNotFoundError, GammaClientError) as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="market",
            identifier=slug.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_watch_mutation("Added", result),
        local_json_output=json_output,
    )


@watch_app.command("remove")
def remove_watch(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Remove a market slug from the local watchlist."""
    try:
        result = MarketIntelService().remove_watch(slug)
    except (MarketNotWatchedError, MarketStateError) as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="watch",
            identifier=slug.strip().lower(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_watch_mutation("Removed", result),
        local_json_output=json_output,
    )


@watch_app.command("list")
def list_watch(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """List watched markets in registry order."""
    try:
        result = MarketIntelService().list_watchlist()
    except MarketStateError as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="watch",
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_watch_list(result),
        local_json_output=json_output,
    )


@watch_app.command("snapshot")
def snapshot_watch(
    ctx: typer.Context,
    slug: str = SLUG_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Snapshot a market by slug and persist the record locally."""
    try:
        result = MarketIntelService().snapshot_market(slug)
    except (MarketStateError, MarketValidationError) as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="snapshot",
            identifier=slug.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc
    except (GammaNotFoundError, GammaClientError) as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="market",
            identifier=slug.strip(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_snapshot_response(result),
        local_json_output=json_output,
    )


@watch_app.command("refresh")
def refresh_watch(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Refresh saved snapshots for every watched market."""
    try:
        result = MarketIntelService().refresh_watchlist()
    except MarketStateError as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="watch",
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_watch_refresh(result),
        local_json_output=json_output,
    )


@recurring_app.command("latest")
def recurring_latest(
    ctx: typer.Context,
    query: str = QUERY_OPTION,
    interval: str = INTERVAL_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Resolve the single best recurring-market candidate."""
    try:
        result = MarketIntelService().recurring_latest(query, interval=interval)
    except (MarketValidationError, GammaClientError, MarketStateError) as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="recurring",
            identifier=interval.strip().lower(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_recurring_latest(result),
        local_json_output=json_output,
    )


@recurring_app.command("list")
def recurring_list(
    ctx: typer.Context,
    query: str = QUERY_OPTION,
    interval: str = INTERVAL_OPTION,
    limit: int = LIMIT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """List ranked recurring-market candidates."""
    try:
        result = MarketIntelService().recurring_list(query, interval=interval, limit=limit)
    except (MarketValidationError, GammaClientError, MarketStateError) as exc:
        _emit_market_service_error(
            ctx,
            exc=exc,
            resource="recurring",
            identifier=interval.strip().lower(),
            json_output=json_output,
        )
        raise typer.Exit(1) from exc

    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_recurring_list(result),
        local_json_output=json_output,
    )


def _handle_market_not_found(
    ctx: typer.Context,
    *,
    slug: str,
    json_output: bool,
    original_error: GammaNotFoundError,
) -> None:
    try:
        with GammaClient() as client:
            event = client.get_event_by_slug(slug)
    except GammaNotFoundError:
        emit_command_error(
            ctx,
            code="not_found",
            message=str(original_error),
            resource="market",
            identifier=slug,
            local_json_output=json_output,
        )
        return
    except GammaClientError as exc:
        emit_command_error(
            ctx,
            code="request_failed",
            message=str(exc),
            resource="event",
            identifier=slug,
            local_json_output=json_output,
        )
        return

    market_slugs = [market.market_slug for market in event.markets]
    market_list = ", ".join(market_slugs) if market_slugs else "no market_slug values returned"
    message = (
        f"This looks like an event slug. Use `pm market event --slug {slug}` "
        f"or choose one of the returned market_slug values: {market_list}."
    )
    emit_command_error(
        ctx,
        code="event_slug_hint",
        message=message,
        resource="market",
        identifier=slug,
        local_json_output=json_output,
        hint={
            "event_slug": event.event_slug,
            "suggested_command": f"pm market event --slug {slug}",
            "market_slugs": market_slugs,
        },
    )


def _emit_market_service_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    resource: str,
    identifier: str | None = None,
    json_output: bool,
) -> None:
    emit_command_error(
        ctx,
        code=_market_error_code(exc),
        message=str(exc),
        resource=resource,
        identifier=identifier,
        local_json_output=json_output,
    )


def _market_error_code(exc: Exception) -> str:
    if isinstance(exc, MarketAlreadyWatchedError):
        return "already_watched"
    if isinstance(exc, MarketNotWatchedError):
        return "not_watched"
    if isinstance(exc, MarketValidationError):
        return "invalid_argument"
    if isinstance(exc, GammaNotFoundError):
        return "not_found"
    if isinstance(exc, MarketStateError):
        return "state_error"
    return "request_failed"


def _format_search_output(result: MarketSearchResponse) -> str:
    if not result.results:
        return f"No markets found for query '{result.query}'."
    return "\n\n".join(_format_market_block(market) for market in result.results)


def _format_market_block(market: NormalizedMarket) -> str:
    lines = [
        f"Market slug: {market.market_slug}",
        f"Event slug: {market.event_slug or '-'}",
        f"Question: {market.question}",
        f"Event title: {market.event_title or '-'}",
        f"Active: {market.active}",
        f"Closed: {market.closed}",
        f"Enable order book: {market.enable_order_book}",
        f"Condition ID: {market.condition_id or '-'}",
    ]

    if market.token_ids and market.outcomes and len(market.token_ids) == len(market.outcomes):
        lines.append("Token IDs:")
        lines.extend(
            f"  {outcome}: {token_id}"
            for outcome, token_id in zip(market.outcomes, market.token_ids, strict=True)
        )
    else:
        lines.append(f"Token IDs: {', '.join(market.token_ids) if market.token_ids else '-'}")

    lines.append(f"Outcomes: {', '.join(market.outcomes) if market.outcomes else '-'}")
    lines.append(f"Min tick: {market.min_tick if market.min_tick is not None else '-'}")
    lines.append(
        "Min order size: "
        f"{market.min_order_size if market.min_order_size is not None else '-'}"
    )
    if market.token_ids:
        lines.append("Next: pm clob book --token-id <id>")
    return "\n".join(lines)


def _format_event_block(event: NormalizedEvent) -> str:
    lines = [
        f"Event slug: {event.event_slug}",
        f"Title: {event.title}",
        f"Active: {event.active}",
        f"Closed: {event.closed}",
        f"Enable order book: {event.enable_order_book}",
        "Markets:",
    ]
    lines.append(
        "\n\n".join(_format_market_block(market) for market in event.markets)
        if event.markets
        else "-"
    )
    return "\n".join(lines)


def _format_watch_mutation(action: str, response: MarketWatchMutationResponse) -> str:
    return "\n".join([f"{action} watched market.", _format_watch_entry(response.market)])


def _format_watch_list(response: MarketWatchListResponse) -> str:
    if not response.items:
        return "No watched markets."
    return "\n\n".join(_format_watch_entry(item) for item in response.items)


def _format_watch_entry(item: WatchedMarket) -> str:
    return "\n".join(
        [
            f"Market slug: {item.market_slug}",
            f"Event slug: {item.event_slug or '-'}",
            f"Question: {item.question}",
            f"Label: {item.label or '-'}",
            f"Tags: {', '.join(item.tags) if item.tags else '-'}",
            f"Added at: {item.added_at}",
        ]
    )


def _format_snapshot_response(response: MarketSnapshotResponse) -> str:
    return _format_snapshot_record(response.snapshot)


def _format_watch_refresh(response: MarketWatchRefreshResponse) -> str:
    if not response.items:
        return "No watched markets."
    return "\n\n".join(_format_snapshot_record(item) for item in response.items)


def _format_snapshot_record(snapshot: MarketSnapshotRecord) -> str:
    lines = [
        f"Snapshot at: {snapshot.snapshot_at}",
        f"Market slug: {snapshot.market_slug}",
        f"Event slug: {snapshot.event_slug or '-'}",
        f"Question: {snapshot.question or '-'}",
        f"Event title: {snapshot.event_title or '-'}",
        f"Condition ID: {snapshot.condition_id or '-'}",
        f"Active: {snapshot.active if snapshot.active is not None else '-'}",
        f"Closed: {snapshot.closed if snapshot.closed is not None else '-'}",
        f"Open interest: {snapshot.open_interest or '-'}",
        f"Holders returned: {snapshot.holders_total_returned}",
    ]

    if snapshot.watch_metadata is not None:
        watch_tags = (
            ", ".join(snapshot.watch_metadata.tags)
            if snapshot.watch_metadata.tags
            else "-"
        )
        lines.extend(
            [
                f"Watch label: {snapshot.watch_metadata.label or '-'}",
                f"Watch tags: {watch_tags}",
            ]
        )

    lines.append("Tokens:")
    if snapshot.tokens:
        for token in snapshot.tokens:
            lines.extend(_format_snapshot_token(token))
    else:
        lines.append("  -")

    lines.append("Top holders:")
    if snapshot.top_holders:
        lines.extend(
            f"  {holder.rank if holder.rank is not None else '-'}: "
            f"{holder.holder_address} amount={holder.amount} token={holder.token_id}"
            for holder in snapshot.top_holders
        )
    else:
        lines.append("  -")

    if snapshot.errors:
        lines.append("Warnings:")
        lines.extend(
            f"  {error.section}: {error.code} - {error.message}" for error in snapshot.errors
        )

    return "\n".join(lines)


def _format_snapshot_token(token: MarketSnapshotTokenSummary) -> list[str]:
    return [
        f"  Token ID: {token.token_id}",
        f"    Outcome: {token.outcome or '-'}",
        f"    Midpoint: {token.midpoint or '-'}",
        f"    Spread: {token.spread or '-'}",
        f"    Best bid: {token.best_bid or '-'}",
        f"    Best ask: {token.best_ask or '-'}",
        f"    Bid levels: {token.bid_level_count}",
        f"    Ask levels: {token.ask_level_count}",
    ]


def _format_recurring_latest(response: RecurringMarketLatestResponse) -> str:
    if response.item is None:
        return (
            f"No recurring market candidates found for query '{response.query}' "
            f"and interval '{response.interval}'."
        )
    return _format_recurring_candidate(response.item)


def _format_recurring_list(response: RecurringMarketListResponse) -> str:
    if not response.items:
        return (
            f"No recurring market candidates found for query '{response.query}' "
            f"and interval '{response.interval}'."
        )
    return "\n\n".join(_format_recurring_candidate(item) for item in response.items)


def _format_recurring_candidate(item: RecurringMarketCandidate) -> str:
    lines = [
        f"Rank: {item.rank}",
        f"Match score: {item.match_score}",
        f"Matched interval: {item.matched_interval}",
        f"Recency source: {item.recency_source or '-'}",
        _format_market_block(
            NormalizedMarket(
                market_slug=item.market_slug,
                event_slug=item.event_slug,
                question=item.question,
                event_title=item.event_title,
                active=item.active,
                closed=item.closed,
                enable_order_book=item.enable_order_book,
                condition_id=item.condition_id,
                token_ids=item.token_ids,
                outcomes=item.outcomes,
                min_tick=item.min_tick,
                min_order_size=item.min_order_size,
            )
        ),
    ]
    return "\n".join(lines)
