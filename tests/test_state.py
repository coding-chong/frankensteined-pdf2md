#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for state management module.

Extended test suite covering:
- State creation and initialization
- Step status management
- State persistence (save/load)
- StateManager operations
- Recovery scenarios
- Error handling
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import json
import hashlib
from datetime import datetime

from ocr_flow.state import State, StateManager, StepStatus


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
def test_pdf(temp_dir):
    """Create a test PDF file."""
    pdf_path = temp_dir / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test content\n%%EOF")
    return pdf_path


@pytest.fixture
def large_test_pdf(temp_dir):
    """Create a larger test PDF file for size testing."""
    pdf_path = temp_dir / "large_test.pdf"
    content = b"%PDF-1.4\n" + b"%" + b"x" * 10000 + b"\n%%EOF"
    pdf_path.write_bytes(content)
    return pdf_path


@pytest.fixture
def corrupted_state_file(temp_dir):
    """Create a corrupted state file."""
    state_path = temp_dir / ".state.json"
    state_path.write_text("{ invalid json content", encoding='utf-8')
    return state_path


# =============================================================================
# TestStepStatus - Step Status Tests
# =============================================================================

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

    def test_step_status_all_fields(self):
        """Test creating step status with all fields."""
        status = StepStatus(
            status="partial",
            output="result/",
            files=["file1.pdf", "file2.pdf"],
            completed=[1, 2, 3],
            failed={"4": "Error message"},
            error="Some error",
            retries=2,
        )

        assert status.status == "partial"
        assert status.completed == [1, 2, 3]
        assert status.failed == {"4": "Error message"}
        assert status.error == "Some error"
        assert status.retries == 2

    def test_step_status_default_values(self):
        """Test default values for optional fields."""
        status = StepStatus()

        assert status.completed == []
        assert status.failed == {}
        assert status.error is None
        assert status.retries == 0


# =============================================================================
# TestState - State Class Tests
# =============================================================================

class TestState:
    """Tests for State class."""

    def test_state_creation(self, test_pdf):
        """Test creating a state object."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        assert state.source_path == str(test_pdf)
        assert state.source_size > 0
        assert len(state.source_sha256) == 64  # SHA256 hex digest
        assert state.options == {"pdf_type": "text"}

    def test_state_sha256_verification(self, test_pdf):
        """Test SHA256 hash calculation correctness."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        # Verify the hash manually
        sha256 = hashlib.sha256()
        with open(test_pdf, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)

        assert state.source_sha256 == sha256.hexdigest()

    def test_state_sha256_different_files(self, test_pdf, large_test_pdf):
        """Test that different files have different hashes."""
        state1 = State.create(test_pdf, {"pdf_type": "text"})
        state2 = State.create(large_test_pdf, {"pdf_type": "text"})

        assert state1.source_sha256 != state2.source_sha256

    def test_state_update_step(self, test_pdf):
        """Test updating a step in state."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step("ocr", status="completed", output="ocr_result.pdf")

        assert "ocr" in state.steps
        assert state.steps["ocr"].status == "completed"
        assert state.steps["ocr"].output == "ocr_result.pdf"

    def test_state_update_step_with_files(self, test_pdf):
        """Test updating step with file list."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step("split", status="completed", files=["part1.pdf", "part2.pdf"])

        assert state.steps["split"].files == ["part1.pdf", "part2.pdf"]

    def test_state_update_step_partial(self, test_pdf):
        """Test updating step with partial completion."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step(
            "mineru",
            status="partial",
            completed=[1, 3, 5],
            failed={"2": "Network error", "4": "Timeout"}
        )

        assert state.steps["mineru"].status == "partial"
        assert state.steps["mineru"].completed == [1, 3, 5]
        assert state.steps["mineru"].failed == {"2": "Network error", "4": "Timeout"}

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

    def test_state_load_nonexistent_file(self, temp_dir):
        """Test loading from nonexistent file returns None."""
        state_path = temp_dir / "nonexistent.json"
        result = State.load(state_path)
        assert result is None

    def test_state_is_completed(self, test_pdf):
        """Test checking if all steps are completed."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        # Empty steps - initially considered not completed (no steps run yet)
        # Actually, is_completed checks if all existing steps are done
        # With no steps, it should return True
        assert state.is_completed()  # No steps to complete

        # Mark a step as running
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

    def test_state_is_completed_with_partial(self, test_pdf):
        """Test that partial steps are not considered complete."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step("ocr", status="skipped")
        state.update_step("split", status="completed")
        state.update_step("mineru", status="partial", completed=[1])

        assert not state.is_completed()

    def test_state_is_completed_with_failed(self, test_pdf):
        """Test that failed steps are not considered complete."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step("ocr", status="skipped")
        state.update_step("split", status="completed")
        state.update_step("mineru", status="failed", error="Network error")

        assert not state.is_completed()

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

    def test_state_get_pending_steps_with_failed(self, test_pdf):
        """Test that failed steps appear in pending."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step("ocr", status="skipped")
        state.update_step("split", status="completed")
        state.update_step("mineru", status="failed", error="Error")

        pending = state.get_pending_steps()
        assert "mineru" in pending

    def test_state_get_pending_steps_with_partial(self, test_pdf):
        """Test that partial steps appear in pending."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        state.update_step("ocr", status="skipped")
        state.update_step("split", status="completed")
        state.update_step("mineru", status="partial", completed=[1])

        pending = state.get_pending_steps()
        assert "mineru" in pending

    def test_state_timestamps(self, test_pdf):
        """Test that timestamps are set correctly."""
        state = State.create(test_pdf, {"pdf_type": "text"})

        assert state.created_at
        assert state.updated_at
        # Parse timestamps to verify format
        datetime.fromisoformat(state.created_at)
        datetime.fromisoformat(state.updated_at)

    def test_state_options_persistence(self, test_pdf, temp_dir):
        """Test that options persist through save/load."""
        options = {
            "pdf_type": "scanned",
            "language": "zh",
            "translate": True,
        }
        state = State.create(test_pdf, options)

        state_path = temp_dir / ".state.json"
        state.save(state_path)

        loaded = State.load(state_path)
        assert loaded.options == options

    def test_state_version(self, test_pdf):
        """Test that state version is set."""
        state = State.create(test_pdf, {"pdf_type": "text"})
        assert state.version == 1


# =============================================================================
# TestStateManager - StateManager Class Tests
# =============================================================================

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

    def test_state_manager_has_state(self, temp_dir, test_pdf):
        """Test has_state method."""
        manager = StateManager(temp_dir)

        assert not manager.has_state()

        manager.load_or_create(test_pdf, {"pdf_type": "text"})

        assert manager.has_state()

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

    def test_state_manager_restore_nonexistent_backup(self, temp_dir):
        """Test restoring from nonexistent backup."""
        manager = StateManager(temp_dir)

        dest = temp_dir / "restored.txt"
        success = manager.restore_from_backup("test_step", "nonexistent.txt", dest)

        assert not success

    def test_state_manager_get_backup_file(self, temp_dir):
        """Test getting backup file path."""
        manager = StateManager(temp_dir)

        # Create and backup a file
        test_file = temp_dir / "test.txt"
        test_file.write_text("content", encoding='utf-8')
        manager.backup_file("test_step", test_file)

        backup_path = manager.get_backup_file("test_step", "test.txt")
        assert backup_path is not None
        assert backup_path.exists()

    def test_state_manager_get_intermediate_file(self, temp_dir):
        """Test getting intermediate file."""
        manager = StateManager(temp_dir)

        # Create a file in work directory
        work_file = temp_dir / "work.txt"
        work_file.write_text("work content", encoding='utf-8')

        result = manager.get_intermediate_file("step", "work.txt", temp_dir)
        assert result == work_file

    def test_state_manager_get_intermediate_from_backup(self, temp_dir):
        """Test getting intermediate file from backup when work file missing."""
        manager = StateManager(temp_dir)

        # Create and backup a file
        test_file = temp_dir / "original.txt"
        test_file.write_text("content", encoding='utf-8')
        manager.backup_file("test_step", test_file)

        # Remove original
        test_file.unlink()

        # Should get from backup
        result = manager.get_intermediate_file("test_step", "original.txt", temp_dir)
        assert result is not None
        assert "backup" in str(result)


# =============================================================================
# TestStateManagerAdvanced - Advanced StateManager Tests
# =============================================================================

class TestStateManagerAdvanced:
    """Advanced tests for StateManager."""

    def test_state_manager_new_source_overwrites(self, temp_dir, test_pdf):
        """Test that new source file overwrites existing state."""
        manager = StateManager(temp_dir)

        # Create state for first PDF
        state1 = manager.load_or_create(test_pdf, {"pdf_type": "text"})
        state1.update_step("split", status="completed")
        manager.save()

        # Create a different PDF
        pdf2 = temp_dir / "test2.pdf"
        pdf2.write_bytes(b"%PDF-1.4\n%different\n%%EOF")

        # Load with different source should create new state
        state2 = manager.load_or_create(pdf2, {"pdf_type": "scanned"})

        # Source path should be updated
        assert state2.source_path == str(pdf2)

    def test_state_manager_corrupted_file(self, temp_dir, corrupted_state_file, test_pdf):
        """Test handling of corrupted state file."""
        # Copy corrupted file to state location
        state_path = temp_dir / ".state.json"
        state_path.write_text("{ invalid json", encoding='utf-8')

        manager = StateManager(temp_dir)

        # Should handle corrupted file gracefully by creating new state
        state = manager.load_or_create(test_pdf, {"pdf_type": "text"})
        assert state.source_path == str(test_pdf)

    def test_state_manager_multiple_backups(self, temp_dir):
        """Test multiple backups for different steps."""
        manager = StateManager(temp_dir)

        # Create test files
        file1 = temp_dir / "ocr_result.pdf"
        file2 = temp_dir / "translated.pdf"
        file3 = temp_dir / "compressed.pdf"

        for f in [file1, file2, file3]:
            f.write_text("content", encoding='utf-8')

        # Backup to different step directories
        manager.backup_file("ocr", file1)
        manager.backup_file("translate", file2)
        manager.backup_file("compress", file3)

        # Verify all backups exist
        assert (temp_dir / ".backup" / "ocr" / "ocr_result.pdf").exists()
        assert (temp_dir / ".backup" / "translate" / "translated.pdf").exists()
        assert (temp_dir / ".backup" / "compress" / "compressed.pdf").exists()

    def test_state_manager_overwrite_backup(self, temp_dir):
        """Test overwriting existing backup."""
        manager = StateManager(temp_dir)

        # Create and backup a file
        test_file = temp_dir / "test.txt"
        test_file.write_text("original", encoding='utf-8')
        manager.backup_file("step", test_file)

        # Modify and backup again
        test_file.write_text("modified", encoding='utf-8')
        manager.backup_file("step", test_file)

        # Should have the modified content
        backup = temp_dir / ".backup" / "step" / "test.txt"
        assert backup.read_text(encoding='utf-8') == "modified"


# =============================================================================
# TestStateSerialization - JSON Serialization Tests
# =============================================================================

class TestStateSerialization:
    """Tests for state serialization."""

    def test_state_json_structure(self, test_pdf, temp_dir):
        """Test the structure of saved JSON."""
        state = State.create(test_pdf, {"pdf_type": "text"})
        state.update_step("ocr", status="skipped")
        state.update_step("split", status="completed", files=["part1.pdf"])

        state_path = temp_dir / ".state.json"
        state.save(state_path)

        with open(state_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Check required fields
        assert "version" in data
        assert "source_path" in data
        assert "source_size" in data
        assert "source_sha256" in data
        assert "options" in data
        assert "steps" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_state_load_invalid_json(self, temp_dir, corrupted_state_file):
        """Test loading invalid JSON returns None."""
        result = State.load(corrupted_state_file)
        assert result is None

    def test_state_roundtrip_preserves_data(self, test_pdf, temp_dir):
        """Test that save/load preserves all data."""
        original = State.create(test_pdf, {
            "pdf_type": "scanned",
            "language": "zh",
            "translate": True,
        })
        original.update_step("ocr", status="completed", output="ocr.pdf")
        original.update_step("split", status="completed", files=["p1.pdf", "p2.pdf"])
        original.update_step("mineru", status="partial", completed=[1], failed={"2": "err"})
        original.total_pages = 5

        state_path = temp_dir / ".state.json"
        original.save(state_path)

        loaded = State.load(state_path)

        assert loaded.source_path == original.source_path
        assert loaded.source_size == original.source_size
        assert loaded.source_sha256 == original.source_sha256
        assert loaded.options == original.options
        assert loaded.total_pages == original.total_pages
        assert loaded.steps["ocr"].status == "completed"
        assert loaded.steps["split"].files == ["p1.pdf", "p2.pdf"]
        assert loaded.steps["mineru"].status == "partial"
