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
    input_path = Path(input_path).resolve()  # Use absolute path
    output_path = Path(output_path).resolve()
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build BabelDOC command as a list
    if config.babeldoc.path:
        cmd = [
            'uv', 'run', '--directory', config.babeldoc.path, 'babeldoc',
        ]
    else:
        cmd = ['babeldoc']

    cmd.extend([
        '--files', str(input_path),
        '--output', str(output_dir),
        '--use-alternating-pages-dual',
        '--dual-translate-first',  # Translation first, then original
        '--watermark-output-mode=no_watermark',
        '--lang-in', config.babeldoc.lang_in,
        '--lang-out', config.babeldoc.lang_out,
    ])

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
    )

    if result.returncode != 0:
        stderr = result.stderr.lower() if result.stderr else ""
        stdout = result.stdout.lower() if result.stdout else ""
        combined = stderr + stdout

        # Provide user-friendly error messages
        if "rate limit" in combined or "rate_limit" in combined:
            raise RuntimeError("Translation API rate limited. Please wait and retry later.")
        elif "api key" in combined or "api_key" in combined or "invalid key" in combined:
            raise RuntimeError("Invalid API key. Check babeldoc.openai_api_key in config.")
        elif "not found" in combined or "command not found" in combined:
            if config.babeldoc.path:
                raise RuntimeError(f"BabelDOC not found at {config.babeldoc.path}. Check babeldoc.path in config.")
            else:
                raise RuntimeError("BabelDOC not found. Install with: pip install BabelDOC")
        elif "connection" in combined or "timeout" in combined:
            raise RuntimeError(f"Network error connecting to translation API. Check your network connection.")
        elif "insufficient" in combined or "quota" in combined:
            raise RuntimeError("API quota exhausted. Check your API usage limits.")

        # Generic error with truncated output
        error_msg = result.stderr[:500] if result.stderr else result.stdout[:500] or "Unknown error"
        raise RuntimeError(f"BabelDOC failed: {error_msg}")

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
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    # Check global install
    try:
        subprocess.run(['babeldoc', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
