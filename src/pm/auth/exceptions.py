"""Exceptions for authenticated setup and dry-run auth flows."""

from __future__ import annotations


class AuthError(RuntimeError):
    """Base exception for authenticated setup and auth flows."""


class AuthValidationError(AuthError):
    """Raised when required auth configuration is missing or invalid."""


class AuthClientError(AuthError):
    """Raised when an authenticated Polymarket SDK call fails."""


class AuthGeoblockedError(AuthError):
    """Raised when the official geoblock endpoint reports blocked access."""


class AuthProfileStateError(AuthError):
    """Raised when local non-secret operator profile state is invalid."""
