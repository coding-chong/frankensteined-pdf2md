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
    timeout: int = 600,
) -> Path:
    """Process a scanned PDF with OCR using UMI OCR.

    Args:
        input_path: Path to input PDF
        output_path: Path to save OCR'd PDF
        config: Config object with umiocr settings
        timeout: Maximum processing time in seconds

    Returns:
        Path to the OCR'd PDF
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

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

    result = response.json()
    if result.get('code') != 100:
        raise RuntimeError(f"Upload failed: {result.get('data')}")

    task_id = result['data']
    print(f"  OCR task started: {task_id}")

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

        result = response.json()
        if result.get('is_done'):
            break

        state = result.get('state', 'unknown')
        processed = result.get('processed_count', 0)
        total = result.get('pages_count', '?')
        print(f"  OCR progress: {processed}/{total} pages ({state})")

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

    result = response.json()
    if result.get('code') != 100:
        raise RuntimeError(f"Download request failed: {result.get('data')}")

    download_url = result['data']

    # Step 4: Download the file
    if download_url.startswith('/'):
        download_url = f"{url}{download_url}"

    response = requests.get(download_url, timeout=120)

    with open(output_path, 'wb') as f:
        f.write(response.content)

    # Step 5: Cleanup task
    try:
        requests.get(f"{url}/api/doc/clear/{task_id}", timeout=10)
    except:
        pass

    print(f"  OCR completed: {output_path}")
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
