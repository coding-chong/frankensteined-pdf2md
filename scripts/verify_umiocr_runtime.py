#!/usr/bin/env python
"""Verify a locally acquired UMI OCR runtime against its manifest."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def probe_plugin_environment(
    root: Path,
    manifest: Dict[str, Any],
    provider_mode: str = "cpu",
) -> Tuple[List[str], Dict[str, Any]]:
    """Probe a plugin environment and return failures plus observations."""
    if provider_mode not in {"cpu", "gpu"}:
        raise ValueError("provider_mode must be 'cpu' or 'gpu'")
    plugin = manifest.get("plugin")
    if not isinstance(plugin, dict):
        if manifest.get("engine") == "paddle":
            return ["Paddle runtime manifest has no plugin contract"], {}
        return [], {}

    contract_failures = []
    expected_python = plugin.get("python")
    if not isinstance(expected_python, str) or not expected_python:
        contract_failures.append("NeoEngine manifest has no plugin.python version")
    expected_dependencies = plugin.get("dependencies")
    if not isinstance(expected_dependencies, dict):
        contract_failures.append("NeoEngine manifest has no plugin.dependencies map")
        expected_dependencies = {}
    for name in ("paddlepaddle", "paddleocr", "onnxruntime"):
        if not isinstance(expected_dependencies.get(name), str) or not expected_dependencies[name]:
            contract_failures.append(
                f"NeoEngine manifest has no plugin.dependencies.{name} version"
            )
    expected_models = plugin.get("models")
    if (
        not isinstance(expected_models, list)
        or not expected_models
        or not all(isinstance(model, str) and model for model in expected_models)
    ):
        contract_failures.append("NeoEngine manifest has no valid plugin.models list")
        expected_models = []
    install_status_contract = plugin.get("install_status")
    if not isinstance(install_status_contract, dict):
        contract_failures.append("NeoEngine manifest has no plugin.install_status contract")
        install_status_contract = {}
    status_relative_path = install_status_contract.get("path")
    if not isinstance(status_relative_path, str) or not status_relative_path:
        contract_failures.append("NeoEngine manifest has no install-status path")
    provider_backends = install_status_contract.get("backends")
    if not isinstance(provider_backends, dict) or not all(
        isinstance(provider_backends.get(mode), str) and provider_backends[mode]
        for mode in ("cpu", "gpu")
    ):
        contract_failures.append("NeoEngine manifest has no valid install-status backends")
        provider_backends = {}
    for field in ("required_status", "required_models"):
        if not isinstance(install_status_contract.get(field), str) or not install_status_contract[field]:
            contract_failures.append(
                f"NeoEngine manifest has no install-status {field} value"
            )
    if contract_failures:
        return contract_failures, {}

    plugin_root = root / "UmiOCR-data" / "plugins" / "win_x64_PaddleOCR_Py"
    environment_name = ".venv_gpu" if provider_mode == "gpu" else ".venv"
    python_candidates = (plugin_root / environment_name / "Scripts" / "python.exe",)
    python_path = next(
        (candidate for candidate in python_candidates if candidate.is_file()),
        None,
    )
    if python_path is None:
        return [f"NeoEngine {provider_mode} Python environment is missing ({environment_name})"], {
            "provider_mode": provider_mode,
            "python": str(python_path) if python_path else None,
            "providers": [],
        }

    probe = (
        "import json, platform, sys, onnxruntime, paddle, paddleocr; "
        "print('__OCR_FLOW_ENV__' + json.dumps({"
        "'python': sys.executable, "
        "'python_version': platform.python_version(), "
        "'paddle': paddle.__version__, 'paddleocr': paddleocr.__version__, "
        "'onnxruntime': onnxruntime.__version__, "
        "'providers': onnxruntime.get_available_providers(), "
        "'device': onnxruntime.get_device()}))"
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
        return [f"NeoEngine dependency probe failed: {' '.join(detail)}"], {
            "provider_mode": provider_mode,
            "python": str(python_path),
            "providers": [],
        }

    marker = next(
        (
            line
            for line in result.stdout.splitlines()
            if line.startswith("__OCR_FLOW_ENV__")
        ),
        None,
    )
    if marker is None:
        return ["NeoEngine dependency probe returned no machine-readable result"], {
            "provider_mode": provider_mode,
            "python": str(python_path),
            "providers": [],
        }
    try:
        observed = json.loads(marker[len("__OCR_FLOW_ENV__") :])
    except json.JSONDecodeError as error:
        return [f"NeoEngine dependency probe returned invalid JSON: {error}"], {
            "provider_mode": provider_mode,
            "python": str(python_path),
            "providers": [],
        }

    failures = []
    observations = {
        "provider_mode": provider_mode,
        "python": observed.get("python", str(python_path)),
        "python_version": observed.get("python_version"),
        "paddle": observed.get("paddle"),
        "paddleocr": observed.get("paddleocr"),
        "onnxruntime": observed.get("onnxruntime"),
        "providers": observed.get("providers", []),
        "device": observed.get("device"),
    }
    if expected_python != observed.get("python_version"):
        failures.append(
            f"python version mismatch: expected {expected_python}, "
            f"found {observed.get('python_version')}"
        )
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
    if provider_mode == "gpu":
        if "CUDAExecutionProvider" not in providers:
            failures.append(
                f"ONNX Runtime has no CUDAExecutionProvider: {providers}"
            )
        if observed.get("device") not in {"GPU", "gpu"}:
            failures.append(
                f"ONNX Runtime device is not GPU: {observed.get('device')}"
            )
    elif "CUDAExecutionProvider" in providers:
        failures.append(
            "CPU environment unexpectedly exposes CUDAExecutionProvider: "
            f"{providers}"
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

    status_path = root / status_relative_path
    if not status_path.is_file():
        failures.append(
            "NeoEngine install status is missing: "
            f"{status_relative_path}; run the plugin's install_status.py "
            "check-env command after installing dependencies and models"
        )
        return failures, observations
    try:
        install_status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        failures.append(f"NeoEngine install status is unreadable: {error}")
        return failures, observations
    if not isinstance(install_status, dict):
        failures.append("NeoEngine install status must be a JSON object")
        return failures, observations
    status_environments = install_status.get("envs")
    if not isinstance(status_environments, dict):
        failures.append("NeoEngine install status has no envs object")
        return failures, observations
    status_entry = status_environments.get(provider_mode, {})
    if not isinstance(status_entry, dict):
        failures.append(
            f"NeoEngine install status envs.{provider_mode} must be an object"
        )
        return failures, observations
    observations["install_status"] = status_entry
    required_status = install_status_contract["required_status"]
    if status_entry.get("status") != required_status:
        failures.append(
            f"NeoEngine {provider_mode} install status is not complete: "
            f"{status_entry.get('status')}"
        )
    expected_backend = provider_backends[provider_mode]
    if status_entry.get("backend") != expected_backend:
        failures.append(
            f"NeoEngine {provider_mode} install backend mismatch: "
            f"expected {expected_backend}, found {status_entry.get('backend')}"
        )
    if status_entry.get("python_version") != expected_python:
        failures.append(
            f"NeoEngine {provider_mode} install Python mismatch: expected "
            f"{expected_python}, found {status_entry.get('python_version')}"
        )
    required_models = install_status_contract["required_models"]
    if status_entry.get("models") != required_models:
        failures.append(
            f"NeoEngine {provider_mode} install models are not ready: "
            f"{status_entry.get('models')}"
        )
    recorded_imports = status_entry.get("imports", {})
    missing_imports = [
        name
        for name in ("paddle", "paddleocr", "onnxruntime")
        if recorded_imports.get(name) is not True
    ]
    if missing_imports:
        failures.append(
            "NeoEngine install status has incomplete imports: "
            + ", ".join(missing_imports)
        )
    return failures, observations


def verify_plugin_environment(
    root: Path,
    manifest: Dict[str, Any],
    provider_mode: str = "cpu",
) -> List[str]:
    """Verify the NeoEngine venv, ONNX provider, and cached baseline models."""
    failures, _observations = probe_plugin_environment(root, manifest, provider_mode)
    return failures


def _write_report(path: Path, report: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


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
    parser.add_argument(
        "--provider-mode",
        choices=("cpu", "gpu"),
        default="cpu",
        help="Expected plugin provider set when --check-environment is enabled",
    )
    parser.add_argument("--report", type=Path, help="Write machine-readable verification JSON")
    args = parser.parse_args()

    root = args.path.resolve()
    manifest = load_manifest(args.manifest or _default_manifest_path(args.engine))
    failures = verify_runtime(root, manifest)
    observations: Dict[str, Any] = {}
    if args.check_environment and not failures:
        environment_failures, observations = probe_plugin_environment(
            root, manifest, args.provider_mode
        )
        failures.extend(environment_failures)
    if args.report:
        plugin = manifest.get("plugin") if isinstance(manifest, dict) else None
        _write_report(
            args.report.expanduser().resolve(),
            {
                "runtime": manifest.get("runtime"),
                "version": manifest.get("version"),
                "engine": manifest.get("engine"),
                "backend": manifest.get("backend"),
                "plugin": plugin,
                "failures": failures,
                "environment": observations,
            },
        )
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
    if observations:
        print("Environment: " + json.dumps(observations, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
