from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceStatus = Literal["aligned", "review_required", "blocked"]
ValidationStatus = Literal["validated", "review_required", "blocked"]
ActionType = Literal["mandatory", "advisory", "informational", "conditional", "unclear"]
Severity = Literal["low", "medium", "high"]


class EvidenceClaim(BaseModel):
    claim_id: str = Field(min_length=1)
    evidence_text: str | None = None
    evidence_start: int | None = Field(default=None, ge=0)
    evidence_end: int | None = Field(default=None, ge=0)
    evidence_status: EvidenceStatus = "review_required"


class Summary(EvidenceClaim):
    text: str = Field(min_length=1)


class AffectedGroup(EvidenceClaim):
    group_type: str
    value: str


class Deadline(EvidenceClaim):
    description: str
    original_text: str
    normalized_date: date | None = None
    normalized_time: time | None = None
    timezone: str | None = None
    date_precision: str
    is_explicit: bool = False


class Action(EvidenceClaim):
    action_text: str
    action_type: ActionType
    mandatory_status: str
    due_date: date | None = None
    due_time: time | None = None
    timezone: str | None = None


class Condition(EvidenceClaim):
    text: str


class Change(EvidenceClaim):
    field_name: str
    old_value: str | None = None
    new_value: str | None = None
    change_type: str


class Uncertainty(EvidenceClaim):
    category: str
    description: str
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    severity: Severity
    resolution_status: str = "unresolved"


class ExtractionMetadata(BaseModel):
    provider_name: str
    model_name: str | None = None
    extracted_at: datetime
    source_text_sha256: str
    attempt_count: int = Field(ge=1)
    reference_date: date | None = None


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: Summary
    changes: list[Change] = Field(default_factory=list)
    affected_groups: list[AffectedGroup] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)
    metadata: ExtractionMetadata
    validation_status: ValidationStatus = "review_required"

    @field_validator("changes")
    @classmethod
    def change_list_is_explicit(cls, changes: list[Change]) -> list[Change]:
        return changes
