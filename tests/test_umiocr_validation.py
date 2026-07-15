"""Tests for the credential-free local UMI OCR layered-PDF validator."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import fitz
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_umiocr_layered_pdf.py"
SPEC = spec_from_file_location("validate_umiocr_layered_pdf", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _write_pdf(path: Path, text: str = "") -> None:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_layered_pdf_validator_accepts_matching_text_layer(tmp_path):
    source = tmp_path / "source.pdf"
    layered = tmp_path / "layered.pdf"
    _write_pdf(source)
    _write_pdf(layered, "Rapid OCR text")

    assert validator.inspect_layered_pdf(source, layered) == {
        "pages": 1,
        "text_characters": len("Rapid OCR text"),
    }


def test_layered_pdf_validator_rejects_textless_output(tmp_path):
    source = tmp_path / "source.pdf"
    layered = tmp_path / "layered.pdf"
    _write_pdf(source)
    _write_pdf(layered)

    with pytest.raises(RuntimeError, match="no extractable text layer"):
        validator.inspect_layered_pdf(source, layered)
