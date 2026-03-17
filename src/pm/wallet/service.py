"""Tracked-wallet reads, discovery, and deterministic wallet scoring."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import TypeVar

from pm.data import DataClient, DataClientError, DataNotFoundError, DataValidationError
from pm.data.models import (
    HoldersResponse,
    NormalizedClosedPosition,
    NormalizedLeaderboardEntry,
)
from pm.wallet.models import (
    TrackedWallet,
    WalletActivityResponse,
    WalletCompareResponse,
    WalletDiscoveryItem,
    WalletDiscoveryTokenExposure,
    WalletHoldersDiscoveryResponse,
    WalletLeaderboardDiscoveryResponse,
    WalletListResponse,
    WalletMutationResponse,
    WalletPositionsResponse,
    WalletRankItem,
    WalletRankTrackedResponse,
    WalletRecentActivity,
    WalletRecentTrades,
    WalletScoreComponent,
    WalletScoreResponse,
    WalletSectionError,
    WalletSnapshotItem,
    WalletSnapshotResponse,
    WalletSummaryMetrics,
    WalletSummaryResponse,
    WalletTradesResponse,
)
from pm.wallet.registry import WalletRegistryService, normalize_wallet_address

T = TypeVar("T")

LEADERBOARD_COMPONENT = "leaderboard_component"
REALIZED_PERFORMANCE_COMPONENT = "realized_performance_component"
ACTIVITY_COMPONENT = "activity_component"
FOOTPRINT_COMPONENT = "footprint_component"
COMPONENT_WEIGHTS = {
    LEADERBOARD_COMPONENT: 0.25,
    REALIZED_PERFORMANCE_COMPONENT: 0.35,
    ACTIVITY_COMPONENT: 0.20,
    FOOTPRINT_COMPONENT: 0.20,
}
COMPONENT_ORDER = (
    LEADERBOARD_COMPONENT,
    REALIZED_PERFORMANCE_COMPONENT,
    ACTIVITY_COMPONENT,
    FOOTPRINT_COMPONENT,
)


class WalletShadowService:
    """High-level tracked-wallet reads, discovery, and scoring."""

    def __init__(self, registry: WalletRegistryService | None = None) -> None:
        self._registry = registry or WalletRegistryService()

    def add_wallet(
        self,
        address: str,
        *,
        label: str | None = None,
        tags: list[str] | None = None,
        note: str | None = None,
    ) -> WalletMutationResponse:
        """Add a wallet to the local tracked-wallet registry."""
        wallet = self._registry.add_wallet(address, label=label, tags=tags, note=note)
        return WalletMutationResponse(wallet=wallet)

    def list_wallets(self) -> WalletListResponse:
        """Return all locally tracked wallets."""
        wallets = self._registry.list_wallets()
        return WalletListResponse(wallets=wallets, total=len(wallets))

    def remove_wallet(self, address: str) -> WalletMutationResponse:
        """Remove a wallet from the local tracked-wallet registry."""
        wallet = self._registry.remove_wallet(address)
        return WalletMutationResponse(wallet=wallet)

    def get_trades(self, address: str, limit: int) -> WalletTradesResponse:
        """Return recent public trades for a tracked wallet."""
        wallet = self._registry.get_wallet(address)
        with DataClient() as client:
            result = client.get_user_trades(wallet.address, limit=limit)
        return WalletTradesResponse(wallet=wallet, items=result.items, total=result.total)

    def get_activity(self, address: str, limit: int) -> WalletActivityResponse:
        """Return recent public activity for a tracked wallet."""
        wallet = self._registry.get_wallet(address)
        with DataClient() as client:
            result = client.get_user_activity(wallet.address, limit=limit)
        return WalletActivityResponse(wallet=wallet, items=result.items, total=result.total)

    def get_positions(self, address: str) -> WalletPositionsResponse:
        """Return current public positions for a tracked wallet."""
        wallet = self._registry.get_wallet(address)
        with DataClient() as client:
            result = client.get_current_positions(wallet.address)
        return WalletPositionsResponse(wallet=wallet, items=result.items, total=result.total)

    def get_summary(self, address: str, *, limit: int) -> WalletSummaryResponse:
        """Build a partial-failure wallet summary from the public Data API."""
        wallet = self._registry.get_wallet(address)
        metrics = WalletSummaryMetrics()
        recent_trades = WalletRecentTrades()
        recent_activity = WalletRecentActivity()
        errors: list[WalletSectionError] = []

        with DataClient() as client:
            holdings_value = self._capture_data_error(
                section="holdings_value",
                errors=errors,
                operation=lambda: client.get_holdings_value(wallet.address),
            )
            if holdings_value is not None:
                metrics.holdings_value = holdings_value.value

            traded_count = self._capture_data_error(
                section="traded_count",
                errors=errors,
                operation=lambda: client.get_traded_count(wallet.address),
            )
            if traded_count is not None:
                metrics.traded_count = traded_count.traded

            positions = self._capture_data_error(
                section="current_positions",
                errors=errors,
                operation=lambda: client.get_current_positions(wallet.address),
            )
            if positions is not None:
                metrics.current_positions_count = positions.total

            closed_positions = self._capture_data_error(
                section="closed_positions",
                errors=errors,
                operation=lambda: client.get_closed_positions(wallet.address),
            )
            if closed_positions is not None:
                metrics.closed_positions_count = closed_positions.total

            trades = self._capture_data_error(
                section="recent_trades",
                errors=errors,
                operation=lambda: client.get_user_trades(wallet.address, limit=limit),
            )
            if trades is not None:
                recent_trades = WalletRecentTrades(items=trades.items, total=trades.total)

            activity = self._capture_data_error(
                section="recent_activity",
                errors=errors,
                operation=lambda: client.get_user_activity(wallet.address, limit=limit),
            )
            if activity is not None:
                recent_activity = WalletRecentActivity(items=activity.items, total=activity.total)

        return WalletSummaryResponse(
            wallet=wallet,
            metrics=metrics,
            recent_trades=recent_trades,
            recent_activity=recent_activity,
            errors=errors,
        )

    def get_snapshot(self, *, limit: int) -> WalletSnapshotResponse:
        """Build a compact tracked-wallet overview in registry order."""
        wallets = self._registry.list_wallets()[:limit]
        items: list[WalletSnapshotItem] = []

        with DataClient() as client:
            for wallet in wallets:
                wallet_address = wallet.address
                metrics = WalletSummaryMetrics()
                errors: list[WalletSectionError] = []

                holdings_value = self._capture_data_error(
                    section="holdings_value",
                    errors=errors,
                    operation=partial(client.get_holdings_value, wallet_address),
                )
                if holdings_value is not None:
                    metrics.holdings_value = holdings_value.value

                traded_count = self._capture_data_error(
                    section="traded_count",
                    errors=errors,
                    operation=partial(client.get_traded_count, wallet_address),
                )
                if traded_count is not None:
                    metrics.traded_count = traded_count.traded

                positions = self._capture_data_error(
                    section="current_positions",
                    errors=errors,
                    operation=partial(client.get_current_positions, wallet_address),
                )
                if positions is not None:
                    metrics.current_positions_count = positions.total

                closed_positions = self._capture_data_error(
                    section="closed_positions",
                    errors=errors,
                    operation=partial(client.get_closed_positions, wallet_address),
                )
                if closed_positions is not None:
                    metrics.closed_positions_count = closed_positions.total

                items.append(WalletSnapshotItem(wallet=wallet, metrics=metrics, errors=errors))

        return WalletSnapshotResponse(items=items, total=len(items))

    def discover_leaderboard(self, *, limit: int) -> WalletLeaderboardDiscoveryResponse:
        """Return wallet candidates from the public trader leaderboard."""
        tracked_map = self._tracked_wallet_map()
        errors: list[WalletSectionError] = []

        with DataClient() as client:
            response = self._capture_data_error(
                section="leaderboard",
                errors=errors,
                operation=lambda: client.get_leaderboard(limit=limit),
            )

        if response is None:
            return WalletLeaderboardDiscoveryResponse(errors=errors)

        items = [
            self._build_leaderboard_discovery_item(entry=response_item, tracked_map=tracked_map)
            for response_item in response.items
        ]
        return WalletLeaderboardDiscoveryResponse(items=items, total=len(items), errors=errors)

    def discover_holders(self, market_ref: str, *, limit: int) -> WalletHoldersDiscoveryResponse:
        """Return unique holder-backed wallet candidates for a market."""
        tracked_map = self._tracked_wallet_map()
        errors: list[WalletSectionError] = []

        with DataClient() as client:
            try:
                response = client.get_holders(market_ref, limit=limit)
            except DataValidationError:
                raise
            except (DataNotFoundError, DataClientError) as exc:
                errors.append(
                    WalletSectionError(
                        section="holders",
                        code=_data_error_code(exc),
                        message=str(exc),
                    )
                )
                return WalletHoldersDiscoveryResponse(errors=errors)

        items = self._build_holders_discovery_items(
            response=response,
            limit=limit,
            tracked_map=tracked_map,
        )
        return WalletHoldersDiscoveryResponse(
            market_slug=response.market_slug,
            condition_id=response.condition_id,
            items=items,
            total=len(items),
            errors=errors,
        )

    def score_wallet(self, address: str) -> WalletScoreResponse:
        """Return a deterministic public wallet score."""
        normalized_address = normalize_wallet_address(address)
        tracked_map = self._tracked_wallet_map()
        with DataClient() as client:
            return self._score_wallet(
                normalized_address,
                client=client,
                tracked_map=tracked_map,
            )

    def rank_tracked_wallets(self) -> WalletRankTrackedResponse:
        """Score and rank every tracked wallet in deterministic order."""
        wallets = self._registry.list_wallets()
        tracked_map = {wallet.address: wallet for wallet in wallets}

        with DataClient() as client:
            scores = [
                self._score_wallet(wallet.address, client=client, tracked_map=tracked_map)
                for wallet in wallets
            ]

        sorted_scores = sorted(
            scores,
            key=lambda score: (
                _descending_sort_key(score.total_score),
                _descending_sort_key(_component_score(score, LEADERBOARD_COMPONENT)),
                _descending_sort_key(_component_score(score, REALIZED_PERFORMANCE_COMPONENT)),
                score.address,
            ),
        )
        items = [
            WalletRankItem(rank=index, score=score)
            for index, score in enumerate(sorted_scores, start=1)
        ]
        return WalletRankTrackedResponse(items=items, total=len(items))

    def compare_wallets(self, left_address: str, right_address: str) -> WalletCompareResponse:
        """Compare two public wallet scores without mutating local state."""
        normalized_left = normalize_wallet_address(left_address)
        normalized_right = normalize_wallet_address(right_address)
        tracked_map = self._tracked_wallet_map()

        with DataClient() as client:
            left = self._score_wallet(normalized_left, client=client, tracked_map=tracked_map)
            right = self._score_wallet(normalized_right, client=client, tracked_map=tracked_map)

        if left.total_score is not None and right.total_score is not None:
            score_delta = _round_score(left.total_score - right.total_score)
            if score_delta > 0:
                winner_address = left.address
            elif score_delta < 0:
                winner_address = right.address
            else:
                winner_address = None
        elif left.total_score is not None:
            score_delta = None
            winner_address = left.address
        elif right.total_score is not None:
            score_delta = None
            winner_address = right.address
        else:
            score_delta = None
            winner_address = None

        component_deltas = {
            component_name: _component_delta(left, right, component_name)
            for component_name in COMPONENT_ORDER
        }
        return WalletCompareResponse(
            left=left,
            right=right,
            winner_address=winner_address,
            score_delta=score_delta,
            component_deltas=component_deltas,
        )

    def _score_wallet(
        self,
        address: str,
        *,
        client: DataClient,
        tracked_map: dict[str, TrackedWallet],
    ) -> WalletScoreResponse:
        tracked_wallet = tracked_map.get(address)
        errors: list[WalletSectionError] = []
        components = {
            LEADERBOARD_COMPONENT: self._score_leaderboard_component(
                client,
                address=address,
                errors=errors,
            ),
            REALIZED_PERFORMANCE_COMPONENT: self._score_realized_performance_component(
                client,
                address=address,
                errors=errors,
            ),
            ACTIVITY_COMPONENT: self._score_activity_component(
                client,
                address=address,
                errors=errors,
            ),
            FOOTPRINT_COMPONENT: self._score_footprint_component(
                client,
                address=address,
                errors=errors,
            ),
        }
        total_score, available_weight = _combine_component_scores(components)
        return WalletScoreResponse(
            address=address,
            tracked=tracked_wallet is not None,
            tracked_wallet=tracked_wallet,
            total_score=total_score,
            available_weight=available_weight,
            components=components,
            errors=errors,
        )

    def _score_leaderboard_component(
        self,
        client: DataClient,
        *,
        address: str,
        errors: list[WalletSectionError],
    ) -> WalletScoreComponent:
        weight = COMPONENT_WEIGHTS[LEADERBOARD_COMPONENT]
        try:
            leaderboard = client.get_leaderboard(limit=1, user=address)
        except (DataNotFoundError, DataClientError) as exc:
            errors.append(
                WalletSectionError(
                    section=LEADERBOARD_COMPONENT,
                    code=_data_error_code(exc),
                    message=str(exc),
                )
            )
            return WalletScoreComponent(weight=weight, score=None, available=False)

        entry = leaderboard.items[0] if leaderboard.items else None
        rank = entry.rank if entry is not None else None
        score = _leaderboard_rank_bucket(rank)
        return WalletScoreComponent(
            weight=weight,
            score=float(score),
            available=True,
            inputs={
                "rank": rank,
                "pnl": entry.pnl if entry is not None else None,
                "volume": entry.volume if entry is not None else None,
            },
        )

    def _score_realized_performance_component(
        self,
        client: DataClient,
        *,
        address: str,
        errors: list[WalletSectionError],
    ) -> WalletScoreComponent:
        weight = COMPONENT_WEIGHTS[REALIZED_PERFORMANCE_COMPONENT]
        try:
            closed_positions = client.get_closed_positions(address)
        except DataNotFoundError:
            closed_positions = None
        except DataClientError as exc:
            errors.append(
                WalletSectionError(
                    section=REALIZED_PERFORMANCE_COMPONENT,
                    code=_data_error_code(exc),
                    message=str(exc),
                )
            )
            return WalletScoreComponent(weight=weight, score=None, available=False)

        positions = closed_positions.items if closed_positions is not None else []
        realized_total = _sum_position_decimals(positions, field="realized_pnl")
        if realized_total is None:
            errors.append(
                WalletSectionError(
                    section=REALIZED_PERFORMANCE_COMPONENT,
                    code="request_failed",
                    message="Could not parse realized_pnl values returned by the Data API.",
                )
            )
            return WalletScoreComponent(weight=weight, score=None, available=False)

        score = _realized_pnl_bucket(realized_total)
        return WalletScoreComponent(
            weight=weight,
            score=float(score),
            available=True,
            inputs={
                "closed_positions_count": len(positions),
                "realized_pnl_total": _decimal_to_string(realized_total),
            },
        )

    def _score_activity_component(
        self,
        client: DataClient,
        *,
        address: str,
        errors: list[WalletSectionError],
    ) -> WalletScoreComponent:
        weight = COMPONENT_WEIGHTS[ACTIVITY_COMPONENT]
        try:
            traded_count = client.get_traded_count(address)
            traded = traded_count.traded
        except DataNotFoundError:
            traded = 0
        except DataClientError as exc:
            errors.append(
                WalletSectionError(
                    section=ACTIVITY_COMPONENT,
                    code=_data_error_code(exc),
                    message=str(exc),
                )
            )
            return WalletScoreComponent(weight=weight, score=None, available=False)

        score = _activity_bucket(traded)
        return WalletScoreComponent(
            weight=weight,
            score=float(score),
            available=True,
            inputs={"traded_count": traded},
        )

    def _score_footprint_component(
        self,
        client: DataClient,
        *,
        address: str,
        errors: list[WalletSectionError],
    ) -> WalletScoreComponent:
        weight = COMPONENT_WEIGHTS[FOOTPRINT_COMPONENT]
        try:
            holdings_value = client.get_holdings_value(address).value
        except DataNotFoundError:
            holdings_value = "0"
        except DataClientError as exc:
            errors.append(
                WalletSectionError(
                    section=FOOTPRINT_COMPONENT,
                    code=_data_error_code(exc),
                    message=str(exc),
                )
            )
            return WalletScoreComponent(weight=weight, score=None, available=False)

        holdings_decimal = _parse_decimal(holdings_value)
        if holdings_decimal is None:
            errors.append(
                WalletSectionError(
                    section=FOOTPRINT_COMPONENT,
                    code="request_failed",
                    message="Could not parse holdings value returned by the Data API.",
                )
            )
            return WalletScoreComponent(weight=weight, score=None, available=False)

        try:
            positions = client.get_current_positions(address)
            current_positions_count = positions.total
        except DataNotFoundError:
            current_positions_count = 0
        except DataClientError as exc:
            errors.append(
                WalletSectionError(
                    section=FOOTPRINT_COMPONENT,
                    code=_data_error_code(exc),
                    message=str(exc),
                )
            )
            return WalletScoreComponent(weight=weight, score=None, available=False)

        holdings_bucket = _holdings_bucket(holdings_decimal)
        positions_bucket = _positions_bucket(current_positions_count)
        score = _round_score((holdings_bucket + positions_bucket) / 2)
        return WalletScoreComponent(
            weight=weight,
            score=score,
            available=True,
            inputs={
                "holdings_value": _decimal_to_string(holdings_decimal),
                "current_positions_count": current_positions_count,
                "holdings_bucket": float(holdings_bucket),
                "positions_bucket": float(positions_bucket),
            },
        )

    def _tracked_wallet_map(self) -> dict[str, TrackedWallet]:
        return {wallet.address: wallet for wallet in self._registry.list_wallets()}

    @staticmethod
    def _capture_data_error(
        *,
        section: str,
        errors: list[WalletSectionError],
        operation: Callable[[], T],
    ) -> T | None:
        try:
            return operation()
        except (DataValidationError, DataNotFoundError, DataClientError) as exc:
            errors.append(
                WalletSectionError(
                    section=section,
                    code=_data_error_code(exc),
                    message=str(exc),
                )
            )
            return None

    @staticmethod
    def _build_leaderboard_discovery_item(
        *,
        entry: NormalizedLeaderboardEntry,
        tracked_map: dict[str, TrackedWallet],
    ) -> WalletDiscoveryItem:
        tracked_wallet = tracked_map.get(entry.address)
        return WalletDiscoveryItem(
            address=entry.address,
            source="leaderboard",
            tracked=tracked_wallet is not None,
            tracked_wallet=tracked_wallet,
            display_name=entry.display_name,
            user_name=entry.user_name,
            rank=entry.rank,
            pnl=entry.pnl,
            volume=entry.volume,
        )

    @staticmethod
    def _build_holders_discovery_items(
        *,
        response: HoldersResponse,
        limit: int,
        tracked_map: dict[str, TrackedWallet],
    ) -> list[WalletDiscoveryItem]:
        candidates: dict[str, WalletDiscoveryItem] = {}

        for holder in response.items:
            try:
                normalized_address = normalize_wallet_address(holder.holder_address)
            except DataValidationError:
                continue

            existing = candidates.get(normalized_address)
            exposure = WalletDiscoveryTokenExposure(
                token_id=holder.token_id,
                amount=holder.amount,
                outcome_index=holder.outcome_index,
            )

            if existing is None:
                if len(candidates) >= limit:
                    continue
                tracked_wallet = tracked_map.get(normalized_address)
                candidates[normalized_address] = WalletDiscoveryItem(
                    address=normalized_address,
                    source="holders",
                    tracked=tracked_wallet is not None,
                    tracked_wallet=tracked_wallet,
                    display_name=holder.name,
                    user_name=holder.pseudonym,
                    rank=holder.rank,
                    market_slug=response.market_slug,
                    condition_id=response.condition_id,
                    token_exposures=[exposure],
                )
                continue

            existing.token_exposures.append(exposure)
            if existing.display_name is None:
                existing.display_name = holder.name
            if existing.user_name is None:
                existing.user_name = holder.pseudonym

        return list(candidates.values())


def _data_error_code(exc: Exception) -> str:
    if isinstance(exc, DataValidationError):
        return "invalid_argument"
    if isinstance(exc, DataNotFoundError):
        return "not_found"
    return "request_failed"


def _sum_position_decimals(
    positions: list[NormalizedClosedPosition],
    *,
    field: str,
) -> Decimal | None:
    total = Decimal("0")
    for position in positions:
        value = getattr(position, field)
        if value is None:
            continue
        parsed = _parse_decimal(value)
        if parsed is None:
            return None
        total += parsed
    return total


def _parse_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _decimal_to_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f").split(".")[0]
    return format(normalized, "f")


def _leaderboard_rank_bucket(rank: int | None) -> int:
    if rank is None:
        return 0
    if rank <= 10:
        return 100
    if rank <= 25:
        return 90
    if rank <= 50:
        return 80
    if rank <= 100:
        return 70
    if rank <= 250:
        return 60
    if rank <= 500:
        return 50
    if rank <= 1000:
        return 40
    return 25


def _realized_pnl_bucket(realized_pnl_total: Decimal) -> int:
    if realized_pnl_total <= Decimal("0"):
        return 0
    if realized_pnl_total < Decimal("100"):
        return 20
    if realized_pnl_total < Decimal("500"):
        return 40
    if realized_pnl_total < Decimal("1000"):
        return 60
    if realized_pnl_total < Decimal("5000"):
        return 80
    return 100


def _activity_bucket(traded_count: int) -> int:
    if traded_count <= 0:
        return 0
    if traded_count < 10:
        return 20
    if traded_count < 25:
        return 40
    if traded_count < 50:
        return 60
    if traded_count < 100:
        return 80
    return 100


def _holdings_bucket(holdings_value: Decimal) -> int:
    if holdings_value <= Decimal("0"):
        return 0
    if holdings_value < Decimal("100"):
        return 20
    if holdings_value < Decimal("1000"):
        return 40
    if holdings_value < Decimal("5000"):
        return 60
    if holdings_value < Decimal("20000"):
        return 80
    return 100


def _positions_bucket(current_positions_count: int) -> int:
    if current_positions_count <= 0:
        return 0
    if current_positions_count == 1:
        return 20
    if current_positions_count < 5:
        return 40
    if current_positions_count < 10:
        return 60
    if current_positions_count < 20:
        return 80
    return 100


def _combine_component_scores(
    components: dict[str, WalletScoreComponent],
) -> tuple[float | None, float]:
    available_components = [
        component
        for component in components.values()
        if component.available and component.score is not None
    ]
    if not available_components:
        return None, 0.0

    available_weight = 0.0
    weighted_total = 0.0
    for component in available_components:
        assert component.score is not None
        available_weight += component.weight
        weighted_total += component.weight * component.score
    return _round_score(weighted_total / available_weight), _round_score(available_weight)


def _component_score(score: WalletScoreResponse, name: str) -> float | None:
    component = score.components.get(name)
    return component.score if component is not None else None


def _component_delta(
    left: WalletScoreResponse,
    right: WalletScoreResponse,
    component_name: str,
) -> float | None:
    left_score = _component_score(left, component_name)
    right_score = _component_score(right, component_name)
    if left_score is None or right_score is None:
        return None
    return _round_score(left_score - right_score)


def _descending_sort_key(value: float | None) -> float:
    return -value if value is not None else float("inf")


def _round_score(value: float) -> float:
    return round(value, 2)
