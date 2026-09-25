"""Local notice-processing worker.

This is the command a Kiro Agent Hook invokes when a new notice file appears in
the inbox folder. It runs the full pipeline locally against the project SQLite
database:

    ingest file text -> create/find Notice -> extract -> evidence alignment
    -> Guardian validation -> save to SQLite -> mark review-required items.

Design guarantees (mapped to the automation safety requirements):

* No unsupported claim is auto-published: publication is gated by the Guardian,
  which only persists a fully validated extraction. Anything ambiguous,
  incomplete, or blocked is stored as ``needs_review``/``blocked`` and never as
  a verified action.
* No secrets are exposed: the worker never reads or logs API keys. Provider
  selection is delegated to :func:`build_provider`, which falls back safely.
* No duplicate processing jobs: a per-file lock file makes concurrent runs on
  the same file a no-op, and a content hash makes re-ingesting identical text a
  no-op.
* No infinite loops: the worker processes a bounded set of files once and exits.
  It writes only into the inbox's ``processed``/``failed`` subfolders and the
  database, never back into the watched folder, so it cannot re-trigger itself.
* Idempotent: notices are keyed by the SHA-256 of their extracted text; an
  already-processed notice is skipped.
* Manual review stays available: review-required and blocked notices are kept in
  the database with their status intact for a human to act on.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai.extractor import ExtractionError, NoticeExtractor
from .ai.provider import build_provider
from .db import create_engine, create_session_factory, init_db
from .ingestion import IngestionError, extract_notice_text
from .models import Notice
from .repositories import create_notice
from .schemas import NoticeCreate

logger = logging.getLogger("fomo_zero.worker")

DEFAULT_DATABASE_URL = "sqlite:///fomo_zero.db"
DEFAULT_INBOX = "notices_inbox"
SUPPORTED_SUFFIXES = {".txt", ".pdf", ".docx"}
MAX_BATCH = 100  # bound the number of files processed in a single run

# Statuses that mean a notice already has (or is having) its pipeline run.
_ALREADY_PROCESSED = {"processing", "complete", "needs_review", "blocked"}


@dataclass
class ProcessResult:
    filename: str
    notice_id: str | None
    status: str  # one of: complete, needs_review, blocked, skipped_duplicate, failed, unsupported
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"complete", "needs_review", "blocked", "skipped_duplicate"}


def _configure_logging(verbose: bool = False) -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s fomo-worker %(levelname)s %(message)s",
        stream=sys.stderr,
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_notice_by_text_hash(session: Session, text_hash: str) -> Notice | None:
    # We store the hash comparison by recomputing on candidate rows. The set of
    # notices is small for this app; for scale this would be a dedicated column.
    for notice in session.scalars(select(Notice)):
        if _sha256(notice.original_text) == text_hash:
            return notice
    return None


class LockError(Exception):
    pass


class _FileLock:
    """A best-effort exclusive lock via atomic marker-file creation.

    Prevents two concurrent worker runs from processing the same file (i.e. no
    duplicate jobs). ``O_CREAT | O_EXCL`` fails if the marker already exists.
    """

    def __init__(self, target: Path):
        self._marker = target.with_suffix(target.suffix + ".lock")
        self._fd: int | None = None

    def __enter__(self) -> "_FileLock":
        try:
            self._fd = os.open(self._marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise LockError(f"another worker is already processing {self._marker.stem}") from exc
        return self

    def __exit__(self, *_exc) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self._marker.unlink()
        except FileNotFoundError:
            pass


class NoticeWorker:
    def __init__(self, database_url: str = DEFAULT_DATABASE_URL, *, extractor: NoticeExtractor | None = None):
        self._engine = create_engine(database_url)
        init_db(self._engine)
        self._session_factory = create_session_factory(self._engine)
        # Provider selection is safe-by-default and never touches/logs secrets.
        self._extractor = extractor or NoticeExtractor(build_provider())

    def dispose(self) -> None:
        self._engine.dispose()

    # -- single file --------------------------------------------------------
    def process_file(self, path: Path) -> ProcessResult:
        path = Path(path)
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            logger.info("skip unsupported file %s", path.name)
            return ProcessResult(path.name, None, "unsupported", "unsupported file type")

        try:
            with _FileLock(path):
                return self._process_locked(path)
        except LockError as exc:
            # Another job holds the lock: do not start a duplicate job.
            logger.info("skip locked file %s (%s)", path.name, exc)
            return ProcessResult(path.name, None, "skipped_duplicate", str(exc))

    def _process_locked(self, path: Path) -> ProcessResult:
        try:
            content = path.read_bytes()
            extracted = extract_notice_text(content, path.name)
        except IngestionError as exc:
            logger.warning("ingestion failed for %s: %s", path.name, exc.status)
            return ProcessResult(path.name, None, "failed", f"ingestion:{exc.status}")

        text_hash = _sha256(extracted.text)
        with self._session_factory() as session:
            existing = _find_notice_by_text_hash(session, text_hash)
            if existing is not None and existing.processing_status in _ALREADY_PROCESSED:
                # Idempotency: identical notice text already handled.
                logger.info("skip duplicate notice %s status=%s sha=%s", existing.id, existing.processing_status, text_hash[:12])
                return ProcessResult(path.name, existing.id, "skipped_duplicate", f"already {existing.processing_status}")

            notice = existing or create_notice(
                session,
                NoticeCreate(
                    title=path.stem,
                    original_text=extracted.text,
                    source_filename=extracted.source_filename,
                    processing_status="ready",
                ),
            )
            notice_id = notice.id

        return self._run_pipeline(notice_id, path.name, text_hash)

    def process_notice_id(self, notice_id: str) -> ProcessResult:
        """Run the pipeline for an existing notice row (e.g. created via the API)."""
        with self._session_factory() as session:
            notice = session.get(Notice, notice_id)
            if notice is None:
                return ProcessResult(notice_id, None, "failed", "notice not found")
            if notice.processing_status in {"processing", "complete", "needs_review", "blocked"}:
                return ProcessResult(notice_id, notice_id, "skipped_duplicate", f"already {notice.processing_status}")
            text_hash = _sha256(notice.original_text)
        return self._run_pipeline(notice_id, notice_id, text_hash)

    def _run_pipeline(self, notice_id: str, label: str, text_hash: str) -> ProcessResult:
        with self._session_factory() as session:
            try:
                output = self._extractor.extract(session, notice_id)
            except ExtractionError as exc:
                # Guardian/extractor already marked the notice failed/blocked.
                logger.warning("extraction error for notice %s sha=%s: %s", notice_id, text_hash[:12], exc)
                return ProcessResult(label, notice_id, "blocked", "extraction_failed")
            except LookupError:
                return ProcessResult(label, None, "failed", "notice disappeared")

        status_map = {"validated": "complete", "review_required": "needs_review", "blocked": "blocked"}
        status = status_map.get(output.validation_status, "needs_review")
        review_flags = len(self._extractor.last_report.problems()) if self._extractor.last_report else 0
        logger.info(
            "processed notice %s sha=%s status=%s review_flags=%d",
            notice_id, text_hash[:12], status, review_flags,
        )
        return ProcessResult(label, notice_id, status, f"{review_flags} review flag(s)")

    # -- batch / folder -----------------------------------------------------
    def process_inbox(self, inbox: Path) -> list[ProcessResult]:
        inbox = Path(inbox)
        inbox.mkdir(parents=True, exist_ok=True)
        processed_dir = inbox / "processed"
        failed_dir = inbox / "failed"

        results: list[ProcessResult] = []
        files = sorted(
            p for p in inbox.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
        )[:MAX_BATCH]
        for path in files:
            result = self.process_file(path)
            results.append(result)
            # Move the file out of the watched folder so it is never re-processed
            # and cannot re-trigger a file hook (no infinite loop).
            destination_dir = processed_dir if result.ok else failed_dir
            _move_out(path, destination_dir)
        return results


def _move_out(path: Path, destination_dir: Path) -> None:
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        target = destination_dir / path.name
        counter = 1
        while target.exists():
            target = destination_dir / f"{path.stem}.{counter}{path.suffix}"
            counter += 1
        path.replace(target)
    except OSError:
        logger.warning("could not move %s out of the inbox", path.name)


def _resolve_target(args: argparse.Namespace) -> Path | None:
    """Resolve a single file target from a hook stdin payload or --file."""
    if args.file:
        return Path(args.file)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fomo-worker", description="Process college notices into validated, review-flagged results.")
    parser.add_argument("--file", help="Process a single notice file.")
    parser.add_argument("--inbox", default=DEFAULT_INBOX, help="Folder to drain of notice files (default: notices_inbox).")
    parser.add_argument("--notice-id", help="Process an existing notice row by id.")
    parser.add_argument("--database-url", default=os.getenv("FOMO_DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    worker = NoticeWorker(args.database_url)
    try:
        if args.notice_id:
            results = [worker.process_notice_id(args.notice_id)]
        elif args.file:
            target = _resolve_target(args)
            results = [worker.process_file(target)] if target else []
        else:
            results = worker.process_inbox(Path(args.inbox))
    finally:
        worker.dispose()

    for result in results:
        logger.info("result file=%s notice=%s status=%s (%s)", result.filename, result.notice_id, result.status, result.detail)

    # Exit non-zero only on a hard failure so the hook surfaces a warning; a
    # notice that legitimately needs review is a success from the pipeline's view.
    failed = [r for r in results if r.status == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
