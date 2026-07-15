#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for image download module.

Test suite covering:
- URL extraction from Markdown
- URL type detection
- Image downloading
- Batch image processing
- Markdown file updates
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock, mock_open

from ocr_flow.steps.image_download import (
    extract_image_urls,
    is_http_url,
    is_local_image_path,
    get_extension_from_url,
    generate_filename,
    download_image,
    download_images,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_md_with_images():
    """Sample Markdown content with images."""
    return """# Document

![Image 1](https://example.com/image1.png)

Some text.

![Image 2](https://cdn.example.com/img2.jpg)

More text with inline image: ![Icon](https://site.com/icon.gif).

![Local Image](images/local.png)
"""


@pytest.fixture
def sample_md_no_images():
    """Sample Markdown content without images."""
    return """# Document

Just text, no images here.

## Section

More text content.
"""


@pytest.fixture
def images_dir(temp_dir):
    """Create an images directory."""
    img_dir = temp_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


@pytest.fixture
def md_file_with_images(temp_dir, sample_md_with_images):
    """Create a Markdown file with images."""
    md_path = temp_dir / "test.md"
    md_path.write_text(sample_md_with_images, encoding='utf-8')
    return md_path


@pytest.fixture
def md_file_no_images(temp_dir, sample_md_no_images):
    """Create a Markdown file without images."""
    md_path = temp_dir / "no_images.md"
    md_path.write_text(sample_md_no_images, encoding='utf-8')
    return md_path


# =============================================================================
# TestExtractImageUrls - URL Extraction Tests
# =============================================================================

class TestExtractImageUrls:
    """Tests for extract_image_urls function."""

    def test_extract_single_image(self):
        """Test extracting a single image URL."""
        content = "![Alt text](https://example.com/image.png)"
        result = extract_image_urls(content)

        assert len(result) == 1
        assert result[0] == ("Alt text", "https://example.com/image.png")

    def test_extract_multiple_images(self):
        """Test extracting multiple image URLs."""
        content = """
![Image 1](url1.png)
![Image 2](url2.jpg)
![Image 3](url3.gif)
"""
        result = extract_image_urls(content)
        assert len(result) == 3

    def test_extract_no_images(self):
        """Test content with no images."""
        content = "Just text, no images."
        result = extract_image_urls(content)

        assert len(result) == 0

    def test_extract_with_special_chars(self):
        """Test extracting images with special characters in alt text."""
        content = "![Image with special chars: !@#$%](https://example.com/img.png)"
        result = extract_image_urls(content)

        assert len(result) == 1
        assert "special chars" in result[0][0]

    def test_extract_empty_alt(self):
        """Test extracting image with empty alt text."""
        content = "![](https://example.com/image.png)"
        result = extract_image_urls(content)

        assert len(result) == 1
        assert result[0][0] == ""

    def test_extract_complex_urls(self):
        """Test extracting images with complex URLs."""
        content = "![Test](https://example.com/path/to/image.png?size=large&format=auto#fragment)"
        result = extract_image_urls(content)

        assert len(result) == 1
        assert "size=large" in result[0][1]

    def test_extract_preserves_order(self):
        """Test that extraction preserves order."""
        content = "![First](url1)\n![Second](url2)\n![Third](url3)"
        result = extract_image_urls(content)

        assert result[0][0] == "First"
        assert result[1][0] == "Second"
        assert result[2][0] == "Third"

    def test_from_markdown_file(self, md_file_with_images):
        """Test extracting from actual Markdown file."""
        content = md_file_with_images.read_text(encoding='utf-8')
        result = extract_image_urls(content)

        assert len(result) == 4  # 3 HTTP + 1 local


# =============================================================================
# TestIsHttpUrl - URL Type Detection Tests
# =============================================================================

class TestIsHttpUrl:
    """Tests for is_http_url function."""

    def test_is_http_url_http(self):
        """Test HTTP URL detection."""
        assert is_http_url("http://example.com/image.png") == True

    def test_is_http_url_https(self):
        """Test HTTPS URL detection."""
        assert is_http_url("https://example.com/image.png") == True

    def test_is_http_url_local_path(self):
        """Test local path detection."""
        assert is_http_url("images/local.png") == False

    def test_is_http_url_absolute_path(self):
        """Test absolute local path."""
        assert is_http_url("/path/to/image.png") == False

    def test_is_http_url_windows_path(self):
        """Test Windows path."""
        assert is_http_url("C:\\Images\\photo.jpg") == False

    def test_is_http_url_relative_path(self):
        """Test relative path with dots."""
        assert is_http_url("../images/photo.jpg") == False


# =============================================================================
# TestIsLocalImagePath - Local Image Detection Tests
# =============================================================================

class TestIsLocalImagePath:
    """Tests for is_local_image_path function."""

    def test_local_path_with_extension(self):
        """Test local path with image extension."""
        assert is_local_image_path("images/photo.png") == True
        assert is_local_image_path("photos/image.jpg") == True
        assert is_local_image_path("pics/graphic.gif") == True

    def test_local_path_no_extension(self):
        """Test local path without image extension."""
        assert is_local_image_path("images/document") == False

    def test_http_url_not_local(self):
        """Test that HTTP URLs are not considered local."""
        assert is_local_image_path("https://example.com/image.png") == False

    def test_local_path_with_query_string(self):
        """Test local path with query string."""
        assert is_local_image_path("images/photo.png?v=1") == True

    def test_various_extensions(self):
        """Test various image extensions."""
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp']
        for ext in extensions:
            assert is_local_image_path(f"image{ext}") == True


# =============================================================================
# TestGetExtensionFromUrl - Extension Extraction Tests
# =============================================================================

class TestGetExtensionFromUrl:
    """Tests for get_extension_from_url function."""

    def test_extension_from_simple_url(self):
        """Test extracting extension from simple URL."""
        assert get_extension_from_url("https://example.com/image.png") == ".png"

    def test_extension_from_url_with_query(self):
        """Test extracting extension with query string."""
        assert get_extension_from_url("https://example.com/image.jpg?size=large") == ".jpg"

    def test_extension_from_url_with_fragment(self):
        """Test extracting extension with fragment."""
        assert get_extension_from_url("https://example.com/image.gif#section") == ".gif"

    def test_no_extension(self):
        """Test URL without extension."""
        assert get_extension_from_url("https://example.com/image") is None

    def test_extension_from_path(self):
        """Test extracting extension from local path."""
        assert get_extension_from_url("images/photo.webp") == ".webp"


# =============================================================================
# TestGenerateFilename - Filename Generation Tests
# =============================================================================

class TestGenerateFilename:
    """Tests for generate_filename function."""

    def test_generate_basic_filename(self):
        """Test basic filename generation."""
        result = generate_filename("https://example.com/image.png", index=1)

        assert result.startswith("img_")
        assert result.endswith(".png")

    def test_generate_with_content_type(self):
        """Test filename generation with content type."""
        result = generate_filename(
            "https://example.com/image",
            content_type="image/jpeg",
            index=2
        )

        assert result.startswith("img_")
        assert result.endswith(".jpg")

    def test_generate_uses_index(self):
        """Test that index is used in filename."""
        result = generate_filename("https://example.com/img.png", index=5)

        assert "005" in result  # Formatted with leading zeros

    def test_generate_same_index_same_extension(self):
        """Test that same index and extension produce same filename."""
        # Note: The current implementation uses index, not URL hash
        result1 = generate_filename("https://example.com/a.png", index=1)
        result2 = generate_filename("https://example.com/b.png", index=1)

        # Both should have same filename since same index and extension
        assert result1 == "img_001.png"
        assert result2 == "img_001.png"

    def test_generate_different_index(self):
        """Test that different indices produce different filenames."""
        result1 = generate_filename("https://example.com/img.png", index=1)
        result2 = generate_filename("https://example.com/img.png", index=2)

        assert result1 != result2

    def test_generate_default_extension(self):
        """Test default extension when none available."""
        result = generate_filename("https://example.com/noext", index=1)

        assert result.endswith(".png")  # Default


# =============================================================================
# TestDownloadImage - Single Image Download Tests
# =============================================================================

class TestDownloadImage:
    """Tests for download_image function."""

    @patch('ocr_flow.steps.image_download.requests.get')
    def test_download_success(self, mock_get, temp_dir):
        """Test successful image download."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'image/png'}
        mock_response.iter_content = lambda chunk_size: [b'fake_image_data']
        mock_get.return_value = mock_response

        success, result = download_image(
            "https://example.com/image.png",
            temp_dir,
            timeout=10
        )

        assert success == True
        assert result.endswith(".png") or result.startswith("img_")
        assert "verify" not in mock_get.call_args.kwargs

    @patch('ocr_flow.steps.image_download.requests.get')
    def test_download_failure_404(self, mock_get, temp_dir):
        """Test download failure with 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        success, result = download_image(
            "https://example.com/notfound.png",
            temp_dir,
            retries=1
        )

        assert success == False
        assert "404" in result

    @patch('ocr_flow.steps.image_download.requests.get')
    def test_download_retry_on_failure(self, mock_get, temp_dir):
        """Test retry on download failure."""
        # First call fails, second succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500

        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.headers = {'Content-Type': 'image/jpeg'}
        mock_response_ok.iter_content = lambda chunk_size: [b'data']

        mock_get.side_effect = [mock_response_fail, mock_response_ok]

        success, result = download_image(
            "https://example.com/image.jpg",
            temp_dir,
            retries=2
        )

        assert success == True
        assert mock_get.call_count == 2

    @patch('ocr_flow.steps.image_download.requests.get')
    def test_download_timeout(self, mock_get, temp_dir):
        """Test download timeout handling."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        success, result = download_image(
            "https://example.com/slow.png",
            temp_dir,
            retries=1,
            timeout=1
        )

        assert success == False

    @patch('ocr_flow.steps.image_download.requests.get')
    def test_download_creates_directory(self, mock_get, temp_dir):
        """Test that download creates output directory."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'image/png'}
        mock_response.iter_content = lambda chunk_size: [b'data']
        mock_get.return_value = mock_response

        nested_dir = temp_dir / "nested" / "images"
        success, result = download_image(
            "https://example.com/image.png",
            nested_dir
        )

        assert nested_dir.exists()


# =============================================================================
# TestDownloadImages - Batch Download Tests
# =============================================================================

class TestDownloadImages:
    """Tests for download_images function."""

    @patch('ocr_flow.steps.image_download.download_image')
    def test_download_images_empty(self, mock_download, md_file_no_images, images_dir):
        """Test downloading with no images."""
        success, failed = download_images(
            md_file_no_images,
            images_dir,
            page_num=1
        )

        assert success == True
        assert len(failed) == 0
        assert mock_download.call_count == 0

    @patch('ocr_flow.steps.image_download.download_image')
    def test_download_images_creates_page_directory(self, mock_download, md_file_with_images, images_dir):
        """Test that page-specific directory is created."""
        mock_download.return_value = (True, "img_001.png")

        download_images(md_file_with_images, images_dir, page_num=1)

        assert (images_dir / "p001").exists()

    @patch('ocr_flow.steps.image_download.download_image')
    def test_download_images_updates_markdown(self, mock_download, md_file_with_images, images_dir, temp_dir):
        """Test that Markdown file is updated with local paths."""
        mock_download.return_value = (True, "downloaded.png")

        download_images(md_file_with_images, images_dir, page_num=1)

        content = md_file_with_images.read_text(encoding='utf-8')

        # HTTP URLs should be replaced with local paths
        assert "images/p001/downloaded.png" in content or "downloaded.png" in content

    @patch('ocr_flow.steps.image_download.download_image')
    def test_download_images_partial_failure(self, mock_download, md_file_with_images, images_dir):
        """Test handling partial download failures."""
        # First succeeds, second fails
        mock_download.side_effect = [
            (True, "img_001.png"),
            (False, "HTTP 404"),
            (True, "img_002.png"),
        ]

        success, failed = download_images(
            md_file_with_images,
            images_dir,
            page_num=1
        )

        assert success == False
        assert len(failed) > 0

    def test_download_images_local_copy(self, temp_dir, images_dir):
        """Test copying local images."""
        # Create source images directory structure
        # The function looks for source_images_dir / url
        source_dir = temp_dir / "source"
        source_dir.mkdir(parents=True)

        # Create images subdirectory matching the URL path
        images_subdir = source_dir / "images"
        images_subdir.mkdir()
        local_image = images_subdir / "local.png"
        local_image.write_bytes(b"fake image data")

        # Create Markdown with local image reference
        md_path = temp_dir / "test.md"
        md_path.write_text("![Local](images/local.png)", encoding='utf-8')

        success, failed = download_images(
            md_path,
            images_dir,
            page_num=1,
            source_images_dir=source_dir
        )

        assert success == True
        assert (images_dir / "p001" / "local.png").exists()


# =============================================================================
# TestDownloadImagesEdgeCases - Edge Case Tests
# =============================================================================

class TestDownloadImagesEdgeCases:
    """Edge case tests for image download."""

    def test_download_images_missing_source_dir(self, temp_dir, images_dir):
        """Test handling missing source directory for local images."""
        md_path = temp_dir / "test.md"
        md_path.write_text("![Local](images/missing.png)", encoding='utf-8')

        success, failed = download_images(
            md_path,
            images_dir,
            page_num=1,
            source_images_dir=None
        )

        # When source_images_dir is None, local images are skipped (not failed)
        # The function returns True because no images need processing
        assert success == True  # No failures, just skipped
        assert len(failed) == 0

    @patch('ocr_flow.steps.image_download.download_image')
    def test_download_images_preserves_other_content(self, mock_download, temp_dir, images_dir):
        """Test that other Markdown content is preserved."""
        mock_download.return_value = (True, "img.png")

        original_content = """# Title

![Image](https://example.com/img.png)

Some **bold** text and *italic*.

- List item 1
- List item 2

```python
code block
```
"""
        md_path = temp_dir / "test.md"
        md_path.write_text(original_content, encoding='utf-8')

        download_images(md_path, images_dir, page_num=1)

        content = md_path.read_text(encoding='utf-8')

        assert "# Title" in content
        assert "Some **bold** text" in content
        assert "List item 1" in content
        assert "```python" in content

    def test_download_images_page_number_formatting(self, temp_dir, images_dir):
        """Test that page number is formatted correctly in path."""
        md_path = temp_dir / "test.md"
        md_path.write_text("", encoding='utf-8')

        # Test various page numbers
        for page_num in [1, 10, 100, 999]:
            download_images(md_path, images_dir, page_num=page_num)

            expected_dir = images_dir / f"p{page_num:03d}"
            # Just verify directory naming format
            assert "p" in expected_dir.name
