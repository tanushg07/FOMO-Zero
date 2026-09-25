from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import ExtractionOutput


@dataclass(frozen=True)
class ValidationResult:
    status: str
    problems: tuple[str, ...]


def validate_extraction(output: ExtractionOutput, *, previous_text: str | None = None) -> ValidationResult:
    problems: list[str] = []
    all_claims = [
        output.summary,
        *output.changes,
        *output.affected_groups,
        *output.deadlines,
        *output.actions,
        *output.conditions,
        *output.uncertainties,
    ]
    for claim in all_claims:
        if claim.evidence_status == "blocked":
            problems.append(f"{claim.claim_id}: evidence is missing")
        elif claim.evidence_status == "review_required":
            problems.append(f"{claim.claim_id}: evidence could not be aligned")

    if previous_text is None and output.changes:
        problems.append("changes were reported without a previous notice")

    for action in output.actions:
        if action.action_type == "mandatory" and action.mandatory_status.lower() not in {"required", "mandatory", "yes"}:
            problems.append(f"{action.claim_id}: mandatory action has unsupported mandatory status")

    for deadline in output.deadlines:
        if deadline.normalized_date is not None and not deadline.is_explicit:
            problems.append(f"{deadline.claim_id}: normalized date is not explicitly supported")
        if re.search(r"\b(today|tomorrow|yesterday|next week|next month)\b", deadline.original_text, re.I) and deadline.normalized_date is not None:
            problems.append(f"{deadline.claim_id}: relative date was normalized without a reliable reference date")

    status = "validated" if not problems else "review_required"
    return ValidationResult(status, tuple(problems))
