from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ChangeType = Literal["added", "removed", "modified", "unchanged"]
ValidationStatus = Literal["validated", "review_required", "blocked"]


class EvidenceSpan(BaseModel):
    text: str
    start: int
    end: int


class ChangeRecordOutput(BaseModel):
    field: str
    previous_value: str | None = None
    current_value: str | None = None
    change_type: ChangeType
    previous_evidence_text: str | None = None
    previous_evidence_start: int | None = None
    previous_evidence_end: int | None = None
    current_evidence_text: str | None = None
    current_evidence_start: int | None = None
    current_evidence_end: int | None = None
    validation_status: ValidationStatus


class ComparisonResult(BaseModel):
    comparison_id: str = Field(default_factory=lambda: str(uuid4()))
    previous_notice_id: str | None = None
    current_notice_id: str | None = None
    changes: list[ChangeRecordOutput]
    validation_status: ValidationStatus
    compared_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ComparisonError(Exception):
    pass


class UnrelatedNoticesError(ComparisonError):
    pass


@dataclass(frozen=True)
class _Fact:
    field: str
    value: str
    evidence: EvidenceSpan
    key: str


_DATE = r"(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?|\d{4}-\d{2}-\d{2})"
_TIME = r"(?:\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)|\d{1,2}:\d{2})"


def _span(source: str, match: re.Match[str]) -> EvidenceSpan:
    return EvidenceSpan(text=match.group(0), start=match.start(), end=match.end())


def _facts(source: str) -> list[_Fact]:
    facts: list[_Fact] = []
    for match in re.finditer(_DATE, source):
        facts.append(_Fact("deadline", match.group(0), _span(source, match), f"deadline:{match.group(0).lower()}"))
    for match in re.finditer(_TIME, source):
        facts.append(_Fact("time", match.group(0), _span(source, match), f"time:{match.group(0).lower()}"))
    for match in re.finditer(r"(?i)(?:location|venue)\s*:\s*([^\.\n]+)", source):
        value = match.group(1).strip()
        start = match.start(1) + (len(match.group(1)) - len(match.group(1).lstrip()))
        evidence = EvidenceSpan(text=match.group(0), start=match.start(), end=match.end())
        facts.append(_Fact("location", value, evidence, "location:" + _normalize(value)))
    for match in re.finditer(r"(?i)\b(?:all|eligible|first-year|undergraduate|graduate)\s+students\b[^\.\n]*", source):
        facts.append(_Fact("affected_group", match.group(0).strip(), _span(source, match), "group:" + re.sub(r"\s+", " ", match.group(0).lower()).strip()))
    for sentence in _sentences(source):
        lower = sentence.text.lower()
        if re.search(r"\b(must|required to|are required|need to|shall|advised to|encouraged to|may)\b", lower):
            facts.append(_Fact("action", sentence.text, sentence, "action:" + _normalize(sentence.text)))
        if re.match(r"\s*(if|when|unless|provided that)\b", lower):
            facts.append(_Fact("condition", sentence.text, sentence, "condition:" + _normalize(sentence.text)))
        if re.match(r"\s*(please|submit|register|contact|complete|attend|bring|visit)\b", lower):
            facts.append(_Fact("instruction", sentence.text, sentence, "instruction:" + _normalize(sentence.text)))
    return facts


def _sentences(source: str) -> list[EvidenceSpan]:
    return [EvidenceSpan(text=m.group(0).strip(), start=m.start(), end=m.end()) for m in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", source) if m.group(0).strip()]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().strip(" .!?"))


def _change(field: str, previous: _Fact | None, current: _Fact | None, change_type: ChangeType, status: ValidationStatus = "validated") -> ChangeRecordOutput:
    return ChangeRecordOutput(
        field=field,
        previous_value=previous.value if previous else None,
        current_value=current.value if current else None,
        change_type=change_type,
        previous_evidence_text=previous.evidence.text if previous else None,
        previous_evidence_start=previous.evidence.start if previous else None,
        previous_evidence_end=previous.evidence.end if previous else None,
        current_evidence_text=current.evidence.text if current else None,
        current_evidence_start=current.evidence.start if current else None,
        current_evidence_end=current.evidence.end if current else None,
        validation_status=status,
    )


def compare_notices(
    previous_text: str,
    current_text: str,
    *,
    previous_title: str | None = None,
    current_title: str | None = None,
    previous_notice_date: str | None = None,
    current_notice_date: str | None = None,
    previous_notice_id: str | None = None,
    current_notice_id: str | None = None,
) -> ComparisonResult:
    if not previous_text or not previous_text.strip() or not current_text or not current_text.strip():
        raise ComparisonError("Both previous and current notices are required")
    previous_facts = _facts(previous_text)
    current_facts = _facts(current_text)
    previous_dates = {fact.value.lower(): fact for fact in previous_facts if fact.field == "deadline"}
    current_dates = {fact.value.lower(): fact for fact in current_facts if fact.field == "deadline"}
    title_tokens_previous = set(re.findall(r"[a-z]{4,}", _normalize(previous_title or "")))
    title_tokens_current = set(re.findall(r"[a-z]{4,}", _normalize(current_title or "")))
    if title_tokens_previous and title_tokens_current and not title_tokens_previous & title_tokens_current:
        raise UnrelatedNoticesError("The notice titles do not identify the same event")
    previous_tokens = _event_tokens(previous_text)
    current_tokens = _event_tokens(current_text)
    common_tokens = previous_tokens & current_tokens
    shared_labeled_fields = {
        label
        for label in ("location", "venue")
        if re.search(rf"(?i)\b{label}\s*:", previous_text) and re.search(rf"(?i)\b{label}\s*:", current_text)
    }
    if not common_tokens and not shared_labeled_fields and _normalize(previous_text) != _normalize(current_text):
        # Different unstructured notices cannot be safely linked without a stable event key.
        raise UnrelatedNoticesError("The notices have no supported matching event fields")

    changes: list[ChangeRecordOutput] = []
    if previous_title or current_title:
        old_title = _metadata_fact("title", previous_title)
        new_title = _metadata_fact("title", current_title)
        if old_title and new_title:
            changes.append(_change("title", old_title, new_title, "unchanged" if _normalize(old_title.value) == _normalize(new_title.value) else "modified"))
    if previous_notice_date or current_notice_date:
        old_date = _metadata_fact("notice_date", previous_notice_date)
        new_date = _metadata_fact("notice_date", current_notice_date)
        if old_date and new_date:
            changes.append(_change("notice_date", old_date, new_date, "unchanged" if old_date.value == new_date.value else "modified"))
    for field in {fact.field for fact in previous_facts + current_facts}:
        old = [fact for fact in previous_facts if fact.field == field]
        new = [fact for fact in current_facts if fact.field == field]
        used_new: set[int] = set()
        for old_fact in old:
            match_index = next((index for index, fact in enumerate(new) if index not in used_new and fact.key == old_fact.key), None)
            if match_index is not None:
                used_new.add(match_index)
                changes.append(_change(field, old_fact, new[match_index], "unchanged"))
            elif new and len(old) == 1 and len(new) == 1:
                used_new.add(0)
                changes.append(_change(field, old_fact, new[0], "modified"))
            else:
                changes.append(_change(field, old_fact, None, "removed"))
        for index, new_fact in enumerate(new):
            if index not in used_new:
                changes.append(_change(field, None, new_fact, "added"))

    changed = [change for change in changes if change.change_type != "unchanged"]
    return ComparisonResult(
        previous_notice_id=previous_notice_id,
        current_notice_id=current_notice_id,
        changes=changes,
        validation_status="validated" if all(change.validation_status == "validated" for change in changed) else "review_required",
    )


def _metadata_fact(field: str, value: str | None) -> _Fact | None:
    if value is None:
        return None
    return _Fact(field, value, EvidenceSpan(text=value, start=0, end=len(value)), field + ":" + _normalize(value))


def _event_tokens(source: str) -> set[str]:
    ignored = {
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december", "location", "venue", "hall",
        "office", "gym", "room", "building", "students", "notice",
    }
    return {token for token in re.findall(r"[a-z]{4,}", _normalize(source)) if token not in ignored}
