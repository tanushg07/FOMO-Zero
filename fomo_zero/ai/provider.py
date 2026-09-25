from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    """Base error for provider failures."""


class ProviderTimeout(ProviderError):
    pass


class ProviderRateLimit(ProviderError):
    pass


class InvalidProviderResponse(ProviderError):
    pass


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    provider_name: str = "unknown"
    model_name: str | None = None


class LLMProvider(Protocol):
    provider_name: str
    model_name: str | None

    def complete(self, prompt: str) -> ProviderResponse:
        """Return a JSON extraction response for the supplied prompt."""
