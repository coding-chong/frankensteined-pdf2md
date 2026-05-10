#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Self-check module for OCR Flow dependencies."""

import subprocess
import shutil
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

import requests


class SelfCheck:
    """Check system dependencies and configuration."""

    def __init__(self, config=None):
        self.config = config

    def check_all(self, needs_ocr: bool = False, needs_translate: bool = False) -> Dict[str, Dict[str, Any]]:
        """Run all checks.

        Args:
            needs_ocr: Whether OCR will be needed
            needs_translate: Whether translation will be needed

        Returns:
            Dict of check name -> {ok: bool, message: str}
        """
        results = {}

        # Always check these
        results['ghostscript'] = self.check_ghostscript()
        results['mineru_api'] = self.check_mineru_api()

        # Conditional checks
        if needs_ocr:
            results['umi_ocr'] = self.check_umi_ocr()

        if needs_translate:
            results['babeldoc'] = self.check_babeldoc()

        return results

    def check_ghostscript(self) -> Dict[str, Any]:
        """Check if Ghostscript is installed."""
        gs_path = find_ghostscript(self.config)
        if gs_path:
            try:
                result = subprocess.run(
                    [gs_path, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    return {'ok': True, 'message': f'Found (version {version}) at {gs_path}'}
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
                return {
                    'ok': False,
                    'message': f'Found at {gs_path} but failed to run: {e}'
                }

        return {
            'ok': False,
            'message': 'Not found. Install from https://ghostscript.com/',
            'next_step': 'Install Ghostscript from https://ghostscript.com/',
        }

    def check_mineru_api(self) -> Dict[str, Any]:
        """Check if MinerU API token is configured."""
        if not self.config or not self.config.mineru.api_token:
            return {
                'ok': False,
                'message': 'API token not configured',
                'next_step': 'ocr-flow config',
            }

        # Only check if token exists, don't call API
        # The actual API call will happen during processing
        token = self.config.mineru.api_token
        if token and token != 'your-mineru-api-token-here':
            return {'ok': True, 'message': f'API token configured ({token[:10]}...)'}

        return {
            'ok': False,
            'message': 'API token not configured',
            'next_step': 'ocr-flow config',
        }

    def check_umi_ocr(self, auto_start: bool = False) -> Dict[str, Any]:
        """Check if UMI OCR service is running.

        Args:
            auto_start: If True and service is not running, try to start it

        Returns:
            Dict with ok, message, and optionally started (if auto-started)
        """
        url = self.config.umiocr.url if self.config else "http://127.0.0.1:1224"

        try:
            response = requests.get(
                f"{url}/api/doc/get_options",
                timeout=5
            )
            if response.status_code == 200:
                return {'ok': True, 'message': f'Service running at {url}'}
            else:
                return {'ok': False, 'message': f'Service returned status {response.status_code}'}
        except requests.exceptions.ConnectionError:
            # Service not running, try to start if auto_start is True
            if auto_start:
                result = start_umi_ocr()
                if result['started']:
                    # Wait for service to be ready
                    for _ in range(10):
                        time.sleep(1)
                        try:
                            r = requests.get(f"{url}/api/doc/get_options", timeout=2)
                            if r.status_code == 200:
                                return {
                                    'ok': True,
                                    'message': f'Service started and running at {url}',
                                    'started': True
                                }
                        except:
                            pass
                    return {
                        'ok': False,
                        'message': f'Service started but not responding at {url}',
                        'next_step': 'ocr-flow doctor --ocr --start-ocr',
                    }
                else:
                    next_step = 'ocr-flow doctor --ocr --start-ocr'
                    if 'UMI OCR not found' in result['message']:
                        next_step = 'Install UMI OCR from https://github.com/hiroi-sora/Umi-OCR/releases'
                    return {
                        'ok': False,
                        'message': f"Service not running. {result['message']}",
                        'next_step': next_step,
                    }
            return {
                'ok': False,
                'message': f'Service not running at {url}. Start UMI OCR application.',
                'next_step': 'ocr-flow doctor --ocr --start-ocr',
            }
        except requests.exceptions.RequestException as e:
            return {'ok': False, 'message': f'Check failed: {e}'}

    def check_babeldoc(self) -> Dict[str, Any]:
        """Check if BabelDOC is available."""
        if self.config and self.config.babeldoc.path:
            # Check path exists
            babel_path = Path(self.config.babeldoc.path)
            if babel_path.exists():
                return {'ok': True, 'message': f'Found at {babel_path}'}
            else:
                return {
                    'ok': False,
                    'message': f'Path not found: {babel_path}',
                    'next_step': 'ocr-flow config',
                }

        # Check global install
        try:
            result = subprocess.run(
                ['babeldoc', '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return {'ok': True, 'message': 'Globally installed'}
        except FileNotFoundError:
            pass
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            pass  # Other subprocess errors, babeldoc check failed

        return {
            'ok': False,
            'message': 'Not found. Install with: pip install BabelDOC or clone and use path config',
            'next_step': 'ocr-flow config',
        }


def find_umi_ocr() -> Optional[str]:
    """Find UMI OCR executable.

    Returns:
        Path to UMI OCR executable or None if not found.
    """
    # Common names
    names = ['Umi-OCR', 'Umi-OCR.exe', 'umi-ocr']

    # Check PATH
    for name in names:
        path = shutil.which(name)
        if path:
            return path

    # Check project-local umiocr directory (relative to this file)
    project_root = Path(__file__).parent.parent.parent  # Go up to project root
    local_umiocr_dir = project_root / 'umiocr'
    if local_umiocr_dir.exists():
        # Search for UMI OCR installations in local directory
        for item in local_umiocr_dir.iterdir():
            if item.is_dir() and 'umi' in item.name.lower():
                exe = item / 'Umi-OCR.exe'
                if exe.exists():
                    return str(exe)

    # Check common install locations on Windows
    if os.name == 'nt':
        common_paths = [
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs',
            Path(os.environ.get('PROGRAMFILES', '')),
            Path(os.environ.get('PROGRAMFILES(X86)', '')),
            Path('D:/Program Files'),
            Path('E:/Program Files'),
            Path('C:/Program Files'),
            Path('C:/Program Files (x86)'),
        ]

        for base in common_paths:
            if not base.exists():
                continue
            # Check for Umi-OCR directory
            for item in base.iterdir():
                if item.is_dir() and 'umi' in item.name.lower() and 'ocr' in item.name.lower():
                    exe = item / 'Umi-OCR.exe'
                    if exe.exists():
                        return str(exe)

        # Also check user-specific locations
        user_paths = [
            Path.home() / 'AppData/Local/Programs',
            Path.home() / 'Desktop',
        ]
        for base in user_paths:
            if not base.exists():
                continue
            for item in base.iterdir():
                if item.is_dir() and 'umi' in item.name.lower():
                    exe = item / 'Umi-OCR.exe'
                    if exe.exists():
                        return str(exe)

    return None


def start_umi_ocr() -> Dict[str, Any]:
    """Start UMI OCR service.

    Returns:
        Dict with 'started' bool and 'message' str
    """
    umi_path = find_umi_ocr()

    if not umi_path:
        return {
            'started': False,
            'message': 'UMI OCR not found. Download from https://github.com/hiroi-sora/Umi-OCR/releases'
        }

    try:
        # Start UMI OCR in background
        if os.name == 'nt':
            # On Windows, use DETACHED_PROCESS to run in background
            subprocess.Popen(
                [umi_path],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                [umi_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

        return {
            'started': True,
            'message': f'Started UMI OCR from {umi_path}'
        }
    except Exception as e:
        return {
            'started': False,
            'message': f'Failed to start UMI OCR: {e}'
        }


def find_ghostscript(config=None) -> str:
    """Find Ghostscript executable.

    Args:
        config: Config object with ghostscript_path setting

    Returns:
        Path to Ghostscript executable or None if not found.
    """
    # Check config path first
    if config and config.compress.ghostscript_path:
        gs_path = config.compress.ghostscript_path
        if Path(gs_path).exists():
            return gs_path

    # Common names
    names = ['gswin64c', 'gswin32c', 'gs', 'gswin64', 'gswin32']

    for name in names:
        path = shutil.which(name)
        if path:
            return path

    # Check common install locations on Windows
    if shutil.os.name == 'nt':
        common_paths = [
            Path('C:/Program Files/gs'),
            Path('C:/Program Files (x86)/gs'),
            Path('D:/Program Files/gs'),
            Path('E:/Program Files/gs'),
            Path('E:/gs-portable'),
        ]

        for base in common_paths:
            if base.exists():
                # Find the latest version
                versions = sorted(base.iterdir(), reverse=True)
                for version_dir in versions:
                    bin_dir = version_dir / 'bin'
                    if bin_dir.exists():
                        for name in ['gswin64c.exe', 'gswin32c.exe']:
                            exe = bin_dir / name
                            if exe.exists():
                                return str(exe)

    return None
