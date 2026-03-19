"""Unit tests for Arkham enrichment and suspicious-wallet heuristics."""

from __future__ import annotations

import httpx
import respx

from pm.arkham import (
    ARKHAM_API_KEY_ENV,
    LEGACY_ARKHAM_API_KEY_ENV,
    ArkhamEnrichmentRecord,
    ArkhamService,
    ArkhamStateError,
    ArkhamStateService,
)
from pm.wallet import WalletPipelineStateService, WalletRegistryService
from pm.wallet.models import (
    WalletEvent,
    WalletShadowCandidateIntent,
    WalletShadowRun,
    WalletShadowRunParameters,
    WalletSignal,
)

API_URL = "https://api.arkm.com"
USER = "0x1111111111111111111111111111111111111111"
USER_TWO = "0x2222222222222222222222222222222222222222"
USER_THREE = "0x3333333333333333333333333333333333333333"
CONDITION_ID = "0x" + ("a" * 64)


@respx.mock
def test_status_prefers_primary_api_key_over_legacy(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ARKHAM_API_KEY_ENV, "primary-key")
    monkeypatch.setenv(LEGACY_ARKHAM_API_KEY_ENV, "legacy-key")
    route = respx.get(f"{API_URL}/chains").mock(
        return_value=httpx.Response(200, json=[{"id": "ethereum"}])
    )

    result = _service(tmp_path).status()

    assert result.configured is True
    assert result.ready is True
    assert result.env_source == ARKHAM_API_KEY_ENV
    assert route.calls.last.request.headers["API-Key"] == "primary-key"


@respx.mock
def test_status_supports_legacy_api_key_fallback(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(ARKHAM_API_KEY_ENV, raising=False)
    monkeypatch.setenv(LEGACY_ARKHAM_API_KEY_ENV, "legacy-key")
    route = respx.get(f"{API_URL}/chains").mock(
        return_value=httpx.Response(200, json=[{"id": "ethereum"}])
    )

    result = _service(tmp_path).status()

    assert result.env_source == LEGACY_ARKHAM_API_KEY_ENV
    assert route.calls.last.request.headers["API-Key"] == "legacy-key"


def test_status_missing_credentials_returns_help_response(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(ARKHAM_API_KEY_ENV, raising=False)
    monkeypatch.delenv(LEGACY_ARKHAM_API_KEY_ENV, raising=False)

    result = _service(tmp_path).status()

    assert result.configured is False
    assert result.ready is False
    assert result.api_reachable is None
    assert result.next_steps[0].startswith("Set ARKHAM_API_KEY")


@respx.mock
def test_enrich_assembles_record_from_enriched_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ARKHAM_API_KEY_ENV, "primary-key")
    respx.get(f"{API_URL}/intelligence/address_enriched/{USER}").mock(
        return_value=httpx.Response(200, json=_enriched_payload(USER))
    )

    service = _service(tmp_path)
    result = service.enrich(USER)

    assert result.record is not None
    assert result.record.confidence_classification == "verified"
    assert result.record.verified_entity is not None
    assert result.record.verified_entity.name == "Binance"
    assert result.record.cluster_ids == ["cluster-1", "cluster-2"]
    assert "OFAC Sanctioned" in result.record.populated_tags
    assert service._state.get_enrichment(USER) is not None


@respx.mock
def test_enrich_degrades_to_basic_address_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ARKHAM_API_KEY_ENV, "primary-key")
    respx.get(f"{API_URL}/intelligence/address_enriched/{USER}").mock(
        return_value=httpx.Response(500)
    )
    respx.get(f"{API_URL}/intelligence/address/{USER}").mock(
        return_value=httpx.Response(200, json=_basic_payload(USER))
    )

    result = _service(tmp_path).enrich(USER)

    assert result.record is not None
    assert result.record.confidence_classification == "verified"
    assert any(item.section == "address_enriched" for item in result.errors)
    assert result.record.verified_entity is not None
    assert result.record.verified_entity.name == "Known Desk"


@respx.mock
def test_dossier_assembles_entity_and_counterparties(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ARKHAM_API_KEY_ENV, "primary-key")
    respx.get(f"{API_URL}/intelligence/address_enriched/{USER}").mock(
        return_value=httpx.Response(200, json=_enriched_payload(USER))
    )
    respx.get(f"{API_URL}/intelligence/entity/entity-1").mock(
        return_value=httpx.Response(200, json=_entity_payload())
    )
    respx.get(f"{API_URL}/counterparties/address/{USER}").mock(
        return_value=httpx.Response(200, json=_counterparties_payload())
    )

    result = _service(tmp_path).dossier(USER)

    assert result.enrichment is not None
    assert result.entity is not None
    assert result.entity.name == "Binance"
    assert result.counterparties_total == 1
    assert result.counterparties[0].counterparty_address == USER_TWO


@respx.mock
def test_sync_tracked_respects_registry_order_limit_and_partial_errors(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv(ARKHAM_API_KEY_ENV, "primary-key")
    service = _service(tmp_path)
    service._wallet_registry.add_wallet(USER, added_at="2026-03-19T00:00:00Z")
    service._wallet_registry.add_wallet(USER_TWO, added_at="2026-03-19T00:01:00Z")
    service._wallet_registry.add_wallet(USER_THREE, added_at="2026-03-19T00:02:00Z")
    respx.get(f"{API_URL}/intelligence/address_enriched/{USER}").mock(
        return_value=httpx.Response(200, json=_enriched_payload(USER))
    )
    respx.get(f"{API_URL}/intelligence/address_enriched/{USER_TWO}").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{API_URL}/intelligence/address/{USER_TWO}").mock(
        return_value=httpx.Response(404)
    )

    result = service.sync_tracked(limit=2)

    assert result.processed_count == 2
    assert result.items[0].address == USER
    assert result.items[1].address == USER_TWO
    assert result.partial_error_count == 1
    assert result.enriched_count == 1


def test_suspicious_tracked_ranks_cached_wallets_with_local_context_only(tmp_path) -> None:
    service = _service(tmp_path)
    service._wallet_registry.add_wallet(USER, label="Alpha", added_at="2026-03-19T00:00:00Z")
    service._wallet_registry.add_wallet(USER_TWO, label="Beta", added_at="2026-03-19T00:01:00Z")
    service._wallet_registry.add_wallet(USER_THREE, label="Gamma", added_at="2026-03-19T00:02:00Z")

    service._state.upsert_enrichment(
        _enrichment_record(
            USER,
            tags=["OFAC Sanctioned"],
            cluster_ids=["cluster-1"],
        )
    )
    service._state.upsert_enrichment(
        _enrichment_record(
            USER_TWO,
            tags=["Fund"],
            cluster_ids=["cluster-1"],
        )
    )

    service._wallet_state.append_events(
        [
            WalletEvent(
                source_wallet=USER,
                condition_id=CONDITION_ID,
                source_kind="trade",
                dedupe_key=f"event-{index}",
                classification="new_entry",
            )
            for index in range(4)
        ]
    )
    service._wallet_state.append_signals(
        [
            WalletSignal(
                source_wallet=USER,
                condition_id=CONDITION_ID,
                source_kind="trade",
                dedupe_key=f"signal-{index}",
                classification="new_entry",
            )
            for index in range(5)
        ]
    )
    service._wallet_state.append_shadow_run(
        WalletShadowRun(
            source_wallet=USER,
            run_at="2026-03-19T00:03:00Z",
            parameters=WalletShadowRunParameters(
                fixed_size_usdc="25",
                max_drift_pct="5",
                max_spread_pct="5",
                entry_only=True,
                limit=20,
            ),
            would_copy_count=3,
            candidate_intents=[
                WalletShadowCandidateIntent(
                    source_wallet=USER,
                    condition_id=CONDITION_ID,
                    simulated_size_usdc="25",
                    decision="WOULD_COPY",
                    classification="new_entry",
                    dedupe_key="candidate-1",
                )
            ],
        )
    )

    result = service.suspicious_tracked(limit=3)

    assert result.items[0].tracked_wallet.address == USER
    assert result.items[0].watch_candidate is True
    assert "sanctions_or_blocklist" in result.items[0].flags
    assert "shared_cluster_ids" in result.items[0].flags
    assert result.missing_enrichment_count == 1


def test_invalid_state_file_raises_state_error(tmp_path) -> None:
    path = tmp_path / "arkham-enrichments.json"
    path.write_text("{not-json", encoding="utf-8")
    state = ArkhamStateService(enrichments_path=path)

    try:
        state.list_enrichments()
    except ArkhamStateError:
        pass
    else:
        raise AssertionError("Expected ArkhamStateError")


def _service(tmp_path) -> ArkhamService:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    wallet_state = WalletPipelineStateService(
        events_path=tmp_path / "wallet-events.json",
        signals_path=tmp_path / "wallet-signals.json",
        shadow_runs_path=tmp_path / "wallet-shadow-runs.json",
    )
    state = ArkhamStateService(enrichments_path=tmp_path / "arkham-enrichments.json")
    return ArkhamService(state=state, wallet_registry=registry, wallet_state=wallet_state)


def _enriched_payload(address: str) -> dict[str, object]:
    return {
        "address": address,
        "chain": "ethereum",
        "arkhamEntity": _entity_payload(),
        "arkhamLabel": {"address": address, "chainType": "ethereum", "name": "Binance 14"},
        "clusterIds": ["cluster-1", "cluster-2"],
        "contract": False,
        "service": True,
        "program": False,
        "isUserAddress": False,
        "depositServiceID": "dep-1",
        "populatedTags": [{"label": "OFAC Sanctioned"}, {"label": "Exchange"}],
    }


def _basic_payload(address: str) -> dict[str, object]:
    return {
        "address": address,
        "chain": "ethereum",
        "arkhamEntity": {
            "id": "entity-basic",
            "name": "Known Desk",
            "type": "market-maker",
            "note": "Publicly identified desk",
            "service": True,
        },
        "arkhamLabel": {"address": address, "chainType": "ethereum", "name": "Known Desk 1"},
        "contract": False,
        "service": True,
        "program": False,
        "isUserAddress": False,
    }


def _entity_payload() -> dict[str, object]:
    return {
        "id": "entity-1",
        "name": "Binance",
        "type": "cex",
        "note": "Large exchange",
        "service": True,
        "website": "https://example.com",
        "twitter": "binance",
        "populatedTags": [{"label": "Exchange"}],
    }


def _counterparties_payload() -> dict[str, object]:
    return {
        "bucket-1": [
            {
                "address": {
                    "address": USER_TWO,
                    "arkhamEntity": _entity_payload(),
                    "arkhamLabel": {
                        "address": USER_TWO,
                        "chainType": "ethereum",
                        "name": "Counterparty",
                    },
                    "populatedTags": [{"label": "Fund"}],
                },
                "chains": ["ethereum"],
                "flow": "out",
                "transactionCount": 4,
                "usd": "2500.25",
            }
        ]
    }


def _enrichment_record(
    address: str,
    *,
    tags: list[str],
    cluster_ids: list[str],
) -> ArkhamEnrichmentRecord:
    return ArkhamEnrichmentRecord(
        address=address,
        chain="ethereum",
        confidence_classification="verified",
        verified_entity=_entity_payload_to_summary(),
        verified_label={"name": "Label"} if False else None,
        populated_tags=tags,
        cluster_ids=cluster_ids,
        recent_enriched_at="2026-03-19T00:04:00Z",
    )


def _entity_payload_to_summary():
    from pm.arkham.models import ArkhamEntitySummary

    return ArkhamEntitySummary(
        entity_id="entity-1",
        name="Binance",
        entity_type="cex",
        note="Large exchange",
        service=True,
        website="https://example.com",
        twitter="binance",
        tags=["Exchange"],
    )
