#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MinerU API client for PDF to Markdown conversion."""

import os
import time
import zipfile
import tempfile
import json
import ipaddress
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests


PUBLIC_DNS_RESOLVER = "https://dns.google/resolve"
DIRECT_CDN_EXTRACTION_ATTEMPTS = 2


class MinerUClient:
    """Client for MinerU API."""

    BASE_URL = "https://mineru.net/api/v4"

    @staticmethod
    def _download_error_kind(error: BaseException) -> str:
        """Describe a download failure without echoing a signed URL."""
        return type(error).__name__

    @staticmethod
    def _remove_temporary_file(path) -> None:
        """Remove a download temporary file unless another process won the race."""
        if not path:
            return
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass

    @staticmethod
    def _validate_merge_tree(source_dir: Path, output_dir: Path) -> None:
        """Reject unsafe or incompatible entries before moving any result."""
        for source in source_dir.iterdir():
            destination = output_dir / source.name
            if source.is_symlink() or destination.is_symlink():
                raise RuntimeError(
                    f"MinerU archive merge rejects symbolic links: {source.name}"
                )
            if destination.exists() and (
                source.is_dir() != destination.is_dir()
            ):
                raise RuntimeError(
                    f"MinerU archive merge type collision: {source.name}"
                )
            if source.is_dir():
                MinerUClient._validate_merge_tree(source, destination)

    @staticmethod
    def _merge_extracted_tree(source_dir: Path, output_dir: Path) -> None:
        """Move a prevalidated extraction tree into the durable result directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        children = sorted(
            source_dir.iterdir(),
            key=lambda path: (path.suffix.lower() != ".md", path.name),
        )
        for source in children:
            destination = output_dir / source.name
            if source.is_dir() and destination.is_dir():
                MinerUClient._merge_extracted_tree(source, destination)
                source.rmdir()
            elif source.is_dir():
                shutil.move(str(source), str(destination))
            else:
                os.replace(source, destination)

    @staticmethod
    def _extract_archive(archive_path: str, output_dir: Path) -> None:
        """Extract on a short same-volume path before moving durable results.

        Live matrix paths can exceed legacy Win32 path limits once MinerU adds
        UUID directories. Extracting directly into that tree can fail after
        only part of the ZIP is present. A same-volume staging directory keeps
        extraction paths short, then directory moves preserve deep descendants
        without recreating every long path.
        """
        output_dir = output_dir.resolve()
        parents = list(output_dir.parents)
        staging_parent = parents[-3] if len(parents) >= 3 else parents[-1]
        with tempfile.TemporaryDirectory(
            prefix=".ocr-flow-mineru-", dir=staging_parent
        ) as staging_value:
            staging_dir = output_dir.__class__(staging_value)
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(staging_dir)
            MinerUClient._validate_merge_tree(staging_dir, output_dir)
            MinerUClient._merge_extracted_tree(staging_dir, output_dir)

    def __init__(self, config, logger=None):
        """Initialize client with config."""
        self.token = config.mineru.api_token
        if not self.token:
            raise ValueError("MinerU API token not configured")

        self.logger = logger

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        # Model version for complex layouts (recommended for chip manuals)
        self.model_version = "vlm"

        # Polling settings
        self.poll_interval = 5  # seconds
        self.poll_timeout = 15 * 60  # seconds
        self.upload_timeout = 2 * 60  # seconds
        self.max_retries = 3
        self.retry_delay = 10  # seconds

    def _log(self, msg: str, level: str = "info"):
        """Log message to both logger and terminal."""
        if self.logger:
            if level == "info":
                self.logger.info(msg)
            elif level == "warning":
                self.logger.warning(msg)
            elif level == "error":
                self.logger.error(msg)
        print(f"  {msg}")

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
        self._log(f"Requesting MinerU upload URL for {pdf_path.name}")
        batch_id, upload_url = self._get_upload_url(pdf_path.name)

        # Step 2: Upload file
        self._log(
            f"Uploading {pdf_path.name} ({file_size_mb:.2f} MB) "
            f"for batch {batch_id}"
        )
        self._upload_file(pdf_path, upload_url)

        # Step 3: Poll for results
        self._log(f"Upload completed; polling MinerU batch {batch_id}")
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
                    response = requests.put(
                        upload_url, data=f, timeout=self.upload_timeout
                    )
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
        started = time.monotonic()
        empty_polls = 0
        pending_state = None
        pending_state_polls = 0
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= self.poll_timeout:
                raise RuntimeError(
                    f"MinerU batch {batch_id} did not produce a result within "
                    f"{self.poll_timeout} seconds"
                )
            try:
                response = requests.get(
                    f"{self.BASE_URL}/extract-results/batch/{batch_id}",
                    headers=self.headers,
                    timeout=30
                )
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    self._log("Poll error: invalid JSON response, retrying...")
                    time.sleep(self.poll_interval)
                    continue

                if result.get("code") != 0:
                    raise RuntimeError(f"Poll error: {result.get('msg')}")

                extract_result = result.get("data", {}).get("extract_result", [])
                if not extract_result:
                    empty_polls += 1
                    if empty_polls == 1 or empty_polls % 6 == 0:
                        self._log(
                            f"Queued: waiting for MinerU batch {batch_id} "
                            f"({int(elapsed)}s elapsed)"
                        )
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
                        self._log(f"Progress: {extracted}/{total} pages")
                        time.sleep(self.poll_interval)

                    else:
                        if state != pending_state:
                            pending_state = state
                            pending_state_polls = 0
                        pending_state_polls += 1
                        if pending_state_polls == 1 or pending_state_polls % 6 == 0:
                            self._log(
                                f"MinerU batch {batch_id} state: "
                                f"{state or 'unknown'} ({int(elapsed)}s elapsed)"
                            )
                        time.sleep(self.poll_interval)

            except requests.exceptions.RequestException as e:
                self._log(f"Poll error: {e}, retrying...")
                time.sleep(self.poll_interval)

    @staticmethod
    def _resolve_public_cdn_ipv4(hostname: str) -> list[str]:
        """Resolve public CDN IPv4 records when local DNS is intercepted."""
        if not hostname.endswith(".openxlab.org.cn"):
            return []
        try:
            response = requests.get(
                PUBLIC_DNS_RESOLVER,
                params={"name": hostname, "type": "A"},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (
            requests.exceptions.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ):
            return []

        addresses = []
        for answer in payload.get("Answer", []):
            if answer.get("type") != 1:
                continue
            try:
                address = ipaddress.ip_address(answer.get("data", ""))
            except ValueError:
                continue
            if address.version == 4 and address.is_global:
                addresses.append(str(address))
        return list(dict.fromkeys(addresses))

    def _download_with_resolved_curl(
        self, curl_path: str, zip_url: str, temporary_path: str
    ) -> bool:
        """Download a CDN ZIP through a public-DNS IP without proxy DNS."""
        parsed = urlparse(zip_url)
        hostname = parsed.hostname
        if parsed.scheme != "https" or not hostname:
            return False

        for address in self._resolve_public_cdn_ipv4(hostname):
            self._remove_temporary_file(temporary_path)
            command = [
                curl_path,
                "-L",
                "--fail",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--noproxy",
                "*",
                "--resolve",
                f"{hostname}:443:{address}",
                "-o",
                temporary_path,
                zip_url,
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=120,
            )
            if (
                result.returncode == 0
                and os.path.exists(temporary_path)
                and os.path.getsize(temporary_path) > 0
            ):
                return True
        return False

    def _download_and_extract(self, zip_url: str, output_dir: Path) -> Path:
        """Download and extract the result ZIP.

        Tries multiple download methods in order of reliability.
        """
        last_error = None
        tmp_path = None
        curl_path = shutil.which('curl')

        self._log("Downloading result...")

        # Method 1: requests honors the system CA store and environment proxy.
        try:
            session = requests.Session()

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = tmp.name
                response = session.get(zip_url, timeout=120, stream=True)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)

            self._extract_archive(tmp_path, output_dir)

            self._remove_temporary_file(tmp_path)
            return self._find_md_file(output_dir)

        except Exception as e:
            last_error = RuntimeError(self._download_error_kind(e))
            self._remove_temporary_file(tmp_path)
            self._log(
                f"Method 1 (requests) failed: {self._download_error_kind(e)}"
            )

        # Method 2: curl also preserves certificate and proxy policy.
        try:
            if curl_path:
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name

                curl_cmd = [curl_path, '-L', '--fail', '-o', tmp_path, zip_url]

                result = subprocess.run(
                    curl_cmd,
                    capture_output=True,
                    timeout=120,
                )
                if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    self._extract_archive(tmp_path, output_dir)
                    self._remove_temporary_file(tmp_path)
                    return self._find_md_file(output_dir)
                else:
                    self._log(f"Method 2 (curl) failed: returncode={result.returncode}")
            else:
                self._log("Method 2 (curl) skipped: curl not found")
        except Exception as e:
            last_error = RuntimeError(self._download_error_kind(e))
            self._log(f"Method 2 (curl) failed: {self._download_error_kind(e)}")

        # Method 2b: use public DNS when the local resolver intercepts the CDN.
        try:
            if curl_path:
                for attempt in range(DIRECT_CDN_EXTRACTION_ATTEMPTS):
                    with tempfile.NamedTemporaryFile(
                        suffix=".zip", dir=output_dir, delete=False
                    ) as tmp:
                        tmp_path = tmp.name

                    if not self._download_with_resolved_curl(
                        curl_path, zip_url, tmp_path
                    ):
                        last_error = RuntimeError(
                            "curl with public DNS did not produce a CDN result"
                        )
                        self._remove_temporary_file(tmp_path)
                        self._log("Method 2b (curl with public DNS) failed")
                        break

                    self._log(
                        "Method 2b (certificate-validating direct CDN fallback) succeeded"
                    )
                    markdown_before_extraction = {
                        path: path.read_bytes()
                        for path in output_dir.rglob("*.md")
                        if path.is_file()
                    }
                    try:
                        self._extract_archive(tmp_path, output_dir)
                    except FileNotFoundError:
                        self._remove_temporary_file(tmp_path)
                        # A late member path can fail after the result Markdown is durable.
                        updated_markdown = next(
                            (
                                path
                                for path in output_dir.rglob("*.md")
                                if path.is_file()
                                and (
                                    path not in markdown_before_extraction
                                    or path.read_bytes()
                                    != markdown_before_extraction[path]
                                )
                            ),
                            None,
                        )
                        if updated_markdown:
                            self._log(
                                "Method 2b retained updated Markdown after extraction "
                                "FileNotFoundError"
                            )
                            return updated_markdown
                        if attempt + 1 == DIRECT_CDN_EXTRACTION_ATTEMPTS:
                            raise
                        self._log(
                            "Method 2b produced no Markdown after extraction "
                            "FileNotFoundError; retrying"
                        )
                        continue

                    self._remove_temporary_file(tmp_path)
                    return self._find_md_file(output_dir)
            else:
                self._log("Method 2b (curl with public DNS) skipped: curl not found")
        except Exception as e:
            last_error = RuntimeError(self._download_error_kind(e))
            self._remove_temporary_file(tmp_path)
            self._log(
                "Method 2b (curl with public DNS) failed: "
                f"{self._download_error_kind(e)}"
            )

        # Method 3: .NET WebClient uses Windows proxy and certificate policy.
        if os.name == 'nt':
            try:
                import clr
                clr.AddReference('System.Net')
                from System.Net import WebClient

                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name

                client = WebClient()
                client.DownloadFile(zip_url, tmp_path)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    self._extract_archive(tmp_path, output_dir)
                    self._remove_temporary_file(tmp_path)
                    return self._find_md_file(output_dir)

            except Exception as e:
                last_error = RuntimeError(self._download_error_kind(e))
                self._remove_temporary_file(tmp_path)
                self._log(
                    "Method 3 (.NET WebClient) failed: "
                    f"{self._download_error_kind(e)}"
                )

        # Method 4: Try PowerShell (uses Windows Schannel)
        if os.name == 'nt':
            try:
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name

                ps_cmd = (
                    f'Invoke-WebRequest -Uri "{zip_url}" '
                    f'-OutFile "{tmp_path}" -UseBasicParsing'
                )

                result = subprocess.run(
                    ['powershell', '-Command', ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    self._extract_archive(tmp_path, output_dir)
                    self._remove_temporary_file(tmp_path)
                    return self._find_md_file(output_dir)
                last_error = RuntimeError(
                    f"PowerShell download returned {result.returncode}"
                )
                self._remove_temporary_file(tmp_path)
                self._log(f"Method 4 (PowerShell) failed: {last_error}")
            except Exception as e:
                last_error = RuntimeError(self._download_error_kind(e))
                self._remove_temporary_file(tmp_path)
                self._log(
                    "Method 4 (PowerShell) failed: "
                    f"{self._download_error_kind(e)}"
                )

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
