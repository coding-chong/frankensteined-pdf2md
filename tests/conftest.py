#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared fixtures for OCR Flow tests.

This module contains all shared fixtures used across test files.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import json
import fitz  # PyMuPDF

from ocr_flow.config import Config, UmiOcrConfig, BabelDocConfig, CompressConfig, MinerUConfig, PostProcessConfig
from ocr_flow.state import State, StateManager


# =============================================================================
# Directory Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs.

    Yields:
        Path to temporary directory (cleaned up after test)
    """
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def test_assets_dir():
    """Get test assets directory.

    Returns:
        Path to test_assets directory
    """
    return Path(__file__).parent.parent / "test_assets"


# =============================================================================
# PDF Fixtures
# =============================================================================

@pytest.fixture
def text_pdf(test_assets_dir):
    """Path to text PDF (has extractable text layer).

    Args:
        test_assets_dir: Path to test assets directory

    Returns:
        Path to text PDF file
    """
    return test_assets_dir / "test_page_text.pdf"


@pytest.fixture
def scanned_pdf(test_assets_dir):
    """Path to scanned PDF (no text layer, image-only).

    Args:
        test_assets_dir: Path to test assets directory

    Returns:
        Path to scanned PDF file
    """
    return test_assets_dir / "test_page_scanned.pdf"


@pytest.fixture
def multi_page_pdf(temp_dir):
    """Create a multi-page PDF for testing.

    Creates a 5-page PDF with text content.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to multi-page PDF file
    """
    pdf_path = temp_dir / "multi_page.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((100, 100), f"Page {i+1}", fontsize=24)
        page.insert_text((100, 150), f"This is content for page {i+1}." * 5, fontsize=12)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def single_page_pdf(temp_dir):
    """Create a single-page PDF for testing.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to single-page PDF file
    """
    pdf_path = temp_dir / "single_page.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Single Page Content", fontsize=24)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def large_multi_page_pdf(temp_dir):
    """Create a large multi-page PDF (20 pages) for performance testing.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to large PDF file
    """
    pdf_path = temp_dir / "large_multi_page.pdf"
    doc = fitz.open()
    for i in range(20):
        page = doc.new_page()
        page.insert_text((100, 100), f"Page {i+1} of 20", fontsize=24)
        # Add more content for realism
        for j in range(10):
            page.insert_text((100, 150 + j * 20), f"Line {j+1} on page {i+1}." * 3, fontsize=10)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def corrupted_pdf(temp_dir):
    """Create a corrupted PDF file for error handling tests.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to corrupted PDF file
    """
    pdf_path = temp_dir / "corrupted.pdf"
    pdf_path.write_bytes(b"Not a valid PDF content! This file is intentionally corrupted.")
    return pdf_path


@pytest.fixture
def empty_pdf(temp_dir):
    """Create an empty file with .pdf extension.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to empty PDF file
    """
    pdf_path = temp_dir / "empty.pdf"
    pdf_path.write_bytes(b"")
    return pdf_path


@pytest.fixture
def minimal_pdf(temp_dir):
    """Create a minimal valid PDF.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to minimal PDF file
    """
    pdf_path = temp_dir / "minimal.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF")
    return pdf_path


@pytest.fixture
def mixed_content_pdf(temp_dir):
    """Create a PDF with mixed content (text and placeholder for images).

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to mixed content PDF file
    """
    pdf_path = temp_dir / "mixed_content.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # Add text
    page.insert_text((100, 100), "Document with Mixed Content", fontsize=24)
    page.insert_text((100, 150), "This page contains both text and image placeholders.", fontsize=12)
    # Draw a rectangle as placeholder for image
    rect = fitz.Rect(100, 200, 300, 400)
    page.draw_rect(rect, color=(0.8, 0.8, 0.8), fill=(0.9, 0.9, 0.9))
    page.insert_text((120, 300), "[Image Placeholder]", fontsize=14, color=(0.5, 0.5, 0.5))
    doc.save(pdf_path)
    doc.close()
    return pdf_path


# =============================================================================
# Markdown Fixtures
# =============================================================================

@pytest.fixture
def sample_md_content():
    """Sample Markdown content for testing format fix.

    Returns:
        String with sample Markdown content
    """
    return """# Header 1

This is a paragraph with some text.

## Header 2

- List item 1
- List item 2

```c
int main() {
    return 0;
}
```

[Image](https://example.com/image.png)

**Bold text** and *italic text*.

Inline `code` here.
"""


@pytest.fixture
def complex_md_content():
    """Complex Markdown content with various formatting issues.

    Returns:
        String with complex Markdown content
    """
    return """#Header Without Space

##  Header with extra space  ##

This  has  double  spaces.

** bold ** and * italic * need fixing.

$ x = 1 + 2 $ needs spacing fix.

中文 文字 之间 多余 空格。

Link: [  link text  ](  https://example.com  )

Image: ![  alt text  ](  image.png  )

```python
def test():
    # Code block should be preserved
    return "hello"
```

Inline code: ` test ` should be preserved.

#Heading with trailing ###

"""


@pytest.fixture
def md_with_math():
    """Markdown content with LaTeX math formulas.

    Returns:
        String with Markdown containing math
    """
    return r"""# Math Document

Inline math: $ x = \frac{a}{b} $

Display math block:

$$
\int_0^1 x^2 dx = \frac{1}{3}
$$

More inline: $E = mc^2$ and $a + b = c$.

Complex formula: $ \sum_{i=1}^{n} i = \frac{n(n+1)}{2} $
"""


@pytest.fixture
def md_with_cjk():
    """Markdown content with CJK characters.

    Returns:
        String with Markdown containing Chinese characters
    """
    return """# 中文标题

这是一段中文内容。

##  中文副标题

中文 文字 之间 有 多余 空格。

标点符号 后面 有 空格 ， 应该 去掉 。

列表项：
- 第一项
- 第二项
- 第三项
"""


@pytest.fixture
def md_file(temp_dir, sample_md_content):
    """Create a temporary Markdown file.

    Args:
        temp_dir: Temporary directory fixture
        sample_md_content: Sample Markdown content fixture

    Returns:
        Path to Markdown file
    """
    md_path = temp_dir / "test.md"
    md_path.write_text(sample_md_content, encoding='utf-8')
    return md_path


# =============================================================================
# Config Fixtures
# =============================================================================

@pytest.fixture
def mock_config():
    """Create a mock Config object for testing.

    Returns:
        Config object with test values
    """
    config = Config()
    config.mineru.api_token = "test-token-12345"
    config.compress.ghostscript_path = None  # Auto-detect
    config.compress.quality = "ebook"
    config.umiocr.url = "http://127.0.0.1:1224"
    config.umiocr.enabled = True
    config.babeldoc.path = None
    config.babeldoc.openai_api_key = "test-api-key"
    config.babeldoc.openai_base_url = "https://api.example.com/v1"
    config.babeldoc.openai_model = "gpt-4"
    return config


@pytest.fixture
def mock_config_with_gs_path(temp_dir):
    """Create a Config with custom Ghostscript path.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Config object with custom paths
    """
    config = Config()
    config.mineru.api_token = "test-token"
    # Create a fake ghostscript path
    fake_gs = temp_dir / "gswin64c.exe"
    fake_gs.write_text("fake gs")
    config.compress.ghostscript_path = str(fake_gs)
    return config


@pytest.fixture
def minimal_config():
    """Create a minimal Config with only required fields.

    Returns:
        Config object with minimal settings
    """
    config = Config()
    config.mineru.api_token = "minimal-token"
    return config


@pytest.fixture
def config_file(temp_dir, mock_config):
    """Create a temporary config file.

    Args:
        temp_dir: Temporary directory fixture
        mock_config: Mock config fixture

    Returns:
        Path to config file
    """
    config_path = temp_dir / "config.toml"
    mock_config.save(config_path)
    return config_path


# =============================================================================
# State Fixtures
# =============================================================================

@pytest.fixture
def test_pdf_for_state(temp_dir):
    """Create a test PDF for state tests.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to test PDF file
    """
    pdf_path = temp_dir / "test_state.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test content\n%%EOF")
    return pdf_path


@pytest.fixture
def mock_state_manager(temp_dir, test_pdf_for_state):
    """Create a StateManager for testing.

    Args:
        temp_dir: Temporary directory fixture
        test_pdf_for_state: Test PDF fixture

    Returns:
        StateManager instance
    """
    manager = StateManager(temp_dir)
    manager.load_or_create(test_pdf_for_state, {"pdf_type": "text"})
    return manager


@pytest.fixture
def partial_state(temp_dir, test_pdf_for_state):
    """Create a state with partial completion.

    Args:
        temp_dir: Temporary directory fixture
        test_pdf_for_state: Test PDF fixture

    Returns:
        State object with partial completion
    """
    manager = StateManager(temp_dir)
    state = manager.load_or_create(test_pdf_for_state, {"pdf_type": "text"})

    # Mark some steps as completed
    state.update_step("ocr", status="skipped")
    state.update_step("translate", status="skipped")
    state.update_step("split", status="completed")
    state.update_step("compress", status="running")
    state.total_pages = 5
    manager.save()

    return state


@pytest.fixture
def failed_state(temp_dir, test_pdf_for_state):
    """Create a state with a failed step.

    Args:
        temp_dir: Temporary directory fixture
        test_pdf_for_state: Test PDF fixture

    Returns:
        State object with failed step
    """
    manager = StateManager(temp_dir)
    state = manager.load_or_create(test_pdf_for_state, {"pdf_type": "text"})

    state.update_step("ocr", status="skipped")
    state.update_step("translate", status="skipped")
    state.update_step("split", status="completed")
    state.update_step("compress", status="completed")
    state.update_step("mineru", status="partial", completed=[1, 3, 5], failed={"2": "Network error", "4": "Timeout"})
    state.total_pages = 5
    manager.save()

    return state


@pytest.fixture
def completed_state(temp_dir, test_pdf_for_state):
    """Create a completed state.

    Args:
        temp_dir: Temporary directory fixture
        test_pdf_for_state: Test PDF fixture

    Returns:
        State object with all steps completed
    """
    manager = StateManager(temp_dir)
    state = manager.load_or_create(test_pdf_for_state, {"pdf_type": "text"})

    state.update_step("ocr", status="skipped")
    state.update_step("translate", status="skipped")
    state.update_step("split", status="completed")
    state.update_step("compress", status="completed")
    state.update_step("mineru", status="completed")
    state.update_step("format_fix", status="completed")
    state.update_step("image_download", status="completed")
    state.total_pages = 5
    manager.save()

    return state


@pytest.fixture
def mock_state_info(mock_state_manager, test_pdf_for_state):
    """Create mock state info for recovery tests.

    Args:
        mock_state_manager: StateManager fixture
        test_pdf_for_state: Test PDF fixture

    Returns:
        Dict with state info
    """
    state = mock_state_manager.state
    state.update_step("ocr", status="skipped")
    state.update_step("split", status="completed")
    state.update_step("mineru", status="partial", completed=[1, 3, 5], failed={"2": "Error"})
    state.total_pages = 5
    mock_state_manager.save()

    return {
        'state': state,
        'state_manager': mock_state_manager,
        'current_step': 'mineru',
        'total': 5,
        'completed': 3,
        'failed': ['2'],
        'pending': 1,
    }


# =============================================================================
# Image Fixtures
# =============================================================================

@pytest.fixture
def sample_image_url():
    """Sample image URL for testing.

    Returns:
        Sample image URL string
    """
    return "https://example.com/images/test.png"


@pytest.fixture
def sample_image_urls():
    """List of sample image URLs for testing.

    Returns:
        List of image URL strings
    """
    return [
        "https://example.com/images/img1.png",
        "https://example.com/images/img2.jpg",
        "https://example.com/images/img3.gif",
        "https://cdn.example.com/pic.webp",
    ]


@pytest.fixture
def md_with_images():
    """Markdown content with image references.

    Returns:
        String with Markdown containing images
    """
    return """# Document with Images

Here is an image:

![Alt text 1](https://example.com/image1.png)

And another:

![Alt text 2](https://example.com/image2.jpg)

Local image:

![Local](images/local.png)

Multiple on one line: ![A](a.png) and ![B](b.jpg).
"""


@pytest.fixture
def images_dir(temp_dir):
    """Create an images directory for testing.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to images directory
    """
    images_path = temp_dir / "images"
    images_path.mkdir(parents=True, exist_ok=True)
    return images_path


# =============================================================================
# Misc Fixtures
# =============================================================================

@pytest.fixture
def sample_json_data():
    """Sample JSON data for testing.

    Returns:
        Dict with sample data
    """
    return {
        "version": 1,
        "source_path": "/path/to/test.pdf",
        "source_size": 1024,
        "options": {
            "pdf_type": "text",
            "language": "en",
            "translate": False,
        },
        "steps": {
            "ocr": {"status": "skipped"},
            "split": {"status": "completed"},
        },
    }


@pytest.fixture
def corrupted_json_file(temp_dir):
    """Create a corrupted JSON file for error testing.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to corrupted JSON file
    """
    json_path = temp_dir / "corrupted.json"
    json_path.write_text("{ invalid json content", encoding='utf-8')
    return json_path


@pytest.fixture
def valid_json_file(temp_dir, sample_json_data):
    """Create a valid JSON file for testing.

    Args:
        temp_dir: Temporary directory fixture
        sample_json_data: Sample JSON data fixture

    Returns:
        Path to valid JSON file
    """
    json_path = temp_dir / "valid.json"
    json_path.write_text(json.dumps(sample_json_data, indent=2), encoding='utf-8')
    return json_path
