from datetime import UTC, date, datetime
import json

import pytest
from sqlalchemy import select

from fomo_zero.ai.extractor import ExtractionError, NoticeExtractor
from fomo_zero.ai.normalizer import align_evidence, normalize_extraction
from fomo_zero.ai.provider import ProviderResponse, ProviderTimeout
from fomo_zero.ai.schemas import ExtractionOutput
from fomo_zero.ai.validator import validate_extraction
from fomo_zero.models import ActionItem, Deadline, ExtractionRecord, Notice
from fomo_zero.repositories import create_notice
from fomo_zero.schemas import NoticeCreate

SOURCE = "The deadline is 2026-10-01. Students must submit the form. Staff may attend. If approved, contact the office."


def metadata():
    return {
        "provider_name": "test-provider",
        "model_name": "test-model",
        "extracted_at": datetime.now(UTC).isoformat(),
        "source_text_sha256": "provider-value-replaced-by-engine",
        "attempt_count": 1,
    }


def payload(*, deadlines=None, actions=None, evidence=SOURCE[:32], conditions=None, changes=None):
    return {
        "summary": {"claim_id": "summary-1", "text": "A form is due on 2026-10-01.", "evidence_text": evidence},
        "changes": changes or [],
        "affected_groups": [],
        "deadlines": deadlines or [],
        "actions": actions or [],
        "conditions": conditions or [],
        "uncertainties": [],
        "metadata": metadata(),
        "validation_status": "review_required",
    }


def deadline(text="The deadline is 2026-10-01.", normalized="2026-10-01", explicit=True):
    return {
        "claim_id": "deadline-1",
        "description": "Submission deadline",
        "original_text": text,
        "normalized_date": normalized,
        "date_precision": "day",
        "is_explicit": explicit,
        "evidence_text": text,
    }


def action(action_type, text, mandatory_status):
    return {
        "claim_id": f"action-{action_type}",
        "action_text": text,
        "action_type": action_type,
        "mandatory_status": mandatory_status,
        "evidence_text": text,
    }


class StaticProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return ProviderResponse(response, self.provider_name, self.model_name)


def create_test_notice(session):
    return create_notice(session, NoticeCreate(title="Test notice", original_text=SOURCE))


def test_simple_deadline_is_aligned_and_saved(session):
    notice = create_test_notice(session)
    provider = StaticProvider([json.dumps(payload(deadlines=[deadline()]))])
    result = NoticeExtractor(provider).extract(session, notice.id)
    assert result.validation_status == "validated"
    assert result.deadlines[0].evidence_status == "aligned"
    assert session.scalar(select(Deadline).where(Deadline.notice_id == notice.id)).normalized_date == date(2026, 10, 1)
    assert session.scalar(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice.id)).summary_text


def test_multiple_deadlines_are_preserved(session):
    notice = create_test_notice(session)
    second = deadline("Students must submit the form.", None, False)
    second["claim_id"] = "deadline-2"
    second["description"] = "Form submission"
    result = NoticeExtractor(StaticProvider([json.dumps(payload(deadlines=[deadline(), second]))])).extract(session, notice.id)
    assert len(result.deadlines) == 2


def test_action_types_are_preserved(session):
    notice = create_test_notice(session)
    actions = [
        action("mandatory", "Students must submit the form.", "required"),
        action("advisory", "Staff may attend.", "not_required"),
        action("conditional", "If approved, contact the office.", "unclear"),
    ]
    result = NoticeExtractor(StaticProvider([json.dumps(payload(actions=actions))])).extract(session, notice.id)
    assert [item.action_type for item in result.actions] == ["mandatory", "advisory", "conditional"]


def test_missing_deadline_remains_empty(session):
    notice = create_test_notice(session)
    result = NoticeExtractor(StaticProvider([json.dumps(payload())])).extract(session, notice.id)
    assert result.deadlines == []


def test_ambiguous_date_is_not_normalized():
    output = ExtractionOutput.model_validate(payload(deadlines=[deadline("The deadline is next Friday.", None, False)]))
    normalize_extraction(output, SOURCE + " The deadline is next Friday.")
    assert validate_extraction(output).status == "validated"
    assert output.deadlines[0].normalized_date is None


def test_unsupported_inference_requires_review():
    output = ExtractionOutput.model_validate(payload(deadlines=[deadline("The deadline is next Friday.", "2026-10-02", False)]))
    assert validate_extraction(output).status == "review_required"


def test_invalid_json_retries_once_and_saves(session):
    notice = create_test_notice(session)
    provider = StaticProvider(["{bad json", json.dumps(payload())])
    result = NoticeExtractor(provider, max_retries=1).extract(session, notice.id)
    assert result.validation_status == "validated"
    assert provider.calls == 2


def test_invalid_model_output_is_blocked(session):
    notice = create_test_notice(session)
    provider = StaticProvider([json.dumps({"summary": {}})])
    with pytest.raises(ExtractionError):
        NoticeExtractor(provider, max_retries=0).extract(session, notice.id)
    refreshed = session.get(Notice, notice.id)
    assert refreshed.processing_status == "failed"
    assert refreshed.validation_status == "blocked"


def test_evidence_mismatch_requires_review_and_is_not_saved(session):
    notice = create_test_notice(session)
    result = NoticeExtractor(StaticProvider([json.dumps(payload(evidence="This sentence is not in the notice."))])).extract(session, notice.id)
    assert result.validation_status == "review_required"
    assert result.summary.evidence_status == "review_required"
    assert session.scalar(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice.id)) is None


def test_whitespace_alignment_preserves_original_evidence():
    aligned = align_evidence("A deadline\n is listed.", "A deadline is listed.")
    assert aligned.status == "aligned"
    assert aligned.text == "A deadline is listed."


def test_repeated_processing_replaces_records(session):
    notice = create_test_notice(session)
    provider = StaticProvider([json.dumps(payload(actions=[action("mandatory", "Students must submit the form.", "required")])), json.dumps(payload(actions=[action("mandatory", "Students must submit the form.", "required")])),])
    extractor = NoticeExtractor(provider)
    extractor.extract(session, notice.id)
    extractor.extract(session, notice.id)
    assert len(session.scalars(select(ActionItem).where(ActionItem.notice_id == notice.id)).all()) == 1
    assert len(session.scalars(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice.id)).all()) == 1


def test_provider_timeout_is_bounded_and_marks_failure(session):
    notice = create_test_notice(session)
    provider = StaticProvider([ProviderTimeout("slow"), ProviderTimeout("slow"), ProviderTimeout("slow")])
    with pytest.raises(ExtractionError):
        NoticeExtractor(provider, max_retries=2).extract(session, notice.id)
    assert provider.calls == 3
    assert session.get(Notice, notice.id).processing_status == "failed"
