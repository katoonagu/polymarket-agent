"""Read-only Data API client package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pm.data.models import (
    ActivityResponse,
    ClosedPositionsResponse,
    HoldersResponse,
    LeaderboardResponse,
    NormalizedActivity,
    NormalizedClosedPosition,
    NormalizedCurrentPosition,
    NormalizedHolder,
    NormalizedHoldingsValue,
    NormalizedLeaderboardEntry,
    NormalizedOpenInterest,
    NormalizedTrade,
    NormalizedTradedCount,
    PositionsResponse,
    TradesResponse,
)

if TYPE_CHECKING:
    from pm.data.client import (
        DataClient,
        DataClientError,
        DataNotFoundError,
        DataValidationError,
    )

__all__ = [
    "ActivityResponse",
    "ClosedPositionsResponse",
    "DataClient",
    "DataClientError",
    "DataNotFoundError",
    "DataValidationError",
    "HoldersResponse",
    "LeaderboardResponse",
    "NormalizedActivity",
    "NormalizedClosedPosition",
    "NormalizedCurrentPosition",
    "NormalizedHolder",
    "NormalizedHoldingsValue",
    "NormalizedLeaderboardEntry",
    "NormalizedOpenInterest",
    "NormalizedTrade",
    "NormalizedTradedCount",
    "PositionsResponse",
    "TradesResponse",
]


def __getattr__(name: str) -> object:
    if name in {
        "DataClient",
        "DataClientError",
        "DataNotFoundError",
        "DataValidationError",
    }:
        from pm.data.client import (
            DataClient,
            DataClientError,
            DataNotFoundError,
            DataValidationError,
        )

        exports = {
            "DataClient": DataClient,
            "DataClientError": DataClientError,
            "DataNotFoundError": DataNotFoundError,
            "DataValidationError": DataValidationError,
        }
        return exports[name]

    raise AttributeError(f"module 'pm.data' has no attribute {name!r}")
