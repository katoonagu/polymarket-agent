from __future__ import annotations

from dataclasses import dataclass

from pm.auth.exceptions import AuthValidationError
from pm.auth.models import AuthContext, AuthShowResponse, GeoblockStatus
from pm.execution import DryRunService, ExecutionValidationError
from pm.market.models import (
    NormalizedBook,
    NormalizedBookLevel,
    NormalizedMarket,
    NormalizedMidpointQuote,
    NormalizedSpreadQuote,
)

CONDITION_ID = "0x" + ("a" * 64)
PRIVATE_KEY = "0x" + ("1" * 64)


@dataclass
class FakeSettings:
    private_key: str = PRIVATE_KEY
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


class FakeSDKClient:
    def get_tick_size(self, token_id: str) -> str:
        return "0.01"

    def get_fee_rate_bps(self, token_id: str) -> int:
        return 12

    def get_neg_risk(self, token_id: str) -> bool:
        return False

    def create_order(self, order_args: object, options: object) -> FakeSignedOrder:
        return FakeSignedOrder()


class FakeAuthService:
    def __init__(self, *, valid: bool = True, geoblocked: bool = False) -> None:
        self.valid = valid
        self.geoblocked = geoblocked

    def show(self) -> AuthShowResponse:
        return AuthShowResponse(
            auth=AuthContext(
                signer_address="0x" + ("3" * 40),
                funder_address=None,
                signature_type=0,
                signature_type_name="EOA",
                clob_host="https://clob.polymarket.com",
                chain_id=137,
                private_key_present=self.valid,
                api_key_derivation_possible=self.valid,
            ),
            errors=[],
        )

    def require_valid_config(self) -> FakeSettings:
        if not self.valid:
            raise AuthValidationError("missing auth")
        return FakeSettings()

    def _context_from_settings(self, settings: FakeSettings) -> AuthContext:
        return self.show().auth

    def check_geoblock(self) -> GeoblockStatus:
        return GeoblockStatus(
            checked=not self.geoblocked,
            blocked=self.geoblocked if self.geoblocked else False,
            message="blocked" if self.geoblocked else "allowed",
        )

    def build_level_1_client(self, settings: FakeSettings) -> FakeSDKClient:
        return FakeSDKClient()


class FakeGammaClient:
    def get_market_by_slug(self, slug: str) -> NormalizedMarket:
        return _market()

    def get_market_by_condition_id(self, condition_id: str) -> NormalizedMarket:
        market = _market()
        market.condition_id = condition_id
        return market

    def close(self) -> None:
        return None


class FakeClobClient:
    def get_book(self, token_id: str) -> NormalizedBook:
        return NormalizedBook(
            token_id=token_id,
            bids=[NormalizedBookLevel(price="0.54", size="20")],
            asks=[NormalizedBookLevel(price="0.56", size="22")],
            tick_size="0.01",
            min_order_size="5",
        )

    def get_midpoint(self, token_id: str) -> NormalizedMidpointQuote:
        return NormalizedMidpointQuote(token_id=token_id, midpoint="0.55")

    def get_spread(self, token_id: str) -> NormalizedSpreadQuote:
        return NormalizedSpreadQuote(token_id=token_id, spread="0.02")

    def close(self) -> None:
        return None


def test_dry_run_would_post_for_market_slug() -> None:
    service = DryRunService(
        auth_service=FakeAuthService(),
        gamma_client=FakeGammaClient(),
        clob_client=FakeClobClient(),
    )

    result = service.dry_run(
        market_ref="btc-above-100k",
        outcome="yes",
        side="buy",
        price="0.55",
        size="10",
    )

    assert result.decision == "WOULD_POST"
    assert result.market is not None
    assert result.market.token_id == "100"
    assert result.market.fee_rate_bps == 12
    assert result.signed_order is not None
    assert result.signed_order["signature"] == "signed-payload"


def test_dry_run_uses_condition_id_lookup() -> None:
    service = DryRunService(
        auth_service=FakeAuthService(),
        gamma_client=FakeGammaClient(),
        clob_client=FakeClobClient(),
    )

    result = service.dry_run(
        market_ref=CONDITION_ID,
        outcome="no",
        side="sell",
        price="0.45",
        size="10",
    )

    assert result.decision == "WOULD_POST"
    assert result.market is not None
    assert result.market.condition_id == CONDITION_ID
    assert result.market.token_id == "101"


def test_dry_run_skips_when_auth_is_missing() -> None:
    service = DryRunService(
        auth_service=FakeAuthService(valid=False),
        gamma_client=FakeGammaClient(),
        clob_client=FakeClobClient(),
    )

    result = service.dry_run(
        market_ref="btc-above-100k",
        outcome="yes",
        side="buy",
        price="0.55",
        size="10",
    )

    assert result.decision == "SKIP"
    assert result.signed_order is None


def test_dry_run_skips_when_price_is_not_aligned() -> None:
    service = DryRunService(
        auth_service=FakeAuthService(),
        gamma_client=FakeGammaClient(),
        clob_client=FakeClobClient(),
    )

    result = service.dry_run(
        market_ref="btc-above-100k",
        outcome="yes",
        side="buy",
        price="0.555",
        size="10",
    )

    assert result.decision == "SKIP"
    assert any(reason.section == "tick_size" for reason in result.reasons)


def test_dry_run_rejects_invalid_outcome_argument() -> None:
    service = DryRunService(
        auth_service=FakeAuthService(),
        gamma_client=FakeGammaClient(),
        clob_client=FakeClobClient(),
    )

    try:
        service.dry_run(
            market_ref="btc-above-100k",
            outcome="maybe",
            side="buy",
            price="0.55",
            size="10",
        )
    except ExecutionValidationError as exc:
        assert "Outcome" in str(exc)
    else:
        raise AssertionError("Expected ExecutionValidationError")


def _market() -> NormalizedMarket:
    return NormalizedMarket(
        market_slug="btc-above-100k",
        event_slug="btc-event",
        question="Will BTC reach 100k?",
        event_title="Bitcoin event",
        active=True,
        closed=False,
        enable_order_book=True,
        condition_id=CONDITION_ID,
        token_ids=["100", "101"],
        outcomes=["Yes", "No"],
        min_tick=0.01,
        min_order_size=5,
    )
