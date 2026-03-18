"""Unit tests for local market watchlist and snapshot state."""

from __future__ import annotations

from pathlib import Path

import pytest

from pm.market.models import MarketSnapshotRecord, WatchedMarket
from pm.market.state import (
    MarketAlreadyWatchedError,
    MarketNotWatchedError,
    MarketStateError,
    MarketStateService,
)


def _build_state(tmp_path: Path) -> MarketStateService:
    return MarketStateService(
        watchlist_path=tmp_path / "market-watchlist.json",
        snapshots_path=tmp_path / "market-snapshots.json",
    )


def test_market_state_add_remove_and_snapshot_append_order(tmp_path: Path) -> None:
    state = _build_state(tmp_path)
    first = _watched_market("btc-above-100k", "First")
    second = _watched_market("btc-above-110k", "Second")

    state.add_watched_market(first)
    state.add_watched_market(second)

    assert [item.market_slug for item in state.list_watchlist()] == [
        "btc-above-100k",
        "btc-above-110k",
    ]

    removed = state.remove_watched_market("btc-above-100k")
    assert removed.market_slug == "btc-above-100k"
    assert [item.market_slug for item in state.list_watchlist()] == ["btc-above-110k"]

    state.append_snapshot(_snapshot_record("btc-above-110k", "2026-03-18T00:00:00Z"))
    state.append_snapshot(_snapshot_record("btc-above-120k", "2026-03-18T00:01:00Z"))

    assert [item.market_slug for item in state.list_snapshots()] == [
        "btc-above-110k",
        "btc-above-120k",
    ]


def test_market_state_duplicate_and_missing_watch_errors(tmp_path: Path) -> None:
    state = _build_state(tmp_path)
    state.add_watched_market(_watched_market("btc-above-100k", "First"))

    with pytest.raises(MarketAlreadyWatchedError, match="already watched"):
        state.add_watched_market(_watched_market("btc-above-100k", "Duplicate"))

    with pytest.raises(MarketNotWatchedError, match="is not watched"):
        state.remove_watched_market("btc-above-110k")


def test_market_state_invalid_watchlist_and_snapshot_documents_raise_state_error(
    tmp_path: Path,
) -> None:
    state = _build_state(tmp_path)
    state.watchlist_path.parent.mkdir(parents=True, exist_ok=True)
    state.watchlist_path.write_text("{bad json", encoding="utf-8")
    state.snapshots_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(MarketStateError, match="Market state"):
        state.list_watchlist()

    with pytest.raises(MarketStateError, match="Market state"):
        state.list_snapshots()


def _watched_market(slug: str, label: str) -> WatchedMarket:
    return WatchedMarket(
        market_slug=slug,
        event_slug="bitcoin-event",
        question=f"Question for {slug}",
        label=label,
        tags=["btc"],
        added_at="2026-03-18T00:00:00Z",
    )


def _snapshot_record(slug: str, snapshot_at: str) -> MarketSnapshotRecord:
    return MarketSnapshotRecord(
        snapshot_at=snapshot_at,
        market_slug=slug,
        event_slug="bitcoin-event",
        question=f"Question for {slug}",
    )
