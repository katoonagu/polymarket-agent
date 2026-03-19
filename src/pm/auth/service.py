"""Authenticated setup and account inspection service for non-live dry-run flows."""

from __future__ import annotations

import os
from collections.abc import Mapping
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

from pm.auth.exceptions import (
    AuthClientError,
    AuthValidationError,
)
from pm.auth.models import (
    AuthAllowancesResponse,
    AuthBalancesResponse,
    AuthContext,
    AuthDeriveApiKeyResponse,
    AuthProfileClearResponse,
    AuthProfileDoctorResponse,
    AuthProfileFromEnvResponse,
    AuthProfileInitResponse,
    AuthProfileShowResponse,
    AuthSectionCheck,
    AuthSectionError,
    AuthShowResponse,
    BalanceAllowanceView,
    DerivedApiCredentials,
    GeoblockStatus,
    OperatorProfile,
    SetupDoctorResponse,
    SetupGuideCheckpoint,
    SetupGuideEnvironmentItem,
    SetupGuideResponse,
    SetupWizardResponse,
)
from pm.auth.state import OperatorProfileStateService

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


@dataclass(slots=True, frozen=True)
class ResolvedAccountContext:
    """Resolved non-secret account fields after applying precedence rules."""

    signer_address: str | None
    funder_address: str | None
    signature_type: int | None
    signature_type_name: str | None
    clob_host: str
    chain_id: int | None
    profile: OperatorProfile | None


class AuthService:
    """Authenticated setup and non-mutating account inspection service."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        sdk_client_cls: type[SDKClobClient] = SDKClobClient,
        env_overrides: Mapping[str, str | None] | None = None,
        account_overrides: Mapping[str, str | int | None] | None = None,
        profile_state: OperatorProfileStateService | None = None,
    ) -> None:
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT)
        self._sdk_client_cls = sdk_client_cls
        self._env_overrides = dict(env_overrides or {})
        self._account_overrides = dict(account_overrides or {})
        self._profile_state = profile_state or OperatorProfileStateService()

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

    def wizard(
        self,
        *,
        interactive: bool,
        private_key_source: str,
        session_only_used: bool = False,
    ) -> SetupWizardResponse:
        """Return the current setup wizard state without persisting secrets."""
        guide = self.guide()
        has_private_key = guide.auth.private_key_present
        resolved_source = private_key_source if has_private_key else "missing"
        return SetupWizardResponse(
            auth=guide.auth,
            doctor=guide.doctor,
            environment_items=guide.environment_items,
            checkpoints=guide.checkpoints,
            next_steps=guide.next_steps,
            interactive=interactive,
            has_private_key=has_private_key,
            private_key_source=resolved_source,
            session_only_supported=True,
            session_only_used=session_only_used,
        )

    def profile_show(self) -> AuthProfileShowResponse:
        """Return the current non-secret operator profile, if one exists."""
        profile = self._profile_state.load_profile()
        return AuthProfileShowResponse(present=profile is not None, profile=profile)

    def profile_init(
        self,
        *,
        signature_type: int,
        signer: str,
        funder: str,
        chain_id: int | None = None,
        label: str | None = None,
    ) -> AuthProfileInitResponse:
        """Persist one explicit non-secret operator profile."""
        signature_type_name = _signature_name_from_int(signature_type)
        if signature_type_name is None:
            raise AuthValidationError("Signature type must be one of: 0, 1, 2.")

        signer_address = _validated_profile_address("signer", signer)
        funder_address = _validated_profile_address("funder", funder)
        resolved_chain_id = chain_id if chain_id is not None else self._resolved_default_chain_id()
        if resolved_chain_id <= 0:
            raise AuthValidationError("Chain id must be greater than zero.")

        profile = OperatorProfile(
            signer_address=signer_address,
            funder_address=funder_address,
            signature_type=signature_type,
            chain_id=resolved_chain_id,
            account_label=(label or "").strip() or None,
            source="manual",
        )
        self._profile_state.save_profile(profile)
        return AuthProfileInitResponse(profile=profile)

    def profile_from_env(self) -> AuthProfileFromEnvResponse:
        """Persist a non-secret operator profile derived from the current env config."""
        settings = self.require_valid_config(include_profile=False)
        auth = self._context_from_settings(settings)
        existing_profile = self._profile_state.load_profile()
        profile = OperatorProfile(
            signer_address=auth.signer_address or "",
            funder_address=auth.funder_address,
            signature_type=auth.signature_type or settings.signature_type,
            chain_id=auth.chain_id or settings.chain_id,
            account_label=existing_profile.account_label if existing_profile is not None else None,
            source="env",
        )
        self._profile_state.save_profile(profile)
        return AuthProfileFromEnvResponse(profile=profile)

    def profile_doctor(self) -> AuthProfileDoctorResponse:
        """Return a compact local identity and readiness summary for account resolution."""
        auth_result = self.show()
        auth = auth_result.auth
        profile = self._profile_state.load_profile()

        auth_env_ready = True
        try:
            self.require_valid_config()
        except AuthValidationError:
            auth_env_ready = False

        checks = [
            AuthSectionCheck(
                section="profile",
                status="pass" if profile is not None else "warn",
                message=(
                    "Non-secret operator profile is present."
                    if profile is not None
                    else "No operator profile is persisted locally."
                ),
            ),
            AuthSectionCheck(
                section="signer",
                status="pass" if auth.signer_address is not None else "fail",
                message=(
                    f"Signer resolves to {auth.signer_address}."
                    if auth.signer_address is not None
                    else "Signer address could not be resolved."
                ),
            ),
            AuthSectionCheck(
                section="funder",
                status=(
                    "pass"
                    if auth.signature_type in (None, 0) or auth.funder_address is not None
                    else "fail"
                ),
                message=(
                    "EOA signature type does not require a separate funder."
                    if auth.signature_type in (None, 0)
                    else f"Funder resolves to {auth.funder_address}."
                    if auth.funder_address is not None
                    else "Funder address is required for the resolved non-EOA signature type."
                ),
            ),
            AuthSectionCheck(
                section="signature_type",
                status="pass" if auth.signature_type is not None else "fail",
                message=(
                    "Signature type resolves to "
                    f"{auth.signature_type_name} ({auth.signature_type})."
                    if auth.signature_type is not None
                    else "Signature type could not be resolved."
                ),
            ),
            AuthSectionCheck(
                section="chain_id",
                status="pass" if auth.chain_id is not None else "fail",
                message=(
                    f"Chain id resolves to {auth.chain_id}."
                    if auth.chain_id is not None
                    else "Chain id could not be resolved."
                ),
            ),
            AuthSectionCheck(
                section="auth_env",
                status="pass" if auth_env_ready else "warn",
                message=(
                    "Authenticated env readiness is complete."
                    if auth_env_ready
                    else (
                        "Authenticated env readiness is incomplete; live auth still "
                        "requires a private key."
                    )
                ),
            ),
        ]

        ready = (
            auth.signer_address is not None
            and auth.signature_type is not None
            and auth.chain_id is not None
            and (auth.signature_type == 0 or auth.funder_address is not None)
            and auth_env_ready
        )
        return AuthProfileDoctorResponse(
            ready=ready,
            present=profile is not None,
            profile=profile,
            auth=auth,
            auth_env_ready=auth_env_ready,
            checks=checks,
            errors=auth_result.errors,
            geoblock_reminder=(
                "Live approval and execution commands still run the official geoblock "
                "check at mutation time."
            ),
        )

    def profile_clear(self) -> AuthProfileClearResponse:
        """Remove the persisted non-secret operator profile."""
        cleared = self._profile_state.clear_profile()
        return AuthProfileClearResponse(cleared=cleared)

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

    def require_valid_config(self, *, include_profile: bool = True) -> AuthSettings:
        """Require a complete valid authenticated environment configuration."""
        private_key = (self._env(PRIVATE_KEY_ENV) or "").strip()
        if not private_key:
            raise AuthValidationError(f"{PRIVATE_KEY_ENV} is required for authenticated commands.")

        try:
            Account.from_key(private_key)
        except Exception as exc:
            raise AuthValidationError(
                f"{PRIVATE_KEY_ENV} could not be parsed as a private key."
            ) from exc

        resolved = self._resolve_account_context(
            require_private_key=True,
            strict_signer_match=True,
            include_profile=include_profile,
        )
        if resolved.signature_type is None or resolved.signature_type_name is None:
            raise AuthValidationError(
                f"{SIGNATURE_TYPE_ENV} is required for authenticated commands."
            )
        if resolved.signature_type != 0 and not resolved.funder_address:
            raise AuthValidationError(
                f"{FUNDER_ENV} is required when signature type is "
                f"{resolved.signature_type_name}."
            )
        if resolved.chain_id is None:
            raise AuthValidationError(
                f"{CHAIN_ID_ENV} is required when {CLOB_HOST_ENV} overrides the default host."
            )

        return AuthSettings(
            private_key=private_key,
            signature_type=resolved.signature_type,
            signature_type_name=resolved.signature_type_name,
            funder_address=resolved.funder_address,
            clob_host=resolved.clob_host,
            chain_id=resolved.chain_id,
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

    def _resolve_account_context(
        self,
        *,
        require_private_key: bool,
        strict_signer_match: bool,
        include_profile: bool = True,
        errors: list[AuthSectionError] | None = None,
    ) -> ResolvedAccountContext:
        collected_errors = errors if errors is not None else []
        profile = self._profile_state.load_profile() if include_profile else None
        clob_host = (
            (self._env(CLOB_HOST_ENV) or "").strip()
            or (self._env(LEGACY_CLOB_HOST_ENV) or "").strip()
            or DEFAULT_CLOB_HOST
        ).rstrip("/")

        signature_type, signature_type_name = self._resolve_signature_type(
            profile=profile,
            errors=collected_errors,
            require_private_key=require_private_key,
            strict=strict_signer_match,
        )
        funder_address = self._resolve_address_field(
            field_name="funder",
            override_value=self._account_overrides.get("funder_address"),
            profile_value=profile.funder_address if profile is not None else None,
            env_value=(self._env(FUNDER_ENV) or "").strip() or None,
            errors=collected_errors,
            strict=strict_signer_match,
        )
        chain_id = self._resolve_chain_id(
            profile=profile,
            clob_host=clob_host,
            errors=collected_errors,
            require_private_key=require_private_key,
            strict=strict_signer_match,
        )
        requested_signer = self._resolve_address_field(
            field_name="signer",
            override_value=self._account_overrides.get("signer_address"),
            profile_value=profile.signer_address if profile is not None else None,
            env_value=None,
            errors=collected_errors,
            strict=strict_signer_match,
        )

        private_key = (self._env(PRIVATE_KEY_ENV) or "").strip()
        signer_from_private_key: str | None = None
        if private_key:
            try:
                signer_from_private_key = Account.from_key(private_key).address
            except Exception:
                signer_from_private_key = None

        if (
            requested_signer is not None
            and signer_from_private_key is not None
            and requested_signer.lower() != signer_from_private_key.lower()
        ):
            message = (
                "Resolved signer address does not match the current private-key-derived signer."
            )
            if strict_signer_match:
                raise AuthValidationError(message)
            collected_errors.append(
                AuthSectionError(
                    section="signer",
                    code="invalid_argument",
                    message=message,
                )
            )

        if signature_type is not None and signature_type != 0 and funder_address is None:
            collected_errors.append(
                AuthSectionError(
                    section="funder",
                    code="invalid_argument",
                    message=f"{FUNDER_ENV} is required for non-EOA signature types.",
                )
            )

        return ResolvedAccountContext(
            signer_address=signer_from_private_key or requested_signer,
            funder_address=funder_address,
            signature_type=signature_type,
            signature_type_name=signature_type_name,
            clob_host=clob_host,
            chain_id=chain_id,
            profile=profile,
        )

    def _build_context(
        self,
        *,
        errors: list[AuthSectionError],
        require_private_key: bool,
    ) -> AuthContext:
        private_key = (self._env(PRIVATE_KEY_ENV) or "").strip()
        resolved = self._resolve_account_context(
            require_private_key=require_private_key,
            strict_signer_match=False,
            errors=errors,
        )

        signer_address = resolved.signer_address
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

        api_key_derivation_possible = (
            signer_address is not None
            and resolved.signature_type is not None
            and (resolved.signature_type == 0 or resolved.funder_address is not None)
            and resolved.chain_id is not None
            and not _has_section_error(errors, "signer")
        )
        return AuthContext(
            signer_address=signer_address,
            funder_address=resolved.funder_address,
            signature_type=resolved.signature_type,
            signature_type_name=resolved.signature_type_name,
            clob_host=resolved.clob_host,
            chain_id=resolved.chain_id,
            private_key_present=bool(private_key),
            api_key_derivation_possible=api_key_derivation_possible,
        )

    def _resolve_signature_type(
        self,
        *,
        profile: OperatorProfile | None,
        errors: list[AuthSectionError],
        require_private_key: bool,
        strict: bool,
    ) -> tuple[int | None, str | None]:
        raw_override = self._account_overrides.get("signature_type")
        if raw_override is not None:
            raw_value = str(raw_override).strip()
        elif profile is not None:
            raw_value = str(profile.signature_type)
        else:
            raw_value = (self._env(SIGNATURE_TYPE_ENV) or "").strip()

        if not raw_value:
            if require_private_key:
                message = f"{SIGNATURE_TYPE_ENV} is required for authenticated commands."
                if strict:
                    raise AuthValidationError(message)
                errors.append(
                    AuthSectionError(
                        section="signature_type",
                        code="invalid_argument",
                        message=message,
                    )
                )
            return None, None

        try:
            return _parse_signature_type(raw_value)
        except ValueError as exc:
            if strict:
                raise AuthValidationError(str(exc)) from exc
            errors.append(
                AuthSectionError(
                    section="signature_type",
                    code="invalid_argument",
                    message=str(exc),
                )
            )
            return None, None

    def _resolve_chain_id(
        self,
        *,
        profile: OperatorProfile | None,
        clob_host: str,
        errors: list[AuthSectionError],
        require_private_key: bool,
        strict: bool,
    ) -> int | None:
        raw_override = self._account_overrides.get("chain_id")
        raw_env = (self._env(CHAIN_ID_ENV) or "").strip()
        if raw_override is not None:
            raw_value = str(raw_override).strip()
        elif profile is not None:
            raw_value = str(profile.chain_id)
        else:
            raw_value = raw_env

        if not raw_value:
            if clob_host == DEFAULT_CLOB_HOST:
                return DEFAULT_CHAIN_ID
            if require_private_key:
                message = (
                    f"{CHAIN_ID_ENV} is required when {CLOB_HOST_ENV} overrides the default host."
                )
                if strict:
                    raise AuthValidationError(message)
                errors.append(
                    AuthSectionError(
                        section="chain_id",
                        code="invalid_argument",
                        message=message,
                    )
                )
            return None

        try:
            return int(raw_value)
        except ValueError as exc:
            message = f"{CHAIN_ID_ENV} must be an integer."
            if strict:
                raise AuthValidationError(message) from exc
            errors.append(
                AuthSectionError(
                    section="chain_id",
                    code="invalid_argument",
                    message=message,
                )
            )
            return None

    def _resolve_address_field(
        self,
        *,
        field_name: str,
        override_value: str | int | None,
        profile_value: str | None,
        env_value: str | None,
        errors: list[AuthSectionError],
        strict: bool,
    ) -> str | None:
        raw_value: str | None
        if override_value is not None:
            raw_value = str(override_value).strip() or None
        elif profile_value is not None:
            raw_value = profile_value.strip() or None
        else:
            raw_value = env_value

        if raw_value is None:
            return None
        if _looks_like_address(raw_value):
            return raw_value

        message = (
            f"{FUNDER_ENV} must use 0x followed by 40 hex characters."
            if field_name == "funder"
            else "Signer address must use 0x followed by 40 hex characters."
        )
        if strict:
            raise AuthValidationError(message)
        errors.append(
            AuthSectionError(
                section=field_name,
                code="invalid_argument",
                message=message,
            )
        )
        return None

    def _resolved_default_chain_id(self) -> int:
        clob_host = (
            (self._env(CLOB_HOST_ENV) or "").strip()
            or (self._env(LEGACY_CLOB_HOST_ENV) or "").strip()
            or DEFAULT_CLOB_HOST
        ).rstrip("/")
        resolved = self._resolve_chain_id(
            profile=None,
            clob_host=clob_host,
            errors=[],
            require_private_key=False,
            strict=False,
        )
        if resolved is None:
            if clob_host != DEFAULT_CLOB_HOST:
                raise AuthValidationError(
                    f"{CHAIN_ID_ENV} is required when {CLOB_HOST_ENV} overrides the default host."
                )
            return DEFAULT_CHAIN_ID
        return resolved

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
        signature_raw = (self._env(SIGNATURE_TYPE_ENV) or "").strip()
        funder_raw = (self._env(FUNDER_ENV) or "").strip()
        custom_host = bool(
            (self._env(CLOB_HOST_ENV) or "").strip()
            or (self._env(LEGACY_CLOB_HOST_ENV) or "").strip()
        )
        chain_raw = (self._env(CHAIN_ID_ENV) or "").strip()
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

    def _env(self, name: str) -> str | None:
        if name in self._env_overrides:
            return self._env_overrides[name]
        return os.getenv(name)


def resolve_operator_account_address(auth: AuthContext) -> str:
    """Resolve the operator account address from normalized auth context."""
    funder_address = _validated_resolved_address(auth.funder_address)
    if funder_address is not None:
        return funder_address

    signer_address = _validated_resolved_address(auth.signer_address)
    if signer_address is not None:
        return signer_address

    raise AuthValidationError(
        "No operator account address could be resolved. Run `pm auth show --json` or "
        "`pm setup guide --json` to inspect authenticated context."
    )


def _validated_resolved_address(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    if _looks_like_address(value):
        return value
    raise AuthValidationError("Resolved account address must use 0x followed by 40 hex characters.")


def _validated_profile_address(field_name: str, value: str) -> str:
    normalized = value.strip()
    if _looks_like_address(normalized):
        return normalized
    if field_name == "funder":
        raise AuthValidationError("Funder address must use 0x followed by 40 hex characters.")
    raise AuthValidationError("Signer address must use 0x followed by 40 hex characters.")


def _signature_name_from_int(value: int) -> str | None:
    for signature_value, signature_name in _SIGNATURE_TYPES.values():
        if signature_value == value:
            return signature_name
    return None


def _has_section_error(errors: list[AuthSectionError], section: str) -> bool:
    return any(item.section == section for item in errors)


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
