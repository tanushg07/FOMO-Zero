from fomo_zero.models import Notice

SYSTEM_INSTRUCTIONS = """Extract only facts supported by the notice text.
Never invent facts, dates, times, groups, mandatory actions, or changes.
Preserve conditional wording. Use null or [] when the notice does not provide a value.
Every claim must quote source evidence and include character offsets when possible.
Only report changes when a previous notice is supplied; otherwise return an empty changes list.
Return JSON only, matching the supplied schema. Do not use today's date.
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
