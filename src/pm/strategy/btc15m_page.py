"""Public page-parity helpers for the BTC15m operator terminal."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Any

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
_STRUCTURED_SOURCE = "page_exact"
_ESTIMATED_SOURCE = "page_estimated"

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
    field_sources: dict[str, str] = field(default_factory=dict)
    matched_market_slug: str | None = None
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
            for field_name in (
                "current_window_label",
                "price_to_beat",
                "current_live_btc_price",
                "up_price",
                "down_price",
            )
        )


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
        best_data = Btc15mPageParityData()
        best_rank = -1
        for url in _candidate_urls(self._base_url, market):
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
        if best_data.has_fields():
            if last_error is not None and last_error not in best_data.notes:
                best_data.notes.append(last_error)
            return best_data
        if last_error is not None:
            best_data.notes.append(last_error)
        return best_data


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
        candidate.notes.append("structured_slug_match")
        rank = _page_data_rank(candidate)
        if rank > best_rank:
            best = candidate
            best_rank = rank
    return best


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
    return _normalize_text_value(value)


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
    return (exact * 100) + (estimated * 10) + label


def _has_full_exact_critical_fields(data: Btc15mPageParityData) -> bool:
    return all(
        data.field_sources.get(field_name) == _STRUCTURED_SOURCE
        for field_name in _CRITICAL_FIELDS
    )
