from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.auth.models import (
    AuthContext,
    AuthProfileClearResponse,
    AuthProfileDoctorResponse,
    AuthProfileFromEnvResponse,
    AuthProfileInitResponse,
    AuthProfileShowResponse,
    AuthSectionCheck,
    OperatorProfile,
)
from pm.cli.app import app

runner = CliRunner()


class FakeProfileAuthService:
    def __init__(self, *args: object, **kwargs: object) -> None:
        return None

    def __enter__(self) -> FakeProfileAuthService:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def profile_show(self) -> AuthProfileShowResponse:
        return AuthProfileShowResponse(present=True, profile=_profile())

    def profile_init(
        self,
        *,
        signature_type: int,
        signer: str,
        funder: str,
        chain_id: int | None = None,
        label: str | None = None,
    ) -> AuthProfileInitResponse:
        return AuthProfileInitResponse(
            profile=_profile(signature_type=signature_type, chain_id=chain_id or 137, label=label)
        )

    def profile_from_env(self) -> AuthProfileFromEnvResponse:
        return AuthProfileFromEnvResponse(profile=_profile(source="env"))

    def profile_doctor(self) -> AuthProfileDoctorResponse:
        return AuthProfileDoctorResponse(
            ready=True,
            present=True,
            profile=_profile(),
            auth=_auth_context(),
            auth_env_ready=True,
            checks=[
                AuthSectionCheck(
                    section="signer",
                    status="pass",
                    message="Signer resolves correctly.",
                )
            ],
            errors=[],
            geoblock_reminder="Live geoblock checks still run at mutation time.",
        )

    def profile_clear(self) -> AuthProfileClearResponse:
        return AuthProfileClearResponse(cleared=True)


def test_auth_help_lists_profile_namespace() -> None:
    result = runner.invoke(app, ["auth", "--help"])

    assert result.exit_code == 0
    assert "profile" in result.stdout


def test_auth_profile_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.auth.AuthService", FakeProfileAuthService)

    show_result = runner.invoke(app, ["auth", "profile", "show", "--json"])
    init_result = runner.invoke(
        app,
        [
            "auth",
            "profile",
            "init",
            "--signature-type",
            "1",
            "--signer",
            "0x" + ("2" * 40),
            "--funder",
            "0x" + ("3" * 40),
            "--chain-id",
            "137",
            "--label",
            "desk-a",
            "--json",
        ],
    )
    from_env_result = runner.invoke(app, ["auth", "profile", "from-env", "--json"])
    doctor_result = runner.invoke(app, ["auth", "profile", "doctor", "--json"])
    clear_result = runner.invoke(app, ["auth", "profile", "clear", "--json"])

    assert json.loads(show_result.stdout)["present"] is True
    assert json.loads(init_result.stdout)["profile"]["account_label"] == "desk-a"
    assert json.loads(from_env_result.stdout)["profile"]["source"] == "env"
    assert json.loads(doctor_result.stdout)["ready"] is True
    assert json.loads(clear_result.stdout)["cleared"] is True


def test_auth_profile_root_output_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.auth.AuthService", FakeProfileAuthService)

    result = runner.invoke(app, ["--output", "json", "auth", "profile", "show"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["profile"]["signer_address"].startswith("0x")


def _profile(
    *,
    signature_type: int = 1,
    chain_id: int = 137,
    label: str | None = "desk-a",
    source: str = "manual",
) -> OperatorProfile:
    return OperatorProfile(
        signer_address="0x" + ("2" * 40),
        funder_address="0x" + ("3" * 40),
        signature_type=signature_type,
        chain_id=chain_id,
        account_label=label,
        source=source,
    )


def _auth_context() -> AuthContext:
    return AuthContext(
        signer_address="0x" + ("2" * 40),
        funder_address="0x" + ("3" * 40),
        signature_type=1,
        signature_type_name="POLY_PROXY",
        clob_host="https://clob.polymarket.com",
        chain_id=137,
        private_key_present=True,
        api_key_derivation_possible=True,
    )
