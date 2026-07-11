"""Tests for the versioned external-runtime manifests and verifiers."""

import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import subprocess

import pytest

from ocr_flow import babeldoc_runtime as managed_runtime


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_script_module(name):
    spec = spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


babeldoc_runtime = load_script_module("babeldoc_runtime")
verify_umiocr_runtime = load_script_module("verify_umiocr_runtime")


def test_babeldoc_manifest_declares_cpu_and_directml_profiles():
    manifest = babeldoc_runtime.load_manifest()

    assert manifest["version"] == "0.6.3"
    assert manifest["release_tag"] == "v0.6.3"
    assert manifest["source_url"] == "https://github.com/funstory-ai/BabelDOC.git"
    assert manifest["profiles"]["cpu-safe"]["patch"] is None
    assert manifest["profiles"]["cpu-safe"]["reinstall_packages"] == ["onnxruntime"]
    assert manifest["profiles"]["windows-directml"]["post_sync_packages"] == [
        "onnxruntime-directml==1.24.4"
    ]
    assert "retired table detection" in babeldoc_runtime.SMOKE_SCRIPT
    directml_patch = babeldoc_runtime.profile_patch_path(manifest, "windows-directml")
    assert directml_patch is not None
    assert directml_patch.is_file()
    assert manifest["provider_files"] == {
        "babeldoc/docvision/doclayout.py": {
            "upstream_blob": "14126c1241263f3ee23cc31cffcfb18cd88a3ade",
            "windows_directml_blob": "2918aafe10314edcddf9d08741401a594062f80b",
        }
    }


def test_babeldoc_manifest_lock_matches_checked_in_profile_lock():
    manifest = babeldoc_runtime.load_manifest()
    lock_path = managed_runtime.PROFILE_ROOT / manifest["lock"]["path"]

    assert lock_path.is_file()
    assert hashlib.sha256(lock_path.read_bytes()).hexdigest().upper() == manifest["lock"]["sha256"]


def test_profile_lock_readiness_rejects_a_changed_external_lock(tmp_path):
    manifest = managed_runtime.load_manifest()
    checkout = tmp_path / "external-babeldoc"
    checkout.mkdir()
    (checkout / "uv.lock").write_text("different lock", encoding="utf-8")

    ready, message = managed_runtime.profile_lock_readiness(checkout, manifest)

    assert not ready
    assert "does not match" in message


def test_umiocr_verifier_accepts_matching_file(tmp_path):
    runtime_file = tmp_path / "runtime.exe"
    runtime_file.write_bytes(b"known runtime")
    manifest = {
        "files": [
            {
                "path": "runtime.exe",
                "bytes": runtime_file.stat().st_size,
                "sha256": hashlib.sha256(b"known runtime").hexdigest().upper(),
            }
        ]
    }

    assert verify_umiocr_runtime.verify_runtime(tmp_path, manifest) == []


def test_umiocr_verifier_reports_hash_mismatch(tmp_path):
    runtime_file = tmp_path / "runtime.exe"
    runtime_file.write_bytes(b"unexpected runtime")
    manifest = {
        "files": [
            {
                "path": "runtime.exe",
                "bytes": runtime_file.stat().st_size,
                "sha256": "0" * 64,
            }
        ]
    }

    assert verify_umiocr_runtime.verify_runtime(tmp_path, manifest) == [
        "SHA-256 mismatch for runtime.exe"
    ]


def test_checkout_python_prefers_windows_environment(tmp_path):
    interpreter = tmp_path / ".venv" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"")

    assert babeldoc_runtime.checkout_python(tmp_path) == interpreter


def test_runtime_manifests_are_valid_json():
    root = managed_runtime.PROFILE_ROOT
    for manifest_path in root.glob("*.json"):
        with manifest_path.open(encoding="utf-8") as handle:
            json.load(handle)


def _git(checkout, *arguments):
    result = subprocess.run(
        ["git", *arguments],
        cwd=checkout,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def test_reconcile_managed_checkout_resets_to_the_pinned_revision(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    checkout = runtime_root / "BabelDOC"
    checkout.mkdir(parents=True)
    _git(checkout, "init")
    _git(checkout, "config", "user.email", "tests@example.com")
    _git(checkout, "config", "user.name", "Runtime Tests")
    _git(
        checkout,
        "remote",
        "add",
        "origin",
        "https://github.com/funstory-ai/BabelDOC.git",
    )

    tracked_file = checkout / "version.txt"
    tracked_file.write_text("v0.6.3", encoding="utf-8")
    _git(checkout, "add", "version.txt")
    _git(checkout, "commit", "-m", "pinned revision")
    pinned_revision = _git(checkout, "rev-parse", "HEAD")

    tracked_file.write_text("other revision", encoding="utf-8")
    _git(checkout, "add", "version.txt")
    _git(checkout, "commit", "-m", "other revision")
    (checkout / "stale.txt").write_text("stale", encoding="utf-8")

    state_path = runtime_root / "babeldoc-runtime-state.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(managed_runtime, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(managed_runtime, "MANAGED_BABELDOC_PATH", checkout)
    monkeypatch.setattr(managed_runtime, "MANAGED_RUNTIME_STATE_PATH", state_path)

    result = managed_runtime.reconcile_managed_checkout(
        {
            "source_url": "https://github.com/funstory-ai/BabelDOC.git",
            "revision": pinned_revision,
        }
    )

    assert result == checkout
    assert _git(checkout, "rev-parse", "HEAD") == pinned_revision
    assert _git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert tracked_file.read_text(encoding="utf-8") == "v0.6.3"
    assert not (checkout / "stale.txt").exists()
    assert not state_path.exists()


def test_reconcile_external_checkout_discards_dirty_state_and_detaches(
    monkeypatch, tmp_path
):
    checkout = tmp_path / "external-babeldoc"
    checkout.mkdir()
    _git(checkout, "init")
    _git(checkout, "config", "user.email", "tests@example.com")
    _git(checkout, "config", "user.name", "Runtime Tests")

    (checkout / ".gitignore").write_text("uv.lock\n", encoding="utf-8")
    version_file = checkout / "version.txt"
    version_file.write_text("v0.6.3", encoding="utf-8")
    clean_file = checkout / "clean.txt"
    clean_file.write_text("clean", encoding="utf-8")
    _git(checkout, "add", ".gitignore", "version.txt", "clean.txt")
    _git(checkout, "commit", "-m", "pinned revision")
    pinned_revision = _git(checkout, "rev-parse", "HEAD")

    version_file.write_text("later", encoding="utf-8")
    clean_file.write_text("later", encoding="utf-8")
    _git(checkout, "add", "version.txt", "clean.txt")
    _git(checkout, "commit", "-m", "later revision")

    version_file.write_text("staged edit", encoding="utf-8")
    _git(checkout, "add", "version.txt")
    clean_file.write_text("unstaged edit", encoding="utf-8")
    (checkout / "stale.txt").write_text("untracked", encoding="utf-8")
    (checkout / "uv.lock").write_text("ignored old lock", encoding="utf-8")

    runtime_root = tmp_path / "runtime"
    state_path = runtime_root / "babeldoc-runtime-state.json"
    runtime_root.mkdir()
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(managed_runtime, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(managed_runtime, "MANAGED_RUNTIME_STATE_PATH", state_path)

    result = managed_runtime.reconcile_external_checkout(
        checkout,
        {
            "source_url": "https://github.com/funstory-ai/BabelDOC.git",
            "revision": pinned_revision,
        },
    )

    assert result == checkout
    assert _git(checkout, "rev-parse", "HEAD") == pinned_revision
    assert _git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert _git(checkout, "status", "--porcelain") == ""
    assert version_file.read_text(encoding="utf-8") == "v0.6.3"
    assert clean_file.read_text(encoding="utf-8") == "clean"
    assert not (checkout / "stale.txt").exists()
    assert not (checkout / "uv.lock").exists()
    assert not state_path.exists()


def test_reconcile_external_checkout_fetches_the_pinned_commit_from_canonical_source(
    monkeypatch, tmp_path
):
    canonical_worktree = tmp_path / "canonical-worktree"
    canonical_worktree.mkdir()
    _git(canonical_worktree, "init")
    _git(canonical_worktree, "config", "user.email", "tests@example.com")
    _git(canonical_worktree, "config", "user.name", "Runtime Tests")
    (canonical_worktree / "version.txt").write_text("v0.6.3", encoding="utf-8")
    _git(canonical_worktree, "add", "version.txt")
    _git(canonical_worktree, "commit", "-m", "pinned revision")
    pinned_revision = _git(canonical_worktree, "rev-parse", "HEAD")
    canonical_remote = tmp_path / "canonical.git"
    subprocess.run(["git", "clone", "--bare", str(canonical_worktree), str(canonical_remote)], check=True)

    unrelated_worktree = tmp_path / "unrelated-worktree"
    unrelated_worktree.mkdir()
    _git(unrelated_worktree, "init")
    _git(unrelated_worktree, "config", "user.email", "tests@example.com")
    _git(unrelated_worktree, "config", "user.name", "Runtime Tests")
    (unrelated_worktree / "version.txt").write_text("other", encoding="utf-8")
    _git(unrelated_worktree, "add", "version.txt")
    _git(unrelated_worktree, "commit", "-m", "unrelated revision")
    unrelated_remote = tmp_path / "unrelated.git"
    subprocess.run(["git", "clone", "--bare", str(unrelated_worktree), str(unrelated_remote)], check=True)

    checkout = tmp_path / "external-babeldoc"
    subprocess.run(["git", "clone", str(unrelated_remote), str(checkout)], check=True)
    assert (
        managed_runtime.run_git(checkout, "cat-file", "-e", f"{pinned_revision}^{{commit}}")
        .returncode
        != 0
    )

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setattr(managed_runtime, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(
        managed_runtime,
        "MANAGED_RUNTIME_STATE_PATH",
        runtime_root / "babeldoc-runtime-state.json",
    )

    managed_runtime.reconcile_external_checkout(
        checkout,
        {
            "source_url": str(canonical_remote),
            "revision": pinned_revision,
        },
    )

    assert _git(checkout, "rev-parse", "HEAD") == pinned_revision
    assert _git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"


def test_installed_checkout_requires_the_directml_patch_after_setup(monkeypatch, tmp_path):
    manifest = {"lock": {"path": "unused", "sha256": "unused"}}
    monkeypatch.setattr(managed_runtime, "verify_checkout", lambda *_args: (True, "verified"))
    monkeypatch.setattr(
        managed_runtime, "profile_lock_readiness", lambda *_args: (True, "lock verified")
    )
    monkeypatch.setattr(managed_runtime, "provider_file_state", lambda *_args: "upstream")

    ready, message = managed_runtime.installed_checkout_readiness(
        tmp_path, manifest, "windows-directml"
    )

    assert not ready
    assert message == "Windows DirectML layout patch is not applied"


def test_bootstrap_records_the_verified_external_checkout(monkeypatch, tmp_path):
    checkout = tmp_path / "external-babeldoc"
    checkout.mkdir()
    runtime_root = tmp_path / "runtime"
    state_path = runtime_root / "babeldoc-runtime-state.json"
    manifest = managed_runtime.load_manifest()

    monkeypatch.setattr(managed_runtime, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(managed_runtime, "MANAGED_RUNTIME_STATE_PATH", state_path)
    monkeypatch.setattr(managed_runtime, "verify_checkout", lambda *_args: (True, "verified"))
    monkeypatch.setattr(managed_runtime, "ensure_profile_lock", lambda *_args: None)
    monkeypatch.setattr(managed_runtime.subprocess, "run", lambda *_args, **_kwargs: None)

    managed_runtime.bootstrap(checkout, manifest, "cpu-safe", managed=False)

    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "runtime": manifest["runtime"],
        "version": manifest["version"],
        "revision": manifest["revision"],
        "profile": "cpu-safe",
        "checkout": str(checkout.resolve()),
        "managed": False,
    }


@pytest.mark.skipif(os.name != "nt", reason="DirectML profile is Windows-only")
def test_bootstrap_applies_a_patch_only_for_the_directml_profile(monkeypatch, tmp_path):
    checkout = tmp_path / "BabelDOC"
    checkout.mkdir()
    patch = tmp_path / "directml.patch"
    patch.write_text("patch", encoding="utf-8")
    commands = []
    manifest = {
        "profiles": {
            "cpu-safe": {
                "extra": None,
                "reinstall_packages": [],
                "post_sync_packages": [],
            },
            "windows-directml": {
                "extra": "directml",
                "reinstall_packages": [],
                "post_sync_packages": [],
            },
        }
    }

    monkeypatch.setattr(managed_runtime, "verify_checkout", lambda *_args: (True, "verified"))
    monkeypatch.setattr(
        managed_runtime,
        "profile_patch_path",
        lambda _manifest, profile: patch if profile == "windows-directml" else None,
    )
    monkeypatch.setattr(managed_runtime, "provider_file_state", lambda *_args: "upstream")
    monkeypatch.setattr(managed_runtime, "provider_files_are_clean", lambda *_args: True)
    monkeypatch.setattr(managed_runtime, "ensure_profile_lock", lambda *_args: None)
    monkeypatch.setattr(
        managed_runtime.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    managed_runtime.bootstrap(checkout, manifest, "cpu-safe")
    managed_runtime.bootstrap(checkout, manifest, "windows-directml")

    assert ["git", "apply", str(patch)] in commands
    assert commands.count(["git", "apply", str(patch)]) == 1


def test_cpu_profile_reinstalls_onnxruntime_from_the_locked_environment(monkeypatch, tmp_path):
    calls = []
    manifest = {
        "profiles": {
            "cpu-safe": {
                "extra": None,
                "reinstall_packages": ["onnxruntime"],
                "post_sync_packages": [],
            }
        }
    }

    monkeypatch.setattr(managed_runtime, "verify_checkout", lambda *_args: (True, "verified"))
    monkeypatch.setattr(managed_runtime, "profile_patch_path", lambda *_args: None)
    monkeypatch.setattr(managed_runtime, "ensure_profile_lock", lambda *_args: None)
    monkeypatch.setattr(
        managed_runtime.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )

    managed_runtime.bootstrap(tmp_path, manifest, "cpu-safe")

    assert calls[0] == [
        "uv",
        "sync",
        "--locked",
        "--reinstall-package",
        "onnxruntime",
    ]
