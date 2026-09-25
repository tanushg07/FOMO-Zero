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
        self.model_name = model_name or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key or key == "PASTE_YOUR_GROQ_API_KEY_HERE":
            raise ValueError("GROQ_API_KEY is not configured")
        from groq import Groq

        self._client = Groq(api_key=key)

    def complete(self, prompt: str) -> ProviderResponse:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_completion_tokens=8192,
                reasoning_effort="low",
                temperature=0,
            )
        except Exception as exc:
            error_name = type(exc).__name__.lower()
            if "timeout" in error_name:
                raise ProviderTimeout("Groq request timed out") from exc
            if "ratelimit" in error_name or "rate_limit" in error_name:
                raise ProviderRateLimit("Groq rate limit reached") from exc
            raise ProviderError("Groq request failed") from exc
        content = response.choices[0].message.content or ""
        return ProviderResponse(content, self.provider_name, self.model_name)


class NullProvider:
    """Safe fallback provider used when no API key is configured.

    It never contacts a network service and never has access to a secret. It
    returns a minimal, deliberately unaligned extraction so the Guardian routes
    the notice to review_required instead of publishing anything as verified.
    This keeps automation running (and manual review available) even without a
    configured model, and guarantees no unsupported claim is auto-published.
    """

    provider_name = "null"
    model_name = None

    def complete(self, prompt: str) -> ProviderResponse:
        import json

        payload = {
            "summary": {
                "claim_id": "summary-null",
                "text": "Automated extraction is unavailable; manual review is required.",
                # Intentionally no evidence_text -> Guardian will require review.
                "evidence_text": None,
            },
            "changes": [],
            "affected_groups": [],
            "deadlines": [],
            "actions": [],
            "conditions": [],
            "uncertainties": [
                {
                    "claim_id": "uncertainty-null",
                    "category": "provider_unavailable",
                    "description": "No language model was configured, so no facts were extracted.",
                    "severity": "high",
                }
            ],
            "metadata": {
                "provider_name": self.provider_name,
                "model_name": None,
                # The engine overwrites metadata with authoritative values.
                "extracted_at": "1970-01-01T00:00:00+00:00",
                "source_text_sha256": "pending",
                "attempt_count": 1,
            },
            "validation_status": "review_required",
        }
        return ProviderResponse(json.dumps(payload), self.provider_name, self.model_name)


def build_provider(*, use_dotenv: bool = True) -> LLMProvider:
    """Return a configured provider, or a safe fallback.

    Never raises on a missing key and never logs the key. If ``GROQ_API_KEY`` is
    absent or a placeholder, returns :class:`NullProvider` so processing degrades
    gracefully to review_required rather than failing or leaking configuration.

    ``use_dotenv`` loads a project ``.env`` when true (production default). Set it
    to ``False`` to rely solely on the current process environment (useful for
    tests that intentionally clear ``GROQ_API_KEY``). ``load_dotenv`` never
    overrides an already-set variable, but it can repopulate a deleted one.
    """
    if use_dotenv:
        load_dotenv()
    key = os.getenv("GROQ_API_KEY")
    if not key or key == "PASTE_YOUR_GROQ_API_KEY_HERE":
        return NullProvider()
    try:
        return GroqProvider()
    except (ValueError, ImportError):
        return NullProvider()
