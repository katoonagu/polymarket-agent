"""Tracked-wallet shadow-intelligence service built on the public Data API."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TypeVar

from pm.data import DataClient, DataClientError, DataNotFoundError, DataValidationError
from pm.wallet.models import (
    WalletActivityResponse,
    WalletListResponse,
    WalletMutationResponse,
    WalletPositionsResponse,
    WalletRecentActivity,
    WalletRecentTrades,
    WalletSectionError,
    WalletSnapshotItem,
    WalletSnapshotResponse,
    WalletSummaryMetrics,
    WalletSummaryResponse,
    WalletTradesResponse,
)
from pm.wallet.registry import WalletRegistryService

T = TypeVar("T")


class WalletShadowService:
    """High-level tracked-wallet reads and aggregation."""

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


def _data_error_code(exc: Exception) -> str:
    if isinstance(exc, DataValidationError):
        return "invalid_argument"
    if isinstance(exc, DataNotFoundError):
        return "not_found"
    return "request_failed"
