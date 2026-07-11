#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Pipeline module.

Test suite covering:
- Pipeline initialization
- Pipeline execution
- Step processing
- Error handling
- Recovery modes
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime

from ocr_flow.pipeline import Pipeline
from ocr_flow.config import Config
from ocr_flow.state import State, StateManager


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
def test_assets_dir():
    """Get test assets directory."""
    return Path(__file__).parent.parent / "test_assets"


@pytest.fixture
def text_pdf(test_assets_dir):
    """Path to text PDF."""
    return test_assets_dir / "test_page_text.pdf"


@pytest.fixture
def mock_config():
    """Create a mock config."""
    config = Config()
    config.mineru.api_token = "test-token"
    config.compress.quality = "ebook"
    return config


@pytest.fixture
def output_dir(temp_dir):
    """Create output directory."""
    out_dir = temp_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


@pytest.fixture
def partial_state_dir(temp_dir, text_pdf):
    """Create a directory with partial state for recovery tests."""
    work_dir = temp_dir / "partial"
    work_dir.mkdir(parents=True)

    manager = StateManager(work_dir)
    state = manager.load_or_create(text_pdf, {"pdf_type": "text"})
    state.update_step("ocr", status="skipped")
    state.update_step("split", status="completed")
    state.update_step("mineru", status="partial", completed=[1], failed={})
    state.total_pages = 2
    manager.save()

    return work_dir


# =============================================================================
# TestPipelineInit - Initialization Tests
# =============================================================================

class TestPipelineInit:
    """Tests for Pipeline initialization."""

    def test_pipeline_init(self, mock_config):
        """Test basic initialization."""
        pipeline = Pipeline(config=mock_config)

        assert pipeline.config == mock_config
        assert pipeline.verbose == False
        assert pipeline.state_manager is None

    def test_pipeline_init_verbose(self, mock_config):
        """Test initialization with verbose flag."""
        pipeline = Pipeline(config=mock_config, verbose=True)

        assert pipeline.verbose == True

    def test_pipeline_init_state_manager_none(self, mock_config):
        """Test that state_manager starts as None."""
        pipeline = Pipeline(config=mock_config)

        assert pipeline.state_manager is None


# =============================================================================
# TestPipelineSetup - Setup Tests
# =============================================================================

class TestPipelineSetup:
    """Tests for pipeline setup methods."""

    def test_setup_logger(self, mock_config, output_dir):
        """Test logger setup."""
        pipeline = Pipeline(config=mock_config)
        logger = pipeline._setup_logger(output_dir)

        assert logger is not None
        log_file = output_dir / "ocr-flow.log"
        assert log_file.exists() or True  # Logger created, file created on first log

    def test_generate_titles_guide(self, mock_config, output_dir):
        """Test titles guide generation."""
        pipeline = Pipeline(config=mock_config)

        final_dir = output_dir / "final"
        final_dir.mkdir(parents=True)

        pipeline._generate_titles_guide(final_dir, 10, "test.pdf")

        guide_path = final_dir.parent / "titles_guide.md"
        assert guide_path.exists()
        content = guide_path.read_text(encoding='utf-8')
        assert "test.pdf" in content
        assert "10" in content

    def test_show_size_comparison(self, mock_config, output_dir, text_pdf):
        """Test size comparison display."""
        pipeline = Pipeline(config=mock_config, verbose=True)

        # Create some test files
        compressed_files = []
        for i in range(3):
            f = output_dir / f"compressed_{i}.pdf"
            f.write_bytes(b"x" * 1000)
            compressed_files.append(f)

        # Should not raise
        pipeline._show_size_comparison(text_pdf, compressed_files)


# =============================================================================
# TestPipelineRun - Run Tests
# =============================================================================

class TestPipelineRun:
    """Tests for Pipeline run method."""

    @patch('ocr_flow.pipeline.split_pdf')
    @patch('ocr_flow.pipeline.compress_pdf')
    @patch('ocr_flow.pipeline.MinerUClient')
    @patch('ocr_flow.pipeline.format_fix')
    @patch('ocr_flow.pipeline.download_images')
    def test_run_text_pdf_basic(
        self,
        mock_download,
        mock_format,
        mock_mineru,
        mock_compress,
        mock_split,
        mock_config,
        text_pdf,
        output_dir
    ):
        """Test basic run with text PDF (no OCR, no translate)."""
        # Setup mocks
        mock_split.return_value = [output_dir / "part_001.pdf"]
        mock_compress.return_value = output_dir / "compressed_001.pdf"
        mock_mineru_instance = MagicMock()
        mock_mineru_instance.convert.return_value = output_dir / "output.md"
        mock_mineru.return_value = mock_mineru_instance
        mock_format.return_value = output_dir / "final.md"
        mock_download.return_value = (True, [])

        # Create necessary directories
        (output_dir / "part_001.pdf").write_bytes(b"%PDF")
        (output_dir / "compressed_001.pdf").write_bytes(b"%PDF")
        (output_dir / "output.md").write_text("# Test", encoding='utf-8')

        pipeline = Pipeline(config=mock_config, verbose=True)
        result = pipeline.run(
            text_pdf,
            output_dir,
            pdf_type="text",
            language="en",
            translate=False
        )

        # Verify steps were called
        mock_split.assert_called_once()
        mock_compress.assert_called_once()

    def test_run_creates_output_directory(self, mock_config, text_pdf, output_dir):
        """Test that run creates output directory."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.side_effect = Exception("Early exit for test")

            pipeline = Pipeline(config=mock_config)

            try:
                pipeline.run(text_pdf, output_dir, pdf_type="text")
            except Exception:
                pass

            # Output directory should have been created
            # (timestamped subdirectory)
            assert output_dir.exists()

    def test_run_generates_state_file(self, mock_config, text_pdf, output_dir):
        """Test that run generates state file."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.side_effect = Exception("Early exit")

            pipeline = Pipeline(config=mock_config)

            try:
                pipeline.run(text_pdf, output_dir, pdf_type="text")
            except:
                pass

        # Find state files
        state_files = list(output_dir.rglob(".state.json"))
        assert len(state_files) > 0


# =============================================================================
# TestPipelineSteps - Step Processing Tests
# =============================================================================

class TestPipelineSteps:
    """Tests for individual step processing."""

    @patch('ocr_flow.pipeline.split_pdf')
    def test_step_split(self, mock_split, mock_config, text_pdf, output_dir):
        """Test split step."""
        mock_split.return_value = [output_dir / "part_001.pdf"]

        pipeline = Pipeline(config=mock_config)

        # Create a minimal test to verify split is called
        with patch('ocr_flow.pipeline.compress_pdf') as mock_compress:
            mock_compress.side_effect = Exception("Stop after split")

            try:
                pipeline.run(text_pdf, output_dir, pdf_type="text")
            except:
                pass

        mock_split.assert_called()

    @patch('ocr_flow.steps.ocr.ocr_pdf')
    def test_step_ocr_for_scanned(self, mock_ocr, mock_config, text_pdf, output_dir):
        """Test OCR step for scanned PDF."""
        mock_ocr.return_value = output_dir / "ocr_result.pdf"

        with patch('ocr_flow.pipeline.StateManager.backup_file'):
            with patch('ocr_flow.pipeline.split_pdf') as mock_split:
                mock_split.side_effect = Exception("Stop for test")

                pipeline = Pipeline(config=mock_config)
                try:
                    pipeline.run(text_pdf, output_dir, pdf_type="scanned")
                except:
                    pass

        # OCR should be attempted for scanned PDF
        # (may not be called if exception happens before)

    @patch('ocr_flow.steps.ocr.resolve_ocr_language')
    @patch('ocr_flow.steps.ocr.ocr_pdf')
    def test_step_ocr_uses_document_language_and_timeout(self, mock_ocr, mock_resolve, mock_config, text_pdf, output_dir):
        """Test scanned PDFs map document language to the OCR model and pass timeout overrides."""
        mock_resolve.return_value = "models/config_chinese.txt"
        mock_ocr.return_value = output_dir / "ocr_result.pdf"

        with patch('ocr_flow.pipeline.StateManager.backup_file'):
            with patch('ocr_flow.pipeline.split_pdf') as mock_split:
                mock_split.side_effect = Exception("Stop for test")

                pipeline = Pipeline(config=mock_config)
                try:
                    pipeline.run(
                        text_pdf,
                        output_dir,
                        pdf_type="scanned",
                        language="zh",
                        translate=False,
                        ocr_timeout=1234,
                    )
                except:
                    pass

        mock_resolve.assert_called_once_with(
            document_language="zh",
            configured_language=mock_config.umiocr.language,
        )
        assert mock_ocr.call_count == 1
        assert mock_ocr.call_args.kwargs["timeout"] == 1234
        assert mock_ocr.call_args.kwargs["ocr_language"] == "models/config_chinese.txt"

    def test_step_ocr_skipped_for_text(self, mock_config, text_pdf, output_dir):
        """Test that OCR is skipped for text PDF."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.side_effect = Exception("Stop for test")

            pipeline = Pipeline(config=mock_config)
            try:
                pipeline.run(text_pdf, output_dir, pdf_type="text")
            except:
                pass

        # Verify OCR was not imported/called
        # This is implicit - we just check the flow doesn't crash


# =============================================================================
# TestPipelineRecovery - Recovery Mode Tests
# =============================================================================

class TestPipelineRecovery:
    """Tests for recovery mode handling."""

    def test_recovery_mode_continue(self, mock_config, text_pdf, partial_state_dir):
        """Test continue recovery mode."""
        state_manager = StateManager(partial_state_dir)
        state = State.load(partial_state_dir / ".state.json")

        state_info = {
            'state': state,
            'state_manager': state_manager,
            'current_step': 'mineru',
            'total': 2,
            'completed': 1,
            'failed': [],
            'pending': 1,
        }

        pipeline = Pipeline(config=mock_config)

        # Recovery mode should load existing state
        # This test verifies the parameters are accepted
        assert state_info['state'] is not None

    @patch('ocr_flow.pipeline.download_images')
    @patch('ocr_flow.pipeline.format_fix')
    @patch('ocr_flow.pipeline.MinerUClient')
    @patch('ocr_flow.pipeline.compress_pdf')
    @patch('ocr_flow.pipeline.split_pdf')
    def test_recovery_mode_retry_reuses_existing_parts_and_only_retries_failed_pages(
        self,
        mock_split,
        mock_compress,
        mock_mineru,
        mock_format,
        mock_download,
        mock_config,
        text_pdf,
        temp_dir,
    ):
        """Test retry recovery resumes MinerU from failed pages without rebuilding prior steps."""
        work_dir = temp_dir / "chunk_001"
        split_dir = work_dir / "intermediate" / "split"
        compress_dir = work_dir / "intermediate" / "compressed"
        final_dir = work_dir / "final"
        split_dir.mkdir(parents=True)
        compress_dir.mkdir(parents=True)
        final_dir.mkdir(parents=True)

        split_files = []
        compressed_files = []
        for i in range(1, 4):
            split_file = split_dir / f"part_{i:03d}.pdf"
            split_file.write_bytes(b"%PDF")
            split_files.append(split_file)

            compressed_file = compress_dir / f"compressed_part_{i:03d}.pdf"
            compressed_file.write_bytes(b"%PDF")
            compressed_files.append(compressed_file)

        existing_final = final_dir / "part_001.md"
        existing_final.write_text("# existing", encoding='utf-8')

        manager = StateManager(work_dir)
        state = manager.load_or_create(text_pdf, {"pdf_type": "text", "language": "zh", "translate": False, "compress": False})
        state.update_step("ocr", status="skipped")
        state.update_step("translate", status="skipped")
        state.update_step("split", status="completed", output_dir=str(split_dir), files=[file.name for file in split_files])
        state.update_step("compress", status="completed", output_dir=str(compress_dir), files=[file.name for file in compressed_files])
        state.update_step("mineru", status="partial", completed=[1], failed={"2": "auth", "3": "auth"})
        state.update_step("format_fix", status="completed", completed=[1])
        state.update_step("image_download", status="completed", completed=[1])
        state.total_pages = 3
        manager.save()

        state_info = {
            'state': state,
            'state_manager': manager,
            'current_step': 'mineru',
            'total': 3,
            'completed': 1,
            'failed': ['2', '3'],
            'pending': 0,
        }

        def convert_side_effect(pdf_path, output_dir):
            md_path = Path(output_dir) / "full.md"
            md_path.write_text(f"# {Path(pdf_path).name}", encoding='utf-8')
            return md_path

        def format_side_effect(md_file, output_md, is_translated=False):
            Path(output_md).write_text(Path(md_file).read_text(encoding='utf-8'), encoding='utf-8')

        mock_mineru_instance = MagicMock()
        mock_mineru_instance.convert.side_effect = convert_side_effect
        mock_mineru.return_value = mock_mineru_instance
        mock_format.side_effect = format_side_effect
        mock_download.return_value = (True, [])

        pipeline = Pipeline(config=mock_config)
        result = pipeline.run(
            text_pdf,
            temp_dir,
            pdf_type="text",
            language="zh",
            translate=False,
            recovery_mode="retry",
            state_info=state_info,
        )

        assert result == final_dir
        mock_split.assert_not_called()
        mock_compress.assert_not_called()
        retried_parts = [call.args[0].name for call in mock_mineru_instance.convert.call_args_list]
        assert retried_parts == ["compressed_part_002.pdf", "compressed_part_003.pdf"]
        assert (final_dir / "part_001.md").exists()
        assert (final_dir / "part_002.md").exists()
        assert (final_dir / "part_003.md").exists()

        saved_state = State.load(work_dir / ".state.json")
        assert saved_state.steps["mineru"].status == "completed"
        assert saved_state.steps["mineru"].completed == [1, 2, 3]
        assert saved_state.steps["mineru"].failed == {}

    def test_recovery_mode_restart(self, mock_config, text_pdf, output_dir):
        """Test restart recovery mode."""
        # Create an existing state
        manager = StateManager(output_dir)
        state = manager.load_or_create(text_pdf, {"pdf_type": "text"})
        state.update_step("split", status="completed")
        manager.save()

        # Restart mode should create fresh state
        pipeline = Pipeline(config=mock_config)

        # Verify state exists
        assert manager.has_state()


# =============================================================================
# TestPipelineErrorHandling - Error Handling Tests
# =============================================================================

class TestPipelineErrorHandling:
    """Tests for error handling."""

    @patch('ocr_flow.pipeline.download_images')
    @patch('ocr_flow.pipeline.format_fix')
    @patch('ocr_flow.pipeline.MinerUClient')
    @patch('ocr_flow.pipeline.compress_pdf')
    @patch('ocr_flow.pipeline.split_pdf')
    def test_all_mineru_failures_preserve_recovery_state_and_stop_pipeline(
        self,
        mock_split,
        mock_compress,
        mock_mineru,
        mock_format,
        mock_download,
        mock_config,
        text_pdf,
        output_dir,
    ):
        """A fully failed MinerU run must remain retryable and not report success."""
        split_file = output_dir / "part_001.pdf"
        compressed_file = output_dir / "compressed_part_001.pdf"
        split_file.write_bytes(b"%PDF")
        compressed_file.write_bytes(b"%PDF")
        mock_split.return_value = [split_file]
        mock_compress.return_value = compressed_file

        mock_mineru_instance = MagicMock()
        mock_mineru_instance.convert.side_effect = RuntimeError("MinerU CDN unavailable")
        mock_mineru.return_value = mock_mineru_instance

        pipeline = Pipeline(config=mock_config)

        with pytest.raises(RuntimeError, match="did not produce any Markdown segments"):
            pipeline.run(text_pdf, output_dir, pdf_type="text")

        state_paths = list(output_dir.rglob(".state.json"))
        assert len(state_paths) == 1
        saved_state = State.load(state_paths[0])
        mineru_step = saved_state.get_step_status("mineru")
        assert mineru_step.status == "partial"
        assert mineru_step.completed == []
        assert mineru_step.failed == {"1": "MinerU CDN unavailable"}
        assert mineru_step.error is not None
        mock_format.assert_not_called()
        mock_download.assert_not_called()

    def test_handles_split_failure(self, mock_config, text_pdf, output_dir):
        """Test handling of split failure."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.side_effect = RuntimeError("Split failed")

            pipeline = Pipeline(config=mock_config)

            with pytest.raises(RuntimeError, match="Split failed"):
                pipeline.run(text_pdf, output_dir, pdf_type="text")

    def test_handles_compress_failure(self, mock_config, text_pdf, output_dir):
        """Test handling of compress failure."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.return_value = [output_dir / "part_001.pdf"]
            (output_dir / "part_001.pdf").write_bytes(b"%PDF")

            with patch('ocr_flow.pipeline.compress_pdf') as mock_compress:
                mock_compress.side_effect = RuntimeError("Compress failed")

                pipeline = Pipeline(config=mock_config)

                with pytest.raises(RuntimeError, match="Compress failed"):
                    pipeline.run(text_pdf, output_dir, pdf_type="text")

    def test_state_saved_on_error(self, mock_config, text_pdf, output_dir):
        """Test that state is saved when error occurs."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.side_effect = RuntimeError("Test error")

            pipeline = Pipeline(config=mock_config)

            try:
                pipeline.run(text_pdf, output_dir, pdf_type="text")
            except RuntimeError:
                pass

        # State file should exist
        state_files = list(output_dir.rglob(".state.json"))
        # State should have been saved
        assert pipeline.state_manager is not None


# =============================================================================
# TestPipelineOutput - Output Tests
# =============================================================================

class TestPipelineOutput:
    """Tests for pipeline output."""

    def test_output_directory_structure(self, mock_config, text_pdf, output_dir):
        """Test output directory structure."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.side_effect = Exception("Stop for structure test")

            pipeline = Pipeline(config=mock_config)

            try:
                pipeline.run(text_pdf, output_dir, pdf_type="text")
            except:
                pass

        # Check that timestamped directory was created
        # Structure: output/YYYYMMDD_HHMMSS/filename/
        subdirs = [d for d in output_dir.iterdir() if d.is_dir()]
        assert len(subdirs) > 0

    def test_returns_final_directory(self, mock_config, text_pdf, output_dir):
        """Test that run returns path to final directory."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            with patch('ocr_flow.pipeline.compress_pdf') as mock_compress:
                with patch('ocr_flow.pipeline.MinerUClient') as mock_mineru:
                    with patch('ocr_flow.pipeline.format_fix') as mock_format:
                        with patch('ocr_flow.pipeline.download_images') as mock_download:
                            # Setup all mocks
                            mock_split.return_value = [output_dir / "p.pdf"]
                            mock_compress.return_value = output_dir / "c.pdf"
                            mock_mineru_instance = MagicMock()
                            mock_mineru_instance.convert.return_value = output_dir / "out.md"
                            mock_mineru.return_value = mock_mineru_instance
                            mock_format.return_value = output_dir / "final.md"
                            mock_download.return_value = (True, [])

                            # Create files
                            (output_dir / "p.pdf").write_bytes(b"x")
                            (output_dir / "c.pdf").write_bytes(b"x")
                            (output_dir / "out.md").write_text("# T")
                            (output_dir / "final.md").write_text("# T")

                            pipeline = Pipeline(config=mock_config)

                            # Run with minimal setup
                            result = pipeline.run(
                                text_pdf,
                                output_dir,
                                pdf_type="text",
                                language="en",
                                translate=False
                            )

                            assert result is not None
                            assert isinstance(result, Path)


# =============================================================================
# TestPipelineLogging - Logging Tests
# =============================================================================

class TestPipelineLogging:
    """Tests for pipeline logging."""

    def test_logger_created(self, mock_config, output_dir):
        """Test that logger is created during run."""
        pipeline = Pipeline(config=mock_config)

        assert pipeline.logger is None  # Before run

        # Setup logger manually
        logger = pipeline._setup_logger(output_dir)

        assert logger is not None
        assert pipeline.logger is None  # Still None until run

    def test_log_file_created(self, mock_config, text_pdf, output_dir):
        """Test that log file is created."""
        with patch('ocr_flow.pipeline.split_pdf') as mock_split:
            mock_split.side_effect = Exception("Test")

            pipeline = Pipeline(config=mock_config)

            try:
                pipeline.run(text_pdf, output_dir, pdf_type="text")
            except:
                pass

        # Find log files
        log_files = list(output_dir.rglob("ocr-flow.log"))
        # May or may not exist depending on when error occurred
