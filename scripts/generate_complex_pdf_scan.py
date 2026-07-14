#!/usr/bin/env python
"""Generate and verify the image-only complex PDF fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / "test_assets"
DEFAULT_SOURCE = ASSET_DIR / "4_gs_prepress_300dpi.pdf"
DEFAULT_SCAN = ASSET_DIR / "4_gs_prepress_300dpi_scanned_300dpi.pdf"
DEFAULT_MANIFEST = ASSET_DIR / "complex_pdf_matrix.json"
DEFAULT_DPI = 300
DEFAULT_JPEG_QUALITY = 92
ANCHORS = {
    "formula_page": {"page": 3, "terms": ["CSC", "RSC", "LP"]},
    "table_page": {"page": 5, "terms": ["TABLE I", "Snubber"]},
    "title_page": {
        "page": 1,
        "terms": ["Snubber-Based Suppression", "SiC MOSFET"],
    },
}


def sha256(path: Path) -> str:
    """Return the SHA-256 digest for one asset."""
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


def describe_assets(source: Path, scan: Path) -> dict[str, Any]:
    """Collect the source/scan invariants checked by tests and verify mode."""
    with fitz.open(source) as source_document, fitz.open(scan) as scan_document:
        source_text_lengths = [
            len(page.get_text("text").strip()) for page in source_document
        ]
        scan_text_lengths = [
            len(page.get_text("text").strip()) for page in scan_document
        ]
        scan_image_counts = [
            len(page.get_images(full=True)) for page in scan_document
        ]
        return {
            "source": {
                "filename": source.name,
                "sha256": sha256(source),
                "bytes": source.stat().st_size,
                "page_count": source_document.page_count,
                "page_sizes": _page_sizes(source_document),
                "has_text_layer": any(source_text_lengths),
                "text_lengths": source_text_lengths,
            },
            "scan": {
                "filename": scan.name,
                "sha256": sha256(scan),
                "bytes": scan.stat().st_size,
                "page_count": scan_document.page_count,
                "page_sizes": _page_sizes(scan_document),
                "has_text_layer": any(scan_text_lengths),
                "text_lengths": scan_text_lengths,
                "image_counts": scan_image_counts,
            },
        }


def build_manifest(source: Path, scan: Path, dpi: int, jpeg_quality: int) -> dict[str, Any]:
    """Build the checked-in fixture manifest after scan generation."""
    metadata = describe_assets(source, scan)
    return {
        "schema_version": 1,
        "generation": {
            "renderer": "PyMuPDF",
            "dpi": dpi,
            "jpeg_quality": jpeg_quality,
            "pages": "one JPEG image per source page",
        },
        "anchors": ANCHORS,
        **metadata,
    }


def _validate_structure(manifest: dict[str, Any]) -> None:
    source = manifest["source"]
    scan = manifest["scan"]
    if not source["has_text_layer"]:
        raise ValueError("The source fixture must have an extractable text layer")
    if scan["has_text_layer"]:
        raise ValueError("The scan fixture must not have an extractable text layer")
    if source["page_count"] != scan["page_count"]:
        raise ValueError("The source and scan page counts differ")
    if source["page_sizes"] != scan["page_sizes"]:
        raise ValueError("The source and scan page geometry differs")
    if any(scan["text_lengths"]):
        raise ValueError("The scan fixture unexpectedly contains extracted text")
    if any(count != 1 for count in scan["image_counts"]):
        raise ValueError("Each scan page must contain exactly one embedded image")


def verify_manifest(source: Path, scan: Path, manifest_path: Path) -> dict[str, Any]:
    """Validate checked-in assets against their manifest and semantic anchors."""
    if not manifest_path.is_file():
        raise ValueError(f"Fixture manifest does not exist: {manifest_path}")
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = build_manifest(
        source,
        scan,
        expected["generation"]["dpi"],
        expected["generation"]["jpeg_quality"],
    )
    if actual != expected:
        raise ValueError("Complex PDF fixture manifest does not match the assets")
    _validate_structure(actual)

    with fitz.open(source) as document:
        for anchor_name, anchor in actual["anchors"].items():
            page_index = anchor["page"] - 1
            text = document[page_index].get_text("text").casefold()
            missing = [term for term in anchor["terms"] if term.casefold() not in text]
            if missing:
                raise ValueError(
                    f"Source {anchor_name} is missing expected terms: {', '.join(missing)}"
                )
    return actual


def generate_scan(source: Path, output: Path, dpi: int, jpeg_quality: int) -> None:
    """Rasterize the source to a one-image-per-page PDF without a text layer."""
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if not 1 <= jpeg_quality <= 100:
        raise ValueError("jpeg_quality must be between 1 and 100")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp.pdf")
    scale = dpi / 72
    source_document = fitz.open(source)
    scan_document = fitz.open()
    try:
        for source_page in source_document:
            pixmap = source_page.get_pixmap(
                matrix=fitz.Matrix(scale, scale), alpha=False
            )
            scan_page = scan_document.new_page(
                width=source_page.rect.width,
                height=source_page.rect.height,
            )
            scan_page.insert_image(
                scan_page.rect,
                stream=pixmap.tobytes("jpeg", jpg_quality=jpeg_quality),
                keep_proportion=False,
            )
        scan_document.save(
            temporary_output,
            garbage=4,
            deflate=True,
            no_new_id=True,
        )
    finally:
        scan_document.close()
        source_document.close()

    try:
        metadata = describe_assets(source, temporary_output)
        _validate_structure(metadata)
        temporary_output.replace(output)
    finally:
        if temporary_output.exists():
            temporary_output.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--jpeg-quality", type=int, default=DEFAULT_JPEG_QUALITY)
    parser.add_argument("--write", action="store_true", help="Generate scan and manifest")
    parser.add_argument("--verify", action="store_true", help="Verify checked-in assets")
    args = parser.parse_args()
    if not args.write and not args.verify:
        parser.error("choose --write and/or --verify")
    return args


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    manifest_path = args.manifest.resolve()
    if not source.is_file():
        raise SystemExit(f"Source fixture does not exist: {source}")

    if args.write:
        generate_scan(source, output, args.dpi, args.jpeg_quality)
        manifest = build_manifest(source, output, args.dpi, args.jpeg_quality)
        _validate_structure(manifest)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.verify:
        manifest = verify_manifest(source, output, manifest_path)
    else:
        manifest = build_manifest(source, output, args.dpi, args.jpeg_quality)

    print(
        json.dumps(
            {
                "source": manifest["source"]["filename"],
                "scan": manifest["scan"]["filename"],
                "pages": manifest["source"]["page_count"],
                "scan_bytes": manifest["scan"]["bytes"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
