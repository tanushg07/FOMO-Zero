# FOMO-Zero

FOMO-Zero helps college students stop missing important deadlines and required actions buried inside college notices.

## Core Features
* Short summary of long notices.
* What changed, when supported.
* Who is affected.
* Important dates.
* Required actions.
* Evidence from the original notice.
* Uncertainty and review flags.

## Backend ingestion

Start the API with:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
uvicorn fomo_zero.api:app --reload
```

Pasted text uses JSON:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/notices `
	-ContentType "application/json" `
	-Body '{"title":"Exam notice","text":"Exam on 2026-10-01."}'
```

Documents use multipart upload:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/notices -F "file=@notice.pdf"
```

The API supports `TXT`, `PDF`, and `DOCX`. PDF uploads with no or insufficient selectable text return `ocr_needed`; no OCR is attempted. The default input limit is 10 MiB.


Video Link: https://drive.google.com/file/d/1An92dnR1HN2BznouUEYSQYktDbRqKG2i/view?usp=drive_link
