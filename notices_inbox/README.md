# Notice inbox

Drop supported notice files here to have them processed automatically:

- `.txt`, `.pdf`, `.docx`

## How processing runs

A Kiro Agent Hook (`.kiro/hooks/notice-processing.json`) watches this folder.
When the agent adds a file here, the hook runs the local worker:

```
python -m fomo_zero.worker --file <path>
```

You can also run the worker manually to drain the whole folder:

```powershell
.\.venv\Scripts\python.exe -m fomo_zero.worker --inbox notices_inbox
```

After processing, each file is moved into `processed/` (on success or when a
notice needs review) or `failed/` (on a hard ingestion/read failure) so it is
never processed twice and cannot re-trigger the hook.

## Important limitation

Kiro file-triggered hooks (`PostFileCreate` / `PostFileSave`) fire **only for
files the Kiro agent creates or saves** — not for files added manually in the OS
file explorer, and not for notices created through the HTTP API. For those
paths, run the worker manually (command above) or wire it into your ingestion
flow. The `SessionStart` hook drains any backlog left in this folder when a Kiro
session begins.

## Review and safety

The worker never auto-publishes unsupported claims. The Guardian validation
layer decides each notice's status:

- `complete` — validated, safe to show as verified.
- `needs_review` — ambiguous/incomplete; kept for manual review.
- `blocked` — unsupported/critical; kept out of verified results.

No API keys are read or logged by the worker. If no model is configured, it
falls back to a safe mode that routes every notice to `needs_review`.
