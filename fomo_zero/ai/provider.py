from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol

from dotenv import load_dotenv


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


class GroqProvider:
    """Groq adapter; the rest of the engine only depends on LLMProvider."""

    provider_name = "groq"

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        load_dotenv()
        self.model_name = model_name or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key or key == "PASTE_YOUR_GROQ_API_KEY_HERE":
            raise ValueError("GROQ_API_KEY is not configured")
        from groq import Groq

        self._client = Groq(api_key=key)

    def complete(self, prompt: str) -> ProviderResponse:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return ProviderResponse(content, self.provider_name, self.model_name)
