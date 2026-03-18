"""Models for dry-run execution, approvals, and order lifecycle audit state."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pm.auth.models import AuthContext, BalanceAllowanceView


class ExecutionReasonBlock(BaseModel):
    """Explainable execution or approval reason block."""

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
    """Static dry-run or post context."""

    order_type: str = "GTC"
    post_only: bool = False
    submit_mode: str = "dry_run_only"
    expires_at: str | None = None


class DryRunResponse(BaseModel):
    """Deterministic dry-run execution plan."""

    request: DryRunRequest
    auth: AuthContext
    market: DryRunResolvedMarket | None = None
    book_context: DryRunBookContext | None = None
    post_context: DryRunPostContext = Field(default_factory=DryRunPostContext)
    signed_order: dict[str, Any] | None = None
    decision: str
    reasons: list[ExecutionReasonBlock] = Field(default_factory=list)


class ApprovalAssetStatus(BaseModel):
    """Normalized approval readiness for one asset class."""

    asset: str
    asset_type: str
    token_id: str | None = None
    balance_view: BalanceAllowanceView
    target_contract_address: str | None = None
    exchange_address: str | None = None
    ready: bool


class ApprovalCheckResponse(BaseModel):
    """Approval-readiness response for the authenticated account."""

    auth: AuthContext
    items: list[ApprovalAssetStatus] = Field(default_factory=list)
    total: int = 0


class ApprovalSetRequest(BaseModel):
    """Normalized approval-set request."""

    asset: str
    live: bool = False
    confirm: bool = False


class ApprovalSetResponse(BaseModel):
    """Preview or live approval mutation response."""

    request: ApprovalSetRequest
    auth: AuthContext
    asset_status: ApprovalAssetStatus | None = None
    mode: str
    decision: str
    plan_id: str
    result_id: str | None = None
    live_response: dict[str, Any] | None = None
    reasons: list[ExecutionReasonBlock] = Field(default_factory=list)


class PostOrderRequest(BaseModel):
    """Normalized order-post request."""

    market_ref: str
    outcome: str
    side: str
    price: str
    size: str
    order_type: str = "gtc"
    expires_at: str | None = None
    post_only: bool = False
    live: bool = False
    confirm: bool = False


class PostOrderResponse(BaseModel):
    """Paper or live order-post response."""

    request: PostOrderRequest
    auth: AuthContext
    market: DryRunResolvedMarket | None = None
    book_context: DryRunBookContext | None = None
    post_context: DryRunPostContext = Field(default_factory=DryRunPostContext)
    signed_order: dict[str, Any] | None = None
    mode: str
    decision: str
    plan_id: str
    result_id: str | None = None
    live_response: dict[str, Any] | None = None
    reasons: list[ExecutionReasonBlock] = Field(default_factory=list)


class NormalizedOrder(BaseModel):
    """Deterministic authenticated order view."""

    order_id: str | None = None
    market: str | None = None
    asset_id: str | None = None
    side: str | None = None
    status: str | None = None
    price: str | None = None
    size: str | None = None
    original_size: str | None = None
    remaining_size: str | None = None
    created_at: str | None = None
    expiration: str | None = None
    order_type: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class OpenOrdersResponse(BaseModel):
    """Authenticated open-order listing response."""

    auth: AuthContext
    items: list[NormalizedOrder] = Field(default_factory=list)
    total: int = 0


class OrderGetResponse(BaseModel):
    """Authenticated single-order response."""

    auth: AuthContext
    order: NormalizedOrder


class ExecutionMutationResponse(BaseModel):
    """Paper or live cancellation-style mutation response."""

    auth: AuthContext
    action: str
    mode: str
    decision: str
    plan_id: str
    result_id: str | None = None
    order_id: str | None = None
    market: str | None = None
    token_id: str | None = None
    response: dict[str, Any] | list[Any] | None = None
    reasons: list[ExecutionReasonBlock] = Field(default_factory=list)


class ApprovalPlanRecord(BaseModel):
    """Append-only approval preview or live plan record."""

    plan_id: str
    asset: str
    mode: str
    decision: str
    created_at: str
    target_contract_address: str | None = None
    exchange_address: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    reasons: list[ExecutionReasonBlock] = Field(default_factory=list)


class ApprovalResultRecord(BaseModel):
    """Append-only approval result record."""

    result_id: str
    plan_id: str
    asset: str
    mode: str
    decision: str
    created_at: str
    response: dict[str, Any] | None = None


class ExecutionOrderPlanRecord(BaseModel):
    """Append-only post or cancel execution plan record."""

    plan_id: str
    action: str
    mode: str
    decision: str
    created_at: str
    order_id: str | None = None
    market: str | None = None
    token_id: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    signed_order: dict[str, Any] | None = None
    reasons: list[ExecutionReasonBlock] = Field(default_factory=list)


class ExecutionOrderResultRecord(BaseModel):
    """Append-only post or cancel execution result record."""

    result_id: str
    plan_id: str
    action: str
    mode: str
    decision: str
    created_at: str
    response: dict[str, Any] | list[Any] | None = None


class ApprovalPlansFile(BaseModel):
    """Versioned local approval-plan state document."""

    version: int = 1
    plans: list[ApprovalPlanRecord] = Field(default_factory=list)


class ApprovalResultsFile(BaseModel):
    """Versioned local approval-result state document."""

    version: int = 1
    results: list[ApprovalResultRecord] = Field(default_factory=list)


class ExecutionOrderPlansFile(BaseModel):
    """Versioned local order-plan state document."""

    version: int = 1
    plans: list[ExecutionOrderPlanRecord] = Field(default_factory=list)


class ExecutionOrderResultsFile(BaseModel):
    """Versioned local order-result state document."""

    version: int = 1
    results: list[ExecutionOrderResultRecord] = Field(default_factory=list)
