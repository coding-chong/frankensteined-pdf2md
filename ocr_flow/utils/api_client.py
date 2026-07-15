#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""API client utilities."""

import time
from typing import Optional, Dict, Any

import requests
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RetrySession:
    """HTTP session with automatic retry."""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 10.0,
        timeout: int = 30,
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.session = requests.Session()

    def request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """Send request with retry logic."""
        kwargs.setdefault('timeout', self.timeout)

        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                return response

            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

        raise last_error

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request('GET', url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request('POST', url, **kwargs)

    def put(self, url: str, **kwargs) -> requests.Response:
        return self.request('PUT', url, **kwargs)


def check_url_accessible(url: str, timeout: int = 10) -> bool:
    """Check if a URL is accessible.

    Returns:
        True if URL returns 200 OK
    """
    try:
        response = requests.head(url, timeout=timeout)
        return response.status_code == 200
    except:
        return False


def download_file(
    url: str,
    output_path,
    timeout: int = 120,
    chunk_size: int = 8192,
) -> int:
    """Download a file from URL.

    Args:
        url: URL to download
        output_path: Path to save file
        timeout: Request timeout
        chunk_size: Download chunk size

    Returns:
        Number of bytes downloaded
    """
    response = requests.get(
        url,
        stream=True,
        timeout=timeout,
    )
    response.raise_for_status()

    total_bytes = 0
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            f.write(chunk)
            total_bytes += len(chunk)

    return total_bytes
