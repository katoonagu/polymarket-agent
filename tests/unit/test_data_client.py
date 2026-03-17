"""Unit tests for the public Polymarket Data API client."""

from __future__ import annotations

import httpx
import respx

from pm.data import (
    DataClient,
    DataNotFoundError,
    DataValidationError,
    NormalizedActivity,
    NormalizedClosedPosition,
    NormalizedCurrentPosition,
    NormalizedHolder,
    NormalizedHoldingsValue,
    NormalizedLeaderboardEntry,
    NormalizedOpenInterest,
    NormalizedTrade,
    NormalizedTradedCount,
)

DATA_URL = "https://data-api.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"
USER = "0x1111111111111111111111111111111111111111"
CONDITION_ID = "0x" + ("a" * 64)
MARKET_SLUG = "btc-above-100k"


def _gamma_market_payload() -> dict[str, object]:
    return {
        "slug": MARKET_SLUG,
        "question": "Will BTC reach 100k?",
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "conditionId": CONDITION_ID,
        "clobTokenIds": ["100", "101"],
        "outcomes": ["Yes", "No"],
    }


@respx.mock
def test_get_user_trades_calls_endpoint_and_normalizes_response() -> None:
    route = respx.get(f"{DATA_URL}/trades").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "side": "BUY",
                    "outcome": "Yes",
                    "price": "0.45",
                    "size": "10",
                    "timestamp": 1710000000,
                    "transactionHash": "0xtrade",
                }
            ],
        )
    )

    with DataClient() as client:
        result = client.get_user_trades(f" {USER} ", limit=5)

    assert route.called
    request = route.calls[0].request
    assert request.url.params["user"] == USER
    assert request.url.params["limit"] == "5"
    assert result.user == USER
    assert result.total == 1
    assert result.items == [
        NormalizedTrade(
            user=USER,
            market_slug=MARKET_SLUG,
            condition_id=CONDITION_ID,
            token_id="100",
            side="BUY",
            outcome="Yes",
            price="0.45",
            size="10",
            timestamp=1710000000,
            transaction_hash="0xtrade",
        )
    ]


@respx.mock
def test_get_user_activity_calls_endpoint_and_normalizes_response() -> None:
    route = respx.get(f"{DATA_URL}/activity").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "type": "TRADE",
                    "side": "SELL",
                    "outcome": "No",
                    "price": "0.55",
                    "size": "7",
                    "usdcSize": "3.85",
                    "timestamp": 1710000100,
                    "transactionHash": "0xactivity",
                }
            ],
        )
    )

    with DataClient() as client:
        result = client.get_user_activity(USER, limit=3)

    assert route.called
    assert route.calls[0].request.url.params["limit"] == "3"
    assert result.items == [
        NormalizedActivity(
            user=USER,
            market_slug=MARKET_SLUG,
            condition_id=CONDITION_ID,
            token_id="100",
            activity_type="TRADE",
            side="SELL",
            outcome="No",
            price="0.55",
            size="7",
            usdc_size="3.85",
            timestamp=1710000100,
            transaction_hash="0xactivity",
        )
    ]


@respx.mock
def test_get_current_positions_calls_endpoint_and_normalizes_response() -> None:
    route = respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "outcome": "Yes",
                    "size": "12",
                    "avgPrice": "0.41",
                    "initialValue": "4.92",
                    "currentValue": "5.52",
                    "cashPnl": "0.60",
                    "percentPnl": "12.19",
                }
            ],
        )
    )

    with DataClient() as client:
        result = client.get_current_positions(USER)

    assert route.called
    assert route.calls[0].request.url.params["user"] == USER
    assert result.items == [
        NormalizedCurrentPosition(
            user=USER,
            market_slug=MARKET_SLUG,
            condition_id=CONDITION_ID,
            token_id="100",
            outcome="Yes",
            size="12",
            average_price="0.41",
            initial_value="4.92",
            current_value="5.52",
            cash_pnl="0.60",
            percent_pnl="12.19",
        )
    ]


@respx.mock
def test_get_closed_positions_calls_endpoint_and_normalizes_response() -> None:
    route = respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "slug": MARKET_SLUG,
                    "conditionId": CONDITION_ID,
                    "asset": "100",
                    "outcome": "Yes",
                    "avgPrice": "0.40",
                    "totalBought": "10",
                    "realizedPnl": "1.25",
                    "curPrice": "0.53",
                    "timestamp": 1710000200,
                }
            ],
        )
    )

    with DataClient() as client:
        result = client.get_closed_positions(USER)

    assert route.called
    assert result.items == [
        NormalizedClosedPosition(
            user=USER,
            market_slug=MARKET_SLUG,
            condition_id=CONDITION_ID,
            token_id="100",
            outcome="Yes",
            average_price="0.40",
            total_bought="10",
            realized_pnl="1.25",
            current_price="0.53",
            timestamp=1710000200,
        )
    ]


@respx.mock
def test_get_holders_resolves_slug_and_flattens_nested_rows() -> None:
    gamma_route = respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_gamma_market_payload())
    )
    holders_route = respx.get(f"{DATA_URL}/holders").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "token": "100",
                    "holders": [
                        {
                            "proxyWallet": USER,
                            "amount": "5",
                            "name": "Alice",
                            "pseudonym": "alice",
                            "outcomeIndex": 0,
                        }
                    ],
                }
            ],
        )
    )

    with DataClient() as client:
        result = client.get_holders(MARKET_SLUG, limit=2)

    assert gamma_route.called
    assert holders_route.called
    assert holders_route.calls[0].request.url.params["market"] == CONDITION_ID
    assert holders_route.calls[0].request.url.params["limit"] == "2"
    assert result.market_slug == MARKET_SLUG
    assert result.condition_id == CONDITION_ID
    assert result.items == [
        NormalizedHolder(
            market_slug=MARKET_SLUG,
            condition_id=CONDITION_ID,
            token_id="100",
            holder_address=USER,
            amount="5",
            name="Alice",
            pseudonym="alice",
            outcome_index=0,
            rank=1,
        )
    ]


@respx.mock
def test_get_open_interest_accepts_condition_id_and_normalizes_response() -> None:
    gamma_route = respx.get(f"{GAMMA_URL}/markets").mock(
        return_value=httpx.Response(200, json=[_gamma_market_payload()])
    )
    oi_route = respx.get(f"{DATA_URL}/oi").mock(
        return_value=httpx.Response(200, json=[{"market": CONDITION_ID, "value": "123.45"}])
    )

    with DataClient() as client:
        result = client.get_open_interest(CONDITION_ID)

    assert gamma_route.called
    assert gamma_route.calls[0].request.url.params["condition_ids"] == CONDITION_ID
    assert oi_route.called
    assert oi_route.calls[0].request.url.params["market"] == CONDITION_ID
    assert result == NormalizedOpenInterest(
        market_slug=MARKET_SLUG,
        condition_id=CONDITION_ID,
        open_interest="123.45",
    )


@respx.mock
def test_get_holdings_value_and_traded_count_normalize_summary_responses() -> None:
    value_route = respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "100.50"})
    )
    traded_route = respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 17})
    )

    with DataClient() as client:
        value = client.get_holdings_value(USER)
        traded = client.get_traded_count(USER)

    assert value_route.called
    assert traded_route.called
    assert value == NormalizedHoldingsValue(user=USER, value="100.50")
    assert traded == NormalizedTradedCount(user=USER, traded=17)


@respx.mock
def test_get_leaderboard_calls_endpoint_and_normalizes_response() -> None:
    route = respx.get(f"{DATA_URL}/v1/leaderboard").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER,
                    "rank": 7,
                    "displayName": "Alpha",
                    "userName": "alpha_user",
                    "pnl": "1234.56",
                    "volume": "9876.54",
                }
            ],
        )
    )

    with DataClient() as client:
        result = client.get_leaderboard(limit=5, user=USER)

    assert route.called
    request = route.calls[0].request
    assert request.url.params["category"] == "OVERALL"
    assert request.url.params["timePeriod"] == "ALL"
    assert request.url.params["orderBy"] == "PNL"
    assert request.url.params["limit"] == "5"
    assert request.url.params["user"] == USER
    assert result.total == 1
    assert result.items == [
        NormalizedLeaderboardEntry(
            address=USER,
            rank=7,
            display_name="Alpha",
            user_name="alpha_user",
            pnl="1234.56",
            volume="9876.54",
        )
    ]


@respx.mock
def test_invalid_wallet_address_rejects_before_network_call() -> None:
    with DataClient() as client:
        try:
            client.get_user_trades("invalid-address")
        except DataValidationError as exc:
            assert str(exc) == "Wallet addresses must use 0x followed by 40 hex characters."
        else:
            raise AssertionError("DataValidationError was not raised")

    assert not respx.calls


@respx.mock
def test_invalid_condition_id_rejects_before_network_call() -> None:
    with DataClient() as client:
        try:
            client.get_holders("0x1234")
        except DataValidationError as exc:
            assert str(exc) == "Condition IDs must use 0x followed by 64 hex characters."
        else:
            raise AssertionError("DataValidationError was not raised")

    assert not respx.calls


@respx.mock
def test_open_interest_empty_payload_maps_to_not_found() -> None:
    respx.get(f"{GAMMA_URL}/markets").mock(
        return_value=httpx.Response(200, json=[_gamma_market_payload()])
    )
    respx.get(f"{DATA_URL}/oi").mock(return_value=httpx.Response(200, json=[]))

    with DataClient() as client:
        try:
            client.get_open_interest(CONDITION_ID)
        except DataNotFoundError as exc:
            assert str(exc) == f"market '{CONDITION_ID}' was not found."
        else:
            raise AssertionError("DataNotFoundError was not raised")
