#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Self-check module for OCR Flow dependencies."""

import subprocess
import shutil
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import requests

from .config import normalize_umiocr_engine, resolve_umiocr_language
from .runtime import resolve_babeldoc_runtime, runtime_readiness


def create_local_umi_session() -> requests.Session:
    """Create a session for local UMI OCR traffic that bypasses env proxies."""
    session = requests.Session()
    session.trust_env = False
    return session


def _selected_umi_ocr_language(config, expected_language: Optional[str]) -> Optional[str]:
    """Resolve the document API language expected from a configured service."""
    if expected_language:
        return expected_language
    umiocr = getattr(config, "umiocr", None)
    if umiocr is None:
        return None
    return resolve_umiocr_language(
        normalize_umiocr_engine(getattr(umiocr, "engine", "paddle")),
        configured_language=getattr(umiocr, "language", None),
    )


def _umi_ocr_option_values(options: Dict[str, Any], name: str) -> List[str]:
    """Extract selectable API values from a UMI OCR options response."""
    option = options.get(name)
    if not isinstance(option, dict):
        return []
    option_list = option.get("optionsList")
    if not isinstance(option_list, list):
        return []

    values: List[str] = []
    for item in option_list:
        value = item[0] if isinstance(item, (list, tuple)) and item else item
        if isinstance(value, str):
            values.append(value)
    return values


def validate_umi_ocr_options(
    options: Dict[str, Any],
    config=None,
    *,
    expected_language: Optional[str] = None,
) -> Tuple[bool, str]:
    """Confirm that the running document API accepts the selected language."""
    if not isinstance(options, dict):
        return False, "UMI OCR options response is not a JSON object"

    selected_language = _selected_umi_ocr_language(config, expected_language)
    if not selected_language:
        return True, "UMI OCR document options were returned"

    available = _umi_ocr_option_values(options, "ocr.language")
    engine = normalize_umiocr_engine(
        getattr(getattr(config, "umiocr", None), "engine", "paddle")
    )
    if not available:
        return (
            False,
            "UMI OCR document options do not expose selectable ocr.language values",
        )
    if selected_language not in available:
        listed = ", ".join(repr(value) for value in available)
        return (
            False,
            f"UMI OCR engine {engine!r} expects language {selected_language!r}, "
            f"but the running service exposes: {listed}",
        )
    return True, f"UMI OCR engine {engine!r} accepts {selected_language!r}"


def validate_umi_ocr_response(
    response,
    config=None,
    *,
    expected_language: Optional[str] = None,
) -> Tuple[bool, str]:
    """Decode and validate a successful /api/doc/get_options response."""
    try:
        options = response.json()
    except (AttributeError, ValueError) as error:
        return False, f"UMI OCR options response is not valid JSON: {error}"
    return validate_umi_ocr_options(
        options,
        config,
        expected_language=expected_language,
    )


def _candidate_umi_roots() -> List[Path]:
    """Return candidate roots that may contain a local UMI OCR copy."""
    module_dir = Path(__file__).resolve().parent
    project_root = module_dir.parent
    workspace_root = project_root.parent
    return [project_root, workspace_root]


def _iter_local_umi_dirs() -> List[Path]:
    """Return candidate local UMI OCR directories under known roots."""
    candidates: List[Path] = []
    for root in _candidate_umi_roots():
        if not root.exists():
            continue

        direct_exe = root / 'Umi-OCR.exe'
        if direct_exe.exists():
            candidates.append(root)

        for item in root.iterdir():
            if not item.is_dir():
                continue
            name = item.name.lower()
            if 'umi' in name and 'ocr' in name:
                candidates.append(item)

    # Preserve order while deduplicating
    unique: List[Path] = []
    seen = set()
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def resolve_umi_launch_command(umi_path: str) -> Tuple[List[str], Optional[str]]:
    """Resolve the best command and cwd for starting UMI OCR."""
    umi_exe = Path(umi_path)

    # Prefer the bundled runtime launcher when available. It avoids startup
    # issues we observed from direct Umi-OCR.exe launches on Windows.
    umi_data_dir = umi_exe.parent / 'UmiOCR-data'
    runtime_python = umi_data_dir / 'runtime' / 'python.exe'
    main_py = umi_data_dir / 'main.py'
    if runtime_python.exists() and main_py.exists():
        return [str(runtime_python), str(main_py.name)], str(umi_data_dir)

    return [str(umi_exe)], str(umi_exe.parent)


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

        session = create_local_umi_session()

        try:
            response = session.get(
                f"{url}/api/doc/get_options",
                timeout=5
            )
            if response.status_code == 200:
                ready, message = validate_umi_ocr_response(response, self.config)
                if ready:
                    return {'ok': True, 'message': f'Service running at {url}; {message}'}
                return {
                    'ok': False,
                    'message': f'Service running at {url}, but {message}',
                    'next_step': 'Check umiocr.engine and the running UMI OCR installation',
                }
            else:
                return {'ok': False, 'message': f'Service returned status {response.status_code}'}
        except requests.exceptions.ConnectionError:
            if auto_start:
                result = ensure_umi_ocr_service(self.config)
                if result['ok']:
                    result['started'] = result.get('started', False)
                    return result
                next_step = 'ocr-flow doctor --ocr --start-ocr'
                if 'UMI OCR not found' in result['message']:
                    next_step = 'Install UMI OCR from https://github.com/hiroi-sora/Umi-OCR/releases'
                return {
                    'ok': False,
                    'message': result['message'],
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
        """Check that the selected BabelDOC Runtime Profile is ready."""
        runtime = resolve_babeldoc_runtime(self.config)
        ready, message = runtime_readiness(runtime)
        if ready:
            return {'ok': True, 'message': message}

        next_step = 'ocr-flow runtime setup'
        if not runtime.managed:
            next_step = f'ocr-flow runtime setup --path {runtime.checkout}'
        return {
            'ok': False,
            'message': message,
            'next_step': next_step,
        }


def find_umi_ocr(config=None) -> Optional[str]:
    """Find UMI OCR executable.

    Returns:
        Path to UMI OCR executable or None if not found.
    """
    # An explicit engine/runtime selection must not be replaced by discovery.
    if config and getattr(config, 'umiocr', None) and config.umiocr.exe_path:
        exe_path = Path(config.umiocr.exe_path)
        if exe_path.exists():
            return config.umiocr.exe_path

    # Project-local copies are the first auto-discovery candidates.
    for item in _iter_local_umi_dirs():
        exe = item / 'Umi-OCR.exe'
        if exe.exists():
            return str(exe)

    # Common names
    names = ['Umi-OCR', 'Umi-OCR.exe', 'umi-ocr']

    # Check PATH
    for name in names:
        path = shutil.which(name)
        if path:
            return path

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


def start_umi_ocr(config=None) -> Dict[str, Any]:
    """Start UMI OCR service.

    Returns:
        Dict with 'started' bool and 'message' str
    """
    umi_path = find_umi_ocr(config)

    if not umi_path:
        return {
            'started': False,
            'message': 'UMI OCR not found. Download from https://github.com/hiroi-sora/Umi-OCR/releases'
        }

    try:
        command, cwd = resolve_umi_launch_command(umi_path)

        # Start UMI OCR in background
        if os.name == 'nt':
            # On Windows, use DETACHED_PROCESS to run in background
            subprocess.Popen(
                command,
                cwd=cwd,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                command,
                cwd=cwd,
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


def ensure_umi_ocr_service(
    config,
    timeout_seconds: int = 10,
    *,
    expected_language: Optional[str] = None,
) -> Dict[str, Any]:
    """Ensure the UMI OCR service is reachable, starting it if needed."""
    url = config.umiocr.url if config else "http://127.0.0.1:1224"
    session = create_local_umi_session()

    try:
        response = session.get(f"{url}/api/doc/get_options", timeout=5)
        if response.status_code == 200:
            ready, message = validate_umi_ocr_response(
                response,
                config,
                expected_language=expected_language,
            )
            if ready:
                return {
                    'ok': True,
                    'message': f'Service running at {url}; {message}',
                    'started': False,
                }
            return {
                'ok': False,
                'message': f'Service running at {url}, but {message}',
                'started': False,
            }
    except requests.exceptions.RequestException:
        pass

    start_result = start_umi_ocr(config)
    if not start_result['started']:
        message = start_result['message']
        if config and not getattr(config.umiocr, 'exe_path', None):
            message = f"{message}. Service not running and umiocr.exe_path is not configured."
        return {'ok': False, 'message': message, 'started': False}

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = session.get(f"{url}/api/doc/get_options", timeout=2)
            if response.status_code == 200:
                ready, message = validate_umi_ocr_response(
                    response,
                    config,
                    expected_language=expected_language,
                )
                if ready:
                    return {
                        'ok': True,
                        'message': f'Service started and running at {url}; {message}',
                        'started': True,
                    }
                return {
                    'ok': False,
                    'message': f'Service started at {url}, but {message}',
                    'started': True,
                }
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)

    exe_path = getattr(config.umiocr, 'exe_path', None) if config else None
    detail = f" from {exe_path}" if exe_path else ""
    return {
        'ok': False,
        'message': f'UMI OCR service did not become ready at {url} after starting{detail}',
        'started': False,
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
