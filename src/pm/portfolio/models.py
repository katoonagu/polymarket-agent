"""Models for portfolio snapshots, attribution, and reconciliation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.data.models import NormalizedClosedPosition, NormalizedCurrentPosition


class PortfolioSectionError(BaseModel):
    """Partial portfolio failure detail."""

    section: str
    code: str
    message: str


class PortfolioAttribution(BaseModel):
    """Local strategy attribution attached to a portfolio position."""

    status: str
    strategy_name: str | None = None
    strategy_names: list[str] = Field(default_factory=list)
    execution_ids: list[str] = Field(default_factory=list)


class PortfolioCurrentPositionItem(BaseModel):
    """Attributed current-position row."""

    position: NormalizedCurrentPosition
    attribution: PortfolioAttribution


class PortfolioClosedPositionItem(BaseModel):
    """Attributed closed-position row."""

    position: NormalizedClosedPosition
    attribution: PortfolioAttribution


class PortfolioMarketSummary(BaseModel):
    """Exposure and PnL summary for one market."""

    condition_id: str
    market_slug: str | None = None
    gross_exposure: str
    net_exposure: str
    realized_pnl: str
    unrealized_pnl: str
    total_pnl: str
    current_positions_count: int = 0
    closed_positions_count: int = 0


class PortfolioStrategySummary(BaseModel):
    """Exposure and PnL summary for one linked strategy."""

    strategy_name: str
    strategy_type: str | None = None
    gross_exposure: str
    net_exposure: str
    realized_pnl: str
    unrealized_pnl: str
    total_pnl: str
    current_positions_count: int = 0
    closed_positions_count: int = 0
    execution_ids: list[str] = Field(default_factory=list)


class PortfolioSnapshotSummary(BaseModel):
    """Top-level account summary for one portfolio snapshot."""

    holdings_value: str | None = None
    realized_pnl_total: str
    unrealized_pnl_total: str
    total_pnl: str
    gross_exposure: str
    net_exposure: str
    current_positions_count: int = 0
    closed_positions_count: int = 0
    linked_current_positions_count: int = 0
    unlinked_current_positions_count: int = 0
    ambiguous_current_positions_count: int = 0
    linked_closed_positions_count: int = 0
    unlinked_closed_positions_count: int = 0
    ambiguous_closed_positions_count: int = 0


class PortfolioSnapshotRecord(BaseModel):
    """Append-only persisted portfolio snapshot."""

    snapshot_id: str
    account_address: str
    created_at: str
    summary: PortfolioSnapshotSummary
    current_positions: list[PortfolioCurrentPositionItem] = Field(default_factory=list)
    closed_positions: list[PortfolioClosedPositionItem] = Field(default_factory=list)
    per_market: list[PortfolioMarketSummary] = Field(default_factory=list)
    per_strategy: list[PortfolioStrategySummary] = Field(default_factory=list)
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioSnapshotsFile(BaseModel):
    """Versioned local portfolio-snapshots state document."""

    version: int = 1
    snapshots: list[PortfolioSnapshotRecord] = Field(default_factory=list)


class PortfolioSummaryResponse(BaseModel):
    """Compact portfolio-summary payload."""

    account_address: str
    snapshot_id: str
    created_at: str
    summary: PortfolioSnapshotSummary
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioPositionsResponse(BaseModel):
    """Current-positions portfolio payload."""

    account_address: str
    snapshot_id: str
    created_at: str
    summary: PortfolioSnapshotSummary
    items: list[PortfolioCurrentPositionItem] = Field(default_factory=list)
    total: int = 0
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioClosedResponse(BaseModel):
    """Closed-positions portfolio payload."""

    account_address: str
    snapshot_id: str
    created_at: str
    summary: PortfolioSnapshotSummary
    items: list[PortfolioClosedPositionItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioMarketResponse(BaseModel):
    """Market-scoped portfolio payload."""

    account_address: str
    snapshot_id: str
    created_at: str
    market: PortfolioMarketSummary
    current_positions: list[PortfolioCurrentPositionItem] = Field(default_factory=list)
    closed_positions: list[PortfolioClosedPositionItem] = Field(default_factory=list)
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioExposureResponse(BaseModel):
    """Exposure-focused portfolio payload."""

    account_address: str
    snapshot_id: str
    created_at: str
    summary: PortfolioSnapshotSummary
    per_market: list[PortfolioMarketSummary] = Field(default_factory=list)
    per_strategy: list[PortfolioStrategySummary] = Field(default_factory=list)
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioPnlResponse(BaseModel):
    """PnL-focused portfolio payload."""

    account_address: str
    snapshot_id: str
    created_at: str
    summary: PortfolioSnapshotSummary
    per_market: list[PortfolioMarketSummary] = Field(default_factory=list)
    per_strategy: list[PortfolioStrategySummary] = Field(default_factory=list)
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioDiscrepancy(BaseModel):
    """Structured portfolio reconciliation discrepancy."""

    kind: str
    severity: str
    condition_id: str | None = None
    token_id: str | None = None
    order_id: str | None = None
    execution_id: str | None = None
    strategy_name: str | None = None
    message: str


class PortfolioReconciliationSummary(BaseModel):
    """Compact health summary for one portfolio reconciliation."""

    health: str
    discrepancy_count: int = 0
    execution_state_mismatch_count: int = 0
    unlinked_current_position_count: int = 0
    linked_execution_missing_from_positions_count: int = 0
    ambiguous_strategy_link_count: int = 0


class PortfolioReconciliationRecord(BaseModel):
    """Append-only persisted portfolio reconciliation."""

    reconciliation_id: str
    snapshot_id: str
    execution_reconciliation_id: str | None = None
    account_address: str
    created_at: str
    summary: PortfolioReconciliationSummary
    discrepancies: list[PortfolioDiscrepancy] = Field(default_factory=list)
    errors: list[PortfolioSectionError] = Field(default_factory=list)


class PortfolioReconciliationsFile(BaseModel):
    """Versioned local portfolio-reconciliations state document."""

    version: int = 1
    reconciliations: list[PortfolioReconciliationRecord] = Field(default_factory=list)


class PortfolioReconciliationResponse(BaseModel):
    """Portfolio reconciliation response payload."""

    reconciliation_id: str
    snapshot_id: str
    execution_reconciliation_id: str | None = None
    account_address: str
    created_at: str
    summary: PortfolioReconciliationSummary
    discrepancies: list[PortfolioDiscrepancy] = Field(default_factory=list)
    errors: list[PortfolioSectionError] = Field(default_factory=list)
