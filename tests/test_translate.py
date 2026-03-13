#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Translation module.

Test suite using mocked subprocess to test:
- translate_pdf function
- BabelDOC interaction
- find_dual_pdf function
- check_babeldoc_available function
- Error handling
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock, Mock

from ocr_flow.steps.translate import (
    translate_pdf,
    find_dual_pdf,
    check_babeldoc_available,
)
from ocr_flow.config import Config, BabelDocConfig


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
def mock_config():
    """Create a mock config for translation."""
    config = Config()
    config.babeldoc.path = None
    config.babeldoc.lang_in = "en"
    config.babeldoc.lang_out = "zh"
    config.babeldoc.openai = False
    return config


@pytest.fixture
def mock_config_with_babeldoc_path(temp_dir):
    """Create a config with babeldoc path."""
    config = Config()
    babel_path = temp_dir / "babeldoc"
    babel_path.mkdir(exist_ok=True)
    config.babeldoc.path = str(babel_path)
    config.babeldoc.lang_in = "en"
    config.babeldoc.lang_out = "zh"
    config.babeldoc.openai = False
    return config


@pytest.fixture
def mock_config_with_openai():
    """Create a config with OpenAI settings."""
    config = Config()
    config.babeldoc.path = None
    config.babeldoc.lang_in = "en"
    config.babeldoc.lang_out = "zh"
    config.babeldoc.openai = True
    config.babeldoc.openai_model = "gpt-4"
    config.babeldoc.openai_base_url = "https://api.openai.com/v1"
    config.babeldoc.openai_api_key = "test-key-123"
    return config


@pytest.fixture
def test_pdf(temp_dir):
    """Create a test PDF file."""
    pdf_path = temp_dir / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test content\n%%EOF")
    return pdf_path


@pytest.fixture
def output_path(temp_dir):
    """Create output path for translation result."""
    return temp_dir / "translated.pdf"


# =============================================================================
# TestFindDualPdf - PDF Finding Tests
# =============================================================================

class TestFindDualPdf:
    """Tests for find_dual_pdf function."""

    def test_find_dual_pdf_exact_match(self, temp_dir, test_pdf):
        """Test finding dual PDF with exact match."""
        # Create a dual PDF
        dual_pdf = temp_dir / "test.zh.dual.pdf"
        dual_pdf.write_bytes(b"%PDF-dual")

        result = find_dual_pdf(temp_dir, test_pdf)

        assert result == dual_pdf

    def test_find_dual_pdf_any_dual(self, temp_dir, test_pdf):
        """Test finding any dual PDF in output directory."""
        # Create a dual PDF with different name
        dual_pdf = temp_dir / "output.zh.dual.pdf"
        dual_pdf.write_bytes(b"%PDF-dual")

        result = find_dual_pdf(temp_dir, test_pdf)

        assert result == dual_pdf

    def test_find_dual_pdf_with_original_prefix(self, temp_dir):
        """Test finding dual PDF with original name prefix."""
        original = temp_dir / "mydoc.pdf"
        original.write_bytes(b"%PDF-original")

        dual_pdf = temp_dir / "mydoc.zh.dual.pdf"
        dual_pdf.write_bytes(b"%PDF-dual")

        result = find_dual_pdf(temp_dir, original)

        assert result == dual_pdf

    def test_find_dual_pdf_not_found(self, temp_dir, test_pdf):
        """Test when no dual PDF exists."""
        result = find_dual_pdf(temp_dir, test_pdf)

        assert result is None

    def test_find_dual_pdf_ignores_mono(self, temp_dir, test_pdf):
        """Test that mono PDF is not returned."""
        # Create only mono PDF
        mono_pdf = temp_dir / "test.zh.mono.pdf"
        mono_pdf.write_bytes(b"%PDF-mono")

        result = find_dual_pdf(temp_dir, test_pdf)

        assert result is None

    def test_find_dual_pdf_multiple_files(self, temp_dir, test_pdf):
        """Test finding dual PDF when multiple files exist."""
        # Create multiple PDFs
        (temp_dir / "test.mono.pdf").write_bytes(b"%PDF-mono")
        dual_pdf = temp_dir / "test.dual.pdf"
        dual_pdf.write_bytes(b"%PDF-dual")
        (temp_dir / "test.other.pdf").write_bytes(b"%PDF-other")

        result = find_dual_pdf(temp_dir, test_pdf)

        assert result == dual_pdf


# =============================================================================
# TestCheckBabelDocAvailable - Availability Check Tests
# =============================================================================

class TestCheckBabelDocAvailable:
    """Tests for check_babeldoc_available function."""

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_global_install_available(self, mock_run, mock_config):
        """Test when BabelDOC is globally installed."""
        mock_run.return_value = MagicMock(returncode=0)

        result = check_babeldoc_available(mock_config)

        assert result == True
        mock_run.assert_called()

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_global_install_not_available(self, mock_run, mock_config):
        """Test when BabelDOC is not installed."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, 'babeldoc')

        result = check_babeldoc_available(mock_config)

        assert result == False

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.Path.exists')
    def test_path_based_available(self, mock_exists, mock_run, mock_config_with_babeldoc_path):
        """Test when BabelDOC is available via path."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = check_babeldoc_available(mock_config_with_babeldoc_path)

        # Should check uv version
        assert result == True

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.Path.exists')
    def test_path_based_not_exists(self, mock_exists, mock_run, mock_config_with_babeldoc_path):
        """Test when configured path doesn't exist."""
        mock_exists.return_value = False

        result = check_babeldoc_available(mock_config_with_babeldoc_path)

        assert result == False

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_filenotfound_error(self, mock_run, mock_config):
        """Test handling FileNotFoundError."""
        mock_run.side_effect = FileNotFoundError()

        result = check_babeldoc_available(mock_config)

        assert result == False


# =============================================================================
# TestTranslatePdf - Translation Tests
# =============================================================================

class TestTranslatePdf:
    """Tests for translate_pdf function."""

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.find_dual_pdf')
    def test_translate_success(self, mock_find, mock_run, mock_config, test_pdf, output_path, temp_dir):
        """Test successful translation."""
        # Mock successful subprocess
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Mock finding the dual PDF
        dual_pdf = temp_dir / "test.zh.dual.pdf"
        dual_pdf.write_bytes(b"%PDF-translated")
        mock_find.return_value = dual_pdf

        result = translate_pdf(test_pdf, output_path, mock_config)

        assert result == dual_pdf
        mock_run.assert_called_once()

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_creates_output_dir(self, mock_run, mock_config, test_pdf, temp_dir):
        """Test that output directory is created."""
        nested_output = temp_dir / "nested" / "deep" / "result.pdf"

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError):
            translate_pdf(test_pdf, nested_output, mock_config)

        # Directory should be created
        assert nested_output.parent.exists()

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_rate_limit_error(self, mock_run, mock_config, test_pdf, output_path):
        """Test handling rate limit error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Rate limit exceeded"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="rate limited"):
            translate_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_api_key_error(self, mock_run, mock_config, test_pdf, output_path):
        """Test handling invalid API key error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Invalid API key"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Invalid API key"):
            translate_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_babeldoc_not_found_global(self, mock_run, mock_config, test_pdf, output_path):
        """Test handling BabelDOC not found (global install)."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "babeldoc: command not found"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="BabelDOC not found"):
            translate_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.Path.exists')
    def test_translate_babeldoc_not_found_path(self, mock_exists, mock_run, mock_config_with_babeldoc_path, test_pdf, output_path):
        """Test handling BabelDOC not found (path config)."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "command not found"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="not found at"):
            translate_pdf(test_pdf, output_path, mock_config_with_babeldoc_path)

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_network_error(self, mock_run, mock_config, test_pdf, output_path):
        """Test handling network error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Connection timeout"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Network error"):
            translate_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_quota_exhausted(self, mock_run, mock_config, test_pdf, output_path):
        """Test handling quota exhausted error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Insufficient quota"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="quota exhausted"):
            translate_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.find_dual_pdf')
    def test_translate_output_not_found(self, mock_find, mock_run, mock_config, test_pdf, output_path):
        """Test when translated output is not found."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        mock_find.return_value = None

        with pytest.raises(RuntimeError, match="Could not find translated PDF"):
            translate_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.find_dual_pdf')
    def test_translate_with_openai(self, mock_find, mock_run, mock_config_with_openai, test_pdf, output_path, temp_dir):
        """Test translation with OpenAI config."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        dual_pdf = temp_dir / "test.zh.dual.pdf"
        dual_pdf.write_bytes(b"%PDF-translated")
        mock_find.return_value = dual_pdf

        result = translate_pdf(test_pdf, output_path, mock_config_with_openai)

        # Check that OpenAI args were added to command
        call_args = mock_run.call_args[0][0]
        assert '--openai' in call_args
        assert '--openai-model' in call_args
        assert 'gpt-4' in call_args

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.find_dual_pdf')
    def test_translate_with_babeldoc_path(self, mock_find, mock_run, mock_config_with_babeldoc_path, test_pdf, output_path, temp_dir):
        """Test translation with custom BabelDOC path."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        dual_pdf = temp_dir / "test.zh.dual.pdf"
        dual_pdf.write_bytes(b"%PDF-translated")
        mock_find.return_value = dual_pdf

        result = translate_pdf(test_pdf, output_path, mock_config_with_babeldoc_path)

        # Check that uv run with directory was used
        call_args = mock_run.call_args[0][0]
        assert 'uv' in call_args
        assert '--directory' in call_args

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_timeout(self, mock_run, mock_config, test_pdf, output_path):
        """Test handling subprocess timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="babeldoc", timeout=60)

        with pytest.raises(subprocess.TimeoutExpired):
            translate_pdf(test_pdf, output_path, mock_config, timeout=60)

    @patch('ocr_flow.steps.translate.subprocess.run')
    def test_translate_generic_error(self, mock_run, mock_config, test_pdf, output_path):
        """Test handling generic error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Some unknown error occurred"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="BabelDOC failed"):
            translate_pdf(test_pdf, output_path, mock_config)


# =============================================================================
# TestTranslatePdfLanguage - Language Configuration Tests
# =============================================================================

class TestTranslatePdfLanguage:
    """Tests for language configuration."""

    @patch('ocr_flow.steps.translate.subprocess.run')
    @patch('ocr_flow.steps.translate.find_dual_pdf')
    def test_custom_language_config(self, mock_find, mock_run, temp_dir):
        """Test that custom language config is used."""
        config = Config()
        config.babeldoc.lang_in = "ja"
        config.babeldoc.lang_out = "en"
        config.babeldoc.openai = False

        test_pdf = temp_dir / "test.pdf"
        test_pdf.write_bytes(b"%PDF")
        output_path = temp_dir / "out.pdf"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        dual_pdf = temp_dir / "test.en.dual.pdf"
        dual_pdf.write_bytes(b"%PDF")
        mock_find.return_value = dual_pdf

        translate_pdf(test_pdf, output_path, config)

        # Check language args in command
        call_args = mock_run.call_args[0][0]
        assert '--lang-in' in call_args
        assert 'ja' in call_args
        assert '--lang-out' in call_args
        assert 'en' in call_args
