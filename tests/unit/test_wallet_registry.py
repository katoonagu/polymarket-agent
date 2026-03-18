"""Unit tests for the local tracked-wallet registry."""

from __future__ import annotations

import json

from pm.data import DataValidationError
from pm.wallet import (
    TrackedWallet,
    WalletAlreadyTrackedError,
    WalletRegistryError,
    WalletRegistryService,
)

USER = "0x1111111111111111111111111111111111111111"
USER_TWO = "0x2222222222222222222222222222222222222222"
USER_THREE = "0x3333333333333333333333333333333333333333"
ADDED_AT = "2026-03-18T00:00:00Z"


def test_add_wallet_creates_registry_file_and_normalizes_fields(tmp_path) -> None:
    registry_path = tmp_path / ".pm" / "state" / "wallets.json"
    registry = WalletRegistryService(path=registry_path)

    wallet = registry.add_wallet(
        USER,
        label=" Alpha ",
        tags=["beta", "alpha", "beta", ""],
        note=" Shadow ",
        added_at=ADDED_AT,
    )

    assert registry_path.exists()
    assert wallet == TrackedWallet(
        address=USER,
        label="Alpha",
        tags=["alpha", "beta"],
        note="Shadow",
        added_at=ADDED_AT,
    )
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["wallets"][0]["address"] == USER


def test_add_wallet_rejects_invalid_address(tmp_path) -> None:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")

    try:
        registry.add_wallet("bad-wallet")
    except DataValidationError as exc:
        assert str(exc) == "Wallet addresses must use 0x followed by 40 hex characters."
    else:
        raise AssertionError("DataValidationError was not raised")


def test_add_wallet_rejects_duplicate_with_different_casing(tmp_path) -> None:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(USER, added_at=ADDED_AT)

    duplicate_address = USER[:2] + USER[2:].upper()

    try:
        registry.add_wallet(duplicate_address, added_at=ADDED_AT)
    except WalletAlreadyTrackedError as exc:
        assert str(exc) == f"wallet '{USER}' is already tracked."
    else:
        raise AssertionError("WalletAlreadyTrackedError was not raised")


def test_list_wallets_preserves_registry_order(tmp_path) -> None:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(USER, added_at="2026-03-18T00:00:00Z")
    registry.add_wallet(USER_TWO, added_at="2026-03-18T00:01:00Z")

    wallets = registry.list_wallets()

    assert [wallet.address for wallet in wallets] == [USER, USER_TWO]


def test_remove_wallet_preserves_remaining_order(tmp_path) -> None:
    registry = WalletRegistryService(path=tmp_path / "wallets.json")
    registry.add_wallet(USER, added_at="2026-03-18T00:00:00Z")
    registry.add_wallet(USER_TWO, added_at="2026-03-18T00:01:00Z")
    registry.add_wallet(USER_THREE, added_at="2026-03-18T00:02:00Z")

    removed = registry.remove_wallet(USER_TWO)
    wallets = registry.list_wallets()

    assert removed.address == USER_TWO
    assert [wallet.address for wallet in wallets] == [USER, USER_THREE]


def test_invalid_registry_schema_raises_registry_error(tmp_path) -> None:
    registry_path = tmp_path / "wallets.json"
    registry_path.write_text(
        json.dumps({"version": 1, "wallets": [{"address": USER}]}),
        encoding="utf-8",
    )

    registry = WalletRegistryService(path=registry_path)

    try:
        registry.list_wallets()
    except WalletRegistryError as exc:
        assert str(exc) == f"Wallet registry at '{registry_path}' is invalid."
    else:
        raise AssertionError("WalletRegistryError was not raised")
