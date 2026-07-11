#!/usr/bin/env python
"""Backward-compatible entry point for BabelDOC Runtime Profile management."""

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


_runtime_module = importlib.import_module("ocr_flow.babeldoc_runtime")


def __getattr__(name):
    """Expose the historical script module API without duplicate imports."""
    return getattr(_runtime_module, name)


def main():
    """Run the package implementation from the legacy script entry point."""
    return _runtime_module.main()


if __name__ == "__main__":
    raise SystemExit(main())
