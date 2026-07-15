"""TLS policy regressions for shared HTTP helpers."""

from unittest.mock import MagicMock, patch

from ocr_flow.utils.api_client import check_url_accessible, download_file


@patch("ocr_flow.utils.api_client.requests.head")
def test_url_probe_preserves_certificate_validation(mock_head):
    mock_head.return_value = MagicMock(status_code=200)

    assert check_url_accessible("https://example.com") is True
    assert "verify" not in mock_head.call_args.kwargs


@patch("ocr_flow.utils.api_client.requests.get")
def test_download_verifies_certificates_by_default(mock_get, tmp_path):
    response = MagicMock()
    response.iter_content.return_value = [b"content"]
    mock_get.return_value = response

    assert download_file("https://example.com/file", tmp_path / "file") == 7
    assert "verify" not in mock_get.call_args.kwargs
