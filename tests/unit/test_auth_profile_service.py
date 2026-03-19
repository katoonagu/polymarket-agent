from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from eth_account import Account

from pm.auth import (
    AuthProfileStateError,
    AuthService,
    AuthValidationError,
    OperatorProfile,
    OperatorProfileStateService,
    resolve_operator_account_address,
)

PRIVATE_KEY = "0x" + ("1" * 64)
SIGNER = Account.from_key(PRIVATE_KEY).address
FUNDER = "0x" + ("3" * 40)
OVERRIDE_SIGNER = "0x" + ("4" * 40)
OVERRIDE_FUNDER = "0x" + ("5" * 40)


@dataclass
class FakeApiCreds:
    api_key: str
    api_secret: str
    api_passphrase: str


class FakeSDKClient:
    def __init__(
        self,
        host: str,
        *,
        chain_id: int | None = None,
        key: str | None = None,
        signature_type: int | None = None,
        funder: str | None = None,
    ) -> None:
        self.host = host
        self.chain_id = chain_id
        self.key = key
        self.signature_type = signature_type
        self.funder = funder

    def get_ok(self) -> dict[str, str]:
        return {"status": "ok"}

    def create_or_derive_api_creds(self) -> FakeApiCreds:
        return FakeApiCreds(
            api_key="derived-key",
            api_secret="derived-secret",
            api_passphrase="derived-passphrase",
        )

    def set_api_creds(self, creds: FakeApiCreds) -> None:
        return None

    def get_balance_allowance(self, params: object) -> dict[str, str]:
        return {"balance": "10", "allowance": "20"}


def _profile_state(tmp_path: Path) -> OperatorProfileStateService:
    return OperatorProfileStateService(profile_path=tmp_path / "operator-profile.json")


def test_profile_init_show_and_clear(tmp_path: Path) -> None:
    state = _profile_state(tmp_path)

    with AuthService(profile_state=state, sdk_client_cls=FakeSDKClient) as service:
        init_result = service.profile_init(
            signature_type=1,
            signer=SIGNER,
            funder=FUNDER,
            chain_id=137,
            label="desk-a",
        )
        show_result = service.profile_show()
        clear_result = service.profile_clear()
        show_after_clear = service.profile_show()

    assert init_result.profile.source == "manual"
    assert init_result.profile.account_label == "desk-a"
    assert show_result.present is True
    assert show_result.profile is not None
    assert show_result.profile.signer_address == SIGNER
    assert clear_result.cleared is True
    assert show_after_clear.present is False
    assert show_after_clear.profile is None


def test_profile_from_env_requires_valid_auth_env(tmp_path: Path) -> None:
    state = _profile_state(tmp_path)

    with AuthService(
        profile_state=state,
        sdk_client_cls=FakeSDKClient,
        env_overrides={
            "POLYMARKET_PRIVATE_KEY": PRIVATE_KEY,
            "POLYMARKET_SIGNATURE_TYPE": "1",
            "POLYMARKET_FUNDER": FUNDER,
            "POLYMARKET_CHAIN_ID": "137",
        },
    ) as service:
        result = service.profile_from_env()

    assert result.profile.source == "env"
    assert result.profile.funder_address == FUNDER
    assert result.profile.chain_id == 137
    assert state.load_profile() is not None


def test_profile_from_env_refuses_partial_invalid_import(tmp_path: Path) -> None:
    state = _profile_state(tmp_path)

    with AuthService(
        profile_state=state,
        sdk_client_cls=FakeSDKClient,
        env_overrides={
            "POLYMARKET_SIGNATURE_TYPE": "1",
            "POLYMARKET_FUNDER": FUNDER,
            "POLYMARKET_CHAIN_ID": "137",
        },
    ) as service:
        with pytest.raises(AuthValidationError):
            service.profile_from_env()

    assert state.load_profile() is None


def test_show_applies_precedence_cli_then_profile_then_env(tmp_path: Path) -> None:
    state = _profile_state(tmp_path)
    state.save_profile(
        OperatorProfile(
            signer_address=SIGNER,
            funder_address=FUNDER,
            signature_type=2,
            chain_id=80002,
            account_label="desk-a",
            source="manual",
        )
    )

    with AuthService(
        profile_state=state,
        sdk_client_cls=FakeSDKClient,
        env_overrides={
            "POLYMARKET_SIGNATURE_TYPE": "0",
            "POLYMARKET_FUNDER": "0x" + ("6" * 40),
            "POLYMARKET_CHAIN_ID": "137",
        },
        account_overrides={
            "signer_address": OVERRIDE_SIGNER,
            "funder_address": OVERRIDE_FUNDER,
            "signature_type": 1,
            "chain_id": 10,
        },
    ) as service:
        result = service.show()

    assert result.auth.signer_address == OVERRIDE_SIGNER
    assert result.auth.funder_address == OVERRIDE_FUNDER
    assert result.auth.signature_type == 1
    assert result.auth.chain_id == 10


def test_require_valid_config_uses_profile_non_secret_fields(tmp_path: Path) -> None:
    state = _profile_state(tmp_path)
    state.save_profile(
        OperatorProfile(
            signer_address=SIGNER,
            funder_address=FUNDER,
            signature_type=1,
            chain_id=137,
            account_label=None,
            source="manual",
        )
    )

    with AuthService(
        profile_state=state,
        sdk_client_cls=FakeSDKClient,
        env_overrides={
            "POLYMARKET_PRIVATE_KEY": PRIVATE_KEY,
        },
    ) as service:
        settings = service.require_valid_config()

    assert settings.signature_type == 1
    assert settings.funder_address == FUNDER
    assert settings.chain_id == 137


def test_require_valid_config_rejects_signer_mismatch(tmp_path: Path) -> None:
    state = _profile_state(tmp_path)
    state.save_profile(
        OperatorProfile(
            signer_address=OVERRIDE_SIGNER,
            funder_address=FUNDER,
            signature_type=1,
            chain_id=137,
            account_label=None,
            source="manual",
        )
    )

    with AuthService(
        profile_state=state,
        sdk_client_cls=FakeSDKClient,
        env_overrides={
            "POLYMARKET_PRIVATE_KEY": PRIVATE_KEY,
            "POLYMARKET_SIGNATURE_TYPE": "1",
            "POLYMARKET_FUNDER": FUNDER,
            "POLYMARKET_CHAIN_ID": "137",
        },
    ) as service:
        with pytest.raises(AuthValidationError):
            service.require_valid_config()


def test_resolve_operator_account_address_prefers_funder_then_signer() -> None:
    auth = type(
        "AuthEnvelope",
        (),
        {
            "funder_address": FUNDER,
            "signer_address": SIGNER,
        },
    )()

    assert resolve_operator_account_address(auth) == FUNDER


def test_profile_state_invalid_document_raises(tmp_path: Path) -> None:
    path = tmp_path / "operator-profile.json"
    path.write_text('{"version":1,"profile":"bad"}\n', encoding="utf-8")
    state = OperatorProfileStateService(profile_path=path)

    with pytest.raises(AuthProfileStateError):
        state.load_profile()
