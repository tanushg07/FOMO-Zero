from datetime import date

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from fomo_zero.models import ActionItem, AffectedGroup, Deadline, Notice
from fomo_zero.repositories import (
    create_notice,
    get_notice,
    reset_extraction_draft,
    save_affected_groups,
    save_deadlines,
    save_extracted_actions,
    save_validation_flags,
)
from fomo_zero.schemas import ActionItemCreate, AffectedGroupCreate, DeadlineCreate, NoticeCreate


def notice_data() -> NoticeCreate:
    return NoticeCreate(title="Road closure", original_text="Road closure on 2026-10-01.", notice_date=date(2026, 10, 1))


def test_database_creation(engine):
    assert {"notices", "action_items", "affected_groups", "deadlines"}.issubset(inspect(engine).get_table_names())


def test_insert_and_retrieve_notice(session):
    created = create_notice(session, notice_data())
    retrieved = get_notice(session, created.id)
    assert retrieved is not None
    assert retrieved.title == "Road closure"
    assert retrieved.notice_date == date(2026, 10, 1)
    assert retrieved.created_at == retrieved.created_at.replace(tzinfo=None)


def test_notice_to_actions_relationship_and_reprocessing(session):
    notice = create_notice(session, notice_data())
    action = ActionItemCreate(action_text="Avoid road", action_type="avoidance", mandatory_status="required", evidence_text="Avoid road")
    save_extracted_actions(session, notice.id, [action])
    save_extracted_actions(session, notice.id, [action, action])
    assert len(session.scalars(select(ActionItem).where(ActionItem.notice_id == notice.id)).all()) == 2


def test_nullable_fields_remain_null(session):
    notice = create_notice(session, NoticeCreate(title="Minimal", original_text="Text"))
    assert notice.source_filename is None
    assert notice.issuing_authority is None
    save_deadlines(session, notice.id, [DeadlineCreate(description="Later", original_text="later", date_precision="unknown")])
    deadline = session.scalar(select(Deadline).where(Deadline.notice_id == notice.id))
    assert deadline.normalized_date is None
    assert deadline.normalized_time is None


def test_foreign_key_integrity(session):
    with pytest.raises(IntegrityError):
        session.add(ActionItem(notice_id="missing", action_text="x", action_type="x", mandatory_status="required", evidence_text="x"))
        session.commit()
    session.rollback()


def test_reset_extraction_draft_removes_all_extracted_records(session):
    notice = create_notice(session, notice_data())
    save_affected_groups(session, notice.id, [AffectedGroupCreate(group_type="resident", value="A", evidence_text="A")])
    save_extracted_actions(session, notice.id, [ActionItemCreate(action_text="Act", action_type="task", mandatory_status="required", evidence_text="Act")])
    save_deadlines(session, notice.id, [DeadlineCreate(description="D", original_text="D", date_precision="day")])
    save_validation_flags(session, notice.id, notice_status="invalid")
    reset_extraction_draft(session, notice.id)
    refreshed = get_notice(session, notice.id)
    assert refreshed.processing_status == "pending"
    assert refreshed.validation_status == "unvalidated"
    assert refreshed.action_items == []
    assert refreshed.deadlines == []
    assert refreshed.affected_groups == []


def test_transaction_rollback(session):
    notice = create_notice(session, notice_data())
    with session.begin_nested():
        notice.title = "temporary"
        session.flush()
        session.rollback()
    assert session.get(Notice, notice.id).title == "Road closure"
