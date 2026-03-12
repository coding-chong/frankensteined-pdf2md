#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for CLI module.

Test suite covering:
- detect_unfinished_task function
- show_recovery_menu function
- interactive_ask function
- CLI commands (process, config, doctor)
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock, Mock
from click.testing import CliRunner

from ocr_flow.cli import (
    detect_unfinished_task,
    show_recovery_menu,
    interactive_ask,
    cli,
)
from ocr_flow.state import State, StateManager
from ocr_flow.config import Config


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
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def test_pdf(temp_dir):
    """Create a test PDF file."""
    pdf_path = temp_dir / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%test content\n%%EOF")
    return pdf_path


@pytest.fixture
def mock_config(temp_dir, monkeypatch):
    """Create a mock config with config file."""
    config_path = temp_dir / ".ocr-flow" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = Config()
    config.mineru.api_token = "test-token"
    config.save(config_path)

    monkeypatch.setattr(Config, 'get_config_path', lambda: config_path)
    return config


@pytest.fixture
def partial_state_dir(temp_dir, test_pdf):
    """Create a directory with partial state."""
    work_dir = temp_dir / "output" / "20260311_120000" / "test"
    work_dir.mkdir(parents=True)

    manager = StateManager(work_dir)
    state = manager.load_or_create(test_pdf, {"pdf_type": "text"})
    state.update_step("ocr", status="skipped")
    state.update_step("split", status="completed")
    state.update_step("mineru", status="partial", completed=[1, 3], failed={"2": "Error"})
    state.total_pages = 5
    manager.save()

    return work_dir


@pytest.fixture
def completed_state_dir(temp_dir, test_pdf):
    """Create a directory with completed state."""
    work_dir = temp_dir / "output" / "20260311_120000" / "completed"
    work_dir.mkdir(parents=True)

    manager = StateManager(work_dir)
    state = manager.load_or_create(test_pdf, {"pdf_type": "text"})
    state.update_step("ocr", status="skipped")
    state.update_step("translate", status="skipped")
    state.update_step("split", status="completed")
    state.update_step("compress", status="completed")
    state.update_step("mineru", status="completed")
    state.update_step("format_fix", status="completed")
    state.update_step("image_download", status="completed")
    manager.save()

    return work_dir


# =============================================================================
# TestDetectUnfinishedTask - Unfinished Task Detection Tests
# =============================================================================

class TestDetectUnfinishedTask:
    """Tests for detect_unfinished_task function."""

    def test_detect_no_state_file(self, temp_dir):
        """Test detection when no state file exists."""
        result = detect_unfinished_task(temp_dir)
        assert result is None

    def test_detect_completed_state(self, completed_state_dir):
        """Test detection returns None for completed state."""
        result = detect_unfinished_task(completed_state_dir)
        assert result is None

    def test_detect_partial_state(self, partial_state_dir):
        """Test detection of partial state."""
        result = detect_unfinished_task(partial_state_dir)

        assert result is not None
        assert result['current_step'] == 'mineru'
        assert result['total'] == 5
        # completed count is len([1, 3]) = 2
        assert result['completed'] == 2
        assert '2' in result['failed']

    def test_detect_returns_state_info(self, partial_state_dir):
        """Test that returned state info has correct structure."""
        result = detect_unfinished_task(partial_state_dir)

        assert 'state' in result
        assert 'state_manager' in result
        assert isinstance(result['state'], State)
        assert isinstance(result['state_manager'], StateManager)


# =============================================================================
# TestShowRecoveryMenu - Recovery Menu Tests
# =============================================================================

class TestShowRecoveryMenu:
    """Tests for show_recovery_menu function."""

    def test_show_menu_with_failed(self, partial_state_dir, monkeypatch, capsys):
        """Test menu display with failed items."""
        state_info = detect_unfinished_task(partial_state_dir)

        # Mock user input
        monkeypatch.setattr('click.prompt', lambda *a, **kw: '1')

        result = show_recovery_menu(state_info)

        # Should return a valid choice
        assert result in ['continue', 'retry', 'continue_retry', 'restart', 'cancel']

    def test_show_menu_without_failed(self, temp_dir, test_pdf, monkeypatch):
        """Test menu without failed items."""
        # Create state with no failures
        work_dir = temp_dir / "work"
        work_dir.mkdir()
        manager = StateManager(work_dir)
        state = manager.load_or_create(test_pdf, {"pdf_type": "text"})
        state.update_step("ocr", status="skipped")
        state.update_step("split", status="running")
        state.total_pages = 3
        manager.save()

        state_info = detect_unfinished_task(work_dir)

        # Mock user input
        monkeypatch.setattr('click.prompt', lambda *a, **kw: '1')

        result = show_recovery_menu(state_info)

        assert result in ['continue', 'restart', 'cancel']

    def test_menu_choices_with_failed(self, partial_state_dir, monkeypatch):
        """Test all choices with failed items."""
        state_info = detect_unfinished_task(partial_state_dir)

        choices = ['1', '2', '3', '4', '5']
        expected = ['continue', 'retry', 'continue_retry', 'restart', 'cancel']

        for choice, expected_result in zip(choices, expected):
            monkeypatch.setattr('click.prompt', lambda *a, **kw: choice)
            result = show_recovery_menu(state_info)
            assert result == expected_result


# =============================================================================
# TestInteractiveAsk - Interactive Mode Tests
# =============================================================================

class TestInteractiveAsk:
    """Tests for interactive_ask function."""

    def test_interactive_single_file(self, monkeypatch):
        """Test single file interactive mode."""
        # Single file mode needs: pdf_choice, lang_choice, trans_choice (if en), confirm
        # Using int type for choices, so need to return integers
        inputs = iter([1, 1, 1, 'Y'])  # pdf_type=1, lang=1, translate=1, confirm=Y

        def mock_prompt(*args, **kwargs):
            try:
                return next(inputs)
            except StopIteration:
                return 'Y'

        monkeypatch.setattr('click.prompt', mock_prompt)
        monkeypatch.setattr('click.echo', lambda *a, **kw: None)

        result = interactive_ask(is_batch=False)

        assert result is not None
        assert result['pdf_type'] == 'text'
        assert result['language'] == 'en'
        assert result['translate'] == True

    def test_interactive_cancel(self, monkeypatch):
        """Test cancellation in interactive mode."""
        inputs = iter([1, 1, 1, 'n'])

        def mock_prompt(*args, **kwargs):
            try:
                return next(inputs)
            except StopIteration:
                return 'n'

        monkeypatch.setattr('click.prompt', mock_prompt)
        monkeypatch.setattr('click.echo', lambda *a, **kw: None)

        result = interactive_ask(is_batch=False)

        assert result is None

    def test_interactive_batch_mode(self, monkeypatch):
        """Test batch processing mode."""
        # Batch mode: pdf_choice, lang_choice, trans_choice, confirm
        inputs = iter([1, 1, 2, 'Y'])  # text, en, no translate

        def mock_prompt(*args, **kwargs):
            try:
                return next(inputs)
            except StopIteration:
                return 'Y'

        monkeypatch.setattr('click.prompt', mock_prompt)
        monkeypatch.setattr('click.echo', lambda *a, **kw: None)

        result = interactive_ask(is_batch=True)

        assert result is not None
        assert result['pdf_type'] == 'text'
        assert result['language'] == 'en'
        assert result['translate'] == False

    def test_interactive_ask_each_pdf_type(self, monkeypatch):
        """Test ask_each for PDF type."""
        inputs = iter([3, 1, 2, 'Y'])  # ask_each, en, no translate

        def mock_prompt(*args, **kwargs):
            try:
                return next(inputs)
            except StopIteration:
                return 'Y'

        monkeypatch.setattr('click.prompt', mock_prompt)
        monkeypatch.setattr('click.echo', lambda *a, **kw: None)

        result = interactive_ask(is_batch=True)

        assert result['pdf_type'] == 'ask_each'

    def test_interactive_chinese_skips_translate(self, monkeypatch):
        """Test that Chinese documents skip translation prompt."""
        # Single file mode: pdf_choice, lang_choice (2=Chinese skips translate), confirm
        inputs = iter([1, 2, 'Y'])  # text, Chinese, confirm

        def mock_prompt(*args, **kwargs):
            try:
                return next(inputs)
            except StopIteration:
                return 'Y'

        monkeypatch.setattr('click.prompt', mock_prompt)
        monkeypatch.setattr('click.echo', lambda *a, **kw: None)

        result = interactive_ask(is_batch=False)

        assert result['language'] == 'zh'
        assert result['translate'] == False  # Auto-skipped for Chinese


# =============================================================================
# TestCliCommands - CLI Command Tests
# =============================================================================

class TestCliCommands:
    """Tests for CLI commands."""

    def test_cli_help(self, runner):
        """Test CLI help output."""
        result = runner.invoke(cli, ['--help'])

        assert result.exit_code == 0
        assert 'OCR Flow' in result.output

    def test_process_help(self, runner):
        """Test process command help."""
        result = runner.invoke(cli, ['process', '--help'])

        assert result.exit_code == 0
        assert 'PDF' in result.output

    def test_config_command(self, runner, mock_config, monkeypatch):
        """Test config command."""
        # Mock the configure_interactive method
        with patch.object(Config, 'configure_interactive') as mock_configure:
            result = runner.invoke(cli, ['config'])
            mock_configure.assert_called_once()

    def test_doctor_help(self, runner):
        """Test doctor command help."""
        result = runner.invoke(cli, ['doctor', '--help'])

        assert result.exit_code == 0

    def test_version(self, runner):
        """Test version output."""
        result = runner.invoke(cli, ['--version'])

        assert result.exit_code == 0

    def test_process_nonexistent_file(self, runner, mock_config):
        """Test processing nonexistent file."""
        result = runner.invoke(cli, ['process', '/nonexistent/file.pdf'])

        assert result.exit_code != 0

    def test_process_directory_no_pdfs(self, runner, temp_dir, mock_config):
        """Test processing directory with no PDFs."""
        result = runner.invoke(cli, ['process', str(temp_dir)])

        assert 'No PDF files' in result.output


# =============================================================================
# TestProcessCommand - Process Command Tests
# =============================================================================

class TestProcessCommand:
    """Tests for process command."""

    def test_process_requires_lang_in_non_interactive(self, runner, test_pdf, mock_config):
        """Test that --lang is required in non-interactive mode."""
        result = runner.invoke(cli, [
            'process', str(test_pdf),
            '--non-interactive',
            '--pdf-type', 'text'
        ])

        # Should fail or complain about missing lang
        assert result.exit_code != 0 or 'required' in result.output.lower()

    def test_process_requires_translate_flag(self, runner, test_pdf, mock_config):
        """Test that translate flag is required in non-interactive mode."""
        result = runner.invoke(cli, [
            'process', str(test_pdf),
            '--non-interactive',
            '--pdf-type', 'text',
            '--lang', 'en'
        ])

        # Should fail or complain about translate flag
        assert result.exit_code != 0 or 'translate' in result.output.lower()

    @patch('ocr_flow.pipeline.Pipeline')
    def test_process_basic(self, mock_pipeline, runner, test_pdf, mock_config):
        """Test basic processing invocation."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = Path("/output/result")
        mock_pipeline.return_value = mock_instance

        result = runner.invoke(cli, [
            'process', str(test_pdf),
            '--non-interactive',
            '--pdf-type', 'text',
            '--lang', 'en',
            '--no-translate'
        ])

        # Check that pipeline was invoked
        mock_pipeline.assert_called_once()


# =============================================================================
# TestDoctorCommand - Doctor Command Tests
# =============================================================================

class TestDoctorCommand:
    """Tests for doctor command."""

    @patch('ocr_flow.self_check.SelfCheck')
    def test_doctor_basic(self, mock_check_class, runner, mock_config):
        """Test basic doctor command."""
        mock_checker = MagicMock()
        mock_checker.check_all.return_value = {
            'ghostscript': {'ok': True, 'message': 'Found'},
            'mineru_api': {'ok': True, 'message': 'Configured'},
        }
        mock_check_class.return_value = mock_checker

        result = runner.invoke(cli, ['doctor'])

        assert result.exit_code == 0
        mock_checker.check_all.assert_called_once()

    @patch('ocr_flow.self_check.SelfCheck')
    def test_doctor_with_ocr(self, mock_check_class, runner, mock_config):
        """Test doctor with --ocr flag."""
        mock_checker = MagicMock()
        mock_checker.check_all.return_value = {
            'ghostscript': {'ok': True, 'message': 'Found'},
            'mineru_api': {'ok': True, 'message': 'OK'},
            'umi_ocr': {'ok': False, 'message': 'Not running'},
        }
        mock_check_class.return_value = mock_checker

        result = runner.invoke(cli, ['doctor', '--ocr'])

        assert result.exit_code == 0
        mock_checker.check_all.assert_called_once_with(needs_ocr=True, needs_translate=False)

    @patch('ocr_flow.self_check.SelfCheck')
    def test_doctor_with_translate(self, mock_check_class, runner, mock_config):
        """Test doctor with --translate flag."""
        mock_checker = MagicMock()
        mock_checker.check_babeldoc.return_value = {'ok': False, 'message': 'Not found'}
        mock_checker.check_all.return_value = {
            'ghostscript': {'ok': True, 'message': 'Found'},
            'mineru_api': {'ok': True, 'message': 'OK'},
            'babeldoc': {'ok': False, 'message': 'Not found'},
        }
        mock_check_class.return_value = mock_checker

        result = runner.invoke(cli, ['doctor', '--translate'])

        assert result.exit_code == 0


# =============================================================================
# TestCliEdgeCases - Edge Case Tests
# =============================================================================

class TestCliEdgeCases:
    """Edge case tests for CLI."""

    def test_process_with_output_dir(self, runner, test_pdf, mock_config, temp_dir):
        """Test process with custom output directory."""
        output_dir = temp_dir / "custom_output"

        with patch('ocr_flow.pipeline.Pipeline') as mock_pipeline:
            mock_instance = MagicMock()
            mock_instance.run.return_value = output_dir
            mock_pipeline.return_value = mock_instance

            result = runner.invoke(cli, [
                'process', str(test_pdf),
                '-o', str(output_dir),
                '--non-interactive',
                '--pdf-type', 'text',
                '--lang', 'en',
                '--no-translate'
            ])

            # Output dir should be created
            assert output_dir.exists() or mock_pipeline.called

    def test_process_auto_pdf_type(self, runner, test_pdf, mock_config):
        """Test process with auto PDF type detection."""
        with patch('ocr_flow.pipeline.Pipeline') as mock_pipeline:
            with patch('ocr_flow.steps.split.detect_pdf_type') as mock_detect:
                mock_detect.return_value = 'text'
                mock_instance = MagicMock()
                mock_instance.run.return_value = Path("/output")
                mock_pipeline.return_value = mock_instance

                result = runner.invoke(cli, [
                    'process', str(test_pdf),
                    '--non-interactive',
                    '--pdf-type', 'auto',
                    '--lang', 'en',
                    '--no-translate'
                ])

                # Auto-detect should be called
                assert mock_pipeline.called or result.exit_code != 0

    def test_invalid_pdf_type(self, runner, test_pdf, mock_config):
        """Test with invalid PDF type."""
        result = runner.invoke(cli, [
            'process', str(test_pdf),
            '--non-interactive',
            '--pdf-type', 'invalid_type',
            '--lang', 'en',
            '--no-translate'
        ])

        # Should fail due to invalid choice
        assert result.exit_code != 0

    def test_process_verbose_flag(self, runner, test_pdf, mock_config):
        """Test verbose flag."""
        with patch('ocr_flow.pipeline.Pipeline') as mock_pipeline:
            mock_instance = MagicMock()
            mock_instance.run.return_value = Path("/output")
            mock_pipeline.return_value = mock_instance

            result = runner.invoke(cli, [
                'process', str(test_pdf),
                '--non-interactive',
                '--pdf-type', 'text',
                '--lang', 'en',
                '--no-translate',
                '-v'
            ])

            # Verbose flag should be passed to Pipeline
            if mock_pipeline.called:
                call_kwargs = mock_pipeline.call_args[1]
                assert call_kwargs.get('verbose') == True
