"""Local tracked-wallet registry backed by a gitignored JSON file."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from pm.data.client import validate_user_address
from pm.wallet.models import TrackedWallet, WalletRegistryFile

DEFAULT_REGISTRY_RELATIVE_PATH = Path(".pm") / "state" / "wallets.json"
REGISTRY_ENV_VAR = "PM_WALLET_REGISTRY_PATH"


class WalletRegistryError(RuntimeError):
    """Raised when the local wallet registry cannot be read or written."""


class WalletAlreadyTrackedError(WalletRegistryError):
    """Raised when an address is already present in the local registry."""


class WalletNotTrackedError(WalletRegistryError):
    """Raised when an address is not present in the local registry."""


class WalletRegistryService:
    """Small file-backed registry for tracked wallets."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_wallet_registry_path()

    @property
    def path(self) -> Path:
        """Return the resolved on-disk registry path."""
        return self._path

    def list_wallets(self) -> list[TrackedWallet]:
        """Load all tracked wallets in deterministic registry order."""
        return self._load_registry().wallets

    def get_wallet(self, address: str) -> TrackedWallet:
        """Return a tracked wallet by normalized address."""
        normalized_address = normalize_wallet_address(address)
        for wallet in self.list_wallets():
            if wallet.address == normalized_address:
                return wallet
        raise WalletNotTrackedError(
            f"wallet '{normalized_address}' is not tracked. "
            f"Use `pm wallet add --address {normalized_address}` first."
        )

    def add_wallet(
        self,
        address: str,
        *,
        label: str | None = None,
        tags: list[str] | None = None,
        note: str | None = None,
        added_at: str | None = None,
    ) -> TrackedWallet:
        """Add a new tracked wallet to the local registry."""
        normalized_address = normalize_wallet_address(address)
        registry = self._load_registry()

        if any(wallet.address == normalized_address for wallet in registry.wallets):
            raise WalletAlreadyTrackedError(f"wallet '{normalized_address}' is already tracked.")

        wallet = TrackedWallet(
            address=normalized_address,
            label=_normalize_text(label),
            tags=_normalize_tags(tags),
            note=_normalize_text(note),
            added_at=added_at or _utc_now_iso(),
        )
        registry.wallets.append(wallet)
        self._write_registry(registry)
        return wallet

    def remove_wallet(self, address: str) -> TrackedWallet:
        """Remove a tracked wallet from the local registry."""
        normalized_address = normalize_wallet_address(address)
        registry = self._load_registry()

        for index, wallet in enumerate(registry.wallets):
            if wallet.address == normalized_address:
                removed_wallet = registry.wallets.pop(index)
                self._write_registry(registry)
                return removed_wallet

        raise WalletNotTrackedError(
            f"wallet '{normalized_address}' is not tracked. "
            f"Use `pm wallet add --address {normalized_address}` first."
        )

    def _load_registry(self) -> WalletRegistryFile:
        if not self._path.exists():
            return WalletRegistryFile()

        try:
            return WalletRegistryFile.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise WalletRegistryError(f"Wallet registry at '{self._path}' is invalid.") from exc

    def _write_registry(self, registry: WalletRegistryFile) -> None:
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
            raise WalletRegistryError(
                f"Could not write wallet registry at '{self._path}'."
            ) from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def get_wallet_registry_path() -> Path:
    """Resolve the default gitignored wallet registry path."""
    override = os.getenv(REGISTRY_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / DEFAULT_REGISTRY_RELATIVE_PATH


def normalize_wallet_address(address: str) -> str:
    """Validate and lowercase a tracked wallet address."""
    return validate_user_address(address).lower()


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return sorted({tag.strip() for tag in tags if tag.strip()})


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
