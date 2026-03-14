#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for PDF utility functions."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from ocr_flow.utils.pdf_utils import (
    get_page_count,
    has_text_layer,
    get_pdf_info,
    merge_pdfs,
    extract_page,
)


class TestGetPageCount:
    """Tests for get_page_count function."""

    def test_get_page_count_single_page(self, tmp_path):
        """Test getting page count from a single-page PDF."""
        # Create a minimal valid PDF using PyMuPDF
        import fitz
        pdf_path = tmp_path / "single.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        result = get_page_count(pdf_path)
        assert result == 1

    def test_get_page_count_multiple_pages(self, tmp_path):
        """Test getting page count from a multi-page PDF."""
        import fitz
        pdf_path = tmp_path / "multi.pdf"
        doc = fitz.open()
        for _ in range(5):
            doc.new_page()
        doc.save(pdf_path)
        doc.close()

        result = get_page_count(pdf_path)
        assert result == 5

    def test_get_page_count_accepts_string_path(self, tmp_path):
        """Test that function accepts string path (not just Path)."""
        import fitz
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        # Pass as string, not Path
        result = get_page_count(str(pdf_path))
        assert result == 1


class TestHasTextLayer:
    """Tests for has_text_layer function."""

    def test_has_text_layer_with_text(self, tmp_path):
        """Test detection of text layer in PDF with text."""
        import fitz
        pdf_path = tmp_path / "with_text.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Insert text using text writer
        text = "Hello, World!"
        page.insert_text((50, 50), text)
        doc.save(pdf_path)
        doc.close()

        result = has_text_layer(pdf_path)
        assert result is True

    def test_has_text_layer_without_text(self, tmp_path):
        """Test detection of text layer in PDF without text (blank)."""
        import fitz
        pdf_path = tmp_path / "blank.pdf"
        doc = fitz.open()
        doc.new_page()  # Blank page
        doc.save(pdf_path)
        doc.close()

        result = has_text_layer(pdf_path)
        assert result is False

    def test_has_text_layer_only_whitespace(self, tmp_path):
        """Test that whitespace-only text is treated as no text."""
        import fitz
        pdf_path = tmp_path / "whitespace.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "   \n\t  ")
        doc.save(pdf_path)
        doc.close()

        result = has_text_layer(pdf_path)
        assert result is False


class TestGetPdfInfo:
    """Tests for get_pdf_info function."""

    def test_get_pdf_info_basic(self, tmp_path):
        """Test getting basic PDF info."""
        import fitz
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Sample text")
        doc.save(pdf_path)
        doc.close()

        result = get_pdf_info(pdf_path)

        assert result['page_count'] == 1
        assert result['has_text'] is True
        assert result['file_size'] > 0
        assert result['pdf_type'] == 'text'

    def test_get_pdf_info_scanned_type(self, tmp_path):
        """Test that blank PDF is detected as scanned."""
        import fitz
        pdf_path = tmp_path / "scanned.pdf"
        doc = fitz.open()
        doc.new_page()  # Blank page
        doc.save(pdf_path)
        doc.close()

        result = get_pdf_info(pdf_path)

        assert result['has_text'] is False
        assert result['pdf_type'] == 'scanned'

    def test_get_pdf_info_multiple_pages(self, tmp_path):
        """Test info for multi-page PDF."""
        import fitz
        pdf_path = tmp_path / "multi.pdf"
        doc = fitz.open()
        for i in range(3):
            doc.new_page()
        doc.save(pdf_path)
        doc.close()

        result = get_pdf_info(pdf_path)

        assert result['page_count'] == 3


class TestMergePdfs:
    """Tests for merge_pdfs function."""

    def test_merge_pdfs_single_file(self, tmp_path):
        """Test merging a single PDF (edge case)."""
        import fitz
        # Create single-page PDF
        pdf1 = tmp_path / "one.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf1)
        doc.close()

        output_path = tmp_path / "merged.pdf"
        result = merge_pdfs([pdf1], output_path)

        assert result == output_path
        assert output_path.exists()
        assert get_page_count(output_path) == 1

    def test_merge_pdfs_multiple_files(self, tmp_path):
        """Test merging multiple PDFs."""
        import fitz
        pdf_files = []
        for i in range(3):
            pdf_path = tmp_path / f"file{i}.pdf"
            doc = fitz.open()
            doc.new_page()
            doc.save(pdf_path)
            doc.close()
            pdf_files.append(pdf_path)

        output_path = tmp_path / "merged.pdf"
        result = merge_pdfs(pdf_files, output_path)

        assert result == output_path
        assert get_page_count(output_path) == 3

    def test_merge_pdfs_creates_parent_dir(self, tmp_path):
        """Test that merge_pdfs creates parent directory if needed."""
        import fitz
        pdf1 = tmp_path / "one.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf1)
        doc.close()

        output_path = tmp_path / "subdir" / "nested" / "merged.pdf"
        result = merge_pdfs([pdf1], output_path)

        assert output_path.exists()

    def test_merge_pdfs_accepts_string_paths(self, tmp_path):
        """Test that merge_pdfs accepts string paths."""
        import fitz
        pdf1 = tmp_path / "one.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf1)
        doc.close()

        output_path = tmp_path / "merged.pdf"
        # Pass string paths
        result = merge_pdfs([str(pdf1)], str(output_path))

        assert result == output_path


class TestExtractPage:
    """Tests for extract_page function."""

    def test_extract_first_page(self, tmp_path):
        """Test extracting the first page (index 0)."""
        import fitz
        # Create 3-page PDF
        source = tmp_path / "source.pdf"
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((50, 50), f"Page {i}")
        doc.save(source)
        doc.close()

        output = tmp_path / "extracted.pdf"
        result = extract_page(source, 0, output)

        assert result == output
        assert output.exists()
        assert get_page_count(output) == 1

    def test_extract_middle_page(self, tmp_path):
        """Test extracting a middle page."""
        import fitz
        source = tmp_path / "source.pdf"
        doc = fitz.open()
        for i in range(5):
            doc.new_page()
        doc.save(source)
        doc.close()

        output = tmp_path / "extracted.pdf"
        result = extract_page(source, 2, output)

        assert get_page_count(output) == 1

    def test_extract_last_page(self, tmp_path):
        """Test extracting the last page."""
        import fitz
        source = tmp_path / "source.pdf"
        doc = fitz.open()
        for i in range(3):
            doc.new_page()
        doc.save(source)
        doc.close()

        output = tmp_path / "extracted.pdf"
        result = extract_page(source, 2, output)

        assert get_page_count(output) == 1

    def test_extract_invalid_page_raises_error(self, tmp_path):
        """Test that invalid page index raises ValueError (PyMuPDF limitation)."""
        import fitz
        source = tmp_path / "source.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(source)
        doc.close()

        output = tmp_path / "extracted.pdf"
        # Page 10 doesn't exist in 1-page PDF
        # PyMuPDF raises ValueError when trying to save empty document
        with pytest.raises(ValueError, match="cannot save with zero pages"):
            extract_page(source, 10, output)

    def test_extract_negative_page_raises_error(self, tmp_path):
        """Test that negative page index raises ValueError."""
        import fitz
        source = tmp_path / "source.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(source)
        doc.close()

        output = tmp_path / "extracted.pdf"
        with pytest.raises(ValueError, match="cannot save with zero pages"):
            extract_page(source, -1, output)

    def test_extract_creates_parent_dir(self, tmp_path):
        """Test that extract_page creates parent directory."""
        import fitz
        source = tmp_path / "source.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(source)
        doc.close()

        output = tmp_path / "nested" / "subdir" / "extracted.pdf"
        result = extract_page(source, 0, output)

        assert output.exists()