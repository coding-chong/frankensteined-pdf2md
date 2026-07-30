"""Tests for the deterministic Chinese image-only OCR fixture."""

import hashlib
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import fitz
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_chinese_ocr_fixture.py"
SPEC = spec_from_file_location("generate_chinese_ocr_fixture", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
fixture = module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


def test_checked_in_fixture_is_image_only_and_matches_manifest():
    manifest_path = ROOT / "test_assets" / "chinese_scanned_ocr_test.json"
    pdf_path = ROOT / "test_assets" / "chinese_scanned_ocr_test.pdf"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["image_only"] is True
    assert manifest["pages"] == 2
    assert manifest["sha256"] == hashlib.sha256(pdf_path.read_bytes()).hexdigest().upper()
    document = fitz.open(pdf_path)
    try:
        assert document.page_count == manifest["pages"]
        assert all(not page.get_text("text").strip() for page in document)
    finally:
        document.close()


@pytest.mark.skipif(
    not any(path.is_file() for path in fixture.FONT_CANDIDATES),
    reason="Windows Chinese font is unavailable",
)
def test_fixture_generation_is_byte_deterministic(tmp_path):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    first_manifest = tmp_path / "first.json"
    second_manifest = tmp_path / "second.json"

    first = fixture.build_fixture(first_pdf, first_manifest)
    second = fixture.build_fixture(second_pdf, second_manifest)

    assert first["sha256"] == second["sha256"]
    assert first_pdf.read_bytes() == second_pdf.read_bytes()
