"""Read-only deployment diagnostics for the unified Windows support baseline."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import requests

from .runtime import resolve_babeldoc_runtime, runtime_readiness
from .self_check import find_ghostscript, find_umi_ocr, validate_umi_ocr_response

CheckStatus = Literal["PASS", "WARN", "FAIL", "UNVERIFIED"]
Verdict = Literal["READY", "NOT_READY", "UNVERIFIED"]
EvidenceValue = bool | int | float | str

SCHEMA_VERSION = 1
MIN_FREE_DISK_GIB = 16.0
SUPPORTED_PYTHON = (3, 13, 12)
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|api[_-]?token|authorization|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)[?&](token|signature|x-amz-signature)=[^&\s]+"),
)


@dataclass(frozen=True)
class DeploymentCheck:
    id: str
    status: CheckStatus
    summary: str
    evidence: Dict[str, EvidenceValue]
    remediation: Optional[str]
    required: bool


@dataclass(frozen=True)
class DeploymentReport:
    schema_version: int
    generated_at: str
    verdict: Verdict
    checks: List[DeploymentCheck]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def aggregate_verdict(checks: List[DeploymentCheck]) -> Verdict:
    if any(check.required and check.status == "FAIL" for check in checks):
        return "NOT_READY"
    if any(check.status in {"WARN", "UNVERIFIED"} for check in checks):
        return "UNVERIFIED"
    return "READY"


def _check(
    check_id: str,
    status: CheckStatus,
    summary: str,
    *,
    evidence: Optional[Dict[str, EvidenceValue]] = None,
    remediation: Optional[str] = None,
    required: bool = True,
) -> DeploymentCheck:
    return DeploymentCheck(
        id=check_id,
        status=status,
        summary=summary,
        evidence=evidence or {},
        remediation=remediation,
        required=required,
    )


def _is_windows_admin() -> Optional[bool]:
    if os.name != "nt":
        return None
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return None


def _writable_probe(path: Path) -> bool:
    """Exercise create/write/rename/delete in an existing directory."""
    if not path.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".ocr-flow-doctor-", delete=False) as handle:
            handle.write(b"deployment-probe")
            source = Path(handle.name)
        target = source.with_suffix(".renamed")
        source.replace(target)
        target.unlink()
        return True
    except OSError:
        return False


def _path_check(check_id: str, category: str, path: Path) -> DeploymentCheck:
    existing = path if path.is_dir() else path.parent
    writable = _writable_probe(existing)
    return _check(
        check_id,
        "PASS" if writable else "FAIL",
        f"{category} location supports atomic file operations" if writable else f"{category} location is not writable",
        evidence={"path_category": category, "atomic_write": writable},
        remediation=None if writable else f"Select a user-writable local {category} location.",
    )


def _nearest_existing_directory(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate if candidate.is_dir() else candidate.parent


def _safe_runtime_check(config) -> DeploymentCheck:
    try:
        runtime = resolve_babeldoc_runtime(config)
        ready, _ = runtime_readiness(runtime)
    except (OSError, RuntimeError, ValueError):
        ready = False
    return _check(
        "runtime.babeldoc_cpu",
        "PASS" if ready else "FAIL",
        "Managed BabelDOC CPU runtime is ready" if ready else "Managed BabelDOC CPU runtime is not ready",
        evidence={"profile": "cpu-safe", "ready": ready},
        remediation=None if ready else "Run ocr-flow runtime setup --profile cpu-safe.",
    )


def _ghostscript_check(config) -> DeploymentCheck:
    executable = find_ghostscript(config)
    if not executable:
        return _check(
            "runtime.ghostscript",
            "FAIL",
            "Ghostscript executable was not found",
            evidence={"discovered": False, "portable_supported": True},
            remediation="Configure a compatible portable Ghostscript executable or install it system-wide.",
        )
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        version = "unknown"
    status: CheckStatus = "WARN" if version != "unknown" else "FAIL"
    return _check(
        "runtime.ghostscript",
        status,
        "Ghostscript runs; one-page PDF compatibility remains to be exercised" if status == "WARN" else "Ghostscript was found but could not run",
        evidence={"discovered": True, "version": version, "compatibility_smoke": False},
        remediation="Run the documented one-page compression compatibility smoke." if status == "WARN" else "Configure a runnable Ghostscript executable.",
    )


def _rapid_check(config) -> DeploymentCheck:
    engine = getattr(getattr(config, "umiocr", None), "engine", "paddle")
    executable = find_umi_ocr(config)
    ready = engine == "rapid" and bool(executable)
    return _check(
        "runtime.umiocr_rapid",
        "PASS" if ready else "FAIL",
        "Rapid CPU OCR executable is selected" if ready else "Rapid CPU OCR executable is not selected and available",
        evidence={"engine": engine, "executable_discovered": bool(executable)},
        remediation=None if ready else "Configure umiocr.engine=rapid and a verified portable Rapid Umi-OCR executable.",
    )


def _umi_service_check(config) -> DeploymentCheck:
    url = getattr(getattr(config, "umiocr", None), "url", "http://127.0.0.1:1224")
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(f"{url}/api/doc/get_options", timeout=2)
        valid, _ = validate_umi_ocr_response(response, config) if response.status_code == 200 else (False, "")
    except requests.RequestException:
        return _check(
            "process.umiocr_port",
            "WARN",
            "No UMI OCR service is listening; deployment doctor did not start it",
            evidence={"listener": False, "auto_started": False},
            remediation="Start the configured Rapid runtime, then rerun deployment doctor.",
        )
    return _check(
        "process.umiocr_port",
        "PASS" if valid else "FAIL",
        "Local UMI OCR listener matches the selected engine" if valid else "Port 1224 is occupied by an incompatible or unhealthy service",
        evidence={"listener": True, "engine_options_match": valid, "auto_started": False},
        remediation=None if valid else "Stop the foreign/stale listener or configure the matching Rapid service.",
    )


def _credential_checks(config) -> List[DeploymentCheck]:
    mineru = getattr(getattr(config, "mineru", None), "api_token", "")
    translation = getattr(getattr(config, "babeldoc", None), "openai_api_key", "")
    mineru_valid = bool(mineru and mineru != "your-mineru-api-token-here")
    return [
        _check("credential.mineru", "PASS" if mineru_valid else "FAIL", "MinerU credential is configured" if mineru_valid else "MinerU credential is not configured", evidence={"configured": mineru_valid}, remediation=None if mineru_valid else "Configure the MinerU credential with ocr-flow config."),
        _check("credential.translation", "PASS" if translation else "FAIL", "Translation credential is configured" if translation else "Translation credential is not configured", evidence={"configured": bool(translation)}, remediation=None if translation else "Configure the translation credential with ocr-flow config."),
    ]


def _uv_check() -> DeploymentCheck:
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        version = "unknown"
    return _check(
        "tool.uv",
        "PASS" if version != "unknown" else "FAIL",
        "uv is available" if version != "unknown" else "uv is not available",
        evidence={"version": version},
        remediation=None if version != "unknown" else "Install uv for the current standard user and reopen the terminal.",
    )


def _path_policy_check(checkout: Path) -> DeploymentCheck:
    raw = str(checkout)
    unc = raw.startswith("\\\\")
    synchronized = any(part.lower() in {"onedrive", "dropbox"} for part in checkout.parts)
    status: CheckStatus = "UNVERIFIED" if unc or synchronized else "PASS"
    return _check(
        "filesystem.path_policy",
        status,
        "Checkout uses a local, non-synchronized path" if status == "PASS" else "Network or synchronized checkout behavior is not verified",
        evidence={"path_kind": "unc" if unc else "local", "synchronized_hint": synchronized, "path_characters": len(raw)},
        remediation=None if status == "PASS" else "Validate the complete matrix in this location or move the checkout to a user-writable local path.",
    )


def build_deployment_report(config, *, checkout: Optional[Path] = None) -> DeploymentReport:
    """Assess deployment prerequisites without starting runtimes or calling paid APIs."""
    checkout = (checkout or Path.cwd()).resolve()
    machine = platform.machine().lower()
    windows = os.name == "nt"
    x64 = machine in {"amd64", "x86_64"}
    checks: List[DeploymentCheck] = [
        _check("platform.windows", "PASS" if windows else "FAIL", "Windows host detected" if windows else "This support baseline requires Windows", evidence={"windows": windows, "release": platform.release()}),
        _check("platform.architecture", "PASS" if x64 else "FAIL", "x64 architecture detected" if x64 else "x64 architecture was not detected", evidence={"architecture": machine}),
        _check("platform.python", "PASS" if tuple(map(int, platform.python_version_tuple())) == SUPPORTED_PYTHON else "FAIL", "Locked CPython 3.13.12 is active" if platform.python_version() == "3.13.12" else "The active Python does not match locked CPython 3.13.12", evidence={"version": platform.python_version()}, remediation=None if platform.python_version() == "3.13.12" else "Run uv python install 3.13.12 and uv sync --locked --extra windows."),
        _check("platform.servicing", "UNVERIFIED", "Microsoft servicing or ESU entitlement cannot be proven locally", evidence={"release": platform.release(), "servicing_verified": False}, remediation="Use an x64 Windows release currently in Microsoft servicing and record its edition/build evidence."),
        _uv_check(),
    ]
    admin = _is_windows_admin()
    checks.append(_check("permissions.standard_user", "PASS" if admin is False else "UNVERIFIED", "Process is running without elevation" if admin is False else "Standard-user operation is not proven by this elevated or indeterminate process", evidence={"elevation_detected": admin is True}, remediation=None if admin is False else "Rerun the complete gate from a standard Windows user session."))
    config_path = config.get_config_path()
    output_path = Path(config.output_dir).expanduser()
    checks.extend([
        _path_check("filesystem.checkout", "<checkout>", checkout),
        _path_check("filesystem.user_config", "<user-config>", config_path.parent),
        _path_check("filesystem.temp", "<temp>", Path(tempfile.gettempdir())),
        _path_check("filesystem.output", "<output>", output_path),
        _path_policy_check(checkout),
    ])
    free_gib = round(shutil.disk_usage(_nearest_existing_directory(output_path)).free / 1024**3, 2)
    checks.append(_check("resource.disk", "PASS" if free_gib >= MIN_FREE_DISK_GIB else "FAIL", "Free disk meets the measured setup and retained-matrix budget" if free_gib >= MIN_FREE_DISK_GIB else "Free disk is below the deployment budget", evidence={"free_gib": free_gib, "required_gib": MIN_FREE_DISK_GIB}, remediation=None if free_gib >= MIN_FREE_DISK_GIB else f"Free at least {MIN_FREE_DISK_GIB:g} GiB on the output/runtime volume."))
    checks.append(_check("resource.memory", "UNVERIFIED", "A minimum RAM contract cannot be derived from the single measured host", evidence={"threshold_established": False}, remediation="Measure peak working set during the complete four-case matrix on low-memory hardware."))
    checks.append(_check("resource.cpu", "PASS" if (os.cpu_count() or 0) >= 2 else "FAIL", "Logical CPU capacity detected", evidence={"logical_cpus": os.cpu_count() or 0}, remediation=None if (os.cpu_count() or 0) >= 2 else "Use a machine with at least two logical CPUs."))
    checks.extend([_ghostscript_check(config), _rapid_check(config), _safe_runtime_check(config), _umi_service_check(config)])
    proxy_names = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
    proxy_configured = any(os.environ.get(name) or os.environ.get(name.lower()) for name in proxy_names)
    checks.append(_check("network.proxy_tls", "UNVERIFIED", "Proxy/TLS policy requires certificate-validating enterprise-network evidence", evidence={"environment_proxy_configured": proxy_configured, "certificate_validation_required": True, "restricted_direct_cdn_fallback": True}, remediation="Validate direct, system proxy, authenticated proxy, enterprise-CA, and restricted direct-CDN fallback modes without disabling TLS verification."))
    checks.extend(_credential_checks(config))
    checks.extend([
        _check("recovery.state", "PASS", "Conversion state is locally retained for interruption recovery", evidence={"state_file": ".state.json", "local_only": True}, required=True),
        _check("security.edr", "UNVERIFIED", "Real antivirus/EDR executable policy has not been exercised", evidence={"real_policy_exercised": False}, remediation="Run the full gate under the target security policy without broad exclusions."),
        _check("hardware.no_gpu", "UNVERIFIED", "A physically GPU-free host has not been exercised", evidence={"physical_no_gpu_exercised": False}, remediation="Run Rapid and cpu-safe local smoke plus the complete matrix on physically GPU-free hardware."),
        _check("validation.full_matrix", "UNVERIFIED", "This machine has not yet completed the post-change four-case paid matrix", evidence={"required_cases": 4, "required_mineru_parts": 24, "required_translations": 2}, remediation="After explicit quota approval, run and visually review the complete CPU/Rapid matrix."),
    ])
    return DeploymentReport(SCHEMA_VERSION, datetime.now(timezone.utc).isoformat(), aggregate_verdict(checks), checks)


def _string_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _string_values(item)


def serialize_report(report: DeploymentReport, config) -> str:
    """Serialize and reject credential or raw-profile-path disclosure."""
    data = report.to_dict()
    forbidden = [
        getattr(getattr(config, "mineru", None), "api_token", ""),
        getattr(getattr(config, "babeldoc", None), "openai_api_key", ""),
        str(Path.home()),
    ]
    strings = list(_string_values(data))
    if any(value and any(value in item for item in strings) for value in forbidden):
        raise ValueError("Deployment report failed the credential/path disclosure scan")
    if any(pattern.search(item) for item in strings for pattern in SECRET_PATTERNS):
        raise ValueError("Deployment report failed the credential/path disclosure scan")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return payload + "\n"


def write_report(path: Path, report: DeploymentReport, config) -> None:
    payload = serialize_report(report, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
