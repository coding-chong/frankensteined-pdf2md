#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for PDF splitting module.

Extended test suite covering:
- Basic splitting functionality
- Multi-page splitting
- PDF type detection
- Error handling
- Edge cases
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import fitz  # PyMuPDF

from ocr_flow.steps.split import (
    split_pdf,
    get_page_count,
    has_text_layer,
    detect_pdf_type,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def test_assets_dir():
    """Get test assets directory."""
    return Path(__file__).parent.parent / "test_assets"


@pytest.fixture
def text_pdf(test_assets_dir):
    """Path to text PDF."""
    return test_assets_dir / "test_page_text.pdf"


@pytest.fixture
def scanned_pdf(test_assets_dir):
    """Path to scanned PDF."""
    return test_assets_dir / "test_page_scanned.pdf"


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def multi_page_pdf(temp_dir):
    """Create a multi-page PDF for testing."""
    pdf_path = temp_dir / "multi_page.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((100, 100), f"Page {i+1}", fontsize=24)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def large_pdf(temp_dir):
    """Create a large PDF (20 pages) for performance testing."""
    pdf_path = temp_dir / "large.pdf"
    doc = fitz.open()
    for i in range(20):
        page = doc.new_page()
        page.insert_text((100, 100), f"Page {i+1} of 20", fontsize=24)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def corrupted_pdf(temp_dir):
    """Create a corrupted PDF file."""
    pdf_path = temp_dir / "corrupted.pdf"
    pdf_path.write_bytes(b"Not a valid PDF content!")
    return pdf_path


@pytest.fixture
def empty_file(temp_dir):
    """Create an empty file."""
    file_path = temp_dir / "empty.pdf"
    file_path.write_bytes(b"")
    return file_path


@pytest.fixture
def pdf_with_images_only(temp_dir):
    """Create a PDF with only images (no text layer)."""
    pdf_path = temp_dir / "image_only.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # Draw a rectangle as a placeholder for image
    rect = fitz.Rect(100, 100, 400, 400)
    page.draw_rect(rect, color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
    doc.save(pdf_path)
    doc.close()
    return pdf_path


# =============================================================================
# TestGetPageCount - Basic Tests
# =============================================================================

class TestGetPageCount:
    """Tests for get_page_count function."""

    def test_text_pdf_page_count(self, text_pdf):
        """Test page count for text PDF."""
        assert get_page_count(text_pdf) == 1

    def test_scanned_pdf_page_count(self, scanned_pdf):
        """Test page count for scanned PDF."""
        assert get_page_count(scanned_pdf) == 1

    def test_multi_page_pdf_count(self, multi_page_pdf):
        """Test page count for multi-page PDF."""
        assert get_page_count(multi_page_pdf) == 5

    def test_large_pdf_count(self, large_pdf):
        """Test page count for large PDF."""
        assert get_page_count(large_pdf) == 20


# =============================================================================
# TestHasTextLayer - Text Detection Tests
# =============================================================================

class TestHasTextLayer:
    """Tests for has_text_layer function."""

    def test_text_pdf_has_text_layer(self, text_pdf):
        """Test that text PDF has extractable text."""
        assert has_text_layer(text_pdf) == True

    def test_scanned_pdf_no_text_layer(self, scanned_pdf):
        """Test that scanned PDF has no extractable text."""
        assert has_text_layer(scanned_pdf) == False

    def test_image_only_pdf_no_text(self, pdf_with_images_only):
        """Test that image-only PDF has no text layer."""
        assert has_text_layer(pdf_with_images_only) == False

    def test_multi_page_pdf_has_text(self, multi_page_pdf):
        """Test that multi-page PDF with text returns True."""
        assert has_text_layer(multi_page_pdf) == True


# =============================================================================
# TestDetectPdfType - Type Detection Tests
# =============================================================================

class TestDetectPdfType:
    """Tests for detect_pdf_type function."""

    def test_detect_text_pdf(self, text_pdf):
        """Test detection of text PDF."""
        assert detect_pdf_type(text_pdf) == 'text'

    def test_detect_scanned_pdf(self, scanned_pdf):
        """Test detection of scanned PDF."""
        assert detect_pdf_type(scanned_pdf) == 'scanned'

    def test_detect_image_only_pdf(self, pdf_with_images_only):
        """Test detection of image-only PDF as scanned."""
        assert detect_pdf_type(pdf_with_images_only) == 'scanned'

    def test_detect_multi_page_text_pdf(self, multi_page_pdf):
        """Test detection of multi-page text PDF."""
        assert detect_pdf_type(multi_page_pdf) == 'text'


# =============================================================================
# TestSplitPdf - Basic Splitting Tests
# =============================================================================

class TestSplitPdf:
    """Tests for split_pdf function."""

    def test_split_single_page_pdf(self, text_pdf, temp_dir):
        """Test splitting a single page PDF."""
        output_dir = temp_dir / "split"
        result = split_pdf(text_pdf, output_dir, pages_per_part=1)

        assert len(result) == 1
        assert result[0].exists()
        assert result[0].name == "part_001.pdf"

    def test_split_output_directory_created(self, text_pdf, temp_dir):
        """Test that output directory is created."""
        output_dir = temp_dir / "nested" / "split"
        result = split_pdf(text_pdf, output_dir, pages_per_part=1)

        assert output_dir.exists()
        assert len(result) == 1

    def test_split_preserves_content(self, text_pdf, temp_dir):
        """Test that split preserves page count."""
        output_dir = temp_dir / "split"
        result = split_pdf(text_pdf, output_dir, pages_per_part=1)

        # Check the split file has correct page count
        assert get_page_count(result[0]) == 1


# =============================================================================
# TestSplitPdfAdvanced - Advanced Splitting Tests
# =============================================================================

class TestSplitPdfAdvanced:
    """Advanced tests for split_pdf function."""

    def test_split_multi_page_pdf(self, multi_page_pdf, temp_dir):
        """Test splitting multi-page PDF into single pages."""
        output_dir = temp_dir / "split"
        result = split_pdf(multi_page_pdf, output_dir, pages_per_part=1)

        assert len(result) == 5
        for i, path in enumerate(result, 1):
            assert path.exists()
            assert path.name == f"part_{i:03d}.pdf"
            assert get_page_count(path) == 1

    def test_split_with_pages_per_part_2(self, multi_page_pdf, temp_dir):
        """Test splitting with 2 pages per part (translation mode)."""
        output_dir = temp_dir / "split"
        result = split_pdf(multi_page_pdf, output_dir, pages_per_part=2)

        # 5 pages / 2 per part = 3 parts (2+2+1)
        assert len(result) == 3

        # First two parts should have 2 pages each
        assert get_page_count(result[0]) == 2
        assert get_page_count(result[1]) == 2
        # Last part has 1 page
        assert get_page_count(result[2]) == 1

    def test_split_with_pages_per_part_3(self, temp_dir):
        """Test splitting with 3 pages per part."""
        # Create a 10-page PDF
        pdf_path = temp_dir / "ten_pages.pdf"
        doc = fitz.open()
        for i in range(10):
            page = doc.new_page()
            page.insert_text((100, 100), f"Page {i+1}")
        doc.save(pdf_path)
        doc.close()

        output_dir = temp_dir / "split"
        result = split_pdf(pdf_path, output_dir, pages_per_part=3)

        # 10 pages / 3 per part = 4 parts (3+3+3+1)
        assert len(result) == 4
        assert get_page_count(result[0]) == 3
        assert get_page_count(result[1]) == 3
        assert get_page_count(result[2]) == 3
        assert get_page_count(result[3]) == 1

    def test_split_output_naming_convention(self, multi_page_pdf, temp_dir):
        """Test output file naming convention part_001.pdf, part_002.pdf."""
        output_dir = temp_dir / "split"
        result = split_pdf(multi_page_pdf, output_dir, pages_per_part=1)

        expected_names = ["part_001.pdf", "part_002.pdf", "part_003.pdf", "part_004.pdf", "part_005.pdf"]
        actual_names = [p.name for p in result]
        assert actual_names == expected_names

    def test_split_large_pdf(self, large_pdf, temp_dir):
        """Test splitting a large PDF (performance test)."""
        output_dir = temp_dir / "split"
        result = split_pdf(large_pdf, output_dir, pages_per_part=1)

        assert len(result) == 20
        for path in result:
            assert path.exists()
            assert get_page_count(path) == 1

    def test_split_preserves_content_integrity(self, multi_page_pdf, temp_dir):
        """Test that split files contain correct content."""
        output_dir = temp_dir / "split"
        result = split_pdf(multi_page_pdf, output_dir, pages_per_part=1)

        # Verify each split file contains the expected page content
        for i, path in enumerate(result, 1):
            doc = fitz.open(path)
            text = doc[0].get_text()
            doc.close()
            assert f"Page {i}" in text


# =============================================================================
# TestSplitPdfErrorHandling - Error Handling Tests
# =============================================================================

class TestSplitPdfErrorHandling:
    """Error handling tests for split_pdf function."""

    def test_split_corrupted_pdf(self, corrupted_pdf, temp_dir):
        """Test splitting corrupted PDF raises appropriate error."""
        output_dir = temp_dir / "split"
        with pytest.raises(Exception):
            split_pdf(corrupted_pdf, output_dir, pages_per_part=1)

    def test_split_nonexistent_file(self, temp_dir):
        """Test splitting non-existent file raises appropriate error."""
        nonexistent = temp_dir / "nonexistent.pdf"
        output_dir = temp_dir / "split"
        with pytest.raises(Exception):
            split_pdf(nonexistent, output_dir, pages_per_part=1)

    def test_split_empty_file(self, empty_file, temp_dir):
        """Test splitting empty file raises appropriate error."""
        output_dir = temp_dir / "split"
        with pytest.raises(Exception):
            split_pdf(empty_file, output_dir, pages_per_part=1)

    def test_get_page_count_corrupted_pdf(self, corrupted_pdf):
        """Test page count on corrupted PDF raises error."""
        with pytest.raises(Exception):
            get_page_count(corrupted_pdf)

    def test_has_text_layer_invalid_pdf(self, corrupted_pdf):
        """Test text layer detection on invalid PDF."""
        with pytest.raises(Exception):
            has_text_layer(corrupted_pdf)


# =============================================================================
# TestSplitPdfEdgeCases - Edge Case Tests
# =============================================================================

class TestSplitPdfEdgeCases:
    """Edge case tests for split_pdf function."""

    def test_split_existing_output_dir(self, text_pdf, temp_dir):
        """Test splitting when output directory already exists."""
        output_dir = temp_dir / "existing"
        output_dir.mkdir()

        # Create an existing file in the directory
        existing_file = output_dir / "old_file.pdf"
        existing_file.write_bytes(b"old content")

        result = split_pdf(text_pdf, output_dir, pages_per_part=1)

        assert len(result) == 1
        # Old file should still exist
        assert existing_file.exists()

    def test_split_overwrites_existing_parts(self, text_pdf, temp_dir):
        """Test that split overwrites existing part files."""
        output_dir = temp_dir / "split"

        # First split
        result1 = split_pdf(text_pdf, output_dir, pages_per_part=1)

        # Create a modified version of the PDF
        new_pdf = temp_dir / "new.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "New Content")
        doc.save(new_pdf)
        doc.close()

        # Second split to same directory
        result2 = split_pdf(new_pdf, output_dir, pages_per_part=1)

        # Should have new content
        doc = fitz.open(result2[0])
        text = doc[0].get_text()
        doc.close()
        assert "New Content" in text

    def test_split_pages_per_part_larger_than_pages(self, text_pdf, temp_dir):
        """Test splitting when pages_per_part exceeds total pages."""
        output_dir = temp_dir / "split"
        # Single page PDF with pages_per_part=10
        result = split_pdf(text_pdf, output_dir, pages_per_part=10)

        assert len(result) == 1
        assert get_page_count(result[0]) == 1

    def test_split_creates_parent_directories(self, text_pdf, temp_dir):
        """Test that split creates nested parent directories."""
        output_dir = temp_dir / "a" / "b" / "c" / "split"
        result = split_pdf(text_pdf, output_dir, pages_per_part=1)

        assert output_dir.exists()
        assert len(result) == 1
