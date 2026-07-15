#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Image download module for Markdown files.

Downloads images from URLs and replaces references with local paths.
Based on confuse_md_fix/fix_markdown.py
"""

import re
import time
import json
import hashlib
import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Supported image extensions
IMAGE_EXTENSIONS = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/svg+xml': '.svg',
    'image/bmp': '.bmp',
}

COMMON_IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp']


def extract_image_urls(content: str) -> List[Tuple[str, str]]:
    """Extract all image URLs from Markdown content.

    Returns:
        List of (alt_text, url) tuples
    """
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    return re.findall(pattern, content)


def is_http_url(url: str) -> bool:
    """Check if URL is HTTP/HTTPS."""
    return url.startswith('http://') or url.startswith('https://')


def is_local_image_path(url: str) -> bool:
    """Check if URL is a local image path (relative path like images/xxx.jpg)."""
    if is_http_url(url):
        return False
    # Check if it looks like an image path
    ext = Path(url.split('?')[0]).suffix.lower()
    return ext in COMMON_IMAGE_EXTS


def get_extension_from_url(url: str) -> str:
    """Get file extension from URL."""
    path = url.split('?')[0].split('#')[0]
    ext = Path(path).suffix.lower()
    if ext in COMMON_IMAGE_EXTS:
        return ext
    return None


def generate_filename(url: str, content_type: str = None, index: int = 1) -> str:
    """Generate a unique filename for an image."""
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]

    ext = get_extension_from_url(url)

    if not ext and content_type:
        content_type = content_type.lower().split(';')[0].strip()
        ext = IMAGE_EXTENSIONS.get(content_type)

    if not ext:
        ext = '.png'

    return f"img_{index:03d}{ext}"


def download_image(
    url: str,
    output_dir: Path,
    timeout: int = 30,
    retries: int = 3,
    delay: float = 1.0,
) -> Tuple[bool, str]:
    """Download a single image.

    Args:
        url: Image URL
        output_dir: Directory to save image
        timeout: Request timeout in seconds
        retries: Number of retry attempts
        delay: Delay after successful download (to avoid rate limiting)

    Returns:
        (success, filename_or_error_message)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                stream=True,
            )

            if response.status_code != 200:
                if attempt == retries - 1:
                    return False, f"HTTP {response.status_code}"
                continue

            # Get content type
            content_type = response.headers.get('Content-Type', '')

            # Generate filename
            ext = get_extension_from_url(url)
            if not ext:
                content_type_lower = content_type.lower().split(';')[0].strip()
                ext = IMAGE_EXTENSIONS.get(content_type_lower, '.png')

            # Use URL hash for unique filename
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
            filename = f"img_{url_hash}{ext}"
            output_path = output_dir / filename

            # Save image
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Delay to avoid rate limiting
            time.sleep(delay)

            return True, filename

        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                return False, str(e)
            time.sleep(delay)

    return False, "Max retries exceeded"


def download_images(
    md_path: Path,
    images_base_dir: Path,
    page_num: int,
    source_images_dir: Optional[Path] = None,
    logger=None,
    max_workers: int = 3,
) -> Tuple[bool, List[str]]:
    """Download all images in a Markdown file.

    Args:
        md_path: Path to Markdown file
        images_base_dir: Base directory for images (final/images)
        page_num: Page number (for subdirectory naming)
        source_images_dir: Source directory for local images (intermediate/mineru_md/part_XXX)
        logger: Logger instance for logging (optional)
        max_workers: Maximum concurrent downloads

    Returns:
        (all_success, list_of_failed_urls)
    """
    md_path = Path(md_path)
    images_base_dir = Path(images_base_dir)

    # Read content
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract images
    images = extract_image_urls(content)

    if not images:
        return True, []

    # Create page-specific directory
    page_images_dir = images_base_dir / f"p{page_num:03d}"
    page_images_dir.mkdir(parents=True, exist_ok=True)

    url_mapping = {}  # original_url -> local_filename
    failed_urls = []

    # Handle local images (from MinerU output)
    local_images = [(alt, url) for alt, url in images if is_local_image_path(url)]
    if local_images and source_images_dir:
        source_dir = Path(source_images_dir)
        for alt, url in local_images:
            # Source image path (relative to source_images_dir)
            source_image = source_dir / url
            if source_image.exists():
                # Copy to destination
                dest_image = page_images_dir / source_image.name
                shutil.copy2(source_image, dest_image)
                url_mapping[url] = dest_image.name
            else:
                # Try without the images/ prefix
                source_image = source_dir / "images" / Path(url).name
                if source_image.exists():
                    dest_image = page_images_dir / source_image.name
                    shutil.copy2(source_image, dest_image)
                    url_mapping[url] = dest_image.name
                else:
                    failed_urls.append(url)

    # Handle HTTP URLs
    http_images = [(alt, url) for alt, url in images if is_http_url(url)]

    for idx, (alt, url) in enumerate(http_images, 1):
        success, result = download_image(url, page_images_dir)

        if success:
            url_mapping[url] = result
        else:
            failed_urls.append(url)
            msg = f"Failed to download: {url[:50]}..."
            if logger:
                logger.warning(msg)
            print(f"  {msg}")

    # Replace URLs in content
    def replace_url(match):
        alt = match.group(1)
        url = match.group(2)
        if url in url_mapping:
            # Use relative path
            return f'![{alt}](images/p{page_num:03d}/{url_mapping[url]})'
        return match.group(0)

    content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_url, content)

    # Write back
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return len(failed_urls) == 0, failed_urls
