from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import sleep

from pydantic import ValidationError
from sqlalchemy.orm import Session

from fomo_zero.models import Notice
from fomo_zero.repositories import save_extraction_output, set_notice_processing_status

from .normalizer import normalize_extraction
from .prompts import build_extraction_prompt
from .provider import InvalidProviderResponse, LLMProvider, ProviderError, ProviderRateLimit, ProviderResponse, ProviderTimeout
from .schemas import ExtractionMetadata, ExtractionOutput
from .validator import validate_extraction


class ExtractionError(Exception):
    pass


class NoticeExtractor:
    def __init__(self, provider: LLMProvider, *, max_retries: int = 2, retry_delay_seconds: float = 0.0):
        self.provider = provider
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)

    def extract(self, session: Session, notice_id: str, *, previous_text: str | None = None) -> ExtractionOutput:
        notice = session.get(Notice, notice_id)
        if notice is None:
            raise LookupError(f"Notice not found: {notice_id}")
        set_notice_processing_status(session, notice_id, "processing")
        prompt = build_extraction_prompt(notice, previous_text)
        try:
            response, output, attempt_count = self._request(prompt)
        except ExtractionError as exc:
            set_notice_processing_status(session, notice_id, "failed", validation_status="blocked")
            raise exc

        output.metadata = ExtractionMetadata(
            provider_name=response.provider_name,
            model_name=response.model_name,
            extracted_at=datetime.now(UTC),
            source_text_sha256=hashlib.sha256(notice.original_text.encode("utf-8")).hexdigest(),
            attempt_count=attempt_count,
            reference_date=output.metadata.reference_date,
        )
        normalize_extraction(output, notice.original_text)
        validation = validate_extraction(output, previous_text=previous_text)
        output.validation_status = validation.status  # type: ignore[assignment]
        if validation.status != "validated":
            set_notice_processing_status(session, notice_id, "needs_review", validation_status=validation.status)
            return output
        save_extraction_output(session, notice_id, output)
        set_notice_processing_status(session, notice_id, "complete", validation_status="validated")
        return output

    def _request(self, prompt: str) -> tuple[ProviderResponse, ExtractionOutput, int]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.provider.complete(prompt)
                if not response.content.strip():
                    raise InvalidProviderResponse("Provider returned an empty response")
                payload = json.loads(response.content)
                return response, ExtractionOutput.model_validate(payload), attempt + 1
            except (ProviderTimeout, ProviderRateLimit, InvalidProviderResponse) as exc:
                last_error = exc
                if attempt < self.max_retries and self.retry_delay_seconds:
                    sleep(self.retry_delay_seconds)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if attempt < self.max_retries and self.retry_delay_seconds:
                    sleep(self.retry_delay_seconds)
            except ProviderError as exc:
                raise ExtractionError("Provider request failed") from exc
        raise ExtractionError("Provider returned invalid output after bounded retries") from last_error
