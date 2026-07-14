"""Offline tests for the structural checks used by the live PDF matrix."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from tests import live_complex_pdf_matrix as matrix


def _fake_page(
    text: str,
    *,
    span_text: str | None = None,
    size: float = 12.0,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 10.0, 10.0),
):
    span = {
        "text": span_text if span_text is not None else text,
        "size": size,
        "bbox": bbox,
    }
    return SimpleNamespace(
        get_text=lambda kind: (
            text if kind == "text" else {"blocks": [{"lines": [{"spans": [span]}]}]}
        ),
        get_fonts=lambda full=False: [(1, "font", "Type0", "font", "", "")],
        rect=SimpleNamespace(height=792.0),
    )


def test_live_command_log_streams_redacted_output(tmp_path, capsys):
    secret = "matrix-test-secret"
    progress_log = tmp_path / "live-progress.log"

    output = matrix._run(
        [sys.executable, "-c", f"print('ready {secret}')"],
        timeout=30,
        secrets=(secret,),
        progress_log=progress_log,
    )

    displayed = capsys.readouterr().out
    saved = progress_log.read_text(encoding="utf-8")
    for value in (output, displayed, saved):
        assert secret not in value
        assert "***" in value


def test_translation_page_checks_use_the_alternating_page_contract(monkeypatch):
    monkeypatch.setattr(matrix, "_ink_fraction", lambda _page: 0.2)

    report = matrix._inspect_translation_pages(
        [
            _fake_page("中文"),
            _fake_page("source"),
            _fake_page("翻译"),
            _fake_page("source"),
        ],
        expected_pages=4,
    )

    assert report["translated_cjk_pages"] == 2
    assert report["translated_font_resources"] == 2


def test_translation_page_checks_reject_an_oversized_short_ocr_span(monkeypatch):
    monkeypatch.setattr(matrix, "_ink_fraction", lambda _page: 0.2)

    with pytest.raises(AssertionError, match="oversized short OCR spans"):
        matrix._inspect_translation_pages(
            [_fake_page("中文", span_text="E", size=80.0), _fake_page("source")],
            expected_pages=2,
        )


def test_translation_page_checks_reject_a_noisy_ocr_margin_span(monkeypatch):
    monkeypatch.setattr(matrix, "_ink_fraction", lambda _page: 0.2)

    with pytest.raises(AssertionError, match="noisy OCR margin spans"):
        matrix._inspect_translation_pages(
            [
                _fake_page(
                    "中文",
                    span_text=(
                        "11001010100410031/40101I01433140120$/0/0101-1o1-00 "
                        "(000) 1 pe A0-00 J 10o04011102"
                    ),
                    bbox=(7.9, 720.6, 500.9, 736.5),
                ),
                _fake_page("source"),
            ],
            expected_pages=2,
        )


def test_translation_page_checks_require_scanned_figure_captions(monkeypatch):
    monkeypatch.setattr(matrix, "_ink_fraction", lambda _page: 0.2)
    expected_captions = {1: frozenset({6})}

    report = matrix._inspect_translation_pages(
        [_fake_page("中文 图6."), _fake_page("source")],
        expected_pages=2,
        expected_figure_captions=expected_captions,
    )

    assert report["translated_figure_captions"] == {"source_page_1": [6]}

    with pytest.raises(AssertionError, match="missing figure captions: 图6"):
        matrix._inspect_translation_pages(
            [_fake_page("中文 图6b"), _fake_page("source")],
            expected_pages=2,
            expected_figure_captions=expected_captions,
        )


def test_source_ink_loss_counts_source_pixels_erased_to_white():
    class FakePage:
        def __init__(self, samples):
            self.samples = samples

        def get_pixmap(self, **_kwargs):
            return SimpleNamespace(samples=self.samples)

    source = FakePage(bytes([0, 0, 255, 255]))
    target = FakePage(bytes([255, 0, 255, 255]))

    loss = matrix._source_ink_loss(source, target, matrix.fitz.Rect(0, 0, 2, 2))

    assert loss == 0.5


def test_visual_anchor_contract_excludes_translatable_captions():
    anchors = {
        name: (page, coordinates, max_loss)
        for name, page, coordinates, max_loss in matrix.OCR_WORKAROUND_VISUAL_ANCHORS
    }

    assert anchors["page_5_table_grid"] == (5, (60.0, 330.0, 290.0, 370.0), 0.08)
    assert "page_5_figure_13_caption" not in anchors


def test_ocr_workaround_visual_anchors_apply_only_to_scanned_cases():
    text_names = {name for name, *_ in matrix._visual_anchors_for(matrix.CASES[2])}
    scanned_names = {name for name, *_ in matrix._visual_anchors_for(matrix.CASES[3])}

    assert "page_5_table_grid" not in text_names
    assert "page_5_table_grid" in scanned_names
