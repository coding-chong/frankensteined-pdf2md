#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Configuration management for OCR Flow."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import click

# Try to import tomli (Python 3.11+ has tomllib built-in)
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# Try to import tomli-w for writing
try:
    import tomli_w
except ImportError:
    tomli_w = None


@dataclass
class UmiOcrConfig:
    """UMI OCR configuration."""
    enabled: bool = True
    url: str = "http://127.0.0.1:1224"
    language: str = "models/config_en.txt"  # Default: English


@dataclass
class BabelDocConfig:
    """BabelDOC configuration."""
    path: Optional[str] = None  # Path to BabelDOC git repo
    lang_in: str = "en-US"
    lang_out: str = "zh-CN"
    openai: bool = True
    openai_model: str = "qwen3.5-flash"
    openai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    openai_api_key: str = ""


@dataclass
class CompressConfig:
    """PDF compression configuration."""
    ghostscript_path: Optional[str] = None  # Auto-detect if None
    quality: str = "ebook"  # screen/ebook/printer/prepress


@dataclass
class MinerUConfig:
    """MinerU API configuration."""
    api_token: str = ""


@dataclass
class PostProcessConfig:
    """Post-processing configuration."""
    fix_format: bool = True
    download_images: bool = True


@dataclass
class Config:
    """Main configuration for OCR Flow."""
    output_dir: str = "./output"
    verbose: bool = False
    umiocr: UmiOcrConfig = field(default_factory=UmiOcrConfig)
    babeldoc: BabelDocConfig = field(default_factory=BabelDocConfig)
    compress: CompressConfig = field(default_factory=CompressConfig)
    mineru: MinerUConfig = field(default_factory=MinerUConfig)
    postprocess: PostProcessConfig = field(default_factory=PostProcessConfig)

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the default config file path."""
        if os.name == 'nt':
            # Windows
            base = Path(os.environ.get('USERPROFILE', '~'))
        else:
            # Unix-like
            base = Path.home()
        return base / '.ocr-flow' / 'config.toml'

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> 'Config':
        """Load configuration from file.

        If config file doesn't exist, returns default config.
        """
        if config_path is None:
            config_path = cls.get_config_path()

        if not config_path.exists():
            return cls()

        if tomllib is None:
            click.echo("Warning: tomli not installed, using default config")
            return cls()

        with open(config_path, 'rb') as f:
            data = tomllib.load(f)

        # Parse config
        config = cls()

        # General
        if 'general' in data:
            config.output_dir = data['general'].get('output_dir', config.output_dir)
            config.verbose = data['general'].get('verbose', config.verbose)

        # UMI OCR
        if 'umiocr' in data:
            umi = data['umiocr']
            config.umiocr.enabled = umi.get('enabled', config.umiocr.enabled)
            config.umiocr.url = umi.get('url', config.umiocr.url)
            config.umiocr.language = umi.get('language', config.umiocr.language)

        # BabelDOC
        if 'babeldoc' in data:
            babel = data['babeldoc']
            # Convert empty strings to None for path
            path_val = babel.get('path', config.babeldoc.path)
            config.babeldoc.path = path_val if path_val else None
            config.babeldoc.lang_in = babel.get('lang_in', config.babeldoc.lang_in)
            config.babeldoc.lang_out = babel.get('lang_out', config.babeldoc.lang_out)
            config.babeldoc.openai = babel.get('openai', config.babeldoc.openai)
            config.babeldoc.openai_model = babel.get('openai_model', config.babeldoc.openai_model)
            config.babeldoc.openai_base_url = babel.get('openai_base_url', config.babeldoc.openai_base_url)
            config.babeldoc.openai_api_key = babel.get('openai_api_key', config.babeldoc.openai_api_key)

        # Compress
        if 'compress' in data:
            comp = data['compress']
            # Convert empty strings to None for ghostscript_path
            gs_path_val = comp.get('ghostscript_path', config.compress.ghostscript_path)
            config.compress.ghostscript_path = gs_path_val if gs_path_val else None
            config.compress.quality = comp.get('quality', config.compress.quality)

        # MinerU
        if 'mineru' in data:
            mineru = data['mineru']
            config.mineru.api_token = mineru.get('api_token', config.mineru.api_token)

        # PostProcess
        if 'postprocess' in data:
            post = data['postprocess']
            config.postprocess.fix_format = post.get('fix_format', config.postprocess.fix_format)
            config.postprocess.download_images = post.get('download_images', config.postprocess.download_images)

        return config

    def save(self, config_path: Optional[Path] = None):
        """Save configuration to file."""
        if config_path is None:
            config_path = self.get_config_path()

        if tomli_w is None:
            raise RuntimeError("tomli-w not installed, cannot save config")

        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'general': {
                'output_dir': self.output_dir,
                'verbose': self.verbose,
            },
            'umiocr': {
                'enabled': self.umiocr.enabled,
                'url': self.umiocr.url,
                'language': self.umiocr.language,
            },
            'babeldoc': {
                'path': self.babeldoc.path or '',
                'lang_in': self.babeldoc.lang_in,
                'lang_out': self.babeldoc.lang_out,
                'openai': self.babeldoc.openai,
                'openai_model': self.babeldoc.openai_model,
                'openai_base_url': self.babeldoc.openai_base_url,
                'openai_api_key': self.babeldoc.openai_api_key,
            },
            'compress': {
                'ghostscript_path': self.compress.ghostscript_path or '',
                'quality': self.compress.quality,
            },
            'mineru': {
                'api_token': self.mineru.api_token,
            },
            'postprocess': {
                'fix_format': self.postprocess.fix_format,
                'download_images': self.postprocess.download_images,
            },
        }

        with open(config_path, 'wb') as f:
            tomli_w.dump(data, f)

    @classmethod
    def configure_interactive(cls):
        """Interactive configuration wizard."""
        click.echo("\n=== OCR Flow Configuration Wizard ===\n")

        config = cls.load()

        # MinerU API Token
        current = config.mineru.api_token
        if current:
            masked = current[:10] + "..." if len(current) > 10 else "***"
            click.echo(f"Current MinerU API Token: {masked}")
        token = click.prompt("MinerU API Token", default=current, show_default=False)
        config.mineru.api_token = token

        # OpenAI API Key
        current = config.babeldoc.openai_api_key
        if current:
            masked = current[:10] + "..." if len(current) > 10 else "***"
            click.echo(f"Current OpenAI API Key: {masked}")
        key = click.prompt("OpenAI API Key (for BabelDOC translation)", default=current, show_default=False)
        config.babeldoc.openai_api_key = key

        # OpenAI Base URL
        click.echo(f"Current OpenAI Base URL: {config.babeldoc.openai_base_url}")
        base_url = click.prompt("OpenAI Base URL", default=config.babeldoc.openai_base_url)
        config.babeldoc.openai_base_url = base_url

        # BabelDOC path
        click.echo(f"Current BabelDOC path: {config.babeldoc.path or '(use global install)'}")
        path = click.prompt("BabelDOC path (leave empty for global install)", default=config.babeldoc.path or "")
        config.babeldoc.path = path if path else None

        # Ghostscript path
        click.echo(f"Current Ghostscript path: {config.compress.ghostscript_path or '(auto-detect)'}")
        gs_path = click.prompt("Ghostscript path (leave empty for auto-detect)", default=config.compress.ghostscript_path or "")
        config.compress.ghostscript_path = gs_path if gs_path else None

        # Save
        config.save()
        click.echo(f"\nConfiguration saved to: {cls.get_config_path()}")
