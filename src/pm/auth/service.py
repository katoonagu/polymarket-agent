"""Authenticated setup and account inspection service for non-live dry-run flows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from eth_account import Account
from py_clob_client.client import ClobClient as SDKClobClient  # type: ignore[import-untyped]
from py_clob_client.clob_types import (  # type: ignore[import-untyped]
    ApiCreds,
    AssetType,
    BalanceAllowanceParams,
)

from pm.auth.exceptions import AuthClientError, AuthValidationError
from pm.auth.models import (
    AuthAllowancesResponse,
    AuthBalancesResponse,
    AuthContext,
    AuthDeriveApiKeyResponse,
    AuthSectionCheck,
    AuthSectionError,
    AuthShowResponse,
    BalanceAllowanceView,
    DerivedApiCredentials,
    GeoblockStatus,
    SetupDoctorResponse,
    SetupGuideCheckpoint,
    SetupGuideEnvironmentItem,
    SetupGuideResponse,
)

DEFAULT_CLOB_HOST = "https://clob.polymarket.com"
DEFAULT_CHAIN_ID = 137
DEFAULT_TIMEOUT = 10.0
GEOBLOCK_URL = "https://polymarket.com/api/geoblock"
PRIVATE_KEY_ENV = "POLYMARKET_PRIVATE_KEY"
SIGNATURE_TYPE_ENV = "POLYMARKET_SIGNATURE_TYPE"
FUNDER_ENV = "POLYMARKET_FUNDER"
CLOB_HOST_ENV = "POLYMARKET_CLOB_HOST"
LEGACY_CLOB_HOST_ENV = "POLYMARKET_CLOB_URL"
CHAIN_ID_ENV = "POLYMARKET_CHAIN_ID"

_SIGNATURE_TYPES = {
    "0": (0, "EOA"),
    "1": (1, "POLY_PROXY"),
    "2": (2, "POLY_GNOSIS_SAFE"),
    "EOA": (0, "EOA"),
    "POLY_PROXY": (1, "POLY_PROXY"),
    "POLY_GNOSIS_SAFE": (2, "POLY_GNOSIS_SAFE"),
}


@dataclass(slots=True, frozen=True)
class AuthSettings:
    """Resolved authenticated environment settings."""

    private_key: str
    signature_type: int
    signature_type_name: str
    funder_address: str | None
    clob_host: str
    chain_id: int


class AuthService:
    """Authenticated setup and non-mutating account inspection service."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        sdk_client_cls: type[SDKClobClient] = SDKClobClient,
    ) -> None:
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT)
        self._sdk_client_cls = sdk_client_cls

    def __enter__(self) -> AuthService:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http_client:
            self._http_client.close()

    def show(self) -> AuthShowResponse:
        """Return best-effort authenticated context without mutating anything."""
        errors: list[AuthSectionError] = []
        auth = self._build_context(errors=errors, require_private_key=False)
        return AuthShowResponse(auth=auth, errors=errors)

    def doctor(self) -> SetupDoctorResponse:
        """Run non-mutating dry-run readiness checks."""
        checks: list[AuthSectionCheck] = []
        errors: list[AuthSectionError] = []
        auth = self._build_context(errors=errors, require_private_key=False)
        geoblock = self.check_geoblock()

        settings: AuthSettings | None = None
        try:
            settings = self.require_valid_config()
            checks.extend(
                [
                    AuthSectionCheck(
                        section="private_key",
                        status="pass",
                        message="Private key environment variable is present.",
                    ),
                    AuthSectionCheck(
                        section="signature_type",
                        status="pass",
                        message=(
                            f"Signature type '{settings.signature_type_name}' "
                            f"({settings.signature_type}) parsed successfully."
                        ),
                    ),
                    AuthSectionCheck(
                        section="funder",
                        status="pass",
                        message=(
                            f"Funder address resolved to {settings.funder_address}."
                            if settings.funder_address is not None
                            else "EOA signature type does not require a separate funder."
                        ),
                    ),
                ]
            )
        except AuthValidationError as exc:
            errors.append(
                AuthSectionError(
                    section="auth_config",
                    code="invalid_argument",
                    message=str(exc),
                )
            )
            checks.append(
                AuthSectionCheck(
                    section="auth_config",
                    status="fail",
                    message=str(exc),
                )
            )

        if auth.signer_address is not None:
            checks.append(
                AuthSectionCheck(
                    section="signer",
                    status="pass",
                    message=f"Signer address resolves to {auth.signer_address}.",
                )
            )
        else:
            checks.append(
                AuthSectionCheck(
                    section="signer",
                    status="fail",
                    message="Signer address could not be derived from the configured key.",
                )
            )

        if geoblock.checked and geoblock.blocked is False:
            checks.append(
                AuthSectionCheck(
                    section="geoblock",
                    status="pass",
                    message=geoblock.message or "Geoblock endpoint reported allowed access.",
                )
            )
        elif geoblock.checked and geoblock.blocked is True:
            checks.append(
                AuthSectionCheck(
                    section="geoblock",
                    status="fail",
                    message=geoblock.message or "Geoblock endpoint reported blocked access.",
                )
            )
            errors.append(
                AuthSectionError(
                    section="geoblock",
                    code="geoblocked",
                    message=geoblock.message or "Authenticated access appears geoblocked.",
                )
            )
        else:
            checks.append(
                AuthSectionCheck(
                    section="geoblock",
                    status="warn",
                    message=geoblock.message or "Geoblock endpoint could not be verified.",
                )
            )
            errors.append(
                AuthSectionError(
                    section="geoblock",
                    code="request_failed",
                    message=geoblock.message or "Geoblock endpoint could not be verified.",
                )
            )

        if settings is not None:
            try:
                client = self.build_level_1_client(settings)
                ok_payload = client.get_ok()
                checks.append(
                    AuthSectionCheck(
                        section="clob_host",
                        status="pass",
                        message=(
                            f"CLOB host responded successfully: {ok_payload!r}"
                            if ok_payload is not None
                            else "CLOB host responded successfully."
                        ),
                    )
                )
            except AuthClientError as exc:
                errors.append(
                    AuthSectionError(
                        section="clob_host",
                        code="request_failed",
                        message=str(exc),
                    )
                )
                checks.append(
                    AuthSectionCheck(
                        section="clob_host",
                        status="fail",
                        message=str(exc),
                    )
                )

            checks.append(
                AuthSectionCheck(
                    section="api_key_derivation",
                    status="pass" if auth.api_key_derivation_possible else "fail",
                    message=(
                        "Configuration is sufficient for ephemeral API-key derivation."
                        if auth.api_key_derivation_possible
                        else "Configuration is not sufficient for ephemeral API-key derivation."
                    ),
                )
            )

        ready = (
            settings is not None
            and auth.signer_address is not None
            and auth.api_key_derivation_possible
            and geoblock.checked
            and geoblock.blocked is False
            and any(check.section == "clob_host" and check.status == "pass" for check in checks)
        )
        return SetupDoctorResponse(
            ready=ready,
            auth=auth,
            geoblock=geoblock,
            checks=checks,
            errors=errors,
        )

    def guide(self) -> SetupGuideResponse:
        """Return a non-mutating guided setup checklist."""
        auth_result = self.show()
        doctor = self.doctor()
        auth = auth_result.auth
        environment_items = self._build_environment_items(auth)
        checkpoints = self._build_guide_checkpoints(auth=auth, doctor=doctor)
        next_steps = self._build_next_steps(doctor=doctor)
        return SetupGuideResponse(
            auth=auth,
            doctor=doctor,
            environment_items=environment_items,
            checkpoints=checkpoints,
            next_steps=next_steps,
        )

    def derive_api_key(self) -> AuthDeriveApiKeyResponse:
        """Derive ephemeral Level 2 API credentials without persisting them."""
        settings = self.require_valid_config()
        auth = self._context_from_settings(settings)
        creds = self.get_api_credentials(settings)
        return AuthDeriveApiKeyResponse(
            auth=auth,
            api_credentials=DerivedApiCredentials(
                api_key=creds.api_key,
                api_secret=creds.api_secret,
                api_passphrase=creds.api_passphrase,
            ),
        )

    def balances(self) -> AuthBalancesResponse:
        """Return authenticated collateral balance information."""
        settings = self.require_valid_config()
        auth = self._context_from_settings(settings)
        payload = self._fetch_balance_allowance(settings)
        return AuthBalancesResponse(
            auth=auth,
            balance_view=_normalize_balance_allowance_view(
                payload,
                signature_type=settings.signature_type,
                asset_type="COLLATERAL",
            ),
        )

    def allowances(self) -> AuthAllowancesResponse:
        """Return authenticated collateral allowance information."""
        settings = self.require_valid_config()
        auth = self._context_from_settings(settings)
        payload = self._fetch_balance_allowance(settings)
        return AuthAllowancesResponse(
            auth=auth,
            allowance_view=_normalize_balance_allowance_view(
                payload,
                signature_type=settings.signature_type,
                asset_type="COLLATERAL",
            ),
        )

    def require_valid_config(self) -> AuthSettings:
        """Require a complete valid authenticated environment configuration."""
        private_key = os.getenv(PRIVATE_KEY_ENV, "").strip()
        if not private_key:
            raise AuthValidationError(f"{PRIVATE_KEY_ENV} is required for authenticated commands.")

        signature_raw = os.getenv(SIGNATURE_TYPE_ENV, "").strip()
        if not signature_raw:
            raise AuthValidationError(
                f"{SIGNATURE_TYPE_ENV} is required for authenticated commands."
            )
        try:
            signature_type, signature_type_name = _parse_signature_type(signature_raw)
        except ValueError as exc:
            raise AuthValidationError(str(exc)) from exc

        funder_address = os.getenv(FUNDER_ENV, "").strip() or None
        if signature_type != 0 and not funder_address:
            raise AuthValidationError(
                f"{FUNDER_ENV} is required when signature type is {signature_type_name}."
            )
        if funder_address is not None and not _looks_like_address(funder_address):
            raise AuthValidationError(f"{FUNDER_ENV} must use 0x followed by 40 hex characters.")

        clob_host = (
            os.getenv(CLOB_HOST_ENV, "").strip()
            or os.getenv(LEGACY_CLOB_HOST_ENV, "").strip()
            or DEFAULT_CLOB_HOST
        ).rstrip("/")
        chain_id_raw = os.getenv(CHAIN_ID_ENV, "").strip()
        if clob_host != DEFAULT_CLOB_HOST and not chain_id_raw:
            raise AuthValidationError(
                f"{CHAIN_ID_ENV} is required when {CLOB_HOST_ENV} overrides the default host."
            )

        chain_id = DEFAULT_CHAIN_ID
        if chain_id_raw:
            try:
                chain_id = int(chain_id_raw)
            except ValueError as exc:
                raise AuthValidationError(f"{CHAIN_ID_ENV} must be an integer.") from exc

        try:
            Account.from_key(private_key)
        except Exception as exc:
            raise AuthValidationError(
                f"{PRIVATE_KEY_ENV} could not be parsed as a private key."
            ) from exc

        return AuthSettings(
            private_key=private_key,
            signature_type=signature_type,
            signature_type_name=signature_type_name,
            funder_address=funder_address,
            clob_host=clob_host,
            chain_id=chain_id,
        )

    def check_geoblock(self) -> GeoblockStatus:
        """Query the official geoblock endpoint."""
        try:
            response = self._http_client.get(GEOBLOCK_URL)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return GeoblockStatus(
                checked=False,
                blocked=None,
                message=f"Official geoblock check failed: {exc}",
            )

        if not isinstance(payload, dict):
            return GeoblockStatus(
                checked=False,
                blocked=None,
                message="Official geoblock response was not a JSON object.",
            )

        blocked = payload.get("blocked")
        if isinstance(blocked, str):
            blocked = blocked.strip().lower() == "true"
        if not isinstance(blocked, bool):
            blocked = None

        country = _string_or_none(payload.get("country")) or _string_or_none(
            payload.get("countryCode")
        )
        region = _string_or_none(payload.get("region")) or _string_or_none(payload.get("state"))
        message = _string_or_none(payload.get("message"))
        if message is None:
            if blocked is True:
                message = "Official geoblock endpoint reported blocked access."
            elif blocked is False:
                message = "Official geoblock endpoint reported allowed access."
            else:
                message = "Official geoblock endpoint did not return a clear blocked flag."

        return GeoblockStatus(
            checked=True,
            blocked=blocked,
            country=country,
            region=region,
            message=message,
        )

    def build_level_1_client(self, settings: AuthSettings | None = None) -> SDKClobClient:
        """Build an authenticated Level 1 SDK client."""
        resolved = settings or self.require_valid_config()
        try:
            return self._sdk_client_cls(
                resolved.clob_host,
                chain_id=resolved.chain_id,
                key=resolved.private_key,
                signature_type=resolved.signature_type,
                funder=resolved.funder_address,
            )
        except Exception as exc:
            raise AuthClientError("Could not initialize authenticated CLOB client.") from exc

    def build_level_2_client(self, settings: AuthSettings | None = None) -> SDKClobClient:
        """Build an authenticated Level 2 SDK client with ephemeral credentials."""
        resolved = settings or self.require_valid_config()
        try:
            client = self.build_level_1_client(resolved)
            creds = self.get_api_credentials(resolved)
            client.set_api_creds(creds)
            return client
        except AuthClientError:
            raise
        except Exception as exc:
            raise AuthClientError(
                "Could not initialize authenticated Level 2 CLOB client."
            ) from exc

    def get_api_credentials(self, settings: AuthSettings | None = None) -> ApiCreds:
        """Return ephemeral Level 2 API credentials without persisting them."""
        resolved = settings or self.require_valid_config()
        return self._derive_api_credentials(resolved)

    def _derive_api_credentials(self, settings: AuthSettings) -> ApiCreds:
        try:
            client = self.build_level_1_client(settings)
            return client.create_or_derive_api_creds()
        except Exception as exc:
            raise AuthClientError("Could not derive API credentials.") from exc

    def _fetch_balance_allowance(self, settings: AuthSettings) -> dict[str, Any]:
        try:
            client = self.build_level_2_client(settings)
            payload = client.get_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=settings.signature_type,
                )
            )
        except Exception as exc:
            raise AuthClientError("Authenticated balance and allowance lookup failed.") from exc

        if not isinstance(payload, dict):
            raise AuthClientError(
                "Authenticated balance and allowance lookup returned a non-object response."
            )
        return payload

    def _build_context(
        self,
        *,
        errors: list[AuthSectionError],
        require_private_key: bool,
    ) -> AuthContext:
        private_key = os.getenv(PRIVATE_KEY_ENV, "").strip()
        signature_raw = os.getenv(SIGNATURE_TYPE_ENV, "").strip()
        funder_address = os.getenv(FUNDER_ENV, "").strip() or None
        clob_host = (
            os.getenv(CLOB_HOST_ENV, "").strip()
            or os.getenv(LEGACY_CLOB_HOST_ENV, "").strip()
            or DEFAULT_CLOB_HOST
        ).rstrip("/")
        chain_id_raw = os.getenv(CHAIN_ID_ENV, "").strip()

        chain_id: int | None = (
            DEFAULT_CHAIN_ID if not chain_id_raw and clob_host == DEFAULT_CLOB_HOST else None
        )
        if chain_id_raw:
            try:
                chain_id = int(chain_id_raw)
            except ValueError:
                errors.append(
                    AuthSectionError(
                        section="chain_id",
                        code="invalid_argument",
                        message=f"{CHAIN_ID_ENV} must be an integer.",
                    )
                )

        signer_address: str | None = None
        if private_key:
            try:
                signer_address = Account.from_key(private_key).address
            except Exception:
                errors.append(
                    AuthSectionError(
                        section="private_key",
                        code="invalid_argument",
                        message=f"{PRIVATE_KEY_ENV} could not be parsed as a private key.",
                    )
                )
        elif require_private_key:
            errors.append(
                AuthSectionError(
                    section="private_key",
                    code="invalid_argument",
                    message=f"{PRIVATE_KEY_ENV} is required for authenticated commands.",
                )
            )

        signature_type: int | None = None
        signature_type_name: str | None = None
        if signature_raw:
            try:
                signature_type, signature_type_name = _parse_signature_type(signature_raw)
            except ValueError as exc:
                errors.append(
                    AuthSectionError(
                        section="signature_type",
                        code="invalid_argument",
                        message=str(exc),
                    )
                )
        elif require_private_key:
            errors.append(
                AuthSectionError(
                    section="signature_type",
                    code="invalid_argument",
                    message=f"{SIGNATURE_TYPE_ENV} is required for authenticated commands.",
                )
            )

        if funder_address is not None and not _looks_like_address(funder_address):
            errors.append(
                AuthSectionError(
                    section="funder",
                    code="invalid_argument",
                    message=f"{FUNDER_ENV} must use 0x followed by 40 hex characters.",
                )
            )

        if signature_type is not None and signature_type != 0 and funder_address is None:
            errors.append(
                AuthSectionError(
                    section="funder",
                    code="invalid_argument",
                    message=f"{FUNDER_ENV} is required for non-EOA signature types.",
                )
            )

        api_key_derivation_possible = (
            signer_address is not None
            and signature_type is not None
            and (signature_type == 0 or funder_address is not None)
            and chain_id is not None
        )
        return AuthContext(
            signer_address=signer_address,
            funder_address=funder_address,
            signature_type=signature_type,
            signature_type_name=signature_type_name,
            clob_host=clob_host,
            chain_id=chain_id,
            private_key_present=bool(private_key),
            api_key_derivation_possible=api_key_derivation_possible,
        )

    def _context_from_settings(self, settings: AuthSettings) -> AuthContext:
        signer_address = Account.from_key(settings.private_key).address
        return AuthContext(
            signer_address=signer_address,
            funder_address=settings.funder_address,
            signature_type=settings.signature_type,
            signature_type_name=settings.signature_type_name,
            clob_host=settings.clob_host,
            chain_id=settings.chain_id,
            private_key_present=True,
            api_key_derivation_possible=True,
        )

    def _build_environment_items(
        self,
        auth: AuthContext,
    ) -> list[SetupGuideEnvironmentItem]:
        signature_raw = os.getenv(SIGNATURE_TYPE_ENV, "").strip()
        funder_raw = os.getenv(FUNDER_ENV, "").strip()
        custom_host = bool(
            os.getenv(CLOB_HOST_ENV, "").strip()
            or os.getenv(LEGACY_CLOB_HOST_ENV, "").strip()
        )
        chain_raw = os.getenv(CHAIN_ID_ENV, "").strip()
        funder_required = auth.signature_type not in (None, 0)
        chain_required = custom_host
        return [
            SetupGuideEnvironmentItem(
                name=PRIVATE_KEY_ENV,
                required=True,
                present=auth.private_key_present,
                safe_value="present" if auth.private_key_present else "missing",
                message="Required for authenticated setup, dry-run signing, and guarded execution.",
            ),
            SetupGuideEnvironmentItem(
                name=SIGNATURE_TYPE_ENV,
                required=True,
                present=bool(signature_raw),
                safe_value=auth.signature_type_name or None,
                message="Required. Supported values: 0, 1, 2, EOA, POLY_PROXY, POLY_GNOSIS_SAFE.",
            ),
            SetupGuideEnvironmentItem(
                name=FUNDER_ENV,
                required=funder_required,
                present=bool(funder_raw),
                safe_value=funder_raw or None,
                message=(
                    "Required for non-EOA signature types."
                    if funder_required
                    else "Optional for EOA signature type."
                ),
            ),
            SetupGuideEnvironmentItem(
                name=CLOB_HOST_ENV,
                required=False,
                present=True,
                safe_value=auth.clob_host,
                message="Optional. Defaults to the official Polymarket CLOB host.",
            ),
            SetupGuideEnvironmentItem(
                name=CHAIN_ID_ENV,
                required=chain_required,
                present=bool(chain_raw) or auth.chain_id is not None,
                safe_value=str(auth.chain_id) if auth.chain_id is not None else None,
                message=(
                    "Required when overriding the default CLOB host."
                    if chain_required
                    else "Optional. Defaults to 137 for the default host."
                ),
            ),
        ]

    def _build_guide_checkpoints(
        self,
        *,
        auth: AuthContext,
        doctor: SetupDoctorResponse,
    ) -> list[SetupGuideCheckpoint]:
        checkpoints = [
            SetupGuideCheckpoint(
                section="signature_type",
                status="ready" if auth.signature_type_name is not None else "blocked",
                message=(
                    f"Using signature type {auth.signature_type_name}."
                    if auth.signature_type_name is not None
                    else f"Set {SIGNATURE_TYPE_ENV} before authenticated commands."
                ),
                details={
                    "signature_type": auth.signature_type_name,
                    "signature_type_code": auth.signature_type,
                },
            ),
            SetupGuideCheckpoint(
                section="funder",
                status=(
                    "ready"
                    if auth.signature_type in (None, 0) or auth.funder_address is not None
                    else "blocked"
                ),
                message=(
                    "EOA signature type does not require a separate funder."
                    if auth.signature_type in (None, 0)
                    else (
                        f"Funder address resolved to {auth.funder_address}."
                        if auth.funder_address is not None
                        else f"Set {FUNDER_ENV} for non-EOA signature types."
                    )
                ),
                details={"funder_address": auth.funder_address},
            ),
            SetupGuideCheckpoint(
                section="geoblock",
                status=(
                    "ready"
                    if doctor.geoblock.checked and doctor.geoblock.blocked is False
                    else "blocked"
                    if doctor.geoblock.blocked is True
                    else "pending"
                ),
                message=(
                    doctor.geoblock.message
                    or "Run the official geoblock check before live actions."
                ),
                details={
                    "checked": doctor.geoblock.checked,
                    "blocked": doctor.geoblock.blocked,
                    "country": doctor.geoblock.country,
                    "region": doctor.geoblock.region,
                },
            ),
        ]
        checkpoints.append(self._balances_checkpoint(auth))
        checkpoints.append(self._allowances_checkpoint(auth))
        return checkpoints

    def _balances_checkpoint(self, auth: AuthContext) -> SetupGuideCheckpoint:
        if not auth.api_key_derivation_possible:
            return SetupGuideCheckpoint(
                section="balances",
                status="blocked",
                message="Complete auth configuration before checking balances.",
            )
        try:
            response = self.balances()
        except (AuthClientError, AuthValidationError) as exc:
            return SetupGuideCheckpoint(
                section="balances",
                status="pending",
                message=str(exc),
            )
        return SetupGuideCheckpoint(
            section="balances",
            status="ready",
            message="Authenticated balance lookup completed.",
            details={
                "asset_type": response.balance_view.asset_type,
                "balance": response.balance_view.balance,
                "allowance": response.balance_view.allowance,
                "signature_type": response.balance_view.signature_type,
            },
        )

    def _allowances_checkpoint(self, auth: AuthContext) -> SetupGuideCheckpoint:
        if not auth.api_key_derivation_possible:
            return SetupGuideCheckpoint(
                section="allowances",
                status="blocked",
                message="Complete auth configuration before checking allowances.",
            )
        try:
            response = self.allowances()
        except (AuthClientError, AuthValidationError) as exc:
            return SetupGuideCheckpoint(
                section="allowances",
                status="pending",
                message=str(exc),
            )
        return SetupGuideCheckpoint(
            section="allowances",
            status="ready",
            message="Authenticated allowance lookup completed.",
            details={
                "asset_type": response.allowance_view.asset_type,
                "balance": response.allowance_view.balance,
                "allowance": response.allowance_view.allowance,
                "signature_type": response.allowance_view.signature_type,
            },
        )

    def _build_next_steps(self, *, doctor: SetupDoctorResponse) -> list[str]:
        steps = [
            "pm auth show --json",
            "pm setup doctor --json",
        ]
        if doctor.ready:
            steps.extend(
                [
                    "pm approve check --json",
                    (
                        "pm exec dry-run --market <market-slug-or-condition-id> "
                        "--outcome yes --side buy --price <p> --size <n> --json"
                    ),
                ]
            )
            return steps

        steps.append(
            "Set the required environment variables, then re-run pm setup doctor --json."
        )
        return steps


def _parse_signature_type(value: str) -> tuple[int, str]:
    normalized = value.strip().upper()
    if normalized not in _SIGNATURE_TYPES:
        supported = ", ".join(["0", "1", "2", "EOA", "POLY_PROXY", "POLY_GNOSIS_SAFE"])
        raise ValueError(f"{SIGNATURE_TYPE_ENV} must be one of: {supported}.")
    return _SIGNATURE_TYPES[normalized]


def _normalize_balance_allowance_view(
    payload: dict[str, Any],
    *,
    signature_type: int,
    asset_type: str,
) -> BalanceAllowanceView:
    token_id = _string_or_none(payload.get("token_id")) or _string_or_none(payload.get("tokenId"))
    balance = _string_or_none(payload.get("balance"))
    allowance = _string_or_none(payload.get("allowance"))
    if balance is None and "balance" in payload:
        balance = str(payload["balance"])
    if allowance is None and "allowance" in payload:
        allowance = str(payload["allowance"])
    return BalanceAllowanceView(
        asset_type=asset_type,
        token_id=token_id,
        signature_type=signature_type,
        balance=balance,
        allowance=allowance,
    )


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _looks_like_address(value: str) -> bool:
    if len(value) != 42 or not value.startswith("0x"):
        return False
    try:
        int(value[2:], 16)
    except ValueError:
        return False
    return True
