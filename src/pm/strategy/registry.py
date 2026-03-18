"""Seeded local registry for read-only strategy definitions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from pm.strategy.models import StrategyDefinition, StrategyRegistryFile

DEFAULT_STATE_DIR_RELATIVE_PATH = Path(".pm") / "state"
STATE_DIR_ENV_VAR = "PM_STRATEGY_STATE_DIR"
REGISTRY_FILENAME = "strategies.json"


class StrategyRegistryError(RuntimeError):
    """Raised when the local strategy registry cannot be read or written."""


class StrategyNotFoundError(StrategyRegistryError):
    """Raised when a seeded strategy name is unknown."""


def seeded_strategy_definitions() -> list[StrategyDefinition]:
    """Return the deterministic built-in strategy catalog."""
    return [
        StrategyDefinition(
            name="wallet_shadow_copy",
            strategy_type="wallet_shadow_copy",
            description=(
                "Promote recent read-only wallet shadow candidates into manual review intents."
            ),
            required_state_files=["wallet-shadow-runs.json"],
            settings={
                "decision_filter": "WOULD_COPY",
                "max_source_age_seconds": 86400,
            },
        ),
        StrategyDefinition(
            name="market_watch_reversion",
            strategy_type="market_watch_reversion",
            description=(
                "Observe watched markets for widened spread plus midpoint drift "
                "versus the last snapshot."
            ),
            required_state_files=["market-watchlist.json", "market-snapshots.json"],
            settings={
                "min_midpoint_drift_pct": "5",
                "min_spread_change": "0.01",
            },
        ),
        StrategyDefinition(
            name="recurring_crypto_interval_observe",
            strategy_type="recurring_crypto_interval_observe",
            description=(
                "Observe recurring crypto markets when recurring Gamma resolution "
                "and local stream context align."
            ),
            required_state_files=["stream-events.jsonl"],
            settings={
                "query": "btc",
                "interval": "15m",
                "symbol": "BTC",
                "min_market_event_count": 1,
                "min_crypto_event_count": 1,
            },
        ),
    ]


class StrategyRegistryService:
    """Small seeded registry mirrored through a local JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_strategy_registry_path()

    @property
    def path(self) -> Path:
        """Return the resolved strategy registry path."""
        return self._path

    def list_strategies(self) -> list[StrategyDefinition]:
        """Return seeded strategies in deterministic order."""
        return self._load_registry().strategies

    def get_strategy(self, name: str) -> StrategyDefinition:
        """Return a seeded strategy by name."""
        normalized_name = normalize_strategy_name(name)
        for strategy in self.list_strategies():
            if strategy.name == normalized_name:
                return strategy
        raise StrategyNotFoundError(f"strategy '{normalized_name}' was not found")

    def _load_registry(self) -> StrategyRegistryFile:
        seeded = StrategyRegistryFile(strategies=seeded_strategy_definitions())
        if not self._path.exists():
            self._write_registry(seeded)
            return seeded

        try:
            loaded = StrategyRegistryFile.model_validate_json(
                self._path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise StrategyRegistryError(
                f"Strategy registry at '{self._path}' is invalid."
            ) from exc

        if loaded.model_dump(mode="json") != seeded.model_dump(mode="json"):
            raise StrategyRegistryError(
                f"Strategy registry at '{self._path}' does not match the seeded strategy catalog."
            )
        return loaded

    def _write_registry(self, registry: StrategyRegistryFile) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(registry.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                delete=False,
                prefix=f"{self._path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)
            os.replace(temp_path, self._path)
        except OSError as exc:
            raise StrategyRegistryError(
                f"Could not write strategy registry at '{self._path}'."
            ) from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_strategy_state_dir() -> Path:
    """Resolve the default gitignored strategy state directory."""
    override = os.getenv(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_STATE_DIR_RELATIVE_PATH


def get_strategy_registry_path() -> Path:
    """Resolve the seeded strategy registry path."""
    return get_strategy_state_dir() / REGISTRY_FILENAME


def normalize_strategy_name(name: str) -> str:
    """Normalize a strategy name for deterministic lookups."""
    return name.strip().lower()
