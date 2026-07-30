"""Tests for the credential-free local UMI OCR layered-PDF validator."""

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from unittest.mock import patch

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


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def get_text(self, _kind: str) -> str:
        return self._text


class _FakeDocument:
    page_count = 1

    def __init__(self, text: str):
        self._page = _FakePage(text)

    def __iter__(self):
        return iter((self._page,))

    def close(self) -> None:
        return None


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


def test_layered_pdf_validator_writes_machine_readable_report(tmp_path):
    report_path = tmp_path / "reports" / "validation.json"

    validator._write_report(
        report_path,
        {
            "runtime": "Umi-OCR Paddle NeoEngine",
            "backend": "onnxruntime",
            "pages": 1,
            "text_characters": 12,
        },
    )

    assert json.loads(report_path.read_text(encoding="utf-8")) == {
        "runtime": "Umi-OCR Paddle NeoEngine",
        "backend": "onnxruntime",
        "pages": 1,
        "text_characters": 12,
    }


def test_layered_pdf_validator_checks_chinese_count_and_anchors(tmp_path):
    source = tmp_path / "source.pdf"
    layered = tmp_path / "layered.pdf"
    source.write_bytes(b"source")
    layered.write_bytes(b"layered")
    with patch.object(
        validator.fitz, "open", side_effect=(
            _FakeDocument(""),
            _FakeDocument("\u4e2d\u6587 OCR \u951a\u70b9"),
        ),
    ):
        result = validator.inspect_layered_pdf(
            source,
            layered,
            expected_anchors=["\u4e2d\u6587 OCR \u951a\u70b9"],
            min_chinese_characters=4,
        )

    assert result["pages"] == 1
    assert result["chinese_characters"] >= 4
    assert result["missing_anchors"] == []


def test_layered_pdf_validator_rejects_missing_chinese_anchor(tmp_path):
    source = tmp_path / "source.pdf"
    layered = tmp_path / "layered.pdf"
    source.write_bytes(b"source")
    layered.write_bytes(b"layered")

    with patch.object(
        validator.fitz, "open", side_effect=(
            _FakeDocument(""),
            _FakeDocument("English only"),
        ),
    ):
        with pytest.raises(RuntimeError, match="expected OCR anchors"):
            validator.inspect_layered_pdf(
                source,
                layered,
                expected_anchors=["\u4e2d\u6587\u951a\u70b9"],
                min_chinese_characters=0,
            )
