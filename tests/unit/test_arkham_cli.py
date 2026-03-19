"""CLI tests for Arkham enrichment commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.arkham.models import (
    ArkhamCounterpartySummary,
    ArkhamDossierResponse,
    ArkhamEnrichmentRecord,
    ArkhamEnrichResponse,
    ArkhamEntitySummary,
    ArkhamStatusResponse,
    ArkhamSuspiciousReason,
    ArkhamSuspiciousTrackedResponse,
    ArkhamSuspiciousWalletItem,
    ArkhamSyncTrackedItem,
    ArkhamSyncTrackedResponse,
)
from pm.cli.app import app
from pm.wallet.models import TrackedWallet

runner = CliRunner()
ADDRESS = "0x1111111111111111111111111111111111111111"


class FakeArkhamService:
    def status(self) -> ArkhamStatusResponse:
        return ArkhamStatusResponse(
            configured=True,
            ready=True,
            env_source="ARKHAM_API_KEY",
            api_reachable=True,
            chains_count=2,
            tracked_wallet_count=3,
            cached_enrichment_count=2,
            latest_enrichment_at="2026-03-19T00:01:00Z",
            next_steps=["pm arkham sync tracked --limit 20"],
        )

    def enrich(self, address: str) -> ArkhamEnrichResponse:
        return ArkhamEnrichResponse(
            configured=True,
            ready=True,
            address=address,
            record=_record(address),
        )

    def dossier(self, address: str) -> ArkhamDossierResponse:
        return ArkhamDossierResponse(
            configured=True,
            ready=True,
            address=address,
            enrichment=_record(address),
            entity=ArkhamEntitySummary(
                entity_id="entity-1",
                name="Binance",
                entity_type="cex",
                service=True,
                tags=["Exchange"],
            ),
            counterparties=[
                ArkhamCounterpartySummary(
                    counterparty_address="0x2222222222222222222222222222222222222222",
                    usd="2500.25",
                    flow="out",
                    transaction_count=4,
                )
            ],
            counterparties_total=1,
        )

    def sync_tracked(self, *, limit: int = 20) -> ArkhamSyncTrackedResponse:
        return ArkhamSyncTrackedResponse(
            configured=True,
            ready=True,
            limit=limit,
            tracked_total=3,
            processed_count=2,
            enriched_count=1,
            partial_error_count=1,
            items=[
                ArkhamSyncTrackedItem(address=ADDRESS, status="enriched", record=_record(ADDRESS)),
                ArkhamSyncTrackedItem(
                    address="0x2222222222222222222222222222222222222222",
                    status="partial",
                    record=_record("0x2222222222222222222222222222222222222222"),
                ),
            ],
        )

    def suspicious_tracked(self, *, limit: int = 20) -> ArkhamSuspiciousTrackedResponse:
        _ = limit
        return ArkhamSuspiciousTrackedResponse(
            cache_only=True,
            total=1,
            tracked_total=3,
            missing_enrichment_count=1,
            items=[
                ArkhamSuspiciousWalletItem(
                    rank=1,
                    tracked_wallet=TrackedWallet(
                        address=ADDRESS,
                        label="Alpha",
                        added_at="2026-03-19T00:00:00Z",
                    ),
                    enrichment=_record(ADDRESS),
                    watch_score=46.0,
                    watch_candidate=True,
                    flags=["sanctions_or_blocklist", "shared_cluster_ids"],
                    reasons=[
                        ArkhamSuspiciousReason(
                            section="risk_labels",
                            status="flag",
                            message="Matched sanctions_or_blocklist heuristic.",
                        )
                    ],
                )
            ],
        )


def test_root_help_lists_arkham_namespace() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "arkham" in result.stdout


def test_arkham_help_lists_commands() -> None:
    result = runner.invoke(app, ["arkham", "--help"])

    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "enrich" in result.stdout
    assert "dossier" in result.stdout
    assert "sync" in result.stdout
    assert "suspicious" in result.stdout


def test_arkham_json_commands(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.arkham.ArkhamService", FakeArkhamService)

    status_result = runner.invoke(app, ["arkham", "status", "--json"])
    enrich_result = runner.invoke(app, ["arkham", "enrich", "--address", ADDRESS, "--json"])
    dossier_result = runner.invoke(app, ["arkham", "dossier", "--address", ADDRESS, "--json"])
    sync_result = runner.invoke(app, ["arkham", "sync", "tracked", "--limit", "2", "--json"])
    suspicious_result = runner.invoke(
        app,
        ["arkham", "suspicious", "tracked", "--limit", "5", "--json"],
    )

    assert json.loads(status_result.stdout)["ready"] is True
    assert json.loads(enrich_result.stdout)["record"]["address"] == ADDRESS
    assert json.loads(dossier_result.stdout)["counterparties_total"] == 1
    assert json.loads(sync_result.stdout)["processed_count"] == 2
    assert json.loads(suspicious_result.stdout)["items"][0]["watch_candidate"] is True


def test_arkham_root_output_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.arkham.ArkhamService", FakeArkhamService)

    result = runner.invoke(app, ["--output", "json", "arkham", "status"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["env_source"] == "ARKHAM_API_KEY"


def test_arkham_human_output_includes_sections(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.arkham.ArkhamService", FakeArkhamService)

    dossier_result = runner.invoke(app, ["arkham", "dossier", "--address", ADDRESS])
    suspicious_result = runner.invoke(app, ["arkham", "suspicious", "tracked", "--limit", "5"])

    assert dossier_result.exit_code == 0
    assert "Counterparties" in dossier_result.stdout
    assert suspicious_result.exit_code == 0
    assert "Watch candidates" in suspicious_result.stdout


def _record(address: str) -> ArkhamEnrichmentRecord:
    return ArkhamEnrichmentRecord(
        address=address,
        chain="ethereum",
        confidence_classification="verified",
        verified_entity=ArkhamEntitySummary(
            entity_id="entity-1",
            name="Binance",
            entity_type="cex",
            service=True,
            tags=["Exchange"],
        ),
        populated_tags=["OFAC Sanctioned", "Exchange"],
        cluster_ids=["cluster-1"],
        recent_enriched_at="2026-03-19T00:01:00Z",
    )
