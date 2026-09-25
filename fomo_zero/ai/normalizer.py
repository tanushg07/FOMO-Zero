from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .schemas import EvidenceClaim, ExtractionOutput


@dataclass(frozen=True)
class Alignment:
    text: str | None
    start: int | None
    end: int | None
    status: str


def align_evidence(source: str, evidence: str | None) -> Alignment:
    if not evidence or not evidence.strip():
        return Alignment(evidence, None, None, "blocked")
    exact_start = source.find(evidence)
    if exact_start >= 0:
        return Alignment(evidence, exact_start, exact_start + len(evidence), "aligned")

    parts = [re.escape(part) for part in re.split(r"\s+", evidence.strip()) if part]
    if not parts:
        return Alignment(evidence, None, None, "blocked")
    match = re.search(r"\s+".join(parts), source, flags=re.MULTILINE)
    if match:
        return Alignment(evidence, match.start(), match.end(), "aligned")
    return Alignment(evidence, None, None, "review_required")


def normalize_claim(claim: EvidenceClaim, source: str) -> None:
    alignment = align_evidence(source, claim.evidence_text)
    claim.evidence_start = alignment.start
    claim.evidence_end = alignment.end
    claim.evidence_status = alignment.status  # type: ignore[assignment]


def normalize_extraction(output: ExtractionOutput, source: str) -> ExtractionOutput:
    claims: Iterable[EvidenceClaim] = [
        output.summary,
        *output.changes,
        *output.affected_groups,
        *output.deadlines,
        *output.actions,
        *output.conditions,
        *output.uncertainties,
    ]
    for claim in claims:
        normalize_claim(claim, source)
    return output
