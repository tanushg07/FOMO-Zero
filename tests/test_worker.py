"""End-to-end tests for the notice-processing worker (the hook's command).

These exercise the full automation target: drop a notice file -> ingest text ->
extract -> evidence alignment -> Guardian validation -> save to SQLite -> mark
review-required items -> result visible via the same store the API serves.

They also verify the safety requirements: idempotency, no duplicate jobs, no
auto-publication of unsupported claims, and safe degradation with no API key.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select

from fomo_zero.ai.extractor import NoticeExtractor
from fomo_zero.ai.provider import NullProvider, ProviderResponse, build_provider
from fomo_zero.models import ActionItem, ChangeRecord, ExtractionRecord, Notice
from fomo_zero.worker import NoticeWorker

VALID_NOTICE = (
    "The submission deadline is 2026-10-01. Students must submit the completed form."
)


# ---------------------------------------------------------------------------
# Stub provider (mirrors the pattern in tests/test_extraction.py)
# ---------------------------------------------------------------------------


def _metadata():
    return {
        "provider_name": "stub",
        "model_name": "stub-model",
        "extracted_at": datetime.now(UTC).isoformat(),
        "source_text_sha256": "replaced-by-engine",
        "attempt_count": 1,
    }


def _valid_payload():
    return {
        "summary": {"claim_id": "summary-1", "text": "A form is due.", "evidence_text": "Students must submit the completed form."},
        "changes": [],
        "affected_groups": [],
        "deadlines": [{
            "claim_id": "deadline-1",
            "description": "Submission deadline",
            "original_text": "The submission deadline is 2026-10-01.",
            "normalized_date": "2026-10-01",
            "date_precision": "day",
            "is_explicit": True,
            "evidence_text": "The submission deadline is 2026-10-01.",
        }],
        "actions": [{
            "claim_id": "action-1",
            "action_text": "Students must submit the completed form.",
            "action_type": "mandatory",
            "mandatory_status": "required",
            "evidence_text": "Students must submit the completed form.",
        }],
        "conditions": [],
        "uncertainties": [],
        "metadata": _metadata(),
        "validation_status": "review_required",
    }


def _blocked_payload():
    # Fabricated mandatory action whose status does not support "required".
    payload = _valid_payload()
    payload["actions"][0]["mandatory_status"] = "optional"
    return payload


class StubProvider:
    provider_name = "stub"
    model_name = "stub-model"

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self._i = 0

    def complete(self, prompt):
        payload = self._payloads[min(self._i, len(self._payloads) - 1)]
        self._i += 1
        return ProviderResponse(json.dumps(payload), self.provider_name, self.model_name)


def make_worker(tmp_path, payloads):
    url = f"sqlite:///{tmp_path / 'worker.db'}"
    extractor = NoticeExtractor(StubProvider(payloads))
    return NoticeWorker(url, extractor=extractor), url


def write_notice(tmp_path, name="notice.txt", text=VALID_NOTICE):
    inbox = tmp_path / "notices_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / name
    path.write_text(text, encoding="utf-8")
    return inbox, path


# ---------------------------------------------------------------------------
# End-to-end: drop file -> validated result in SQLite
# ---------------------------------------------------------------------------


def test_valid_notice_processed_end_to_end(tmp_path):
    worker, _ = make_worker(tmp_path, [_valid_payload()])
    inbox, _ = write_notice(tmp_path)
    try:
        results = worker.process_inbox(inbox)
        assert [r.status for r in results] == ["complete"]
        notice_id = results[0].notice_id
        with worker._session_factory() as session:  # noqa: SLF001 - test introspection
            notice = session.get(Notice, notice_id)
            assert notice.processing_status == "complete"
            assert notice.validation_status == "validated"
            # The validated action is published (visible to the API/frontend).
            action = session.scalar(select(ActionItem).where(ActionItem.notice_id == notice_id))
            assert action.action_type == "mandatory"
            assert session.scalar(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice_id)) is not None
        # File was moved out of the watched folder (no re-trigger loop).
        assert not any(p.suffix == ".txt" for p in inbox.iterdir() if p.is_file())
        assert (inbox / "processed" / "notice.txt").exists()
    finally:
        worker.dispose()


def test_blocked_notice_is_flagged_not_published(tmp_path):
    worker, _ = make_worker(tmp_path, [_blocked_payload()])
    inbox, _ = write_notice(tmp_path)
    try:
        results = worker.process_inbox(inbox)
        assert results[0].status == "blocked"
        notice_id = results[0].notice_id
        with worker._session_factory() as session:  # noqa: SLF001
            notice = session.get(Notice, notice_id)
            assert notice.processing_status == "needs_review"
            assert notice.validation_status == "blocked"
            # The unsupported mandatory action is NOT published as verified.
            assert session.scalar(select(ActionItem).where(ActionItem.notice_id == notice_id)) is None
            assert session.scalar(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice_id)) is None
        # A blocked notice is still archived (manual review remains available).
        assert (inbox / "processed" / "notice.txt").exists()
    finally:
        worker.dispose()


def test_needs_review_notice_is_kept_for_manual_review(tmp_path):
    # A change reported without a previous notice -> Guardian blocks that claim,
    # so the notice is held. Use an ambiguous date to force review_required.
    payload = _valid_payload()
    payload["deadlines"][0]["original_text"] = "The deadline is next Friday."
    payload["deadlines"][0]["is_explicit"] = False
    payload["deadlines"][0]["evidence_text"] = "The deadline is next Friday."
    worker, _ = make_worker(tmp_path, [payload])
    inbox, _ = write_notice(tmp_path, text="The deadline is next Friday. Students must submit the completed form.")
    try:
        results = worker.process_inbox(inbox)
        assert results[0].status == "needs_review"
        with worker._session_factory() as session:  # noqa: SLF001
            notice = session.get(Notice, results[0].notice_id)
            assert notice.processing_status == "needs_review"
            assert notice.validation_status == "review_required"
    finally:
        worker.dispose()


# ---------------------------------------------------------------------------
# Idempotency and duplicate-job prevention
# ---------------------------------------------------------------------------


def test_identical_notice_content_is_idempotent(tmp_path):
    worker, _ = make_worker(tmp_path, [_valid_payload(), _valid_payload()])
    inbox, _ = write_notice(tmp_path, name="first.txt")
    try:
        first = worker.process_inbox(inbox)
        assert first[0].status == "complete"
        first_id = first[0].notice_id

        # Drop the SAME content again under a different filename.
        write_notice(tmp_path, name="second.txt")
        second = worker.process_inbox(inbox)
        assert second[0].status == "skipped_duplicate"
        assert second[0].notice_id == first_id

        with worker._session_factory() as session:  # noqa: SLF001
            notices = session.scalars(select(Notice)).all()
            assert len(notices) == 1  # no duplicate notice row
            actions = session.scalars(select(ActionItem)).all()
            assert len(actions) == 1  # no duplicate extracted records
    finally:
        worker.dispose()


def test_reprocessing_same_notice_id_is_skipped(tmp_path):
    worker, _ = make_worker(tmp_path, [_valid_payload(), _valid_payload()])
    inbox, _ = write_notice(tmp_path)
    try:
        first = worker.process_inbox(inbox)
        notice_id = first[0].notice_id
        again = worker.process_notice_id(notice_id)
        assert again.status == "skipped_duplicate"
    finally:
        worker.dispose()


def test_file_lock_prevents_duplicate_job(tmp_path):
    from fomo_zero.worker import LockError, _FileLock

    worker, _ = make_worker(tmp_path, [_valid_payload()])
    inbox, path = write_notice(tmp_path)
    try:
        # Hold the lock, then a concurrent process_file must skip (no dup job).
        with _FileLock(path):
            result = worker.process_file(path)
        assert result.status == "skipped_duplicate"
        # Lock releases cleanly and a subsequent run can proceed.
        try:
            with _FileLock(path):
                pass
        except LockError:
            raise AssertionError("lock should have been released")
    finally:
        worker.dispose()


# ---------------------------------------------------------------------------
# Bounded processing and unsupported files
# ---------------------------------------------------------------------------


def test_unsupported_file_is_skipped(tmp_path):
    worker, _ = make_worker(tmp_path, [_valid_payload()])
    inbox = tmp_path / "notices_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "notes.md").write_text("not a notice", encoding="utf-8")
    try:
        results = worker.process_inbox(inbox)
        # .md is not a supported notice type and is left untouched.
        assert results == []
        assert (inbox / "notes.md").exists()
    finally:
        worker.dispose()


def test_empty_or_unreadable_file_marked_failed(tmp_path):
    worker, _ = make_worker(tmp_path, [_valid_payload()])
    inbox, _ = write_notice(tmp_path, name="empty.txt", text="")
    try:
        results = worker.process_inbox(inbox)
        assert results[0].status == "failed"
        assert (inbox / "failed" / "empty.txt").exists()
    finally:
        worker.dispose()


# ---------------------------------------------------------------------------
# Safe provider fallback (no key -> no crash, no leak, review_required)
# ---------------------------------------------------------------------------


class ExplodingProvider:
    """Simulates an unexpected provider/API error (e.g. model-not-found 404)."""

    provider_name = "boom"
    model_name = "boom-model"

    def complete(self, prompt):
        raise RuntimeError("secret-bearing provider failure that must not leak")


def test_unexpected_provider_error_holds_for_review_without_crashing(tmp_path):
    url = f"sqlite:///{tmp_path / 'boom.db'}"
    worker = NoticeWorker(url, extractor=NoticeExtractor(ExplodingProvider(), max_retries=0))
    inbox, _ = write_notice(tmp_path)
    try:
        # The hook command must not raise; it degrades to needs_review.
        results = worker.process_inbox(inbox)
        assert results[0].status == "needs_review"
        assert "provider_error:RuntimeError" in results[0].detail
        with worker._session_factory() as session:  # noqa: SLF001
            notice = session.get(Notice, results[0].notice_id)
            assert notice.processing_status == "needs_review"
            assert notice.validation_status == "review_required"
            # Nothing was published as verified.
            assert session.scalar(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice.id)) is None
    finally:
        worker.dispose()


def test_build_provider_falls_back_without_key(monkeypatch):
    # use_dotenv=False so a real .env on the machine can't resurrect the key.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    provider = build_provider(use_dotenv=False)
    assert isinstance(provider, NullProvider)


def test_build_provider_falls_back_on_placeholder(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "PASTE_YOUR_GROQ_API_KEY_HERE")
    assert isinstance(build_provider(use_dotenv=False), NullProvider)


def test_null_provider_routes_to_review(tmp_path):
    # Using the real NullProvider (no stub), a notice must never auto-publish.
    url = f"sqlite:///{tmp_path / 'null.db'}"
    worker = NoticeWorker(url, extractor=NoticeExtractor(NullProvider()))
    inbox, _ = write_notice(tmp_path)
    try:
        results = worker.process_inbox(inbox)
        assert results[0].status in {"needs_review", "blocked"}
        with worker._session_factory() as session:  # noqa: SLF001
            notice = session.get(Notice, results[0].notice_id)
            assert notice.validation_status in {"review_required", "blocked"}
            assert session.scalar(select(ExtractionRecord).where(ExtractionRecord.notice_id == notice.id)) is None
    finally:
        worker.dispose()
