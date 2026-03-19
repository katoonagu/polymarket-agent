from __future__ import annotations

import json

from typer.testing import CliRunner

from pm.auth.models import AuthContext, BalanceAllowanceView
from pm.cli.app import app
from pm.execution.models import (
    ApprovalAssetStatus,
    ApprovalCheckResponse,
    ApprovalSetRequest,
    ApprovalSetResponse,
    DryRunBookContext,
    DryRunPostContext,
    DryRunResolvedMarket,
    ExecutionMutationResponse,
    ExecutionReasonBlock,
    NormalizedOrder,
    OpenOrdersResponse,
    OrderGetResponse,
    PostOrderRequest,
    PostOrderResponse,
)

runner = CliRunner()


class FakeLifecycleCLIService:
    def check_approvals(self) -> ApprovalCheckResponse:
        return ApprovalCheckResponse(
            auth=_auth_context(),
            items=[
                ApprovalAssetStatus(
                    asset="usdc",
                    asset_type="COLLATERAL",
                    balance_view=BalanceAllowanceView(
                        asset_type="COLLATERAL",
                        signature_type=0,
                        balance="100",
                        allowance="100",
                    ),
                    target_contract_address="0xcollateral",
                    exchange_address="0xexchange",
                    ready=True,
                ),
                ApprovalAssetStatus(
                    asset="ctf",
                    asset_type="CONDITIONAL",
                    balance_view=BalanceAllowanceView(
                        asset_type="CONDITIONAL",
                        token_id="100",
                        signature_type=0,
                        balance="25",
                        allowance="25",
                    ),
                    target_contract_address="0xconditional",
                    exchange_address="0xexchange",
                    ready=True,
                ),
            ],
            total=2,
        )

    def set_approval(
        self,
        *,
        asset: str,
        live: bool = False,
        confirm: bool = False,
    ) -> ApprovalSetResponse:
        return ApprovalSetResponse(
            request=ApprovalSetRequest(asset=asset, live=live, confirm=confirm),
            auth=_auth_context(),
            asset_status=self.check_approvals().items[0],
            mode="live" if live else "preview",
            decision="SET" if live else "WOULD_SET",
            plan_id="approval_plan_1",
            result_id="approval_result_1" if live else None,
            live_response={"txHash": "0xapprove"} if live else None,
            reasons=[
                ExecutionReasonBlock(
                    section="allowance",
                    status="pass",
                    message="approval okay",
                )
            ],
        )

    def post(self, **kwargs: object) -> PostOrderResponse:
        return PostOrderResponse(
            request=PostOrderRequest(
                market_ref=str(kwargs["market_ref"]),
                outcome=str(kwargs["outcome"]),
                side=str(kwargs["side"]),
                price=str(kwargs["price"]),
                size=str(kwargs["size"]),
                order_type=str(kwargs.get("order_type", "gtc")),
                expires_at=kwargs.get("expires_at"),
                post_only=bool(kwargs.get("post_only", False)),
                live=bool(kwargs.get("live", False)),
                confirm=bool(kwargs.get("confirm", False)),
            ),
            auth=_auth_context(),
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
            post_context=DryRunPostContext(
                order_type="GTC",
                post_only=False,
                submit_mode="paper",
            ),
            signed_order={"signature": "signed-payload"},
            mode="paper",
            decision="WOULD_POST",
            plan_id="execution_plan_1",
            result_id="execution_result_1",
            live_response=None,
            reasons=[
                ExecutionReasonBlock(
                    section="balance",
                    status="pass",
                    message="balance okay",
                )
            ],
        )

    def orders_open(
        self,
        *,
        market: str | None = None,
        token_id: str | None = None,
    ) -> OpenOrdersResponse:
        return OpenOrdersResponse(
            auth=_auth_context(),
            items=[
                NormalizedOrder(
                    order_id="order-123",
                    market=market or "0x" + ("a" * 64),
                    asset_id=token_id or "100",
                    side="BUY",
                    status="OPEN",
                    price="0.55",
                    size="10",
                )
            ],
            total=1,
        )

    def order_get(self, *, order_id: str) -> OrderGetResponse:
        return OrderGetResponse(
            auth=_auth_context(),
            order=NormalizedOrder(
                order_id=order_id,
                market="0x" + ("a" * 64),
                asset_id="100",
                side="BUY",
                status="OPEN",
                price="0.55",
                size="10",
            ),
        )

    def cancel(
        self,
        *,
        order_id: str,
        live: bool = False,
        confirm: bool = False,
    ) -> ExecutionMutationResponse:
        return _mutation("cancel", order_id=order_id)

    def cancel_all(self, *, live: bool = False, confirm: bool = False) -> ExecutionMutationResponse:
        return _mutation("cancel_all")

    def cancel_market(
        self,
        *,
        market: str,
        token_id: str | None = None,
        live: bool = False,
        confirm: bool = False,
    ) -> ExecutionMutationResponse:
        return _mutation("cancel_market", market=market, token_id=token_id)


class SpyLifecycleCLIService(FakeLifecycleCLIService):
    def __init__(self) -> None:
        self.last_set_approval: dict[str, object] | None = None
        self.last_post: dict[str, object] | None = None
        self.last_cancel: dict[str, object] | None = None

    def set_approval(
        self,
        *,
        asset: str,
        live: bool = False,
        confirm: bool = False,
    ) -> ApprovalSetResponse:
        self.last_set_approval = {
            "asset": asset,
            "live": live,
            "confirm": confirm,
        }
        return super().set_approval(asset=asset, live=live, confirm=confirm)

    def post(self, **kwargs: object) -> PostOrderResponse:
        self.last_post = dict(kwargs)
        response = super().post(**kwargs)
        if bool(kwargs.get("live", False)):
            return response.model_copy(
                update={
                    "mode": "live",
                    "decision": "POSTED",
                    "live_response": {"orderID": "order-live-1"},
                }
            )
        return response

    def cancel(
        self,
        *,
        order_id: str,
        live: bool = False,
        confirm: bool = False,
    ) -> ExecutionMutationResponse:
        self.last_cancel = {
            "order_id": order_id,
            "live": live,
            "confirm": confirm,
        }
        return _mutation("cancel", order_id=order_id, live=live)


def test_approve_check_and_set_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.approve.OrderLifecycleService", lambda: FakeLifecycleCLIService())

    check_result = runner.invoke(app, ["approve", "check", "--json"])
    set_result = runner.invoke(app, ["approve", "set", "--asset", "usdc", "--json"])

    assert check_result.exit_code == 0
    assert set_result.exit_code == 0
    assert json.loads(check_result.stdout)["total"] == 2
    assert json.loads(set_result.stdout)["decision"] == "WOULD_SET"


def test_exec_post_and_open_orders_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.execution.OrderLifecycleService", lambda: FakeLifecycleCLIService())

    post_result = runner.invoke(
        app,
        [
            "exec",
            "post",
            "--market",
            "btc-above-100k",
            "--outcome",
            "yes",
            "--side",
            "buy",
            "--price",
            "0.55",
            "--size",
            "10",
            "--json",
        ],
    )
    open_result = runner.invoke(
        app,
        ["exec", "orders", "open", "--market", "0x" + ("a" * 64), "--json"],
    )

    assert post_result.exit_code == 0
    assert open_result.exit_code == 0
    assert json.loads(post_result.stdout)["decision"] == "WOULD_POST"
    assert json.loads(open_result.stdout)["items"][0]["order_id"] == "order-123"


def test_exec_order_get_and_cancel_json(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.execution.OrderLifecycleService", lambda: FakeLifecycleCLIService())

    get_result = runner.invoke(app, ["exec", "order", "get", "--order-id", "order-123", "--json"])
    cancel_result = runner.invoke(app, ["exec", "cancel", "--order-id", "order-123", "--json"])

    assert get_result.exit_code == 0
    assert cancel_result.exit_code == 0
    assert json.loads(get_result.stdout)["order"]["order_id"] == "order-123"
    assert json.loads(cancel_result.stdout)["decision"] == "WOULD_CANCEL"


def test_exec_root_output_json_for_cancel_all(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.execution.OrderLifecycleService", lambda: FakeLifecycleCLIService())

    result = runner.invoke(app, ["--output", "json", "exec", "cancel-all"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["decision"] == "WOULD_CANCEL_ALL"


def test_approve_live_prompt_decline_cancels(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.support.interactive_allowed", lambda *args, **kwargs: True)

    result = runner.invoke(app, ["approve", "set", "--asset", "usdc", "--live"], input="n\n")

    assert result.exit_code == 0
    assert "cancelled" in result.stdout.lower()


def test_exec_post_live_prompt_accepts_and_sets_confirm(monkeypatch) -> None:
    service = SpyLifecycleCLIService()
    monkeypatch.setattr("pm.cli.execution.OrderLifecycleService", lambda: service)
    monkeypatch.setattr("pm.cli.support.interactive_allowed", lambda *args, **kwargs: True)

    result = runner.invoke(
        app,
        [
            "exec",
            "post",
            "--market",
            "btc-above-100k",
            "--outcome",
            "yes",
            "--side",
            "buy",
            "--price",
            "0.55",
            "--size",
            "10",
            "--live",
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    assert service.last_post is not None
    assert service.last_post["live"] is True
    assert service.last_post["confirm"] is True
    assert "POSTED" in result.stdout


def test_exec_cancel_live_prompt_decline_cancels(monkeypatch) -> None:
    service = SpyLifecycleCLIService()
    monkeypatch.setattr("pm.cli.execution.OrderLifecycleService", lambda: service)
    monkeypatch.setattr("pm.cli.support.interactive_allowed", lambda *args, **kwargs: True)

    result = runner.invoke(
        app,
        ["exec", "cancel", "--order-id", "order-123", "--live"],
        input="n\n",
    )

    assert result.exit_code == 0
    assert service.last_cancel is None
    assert "cancelled" in result.stdout.lower()


def test_exec_post_live_json_requires_confirm(monkeypatch) -> None:
    monkeypatch.setattr("pm.cli.execution.OrderLifecycleService", lambda: FakeLifecycleCLIService())

    result = runner.invoke(
        app,
        [
            "exec",
            "post",
            "--market",
            "btc-above-100k",
            "--outcome",
            "yes",
            "--side",
            "buy",
            "--price",
            "0.55",
            "--size",
            "10",
            "--live",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["identifier"] == "confirm"


def _mutation(
    action: str,
    order_id: str | None = None,
    market: str | None = None,
    token_id: str | None = None,
    live: bool = False,
) -> ExecutionMutationResponse:
    return ExecutionMutationResponse(
        auth=_auth_context(),
        action=action,
        mode="live" if live else "paper",
        decision={
            "cancel": "CANCELLED" if live else "WOULD_CANCEL",
            "cancel_all": "CANCELLED" if live else "WOULD_CANCEL_ALL",
            "cancel_market": "CANCELLED" if live else "WOULD_CANCEL_MARKET",
        }[action],
        plan_id="execution_plan_1",
        result_id="execution_result_1",
        order_id=order_id,
        market=market,
        token_id=token_id,
        response={"ok": True} if live else None,
        reasons=[
            ExecutionReasonBlock(
                section="auth_config",
                status="pass",
                message="auth okay",
            )
        ],
    )


def _auth_context() -> AuthContext:
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
