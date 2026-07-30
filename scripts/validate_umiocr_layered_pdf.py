#!/usr/bin/env python
"""Validate a local UMI OCR engine by producing a readable layered PDF."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = PROJECT_ROOT / "scripts" / "verify_umiocr_runtime.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Scanned PDF input")
    parser.add_argument("--output", required=True, type=Path, help="Layered PDF output")
    parser.add_argument(
        "--umiocr",
        required=True,
        type=Path,
        help="Path to the selected Umi-OCR.exe",
    )
    parser.add_argument(
        "--engine",
        choices=("paddle", "rapid"),
        default="rapid",
        help="Expected engine and checked-in runtime manifest",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "zh"),
        default="en",
        help="Document language used for the local OCR request",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:1224",
        help="Local UMI OCR document API endpoint",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="End-to-end OCR timeout in seconds",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report path for machine-readable validation evidence",
    )
    return parser.parse_args()


def _verify_runtime(executable: Path, engine: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--path",
            str(executable.parent),
            "--engine",
            engine,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"UMI OCR runtime verification failed: {detail}")
    print(result.stdout.strip())


def inspect_layered_pdf(input_path: Path, output_path: Path) -> dict[str, int]:
    """Reject missing, page-mismatched, or textless local OCR output."""
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"UMI OCR did not create a readable output file: {output_path}")

    source = fitz.open(input_path)
    layered = fitz.open(output_path)
    try:
        if source.page_count != layered.page_count:
            raise RuntimeError(
                "Layered PDF page count does not match input: "
                f"{layered.page_count} != {source.page_count}"
            )
        text_characters = sum(len(page.get_text("text").strip()) for page in layered)
        if text_characters == 0:
            raise RuntimeError("Layered PDF has no extractable text layer")
        return {"pages": layered.page_count, "text_characters": text_characters}
    finally:
        layered.close()
        source.close()


def _write_report(path: Path, report: dict[str, object]) -> None:
    """Persist redaction-safe local validation evidence as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    executable = args.umiocr.expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Scanned PDF does not exist: {input_path}")
    if not executable.is_file():
        raise SystemExit(f"UMI OCR executable does not exist: {executable}")

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from ocr_flow.config import Config, resolve_umiocr_language
    from ocr_flow.steps.ocr import ocr_pdf

    _verify_runtime(executable, args.engine)
    config = Config()
    config.umiocr.engine = args.engine
    config.umiocr.language = resolve_umiocr_language(
        args.engine,
        document_language=args.lang,
    )
    config.umiocr.exe_path = str(executable)
    config.umiocr.url = args.url.rstrip("/")

    ocr_pdf(
        input_path,
        output_path,
        config,
        timeout=args.timeout,
        ocr_language=config.umiocr.language,
    )
    result = inspect_layered_pdf(input_path, output_path)
    manifest = {}
    try:
        from ocr_flow.runtime import load_umiocr_manifest

        manifest = load_umiocr_manifest(args.engine)
    except (OSError, ValueError, KeyError):
        pass
    if args.report:
        plugin = manifest.get("plugin", {}) if isinstance(manifest, dict) else {}
        _write_report(
            args.report.expanduser().resolve(),
            {
                "input": str(input_path),
                "output": str(output_path),
                "umiocr": str(executable),
                "engine": args.engine,
                "language": config.umiocr.language,
                "runtime": (
                    manifest.get("runtime") if isinstance(manifest, dict) else None
                ),
                "runtime_version": (
                    manifest.get("version") if isinstance(manifest, dict) else None
                ),
                "backend": (
                    manifest.get("backend") if isinstance(manifest, dict) else None
                ),
                "plugin": plugin,
                **result,
            },
        )
    print(
        "Layered PDF validation passed: "
        f"pages={result['pages']} text_characters={result['text_characters']} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
