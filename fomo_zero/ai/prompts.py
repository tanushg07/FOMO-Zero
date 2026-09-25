from fomo_zero.models import Notice

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
"""
