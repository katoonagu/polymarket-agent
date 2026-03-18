"""Exceptions for authenticated dry-run execution planning."""

from __future__ import annotations


class ExecutionError(RuntimeError):
    """Base exception for dry-run execution failures."""


class ExecutionValidationError(ExecutionError):
    """Raised when dry-run CLI arguments are invalid."""
