#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Markdown format fix module."""

import pytest
from pathlib import Path
import tempfile
import shutil

from ocr_flow.steps.format_fix import format_fix, fix_markdown, add_page_hints


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_md_content():
    """Sample Markdown content for testing."""
    return """# Header 1

This is a paragraph.

## Header 2

- List item 1
- List item 2

```c
int main() {
    return 0;
}
```

[Image](https://example.com/image.png)
"""


class TestFixMarkdown:
    """Tests for fix_markdown function."""

    def test_fix_markdown_preserves_headings(self, sample_md_content):
        """Test that fix_markdown preserves headings."""
        result = fix_markdown(sample_md_content)

        assert "# Header 1" in result
        assert "## Header 2" in result

    def test_fix_markdown_preserves_code_blocks(self):
        """Test that fix_markdown preserves code blocks."""
        content = "```python\nprint('hello')\n```"
        result = fix_markdown(content)

        assert "print('hello')" in result

    def test_fix_markdown_normalizes_whitespace(self):
        """Test whitespace normalization."""
        content = "Hello  world"  # Double space
        result = fix_markdown(content)

        assert "  " not in result or "Hello world" in result


class TestAddPageHints:
    """Tests for add_page_hints function."""

    def test_add_page_hints_adds_header(self):
        """Test that hints are added."""
        content = "# Test"
        result = add_page_hints(content, is_translated=False)

        assert "分页" in result
        assert "paginated" in result

    def test_add_page_hints_adds_footer(self):
        """Test that footer hint is added."""
        content = "# Test"
        result = add_page_hints(content, is_translated=False)

        assert "下一页" in result or "next page" in result.lower()


class TestFormatFix:
    """Tests for format_fix function."""

    def test_format_fix_creates_output(self, temp_dir, sample_md_content):
        """Test that format_fix creates output file."""
        input_file = temp_dir / "input.md"
        input_file.write_text(sample_md_content, encoding='utf-8')
        output_file = temp_dir / "output.md"

        result = format_fix(input_file, output_file)

        assert result == output_file
        assert output_file.exists()

    def test_format_fix_preserves_content(self, temp_dir, sample_md_content):
        """Test that format_fix preserves basic content."""
        input_file = temp_dir / "input.md"
        input_file.write_text(sample_md_content, encoding='utf-8')
        output_file = temp_dir / "output.md"

        format_fix(input_file, output_file)
        content = output_file.read_text(encoding='utf-8')

        assert "# Header 1" in content
        assert "## Header 2" in content
        assert "List item 1" in content

    def test_format_fix_adds_pagination_hint(self, temp_dir, sample_md_content):
        """Test that format_fix adds pagination hints."""
        input_file = temp_dir / "input.md"
        input_file.write_text(sample_md_content, encoding='utf-8')
        output_file = temp_dir / "output.md"

        format_fix(input_file, output_file)
        content = output_file.read_text(encoding='utf-8')

        # Should add hint at beginning
        assert "分页" in content or "paginated" in content.lower()

    def test_format_fix_handles_empty_content(self, temp_dir):
        """Test that format_fix handles empty content."""
        input_file = temp_dir / "empty.md"
        input_file.write_text("", encoding='utf-8')
        output_file = temp_dir / "output.md"

        result = format_fix(input_file, output_file)

        assert result == output_file
        assert output_file.exists()
