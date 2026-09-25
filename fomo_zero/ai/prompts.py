from fomo_zero.models import Notice

OUTPUT_TEMPLATE = """{
    "summary": {"claim_id": "summary-1", "text": "...", "evidence_text": "...", "evidence_start": 0, "evidence_end": 3, "evidence_status": "review_required"},
    "changes": [],
    "affected_groups": [],
    "deadlines": [{"claim_id": "deadline-1", "description": "...", "original_text": "...", "normalized_date": null, "normalized_time": null, "timezone": null, "date_precision": "day|month|unknown", "is_explicit": false, "evidence_text": "...", "evidence_start": 0, "evidence_end": 3, "evidence_status": "review_required"}],
    "actions": [{"claim_id": "action-1", "action_text": "...", "action_type": "mandatory|advisory|informational|conditional|unclear", "mandatory_status": "required|not_required|unclear", "due_date": null, "due_time": null, "timezone": null, "evidence_text": "...", "evidence_start": 0, "evidence_end": 3, "evidence_status": "review_required"}],
    "conditions": [],
    "uncertainties": [],
    "metadata": {"provider_name": "groq", "model_name": "...", "extracted_at": "2026-01-01T00:00:00Z", "source_text_sha256": "pending", "attempt_count": 1, "reference_date": null},
    "validation_status": "review_required"
}"""

SYSTEM_INSTRUCTIONS = """Extract only facts supported by the notice text.
Never invent facts, dates, times, groups, mandatory actions, or changes.
Preserve conditional, advisory, and ambiguous wording exactly; do not resolve it.
Use null or [] when the notice does not provide a value.
Every claim must quote source evidence and include character offsets when possible.
Do not classify an action as mandatory unless the notice explicitly requires it.
Do not broaden the audience to "all students" unless the notice says so.
Only fill normalized_date/normalized_time when the notice states an explicit date/time;
otherwise leave them null and keep is_explicit false.
Only report changes when a previous notice is supplied; otherwise return an empty changes list.
Return JSON only, matching the supplied schema. Do not use today's date.
A downstream Guardian will block unsupported claims, so fabricated values are never published.
For every claim, use the exact field names and include claim_id, evidence_text,
evidence_start, evidence_end, and evidence_status. Use validation_status exactly
as one of: validated, review_required, blocked. Use action_type exactly as one
of: mandatory, advisory, informational, conditional, unclear. Do not return a
summary string; summary must be an object with text and evidence fields.
"""


def build_extraction_prompt(notice: Notice, previous_text: str | None = None) -> str:
    previous_section = "No previous notice is available; changes must be empty."
    if previous_text is not None:
        previous_section = f"Previous notice text:\n{previous_text}"
    return f"""{SYSTEM_INSTRUCTIONS}

Notice title: {notice.title}
Notice text:
{notice.original_text}

{previous_section}

Return an object with keys: summary, changes, affected_groups, deadlines, actions,
conditions, uncertainties, metadata, validation_status.

Use this compact output template. Keep every object field, use null for missing
values, and use [] for empty collections:
{OUTPUT_TEMPLATE}
"""
