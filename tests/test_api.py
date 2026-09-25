from io import BytesIO

import fitz
from docx import Document
from fastapi.testclient import TestClient

from fomo_zero.api import create_app


def pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def client(tmp_path):
    return TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}"))


def test_valid_pasted_notice_and_persistence(tmp_path):
    with client(tmp_path) as api:
        response = api.post("/api/notices", json={"title": "Exam notice", "text": "Exam on 2026-10-01."})
        assert response.status_code == 201
        notice_id = response.json()["id"]
        assert api.get(f"/api/notices/{notice_id}").json()["original_text"] == "Exam on 2026-10-01."
        assert len(api.get("/api/notices").json()["items"]) == 1


def test_empty_input_is_rejected(tmp_path):
    with client(tmp_path) as api:
        response = api.post("/api/notices", json={"text": "   "})
        assert response.status_code == 422


def test_pdf_and_docx_extraction(tmp_path):
    with client(tmp_path) as api:
        pdf_response = api.post("/api/notices", files={"file": ("notice.pdf", pdf_bytes("PDF notice with enough selectable text."), "application/pdf")})
        docx_response = api.post("/api/notices", files={"file": ("notice.docx", docx_bytes("DOCX notice paragraph."), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert pdf_response.status_code == 201
        assert docx_response.status_code == 201


def test_empty_pdf_returns_ocr_needed(tmp_path):
    document = fitz.open()
    document.new_page()
    empty_pdf = document.tobytes()
    document.close()
    with client(tmp_path) as api:
        response = api.post("/api/notices", files={"file": ("scan.pdf", empty_pdf, "application/pdf")})
        assert response.status_code == 422
        assert response.json()["error"] == "ocr_needed"


def test_unsupported_extension(tmp_path):
    with client(tmp_path) as api:
        response = api.post("/api/notices", files={"file": ("notice.exe", b"data", "application/octet-stream")})
        assert response.status_code == 415
        assert response.json()["error"] == "unsupported_file_type"


def test_missing_notice_id(tmp_path):
    with client(tmp_path) as api:
        response = api.get("/api/notices/missing")
        assert response.status_code == 404
        assert response.json()["detail"] == "Notice not found"


def test_delete_is_safe(tmp_path):
    with client(tmp_path) as api:
        notice_id = api.post("/api/notices", json={"text": "A notice."}).json()["id"]
        assert api.delete(f"/api/notices/{notice_id}").status_code == 204
        assert api.get(f"/api/notices/{notice_id}").status_code == 404
        assert api.delete(f"/api/notices/{notice_id}").status_code == 404


def test_file_size_limit(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'api.db'}", max_input_bytes=10)) as api:
        response = api.post("/api/notices", files={"file": ("notice.txt", b"too large notice", "text/plain")})
        assert response.status_code == 413
        assert response.json()["error"] == "file_too_large"
