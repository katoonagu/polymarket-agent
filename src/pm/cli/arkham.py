"""Arkham intelligence CLI commands."""

from __future__ import annotations

import typer
from rich.console import RenderableType

from pm.arkham import (
    ArkhamClientError,
    ArkhamCounterpartySummary,
    ArkhamDossierResponse,
    ArkhamEnrichmentRecord,
    ArkhamEnrichResponse,
    ArkhamSectionError,
    ArkhamService,
    ArkhamStateError,
    ArkhamStatusResponse,
    ArkhamSuspiciousTrackedResponse,
    ArkhamSyncTrackedResponse,
    ArkhamValidationError,
)
from pm.cli.support import LOCAL_JSON_OPTION, emit_command_error, emit_command_output
from pm.common.tables import empty_message, render_group, row_table, section_panel, summary_table

app = typer.Typer(
    add_completion=False,
    help="Arkham-backed wallet intelligence enrichment and suspicious-wallet heuristics.",
    no_args_is_help=True,
)
sync_app = typer.Typer(add_completion=False, help="Arkham sync commands.")
suspicious_app = typer.Typer(add_completion=False, help="Arkham suspicious-wallet commands.")
app.add_typer(sync_app, name="sync")
app.add_typer(suspicious_app, name="suspicious")

ADDRESS_OPTION = typer.Option(..., "--address", help="0x-prefixed EVM wallet address.")
LIMIT_OPTION = typer.Option(20, "--limit", min=1, help="Maximum number of rows to return.")


@app.command("status")
def status(
    ctx: typer.Context,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Show Arkham readiness and local cache status."""
    try:
        result = ArkhamService().status()
    except ArkhamStateError as exc:
        _emit_arkham_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_status(result),
        renderable=_render_status(result),
        local_json_output=json_output,
    )


@app.command("enrich")
def enrich(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Enrich one wallet address and cache the latest record."""
    try:
        result = ArkhamService().enrich(address)
    except (ArkhamValidationError, ArkhamClientError, ArkhamStateError) as exc:
        _emit_arkham_error(ctx, exc=exc, json_output=json_output, identifier=address)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_enrich(result),
        renderable=_render_dossier_like(result.address, result.record, result.errors, []),
        local_json_output=json_output,
    )


@app.command("dossier")
def dossier(
    ctx: typer.Context,
    address: str = ADDRESS_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Build a richer Arkham dossier for one address."""
    try:
        result = ArkhamService().dossier(address)
    except (ArkhamValidationError, ArkhamClientError, ArkhamStateError) as exc:
        _emit_arkham_error(ctx, exc=exc, json_output=json_output, identifier=address)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_dossier(result),
        renderable=_render_dossier(result),
        local_json_output=json_output,
    )


@sync_app.command("tracked")
def sync_tracked(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Enrich tracked wallets from the local wallet registry."""
    try:
        result = ArkhamService().sync_tracked(limit=limit)
    except (ArkhamValidationError, ArkhamClientError, ArkhamStateError) as exc:
        _emit_arkham_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_sync(result),
        local_json_output=json_output,
    )


@suspicious_app.command("tracked")
def suspicious_tracked(
    ctx: typer.Context,
    limit: int = LIMIT_OPTION,
    json_output: bool = LOCAL_JSON_OPTION,
) -> None:
    """Rank tracked wallets using cached Arkham and local wallet context."""
    try:
        result = ArkhamService().suspicious_tracked(limit=limit)
    except (ArkhamValidationError, ArkhamStateError) as exc:
        _emit_arkham_error(ctx, exc=exc, json_output=json_output)
        raise typer.Exit(1) from exc
    emit_command_output(
        ctx,
        result.model_dump(mode="json"),
        text=_format_suspicious(result),
        renderable=_render_suspicious(result),
        local_json_output=json_output,
    )


def _emit_arkham_error(
    ctx: typer.Context,
    *,
    exc: Exception,
    json_output: bool,
    identifier: str | None = None,
) -> None:
    code = "invalid_argument" if isinstance(exc, ArkhamValidationError) else "request_failed"
    if isinstance(exc, ArkhamStateError):
        code = "state_error"
    emit_command_error(
        ctx,
        code=code,
        message=str(exc),
        resource="arkham",
        identifier=identifier,
        local_json_output=json_output,
    )


def _format_status(response: ArkhamStatusResponse) -> str:
    return "\n".join(
        [
            f"Configured: {response.configured}",
            f"Ready: {response.ready}",
            f"Env source: {response.env_source or '-'}",
            f"API reachable: {response.api_reachable}",
            f"Tracked wallets: {response.tracked_wallet_count}",
            f"Cached enrichments: {response.cached_enrichment_count}",
            f"Latest enrichment: {response.latest_enrichment_at or '-'}",
        ]
    )


def _format_enrich(response: ArkhamEnrichResponse) -> str:
    if response.record is None:
        return f"Address: {response.address}\nNo Arkham enrichment is available."
    return "\n".join(
        [
            f"Address: {response.address}",
            f"Classification: {response.record.confidence_classification}",
            f"Tags: {', '.join(response.record.populated_tags) or '-'}",
            f"Clusters: {', '.join(response.record.cluster_ids) or '-'}",
            f"Enriched at: {response.record.recent_enriched_at}",
        ]
    )


def _format_dossier(response: ArkhamDossierResponse) -> str:
    return "\n".join(
        [
            f"Address: {response.address}",
            f"Configured: {response.configured}",
            f"Ready: {response.ready}",
            f"Counterparties: {response.counterparties_total}",
        ]
    )


def _format_sync(response: ArkhamSyncTrackedResponse) -> str:
    return "\n".join(
        [
            f"Configured: {response.configured}",
            f"Ready: {response.ready}",
            f"Tracked total: {response.tracked_total}",
            f"Processed: {response.processed_count}",
            f"Enriched: {response.enriched_count}",
            f"Partial: {response.partial_error_count}",
        ]
    )


def _format_suspicious(response: ArkhamSuspiciousTrackedResponse) -> str:
    return "\n".join(
        [
            f"Cache only: {response.cache_only}",
            f"Tracked total: {response.tracked_total}",
            f"Ranked: {response.total}",
            f"Missing enrichment: {response.missing_enrichment_count}",
        ]
    )


def _render_status(response: ArkhamStatusResponse) -> RenderableType:
    rows = [
        ("Configured", str(response.configured)),
        ("Ready", str(response.ready)),
        ("Env source", response.env_source or "-"),
        ("API reachable", str(response.api_reachable)),
        ("Chains", str(response.chains_count or 0)),
        ("Tracked wallets", str(response.tracked_wallet_count)),
        ("Cached enrichments", str(response.cached_enrichment_count)),
        ("Latest enrichment", response.latest_enrichment_at or "-"),
    ]
    body = [section_panel("Status", summary_table(title="Arkham", rows=rows))]
    if response.errors:
        body.append(
            section_panel(
                "Errors",
                row_table(
                    title="Arkham errors",
                    columns=("Section", "Code", "Message"),
                    rows=((item.section, item.code, item.message) for item in response.errors),
                ),
            )
        )
    return render_group(*body)


def _render_dossier(response: ArkhamDossierResponse) -> RenderableType:
    return _render_dossier_like(
        response.address,
        response.enrichment,
        response.errors,
        response.counterparties,
    )


def _render_dossier_like(
    address: str,
    record: ArkhamEnrichmentRecord | None,
    errors: list[ArkhamSectionError],
    counterparties: list[ArkhamCounterpartySummary],
) -> RenderableType:
    summary_rows = [("Address", address)]
    if record is not None:
        summary_rows.extend(
            [
                ("Classification", record.confidence_classification),
                ("Tags", ", ".join(record.populated_tags) or "-"),
                ("Clusters", ", ".join(record.cluster_ids) or "-"),
                ("Enriched at", record.recent_enriched_at),
            ]
        )
    sections = [
        section_panel(
            "Enrichment",
            summary_table(title="Arkham dossier", rows=summary_rows),
        )
    ]
    if counterparties:
        sections.append(
            section_panel(
                "Counterparties",
                row_table(
                    title="Top counterparties",
                    columns=("Address", "USD", "Flow", "Txs"),
                    rows=(
                        (
                            item.counterparty_address,
                            item.usd or "-",
                            item.flow or "-",
                            str(item.transaction_count or 0),
                        )
                        for item in counterparties
                    ),
                ),
            )
        )
    elif not counterparties:
        sections.append(section_panel("Counterparties", empty_message("No Arkham counterparties.")))
    if errors:
        sections.append(
            section_panel(
                "Errors",
                row_table(
                    title="Arkham errors",
                    columns=("Section", "Code", "Message"),
                    rows=((item.section, item.code, item.message) for item in errors),
                ),
            )
        )
    return render_group(*sections)


def _render_suspicious(response: ArkhamSuspiciousTrackedResponse) -> RenderableType:
    if not response.items:
        return section_panel("Suspicious tracked", empty_message("No tracked wallets ranked."))
    return render_group(
        section_panel(
            "Suspicious tracked",
            row_table(
                title="Watch candidates",
                columns=("Rank", "Address", "Score", "Candidate", "Flags"),
                rows=(
                    (
                        str(item.rank),
                        item.tracked_wallet.address,
                        f"{item.watch_score:.2f}",
                        str(item.watch_candidate),
                        ", ".join(item.flags) or "-",
                    )
                    for item in response.items
                ),
            ),
        )
    )
