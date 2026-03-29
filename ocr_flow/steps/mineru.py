#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MinerU API client for PDF to Markdown conversion."""

import os
import time
import zipfile
import tempfile
import ssl
import json
from pathlib import Path
from typing import Optional

import requests
import urllib3

# Disable SSL warnings for CDN downloads
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MinerUClient:
    """Client for MinerU API."""

    BASE_URL = "https://mineru.net/api/v4"

    def __init__(self, config, use_text_extraction: bool = False):
        """Initialize client with config.

        Args:
            config: Config object with mineru settings
            use_text_extraction: If True, use 'pipeline' model which prioritizes
                text layer extraction. If False, use 'vlm' model which uses
                visual language model. Use True for translated PDFs that have
                background images but also text layers.
        """
        self.token = config.mineru.api_token
        if not self.token:
            raise ValueError("MinerU API token not configured")

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        # Model version selection:
        # - 'vlm': Visual Language Model, good for scanned PDFs but may ignore
        #   text layers when background images are present
        # - 'pipeline': Traditional OCR pipeline, prioritizes text layer extraction
        # Use 'pipeline' for translated PDFs to preserve CJK text from BabelDOC
        self.model_version = "pipeline" if use_text_extraction else "vlm"

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
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    if attempt == self.max_retries - 1:
                        raise RuntimeError(f"Invalid JSON response from API (status {response.status_code})")
                    time.sleep(self.retry_delay)
                    continue

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
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    print(f"  Poll error: invalid JSON response, retrying...")
                    time.sleep(self.poll_interval)
                    continue

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
        """Download and extract the result ZIP.

        Uses .NET WebClient on Windows (bypasses SSL issues with some antivirus software).
        Falls back to other methods if .NET is not available.
        """
        last_error = None
        tmp_path = None

        print("  Downloading result...")

        # Method 1: Try .NET WebClient (works on Windows, bypasses antivirus SSL issues)
        if os.name == 'nt':
            try:
                import clr
                clr.AddReference('System.Net')
                from System.Net import WebClient, SecurityProtocolType, ServicePointManager
                from System import Func, Boolean, Object
                from System.Security.Cryptography.X509Certificates import X509Certificate2
                from System.Net.Security import SslPolicyErrors

                # Configure TLS
                ServicePointManager.SecurityProtocol = (
                    SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls
                )

                # Create a proper delegate for certificate validation
                def validate_cert(sender, certificate, chain, errors):
                    return True

                # Set the callback using a proper delegate type
                from System.Net.Security import RemoteCertificateValidationCallback
                callback = RemoteCertificateValidationCallback(validate_cert)
                ServicePointManager.ServerCertificateValidationCallback = callback

                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name

                client = WebClient()
                client.DownloadFile(zip_url, tmp_path)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    with zipfile.ZipFile(tmp_path, 'r') as zf:
                        zf.extractall(output_dir)
                    os.unlink(tmp_path)
                    return self._find_md_file(output_dir)

            except Exception as e:
                last_error = e
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                print(f"  Method 1 (.NET WebClient) failed: {e}")

        # Method 2: Try requests with custom SSL
        # NOTE: Don't use proxy for MinerU CDN due to SSL certificate issues
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.ssl_ import create_urllib3_context

            class SSLAdapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    ctx = create_urllib3_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
                    ctx.minimum_version = ssl.TLSVersion.TLSv1
                    ctx.maximum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED
                    kwargs['ssl_context'] = ctx
                    return super().init_poolmanager(*args, **kwargs)

            session = requests.Session()
            session.mount('https://', SSLAdapter())
            # Don't use proxy for MinerU CDN (SSL issues with proxy CONNECT tunnel)
            session.trust_env = False  # Disable environment-based proxy settings

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = tmp.name
                response = session.get(zip_url, timeout=120, verify=False, stream=True)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)

            with zipfile.ZipFile(tmp_path, 'r') as zf:
                zf.extractall(output_dir)

            os.unlink(tmp_path)
            return self._find_md_file(output_dir)

        except Exception as e:
            last_error = e
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            print(f"  Method 2 (requests) failed: {e}")

        # Method 3: Try curl with -k flag (skip SSL verification)
        # NOTE: Don't use proxy for MinerU CDN due to SSL issues with CONNECT tunnel
        try:
            import shutil
            import subprocess
            curl_path = shutil.which('curl')
            if curl_path:
                print("  Trying Method 3 (curl -k)...")
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name

                # Don't use proxy - curl -k doesn't work through proxy CONNECT tunnel
                # Create a clean environment without proxy settings
                env = os.environ.copy()
                env.pop('http_proxy', None)
                env.pop('https_proxy', None)
                env.pop('all_proxy', None)
                env.pop('HTTP_PROXY', None)
                env.pop('HTTPS_PROXY', None)
                env.pop('ALL_PROXY', None)

                curl_cmd = [curl_path, '-L', '-k', '-o', tmp_path, zip_url]

                result = subprocess.run(
                    curl_cmd,
                    capture_output=True,
                    timeout=120,
                    env=env  # Use clean environment without proxy
                )
                if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    with zipfile.ZipFile(tmp_path, 'r') as zf:
                        zf.extractall(output_dir)
                    os.unlink(tmp_path)
                    print("  Method 3 (curl) succeeded!")
                    return self._find_md_file(output_dir)
                else:
                    print(f"  Method 3 (curl) failed: returncode={result.returncode}")
            else:
                print("  Method 3 (curl) skipped: curl not found")
        except Exception as e:
            print(f"  Method 3 (curl) failed: {e}")

        # Method 4: Try PowerShell (uses Windows Schannel)
        if os.name == 'nt':
            try:
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name

                ps_cmd = f'''
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls
                try {{
                    Invoke-WebRequest -Uri "{zip_url}" -OutFile "{tmp_path}" -UseBasicParsing
                }} catch {{
                    # Try with ServerCertificateValidationCallback
                    add-type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCertsPolicy {{
    public static void TrustAll() {{
        ServicePointManager.ServerCertificateValidationCallback = (sender, cert, chain, errors) => true;
    }}
}}
"@
[TrustAllCertsPolicy]::TrustAll()
                    Invoke-WebRequest -Uri "{zip_url}" -OutFile "{tmp_path}" -UseBasicParsing
                }}
                '''

                result = subprocess.run(
                    ['powershell', '-Command', ps_cmd],
                    capture_output=True,
                    timeout=120
                )
                if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    with zipfile.ZipFile(tmp_path, 'r') as zf:
                        zf.extractall(output_dir)
                    os.unlink(tmp_path)
                    return self._find_md_file(output_dir)
            except Exception as e:
                print(f"  Method 4 (PowerShell) failed: {e}")

        raise RuntimeError(f"All download methods failed. Last error: {last_error}")

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
