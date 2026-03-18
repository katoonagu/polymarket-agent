"""Read-only client for the public Polymarket Data API."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from pm import __version__
from pm.data.models import (
    ActivityResponse,
    ClosedPositionsResponse,
    HoldersResponse,
    LeaderboardResponse,
    NormalizedActivity,
    NormalizedClosedPosition,
    NormalizedCurrentPosition,
    NormalizedHolder,
    NormalizedHoldingsValue,
    NormalizedLeaderboardEntry,
    NormalizedOpenInterest,
    NormalizedTrade,
    NormalizedTradedCount,
    PositionsResponse,
    TradesResponse,
)
from pm.market.exceptions import GammaClientError, GammaNotFoundError
from pm.market.gamma import GammaClient

DEFAULT_DATA_URL = "https://data-api.polymarket.com"
DEFAULT_TIMEOUT = 10.0
DEFAULT_LIMIT = 20
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
CONDITION_ID_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
QueryValue = str | int | float | bool | None
QueryMapping = dict[str, QueryValue]


class DataClientError(RuntimeError):
    """Raised when the Data API returns an unexpected response."""


class DataNotFoundError(DataClientError):
    """Raised when a Data API lookup returns no records."""


class DataValidationError(DataClientError):
    """Raised when CLI-facing arguments fail validation."""


class DataClient:
    """Small sync client for the public Polymarket Data API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=(base_url or os.getenv("POLYMARKET_DATA_URL") or DEFAULT_DATA_URL).rstrip("/"),
            timeout=timeout,
            headers={"User-Agent": f"polymarket-agent/{__version__}"},
        )

    def __enter__(self) -> DataClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_client:
            self._client.close()

    def get_user_trades(self, user: str, limit: int = DEFAULT_LIMIT) -> TradesResponse:
        """Fetch public trades for a user."""
        normalized_user = validate_user_address(user)
        payload = self._get_json("/trades", params={"user": normalized_user, "limit": limit})
        items = _ensure_list(payload, "trades")
        trades = [
            NormalizedTrade(
                user=_string_or_default(item.get("proxyWallet"), normalized_user),
                market_slug=_string_or_none(item.get("slug")),
                condition_id=_string_or_none(item.get("conditionId")),
                token_id=_string_or_none(item.get("asset")),
                side=_string_or_none(item.get("side")),
                outcome=_string_or_none(item.get("outcome")),
                price=_decimal_or_none(item.get("price")),
                size=_decimal_or_none(item.get("size")),
                timestamp=_int_or_none(item.get("timestamp")),
                transaction_hash=_string_or_none(item.get("transactionHash")),
            )
            for item in items
        ]
        return TradesResponse(user=normalized_user, items=trades, total=len(trades))

    def get_user_activity(self, user: str, limit: int = DEFAULT_LIMIT) -> ActivityResponse:
        """Fetch public activity for a user."""
        normalized_user = validate_user_address(user)
        payload = self._get_json("/activity", params={"user": normalized_user, "limit": limit})
        items = _ensure_list(payload, "activity")
        activities = [
            NormalizedActivity(
                user=_string_or_default(item.get("proxyWallet"), normalized_user),
                market_slug=_string_or_none(item.get("slug")),
                condition_id=_string_or_none(item.get("conditionId")),
                token_id=_string_or_none(item.get("asset")),
                activity_type=_string_or_default(item.get("type"), "UNKNOWN"),
                side=_string_or_none(item.get("side")),
                outcome=_string_or_none(item.get("outcome")),
                price=_decimal_or_none(item.get("price")),
                size=_decimal_or_none(item.get("size")),
                usdc_size=_decimal_or_none(item.get("usdcSize")),
                timestamp=_int_or_none(item.get("timestamp")),
                transaction_hash=_string_or_none(item.get("transactionHash")),
            )
            for item in items
        ]
        return ActivityResponse(user=normalized_user, items=activities, total=len(activities))

    def get_current_positions(self, user: str) -> PositionsResponse:
        """Fetch current positions for a user."""
        normalized_user = validate_user_address(user)
        payload = self._get_json("/positions", params={"user": normalized_user})
        items = _ensure_list(payload, "positions")
        positions = [
            NormalizedCurrentPosition(
                user=_string_or_default(item.get("proxyWallet"), normalized_user),
                market_slug=_string_or_none(item.get("slug")),
                condition_id=_string_or_none(item.get("conditionId")),
                token_id=_string_or_none(item.get("asset")),
                outcome=_string_or_none(item.get("outcome")),
                size=_decimal_or_none(item.get("size")),
                average_price=_decimal_or_none(item.get("avgPrice")),
                initial_value=_decimal_or_none(item.get("initialValue")),
                current_value=_decimal_or_none(item.get("currentValue")),
                cash_pnl=_decimal_or_none(item.get("cashPnl")),
                percent_pnl=_decimal_or_none(item.get("percentPnl")),
            )
            for item in items
        ]
        return PositionsResponse(user=normalized_user, items=positions, total=len(positions))

    def get_closed_positions(self, user: str) -> ClosedPositionsResponse:
        """Fetch closed positions for a user."""
        normalized_user = validate_user_address(user)
        payload = self._get_json("/closed-positions", params={"user": normalized_user})
        items = _ensure_list(payload, "closed positions")
        positions = [
            NormalizedClosedPosition(
                user=_string_or_default(item.get("proxyWallet"), normalized_user),
                market_slug=_string_or_none(item.get("slug")),
                condition_id=_string_or_none(item.get("conditionId")),
                token_id=_string_or_none(item.get("asset")),
                outcome=_string_or_none(item.get("outcome")),
                average_price=_decimal_or_none(item.get("avgPrice")),
                total_bought=_decimal_or_none(item.get("totalBought")),
                realized_pnl=_decimal_or_none(item.get("realizedPnl")),
                current_price=_decimal_or_none(item.get("curPrice")),
                timestamp=_int_or_none(item.get("timestamp")),
            )
            for item in items
        ]
        return ClosedPositionsResponse(user=normalized_user, items=positions, total=len(positions))

    def get_holders(self, market_ref: str, limit: int = DEFAULT_LIMIT) -> HoldersResponse:
        """Fetch public top holders for a market reference."""
        resolved_market = self._resolve_market_ref(market_ref)
        payload = self._get_json(
            "/holders",
            params={"market": resolved_market.condition_id, "limit": limit},
        )
        holders = _normalize_holders(payload, resolved_market=resolved_market)
        return HoldersResponse(
            market_slug=resolved_market.market_slug,
            condition_id=resolved_market.condition_id,
            items=holders,
            total=len(holders),
        )

    def get_open_interest(self, market_ref: str) -> NormalizedOpenInterest:
        """Fetch public open interest for a market reference."""
        resolved_market = self._resolve_market_ref(market_ref)
        payload = self._get_json("/oi", params={"market": resolved_market.condition_id})
        items = [payload] if isinstance(payload, dict) else _ensure_list(payload, "open interest")
        if not items:
            raise DataNotFoundError(f"market '{resolved_market.condition_id}' was not found.")

        for item in items:
            market_id = _string_or_none(item.get("market")) or _string_or_none(
                item.get("conditionId")
            )
            if market_id == resolved_market.condition_id:
                return NormalizedOpenInterest(
                    market_slug=resolved_market.market_slug,
                    condition_id=resolved_market.condition_id,
                    open_interest=_decimal_or_default(
                        item.get("value") if "value" in item else item.get("openInterest"),
                        "0",
                    ),
                )

        raise DataNotFoundError(f"market '{resolved_market.condition_id}' was not found.")

    def get_holdings_value(self, user: str) -> NormalizedHoldingsValue:
        """Fetch current holdings value for a user."""
        normalized_user = validate_user_address(user)
        payload = self._get_json("/value", params={"user": normalized_user})
        if isinstance(payload, dict):
            first_item = payload
        else:
            items = _ensure_list(payload, "holdings value")
            if not items:
                raise DataNotFoundError(f"user '{normalized_user}' has no holdings value.")
            first_item = items[0]
        return NormalizedHoldingsValue(
            user=_string_or_default(first_item.get("user"), normalized_user),
            value=_decimal_or_default(first_item.get("value"), "0"),
        )

    def get_traded_count(self, user: str) -> NormalizedTradedCount:
        """Fetch total traded-market count for a user."""
        normalized_user = validate_user_address(user)
        payload = self._get_json("/traded", params={"user": normalized_user})
        item = _ensure_mapping(payload, "traded count")
        traded = item.get("traded")
        if not isinstance(traded, int):
            raise DataClientError(
                "Data API traded response did not include an integer traded count."
            )
        return NormalizedTradedCount(
            user=_string_or_default(item.get("user"), normalized_user),
            traded=traded,
        )

    def get_leaderboard(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        user: str | None = None,
        category: str = "OVERALL",
        time_period: str = "ALL",
        order_by: str = "PNL",
    ) -> LeaderboardResponse:
        """Fetch public trader leaderboard rows."""
        normalized_user = validate_user_address(user) if user is not None else None
        payload = self._get_json(
            "/v1/leaderboard",
            params={
                "category": category,
                "timePeriod": time_period,
                "orderBy": order_by,
                "limit": limit,
                "user": normalized_user,
            },
        )
        items = _ensure_leaderboard_items(payload)
        entries: list[NormalizedLeaderboardEntry] = []

        for item in items:
            entry = _normalize_leaderboard_entry(item)
            if entry is None:
                continue
            if normalized_user is not None and entry.address.lower() != normalized_user.lower():
                continue
            entries.append(entry)

        return LeaderboardResponse(items=entries, total=len(entries))

    def _resolve_market_ref(self, market_ref: str) -> ResolvedMarket:
        normalized_ref = market_ref.strip()
        if not normalized_ref:
            raise DataValidationError("Market reference is required.")

        try:
            with GammaClient() as gamma_client:
                if CONDITION_ID_RE.match(normalized_ref):
                    market = gamma_client.get_market_by_condition_id(normalized_ref)
                    return ResolvedMarket(
                        market_slug=market.market_slug,
                        condition_id=normalized_ref,
                    )

                if normalized_ref.startswith("0x"):
                    validate_condition_id(normalized_ref)

                market = gamma_client.get_market_by_slug(normalized_ref)
                if market.condition_id is None:
                    raise DataNotFoundError(
                        f"market '{normalized_ref}' could not be resolved to a condition ID."
                    )
                return ResolvedMarket(
                    market_slug=market.market_slug,
                    condition_id=market.condition_id,
                )
        except GammaNotFoundError as exc:
            raise DataNotFoundError(str(exc)) from exc
        except GammaClientError as exc:
            raise DataClientError(f"Market resolution failed: {exc}") from exc

    def _get_json(self, path: str, *, params: QueryMapping | None = None) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise DataClientError("Data API request failed.") from exc

        if response.status_code == 404:
            raise DataNotFoundError(f"Data API resource '{path}' was not found.")

        if response.status_code >= 400:
            raise DataClientError(
                f"Data API request failed with status {response.status_code} for {path}."
            )

        try:
            return response.json()
        except ValueError as exc:
            raise DataClientError("Data API response body was not valid JSON.") from exc


class ResolvedMarket:
    """Resolved condition-id and market-slug pair."""

    def __init__(self, *, market_slug: str | None, condition_id: str) -> None:
        self.market_slug = market_slug
        self.condition_id = condition_id


def validate_user_address(user: str) -> str:
    """Validate and normalize a public EVM wallet address."""
    normalized_user = user.strip()
    if not ADDRESS_RE.match(normalized_user):
        raise DataValidationError("Wallet addresses must use 0x followed by 40 hex characters.")
    return normalized_user


def validate_condition_id(condition_id: str) -> str:
    """Validate and normalize a public condition ID."""
    normalized_condition_id = condition_id.strip()
    if not CONDITION_ID_RE.match(normalized_condition_id):
        raise DataValidationError("Condition IDs must use 0x followed by 64 hex characters.")
    return normalized_condition_id


def _ensure_list(payload: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise DataClientError(f"Data API {label} response was not a list.")
    return [item for item in payload if isinstance(item, dict)]


def _ensure_leaderboard_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("items", "results", "data", "leaderboard", "users"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    raise DataClientError("Data API leaderboard response was not a list.")


def _ensure_mapping(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DataClientError(f"Data API {label} response was not an object.")
    return payload


def _normalize_leaderboard_entry(payload: dict[str, Any]) -> NormalizedLeaderboardEntry | None:
    address = _string_or_none(
        payload.get("proxyWallet")
        if "proxyWallet" in payload
        else payload.get("address")
        if "address" in payload
        else payload.get("user")
        if "user" in payload
        else payload.get("wallet")
    )
    if address is None or not ADDRESS_RE.match(address):
        return None

    return NormalizedLeaderboardEntry(
        address=address.lower(),
        rank=_int_or_none(payload.get("rank"))
        or _int_or_none(payload.get("position"))
        or _int_or_none(payload.get("leaderboardPosition")),
        display_name=_string_or_none(payload.get("displayName"))
        or _string_or_none(payload.get("name")),
        user_name=_string_or_none(payload.get("userName"))
        or _string_or_none(payload.get("username"))
        or _string_or_none(payload.get("pseudonym")),
        pnl=_decimal_or_none(payload.get("pnl"))
        or _decimal_or_none(payload.get("profit"))
        or _decimal_or_none(payload.get("profitAndLoss"))
        or _decimal_or_none(payload.get("totalPnl")),
        volume=_decimal_or_none(payload.get("volume"))
        or _decimal_or_none(payload.get("totalVolume"))
        or _decimal_or_none(payload.get("volumeUsd"))
        or _decimal_or_none(payload.get("amount")),
    )


def _normalize_holders(
    payload: Any,
    *,
    resolved_market: ResolvedMarket,
) -> list[NormalizedHolder]:
    items = _ensure_list(payload, "holders")
    holders: list[NormalizedHolder] = []
    rank = 0
    for token_payload in items:
        nested_holders = token_payload.get("holders")
        if isinstance(nested_holders, list):
            token_id = _string_or_default(
                token_payload.get("token")
                if "token" in token_payload
                else token_payload.get("asset"),
                "",
            )
            for holder_payload in _ensure_list(nested_holders, "holder rows"):
                rank += 1
                holders.append(
                    NormalizedHolder(
                        market_slug=resolved_market.market_slug,
                        condition_id=resolved_market.condition_id,
                        token_id=token_id,
                        holder_address=_string_or_default(holder_payload.get("proxyWallet"), ""),
                        amount=_decimal_or_default(
                            holder_payload.get("amount")
                            if "amount" in holder_payload
                            else holder_payload.get("balance"),
                            "0",
                        ),
                        name=_string_or_none(holder_payload.get("name")),
                        pseudonym=_string_or_none(holder_payload.get("pseudonym")),
                        outcome_index=_int_or_none(holder_payload.get("outcomeIndex")),
                        rank=rank,
                    )
                )
            continue

        rank += 1
        holders.append(
            NormalizedHolder(
                market_slug=resolved_market.market_slug,
                condition_id=resolved_market.condition_id,
                token_id=_string_or_default(
                    token_payload.get("token")
                    if "token" in token_payload
                    else token_payload.get("asset"),
                    "",
                ),
                holder_address=_string_or_default(token_payload.get("proxyWallet"), ""),
                amount=_decimal_or_default(
                    token_payload.get("amount")
                    if "amount" in token_payload
                    else token_payload.get("balance"),
                    "0",
                ),
                name=_string_or_none(token_payload.get("name")),
                pseudonym=_string_or_none(token_payload.get("pseudonym")),
                outcome_index=_int_or_none(token_payload.get("outcomeIndex")),
                rank=rank,
            )
        )
    return holders


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _string_or_default(value: Any, default: str) -> str:
    return _string_or_none(value) or default


def _decimal_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return str(value)
    return None


def _decimal_or_default(value: Any, default: str) -> str:
    return _decimal_or_none(value) or default


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        return int(stripped) if stripped.isdigit() else None
    return None
