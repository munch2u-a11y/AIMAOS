import io
import importlib.util
from pathlib import Path
import zipfile

import pytest

from core.document_text import extract_document_text, validate_upload_content
from core.security import SecurityValidationError


def test_text_validation_rejects_binary_disguised_as_text():
    with pytest.raises(SecurityValidationError):
        validate_upload_content("notes.txt", b"hello\x00binary")


def test_signature_validation_rejects_mismatched_pdf():
    with pytest.raises(SecurityValidationError):
        validate_upload_content("filing.pdf", b"not a pdf")
    validate_upload_content("filing.pdf", b"%PDF-1.7\nsynthetic")


def test_office_archive_rejects_unsafe_member_path():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../outside.xml", "unsafe")
    with pytest.raises(SecurityValidationError):
        validate_upload_content("filing.docx", buffer.getvalue())


def test_local_text_extraction_is_bounded(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("a" * 120_000, encoding="utf-8")
    result = extract_document_text(str(path))
    assert result.status == "extracted"
    assert len(result.text) == 100_000
    assert "truncated" in result.detail


def test_unsupported_binary_format_requires_manual_review(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = extract_document_text(str(path))
    assert result.status == "manual_review_required"


def test_document_engine_renders_a_real_bundled_template(tmp_path):
    pytest.importorskip("docxtpl")
    root = Path(__file__).resolve().parents[2]
    engine_path = root / "starter_packs/document_heavy/Alix-AI/business/document_engine.py"
    spec = importlib.util.spec_from_file_location("test_document_engine", engine_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = root / "starter_packs/document_heavy/Alix-AI/templates/form_12_982_a/template.docx"
    output = tmp_path / "synthetic_draft.docx"
    context = {
        "client_name": "Synthetic Beta User",
        "county": "Test County",
        "circuit_number": "1",
        "case_number": "TEST-000",
        "client_address": "123 Test Street",
        "client_phone": "555-0100",
        "date_of_birth": "2000-01-01",
        "division": "Test",
        "client_email": "synthetic@example.invalid",
        "client_city_state_zip": "Test City, TS 00000",
        "new_name": "Synthetic Example",
    }
    result = module.DocumentEngine(str(template)).generate(context, str(output))
    assert output.is_file() and output.stat().st_size > 0
    assert result["status"] == "success"
    assert result["issues"]["unrendered_tags"] == []
