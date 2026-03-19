from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.auth.models import (
    AuthAllowancesResponse,
    AuthBalancesResponse,
    AuthContext,
    AuthDeriveApiKeyResponse,
    AuthShowResponse,
    BalanceAllowanceView,
    DerivedApiCredentials,
    GeoblockStatus,
    SetupDoctorResponse,
    SetupGuideCheckpoint,
    SetupGuideEnvironmentItem,
    SetupGuideResponse,
    SetupWizardResponse,
)
from pm.cli.app import app
from pm.execution.models import (
    DryRunBookContext,
    DryRunRequest,
    DryRunResolvedMarket,
    DryRunResponse,
    ExecutionReasonBlock,
)

runner = CliRunner()


class FakeSetupAuthService:
    def __init__(self, *args: object, **kwargs: object) -> None:
        env_overrides = kwargs.get("env_overrides")
        self._session_key_present = bool(
            isinstance(env_overrides, dict)
            and env_overrides.get("POLYMARKET_PRIVATE_KEY")
        )

    def __enter__(self) -> FakeSetupAuthService:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def doctor(self) -> SetupDoctorResponse:
        return SetupDoctorResponse(
            ready=True,
            auth=_auth_context(private_key_present=True),
            geoblock=GeoblockStatus(checked=True, blocked=False, message="Allowed"),
            checks=[],
            errors=[],
        )

    def guide(self) -> SetupGuideResponse:
        return SetupGuideResponse(
            auth=_auth_context(private_key_present=True),
            doctor=self.doctor(),
            environment_items=[
                SetupGuideEnvironmentItem(
                    name="POLYMARKET_PRIVATE_KEY",
                    required=True,
                    present=True,
                    safe_value="present",
                    message="Required for authenticated commands.",
                )
            ],
            checkpoints=[
                SetupGuideCheckpoint(
                    section="balances",
                    status="ready",
                    message="Authenticated balance lookup completed.",
                    details={"balance": "123.45"},
                ),
                SetupGuideCheckpoint(
                    section="allowances",
                    status="ready",
                    message="Authenticated allowance lookup completed.",
                    details={"allowance": "456.78"},
                ),
            ],
            next_steps=["pm approve check --json"],
        )

    def show(self) -> AuthShowResponse:
        return AuthShowResponse(
            auth=_auth_context(private_key_present=self._session_key_present),
            errors=[],
        )

    def wizard(
        self,
        *,
        interactive: bool,
        private_key_source: str,
        session_only_used: bool = False,
    ) -> SetupWizardResponse:
        has_private_key = private_key_source != "missing"
        auth = _auth_context(private_key_present=has_private_key)
        doctor = SetupDoctorResponse(
            ready=has_private_key,
            auth=auth,
            geoblock=GeoblockStatus(checked=True, blocked=False, message="Allowed"),
            checks=[],
            errors=[],
        )
        return SetupWizardResponse(
            auth=auth,
            doctor=doctor,
            environment_items=[
                SetupGuideEnvironmentItem(
                    name="POLYMARKET_PRIVATE_KEY",
                    required=True,
                    present=has_private_key,
                    safe_value="present" if has_private_key else "missing",
                    message="Required for authenticated commands.",
                )
            ],
            checkpoints=[
                SetupGuideCheckpoint(
                    section="geoblock",
                    status="ready",
                    message="Allowed",
                    details={"checked": True, "blocked": False},
                )
            ],
            next_steps=["pm setup doctor --json"],
            interactive=interactive,
            has_private_key=has_private_key,
            private_key_source=private_key_source if has_private_key else "missing",
            session_only_supported=True,
            session_only_used=session_only_used,
        )


class FakeShowAuthService(FakeSetupAuthService):
    def show(self) -> AuthShowResponse:
        return AuthShowResponse(auth=_auth_context(), errors=[])

    def derive_api_key(self) -> AuthDeriveApiKeyResponse:
        return AuthDeriveApiKeyResponse(
            auth=_auth_context(),
            api_credentials=DerivedApiCredentials(
                api_key="derived-key",
                api_secret="derived-secret",
                api_passphrase="derived-passphrase",
            ),
        )

    def balances(self) -> AuthBalancesResponse:
        return AuthBalancesResponse(
            auth=_auth_context(),
            balance_view=BalanceAllowanceView(
                asset_type="COLLATERAL",
                token_id=None,
                signature_type=0,
                balance="123.45",
                allowance="456.78",
            ),
        )

    def allowances(self) -> AuthAllowancesResponse:
        return AuthAllowancesResponse(
            auth=_auth_context(),
            allowance_view=BalanceAllowanceView(
                asset_type="COLLATERAL",
                token_id=None,
                signature_type=0,
                balance="123.45",
                allowance="456.78",
            ),
        )


class FakeDryRunService:
    def dry_run(
        self,
        *,
        market_ref: str,
        outcome: str,
        side: str,
        price: str,
        size: str,
    ) -> DryRunResponse:
        return DryRunResponse(
            request=DryRunRequest(
                market_ref=market_ref,
                outcome=outcome,
                side=side,
                price=price,
                size=size,
            ),
            auth=_auth_context(),
            market=DryRunResolvedMarket(
                market_slug="btc-above-100k",
                condition_id="0x" + ("a" * 64),
                question="Will BTC reach 100k?",
                token_id="100",
                outcome="yes",
                active=True,
                closed=False,
                tick_size="0.01",
                min_order_size="5",
                fee_rate_bps=12,
                neg_risk=False,
            ),
            book_context=DryRunBookContext(
                best_bid="0.54",
                best_ask="0.56",
                midpoint="0.55",
                spread="0.02",
                bid_level_count=1,
                ask_level_count=1,
            ),
            signed_order={"signature": "signed-payload", "tokenId": "100"},
            decision="WOULD_POST",
            reasons=[
                ExecutionReasonBlock(
                    section="local_signing",
                    status="pass",
                    message="Order was built and signed locally without submission.",
                )
            ],
        )


def test_setup_doctor_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.setup.AuthService", FakeSetupAuthService)

    result = runner.invoke(app, ["setup", "doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["auth"]["signer_address"].startswith("0x")


def test_setup_guide_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.setup.AuthService", FakeSetupAuthService)

    result = runner.invoke(app, ["setup", "guide", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["environment_items"][0]["name"] == "POLYMARKET_PRIVATE_KEY"
    assert payload["environment_items"][0]["safe_value"] == "present"
    assert payload["checkpoints"][0]["section"] == "balances"
    assert payload["next_steps"][0] == "pm approve check --json"


def test_setup_guide_human_output(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.setup.AuthService", FakeSetupAuthService)

    result = runner.invoke(app, ["setup", "guide"])

    assert result.exit_code == 0
    assert "POLYMARKET AGENT" in result.stdout
    assert "Environment Variables" in result.stdout
    assert "Setup Checkpoints" in result.stdout
    assert "Suggested Next Commands" in result.stdout


def test_setup_wizard_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.setup.AuthService", FakeSetupAuthService)

    result = runner.invoke(app, ["setup", "wizard", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["interactive"] is False
    assert payload["private_key_source"] == "missing"
    assert payload["secret_policy"].startswith("env_only_default")


def test_setup_wizard_human_no_private_key(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.setup.AuthService", FakeSetupAuthService)
    monkeypatch.setattr("pm.cli.setup.interactive_allowed", lambda *args, **kwargs: True)

    result = runner.invoke(app, ["setup", "wizard"], input="n\n")

    assert result.exit_code == 0
    assert "POLYMARKET AGENT" in result.stdout
    assert "Private key source" in result.stdout
    assert "missing" in result.stdout
    assert "Wizard Summary" in result.stdout


def test_setup_wizard_session_secret_does_not_echo(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.setup.AuthService", FakeSetupAuthService)
    monkeypatch.setattr("pm.cli.setup.interactive_allowed", lambda *args, **kwargs: True)

    private_key = "0x" + ("1" * 64)
    result = runner.invoke(
        app,
        ["setup", "wizard"],
        input=f"y\ny\n{private_key}\n",
    )

    assert result.exit_code == 0
    assert private_key not in result.stdout
    assert "Private key source" in result.stdout
    assert "session" in result.stdout
    assert "Session-only used" in result.stdout


def test_auth_show_and_derive_api_key_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.auth.AuthService", FakeShowAuthService)

    show_result = runner.invoke(app, ["auth", "show", "--json"])
    derive_result = runner.invoke(app, ["auth", "derive-api-key", "--json"])

    assert show_result.exit_code == 0
    assert derive_result.exit_code == 0
    assert json.loads(show_result.stdout)["auth"]["private_key_present"] is True
    assert json.loads(derive_result.stdout)["api_credentials"]["api_key"] == "derived-key"


def test_auth_balances_and_allowances_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.auth.AuthService", FakeShowAuthService)

    balances_result = runner.invoke(app, ["auth", "balances", "--json"])
    allowances_result = runner.invoke(app, ["auth", "allowances", "--json"])

    assert balances_result.exit_code == 0
    assert allowances_result.exit_code == 0
    assert json.loads(balances_result.stdout)["balance_view"]["balance"] == "123.45"
    assert json.loads(allowances_result.stdout)["allowance_view"]["allowance"] == "456.78"


def test_exec_dry_run_uses_root_json_output(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.execution.DryRunService", lambda: FakeDryRunService())

    result = runner.invoke(
        app,
        [
            "--output",
            "json",
            "exec",
            "dry-run",
            "--market",
            "btc-above-100k",
            "--outcome",
            "yes",
            "--side",
            "buy",
            "--price",
            "0.55",
            "--size",
            "10",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "WOULD_POST"
    assert payload["signed_order"]["signature"] == "signed-payload"


def _auth_context(*, private_key_present: bool = True) -> AuthContext:
    return AuthContext(
        signer_address="0x" + ("3" * 40),
        funder_address=None,
        signature_type=0,
        signature_type_name="EOA",
        clob_host="https://clob.polymarket.com",
        chain_id=137,
        private_key_present=private_key_present,
        api_key_derivation_possible=private_key_present,
    )
