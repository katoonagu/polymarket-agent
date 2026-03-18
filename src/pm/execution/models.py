"""Models for authenticated dry-run execution planning."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm.auth.models import AuthContext


class ExecutionReasonBlock(BaseModel):
    """Explainable dry-run reason block."""

    section: str
    status: str
    message: str


class DryRunRequest(BaseModel):
    """Normalized dry-run request."""

    market_ref: str
    outcome: str
    side: str
    price: str
    size: str


class DryRunResolvedMarket(BaseModel):
    """Resolved market and token context for a dry-run plan."""

    market_slug: str
    condition_id: str | None = None
    question: str
    token_id: str | None = None
    outcome: str | None = None
    active: bool
    closed: bool
    tick_size: str | None = None
    min_order_size: str | None = None
    fee_rate_bps: int | None = None
    neg_risk: bool | None = None


class DryRunBookContext(BaseModel):
    """Compact public book context for the selected token."""

    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    bid_level_count: int = 0
    ask_level_count: int = 0


class DryRunPostContext(BaseModel):
    """Static dry-run post context."""

    order_type: str = "GTC"
    post_only: bool = False
    submit_mode: str = "dry_run_only"


class DryRunResponse(BaseModel):
    """Deterministic dry-run execution plan."""

    request: DryRunRequest
    auth: AuthContext
    market: DryRunResolvedMarket | None = None
    book_context: DryRunBookContext | None = None
    post_context: DryRunPostContext = Field(default_factory=DryRunPostContext)
    signed_order: dict[str, str | int | float | bool | None] | None = None
    decision: str
    reasons: list[ExecutionReasonBlock] = Field(default_factory=list)
