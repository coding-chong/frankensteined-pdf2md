#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OCR module using UMI OCR HTTP API."""

import json
import time
from pathlib import Path

import requests


def ocr_pdf(
    input_path: Path,
    output_path: Path,
    config,
    logger=None,
    timeout: int = 600,
) -> Path:
    """Process a scanned PDF with OCR using UMI OCR.

    Args:
        input_path: Path to input PDF
        output_path: Path to save OCR'd PDF
        config: Config object with umiocr settings
        logger: Logger instance for logging (optional)
        timeout: Maximum processing time in seconds

    Returns:
        Path to the OCR'd PDF
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Check file size
    file_size_mb = input_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 100:
        msg = f"Warning: Large file ({file_size_mb:.1f}MB). OCR may take a long time."
        if logger:
            logger.warning(msg)
        print(f"  {msg}")
    msg = f"File size: {file_size_mb:.1f}MB"
    if logger:
        logger.info(msg)
    print(f"  {msg}")

    url = config.umiocr.url
    language = config.umiocr.language

    # Step 1: Upload PDF
    with open(input_path, 'rb') as f:
        files = {'file': f}
        data = {
            'json': json.dumps({
                'doc.extractionMode': 'fullPage',  # Force OCR on entire page
                'ocr.language': language,
            })
        }

        response = requests.post(
            f"{url}/api/doc/upload",
            files=files,
            data=data,
            timeout=60
        )

    try:
        result = response.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Upload failed: invalid JSON response (status {response.status_code})")
    if result.get('code') != 100:
        raise RuntimeError(f"Upload failed: {result.get('data')}")

    task_id = result['data']
    msg = f"OCR task started: {task_id}"
    if logger:
        logger.info(msg)
    print(f"  {msg}")

    # Step 2: Poll for completion
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            raise RuntimeError("OCR timeout")

        response = requests.post(
            f"{url}/api/doc/result",
            json={'id': task_id, 'is_data': False},
            timeout=30
        )

        try:
            result = response.json()
        except json.JSONDecodeError:
            raise RuntimeError(f"Poll failed: invalid JSON response")
        if result.get('is_done'):
            break

        state = result.get('state', 'unknown')
        processed = result.get('processed_count', 0)
        total = result.get('pages_count', '?')
        msg = f"OCR progress: {processed}/{total} pages ({state})"
        if logger:
            logger.info(msg)
        print(f"  {msg}")

        time.sleep(3)

    # Check final state
    if result.get('state') != 'success':
        raise RuntimeError(f"OCR failed: {result.get('message', 'Unknown error')}")

    # Step 3: Get download URL
    response = requests.post(
        f"{url}/api/doc/download",
        json={'id': task_id, 'file_types': ['pdfLayered']},
        timeout=30
    )

    try:
        result = response.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Download request failed: invalid JSON response")
    if result.get('code') != 100:
        raise RuntimeError(f"Download request failed: {result.get('data')}")

    download_url = result['data']

    # Step 4: Download the file
    if download_url.startswith('/'):
        download_url = f"{url}{download_url}"

    response = requests.get(download_url, timeout=120)
    response.raise_for_status()  # Verify download succeeded

    with open(output_path, 'wb') as f:
        f.write(response.content)

    # Step 5: Cleanup task
    try:
        requests.get(f"{url}/api/doc/clear/{task_id}", timeout=10)
    except:
        pass

    msg = f"OCR completed: {output_path}"
    if logger:
        logger.info(msg)
    print(f"  {msg}")
    return output_path


def check_umi_ocr_service(url: str = "http://127.0.0.1:1224") -> bool:
    """Check if UMI OCR service is running.

    Args:
        url: UMI OCR service URL

    Returns:
        True if service is available
    """
    try:
        response = requests.get(f"{url}/api/doc/get_options", timeout=5)
        return response.status_code == 200
    except:
        return False
