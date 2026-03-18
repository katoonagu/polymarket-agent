from __future__ import annotations

from dataclasses import dataclass

from py_clob_client.clob_types import AssetType

from pm.auth.models import AuthContext, GeoblockStatus
from pm.execution import (
    DryRunBookContext,
    DryRunRequest,
    DryRunResolvedMarket,
    DryRunResponse,
    ExecutionReasonBlock,
    ExecutionStateService,
    ExecutionValidationError,
    OrderLifecycleService,
)


@dataclass
class FakeSettings:
    private_key: str = "0x" + ("1" * 64)
    signature_type: int = 0
    signature_type_name: str = "EOA"
    funder_address: str | None = None
    clob_host: str = "https://clob.polymarket.com"
    chain_id: int = 137


class FakeSignedOrder:
    def dict(self) -> dict[str, str | int]:
        return {
            "tokenId": "100",
            "price": "0.55",
            "size": "10",
            "signature": "signed-payload",
            "nonce": 0,
        }


class FakeLifecycleSDKClient:
    def __init__(self, *, low_allowance: bool = False) -> None:
        self.low_allowance = low_allowance

    def get_exchange_address(self, neg_risk: bool = False) -> str:
        return "0xexchange"

    def get_collateral_address(self) -> str:
        return "0xcollateral"

    def get_conditional_address(self) -> str:
        return "0xconditional"

    def get_balance_allowance(self, params: object) -> dict[str, str]:
        asset_type = getattr(params, "asset_type", None)
        token_id = getattr(params, "token_id", None)
        allowance = "0" if self.low_allowance else "100"
        if asset_type == AssetType.COLLATERAL:
            return {"balance": "100", "allowance": allowance}
        return {"balance": "25", "allowance": allowance, "token_id": token_id or "100"}

    def update_balance_allowance(self, params: object) -> dict[str, str]:
        return {"status": "ok", "txHash": "0xapprove"}

    def create_order(self, order_args: object, options: object) -> FakeSignedOrder:
        return FakeSignedOrder()

    def post_order(
        self, order: object, orderType: object = None, post_only: bool = False
    ) -> dict[str, str]:
        return {"orderID": "order-123", "status": "LIVE"}

    def get_order(self, order_id: str) -> dict[str, str]:
        return {
            "id": order_id,
            "market": "0x" + ("a" * 64),
            "asset_id": "100",
            "side": "BUY",
            "status": "OPEN",
            "price": "0.55",
            "size": "10",
        }

    def get_orders(self, params: object = None) -> list[dict[str, str]]:
        return [self.get_order("order-123")]

    def cancel(self, order_id: str) -> dict[str, list[str]]:
        return {"canceled": [order_id]}

    def cancel_all(self) -> dict[str, list[str]]:
        return {"canceled": ["order-123", "order-456"]}

    def cancel_market_orders(self, market: str = "", asset_id: str = "") -> dict[str, list[str]]:
        return {"canceled": [market, asset_id]}


class FakeLifecycleAuthService:
    def __init__(self, *, geoblocked: bool = False, low_allowance: bool = False) -> None:
        self.geoblocked = geoblocked
        self.low_allowance = low_allowance

    def require_valid_config(self) -> FakeSettings:
        return FakeSettings()

    def _context_from_settings(self, settings: FakeSettings) -> AuthContext:
        return AuthContext(
            signer_address="0x" + ("3" * 40),
            funder_address=None,
            signature_type=0,
            signature_type_name="EOA",
            clob_host="https://clob.polymarket.com",
            chain_id=137,
            private_key_present=True,
            api_key_derivation_possible=True,
        )

    def build_level_2_client(self, settings: FakeSettings | None = None) -> FakeLifecycleSDKClient:
        return FakeLifecycleSDKClient(low_allowance=self.low_allowance)

    def check_geoblock(self) -> GeoblockStatus:
        return GeoblockStatus(
            checked=not self.geoblocked,
            blocked=self.geoblocked if self.geoblocked else False,
            message="blocked" if self.geoblocked else "allowed",
        )


class FakeLifecycleDryRunService:
    def __init__(self, *, decision: str = "WOULD_POST") -> None:
        self.decision = decision

    def plan_order(self, **kwargs: object) -> DryRunResponse:
        return DryRunResponse(
            request=DryRunRequest(
                market_ref=str(kwargs["market_ref"]),
                outcome=str(kwargs["outcome"]),
                side=str(kwargs["side"]),
                price=str(kwargs["price"]),
                size=str(kwargs["size"]),
            ),
            auth=AuthContext(
                signer_address="0x" + ("3" * 40),
                funder_address=None,
                signature_type=0,
                signature_type_name="EOA",
                clob_host="https://clob.polymarket.com",
                chain_id=137,
                private_key_present=True,
                api_key_derivation_possible=True,
            ),
            market=DryRunResolvedMarket(
                market_slug="btc-above-100k",
                condition_id="0x" + ("a" * 64),
                question="Will BTC reach 100k?",
                token_id="100",
                outcome="yes",
                active=True,
                closed=False,
                tick_size="0.01",
                min_order_size="5",
                fee_rate_bps=12,
                neg_risk=False,
            ),
            book_context=DryRunBookContext(
                best_bid="0.54",
                best_ask="0.56",
                midpoint="0.55",
                spread="0.02",
                bid_level_count=1,
                ask_level_count=1,
            ),
            signed_order={"signature": "signed-payload"},
            decision=self.decision,
            reasons=[
                ExecutionReasonBlock(
                    section="local_signing",
                    status="pass",
                    message="Order was built and signed locally without submission.",
                )
            ],
        )


def _state_service(tmp_path) -> ExecutionStateService:
    return ExecutionStateService(
        approval_plans_path=tmp_path / "approval-plans.json",
        approval_results_path=tmp_path / "approval-results.json",
        order_plans_path=tmp_path / "execution-order-plans.json",
        order_results_path=tmp_path / "execution-order-results.json",
    )


def test_approval_check_returns_both_assets(tmp_path) -> None:
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=_state_service(tmp_path),
    )

    result = service.check_approvals()

    assert result.total == 2
    assert [item.asset for item in result.items] == ["usdc", "ctf"]
    assert result.items[0].ready is True


def test_approve_set_preview_persists_plan_only(tmp_path) -> None:
    state = _state_service(tmp_path)
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(low_allowance=True),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=state,
    )

    result = service.set_approval(asset="usdc")

    assert result.decision == "WOULD_SET"
    assert result.result_id is None
    assert len(state.list_approval_plans()) == 1
    assert len(state.list_approval_results()) == 0


def test_approve_set_live_geoblocked_persists_skip_result(tmp_path) -> None:
    state = _state_service(tmp_path)
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(geoblocked=True),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=state,
    )

    result = service.set_approval(asset="ctf", live=True, confirm=True)

    assert result.decision == "SKIP"
    assert result.result_id is not None
    assert len(state.list_approval_results()) == 1


def test_post_paper_mode_persists_plan_and_result(tmp_path) -> None:
    state = _state_service(tmp_path)
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=state,
    )

    result = service.post(
        market_ref="btc-above-100k",
        outcome="yes",
        side="buy",
        price="0.55",
        size="10",
    )

    assert result.mode == "paper"
    assert result.decision == "WOULD_POST"
    assert result.signed_order is not None
    assert len(state.list_order_plans()) == 1
    assert len(state.list_order_results()) == 1


def test_post_live_mode_returns_posted(tmp_path) -> None:
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=_state_service(tmp_path),
    )

    result = service.post(
        market_ref="btc-above-100k",
        outcome="yes",
        side="buy",
        price="0.55",
        size="10",
        live=True,
        confirm=True,
    )

    assert result.decision == "POSTED"
    assert result.live_response is not None
    assert result.live_response["order"]["order_id"] == "order-123"


def test_post_rejects_missing_gtd_expiration(tmp_path) -> None:
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=_state_service(tmp_path),
    )

    try:
        service.post(
            market_ref="btc-above-100k",
            outcome="yes",
            side="buy",
            price="0.55",
            size="10",
            order_type="gtd",
        )
    except ExecutionValidationError as exc:
        assert "--expires-at" in str(exc)
    else:
        raise AssertionError("Expected ExecutionValidationError")


def test_orders_open_and_order_get_use_live_reads(tmp_path) -> None:
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=_state_service(tmp_path),
    )

    open_result = service.orders_open(market="0x" + ("a" * 64))
    get_result = service.order_get(order_id="order-123")

    assert open_result.total == 1
    assert open_result.items[0].order_id == "order-123"
    assert get_result.order.market == "0x" + ("a" * 64)


def test_cancel_defaults_to_paper_mode(tmp_path) -> None:
    state = _state_service(tmp_path)
    service = OrderLifecycleService(
        auth_service=FakeLifecycleAuthService(),
        dry_run_service=FakeLifecycleDryRunService(),
        state_service=state,
    )

    result = service.cancel(order_id="order-123")

    assert result.mode == "paper"
    assert result.decision == "WOULD_CANCEL"
    assert len(state.list_order_results()) == 1
