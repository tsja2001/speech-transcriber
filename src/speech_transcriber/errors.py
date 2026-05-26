"""Typed service errors."""

from __future__ import annotations


class SpeechTranscriberError(Exception):
    """Base error for the service."""


class ProviderError(SpeechTranscriberError):
    """Provider call failed."""

    def __init__(self, provider: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ConfigError(SpeechTranscriberError):
    """Configuration is invalid."""
