"""Resolve verified BabelDOC Runtime Profiles for Translation Enrichment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .config import normalize_umiocr_engine


PACKAGE_ROOT = Path(__file__).resolve().parent
PROFILE_ROOT = PACKAGE_ROOT / "runtime_profiles"


def _resolve_project_root() -> Path:
    """Keep source checkouts local while installed wheels use their launch root."""
    source_root = PACKAGE_ROOT.parent
    if (source_root / "pyproject.toml").is_file():
        return source_root
    return Path.cwd()


PROJECT_ROOT = _resolve_project_root()
RUNTIME_ROOT = PROJECT_ROOT / ".ocr-flow-runtime"
MANAGED_BABELDOC_PATH = RUNTIME_ROOT / "BabelDOC"
MANAGED_RUNTIME_STATE_PATH = RUNTIME_ROOT / "babeldoc-runtime-state.json"
DEFAULT_BABELDOC_MANIFEST = PROFILE_ROOT / "babeldoc-v0.6.3.json"
DEFAULT_UMIOCR_MANIFEST = PROFILE_ROOT / "umiocr-paddle-v2.1.5.json"
UMIOCR_MANIFESTS = {
    "paddle": DEFAULT_UMIOCR_MANIFEST,
    "rapid": PROFILE_ROOT / "umiocr-rapid-v2.1.5.json",
}


@dataclass(frozen=True)
class BabelDocRuntime:
    """The verified runtime selected for one Translation Enrichment invocation."""

    checkout: Path
    managed: bool


def load_babeldoc_manifest(
    path: Path = DEFAULT_BABELDOC_MANIFEST,
) -> Dict[str, Any]:
    """Load the supported BabelDOC Runtime Profile manifest."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def umiocr_manifest_path(engine: str = "paddle") -> Path:
    """Return the tracked UMI OCR manifest for one supported engine."""
    return UMIOCR_MANIFESTS[normalize_umiocr_engine(engine)]


def load_umiocr_manifest(engine: str = "paddle") -> Dict[str, Any]:
    """Load the tracked UMI OCR manifest for one supported engine."""
    with umiocr_manifest_path(engine).open(encoding="utf-8") as handle:
        return json.load(handle)


def checkout_python(checkout: Path) -> Path:
    """Return the Python interpreter created inside a BabelDOC checkout."""
    candidates = (
        checkout / ".venv" / "Scripts" / "python.exe",
        checkout / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"BabelDOC environment was not created in {checkout / '.venv'}")


def resolve_babeldoc_runtime(config: Any) -> BabelDocRuntime:
    """Select a configured external runtime or the project-managed default."""
    configured_path = getattr(getattr(config, "babeldoc", None), "path", None)
    if configured_path:
        return BabelDocRuntime(Path(configured_path).expanduser().resolve(), False)
    return BabelDocRuntime(MANAGED_BABELDOC_PATH, True)


def _same_checkout_path(left: Path, right: Path) -> bool:
    """Compare runtime paths without making Windows path casing significant."""
    left_value = str(left.expanduser().resolve())
    right_value = str(right.expanduser().resolve())
    if os.name == "nt":
        return left_value.casefold() == right_value.casefold()
    return left_value == right_value


def _setup_command(checkout: Path, managed: bool) -> str:
    """Render the setup command that can repair one runtime selection."""
    if managed:
        return "`ocr-flow runtime setup`"
    return f"`ocr-flow runtime setup --path {checkout}`"


def _runtime_label(managed: bool) -> str:
    """Return a stable label for managed and explicit external runtimes."""
    return "Managed BabelDOC Runtime" if managed else "Configured BabelDOC Runtime"


def _runtime_state_error(
    runtime: BabelDocRuntime, expected_profile: Optional[str] = None
) -> Optional[str]:
    """Return a user-facing reason why a selected runtime cannot be used."""
    checkout = runtime.checkout
    managed = runtime.managed
    label = _runtime_label(managed)
    if not checkout.is_dir():
        return f"{label} checkout does not exist: {checkout}"
    if not MANAGED_RUNTIME_STATE_PATH.is_file():
        return f"{label} has not completed profile setup"

    try:
        with MANAGED_RUNTIME_STATE_PATH.open(encoding="utf-8") as handle:
            state = json.load(handle)
        manifest = load_babeldoc_manifest()
    except (OSError, ValueError, KeyError) as error:
        return f"{label} state is unreadable: {error}"

    if not isinstance(state, dict):
        return f"{label} state is unreadable"

    expected = {
        "runtime": manifest["runtime"],
        "version": manifest["version"],
        "revision": manifest["revision"],
    }
    for key, value in expected.items():
        if state.get(key) != value:
            return f"{label} state has an unexpected {key}"

    recorded_managed = state.get("managed", True)
    if managed:
        if recorded_managed is not True:
            return f"{label} state selects a different checkout"
        recorded_checkout = state.get("checkout")
        if recorded_checkout and not _same_checkout_path(
            Path(recorded_checkout), checkout
        ):
            return f"{label} state selects a different checkout"
    else:
        if recorded_managed is not False:
            return f"{label} was not set up as an external checkout"
        recorded_checkout = state.get("checkout")
        if not isinstance(recorded_checkout, str) or not _same_checkout_path(
            Path(recorded_checkout), checkout
        ):
            return f"{label} state does not match {checkout}"

    profile = state.get("profile")
    if not isinstance(profile, str) or profile not in manifest["profiles"]:
        return f"{label} state has an unexpected profile"
    if expected_profile and profile != expected_profile:
        return (
            f"{label} was set up with profile {profile}, not the requested "
            f"{expected_profile} profile"
        )

    try:
        checkout_python(checkout)
    except RuntimeError as error:
        return str(error)

    # Import lazily: babeldoc_runtime imports the constants above, while this
    # module owns the runtime-selection boundary.
    from .babeldoc_runtime import installed_checkout_readiness

    verified, message = installed_checkout_readiness(checkout, manifest, profile)
    if not verified:
        return f"{label} verification failed: {message}"
    return None


def runtime_readiness(
    runtime: BabelDocRuntime, expected_profile: Optional[str] = None
) -> Tuple[bool, str]:
    """Report whether a selected runtime matches its recorded profile state."""
    error = _runtime_state_error(runtime, expected_profile)
    if error:
        return False, f"{error}. Run {_setup_command(runtime.checkout, runtime.managed)}."
    return True, f"{_runtime_label(runtime.managed)} ready at {runtime.checkout}"


def managed_runtime_readiness(
    expected_profile: Optional[str] = None,
) -> Tuple[bool, str]:
    """Report whether Translation Enrichment may use the managed default."""
    return runtime_readiness(
        BabelDocRuntime(MANAGED_BABELDOC_PATH, True), expected_profile
    )


def external_runtime_readiness(
    checkout: Path, expected_profile: Optional[str] = None
) -> Tuple[bool, str]:
    """Report whether an explicitly configured external checkout is verified."""
    return runtime_readiness(
        BabelDocRuntime(checkout.expanduser().resolve(), False), expected_profile
    )


def recorded_runtime_readiness() -> Tuple[bool, str]:
    """Report readiness for the runtime recorded by the last successful setup."""
    if not MANAGED_RUNTIME_STATE_PATH.is_file():
        return managed_runtime_readiness()

    try:
        with MANAGED_RUNTIME_STATE_PATH.open(encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError) as error:
        return False, f"BabelDOC Runtime state is unreadable: {error}"

    if isinstance(state, dict) and state.get("managed") is False:
        checkout = state.get("checkout")
        if isinstance(checkout, str):
            return external_runtime_readiness(Path(checkout))
    return managed_runtime_readiness()


def require_babeldoc_runtime(config: Any) -> BabelDocRuntime:
    """Resolve a runtime and reject a missing or unverified selection."""
    runtime = resolve_babeldoc_runtime(config)
    ready, message = runtime_readiness(runtime)
    if not ready:
        raise RuntimeError(message)
    return runtime
