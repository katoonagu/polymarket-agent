"""Seeded risk policy service for guarded strategy dispatch."""

from __future__ import annotations

from pm.risk.models import (
    RiskInitDefaultsResponse,
    RiskPoliciesFile,
    RiskPolicy,
    RiskShowResponse,
)
from pm.risk.state import RiskStateError, RiskStateService
from pm.strategy.registry import StrategyRegistryService

DEFAULT_POLICY_NAME = "default"
DISPATCH_ENABLED_STRATEGIES = {"wallet_shadow_copy"}


class RiskPolicyService:
    """Resolve effective risk policies for strategy dispatch."""

    def __init__(
        self,
        *,
        state: RiskStateService | None = None,
        registry: StrategyRegistryService | None = None,
    ) -> None:
        self._state = state or RiskStateService()
        self._registry = registry or StrategyRegistryService()

    def show(self) -> RiskShowResponse:
        """Return the effective policy set without forcing persistence."""
        document, persisted = self._load_effective_document()
        return RiskShowResponse(
            persisted=persisted,
            default_policy=document.default_policy,
            strategies=document.strategies,
            total=len(document.strategies),
        )

    def init_defaults(self) -> RiskInitDefaultsResponse:
        """Persist the seeded default policy set once, idempotently."""
        if self._state.exists():
            document = self._state.load()
            initialized = False
        else:
            document = _seeded_policies(self._registry)
            self._state.write(document)
            initialized = True
        return RiskInitDefaultsResponse(
            initialized=initialized,
            persisted=True,
            default_policy=document.default_policy,
            strategies=document.strategies,
            total=len(document.strategies),
        )

    def get_policy(self, strategy_name: str) -> RiskPolicy:
        """Return the effective materialized policy for one strategy."""
        document, _ = self._load_effective_document()
        for policy in document.strategies:
            if policy.strategy_name == strategy_name:
                return policy
        return document.default_policy

    def _load_effective_document(self) -> tuple[RiskPoliciesFile, bool]:
        if self._state.exists():
            return self._state.load(), True
        return _seeded_policies(self._registry), False


def _seeded_policies(registry: StrategyRegistryService) -> RiskPoliciesFile:
    strategies = registry.list_strategies()
    default_policy = RiskPolicy(
        strategy_name=DEFAULT_POLICY_NAME,
        dispatch_enabled=False,
        max_drift_pct="5",
        max_spread_pct="5",
        max_size_usdc_per_order="25",
        max_exposure_usdc_per_market="100",
        max_exposure_usdc_per_strategy="250",
        require_market_open=True,
        require_balance_ready=True,
        require_allowance_ready=True,
    )
    materialized = [
        default_policy.model_copy(
            update={
                "strategy_name": strategy.name,
                "dispatch_enabled": strategy.name in DISPATCH_ENABLED_STRATEGIES,
            }
        )
        for strategy in strategies
    ]
    return RiskPoliciesFile(default_policy=default_policy, strategies=materialized)


__all__ = [
    "DEFAULT_POLICY_NAME",
    "DISPATCH_ENABLED_STRATEGIES",
    "RiskPolicyService",
    "RiskStateError",
]
