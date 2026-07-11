#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Translation module using BabelDOC."""

import subprocess
from pathlib import Path
from typing import Optional, Sequence

from ocr_flow.config import normalize_primary_font_family
from ocr_flow.runtime import BabelDocRuntime, require_babeldoc_runtime, resolve_babeldoc_runtime


def _format_command_for_log(command: Sequence[str]) -> str:
    """Format a BabelDOC command without exposing sensitive option values."""
    redacted = list(command)
    for index, argument in enumerate(redacted[:-1]):
        if argument == "--openai-api-key":
            redacted[index + 1] = "***"
    return " ".join(redacted)


def _redact_secret(value: str, secret: str) -> str:
    """Remove a configured secret from subprocess output before surfacing it."""
    return value.replace(secret, "***") if secret else value


def _build_babeldoc_command(
    input_path: Path,
    output_dir: Path,
    config,
    *,
    skip_clean: bool,
    ocr_workaround: bool,
    runtime: Optional[BabelDocRuntime] = None,
) -> list[str]:
    """Build the BabelDOC command without formatting it for display."""
    runtime = runtime or resolve_babeldoc_runtime(config)
    command = [
        "uv",
        "run",
        "--directory",
        str(runtime.checkout),
        "--locked",
        "babeldoc",
    ]

    command.extend(
        [
            "--files",
            str(input_path),
            "--output",
            str(output_dir),
            "--use-alternating-pages-dual",
            "--dual-translate-first",
            "--watermark-output-mode=no_watermark",
            "--lang-in",
            config.babeldoc.lang_in,
            "--lang-out",
            config.babeldoc.lang_out,
            "--qps",
            str(config.babeldoc.qps),
        ]
    )

    primary_font_family = normalize_primary_font_family(
        config.babeldoc.primary_font_family
    )
    if primary_font_family:
        command.extend(["--primary-font-family", primary_font_family])

    if ocr_workaround:
        command.append("--ocr-workaround")
    if skip_clean:
        command.append("--skip-clean")

    if config.babeldoc.openai:
        command.extend(
            [
                "--openai",
                "--openai-model",
                config.babeldoc.openai_model,
                "--openai-base-url",
                config.babeldoc.openai_base_url,
                "--openai-api-key",
                config.babeldoc.openai_api_key,
            ]
        )

    return command


def translate_pdf(
    input_path: Path,
    output_path: Path,
    config,
    skip_clean: bool = False,
    ocr_workaround: bool = False,
    logger=None,
    timeout: int = 3600,
) -> Path:
    """Translate a PDF using BabelDOC.

    Args:
        input_path: Path to input PDF
        output_path: Path to save translated PDF (for reference, actual output is in output_dir)
        config: Config object with babeldoc settings
        skip_clean: Whether to skip font subsetting (use when compressing with Ghostscript)
        logger: Logger instance for logging (optional)
        timeout: Maximum processing time in seconds

    Returns:
        Path to the translated PDF
    """
    input_path = Path(input_path).resolve()  # Use absolute path
    output_path = Path(output_path).resolve()
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime = require_babeldoc_runtime(config)
    cmd = _build_babeldoc_command(
        input_path,
        output_dir,
        config,
        skip_clean=skip_clean,
        ocr_workaround=ocr_workaround,
        runtime=runtime,
    )

    msg = f"Running: {_format_command_for_log(cmd)}"
    if logger:
        logger.info(msg)
    print(f"  {msg}")

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
            raise RuntimeError(
                "Translation API rate limited. Please wait and retry later."
            )
        elif (
            "api key" in combined or "api_key" in combined or "invalid key" in combined
        ):
            raise RuntimeError(
                "Invalid API key. Check babeldoc.openai_api_key in config."
            )
        elif "not found" in combined or "command not found" in combined:
            raise RuntimeError("BabelDOC Runtime is unavailable. Run `ocr-flow runtime setup`.")
        elif "connection" in combined or "timeout" in combined:
            raise RuntimeError(
                "Network error connecting to translation API. Check your network connection."
            )
        elif "insufficient" in combined or "quota" in combined:
            raise RuntimeError("API quota exhausted. Check your API usage limits.")

        # Generic error with truncated output
        error_msg = (
            result.stderr[:500]
            if result.stderr
            else result.stdout[:500] or "Unknown error"
        )
        error_msg = _redact_secret(error_msg, config.babeldoc.openai_api_key)
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
    try:
        require_babeldoc_runtime(config)
        subprocess.run(["uv", "--version"], capture_output=True, check=True, timeout=10)
        return True
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False
