from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NoticeTextRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    text: str = Field(min_length=1)
    source_filename: str | None = Field(default=None, max_length=500)
    issuing_authority: str | None = Field(default=None, max_length=500)
    notice_date: date | None = None

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Notice text cannot be blank")
        return value.strip()


class ActionItemResponse(BaseModel):
    task: str
    deadline: str | None = None
    priority: str

class CriticalDateResponse(BaseModel):
    date: str
    event: str


class NoticeResponse(BaseModel):
    id: str
    title: str
    original_text: str
    source_filename: str | None
    issuing_authority: str | None
    notice_date: date | None
    created_at: datetime
    updated_at: datetime
    processing_status: str
    validation_status: str
    validation_reason: str | None = None
    target_audience: str = ""
    core_update: str = ""
    critical_dates: list[CriticalDateResponse] = Field(default_factory=list)
    action_checklist: list[ActionItemResponse] = Field(default_factory=list)
    consequence_if_missed: str = ""
    raw_evidence: str = ""

    @classmethod
    def from_model(cls, notice):
        target_audience = ", ".join(g.value for g in notice.affected_groups) if notice.affected_groups else ""
        core_update = notice.extraction_record.summary_text if getattr(notice, 'extraction_record', None) else "No summary available."
        
        critical_dates = []
        for d in notice.deadlines:
            d_date = d.normalized_date.isoformat() if d.normalized_date else d.original_text
            critical_dates.append(CriticalDateResponse(date=d_date, event=d.description))
            
        action_checklist = []
        for a in notice.action_items:
            a_deadline = a.due_date.isoformat() if a.due_date else None
            a_priority = "High" if a.mandatory_status in {"mandatory", "required", "yes"} else "Medium"
            action_checklist.append(ActionItemResponse(task=a.action_text, deadline=a_deadline, priority=a_priority))
            
        evidences = []
        if getattr(notice, 'extraction_record', None) and notice.extraction_record.summary_evidence_text:
            evidences.append(f"Summary Evidence:\n{notice.extraction_record.summary_evidence_text}")
        for a in notice.action_items:
            if a.evidence_text:
                evidences.append(f"Action '{a.action_text}' Evidence:\n{a.evidence_text}")
        raw_evidence = "\n\n".join(evidences)

        vs_map = {"validated": "Verified", "unvalidated": "Needs Review", "review_required": "Needs Review", "blocked": "Blocked"}
        mapped_vs = vs_map.get(notice.validation_status, "Needs Review")
        if notice.processing_status == "failed":
            mapped_vs = "Blocked"

        return cls(
            id=notice.id,
            title=notice.title,
            original_text=notice.original_text,
            source_filename=notice.source_filename,
            issuing_authority=notice.issuing_authority,
            notice_date=notice.notice_date,
            created_at=notice.created_at,
            updated_at=notice.updated_at,
            processing_status=notice.processing_status,
            validation_status=mapped_vs,
            validation_reason=notice.validation_reason,
            target_audience=target_audience,
            core_update=core_update,
            critical_dates=critical_dates,
            action_checklist=action_checklist,
            consequence_if_missed="",
            raw_evidence=raw_evidence
        )


class NoticeListResponse(BaseModel):
    items: list[NoticeResponse]
    limit: int
    offset: int


class IngestionErrorResponse(BaseModel):
    error: Literal[
        "invalid_input",
        "unsupported_file_type",
        "file_too_large",
        "ocr_needed",
        "extraction_failed",
        "notice_not_found",
        "database_failure",
    ]
    message: str
