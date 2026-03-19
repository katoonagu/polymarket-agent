"""Models for guarded strategy-to-execution risk policy state."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RiskPolicy(BaseModel):
    """Materialized risk policy for one strategy scope."""

    strategy_name: str
    dispatch_enabled: bool
    max_drift_pct: str
    max_spread_pct: str
    max_size_usdc_per_order: str
    max_exposure_usdc_per_market: str
    max_exposure_usdc_per_strategy: str
    require_market_open: bool = True
    require_balance_ready: bool = True
    require_allowance_ready: bool = True


class RiskPoliciesFile(BaseModel):
    """Versioned local risk policy document."""

    version: int = 1
    default_policy: RiskPolicy
    strategies: list[RiskPolicy] = Field(default_factory=list)


class RiskShowResponse(BaseModel):
    """Effective policy payload returned by `pm risk show`."""

    persisted: bool
    default_policy: RiskPolicy
    strategies: list[RiskPolicy] = Field(default_factory=list)
    total: int = 0


class RiskInitDefaultsResponse(BaseModel):
    """Idempotent initialization payload for `pm risk init-defaults`."""

    initialized: bool
    persisted: bool
    default_policy: RiskPolicy
    strategies: list[RiskPolicy] = Field(default_factory=list)
    total: int = 0
