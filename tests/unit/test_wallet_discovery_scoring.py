"""Unit tests for wallet discovery and deterministic scoring."""

from __future__ import annotations

import httpx
import respx

from pm.wallet import WalletRegistryService, WalletShadowService

DATA_URL = "https://data-api.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"
USER = "0x1111111111111111111111111111111111111111"
USER_TWO = "0x2222222222222222222222222222222222222222"
USER_THREE = "0x3333333333333333333333333333333333333333"
MARKET_SLUG = "btc-above-100k"
CONDITION_ID = "0x" + ("a" * 64)


@respx.mock
def test_discover_leaderboard_preserves_api_order_and_marks_tracked(tmp_path) -> None:
    service = _service_with_wallet(tmp_path, USER, label="Tracked")
    route = respx.get(f"{DATA_URL}/v1/leaderboard").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "proxyWallet": USER_TWO,
                    "rank": 2,
                    "displayName": "Second",
                    "userName": "second",
                    "pnl": "50",
                    "volume": "75",
                },
                {
                    "proxyWallet": USER,
                    "rank": 5,
                    "displayName": "Tracked",
                    "userName": "tracked",
                    "pnl": "100",
                    "volume": "150",
                },
            ],
        )
    )

    result = service.discover_leaderboard(limit=2)

    assert route.called
    assert route.calls[0].request.url.params["category"] == "OVERALL"
    assert route.calls[0].request.url.params["timePeriod"] == "ALL"
    assert route.calls[0].request.url.params["orderBy"] == "PNL"
    assert result.total == 2
    assert [item.address for item in result.items] == [USER_TWO, USER]
    assert result.items[0].tracked is False
    assert result.items[1].tracked is True
    assert result.items[1].tracked_wallet is not None
    assert result.items[1].tracked_wallet.label == "Tracked"
    assert result.errors == []


@respx.mock
def test_discover_holders_dedupes_wallets_and_preserves_first_seen_order(tmp_path) -> None:
    service = _service_with_wallet(tmp_path, USER, label="Tracked")
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_gamma_market_payload())
    )
    respx.get(f"{DATA_URL}/holders").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "token": "100",
                    "holders": [
                        {
                            "proxyWallet": USER,
                            "amount": "5",
                            "name": "Tracked Holder",
                            "pseudonym": "tracked",
                            "outcomeIndex": 0,
                        },
                        {
                            "proxyWallet": USER_TWO,
                            "amount": "2",
                            "name": "Second Holder",
                            "pseudonym": "second",
                            "outcomeIndex": 0,
                        },
                    ],
                },
                {
                    "token": "101",
                    "holders": [
                        {
                            "proxyWallet": USER,
                            "amount": "3",
                            "name": "Tracked Holder",
                            "pseudonym": "tracked",
                            "outcomeIndex": 1,
                        },
                        {
                            "proxyWallet": USER_THREE,
                            "amount": "1",
                            "name": "Third Holder",
                            "pseudonym": "third",
                            "outcomeIndex": 1,
                        },
                    ],
                },
            ],
        )
    )

    result = service.discover_holders(MARKET_SLUG, limit=2)

    assert result.market_slug == MARKET_SLUG
    assert result.condition_id == CONDITION_ID
    assert result.total == 2
    assert [item.address for item in result.items] == [USER, USER_TWO]
    assert result.items[0].rank == 1
    assert result.items[0].tracked is True
    assert result.items[0].tracked_wallet is not None
    assert len(result.items[0].token_exposures) == 2
    assert result.items[0].token_exposures[0].token_id == "100"
    assert result.items[0].token_exposures[1].token_id == "101"
    assert result.items[1].rank == 2
    assert result.items[1].tracked is False


@respx.mock
def test_score_wallet_uses_transparent_bucket_formula_and_rounding(tmp_path) -> None:
    service = _service(tmp_path)
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(
        return_value=httpx.Response(200, json=[{"proxyWallet": USER, "rank": 20}])
    )
    respx.get(f"{DATA_URL}/closed-positions").mock(
        return_value=httpx.Response(200, json=[{"proxyWallet": USER, "realizedPnl": "600"}])
    )
    respx.get(f"{DATA_URL}/traded").mock(
        return_value=httpx.Response(200, json={"user": USER, "traded": 30})
    )
    respx.get(f"{DATA_URL}/value").mock(
        return_value=httpx.Response(200, json={"user": USER, "value": "1500"})
    )
    respx.get(f"{DATA_URL}/positions").mock(
        return_value=httpx.Response(
            200,
            json=[{"proxyWallet": USER, "asset": str(index)} for index in range(6)],
        )
    )

    result = service.score_wallet(USER)

    assert result.total_score == 67.5
    assert result.available_weight == 1.0
    assert result.components["leaderboard_component"].score == 90.0
    assert result.components["realized_performance_component"].score == 60.0
    assert result.components["activity_component"].score == 60.0
    assert result.components["footprint_component"].score == 60.0
    assert result.errors == []


@respx.mock
def test_score_wallet_treats_no_data_as_zero_and_request_failures_as_partial_errors(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/closed-positions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DATA_URL}/traded").mock(return_value=httpx.Response(404))
    respx.get(f"{DATA_URL}/value").mock(return_value=httpx.Response(500))

    result = service.score_wallet(USER)

    assert result.total_score == 0.0
    assert result.available_weight == 0.8
    assert result.components["leaderboard_component"].available is True
    assert result.components["leaderboard_component"].score == 0.0
    assert result.components["realized_performance_component"].available is True
    assert result.components["realized_performance_component"].score == 0.0
    assert result.components["activity_component"].available is True
    assert result.components["activity_component"].score == 0.0
    assert result.components["footprint_component"].available is False
    assert result.components["footprint_component"].score is None
    assert len(result.errors) == 1
    assert result.errors[0].section == "footprint_component"
    assert result.errors[0].code == "request_failed"
    assert result.errors[0].message == "Data API request failed with status 500 for /value."


@respx.mock
def test_rank_tracked_wallets_uses_deterministic_tiebreaks(tmp_path) -> None:
    service = _service_with_two_wallets(tmp_path)
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(side_effect=_leaderboard_side_effect)
    respx.get(f"{DATA_URL}/closed-positions").mock(side_effect=_closed_positions_side_effect)
    respx.get(f"{DATA_URL}/traded").mock(side_effect=_traded_side_effect)
    respx.get(f"{DATA_URL}/value").mock(side_effect=_value_side_effect)
    respx.get(f"{DATA_URL}/positions").mock(side_effect=_positions_side_effect)

    result = service.rank_tracked_wallets()

    assert result.total == 2
    assert [item.score.address for item in result.items] == [USER, USER_TWO]
    assert result.items[0].score.total_score == 49.5
    assert result.items[1].score.total_score == 49.5
    assert result.items[0].score.components["leaderboard_component"].score == 90.0
    assert result.items[1].score.components["leaderboard_component"].score == 70.0


@respx.mock
def test_compare_wallets_returns_winner_and_component_deltas(tmp_path) -> None:
    service = _service(tmp_path)
    respx.get(f"{DATA_URL}/v1/leaderboard").mock(side_effect=_compare_leaderboard_side_effect)
    respx.get(f"{DATA_URL}/closed-positions").mock(side_effect=_compare_closed_positions_side_effect)
    respx.get(f"{DATA_URL}/traded").mock(side_effect=_compare_traded_side_effect)
    respx.get(f"{DATA_URL}/value").mock(side_effect=_compare_value_side_effect)
    respx.get(f"{DATA_URL}/positions").mock(side_effect=_compare_positions_side_effect)

    result = service.compare_wallets(USER, USER_TWO)

    assert result.left.address == USER
    assert result.right.address == USER_TWO
    assert result.winner_address == USER
    assert result.score_delta == 79.5
    assert result.component_deltas == {
        "leaderboard_component": 50.0,
        "realized_performance_component": 100.0,
        "activity_component": 60.0,
        "footprint_component": 100.0,
    }


def _service(tmp_path) -> WalletShadowService:
    return WalletShadowService(registry=WalletRegistryService(path=tmp_path / "wallets.json"))


def _service_with_wallet(
    tmp_path,
    address: str,
    *,
    label: str | None = None,
) -> WalletShadowService:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(address, label=label, added_at="2026-03-18T00:00:00Z")
    return WalletShadowService(registry=registry)


def _service_with_two_wallets(tmp_path) -> WalletShadowService:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(USER, label="First", added_at="2026-03-18T00:00:00Z")
    registry.add_wallet(USER_TWO, label="Second", added_at="2026-03-18T00:01:00Z")
    return WalletShadowService(registry=registry)


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


def _leaderboard_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    if user == USER:
        payload = [{"proxyWallet": USER, "rank": 20}]
    else:
        payload = [{"proxyWallet": USER_TWO, "rank": 100}]
    return httpx.Response(200, json=payload)


def _closed_positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    if user == USER:
        payload = [{"proxyWallet": USER, "realizedPnl": "600"}]
    else:
        payload = [{"proxyWallet": USER_TWO, "realizedPnl": "2000"}]
    return httpx.Response(200, json=payload)


def _traded_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    traded = 5 if user == USER else 0
    return httpx.Response(200, json={"user": user, "traded": traded})


def _value_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    value = "0" if user == USER else "50"
    return httpx.Response(200, json={"user": user, "value": value})


def _positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    asset = "100" if user == USER else "200"
    return httpx.Response(200, json=[{"proxyWallet": user, "asset": asset}])


def _compare_leaderboard_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    rank = 10 if user == USER else 500
    return httpx.Response(200, json=[{"proxyWallet": user, "rank": rank}])


def _compare_closed_positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    realized_pnl = "5000" if user == USER else "0"
    return httpx.Response(200, json=[{"proxyWallet": user, "realizedPnl": realized_pnl}])


def _compare_traded_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    traded = 100 if user == USER else 10
    return httpx.Response(200, json={"user": user, "traded": traded})


def _compare_value_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    value = "20000" if user == USER else "0"
    return httpx.Response(200, json={"user": user, "value": value})


def _compare_positions_side_effect(request: httpx.Request) -> httpx.Response:
    user = request.url.params["user"]
    if user == USER:
        payload = [{"proxyWallet": user, "asset": str(index)} for index in range(20)]
    else:
        payload = []
    return httpx.Response(200, json=payload)
