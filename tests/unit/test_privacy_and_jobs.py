import threading

from core.db.office_sqlite import OfficeSQLite
from core.privacy import privacy_safe_tool_record, redact_sensitive


def test_sensitive_value_redaction():
    redacted = redact_sensitive("Email ada@example.com SSN 123-45-6789 card 4111 1111 1111 1111")
    assert "ada@example.com" not in redacted
    assert "123-45-6789" not in redacted
    assert "4111" not in redacted


def test_privacy_safe_record_has_digest_without_unredacted_output(monkeypatch):
    monkeypatch.setattr("core.privacy.raw_tool_logs_enabled", lambda: False)
    record = privacy_safe_tool_record("confidential text")
    assert record["output_chars"] == 17
    assert len(record["output_sha256"]) == 64
    assert "confidential" not in record["raw_output"]


def test_job_storage_lifecycle_and_interruption(tmp_path):
    db = OfficeSQLite(str(tmp_path / "office.sqlite"))
    db.create_job("job_1", "document", "Draft document")
    assert db.get_job("job_1")["status"] == "queued"
    db.update_job("job_1", status="completed", result={"file": "draft.docx"})
    assert db.get_job("job_1")["result"] == {"file": "draft.docx"}
    db.create_job("job_2", "assistant", "Question")
    db.interrupt_unfinished_jobs()
    assert db.get_job("job_2")["status"] == "interrupted"


def test_sqlite_handles_parallel_job_writes(tmp_path):
    db = OfficeSQLite(str(tmp_path / "office.sqlite"))

    def create(index):
        db.create_job(f"job_{index}", "test", f"Job {index}")

    threads = [threading.Thread(target=create, args=(index,)) for index in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(db.list_jobs(limit=20)) == 12
