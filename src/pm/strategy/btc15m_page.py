"""Public page-parity helpers for the BTC15m operator terminal."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from importlib import import_module
from typing import Any, Protocol

import httpx

from pm.market.models import NormalizedMarket

DEFAULT_POLYMARKET_WEB_URL = "https://polymarket.com"
DEFAULT_TIMEOUT = 5.0

_CRITICAL_FIELDS = (
    "price_to_beat",
    "current_live_btc_price",
    "up_price",
    "down_price",
)
_DISPLAY_FIELDS = (
    "current_window_label",
    "price_to_beat",
    "current_live_btc_price",
    "up_price",
    "down_price",
    "volume",
)
_STRUCTURED_SOURCE = "page_exact"
_ESTIMATED_SOURCE = "page_estimated"
_CENT_MARKER_REGEX = r"(?:\u00A2|c)"

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
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
        "liveBtcPrice",
        "btcPrice",
        "btcUsdPrice",
    ),
    "up_price": (
        "upPrice",
        "up_price",
    ),
    "down_price": (
        "downPrice",
        "down_price",
    ),
    "volume": (
        "volume",
        "displayVolume",
        "marketVolume",
        "display_volume",
    ),
}
_MARKET_SLUG_KEYS = ("marketSlug", "market_slug", "slug")
_OUTCOME_KEYS = ("outcome", "label", "name", "title", "tokenName")
_OUTCOME_PRICE_KEYS = ("price", "displayPrice", "lastPrice", "midPrice", "value")
_OUTCOME_ARRAY_NAME_KEYS = ("outcomes", "outcomeNames", "labels")
_OUTCOME_ARRAY_PRICE_KEYS = ("prices", "outcomePrices", "displayPrices")

_VISIBLE_FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "price_to_beat": (
        re.compile(r"price\s+to\s+beat[^0-9$]{0,32}\$?(?P<value>[0-9][0-9,\.]*)", re.I),
    ),
    "current_live_btc_price": (
        re.compile(
            r"(?:current|live)\s+btc(?:/usd)?(?:\s+price)?[^0-9$]{0,32}\$?(?P<value>[0-9][0-9,\.]*)",
            re.I,
        ),
    ),
    "up_price": (
        re.compile(
            r"\bup\b(?:\s+price)?[^0-9$¢]{0,16}(?P<value>\d{1,2}\s*¢|0?\.\d+)",
            re.I,
        ),
    ),
    "down_price": (
        re.compile(
            r"\bdown\b(?:\s+price)?[^0-9$¢]{0,16}(?P<value>\d{1,2}\s*¢|0?\.\d+)",
            re.I,
        ),
    ),
}
_VISIBLE_FIELD_PATTERNS["volume"] = (
    re.compile(
        r"\bvolume\b[^0-9$]{0,24}\$?(?P<value>[0-9][0-9,\.]*(?:\s*[kmb])?)",
        re.I,
    ),
)
_BROWSER_EXACT_FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "price_to_beat": (
        re.compile(r"\bprice\s+to\s+beat\b[^0-9$]{0,20}\$?(?P<value>[0-9][0-9,\.]*)", re.I),
    ),
    "current_live_btc_price": (
        re.compile(
            r"\bcurrent(?:\s+price|\s+btc(?:/usd)?(?:\s+price)?)\b[^0-9$]{0,20}\$?(?P<value>[0-9][0-9,\.]*)",
            re.I,
        ),
    ),
    "up_price": (
        re.compile(
            r"\bup\b(?:\s+price)?[^0-9$Вў]{0,12}(?P<value>\d{1,2}\s*Вў|0?\.\d+)",
            re.I,
        ),
    ),
    "down_price": (
        re.compile(
            r"\bdown\b(?:\s+price)?[^0-9$Вў]{0,12}(?P<value>\d{1,2}\s*Вў|0?\.\d+)",
            re.I,
        ),
    ),
    "volume": (
        re.compile(
            r"\bvolume\b[^0-9$]{0,20}\$?(?P<value>[0-9][0-9,\.]*(?:\s*[kmb])?)",
            re.I,
        ),
    ),
}

# Override cent-price parsing with explicit cent-sign support for visible and
# browser-rendered page text. This keeps exact page extraction tied to the
# actual rendered page values instead of depending on mojibake-specific bytes.
_VISIBLE_FIELD_PATTERNS["up_price"] = (
    re.compile(
        rf"\bup\b(?:\s+price)?[^0-9$]{{0,16}}(?P<value>\d{{1,2}}(?:\s*{_CENT_MARKER_REGEX})?|0?\.\d+)",
        re.I,
    ),
)
_VISIBLE_FIELD_PATTERNS["down_price"] = (
    re.compile(
        rf"\bdown\b(?:\s+price)?[^0-9$]{{0,16}}(?P<value>\d{{1,2}}(?:\s*{_CENT_MARKER_REGEX})?|0?\.\d+)",
        re.I,
    ),
)
_BROWSER_EXACT_FIELD_PATTERNS["up_price"] = (
    re.compile(
        rf"\bup\b(?:\s+price)?[^0-9$]{{0,12}}(?P<value>\d{{1,2}}(?:\s*{_CENT_MARKER_REGEX})?|0?\.\d+)",
        re.I,
    ),
)
_BROWSER_EXACT_FIELD_PATTERNS["down_price"] = (
    re.compile(
        rf"\bdown\b(?:\s+price)?[^0-9$]{{0,12}}(?P<value>\d{{1,2}}(?:\s*{_CENT_MARKER_REGEX})?|0?\.\d+)",
        re.I,
    ),
)

_SCRIPT_PATTERN = re.compile(
    r"<script\b[^>]*>(?P<body>.*?)</script>",
    re.I | re.S,
)
_JSON_ASSIGNMENT_PATTERN = re.compile(
    r"(?:window\.)?[A-Za-z0-9_$.]+\s*=\s*(?P<value>\{.*|\[.*)",
    re.S,
)


@dataclass(slots=True)
class Btc15mPageParityData:
    """Best-effort public page values for BTC15m page parity."""

    event_url: str | None = None
    current_window_label: str | None = None
    price_to_beat: str | None = None
    current_live_btc_price: str | None = None
    up_price: str | None = None
    down_price: str | None = None
    volume: str | None = None
    field_sources: dict[str, str] = field(default_factory=dict)
    matched_market_slug: str | None = None
    observed_at: str | None = None
    stale: bool = False
    notes: list[str] = field(default_factory=list)

    def set_field(self, field_name: str, value: str | None, source: str) -> None:
        """Persist a normalized extracted page field with its provenance."""
        if value is None:
            return
        setattr(self, field_name, value)
        self.field_sources[field_name] = source

    def has_fields(self) -> bool:
        """Return whether any operator-facing page field was extracted."""
        return any(
            getattr(self, field_name) is not None
            for field_name in _DISPLAY_FIELDS
        )

    def stale_copy(self, *notes: str) -> Btc15mPageParityData:
        """Return one stale copy that keeps the last valid visible page state."""
        return replace(
            self,
            stale=True,
            notes=_merge_notes(self.notes, [*notes, "stale_last_valid_snapshot"]),
        )


class Btc15mPageBrowserAdapter(Protocol):
    """Optional browser-rendered public page adapter for exact BTC15m parity."""

    def fetch(self, market: NormalizedMarket, *, urls: list[str]) -> Btc15mPageParityData:
        """Fetch exact visible public page values for one BTC15m market."""


class PlaywrightBtc15mPageBrowserAdapter:
    """Best-effort Playwright-backed adapter for exact visible public page state."""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout_ms = max(1, int(timeout * 1000))

    def fetch(self, market: NormalizedMarket, *, urls: list[str]) -> Btc15mPageParityData:
        try:
            sync_api = import_module("playwright.sync_api")
        except ImportError:
            return Btc15mPageParityData(notes=["browser_adapter_unavailable"])

        sync_playwright = getattr(sync_api, "sync_playwright", None)
        if sync_playwright is None:
            return Btc15mPageParityData(notes=["browser_adapter_unavailable"])

        best = Btc15mPageParityData(notes=["browser_exact_unavailable"])
        best_rank = -1
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    for url in urls:
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
                            try:
                                page.wait_for_load_state(
                                    "networkidle",
                                    timeout=min(self._timeout_ms, 2000),
                                )
                            except Exception:
                                pass
                            html = page.content()
                            visible_text = page.locator("body").inner_text(timeout=self._timeout_ms)
                            browser_payload = _capture_browser_page_payload(
                                page,
                                timeout_ms=self._timeout_ms,
                            )
                        except Exception as exc:
                            candidate = Btc15mPageParityData(notes=[f"browser_fetch_failed:{exc}"])
                        else:
                            candidate = _extract_browser_payload_data(
                                browser_payload,
                                market=market,
                            )
                            if not candidate.has_fields():
                                candidate = _extract_browser_page_data(
                                    html,
                                    visible_text=visible_text,
                                    market=market,
                                )
                            candidate.event_url = url
                        rank = _page_data_rank(candidate)
                        if rank > best_rank:
                            best = candidate
                            best_rank = rank
                        if _has_full_exact_terminal_fields(candidate):
                            return candidate
                finally:
                    browser.close()
        except Exception as exc:
            return Btc15mPageParityData(notes=[f"browser_adapter_unavailable:{exc}"])
        return best


class Btc15mPageParityService:
    """Best-effort public page extractor for BTC15m operator parity."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        base_url: str = DEFAULT_POLYMARKET_WEB_URL,
        timeout: float = DEFAULT_TIMEOUT,
        browser_adapter: Btc15mPageBrowserAdapter | None = None,
    ) -> None:
        self._owns_client = client is None
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)
        self._browser_adapter = browser_adapter or PlaywrightBtc15mPageBrowserAdapter(
            timeout=timeout
        )

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            self._client.close()

    def fetch(self, market: NormalizedMarket) -> Btc15mPageParityData:
        """Fetch best-effort parity values from the public event or market page."""
        last_error: str | None = None
        best_data = Btc15mPageParityData()
        best_rank = -1
        urls = _candidate_urls(self._base_url, market)
        for url in urls:
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue
            if response.status_code >= 400:
                last_error = f"status={response.status_code}"
                continue
            parsed = _extract_page_data(response.text, market=market)
            parsed.event_url = url
            rank = _page_data_rank(parsed)
            if rank > best_rank:
                best_data = parsed
                best_rank = rank
            if _has_full_exact_critical_fields(parsed):
                return parsed
            if parsed.has_fields():
                last_error = "page_fields_partial"
            else:
                last_error = "page_fields_unavailable"
        browser_data = self._browser_adapter.fetch(market, urls=urls)
        merged = _merge_page_data(best_data, browser_data)
        merged_rank = _page_data_rank(merged)
        if merged_rank >= best_rank:
            best_data = merged
            best_rank = merged_rank
        else:
            best_data.notes = _merge_notes(best_data.notes, browser_data.notes)
        if _has_full_exact_critical_fields(best_data):
            return _stamp_page_data(best_data)
        if best_data.has_fields():
            if last_error is not None and last_error not in best_data.notes:
                best_data.notes.append(last_error)
            return _stamp_page_data(best_data)
        if last_error is not None:
            best_data.notes.append(last_error)
        return _stamp_page_data(best_data)

    def fetch_terminal_current(
        self,
        market: NormalizedMarket,
        *,
        previous: Btc15mPageParityData | None = None,
    ) -> Btc15mPageParityData:
        """Fetch current-window terminal page truth from the rendered public page first."""
        urls = _candidate_urls(self._base_url, market)
        browser_data = self._browser_adapter.fetch(market, urls=urls)
        browser_data = _stamp_page_data(browser_data)
        if _has_full_exact_terminal_fields(browser_data):
            browser_data.stale = False
            return browser_data
        if previous is not None and _has_full_exact_terminal_fields(previous):
            stale = previous.stale_copy(*browser_data.notes)
            stale.event_url = browser_data.event_url or previous.event_url
            stale.matched_market_slug = (
                previous.matched_market_slug or browser_data.matched_market_slug
            )
            return stale
        if previous is not None and previous.has_fields() and browser_data.notes:
            browser_data.notes = _merge_notes(previous.notes, browser_data.notes)
        return browser_data


def _candidate_urls(base_url: str, market: NormalizedMarket) -> list[str]:
    urls: list[str] = []
    if market.event_slug:
        urls.append(f"{base_url}/event/{market.event_slug}")
    urls.append(f"{base_url}/market/{market.market_slug}")
    return urls


def _extract_page_data(html: str, *, market: NormalizedMarket) -> Btc15mPageParityData:
    data = _extract_structured_page_data(unescape(html), market=market)
    visible_text = _collapse_visible_text(html)
    if data.current_window_label is None:
        label = _extract_visible_window_label(visible_text)
        if label is not None:
            data.set_field("current_window_label", label, _ESTIMATED_SOURCE)
    for field_name, patterns in _VISIBLE_FIELD_PATTERNS.items():
        if getattr(data, field_name) is not None:
            continue
        for pattern in patterns:
            match = pattern.search(visible_text)
            if match is None:
                continue
            value = _normalize_visible_field(field_name, match.group("value"))
            if value is None:
                data.notes.append(f"{field_name}_visible_rejected")
                break
            data.set_field(field_name, value, _ESTIMATED_SOURCE)
            break
    return data


def _extract_browser_page_data(
    html: str,
    *,
    visible_text: str,
    market: NormalizedMarket,
) -> Btc15mPageParityData:
    structured = _extract_structured_page_data(unescape(html), market=market)
    visible_exact = _extract_browser_visible_exact_data(
        html,
        visible_text=visible_text,
        market=market,
    )
    return _merge_page_data(structured, visible_exact)


def _capture_browser_page_payload(page: Any, *, timeout_ms: int) -> dict[str, Any]:
    _ = timeout_ms
    payload = page.evaluate(
        """
        () => {
          const text = (value) => {
            if (typeof value !== "string") return null;
            const trimmed = value.replace(/\\s+/g, " ").trim();
            return trimmed || null;
          };
          const scripts = Array.from(
            document.querySelectorAll("script, script[type='application/json']")
          )
            .map((node) => text(node.textContent))
            .filter((value) => value !== null);
          const nextDataNode = document.querySelector("#__NEXT_DATA__");
          let nextData = null;
          if (nextDataNode && nextDataNode.textContent) {
            nextData = text(nextDataNode.textContent);
          }
          const bodyText = text(document.body ? document.body.innerText : null);
          return {
            url: window.location.href,
            title: text(document.title),
            body_text: bodyText,
            next_data: nextData,
            scripts,
          };
        }
        """,
    )
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_browser_payload_data(
    payload: dict[str, Any],
    *,
    market: NormalizedMarket,
) -> Btc15mPageParityData:
    scripts: list[str] = []
    next_data = payload.get("next_data")
    if isinstance(next_data, str) and next_data.strip():
        scripts.append(next_data)
    raw_scripts = payload.get("scripts")
    if isinstance(raw_scripts, list):
        scripts.extend(item for item in raw_scripts if isinstance(item, str) and item.strip())

    best = Btc15mPageParityData()
    best_rank = -1
    for script_text in scripts:
        structured = _extract_structured_page_data(script_text, market=market)
        rank = _page_data_rank(structured)
        if rank > best_rank:
            best = structured
            best_rank = rank

    visible_text = payload.get("body_text")
    url = payload.get("url")
    title = payload.get("title")
    if not isinstance(visible_text, str):
        return best
    slug_haystack = " ".join(
        item
        for item in (
            str(url) if url is not None else None,
            str(title) if title is not None else None,
            visible_text,
        )
        if item
    )
    visible = _extract_browser_visible_exact_data(
        slug_haystack,
        visible_text=visible_text,
        market=market,
    )
    return _merge_page_data(best, visible)


def _extract_structured_page_data(text: str, *, market: NormalizedMarket) -> Btc15mPageParityData:
    best = Btc15mPageParityData()
    best_rank = -1
    for payload in _extract_structured_payloads(text):
        candidate = _extract_market_exact_data(payload, market=market)
        rank = _page_data_rank(candidate)
        if rank > best_rank:
            best = candidate
            best_rank = rank
    return best


def _extract_structured_payloads(text: str) -> list[Any]:
    payloads: list[Any] = []
    for match in _SCRIPT_PATTERN.finditer(text):
        body = match.group("body").strip()
        if not body:
            continue
        payload = _parse_script_payload(body)
        if payload is not None:
            payloads.append(payload)
    return payloads


def _parse_script_payload(body: str) -> Any | None:
    stripped = body.strip()
    if not stripped:
        return None
    direct = _json_loads_maybe(stripped)
    if direct is not None:
        return direct
    assignment_match = _JSON_ASSIGNMENT_PATTERN.search(stripped)
    if assignment_match is None:
        return None
    candidate = assignment_match.group("value").strip()
    if not candidate:
        return None
    if candidate[0] not in "{[":
        return None
    extracted = _extract_balanced_json_prefix(candidate)
    if extracted is None:
        return None
    return _json_loads_maybe(extracted)


def _json_loads_maybe(text: str) -> Any | None:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _extract_balanced_json_prefix(text: str) -> str | None:
    opening = text[0]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == opening:
            depth += 1
            continue
        if char == closing:
            depth -= 1
            if depth == 0:
                return text[: index + 1]
    return None


def _extract_market_exact_data(payload: Any, *, market: NormalizedMarket) -> Btc15mPageParityData:
    best = Btc15mPageParityData()
    best_rank = -1
    for node in _iter_nodes(payload):
        if not isinstance(node, dict):
            continue
        if not _node_matches_market_slug(node, market.market_slug):
            continue
        candidate = Btc15mPageParityData(matched_market_slug=market.market_slug)
        candidate.set_field(
            "current_window_label",
            _find_field_value(node, "current_window_label", normalizer=_normalize_text_value),
            _STRUCTURED_SOURCE,
        )
        candidate.set_field(
            "price_to_beat",
            _find_field_value(node, "price_to_beat", normalizer=_normalize_btc_value),
            _STRUCTURED_SOURCE,
        )
        candidate.set_field(
            "current_live_btc_price",
            _find_field_value(
                node,
                "current_live_btc_price",
                normalizer=_normalize_btc_value,
            ),
            _STRUCTURED_SOURCE,
        )
        up_price, down_price = _extract_outcome_prices(node)
        candidate.set_field("up_price", up_price, _STRUCTURED_SOURCE)
        candidate.set_field("down_price", down_price, _STRUCTURED_SOURCE)
        candidate.set_field(
            "volume",
            _find_field_value(node, "volume", normalizer=_normalize_volume_value),
            _STRUCTURED_SOURCE,
        )
        candidate.notes.append("structured_slug_match")
        rank = _page_data_rank(candidate)
        if rank > best_rank:
            best = candidate
            best_rank = rank
    return best


def _extract_browser_visible_exact_data(
    html: str,
    *,
    visible_text: str,
    market: NormalizedMarket,
) -> Btc15mPageParityData:
    data = Btc15mPageParityData()
    html_lower = html.lower()
    if market.market_slug.lower() not in html_lower:
        data.notes.append("browser_slug_unmatched")
        return data
    data.matched_market_slug = market.market_slug
    for field_name, patterns in _BROWSER_EXACT_FIELD_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(visible_text)
            if match is None:
                continue
            value = _normalize_browser_visible_field(field_name, match.group("value"))
            if value is None:
                data.notes.append(f"{field_name}_browser_visible_rejected")
                break
            data.set_field(field_name, value, _STRUCTURED_SOURCE)
            break
    if data.has_fields():
        data.notes.append("browser_exact_visible_match")
    else:
        data.notes.append("browser_exact_unavailable")
    return data


def _iter_nodes(value: Any) -> list[Any]:
    nodes: list[Any] = [value]
    if isinstance(value, dict):
        for nested in value.values():
            nodes.extend(_iter_nodes(nested))
    elif isinstance(value, list):
        for nested in value:
            nodes.extend(_iter_nodes(nested))
    return nodes


def _node_matches_market_slug(node: dict[str, Any], market_slug: str) -> bool:
    for key in _MARKET_SLUG_KEYS:
        value = node.get(key)
        if isinstance(value, str) and value.strip() == market_slug:
            return True
    return False


def _find_field_value(
    node: Any,
    field_name: str,
    *,
    normalizer: Callable[[Any], str | None],
) -> str | None:
    aliases = _FIELD_ALIASES[field_name]
    if isinstance(node, dict):
        for key, value in node.items():
            if key in aliases:
                normalized = normalizer(value)
                if normalized is not None:
                    return normalized
            normalized = _find_field_value(value, field_name, normalizer=normalizer)
            if normalized is not None:
                return normalized
    elif isinstance(node, list):
        for value in node:
            normalized = _find_field_value(value, field_name, normalizer=normalizer)
            if normalized is not None:
                return normalized
    return None


def _extract_outcome_prices(node: Any) -> tuple[str | None, str | None]:
    up_price = _find_field_value(node, "up_price", normalizer=_normalize_outcome_price)
    down_price = _find_field_value(node, "down_price", normalizer=_normalize_outcome_price)
    if up_price is not None or down_price is not None:
        return up_price, down_price
    direct_up, direct_down = _extract_outcome_prices_from_nodes(node)
    if direct_up is not None or direct_down is not None:
        return direct_up, direct_down
    return _extract_outcome_prices_from_arrays(node)


def _extract_outcome_prices_from_nodes(node: Any) -> tuple[str | None, str | None]:
    up_price: str | None = None
    down_price: str | None = None
    for item in _iter_nodes(node):
        if not isinstance(item, dict):
            continue
        outcome_name = _normalize_outcome_name(item)
        if outcome_name not in {"up", "down"}:
            continue
        for key in _OUTCOME_PRICE_KEYS:
            normalized = _normalize_outcome_price(item.get(key))
            if normalized is None:
                continue
            if outcome_name == "up":
                up_price = normalized
            else:
                down_price = normalized
            break
    return up_price, down_price


def _extract_outcome_prices_from_arrays(node: Any) -> tuple[str | None, str | None]:
    for item in _iter_nodes(node):
        if not isinstance(item, dict):
            continue
        outcomes = None
        prices = None
        for key in _OUTCOME_ARRAY_NAME_KEYS:
            if isinstance(item.get(key), list):
                outcomes = item.get(key)
                break
        for key in _OUTCOME_ARRAY_PRICE_KEYS:
            if isinstance(item.get(key), list):
                prices = item.get(key)
                break
        if not isinstance(outcomes, list) or not isinstance(prices, list):
            continue
        if len(outcomes) != len(prices):
            continue
        up_price: str | None = None
        down_price: str | None = None
        for outcome_name, price in zip(outcomes, prices, strict=False):
            outcome_key = _normalize_outcome_text(outcome_name)
            normalized_price = _normalize_outcome_price(price)
            if normalized_price is None:
                continue
            if outcome_key == "up":
                up_price = normalized_price
            if outcome_key == "down":
                down_price = normalized_price
        if up_price is not None or down_price is not None:
            return up_price, down_price
    return None, None


def _normalize_outcome_name(node: dict[str, Any]) -> str | None:
    for key in _OUTCOME_KEYS:
        normalized = _normalize_outcome_text(node.get(key))
        if normalized is not None:
            return normalized
    return None


def _normalize_outcome_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered == "up":
        return "up"
    if lowered == "down":
        return "down"
    return None


def _collapse_visible_text(text: str) -> str:
    visible = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    visible = re.sub(r"<style\b[^>]*>.*?</style>", " ", visible, flags=re.I | re.S)
    visible = re.sub(r"<[^>]+>", " ", visible)
    visible = unescape(visible)
    visible = re.sub(r"\s+", " ", visible)
    return visible.strip()


def _extract_visible_window_label(text: str) -> str | None:
    match = re.search(
        r"\b(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})\s*(?:UTC)?\b",
        text,
    )
    if match is None:
        return None
    label = f"{match.group('start')} - {match.group('end')} UTC"
    return _normalize_text_value(label)


def _normalize_visible_field(field_name: str, value: str) -> str | None:
    if field_name in {"price_to_beat", "current_live_btc_price"}:
        return _normalize_btc_value(value)
    if field_name in {"up_price", "down_price"}:
        return _normalize_outcome_price(value)
    if field_name == "volume":
        return _normalize_volume_value(value)
    return _normalize_text_value(value)


def _normalize_browser_visible_field(field_name: str, value: str) -> str | None:
    return _normalize_visible_field(field_name, value)


def _normalize_text_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = " ".join(value.strip().split())
    if not stripped:
        return None
    return stripped


def _normalize_btc_value(value: Any) -> str | None:
    normalized = _normalize_numeric_text(value)
    if normalized is None:
        return None
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        return None
    if parsed < Decimal("100"):
        return None
    return normalized


def _normalize_outcome_price(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        if parsed < 0 or parsed > 1:
            return None
        return _trim_decimal(parsed)
    if not isinstance(value, str):
        return None
    stripped = value.strip().replace("$", "")
    modern_cents_match = re.fullmatch(
        rf"(?P<cents>\d{{1,2}})(?:\s*{_CENT_MARKER_REGEX})",
        stripped,
        re.I,
    )
    if modern_cents_match is not None:
        cents = Decimal(modern_cents_match.group("cents")) / Decimal("100")
        return _trim_decimal(cents)
    cents_match = re.fullmatch(r"(?P<cents>\d{1,2})(?:\s*¢|\s*c)", stripped, re.I)
    if cents_match is not None:
        cents = Decimal(cents_match.group("cents")) / Decimal("100")
        return _trim_decimal(cents)
    numeric = _normalize_numeric_text(stripped)
    if numeric is None:
        return None
    try:
        parsed = Decimal(numeric)
    except InvalidOperation:
        return None
    if parsed < 0 or parsed > 1:
        return None
    return _trim_decimal(parsed)


def _normalize_volume_value(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        numeric = _normalize_numeric_text(value)
        return numeric
    if not isinstance(value, str):
        return None
    stripped = " ".join(value.strip().split()).replace("$", "")
    if not stripped:
        return None
    if re.fullmatch(r"[0-9][0-9,\.]*(?:\s*[kmb])?", stripped, re.I):
        return stripped.upper().replace(" ", "")
    return None


def _normalize_numeric_text(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return None
    stripped = value.strip().replace("$", "").replace(",", "")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", stripped):
        return None
    return stripped


def _trim_decimal(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." not in normalized:
        return normalized
    return normalized.rstrip("0").rstrip(".")


def _merge_page_data(
    primary: Btc15mPageParityData,
    secondary: Btc15mPageParityData,
) -> Btc15mPageParityData:
    merged = Btc15mPageParityData(
        event_url=secondary.event_url or primary.event_url,
        matched_market_slug=secondary.matched_market_slug or primary.matched_market_slug,
        notes=_merge_notes(primary.notes, secondary.notes),
    )
    for field_name in _DISPLAY_FIELDS:
        primary_source = primary.field_sources.get(field_name)
        secondary_source = secondary.field_sources.get(field_name)
        primary_value = getattr(primary, field_name)
        secondary_value = getattr(secondary, field_name)
        if _field_source_rank(secondary_source) > _field_source_rank(primary_source):
            if secondary_value is not None:
                merged.set_field(field_name, secondary_value, secondary_source or _ESTIMATED_SOURCE)
                continue
        if primary_value is not None:
            merged.set_field(field_name, primary_value, primary_source or _ESTIMATED_SOURCE)
            continue
        if secondary_value is not None:
            merged.set_field(field_name, secondary_value, secondary_source or _ESTIMATED_SOURCE)
    return merged


def _field_source_rank(source: str | None) -> int:
    if source == _STRUCTURED_SOURCE:
        return 2
    if source == _ESTIMATED_SOURCE:
        return 1
    return 0


def _merge_notes(primary: list[str], secondary: list[str]) -> list[str]:
    merged: list[str] = []
    for note in [*primary, *secondary]:
        if note not in merged:
            merged.append(note)
    return merged


def _page_data_rank(data: Btc15mPageParityData) -> int:
    exact = sum(
        1
        for field_name in _CRITICAL_FIELDS
        if data.field_sources.get(field_name) == _STRUCTURED_SOURCE
    )
    estimated = sum(
        1
        for field_name in _CRITICAL_FIELDS
        if data.field_sources.get(field_name) == _ESTIMATED_SOURCE
    )
    label = 1 if data.current_window_label is not None else 0
    volume_exact = 5 if data.field_sources.get("volume") == _STRUCTURED_SOURCE else 0
    volume_estimated = 1 if data.field_sources.get("volume") == _ESTIMATED_SOURCE else 0
    return (exact * 100) + (estimated * 10) + volume_exact + volume_estimated + label


def _has_full_exact_critical_fields(data: Btc15mPageParityData) -> bool:
    return all(
        data.field_sources.get(field_name) == _STRUCTURED_SOURCE
        for field_name in _CRITICAL_FIELDS
    )


def _has_full_exact_terminal_fields(data: Btc15mPageParityData) -> bool:
    required_fields = (*_CRITICAL_FIELDS, "volume")
    return all(
        data.field_sources.get(field_name) == _STRUCTURED_SOURCE
        and getattr(data, field_name) is not None
        for field_name in required_fields
    )


def _stamp_page_data(data: Btc15mPageParityData) -> Btc15mPageParityData:
    if data.observed_at is not None:
        return data
    data.observed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return data
