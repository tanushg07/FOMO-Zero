from datetime import date, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NoticeCreate(BaseModel):
    title: str = Field(min_length=1)
    original_text: str = Field(min_length=1)
    source_filename: Optional[str] = None
    issuing_authority: Optional[str] = None
    notice_date: Optional[date] = None
    processing_status: str = "pending"
    validation_status: str = "unvalidated"


class AffectedGroupCreate(BaseModel):
    group_type: str
    value: str
    evidence_text: str
    evidence_start: Optional[int] = None
    evidence_end: Optional[int] = None


class ActionItemCreate(BaseModel):
    action_text: str
    action_type: str
    mandatory_status: str
    completion_status: str = "not_started"
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    timezone: Optional[str] = None
    evidence_text: str
    evidence_start: Optional[int] = None
    evidence_end: Optional[int] = None
    validation_status: str = "unvalidated"


class DeadlineCreate(BaseModel):
    description: str
    original_text: str
    normalized_date: Optional[date] = None
    normalized_time: Optional[time] = None
    timezone: Optional[str] = None
    date_precision: str
    is_explicit: bool = False
    validation_status: str = "unvalidated"


class NoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_text: str
    source_filename: Optional[str]
    issuing_authority: Optional[str]
    notice_date: Optional[date]
    processing_status: str
    validation_status: str
