"""Arkham intelligence client and service exceptions."""

from __future__ import annotations


class ArkhamError(RuntimeError):
    """Base Arkham intelligence error."""


class ArkhamValidationError(ArkhamError):
    """Raised when Arkham command inputs are invalid."""


class ArkhamClientError(ArkhamError):
    """Raised when Arkham upstream requests fail."""


class ArkhamNotFoundError(ArkhamClientError):
    """Raised when Arkham cannot resolve a requested resource."""
