#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Self-check module for OCR Flow dependencies."""

import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any

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
        gs_path = find_ghostscript()
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
            except Exception as e:
                pass

        return {
            'ok': False,
            'message': 'Not found. Install from https://ghostscript.com/'
        }

    def check_mineru_api(self) -> Dict[str, Any]:
        """Check if MinerU API token is configured."""
        if not self.config or not self.config.mineru.api_token:
            return {'ok': False, 'message': 'API token not configured'}

        # Only check if token exists, don't call API
        # The actual API call will happen during processing
        token = self.config.mineru.api_token
        if token and token != 'your-mineru-api-token-here':
            return {'ok': True, 'message': f'API token configured ({token[:10]}...)'}

        return {'ok': False, 'message': 'API token not configured'}

    def check_umi_ocr(self) -> Dict[str, Any]:
        """Check if UMI OCR service is running."""
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
            return {'ok': False, 'message': f'Service not running at {url}. Start UMI OCR application.'}
        except Exception as e:
            return {'ok': False, 'message': f'Check failed: {e}'}

    def check_babeldoc(self) -> Dict[str, Any]:
        """Check if BabelDOC is available."""
        if self.config and self.config.babeldoc.path:
            # Check path exists
            babel_path = Path(self.config.babeldoc.path)
            if babel_path.exists():
                return {'ok': True, 'message': f'Found at {babel_path}'}
            else:
                return {'ok': False, 'message': f'Path not found: {babel_path}'}

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
        except Exception:
            pass

        return {
            'ok': False,
            'message': 'Not found. Install with: pip install BabelDOC or clone and use path config'
        }


def find_ghostscript() -> str:
    """Find Ghostscript executable.

    Returns:
        Path to Ghostscript executable or None if not found.
    """
    # Check config path first
    # (This would be set from config, for now just search)

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
