"""Unit tests for market watchlist, snapshots, and recurring resolution."""

from __future__ import annotations

import httpx
import respx

from pm.market.models import WatchedMarket
from pm.market.service import MarketIntelService, MarketValidationError
from pm.market.state import MarketAlreadyWatchedError, MarketStateService

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"
MARKET_SLUG = "btc-above-100k"
CONDITION_ID = "0x" + ("a" * 64)


def _build_state(tmp_path) -> MarketStateService:
    return MarketStateService(
        watchlist_path=tmp_path / "market-watchlist.json",
        snapshots_path=tmp_path / "market-snapshots.json",
    )


def _market_payload(
    *,
    slug: str = MARKET_SLUG,
    question: str = "Will BTC reach 100k?",
    active: bool = True,
    closed: bool = False,
    end_date: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "slug": slug,
        "question": question,
        "active": active,
        "closed": closed,
        "enableOrderBook": True,
        "conditionId": CONDITION_ID,
        "clobTokenIds": ["100", "101"],
        "outcomes": ["Yes", "No"],
        "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5,
        "events": [{"slug": "bitcoin-event", "title": "Bitcoin event"}],
    }
    if end_date is not None:
        payload["endDate"] = end_date
    return payload


@respx.mock
def test_watch_crud_preserves_order_and_rejects_duplicates(tmp_path) -> None:
    state = _build_state(tmp_path)
    service = MarketIntelService(state=state)
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload())
    )
    respx.get(f"{GAMMA_URL}/markets/slug/btc-above-110k").mock(
        return_value=httpx.Response(
            200,
            json=_market_payload(slug="btc-above-110k", question="Will BTC reach 110k?"),
        )
    )

    first = service.add_watch(MARKET_SLUG, label="Primary", tags=["b", "a"])
    second = service.add_watch("btc-above-110k")
    listed = service.list_watchlist()

    assert first.market.market_slug == MARKET_SLUG
    assert first.market.tags == ["a", "b"]
    assert second.market.market_slug == "btc-above-110k"
    assert [item.market_slug for item in listed.items] == [MARKET_SLUG, "btc-above-110k"]

    try:
        service.add_watch(MARKET_SLUG)
    except MarketAlreadyWatchedError as exc:
        assert str(exc) == f"market '{MARKET_SLUG}' is already watched."
    else:
        raise AssertionError("MarketAlreadyWatchedError was not raised")

    removed = service.remove_watch(MARKET_SLUG)
    assert removed.market.market_slug == MARKET_SLUG
    assert [item.market_slug for item in service.list_watchlist().items] == ["btc-above-110k"]


@respx.mock
def test_snapshot_market_builds_and_persists_summary(tmp_path) -> None:
    state = _build_state(tmp_path)
    service = MarketIntelService(state=state)
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload())
    )
    respx.get(f"{GAMMA_URL}/events/slug/bitcoin-event").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": "bitcoin-event",
                "title": "Bitcoin event",
                "active": True,
                "closed": False,
                "enableOrderBook": True,
                "markets": [_market_payload()],
            },
        )
    )
    respx.get(f"{CLOB_URL}/midpoint").mock(
        side_effect=[
            httpx.Response(200, json={"mid": "0.45"}),
            httpx.Response(200, json={"mid": "0.55"}),
        ]
    )
    respx.get(f"{CLOB_URL}/spread").mock(
        side_effect=[
            httpx.Response(200, json={"spread": "0.02"}),
            httpx.Response(200, json={"spread": "0.03"}),
        ]
    )
    respx.get(f"{CLOB_URL}/book").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "asset_id": "100",
                    "bids": [{"price": "0.44", "size": "10"}],
                    "asks": [{"price": "0.46", "size": "12"}],
                },
            ),
            httpx.Response(
                200,
                json={
                    "asset_id": "101",
                    "bids": [{"price": "0.54", "size": "8"}],
                    "asks": [{"price": "0.56", "size": "9"}],
                },
            ),
        ]
    )
    respx.get(f"{DATA_URL}/oi").mock(
        return_value=httpx.Response(200, json=[{"market": CONDITION_ID, "value": "123.45"}])
    )
    respx.get(f"{DATA_URL}/holders").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "token": "100",
                    "holders": [
                        {
                            "proxyWallet": "0x1111111111111111111111111111111111111111",
                            "amount": "5",
                            "outcomeIndex": 0,
                        }
                    ],
                }
            ],
        )
    )

    result = service.snapshot_market(MARKET_SLUG)

    assert result.snapshot.market_slug == MARKET_SLUG
    assert result.snapshot.event_title == "Bitcoin event"
    assert result.snapshot.open_interest == "123.45"
    assert result.snapshot.tokens[0].best_bid == "0.44"
    assert result.snapshot.tokens[1].best_ask == "0.56"
    assert result.snapshot.holders_total_returned == 1
    assert len(state.list_snapshots()) == 1


@respx.mock
def test_snapshot_market_keeps_partial_errors_and_saves_record(tmp_path) -> None:
    state = _build_state(tmp_path)
    service = MarketIntelService(state=state)
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(
        return_value=httpx.Response(200, json=_market_payload())
    )
    respx.get(f"{GAMMA_URL}/events/slug/bitcoin-event").mock(return_value=httpx.Response(404))
    respx.get(f"{CLOB_URL}/midpoint").mock(
        side_effect=[
            httpx.Response(200, json={"mid": "0.45"}),
            httpx.Response(200, json={"mid": "0.55"}),
        ]
    )
    respx.get(f"{CLOB_URL}/spread").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"spread": "0.03"}),
        ]
    )
    respx.get(f"{CLOB_URL}/book").mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(
                200,
                json={"asset_id": "101", "bids": [], "asks": [{"price": "0.56", "size": "9"}]},
            ),
        ]
    )
    respx.get(f"{DATA_URL}/oi").mock(return_value=httpx.Response(500))
    respx.get(f"{DATA_URL}/holders").mock(return_value=httpx.Response(200, json=[]))

    result = service.snapshot_market(MARKET_SLUG)

    assert result.snapshot.errors
    assert {error.section for error in result.snapshot.errors} >= {
        "event",
        "token:100:spread",
        "token:100:book",
        "open_interest",
    }
    assert result.snapshot.tokens[0].spread is None
    assert len(state.list_snapshots()) == 1


@respx.mock
def test_refresh_watchlist_appends_failure_snapshot_for_missing_market(tmp_path) -> None:
    state = _build_state(tmp_path)
    state.add_watched_market(
        WatchedMarket(
            market_slug=MARKET_SLUG,
            event_slug="bitcoin-event",
            question="Will BTC reach 100k?",
            label="Tracked",
            tags=["btc"],
            added_at="2026-03-18T00:00:00Z",
        )
    )
    service = MarketIntelService(state=state)
    respx.get(f"{GAMMA_URL}/markets/slug/{MARKET_SLUG}").mock(return_value=httpx.Response(404))

    result = service.refresh_watchlist()

    assert result.total == 1
    assert result.items[0].market_slug == MARKET_SLUG
    assert result.items[0].errors[0].code == "not_found"
    assert len(state.list_snapshots()) == 1


@respx.mock
def test_recurring_list_ranks_active_open_interval_matches_by_recency(tmp_path) -> None:
    service = MarketIntelService(state=_build_state(tmp_path))
    respx.get(f"{GAMMA_URL}/public-search").mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "slug": "bitcoin-event",
                        "title": "Bitcoin 15 minute markets",
                        "markets": [
                            _market_payload(
                                slug="btc-15m-older",
                                question="Bitcoin Up or Down - 15 min",
                                end_date="2026-03-18T12:15:00Z",
                            ),
                            _market_payload(
                                slug="btc-15m-newer",
                                question="Bitcoin Up or Down - 15 min",
                                end_date="2026-03-18T12:30:00Z",
                            ),
                            _market_payload(
                                slug="btc-15m-closed",
                                question="Bitcoin Up or Down - 15 min",
                                closed=True,
                                end_date="2026-03-18T12:45:00Z",
                            ),
                            _market_payload(
                                slug="btc-5m",
                                question="Bitcoin Up or Down - 5 min",
                                end_date="2026-03-18T12:30:00Z",
                            ),
                        ],
                    }
                ]
            },
        )
    )

    result = service.recurring_list("btc", interval="15m", limit=3)

    assert [item.market_slug for item in result.items] == [
        "btc-15m-newer",
        "btc-15m-older",
        "btc-15m-closed",
    ]
    assert result.items[0].recency_source == "endDate"
    assert result.items[0].rank == 1


def test_invalid_interval_raises_validation_error(tmp_path) -> None:
    service = MarketIntelService(state=_build_state(tmp_path))

    try:
        service.recurring_list("btc", interval="30m", limit=1)
    except MarketValidationError as exc:
        assert str(exc) == "Interval must be one of: 5m, 15m, 1h."
    else:
        raise AssertionError("MarketValidationError was not raised")
