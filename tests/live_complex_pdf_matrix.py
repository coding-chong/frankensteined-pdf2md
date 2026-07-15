"""Strict live validation for the complex PDF integration matrix.

This module is intentionally not named ``test_*.py``. Run it only through
``scripts/run_live_complex_pdf_matrix.py`` because it spends real API quota.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import fitz
import pytest

from ocr_flow.config import Config
from ocr_flow.runtime import managed_runtime_readiness
from ocr_flow.self_check import find_umi_ocr
from ocr_flow.steps.compress import find_ghostscript


pytestmark = pytest.mark.live

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / "test_assets"
SOURCE_PDF = ASSET_DIR / "4_gs_prepress_300dpi.pdf"
SCANNED_PDF = ASSET_DIR / "4_gs_prepress_300dpi_scanned_300dpi.pdf"
SOURCE_PAGE_COUNT = 6
CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
FORMULA_PATTERN = re.compile(r"\$\$|\\\[|\\\(|\\begin\{|<math", re.IGNORECASE)
OVERSIZED_SHORT_SPAN_MIN_SIZE = 48.0
OCR_NOISE_MARGIN_HEIGHT = 96.0
OCR_NOISE_MIN_LENGTH = 48
OCR_NOISE_MAX_ALPHABETIC_RATIO = 0.2
OCR_NOISE_MIN_DIGIT_OR_SYMBOL_RATIO = 0.65
FIGURE_CAPTION_PATTERN = re.compile(r"图\s*(\d+)\s*[.。:：]")
SCANNED_FIGURE_CAPTION_EXPECTATIONS = {
    3: frozenset({6, 7, 8, 9}),
    5: frozenset({13, 14}),
}
VISUAL_ANCHORS = (
    # Translation may replace nearby prose, so these thresholds allow normal
    # text-mask differences while still rejecting erased formulae and plots.
    ("page_3_formula", 3, (45.0, 345.0, 300.0, 435.0), 0.38),
    ("page_3_lower_circuit", 3, (312.0, 500.0, 563.0, 685.0), 0.25),
    ("page_5_left_plots", 5, (45.0, 380.0, 300.0, 650.0), 0.30),
    ("page_5_right_plots", 5, (312.0, 150.0, 563.0, 420.0), 0.34),
)
OCR_WORKAROUND_VISUAL_ANCHORS = (
    # OCR workaround preserves table and figure raster content. Captions are
    # intentionally excluded because they are masked and translated as text.
    ("page_5_table_grid", 5, (60.0, 330.0, 290.0, 370.0), 0.08),
)


@dataclass(frozen=True)
class MatrixCase:
    """One externally observable pipeline path."""

    name: str
    input_pdf: Path
    pdf_type: str
    translate: bool
    compress: bool
    expected_steps: dict[str, str]


CASES = (
    MatrixCase(
        name="text_no_translate",
        input_pdf=SOURCE_PDF,
        pdf_type="text",
        translate=False,
        compress=False,
        expected_steps={
            "ocr": "skipped",
            "translate": "skipped",
            "compress": "completed",
        },
    ),
    MatrixCase(
        name="scan_no_translate",
        input_pdf=SCANNED_PDF,
        pdf_type="scanned",
        translate=False,
        compress=False,
        expected_steps={
            "ocr": "completed",
            "translate": "skipped",
            "compress": "completed",
        },
    ),
    MatrixCase(
        name="text_translate_uncompressed",
        input_pdf=SOURCE_PDF,
        pdf_type="text",
        translate=True,
        compress=False,
        expected_steps={
            "ocr": "skipped",
            "translate": "completed",
            "compress": "skipped",
        },
    ),
    MatrixCase(
        name="scan_translate_compressed",
        input_pdf=SCANNED_PDF,
        pdf_type="scanned",
        translate=True,
        compress=True,
        expected_steps={
            "ocr": "completed",
            "translate": "completed",
            "compress": "completed",
        },
    ),
)


def _visual_anchors_for(case: MatrixCase):
    if case.pdf_type == "scanned":
        return (*VISUAL_ANCHORS, *OCR_WORKAROUND_VISUAL_ANCHORS)
    return VISUAL_ANCHORS


def _redact(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "***")
    return value


def _read_process_output(stream, lines: queue.Queue[str | None]) -> None:
    try:
        for line in iter(stream.readline, ""):
            lines.put(line)
    finally:
        stream.close()
        lines.put(None)


def _run(
    command: list[str],
    *,
    timeout: int,
    secrets: tuple[str, ...],
    cwd: Path = PROJECT_ROOT,
    progress_log: Optional[Path] = None,
) -> str:
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
    except OSError as error:
        raise AssertionError(f"Could not start command: {error}") from error

    assert process.stdout is not None
    lines: queue.Queue[str | None] = queue.Queue()
    reader = threading.Thread(
        target=_read_process_output,
        args=(process.stdout, lines),
        daemon=True,
    )
    reader.start()
    output: list[str] = []
    deadline = time.monotonic() + timeout
    log_handle = (
        progress_log.open("a", encoding="utf-8") if progress_log is not None else None
    )
    try:
        if log_handle is not None:
            rendered_command = _redact(" ".join(command), secrets)
            log_handle.write(f"\n$ {rendered_command}\n")
            log_handle.flush()
            print(f"$ {rendered_command}", flush=True)

        while reader.is_alive() or not lines.empty():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                reader.join(timeout=1)
                while not lines.empty():
                    line = lines.get_nowait()
                    if line is not None:
                        output.append(_redact(line, secrets))
                raise AssertionError(
                    f"Timed out after {timeout}s: {''.join(output)[-2000:]}"
                )
            try:
                line = lines.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            if line is None:
                continue
            redacted_line = _redact(line, secrets)
            output.append(redacted_line)
            if log_handle is not None:
                log_handle.write(redacted_line)
                log_handle.flush()
                print(redacted_line, end="", flush=True)
    finally:
        if log_handle is not None:
            log_handle.close()

    result_code = process.wait()
    rendered_output = "".join(output)
    if result_code != 0:
        raise AssertionError(
            f"Command failed with exit code {result_code}: {rendered_output[-4000:]}"
        )
    return rendered_output


def _require_live_environment() -> tuple[Config, tuple[str, ...], dict[str, str]]:
    config_value = os.environ.get("OCR_FLOW_LIVE_CONFIG")
    if not config_value:
        raise AssertionError(
            "OCR_FLOW_LIVE_CONFIG is required; use scripts/run_live_complex_pdf_matrix.py --config <path>."
        )

    config_path = Path(config_value).expanduser().resolve()
    if not config_path.is_file():
        raise AssertionError(f"Live credential config does not exist: {config_path}")

    source_config = Config.load(config_path)
    umi_override = os.environ.get("OCR_FLOW_LIVE_UMIOCR_EXE")
    umi_engine_override = os.environ.get("OCR_FLOW_LIVE_UMIOCR_ENGINE")
    ghostscript_override = os.environ.get("OCR_FLOW_LIVE_GHOSTSCRIPT")
    umi_executable = (
        Path(umi_override).expanduser()
        if umi_override
        else Path(source_config.umiocr.exe_path).expanduser()
        if source_config.umiocr.exe_path
        else Path(find_umi_ocr(source_config) or "")
    )
    ghostscript_executable = (
        Path(ghostscript_override).expanduser()
        if ghostscript_override
        else Path(source_config.compress.ghostscript_path).expanduser()
        if source_config.compress.ghostscript_path
        else Path(find_ghostscript() or "")
    )

    missing = []
    if not source_config.mineru.api_token:
        missing.append("mineru.api_token")
    if not source_config.babeldoc.openai:
        missing.append("babeldoc.openai=true")
    if not source_config.babeldoc.openai_api_key:
        missing.append("babeldoc.openai_api_key")
    if not umi_executable.is_file():
        missing.append("a valid UMI OCR executable")
    if not ghostscript_executable.is_file():
        missing.append("a valid Ghostscript executable")
    if missing:
        raise AssertionError(
            "Live matrix prerequisites are missing: " + ", ".join(missing)
        )

    isolated = Config()
    isolated.umiocr.enabled = source_config.umiocr.enabled
    isolated.umiocr.url = source_config.umiocr.url
    isolated.umiocr.language = source_config.umiocr.language
    isolated.umiocr.engine = umi_engine_override or source_config.umiocr.engine
    isolated.umiocr.exe_path = str(umi_executable.resolve())
    isolated.babeldoc.path = None
    isolated.babeldoc.lang_in = source_config.babeldoc.lang_in
    isolated.babeldoc.lang_out = source_config.babeldoc.lang_out
    isolated.babeldoc.openai = True
    isolated.babeldoc.openai_model = source_config.babeldoc.openai_model
    isolated.babeldoc.openai_base_url = source_config.babeldoc.openai_base_url
    isolated.babeldoc.openai_api_key = source_config.babeldoc.openai_api_key
    isolated.babeldoc.qps = source_config.babeldoc.qps
    isolated.babeldoc.primary_font_family = source_config.babeldoc.primary_font_family
    isolated.compress.ghostscript_path = str(ghostscript_executable.resolve())
    isolated.compress.quality = source_config.compress.quality
    isolated.mineru.api_token = source_config.mineru.api_token
    isolated.postprocess.fix_format = source_config.postprocess.fix_format
    isolated.postprocess.download_images = source_config.postprocess.download_images

    version = _run(
        [str(ghostscript_executable), "--version"],
        timeout=30,
        secrets=(source_config.mineru.api_token, source_config.babeldoc.openai_api_key),
    ).strip()
    metadata = {
        "ghostscript_version": version,
        "umiocr_executable": umi_executable.name,
        "umiocr_engine": isolated.umiocr.engine,
        "translation_model": source_config.babeldoc.openai_model,
    }
    return (
        isolated,
        (
            source_config.mineru.api_token,
            source_config.babeldoc.openai_api_key,
        ),
        metadata,
    )


def _write_isolated_config(config: Config) -> tuple[Path, Path]:
    directory = Path(tempfile.mkdtemp(prefix="ocr-flow-live-config-"))
    config_path = directory / "config.toml"
    config.save(config_path)
    return directory, config_path


def _configure_managed_profile(
    profile: str,
    secrets: tuple[str, ...],
    *,
    progress_log: Optional[Path] = None,
) -> str:
    if profile == "windows-directml" and os.name != "nt":
        raise AssertionError("windows-directml live validation requires Windows")
    output = _run(
        [
            sys.executable,
            "-m",
            "ocr_flow.cli",
            "runtime",
            "setup",
            "--profile",
            profile,
        ],
        timeout=1800,
        secrets=secrets,
        progress_log=progress_log,
    )
    ready, message = managed_runtime_readiness(profile)
    if not ready:
        raise AssertionError(message)
    return output


def _find_work_directory(case_root: Path) -> Path:
    states = list(case_root.rglob(".state.json"))
    if len(states) != 1:
        raise AssertionError(
            f"Expected one pipeline state below {case_root}, found {len(states)}"
        )
    return states[0].parent


def _state_path(value: str | None) -> Path:
    if not value:
        raise AssertionError("Pipeline state did not record an expected output path")
    path = Path(value)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _open_pdf(path: Path) -> fitz.Document:
    if not path.is_file():
        raise AssertionError(f"Expected PDF does not exist: {path}")
    try:
        return fitz.open(path)
    except fitz.FileDataError as error:
        raise AssertionError(f"PDF is unreadable: {path}: {error}") from error


def _ink_fraction(page: fitz.Page) -> float:
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(1, 1), colorspace=fitz.csGRAY, alpha=False
    )
    return sum(sample < 245 for sample in pixmap.samples) / len(pixmap.samples)


def _assert_readable_pdf(path: Path, expected_pages: int) -> None:
    with _open_pdf(path) as document:
        assert document.page_count == expected_pages, (
            f"{path.name} page count {document.page_count} != {expected_pages}"
        )
        assert all(_ink_fraction(page) > 0.005 for page in document), (
            f"{path.name} contains an empty or near-blank page"
        )


def _write_contact_sheet(pdf_path: Path | list[Path], output_path: Path) -> Path:
    """Render all pages into a compact PNG for required human visual review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    paths = [pdf_path] if isinstance(pdf_path, Path) else pdf_path
    documents = [_open_pdf(path) for path in paths]
    try:
        pages = [page for document in documents for page in document]
        columns = 2
        thumbnail_width = 306
        thumbnail_height = 396
        rows = (len(pages) + columns - 1) // columns
        sheet_document = fitz.open()
        try:
            sheet_page = sheet_document.new_page(
                width=columns * thumbnail_width,
                height=rows * thumbnail_height,
            )
            for index, page in enumerate(pages):
                column = index % columns
                row = index // columns
                rect = fitz.Rect(
                    column * thumbnail_width,
                    row * thumbnail_height,
                    (column + 1) * thumbnail_width,
                    (row + 1) * thumbnail_height,
                )
                pixmap = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
                sheet_page.insert_image(rect, stream=pixmap.tobytes("png"))
                sheet_page.insert_text(
                    (rect.x0 + 6, rect.y0 + 14),
                    str(index + 1),
                    fontsize=9,
                    color=(1, 0, 0),
                )
            sheet_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).save(
                output_path
            )
        finally:
            sheet_document.close()
    finally:
        for document in documents:
            document.close()
    return output_path


def _find_oversized_short_spans(page: fitz.Page) -> list[dict[str, Any]]:
    """Find OCR artifacts that render a single short token as a giant glyph."""
    anomalies = []
    blocks = page.get_text("dict").get("blocks", [])
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text", "")).strip()
                size = float(span.get("size", 0.0))
                if not text or len(text) > 3 or size < OVERSIZED_SHORT_SPAN_MIN_SIZE:
                    continue
                anomalies.append(
                    {
                        "text": text,
                        "size": round(size, 1),
                        "bbox": [round(value, 1) for value in span["bbox"]],
                    }
                )
    return anomalies


def _find_noisy_ocr_margin_spans(page: fitz.Page) -> list[dict[str, Any]]:
    """Find long, non-linguistic OCR text re-rendered in a page margin."""
    anomalies = []
    minimum_y = page.rect.height - OCR_NOISE_MARGIN_HEIGHT
    blocks = page.get_text("dict").get("blocks", [])
    for block in blocks:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(str(span.get("text", "")) for span in spans)
            compact_text = re.sub(r"\s+", "", text)
            if len(compact_text) < OCR_NOISE_MIN_LENGTH:
                continue
            y1 = min(float(span["bbox"][1]) for span in spans)
            if y1 < minimum_y:
                continue
            alphabetic = sum(character.isalpha() for character in compact_text)
            digit_or_symbol = sum(
                character.isdigit() or character in "/-_()$.,:"
                for character in compact_text
            )
            if (
                alphabetic > len(compact_text) * OCR_NOISE_MAX_ALPHABETIC_RATIO
                or digit_or_symbol
                < len(compact_text) * OCR_NOISE_MIN_DIGIT_OR_SYMBOL_RATIO
            ):
                continue
            anomalies.append(
                {
                    "text": compact_text,
                    "bbox": [
                        round(min(float(span["bbox"][index]) for span in spans), 1)
                        for index in (0, 1)
                    ]
                    + [
                        round(max(float(span["bbox"][index]) for span in spans), 1)
                        for index in (2, 3)
                    ],
                }
            )
    return anomalies


def _gray_samples(page: fitz.Page, rect: fitz.Rect | None = None) -> bytes:
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(1, 1),
        colorspace=fitz.csGRAY,
        clip=rect,
        alpha=False,
    )
    return pixmap.samples


def _source_ink_loss(
    reference_page: fitz.Page, target_page: fitz.Page, rect: fitz.Rect
) -> float:
    """Measure source drawing pixels that became white in translated output."""
    reference = _gray_samples(reference_page, rect)
    target = _gray_samples(target_page, rect)
    if len(reference) != len(target):
        raise AssertionError(
            f"Rendered comparison geometry differs for region {tuple(rect)}"
        )
    source_ink = sum(value < 220 for value in reference)
    if source_ink == 0:
        raise AssertionError(
            f"Visual anchor region is blank in the reference: {tuple(rect)}"
        )
    lost_ink = sum(
        source_value < 220 and target_value > 245
        for source_value, target_value in zip(reference, target)
    )
    return lost_ink / source_ink


def _validate_visual_anchors(
    reference_path: Path,
    translated_pages: list[fitz.Page],
    anchors=VISUAL_ANCHORS,
) -> dict[str, dict[str, float | int]]:
    """Reject representative formula/graphic regions erased by translation."""
    expected_pages = SOURCE_PAGE_COUNT * 2
    assert len(translated_pages) == expected_pages, (
        f"Expected {expected_pages} translated PDF pages, found {len(translated_pages)}"
    )
    metrics: dict[str, dict[str, float | int]] = {}
    with _open_pdf(reference_path) as reference:
        for name, source_page_number, coordinates, max_loss in anchors:
            source_page = reference[source_page_number - 1]
            translated_page_number = (source_page_number * 2) - 1
            translated_page = translated_pages[translated_page_number - 1]
            loss = _source_ink_loss(
                source_page,
                translated_page,
                fitz.Rect(coordinates),
            )
            assert loss <= max_loss, (
                f"Translated {name} lost too much source drawing coverage: "
                f"{loss:.3f} > {max_loss:.3f}"
            )
            metrics[name] = {
                "source_page": source_page_number,
                "translated_page": translated_page_number,
                "source_ink_loss": round(loss, 4),
                "max_source_ink_loss": max_loss,
            }
    return metrics


def _validate_translated_figure_captions(
    pages: list[fitz.Page], expected_captions: dict[int, frozenset[int]]
) -> dict[str, list[int]]:
    """Require scanned OCR figure captions to remain translatable text."""
    translated_captions = {}
    for source_page_number, expected_numbers in expected_captions.items():
        translated_page_number = source_page_number * 2 - 1
        text = pages[translated_page_number - 1].get_text("text")
        actual_numbers = {
            int(match.group(1)) for match in FIGURE_CAPTION_PATTERN.finditer(text)
        }
        missing = expected_numbers - actual_numbers
        assert not missing, (
            f"Translated page {translated_page_number} is missing figure captions: "
            + ", ".join(f"图{number}" for number in sorted(missing))
        )
        translated_captions[f"source_page_{source_page_number}"] = sorted(
            actual_numbers
        )
    return translated_captions


def _inspect_translation_pages(
    pages: list[fitz.Page],
    expected_pages: int,
    *,
    expected_figure_captions: Optional[dict[int, frozenset[int]]] = None,
) -> dict[str, Any]:
    """Validate the alternating translated/original page contract."""
    assert len(pages) == expected_pages, (
        f"Expected {expected_pages} translated PDF pages, found {len(pages)}"
    )
    cjk_page_count = 0
    font_resource_count = 0
    for page_number, page in enumerate(pages, start=1):
        text = page.get_text("text")
        assert "\ufffd" not in text, "Translated PDF contains replacement glyphs"
        if page_number % 2 == 0:
            continue
        cjk_page_count += bool(CJK_PATTERN.search(text))
        fonts = page.get_fonts(full=True)
        font_resource_count += len(fonts)
        assert CJK_PATTERN.search(text), (
            f"Translated page {page_number} has no CJK text"
        )
        assert fonts, f"Translated page {page_number} has no font resources"
        assert any(font[2] == "Type0" for font in fonts), (
            f"Translated page {page_number} has no Unicode composite font"
        )
        assert _ink_fraction(page) > 0.02, (
            f"Translated page {page_number} is empty or near-blank"
        )
        anomalies = _find_oversized_short_spans(page)
        assert not anomalies, (
            f"Translated page {page_number} contains oversized short OCR spans: "
            f"{anomalies}"
        )
        noisy_margin_spans = _find_noisy_ocr_margin_spans(page)
        assert not noisy_margin_spans, (
            f"Translated page {page_number} contains noisy OCR margin spans: "
            f"{noisy_margin_spans}"
        )
    assert cjk_page_count == expected_pages // 2, (
        f"Expected {expected_pages // 2} translated CJK pages, found {cjk_page_count}"
    )
    report = {
        "translated_cjk_pages": cjk_page_count,
        "translated_font_resources": font_resource_count,
    }
    if expected_figure_captions:
        report["translated_figure_captions"] = _validate_translated_figure_captions(
            pages, expected_figure_captions
        )
    return report


def _validate_markdown(work_dir: Path, total_parts: int) -> dict[str, Any]:
    final_dir = work_dir / "final"
    markdown_files = sorted(final_dir.glob("part_*.md"))
    assert len(markdown_files) == total_parts, (
        f"Expected {total_parts} Markdown files, found {len(markdown_files)}"
    )
    contents = []
    for markdown_file in markdown_files:
        content = markdown_file.read_text(encoding="utf-8")
        assert content.strip(), f"Markdown file is empty: {markdown_file}"
        contents.append(content)
    combined = "\n".join(contents)
    normalized = combined.casefold()
    assert "snubber" in normalized
    assert "mosfet" in normalized
    assert FORMULA_PATTERN.search(combined), "MinerU Markdown has no formula marker"
    return {"markdown_files": len(markdown_files), "markdown_chars": len(combined)}


def _validate_ocr(work_dir: Path, visual_dir: Path, case: MatrixCase) -> dict[str, Any]:
    state = json.loads((work_dir / ".state.json").read_text(encoding="utf-8"))
    ocr_path = _state_path(state["steps"]["ocr"]["output"])
    _assert_readable_pdf(ocr_path, SOURCE_PAGE_COUNT)
    with _open_pdf(ocr_path) as document:
        text = "\n".join(page.get_text("text") for page in document)
        assert len(text.strip()) > 1000, "OCR output does not contain enough text"
        assert "snubber" in text.casefold()
        assert "mosfet" in text.casefold()
        assert _ink_fraction(document[2]) > 0.02
    contact_sheet = _write_contact_sheet(
        ocr_path, visual_dir / f"{case.name}_ocr_contact_sheet.png"
    )
    return {"ocr_pdf": str(ocr_path), "ocr_contact_sheet": str(contact_sheet)}


def _validate_translation(
    work_dir: Path, visual_dir: Path, case: MatrixCase
) -> dict[str, Any]:
    state = json.loads((work_dir / ".state.json").read_text(encoding="utf-8"))
    translated_path = _state_path(state["steps"]["translate"]["output"])
    expected_pages = SOURCE_PAGE_COUNT * 2
    reference_path = (
        _state_path(state["steps"]["ocr"]["output"])
        if state["steps"]["ocr"]["status"] == "completed"
        else case.input_pdf.resolve()
    )
    with _open_pdf(translated_path) as document:
        pages = list(document)
        visual_anchors = _validate_visual_anchors(
            reference_path, pages, _visual_anchors_for(case)
        )
        report = _inspect_translation_pages(
            pages,
            expected_pages,
            expected_figure_captions=(
                SCANNED_FIGURE_CAPTION_EXPECTATIONS
                if case.pdf_type == "scanned"
                else None
            ),
        )
        report["visual_anchors"] = visual_anchors
    contact_sheet = _write_contact_sheet(
        translated_path, visual_dir / f"{case.name}_translation_contact_sheet.png"
    )
    return {
        **report,
        "translated_pdf": str(translated_path),
        "translation_contact_sheet": str(contact_sheet),
    }


def _validate_compression(
    work_dir: Path,
    state: dict[str, Any],
    case: MatrixCase,
    visual_dir: Path,
) -> dict[str, Any]:
    split_dir = _state_path(state["steps"]["split"]["output_dir"])
    split_files = [split_dir / name for name in state["steps"]["split"]["files"]]
    assert split_files and all(path.is_file() for path in split_files)
    split_bytes = sum(path.stat().st_size for path in split_files)
    compression = state["steps"]["compress"]
    if compression["status"] == "skipped":
        assert not (work_dir / "intermediate" / "compressed").exists()
        return {"split_bytes": split_bytes, "compressed_bytes": split_bytes}

    compressed_dir = _state_path(compression["output_dir"])
    compressed_files = [compressed_dir / name for name in compression["files"]]
    assert len(compressed_files) == len(split_files)
    compressed_bytes = 0
    for split_file, compressed_file in zip(split_files, compressed_files):
        with _open_pdf(split_file) as split_document:
            expected_pages = split_document.page_count
        _assert_readable_pdf(compressed_file, expected_pages)
        compressed_bytes += compressed_file.stat().st_size
    assert compressed_bytes < split_bytes, (
        f"Ghostscript did not reduce fixture size: {compressed_bytes} >= {split_bytes}"
    )
    report: dict[str, Any] = {
        "split_bytes": split_bytes,
        "compressed_bytes": compressed_bytes,
    }
    if case.translate:
        reference_path = (
            _state_path(state["steps"]["ocr"]["output"])
            if state["steps"]["ocr"]["status"] == "completed"
            else case.input_pdf.resolve()
        )
        documents = [_open_pdf(path) for path in compressed_files]
        try:
            pages = [page for document in documents for page in document]
            visual_anchors = _validate_visual_anchors(
                reference_path, pages, _visual_anchors_for(case)
            )
            translated_report = _inspect_translation_pages(
                pages,
                SOURCE_PAGE_COUNT * 2,
                expected_figure_captions=(
                    SCANNED_FIGURE_CAPTION_EXPECTATIONS
                    if case.pdf_type == "scanned"
                    else None
                ),
            )
            translated_report["visual_anchors"] = visual_anchors
        finally:
            for document in documents:
                document.close()
        contact_sheet = _write_contact_sheet(
            compressed_files,
            visual_dir / f"{case.name}_compressed_translation_contact_sheet.png",
        )
        report["compressed_translation"] = {
            **translated_report,
            "pdfs": [str(path) for path in compressed_files],
            "translation_contact_sheet": str(contact_sheet),
        }
    return report


def _run_case(
    case: MatrixCase,
    *,
    config_path: Path,
    output_root: Path,
    visual_dir: Path,
    secrets: tuple[str, ...],
    progress_log: Optional[Path] = None,
) -> dict[str, Any]:
    case_root = output_root / case.name
    case_root.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        "-m",
        "ocr_flow.cli",
        "process",
        str(case.input_pdf),
        "-o",
        str(case_root),
        "--config",
        str(config_path),
        "--non-interactive",
        "--pdf-type",
        case.pdf_type,
        "--lang",
        "en",
        "--translate" if case.translate else "--no-translate",
        "--no-open-output",
        "-v",
    ]
    if case.compress:
        command.append("--compress")

    started = time.monotonic()
    _run(command, timeout=7200, secrets=secrets, progress_log=progress_log)
    elapsed_seconds = round(time.monotonic() - started, 2)
    work_dir = _find_work_directory(case_root)
    state = json.loads((work_dir / ".state.json").read_text(encoding="utf-8"))
    assert state["total_pages"] == SOURCE_PAGE_COUNT
    for step_name, expected_status in case.expected_steps.items():
        assert state["steps"][step_name]["status"] == expected_status
    assert state["steps"]["mineru"]["status"] == "completed"
    assert state["steps"]["mineru"]["failed"] == {}
    assert state["steps"]["mineru"]["completed"] == list(
        range(1, SOURCE_PAGE_COUNT + 1)
    )

    visual_dir.mkdir(parents=True, exist_ok=True)
    source_sheet = _write_contact_sheet(
        case.input_pdf, visual_dir / f"{case.name}_input_contact_sheet.png"
    )
    report: dict[str, Any] = {
        "work_dir": str(work_dir),
        "elapsed_seconds": elapsed_seconds,
        "input_contact_sheet": str(source_sheet),
        "markdown": _validate_markdown(work_dir, SOURCE_PAGE_COUNT),
        "compression": _validate_compression(work_dir, state, case, visual_dir),
    }
    if case.pdf_type == "scanned":
        report["ocr"] = _validate_ocr(work_dir, visual_dir, case)
    if case.translate:
        report["translation"] = _validate_translation(work_dir, visual_dir, case)
    return report


def test_live_complex_pdf_matrix():
    """Run the entire real-service matrix for one managed BabelDOC profile."""
    profile = os.environ.get("OCR_FLOW_LIVE_PROFILE", "cpu-safe")
    output_value = os.environ.get("OCR_FLOW_LIVE_OUTPUT")
    if not output_value:
        raise AssertionError("OCR_FLOW_LIVE_OUTPUT is required")
    output_root = Path(output_value).expanduser().resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise AssertionError(f"Live output directory must be empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    visual_dir = output_root / "visual_review"
    progress_log = output_root / "live-progress.log"
    report: dict[str, Any] = {
        "profile": profile,
        "cases": {},
        "progress_log": str(progress_log),
        "status": "failed",
    }
    isolated_config_dir: Path | None = None
    secrets: tuple[str, ...] = ()
    cleanup_failure: Exception | None = None
    try:
        isolated_config, secrets, metadata = _require_live_environment()
        report["preflight"] = metadata
        isolated_config_dir, isolated_config_path = _write_isolated_config(
            isolated_config
        )
        report["managed_runtime_setup"] = "completed"
        _configure_managed_profile(profile, secrets, progress_log=progress_log)
        for case in CASES:
            report["cases"][case.name] = _run_case(
                case,
                config_path=isolated_config_path,
                output_root=output_root,
                visual_dir=visual_dir,
                secrets=secrets,
                progress_log=progress_log,
            )
        report["api_requests"] = {
            "mineru_parts": SOURCE_PAGE_COUNT * len(CASES),
            "translation_documents": sum(case.translate for case in CASES),
        }
        report["status"] = "passed"
    except BaseException as error:
        report["failure"] = _redact(str(error), secrets)
        raise
    finally:
        if profile == "windows-directml":
            try:
                _configure_managed_profile(
                    "cpu-safe", secrets, progress_log=progress_log
                )
                report["cpu_safe_restore"] = "completed"
            except Exception as cleanup_error:
                report["cpu_safe_restore"] = _redact(str(cleanup_error), secrets)
                if report["status"] == "passed":
                    cleanup_failure = cleanup_error
        if isolated_config_dir:
            shutil.rmtree(isolated_config_dir, ignore_errors=True)
        (output_root / "live-matrix-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if cleanup_failure:
            raise cleanup_failure
