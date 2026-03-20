"""Authenticated dry-run order planning and local signing service."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from py_clob_client.clob_types import (  # type: ignore[import-untyped]
    OrderArgs,
    PartialCreateOrderOptions,
)
from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore[import-untyped]

from pm.auth import AuthService, AuthValidationError
from pm.execution.exceptions import ExecutionValidationError
from pm.execution.models import (
    DryRunBookContext,
    DryRunPostContext,
    DryRunRequest,
    DryRunResolvedMarket,
    DryRunResponse,
    ExecutionReasonBlock,
)
from pm.market import ClobClient as PublicClobClient
from pm.market import ClobClientError, GammaClient, GammaClientError, GammaNotFoundError
from pm.market.models import NormalizedBook, NormalizedMarket


class DryRunService:
    """Build and sign non-live orders locally without posting them."""

    def __init__(
        self,
        *,
        auth_service: AuthService | None = None,
        gamma_client: GammaClient | None = None,
        clob_client: PublicClobClient | None = None,
    ) -> None:
        self._auth_service = auth_service or AuthService()
        self._gamma_client = gamma_client
        self._clob_client = clob_client

    def dry_run(
        self,
        *,
        market_ref: str,
        outcome: str,
        side: str,
        price: str,
        size: str,
    ) -> DryRunResponse:
        """Build a deterministic non-live dry-run order plan."""
        return self.plan_order(
            market_ref=market_ref,
            outcome=outcome,
            side=side,
            price=price,
            size=size,
        )

    def plan_order(
        self,
        *,
        market_ref: str,
        outcome: str,
        side: str,
        price: str,
        size: str,
        order_type: str = "GTC",
        post_only: bool = False,
        expires_at: str | None = None,
        expiration: int = 0,
    ) -> DryRunResponse:
        """Build a deterministic non-live dry-run order plan with post metadata."""
        normalized_outcome = normalize_outcome(outcome)
        normalized_side = normalize_side(side)
        request = DryRunRequest(
            market_ref=market_ref.strip(),
            outcome=normalized_outcome,
            side=normalized_side,
            price=str(price),
            size=str(size),
        )

        show_response = self._auth_service.show()
        auth_context = show_response.auth
        reasons: list[ExecutionReasonBlock] = []

        try:
            settings = self._auth_service.require_valid_config()
            auth_context = self._auth_service._context_from_settings(settings)
            reasons.append(
                ExecutionReasonBlock(
                    section="auth_config",
                    status="pass",
                    message="Authenticated configuration is present and parseable.",
                )
            )
        except AuthValidationError as exc:
            reasons.append(
                ExecutionReasonBlock(
                    section="auth_config",
                    status="fail",
                    message=str(exc),
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        geoblock = self._auth_service.check_geoblock()
        if not geoblock.checked:
            reasons.append(
                ExecutionReasonBlock(
                    section="geoblock",
                    status="fail",
                    message=geoblock.message or "Official geoblock check could not be verified.",
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )
        if geoblock.blocked is True:
            reasons.append(
                ExecutionReasonBlock(
                    section="geoblock",
                    status="fail",
                    message=(
                        geoblock.message
                        or "Official geoblock endpoint reported blocked access."
                    ),
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )
        reasons.append(
            ExecutionReasonBlock(
                section="geoblock",
                status="pass",
                message=geoblock.message or "Official geoblock endpoint reported allowed access.",
            )
        )

        market = self.resolve_market(request.market_ref)
        if market is None:
            reasons.append(
                ExecutionReasonBlock(
                    section="market",
                    status="fail",
                    message=f"Market '{request.market_ref}' was not found.",
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        token_id = resolve_token_id(market, normalized_outcome)
        market_view = DryRunResolvedMarket(
            market_slug=market.market_slug,
            condition_id=market.condition_id,
            question=market.question,
            token_id=token_id,
            outcome=normalized_outcome,
            active=market.active,
            closed=market.closed,
        )
        if token_id is None:
            reasons.append(
                ExecutionReasonBlock(
                    section="outcome_mapping",
                    status="fail",
                    message=f"Outcome '{normalized_outcome}' could not be mapped to a token id.",
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        if not market.active or market.closed:
            reasons.append(
                ExecutionReasonBlock(
                    section="market_state",
                    status="fail",
                    message="Market is inactive or closed.",
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        try:
            book, midpoint, spread = self._load_public_book_context(token_id)
        except ClobClientError as exc:
            reasons.append(
                ExecutionReasonBlock(
                    section="book_context",
                    status="fail",
                    message=str(exc),
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        book_context = DryRunBookContext(
            best_bid=book.bids[0].price if book.bids else None,
            best_ask=book.asks[0].price if book.asks else None,
            midpoint=midpoint,
            spread=spread,
            bid_level_count=len(book.bids),
            ask_level_count=len(book.asks),
        )
        reasons.append(
            ExecutionReasonBlock(
                section="book_context",
                status="pass",
                message="Public book, midpoint, and spread context loaded successfully.",
            )
        )

        try:
            price_decimal = Decimal(request.price)
            size_decimal = Decimal(request.size)
        except (InvalidOperation, TypeError) as exc:
            raise ExecutionValidationError("Price and size must be valid decimal values.") from exc
        if price_decimal <= 0:
            raise ExecutionValidationError("Price must be greater than zero.")
        if size_decimal <= 0:
            raise ExecutionValidationError("Size must be greater than zero.")

        try:
            sdk_client = self._auth_service.build_level_1_client(settings)
            tick_size = str(sdk_client.get_tick_size(token_id))
            fee_rate_bps = int(sdk_client.get_fee_rate_bps(token_id))
            neg_risk = bool(sdk_client.get_neg_risk(token_id))
        except Exception as exc:
            reasons.append(
                ExecutionReasonBlock(
                    section="execution_context",
                    status="fail",
                    message=str(exc),
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                book_context=book_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        market_view.tick_size = tick_size
        market_view.fee_rate_bps = fee_rate_bps
        market_view.neg_risk = neg_risk
        market_view.min_order_size = book.min_order_size or (
            str(market.min_order_size) if market.min_order_size is not None else None
        )

        tick_decimal = Decimal(tick_size)
        if (price_decimal % tick_decimal) != 0:
            reasons.append(
                ExecutionReasonBlock(
                    section="tick_size",
                    status="fail",
                    message=f"Price {price_decimal} is not aligned to tick size {tick_size}.",
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                book_context=book_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        max_price = Decimal("1") - tick_decimal
        if price_decimal < tick_decimal or price_decimal > max_price:
            reasons.append(
                ExecutionReasonBlock(
                    section="price_range",
                    status="fail",
                    message=f"Price must be between {tick_size} and {max_price}.",
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                book_context=book_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        min_order_size = decimal_or_none(market_view.min_order_size)
        if min_order_size is not None and size_decimal < min_order_size:
            reasons.append(
                ExecutionReasonBlock(
                    section="min_order_size",
                    status="fail",
                    message=(
                        f"Size {size_decimal} is below min order size {market_view.min_order_size}."
                    ),
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                book_context=book_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        reasons.extend(
            [
                ExecutionReasonBlock(
                    section="tick_size",
                    status="pass",
                    message=f"Price aligns to tick size {tick_size}.",
                ),
                ExecutionReasonBlock(
                    section="fee_rate",
                    status="pass",
                    message=f"Resolved fee rate to {fee_rate_bps} bps.",
                ),
            ]
        )

        try:
            signed_order = sdk_client.create_order(
                OrderArgs(
                    token_id=token_id,
                    price=float(price_decimal),
                    size=float(size_decimal),
                    side=BUY if normalized_side == "buy" else SELL,
                    fee_rate_bps=fee_rate_bps,
                    nonce=0,
                    expiration=expiration,
                ),
                PartialCreateOrderOptions(
                    tick_size=tick_size,
                    neg_risk=neg_risk,
                ),
            )
        except Exception as exc:
            reasons.append(
                ExecutionReasonBlock(
                    section="local_signing",
                    status="fail",
                    message=f"Local order signing failed: {exc}",
                )
            )
            return DryRunResponse(
                request=request,
                auth=auth_context,
                market=market_view,
                book_context=book_context,
                post_context=DryRunPostContext(
                    order_type=order_type.upper(),
                    post_only=post_only,
                    submit_mode="dry_run_only",
                    expires_at=expires_at,
                ),
                decision="SKIP",
                reasons=reasons,
            )

        reasons.append(
            ExecutionReasonBlock(
                section="local_signing",
                status="pass",
                message="Order was built and signed locally without submission.",
            )
        )
        return DryRunResponse(
            request=request,
            auth=auth_context,
            market=market_view,
            book_context=book_context,
            post_context=DryRunPostContext(
                order_type=order_type.upper(),
                post_only=post_only,
                submit_mode="dry_run_only",
                expires_at=expires_at,
            ),
            signed_order=normalize_signed_order(signed_order.dict()),
            decision="WOULD_POST",
            reasons=reasons,
        )

    def resolve_market(self, market_ref: str) -> NormalizedMarket | None:
        """Resolve one market from a slug or condition id."""
        normalized = market_ref.strip()
        if not normalized:
            raise ExecutionValidationError("Market reference is required.")

        owns_client = self._gamma_client is None
        client = self._gamma_client or GammaClient()
        try:
            try:
                if looks_like_condition_id(normalized):
                    return client.get_market_by_condition_id(normalized)
                return client.get_market_by_slug(normalized)
            except GammaNotFoundError:
                return None
            except GammaClientError as exc:
                raise ExecutionValidationError(str(exc)) from exc
        finally:
            if owns_client:
                client.close()

    def load_public_book_context(
        self,
        token_id: str,
    ) -> tuple[NormalizedBook, str | None, str | None]:
        """Load public book, midpoint, and spread for one token."""
        return self._load_public_book_context(token_id)

    def _load_public_book_context(
        self,
        token_id: str,
    ) -> tuple[NormalizedBook, str | None, str | None]:
        owns_client = self._clob_client is None
        client = self._clob_client or PublicClobClient()
        try:
            book = client.get_book(token_id)
            midpoint = client.get_midpoint(token_id).midpoint
            spread = client.get_spread(token_id).spread
            return book, midpoint, spread
        finally:
            if owns_client:
                client.close()


def normalize_outcome(value: str) -> str:
    """Normalize a yes/no or up/down outcome token."""
    normalized = value.strip().lower()
    if normalized not in {"yes", "no", "up", "down"}:
        raise ExecutionValidationError("Outcome must be one of: yes, no, up, down.")
    return normalized


def normalize_side(value: str) -> str:
    """Normalize a buy/sell order side."""
    normalized = value.strip().lower()
    if normalized not in {"buy", "sell"}:
        raise ExecutionValidationError("Side must be one of: buy, sell.")
    return normalized


def resolve_token_id(market: NormalizedMarket, outcome: str) -> str | None:
    """Map a normalized outcome token to a market token id."""
    normalized_outcome = outcome.lower()
    for index, market_outcome in enumerate(market.outcomes):
        market_token = market_outcome.strip().lower()
        if market_token == normalized_outcome and index < len(market.token_ids):
            return market.token_ids[index]
        if normalized_outcome == "yes" and market_token in {"yes", "up"} and index < len(
            market.token_ids
        ):
            return market.token_ids[index]
        if normalized_outcome == "no" and market_token in {"no", "down"} and index < len(
            market.token_ids
        ):
            return market.token_ids[index]
        if normalized_outcome == "up" and market_token in {"up", "yes"} and index < len(
            market.token_ids
        ):
            return market.token_ids[index]
        if normalized_outcome == "down" and market_token in {"down", "no"} and index < len(
            market.token_ids
        ):
            return market.token_ids[index]
    return None


def looks_like_condition_id(value: str) -> bool:
    """Return whether a value looks like a 32-byte hex condition id."""
    return len(value) == 66 and value.startswith("0x") and all(
        char in "0123456789abcdefABCDEF" for char in value[2:]
    )


def decimal_or_none(value: str | None) -> Decimal | None:
    """Best-effort decimal parsing for optional numeric strings."""
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def normalize_signed_order(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a signed order payload into JSON-safe primitives."""
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            normalized[key] = None
        elif isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        else:
            normalized[key] = str(value)
    return normalized
