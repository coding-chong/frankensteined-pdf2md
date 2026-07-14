#!/usr/bin/env python
"""Run the strict API-consuming complex PDF matrix through pytest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_TEST = PROJECT_ROOT / "tests" / "live_complex_pdf_matrix.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Credential config; it is read but never modified",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=["cpu-safe", "windows-directml"],
        help="Managed BabelDOC profile to validate; repeatable",
    )
    parser.add_argument(
        "--all-profiles",
        action="store_true",
        help="Run cpu-safe and Windows DirectML on a Windows host",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Root for retained reports, PDFs, Markdown, and visual review images",
    )
    parser.add_argument(
        "--ghostscript",
        type=Path,
        help="Override Ghostscript executable without changing the credential config",
    )
    parser.add_argument(
        "--umiocr",
        type=Path,
        help="Override UMI OCR executable without changing the credential config",
    )
    return parser.parse_args()


def _profiles(args: argparse.Namespace) -> list[str]:
    if args.all_profiles and args.profile:
        raise SystemExit("Use either --profile or --all-profiles, not both")
    if args.all_profiles:
        if os.name != "nt":
            raise SystemExit("--all-profiles requires Windows for windows-directml")
        return ["cpu-safe", "windows-directml"]
    return args.profile or ["cpu-safe"]


def main() -> int:
    args = parse_args()
    config = args.config.expanduser().resolve()
    if not config.is_file():
        raise SystemExit(f"Credential config does not exist: {config}")
    if args.ghostscript and not args.ghostscript.expanduser().is_file():
        raise SystemExit(f"Ghostscript executable does not exist: {args.ghostscript}")
    if args.umiocr and not args.umiocr.expanduser().is_file():
        raise SystemExit(f"UMI OCR executable does not exist: {args.umiocr}")

    output_root = (
        args.output.expanduser().resolve()
        if args.output
        else PROJECT_ROOT
        / "output"
        / "live_complex_pdf_matrix"
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    output_root.mkdir(parents=True, exist_ok=False)
    summary: dict[str, object] = {"profiles": {}, "status": "failed"}
    for profile in _profiles(args):
        profile_output = output_root / profile
        environment = os.environ.copy()
        environment["OCR_FLOW_LIVE_CONFIG"] = str(config)
        environment["OCR_FLOW_LIVE_OUTPUT"] = str(profile_output)
        environment["OCR_FLOW_LIVE_PROFILE"] = profile
        if args.ghostscript:
            environment["OCR_FLOW_LIVE_GHOSTSCRIPT"] = str(
                args.ghostscript.expanduser().resolve()
            )
        if args.umiocr:
            environment["OCR_FLOW_LIVE_UMIOCR_EXE"] = str(
                args.umiocr.expanduser().resolve()
            )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(LIVE_TEST),
                "-q",
                "-s",
                "-m",
                "live",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
        )
        summary["profiles"][profile] = {
            "exit_code": result.returncode,
            "output": str(profile_output),
        }
        (output_root / "runner-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if result.returncode:
            return result.returncode

    summary["status"] = "passed"
    (output_root / "runner-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Live matrix passed. Retained artifacts: {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
