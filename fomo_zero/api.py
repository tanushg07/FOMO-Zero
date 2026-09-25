from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .api_schemas import IngestionErrorResponse, NoticeListResponse, NoticeResponse, NoticeTextRequest
from .db import create_engine, create_session_factory, init_db
from .ingestion import IngestionError, extract_notice_text, validate_size
from .models import Notice
from .repositories import create_notice, get_notice, list_notices, set_notice_processing_status
from .schemas import NoticeCreate
from .ai.extractor import ExtractionError, NoticeExtractor
from .ai.provider import build_provider

logger = logging.getLogger(__name__)
DEFAULT_MAX_INPUT_BYTES = 10 * 1024 * 1024


def create_app(database_url: str = "sqlite:///fomo_zero.db", max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES) -> FastAPI:
    engine = create_engine(database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="FOMO-Zero Backend", lifespan=lifespan)
    app.state.max_input_bytes = max_input_bytes

    def get_session():
        with session_factory() as session:
            yield session

    @app.exception_handler(IngestionError)
    async def ingestion_error_handler(_, exc: IngestionError):
        status_code = {
            "invalid_input": 422,
            "unsupported_file_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "file_too_large": 413,
            "ocr_needed": 422,
            "extraction_failed": 422,
        }.get(exc.status, 422)
        return JSONResponse(status_code=status_code, content=IngestionErrorResponse(error=exc.status, message=exc.message).model_dump())

    @app.post("/api/notices", response_model=NoticeResponse, status_code=status.HTTP_201_CREATED)
    async def create_notice_endpoint(request: Request, session: Session = Depends(get_session)):
        content_type = request.headers.get("content-type", "")
        text_request: NoticeTextRequest | None = None
        file = None
        title = None
        issuing_authority = None
        notice_date = None
        if content_type.startswith("application/json"):
            try:
                text_request = NoticeTextRequest.model_validate(await request.json())
            except (ValueError, TypeError) as exc:
                raise IngestionError("invalid_input", "Request JSON is invalid") from exc
        elif content_type.startswith("multipart/form-data"):
            form = await request.form()
            file = form.get("file")
            title = form.get("title")
            issuing_authority = form.get("issuing_authority")
            notice_date = form.get("notice_date")
            if file is None or not hasattr(file, "read"):
                raise IngestionError("invalid_input", "Provide a supported file")
        else:
            raise IngestionError("invalid_input", "Use application/json or multipart/form-data")

        if file is not None:
            content = await file.read(app.state.max_input_bytes + 1)
            validate_size(content, app.state.max_input_bytes)
            extracted = extract_notice_text(content, file.filename or "")
            notice_title = title or Path(file.filename or "Notice").stem
            parsed_date = notice_date
            source_filename = extracted.source_filename
            original_text = extracted.text
        else:
            source_filename = text_request.source_filename
            original_text = text_request.text
            notice_title = text_request.title or "Untitled notice"
            parsed_date = text_request.notice_date
            if len(original_text.encode("utf-8")) > app.state.max_input_bytes:
                raise IngestionError("file_too_large", f"Input exceeds the {app.state.max_input_bytes}-byte limit")

        try:
            data = NoticeCreate(
                title=notice_title,
                original_text=original_text,
                source_filename=source_filename,
                issuing_authority=issuing_authority or (text_request.issuing_authority if text_request else None),
                notice_date=parsed_date,
                processing_status="ready",
            )
            notice = create_notice(session, data)
            return NoticeResponse.from_model(notice)
        except ValueError as exc:
            raise IngestionError("invalid_input", "Notice metadata is invalid") from exc
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception("Database failure while saving notice")
            raise HTTPException(status_code=500, detail="Database failure while saving notice") from exc

    @app.get("/api/notices", response_model=NoticeListResponse)
    def list_notices_endpoint(limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0), session: Session = Depends(get_session)):
        try:
            notices = list_notices(session, limit=limit, offset=offset)
            return NoticeListResponse(items=[NoticeResponse.from_model(notice) for notice in notices], limit=limit, offset=offset)
        except SQLAlchemyError as exc:
            logger.exception("Database failure while listing notices")
            raise HTTPException(status_code=500, detail="Database failure while listing notices") from exc

    @app.get("/api/notices/{notice_id}", response_model=NoticeResponse)
    def get_notice_endpoint(notice_id: str, session: Session = Depends(get_session)):
        notice = get_notice(session, notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="Notice not found")
        return NoticeResponse.from_model(notice)

    @app.post("/api/notices/{notice_id}/extract", response_model=NoticeResponse)
    def extract_notice_endpoint(notice_id: str, session: Session = Depends(get_session)):
        if session.get(Notice, notice_id) is None:
            raise HTTPException(status_code=404, detail="Notice not found")
        try:
            NoticeExtractor(build_provider()).extract(session, notice_id)
        except ExtractionError:
            # The extractor has already recorded the safe failed status.
            logger.warning("notice extraction failed for %s", notice_id)
        except Exception as exc:  # noqa: BLE001 - API must not expose provider details
            session.rollback()
            set_notice_processing_status(session, notice_id, "needs_review", validation_status="review_required")
            logger.warning("unexpected notice extraction error: %s", type(exc).__name__)
        notice = get_notice(session, notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="Notice not found")
        return NoticeResponse.from_model(notice)

    @app.delete("/api/notices/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_notice_endpoint(notice_id: str, session: Session = Depends(get_session)):
        notice = session.get(Notice, notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="Notice not found")
        try:
            session.delete(notice)
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception("Database failure while deleting notice")
            raise HTTPException(status_code=500, detail="Database failure while deleting notice") from exc
        return None

    return app


app = create_app()
