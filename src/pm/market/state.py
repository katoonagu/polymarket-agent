"""Local gitignored state for watched markets and saved snapshots."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pm.market.models import (
    MarketSnapshotRecord,
    MarketSnapshotsFile,
    MarketWatchlistFile,
    WatchedMarket,
)

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_MARKET_STATE_DIR"
WATCHLIST_FILENAME = "market-watchlist.json"
SNAPSHOTS_FILENAME = "market-snapshots.json"

DocumentT = TypeVar("DocumentT", MarketWatchlistFile, MarketSnapshotsFile)


class MarketStateError(RuntimeError):
    """Raised when local market watchlist state cannot be read or written."""


class MarketAlreadyWatchedError(MarketStateError):
    """Raised when a market slug is already present in the watchlist."""


class MarketNotWatchedError(MarketStateError):
    """Raised when a market slug is not present in the watchlist."""


class MarketStateService:
    """Small file-backed store for watched markets and saved snapshots."""

    def __init__(
        self,
        *,
        watchlist_path: Path | None = None,
        snapshots_path: Path | None = None,
    ) -> None:
        state_dir = get_market_state_dir()
        self._watchlist_path = watchlist_path or (state_dir / WATCHLIST_FILENAME)
        self._snapshots_path = snapshots_path or (state_dir / SNAPSHOTS_FILENAME)

    @property
    def watchlist_path(self) -> Path:
        """Return the resolved watchlist path."""
        return self._watchlist_path

    @property
    def snapshots_path(self) -> Path:
        """Return the resolved snapshot path."""
        return self._snapshots_path

    def list_watchlist(self) -> list[WatchedMarket]:
        """Return watched markets in deterministic append order."""
        return self._load_document(self._watchlist_path, MarketWatchlistFile).markets

    def find_watched_market(self, market_slug: str) -> WatchedMarket | None:
        """Return a watched market when present."""
        normalized_slug = _normalize_market_slug(market_slug)
        for market in self.list_watchlist():
            if market.market_slug == normalized_slug:
                return market
        return None

    def add_watched_market(self, market: WatchedMarket) -> None:
        """Append a watched market to the local watchlist."""
        document = self._load_document(self._watchlist_path, MarketWatchlistFile)
        if any(item.market_slug == market.market_slug for item in document.markets):
            raise MarketAlreadyWatchedError(f"market '{market.market_slug}' is already watched.")
        document.markets.append(market)
        self._write_document(self._watchlist_path, document)

    def remove_watched_market(self, market_slug: str) -> WatchedMarket:
        """Remove a watched market by canonical slug."""
        normalized_slug = _normalize_market_slug(market_slug)
        document = self._load_document(self._watchlist_path, MarketWatchlistFile)

        for index, market in enumerate(document.markets):
            if market.market_slug == normalized_slug:
                removed_market = document.markets.pop(index)
                self._write_document(self._watchlist_path, document)
                return removed_market

        raise MarketNotWatchedError(f"market '{normalized_slug}' is not watched.")

    def list_snapshots(self, market_slug: str | None = None) -> list[MarketSnapshotRecord]:
        """Return saved snapshots in append order."""
        snapshots = self._load_document(self._snapshots_path, MarketSnapshotsFile).snapshots
        if market_slug is None:
            return snapshots

        normalized_slug = _normalize_market_slug(market_slug)
        return [snapshot for snapshot in snapshots if snapshot.market_slug == normalized_slug]

    def append_snapshot(self, snapshot: MarketSnapshotRecord) -> None:
        """Append a saved market snapshot."""
        document = self._load_document(self._snapshots_path, MarketSnapshotsFile)
        document.snapshots.append(snapshot)
        self._write_document(self._snapshots_path, document)

    def _load_document(self, path: Path, model_type: type[DocumentT]) -> DocumentT:
        if not path.exists():
            return model_type()

        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise MarketStateError(f"Market state at '{path}' is invalid.") from exc

    def _write_document(self, path: Path, document: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temp_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
                prefix=f"{path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)

            os.replace(temp_path, path)
        except OSError as exc:
            raise MarketStateError(f"Could not write market state at '{path}'.") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_market_state_dir() -> Path:
    """Resolve the default gitignored market state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH


def _normalize_market_slug(slug: str) -> str:
    return slug.strip().lower()
