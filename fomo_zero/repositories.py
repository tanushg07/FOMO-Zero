from __future__ import annotations

from collections.abc import Iterable
import json
from typing import Any, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from .ai.schemas import ExtractionOutput
from .models import ActionItem, AffectedGroup, ChangeRecord, Deadline, ExtractionRecord, Notice, UncertaintyRecord
from .schemas import ActionItemCreate, AffectedGroupCreate, DeadlineCreate, NoticeCreate

T = TypeVar("T")


def create_notice(session: Session, data: NoticeCreate) -> Notice:
    notice = Notice(**data.model_dump())
    session.add(notice)
    session.commit()
    session.refresh(notice)
    return notice


def get_notice(session: Session, notice_id: str) -> Notice | None:
    statement = (
        select(Notice)
        .where(Notice.id == notice_id)
        .options(
            selectinload(Notice.affected_groups),
            selectinload(Notice.action_items),
            selectinload(Notice.deadlines),
            selectinload(Notice.change_records),
            selectinload(Notice.uncertainty_records),
        )
    )
    return session.scalar(statement)


def list_notices(session: Session, *, limit: int = 100, offset: int = 0) -> list[Notice]:
    return list(session.scalars(select(Notice).order_by(Notice.created_at.desc()).limit(limit).offset(offset)))


def _replace_children(session: Session, notice_id: str, model: type[T], values: Iterable[dict[str, Any]]) -> list[T]:
    session.execute(delete(model).where(model.notice_id == notice_id))
    records = [model(notice_id=notice_id, **value) for value in values]
    session.add_all(records)
    session.commit()
    return records


def save_extracted_actions(session: Session, notice_id: str, actions: Iterable[ActionItemCreate]) -> list[ActionItem]:
    return _replace_children(session, notice_id, ActionItem, (action.model_dump() for action in actions))


def save_deadlines(session: Session, notice_id: str, deadlines: Iterable[DeadlineCreate]) -> list[Deadline]:
    return _replace_children(session, notice_id, Deadline, (deadline.model_dump() for deadline in deadlines))


def save_affected_groups(session: Session, notice_id: str, groups: Iterable[AffectedGroupCreate]) -> list[AffectedGroup]:
    return _replace_children(session, notice_id, AffectedGroup, (group.model_dump() for group in groups))


def save_validation_flags(session: Session, notice_id: str, *, notice_status: str | None = None, action_status: str | None = None, deadline_status: str | None = None) -> None:
    notice = session.get(Notice, notice_id)
    if notice is None:
        raise LookupError(f"Notice not found: {notice_id}")
    if notice_status is not None:
        notice.validation_status = notice_status
    if action_status is not None:
        session.query(ActionItem).filter(ActionItem.notice_id == notice_id).update({"validation_status": action_status})
    if deadline_status is not None:
        session.query(Deadline).filter(Deadline.notice_id == notice_id).update({"validation_status": deadline_status})
    session.commit()


def reset_extraction_draft(session: Session, notice_id: str) -> None:
    notice = session.get(Notice, notice_id)
    if notice is None:
        raise LookupError(f"Notice not found: {notice_id}")
    notice.processing_status = "pending"
    notice.validation_status = "unvalidated"
    notice.affected_groups.clear()
    notice.action_items.clear()
    notice.deadlines.clear()
    notice.change_records.clear()
    notice.uncertainty_records.clear()
    notice.extraction_record = None
    session.commit()


def set_notice_processing_status(session: Session, notice_id: str, processing_status: str, *, validation_status: str | None = None) -> None:
    notice = session.get(Notice, notice_id)
    if notice is None:
        raise LookupError(f"Notice not found: {notice_id}")
    notice.processing_status = processing_status
    if validation_status is not None:
        notice.validation_status = validation_status
    session.commit()


def save_extraction_output(session: Session, notice_id: str, output: ExtractionOutput) -> ExtractionRecord:
    if output.validation_status != "validated":
        raise ValueError("Only validated extraction output may be saved")
    notice = session.get(Notice, notice_id)
    if notice is None:
        raise LookupError(f"Notice not found: {notice_id}")

    for model in (AffectedGroup, ActionItem, Deadline, ChangeRecord, UncertaintyRecord):
        session.execute(delete(model).where(model.notice_id == notice_id))
    session.execute(delete(ExtractionRecord).where(ExtractionRecord.notice_id == notice_id))
    summary = output.summary
    record = ExtractionRecord(
        notice_id=notice_id,
        summary_text=summary.text,
        summary_evidence_text=summary.evidence_text,
        summary_evidence_start=summary.evidence_start,
        summary_evidence_end=summary.evidence_end,
        conditions_json=json.dumps([condition.model_dump(mode="json") for condition in output.conditions]),
        metadata_json=json.dumps(output.metadata.model_dump(mode="json")),
        validation_status=output.validation_status,
    )
    session.add(record)
    session.add_all(
        AffectedGroup(notice_id=notice_id, **group.model_dump(include={"group_type", "value", "evidence_text", "evidence_start", "evidence_end"}))
        for group in output.affected_groups
    )
    session.add_all(
        ActionItem(notice_id=notice_id, **action.model_dump(include={"action_text", "action_type", "mandatory_status", "due_date", "due_time", "timezone", "evidence_text", "evidence_start", "evidence_end"}))
        for action in output.actions
    )
    session.add_all(
        Deadline(notice_id=notice_id, **deadline.model_dump(include={"description", "original_text", "normalized_date", "normalized_time", "timezone", "date_precision", "is_explicit", "evidence_text", "evidence_start", "evidence_end"}))
        for deadline in output.deadlines
    )
    session.add_all(
        ChangeRecord(notice_id=notice_id, **change.model_dump(include={"field_name", "old_value", "new_value", "change_type", "evidence_text", "evidence_start", "evidence_end"}))
        for change in output.changes
    )
    session.add_all(
        UncertaintyRecord(notice_id=notice_id, **uncertainty.model_dump(include={"category", "description", "related_entity_type", "related_entity_id", "severity", "resolution_status", "evidence_text", "evidence_start", "evidence_end"}))
        for uncertainty in output.uncertainties
    )
    session.commit()
    session.refresh(record)
    return record
