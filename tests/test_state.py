#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for state management module."""

import pytest
from pathlib import Path
import tempfile
import shutil
import json

from ocr_flow.state import State, StateManager, StepStatus


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def test_pdf(temp_dir):
    """Create a test PDF file."""
    pdf_path = temp_dir / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test content\n%%EOF")
    return pdf_path


class TestStepStatus:
    """Tests for StepStatus class."""

    def test_step_status_creation(self):
        """Test creating a step status."""
        status = StepStatus()

        assert status.status == "pending"
        assert status.output is None
        assert status.files == []

    def test_step_status_with_values(self):
        """Test creating step status with values."""
        status = StepStatus(
            status="completed",
            output="result.pdf",
            files=["part1.pdf", "part2.pdf"],
        )

        assert status.status == "completed"
        assert status.output == "result.pdf"
        assert len(status.files) == 2


class TestState:
    """Tests for State class."""

    def test_state_creation(self, test_pdf):
        """Test creating a state object."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        assert state.source_path == str(test_pdf)
        assert state.source_size > 0
        assert len(state.source_sha256) == 64  # SHA256 hex digest
        assert state.options == {"pdf_type": "text"}

    def test_state_update_step(self, test_pdf):
        """Test updating a step in state."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step("ocr", status="completed", output="ocr_result.pdf")

        assert "ocr" in state.steps
        assert state.steps["ocr"].status == "completed"
        assert state.steps["ocr"].output == "ocr_result.pdf"

    def test_state_save_and_load(self, test_pdf, temp_dir):
        """Test saving and loading state."""
        state = State.create(test_pdf, {"pdf_type": "text"})
        state.update_step("split", status="completed")

        state_path = temp_dir / ".state.json"
        state.save(state_path)

        loaded = State.load(state_path)

        assert loaded.source_path == str(test_pdf)
        assert "split" in loaded.steps
        assert loaded.steps["split"].status == "completed"

    def test_state_is_completed(self, test_pdf):
        """Test checking if all steps are completed."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        # Empty steps means no pending work, so it's considered completed
        # Mark a step as running to test the "not completed" case
        state.update_step("split", status="running")
        assert not state.is_completed()

        # Mark all steps as completed or skipped
        state.update_step("ocr", status="skipped")
        state.update_step("translate", status="skipped")
        state.update_step("split", status="completed")
        state.update_step("compress", status="completed")
        state.update_step("mineru", status="completed")
        state.update_step("format_fix", status="completed")
        state.update_step("image_download", status="completed")

        assert state.is_completed()

    def test_state_get_pending_steps(self, test_pdf):
        """Test getting pending steps."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        # All steps pending initially
        pending = state.get_pending_steps()
        assert len(pending) == 7  # All 7 steps

        # Mark some as completed
        state.update_step("ocr", status="skipped")
        state.update_step("split", status="completed")

        pending = state.get_pending_steps()
        assert "ocr" not in pending
        assert "split" not in pending


class TestStateManager:
    """Tests for StateManager class."""

    def test_state_manager_creates_state_file(self, temp_dir, test_pdf):
        """Test that StateManager creates state file."""
        manager = StateManager(temp_dir)
        state = manager.load_or_create(test_pdf, {"pdf_type": "text"})

        state_file = temp_dir / ".state.json"
        assert state_file.exists()

    def test_state_manager_saves_state(self, temp_dir, test_pdf):
        """Test that StateManager saves state."""
        manager = StateManager(temp_dir)
        state = manager.load_or_create(test_pdf, {"pdf_type": "text"})

        state.update_step("split", status="completed")
        manager.save()

        state_file = temp_dir / ".state.json"
        content = json.loads(state_file.read_text(encoding='utf-8'))

        assert "split" in content["steps"]

    def test_state_manager_loads_existing_state(self, temp_dir, test_pdf):
        """Test that StateManager loads existing state."""
        # Create initial state
        manager1 = StateManager(temp_dir)
        state1 = manager1.load_or_create(test_pdf, {"pdf_type": "text"})
        state1.update_step("ocr", status="skipped")
        manager1.save()

        # Load existing state
        manager2 = StateManager(temp_dir)
        state2 = manager2.load_or_create(test_pdf, {"pdf_type": "text"})

        assert "ocr" in state2.steps
        assert state2.steps["ocr"].status == "skipped"

    def test_state_manager_backup_file(self, temp_dir):
        """Test that StateManager can backup files."""
        manager = StateManager(temp_dir)

        # Create a test file
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content", encoding='utf-8')

        manager.backup_file("test_step", test_file)

        backup_dir = temp_dir / ".backup" / "test_step"
        assert backup_dir.exists()
        assert (backup_dir / "test.txt").exists()

    def test_state_manager_restore_from_backup(self, temp_dir):
        """Test restoring files from backup."""
        manager = StateManager(temp_dir)

        # Create and backup a file
        test_file = temp_dir / "test.txt"
        test_file.write_text("original content", encoding='utf-8')
        manager.backup_file("test_step", test_file)

        # Modify the original
        test_file.write_text("modified content", encoding='utf-8')

        # Restore
        dest = temp_dir / "restored.txt"
        success = manager.restore_from_backup("test_step", "test.txt", dest)

        assert success
        assert dest.read_text(encoding='utf-8') == "original content"
