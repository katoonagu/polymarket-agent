from __future__ import annotations

from dataclasses import dataclass

from pm.market.models import NormalizedMarket
from pm.strategy.btc15m_page import (
    Btc15mPageParityData,
    Btc15mPageParityService,
    _extract_page_data,
)


def test_extract_page_data_uses_structured_slug_matched_state() -> None:
    market = _market()
    html = """
    <html>
      <body>
        <script id="__NEXT_DATA__" type="application/json">
          {
            "props": {
              "pageProps": {
                "markets": [
                  {
                    "slug": "btc-updown-15m-1774002600",
                    "currentWindowLabel": "10:30 - 10:45 UTC",
                    "priceToBeat": "101234.5",
                    "currentLiveBtcPrice": "101240.1",
                    "upPrice": "0.33",
                    "downPrice": "0.67",
                    "volume": "120K"
                  }
                ]
              }
            }
          }
        </script>
      </body>
    </html>
    """

    data = _extract_page_data(html, market=market)

    assert data.matched_market_slug == market.market_slug
    assert data.price_to_beat == "101234.5"
    assert data.current_live_btc_price == "101240.1"
    assert data.up_price == "0.33"
    assert data.down_price == "0.67"
    assert data.volume == "120K"
    assert data.field_sources["price_to_beat"] == "page_exact"
    assert data.field_sources["current_live_btc_price"] == "page_exact"
    assert data.field_sources["up_price"] == "page_exact"
    assert data.field_sources["down_price"] == "page_exact"
    assert data.field_sources["volume"] == "page_exact"


def test_extract_page_data_rejects_interval_text_false_positive() -> None:
    market = _market()
    html = """
    <html>
      <body>
        <div>BTC 15 Minutes</div>
        <div>Up</div>
        <div>Down</div>
      </body>
    </html>
    """

    data = _extract_page_data(html, market=market)

    assert data.price_to_beat is None
    assert data.current_live_btc_price is None
    assert data.up_price is None
    assert data.down_price is None
    assert "price_to_beat_visible_rejected" not in data.notes


def test_extract_page_data_marks_visible_text_as_estimated() -> None:
    market = _market()
    html = """
    <html>
      <body>
        <div>Price to beat $101234.5</div>
        <div>Live BTC price $101240.1</div>
        <div>Up 33¢</div>
        <div>Down 67¢</div>
      </body>
    </html>
    """

    data = _extract_page_data(html, market=market)

    assert data.price_to_beat == "101234.5"
    assert data.current_live_btc_price == "101240.1"
    assert data.up_price == "0.33"
    assert data.down_price == "0.67"
    assert data.field_sources["price_to_beat"] == "page_estimated"
    assert data.field_sources["current_live_btc_price"] == "page_estimated"
    assert data.field_sources["up_price"] == "page_estimated"
    assert data.field_sources["down_price"] == "page_estimated"


def test_page_service_prefers_exact_market_page_over_estimated_event_page() -> None:
    market = _market()
    client = _FakeClient(
        {
            "https://polymarket.com/event/btc-15m-event": _FakeResponse(
                """
                <html>
                  <body>
                    <div>Price to beat $101200</div>
                    <div>Up 31¢</div>
                    <div>Down 69¢</div>
                  </body>
                </html>
                """
            ),
            "https://polymarket.com/market/btc-updown-15m-1774002600": _FakeResponse(
                """
                <html>
                  <body>
                    <script id="__NEXT_DATA__" type="application/json">
                      {
                        "props": {
                          "pageProps": {
                            "market": {
                              "slug": "btc-updown-15m-1774002600",
                              "priceToBeat": "101234.5",
                              "currentLiveBtcPrice": "101240.1",
                              "upPrice": "0.33",
                              "downPrice": "0.67"
                            }
                          }
                        }
                      }
                    </script>
                  </body>
                </html>
                """
            ),
        }
    )
    service = Btc15mPageParityService(client=client)

    data = service.fetch(market)

    assert data.event_url == "https://polymarket.com/market/btc-updown-15m-1774002600"
    assert data.field_sources["price_to_beat"] == "page_exact"
    assert data.field_sources["up_price"] == "page_exact"
    assert data.field_sources["down_price"] == "page_exact"


def test_page_service_uses_browser_adapter_when_structured_page_is_unavailable() -> None:
    market = _market()
    client = _FakeClient(
        {
            "https://polymarket.com/event/btc-15m-event": _FakeResponse(
                "<html><body></body></html>"
            ),
            "https://polymarket.com/market/btc-updown-15m-1774002600": _FakeResponse(
                "<html><body><div>Loading...</div></body></html>"
            ),
        }
    )
    service = Btc15mPageParityService(
        client=client,
        browser_adapter=_FakeBrowserAdapter(
            Btc15mPageParityData(
                event_url="https://polymarket.com/market/btc-updown-15m-1774002600",
                current_window_label="10:30 - 10:45 UTC",
                price_to_beat="101234.5",
                current_live_btc_price="101240.1",
                up_price="0.33",
                down_price="0.67",
                volume="120K",
                field_sources={
                    "price_to_beat": "page_exact",
                    "current_live_btc_price": "page_exact",
                    "up_price": "page_exact",
                    "down_price": "page_exact",
                    "volume": "page_exact",
                },
                matched_market_slug=market.market_slug,
                notes=["browser_exact_visible_match"],
            )
        ),
    )

    data = service.fetch(market)

    assert data.field_sources["price_to_beat"] == "page_exact"
    assert data.current_live_btc_price == "101240.1"
    assert data.volume == "120K"
    assert "browser_exact_visible_match" in data.notes


def test_page_service_marks_browser_adapter_unavailable_without_false_exact() -> None:
    market = _market()
    client = _FakeClient(
        {
            "https://polymarket.com/event/btc-15m-event": _FakeResponse(
                "<html><body>BTC 15 Minutes</body></html>"
            ),
            "https://polymarket.com/market/btc-updown-15m-1774002600": _FakeResponse(
                "<html><body>Price to beat unavailable</body></html>"
            ),
        }
    )
    service = Btc15mPageParityService(
        client=client,
        browser_adapter=_FakeBrowserAdapter(
            Btc15mPageParityData(notes=["browser_adapter_unavailable"])
        ),
    )

    data = service.fetch(market)

    assert data.field_sources.get("price_to_beat") != "page_exact"
    assert "browser_adapter_unavailable" in data.notes


def test_page_service_terminal_current_prefers_browser_exact_snapshot() -> None:
    market = _market()
    service = Btc15mPageParityService(
        client=_FakeClient({}),
        browser_adapter=_FakeBrowserAdapter(
            Btc15mPageParityData(
                event_url="https://polymarket.com/market/btc-updown-15m-1774002600",
                price_to_beat="101234.5",
                current_live_btc_price="101240.1",
                up_price="0.33",
                down_price="0.67",
                volume="120K",
                field_sources={
                    "price_to_beat": "page_exact",
                    "current_live_btc_price": "page_exact",
                    "up_price": "page_exact",
                    "down_price": "page_exact",
                    "volume": "page_exact",
                },
                matched_market_slug=market.market_slug,
            )
        ),
    )

    data = service.fetch_terminal_current(market)

    assert data.price_to_beat == "101234.5"
    assert data.current_live_btc_price == "101240.1"
    assert data.up_price == "0.33"
    assert data.down_price == "0.67"
    assert data.volume == "120K"
    assert data.stale is False
    assert data.observed_at is not None


def test_page_service_terminal_current_keeps_last_valid_exact_snapshot_when_browser_fails() -> None:
    market = _market()
    previous = Btc15mPageParityData(
        event_url="https://polymarket.com/market/btc-updown-15m-1774002600",
        price_to_beat="101234.5",
        current_live_btc_price="101240.1",
        up_price="0.33",
        down_price="0.67",
        volume="120K",
        field_sources={
            "price_to_beat": "page_exact",
            "current_live_btc_price": "page_exact",
            "up_price": "page_exact",
            "down_price": "page_exact",
            "volume": "page_exact",
        },
        matched_market_slug=market.market_slug,
        observed_at="2026-03-20T10:39:00Z",
    )
    service = Btc15mPageParityService(
        client=_FakeClient({}),
        browser_adapter=_FakeBrowserAdapter(
            Btc15mPageParityData(notes=["browser_adapter_unavailable"])
        ),
    )

    data = service.fetch_terminal_current(market, previous=previous)

    assert data.price_to_beat == "101234.5"
    assert data.current_live_btc_price == "101240.1"
    assert data.up_price == "0.33"
    assert data.down_price == "0.67"
    assert data.volume == "120K"
    assert data.stale is True
    assert data.observed_at == "2026-03-20T10:39:00Z"
    assert "stale_last_valid_snapshot" in data.notes
    assert "browser_adapter_unavailable" in data.notes


def _market() -> NormalizedMarket:
    return NormalizedMarket(
        market_slug="btc-updown-15m-1774002600",
        event_slug="btc-15m-event",
        question="Will Bitcoin be above $101234.5 in 15 minutes?",
        event_title="Bitcoin 15 minute markets",
        active=True,
        closed=False,
        enable_order_book=True,
        condition_id="0x" + ("a" * 64),
        token_ids=["100", "101"],
        outcomes=["Up", "Down"],
        min_tick=0.01,
        min_order_size=5,
    )


@dataclass
class _FakeResponse:
    text: str
    status_code: int = 200


class _FakeClient:
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self._responses = responses

    def get(self, url: str) -> _FakeResponse:
        return self._responses[url]


class _FakeBrowserAdapter:
    def __init__(self, data: Btc15mPageParityData) -> None:
        self._data = data

    def fetch(self, market: NormalizedMarket, *, urls: list[str]) -> Btc15mPageParityData:
        _ = market
        _ = urls
        return self._data
