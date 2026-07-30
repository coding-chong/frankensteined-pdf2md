#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PDF compression using Ghostscript and text-preservation validation."""

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import fitz


MIN_MEANINGFUL_TEXT_CHARS = 1
MIN_TEXT_SIMILARITY = 0.98


@dataclass(frozen=True)
class PageTextValidation:
    """Credential-safe text comparison metrics for one PDF page."""

    page: int
    source_chars: int
    candidate_chars: int
    source_cjk_chars: int
    candidate_cjk_chars: int
    text_similarity: float
    cjk_preserved: bool
    preserved: bool


@dataclass(frozen=True)
class CompressionValidation:
    """Structured result for a compressed PDF text-preservation check."""

    preserved: bool
    reason: str
    source_pages: int
    candidate_pages: int
    source_has_meaningful_text: bool
    minimum_text_similarity: float
    pages: tuple[PageTextValidation, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report without extracted document text."""
        return asdict(self)


def _normalize_text(text: str) -> str:
    """Remove layout whitespace without rewriting document characters."""
    return "".join(text.split())


def _cjk_sequence(text: str) -> str:
    """Extract CJK characters while preserving their order."""
    return "".join(
        char
        for char in text
        if "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
    )


def validate_compressed_pdf(
    source_path: Path,
    candidate_path: Path,
) -> CompressionValidation:
    """Verify that compression preserved each meaningful PDF text layer.

    Image-only pages have no text invariant and therefore remain eligible for
    compression. Any validation/read failure is reported by the caller as a
    rejected candidate rather than silently sending an unchecked file onward.
    """
    source_path = Path(source_path)
    candidate_path = Path(candidate_path)

    with fitz.open(source_path) as source, fitz.open(candidate_path) as candidate:
        source_pages = source.page_count
        candidate_pages = candidate.page_count
        if source_pages != candidate_pages:
            return CompressionValidation(
                preserved=False,
                reason="page_count_mismatch",
                source_pages=source_pages,
                candidate_pages=candidate_pages,
                source_has_meaningful_text=False,
                minimum_text_similarity=0.0,
                pages=(),
            )

        page_results = []
        has_meaningful_text = False
        for page_index in range(source_pages):
            source_text = _normalize_text(source[page_index].get_text())
            candidate_text = _normalize_text(candidate[page_index].get_text())
            meaningful = len(source_text) >= MIN_MEANINGFUL_TEXT_CHARS
            has_meaningful_text = has_meaningful_text or meaningful

            if meaningful:
                similarity = SequenceMatcher(
                    None, source_text, candidate_text, autojunk=False
                ).ratio()
                source_cjk = _cjk_sequence(source_text)
                candidate_cjk = _cjk_sequence(candidate_text)
                cjk_preserved = not source_cjk or source_cjk == candidate_cjk
                preserved = (
                    bool(candidate_text)
                    and similarity >= MIN_TEXT_SIMILARITY
                    and cjk_preserved
                )
            else:
                source_cjk = _cjk_sequence(source_text)
                candidate_cjk = _cjk_sequence(candidate_text)
                similarity = 1.0
                cjk_preserved = True
                preserved = True

            page_results.append(
                PageTextValidation(
                    page=page_index + 1,
                    source_chars=len(source_text),
                    candidate_chars=len(candidate_text),
                    source_cjk_chars=len(source_cjk),
                    candidate_cjk_chars=len(candidate_cjk),
                    text_similarity=similarity,
                    cjk_preserved=cjk_preserved,
                    preserved=preserved,
                )
            )

    failed_pages = [page for page in page_results if not page.preserved]
    if failed_pages:
        reason = "text_not_preserved"
        preserved = False
    elif not has_meaningful_text:
        reason = "image_only_source"
        preserved = True
    else:
        reason = "text_preserved"
        preserved = True

    similarities = [
        page.text_similarity
        for page in page_results
        if page.source_chars >= MIN_MEANINGFUL_TEXT_CHARS
    ]
    return CompressionValidation(
        preserved=preserved,
        reason=reason,
        source_pages=source_pages,
        candidate_pages=candidate_pages,
        source_has_meaningful_text=has_meaningful_text,
        minimum_text_similarity=min(similarities, default=1.0),
        pages=tuple(page_results),
    )


def find_ghostscript() -> Optional[str]:
    """Find Ghostscript executable.

    Returns:
        Path to Ghostscript executable or None if not found.
    """
    # Common names
    names = ['gswin64c', 'gswin32c', 'gs', 'gswin64', 'gswin32']

    for name in names:
        path = shutil.which(name)
        if path:
            return path

    # Check common install locations on Windows
    import os
    if os.name == 'nt':
        common_paths = [
            Path('C:/Program Files/gs'),
            Path('C:/Program Files (x86)/gs'),
            Path('E:/gs-portable'),
        ]

        for base in common_paths:
            if base.exists():
                # Find the latest version
                versions = sorted(base.iterdir(), reverse=True)
                for version_dir in versions:
                    bin_dir = version_dir / 'bin'
                    if bin_dir.exists():
                        for name in ['gswin64c.exe', 'gswin32c.exe']:
                            exe = bin_dir / name
                            if exe.exists():
                                return str(exe)

    return None


def compress_pdf(
    input_path: Path,
    output_dir: Path,
    config=None,
    quality: str = "ebook",
) -> Path:
    """Compress PDF using Ghostscript.

    Args:
        input_path: Path to input PDF
        output_dir: Directory to save compressed PDF
        config: Config object (for ghostscript_path and quality)
        quality: Compression quality (screen/ebook/printer/prepress)

    Returns:
        Path to compressed PDF
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get Ghostscript path
    if config and config.compress.ghostscript_path:
        gs_path = config.compress.ghostscript_path
    else:
        gs_path = find_ghostscript()

    if not gs_path:
        raise RuntimeError("Ghostscript not found. Install from https://ghostscript.com/")

    # Get quality setting
    if config and config.compress.quality:
        quality = config.compress.quality

    # Quality presets
    quality_settings = {
        'screen': '/screen',  # 72 dpi, smallest size
        'ebook': '/ebook',    # 150 dpi, good balance
        'printer': '/printer',  # 300 dpi, high quality
        'prepress': '/prepress',  # 300 dpi, maximum quality
    }

    gs_quality = quality_settings.get(quality, '/ebook')

    # Output path with total count placeholder (will be set by caller)
    output_name = f"compressed_{input_path.stem}.pdf"
    output_path = output_dir / output_name

    # Ghostscript command
    cmd = [
        gs_path,
        '-sDEVICE=pdfwrite',
        f'-dPDFSETTINGS={gs_quality}',
        '-dCompatibilityLevel=1.4',
        '-dNOPAUSE',
        '-dQUIET',
        '-dBATCH',
        f'-sOutputFile={output_path}',
        str(input_path),
    ]

    # Run Ghostscript with timeout
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Ghostscript timeout (>300s). File may be too large or complex.")

    if result.returncode != 0:
        error_msg = result.stderr.strip() or f"Exit code {result.returncode}"
        raise RuntimeError(f"Ghostscript failed: {error_msg}")

    return output_path


def compress_batch(
    input_files: list,
    output_dir: Path,
    config=None,
    total_count: Optional[int] = None,
) -> list:
    """Compress multiple PDF files.

    Args:
        input_files: List of input PDF paths
        output_dir: Directory to save compressed PDFs
        config: Config object
        total_count: Total number of files (for naming)

    Returns:
        List of compressed PDF paths
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if total_count is None:
        total_count = len(input_files)

    compressed_files = []

    for i, input_path in enumerate(input_files, 1):
        # Rename with part number
        output_name = f"compressed_part_{i:03d}_of_{total_count:03d}.pdf"
        temp_output = compress_pdf(input_path, output_dir, config)
        final_output = output_dir / output_name
        temp_output.rename(final_output)
        compressed_files.append(final_output)

    return compressed_files
