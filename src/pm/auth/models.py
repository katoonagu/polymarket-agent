"""Models for authenticated setup, balances, allowances, and dry-run context."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuthSectionCheck(BaseModel):
    """Deterministic setup-doctor or auth status check."""

    section: str
    status: str
    message: str


class AuthSectionError(BaseModel):
    """Partial auth/setup failure detail."""

    section: str
    code: str
    message: str


class AuthContext(BaseModel):
    """Normalized authenticated context derived from environment configuration."""

    signer_address: str | None = None
    funder_address: str | None = None
    signature_type: int | None = None
    signature_type_name: str | None = None
    clob_host: str
    chain_id: int | None = None
    private_key_present: bool
    api_key_derivation_possible: bool


class GeoblockStatus(BaseModel):
    """Normalized geoblock result from the official endpoint."""

    checked: bool = False
    blocked: bool | None = None
    country: str | None = None
    region: str | None = None
    message: str | None = None


class SetupDoctorResponse(BaseModel):
    """Readiness report for authenticated dry-run execution."""

    ready: bool
    auth: AuthContext
    geoblock: GeoblockStatus
    checks: list[AuthSectionCheck] = Field(default_factory=list)
    errors: list[AuthSectionError] = Field(default_factory=list)


class SetupGuideEnvironmentItem(BaseModel):
    """One safe environment/configuration item for the setup guide."""

    name: str
    required: bool
    present: bool
    safe_value: str | None = None
    message: str


class SetupGuideCheckpoint(BaseModel):
    """One guided setup checkpoint."""

    section: str
    status: str
    message: str
    details: dict[str, str | int | bool | None] = Field(default_factory=dict)


class SetupGuideResponse(BaseModel):
    """Guided env-only setup payload."""

    auth: AuthContext
    doctor: SetupDoctorResponse
    environment_items: list[SetupGuideEnvironmentItem] = Field(default_factory=list)
    checkpoints: list[SetupGuideCheckpoint] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class SetupWizardResponse(SetupGuideResponse):
    """Interactive or non-interactive setup-wizard payload."""

    interactive: bool
    has_private_key: bool
    private_key_source: str
    session_only_supported: bool = True
    session_only_used: bool = False
    secret_policy: str = "env_only_default_session_only_wizard_never_plaintext_config"


class AuthShowResponse(BaseModel):
    """Current authenticated environment context."""

    auth: AuthContext
    errors: list[AuthSectionError] = Field(default_factory=list)


class DerivedApiCredentials(BaseModel):
    """Ephemeral L2 API credentials derived through the official client."""

    api_key: str
    api_secret: str
    api_passphrase: str


class AuthDeriveApiKeyResponse(BaseModel):
    """Derived API credential response."""

    auth: AuthContext
    api_credentials: DerivedApiCredentials


class BalanceAllowanceView(BaseModel):
    """Normalized balance and allowance view for the authenticated account."""

    asset_type: str
    token_id: str | None = None
    signature_type: int
    balance: str | None = None
    allowance: str | None = None


class AuthBalancesResponse(BaseModel):
    """Authenticated balance response."""

    auth: AuthContext
    balance_view: BalanceAllowanceView


class AuthAllowancesResponse(BaseModel):
    """Authenticated allowance response."""

    auth: AuthContext
    allowance_view: BalanceAllowanceView
