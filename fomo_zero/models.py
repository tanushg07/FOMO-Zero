from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Optional
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid4())


class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(500))
    issuing_authority: Mapped[Optional[str]] = mapped_column(String(500))
    notice_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    validation_status: Mapped[str] = mapped_column(String(50), default="unvalidated", nullable=False, index=True)
    validation_reason: Mapped[Optional[str]] = mapped_column(Text)

    affected_groups: Mapped[list[AffectedGroup]] = relationship(back_populates="notice", cascade="all, delete-orphan")
    action_items: Mapped[list[ActionItem]] = relationship(back_populates="notice", cascade="all, delete-orphan")
    deadlines: Mapped[list[Deadline]] = relationship(back_populates="notice", cascade="all, delete-orphan")
    change_records: Mapped[list[ChangeRecord]] = relationship(back_populates="notice", cascade="all, delete-orphan")
    uncertainty_records: Mapped[list[UncertaintyRecord]] = relationship(back_populates="notice", cascade="all, delete-orphan")
    extraction_record: Mapped[Optional[ExtractionRecord]] = relationship(back_populates="notice", cascade="all, delete-orphan", uselist=False)


class NoticeChild:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    notice_id: Mapped[str] = mapped_column(ForeignKey("notices.id", ondelete="CASCADE"), nullable=False, index=True)


class AffectedGroup(NoticeChild, Base):
    __tablename__ = "affected_groups"

    group_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    notice: Mapped[Notice] = relationship(back_populates="affected_groups")


class ActionItem(NoticeChild, Base):
    __tablename__ = "action_items"

    action_text: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    mandatory_status: Mapped[str] = mapped_column(String(50), nullable=False)
    completion_status: Mapped[str] = mapped_column(String(50), default="not_started", nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    due_time: Mapped[Optional[time]] = mapped_column(Time)
    timezone: Mapped[Optional[str]] = mapped_column(String(100))
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    validation_status: Mapped[str] = mapped_column(String(50), default="unvalidated", nullable=False, index=True)
    notice: Mapped[Notice] = relationship(back_populates="action_items")


class Deadline(NoticeChild, Base):
    __tablename__ = "deadlines"

    description: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_date: Mapped[Optional[date]] = mapped_column(Date)
    normalized_time: Mapped[Optional[time]] = mapped_column(Time)
    timezone: Mapped[Optional[str]] = mapped_column(String(100))
    date_precision: Mapped[str] = mapped_column(String(50), nullable=False)
    is_explicit: Mapped[bool] = mapped_column(nullable=False, default=False)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    validation_status: Mapped[str] = mapped_column(String(50), default="unvalidated", nullable=False, index=True)
    notice: Mapped[Notice] = relationship(back_populates="deadlines")


class ChangeRecord(NoticeChild, Base):
    __tablename__ = "change_records"

    comparison_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    field_name: Mapped[str] = mapped_column(String(200), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    previous_evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    previous_evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    previous_evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    current_evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    current_evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    current_evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    validation_status: Mapped[str] = mapped_column(String(50), default="unvalidated", nullable=False, index=True)
    notice: Mapped[Notice] = relationship(back_populates="change_records")


class UncertaintyRecord(NoticeChild, Base):
    __tablename__ = "uncertainty_records"

    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(50), default="unresolved", nullable=False)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    notice: Mapped[Notice] = relationship(back_populates="uncertainty_records")


class ExtractionRecord(Base):
    __tablename__ = "extraction_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    notice_id: Mapped[str] = mapped_column(ForeignKey("notices.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    summary_evidence_start: Mapped[Optional[int]] = mapped_column(Integer)
    summary_evidence_end: Mapped[Optional[int]] = mapped_column(Integer)
    conditions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    validation_status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    notice: Mapped[Notice] = relationship(back_populates="extraction_record")


Index("ix_action_items_notice_due_date", ActionItem.notice_id, ActionItem.due_date)
Index("ix_deadlines_notice_normalized_date", Deadline.notice_id, Deadline.normalized_date)
