#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Graceful exit handler for OCR Flow - handles Ctrl+C signal."""

import signal
import sys
from typing import Optional


class GracefulExit:
    """Handle Ctrl+C gracefully, saving state before exit.

    Usage:
        graceful = GracefulExit(state_manager)
        # ... processing ...
        if graceful.interrupted:
            # cleanup
    """

    def __init__(self, state_manager=None):
        """Initialize the graceful exit handler.

        Args:
            state_manager: StateManager instance to save state on interrupt
        """
        self.state_manager = state_manager
        self.interrupted = False
        self._original_handler = None

        # Register signal handler
        try:
            self._original_handler = signal.signal(signal.SIGINT, self._handler)
        except (ValueError, OSError):
            # SIGINT might not be available on some platforms
            pass

    def _handler(self, signum, frame):
        """Handle SIGINT signal (Ctrl+C)."""
        if self.interrupted:
            # Second Ctrl+C, force exit
            print("\n强制退出...")
            sys.exit(1)

        self.interrupted = True
        print("\n\n正在保存进度，请稍候...")

        if self.state_manager:
            try:
                self.state_manager.save()
                print("✅ 进度已保存，下次运行可继续")
            except Exception as e:
                print(f"保存进度失败: {e}")

        sys.exit(0)

    def check(self) -> bool:
        """Check if interrupted, raise KeyboardInterrupt if so.

        Returns:
            True if not interrupted (continue processing)

        Raises:
            KeyboardInterrupt: If interrupted
        """
        if self.interrupted:
            raise KeyboardInterrupt()
        return True

    def restore(self):
        """Restore original signal handler."""
        if self._original_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._original_handler)
            except (ValueError, OSError):
                pass


class GracefulExitContext:
    """Context manager for graceful exit handling.

    Usage:
        with GracefulExitContext(state_manager) as graceful:
            # ... processing ...
            if graceful.interrupted:
                break
    """

    def __init__(self, state_manager=None):
        self.state_manager = state_manager
        self.graceful: Optional[GracefulExit] = None

    def __enter__(self) -> GracefulExit:
        self.graceful = GracefulExit(self.state_manager)
        return self.graceful

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.graceful:
            self.graceful.restore()
        return False  # Don't suppress exceptions
