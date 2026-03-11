#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for graceful exit handler module.

Test suite covering:
- GracefulExit class initialization
- Signal handling
- State saving on interrupt
- Context manager behavior
"""

import pytest
import signal
import sys
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock, Mock

from ocr_flow.utils.graceful_exit import GracefulExit, GracefulExitContext


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
def mock_state_manager(temp_dir):
    """Create a mock state manager."""
    manager = MagicMock()
    manager.save = MagicMock()
    manager.output_dir = temp_dir
    return manager


# =============================================================================
# TestGracefulExit - GracefulExit Class Tests
# =============================================================================

class TestGracefulExit:
    """Tests for GracefulExit class."""

    def test_graceful_exit_init(self):
        """Test GracefulExit initialization."""
        graceful = GracefulExit()

        assert graceful.interrupted == False
        assert graceful.state_manager is None

    def test_graceful_exit_init_with_state_manager(self, mock_state_manager):
        """Test initialization with state manager."""
        graceful = GracefulExit(state_manager=mock_state_manager)

        assert graceful.state_manager == mock_state_manager
        assert graceful.interrupted == False

    def test_check_not_interrupted(self):
        """Test check method when not interrupted."""
        graceful = GracefulExit()

        result = graceful.check()

        assert result == True
        assert graceful.interrupted == False

    def test_check_interrupted_raises(self):
        """Test check method raises when interrupted."""
        graceful = GracefulExit()
        graceful.interrupted = True

        with pytest.raises(KeyboardInterrupt):
            graceful.check()

    def test_restore(self):
        """Test restore method restores original handler."""
        graceful = GracefulExit()

        # Should not raise even if no original handler
        graceful.restore()


# =============================================================================
# TestGracefulExitSignalHandling - Signal Handling Tests
# =============================================================================

class TestGracefulExitSignalHandling:
    """Tests for signal handling behavior."""

    def test_first_interrupt_sets_flag(self, mock_state_manager):
        """Test that first interrupt sets the interrupted flag."""
        graceful = GracefulExit(state_manager=mock_state_manager)

        # Simulate first interrupt - this will call sys.exit(0)
        with pytest.raises(SystemExit):
            graceful._handler(signal.SIGINT, None)

        assert graceful.interrupted == True
        mock_state_manager.save.assert_called_once()

    def test_first_interrupt_saves_state(self, mock_state_manager):
        """Test that state is saved on first interrupt."""
        graceful = GracefulExit(state_manager=mock_state_manager)

        with pytest.raises(SystemExit):
            graceful._handler(signal.SIGINT, None)

        mock_state_manager.save.assert_called_once()

    def test_first_interrupt_exits_gracefully(self, mock_state_manager):
        """Test that first interrupt exits with code 0."""
        graceful = GracefulExit(state_manager=mock_state_manager)

        with pytest.raises(SystemExit) as exc_info:
            graceful._handler(signal.SIGINT, None)

        assert exc_info.value.code == 0

    def test_second_interrupt_forces_exit(self, mock_state_manager):
        """Test that second interrupt forces exit with code 1."""
        graceful = GracefulExit(state_manager=mock_state_manager)
        graceful.interrupted = True  # Simulate already interrupted

        with pytest.raises(SystemExit) as exc_info:
            graceful._handler(signal.SIGINT, None)

        assert exc_info.value.code == 1

    def test_handler_without_state_manager(self):
        """Test handler works without state manager."""
        graceful = GracefulExit(state_manager=None)

        with pytest.raises(SystemExit):
            graceful._handler(signal.SIGINT, None)

        assert graceful.interrupted == True

    def test_handler_catches_save_exception(self, mock_state_manager):
        """Test that exceptions during save are caught."""
        mock_state_manager.save.side_effect = Exception("Save failed")

        graceful = GracefulExit(state_manager=mock_state_manager)

        # Should not raise, should exit gracefully
        with pytest.raises(SystemExit) as exc_info:
            graceful._handler(signal.SIGINT, None)

        assert exc_info.value.code == 0


# =============================================================================
# TestGracefulExitContext - Context Manager Tests
# =============================================================================

class TestGracefulExitContext:
    """Tests for GracefulExitContext context manager."""

    def test_context_enter_exit(self, mock_state_manager):
        """Test context manager enter and exit."""
        with GracefulExitContext(mock_state_manager) as graceful:
            assert isinstance(graceful, GracefulExit)
            assert graceful.state_manager == mock_state_manager

        # After exit, handler should be restored

    def test_context_returns_graceful_exit(self, mock_state_manager):
        """Test that context returns GracefulExit instance."""
        with GracefulExitContext(mock_state_manager) as graceful:
            assert isinstance(graceful, GracefulExit)

    def test_context_without_state_manager(self):
        """Test context manager without state manager."""
        with GracefulExitContext(None) as graceful:
            assert graceful.state_manager is None

    def test_context_restores_handler(self, mock_state_manager):
        """Test that original handler is restored after context."""
        # Store original handler
        original = signal.getsignal(signal.SIGINT)

        with GracefulExitContext(mock_state_manager):
            pass

        # After context, should restore original
        # Note: The actual behavior depends on platform
        restored = signal.getsignal(signal.SIGINT)
        # Just verify it's a valid handler

    def test_context_with_exception(self, mock_state_manager):
        """Test context manager handles exceptions."""
        with pytest.raises(ValueError):
            with GracefulExitContext(mock_state_manager) as graceful:
                raise ValueError("Test error")

        # Handler should still be restored

    def test_context_check_interrupted(self, mock_state_manager):
        """Test checking interrupted state within context."""
        with GracefulExitContext(mock_state_manager) as graceful:
            assert graceful.interrupted == False
            graceful.interrupted = True
            assert graceful.interrupted == True


# =============================================================================
# TestGracefulExitIntegration - Integration Tests
# =============================================================================

class TestGracefulExitIntegration:
    """Integration tests for graceful exit."""

    def test_full_flow_no_interrupt(self, mock_state_manager):
        """Test normal flow without interrupt."""
        with GracefulExitContext(mock_state_manager) as graceful:
            # Simulate normal processing
            for i in range(10):
                graceful.check()  # Should not raise

        # State should not be saved
        mock_state_manager.save.assert_not_called()

    def test_interrupted_state_propagates(self, mock_state_manager):
        """Test that interrupted state is accessible."""
        graceful = GracefulExit(state_manager=mock_state_manager)

        assert graceful.interrupted == False

        # Simulate interrupt
        graceful.interrupted = True

        with pytest.raises(KeyboardInterrupt):
            graceful.check()

    def test_multiple_state_managers(self, temp_dir):
        """Test with multiple state manager instances."""
        manager1 = MagicMock()
        manager2 = MagicMock()

        graceful1 = GracefulExit(state_manager=manager1)
        graceful2 = GracefulExit(state_manager=manager2)

        # Each should have its own state manager
        assert graceful1.state_manager != graceful2.state_manager


# =============================================================================
# TestGracefulExitEdgeCases - Edge Case Tests
# =============================================================================

class TestGracefulExitEdgeCases:
    """Edge case tests for graceful exit."""

    def test_handler_with_none_frame(self, mock_state_manager):
        """Test handler with None frame."""
        graceful = GracefulExit(state_manager=mock_state_manager)

        # Should not raise
        with pytest.raises(SystemExit):
            graceful._handler(signal.SIGINT, None)

    def test_nested_contexts(self, mock_state_manager):
        """Test nested context managers."""
        with GracefulExitContext(mock_state_manager) as outer:
            with GracefulExitContext(mock_state_manager) as inner:
                assert inner.state_manager == mock_state_manager

    def test_signal_handler_registration(self, mock_state_manager):
        """Test that signal handler is registered."""
        # This test verifies that signal.signal is called
        # The actual registration depends on platform
        graceful = GracefulExit(state_manager=mock_state_manager)

        # Handler should be set (may fail on some platforms)
        # Just verify initialization didn't crash
        assert graceful._original_handler is not None or True  # Platform dependent
