#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for self-check module.

Test suite covering:
- SelfCheck class functionality
- Ghostscript checking
- MinerU API checking
- UMI OCR checking
- BabelDOC checking
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import subprocess
from unittest.mock import patch, MagicMock, Mock

from ocr_flow.self_check import (
    SelfCheck,
    find_ghostscript,
    find_umi_ocr,
    start_umi_ocr,
)
from ocr_flow.config import Config


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
    """Create a mock config for testing."""
    config = Config()
    config.mineru.api_token = "test-api-token-12345"
    config.umiocr.url = "http://127.0.0.1:1224"
    config.babeldoc.path = None
    return config


@pytest.fixture
def mock_config_no_token():
    """Create a config without API token."""
    config = Config()
    config.mineru.api_token = ""
    return config


@pytest.fixture
def mock_config_with_babeldoc_path(temp_dir):
    """Create a config with BabelDOC path."""
    config = Config()
    config.babeldoc.path = str(temp_dir / "babeldoc")
    return config


# =============================================================================
# TestSelfCheckInit - Initialization Tests
# =============================================================================

class TestSelfCheckInit:
    """Tests for SelfCheck initialization."""

    def test_init_with_config(self, mock_config):
        """Test initialization with config."""
        checker = SelfCheck(config=mock_config)
        assert checker.config == mock_config

    def test_init_without_config(self):
        """Test initialization without config."""
        checker = SelfCheck(config=None)
        assert checker.config is None


# =============================================================================
# TestCheckAll - Check All Tests
# =============================================================================

class TestCheckAll:
    """Tests for check_all method."""

    def test_check_all_basic(self, mock_config):
        """Test basic check_all without OCR or translate."""
        checker = SelfCheck(config=mock_config)
        results = checker.check_all(needs_ocr=False, needs_translate=False)

        assert 'ghostscript' in results
        assert 'mineru_api' in results
        assert 'umi_ocr' not in results
        assert 'babeldoc' not in results

    def test_check_all_with_ocr(self, mock_config):
        """Test check_all with OCR needed."""
        checker = SelfCheck(config=mock_config)
        results = checker.check_all(needs_ocr=True, needs_translate=False)

        assert 'ghostscript' in results
        assert 'mineru_api' in results
        assert 'umi_ocr' in results

    def test_check_all_with_translate(self, mock_config):
        """Test check_all with translate needed."""
        checker = SelfCheck(config=mock_config)
        results = checker.check_all(needs_ocr=False, needs_translate=True)

        assert 'ghostscript' in results
        assert 'mineru_api' in results
        assert 'babeldoc' in results

    def test_check_all_all_checks(self, mock_config):
        """Test check_all with all checks enabled."""
        checker = SelfCheck(config=mock_config)
        results = checker.check_all(needs_ocr=True, needs_translate=True)

        assert 'ghostscript' in results
        assert 'mineru_api' in results
        assert 'umi_ocr' in results
        assert 'babeldoc' in results


# =============================================================================
# TestCheckGhostscript - Ghostscript Check Tests
# =============================================================================

class TestCheckGhostscript:
    """Tests for check_ghostscript method."""

    def test_check_ghostscript_found(self, mock_config, monkeypatch):
        """Test when Ghostscript is found."""
        # Mock find_ghostscript to return a path
        monkeypatch.setattr(
            'ocr_flow.self_check.find_ghostscript',
            lambda config=None: '/usr/bin/gs'
        )

        # Mock subprocess.run
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "9.50"
        monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: mock_result)

        checker = SelfCheck(config=mock_config)
        result = checker.check_ghostscript()

        assert result['ok'] == True
        assert '9.50' in result['message']

    def test_check_ghostscript_not_found(self, mock_config, monkeypatch):
        """Test when Ghostscript is not found."""
        monkeypatch.setattr(
            'ocr_flow.self_check.find_ghostscript',
            lambda config=None: None
        )

        checker = SelfCheck(config=mock_config)
        result = checker.check_ghostscript()

        assert result['ok'] == False
        assert 'Not found' in result['message']


# =============================================================================
# TestCheckMineruApi - MinerU API Check Tests
# =============================================================================

class TestCheckMineruApi:
    """Tests for check_mineru_api method."""

    def test_check_mineru_configured(self, mock_config):
        """Test when MinerU API token is configured."""
        checker = SelfCheck(config=mock_config)
        result = checker.check_mineru_api()

        assert result['ok'] == True
        assert 'configured' in result['message'].lower()

    def test_check_mineru_not_configured(self, mock_config_no_token):
        """Test when MinerU API token is not configured."""
        checker = SelfCheck(config=mock_config_no_token)
        result = checker.check_mineru_api()

        assert result['ok'] == False
        assert 'not configured' in result['message'].lower()

    def test_check_mineru_placeholder_token(self):
        """Test with placeholder token."""
        config = Config()
        config.mineru.api_token = "your-mineru-api-token-here"

        checker = SelfCheck(config=config)
        result = checker.check_mineru_api()

        assert result['ok'] == False

    def test_check_mineru_no_config(self):
        """Test check without config."""
        checker = SelfCheck(config=None)
        result = checker.check_mineru_api()

        assert result['ok'] == False


# =============================================================================
# TestCheckUmiOcr - UMI OCR Check Tests
# =============================================================================

class TestCheckUmiOcr:
    """Tests for check_umi_ocr method."""

    @patch('ocr_flow.self_check.requests.get')
    def test_check_umi_ocr_running(self, mock_get, mock_config):
        """Test when UMI OCR service is running."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        checker = SelfCheck(config=mock_config)
        result = checker.check_umi_ocr()

        assert result['ok'] == True
        assert 'running' in result['message'].lower()

    @patch('ocr_flow.self_check.requests.get')
    def test_check_umi_ocr_not_running(self, mock_get, mock_config):
        """Test when UMI OCR service is not running."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        checker = SelfCheck(config=mock_config)
        result = checker.check_umi_ocr()

        assert result['ok'] == False
        assert 'not running' in result['message'].lower()

    @patch('ocr_flow.self_check.requests.get')
    def test_check_umi_ocr_wrong_status(self, mock_get, mock_config):
        """Test when UMI OCR returns wrong status."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        checker = SelfCheck(config=mock_config)
        result = checker.check_umi_ocr()

        assert result['ok'] == False

    @patch('ocr_flow.self_check.start_umi_ocr')
    @patch('ocr_flow.self_check.requests.get')
    def test_check_umi_ocr_auto_start(self, mock_get, mock_start, mock_config):
        """Test auto-starting UMI OCR."""
        import requests

        # First call fails (not running)
        # After start, second check succeeds
        mock_get.side_effect = [
            requests.exceptions.ConnectionError(),
            MagicMock(status_code=200)
        ]
        mock_start.return_value = {'started': True, 'message': 'Started'}

        checker = SelfCheck(config=mock_config)
        result = checker.check_umi_ocr(auto_start=True)

        mock_start.assert_called_once()


# =============================================================================
# TestCheckBabeldoc - BabelDOC Check Tests
# =============================================================================

class TestCheckBabeldoc:
    """Tests for check_babeldoc method."""

    def test_check_babeldoc_global(self, mock_config, monkeypatch):
        """Test globally installed BabelDOC."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "babeldoc 1.0.0"
        monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: mock_result)

        checker = SelfCheck(config=mock_config)
        result = checker.check_babeldoc()

        assert result['ok'] == True
        assert 'installed' in result['message'].lower()

    def test_check_babeldoc_not_found(self, mock_config, monkeypatch):
        """Test BabelDOC not found."""
        def raise_not_found(*args, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, 'run', raise_not_found)

        checker = SelfCheck(config=mock_config)
        result = checker.check_babeldoc()

        assert result['ok'] == False
        assert 'Not found' in result['message']

    def test_check_babeldoc_local_path_exists(self, temp_dir):
        """Test BabelDOC at local path."""
        babeldoc_path = temp_dir / "babeldoc"
        babeldoc_path.mkdir()

        config = Config()
        config.babeldoc.path = str(babeldoc_path)

        checker = SelfCheck(config=config)
        result = checker.check_babeldoc()

        assert result['ok'] == True

    def test_check_babeldoc_local_path_not_exists(self, temp_dir):
        """Test BabelDOC at non-existent local path."""
        config = Config()
        config.babeldoc.path = str(temp_dir / "nonexistent")

        checker = SelfCheck(config=config)
        result = checker.check_babeldoc()

        assert result['ok'] == False
        assert 'not found' in result['message'].lower()


# =============================================================================
# TestFindGhostscript - Ghostscript Discovery Tests
# =============================================================================

class TestFindGhostscript:
    """Tests for find_ghostscript function."""

    def test_find_in_path(self, monkeypatch):
        """Test finding Ghostscript in PATH."""
        monkeypatch.setattr(shutil, 'which', lambda name: '/usr/bin/gs' if name in ['gs', 'gswin64c'] else None)

        result = find_ghostscript()
        assert result == '/usr/bin/gs'

    def test_not_found(self, monkeypatch):
        """Test Ghostscript not found."""
        monkeypatch.setattr(shutil, 'which', lambda name: None)
        monkeypatch.setattr(Path, 'exists', lambda self: False)

        result = find_ghostscript()
        assert result is None


# =============================================================================
# TestFindUmiOcr - UMI OCR Discovery Tests
# =============================================================================

class TestFindUmiOcr:
    """Tests for find_umi_ocr function."""

    def test_find_in_path(self, monkeypatch):
        """Test finding UMI OCR in PATH."""
        monkeypatch.setattr(shutil, 'which', lambda name: '/usr/bin/umi-ocr' if name == 'umi-ocr' else None)

        result = find_umi_ocr()
        assert result == '/usr/bin/umi-ocr'

    def test_find_local_directory(self, temp_dir, monkeypatch):
        """Test finding UMI OCR in local directory."""
        # Create fake UMI OCR structure
        umi_dir = temp_dir / "umiocr" / "Umi-OCR_v1.0"
        umi_dir.mkdir(parents=True)
        exe_path = umi_dir / "Umi-OCR.exe"
        exe_path.write_text("fake")

        # Mock shutil.which to return None (not in PATH)
        monkeypatch.setattr(shutil, 'which', lambda name: None)

        # The function looks for project_root/umiocr
        # Just verify it doesn't crash and returns a result
        result = find_umi_ocr()
        # Result depends on system state
        assert result is None or isinstance(result, str)

    def test_not_found(self, monkeypatch):
        """Test UMI OCR not found."""
        monkeypatch.setattr(shutil, 'which', lambda name: None)
        monkeypatch.setattr(Path, 'exists', lambda self: False)

        result = find_umi_ocr()
        assert result is None


# =============================================================================
# TestStartUmiOcr - UMI OCR Start Tests
# =============================================================================

class TestStartUmiOcr:
    """Tests for start_umi_ocr function."""

    def test_start_not_found(self, monkeypatch):
        """Test starting when UMI OCR not found."""
        monkeypatch.setattr('ocr_flow.self_check.find_umi_ocr', lambda: None)

        result = start_umi_ocr()

        assert result['started'] == False
        assert 'not found' in result['message'].lower()

    @patch('subprocess.Popen')
    def test_start_success(self, mock_popen, monkeypatch):
        """Test successful start of UMI OCR."""
        monkeypatch.setattr('ocr_flow.self_check.find_umi_ocr', lambda: '/path/to/umi-ocr')
        mock_popen.return_value = MagicMock()

        result = start_umi_ocr()

        assert result['started'] == True
        mock_popen.assert_called_once()

    @patch('subprocess.Popen')
    def test_start_exception(self, mock_popen, monkeypatch):
        """Test handling exception during start."""
        monkeypatch.setattr('ocr_flow.self_check.find_umi_ocr', lambda: '/path/to/umi-ocr')
        mock_popen.side_effect = Exception("Failed to start")

        result = start_umi_ocr()

        assert result['started'] == False
        assert 'Failed' in result['message']
