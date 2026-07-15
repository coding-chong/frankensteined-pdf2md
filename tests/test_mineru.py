#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for MinerU API client module.

Test suite using mocked HTTP responses to test:
- Client initialization
- Upload functionality
- Polling for results
- Download and extraction
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import zipfile
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import ocr_flow.steps.mineru as mineru
from ocr_flow.steps.mineru import MinerUClient
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
    """Create a mock config with MinerU token."""
    config = Config()
    config.mineru.api_token = "test-api-token-12345"
    return config


@pytest.fixture
def mock_config_no_token():
    """Create a config without API token."""
    config = Config()
    config.mineru.api_token = ""
    return config


@pytest.fixture
def test_pdf(temp_dir):
    """Create a test PDF file."""
    pdf_path = temp_dir / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test content\n%%EOF")
    return pdf_path


@pytest.fixture
def large_pdf(temp_dir):
    """Create a PDF larger than 200MB (simulated)."""
    pdf_path = temp_dir / "large.pdf"
    # Create a smaller file for testing, we'll mock the size check
    pdf_path.write_bytes(b"%PDF-1.4\n%small\n%%EOF")
    return pdf_path


@pytest.fixture
def mock_zip_file(temp_dir):
    """Create a mock ZIP file with Markdown."""
    zip_path = temp_dir / "result.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("output.md", "# Test Document\n\nContent here.")
    return zip_path


# =============================================================================
# TestMinerUClientInit - Initialization Tests
# =============================================================================

class TestMinerUClientInit:
    """Tests for MinerUClient initialization."""

    def test_client_init(self, mock_config):
        """Test basic client initialization."""
        client = MinerUClient(mock_config)

        assert client.token == "test-api-token-12345"
        assert client.model_version == "vlm"
        assert client.poll_interval == 5
        assert client.poll_timeout == 900
        assert client.upload_timeout == 120

    def test_client_missing_token(self, mock_config_no_token):
        """Test initialization without API token raises error."""
        with pytest.raises(ValueError, match="API token not configured"):
            MinerUClient(mock_config_no_token)

    def test_client_headers(self, mock_config):
        """Test that correct headers are set."""
        client = MinerUClient(mock_config)

        assert "Authorization" in client.headers
        assert client.headers["Authorization"] == "Bearer test-api-token-12345"
        assert client.headers["Content-Type"] == "application/json"


# =============================================================================
# TestGetUploadUrl - Upload URL Tests
# =============================================================================

class TestGetUploadUrl:
    """Tests for _get_upload_url method."""

    @patch('ocr_flow.steps.mineru.requests.post')
    def test_get_upload_url_success(self, mock_post, mock_config):
        """Test successful upload URL retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://upload.url/file"]
            }
        }
        mock_post.return_value = mock_response

        client = MinerUClient(mock_config)
        batch_id, upload_url = client._get_upload_url("test.pdf")

        assert batch_id == "batch-123"
        assert upload_url == "https://upload.url/file"

    @patch('ocr_flow.steps.mineru.requests.post')
    def test_get_upload_url_failure(self, mock_post, mock_config):
        """Test upload URL retrieval failure."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 1,
            "msg": "Invalid token"
        }
        mock_post.return_value = mock_response

        client = MinerUClient(mock_config)

        with pytest.raises(RuntimeError, match="Failed to get upload URL"):
            client._get_upload_url("test.pdf")

    @patch('ocr_flow.steps.mineru.requests.post')
    def test_get_upload_url_retry(self, mock_post, mock_config):
        """Test retry on network error."""
        import requests

        # First call fails, second succeeds
        mock_post.side_effect = [
            requests.exceptions.RequestException("Network error"),
            MagicMock(json=lambda: {"code": 0, "data": {"batch_id": "b", "file_urls": ["url"]}})
        ]

        client = MinerUClient(mock_config)
        batch_id, upload_url = client._get_upload_url("test.pdf")

        assert batch_id == "b"
        assert mock_post.call_count == 2


# =============================================================================
# TestUploadFile - File Upload Tests
# =============================================================================

class TestUploadFile:
    """Tests for _upload_file method."""

    @patch('ocr_flow.steps.mineru.requests.put')
    def test_upload_file_success(self, mock_put, mock_config, test_pdf):
        """Test successful file upload."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_put.return_value = mock_response

        client = MinerUClient(mock_config)
        client._upload_file(test_pdf, "https://upload.url")

        mock_put.assert_called_once()
        assert mock_put.call_args.kwargs["timeout"] == client.upload_timeout

    @patch('ocr_flow.steps.mineru.requests.put')
    def test_upload_file_failure(self, mock_put, mock_config, test_pdf):
        """Test file upload failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_put.return_value = mock_response

        client = MinerUClient(mock_config)

        with pytest.raises(RuntimeError, match="Upload failed"):
            client._upload_file(test_pdf, "https://upload.url")

    @patch('ocr_flow.steps.mineru.requests.put')
    def test_upload_file_retry(self, mock_put, mock_config, test_pdf):
        """Test upload retry on error."""
        import requests

        mock_put.side_effect = [
            requests.exceptions.RequestException("Error"),
            MagicMock(status_code=200)
        ]

        client = MinerUClient(mock_config)
        client._upload_file(test_pdf, "https://upload.url")

        assert mock_put.call_count == 2


# =============================================================================
# TestPollForResult - Polling Tests
# =============================================================================

class TestPollForResult:
    """Tests for _poll_for_result method."""

    @patch('ocr_flow.steps.mineru.requests.get')
    def test_poll_success(self, mock_get, mock_config):
        """Test successful polling."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "data": {
                "extract_result": [{
                    "state": "done",
                    "full_zip_url": "https://result.url/zip"
                }]
            }
        }
        mock_get.return_value = mock_response

        client = MinerUClient(mock_config)
        result = client._poll_for_result("batch-123")

        assert result == "https://result.url/zip"

    @patch('ocr_flow.steps.mineru.requests.get')
    def test_poll_failure(self, mock_get, mock_config):
        """Test polling when conversion fails."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "data": {
                "extract_result": [{
                    "state": "failed",
                    "err_msg": "Conversion error"
                }]
            }
        }
        mock_get.return_value = mock_response

        client = MinerUClient(mock_config)

        with pytest.raises(RuntimeError, match="Conversion failed"):
            client._poll_for_result("batch-123")

    @patch('ocr_flow.steps.mineru.requests.get')
    @patch('ocr_flow.steps.mineru.time.sleep')
    def test_poll_running_then_done(self, mock_sleep, mock_get, mock_config):
        """Test polling through running state to done."""
        # Create responses for running and done states
        running_response = MagicMock()
        running_response.json.return_value = {
            "code": 0,
            "data": {"extract_result": [{"state": "running", "extract_progress": {"extracted_pages": 1, "total_pages": 5}}]}
        }

        done_response = MagicMock()
        done_response.json.return_value = {
            "code": 0,
            "data": {"extract_result": [{"state": "done", "full_zip_url": "https://result.url"}]}
        }

        mock_get.side_effect = [running_response, done_response]

        client = MinerUClient(mock_config)
        result = client._poll_for_result("batch-123")

        assert result == "https://result.url"
        assert mock_get.call_count == 2

    @patch('ocr_flow.steps.mineru.requests.get')
    @patch('ocr_flow.steps.mineru.time.sleep')
    @patch('ocr_flow.steps.mineru.time.monotonic')
    def test_poll_empty_result_logs_queue_and_times_out(
        self, mock_monotonic, mock_sleep, mock_get, mock_config, capsys
    ):
        response = MagicMock()
        response.json.return_value = {
            "code": 0,
            "data": {"extract_result": []},
        }
        mock_get.return_value = response
        mock_monotonic.side_effect = [0, 0, 901]

        client = MinerUClient(mock_config)

        with pytest.raises(RuntimeError, match="batch-123.*900 seconds"):
            client._poll_for_result("batch-123")

        assert "Queued: waiting for MinerU batch batch-123" in capsys.readouterr().out
        mock_sleep.assert_called_once_with(client.poll_interval)

    @patch('ocr_flow.steps.mineru.requests.get')
    @patch('ocr_flow.steps.mineru.time.sleep')
    @patch('ocr_flow.steps.mineru.time.monotonic')
    def test_poll_logs_nonterminal_service_state(
        self, mock_monotonic, mock_sleep, mock_get, mock_config, capsys
    ):
        waiting_response = MagicMock()
        waiting_response.json.return_value = {
            "code": 0,
            "data": {"extract_result": [{"state": "waiting-file"}]},
        }
        done_response = MagicMock()
        done_response.json.return_value = {
            "code": 0,
            "data": {
                "extract_result": [
                    {"state": "done", "full_zip_url": "https://result.url"}
                ]
            },
        }
        mock_get.side_effect = [waiting_response, done_response]
        mock_monotonic.side_effect = [0, 0, 5]

        client = MinerUClient(mock_config)

        assert client._poll_for_result("batch-123") == "https://result.url"
        assert "state: waiting-file" in capsys.readouterr().out
        mock_sleep.assert_called_once_with(client.poll_interval)


# =============================================================================
# TestDownloadAndExtract - Download Tests
# =============================================================================

class TestDownloadAndExtract:
    """Tests for _download_and_extract method."""

    @patch('ocr_flow.steps.mineru.requests.Session.get')
    def test_download_success(self, mock_get, mock_config, temp_dir, mock_zip_file):
        """Test successful download and extraction."""
        # Read the mock zip file content
        zip_content = mock_zip_file.read_bytes()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_content = lambda chunk_size: [zip_content]
        mock_get.return_value = mock_response

        client = MinerUClient(mock_config)

        # Create output directory with markdown file for _find_md_file
        output_dir = temp_dir / "extracted"
        output_dir.mkdir()

        result = client._download_and_extract("https://result.url", output_dir)

        # Should find the markdown file
        assert result is not None
        assert mock_get.call_args.kwargs["stream"] is True
        assert "verify" not in mock_get.call_args.kwargs

    def test_find_md_file(self, mock_config, temp_dir):
        """Test finding markdown file in output."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Create markdown file
        md_file = output_dir / "output.md"
        md_file.write_text("# Test", encoding='utf-8')

        client = MinerUClient(mock_config)
        result = client._find_md_file(output_dir)

        assert result == md_file

    def test_find_md_file_in_subdirectory(self, mock_config, temp_dir):
        """Test finding markdown file in subdirectory."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        subdir = output_dir / "subdir"
        subdir.mkdir()
        md_file = subdir / "content.md"
        md_file.write_text("# Test", encoding='utf-8')

        client = MinerUClient(mock_config)
        result = client._find_md_file(output_dir)

        assert result == md_file

    def test_find_md_file_not_found(self, mock_config, temp_dir):
        """Test error when no markdown file found."""
        output_dir = temp_dir / "empty"
        output_dir.mkdir()

        client = MinerUClient(mock_config)

        with pytest.raises(RuntimeError, match="No Markdown file found"):
            client._find_md_file(output_dir)


# =============================================================================
# TestConvert - Convert Method Tests
# =============================================================================

class TestConvert:
    """Tests for convert method."""

    @patch.object(MinerUClient, '_download_and_extract')
    @patch.object(MinerUClient, '_poll_for_result')
    @patch.object(MinerUClient, '_upload_file')
    @patch.object(MinerUClient, '_get_upload_url')
    def test_convert_full_flow(
        self,
        mock_get_url,
        mock_upload,
        mock_poll,
        mock_download,
        mock_config,
        test_pdf,
        temp_dir
    ):
        """Test full convert flow."""
        mock_get_url.return_value = ("batch-123", "https://upload.url")
        mock_upload.return_value = None
        mock_poll.return_value = "https://result.url"
        mock_download.return_value = temp_dir / "output.md"

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        client = MinerUClient(mock_config)
        client.convert(test_pdf, output_dir)

        mock_get_url.assert_called_once()
        mock_upload.assert_called_once()
        mock_poll.assert_called_once()
        mock_download.assert_called_once()

    def test_convert_file_too_large(self, mock_config, temp_dir):
        """Test error when file exceeds size limit."""
        # Create a file that we'll pretend is large
        large_pdf = temp_dir / "fake_large.pdf"
        large_pdf.write_bytes(b"%PDF-1.4\n%test\n%%EOF")

        # Create a stat result with large size and required attributes
        from unittest.mock import MagicMock

        mock_stat = MagicMock()
        mock_stat.st_size = 250 * 1024 * 1024  # 250MB
        mock_stat.st_mode = 0o100644  # Regular file mode
        mock_stat.st_ino = 0
        mock_stat.st_dev = 0
        mock_stat.st_nlink = 1
        mock_stat.st_uid = 0
        mock_stat.st_gid = 0
        mock_stat.st_atime = 0
        mock_stat.st_mtime = 0
        mock_stat.st_ctime = 0

        # Only mock stat for the specific file, not the whole Path class
        original_stat = Path.stat

        def mock_stat_if_large_file(self, *args, **kwargs):
            if self == large_pdf:
                return mock_stat
            return original_stat(self, *args, **kwargs)

        with patch.object(Path, 'stat', mock_stat_if_large_file):
            client = MinerUClient(mock_config)

            with pytest.raises(ValueError, match="File too large"):
                client.convert(large_pdf, temp_dir)


# =============================================================================
# TestUploadAndConvert - Integration Tests
# =============================================================================

class TestUploadAndConvert:
    """Integration tests for upload_and_convert method."""

    @patch.object(MinerUClient, '_download_and_extract')
    @patch.object(MinerUClient, '_poll_for_result')
    @patch.object(MinerUClient, '_upload_file')
    @patch.object(MinerUClient, '_get_upload_url')
    def test_upload_and_convert(
        self,
        mock_get_url,
        mock_upload,
        mock_poll,
        mock_download,
        mock_config,
        test_pdf,
        temp_dir
    ):
        """Test upload_and_convert is alias for convert."""
        mock_get_url.return_value = ("batch", "url")
        mock_upload.return_value = None
        mock_poll.return_value = "result_url"
        mock_download.return_value = temp_dir / "out.md"

        output_dir = temp_dir / "out"
        output_dir.mkdir()

        client = MinerUClient(mock_config)
        result = client.upload_and_convert(test_pdf, output_dir)

        assert result == temp_dir / "out.md"


class TestCdnDownloadFallback:
    """Tests for the public-DNS CDN fallback used after normal TLS attempts."""

    @patch('ocr_flow.steps.mineru.requests.get')
    def test_resolve_public_cdn_ipv4_ignores_intercepted_addresses(
        self, mock_get, mock_config
    ):
        response = MagicMock()
        response.json.return_value = {
            "Answer": [
                {"type": 1, "data": "198.18.0.8"},
                {"type": 1, "data": "8.222.80.133"},
                {"type": 28, "data": "2001:db8::1"},
                {"type": 1, "data": "not-an-ip"},
            ]
        }
        mock_get.return_value = response

        client = MinerUClient(mock_config)

        assert client._resolve_public_cdn_ipv4(
            "cdn-mineru.openxlab.org.cn"
        ) == ["8.222.80.133"]
        mock_get.assert_called_once()
        assert mock_get.call_args.args[0] == "https://dns.google/resolve"
        assert "verify" not in mock_get.call_args.kwargs

    def test_resolve_public_cdn_ipv4_rejects_non_cdn_hostname(self, mock_config):
        client = MinerUClient(mock_config)

        assert client._resolve_public_cdn_ipv4("example.com") == []

    @patch.object(MinerUClient, '_resolve_public_cdn_ipv4', return_value=['8.222.80.133'])
    @patch('ocr_flow.steps.mineru.subprocess.run')
    def test_resolved_curl_download_uses_hostname_and_public_ip(
        self, mock_run, mock_resolve, mock_config, temp_dir
    ):
        destination = temp_dir / "result.zip"

        def write_archive(command, **_kwargs):
            output_path = Path(command[command.index('-o') + 1])
            output_path.write_bytes(b'zip-content')
            return SimpleNamespace(returncode=0)

        mock_run.side_effect = write_archive
        client = MinerUClient(mock_config)

        assert client._download_with_resolved_curl(
            "curl",
            "https://cdn-mineru.openxlab.org.cn/pdf/result.zip",
            str(destination),
        )
        command = mock_run.call_args.args[0]
        assert "-k" not in command
        assert command[command.index('--proto') + 1] == "=https"
        assert command[command.index('--proto-redir') + 1] == "=https"
        assert command[command.index('--resolve') + 1] == (
            "cdn-mineru.openxlab.org.cn:443:8.222.80.133"
        )
        assert command[command.index('--noproxy') + 1] == "*"

    def test_resolved_curl_keeps_extracted_markdown_when_temp_cleanup_races(
        self, mock_config, temp_dir
    ):
        output_dir = temp_dir / "result"
        output_dir.mkdir()
        client = MinerUClient(mock_config)
        original_unlink = mineru.os.unlink
        fallback_completed = False

        def write_archive(_curl_path, _url, temporary_path):
            nonlocal fallback_completed
            with zipfile.ZipFile(temporary_path, "w") as archive:
                archive.writestr("full.md", "# Extracted")
            fallback_completed = True
            return True

        def disappear_during_cleanup(path):
            if fallback_completed and str(path).endswith(".zip"):
                original_unlink(path)
                raise FileNotFoundError(path)
            return original_unlink(path)

        with (
            patch.object(
                mineru.requests.Session,
                "get",
                side_effect=mineru.requests.exceptions.SSLError(),
            ),
            patch.object(mineru.shutil, "which", return_value="curl"),
            patch.object(
                mineru.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=35),
            ),
            patch.object(
                MinerUClient,
                "_download_with_resolved_curl",
                side_effect=write_archive,
            ),
            patch.object(mineru.os, "unlink", side_effect=disappear_during_cleanup),
            patch.object(mineru.os, "name", "posix"),
        ):
            result = client._download_and_extract(
                "https://cdn-mineru.openxlab.org.cn/result.zip", output_dir
            )

        assert result == output_dir / "full.md"

    def test_resolved_curl_retries_when_archive_disappears_before_extraction(
        self, mock_config, temp_dir
    ):
        output_dir = temp_dir / "result"
        output_dir.mkdir()
        client = MinerUClient(mock_config)
        attempts = 0
        archive_paths = []

        def write_archive(_curl_path, _url, temporary_path):
            nonlocal attempts
            attempts += 1
            archive_paths.append(temporary_path)
            with zipfile.ZipFile(temporary_path, "w") as archive:
                archive.writestr("full.md", "# Extracted")
            if attempts == 1:
                Path(temporary_path).unlink()
            return True

        with (
            patch.object(
                mineru.requests.Session,
                "get",
                side_effect=mineru.requests.exceptions.SSLError(),
            ),
            patch.object(mineru.shutil, "which", return_value="curl"),
            patch.object(
                mineru.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=35),
            ),
            patch.object(
                MinerUClient,
                "_download_with_resolved_curl",
                side_effect=write_archive,
            ),
            patch.object(mineru.os, "name", "posix"),
        ):
            result = client._download_and_extract(
                "https://cdn-mineru.openxlab.org.cn/result.zip", output_dir
            )

        assert attempts == 2
        assert all(Path(path).parent == output_dir for path in archive_paths)
        assert result == output_dir / "full.md"

    def test_resolved_curl_keeps_new_markdown_after_extract_file_not_found(
        self, mock_config, temp_dir
    ):
        output_dir = temp_dir / "result"
        output_dir.mkdir()
        client = MinerUClient(mock_config)

        class PartialArchive:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extractall(self, _destination):
                (output_dir / "full.md").write_text("# Extracted", encoding="utf-8")
                raise FileNotFoundError("late archive member")

        with (
            patch.object(
                mineru.requests.Session,
                "get",
                side_effect=mineru.requests.exceptions.SSLError(),
            ),
            patch.object(mineru.shutil, "which", return_value="curl"),
            patch.object(
                mineru.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=35),
            ),
            patch.object(
                MinerUClient,
                "_download_with_resolved_curl",
                return_value=True,
            ) as mock_download,
            patch.object(mineru.zipfile, "ZipFile", return_value=PartialArchive()),
            patch.object(mineru.os, "name", "posix"),
        ):
            result = client._download_and_extract(
                "https://cdn-mineru.openxlab.org.cn/result.zip", output_dir
            )

        assert mock_download.call_count == 1
        assert result == output_dir / "full.md"

    def test_resolved_curl_does_not_accept_stale_markdown_after_extract_error(
        self, mock_config, temp_dir
    ):
        output_dir = temp_dir / "result"
        output_dir.mkdir()
        (output_dir / "full.md").write_text("# Previous", encoding="utf-8")
        client = MinerUClient(mock_config)

        class BrokenArchive:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extractall(self, _destination):
                raise FileNotFoundError("late archive member")

        with (
            patch.object(
                mineru.requests.Session,
                "get",
                side_effect=mineru.requests.exceptions.SSLError(),
            ),
            patch.object(mineru.shutil, "which", return_value="curl"),
            patch.object(
                mineru.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=35),
            ),
            patch.object(
                MinerUClient,
                "_download_with_resolved_curl",
                return_value=True,
            ) as mock_download,
            patch.object(mineru.zipfile, "ZipFile", return_value=BrokenArchive()),
            patch.object(mineru.os, "name", "posix"),
        ):
            with pytest.raises(RuntimeError, match="All download methods failed"):
                client._download_and_extract(
                    "https://cdn-mineru.openxlab.org.cn/result.zip", output_dir
                )

        assert mock_download.call_count == 2

    def test_resolved_curl_accepts_replaced_markdown_after_extract_error(
        self, mock_config, temp_dir
    ):
        output_dir = temp_dir / "result"
        output_dir.mkdir()
        (output_dir / "full.md").write_text("# Previous", encoding="utf-8")
        client = MinerUClient(mock_config)

        class ReplacesMarkdownThenRaises:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extractall(self, _destination):
                (output_dir / "full.md").write_text("# Extracted", encoding="utf-8")
                raise FileNotFoundError("late archive member")

        with (
            patch.object(
                mineru.requests.Session,
                "get",
                side_effect=mineru.requests.exceptions.SSLError(),
            ),
            patch.object(mineru.shutil, "which", return_value="curl"),
            patch.object(
                mineru.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=35),
            ),
            patch.object(
                MinerUClient,
                "_download_with_resolved_curl",
                return_value=True,
            ) as mock_download,
            patch.object(
                mineru.zipfile,
                "ZipFile",
                return_value=ReplacesMarkdownThenRaises(),
            ),
            patch.object(mineru.os, "name", "posix"),
        ):
            result = client._download_and_extract(
                "https://cdn-mineru.openxlab.org.cn/result.zip", output_dir
            )

        assert mock_download.call_count == 1
        assert result == output_dir / "full.md"

    def test_download_error_kind_does_not_echo_signed_url(self, mock_config):
        client = MinerUClient(mock_config)
        error = RuntimeError(
            "failed https://cdn.example/result.zip?signature=private-value"
        )

        assert client._download_error_kind(error) == "RuntimeError"
