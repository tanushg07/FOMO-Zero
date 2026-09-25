"""Tests for the Guardian validation layer.

Every validation check has positive and negative coverage. Negative tests
simulate a model that fabricates information (invented dates/times, unsupported
mandatory actions, broadened scope, changes without a previous notice, and
missing references) and assert the Guardian refuses to publish it as verified.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
import json

import pytest
from sqlalchemy import select

from fomo_zero.ai.extractor import NoticeExtractor
from fomo_zero.ai.guardian import Guardian, GuardianState
from fomo_zero.ai.normalizer import normalize_extraction
from fomo_zero.ai.provider import ProviderResponse
from fomo_zero.ai.schemas import ExtractionOutput
from fomo_zero.models import ActionItem, ChangeRecord, Deadline, ExtractionRecord, Notice
from fomo_zero.repositories import create_notice
from fomo_zero.schemas import NoticeCreate

SOURCE = (
    "The submission deadline is 2026-10-01. "
    "Students must submit the completed form. "
    "Staff may attend the briefing. "
    "If approved, contact the office. "
    "Eligible final year students should register. "
    "Refer to the attached document for details."
)


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def metadata():
    return {
        "provider_name": "test-provider",
        "model_name": "test-model",
        "extracted_at": datetime.now(UTC).isoformat(),
        "source_text_sha256": "replaced-by-engine",
        "attempt_count": 1,
    }


def build_payload(**overrides):
    payload = {
        "summary": {"claim_id": "summary-1", "text": "A form is due on 2026-10-01.", "evidence_text": "The submission deadline is 2026-10-01."},
        "changes": [],
        "affected_groups": [],
        "deadlines": [],
        "actions": [],
        "conditions": [],
        "uncertainties": [],
        "metadata": metadata(),
        "validation_status": "review_required",
    }
    payload.update(overrides)
    return payload


def make_output(source=SOURCE, *, previous_text=None, **overrides) -> tuple[ExtractionOutput, str, str | None]:
    output = ExtractionOutput.model_validate(build_payload(**overrides))
    normalize_extraction(output, source)
    return output, source, previous_text


def review(source=SOURCE, *, previous_text=None, **overrides):
    output, src, prev = make_output(source, previous_text=previous_text, **overrides)
    report = Guardian().review(output, source_text=src, previous_text=prev)
    return output, report


def deadline(claim_id="deadline-1", *, text="The submission deadline is 2026-10-01.", normalized_date="2026-10-01", normalized_time=None, timezone=None, is_explicit=True, evidence=None):
    return {
        "claim_id": claim_id,
        "description": "Submission deadline",
        "original_text": text,
        "normalized_date": normalized_date,
        "normalized_time": normalized_time,
        "timezone": timezone,
        "date_precision": "day",
        "is_explicit": is_explicit,
        "evidence_text": evidence if evidence is not None else text,
    }


def action(claim_id, *, text, action_type, mandatory_status, evidence=None, due_time=None, timezone=None):
    return {
        "claim_id": claim_id,
        "action_text": text,
        "action_type": action_type,
        "mandatory_status": mandatory_status,
        "due_time": due_time,
        "timezone": timezone,
        "evidence_text": evidence if evidence is not None else text,
    }


def group(claim_id, *, group_type, value, evidence):
    return {"claim_id": claim_id, "group_type": group_type, "value": value, "evidence_text": evidence}


def change(claim_id, *, field_name="deadline", old_value=None, new_value=None, change_type="modified", evidence):
    return {
        "claim_id": claim_id,
        "field_name": field_name,
        "old_value": old_value,
        "new_value": new_value,
        "change_type": change_type,
        "evidence_text": evidence,
    }


# ---------------------------------------------------------------------------
# State / report semantics
# ---------------------------------------------------------------------------


CLEAN_SOURCE = "The submission deadline is 2026-10-01. Students must submit the completed form."


def test_clean_output_passes():
    _, report = review(
        source=CLEAN_SOURCE,
        deadlines=[deadline()],
        actions=[action("a1", text="Students must submit the completed form.", action_type="mandatory", mandatory_status="required")],
    )
    assert report.state is GuardianState.PASS
    assert report.pipeline_status == "validated"
    assert report.problems() == ()


def test_state_ordering_takes_most_severe():
    assert max([GuardianState.PASS, GuardianState.WARN, GuardianState.BLOCK]) is GuardianState.BLOCK
    assert GuardianState.BLOCK > GuardianState.REPAIR > GuardianState.WARN > GuardianState.PASS


def test_pipeline_status_mapping():
    assert review(changes=[change("c1", evidence="not present anywhere")])[1].pipeline_status == "blocked"
    warn_report = review(deadlines=[deadline(normalized_date=None, text="The deadline is next Friday.", is_explicit=False)])[1]
    assert warn_report.pipeline_status == "review_required"


# ---------------------------------------------------------------------------
# 1. Evidence check
# ---------------------------------------------------------------------------


def test_evidence_present_passes():
    _, report = review(source=CLEAN_SOURCE, deadlines=[deadline()])
    assert report.state is GuardianState.PASS


def test_missing_evidence_on_critical_claim_blocks():
    # Fabrication: an action with no evidence text at all.
    _, report = review(actions=[action("a1", text="Students must submit the completed form.", action_type="mandatory", mandatory_status="required", evidence="")])
    assert report.pipeline_status == "blocked"
    assert any(f.check == "evidence" and f.state is GuardianState.BLOCK for f in report.findings)


def test_unaligned_evidence_warns():
    # Fabrication: evidence text that does not appear in the source.
    _, report = review(deadlines=[deadline(evidence="This exact sentence is not in the notice at all.")])
    assert any(f.check == "evidence" and f.state is GuardianState.WARN for f in report.findings)
    assert report.pipeline_status == "review_required"


# ---------------------------------------------------------------------------
# 2. Date check
# ---------------------------------------------------------------------------


def test_explicit_date_passes():
    _, report = review(deadlines=[deadline()])
    assert not any(f.check == "date" for f in report.findings)


def test_invented_date_is_repaired_and_dropped():
    # Fabrication: a concrete date derived from ambiguous wording.
    output, report = review(deadlines=[deadline(text="The deadline is next Friday.", normalized_date="2026-10-02", is_explicit=False)])
    assert report.state is GuardianState.REPAIR
    assert "deadline-1" in report.repairs
    Guardian.apply_repairs(output, report)
    assert output.deadlines[0].normalized_date is None
    # Ambiguous wording itself is preserved, never rewritten.
    assert output.deadlines[0].original_text == "The deadline is next Friday."


def test_non_explicit_date_is_repaired():
    output, report = review(deadlines=[deadline(text="The submission deadline is 2026-10-01.", normalized_date="2026-10-01", is_explicit=False)])
    assert any(f.check == "date" and f.state is GuardianState.REPAIR for f in report.findings)


def test_invented_time_is_repaired_and_dropped():
    # Fabrication: a time that does not appear in the notice.
    output, report = review(deadlines=[deadline(normalized_time="09:00:00", timezone="IST")])
    assert any(f.check == "date" and f.repair_field == "normalized_time" for f in report.findings)
    Guardian.apply_repairs(output, report)
    assert output.deadlines[0].normalized_time is None


def test_missing_timezone_when_time_present_warns():
    _, report = review(deadlines=[deadline(text="Submit by 09:00 on 2026-10-01.", normalized_time="09:00:00", timezone=None, evidence="Submit by 09:00 on 2026-10-01.")], source="Submit by 09:00 on 2026-10-01.")
    assert any(f.check == "date" and "timezone" in f.message for f in report.findings)


def test_ambiguous_wording_preserved_and_warned():
    _, report = review(deadlines=[deadline(text="The deadline is next Friday.", normalized_date=None, is_explicit=False)])
    assert any(f.check == "date" and f.state is GuardianState.WARN for f in report.findings)
    assert report.pipeline_status == "review_required"


# ---------------------------------------------------------------------------
# 3. Action check
# ---------------------------------------------------------------------------


def test_supported_mandatory_action_passes():
    _, report = review(actions=[action("a1", text="Students must submit the completed form.", action_type="mandatory", mandatory_status="required")])
    assert not any(f.check == "action" for f in report.findings)


def test_unsupported_mandatory_status_blocks():
    # Fabrication: mandatory action whose status does not support "required".
    _, report = review(actions=[action("a1", text="Students must submit the completed form.", action_type="mandatory", mandatory_status="optional")])
    assert report.pipeline_status == "blocked"
    assert any(f.check == "action" and f.state is GuardianState.BLOCK for f in report.findings)


def test_mandatory_action_with_advisory_evidence_blocks():
    # Fabrication: labelled mandatory but the evidence only says "may".
    _, report = review(actions=[action("a1", text="attend the briefing", action_type="mandatory", mandatory_status="required", evidence="Staff may attend the briefing.")])
    assert any(f.check == "action" and f.state is GuardianState.BLOCK for f in report.findings)


def test_advisory_language_is_preserved():
    _, report = review(actions=[action("a1", text="Staff may attend the briefing.", action_type="advisory", mandatory_status="not_required")])
    assert not any(f.check == "action" and f.state is GuardianState.BLOCK for f in report.findings)


def test_conditional_action_promoted_to_required_warns():
    _, report = review(actions=[action("a1", text="If approved, contact the office.", action_type="conditional", mandatory_status="required")])
    assert any(f.check == "action" and f.state is GuardianState.WARN for f in report.findings)


# ---------------------------------------------------------------------------
# 4. Scope check
# ---------------------------------------------------------------------------


def test_supported_audience_passes():
    _, report = review(affected_groups=[group("g1", group_type="cohort", value="final year students", evidence="Eligible final year students should register.")])
    # eligibility-restricted -> WARN, not blocked.
    assert not any(f.check == "scope" and f.state is GuardianState.BLOCK for f in report.findings)


def test_broadened_to_all_students_blocks():
    # Fabrication: claims all students are affected without support.
    _, report = review(affected_groups=[group("g1", group_type="cohort", value="all students", evidence="Eligible final year students should register.")])
    assert report.pipeline_status == "blocked"
    assert any(f.check == "scope" and f.state is GuardianState.BLOCK for f in report.findings)


def test_incomplete_eligibility_warns():
    _, report = review(affected_groups=[group("g1", group_type="cohort", value="eligible students", evidence="Eligible final year students should register.")])
    assert any(f.check == "scope" and f.state is GuardianState.WARN for f in report.findings)


def test_all_students_allowed_when_supported():
    src = "All students must submit the form."
    _, report = review(source=src, affected_groups=[group("g1", group_type="cohort", value="all students", evidence="All students must submit the form.")])
    assert not any(f.check == "scope" and f.state is GuardianState.BLOCK for f in report.findings)


# ---------------------------------------------------------------------------
# 5. Comparison check
# ---------------------------------------------------------------------------


def test_change_without_previous_notice_blocks():
    # Fabrication: a historical change from a single notice.
    _, report = review(changes=[change("c1", old_value="2026-09-01", new_value="2026-10-01", evidence="The submission deadline is 2026-10-01.")])
    assert report.pipeline_status == "blocked"
    assert any(f.check == "comparison" and f.state is GuardianState.BLOCK for f in report.findings)


def test_supported_change_with_previous_notice_passes():
    previous = "The submission deadline is 2026-09-01."
    _, report = review(previous_text=previous, changes=[change("c1", old_value="2026-09-01", new_value="2026-10-01", evidence="The submission deadline is 2026-10-01.")])
    assert not any(f.check == "comparison" for f in report.findings)


def test_change_with_unfounded_old_value_warns():
    previous = "Something unrelated entirely."
    _, report = review(previous_text=previous, changes=[change("c1", old_value="2026-09-01", new_value="2026-10-01", evidence="The submission deadline is 2026-10-01.")])
    assert any(f.check == "comparison" and f.state is GuardianState.WARN for f in report.findings)


def test_change_with_unaligned_new_value_warns():
    previous = "The submission deadline is 2026-09-01."
    _, report = review(previous_text=previous, changes=[change("c1", old_value="2026-09-01", new_value="2026-10-01", evidence="This new-value evidence is absent from the source.")])
    assert any(f.check == "comparison" and f.state is GuardianState.WARN for f in report.findings)


# ---------------------------------------------------------------------------
# 6. Missing reference check
# ---------------------------------------------------------------------------


def test_attached_document_reference_is_flagged():
    _, report = review()
    assert any(f.check == "missing_reference" and "attached document" in f.message for f in report.findings)


def test_external_guideline_reference_is_flagged():
    src = "Proceed as per the guidelines issued last year."
    _, report = review(source=src)
    assert any(f.check == "missing_reference" for f in report.findings)


def test_separate_form_and_additional_circular_flagged():
    src = "Fill the separate form. See the additional circular for eligibility."
    _, report = review(source=src)
    labels = " ".join(f.message for f in report.findings if f.check == "missing_reference")
    assert "separate form" in labels
    assert "additional circular" in labels


def test_no_reference_no_flag():
    src = "The event is on 2026-10-01. Students must register."
    _, report = review(source=src)
    assert not any(f.check == "missing_reference" for f in report.findings)


# ---------------------------------------------------------------------------
# Policy: preserve valid claims, never hide failures, never rewrite evidence
# ---------------------------------------------------------------------------


def test_valid_claims_preserved_when_another_is_blocked():
    # One blocked action (unsupported mandatory) alongside one valid deadline.
    output, report = review(
        deadlines=[deadline("deadline-1")],
        actions=[action("bad", text="Students must submit the completed form.", action_type="mandatory", mandatory_status="optional")],
    )
    assert "bad" in report.blocked_claim_ids
    assert "deadline-1" not in report.blocked_claim_ids
    # The valid deadline is untouched by the block.
    assert output.deadlines[0].normalized_date == date(2026, 10, 1)


def test_failures_are_never_hidden():
    _, report = review(changes=[change("c1", evidence="not in source")])
    assert len(report.problems()) >= 1
    assert all(isinstance(p, str) and p for p in report.problems())


def test_repairs_never_edit_evidence_text():
    output, report = review(deadlines=[deadline(text="The deadline is next Friday.", normalized_date="2026-10-02", is_explicit=False, evidence="The submission deadline is 2026-10-01.")])
    original_evidence = output.deadlines[0].evidence_text
    Guardian.apply_repairs(output, report)
    assert output.deadlines[0].evidence_text == original_evidence
    assert output.deadlines[0].normalized_date is None


# ---------------------------------------------------------------------------
# Pipeline integration: blocked claims never appear as verified actions
# ---------------------------------------------------------------------------


class StaticProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return ProviderResponse(next(self.responses), self.provider_name, self.model_name)


def _notice(session):
    return create_notice(session, NoticeCreate(title="Test", original_text=SOURCE))


def test_pipeline_blocks_unsupported_mandatory_action(session):
    notice = _notice(session)
    payload = build_payload(actions=[action("a1", text="Students must submit the completed form.", action_type="mandatory", mandatory_status="optional")])
    result = NoticeExtractor(StaticProvider([json.dumps(payload)])).extract(session, notice.id)
    assert result.validation_status == "blocked"
    # The blocked action is not persisted as a verified action item.
    assert session.scalar(select(ActionItem).where(ActionItem.notice_id == notice.id)) is None
    assert session.scalar(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice.id)) is None
    refreshed = session.get(Notice, notice.id)
    assert refreshed.processing_status == "needs_review"
    assert refreshed.validation_status == "blocked"


def test_pipeline_blocks_change_without_previous_notice(session):
    notice = _notice(session)
    payload = build_payload(changes=[change("c1", old_value="2026-09-01", new_value="2026-10-01", evidence="The submission deadline is 2026-10-01.")])
    result = NoticeExtractor(StaticProvider([json.dumps(payload)])).extract(session, notice.id)
    assert result.validation_status == "blocked"
    assert session.scalar(select(ChangeRecord).where(ChangeRecord.notice_id == notice.id)) is None


def test_pipeline_repairs_invented_date_then_holds_for_review(session):
    notice = _notice(session)
    payload = build_payload(deadlines=[deadline(text="The deadline is next Friday.", normalized_date="2026-10-02", is_explicit=False)])
    result = NoticeExtractor(StaticProvider([json.dumps(payload)])).extract(session, notice.id)
    assert result.validation_status == "review_required"
    # The invented date was dropped by the repair.
    assert result.deadlines[0].normalized_date is None
    # Not published, because review is required.
    assert session.scalar(select(Deadline).where(Deadline.notice_id == notice.id)) is None


def test_pipeline_publishes_clean_extraction(session):
    # A source with no missing-reference wording so a clean extraction passes.
    clean_source = "The submission deadline is 2026-10-01. Students must submit the completed form."
    clean_notice = create_notice(session, NoticeCreate(title="Clean", original_text=clean_source))
    payload = build_payload(
        deadlines=[{
            "claim_id": "deadline-1",
            "description": "Submission deadline",
            "original_text": "The submission deadline is 2026-10-01.",
            "normalized_date": "2026-10-01",
            "date_precision": "day",
            "is_explicit": True,
            "evidence_text": "The submission deadline is 2026-10-01.",
        }],
        actions=[action("a1", text="Students must submit the completed form.", action_type="mandatory", mandatory_status="required")],
        summary={"claim_id": "summary-1", "text": "A form is due.", "evidence_text": "Students must submit the completed form."},
    )
    result = NoticeExtractor(StaticProvider([json.dumps(payload)])).extract(session, clean_notice.id)
    assert result.validation_status == "validated"
    assert session.scalar(select(Deadline).where(Deadline.notice_id == clean_notice.id)).normalized_date == date(2026, 10, 1)
    assert session.scalar(select(ActionItem).where(ActionItem.notice_id == clean_notice.id)).action_type == "mandatory"


def test_pipeline_preserves_valid_deadline_when_action_blocked(session):
    notice = _notice(session)
    clean_source = "The submission deadline is 2026-10-01. Staff may attend the briefing."
    clean_notice = create_notice(session, NoticeCreate(title="Mixed", original_text=clean_source))
    payload = build_payload(
        summary={"claim_id": "summary-1", "text": "A deadline exists.", "evidence_text": "The submission deadline is 2026-10-01."},
        deadlines=[{
            "claim_id": "deadline-1",
            "description": "Submission deadline",
            "original_text": "The submission deadline is 2026-10-01.",
            "normalized_date": "2026-10-01",
            "date_precision": "day",
            "is_explicit": True,
            "evidence_text": "The submission deadline is 2026-10-01.",
        }],
        actions=[action("bad", text="attend the briefing", action_type="mandatory", mandatory_status="required", evidence="Staff may attend the briefing.")],
    )
    result = NoticeExtractor(StaticProvider([json.dumps(payload)])).extract(session, clean_notice.id)
    # The block holds the whole notice for review, but the blocked action is
    # removed while the valid deadline remains in the returned output.
    assert result.validation_status == "blocked"
    assert [d.claim_id for d in result.deadlines] == ["deadline-1"]
    assert result.actions == []
