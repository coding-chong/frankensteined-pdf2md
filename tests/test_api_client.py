#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for API client utilities.

Test suite using mocked HTTP responses to test:
- RetrySession class
- check_url_accessible function
- download_file function
- Error handling and retry logic
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock, Mock
import requests

from ocr_flow.utils.api_client import (
    RetrySession,
    check_url_accessible,
    download_file,
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
def retry_session():
    """Create a RetrySession instance."""
    return RetrySession(max_retries=3, retry_delay=0.1, timeout=30)


# =============================================================================
# TestRetrySession - Retry Logic Tests
# =============================================================================

class TestRetrySession:
    """Tests for RetrySession class."""

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    def test_request_success(self, mock_request, retry_session):
        """Test successful request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        result = retry_session.request('GET', 'http://example.com')

        assert result == mock_response
        mock_request.assert_called_once()

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    @patch('ocr_flow.utils.api_client.time.sleep')
    def test_request_retry_on_failure(self, mock_sleep, mock_request, retry_session):
        """Test retry on request failure."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        # Fail twice, succeed on third attempt
        mock_request.side_effect = [
            requests.exceptions.ConnectionError(),
            requests.exceptions.ConnectionError(),
            mock_response
        ]

        result = retry_session.request('GET', 'http://example.com')

        assert result == mock_response
        assert mock_request.call_count == 3
        # Should have slept between retries
        assert mock_sleep.call_count == 2

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    @patch('ocr_flow.utils.api_client.time.sleep')
    def test_request_max_retries_exceeded(self, mock_sleep, mock_request, retry_session):
        """Test that exception is raised after max retries."""
        mock_request.side_effect = requests.exceptions.ConnectionError()

        with pytest.raises(requests.exceptions.ConnectionError):
            retry_session.request('GET', 'http://example.com')

        assert mock_request.call_count == 3

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    def test_request_with_custom_timeout(self, mock_request, retry_session):
        """Test that custom timeout is applied."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        retry_session.request('GET', 'http://example.com', timeout=60)

        # Check that timeout was passed
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs['timeout'] == 60

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    def test_request_uses_default_timeout(self, mock_request, retry_session):
        """Test that default timeout is used when not specified."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        retry_session.request('GET', 'http://example.com')

        call_kwargs = mock_request.call_args[1]
        assert call_kwargs['timeout'] == 30

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    def test_get_method(self, mock_request, retry_session):
        """Test GET method wrapper."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        result = retry_session.get('http://example.com')

        assert result == mock_response
        mock_request.assert_called_with('GET', 'http://example.com', timeout=30)

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    def test_post_method(self, mock_request, retry_session):
        """Test POST method wrapper."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        result = retry_session.post('http://example.com', json={'key': 'value'})

        assert result == mock_response
        mock_request.assert_called()

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    def test_put_method(self, mock_request, retry_session):
        """Test PUT method wrapper."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        result = retry_session.put('http://example.com', data=b'data')

        assert result == mock_response
        mock_request.assert_called()

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    @patch('ocr_flow.utils.api_client.time.sleep')
    def test_retry_on_timeout(self, mock_sleep, mock_request, retry_session):
        """Test retry on timeout error."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_request.side_effect = [
            requests.exceptions.Timeout(),
            mock_response
        ]

        result = retry_session.request('GET', 'http://example.com')

        assert result == mock_response
        assert mock_request.call_count == 2

    @patch('ocr_flow.utils.api_client.requests.Session.request')
    @patch('ocr_flow.utils.api_client.time.sleep')
    def test_retry_on_http_error(self, mock_sleep, mock_request, retry_session):
        """Test retry on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_request.side_effect = [
            requests.exceptions.HTTPError(),
            mock_response
        ]

        result = retry_session.request('GET', 'http://example.com')

        assert result == mock_response


# =============================================================================
# TestCheckUrlAccessible - URL Check Tests
# =============================================================================

class TestCheckUrlAccessible:
    """Tests for check_url_accessible function."""

    @patch('ocr_flow.utils.api_client.requests.head')
    def test_url_accessible(self, mock_head):
        """Test when URL is accessible."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        result = check_url_accessible('http://example.com')

        assert result == True

    @patch('ocr_flow.utils.api_client.requests.head')
    def test_url_not_accessible_404(self, mock_head):
        """Test when URL returns 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_head.return_value = mock_response

        result = check_url_accessible('http://example.com/notfound')

        assert result == False

    @patch('ocr_flow.utils.api_client.requests.head')
    def test_url_not_accessible_500(self, mock_head):
        """Test when URL returns 500."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_head.return_value = mock_response

        result = check_url_accessible('http://example.com/error')

        assert result == False

    @patch('ocr_flow.utils.api_client.requests.head')
    def test_url_connection_error(self, mock_head):
        """Test handling connection error."""
        mock_head.side_effect = requests.exceptions.ConnectionError()

        result = check_url_accessible('http://nonexistent.example')

        assert result == False

    @patch('ocr_flow.utils.api_client.requests.head')
    def test_url_timeout(self, mock_head):
        """Test handling timeout."""
        mock_head.side_effect = requests.exceptions.Timeout()

        result = check_url_accessible('http://slow.example')

        assert result == False

    @patch('ocr_flow.utils.api_client.requests.head')
    def test_url_custom_timeout(self, mock_head):
        """Test using custom timeout."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        check_url_accessible('http://example.com', timeout=60)

        mock_head.assert_called_with('http://example.com', timeout=60, verify=False)

    @patch('ocr_flow.utils.api_client.requests.head')
    def test_url_ssl_disabled(self, mock_head):
        """Test that SSL verification is disabled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        check_url_accessible('https://example.com')

        call_kwargs = mock_head.call_args[1]
        assert call_kwargs['verify'] == False


# =============================================================================
# TestDownloadFile - File Download Tests
# =============================================================================

class TestDownloadFile:
    """Tests for download_file function."""

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_success(self, mock_get, temp_dir):
        """Test successful file download."""
        # Mock response with content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'test content']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'downloaded.txt'
        result = download_file('http://example.com/file.txt', output_path)

        assert result == 12  # len(b'test content')
        assert output_path.exists()
        assert output_path.read_bytes() == b'test content'

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_multiple_chunks(self, mock_get, temp_dir):
        """Test download with multiple chunks."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [
            b'chunk1',
            b'chunk2',
            b'chunk3'
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'downloaded.txt'
        result = download_file('http://example.com/file.txt', output_path)

        assert result == 18  # 6 + 6 + 6 bytes
        assert output_path.read_bytes() == b'chunk1chunk2chunk3'

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_http_error(self, mock_get, temp_dir):
        """Test handling HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'downloaded.txt'

        with pytest.raises(requests.exceptions.HTTPError):
            download_file('http://example.com/notfound.txt', output_path)

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_connection_error(self, mock_get, temp_dir):
        """Test handling connection error."""
        mock_get.side_effect = requests.exceptions.ConnectionError()

        output_path = temp_dir / 'downloaded.txt'

        with pytest.raises(requests.exceptions.ConnectionError):
            download_file('http://nonexistent.example/file.txt', output_path)

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_creates_file(self, mock_get, temp_dir):
        """Test that download creates the output file."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'data']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'new_file.txt'
        assert not output_path.exists()

        download_file('http://example.com/file.txt', output_path)

        assert output_path.exists()

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_custom_chunk_size(self, mock_get, temp_dir):
        """Test using custom chunk size."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'data']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'downloaded.txt'
        download_file('http://example.com/file.txt', output_path, chunk_size=16384)

        mock_get.assert_called_once()

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_custom_timeout(self, mock_get, temp_dir):
        """Test using custom timeout."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'data']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'downloaded.txt'
        download_file('http://example.com/file.txt', output_path, timeout=300)

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs['timeout'] == 300

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_ssl_verification(self, mock_get, temp_dir):
        """Test SSL verification setting."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'data']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'downloaded.txt'

        # Test with verify_ssl=True
        download_file('https://example.com/file.txt', output_path, verify_ssl=True)

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs['verify'] == True

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_empty_file(self, mock_get, temp_dir):
        """Test downloading empty file."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = []
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        output_path = temp_dir / 'empty.txt'
        result = download_file('http://example.com/empty.txt', output_path)

        assert result == 0
        assert output_path.exists()
        assert output_path.read_bytes() == b''

    @patch('ocr_flow.utils.api_client.requests.get')
    def test_download_overwrites_existing(self, mock_get, temp_dir):
        """Test that download overwrites existing file."""
        output_path = temp_dir / 'existing.txt'
        output_path.write_bytes(b'old content')

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'new content']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        download_file('http://example.com/file.txt', output_path)

        assert output_path.read_bytes() == b'new content'
