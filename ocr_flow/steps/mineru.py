#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MinerU API client for PDF to Markdown conversion."""

import os
import time
import zipfile
import tempfile
from pathlib import Path
from typing import Optional

import requests
import urllib3

# Disable SSL warnings for CDN downloads
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MinerUClient:
    """Client for MinerU API."""

    BASE_URL = "https://mineru.net/api/v4"

    def __init__(self, config):
        """Initialize client with config."""
        self.token = config.mineru.api_token
        if not self.token:
            raise ValueError("MinerU API token not configured")

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        # Model version for complex layouts (recommended for chip manuals)
        self.model_version = "vlm"

        # Polling settings
        self.poll_interval = 5  # seconds
        self.max_retries = 3
        self.retry_delay = 10  # seconds

    def upload_and_convert(self, pdf_path: Path, output_dir: Path) -> Path:
        """Upload PDF and convert to Markdown.

        This is the main entry point that combines upload, poll, and download.

        Args:
            pdf_path: Path to input PDF
            output_dir: Directory to save output files

        Returns:
            Path to the extracted Markdown file
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Check file size (200MB limit)
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 200:
            raise ValueError(f"File too large: {file_size_mb:.1f}MB (limit: 200MB)")

        # Step 1: Get upload URL
        batch_id, upload_url = self._get_upload_url(pdf_path.name)

        # Step 2: Upload file
        self._upload_file(pdf_path, upload_url)

        # Step 3: Poll for results
        zip_url = self._poll_for_result(batch_id)

        # Step 4: Download and extract
        md_file = self._download_and_extract(zip_url, output_dir)

        return md_file

    def _get_upload_url(self, filename: str) -> tuple:
        """Get upload URL from MinerU API."""
        data = {
            "files": [{"name": filename}],
            "model_version": self.model_version
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.BASE_URL}/file-urls/batch",
                    headers=self.headers,
                    json=data,
                    timeout=30
                )
                result = response.json()

                if result.get("code") != 0:
                    raise RuntimeError(f"Failed to get upload URL: {result.get('msg')}")

                batch_id = result["data"]["batch_id"]
                upload_url = result["data"]["file_urls"][0]
                return batch_id, upload_url

            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"Network error: {e}")
                time.sleep(self.retry_delay)

    def _upload_file(self, pdf_path: Path, upload_url: str):
        """Upload file to the provided URL."""
        with open(pdf_path, "rb") as f:
            for attempt in range(self.max_retries):
                try:
                    response = requests.put(upload_url, data=f, timeout=300)
                    if response.status_code == 200:
                        return
                    raise RuntimeError(f"Upload failed with status {response.status_code}")
                except requests.exceptions.RequestException as e:
                    if attempt == self.max_retries - 1:
                        raise RuntimeError(f"Upload error: {e}")
                    time.sleep(self.retry_delay)
                    f.seek(0)  # Reset file position for retry

    def _poll_for_result(self, batch_id: str) -> str:
        """Poll API for conversion result."""
        while True:
            try:
                response = requests.get(
                    f"{self.BASE_URL}/extract-results/batch/{batch_id}",
                    headers=self.headers,
                    timeout=30
                )
                result = response.json()

                if result.get("code") != 0:
                    raise RuntimeError(f"Poll error: {result.get('msg')}")

                extract_result = result.get("data", {}).get("extract_result", [])
                if not extract_result:
                    time.sleep(self.poll_interval)
                    continue

                for item in extract_result:
                    state = item.get("state")

                    if state == "done":
                        return item.get("full_zip_url")

                    elif state == "failed":
                        raise RuntimeError(f"Conversion failed: {item.get('err_msg')}")

                    elif state == "running":
                        progress = item.get("extract_progress", {})
                        extracted = progress.get("extracted_pages", 0)
                        total = progress.get("total_pages", "?")
                        print(f"  Progress: {extracted}/{total} pages")
                        time.sleep(self.poll_interval)

                    else:
                        time.sleep(self.poll_interval)

            except requests.exceptions.RequestException as e:
                print(f"  Poll error: {e}, retrying...")
                time.sleep(self.poll_interval)

    def _download_and_extract(self, zip_url: str, output_dir: Path) -> Path:
        """Download and extract the result ZIP."""
        import ssl
        import urllib.request
        import subprocess

        # Try Python download first
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.options |= ssl.OP_LEGACY_SERVER_CONNECT

        last_error = None
        tmp_path = None

        # Method 1: Try Python urllib
        for attempt in range(self.max_retries):
            try:
                request = urllib.request.Request(
                    zip_url,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )

                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name

                with urllib.request.urlopen(request, timeout=120, context=ssl_context) as response:
                    with open(tmp_path, 'wb') as f:
                        f.write(response.read())

                # Extract
                with zipfile.ZipFile(tmp_path, 'r') as zf:
                    zf.extractall(output_dir)

                os.unlink(tmp_path)

                # Find MD file
                return self._find_md_file(output_dir)

            except Exception as e:
                last_error = e
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                print(f"  Download attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

        # Method 2: Fallback to PowerShell (Windows)
        if os.name == 'nt':
            print("  Trying PowerShell fallback...")
            try:
                tmp_path = os.path.join(tempfile.gettempdir(), "mineru_download.zip")

                ps_cmd = f'''
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls11
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {{$true}}
$client = New-Object System.Net.WebClient
$client.DownloadFile('{zip_url}', '{tmp_path}')
'''

                result = subprocess.run(
                    ['powershell', '-Command', ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                if result.returncode == 0 and os.path.exists(tmp_path):
                    # Extract
                    with zipfile.ZipFile(tmp_path, 'r') as zf:
                        zf.extractall(output_dir)

                    os.unlink(tmp_path)
                    return self._find_md_file(output_dir)
                else:
                    print(f"  PowerShell failed: {result.stderr}")

            except Exception as e:
                print(f"  PowerShell fallback failed: {e}")

        raise RuntimeError(f"Failed to download after {self.max_retries} attempts: {last_error}")

    def _find_md_file(self, output_dir: Path) -> Path:
        """Find the main Markdown file in output directory."""
        md_files = list(output_dir.glob("*.md"))
        if md_files:
            return md_files[0]

        # Check for subdirectories
        for subdir in output_dir.iterdir():
            if subdir.is_dir():
                md_files = list(subdir.glob("*.md"))
                if md_files:
                    return md_files[0]

        raise RuntimeError("No Markdown file found in result")

    def convert(self, pdf_path: Path, output_dir: Path) -> Path:
        """Convert PDF to Markdown (alias for upload_and_convert)."""
        return self.upload_and_convert(pdf_path, output_dir)
