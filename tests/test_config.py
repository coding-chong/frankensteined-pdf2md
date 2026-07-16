#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for configuration management module.

Test suite covering:
- Config class creation and defaults
- Config loading from files
- Config saving to files
- Sub-config classes
- Environment-specific behavior
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import os

from ocr_flow.config import (
    Config,
    UmiOcrConfig,
    BabelDocConfig,
    CompressConfig,
    MinerUConfig,
    PostProcessConfig,
    normalize_umiocr_engine,
    normalize_primary_font_family,
    resolve_umiocr_language,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_home(temp_dir, monkeypatch):
    """Set a temporary home directory."""
    monkeypatch.setenv('USERPROFILE' if os.name == 'nt' else 'HOME', str(temp_dir))
    return temp_dir


# =============================================================================
# TestUmiOcrConfig - UMI OCR Configuration Tests
# =============================================================================

class TestUmiOcrConfig:
    """Tests for UmiOcrConfig class."""

    def test_umiocr_default_url(self):
        """Test default UMI OCR URL."""
        config = UmiOcrConfig()
        assert config.url == "http://127.0.0.1:1224"

    def test_umiocr_default_language(self):
        """Test default language configuration."""
        config = UmiOcrConfig()
        assert config.language == "models/config_en.txt"

    def test_umiocr_default_engine_is_paddle(self):
        """Existing configuration files keep Paddle behavior by default."""
        assert UmiOcrConfig().engine == "paddle"

    def test_umiocr_default_enabled(self):
        """Test default enabled state."""
        config = UmiOcrConfig()
        assert config.enabled == True

    def test_umiocr_default_exe_path(self):
        """Test default UMI OCR exe path."""
        config = UmiOcrConfig()
        assert config.exe_path is None

    def test_umiocr_custom_values(self):
        """Test creating with custom values."""
        config = UmiOcrConfig(
            enabled=False,
            url="http://192.168.1.100:8080",
            language="models/config_chinese.txt",
            exe_path="E:/Umi-OCR/Umi-OCR.exe",
            engine="rapid",
        )
        assert config.enabled == False
        assert config.url == "http://192.168.1.100:8080"
        assert config.language == "models/config_chinese.txt"
        assert config.exe_path == "E:/Umi-OCR/Umi-OCR.exe"
        assert config.engine == "rapid"


# =============================================================================
# TestBabelDocConfig - BabelDOC Configuration Tests
# =============================================================================

class TestBabelDocConfig:
    """Tests for BabelDocConfig class."""

    def test_babeldoc_default_values(self):
        """Test default BabelDOC values."""
        config = BabelDocConfig()
        assert config.path is None
        assert config.lang_in == "en-US"
        assert config.lang_out == "zh-CN"
        assert config.openai == True
        assert config.openai_model == "deepseek-chat"
        assert config.openai_base_url == "https://api.deepseek.com"

    def test_babeldoc_default_api_key(self):
        """Test default API key is empty."""
        config = BabelDocConfig()
        assert config.openai_api_key == ""

    def test_babeldoc_openai_config(self):
        """Test OpenAI configuration."""
        config = BabelDocConfig(
            openai=True,
            openai_model="gpt-4",
            openai_base_url="https://api.openai.com/v1",
            openai_api_key="sk-test-key",
        )
        assert config.openai == True
        assert config.openai_model == "gpt-4"
        assert config.openai_base_url == "https://api.openai.com/v1"
        assert config.openai_api_key == "sk-test-key"

    def test_babeldoc_custom_path(self):
        """Test custom BabelDOC path."""
        config = BabelDocConfig(path="/path/to/babeldoc")
        assert config.path == "/path/to/babeldoc"

    def test_babeldoc_primary_font_family_defaults_to_automatic(self):
        assert BabelDocConfig().primary_font_family is None

    def test_babeldoc_primary_font_family_rejects_unknown_value(self):
        with pytest.raises(ValueError, match="primary_font_family"):
            normalize_primary_font_family("Source Han Serif")


# =============================================================================
# TestCompressConfig - Compression Configuration Tests
# =============================================================================

class TestCompressConfig:
    """Tests for CompressConfig class."""

    def test_compress_default_quality(self):
        """Test default compression quality."""
        config = CompressConfig()
        assert config.quality == "ebook"

    def test_compress_default_ghostscript_path(self):
        """Test default Ghostscript path is None (auto-detect)."""
        config = CompressConfig()
        assert config.ghostscript_path is None

    def test_compress_custom_values(self):
        """Test custom compression settings."""
        config = CompressConfig(
            ghostscript_path="/usr/bin/gs",
            quality="printer",
        )
        assert config.ghostscript_path == "/usr/bin/gs"
        assert config.quality == "printer"

    def test_compress_quality_options(self):
        """Test different quality options."""
        valid_qualities = ["screen", "ebook", "printer", "prepress"]
        for quality in valid_qualities:
            config = CompressConfig(quality=quality)
            assert config.quality == quality


# =============================================================================
# TestMinerUConfig - MinerU Configuration Tests
# =============================================================================

class TestMinerUConfig:
    """Tests for MinerUConfig class."""

    def test_mineru_default_token(self):
        """Test default API token is empty."""
        config = MinerUConfig()
        assert config.api_token == ""

    def test_mineru_custom_token(self):
        """Test custom API token."""
        config = MinerUConfig(api_token="my-secret-token")
        assert config.api_token == "my-secret-token"


# =============================================================================
# TestPostProcessConfig - Post-Processing Configuration Tests
# =============================================================================

class TestPostProcessConfig:
    """Tests for PostProcessConfig class."""

    def test_postprocess_defaults(self):
        """Test default post-processing settings."""
        config = PostProcessConfig()
        assert config.fix_format == True
        assert config.download_images == True

    def test_postprocess_custom_values(self):
        """Test custom post-processing settings."""
        config = PostProcessConfig(
            fix_format=False,
            download_images=False,
        )
        assert config.fix_format == False
        assert config.download_images == False


# =============================================================================
# TestConfig - Main Config Class Tests
# =============================================================================

class TestConfig:
    """Tests for main Config class."""

    def test_config_default_values(self):
        """Test default configuration values."""
        config = Config()
        assert config.output_dir == "./output"
        assert config.verbose == False

    def test_config_default_sub_configs(self):
        """Test that sub-configs are initialized."""
        config = Config()
        assert isinstance(config.umiocr, UmiOcrConfig)
        assert isinstance(config.babeldoc, BabelDocConfig)
        assert isinstance(config.compress, CompressConfig)
        assert isinstance(config.mineru, MinerUConfig)
        assert isinstance(config.postprocess, PostProcessConfig)

    def test_config_get_config_path_windows(self, temp_home, monkeypatch):
        """Test config path on Windows."""
        if os.name != 'nt':
            pytest.skip("Windows-only test")

        path = Config.get_config_path()
        assert '.ocr-flow' in str(path)
        assert 'config.toml' in str(path)

    def test_config_get_config_path_unix(self, temp_home, monkeypatch):
        """Test config path on Unix systems."""
        if os.name == 'nt':
            pytest.skip("Unix-only test")

        path = Config.get_config_path()
        assert '.ocr-flow' in str(path)
        assert 'config.toml' in str(path)

    def test_config_load_missing_file(self, temp_dir):
        """Test loading from nonexistent config file returns defaults."""
        nonexistent = temp_dir / "nonexistent.toml"
        config = Config.load(nonexistent)

        # Should return default config
        assert config.output_dir == "./output"

    def test_config_save_and_load(self, temp_dir):
        """Test saving and loading configuration."""
        original = Config()
        original.output_dir = "/custom/output"
        original.verbose = True
        original.mineru.api_token = "test-token"
        original.compress.quality = "printer"
        original.babeldoc.primary_font_family = "sans-serif"

        config_path = temp_dir / "config.toml"
        original.save(config_path)

        # Load the saved config
        loaded = Config.load(config_path)

        assert loaded.output_dir == "/custom/output"
        assert loaded.verbose == True
        assert loaded.mineru.api_token == "test-token"
        assert loaded.compress.quality == "printer"
        assert loaded.babeldoc.primary_font_family == "sans-serif"

    def test_config_save_creates_directory(self, temp_dir):
        """Test that save creates parent directories."""
        config = Config()
        config_path = temp_dir / "nested" / "dir" / "config.toml"

        config.save(config_path)

        assert config_path.exists()
        assert config_path.parent.exists()

    def test_config_partial_load(self, temp_dir):
        """Test loading config with partial content."""
        # Create a minimal config file
        config_path = temp_dir / "partial.toml"
        config_path.write_text("""
[general]
output_dir = "/test/output"

[mineru]
api_token = "partial-token"
""", encoding='utf-8')

        config = Config.load(config_path)

        assert config.output_dir == "/test/output"
        assert config.mineru.api_token == "partial-token"
        # Other values should be defaults
        assert config.verbose == False
        assert config.compress.quality == "ebook"


# =============================================================================
# TestConfigWithToml - TOML Handling Tests
# =============================================================================

class TestConfigWithToml:
    """Tests for TOML file handling."""

    def test_config_save_format(self, temp_dir):
        """Test that config saves in valid TOML format."""
        config = Config()
        config.mineru.api_token = "test-token"

        config_path = temp_dir / "test.toml"
        config.save(config_path)

        content = config_path.read_text(encoding='utf-8')

        # Should be valid TOML
        assert "[general]" in content
        assert "[umiocr]" in content
        assert "[babeldoc]" in content
        assert "[compress]" in content
        assert "[mineru]" in content
        assert "[postprocess]" in content

    def test_config_load_full_file(self, temp_dir):
        """Test loading a complete config file."""
        config_content = """
[general]
output_dir = "/custom/output"
verbose = true

[umiocr]
enabled = false
url = "http://192.168.1.1:1224"
language = "models/config_chinese.txt"
exe_path = "E:/Umi-OCR/Umi-OCR.exe"

[babeldoc]
path = "/path/to/babeldoc"
lang_in = "ja-JP"
lang_out = "zh-CN"
openai = true
openai_model = "gpt-4"
openai_base_url = "https://api.openai.com/v1"
openai_api_key = "sk-key"
primary_font_family = "serif"

[compress]
ghostscript_path = "/usr/bin/gs"
quality = "screen"

[mineru]
api_token = "mineru-token"

[postprocess]
fix_format = false
download_images = false
"""
        config_path = temp_dir / "full.toml"
        config_path.write_text(config_content, encoding='utf-8')

        config = Config.load(config_path)

        # Verify all loaded values
        assert config.output_dir == "/custom/output"
        assert config.verbose == True
        assert config.umiocr.enabled == False
        assert config.umiocr.url == "http://192.168.1.1:1224"
        assert config.umiocr.language == "models/config_chinese.txt"
        assert config.umiocr.exe_path == "E:/Umi-OCR/Umi-OCR.exe"
        assert config.umiocr.engine == "paddle"
        assert config.babeldoc.path == "/path/to/babeldoc"
        assert config.babeldoc.lang_in == "ja-JP"
        assert config.babeldoc.openai_model == "gpt-4"
        assert config.babeldoc.primary_font_family == "serif"
        assert config.compress.ghostscript_path == "/usr/bin/gs"
        assert config.compress.quality == "screen"
        assert config.mineru.api_token == "mineru-token"
        assert config.postprocess.fix_format == False

    def test_config_empty_values_handled(self, temp_dir):
        """Test that empty string values are handled correctly."""
        config = Config()
        config.babeldoc.path = ""  # Empty string
        config.compress.ghostscript_path = ""  # Empty string
        config.umiocr.exe_path = ""  # Empty string

        config_path = temp_dir / "empty.toml"
        config.save(config_path)

        loaded = Config.load(config_path)

        # Empty strings should be converted to None or remain empty
        assert loaded.babeldoc.path == "" or loaded.babeldoc.path is None
        assert loaded.umiocr.exe_path == "" or loaded.umiocr.exe_path is None


# =============================================================================
# TestConfigValidation - Validation Tests
# =============================================================================

class TestConfigValidation:
    """Tests for configuration validation."""

    def test_config_quality_validation(self):
        """Test that any quality string is accepted (validation happens at runtime)."""
        config = CompressConfig(quality="invalid")
        # Config accepts any value, validation happens in compress.py
        assert config.quality == "invalid"

    def test_config_url_formats(self):
        """Test different URL formats."""
        config = UmiOcrConfig()

        # Test various valid URL formats
        valid_urls = [
            "http://localhost:1224",
            "http://127.0.0.1:1224",
            "http://192.168.1.100:8080",
            "https://ocr.example.com:443",
        ]

        for url in valid_urls:
            config.url = url
            assert config.url == url

    def test_config_api_key_formats(self):
        """Test various API key formats."""
        config = BabelDocConfig()

        keys = [
            "sk-simple-key",
            "sk-proj-xxxxxxxxxxxxx",
            "ghp_xxxxxxxxxxxxx",
            "",  # Empty is valid (not configured)
        ]

        for key in keys:
            config.openai_api_key = key
            assert config.openai_api_key == key

    def test_umiocr_engine_validation_rejects_unknown_engine(self):
        """Only checked-in UMI engine contracts may be selected."""
        with pytest.raises(ValueError, match="umiocr.engine"):
            UmiOcrConfig(engine="unsupported")
        with pytest.raises(ValueError, match="umiocr.engine"):
            normalize_umiocr_engine("rapid-plus")

    def test_rapid_language_mapping_translates_legacy_default(self):
        """Rapid uses API language names, not Paddle model paths."""
        assert resolve_umiocr_language("rapid", document_language="en") == "English"
        assert resolve_umiocr_language("rapid", document_language="zh") == "简体中文"
        assert (
            resolve_umiocr_language(
                "rapid", configured_language="models/config_en.txt"
            )
            == "English"
        )


class TestInteractiveConfig:
    """Tests for configuration-wizard runtime selection behavior."""

    def test_configure_interactive_preserves_external_babeldoc_checkout(
        self, monkeypatch
    ):
        config = Config()
        config.babeldoc.path = "C:/work/BabelDOC"
        responses = iter(
            [
                config.mineru.api_token,
                config.babeldoc.openai_api_key,
                "custom-model",
                config.babeldoc.openai_base_url,
                config.babeldoc.path,
                "auto",
                "",
                config.umiocr.engine,
                "",
            ]
        )
        saved = []

        monkeypatch.setattr(
            Config, "load", classmethod(lambda cls: config)
        )
        monkeypatch.setattr(
            Config, "save", lambda self: saved.append(self)
        )
        monkeypatch.setattr(
            "ocr_flow.config.click.prompt", lambda *_args, **_kwargs: next(responses)
        )

        Config.configure_interactive()

        assert saved == [config]
        assert config.babeldoc.openai_model == "custom-model"
        assert config.babeldoc.path == "C:/work/BabelDOC"


# =============================================================================
# TestConfigEnvironment - Environment-Specific Tests
# =============================================================================

class TestConfigEnvironment:
    """Tests for environment-specific behavior."""

    def test_config_home_windows(self, monkeypatch, temp_dir):
        """Test config path uses USERPROFILE on Windows."""
        if os.name != 'nt':
            pytest.skip("Windows-only test")

        monkeypatch.setenv('USERPROFILE', str(temp_dir))
        path = Config.get_config_path()

        assert str(temp_dir) in str(path)

    def test_config_home_unix(self, monkeypatch, temp_dir):
        """Test config path uses HOME on Unix."""
        if os.name == 'nt':
            pytest.skip("Unix-only test")

        monkeypatch.setenv('HOME', str(temp_dir))
        path = Config.get_config_path()

        assert str(temp_dir) in str(path)

    def test_config_missing_env_uses_fallback(self, monkeypatch):
        """Test fallback when environment variable is missing."""
        # Remove both possible env vars
        monkeypatch.delenv('USERPROFILE', raising=False)
        monkeypatch.delenv('HOME', raising=False)

        # Should not raise, uses fallback
        path = Config.get_config_path()
        assert path is not None
