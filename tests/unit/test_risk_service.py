"""Unit tests for guarded strategy dispatch risk policy state."""

from __future__ import annotations

from pm.risk import RiskPolicyService, RiskStateError, RiskStateService
from pm.strategy import StrategyRegistryService


def _build_service(tmp_path) -> RiskPolicyService:
    return RiskPolicyService(
        state=RiskStateService(policies_path=tmp_path / "risk-policies.json"),
        registry=StrategyRegistryService(path=tmp_path / "strategies.json"),
    )


def test_risk_show_uses_built_in_defaults_without_writing(tmp_path) -> None:
    service = _build_service(tmp_path)

    result = service.show()

    assert result.persisted is False
    assert result.total == 3
    assert result.default_policy.strategy_name == "default"
    assert result.strategies[0].strategy_name == "wallet_shadow_copy"
    assert result.strategies[0].dispatch_enabled is True
    assert result.strategies[1].dispatch_enabled is False
    assert not (tmp_path / "risk-policies.json").exists()


def test_risk_init_defaults_is_idempotent(tmp_path) -> None:
    service = _build_service(tmp_path)

    first = service.init_defaults()
    second = service.init_defaults()

    assert first.initialized is True
    assert second.initialized is False
    assert first.persisted is True
    assert second.persisted is True
    assert (tmp_path / "risk-policies.json").exists()


def test_invalid_risk_policy_state_raises_error(tmp_path) -> None:
    (tmp_path / "risk-policies.json").write_text('{"version": "bad"}\n', encoding="utf-8")
    service = _build_service(tmp_path)

    try:
        service.show()
    except RiskStateError as exc:
        assert "Risk policy state" in str(exc)
    else:
        raise AssertionError("Expected RiskStateError for invalid risk policy state.")
