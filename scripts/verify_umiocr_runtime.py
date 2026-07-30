#!/usr/bin/env python
"""Verify a locally acquired UMI OCR runtime against its manifest."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _default_manifest_path(engine: str = "paddle") -> Path:
    """Resolve the package-owned manifest when this source script is run directly."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from ocr_flow.runtime import umiocr_manifest_path

    return umiocr_manifest_path(engine)


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


def verify_plugin_environment(root: Path, manifest: Dict[str, Any]) -> List[str]:
    """Verify the NeoEngine venv, ONNX provider, and cached baseline models."""
    plugin = manifest.get("plugin")
    if not isinstance(plugin, dict):
        return []

    plugin_root = root / "UmiOCR-data" / "plugins" / "win_x64_PaddleOCR_Py"
    python_candidates = (
        plugin_root / ".venv" / "Scripts" / "python.exe",
        plugin_root / ".venv_gpu" / "Scripts" / "python.exe",
    )
    python_path = next(
        (candidate for candidate in python_candidates if candidate.is_file()),
        None,
    )
    if python_path is None:
        return ["NeoEngine Python environment is missing (.venv or .venv_gpu)"]

    probe = (
        "import json, onnxruntime, paddle, paddleocr; "
        "print('__OCR_FLOW_ENV__' + json.dumps({"
        "'paddle': paddle.__version__, 'paddleocr': paddleocr.__version__, "
        "'onnxruntime': onnxruntime.__version__, "
        "'providers': onnxruntime.get_available_providers()}))"
    )
    environment = os.environ.copy()
    # A caller such as ``uv run`` may set PYTHONHOME for its own interpreter.
    # Passing that path to a different plugin Python causes a SRE/stdlib
    # mismatch before any dependency import can run.
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment["PADDLE_PDX_CACHE_HOME"] = str(plugin_root / "paddlex")
    result = subprocess.run(
        [str(python_path), "-c", probe],
        cwd=plugin_root,
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        return [f"NeoEngine dependency probe failed: {' '.join(detail)}"]

    marker = next(
        (
            line
            for line in result.stdout.splitlines()
            if line.startswith("__OCR_FLOW_ENV__")
        ),
        None,
    )
    if marker is None:
        return ["NeoEngine dependency probe returned no machine-readable result"]
    try:
        observed = json.loads(marker[len("__OCR_FLOW_ENV__") :])
    except json.JSONDecodeError as error:
        return [f"NeoEngine dependency probe returned invalid JSON: {error}"]

    failures = []
    expected_dependencies = plugin.get("dependencies", {})
    for name in ("paddlepaddle", "paddleocr", "onnxruntime"):
        package_name = {
            "paddlepaddle": "paddle",
            "paddleocr": "paddleocr",
            "onnxruntime": "onnxruntime",
        }[name]
        if expected_dependencies.get(name) != observed.get(package_name):
            failures.append(
                f"{name} version mismatch: expected {expected_dependencies.get(name)}, "
                f"found {observed.get(package_name)}"
            )
    providers = observed.get("providers", [])
    if "CPUExecutionProvider" not in providers:
        failures.append(f"ONNX Runtime has no CPUExecutionProvider: {providers}")

    expected_models = plugin.get(
        "models", ["PP-OCRv6_medium_det_onnx", "PP-OCRv6_medium_rec_onnx"]
    )
    for model in expected_models:
        model_file = (
            plugin_root
            / "paddlex"
            / "official_models"
            / model
            / "inference.onnx"
        )
        if not model_file.is_file() or model_file.stat().st_size == 0:
            failures.append(f"Missing cached NeoEngine model: {model}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, type=Path, help="UMI OCR root")
    parser.add_argument(
        "--engine",
        choices=("paddle", "rapid"),
        default="paddle",
        help="Select the checked-in engine manifest unless --manifest is supplied",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--check-environment",
        action="store_true",
        help="Also verify the NeoEngine venv, dependencies, provider, and models",
    )
    args = parser.parse_args()

    root = args.path.resolve()
    manifest = load_manifest(args.manifest or _default_manifest_path(args.engine))
    failures = verify_runtime(root, manifest)
    if args.check_environment and not failures:
        failures.extend(verify_plugin_environment(root, manifest))
    if failures:
        print("UMI OCR runtime verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Verified {manifest['runtime']} {manifest['version']}")
    plugin = manifest.get("plugin")
    if isinstance(plugin, dict):
        print(
            "NeoEngine: "
            f"{plugin.get('name')} {plugin.get('version')} "
            f"commit={plugin.get('commit')} backend={manifest.get('backend')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
