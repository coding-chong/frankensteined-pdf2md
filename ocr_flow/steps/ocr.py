#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OCR module using UMI OCR HTTP API."""

import json
import time
from pathlib import Path
from typing import Optional

import requests

from ..config import (
    UMIOCR_ENGINE_LANGUAGE_VALUES,
    normalize_umiocr_engine,
    resolve_umiocr_language,
)
from ..self_check import ensure_umi_ocr_service

DEFAULT_OCR_TIMEOUT = 600
LARGE_FILE_THRESHOLD_MB = 100
LARGE_FILE_OCR_TIMEOUT = 21600

DOCUMENT_LANGUAGE_TO_OCR_MODEL = UMIOCR_ENGINE_LANGUAGE_VALUES["paddle"]


def create_local_umi_session() -> requests.Session:
    """Create a session for local UMI OCR traffic that bypasses env proxies."""
    session = requests.Session()
    session.trust_env = False
    return session


def resolve_ocr_language(
    document_language: Optional[str] = None,
    configured_language: Optional[str] = None,
    engine: str = "paddle",
) -> str:
    """Resolve the UMI OCR document-API language for the selected engine."""
    return resolve_umiocr_language(
        normalize_umiocr_engine(engine),
        document_language=document_language,
        configured_language=configured_language,
    )


def resolve_ocr_timeout(file_size_mb: float, timeout: Optional[int] = None) -> int:
    """Resolve OCR timeout, extending it automatically for large files."""
    if timeout is not None:
        return timeout
    if file_size_mb > LARGE_FILE_THRESHOLD_MB:
        return LARGE_FILE_OCR_TIMEOUT
    return DEFAULT_OCR_TIMEOUT


def ocr_pdf(
    input_path: Path,
    output_path: Path,
    config,
    logger=None,
    timeout: Optional[int] = None,
    ocr_language: Optional[str] = None,
) -> Path:
    """Process a scanned PDF with OCR using UMI OCR.

    Args:
        input_path: Path to input PDF
        output_path: Path to save OCR'd PDF
        config: Config object with umiocr settings
        logger: Logger instance for logging (optional)
        timeout: Maximum processing time in seconds
        ocr_language: Explicit UMI OCR model path to use

    Returns:
        Path to the OCR'd PDF
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    file_size_mb = input_path.stat().st_size / (1024 * 1024)
    if file_size_mb > LARGE_FILE_THRESHOLD_MB:
        msg = f"Warning: Large file ({file_size_mb:.1f}MB). OCR may take a long time."
        if logger:
            logger.warning(msg)
        print(f"  {msg}")
    msg = f"File size: {file_size_mb:.1f}MB"
    if logger:
        logger.info(msg)
    print(f"  {msg}")

    resolved_timeout = resolve_ocr_timeout(file_size_mb, timeout)
    engine = normalize_umiocr_engine(config.umiocr.engine)
    language = ocr_language or resolve_ocr_language(
        configured_language=config.umiocr.language,
        engine=engine,
    )
    url = config.umiocr.url

    msg = f"OCR engine/language: {engine}/{language}"
    if logger:
        logger.info(msg)
    print(f"  {msg}")

    msg = f"OCR timeout: {resolved_timeout}s"
    if logger:
        logger.info(msg)
    print(f"  {msg}")

    service_result = ensure_umi_ocr_service(config, expected_language=language)
    if not service_result['ok']:
        raise RuntimeError(service_result['message'])

    session = create_local_umi_session()

    with open(input_path, 'rb') as f:
        files = {'file': f}
        data = {
            'json': json.dumps({
                'doc.extractionMode': 'fullPage',
                'ocr.language': language,
            }, ensure_ascii=False)
        }

        response = session.post(
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

    start_time = time.time()
    while True:
        if time.time() - start_time > resolved_timeout:
            raise RuntimeError("OCR timeout")

        response = session.post(
            f"{url}/api/doc/result",
            json={'id': task_id, 'is_data': False},
            timeout=30
        )

        try:
            result = response.json()
        except json.JSONDecodeError:
            raise RuntimeError("Poll failed: invalid JSON response")
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

    if result.get('state') != 'success':
        raise RuntimeError(f"OCR failed: {result.get('message', 'Unknown error')}")

    response = session.post(
        f"{url}/api/doc/download",
        json={'id': task_id, 'file_types': ['pdfLayered']},
        timeout=30
    )

    try:
        result = response.json()
    except json.JSONDecodeError:
        raise RuntimeError("Download request failed: invalid JSON response")
    if result.get('code') != 100:
        raise RuntimeError(f"Download request failed: {result.get('data')}")

    download_url = result['data']
    if download_url.startswith('/'):
        download_url = f"{url}{download_url}"

    response = session.get(download_url, timeout=120)
    response.raise_for_status()

    with open(output_path, 'wb') as f:
        f.write(response.content)

    try:
        session.get(f"{url}/api/doc/clear/{task_id}", timeout=10)
    except Exception:
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
    session = create_local_umi_session()
    try:
        response = session.get(f"{url}/api/doc/get_options", timeout=5)
        return response.status_code == 200
    except Exception:
        return False
