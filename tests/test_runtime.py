"""Tests for resolving verified BabelDOC Runtime Profiles."""

import json

import pytest

from ocr_flow import babeldoc_runtime
from ocr_flow import runtime
from ocr_flow.config import Config


def test_runtime_profile_assets_live_inside_the_python_package():
    assert runtime.DEFAULT_BABELDOC_MANIFEST.is_file()
    assert runtime.DEFAULT_UMIOCR_MANIFEST.is_file()
    assert runtime.PROFILE_ROOT == runtime.PACKAGE_ROOT / "runtime_profiles"


def test_installed_runtime_uses_its_launch_directory(monkeypatch, tmp_path):
    package_root = tmp_path / "site-packages" / "ocr_flow"
    package_root.mkdir(parents=True)
    monkeypatch.setattr(runtime, "PACKAGE_ROOT", package_root)
    monkeypatch.chdir(tmp_path)

    assert runtime._resolve_project_root() == tmp_path


def _install_runtime_marker(
    monkeypatch, tmp_path, *, managed: bool, verified=True
):
    checkout = tmp_path / ("managed-BabelDOC" if managed else "external-BabelDOC")
    interpreter = checkout / ".venv" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"")
    state_path = tmp_path / "babeldoc-runtime-state.json"
    manifest = runtime.load_babeldoc_manifest()
    state_path.write_text(
        json.dumps(
            {
                "runtime": manifest["runtime"],
                "version": manifest["version"],
                "revision": manifest["revision"],
                "profile": "cpu-safe",
                "checkout": str(checkout.resolve()),
                "managed": managed,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "MANAGED_RUNTIME_STATE_PATH", state_path)
    if managed:
        monkeypatch.setattr(runtime, "MANAGED_BABELDOC_PATH", checkout)
    monkeypatch.setattr(
        babeldoc_runtime,
        "installed_checkout_readiness",
        lambda *_args: (verified, "source verified" if verified else "source changed"),
    )
    return checkout, state_path


def test_default_runtime_requires_project_managed_setup(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "MANAGED_BABELDOC_PATH", tmp_path / "BabelDOC")
    monkeypatch.setattr(runtime, "MANAGED_RUNTIME_STATE_PATH", tmp_path / "state.json")

    with pytest.raises(RuntimeError, match="ocr-flow runtime setup"):
        runtime.require_babeldoc_runtime(Config())


def test_default_runtime_resolves_verified_managed_checkout(monkeypatch, tmp_path):
    checkout, _ = _install_runtime_marker(monkeypatch, tmp_path, managed=True)

    selected = runtime.require_babeldoc_runtime(Config())

    assert selected.managed is True
    assert selected.checkout == checkout


def test_configured_external_path_resolves_only_after_matching_setup(
    monkeypatch, tmp_path
):
    checkout, _ = _install_runtime_marker(monkeypatch, tmp_path, managed=False)
    config = Config()
    config.babeldoc.path = str(checkout)

    selected = runtime.require_babeldoc_runtime(config)

    assert selected.managed is False
    assert selected.checkout == checkout


def test_external_path_without_setup_is_rejected(monkeypatch, tmp_path):
    checkout = tmp_path / "external-BabelDOC"
    checkout.mkdir()
    monkeypatch.setattr(runtime, "MANAGED_RUNTIME_STATE_PATH", tmp_path / "state.json")
    config = Config()
    config.babeldoc.path = str(checkout)

    with pytest.raises(RuntimeError, match="runtime setup --path"):
        runtime.require_babeldoc_runtime(config)


def test_external_path_requires_the_marker_to_match_its_checkout(monkeypatch, tmp_path):
    checkout, state_path = _install_runtime_marker(monkeypatch, tmp_path, managed=False)
    other_checkout = tmp_path / "other-BabelDOC"
    other_checkout.mkdir()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["checkout"] = str(other_checkout.resolve())
    state_path.write_text(json.dumps(state), encoding="utf-8")
    config = Config()
    config.babeldoc.path = str(checkout)

    with pytest.raises(RuntimeError, match="runtime setup --path"):
        runtime.require_babeldoc_runtime(config)


def test_external_path_rejects_a_checkout_that_fails_profile_verification(
    monkeypatch, tmp_path
):
    checkout, _ = _install_runtime_marker(
        monkeypatch, tmp_path, managed=False, verified=False
    )
    config = Config()
    config.babeldoc.path = str(checkout)

    with pytest.raises(RuntimeError, match="source changed"):
        runtime.require_babeldoc_runtime(config)


def test_recorded_runtime_readiness_reports_the_last_external_setup(
    monkeypatch, tmp_path
):
    checkout, _ = _install_runtime_marker(monkeypatch, tmp_path, managed=False)

    ready, message = runtime.recorded_runtime_readiness()

    assert ready
    assert str(checkout) in message
