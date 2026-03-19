"""Normalized models for Arkham intelligence enrichment."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.wallet.models import TrackedWallet


class ArkhamSectionError(BaseModel):
    """Structured Arkham partial error."""

    section: str
    code: str
    message: str


class ArkhamSourceAttribution(BaseModel):
    """Source attribution for one Arkham-backed section."""

    provider: str = "arkham"
    endpoint: str
    retrieved_at: str


class ArkhamLabelSummary(BaseModel):
    """Compact Arkham label summary."""

    name: str
    address: str | None = None
    chain_type: str | None = None
    note: str | None = None


class ArkhamEntitySummary(BaseModel):
    """Compact Arkham entity summary."""

    entity_id: str
    name: str
    entity_type: str | None = None
    note: str | None = None
    service: bool | None = None
    website: str | None = None
    twitter: str | None = None
    tags: list[str] = Field(default_factory=list)


class ArkhamCounterpartySummary(BaseModel):
    """Compact Arkham counterparty summary."""

    counterparty_address: str
    flow: str | None = None
    usd: str | None = None
    transaction_count: int | None = None
    chains: list[str] = Field(default_factory=list)
    entity: ArkhamEntitySummary | None = None
    label: ArkhamLabelSummary | None = None
    tags: list[str] = Field(default_factory=list)


class ArkhamEnrichmentRecord(BaseModel):
    """Latest cached Arkham enrichment for one wallet address."""

    address: str
    chain: str | None = None
    confidence_classification: str
    verified_entity: ArkhamEntitySummary | None = None
    predicted_entity: ArkhamEntitySummary | None = None
    user_entity: ArkhamEntitySummary | None = None
    verified_label: ArkhamLabelSummary | None = None
    user_label: ArkhamLabelSummary | None = None
    populated_tags: list[str] = Field(default_factory=list)
    cluster_ids: list[str] = Field(default_factory=list)
    contract: bool | None = None
    service: bool | None = None
    program: bool | None = None
    is_user_address: bool | None = None
    deposit_service_id: str | None = None
    recent_enriched_at: str
    source_attributions: list[ArkhamSourceAttribution] = Field(default_factory=list)
    errors: list[ArkhamSectionError] = Field(default_factory=list)


class ArkhamEnrichmentsFile(BaseModel):
    """On-disk Arkham enrichment cache."""

    version: int = 1
    enrichments: list[ArkhamEnrichmentRecord] = Field(default_factory=list)


class ArkhamStatusResponse(BaseModel):
    """Arkham readiness and cache status payload."""

    configured: bool
    ready: bool
    env_source: str | None = None
    api_reachable: bool | None = None
    chains_count: int | None = None
    tracked_wallet_count: int = 0
    cached_enrichment_count: int = 0
    latest_enrichment_at: str | None = None
    next_steps: list[str] = Field(default_factory=list)
    errors: list[ArkhamSectionError] = Field(default_factory=list)


class ArkhamEnrichResponse(BaseModel):
    """Single-address enrichment response."""

    configured: bool
    ready: bool
    address: str
    record: ArkhamEnrichmentRecord | None = None
    next_steps: list[str] = Field(default_factory=list)
    errors: list[ArkhamSectionError] = Field(default_factory=list)


class ArkhamDossierResponse(BaseModel):
    """Rich Arkham dossier response for one address."""

    configured: bool
    ready: bool
    address: str
    enrichment: ArkhamEnrichmentRecord | None = None
    entity: ArkhamEntitySummary | None = None
    counterparties: list[ArkhamCounterpartySummary] = Field(default_factory=list)
    counterparties_total: int = 0
    next_steps: list[str] = Field(default_factory=list)
    errors: list[ArkhamSectionError] = Field(default_factory=list)


class ArkhamSyncTrackedItem(BaseModel):
    """Per-wallet tracked sync result."""

    address: str
    status: str
    record: ArkhamEnrichmentRecord | None = None
    errors: list[ArkhamSectionError] = Field(default_factory=list)


class ArkhamSyncTrackedResponse(BaseModel):
    """Batch tracked-wallet Arkham sync response."""

    configured: bool
    ready: bool
    limit: int
    tracked_total: int = 0
    processed_count: int = 0
    enriched_count: int = 0
    partial_error_count: int = 0
    items: list[ArkhamSyncTrackedItem] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    errors: list[ArkhamSectionError] = Field(default_factory=list)


class ArkhamSuspiciousReason(BaseModel):
    """Explainable suspicious-wallet heuristic reason."""

    section: str
    status: str
    message: str


class ArkhamLocalWalletContext(BaseModel):
    """Local wallet-pipeline context used for suspicious heuristics."""

    events_count: int = 0
    signals_count: int = 0
    shadow_runs_count: int = 0
    would_copy_count: int = 0
    distinct_markets_count: int = 0
    dominant_market_condition_id: str | None = None
    dominant_market_count: int = 0


class ArkhamSuspiciousWalletItem(BaseModel):
    """Ranked suspicious-wallet watch candidate."""

    rank: int
    tracked_wallet: TrackedWallet
    enrichment: ArkhamEnrichmentRecord | None = None
    watch_score: float
    watch_candidate: bool
    flags: list[str] = Field(default_factory=list)
    local_context: ArkhamLocalWalletContext = Field(default_factory=ArkhamLocalWalletContext)
    reasons: list[ArkhamSuspiciousReason] = Field(default_factory=list)


class ArkhamSuspiciousTrackedResponse(BaseModel):
    """Ranked suspicious tracked-wallet report."""

    cache_only: bool = True
    items: list[ArkhamSuspiciousWalletItem] = Field(default_factory=list)
    total: int = 0
    tracked_total: int = 0
    missing_enrichment_count: int = 0
    next_steps: list[str] = Field(default_factory=list)
