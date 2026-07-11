"""Install, verify, and inspect the supported BabelDOC Runtime Profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .runtime import (
    DEFAULT_BABELDOC_MANIFEST,
    MANAGED_BABELDOC_PATH,
    MANAGED_RUNTIME_STATE_PATH,
    PROFILE_ROOT,
    RUNTIME_ROOT,
    checkout_python,
    load_babeldoc_manifest,
    recorded_runtime_readiness,
)


DEFAULT_MANIFEST = DEFAULT_BABELDOC_MANIFEST
SMOKE_SCRIPT = """
from pathlib import Path
import re
import sys

import numpy as np
import pymupdf
from babeldoc.docvision.doclayout import OnnxModel
from babeldoc.docvision.table_detection.rapidocr import RapidOCRModel

pdf_path = Path(sys.argv[1])
profile = sys.argv[2]
document = pymupdf.open(pdf_path)
pixmap = document[0].get_pixmap(dpi=96, colorspace=pymupdf.csRGB)
image = np.frombuffer(pixmap.samples, np.uint8).reshape(
    pixmap.height, pixmap.width, 3
)[:, :, ::-1]

layout = OnnxModel.from_pretrained()
layout_result = layout.predict(image)
table = RapidOCRModel()
table_result = table.predict(image)
providers = layout.model.get_providers()
table_boxes = getattr(table_result, "boxes", [])

print(f"layout_providers={providers}")
print(f"layout_result_count={len(layout_result)}")
print(f"table_result_boxes={len(table_boxes)}")
print("table_policy=retired")

if profile == "windows-directml":
    if "DmlExecutionProvider" not in providers:
        raise SystemExit("Windows DirectML profile did not select DirectML layout inference")
elif profile == "cpu-safe":
    if any(re.match(r"dml|cuda", provider, re.IGNORECASE) for provider in providers):
        raise SystemExit("CPU-safe profile selected a non-CPU provider")

if table_boxes:
    raise SystemExit("BabelDOC 0.6 retired table detection but returned table boxes")
"""


def load_manifest(path: Path = DEFAULT_MANIFEST) -> Dict[str, Any]:
    """Load the checked-in BabelDOC Runtime Profile manifest."""
    return load_babeldoc_manifest(path)


def _runtime_environment() -> Dict[str, str]:
    """Keep uv commands scoped to the selected BabelDOC checkout."""
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    return environment


def run_git(checkout: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run a Git inspection command without modifying the checkout."""
    return subprocess.run(
        ["git", *arguments],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )


def profile_patch_path(manifest: Dict[str, Any], profile: str) -> Optional[Path]:
    """Resolve the optional patch path for a named profile."""
    patch = manifest["profiles"][profile]["patch"]
    return PROFILE_ROOT / patch if patch else None


def patch_state(checkout: Path, patch: Path) -> str:
    """Classify a profile patch as applicable, applied, or incompatible."""
    applicable = run_git(checkout, "apply", "--check", str(patch))
    if applicable.returncode == 0:
        return "applicable"
    applied = run_git(checkout, "apply", "--check", "--reverse", str(patch))
    if applied.returncode == 0:
        return "applied"
    return "incompatible"


def provider_file_state(checkout: Path, manifest: Dict[str, Any]) -> str:
    """Classify provider files by their exact manifest blob identities."""
    states = set()
    for relative_path, expected in manifest["provider_files"].items():
        result = run_git(checkout, "hash-object", relative_path)
        if result.returncode != 0:
            return "incompatible"
        actual_blob = result.stdout.strip()
        if actual_blob == expected["upstream_blob"]:
            states.add("upstream")
        elif actual_blob == expected["windows_directml_blob"]:
            states.add("directml")
        else:
            return "incompatible"
    return states.pop() if len(states) == 1 else "incompatible"


def provider_files_are_clean(checkout: Path, manifest: Dict[str, Any]) -> bool:
    """Check both worktree and index before applying a profile patch."""
    paths = list(manifest["provider_files"])
    worktree_clean = run_git(checkout, "diff", "--quiet", "--", *paths)
    index_clean = run_git(checkout, "diff", "--cached", "--quiet", "--", *paths)
    return worktree_clean.returncode == 0 and index_clean.returncode == 0


def verify_checkout(
    checkout: Path, manifest: Dict[str, Any], profile: str
) -> Tuple[bool, str]:
    """Verify revision and source-patch state without changing files."""
    if not checkout.is_dir():
        return False, f"BabelDOC checkout does not exist: {checkout}"
    if profile not in manifest["profiles"]:
        return False, f"Unsupported profile: {profile}"

    revision = run_git(checkout, "rev-parse", "HEAD")
    if revision.returncode != 0:
        return False, f"Not a readable Git checkout: {checkout}"
    actual_revision = revision.stdout.strip()
    expected_revision = manifest["revision"]
    if actual_revision != expected_revision:
        return (
            False,
            f"Expected BabelDOC {manifest['version']} at {expected_revision}, "
            f"found {actual_revision}",
        )

    state = provider_file_state(checkout, manifest)
    if profile == "cpu-safe":
        if state != "upstream":
            return (
                False,
                f"cpu-safe requires unmodified upstream provider files; found {state}",
            )
        return True, "CPU-safe upstream source verified"

    patch = profile_patch_path(manifest, profile)
    assert patch is not None
    if state == "incompatible" or patch_state(checkout, patch) == "incompatible":
        return False, "Windows DirectML layout patch does not match this checkout"
    if state == "directml":
        return True, "Windows DirectML layout patch is applied"
    if state != "upstream":
        return False, "Windows DirectML provider files have mixed states"
    return True, "Windows DirectML layout patch is applicable"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def ensure_profile_lock(checkout: Path, manifest: Dict[str, Any]) -> None:
    """Install the profile-owned lock without replacing a conflicting file."""
    lock = manifest["lock"]
    source = PROFILE_ROOT / lock["path"]
    expected_hash = lock["sha256"]
    if not source.is_file() or _sha256(source) != expected_hash:
        raise RuntimeError(f"Checked-in profile lock is missing or corrupt: {source}")

    destination = checkout / "uv.lock"
    if destination.exists():
        if _sha256(destination) != expected_hash:
            raise RuntimeError(
                f"Refusing to replace a different lock file in {checkout}. "
                "Use a clean checkout for this profile."
            )
        return
    shutil.copyfile(source, destination)


def profile_lock_readiness(
    checkout: Path, manifest: Dict[str, Any]
) -> Tuple[bool, str]:
    """Verify that a checkout still uses the checked-in profile lock."""
    lock = manifest["lock"]
    source = PROFILE_ROOT / lock["path"]
    expected_hash = lock["sha256"]
    if not source.is_file() or _sha256(source) != expected_hash:
        return False, f"Checked-in profile lock is missing or corrupt: {source}"

    destination = checkout / "uv.lock"
    if not destination.is_file() or _sha256(destination) != expected_hash:
        return False, f"BabelDOC profile lock does not match: {destination}"
    return True, "Profile lock verified"


def _same_remote(actual: str, expected: str) -> bool:
    """Compare canonical GitHub URLs while tolerating a trailing .git."""
    return actual.rstrip("/").removesuffix(".git") == expected.rstrip("/").removesuffix(
        ".git"
    )


def ensure_managed_checkout(manifest: Dict[str, Any]) -> Path:
    """Acquire the exact profile revision in the Frank OCR-owned location."""
    checkout = MANAGED_BABELDOC_PATH
    if not checkout.exists():
        RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--no-checkout", manifest["source_url"], str(checkout)],
            check=True,
            env=_runtime_environment(),
        )
        subprocess.run(
            ["git", "checkout", "--detach", manifest["revision"]],
            cwd=checkout,
            check=True,
            env=_runtime_environment(),
        )
        return checkout

    if not checkout.is_dir():
        raise RuntimeError(f"Managed BabelDOC path is not a directory: {checkout}")
    remote = run_git(checkout, "config", "--get", "remote.origin.url")
    if remote.returncode != 0 or not _same_remote(
        remote.stdout.strip(), manifest["source_url"]
    ):
        raise RuntimeError(
            f"Managed BabelDOC checkout has a different origin: {checkout}. "
            "Move it aside instead of allowing Frank OCR to overwrite it."
        )
    return checkout


def _clear_runtime_state() -> None:
    """Remove the old selection marker before a destructive profile reset."""
    if not MANAGED_RUNTIME_STATE_PATH.exists():
        return
    if not MANAGED_RUNTIME_STATE_PATH.is_file():
        raise RuntimeError(
            f"BabelDOC runtime state path is not a file: {MANAGED_RUNTIME_STATE_PATH}"
        )
    MANAGED_RUNTIME_STATE_PATH.unlink()


def _ensure_pinned_revision(checkout: Path, manifest: Dict[str, Any]) -> None:
    """Ensure the pinned commit is locally available from canonical upstream."""
    revision = manifest["revision"]
    available = run_git(checkout, "cat-file", "-e", f"{revision}^{{commit}}")
    if available.returncode != 0:
        release_tag = manifest.get("release_tag")
        fetch_target = f"refs/tags/{release_tag}" if release_tag else revision
        subprocess.run(
            ["git", "fetch", "--no-tags", manifest["source_url"], fetch_target],
            cwd=checkout,
            check=True,
            env=_runtime_environment(),
        )
        available = run_git(checkout, "cat-file", "-e", f"{revision}^{{commit}}")
        if available.returncode != 0:
            raise RuntimeError(
                f"Canonical BabelDOC source does not provide the pinned revision {revision}"
            )


def _discard_profile_lock(checkout: Path) -> None:
    """Remove a prior generated lock that Git clean may intentionally retain."""
    lock = checkout / "uv.lock"
    if not lock.exists() and not lock.is_symlink():
        return
    if lock.is_dir() and not lock.is_symlink():
        shutil.rmtree(lock)
    else:
        lock.unlink()


def reconcile_checkout(checkout: Path, manifest: Dict[str, Any]) -> Path:
    """Discard prior state and force a Git worktree to the pinned revision."""
    revision = manifest["revision"]
    _ensure_pinned_revision(checkout, manifest)
    _clear_runtime_state()

    # The caller has explicitly selected this checkout for normalization. This
    # reset discards branches, staged and unstaged changes, untracked files,
    # prior profile patches, and generated locks before the profile is applied.
    subprocess.run(
        ["git", "clean", "-fd"],
        cwd=checkout,
        check=True,
        env=_runtime_environment(),
    )
    _discard_profile_lock(checkout)
    subprocess.run(
        ["git", "checkout", "--detach", "--force", revision],
        cwd=checkout,
        check=True,
        env=_runtime_environment(),
    )
    return checkout


def _external_checkout_root(checkout: Path) -> Path:
    """Return an external Git worktree root or reject an ambiguous path."""
    supplied = checkout.expanduser().resolve()
    if not supplied.is_dir():
        raise RuntimeError(f"BabelDOC checkout does not exist: {supplied}")
    root = run_git(supplied, "rev-parse", "--show-toplevel")
    if root.returncode != 0:
        raise RuntimeError(f"Not a readable Git checkout: {supplied}")
    worktree_root = Path(root.stdout.strip()).resolve()
    if worktree_root != supplied:
        raise RuntimeError(
            f"--path must name the BabelDOC Git worktree root, not {supplied}"
        )
    if worktree_root == MANAGED_BABELDOC_PATH.resolve():
        raise RuntimeError("Use `ocr-flow runtime setup` without --path for the managed runtime")
    return worktree_root


def reconcile_managed_checkout(manifest: Dict[str, Any]) -> Path:
    """Reset Frank OCR's owned runtime to the profile revision before setup."""
    return reconcile_checkout(ensure_managed_checkout(manifest), manifest)


def reconcile_external_checkout(checkout: Path, manifest: Dict[str, Any]) -> Path:
    """Force an explicitly supplied user Git checkout to the pinned profile."""
    return reconcile_checkout(_external_checkout_root(checkout), manifest)


def _record_runtime_setup(
    checkout: Path, manifest: Dict[str, Any], profile: str, *, managed: bool
) -> None:
    """Write the marker used by Translation Enrichment runtime resolution."""
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    state = {
        "runtime": manifest["runtime"],
        "version": manifest["version"],
        "revision": manifest["revision"],
        "profile": profile,
        "checkout": str(checkout.resolve()),
        "managed": managed,
    }
    MANAGED_RUNTIME_STATE_PATH.write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )


def bootstrap(
    checkout: Path,
    manifest: Dict[str, Any],
    profile: str,
    *,
    managed: Optional[bool] = None,
) -> None:
    """Install a verified profile and apply only its declared optional patch."""
    if profile == "windows-directml" and os.name != "nt":
        raise RuntimeError("windows-directml is supported only on Windows")

    valid, message = verify_checkout(checkout, manifest, profile)
    if not valid:
        raise RuntimeError(message)

    patch = profile_patch_path(manifest, profile)
    patch_needed = patch and provider_file_state(checkout, manifest) == "upstream"
    if patch_needed and not provider_files_are_clean(checkout, manifest):
        raise RuntimeError(
            "Refusing to apply the DirectML patch over other provider-file changes"
        )

    ensure_profile_lock(checkout, manifest)
    command = ["uv", "sync", "--locked"]
    for package in manifest["profiles"][profile].get("reinstall_packages", []):
        command.extend(["--reinstall-package", package])
    extra = manifest["profiles"][profile]["extra"]
    if extra:
        command.extend(["--extra", extra])
    subprocess.run(command, cwd=checkout, check=True, env=_runtime_environment())

    post_sync_packages = manifest["profiles"][profile]["post_sync_packages"]
    if post_sync_packages:
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(checkout_python(checkout)),
                "--reinstall",
                "--no-deps",
                *post_sync_packages,
            ],
            cwd=checkout,
            check=True,
            env=_runtime_environment(),
        )
    subprocess.run(
        ["uv", "run", "--locked", "babeldoc", "--version"],
        cwd=checkout,
        check=True,
        env=_runtime_environment(),
    )
    if patch_needed:
        assert patch is not None
        subprocess.run(
            ["git", "apply", str(patch)],
            cwd=checkout,
            check=True,
            env=_runtime_environment(),
        )
        message = "Windows DirectML layout patch is applied"
    if managed is not None:
        _record_runtime_setup(checkout, manifest, profile, managed=managed)
    print(f"Installed {profile}: {message}")


def installed_checkout_readiness(
    checkout: Path, manifest: Dict[str, Any], profile: str
) -> Tuple[bool, str]:
    """Verify the source and lock state required by an installed profile."""
    valid, message = verify_checkout(checkout, manifest, profile)
    if not valid:
        return False, message

    lock_ready, lock_message = profile_lock_readiness(checkout, manifest)
    if not lock_ready:
        return False, lock_message

    if profile == "windows-directml" and provider_file_state(checkout, manifest) != "directml":
        return False, "Windows DirectML layout patch is not applied"
    return True, message


def smoke(
    checkout: Path, manifest: Dict[str, Any], profile: str, input_path: Path
) -> None:
    """Run local layout inference without invoking a translation API."""
    valid, message = verify_checkout(checkout, manifest, profile)
    if not valid:
        raise RuntimeError(message)
    if not input_path.is_file():
        raise RuntimeError(f"Smoke-test PDF does not exist: {input_path}")
    subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-c",
            SMOKE_SCRIPT,
            str(input_path.resolve()),
            profile,
        ],
        cwd=checkout,
        check=True,
        env=_runtime_environment(),
    )


def latest_upstream_release(manifest: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Return the newest stable upstream tag without changing any checkout."""
    result = subprocess.run(
        ["git", "ls-remote", "--tags", manifest["source_url"]],
        capture_output=True,
        text=True,
        check=False,
        env=_runtime_environment(),
    )
    if result.returncode != 0:
        return None, result.stderr.strip() or "unable to query upstream tags"

    releases = []
    for line in result.stdout.splitlines():
        match = re.search(r"refs/tags/(v(\d+)\.(\d+)\.(\d+))\^?", line)
        if match:
            releases.append(
                ((int(match.group(2)), int(match.group(3)), int(match.group(4))), match.group(1))
            )
    if not releases:
        return None, "no stable upstream tags were returned"
    return max(releases)[1], None


def status_lines(manifest: Dict[str, Any]) -> Tuple[Tuple[str, ...], bool]:
    """Render local runtime and advisory upstream-release status."""
    ready, local_message = recorded_runtime_readiness()
    latest, error = latest_upstream_release(manifest)
    lines = [
        f"Supported BabelDOC: v{manifest['version']} ({manifest['revision']})",
        local_message,
    ]
    if latest:
        if latest == manifest["release_tag"]:
            lines.append(f"Upstream release check: {latest} (current profile)")
        else:
            lines.append(
                f"Upstream release check: {latest} is newer than the tested "
                f"profile {manifest['release_tag']}; no automatic upgrade was performed."
            )
    else:
        lines.append(f"Upstream release check unavailable: {error}")
    return tuple(lines), ready


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify", "bootstrap", "smoke", "status"])
    parser.add_argument(
        "--path",
        type=Path,
        help="Advanced external BabelDOC checkout; omitted uses Frank OCR's managed runtime",
    )
    parser.add_argument(
        "--profile",
        default="cpu-safe",
        choices=["cpu-safe", "windows-directml"],
        help="Runtime Profile to verify or install (default: cpu-safe)",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--input", type=Path, help="Single-page PDF for smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    if args.command == "status":
        lines, _ = status_lines(manifest)
        print("\n".join(lines))
        return 0

    try:
        managed = args.path is None
        if args.command == "bootstrap":
            checkout = (
                reconcile_managed_checkout(manifest)
                if managed
                else reconcile_external_checkout(args.path, manifest)
            )
        elif managed:
            checkout = ensure_managed_checkout(manifest)
        else:
            checkout = _external_checkout_root(args.path)
        if args.command == "verify":
            valid, message = verify_checkout(checkout, manifest, args.profile)
            print(message)
            return 0 if valid else 1
        if args.command == "bootstrap":
            bootstrap(checkout, manifest, args.profile, managed=managed)
        else:
            if args.input is None:
                raise RuntimeError("smoke requires --input <PDF>")
            smoke(checkout, manifest, args.profile, args.input)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"BabelDOC Runtime Profile setup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
