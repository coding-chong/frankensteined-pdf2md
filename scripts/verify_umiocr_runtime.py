#!/usr/bin/env python
"""Verify a locally acquired UMI OCR runtime against its manifest."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _default_manifest_path() -> Path:
    """Resolve the package-owned manifest when this source script is run directly."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from ocr_flow.runtime import DEFAULT_UMIOCR_MANIFEST

    return DEFAULT_UMIOCR_MANIFEST


DEFAULT_MANIFEST = _default_manifest_path()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> Dict[str, Any]:
    """Load the checked-in UMI OCR runtime manifest."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    """Return the uppercase SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_runtime(root: Path, manifest: Dict[str, Any]) -> List[str]:
    """Return human-readable verification failures for a runtime root."""
    failures = []
    for expected in manifest["files"]:
        target = root / expected["path"]
        if not target.is_file():
            failures.append(f"Missing {expected['path']}")
            continue
        if target.stat().st_size != expected["bytes"]:
            failures.append(f"Size mismatch for {expected['path']}")
            continue
        if sha256(target) != expected["sha256"]:
            failures.append(f"SHA-256 mismatch for {expected['path']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, type=Path, help="UMI OCR root")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    failures = verify_runtime(args.path.resolve(), manifest)
    if failures:
        print("UMI OCR runtime verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Verified {manifest['runtime']} {manifest['version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
