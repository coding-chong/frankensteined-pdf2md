#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PDF compression using Ghostscript."""

import subprocess
import shutil
from pathlib import Path
from typing import Optional


def find_ghostscript() -> Optional[str]:
    """Find Ghostscript executable.

    Returns:
        Path to Ghostscript executable or None if not found.
    """
    # Common names
    names = ['gswin64c', 'gswin32c', 'gs', 'gswin64', 'gswin32']

    for name in names:
        path = shutil.which(name)
        if path:
            return path

    # Check common install locations on Windows
    import os
    if os.name == 'nt':
        common_paths = [
            Path('C:/Program Files/gs'),
            Path('C:/Program Files (x86)/gs'),
            Path('E:/gs-portable'),
        ]

        for base in common_paths:
            if base.exists():
                # Find the latest version
                versions = sorted(base.iterdir(), reverse=True)
                for version_dir in versions:
                    bin_dir = version_dir / 'bin'
                    if bin_dir.exists():
                        for name in ['gswin64c.exe', 'gswin32c.exe']:
                            exe = bin_dir / name
                            if exe.exists():
                                return str(exe)

    return None


def compress_pdf(
    input_path: Path,
    output_dir: Path,
    config=None,
    quality: str = "ebook",
) -> Path:
    """Compress PDF using Ghostscript.

    Args:
        input_path: Path to input PDF
        output_dir: Directory to save compressed PDF
        config: Config object (for ghostscript_path and quality)
        quality: Compression quality (screen/ebook/printer/prepress)

    Returns:
        Path to compressed PDF
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get Ghostscript path
    if config and config.compress.ghostscript_path:
        gs_path = config.compress.ghostscript_path
    else:
        gs_path = find_ghostscript()

    if not gs_path:
        raise RuntimeError("Ghostscript not found. Install from https://ghostscript.com/")

    # Get quality setting
    if config and config.compress.quality:
        quality = config.compress.quality

    # Quality presets
    quality_settings = {
        'screen': '/screen',  # 72 dpi, smallest size
        'ebook': '/ebook',    # 150 dpi, good balance
        'printer': '/printer',  # 300 dpi, high quality
        'prepress': '/prepress',  # 300 dpi, maximum quality
    }

    gs_quality = quality_settings.get(quality, '/ebook')

    # Output path with total count placeholder (will be set by caller)
    output_name = f"compressed_{input_path.stem}.pdf"
    output_path = output_dir / output_name

    # Ghostscript command
    cmd = [
        gs_path,
        '-sDEVICE=pdfwrite',
        f'-dPDFSETTINGS={gs_quality}',
        '-dCompatibilityLevel=1.4',
        '-dNOPAUSE',
        '-dQUIET',
        '-dBATCH',
        f'-sOutputFile={output_path}',
        str(input_path),
    ]

    # Run Ghostscript
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Ghostscript failed: {result.stderr}")

    return output_path


def compress_batch(
    input_files: list,
    output_dir: Path,
    config=None,
    total_count: int = None,
) -> list:
    """Compress multiple PDF files.

    Args:
        input_files: List of input PDF paths
        output_dir: Directory to save compressed PDFs
        config: Config object
        total_count: Total number of files (for naming)

    Returns:
        List of compressed PDF paths
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if total_count is None:
        total_count = len(input_files)

    compressed_files = []

    for i, input_path in enumerate(input_files, 1):
        # Rename with part number
        output_name = f"compressed_part_{i:03d}_of_{total_count:03d}.pdf"
        temp_output = compress_pdf(input_path, output_dir, config)
        final_output = output_dir / output_name
        temp_output.rename(final_output)
        compressed_files.append(final_output)

    return compressed_files
