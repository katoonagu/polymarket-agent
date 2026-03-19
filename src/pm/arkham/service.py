"""Arkham intelligence enrichment and suspicious-wallet service layer."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from pm.arkham.client import ArkhamClient
from pm.arkham.exceptions import ArkhamClientError, ArkhamNotFoundError, ArkhamValidationError
from pm.arkham.models import (
    ArkhamCounterpartySummary,
    ArkhamDossierResponse,
    ArkhamEnrichmentRecord,
    ArkhamEnrichResponse,
    ArkhamEntitySummary,
    ArkhamLabelSummary,
    ArkhamLocalWalletContext,
    ArkhamSectionError,
    ArkhamSourceAttribution,
    ArkhamStatusResponse,
    ArkhamSuspiciousReason,
    ArkhamSuspiciousTrackedResponse,
    ArkhamSuspiciousWalletItem,
    ArkhamSyncTrackedItem,
    ArkhamSyncTrackedResponse,
)
from pm.arkham.state import ArkhamStateService
from pm.wallet import (
    TrackedWallet,
    WalletPipelineStateService,
    WalletRegistryService,
    normalize_wallet_address,
)

ARKHAM_API_KEY_ENV = "ARKHAM_API_KEY"
LEGACY_ARKHAM_API_KEY_ENV = "PM_ARKHAM_API_KEY"
COUNTERPARTY_DEFAULT_LIMIT = 10
SYNC_DEFAULT_LIMIT = 20
SUSPICIOUS_DEFAULT_LIMIT = 20
_RISK_LEXICON = {
    "sanctions_or_blocklist": ("ofac", "sanction", "blocklist", "blacklist", "banned"),
    "exploit_or_hack": ("hack", "hacker", "exploit", "drainer", "stolen"),
    "fraud_or_scam": ("fraud", "scam", "phishing", "rug", "ponzi"),
    "mixer_or_obfuscation": ("mixer", "mixing", "tornado", "obfuscation", "launder"),
    "high_risk_service": ("ransomware", "darknet", "malware", "illicit"),
}


@dataclass(slots=True, frozen=True)
class ArkhamSettings:
    """Resolved Arkham API settings."""

    api_key: str
    env_source: str


class ArkhamService:
    """High-level Arkham enrichment and suspicious-wallet service."""

    def __init__(
        self,
        *,
        state: ArkhamStateService | None = None,
        wallet_registry: WalletRegistryService | None = None,
        wallet_state: WalletPipelineStateService | None = None,
        http_client: httpx.Client | None = None,
        env_overrides: Mapping[str, str | None] | None = None,
    ) -> None:
        self._state = state or ArkhamStateService()
        self._wallet_registry = wallet_registry or WalletRegistryService()
        self._wallet_state = wallet_state or WalletPipelineStateService()
        self._http_client = http_client
        self._env_overrides = dict(env_overrides or {})

    def status(self) -> ArkhamStatusResponse:
        """Return Arkham readiness and cache status."""
        tracked_wallets = self._wallet_registry.list_wallets()
        cached = self._state.list_enrichments()
        latest = cached[-1].recent_enriched_at if cached else None
        settings = self._load_settings()
        errors: list[ArkhamSectionError] = []
        ready = False
        api_reachable: bool | None = None
        chains_count: int | None = None

        if settings is not None:
            try:
                with self._build_client(settings) as client:
                    chains = client.get_chains()
                api_reachable = True
                chains_count = _collection_length(chains)
                ready = True
            except ArkhamClientError as exc:
                api_reachable = False
                errors.append(
                    ArkhamSectionError(
                        section="status",
                        code="request_failed",
                        message=str(exc),
                    )
                )

        return ArkhamStatusResponse(
            configured=settings is not None,
            ready=ready,
            env_source=settings.env_source if settings is not None else None,
            api_reachable=api_reachable,
            chains_count=chains_count,
            tracked_wallet_count=len(tracked_wallets),
            cached_enrichment_count=len(cached),
            latest_enrichment_at=latest,
            next_steps=self._next_steps(configured=settings is not None),
            errors=errors,
        )

    def enrich(self, address: str) -> ArkhamEnrichResponse:
        """Enrich one address and persist the latest record."""
        normalized = _normalize_address(address)
        settings = self._load_settings()
        if settings is None:
            return ArkhamEnrichResponse(
                configured=False,
                ready=False,
                address=normalized,
                record=self._state.get_enrichment(normalized),
                next_steps=self._next_steps(configured=False),
            )

        record, response_errors = self._fetch_enrichment_record(normalized, settings=settings)
        persisted = self._state.upsert_enrichment(record)
        return ArkhamEnrichResponse(
            configured=True,
            ready=True,
            address=normalized,
            record=persisted,
            next_steps=self._next_steps(configured=True),
            errors=response_errors,
        )

    def dossier(self, address: str) -> ArkhamDossierResponse:
        """Build a dossier from enrichment plus best-effort add-ons."""
        normalized = _normalize_address(address)
        settings = self._load_settings()
        cached = self._state.get_enrichment(normalized)
        if settings is None:
            return ArkhamDossierResponse(
                configured=False,
                ready=False,
                address=normalized,
                enrichment=cached,
                next_steps=self._next_steps(configured=False),
            )

        enrichment_record, response_errors = self._fetch_enrichment_record(
            normalized,
            settings=settings,
        )
        self._state.upsert_enrichment(enrichment_record)
        entity_summary: ArkhamEntitySummary | None = None
        counterparties: list[ArkhamCounterpartySummary] = []
        entity_id = _preferred_entity_id(enrichment_record)

        with self._build_client(settings) as client:
            if entity_id is not None:
                try:
                    entity_payload = client.get_entity_intelligence(entity_id)
                    entity_summary = _entity_from_payload(entity_payload)
                    if entity_summary is not None:
                        enrichment_record.source_attributions.append(
                            _source("GET /intelligence/entity/{entity}")
                        )
                except (ArkhamClientError, ArkhamNotFoundError) as exc:
                    response_errors.append(
                        ArkhamSectionError(
                            section="entity",
                            code=_client_error_code(exc),
                            message=str(exc),
                        )
                    )
            try:
                counterparties_payload = client.get_counterparties(
                    normalized,
                    limit=COUNTERPARTY_DEFAULT_LIMIT,
                )
                counterparties = _counterparties_from_payload(counterparties_payload)
                if counterparties:
                    enrichment_record.source_attributions.append(
                        _source("GET /counterparties/address/{address}")
                    )
            except (ArkhamClientError, ArkhamNotFoundError) as exc:
                response_errors.append(
                    ArkhamSectionError(
                        section="counterparties",
                        code=_client_error_code(exc),
                        message=str(exc),
                    )
                )

        return ArkhamDossierResponse(
            configured=True,
            ready=True,
            address=normalized,
            enrichment=enrichment_record,
            entity=entity_summary,
            counterparties=counterparties,
            counterparties_total=len(counterparties),
            next_steps=self._next_steps(configured=True),
            errors=response_errors,
        )

    def sync_tracked(self, *, limit: int = SYNC_DEFAULT_LIMIT) -> ArkhamSyncTrackedResponse:
        """Enrich tracked wallets in registry order."""
        if limit < 1:
            raise ArkhamValidationError("limit must be at least 1")

        tracked_wallets = self._wallet_registry.list_wallets()
        settings = self._load_settings()
        if settings is None:
            return ArkhamSyncTrackedResponse(
                configured=False,
                ready=False,
                limit=limit,
                tracked_total=len(tracked_wallets),
                next_steps=self._next_steps(configured=False),
            )

        processed = tracked_wallets[:limit]
        items: list[ArkhamSyncTrackedItem] = []
        partial_error_count = 0
        enriched_count = 0
        for wallet in processed:
            record, response_errors = self._fetch_enrichment_record(
                wallet.address,
                settings=settings,
            )
            self._state.upsert_enrichment(record)
            status = "partial" if response_errors else "enriched"
            if response_errors:
                partial_error_count += 1
            else:
                enriched_count += 1
            items.append(
                ArkhamSyncTrackedItem(
                    address=wallet.address,
                    status=status,
                    record=record,
                    errors=response_errors,
                )
            )

        return ArkhamSyncTrackedResponse(
            configured=True,
            ready=True,
            limit=limit,
            tracked_total=len(tracked_wallets),
            processed_count=len(processed),
            enriched_count=enriched_count,
            partial_error_count=partial_error_count,
            items=items,
            next_steps=self._next_steps(configured=True),
        )

    def suspicious_tracked(
        self,
        *,
        limit: int = SUSPICIOUS_DEFAULT_LIMIT,
    ) -> ArkhamSuspiciousTrackedResponse:
        """Rank tracked wallets using cached Arkham and local wallet state only."""
        if limit < 1:
            raise ArkhamValidationError("limit must be at least 1")

        tracked_wallets = self._wallet_registry.list_wallets()
        enrichments = self._state.list_enrichments()
        enrichment_map = {record.address: record for record in enrichments}
        shared_clusters = Counter(
            cluster_id
            for record in enrichments
            for cluster_id in record.cluster_ids
            if cluster_id
        )
        shared_entities = Counter(
            entity_id
            for record in enrichments
            for entity_id in _record_entity_ids(record)
            if entity_id
        )

        ranked: list[ArkhamSuspiciousWalletItem] = []
        missing_enrichment_count = 0
        for wallet in tracked_wallets:
            record = enrichment_map.get(wallet.address)
            if record is None:
                missing_enrichment_count += 1
            local_context = self._local_wallet_context(wallet.address)
            ranked.append(
                self._build_suspicious_item(
                    wallet=wallet,
                    record=record,
                    shared_clusters=shared_clusters,
                    shared_entities=shared_entities,
                    local_context=local_context,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.watch_score,
                -_timestamp_key(
                    item.enrichment.recent_enriched_at if item.enrichment is not None else None
                ),
                item.tracked_wallet.address,
            )
        )
        limited = [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(ranked[:limit], start=1)
        ]
        return ArkhamSuspiciousTrackedResponse(
            cache_only=True,
            items=limited,
            total=len(limited),
            tracked_total=len(tracked_wallets),
            missing_enrichment_count=missing_enrichment_count,
            next_steps=["pm arkham sync tracked --limit 20"],
        )

    def _fetch_enrichment_record(
        self,
        address: str,
        *,
        settings: ArkhamSettings,
    ) -> tuple[ArkhamEnrichmentRecord, list[ArkhamSectionError]]:
        errors: list[ArkhamSectionError] = []
        with self._build_client(settings) as client:
            source_attributions: list[ArkhamSourceAttribution] = []
            try:
                enriched_payload = client.get_address_enriched(address)
                source_attributions.append(
                    _source("GET /intelligence/address_enriched/{address}")
                )
                return (
                    _record_from_enriched_payload(
                        address,
                        enriched_payload,
                        source_attributions=source_attributions,
                        errors=errors,
                    ),
                    errors,
                )
            except (ArkhamClientError, ArkhamNotFoundError) as exc:
                errors.append(
                    ArkhamSectionError(
                        section="address_enriched",
                        code=_client_error_code(exc),
                        message=str(exc),
                    )
                )

            base_payload: dict[str, Any] | None = None
            try:
                base_payload = client.get_address_intelligence(address)
                source_attributions.append(_source("GET /intelligence/address/{address}"))
            except (ArkhamClientError, ArkhamNotFoundError) as exc:
                errors.append(
                    ArkhamSectionError(
                        section="address",
                        code=_client_error_code(exc),
                        message=str(exc),
                    )
                )

        if base_payload is None:
            record = ArkhamEnrichmentRecord(
                address=address,
                confidence_classification="unknown",
                recent_enriched_at=_utc_now_iso(),
                source_attributions=source_attributions,
                errors=list(errors),
            )
            return record, errors

        return (
            _record_from_basic_payload(
                address,
                base_payload,
                source_attributions=source_attributions,
                errors=errors,
            ),
            errors,
        )

    def _build_client(self, settings: ArkhamSettings) -> ArkhamClient:
        return ArkhamClient(settings.api_key, http_client=self._http_client)

    def _load_settings(self) -> ArkhamSettings | None:
        primary = self._env(ARKHAM_API_KEY_ENV)
        if primary:
            return ArkhamSettings(api_key=primary, env_source=ARKHAM_API_KEY_ENV)
        fallback = self._env(LEGACY_ARKHAM_API_KEY_ENV)
        if fallback:
            return ArkhamSettings(
                api_key=fallback,
                env_source=LEGACY_ARKHAM_API_KEY_ENV,
            )
        return None

    def _env(self, name: str) -> str | None:
        if name in self._env_overrides:
            return self._env_overrides[name]
        return os.getenv(name)

    def _next_steps(self, *, configured: bool) -> list[str]:
        if configured:
            return [
                "pm arkham sync tracked --limit 20",
                "pm arkham suspicious tracked --limit 20",
            ]
        return [
            f"Set {ARKHAM_API_KEY_ENV} in your environment.",
            "pm arkham status --json",
        ]

    def _local_wallet_context(self, address: str) -> ArkhamLocalWalletContext:
        events = self._wallet_state.list_events(address)
        signals = self._wallet_state.list_signals(address)
        shadow_runs = self._wallet_state.list_shadow_runs(address)
        market_ids = [event.condition_id for event in events if event.condition_id is not None]
        market_ids.extend(
            signal.condition_id for signal in signals if signal.condition_id is not None
        )
        for run in shadow_runs:
            market_ids.extend(
                item.condition_id
                for item in run.candidate_intents
                if item.condition_id is not None
            )
        market_counts = Counter(market_ids)
        dominant_market_condition_id, dominant_market_count = (None, 0)
        if market_counts:
            dominant_market_condition_id, dominant_market_count = sorted(
                market_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[0]

        return ArkhamLocalWalletContext(
            events_count=len(events),
            signals_count=len(signals),
            shadow_runs_count=len(shadow_runs),
            would_copy_count=sum(run.would_copy_count for run in shadow_runs),
            distinct_markets_count=len(market_counts),
            dominant_market_condition_id=dominant_market_condition_id,
            dominant_market_count=dominant_market_count,
        )

    def _build_suspicious_item(
        self,
        *,
        wallet: TrackedWallet,
        record: ArkhamEnrichmentRecord | None,
        shared_clusters: Counter[str],
        shared_entities: Counter[str],
        local_context: ArkhamLocalWalletContext,
    ) -> ArkhamSuspiciousWalletItem:
        score = 0.0
        flags: list[str] = []
        reasons: list[ArkhamSuspiciousReason] = []

        if record is None:
            reasons.append(
                ArkhamSuspiciousReason(
                    section="enrichment",
                    status="info",
                    message="No Arkham enrichment is cached for this tracked wallet yet.",
                )
            )
        else:
            score += {
                "verified": 2.0,
                "predicted": 1.0,
                "user": 0.5,
                "unknown": 0.0,
            }.get(record.confidence_classification, 0.0)
            reasons.append(
                ArkhamSuspiciousReason(
                    section="enrichment",
                    status="info",
                    message=(
                        "Arkham enrichment quality is "
                        f"'{record.confidence_classification}'."
                    ),
                )
            )

            risk_matches = _risk_families(record)
            for family in risk_matches:
                score += 25.0
                flags.append(family)
                reasons.append(
                    ArkhamSuspiciousReason(
                        section="risk_labels",
                        status="flag",
                        message=(
                            "Arkham tags or labels matched the "
                            f"'{family}' watch heuristic."
                        ),
                    )
                )

            shared_cluster_count = sum(
                1 for cluster_id in record.cluster_ids if shared_clusters[cluster_id] > 1
            )
            if shared_cluster_count:
                score += min(shared_cluster_count * 8.0, 24.0)
                flags.append("shared_cluster_ids")
                reasons.append(
                    ArkhamSuspiciousReason(
                        section="cluster_overlap",
                        status="flag",
                        message=(
                            f"Arkham cluster ids overlap with {shared_cluster_count} "
                            "tracked-wallet cluster memberships."
                        ),
                    )
                )

            shared_entity_count = sum(
                1 for entity_id in _record_entity_ids(record) if shared_entities[entity_id] > 1
            )
            if shared_entity_count:
                score += min(shared_entity_count * 6.0, 18.0)
                flags.append("shared_entity_ids")
                reasons.append(
                    ArkhamSuspiciousReason(
                        section="entity_overlap",
                        status="flag",
                        message=(
                            f"Arkham entity attribution overlaps with {shared_entity_count} "
                            "tracked-wallet entity memberships."
                        ),
                    )
                )

        if local_context.events_count >= 10:
            score += 6.0
            reasons.append(
                ArkhamSuspiciousReason(
                    section="activity_context",
                    status="info",
                    message="Local wallet event history is high-volume.",
                )
            )
        elif local_context.events_count >= 3:
            score += 3.0
            reasons.append(
                ArkhamSuspiciousReason(
                    section="activity_context",
                    status="info",
                    message="Local wallet event history shows repeated activity.",
                )
            )

        if local_context.signals_count >= 5:
            score += 8.0
            flags.append("signal_density")
            reasons.append(
                ArkhamSuspiciousReason(
                    section="signal_context",
                    status="flag",
                    message="Local wallet signals show persistent notable behavior.",
                )
            )
        elif local_context.signals_count >= 1:
            score += 4.0
            reasons.append(
                ArkhamSuspiciousReason(
                    section="signal_context",
                    status="info",
                    message="Local wallet signals are present.",
                )
            )

        if local_context.would_copy_count >= 3:
            score += 8.0
            flags.append("shadow_copy_density")
            reasons.append(
                ArkhamSuspiciousReason(
                    section="shadow_context",
                    status="flag",
                    message="Shadow-copy runs produced multiple WOULD_COPY candidates.",
                )
            )
        elif local_context.would_copy_count >= 1:
            score += 4.0
            reasons.append(
                ArkhamSuspiciousReason(
                    section="shadow_context",
                    status="info",
                    message="Shadow-copy runs have produced at least one WOULD_COPY candidate.",
                )
            )

        if (
            local_context.dominant_market_count >= 3
            and local_context.distinct_markets_count <= 2
        ):
            score += 5.0
            flags.append("activity_concentration")
            reasons.append(
                ArkhamSuspiciousReason(
                    section="concentration_context",
                    status="flag",
                    message=(
                        "Local wallet activity appears concentrated in a narrow "
                        "market footprint."
                    ),
                )
            )

        return ArkhamSuspiciousWalletItem(
            rank=0,
            tracked_wallet=wallet,
            enrichment=record,
            watch_score=round(score, 2),
            watch_candidate=score >= 25.0,
            flags=sorted(set(flags)),
            local_context=local_context,
            reasons=reasons,
        )


def _normalize_address(address: str) -> str:
    try:
        return normalize_wallet_address(address)
    except Exception as exc:  # pragma: no cover - validated in wallet tests
        raise ArkhamValidationError(str(exc)) from exc


def _collection_length(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return len(payload)
    return 0


def _source(endpoint: str) -> ArkhamSourceAttribution:
    return ArkhamSourceAttribution(endpoint=endpoint, retrieved_at=_utc_now_iso())


def _entity_from_payload(payload: Mapping[str, Any] | None) -> ArkhamEntitySummary | None:
    if not isinstance(payload, Mapping):
        return None
    entity_id = payload.get("id")
    name = payload.get("name")
    if not entity_id or not name:
        return None
    return ArkhamEntitySummary(
        entity_id=str(entity_id),
        name=str(name),
        entity_type=_string_or_none(payload.get("type")),
        note=_string_or_none(payload.get("note")),
        service=_bool_or_none(payload.get("service")),
        website=_string_or_none(payload.get("website")),
        twitter=_string_or_none(payload.get("twitter")),
        tags=_extract_tags(payload.get("populatedTags")),
    )


def _label_from_payload(payload: Mapping[str, Any] | None) -> ArkhamLabelSummary | None:
    if not isinstance(payload, Mapping):
        return None
    name = payload.get("name")
    if not name:
        return None
    return ArkhamLabelSummary(
        name=str(name),
        address=_string_or_none(payload.get("address")),
        chain_type=_string_or_none(payload.get("chainType")),
        note=_string_or_none(payload.get("note")),
    )


def _record_from_enriched_payload(
    address: str,
    payload: Mapping[str, Any],
    *,
    source_attributions: list[ArkhamSourceAttribution],
    errors: list[ArkhamSectionError],
) -> ArkhamEnrichmentRecord:
    verified_entity = _entity_from_payload(_mapping_or_none(payload.get("arkhamEntity")))
    predicted_entity = _entity_from_payload(_mapping_or_none(payload.get("predictedEntity")))
    user_entity = _entity_from_payload(_mapping_or_none(payload.get("userEntity")))
    verified_label = _label_from_payload(_mapping_or_none(payload.get("arkhamLabel")))
    user_label = _label_from_payload(_mapping_or_none(payload.get("userLabel")))
    return ArkhamEnrichmentRecord(
        address=address,
        chain=_string_or_none(payload.get("chain")),
        confidence_classification=_confidence_classification(
            verified_entity=verified_entity,
            verified_label=verified_label,
            predicted_entity=predicted_entity,
            user_entity=user_entity,
            user_label=user_label,
        ),
        verified_entity=verified_entity,
        predicted_entity=predicted_entity,
        user_entity=user_entity,
        verified_label=verified_label,
        user_label=user_label,
        populated_tags=_extract_tags(payload.get("populatedTags")),
        cluster_ids=_extract_string_list(payload.get("clusterIds")),
        contract=_bool_or_none(payload.get("contract")),
        service=_bool_or_none(payload.get("service")),
        program=_bool_or_none(payload.get("program")),
        is_user_address=_bool_or_none(payload.get("isUserAddress")),
        deposit_service_id=_string_or_none(payload.get("depositServiceID")),
        recent_enriched_at=_utc_now_iso(),
        source_attributions=source_attributions,
        errors=list(errors),
    )


def _record_from_basic_payload(
    address: str,
    payload: Mapping[str, Any],
    *,
    source_attributions: list[ArkhamSourceAttribution],
    errors: list[ArkhamSectionError],
) -> ArkhamEnrichmentRecord:
    verified_entity = _entity_from_payload(_mapping_or_none(payload.get("arkhamEntity")))
    verified_label = _label_from_payload(_mapping_or_none(payload.get("arkhamLabel")))
    user_entity = _entity_from_payload(_mapping_or_none(payload.get("userEntity")))
    user_label = _label_from_payload(_mapping_or_none(payload.get("userLabel")))
    return ArkhamEnrichmentRecord(
        address=address,
        chain=_string_or_none(payload.get("chain")),
        confidence_classification=_confidence_classification(
            verified_entity=verified_entity,
            verified_label=verified_label,
            predicted_entity=None,
            user_entity=user_entity,
            user_label=user_label,
        ),
        verified_entity=verified_entity,
        user_entity=user_entity,
        verified_label=verified_label,
        user_label=user_label,
        contract=_bool_or_none(payload.get("contract")),
        service=_bool_or_none(payload.get("service")),
        program=_bool_or_none(payload.get("program")),
        is_user_address=_bool_or_none(payload.get("isUserAddress")),
        recent_enriched_at=_utc_now_iso(),
        source_attributions=source_attributions,
        errors=list(errors),
    )


def _confidence_classification(
    *,
    verified_entity: ArkhamEntitySummary | None,
    verified_label: ArkhamLabelSummary | None,
    predicted_entity: ArkhamEntitySummary | None,
    user_entity: ArkhamEntitySummary | None,
    user_label: ArkhamLabelSummary | None,
) -> str:
    if verified_entity is not None or verified_label is not None:
        return "verified"
    if predicted_entity is not None:
        return "predicted"
    if user_entity is not None or user_label is not None:
        return "user"
    return "unknown"


def _counterparties_from_payload(payload: Any) -> list[ArkhamCounterpartySummary]:
    if not isinstance(payload, Mapping):
        return []

    items: list[ArkhamCounterpartySummary] = []
    for value in payload.values():
        if not isinstance(value, list):
            continue
        for raw_item in value:
            if not isinstance(raw_item, Mapping):
                continue
            address_payload = _mapping_or_none(raw_item.get("address"))
            if address_payload is None:
                continue
            counterparty_address = _string_or_none(address_payload.get("address"))
            if counterparty_address is None:
                continue
            items.append(
                ArkhamCounterpartySummary(
                    counterparty_address=counterparty_address,
                    flow=_string_or_none(raw_item.get("flow")),
                    usd=_string_or_none(raw_item.get("usd")),
                    transaction_count=_int_or_none(raw_item.get("transactionCount")),
                    chains=_extract_string_list(raw_item.get("chains")),
                    entity=_entity_from_payload(
                        _mapping_or_none(address_payload.get("arkhamEntity"))
                    ),
                    label=_label_from_payload(
                        _mapping_or_none(address_payload.get("arkhamLabel"))
                    ),
                    tags=_counterparty_tags_from_address_payload(address_payload),
                )
            )
    items.sort(key=lambda item: (-_float_or_zero(item.usd), item.counterparty_address))
    return items[:COUNTERPARTY_DEFAULT_LIMIT]


def _counterparty_tags_from_address_payload(payload: Mapping[str, Any]) -> list[str]:
    tags = _extract_tags(payload.get("populatedTags"))
    for entity_key in ("arkhamEntity", "predictedEntity", "userEntity"):
        entity_payload = _mapping_or_none(payload.get(entity_key))
        if entity_payload is not None:
            tags.extend(_extract_tags(entity_payload.get("populatedTags")))
    return sorted(dict.fromkeys(tags))


def _risk_families(record: ArkhamEnrichmentRecord) -> list[str]:
    haystacks = [
        record.verified_label.name if record.verified_label else None,
        record.verified_label.note if record.verified_label else None,
        record.user_label.name if record.user_label else None,
        record.user_label.note if record.user_label else None,
        record.verified_entity.name if record.verified_entity else None,
        record.verified_entity.entity_type if record.verified_entity else None,
        record.verified_entity.note if record.verified_entity else None,
        record.predicted_entity.name if record.predicted_entity else None,
        record.predicted_entity.entity_type if record.predicted_entity else None,
        record.predicted_entity.note if record.predicted_entity else None,
        record.user_entity.name if record.user_entity else None,
        record.user_entity.entity_type if record.user_entity else None,
        record.user_entity.note if record.user_entity else None,
        *record.populated_tags,
    ]
    normalized = " ".join(item.lower() for item in haystacks if item)
    return sorted(
        family
        for family, terms in _RISK_LEXICON.items()
        if any(term in normalized for term in terms)
    )


def _record_entity_ids(record: ArkhamEnrichmentRecord) -> set[str]:
    return {
        entity.entity_id
        for entity in [
            record.verified_entity,
            record.predicted_entity,
            record.user_entity,
        ]
        if entity is not None
    }


def _preferred_entity_id(record: ArkhamEnrichmentRecord) -> str | None:
    for entity in [record.verified_entity, record.predicted_entity, record.user_entity]:
        if entity is not None:
            return entity.entity_id
    return None


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _float_or_zero(value: str | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _extract_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _extract_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            label = item.get("label")
            if label is not None:
                tags.append(str(label))
                continue
        if item is not None:
            tags.append(str(item))
    return sorted(dict.fromkeys(tags))


def _timestamp_key(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _client_error_code(exc: Exception) -> str:
    if isinstance(exc, ArkhamNotFoundError):
        return "not_found"
    return "request_failed"


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
