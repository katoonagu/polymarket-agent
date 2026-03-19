"""Portfolio snapshot assembly, exposure/PnL views, and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from pm.auth import AuthClientError, AuthService, AuthValidationError
from pm.data import DataClient, DataClientError, DataNotFoundError, DataValidationError
from pm.data.client import validate_condition_id, validate_user_address
from pm.data.models import NormalizedClosedPosition, NormalizedCurrentPosition
from pm.execution import (
    ExecutionNotFoundError,
    ExecutionStateError,
    ExecutionStateService,
    ExecutionValidationError,
    ExecutionWatchService,
)
from pm.portfolio.models import (
    PortfolioAttribution,
    PortfolioClosedPositionItem,
    PortfolioClosedResponse,
    PortfolioCurrentPositionItem,
    PortfolioDiscrepancy,
    PortfolioExposureResponse,
    PortfolioMarketResponse,
    PortfolioMarketSummary,
    PortfolioPnlResponse,
    PortfolioPositionsResponse,
    PortfolioReconciliationRecord,
    PortfolioReconciliationResponse,
    PortfolioReconciliationSummary,
    PortfolioSectionError,
    PortfolioSnapshotRecord,
    PortfolioSnapshotSummary,
    PortfolioStrategySummary,
    PortfolioSummaryResponse,
)
from pm.portfolio.state import PortfolioStateService
from pm.strategy import StrategyStateService

DEFAULT_CLOSED_LIMIT = 20


class PortfolioError(RuntimeError):
    """Raised when a portfolio operation cannot complete."""


class PortfolioValidationError(PortfolioError):
    """Raised when portfolio arguments or context are invalid."""


class PortfolioNotFoundError(PortfolioError):
    """Raised when a requested portfolio scope is unavailable."""


@dataclass(slots=True)
class PostedStrategyLink:
    """Unique strategy linkage for one condition/token pair."""

    strategy_names: set[str] = field(default_factory=set)
    strategy_types: set[str] = field(default_factory=set)
    execution_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _MarketAccumulator:
    """Mutable market aggregation bucket."""

    condition_id: str
    market_slug: str | None = None
    gross_exposure: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    yes_exposure: Decimal = Decimal("0")
    no_exposure: Decimal = Decimal("0")
    other_exposure: Decimal = Decimal("0")
    current_positions_count: int = 0
    closed_positions_count: int = 0


@dataclass(slots=True)
class _StrategyAccumulator:
    """Mutable strategy aggregation bucket."""

    strategy_name: str
    strategy_type: str | None = None
    gross_exposure: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    yes_exposure: Decimal = Decimal("0")
    no_exposure: Decimal = Decimal("0")
    other_exposure: Decimal = Decimal("0")
    current_positions_count: int = 0
    closed_positions_count: int = 0
    execution_ids: set[str] = field(default_factory=set)


class PortfolioService:
    """Build deterministic account-level portfolio views from public and local state."""

    def __init__(
        self,
        *,
        auth_service: AuthService | None = None,
        data_client_cls: type[DataClient] = DataClient,
        strategy_state: StrategyStateService | None = None,
        execution_state: ExecutionStateService | None = None,
        portfolio_state: PortfolioStateService | None = None,
        watch_service: ExecutionWatchService | None = None,
    ) -> None:
        self._auth_service = auth_service or AuthService()
        self._data_client_cls = data_client_cls
        self._strategy_state = strategy_state or StrategyStateService()
        self._execution_state = execution_state or ExecutionStateService()
        self._portfolio_state = portfolio_state or PortfolioStateService()
        self._watch_service = watch_service or ExecutionWatchService(
            auth_service=self._auth_service,
            state_service=self._execution_state,
        )

    def summary(self) -> PortfolioSummaryResponse:
        """Return a compact portfolio summary for the operator account."""
        snapshot = self.build_snapshot()
        return PortfolioSummaryResponse(
            account_address=snapshot.account_address,
            snapshot_id=snapshot.snapshot_id,
            created_at=snapshot.created_at,
            summary=snapshot.summary,
            errors=snapshot.errors,
        )

    def positions(self) -> PortfolioPositionsResponse:
        """Return attributed current positions plus the snapshot summary."""
        snapshot = self.build_snapshot()
        return PortfolioPositionsResponse(
            account_address=snapshot.account_address,
            snapshot_id=snapshot.snapshot_id,
            created_at=snapshot.created_at,
            summary=snapshot.summary,
            items=snapshot.current_positions,
            total=len(snapshot.current_positions),
            errors=snapshot.errors,
        )

    def closed(self, *, limit: int = DEFAULT_CLOSED_LIMIT) -> PortfolioClosedResponse:
        """Return attributed closed positions newest-first."""
        if limit < 1:
            raise PortfolioValidationError("Limit must be greater than zero.")
        snapshot = self.build_snapshot()
        return PortfolioClosedResponse(
            account_address=snapshot.account_address,
            snapshot_id=snapshot.snapshot_id,
            created_at=snapshot.created_at,
            summary=snapshot.summary,
            items=snapshot.closed_positions[:limit],
            total=len(snapshot.closed_positions),
            limit=limit,
            errors=snapshot.errors,
        )

    def market(self, *, market: str) -> PortfolioMarketResponse:
        """Return a market-scoped portfolio view for one condition id."""
        try:
            condition_id = validate_condition_id(market)
        except DataValidationError as exc:
            raise PortfolioValidationError(str(exc)) from exc

        snapshot = self.build_snapshot()
        market_summary = next(
            (item for item in snapshot.per_market if item.condition_id == condition_id),
            None,
        )
        current_positions = [
            item
            for item in snapshot.current_positions
            if item.position.condition_id == condition_id
        ]
        closed_positions = [
            item
            for item in snapshot.closed_positions
            if item.position.condition_id == condition_id
        ]
        if market_summary is None and not current_positions and not closed_positions:
            raise PortfolioNotFoundError(
                f"Portfolio has no current or closed positions for market '{condition_id}'."
            )
        if market_summary is None:
            market_summary = PortfolioMarketSummary(
                condition_id=condition_id,
                market_slug=_first_market_slug(current_positions, closed_positions),
                gross_exposure="0",
                net_exposure="0",
                realized_pnl="0",
                unrealized_pnl="0",
                total_pnl="0",
                current_positions_count=len(current_positions),
                closed_positions_count=len(closed_positions),
            )
        return PortfolioMarketResponse(
            account_address=snapshot.account_address,
            snapshot_id=snapshot.snapshot_id,
            created_at=snapshot.created_at,
            market=market_summary,
            current_positions=current_positions,
            closed_positions=closed_positions,
            errors=snapshot.errors,
        )

    def exposure(self) -> PortfolioExposureResponse:
        """Return gross/net exposure plus per-market and per-strategy slices."""
        snapshot = self.build_snapshot()
        return PortfolioExposureResponse(
            account_address=snapshot.account_address,
            snapshot_id=snapshot.snapshot_id,
            created_at=snapshot.created_at,
            summary=snapshot.summary,
            per_market=snapshot.per_market,
            per_strategy=snapshot.per_strategy,
            errors=snapshot.errors,
        )

    def pnl(self) -> PortfolioPnlResponse:
        """Return realized/unrealized/total PnL plus linked slices."""
        snapshot = self.build_snapshot()
        return PortfolioPnlResponse(
            account_address=snapshot.account_address,
            snapshot_id=snapshot.snapshot_id,
            created_at=snapshot.created_at,
            summary=snapshot.summary,
            per_market=snapshot.per_market,
            per_strategy=snapshot.per_strategy,
            errors=snapshot.errors,
        )

    def build_snapshot(self, *, persist: bool = True) -> PortfolioSnapshotRecord:
        """Build one fresh local portfolio snapshot from Data API and local linkage state."""
        auth = self._auth_service.show().auth
        account_address = _resolve_account_address(auth)

        errors: list[PortfolioSectionError] = []
        current_positions: list[NormalizedCurrentPosition] = []
        closed_positions: list[NormalizedClosedPosition] = []
        holdings_value: str | None = None

        with self._data_client_cls() as client:
            try:
                current_positions = client.get_current_positions(account_address).items
            except (DataClientError, DataNotFoundError, DataValidationError) as exc:
                errors.append(
                    PortfolioSectionError(
                        section="current_positions",
                        code=_data_error_code(exc),
                        message=str(exc),
                    )
                )

            try:
                closed_positions = client.get_closed_positions(account_address).items
            except (DataClientError, DataNotFoundError, DataValidationError) as exc:
                errors.append(
                    PortfolioSectionError(
                        section="closed_positions",
                        code=_data_error_code(exc),
                        message=str(exc),
                    )
                )

            try:
                holdings_value = client.get_holdings_value(account_address).value
            except (DataClientError, DataNotFoundError, DataValidationError) as exc:
                errors.append(
                    PortfolioSectionError(
                        section="holdings_value",
                        code=_data_error_code(exc),
                        message=str(exc),
                    )
                )

        if not current_positions and not closed_positions and holdings_value is None and errors:
            raise PortfolioError(
                "Portfolio snapshot could not be built from public Data API account state."
            )

        pair_map = self._load_posted_strategy_pairs()
        current_items = [
            PortfolioCurrentPositionItem(
                position=position,
                attribution=_attribution_for_pair(
                    pair_map,
                    condition_id=position.condition_id,
                    token_id=position.token_id,
                ),
            )
            for position in sorted(
                current_positions,
                key=lambda item: (
                    item.market_slug or "",
                    item.condition_id or "",
                    item.outcome or "",
                    item.token_id or "",
                ),
            )
        ]
        closed_items = [
            PortfolioClosedPositionItem(
                position=position,
                attribution=_attribution_for_pair(
                    pair_map,
                    condition_id=position.condition_id,
                    token_id=position.token_id,
                ),
            )
            for position in sorted(
                closed_positions,
                key=lambda item: (
                    -(item.timestamp or 0),
                    item.market_slug or "",
                    item.token_id or "",
                ),
            )
        ]

        per_market = _build_market_summaries(current_items, closed_items)
        per_strategy = _build_strategy_summaries(current_items, closed_items, pair_map)
        summary = _build_snapshot_summary(
            current_items=current_items,
            closed_items=closed_items,
            per_market=per_market,
            holdings_value=holdings_value,
        )
        snapshot = PortfolioSnapshotRecord(
            snapshot_id=_make_id("portfolio_snapshot"),
            account_address=account_address,
            created_at=_utc_now(),
            summary=summary,
            current_positions=current_items,
            closed_positions=closed_items,
            per_market=per_market,
            per_strategy=per_strategy,
            errors=errors,
        )
        if persist:
            self._portfolio_state.append_snapshot(snapshot)
        return snapshot

    def reconcile(self) -> PortfolioReconciliationResponse:
        """Compare fresh portfolio state against fresh execution reconciliation state."""
        snapshot = self.build_snapshot()
        try:
            execution_reconcile = self._watch_service.reconcile()
        except (
            AuthClientError,
            AuthValidationError,
            ExecutionNotFoundError,
            ExecutionStateError,
            ExecutionValidationError,
        ) as exc:
            raise PortfolioError(
                f"Portfolio reconciliation requires authenticated execution access: {exc}"
            ) from exc

        discrepancies: list[PortfolioDiscrepancy] = []
        errors = list(snapshot.errors)
        errors.extend(
            PortfolioSectionError(
                section=f"execution_reconcile.{item.section}",
                code=item.code,
                message=item.message,
            )
            for item in execution_reconcile.errors
        )

        for execution_item in execution_reconcile.items:
            if execution_item.classification != "mismatch":
                continue
            discrepancies.append(
                PortfolioDiscrepancy(
                    kind="execution_state_mismatch",
                    severity="high",
                    condition_id=execution_item.condition_id,
                    order_id=execution_item.order_id,
                    message=execution_item.message,
                )
            )

        for current_item in snapshot.current_positions:
            if current_item.attribution.status == "unlinked":
                discrepancies.append(
                    PortfolioDiscrepancy(
                        kind="unlinked_current_position",
                        severity="medium",
                        condition_id=current_item.position.condition_id,
                        token_id=current_item.position.token_id,
                        message=(
                            "Current position has no explicit local strategy-execution linkage."
                        ),
                    )
                )
            elif current_item.attribution.status == "ambiguous":
                discrepancies.append(
                    PortfolioDiscrepancy(
                        kind="ambiguous_strategy_link",
                        severity="medium",
                        condition_id=current_item.position.condition_id,
                        token_id=current_item.position.token_id,
                        message=(
                            "Current position matches more than one linked strategy name."
                        ),
                    )
                )

        snapshot_pairs = _snapshot_pairs(snapshot)
        for (condition_id, token_id), link in self._load_posted_strategy_pairs().items():
            if (condition_id, token_id) in snapshot_pairs:
                continue
            discrepancies.append(
                PortfolioDiscrepancy(
                    kind="linked_execution_missing_from_positions",
                    severity="high",
                    condition_id=condition_id,
                    token_id=token_id,
                    execution_id=_single_or_none(link.execution_ids),
                    strategy_name=_single_or_none(link.strategy_names),
                    message=(
                        "Live posted strategy execution linkage is missing from current and "
                        "closed portfolio positions."
                    ),
                )
            )

        summary = PortfolioReconciliationSummary(
            health=_portfolio_health(discrepancies),
            discrepancy_count=len(discrepancies),
            execution_state_mismatch_count=sum(
                1 for item in discrepancies if item.kind == "execution_state_mismatch"
            ),
            unlinked_current_position_count=sum(
                1 for item in discrepancies if item.kind == "unlinked_current_position"
            ),
            linked_execution_missing_from_positions_count=sum(
                1
                for item in discrepancies
                if item.kind == "linked_execution_missing_from_positions"
            ),
            ambiguous_strategy_link_count=sum(
                1 for item in discrepancies if item.kind == "ambiguous_strategy_link"
            ),
        )
        record = PortfolioReconciliationRecord(
            reconciliation_id=_make_id("portfolio_reconciliation"),
            snapshot_id=snapshot.snapshot_id,
            execution_reconciliation_id=execution_reconcile.reconciliation_id,
            account_address=snapshot.account_address,
            created_at=_utc_now(),
            summary=summary,
            discrepancies=discrepancies,
            errors=errors,
        )
        self._portfolio_state.append_reconciliation(record)
        return PortfolioReconciliationResponse(
            reconciliation_id=record.reconciliation_id,
            snapshot_id=record.snapshot_id,
            execution_reconciliation_id=record.execution_reconciliation_id,
            account_address=record.account_address,
            created_at=record.created_at,
            summary=record.summary,
            discrepancies=record.discrepancies,
            errors=record.errors,
        )

    def _load_posted_strategy_pairs(self) -> dict[tuple[str, str], PostedStrategyLink]:
        links_by_execution_id = {
            link.execution_id: link for link in self._strategy_state.list_execution_links()
        }
        order_results_by_id = {
            result.result_id: result
            for result in self._execution_state.list_order_results()
            if result.result_id is not None
        }
        pair_map: dict[tuple[str, str], PostedStrategyLink] = {}

        for result in self._strategy_state.list_dispatch_results():
            if result.decision != "POSTED" or result.mode != "live":
                continue
            pair = _pair_or_none(result.condition_id, result.token_id)
            if pair is None:
                continue
            link = links_by_execution_id.get(result.execution_id)
            if link is None:
                continue
            if link.execution_result_id is not None:
                order_result = order_results_by_id.get(link.execution_result_id)
                if order_result is None:
                    continue
                if (
                    order_result.action != "post"
                    or order_result.mode != "live"
                    or order_result.decision != "POSTED"
                ):
                    continue

            bucket = pair_map.setdefault(pair, PostedStrategyLink())
            bucket.strategy_names.add(result.strategy_name)
            bucket.strategy_types.add(result.strategy_type)
            bucket.execution_ids.add(result.execution_id)

        return pair_map


def _resolve_account_address(auth: Any) -> str:
    funder_address = _validated_address(getattr(auth, "funder_address", None))
    if funder_address is not None:
        return funder_address

    signer_address = _validated_address(getattr(auth, "signer_address", None))
    if signer_address is not None:
        return signer_address

    raise PortfolioValidationError(
        "No operator account address could be resolved. Run `pm auth show --json` or "
        "`pm setup guide --json` to inspect authenticated context."
    )


def _validated_address(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return validate_user_address(value)
    except DataValidationError as exc:
        raise PortfolioValidationError(str(exc)) from exc


def _attribution_for_pair(
    pair_map: dict[tuple[str, str], PostedStrategyLink],
    *,
    condition_id: str | None,
    token_id: str | None,
) -> PortfolioAttribution:
    pair = _pair_or_none(condition_id, token_id)
    if pair is None:
        return PortfolioAttribution(status="unlinked")
    link = pair_map.get(pair)
    if link is None:
        return PortfolioAttribution(status="unlinked")

    strategy_names = sorted(link.strategy_names)
    execution_ids = sorted(link.execution_ids)
    if len(strategy_names) == 1:
        return PortfolioAttribution(
            status="linked",
            strategy_name=strategy_names[0],
            strategy_names=strategy_names,
            execution_ids=execution_ids,
        )
    return PortfolioAttribution(
        status="ambiguous",
        strategy_names=strategy_names,
        execution_ids=execution_ids,
    )


def _build_market_summaries(
    current_items: list[PortfolioCurrentPositionItem],
    closed_items: list[PortfolioClosedPositionItem],
) -> list[PortfolioMarketSummary]:
    buckets: dict[str, _MarketAccumulator] = {}

    for current_item in current_items:
        condition_id = current_item.position.condition_id
        if not condition_id:
            continue
        bucket = buckets.setdefault(condition_id, _MarketAccumulator(condition_id=condition_id))
        bucket.market_slug = bucket.market_slug or current_item.position.market_slug
        bucket.current_positions_count += 1
        bucket.gross_exposure += _decimal_or_zero(current_item.position.current_value)
        bucket.unrealized_pnl += _decimal_or_zero(current_item.position.cash_pnl)
        _apply_outcome_exposure(
            current_item.position.outcome,
            _decimal_or_zero(current_item.position.current_value),
            bucket,
        )

    for closed_item in closed_items:
        condition_id = closed_item.position.condition_id
        if not condition_id:
            continue
        bucket = buckets.setdefault(condition_id, _MarketAccumulator(condition_id=condition_id))
        bucket.market_slug = bucket.market_slug or closed_item.position.market_slug
        bucket.closed_positions_count += 1
        bucket.realized_pnl += _decimal_or_zero(closed_item.position.realized_pnl)

    summaries = [
        PortfolioMarketSummary(
            condition_id=bucket.condition_id,
            market_slug=bucket.market_slug,
            gross_exposure=_decimal_to_string(bucket.gross_exposure),
            net_exposure=_net_exposure_string(bucket),
            realized_pnl=_decimal_to_string(bucket.realized_pnl),
            unrealized_pnl=_decimal_to_string(bucket.unrealized_pnl),
            total_pnl=_decimal_to_string(bucket.realized_pnl + bucket.unrealized_pnl),
            current_positions_count=bucket.current_positions_count,
            closed_positions_count=bucket.closed_positions_count,
        )
        for bucket in buckets.values()
    ]
    return sorted(
        summaries,
        key=lambda item: (
            -_decimal_or_zero(item.gross_exposure),
            item.condition_id,
        ),
    )


def _build_strategy_summaries(
    current_items: list[PortfolioCurrentPositionItem],
    closed_items: list[PortfolioClosedPositionItem],
    pair_map: dict[tuple[str, str], PostedStrategyLink],
) -> list[PortfolioStrategySummary]:
    buckets: dict[str, _StrategyAccumulator] = {}

    for current_item in current_items:
        if (
            current_item.attribution.status != "linked"
            or current_item.attribution.strategy_name is None
        ):
            continue
        pair = _pair_or_none(current_item.position.condition_id, current_item.position.token_id)
        if pair is None:
            continue
        posted_link = pair_map.get(pair)
        bucket = buckets.setdefault(
            current_item.attribution.strategy_name,
            _StrategyAccumulator(strategy_name=current_item.attribution.strategy_name),
        )
        if posted_link is not None and len(posted_link.strategy_types) == 1:
            bucket.strategy_type = _single_or_none(posted_link.strategy_types)
        bucket.current_positions_count += 1
        bucket.gross_exposure += _decimal_or_zero(current_item.position.current_value)
        bucket.unrealized_pnl += _decimal_or_zero(current_item.position.cash_pnl)
        bucket.execution_ids.update(current_item.attribution.execution_ids)
        _apply_outcome_exposure(
            current_item.position.outcome,
            _decimal_or_zero(current_item.position.current_value),
            bucket,
        )

    for closed_item in closed_items:
        if (
            closed_item.attribution.status != "linked"
            or closed_item.attribution.strategy_name is None
        ):
            continue
        pair = _pair_or_none(closed_item.position.condition_id, closed_item.position.token_id)
        if pair is None:
            continue
        posted_link = pair_map.get(pair)
        bucket = buckets.setdefault(
            closed_item.attribution.strategy_name,
            _StrategyAccumulator(strategy_name=closed_item.attribution.strategy_name),
        )
        if posted_link is not None and len(posted_link.strategy_types) == 1:
            bucket.strategy_type = _single_or_none(posted_link.strategy_types)
        bucket.closed_positions_count += 1
        bucket.realized_pnl += _decimal_or_zero(closed_item.position.realized_pnl)
        bucket.execution_ids.update(closed_item.attribution.execution_ids)

    summaries = [
        PortfolioStrategySummary(
            strategy_name=bucket.strategy_name,
            strategy_type=bucket.strategy_type,
            gross_exposure=_decimal_to_string(bucket.gross_exposure),
            net_exposure=_net_exposure_string(bucket),
            realized_pnl=_decimal_to_string(bucket.realized_pnl),
            unrealized_pnl=_decimal_to_string(bucket.unrealized_pnl),
            total_pnl=_decimal_to_string(bucket.realized_pnl + bucket.unrealized_pnl),
            current_positions_count=bucket.current_positions_count,
            closed_positions_count=bucket.closed_positions_count,
            execution_ids=sorted(bucket.execution_ids),
        )
        for bucket in buckets.values()
    ]
    return sorted(
        summaries,
        key=lambda item: (-_decimal_or_zero(item.gross_exposure), item.strategy_name),
    )


def _build_snapshot_summary(
    *,
    current_items: list[PortfolioCurrentPositionItem],
    closed_items: list[PortfolioClosedPositionItem],
    per_market: list[PortfolioMarketSummary],
    holdings_value: str | None,
) -> PortfolioSnapshotSummary:
    realized_total = sum(
        (_decimal_or_zero(item.position.realized_pnl) for item in closed_items),
        start=Decimal("0"),
    )
    unrealized_total = sum(
        (_decimal_or_zero(item.position.cash_pnl) for item in current_items),
        start=Decimal("0"),
    )
    gross_exposure = sum(
        (_decimal_or_zero(item.position.current_value) for item in current_items),
        start=Decimal("0"),
    )
    net_exposure = sum(
        (_decimal_or_zero(item.net_exposure) for item in per_market),
        start=Decimal("0"),
    )
    return PortfolioSnapshotSummary(
        holdings_value=holdings_value,
        realized_pnl_total=_decimal_to_string(realized_total),
        unrealized_pnl_total=_decimal_to_string(unrealized_total),
        total_pnl=_decimal_to_string(realized_total + unrealized_total),
        gross_exposure=_decimal_to_string(gross_exposure),
        net_exposure=_decimal_to_string(net_exposure),
        current_positions_count=len(current_items),
        closed_positions_count=len(closed_items),
        linked_current_positions_count=sum(
            1 for item in current_items if item.attribution.status == "linked"
        ),
        unlinked_current_positions_count=sum(
            1 for item in current_items if item.attribution.status == "unlinked"
        ),
        ambiguous_current_positions_count=sum(
            1 for item in current_items if item.attribution.status == "ambiguous"
        ),
        linked_closed_positions_count=sum(
            1 for item in closed_items if item.attribution.status == "linked"
        ),
        unlinked_closed_positions_count=sum(
            1 for item in closed_items if item.attribution.status == "unlinked"
        ),
        ambiguous_closed_positions_count=sum(
            1 for item in closed_items if item.attribution.status == "ambiguous"
        ),
    )


def _snapshot_pairs(snapshot: PortfolioSnapshotRecord) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for current_item in snapshot.current_positions:
        pair = _pair_or_none(current_item.position.condition_id, current_item.position.token_id)
        if pair is not None:
            pairs.add(pair)
    for closed_item in snapshot.closed_positions:
        pair = _pair_or_none(closed_item.position.condition_id, closed_item.position.token_id)
        if pair is not None:
            pairs.add(pair)
    return pairs


def _pair_or_none(
    condition_id: str | None,
    token_id: str | None,
) -> tuple[str, str] | None:
    if not condition_id or not token_id:
        return None
    return (_pair_key(condition_id), _pair_key(token_id))


def _pair_key(value: str) -> str:
    return value.strip().lower()


def _first_market_slug(
    current_items: list[PortfolioCurrentPositionItem],
    closed_items: list[PortfolioClosedPositionItem],
) -> str | None:
    for current_item in current_items:
        if current_item.position.market_slug:
            return current_item.position.market_slug
    for closed_item in closed_items:
        if closed_item.position.market_slug:
            return closed_item.position.market_slug
    return None


def _single_or_none(values: set[str]) -> str | None:
    if len(values) != 1:
        return None
    return next(iter(values))


def _apply_outcome_exposure(
    outcome: str | None,
    value: Decimal,
    accumulator: _MarketAccumulator | _StrategyAccumulator,
) -> None:
    normalized = (outcome or "").strip().upper()
    if normalized == "YES":
        accumulator.yes_exposure += value
    elif normalized == "NO":
        accumulator.no_exposure += value
    else:
        accumulator.other_exposure += value


def _net_exposure_string(accumulator: _MarketAccumulator | _StrategyAccumulator) -> str:
    net_value = abs(accumulator.yes_exposure - accumulator.no_exposure)
    net_value += accumulator.other_exposure
    return _decimal_to_string(net_value)


def _decimal_or_zero(value: str | Decimal | None) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_to_string(value: Decimal) -> str:
    normalized = value.normalize()
    rendered = format(normalized, "f")
    if "." not in rendered:
        return rendered
    trimmed = rendered.rstrip("0").rstrip(".")
    return trimmed or "0"


def _data_error_code(exc: Exception) -> str:
    if isinstance(exc, DataValidationError):
        return "invalid_argument"
    if isinstance(exc, DataNotFoundError):
        return "not_found"
    return "request_failed"


def _portfolio_health(discrepancies: list[PortfolioDiscrepancy]) -> str:
    if not discrepancies:
        return "healthy"
    high_priority = {
        "execution_state_mismatch",
        "linked_execution_missing_from_positions",
    }
    if any(item.kind in high_priority for item in discrepancies):
        return "mismatch"
    return "warning"


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
