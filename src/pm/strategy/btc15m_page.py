"""Public page-parity helpers for the BTC15m operator terminal."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape

import httpx

from pm.market.models import NormalizedMarket

DEFAULT_POLYMARKET_WEB_URL = "https://polymarket.com"
DEFAULT_TIMEOUT = 5.0

_JSON_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "current_window_label": (
        "currentWindowLabel",
        "windowLabel",
        "window_label",
    ),
    "price_to_beat": (
        "priceToBeat",
        "price_to_beat",
    ),
    "current_live_btc_price": (
        "currentLiveBtcPrice",
        "currentBtcPrice",
        "currentPrice",
        "liveBtcPrice",
    ),
    "up_price": (
        "upPrice",
        "up_price",
    ),
    "down_price": (
        "downPrice",
        "down_price",
    ),
}

_VISIBLE_FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "price_to_beat": (
        re.compile(r"Price\s+to\s+beat[^0-9$]*\$?(?P<value>[0-9][0-9,\.]*)", re.I),
    ),
    "current_live_btc_price": (
        re.compile(
            r"(?:Current|Live)\s+BTC(?:/USD)?\s+price[^0-9$]*\$?(?P<value>[0-9][0-9,\.]*)",
            re.I,
        ),
    ),
    "up_price": (
        re.compile(r"\bUp\b[^0-9]{0,24}(?P<value>0?\.\d+|\d{1,2}(?:\.\d+)?)", re.I),
    ),
    "down_price": (
        re.compile(r"\bDown\b[^0-9]{0,24}(?P<value>0?\.\d+|\d{1,2}(?:\.\d+)?)", re.I),
    ),
}


@dataclass(slots=True)
class Btc15mPageParityData:
    """Best-effort public page values for BTC15m page parity."""

    event_url: str | None = None
    current_window_label: str | None = None
    price_to_beat: str | None = None
    current_live_btc_price: str | None = None
    up_price: str | None = None
    down_price: str | None = None
    notes: list[str] = field(default_factory=list)


class Btc15mPageParityService:
    """Best-effort public page extractor for BTC15m operator parity."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        base_url: str = DEFAULT_POLYMARKET_WEB_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._owns_client = client is None
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            self._client.close()

    def fetch(self, market: NormalizedMarket) -> Btc15mPageParityData:
        """Fetch best-effort parity values from the public event or market page."""
        last_error: str | None = None
        for url in _candidate_urls(self._base_url, market):
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue
            if response.status_code >= 400:
                last_error = f"status={response.status_code}"
                continue
            parsed = _extract_page_data(response.text)
            parsed.event_url = url
            if any(
                value is not None
                for value in (
                    parsed.current_window_label,
                    parsed.price_to_beat,
                    parsed.current_live_btc_price,
                    parsed.up_price,
                    parsed.down_price,
                )
            ):
                return parsed
            last_error = "page_fields_unavailable"
        data = Btc15mPageParityData()
        if last_error is not None:
            data.notes.append(last_error)
        return data


def _candidate_urls(base_url: str, market: NormalizedMarket) -> list[str]:
    urls: list[str] = []
    if market.event_slug:
        urls.append(f"{base_url}/event/{market.event_slug}")
    urls.append(f"{base_url}/market/{market.market_slug}")
    return urls


def _extract_page_data(html: str) -> Btc15mPageParityData:
    data = Btc15mPageParityData()
    text = unescape(html)
    for field_name, keys in _JSON_FIELD_PATTERNS.items():
        value = _extract_json_field(text, keys)
        if value is not None:
            setattr(data, field_name, value)
    for field_name, patterns in _VISIBLE_FIELD_PATTERNS.items():
        if getattr(data, field_name) is not None:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match is None:
                continue
            setattr(data, field_name, match.group("value"))
            break
    return data


def _extract_json_field(text: str, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        for pattern in (
            rf'"{re.escape(key)}"\s*:\s*"(?P<value>[^"]+)"',
            rf'"{re.escape(key)}"\s*:\s*(?P<value>[0-9][0-9,\.]*)',
        ):
            match = re.search(pattern, text)
            if match is not None:
                return _normalize_page_value(match.group("value"))
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_page_value(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("$"):
        return stripped[1:]
    return stripped
