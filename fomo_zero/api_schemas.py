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

    @classmethod
    def from_model(cls, notice):
        return cls.model_validate(notice, from_attributes=True)


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
