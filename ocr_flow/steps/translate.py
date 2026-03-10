#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Translation module using BabelDOC."""

import subprocess
from pathlib import Path
from typing import Optional


def translate_pdf(
    input_path: Path,
    output_path: Path,
    config,
    timeout: int = 3600,
) -> Path:
    """Translate a PDF using BabelDOC.

    Args:
        input_path: Path to input PDF
        output_path: Path to save translated PDF (for reference, actual output is in output_dir)
        config: Config object with babeldoc settings
        timeout: Maximum processing time in seconds

    Returns:
        Path to the translated PDF
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build BabelDOC command
    if config.babeldoc.path:
        cmd_base = f"uv run --directory {config.babeldoc.path} babeldoc"
    else:
        cmd_base = "babeldoc"

    cmd = [
        cmd_base if ' ' not in cmd_base else cmd_base,
        '--files', str(input_path),
        '--output', str(output_dir),
        '--use-alternating-pages-dual',
        '--dual-translate-first',  # Translation first, then original
        '--watermark-output-mode=no_watermark',
        '--lang-in', config.babeldoc.lang_in,
        '--lang-out', config.babeldoc.lang_out,
    ]

    # Add OpenAI config if enabled
    if config.babeldoc.openai:
        cmd.extend([
            '--openai',
            '--openai-model', config.babeldoc.openai_model,
            '--openai-base-url', config.babeldoc.openai_base_url,
            '--openai-api-key', config.babeldoc.openai_api_key,
        ])

    print(f"  Running: {' '.join(cmd)}")

    # Run BabelDOC
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=' ' in cmd_base
    )

    if result.returncode != 0:
        raise RuntimeError(f"BabelDOC failed: {result.stderr}")

    # Find the output file
    # BabelDOC outputs: {name}.{lang_out}.dual.pdf
    dual_pdf = find_dual_pdf(output_dir, input_path)

    if not dual_pdf:
        raise RuntimeError(f"Could not find translated PDF in {output_dir}")

    # Rename to expected output path if different
    if dual_pdf != output_path:
        # Just return the dual_pdf path since it's already in the output directory
        pass

    return dual_pdf


def find_dual_pdf(output_dir: Path, original_path: Path) -> Optional[Path]:
    """Find the dual PDF output from BabelDOC.

    BabelDOC outputs:
    - {name}.{lang_out}.dual.pdf (bilingual with alternating pages)
    - {name}.{lang_out}.mono.pdf (translation only)
    """
    output_dir = Path(output_dir)
    original_name = original_path.stem

    # Look for dual PDF
    for pdf in output_dir.glob("*.dual.pdf"):
        return pdf

    # Try with original name prefix
    for pdf in output_dir.glob(f"{original_name}*.dual.pdf"):
        return pdf

    # Fallback: any PDF with 'dual' in name
    for pdf in output_dir.glob("*dual*.pdf"):
        return pdf

    return None


def check_babeldoc_available(config) -> bool:
    """Check if BabelDOC is available.

    Returns:
        True if BabelDOC can be invoked
    """
    if config.babeldoc.path:
        babel_path = Path(config.babeldoc.path)
        if not babel_path.exists():
            return False
        # Check for uv
        try:
            subprocess.run(['uv', '--version'], capture_output=True, check=True)
            return True
        except:
            return False

    # Check global install
    try:
        subprocess.run(['babeldoc', '--version'], capture_output=True, check=True)
        return True
    except:
        return False
