"""Exceptions for the read-only market discovery adapters."""

from __future__ import annotations


class GammaClientError(RuntimeError):
    """Base exception for Gamma adapter failures."""


class GammaNotFoundError(GammaClientError):
    """Raised when a market or event slug cannot be found."""

    def __init__(self, *, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} '{identifier}' was not found")


class ClobClientError(RuntimeError):
    """Base exception for public CLOB adapter failures."""


class ClobNotFoundError(ClobClientError):
    """Raised when public CLOB data cannot be found for a token."""

    def __init__(self, *, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} for token_id '{identifier}' was not found")
