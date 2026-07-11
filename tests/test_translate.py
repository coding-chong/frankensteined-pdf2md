"""Tests for BabelDOC command construction and sensitive-value handling."""

from pathlib import Path

import pytest

from ocr_flow.config import Config
from ocr_flow.runtime import BabelDocRuntime, MANAGED_BABELDOC_PATH
from ocr_flow.steps.translate import (
    _build_babeldoc_command,
    _format_command_for_log,
    _redact_secret,
    translate_pdf,
)


def test_format_command_for_log_redacts_openai_api_key():
    command = [
        "babeldoc",
        "--openai-api-key",
        "live-secret",
        "--openai-model",
        "example-model",
    ]

    rendered = _format_command_for_log(command)

    assert "live-secret" not in rendered
    assert "--openai-api-key ***" in rendered
    assert "example-model" in rendered


def test_redact_secret_removes_key_from_subprocess_output():
    result = _redact_secret("backend rejected live-secret", "live-secret")

    assert result == "backend rejected ***"


def test_build_command_passes_public_primary_font_family():
    config = Config()
    config.babeldoc.primary_font_family = "serif"
    config.babeldoc.openai = False
    managed_runtime = BabelDocRuntime(Path("C:/runtime/BabelDOC"), True)

    command = _build_babeldoc_command(
        Path("input.pdf"),
        Path("output"),
        config,
        skip_clean=False,
        ocr_workaround=False,
        runtime=managed_runtime,
    )

    assert command[:6] == [
        "uv",
        "run",
        "--directory",
        str(Path("C:/runtime/BabelDOC")),
        "--locked",
        "babeldoc",
    ]
    assert command[command.index("--primary-font-family") + 1] == "serif"


def test_build_command_uses_configured_external_runtime():
    config = Config()
    config.babeldoc.path = "C:/runtime/BabelDOC"

    command = _build_babeldoc_command(
        Path("input.pdf"),
        Path("output"),
        config,
        skip_clean=False,
        ocr_workaround=False,
    )

    assert command[:6] == [
        "uv",
        "run",
        "--directory",
        str(Path("C:/runtime/BabelDOC")),
        "--locked",
        "babeldoc",
    ]


def test_build_command_omits_automatic_primary_font_family():
    config = Config()
    config.babeldoc.openai = False

    command = _build_babeldoc_command(
        Path("input.pdf"),
        Path("output"),
        config,
        skip_clean=False,
        ocr_workaround=False,
    )

    assert "--primary-font-family" not in command


def test_build_command_uses_managed_runtime_by_default():
    config = Config()
    config.babeldoc.openai = False

    command = _build_babeldoc_command(
        Path("input.pdf"),
        Path("output"),
        config,
        skip_clean=False,
        ocr_workaround=False,
    )

    assert command[:6] == [
        "uv",
        "run",
        "--directory",
        str(MANAGED_BABELDOC_PATH),
        "--locked",
        "babeldoc",
    ]


def test_translate_requires_managed_setup_before_starting_subprocess(monkeypatch, tmp_path):
    config = Config()
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"pdf")
    output_path = tmp_path / "output.pdf"

    monkeypatch.setattr(
        'ocr_flow.steps.translate.require_babeldoc_runtime',
        lambda _config: (_ for _ in ()).throw(
            RuntimeError("Managed BabelDOC Runtime is not installed. Run `ocr-flow runtime setup`.")
        ),
    )
    monkeypatch.setattr(
        'ocr_flow.steps.translate.subprocess.run',
        lambda *args, **kwargs: pytest.fail("BabelDOC subprocess must not start before runtime setup"),
    )

    with pytest.raises(RuntimeError, match="runtime setup"):
        translate_pdf(input_path, output_path, config)
