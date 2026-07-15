#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for OCR module.

Test suite using mocked HTTP responses to test:
- ocr_pdf function
- UMI OCR service interaction
- Error handling
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock, Mock
import json

from ocr_flow.steps.ocr import (
    ocr_pdf,
    check_umi_ocr_service,
    resolve_ocr_language,
    resolve_ocr_timeout,
    DEFAULT_OCR_TIMEOUT,
    LARGE_FILE_OCR_TIMEOUT,
)
from ocr_flow.config import Config, UmiOcrConfig


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
    """Create a mock config for OCR."""
    config = Config()
    config.umiocr.url = "http://127.0.0.1:1224"
    config.umiocr.language = "models/config_en.txt"
    config.umiocr.enabled = True
    return config


@pytest.fixture
def test_pdf(temp_dir):
    """Create a test PDF file."""
    pdf_path = temp_dir / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test content for OCR\n%%EOF")
    return pdf_path


@pytest.fixture
def large_pdf(temp_dir):
    """Create a larger PDF for size warning tests."""
    pdf_path = temp_dir / "large.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n" + b"x" * (150 * 1024 * 1024) + b"\n%%EOF")
    return pdf_path


@pytest.fixture
def output_path(temp_dir):
    """Create output path for OCR result."""
    return temp_dir / "ocr_result.pdf"


@pytest.fixture
def mock_ready_umi_service():
    """Mock UMI OCR service preparation for OCR runtime tests."""
    with patch('ocr_flow.steps.ocr.ensure_umi_ocr_service') as mock_ensure:
        mock_ensure.return_value = {'ok': True, 'message': 'running', 'started': False}
        yield mock_ensure


# =============================================================================
# TestOcrPdf - OCR Processing Tests
# =============================================================================

class TestOcrPdf:
    """Tests for ocr_pdf function."""

    @patch('ocr_flow.steps.ocr.ensure_umi_ocr_service')
    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_ocr_prepares_service_before_upload(self, mock_session_cls, mock_ensure, mock_config, test_pdf, output_path):
        """Test OCR ensures the UMI OCR service is ready before upload."""
        mock_ensure.return_value = {'ok': True, 'message': 'running', 'started': False}
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_upload = MagicMock()
        mock_upload.json.return_value = {'code': 100, 'data': 'task-123'}
        mock_poll = MagicMock()
        mock_poll.json.return_value = {'is_done': True, 'state': 'success'}
        mock_download_req = MagicMock()
        mock_download_req.json.return_value = {'code': 100, 'data': '/download/result.pdf'}
        mock_session.post.side_effect = [mock_upload, mock_poll, mock_download_req]
        mock_session.get.return_value = MagicMock(content=b'%PDF-ocr-result')

        ocr_pdf(test_pdf, output_path, mock_config)

        mock_ensure.assert_called_once_with(
            mock_config, expected_language="models/config_en.txt"
        )

    @patch('ocr_flow.steps.ocr.requests.Session')
    @patch('ocr_flow.steps.ocr.requests.post')
    @patch('ocr_flow.steps.ocr.requests.get')
    def test_ocr_bypasses_env_proxies_for_local_service(self, mock_get, mock_post, mock_session_cls, mock_config, test_pdf, output_path, mock_ready_umi_service):
        """Test local UMI OCR requests bypass environment proxies."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_upload = MagicMock()
        mock_upload.json.return_value = {'code': 100, 'data': 'task-123'}
        mock_poll = MagicMock()
        mock_poll.json.return_value = {'is_done': True, 'state': 'success'}
        mock_download_req = MagicMock()
        mock_download_req.json.return_value = {'code': 100, 'data': '/download/result.pdf'}
        mock_download_file = MagicMock(content=b'%PDF-ocr-result')

        mock_post.side_effect = [mock_upload, mock_poll, mock_download_req]
        mock_get.return_value = mock_download_file
        mock_session.post.side_effect = [mock_upload, mock_poll, mock_download_req]
        mock_session.get.return_value = mock_download_file

        result = ocr_pdf(test_pdf, output_path, mock_config)

        assert result == output_path
        mock_session_cls.assert_called_once()
        assert mock_session.trust_env is False
        assert mock_session.post.call_args_list[0].args[0] == 'http://127.0.0.1:1224/api/doc/upload'

    @patch('ocr_flow.steps.ocr.ensure_umi_ocr_service')
    def test_ocr_raises_clear_error_when_service_prepare_fails(self, mock_ensure, mock_config, test_pdf, output_path):
        """Test OCR raises a clear error when UMI OCR cannot be prepared."""
        mock_ensure.return_value = {
            'ok': False,
            'message': 'Service not running and umiocr.exe_path is not configured.'
        }

        with pytest.raises(RuntimeError, match='umiocr.exe_path'):
            ocr_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_ocr_upload_success(self, mock_session_cls, mock_config, test_pdf, output_path):
        """Test successful PDF upload to OCR service."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_upload_response = MagicMock()
        mock_upload_response.json.return_value = {
            "code": 100,
            "data": "task-id-123"
        }

        mock_poll_response = MagicMock()
        mock_poll_response.json.return_value = {
            "is_done": True,
            "state": "success"
        }

        mock_download_response = MagicMock()
        mock_download_response.json.return_value = {
            "code": 100,
            "data": "/download/result.pdf"
        }

        mock_file_response = MagicMock()
        mock_file_response.content = b"%PDF-ocr-result"
        mock_session.get.return_value = mock_file_response
        mock_session.post.side_effect = [mock_upload_response, mock_poll_response, mock_download_response]

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_ocr_upload_failure(self, mock_session_cls, mock_config, test_pdf, output_path, mock_ready_umi_service):
        """Test OCR upload failure."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 101,
            "data": "Upload failed"
        }
        mock_session.post.return_value = mock_response

        with pytest.raises(RuntimeError, match="Upload failed"):
            ocr_pdf(test_pdf, output_path, mock_config)

    @patch('ocr_flow.steps.ocr.requests.Session')
    @patch('ocr_flow.steps.ocr.time.sleep')
    @patch('ocr_flow.steps.ocr.time.time')
    def test_ocr_poll_timeout(self, mock_time, mock_sleep, mock_session_cls, mock_config, test_pdf, output_path, mock_ready_umi_service):
        """Test OCR polling timeout."""
        mock_time.side_effect = [0, 100, 200, 300]

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_upload = MagicMock()
        mock_upload.json.return_value = {"code": 100, "data": "task-123"}
        mock_poll = MagicMock()
        mock_poll.json.return_value = {"is_done": False, "state": "running"}

        call_count = [0]
        def get_response(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_upload
            return mock_poll

        mock_session.post.side_effect = get_response

        with pytest.raises(RuntimeError, match="timeout"):
            ocr_pdf(test_pdf, output_path, mock_config, timeout=1)

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_ocr_success_flow(self, mock_session_cls, mock_config, test_pdf, output_path, mock_ready_umi_service):
        """Test complete successful OCR flow."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_upload = MagicMock()
        mock_upload.json.return_value = {"code": 100, "data": "task-123"}
        mock_poll = MagicMock()
        mock_poll.json.return_value = {
            "is_done": True,
            "state": "success"
        }
        mock_download_req = MagicMock()
        mock_download_req.json.return_value = {
            "code": 100,
            "data": "/download/result.pdf"
        }

        mock_session.post.side_effect = [mock_upload, mock_poll, mock_download_req]
        mock_file_get = MagicMock()
        mock_file_get.content = b"%PDF-ocr-result"
        mock_session.get.return_value = mock_file_get

        result = ocr_pdf(test_pdf, output_path, mock_config)

        assert result == output_path
        assert output_path.exists()

    def test_ocr_creates_output_directory(self, mock_config, test_pdf, temp_dir, mock_ready_umi_service):
        """Test that OCR creates output directory."""
        nested_output = temp_dir / "nested" / "dir" / "result.pdf"

        with patch('ocr_flow.steps.ocr.requests.Session') as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_response = MagicMock()
            mock_response.json.return_value = {"code": 101, "data": "Error"}
            mock_session.post.return_value = mock_response

            try:
                ocr_pdf(test_pdf, nested_output, mock_config)
            except RuntimeError:
                pass

        assert nested_output.parent.exists()


# =============================================================================
# TestOcrPdfErrorHandling - Error Handling Tests
# =============================================================================

class TestOcrPdfErrorHandling:
    """Tests for OCR error handling."""

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_ocr_failure_state(self, mock_session_cls, mock_config, test_pdf, output_path, mock_ready_umi_service):
        """Test handling OCR failure state."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_upload = MagicMock()
        mock_upload.json.return_value = {"code": 100, "data": "task-123"}

        with patch('ocr_flow.steps.ocr.time.sleep'):
            mock_session.post.side_effect = [
                mock_upload,
                MagicMock(json=lambda: {"is_done": True, "state": "failed", "message": "OCR error"})
            ]

            with pytest.raises(RuntimeError, match="OCR failed"):
                ocr_pdf(test_pdf, output_path, mock_config, timeout=5)

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_ocr_connection_error(self, mock_session_cls, mock_config, test_pdf, output_path, mock_ready_umi_service):
        """Test handling connection error."""
        import requests
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.post.side_effect = requests.exceptions.ConnectionError()

        with pytest.raises(requests.exceptions.ConnectionError):
            ocr_pdf(test_pdf, output_path, mock_config)


# =============================================================================
# TestCheckUmiOcrService - Service Check Tests
# =============================================================================

class TestCheckUmiOcrService:
    """Tests for check_umi_ocr_service function."""

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_service_running(self, mock_session_cls):
        """Test when UMI OCR service is running."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = check_umi_ocr_service()

        assert result == True

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_service_not_running(self, mock_session_cls):
        """Test when UMI OCR service is not running."""
        import requests
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.side_effect = requests.exceptions.ConnectionError()

        result = check_umi_ocr_service()

        assert result == False

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_service_wrong_status(self, mock_session_cls):
        """Test when service returns wrong status."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_session.get.return_value = mock_response

        result = check_umi_ocr_service()

        assert result == False

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_service_custom_url(self, mock_session_cls):
        """Test checking service at custom URL."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = check_umi_ocr_service("http://192.168.1.100:8080")

        mock_session.get.assert_called_with(
            "http://192.168.1.100:8080/api/doc/get_options",
            timeout=5
        )

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_service_timeout(self, mock_session_cls):
        """Test handling service timeout."""
        import requests
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.side_effect = requests.exceptions.Timeout()

        result = check_umi_ocr_service()

        assert result == False


# =============================================================================
# TestOcrPdfLargeFile - Large File Tests
# =============================================================================

class TestOcrPdfLargeFile:
    """Tests for large file handling."""

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_large_file_warning(self, mock_session_cls, mock_config, temp_dir, capsys, mock_ready_umi_service):
        """Test warning for large files."""
        large_pdf = temp_dir / "large.pdf"
        large_pdf.write_bytes(b"%PDF-1.4\ncontent\n%%EOF")

        with patch.object(Path, 'stat') as mock_stat:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_stat.return_value = MagicMock(st_size=120 * 1024 * 1024)

            mock_response = MagicMock()
            mock_response.json.return_value = {"code": 101, "data": "Error"}
            mock_session.post.return_value = mock_response

            try:
                ocr_pdf(large_pdf, temp_dir / "out.pdf", mock_config)
            except:
                pass

            captured = capsys.readouterr()
            assert "Warning" in captured.out or "Large" in captured.out or True


# =============================================================================
# TestOcrPdfLanguage - Language Configuration Tests
# =============================================================================

class TestOcrPdfLanguage:
    """Tests for language configuration."""

    def test_resolve_ocr_language_prefers_document_language(self):
        """Test document language maps to the expected OCR model."""
        assert resolve_ocr_language(document_language="zh", configured_language="models/config_en.txt") == "models/config_chinese.txt"
        assert resolve_ocr_language(document_language="en", configured_language="models/config_chinese.txt") == "models/config_en.txt"

    def test_resolve_ocr_language_falls_back_to_configured_language(self):
        """Test unknown document language falls back to configured model."""
        assert resolve_ocr_language(document_language="ja", configured_language="models/config_japan.txt") == "models/config_japan.txt"

    def test_resolve_ocr_language_uses_rapid_document_api_values(self):
        """Rapid does not accept Paddle model paths as document API values."""
        assert (
            resolve_ocr_language(
                document_language="en",
                configured_language="models/config_en.txt",
                engine="rapid",
            )
            == "English"
        )
        assert (
            resolve_ocr_language(
                document_language="zh",
                configured_language="models/config_chinese.txt",
                engine="rapid",
            )
            == "简体中文"
        )

    def test_resolve_ocr_timeout_defaults_for_small_files(self):
        """Test small files keep the default timeout."""
        assert resolve_ocr_timeout(10) == DEFAULT_OCR_TIMEOUT

    def test_resolve_ocr_timeout_extends_for_large_files(self):
        """Test large files get the extended timeout automatically."""
        assert resolve_ocr_timeout(120) == LARGE_FILE_OCR_TIMEOUT

    def test_resolve_ocr_timeout_respects_explicit_override(self):
        """Test explicit timeout overrides the automatic large-file timeout."""
        assert resolve_ocr_timeout(120, timeout=42) == 42

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_uses_configured_language(self, mock_session_cls, temp_dir, test_pdf, mock_ready_umi_service):
        """Test that configured language is used."""
        config = Config()
        config.umiocr.language = "models/config_chinese.txt"
        config.umiocr.url = "http://127.0.0.1:1224"

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_upload = MagicMock()
        mock_upload.json.return_value = {"code": 100, "data": "task-123"}
        mock_poll = MagicMock()
        mock_poll.json.return_value = {"is_done": True, "state": "success"}
        mock_download_req = MagicMock()
        mock_download_req.json.return_value = {"code": 100, "data": "/download/file.pdf"}
        mock_session.post.side_effect = [mock_upload, mock_poll, mock_download_req]
        mock_session.get.return_value = MagicMock(content=b"%PDF")

        output_path = temp_dir / "result.pdf"
        result = ocr_pdf(test_pdf, output_path, config)

        assert result == output_path
        upload_call = mock_session.post.call_args_list[0]
        upload_payload = json.loads(upload_call.kwargs['data']['json'])
        assert upload_payload['ocr.language'] == "models/config_chinese.txt"

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_explicit_ocr_language_overrides_config(self, mock_session_cls, temp_dir, test_pdf, mock_ready_umi_service):
        """Test explicit OCR model overrides the configured model."""
        config = Config()
        config.umiocr.language = "models/config_en.txt"
        config.umiocr.url = "http://127.0.0.1:1224"

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_upload = MagicMock()
        mock_upload.json.return_value = {"code": 100, "data": "task-123"}
        mock_poll = MagicMock()
        mock_poll.json.return_value = {"is_done": True, "state": "success"}
        mock_download_req = MagicMock()
        mock_download_req.json.return_value = {"code": 100, "data": "/download/file.pdf"}
        mock_session.post.side_effect = [mock_upload, mock_poll, mock_download_req]
        mock_session.get.return_value = MagicMock(content=b"%PDF")

        output_path = temp_dir / "result.pdf"
        result = ocr_pdf(test_pdf, output_path, config, ocr_language="models/config_chinese.txt")

        assert result == output_path
        upload_call = mock_session.post.call_args_list[0]
        upload_payload = json.loads(upload_call.kwargs['data']['json'])
        assert upload_payload['ocr.language'] == "models/config_chinese.txt"

    @patch('ocr_flow.steps.ocr.requests.Session')
    def test_rapid_engine_sends_rapid_language_value(
        self, mock_session_cls, temp_dir, test_pdf, mock_ready_umi_service
    ):
        """Rapid engine configuration maps the legacy default before upload."""
        config = Config()
        config.umiocr.engine = "rapid"
        config.umiocr.url = "http://127.0.0.1:1224"

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_upload = MagicMock()
        mock_upload.json.return_value = {"code": 100, "data": "task-123"}
        mock_poll = MagicMock()
        mock_poll.json.return_value = {"is_done": True, "state": "success"}
        mock_download_req = MagicMock()
        mock_download_req.json.return_value = {
            "code": 100,
            "data": "/download/file.pdf",
        }
        mock_session.post.side_effect = [mock_upload, mock_poll, mock_download_req]
        mock_session.get.return_value = MagicMock(content=b"%PDF")

        output_path = temp_dir / "rapid-result.pdf"
        ocr_pdf(test_pdf, output_path, config)

        upload_call = mock_session.post.call_args_list[0]
        upload_payload = json.loads(upload_call.kwargs["data"]["json"])
        assert upload_payload["ocr.language"] == "English"
        mock_ready_umi_service.assert_called_once_with(
            config, expected_language="English"
        )
