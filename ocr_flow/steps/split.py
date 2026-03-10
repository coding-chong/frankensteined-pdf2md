#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PDF splitting module."""

from pathlib import Path
from typing import List

import fitz  # PyMuPDF


def split_pdf(
    pdf_path: Path,
    output_dir: Path,
    pages_per_part: int = 1,
) -> List[Path]:
    """Split PDF into smaller parts.

    Args:
        pdf_path: Path to input PDF
        output_dir: Directory to save split files
        pages_per_part: Number of pages per split file (1 for single-language, 2 for translated)

    Returns:
        List of paths to split PDF files
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    total_pages = doc.page_count
    total_parts = (total_pages + pages_per_part - 1) // pages_per_part

    split_files = []

    for start_page in range(0, total_pages, pages_per_part):
        part_num = start_page // pages_per_part + 1
        end_page = min(start_page + pages_per_part - 1, total_pages - 1)

        # Create sub-document with the specified pages
        sub_doc = fitz.open()
        sub_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)

        # Save with consistent naming
        output_name = f"part_{part_num:03d}.pdf"
        output_path = output_dir / output_name
        sub_doc.save(output_path)
        sub_doc.close()

        split_files.append(output_path)

    doc.close()
    return split_files


def get_page_count(pdf_path: Path) -> int:
    """Get the number of pages in a PDF."""
    doc = fitz.open(pdf_path)
    count = doc.page_count
    doc.close()
    return count


def has_text_layer(pdf_path: Path) -> bool:
    """Check if PDF has extractable text (vs scanned images).

    Returns:
        True if any page has extractable text, False otherwise.
    """
    doc = fitz.open(pdf_path)

    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = page.get_text()

        # If any page has meaningful text, it's not a pure scanned PDF
        if text.strip():
            doc.close()
            return True

    doc.close()
    return False


def detect_pdf_type(pdf_path: Path) -> str:
    """Detect if PDF is text or scanned.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        'text' if PDF has extractable text, 'scanned' otherwise
    """
    pdf_path = Path(pdf_path)
    if has_text_layer(pdf_path):
        return 'text'
    return 'scanned'
