"""Guardian validation layer.

The Guardian is the last gate before extracted notice content is published to
students as verified information. It exists to stop unsupported AI claims from
reaching students. It does not trust the model: it independently re-checks the
extraction output against the original notice text and the (optional) previous
notice, and assigns each claim one of four states.

States
------
PASS   The claim is supported by source evidence and internally consistent.
       Safe to publish as verified information.
WARN   The claim is ambiguous or incomplete. Publish only with a review flag;
       never present it as fully verified.
BLOCK  The claim is unsupported, fabricated, or a critical safety failure.
       It must NOT be published as a verified action.
REPAIR The claim carries an invented/derived value that is not supported by the
       source, but a safe, source-faithful version exists (drop the invented
       value, keep the wording). The Guardian records the repair intent; the
       caller applies it. The Guardian never silently rewrites source evidence.

Policy
------
* BLOCK unsupported critical claims.
* WARN on ambiguous or incomplete information.
* Do not hide validation failures (every finding is recorded and reported).
* Preserve valid claims even when another claim fails (findings are per-claim).
* Never silently rewrite source evidence (repairs are explicit and only ever
  remove unsupported derived values, never edit the quoted evidence text).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum

from .schemas import Action, Change, Deadline, EvidenceClaim, ExtractionOutput

# ---------------------------------------------------------------------------
# States and reports
# ---------------------------------------------------------------------------


class GuardianState(IntEnum):
    """Ordered so that ``max`` gives the most severe state of a set."""

    PASS = 0
    WARN = 1
    REPAIR = 2
    BLOCK = 3

    @property
    def label(self) -> str:
        return self.name


# The check that produced a finding, for honest, navigable reporting.
CheckName = str
EVIDENCE_CHECK: CheckName = "evidence"
DATE_CHECK: CheckName = "date"
ACTION_CHECK: CheckName = "action"
SCOPE_CHECK: CheckName = "scope"
COMPARISON_CHECK: CheckName = "comparison"
MISSING_REFERENCE_CHECK: CheckName = "missing_reference"


@dataclass(frozen=True)
class GuardianFinding:
    """A single validation observation about one claim (or the notice as a whole)."""

    check: CheckName
    state: GuardianState
    claim_id: str
    message: str
    # For REPAIR findings: which field should be dropped to make the claim safe.
    repair_field: str | None = None

    def describe(self) -> str:
        return f"[{self.state.label}] {self.check}:{self.claim_id}: {self.message}"


@dataclass
class GuardianReport:
    """The full, non-hiding result of Guardian validation."""

    findings: list[GuardianFinding] = field(default_factory=list)
    # Claim ids that must not be published as verified information.
    blocked_claim_ids: set[str] = field(default_factory=set)
    # Claim ids that are publishable only behind a review flag.
    warned_claim_ids: set[str] = field(default_factory=set)
    # Repairs the caller should apply (claim_id -> fields to clear).
    repairs: dict[str, set[str]] = field(default_factory=dict)

    def add(self, finding: GuardianFinding) -> None:
        self.findings.append(finding)
        if finding.state is GuardianState.BLOCK:
            self.blocked_claim_ids.add(finding.claim_id)
        elif finding.state is GuardianState.WARN:
            self.warned_claim_ids.add(finding.claim_id)
        elif finding.state is GuardianState.REPAIR and finding.repair_field is not None:
            self.repairs.setdefault(finding.claim_id, set()).add(finding.repair_field)

    @property
    def state(self) -> GuardianState:
        """The overall verdict: the most severe finding, or PASS if clean."""
        if not self.findings:
            return GuardianState.PASS
        return max(finding.state for finding in self.findings)

    @property
    def pipeline_status(self) -> str:
        """Map the Guardian verdict onto the existing ValidationStatus vocabulary.

        BLOCK  -> "blocked"          (critical, must not be published)
        WARN   -> "review_required"  (ambiguous/incomplete, needs a human)
        REPAIR -> "review_required"  (a safe version exists but a human should confirm)
        PASS   -> "validated"        (safe to publish as verified)
        """
        overall = self.state
        if overall is GuardianState.BLOCK:
            return "blocked"
        if overall in (GuardianState.WARN, GuardianState.REPAIR):
            return "review_required"
        return "validated"

    def problems(self) -> tuple[str, ...]:
        """Human-readable descriptions of every finding. Failures are never hidden."""
        return tuple(finding.describe() for finding in self.findings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RELATIVE_DATE_PATTERN = re.compile(
    r"\b(today|tomorrow|yesterday|next\s+week|next\s+month|last\s+week|last\s+month|"
    r"this\s+week|this\s+month|next\s+\w+day|following\s+week|soon|shortly|tbd|tba)\b",
    re.IGNORECASE,
)

_MANDATORY_STATUS_TOKENS = {"required", "mandatory", "yes", "compulsory", "must"}
_ADVISORY_ACTION_TYPES = {"advisory", "informational", "conditional", "unclear"}

# Phrases that indicate the notice points at something not contained in the text.
_MISSING_REFERENCE_PATTERNS = (
    (re.compile(r"\battached\s+(document|form|circular|file|pdf|copy)\b", re.I), "attached document"),
    (re.compile(r"\bsee\s+(the\s+)?attach", re.I), "attached document"),
    (re.compile(r"\benclosed\b", re.I), "enclosed document"),
    (re.compile(r"\bannexure\b", re.I), "annexure"),
    (re.compile(r"\bappendix\b", re.I), "appendix"),
    (re.compile(r"\bas\s+per\s+(the\s+)?guidelines?\b", re.I), "external guideline"),
    (re.compile(r"\brefer\s+to\s+(the\s+)?(guidelines?|circular|notice|form|document)\b", re.I), "external reference"),
    (re.compile(r"\bseparate\s+form\b", re.I), "separate form"),
    (re.compile(r"\badditional\s+circular\b", re.I), "additional circular"),
    (re.compile(r"\bcircular\s+(no\.?|number)\b", re.I), "referenced circular"),
    (re.compile(r"\bform\s+(no\.?|number)\b", re.I), "referenced form"),
)

# Scope wording that signals the audience is not the whole student body but is
# left incompletely specified.
_PARTIAL_SCOPE_PATTERN = re.compile(
    r"\b(eligible|selected|shortlisted|certain|some|specific|concerned|relevant|"
    r"final\s+year|first\s+year|second\s+year|third\s+year|those\s+who|students\s+who)\b",
    re.IGNORECASE,
)

_ALL_STUDENTS_PATTERN = re.compile(r"\ball\s+students\b", re.IGNORECASE)


def _evidence_missing(claim: EvidenceClaim) -> bool:
    return claim.evidence_status == "blocked"


def _evidence_unaligned(claim: EvidenceClaim) -> bool:
    return claim.evidence_status == "review_required"


def _iter_all_claims(output: ExtractionOutput) -> list[EvidenceClaim]:
    return [
        output.summary,
        *output.changes,
        *output.affected_groups,
        *output.deadlines,
        *output.actions,
        *output.conditions,
        *output.uncertainties,
    ]


# ---------------------------------------------------------------------------
# The Guardian
# ---------------------------------------------------------------------------


class Guardian:
    """Validates an extraction output and produces a :class:`GuardianReport`.

    The Guardian is deliberately stateless and side-effect free with respect to
    the source: it reads ``ExtractionOutput`` and the original/previous notice
    text and only records findings. Applying repairs is a separate, explicit
    step (:meth:`apply_repairs`) so nothing is rewritten silently.
    """

    def review(
        self,
        output: ExtractionOutput,
        *,
        source_text: str,
        previous_text: str | None = None,
    ) -> GuardianReport:
        report = GuardianReport()
        self._evidence_check(output, report)
        self._date_check(output, report)
        self._action_check(output, report)
        self._scope_check(output, report)
        self._comparison_check(output, report, previous_text=previous_text)
        self._missing_reference_check(output, report, source_text=source_text)
        return report

    # -- 1. Evidence check --------------------------------------------------
    def _evidence_check(self, output: ExtractionOutput, report: GuardianReport) -> None:
        """Every action, deadline, affected group, and change must have source
        evidence or an explicit uncertainty status. Missing evidence on a
        critical claim is a BLOCK; unaligned evidence is a WARN."""
        critical = {id(claim) for claim in [*output.actions, *output.deadlines, *output.affected_groups, *output.changes]}
        for claim in _iter_all_claims(output):
            if _evidence_missing(claim):
                if id(claim) in critical:
                    report.add(GuardianFinding(EVIDENCE_CHECK, GuardianState.BLOCK, claim.claim_id, "critical claim has no source evidence"))
                else:
                    report.add(GuardianFinding(EVIDENCE_CHECK, GuardianState.WARN, claim.claim_id, "claim has no source evidence"))
            elif _evidence_unaligned(claim):
                report.add(GuardianFinding(EVIDENCE_CHECK, GuardianState.WARN, claim.claim_id, "evidence could not be aligned to the source"))

    # -- 2. Date check ------------------------------------------------------
    def _date_check(self, output: ExtractionOutput, report: GuardianReport) -> None:
        """No invented date/time. Reject invalid dates and conflicting fields.
        Preserve ambiguous wording. Flag missing timezone when a time is given."""
        for deadline in output.deadlines:
            self._check_one_deadline(deadline, report)
        for action in output.actions:
            self._check_action_dates(action, report)

    def _check_one_deadline(self, deadline: Deadline, report: GuardianReport) -> None:
        text = deadline.original_text or ""

        # Invented date: a normalized date exists but the notice never stated an
        # explicit date. This is the model deriving/inventing a value.
        if deadline.normalized_date is not None and not deadline.is_explicit:
            report.add(
                GuardianFinding(
                    DATE_CHECK, GuardianState.REPAIR, deadline.claim_id,
                    "normalized date is not explicitly supported by the notice; drop the invented date",
                    repair_field="normalized_date",
                )
            )

        # Relative/ambiguous wording that was resolved to a concrete date is an
        # invented date. Preserve the ambiguous wording (original_text is never
        # touched); only the derived date is unsafe.
        if deadline.normalized_date is not None and _RELATIVE_DATE_PATTERN.search(text):
            report.add(
                GuardianFinding(
                    DATE_CHECK, GuardianState.REPAIR, deadline.claim_id,
                    "relative/ambiguous date wording was resolved to a concrete date without a reliable reference; drop the invented date",
                    repair_field="normalized_date",
                )
            )

        # Invented time: a time exists but the notice text shows no time token.
        if deadline.normalized_time is not None and not _text_mentions_time(text):
            report.add(
                GuardianFinding(
                    DATE_CHECK, GuardianState.REPAIR, deadline.claim_id,
                    "normalized time is not present in the notice text; drop the invented time",
                    repair_field="normalized_time",
                )
            )

        # Missing timezone when a time is present and timezone matters.
        if deadline.normalized_time is not None and not deadline.timezone:
            report.add(
                GuardianFinding(
                    DATE_CHECK, GuardianState.WARN, deadline.claim_id,
                    "a time is given without a timezone",
                )
            )

        # Ambiguous wording with no concrete date resolved: preserve it, but
        # surface it as incomplete so it is not published as verified.
        if deadline.normalized_date is None and _RELATIVE_DATE_PATTERN.search(text):
            report.add(
                GuardianFinding(
                    DATE_CHECK, GuardianState.WARN, deadline.claim_id,
                    "date wording is ambiguous and left unresolved",
                )
            )

    def _check_action_dates(self, action: Action, report: GuardianReport) -> None:
        # Invented time on an action without any time token in its evidence.
        if action.due_time is not None and not _text_mentions_time(action.action_text or "") and not _text_mentions_time(action.evidence_text or ""):
            report.add(
                GuardianFinding(
                    DATE_CHECK, GuardianState.REPAIR, action.claim_id,
                    "action due time is not present in the notice text; drop the invented time",
                    repair_field="due_time",
                )
            )
        if action.due_time is not None and not action.timezone:
            report.add(
                GuardianFinding(
                    DATE_CHECK, GuardianState.WARN, action.claim_id,
                    "action has a due time without a timezone",
                )
            )

    # -- 3. Action check ----------------------------------------------------
    def _action_check(self, output: ExtractionOutput, report: GuardianReport) -> None:
        """Verify action evidence and mandatory classification. Preserve
        advisory/conditional language. Reject unsupported mandatory claims."""
        for action in output.actions:
            status = (action.mandatory_status or "").strip().lower()
            is_marked_mandatory = action.action_type == "mandatory"
            status_supports_mandatory = any(token in status for token in _MANDATORY_STATUS_TOKENS)

            if is_marked_mandatory and not status_supports_mandatory:
                # An action is presented as mandatory but nothing supports the
                # "must" claim. This is a critical, potentially harmful claim.
                report.add(
                    GuardianFinding(
                        ACTION_CHECK, GuardianState.BLOCK, action.claim_id,
                        f"action classified mandatory but mandatory_status '{action.mandatory_status}' does not support a required action",
                    )
                )

            # A mandatory action whose evidence text uses only advisory language
            # ("may", "optional", "encouraged") is an unsupported mandatory claim.
            if is_marked_mandatory and _text_is_advisory(action.evidence_text or action.action_text or ""):
                report.add(
                    GuardianFinding(
                        ACTION_CHECK, GuardianState.BLOCK, action.claim_id,
                        "action classified mandatory but its evidence uses advisory/optional language",
                    )
                )

            # Advisory/conditional actions that were promoted to a required
            # status: the classification contradicts itself. Warn (do not block)
            # so the advisory wording is preserved but flagged.
            if action.action_type in _ADVISORY_ACTION_TYPES and status_supports_mandatory:
                report.add(
                    GuardianFinding(
                        ACTION_CHECK, GuardianState.WARN, action.claim_id,
                        f"{action.action_type} action carries a mandatory status '{action.mandatory_status}'",
                    )
                )

    # -- 4. Scope check -----------------------------------------------------
    def _scope_check(self, output: ExtractionOutput, report: GuardianReport) -> None:
        """Verify the affected audience. Do not assume all students are
        affected. Flag incomplete eligibility."""
        source_all_students = _ALL_STUDENTS_PATTERN.search(output.summary.evidence_text or "") is not None
        for group in output.affected_groups:
            value = f"{group.group_type} {group.value}".strip()
            evidence = group.evidence_text or ""

            # The extraction says "all students" but the evidence does not.
            if _ALL_STUDENTS_PATTERN.search(value) and not _ALL_STUDENTS_PATTERN.search(evidence) and not source_all_students:
                report.add(
                    GuardianFinding(
                        SCOPE_CHECK, GuardianState.BLOCK, group.claim_id,
                        "audience broadened to 'all students' without supporting evidence",
                    )
                )
                continue

            # Partial/eligibility-restricted audience that is incompletely
            # specified: publish only with a review flag.
            if _PARTIAL_SCOPE_PATTERN.search(evidence) or _PARTIAL_SCOPE_PATTERN.search(value):
                report.add(
                    GuardianFinding(
                        SCOPE_CHECK, GuardianState.WARN, group.claim_id,
                        "affected audience is eligibility-restricted and may be incompletely specified",
                    )
                )

    # -- 5. Comparison check ------------------------------------------------
    def _comparison_check(self, output: ExtractionOutput, report: GuardianReport, *, previous_text: str | None) -> None:
        """One notice alone cannot establish a historical change. Two notices
        require a reliable version comparison. Flag uncertain changes."""
        if not output.changes:
            return
        if previous_text is None or not previous_text.strip():
            # A change was reported with only a single notice: cannot be
            # established. Block it from being published as a verified change.
            for change in output.changes:
                report.add(
                    GuardianFinding(
                        COMPARISON_CHECK, GuardianState.BLOCK, change.claim_id,
                        "a change was reported without a previous notice to compare against",
                    )
                )
            return

        # Two notices present: require that the change is grounded in a reliable
        # comparison (old value present in the previous text, new value present
        # in the current source evidence).
        for change in output.changes:
            self._check_one_change(change, report, previous_text=previous_text)

    def _check_one_change(self, change: Change, report: GuardianReport, *, previous_text: str) -> None:
        old_supported = change.old_value is None or (change.old_value.strip() and change.old_value.strip() in previous_text)
        # new_value support is proxied by the claim's own evidence alignment
        # (already computed by the normalizer against the current source).
        new_supported = change.new_value is None or change.evidence_status == "aligned"

        if not old_supported and not new_supported:
            report.add(
                GuardianFinding(
                    COMPARISON_CHECK, GuardianState.BLOCK, change.claim_id,
                    "reported change is not supported by either the previous or the current notice",
                )
            )
        elif not old_supported:
            report.add(
                GuardianFinding(
                    COMPARISON_CHECK, GuardianState.WARN, change.claim_id,
                    "old value of the change is not found in the previous notice",
                )
            )
        elif not new_supported:
            report.add(
                GuardianFinding(
                    COMPARISON_CHECK, GuardianState.WARN, change.claim_id,
                    "new value of the change could not be aligned to the current notice",
                )
            )

    # -- 6. Missing reference check -----------------------------------------
    def _missing_reference_check(self, output: ExtractionOutput, report: GuardianReport, *, source_text: str) -> None:
        """If the notice mentions an attached document, external guideline,
        separate form, or additional circular, flag it as a missing reference
        because that content is unavailable to the pipeline."""
        seen: set[str] = set()
        for pattern, label in _MISSING_REFERENCE_PATTERNS:
            match = pattern.search(source_text)
            if match and label not in seen:
                seen.add(label)
                report.add(
                    GuardianFinding(
                        MISSING_REFERENCE_CHECK, GuardianState.WARN, "notice",
                        f"notice references an unavailable {label}: '{match.group(0).strip()}'",
                    )
                )

    # -- Repairs ------------------------------------------------------------
    @staticmethod
    def apply_repairs(output: ExtractionOutput, report: GuardianReport) -> None:
        """Apply the report's repairs in place.

        Only ever clears unsupported derived values (invented dates/times).
        Never edits quoted evidence text or original wording. This is the only
        mutation the Guardian performs, and it only removes fabricated data.
        """
        by_id: dict[str, list[EvidenceClaim]] = {}
        for claim in _iter_all_claims(output):
            by_id.setdefault(claim.claim_id, []).append(claim)
        for claim_id, fields in report.repairs.items():
            for claim in by_id.get(claim_id, []):
                for field_name in fields:
                    if hasattr(claim, field_name):
                        setattr(claim, field_name, None)


def _text_mentions_time(text: str) -> bool:
    return bool(re.search(r"\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s*(am|pm|a\.m\.|p\.m\.)\b|\b(noon|midnight|hours?|hrs)\b", text, re.IGNORECASE))


def _text_is_advisory(text: str) -> bool:
    return bool(re.search(r"\b(may|might|optional|encouraged|recommended|advised|can|could|if\s+you\s+wish|at\s+your\s+discretion)\b", text, re.IGNORECASE))
