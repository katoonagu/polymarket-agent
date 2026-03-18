from __future__ import annotations

from dataclasses import dataclass

from pm.auth.models import GeoblockStatus
from pm.auth.service import (
    CHAIN_ID_ENV,
    CLOB_HOST_ENV,
    FUNDER_ENV,
    PRIVATE_KEY_ENV,
    SIGNATURE_TYPE_ENV,
    AuthService,
    AuthValidationError,
)

PRIVATE_KEY = "0x" + ("1" * 64)


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
        self.creds: FakeApiCreds | None = None

    def get_ok(self) -> dict[str, str]:
        return {"status": "ok"}

    def create_or_derive_api_creds(self) -> FakeApiCreds:
        return FakeApiCreds(
            api_key="derived-key",
            api_secret="derived-secret",
            api_passphrase="derived-passphrase",
        )

    def set_api_creds(self, creds: FakeApiCreds) -> None:
        self.creds = creds

    def get_balance_allowance(self, params: object) -> dict[str, str | int]:
        return {
            "balance": "123.45",
            "allowance": "456.78",
            "tokenId": "",
        }


def test_auth_show_never_exposes_private_key(monkeypatch) -> None:
    monkeypatch.setenv(PRIVATE_KEY_ENV, PRIVATE_KEY)
    monkeypatch.setenv(SIGNATURE_TYPE_ENV, "EOA")

    with AuthService(sdk_client_cls=FakeSDKClient) as service:
        result = service.show()

    payload = result.model_dump_json()
    assert result.auth.private_key_present is True
    assert result.auth.signer_address is not None
    assert PRIVATE_KEY not in payload


def test_auth_require_valid_config_requires_chain_id_for_custom_host(monkeypatch) -> None:
    monkeypatch.setenv(PRIVATE_KEY_ENV, PRIVATE_KEY)
    monkeypatch.setenv(SIGNATURE_TYPE_ENV, "EOA")
    monkeypatch.setenv(CLOB_HOST_ENV, "https://example.com")
    monkeypatch.delenv(CHAIN_ID_ENV, raising=False)

    with AuthService(sdk_client_cls=FakeSDKClient) as service:
        try:
            service.require_valid_config()
        except AuthValidationError as exc:
            assert CHAIN_ID_ENV in str(exc)
        else:
            raise AssertionError("Expected AuthValidationError")


def test_auth_doctor_reports_ready_when_config_is_valid(monkeypatch) -> None:
    monkeypatch.setenv(PRIVATE_KEY_ENV, PRIVATE_KEY)
    monkeypatch.setenv(SIGNATURE_TYPE_ENV, "EOA")

    with AuthService(sdk_client_cls=FakeSDKClient) as service:
        service.check_geoblock = lambda: GeoblockStatus(  # type: ignore[method-assign]
            checked=True,
            blocked=False,
            message="Allowed",
        )
        result = service.doctor()

    assert result.ready is True
    assert result.auth.signer_address is not None
    assert any(check.section == "clob_host" and check.status == "pass" for check in result.checks)


def test_auth_derive_api_key_returns_ephemeral_credentials(monkeypatch) -> None:
    monkeypatch.setenv(PRIVATE_KEY_ENV, PRIVATE_KEY)
    monkeypatch.setenv(SIGNATURE_TYPE_ENV, "EOA")

    with AuthService(sdk_client_cls=FakeSDKClient) as service:
        result = service.derive_api_key()

    assert result.api_credentials.api_key == "derived-key"
    assert result.api_credentials.api_secret == "derived-secret"
    assert result.api_credentials.api_passphrase == "derived-passphrase"


def test_auth_balances_and_allowances_use_authenticated_lookup(monkeypatch) -> None:
    monkeypatch.setenv(PRIVATE_KEY_ENV, PRIVATE_KEY)
    monkeypatch.setenv(SIGNATURE_TYPE_ENV, "1")
    monkeypatch.setenv(FUNDER_ENV, "0x" + ("2" * 40))

    with AuthService(sdk_client_cls=FakeSDKClient) as service:
        balances = service.balances()
        allowances = service.allowances()

    assert balances.balance_view.balance == "123.45"
    assert balances.balance_view.allowance == "456.78"
    assert allowances.allowance_view.allowance == "456.78"
