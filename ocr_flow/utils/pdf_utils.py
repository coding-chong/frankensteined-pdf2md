#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PDF utility functions."""

from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF


def get_page_count(pdf_path: Path) -> int:
    """Get the number of pages in a PDF."""
    doc = fitz.open(pdf_path)
    try:
        count = doc.page_count
        return count
    finally:
        doc.close()


def has_text_layer(pdf_path: Path) -> bool:
    """Check if PDF has extractable text (vs scanned images).

    Returns:
        True if any page has extractable text, False otherwise.
    """
    doc = fitz.open(pdf_path)
    try:
        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = page.get_text()

            # If any page has meaningful text, it's not a pure scanned PDF
            if text.strip():
                return True

        return False
    finally:
        doc.close()


def get_pdf_info(pdf_path: Path) -> dict:
    """Get basic info about a PDF file.

    Returns:
        Dict with page_count, has_text, file_size
    """
    pdf_path = Path(pdf_path)

    doc = fitz.open(pdf_path)
    try:
        page_count = doc.page_count

        # Check for text in the same open document
        has_text = False
        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                has_text = True
                break

        # File size
        file_size = pdf_path.stat().st_size

        return {
            'page_count': page_count,
            'has_text': has_text,
            'file_size': file_size,
            'pdf_type': 'text' if has_text else 'scanned',
        }
    finally:
        doc.close()


def merge_pdfs(pdf_paths: list, output_path: Path) -> Path:
    """Merge multiple PDFs into one.

    Args:
        pdf_paths: List of PDF paths to merge
        output_path: Path to save merged PDF

    Returns:
        Path to merged PDF
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = fitz.open()

    for pdf_path in pdf_paths:
        pdf_path = Path(pdf_path)
        doc = fitz.open(pdf_path)
        result.insert_pdf(doc)
        doc.close()

    result.save(output_path)
    result.close()

    return output_path


def extract_page(pdf_path: Path, page_num: int, output_path: Path) -> Path:
    """Extract a single page from a PDF.

    Args:
        pdf_path: Path to source PDF
        page_num: Page number (0-indexed)
        output_path: Path to save extracted page

    Returns:
        Path to extracted PDF
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    src = fitz.open(pdf_path)
    try:
        dst = fitz.open()
        try:
            if 0 <= page_num < src.page_count:
                dst.insert_pdf(src, from_page=page_num, to_page=page_num)
            dst.save(output_path)
        finally:
            dst.close()
    finally:
        src.close()

    return output_path
