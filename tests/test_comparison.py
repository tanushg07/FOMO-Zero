import pytest
from sqlalchemy import select

from fomo_zero.comparison import ComparisonError, UnrelatedNoticesError, ChangeRecordOutput, compare_notices
from fomo_zero.models import ChangeRecord
from fomo_zero.repositories import create_notice, save_comparison_changes
from fomo_zero.schemas import NoticeCreate


def test_date_change_has_both_evidence_spans():
    result = compare_notices("Registration closes on 25 October.", "Registration closes on 30 October.")
    change = next(item for item in result.changes if item.field == "deadline")
    assert change.change_type == "modified"
    assert change.previous_value == "25 October"
    assert change.current_value == "30 October"
    assert change.previous_evidence_text == "25 October"
    assert change.current_evidence_text == "30 October"


def test_time_change():
    result = compare_notices("The exam starts at 9:00 AM.", "The exam starts at 10:00 AM.")
    change = next(item for item in result.changes if item.field == "time")
    assert change.change_type == "modified"
    assert change.previous_value == "9:00 AM"
    assert change.current_value == "10:00 AM"


def test_location_change():
    result = compare_notices("Location: Main Hall.", "Location: Science Hall.")
    change = next(item for item in result.changes if item.field == "location")
    assert change.change_type == "modified"
    assert change.previous_value == "Main Hall"
    assert change.current_value == "Science Hall"


def test_added_action():
    result = compare_notices("Registration closes on 25 October.", "Registration closes on 25 October. Students must submit the form.")
    change = next(item for item in result.changes if item.field == "action")
    assert change.change_type == "added"
    assert change.previous_value is None


def test_removed_action():
    result = compare_notices("Registration closes on 25 October. Students must submit the form.", "Registration closes on 25 October.")
    change = next(item for item in result.changes if item.field == "action")
    assert change.change_type == "removed"
    assert change.current_value is None


def test_advisory_to_mandatory_is_modified_without_reason():
    result = compare_notices("Students are advised to attend.", "Students are required to attend.")
    change = next(item for item in result.changes if item.field == "action")
    assert change.change_type == "modified"
    assert "advised" in change.previous_value
    assert "required" in change.current_value


def test_no_actual_change_is_unchanged():
    result = compare_notices("Registration closes on 25 October.", "Registration closes on 25 October.")
    assert result.validation_status == "validated"
    assert result.changes
    assert all(change.change_type == "unchanged" for change in result.changes)


def test_unrelated_notices_are_rejected():
    with pytest.raises(UnrelatedNoticesError):
        compare_notices("Basketball tryouts are in Gym A on 25 October.", "Library cards are issued in Office B on 30 October.")


def test_missing_version_is_rejected():
    with pytest.raises(ComparisonError):
        compare_notices("Registration closes on 25 October.", "")


def test_missing_evidence_is_not_validated():
    change = ChangeRecordOutput(field="deadline", change_type="modified", validation_status="review_required")
    assert change.previous_evidence_text is None
    assert change.current_evidence_text is None
    assert change.validation_status == "review_required"


def test_title_and_notice_date_are_compared():
    result = compare_notices(
        "Registration closes on 25 October.",
        "Registration closes on 30 October.",
        previous_title="Fall registration",
        current_title="Updated fall registration",
        previous_notice_date="2026-09-01",
        current_notice_date="2026-09-15",
    )
    assert next(item for item in result.changes if item.field == "title").change_type == "modified"
    assert next(item for item in result.changes if item.field == "notice_date").change_type == "modified"


def test_validated_changes_persist_for_current_notice(session):
    previous = create_notice(session, NoticeCreate(title="Registration", original_text="Registration closes on 25 October."))
    current = create_notice(session, NoticeCreate(title="Registration", original_text="Registration closes on 30 October."))
    result = compare_notices(previous.original_text, current.original_text, previous_notice_id=previous.id, current_notice_id=current.id)
    records = save_comparison_changes(session, current.id, result)
    assert len(records) == 1
    record = session.scalar(select(ChangeRecord).where(ChangeRecord.notice_id == current.id))
    assert record.old_value == "25 October"
    assert record.new_value == "30 October"
    assert record.previous_evidence_text == "25 October"
    assert record.current_evidence_text == "30 October"
