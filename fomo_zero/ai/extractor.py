from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import sleep

from pydantic import ValidationError
from sqlalchemy.orm import Session

from fomo_zero.models import Notice
from fomo_zero.repositories import save_extraction_output, set_notice_processing_status

from .guardian import Guardian, GuardianReport
from .normalizer import normalize_extraction
from .prompts import build_extraction_prompt
from .provider import InvalidProviderResponse, LLMProvider, ProviderError, ProviderRateLimit, ProviderResponse, ProviderTimeout
from .schemas import ExtractionMetadata, ExtractionOutput


class ExtractionError(Exception):
    pass


class NoticeExtractor:
    def __init__(self, provider: LLMProvider, *, max_retries: int = 2, retry_delay_seconds: float = 0.0, guardian: Guardian | None = None):
        self.provider = provider
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.guardian = guardian or Guardian()
        self.last_report: GuardianReport | None = None

    def extract(self, session: Session, notice_id: str, *, previous_text: str | None = None) -> ExtractionOutput:
        notice = session.get(Notice, notice_id)
        if notice is None:
            raise LookupError(f"Notice not found: {notice_id}")
        set_notice_processing_status(session, notice_id, "processing")
        prompt = build_extraction_prompt(notice, previous_text)
        try:
            response, output, attempt_count = self._request(prompt)
        except ExtractionError as exc:
            set_notice_processing_status(
                session, notice_id, "failed", validation_status="blocked",
                validation_reason="Provider extraction failed: invalid or unavailable model output.",
            )
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

        # Guardian is the authoritative gate before publication. It never
        # trusts the model: it re-checks every claim against the source and the
        # previous notice, records all findings, and decides the verdict.
        report = self.guardian.review(output, source_text=notice.original_text, previous_text=previous_text)
        self.last_report = report

        # Repairs only remove unsupported derived values (invented dates/times);
        # they never rewrite the quoted evidence.
        Guardian.apply_repairs(output, report)

        if report.blocked_claim_ids:
            # Blocked claims must never reach students as verified information.
            # Drop them so they cannot be published, but keep the valid claims.
            _drop_blocked_claims(output, report)

        pipeline_status = report.pipeline_status
        output.validation_status = pipeline_status  # type: ignore[assignment]

        if pipeline_status != "validated":
            # Anything not fully verified is held for review; nothing ambiguous,
            # incomplete, or blocked is published as a verified action.
            set_notice_processing_status(
                session, notice_id, "needs_review", validation_status=pipeline_status,
                validation_reason="; ".join(report.problems()) or "Guardian requires manual review.",
            )
            return output
        save_extraction_output(session, notice_id, output)
        set_notice_processing_status(session, notice_id, "complete", validation_status="validated", validation_reason=None)
        return output

    def _request(self, prompt: str) -> tuple[ProviderResponse, ExtractionOutput, int]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.provider.complete(prompt)
                if not response.content.strip():
                    raise InvalidProviderResponse("Provider returned an empty response")
                payload = json.loads(response.content)
                payload.setdefault("metadata", {
                    "provider_name": response.provider_name,
                    "model_name": response.model_name,
                    "extracted_at": datetime.now(UTC).isoformat(),
                    "source_text_sha256": "pending",
                    "attempt_count": attempt + 1,
                })
                _canonicalize_provider_payload(payload)
                _normalize_provider_evidence_statuses(payload)
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


def _drop_blocked_claims(output: ExtractionOutput, report: GuardianReport) -> None:
    """Remove claims the Guardian blocked so they cannot be published.

    Valid claims are preserved: only the claims whose ids appear in
    ``report.blocked_claim_ids`` are removed from their lists. The summary is a
    required field and is never removed here; if the summary itself is blocked
    the overall status is already non-validated, so it will not be persisted.
    """
    blocked = report.blocked_claim_ids
    output.changes = [c for c in output.changes if c.claim_id not in blocked]
    output.affected_groups = [g for g in output.affected_groups if g.claim_id not in blocked]
    output.deadlines = [d for d in output.deadlines if d.claim_id not in blocked]
    output.actions = [a for a in output.actions if a.claim_id not in blocked]
    output.conditions = [c for c in output.conditions if c.claim_id not in blocked]
    output.uncertainties = [u for u in output.uncertainties if u.claim_id not in blocked]


def _normalize_provider_evidence_statuses(payload: dict) -> None:
    """Remove provider vocabulary differences before source alignment.

    Evidence status is recalculated by ``normalize_extraction`` from the real
    notice text, so provider-reported values are never trusted as validation.
    """
    collections = ["summary", "changes", "affected_groups", "deadlines", "actions", "conditions", "uncertainties"]
    for collection in collections:
        values = payload.get(collection, [])
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            continue
        for claim in values:
            if isinstance(claim, dict) and claim.get("evidence_status") not in {"aligned", "review_required", "blocked"}:
                claim["evidence_status"] = "review_required"


def _canonicalize_provider_payload(payload: dict) -> None:
    """Map harmless provider aliases to the application's canonical fields."""
    for group in payload.get("affected_groups", []) or []:
        if isinstance(group, dict):
            if "value" not in group and isinstance(group.get("group"), str):
                group["value"] = group["group"]
            if "value" not in group and isinstance(group.get("group_name"), str):
                group["value"] = group["group_name"]
            if "value" not in group and isinstance(group.get("description"), str):
                group["value"] = group["description"]
            if "group_type" not in group:
                group["group_type"] = group.get("type") or "unspecified"
    for deadline in payload.get("deadlines", []) or []:
        if isinstance(deadline, dict):
            if "normalized_date" not in deadline and "date" in deadline:
                deadline["normalized_date"] = deadline["date"]
            if "description" not in deadline:
                deadline["description"] = deadline.get("event") or "Deadline"
            if "original_text" not in deadline:
                deadline["original_text"] = deadline.get("evidence_text") or ""
            deadline.setdefault("date_precision", "unknown")
            deadline.setdefault("is_explicit", deadline.get("normalized_date") is not None)
    for action in payload.get("actions", []) or []:
        if isinstance(action, dict):
            if "action_text" not in action and "description" in action:
                action["action_text"] = action["description"]
            action.setdefault("action_type", "unclear")
            action.setdefault("mandatory_status", "unclear")
