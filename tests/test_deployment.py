"""Deployment preflight contract tests."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ocr_flow.config import Config
from ocr_flow.deployment import (
    DeploymentCheck,
    DeploymentReport,
    _path_check,
    aggregate_verdict,
    build_deployment_report,
    serialize_report,
)


def _item(status, *, required=True):
    return DeploymentCheck("test.check", status, "safe", {}, None, required)


@pytest.mark.parametrize(
    ("checks", "expected"),
    [
        ([_item("PASS")], "READY"),
        ([_item("WARN")], "UNVERIFIED"),
        ([_item("UNVERIFIED")], "UNVERIFIED"),
        ([_item("FAIL", required=False)], "READY"),
        ([_item("FAIL")], "NOT_READY"),
    ],
)
def test_aggregate_verdict(checks, expected):
    assert aggregate_verdict(checks) == expected


def test_report_schema_and_stable_unique_ids(tmp_path, monkeypatch):
    config = Config(output_dir=str(tmp_path / "output"))
    config.mineru.api_token = "distinct-mineru-secret"
    config.babeldoc.openai_api_key = "distinct-translation-secret"
    config.umiocr.engine = "rapid"
    monkeypatch.setattr("ocr_flow.deployment.find_umi_ocr", lambda config: "<rapid-executable>")
    monkeypatch.setattr("ocr_flow.deployment.find_ghostscript", lambda config: None)
    monkeypatch.setattr("ocr_flow.deployment.runtime_readiness", lambda runtime: (True, "raw path ignored"))
    monkeypatch.setattr("ocr_flow.deployment.resolve_babeldoc_runtime", lambda config: object())

    report = build_deployment_report(config, checkout=tmp_path)
    payload = json.loads(serialize_report(report, config))
    ids = [check["id"] for check in payload["checks"]]

    assert payload["schema_version"] == 1
    assert len(ids) == len(set(ids))
    assert set(ids) == {
        "platform.windows",
        "platform.architecture",
        "platform.python",
        "platform.servicing",
        "tool.uv",
        "permissions.standard_user",
        "filesystem.checkout",
        "filesystem.user_config",
        "filesystem.temp",
        "filesystem.output",
        "filesystem.path_policy",
        "resource.disk",
        "resource.memory",
        "resource.cpu",
        "runtime.ghostscript",
        "runtime.umiocr_rapid",
        "runtime.babeldoc_cpu",
        "process.umiocr_port",
        "network.proxy_tls",
        "credential.mineru",
        "credential.translation",
        "recovery.state",
        "security.edr",
        "hardware.no_gpu",
        "validation.full_matrix",
    }
    assert {check["status"] for check in payload["checks"]} <= {"PASS", "WARN", "FAIL", "UNVERIFIED"}
    assert "distinct-mineru-secret" not in json.dumps(payload)
    assert "distinct-translation-secret" not in json.dumps(payload)
    assert str(Path.home()) not in json.dumps(payload)


def test_serialization_rejects_configured_secret():
    config = Config()
    config.mineru.api_token = "distinct-secret-value"
    report = DeploymentReport(1, "now", "READY", [_item("PASS")])
    leaking = replace(report, checks=[replace(report.checks[0], summary="distinct-secret-value")])

    with pytest.raises(ValueError, match="disclosure scan"):
        serialize_report(leaking, config)


def test_serialization_rejects_raw_user_profile_path():
    config = Config()
    report = DeploymentReport(1, "now", "READY", [_item("PASS")])
    leaking = replace(report, checks=[replace(report.checks[0], summary=str(Path.home() / "private"))])

    with pytest.raises(ValueError, match="disclosure scan"):
        serialize_report(leaking, config)


def test_build_does_not_start_or_install_runtime(tmp_path, monkeypatch):
    config = Config(output_dir=str(tmp_path))
    config.umiocr.engine = "rapid"
    monkeypatch.setattr("ocr_flow.deployment.find_umi_ocr", lambda config: None)
    monkeypatch.setattr("ocr_flow.deployment.find_ghostscript", lambda config: None)
    monkeypatch.setattr("ocr_flow.deployment.runtime_readiness", lambda runtime: (False, "not ready"))
    monkeypatch.setattr("ocr_flow.deployment.resolve_babeldoc_runtime", lambda config: object())
    monkeypatch.setattr("ocr_flow.self_check.start_umi_ocr", lambda *args, **kwargs: pytest.fail("runtime started"))

    report = build_deployment_report(config, checkout=tmp_path)

    assert next(check for check in report.checks if check.id == "process.umiocr_port").evidence["auto_started"] is False


def test_non_ascii_space_and_long_path_atomic_probe(tmp_path):
    target = tmp_path / "用户 Profile" / ("long-segment-" * 8)
    target.mkdir(parents=True)

    result = _path_check("filesystem.simulated", "<output>", target)

    assert result.status == "PASS"
    assert not list(target.glob(".ocr-flow-doctor-*"))


def test_read_only_path_is_reported_as_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("ocr_flow.deployment._writable_probe", lambda path: False)

    result = _path_check("filesystem.output", "<output>", tmp_path)

    assert result.status == "FAIL"
    assert "user-writable" in result.remediation
