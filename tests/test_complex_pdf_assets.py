"""Offline invariants for the complex source and image-only scan fixtures."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / "test_assets"
SOURCE = ASSET_DIR / "4_gs_prepress_300dpi.pdf"
SCAN = ASSET_DIR / "4_gs_prepress_300dpi_scanned_300dpi.pdf"
MANIFEST = ASSET_DIR / "complex_pdf_matrix.json"
GENERATOR = PROJECT_ROOT / "scripts" / "generate_complex_pdf_scan.py"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _page_sizes(document: fitz.Document) -> list[list[float]]:
    return [
        [round(page.rect.width, 2), round(page.rect.height, 2)]
        for page in document
    ]


def _ink_fraction(page: fitz.Page) -> float:
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(1, 1), colorspace=fitz.csGRAY, alpha=False
    )
    return sum(sample < 245 for sample in pixmap.samples) / len(pixmap.samples)


def test_complex_fixture_manifest_matches_checked_in_assets():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["source"]["filename"] == SOURCE.name
    assert manifest["scan"]["filename"] == SCAN.name
    assert manifest["source"]["sha256"] == _sha256(SOURCE)
    assert manifest["scan"]["sha256"] == _sha256(SCAN)
    assert manifest["generation"] == {
        "dpi": 300,
        "jpeg_quality": 92,
        "pages": "one JPEG image per source page",
        "renderer": "PyMuPDF",
    }


def test_complex_source_has_text_and_documented_technical_content():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with fitz.open(SOURCE) as source_document:
        assert source_document.page_count == 6
        assert _page_sizes(source_document) == manifest["source"]["page_sizes"]
        assert all(page.get_text("text").strip() for page in source_document)

        for anchor in manifest["anchors"].values():
            text = source_document[anchor["page"] - 1].get_text("text").casefold()
            assert all(term.casefold() in text for term in anchor["terms"])

        assert _ink_fraction(source_document[2]) > 0.02


def test_complex_scan_is_image_only_and_preserves_page_geometry():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with fitz.open(SOURCE) as source_document, fitz.open(SCAN) as scan_document:
        assert scan_document.page_count == source_document.page_count == 6
        assert _page_sizes(scan_document) == _page_sizes(source_document)
        assert _page_sizes(scan_document) == manifest["scan"]["page_sizes"]
        assert all(not page.get_text("text").strip() for page in scan_document)
        assert all(len(page.get_images(full=True)) == 1 for page in scan_document)
        assert _ink_fraction(scan_document[2]) > 0.02


def test_complex_fixture_generator_verify_mode_passes():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--verify"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
