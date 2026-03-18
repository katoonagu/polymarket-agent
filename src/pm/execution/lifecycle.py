"""Approval and order lifecycle service for paper-default and live-gated execution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from py_clob_client.clob_types import (  # type: ignore[import-untyped]
    AssetType,
    BalanceAllowanceParams,
    OpenOrderParams,
    OrderArgs,
    OrderType,
    PartialCreateOrderOptions,
)
from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore[import-untyped]

from pm.auth import AuthClientError, AuthService, AuthValidationError
from pm.auth.models import BalanceAllowanceView
from pm.execution.exceptions import ExecutionValidationError
from pm.execution.models import (
    ApprovalAssetStatus,
    ApprovalCheckResponse,
    ApprovalPlanRecord,
    ApprovalResultRecord,
    ApprovalSetRequest,
    ApprovalSetResponse,
    DryRunPostContext,
    ExecutionMutationResponse,
    ExecutionOrderPlanRecord,
    ExecutionOrderResultRecord,
    ExecutionReasonBlock,
    NormalizedOrder,
    OpenOrdersResponse,
    OrderGetResponse,
    PostOrderRequest,
    PostOrderResponse,
)
from pm.execution.service import (
    DryRunService,
    decimal_or_none,
    normalize_side,
    normalize_signed_order,
)
from pm.execution.state import ExecutionStateService


class OrderLifecycleService:
    """Authenticated paper/live execution lifecycle service."""

    def __init__(
        self,
        *,
        auth_service: AuthService | None = None,
        dry_run_service: DryRunService | None = None,
        state_service: ExecutionStateService | None = None,
    ) -> None:
        self._auth_service = auth_service or AuthService()
        self._dry_run_service = dry_run_service or DryRunService(auth_service=self._auth_service)
        self._state_service = state_service or ExecutionStateService()

    def check_approvals(self) -> ApprovalCheckResponse:
        """Return current approval readiness for collateral and conditional tokens."""
        settings = self._auth_service.require_valid_config()
        auth = self._auth_service._context_from_settings(settings)
        client = self._auth_service.build_level_2_client(settings)
        exchange_address = _string_or_none(client.get_exchange_address(False))

        usdc_payload = client.get_balance_allowance(
            BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=settings.signature_type,
            )
        )
        ctf_payload = client.get_balance_allowance(
            BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                signature_type=settings.signature_type,
            )
        )

        items = [
            ApprovalAssetStatus(
                asset="usdc",
                asset_type="COLLATERAL",
                balance_view=_balance_allowance_view(
                    usdc_payload,
                    asset_type="COLLATERAL",
                    signature_type=settings.signature_type,
                ),
                target_contract_address=_string_or_none(client.get_collateral_address()),
                exchange_address=exchange_address,
                ready=_positive_decimal(_raw_value(usdc_payload, "allowance"))
                and _positive_decimal(_raw_value(usdc_payload, "balance")),
            ),
            ApprovalAssetStatus(
                asset="ctf",
                asset_type="CONDITIONAL",
                balance_view=_balance_allowance_view(
                    ctf_payload,
                    asset_type="CONDITIONAL",
                    signature_type=settings.signature_type,
                ),
                target_contract_address=_string_or_none(client.get_conditional_address()),
                exchange_address=exchange_address,
                ready=_positive_decimal(_raw_value(ctf_payload, "allowance")),
            ),
        ]
        return ApprovalCheckResponse(auth=auth, items=items, total=len(items))

    def set_approval(
        self,
        *,
        asset: str,
        live: bool = False,
        confirm: bool = False,
    ) -> ApprovalSetResponse:
        """Preview or perform an allowance update."""
        normalized_asset = _normalize_asset(asset)
        if live and not confirm:
            raise ExecutionValidationError(
                "Live approval writes require both --live and --confirm."
            )

        settings = self._auth_service.require_valid_config()
        auth = self._auth_service._context_from_settings(settings)
        client = self._auth_service.build_level_2_client(settings)
        asset_type = AssetType.COLLATERAL if normalized_asset == "usdc" else AssetType.CONDITIONAL
        payload = client.get_balance_allowance(
            BalanceAllowanceParams(
                asset_type=asset_type,
                signature_type=settings.signature_type,
            )
        )
        asset_status = ApprovalAssetStatus(
            asset=normalized_asset,
            asset_type="COLLATERAL" if normalized_asset == "usdc" else "CONDITIONAL",
            balance_view=_balance_allowance_view(
                payload,
                asset_type="COLLATERAL" if normalized_asset == "usdc" else "CONDITIONAL",
                signature_type=settings.signature_type,
            ),
            target_contract_address=_string_or_none(
                client.get_collateral_address()
                if normalized_asset == "usdc"
                else client.get_conditional_address()
            ),
            exchange_address=_string_or_none(client.get_exchange_address(False)),
            ready=_positive_decimal(_raw_value(payload, "allowance"))
            and (normalized_asset != "usdc" or _positive_decimal(_raw_value(payload, "balance"))),
        )

        reasons: list[ExecutionReasonBlock] = [
            ExecutionReasonBlock(
                section="auth_config",
                status="pass",
                message="Authenticated configuration is present and parseable.",
            )
        ]
        if _positive_decimal(asset_status.balance_view.allowance):
            reasons.append(
                ExecutionReasonBlock(
                    section="allowance",
                    status="fail",
                    message=f"{normalized_asset} allowance already appears to be set.",
                )
            )
            decision = "SKIP"
        else:
            reasons.append(
                ExecutionReasonBlock(
                    section="allowance",
                    status="pass",
                    message=f"{normalized_asset} allowance can be updated.",
                )
            )
            decision = "SET" if live else "WOULD_SET"

        plan_id = _make_id("approval_plan")
        self._state_service.append_approval_plan(
            ApprovalPlanRecord(
                plan_id=plan_id,
                asset=normalized_asset,
                mode="live" if live else "preview",
                decision=decision,
                created_at=_utc_now(),
                target_contract_address=asset_status.target_contract_address,
                exchange_address=asset_status.exchange_address,
                request=ApprovalSetRequest(
                    asset=normalized_asset,
                    live=live,
                    confirm=confirm,
                ).model_dump(mode="json"),
                reasons=reasons,
            )
        )

        live_response: dict[str, Any] | None = None
        result_id: str | None = None
        if live:
            if decision != "SKIP":
                geoblock = self._auth_service.check_geoblock()
                if not geoblock.checked or geoblock.blocked is True:
                    reasons.append(
                        ExecutionReasonBlock(
                            section="geoblock",
                            status="fail",
                            message=geoblock.message
                            or "Official geoblock endpoint blocked or could not verify access.",
                        )
                    )
                    decision = "SKIP"
                else:
                    reasons.append(
                        ExecutionReasonBlock(
                            section="geoblock",
                            status="pass",
                            message=geoblock.message
                            or "Official geoblock endpoint reported allowed access.",
                        )
                    )
                    response = client.update_balance_allowance(
                        BalanceAllowanceParams(
                            asset_type=asset_type,
                            signature_type=settings.signature_type,
                        )
                    )
                    live_response = _normalize_dict_response(response)
            result_id = _make_id("approval_result")
            self._state_service.append_approval_result(
                ApprovalResultRecord(
                    result_id=result_id,
                    plan_id=plan_id,
                    asset=normalized_asset,
                    mode="live",
                    decision=decision,
                    created_at=_utc_now(),
                    response=live_response,
                )
            )

        return ApprovalSetResponse(
            request=ApprovalSetRequest(asset=normalized_asset, live=live, confirm=confirm),
            auth=auth,
            asset_status=asset_status,
            mode="live" if live else "preview",
            decision=decision,
            plan_id=plan_id,
            result_id=result_id,
            live_response=live_response,
            reasons=reasons,
        )

    def post(
        self,
        *,
        market_ref: str,
        outcome: str,
        side: str,
        price: str,
        size: str,
        order_type: str = "gtc",
        expires_at: str | None = None,
        post_only: bool = False,
        live: bool = False,
        confirm: bool = False,
    ) -> PostOrderResponse:
        """Preview or submit one order."""
        normalized_type = _normalize_order_type(order_type)
        if live and not confirm:
            raise ExecutionValidationError("Live order posting requires both --live and --confirm.")
        if normalized_type == "gtd" and expires_at is None:
            raise ExecutionValidationError("GTD orders require --expires-at.")
        if normalized_type != "gtd" and expires_at is not None:
            raise ExecutionValidationError("--expires-at is only valid with --order-type gtd.")
        if post_only and normalized_type == "fok":
            raise ExecutionValidationError("--post-only is only allowed for gtc and gtd orders.")

        expiration = _parse_expiration(expires_at)
        plan = self._dry_run_service.plan_order(
            market_ref=market_ref,
            outcome=outcome,
            side=side,
            price=price,
            size=size,
            order_type=normalized_type.upper(),
            post_only=post_only,
            expires_at=expires_at,
            expiration=expiration,
        )
        reasons = list(plan.reasons)
        request = PostOrderRequest(
            market_ref=market_ref.strip(),
            outcome=plan.request.outcome,
            side=plan.request.side,
            price=plan.request.price,
            size=plan.request.size,
            order_type=normalized_type,
            expires_at=expires_at,
            post_only=post_only,
            live=live,
            confirm=confirm,
        )

        settings: Any | None = None
        if plan.decision == "WOULD_POST":
            try:
                settings = self._auth_service.require_valid_config()
                client = self._auth_service.build_level_2_client(settings)
            except (AuthValidationError, AuthClientError) as exc:
                reasons.append(
                    ExecutionReasonBlock(
                        section="auth_client",
                        status="fail",
                        message=str(exc),
                    )
                )
                plan = plan.model_copy(update={"decision": "SKIP"})
                client = None

            if plan.decision == "WOULD_POST" and client is not None and plan.market is not None:
                balance_reasons = self._balance_allowance_reasons(
                    client=client,
                    settings=settings,
                    market=plan.market,
                    side=request.side,
                    price=request.price,
                    size=request.size,
                )
                reasons.extend(balance_reasons)
                if any(
                    item.section in {"balance", "allowance"} and item.status == "fail"
                    for item in balance_reasons
                ):
                    plan = plan.model_copy(update={"decision": "SKIP"})

        signed_order_payload: dict[str, Any] | None = None
        signed_order_obj: Any | None = None
        if plan.decision == "WOULD_POST" and plan.market is not None and settings is not None:
            try:
                order_client = self._auth_service.build_level_2_client(settings)
                signed_order_obj = self._create_signed_order(
                    client=order_client,
                    token_id=plan.market.token_id or "",
                    side=request.side,
                    price=request.price,
                    size=request.size,
                    fee_rate_bps=plan.market.fee_rate_bps or 0,
                    tick_size=plan.market.tick_size or "0.01",
                    neg_risk=bool(plan.market.neg_risk),
                    expiration=expiration,
                )
                signed_order_payload = normalize_signed_order(signed_order_obj.dict())
            except Exception as exc:
                reasons.append(
                    ExecutionReasonBlock(
                        section="local_signing",
                        status="fail",
                        message=f"Local order signing failed: {exc}",
                    )
                )
                plan = plan.model_copy(update={"decision": "SKIP"})

        decision = plan.decision
        live_response: dict[str, Any] | None = None
        if live and decision == "WOULD_POST":
            geoblock = self._auth_service.check_geoblock()
            if not geoblock.checked or geoblock.blocked is True:
                reasons.append(
                    ExecutionReasonBlock(
                        section="geoblock",
                        status="fail",
                        message=geoblock.message
                        or "Official geoblock endpoint blocked or could not verify access.",
                    )
                )
                decision = "SKIP"
            else:
                reasons.append(
                    ExecutionReasonBlock(
                        section="geoblock",
                        status="pass",
                        message=geoblock.message
                        or "Official geoblock endpoint reported allowed access.",
                    )
                )
                live_client = self._auth_service.build_level_2_client(settings)
                post_result = live_client.post_order(
                    signed_order_obj,
                    orderType=_sdk_order_type(normalized_type),
                    post_only=post_only,
                )
                order_id = _extract_order_id(post_result)
                fetched_order = (
                    _normalize_order(live_client.get_order(order_id))
                    if order_id is not None
                    else None
                )
                live_response = {
                    "post_result": _normalize_response_payload(post_result),
                    "order": fetched_order.model_dump(mode="json") if fetched_order else None,
                }
                decision = "POSTED"

        plan_id = _make_id("execution_plan")
        result_id = _make_id("execution_result")
        self._state_service.append_order_plan(
            ExecutionOrderPlanRecord(
                plan_id=plan_id,
                action="post",
                mode="live" if live else "paper",
                decision=decision if decision != "POSTED" else "WOULD_POST",
                created_at=_utc_now(),
                market=plan.market.condition_id if plan.market is not None else None,
                token_id=plan.market.token_id if plan.market is not None else None,
                request=request.model_dump(mode="json"),
                signed_order=signed_order_payload,
                reasons=reasons,
            )
        )
        self._state_service.append_order_result(
            ExecutionOrderResultRecord(
                result_id=result_id,
                plan_id=plan_id,
                action="post",
                mode="live" if live else "paper",
                decision=decision,
                created_at=_utc_now(),
                response=live_response,
            )
        )
        return PostOrderResponse(
            request=request,
            auth=plan.auth,
            market=plan.market,
            book_context=plan.book_context,
            post_context=DryRunPostContext(
                order_type=normalized_type.upper(),
                post_only=post_only,
                submit_mode="live" if live else "paper",
                expires_at=expires_at,
            ),
            signed_order=signed_order_payload,
            mode="live" if live else "paper",
            decision=decision if live else ("WOULD_POST" if decision == "WOULD_POST" else "SKIP"),
            plan_id=plan_id,
            result_id=result_id,
            live_response=live_response,
            reasons=reasons,
        )

    def orders_open(
        self,
        *,
        market: str | None = None,
        token_id: str | None = None,
    ) -> OpenOrdersResponse:
        """Return authenticated open orders."""
        settings = self._auth_service.require_valid_config()
        auth = self._auth_service._context_from_settings(settings)
        client = self._auth_service.build_level_2_client(settings)
        params = None
        if market or token_id:
            params = OpenOrderParams(market=market, asset_id=token_id)
        payload = client.get_orders(params)
        items = [_normalize_order(item) for item in payload]
        return OpenOrdersResponse(auth=auth, items=items, total=len(items))

    def order_get(self, *, order_id: str) -> OrderGetResponse:
        """Return one authenticated order by id."""
        normalized_order_id = order_id.strip()
        if not normalized_order_id:
            raise ExecutionValidationError("Order id is required.")
        settings = self._auth_service.require_valid_config()
        auth = self._auth_service._context_from_settings(settings)
        client = self._auth_service.build_level_2_client(settings)
        payload = client.get_order(normalized_order_id)
        return OrderGetResponse(auth=auth, order=_normalize_order(payload))

    def cancel(
        self,
        *,
        order_id: str,
        live: bool = False,
        confirm: bool = False,
    ) -> ExecutionMutationResponse:
        """Preview or cancel one order."""
        normalized_order_id = order_id.strip()
        if not normalized_order_id:
            raise ExecutionValidationError("Order id is required.")
        if live and not confirm:
            raise ExecutionValidationError(
                "Live order cancellation requires both --live and --confirm."
            )
        return self._cancel_common(
            action="cancel",
            live=live,
            confirm=confirm,
            order_id=normalized_order_id,
        )

    def cancel_all(
        self,
        *,
        live: bool = False,
        confirm: bool = False,
    ) -> ExecutionMutationResponse:
        """Preview or cancel all orders."""
        if live and not confirm:
            raise ExecutionValidationError(
                "Live order cancellation requires both --live and --confirm."
            )
        return self._cancel_common(action="cancel_all", live=live, confirm=confirm)

    def cancel_market(
        self,
        *,
        market: str,
        token_id: str | None = None,
        live: bool = False,
        confirm: bool = False,
    ) -> ExecutionMutationResponse:
        """Preview or cancel market-scoped orders."""
        normalized_market = market.strip()
        if not normalized_market:
            raise ExecutionValidationError("Market condition id is required.")
        if live and not confirm:
            raise ExecutionValidationError(
                "Live order cancellation requires both --live and --confirm."
            )
        return self._cancel_common(
            action="cancel_market",
            live=live,
            confirm=confirm,
            market=normalized_market,
            token_id=token_id.strip() if token_id else None,
        )

    def _cancel_common(
        self,
        *,
        action: str,
        live: bool,
        confirm: bool,
        order_id: str | None = None,
        market: str | None = None,
        token_id: str | None = None,
    ) -> ExecutionMutationResponse:
        settings = self._auth_service.require_valid_config()
        auth = self._auth_service._context_from_settings(settings)
        reasons = [
            ExecutionReasonBlock(
                section="auth_config",
                status="pass",
                message="Authenticated configuration is present and parseable.",
            )
        ]
        decision = {
            "cancel": "WOULD_CANCEL",
            "cancel_all": "WOULD_CANCEL_ALL",
            "cancel_market": "WOULD_CANCEL_MARKET",
        }[action]
        response_payload: dict[str, Any] | list[Any] | None = None

        if live:
            geoblock = self._auth_service.check_geoblock()
            if not geoblock.checked or geoblock.blocked is True:
                reasons.append(
                    ExecutionReasonBlock(
                        section="geoblock",
                        status="fail",
                        message=geoblock.message
                        or "Official geoblock endpoint blocked or could not verify access.",
                    )
                )
                decision = "SKIP"
            else:
                reasons.append(
                    ExecutionReasonBlock(
                        section="geoblock",
                        status="pass",
                        message=geoblock.message
                        or "Official geoblock endpoint reported allowed access.",
                    )
                )
                client = self._auth_service.build_level_2_client(settings)
                if action == "cancel":
                    response_payload = _normalize_response_payload(client.cancel(order_id or ""))
                elif action == "cancel_all":
                    response_payload = _normalize_response_payload(client.cancel_all())
                else:
                    response_payload = _normalize_response_payload(
                        client.cancel_market_orders(market=market or "", asset_id=token_id or "")
                    )
                decision = "CANCELLED"

        plan_id = _make_id("execution_plan")
        result_id = _make_id("execution_result")
        self._state_service.append_order_plan(
            ExecutionOrderPlanRecord(
                plan_id=plan_id,
                action=action,
                mode="live" if live else "paper",
                decision=decision if decision != "CANCELLED" else {
                    "cancel": "WOULD_CANCEL",
                    "cancel_all": "WOULD_CANCEL_ALL",
                    "cancel_market": "WOULD_CANCEL_MARKET",
                }[action],
                created_at=_utc_now(),
                order_id=order_id,
                market=market,
                token_id=token_id,
                request={
                    "order_id": order_id,
                    "market": market,
                    "token_id": token_id,
                    "live": live,
                    "confirm": confirm,
                },
                reasons=reasons,
            )
        )
        self._state_service.append_order_result(
            ExecutionOrderResultRecord(
                result_id=result_id,
                plan_id=plan_id,
                action=action,
                mode="live" if live else "paper",
                decision=decision,
                created_at=_utc_now(),
                response=response_payload,
            )
        )
        return ExecutionMutationResponse(
            auth=auth,
            action=action,
            mode="live" if live else "paper",
            decision=decision,
            plan_id=plan_id,
            result_id=result_id,
            order_id=order_id,
            market=market,
            token_id=token_id,
            response=response_payload,
            reasons=reasons,
        )

    def _balance_allowance_reasons(
        self,
        *,
        client: Any,
        settings: Any,
        market: Any,
        side: str,
        price: str,
        size: str,
    ) -> list[ExecutionReasonBlock]:
        normalized_side = normalize_side(side)
        required_amount = (
            Decimal(price) * Decimal(size)
            if normalized_side == "buy"
            else Decimal(size)
        )
        if normalized_side == "buy":
            payload = client.get_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=settings.signature_type,
                )
            )
            asset_label = "collateral"
        else:
            payload = client.get_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.CONDITIONAL,
                    token_id=market.token_id,
                    signature_type=settings.signature_type,
                )
            )
            asset_label = "conditional token"

        balance_value = decimal_or_none(_raw_value(payload, "balance"))
        allowance_value = decimal_or_none(_raw_value(payload, "allowance"))
        reasons: list[ExecutionReasonBlock] = []
        if balance_value is None or balance_value < required_amount:
            reasons.append(
                ExecutionReasonBlock(
                    section="balance",
                    status="fail",
                    message=f"Insufficient {asset_label} balance for requested order size.",
                )
            )
        else:
            reasons.append(
                ExecutionReasonBlock(
                    section="balance",
                    status="pass",
                    message=f"Balance covers required amount {required_amount}.",
                )
            )
        if allowance_value is None or allowance_value < required_amount:
            reasons.append(
                ExecutionReasonBlock(
                    section="allowance",
                    status="fail",
                    message=f"Insufficient {asset_label} allowance for requested order size.",
                )
            )
        else:
            reasons.append(
                ExecutionReasonBlock(
                    section="allowance",
                    status="pass",
                    message=f"Allowance covers required amount {required_amount}.",
                )
            )
        return reasons

    def _create_signed_order(
        self,
        *,
        client: Any,
        token_id: str,
        side: str,
        price: str,
        size: str,
        fee_rate_bps: int,
        tick_size: str,
        neg_risk: bool,
        expiration: int,
    ) -> Any:
        return client.create_order(
            OrderArgs(
                token_id=token_id,
                price=float(Decimal(price)),
                size=float(Decimal(size)),
                side=BUY if normalize_side(side) == "buy" else SELL,
                fee_rate_bps=fee_rate_bps,
                nonce=0,
                expiration=expiration,
            ),
            PartialCreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )


def _normalize_asset(asset: str) -> str:
    normalized = asset.strip().lower()
    if normalized not in {"usdc", "ctf"}:
        raise ExecutionValidationError("Asset must be one of: usdc, ctf.")
    return normalized


def _normalize_order_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"gtc", "gtd", "fok"}:
        raise ExecutionValidationError("Order type must be one of: gtc, gtd, fok.")
    return normalized


def _sdk_order_type(value: str) -> Any:
    if value == "gtc":
        return OrderType.GTC
    if value == "gtd":
        return OrderType.GTD
    return OrderType.FOK


def _parse_expiration(value: str | None) -> int:
    if value is None:
        return 0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionValidationError("--expires-at must be a valid ISO8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _balance_allowance_view(
    payload: dict[str, Any],
    *,
    asset_type: str,
    signature_type: int,
) -> BalanceAllowanceView:
    return BalanceAllowanceView(
        asset_type=asset_type,
        token_id=_string_or_none(payload.get("token_id"))
        or _string_or_none(payload.get("tokenId")),
        signature_type=signature_type,
        balance=_raw_value(payload, "balance"),
        allowance=_raw_value(payload, "allowance"),
    )


def _raw_value(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _positive_decimal(value: str | None) -> bool:
    parsed = decimal_or_none(value)
    return parsed is not None and parsed > 0


def _normalize_response_payload(payload: Any) -> dict[str, Any] | list[Any] | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return {str(key): _normalize_json_value(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_normalize_json_value(item) for item in payload]
    return {"value": _normalize_json_value(payload)}


def _normalize_order(payload: Any) -> NormalizedOrder:
    if not isinstance(payload, dict):
        return NormalizedOrder(raw={"value": str(payload)})
    normalized_raw = _normalize_response_payload(payload)
    return NormalizedOrder(
        order_id=_string_or_none(payload.get("id"))
        or _string_or_none(payload.get("orderID")),
        market=_string_or_none(payload.get("market")),
        asset_id=_string_or_none(payload.get("asset_id"))
        or _string_or_none(payload.get("assetId")),
        side=_string_or_none(payload.get("side")),
        status=_string_or_none(payload.get("status")),
        price=_raw_value(payload, "price"),
        size=_raw_value(payload, "size"),
        original_size=_raw_value(payload, "original_size")
        or _raw_value(payload, "originalSize"),
        remaining_size=_raw_value(payload, "size_matched")
        or _raw_value(payload, "remaining_size")
        or _raw_value(payload, "remainingSize"),
        created_at=_string_or_none(payload.get("created_at"))
        or _string_or_none(payload.get("createdAt")),
        expiration=_raw_value(payload, "expiration"),
        order_type=_string_or_none(payload.get("order_type"))
        or _string_or_none(payload.get("type")),
        raw=normalized_raw if isinstance(normalized_raw, dict) else {},
    )


def _normalize_dict_response(payload: Any) -> dict[str, Any] | None:
    normalized = _normalize_response_payload(payload)
    if normalized is None:
        return None
    if isinstance(normalized, dict):
        return normalized
    return {"items": normalized}


def _normalize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return str(value)


def _extract_order_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        return _string_or_none(payload.get("orderID")) or _string_or_none(payload.get("id"))
    return None


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
