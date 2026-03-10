#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for PDF splitting module."""

import pytest
from pathlib import Path
import tempfile
import shutil

from ocr_flow.steps.split import (
    split_pdf,
    get_page_count,
    has_text_layer,
    detect_pdf_type,
)


# Test fixtures
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


class TestGetPageCount:
    """Tests for get_page_count function."""

    def test_text_pdf_page_count(self, text_pdf):
        """Test page count for text PDF."""
        assert get_page_count(text_pdf) == 1

    def test_scanned_pdf_page_count(self, scanned_pdf):
        """Test page count for scanned PDF."""
        assert get_page_count(scanned_pdf) == 1


class TestHasTextLayer:
    """Tests for has_text_layer function."""

    def test_text_pdf_has_text_layer(self, text_pdf):
        """Test that text PDF has extractable text."""
        assert has_text_layer(text_pdf) == True

    def test_scanned_pdf_no_text_layer(self, scanned_pdf):
        """Test that scanned PDF has no extractable text."""
        assert has_text_layer(scanned_pdf) == False


class TestDetectPdfType:
    """Tests for detect_pdf_type function."""

    def test_detect_text_pdf(self, text_pdf):
        """Test detection of text PDF."""
        assert detect_pdf_type(text_pdf) == 'text'

    def test_detect_scanned_pdf(self, scanned_pdf):
        """Test detection of scanned PDF."""
        assert detect_pdf_type(scanned_pdf) == 'scanned'


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
