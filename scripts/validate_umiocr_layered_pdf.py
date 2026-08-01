#!/usr/bin/env python
"""Validate a local UMI OCR engine by producing a readable layered PDF."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

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
    parser.add_argument(
        "--expected-text",
        type=Path,
        help="JSON fixture manifest or newline-delimited anchor text",
    )
    parser.add_argument(
        "--min-chinese-characters",
        type=int,
        default=0,
        help="Require at least this many CJK characters in extracted text",
    )
    parser.add_argument(
        "--provider-mode",
        choices=("cpu", "gpu"),
        help=(
            "Paddle provider contract; defaults to cpu for Paddle and is not "
            "valid for Rapid"
        ),
    )
    return parser.parse_args()


def resolve_provider_mode(engine: str, requested: Optional[str]) -> Optional[str]:
    """Apply the Paddle CPU baseline without leaking it into Rapid."""
    if engine == "rapid":
        if requested is not None:
            raise ValueError("--provider-mode is only valid with --engine paddle")
        return None
    return requested or "cpu"


def _verify_runtime(
    executable: Path,
    engine: str,
    provider_mode: Optional[str] = None,
) -> dict[str, object]:
    command = [
        sys.executable,
        str(VERIFY_SCRIPT),
        "--path",
        str(executable.parent),
        "--engine",
        engine,
    ]
    if provider_mode:
        command.extend(["--check-environment", "--provider-mode", provider_mode])
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"UMI OCR runtime verification failed: {detail}")
    print(result.stdout.strip())
    environment_line = next(
        (
            line
            for line in result.stdout.splitlines()
            if line.startswith("Environment: ")
        ),
        None,
    )
    if environment_line:
        try:
            return json.loads(environment_line[len("Environment: ") :])
        except json.JSONDecodeError as error:
            raise RuntimeError(f"UMI OCR environment report is invalid: {error}") from error
    return {}


def _normalize_anchor(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _is_cjk(value: str) -> bool:
    return any(
        start <= ord(value) <= end
        for start, end in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
        )
    )


def load_expected_anchors(path: Optional[Path]) -> List[str]:
    """Load anchor strings from a fixture manifest or plain-text file."""
    if path is None:
        return []
    if not path.is_file():
        raise RuntimeError(f"Expected-text file does not exist: {path}")
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Expected-text manifest is unreadable: {error}") from error
        anchors = payload.get("anchors") if isinstance(payload, dict) else None
    else:
        anchors = path.read_text(encoding="utf-8").splitlines()
    if not isinstance(anchors, list) or not all(isinstance(item, str) for item in anchors):
        raise RuntimeError("Expected-text manifest must contain an anchors list")
    anchors = [item.strip() for item in anchors if item.strip()]
    if not anchors:
        raise RuntimeError("Expected-text manifest contains no anchors")
    return anchors


def inspect_layered_pdf(
    input_path: Path,
    output_path: Path,
    *,
    expected_anchors: Optional[Iterable[str]] = None,
    min_chinese_characters: int = 0,
) -> dict[str, object]:
    """Reject missing, page-mismatched, textless, or low-quality OCR output."""
    if min_chinese_characters < 0:
        raise ValueError("min_chinese_characters must be non-negative")
    anchors = list(expected_anchors) if expected_anchors is not None else None
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
        extracted_text = "\n".join(page.get_text("text").strip() for page in layered)
        text_characters = len(extracted_text.strip())
        if text_characters == 0:
            raise RuntimeError("Layered PDF has no extractable text layer")
        result: dict[str, object] = {
            "pages": layered.page_count,
            "text_characters": text_characters,
        }
        if min_chinese_characters or anchors is not None:
            chinese_characters = sum(1 for value in extracted_text if _is_cjk(value))
            result["chinese_characters"] = chinese_characters
            if chinese_characters < min_chinese_characters:
                raise RuntimeError(
                    "Layered PDF has too few Chinese characters: "
                    f"{chinese_characters} < {min_chinese_characters}"
                )
        if anchors is not None:
            normalized_text = _normalize_anchor(extracted_text)
            missing = [
                anchor
                for anchor in anchors
                if _normalize_anchor(anchor) not in normalized_text
            ]
            result["expected_anchors"] = anchors
            result["missing_anchors"] = missing
            if missing:
                raise RuntimeError(
                    "Layered PDF is missing expected OCR anchors: "
                    + ", ".join(missing)
                )
        return result
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

    try:
        provider_mode = resolve_provider_mode(args.engine, args.provider_mode)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    environment = _verify_runtime(executable, args.engine, provider_mode)
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
    expected_anchors = load_expected_anchors(args.expected_text)
    result = inspect_layered_pdf(
        input_path,
        output_path,
        expected_anchors=expected_anchors if args.expected_text else None,
        min_chinese_characters=args.min_chinese_characters,
    )
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
                "provider_mode": provider_mode,
                "environment": environment,
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
