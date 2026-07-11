# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OCR Flow is a CLI tool that converts PDF documents (chip manuals, datasheets) to AI-readable Markdown format. It uses MinerU API for conversion, supports OCR for scanned PDFs via UMI OCR, and can translate documents using BabelDOC.

## Common Commands

### Setup
```bash
uv venv
uv pip install -e .
uv pip install -e ".[dev]"  # For running tests
uv pip install pythonnet     # Windows SSL bypass for MinerU CDN downloads
```

### CLI Usage
```bash
ocr-flow doctor              # Check dependencies
ocr-flow doctor --ocr --start-ocr  # Check OCR deps, auto-start UMI OCR
ocr-flow config              # Interactive configuration wizard
ocr-flow process input.pdf -o output/ --non-interactive --pdf-type auto --lang en --no-translate -v
```

### Testing
```bash
pytest tests/ -v
pytest tests/test_pipeline.py -v  # Run single test file
pytest tests/test_mineru.py::test_upload -v  # Run single test
```

### Create Test Assets
```bash
python create_stress_test_pdf.py
python create_test_assets.py
```

## Architecture

### Processing Pipeline (7 Steps)

```
Input PDF → [OCR] → [Translate] → [Split] → [Compress] → [MinerU API] → [Format Fix] → [Image Download] → Output Markdown
```

**Step execution order** (see `pipeline.py:Pipeline.run()`):
1. **OCR** (`steps/ocr.py`) - Optional, for scanned PDFs via UMI OCR
2. **Translate** (`steps/translate.py`) - Optional, via BabelDOC
3. **Split** (`steps/split.py`) - Split into page chunks (2 pages if translated, else 1)
4. **Compress** (`steps/compress.py`) - Reduce file size via Ghostscript
5. **MinerU API** (`steps/mineru.py`) - Upload to cloud, poll for result, download ZIP
6. **Format Fix** (`steps/format_fix.py`) - Clean up Markdown formatting
7. **Image Download** (`steps/image_download.py`) - Localize remote images

### Key Files

| File | Purpose |
|------|---------|
| `cli.py` | Click CLI commands: `process`, `config`, `doctor` |
| `pipeline.py` | Main orchestration, handles recovery mode |
| `config.py` | Configuration dataclasses and TOML loading |
| `state.py` | State persistence for resume/retry functionality |
| `self_check.py` | Dependency checking (Ghostscript, MinerU API, UMI OCR) |
| `steps/*.py` | Individual processing steps |
| `utils/api_client.py` | HTTP client utilities |
| `utils/graceful_exit.py` | Ctrl+C handling with state save |

### Configuration

Config file: `~/.ocr-flow/config.toml` (Windows: `%USERPROFILE%\.ocr-flow\config.toml`)

Key settings:
- `mineru.api_token` - Required for PDF conversion
- `compress.ghostscript_path` - Auto-detected if empty
- `babeldoc.path` - Optional BabelDOC Git worktree already normalized by
  `ocr-flow runtime setup --path`; leave empty for the managed runtime
- `umiocr.url` - Local OCR service URL (default: `http://127.0.0.1:1224`)

### State Management

Output directory structure:
```
output/YYYYMMDD_HHMMSS/filename/
├── .state.json          # State for resume/retry
├── intermediate/        # Step outputs (split/, compressed/, mineru_md/)
├── final/               # Final Markdown files + images/
└── ocr-flow.log         # Processing log
```

State tracks: current step, completed files, failed files. On interrupt, user can continue, retry failed, or restart.

## External Dependencies

| Dependency | Purpose | Install |
|------------|---------|---------|
| Ghostscript | PDF compression | https://ghostscript.com/ |
| UMI OCR | Scanned PDF OCR | https://github.com/hiroi-sora/Umi-OCR/releases |
| BabelDOC | PDF translation | `ocr-flow runtime setup`; use `runtime setup --path <git-root>` only to destructively normalize an existing clone |
| MinerU API | Cloud PDF→Markdown | Get token from https://mineru.net/ |

## Notes

- MinerU API has 200MB file size limit
- Use `--pdf-type auto` to auto-detect text vs scanned PDF
- On Windows, `pythonnet` enables .NET WebClient for SSL bypass when downloading from MinerU CDN
