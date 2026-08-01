#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pipeline orchestration for OCR Flow."""

from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import shutil
import logging

from .config import Config
from .state import StateManager
from .steps.split import has_text_layer, split_pdf
from .steps.compress import compress_pdf, validate_compressed_pdf
from .steps.mineru import MinerUClient
from .steps.format_fix import format_fix
from .steps.image_download import download_images
from .utils.graceful_exit import GracefulExitContext


class AllMinerUSegmentsFailedError(RuntimeError):
    """Raised when MinerU does not produce Markdown for any requested segment."""


class ScannedPdfHasTextLayerError(RuntimeError):
    """Raised when explicit scanned OCR would duplicate an existing text layer."""


class Pipeline:
    """Main processing pipeline."""

    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.state_manager: Optional[StateManager] = None
        self.logger: Optional[logging.Logger] = None

    def _setup_logger(self, work_dir: Path) -> logging.Logger:
        """Setup logging for this pipeline run."""
        from logging.handlers import RotatingFileHandler

        log_file = work_dir / "ocr-flow.log"

        logger = logging.getLogger('ocr_flow')
        logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        logger.handlers = []

        # Rotating file handler: 10MB, keep 3 backups
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,
            backupCount=3,
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))

        logger.addHandler(handler)
        return logger

    def _generate_titles_guide(self, final_dir: Path, total_pages: int, source_name: str):
        """Generate titles_guide.md for Claude Code to generate titles."""
        guide_path = final_dir.parent / "titles_guide.md"

        content = f"""# 标题生成任务

处理 ./final/ 目录下的分页 Markdown 文件，为每个文件生成标题并重命名。

## 规则

1. 标题不超过 30 字符
2. 用中文概括该页核心主题
3. 特殊页面：
   - 目录页 → "目录"
   - 空白页 → "空白"
   - 图表为主 → "图解XXX"
4. 不使用非法字符：\\/:*?"<>|

## 输出

1. 重命名文件：part_XXX.md → {{标题}}_pXXX.md
2. 生成 titles.json 记录所有标题

## titles.json 格式

```json
{{
  "source": "{source_name}",
  "total_pages": {total_pages},
  "pages": [
    {{"page": 1, "title": "待生成", "file": "part_001.md"}}
  ]
}}
```
"""
        guide_path.write_text(content, encoding='utf-8')
        if self.verbose:
            print(f"  Generated: {guide_path}")

    def _show_size_comparison(self, original: Path, compressed_files: List[Path]):
        """Show file size comparison between original and compressed PDFs."""
        original_size = original.stat().st_size
        compressed_size = sum(f.stat().st_size for f in compressed_files if f.exists())

        original_mb = original_size / (1024 * 1024)
        compressed_mb = compressed_size / (1024 * 1024)

        if original_size > 0:
            ratio = (1 - compressed_size / original_size) * 100
        else:
            ratio = 0

        if self.verbose:
            print(f"  原始大小: {original_mb:.2f} MB")
            print(f"  压缩后: {compressed_mb:.2f} MB")
            print(f"  压缩率: {ratio:.1f}%")

        if self.logger:
            self.logger.info(f"Size comparison: {original_mb:.2f}MB -> {compressed_mb:.2f}MB ({ratio:.1f}% reduction)")

    def _load_recorded_files(self, step, output_dir: Path) -> List[Path]:
        """Load previously recorded files for a completed step."""
        if not step or not step.output_dir:
            return []

        base_dir = Path(step.output_dir)
        files = []
        for name in step.files:
            file_path = base_dir / name
            if file_path.exists():
                files.append(file_path)
        return files

    def _find_existing_md_file(self, part_dir: Path) -> Optional[Path]:
        """Find an existing Markdown file under a MinerU part directory."""
        if not part_dir.exists():
            return None

        md_files = list(part_dir.glob("*.md"))
        if md_files:
            return md_files[0]

        for subdir in part_dir.iterdir():
            if subdir.is_dir():
                md_files = list(subdir.glob("*.md"))
                if md_files:
                    return md_files[0]
        return None

    def _resolve_mineru_targets(self, total_parts: int, mineru_step, recovery_mode: Optional[str]) -> List[int]:
        """Resolve which MinerU parts should run for the current mode."""
        if total_parts <= 0:
            return []

        all_parts = list(range(1, total_parts + 1))
        if not recovery_mode or not mineru_step:
            return all_parts

        completed = set(mineru_step.completed or [])
        failed = {int(key) for key in (mineru_step.failed or {}).keys()}
        pending = [part for part in all_parts if part not in completed and part not in failed]

        if recovery_mode == "continue":
            return pending
        if recovery_mode == "retry":
            return sorted(failed)
        if recovery_mode == "continue_retry":
            return sorted(set(pending) | failed)
        return all_parts

    def run(
        self,
        input_pdf: Path,
        output_dir: Path,
        pdf_type: str = "text",
        language: str = "en",
        translate: bool = False,
        compress: bool = False,
        recovery_mode: Optional[str] = None,
        state_info: Optional[Dict[str, Any]] = None,
        ocr_timeout: Optional[int] = None,
        ocr_language: Optional[str] = None,
    ) -> Path:
        """Run the full pipeline on a PDF file.

        Args:
            input_pdf: Path to input PDF
            output_dir: Base output directory
            pdf_type: 'text' or 'scanned'
            language: 'en' or 'zh'
            translate: Whether to translate to Chinese
            compress: Whether to compress translated PDFs (disables font subsetting)
            recovery_mode: 'continue' | 'retry' | 'continue_retry' | 'restart' | None
            state_info: Existing state info for recovery
            ocr_timeout: Override OCR timeout in seconds
            ocr_language: Override UMI OCR model path

        Returns:
            Path to the final output directory
        """
        input_pdf = Path(input_pdf)
        output_dir = Path(output_dir)

        # Handle recovery mode
        if recovery_mode and state_info:
            work_dir = state_info['state_manager'].output_dir
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Create timestamped output directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = input_pdf.stem
            work_dir = output_dir / timestamp / stem
            work_dir.mkdir(parents=True, exist_ok=True)

        # S2.2: Setup logger
        self.logger = self._setup_logger(work_dir)
        self.logger.info(f"Starting pipeline for: {input_pdf}")
        self.logger.info(f"Options: pdf_type={pdf_type}, language={language}, translate={translate}, compress={compress}")

        # Initialize state
        options = {
            'pdf_type': pdf_type,
            'language': language,
            'translate': translate,
            'compress': compress,
        }
        self.state_manager = StateManager(work_dir)

        if recovery_mode and state_info:
            state = state_info['state']
            self.state_manager.state = state
        else:
            state = self.state_manager.load_or_create(input_pdf, options)

        # Setup directories
        intermediate_dir = work_dir / "intermediate"
        intermediate_dir.mkdir(exist_ok=True)
        final_dir = work_dir / "final"
        final_dir.mkdir(exist_ok=True)

        # Data flow: current_pdf tracks the current file being processed
        current_pdf = input_pdf

        # S1.2: Use GracefulExit to handle Ctrl+C
        with GracefulExitContext(self.state_manager):
            try:
                ocr_step = state.get_step_status("ocr")
                translate_step = state.get_step_status("translate")
                split_step = state.get_step_status("split")
                compress_step = state.get_step_status("compress")
                mineru_step = state.get_step_status("mineru")

                # Step 1: OCR (optional, for scanned PDFs)
                if pdf_type == "scanned":
                    if recovery_mode and ocr_step.status == "completed" and ocr_step.output and Path(ocr_step.output).exists():
                        current_pdf = Path(ocr_step.output)
                    else:
                        if has_text_layer(input_pdf):
                            message = (
                                "Explicit scanned mode requires an input PDF without an "
                                "extractable text layer. Use --pdf-type text or "
                                "preprocess the PDF explicitly before OCR."
                            )
                            state.update_step("ocr", status="failed", error=message)
                            self.state_manager.save()
                            if self.logger:
                                self.logger.error(message)
                            raise ScannedPdfHasTextLayerError(message)

                        msg = "[1/7] OCR processing"
                        self.logger.info(msg)
                        if self.verbose:
                            print(f"{msg}: {input_pdf}")
                        from .steps.ocr import ocr_pdf, resolve_ocr_language
                        ocr_output = intermediate_dir / "ocr_result.pdf"
                        current_pdf = ocr_pdf(
                            current_pdf,
                            ocr_output,
                            self.config,
                            logger=self.logger,
                            timeout=ocr_timeout,
                            ocr_language=ocr_language or resolve_ocr_language(
                                document_language=language,
                                configured_language=self.config.umiocr.language,
                                engine=self.config.umiocr.engine,
                            ),
                        )
                        self.state_manager.backup_file("ocr", current_pdf)
                        state.update_step("ocr", status="completed", output=str(current_pdf))
                        self.state_manager.save()
                else:
                    state.update_step("ocr", status="skipped")
                    self.state_manager.save()

                # Step 2: Translate (optional)
                if translate:
                    if recovery_mode and translate_step.status == "completed" and translate_step.output and Path(translate_step.output).exists():
                        current_pdf = Path(translate_step.output)
                    else:
                        msg = "[2/7] Translating"
                        self.logger.info(msg)
                        if self.verbose:
                            print(f"{msg}: {current_pdf}")
                        from .steps.translate import translate_pdf
                        translate_output = intermediate_dir / "translated.dual.pdf"
                        current_pdf = translate_pdf(current_pdf, translate_output, self.config, skip_clean=compress, ocr_workaround=(pdf_type == "scanned"), logger=self.logger)
                        self.state_manager.backup_file("translate", current_pdf)
                        state.update_step("translate", status="completed", output=str(current_pdf))
                        self.state_manager.save()
                else:
                    state.update_step("translate", status="skipped")
                    self.state_manager.save()

                # Step 3: Split
                split_files = self._load_recorded_files(split_step, intermediate_dir / "split") if recovery_mode else []
                if split_files:
                    split_dir = Path(split_step.output_dir)
                else:
                    msg = "[3/7] Splitting PDF"
                    self.logger.info(f"{msg}: {current_pdf}")
                    if self.verbose:
                        print(f"{msg}: {current_pdf}")
                    pages_per_part = 2 if translate else 1
                    split_dir = intermediate_dir / "split"
                    split_files = split_pdf(current_pdf, split_dir, pages_per_part)
                    state.update_step("split", status="completed", output_dir=str(split_dir),
                                    files=[f.name for f in split_files])
                    self.state_manager.save()

                # Step 4: Compress
                # By default, skip compression for translated PDFs to preserve CJK font encoding.
                # Use --compress flag to enable compression (disables font subsetting instead).
                if translate and not compress:
                    if self.verbose and not split_files:
                        print("[4/7] Skipping compression for translated PDF (use --compress to enable)...")
                    self.logger.info("Step 4: Skipping compression for translated PDF (font subsetting preserved)")
                    compressed_files = split_files
                    state.update_step("compress", status="skipped")
                    self.state_manager.save()
                else:
                    compressed_files = self._load_recorded_files(compress_step, intermediate_dir / "compressed") if recovery_mode else []
                    if compressed_files:
                        compress_dir = Path(compress_step.output_dir)
                    else:
                        if self.verbose:
                            print("[4/7] Compressing PDF files...")
                        self.logger.info("Step 4: Compressing PDF files")

                        compress_dir = intermediate_dir / "compressed"
                        compress_dir.mkdir(exist_ok=True)
                        compressed_files = []
                        validation_reports = []
                        for split_file in split_files:
                            compressed = compress_pdf(split_file, compress_dir, self.config)
                            self.state_manager.backup_file("compress", compressed)

                            try:
                                validation = validate_compressed_pdf(split_file, compressed)
                                report = validation.to_dict()
                            except Exception as exc:
                                validation = None
                                report = {
                                    "preserved": False,
                                    "reason": "validation_error",
                                    "source_pages": None,
                                    "candidate_pages": None,
                                    "source_has_meaningful_text": None,
                                    "minimum_text_similarity": 0.0,
                                    "pages": [],
                                    "error_type": type(exc).__name__,
                                }

                            selected = compressed
                            if validation is None or not validation.preserved:
                                selected = compress_dir / f"text_safe_{split_file.name}"
                                shutil.copy2(split_file, selected)
                                self.state_manager.backup_file("compress", selected)
                                self.logger.warning(
                                    "Compression text validation rejected part=%s "
                                    "reason=%s minimum_similarity=%.6f; using=%s",
                                    split_file.name,
                                    report["reason"],
                                    report["minimum_text_similarity"],
                                    selected.name,
                                )
                            else:
                                self.logger.info(
                                    "Compression text validation accepted part=%s "
                                    "reason=%s minimum_similarity=%.6f",
                                    split_file.name,
                                    validation.reason,
                                    validation.minimum_text_similarity,
                                )

                            report.update(
                                {
                                    "source_file": split_file.name,
                                    "candidate_file": compressed.name,
                                    "selected_file": selected.name,
                                }
                            )
                            validation_reports.append(report)
                            compressed_files.append(selected)

                        validation_report_path = compress_dir / "compression_validation.json"
                        validation_report_path.write_text(
                            json.dumps(
                                {"version": 1, "parts": validation_reports},
                                ensure_ascii=False,
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                        self.state_manager.backup_file("compress", validation_report_path)

                        state.update_step("compress", status="completed", output_dir=str(compress_dir),
                                        files=[f.name for f in compressed_files])
                        self.state_manager.save()

                state.total_pages = len(compressed_files)

                # S3.2: Show size comparison (only when compression was performed)
                if not translate or compress:
                    self._show_size_comparison(input_pdf, compressed_files)

                # Step 5: MinerU API
                msg = "[5/7] Converting to Markdown via MinerU API"
                self.logger.info(msg)
                if self.verbose:
                    print(msg)

                mineru_client = MinerUClient(self.config, logger=self.logger)
                md_dir = intermediate_dir / "mineru_md"
                md_dir.mkdir(exist_ok=True)

                completed = list(mineru_step.completed or []) if recovery_mode else []
                failed = {}
                md_files_map = {}

                for i in completed:
                    part_md_dir = md_dir / f"part_{i:03d}"
                    md_file = self._find_existing_md_file(part_md_dir)
                    if md_file and md_file.exists():
                        md_files_map[i] = md_file

                mineru_targets = self._resolve_mineru_targets(len(compressed_files), mineru_step, recovery_mode)

                for i in mineru_targets:
                    pdf_file = compressed_files[i - 1]
                    try:
                        msg = f"Processing part {i}/{len(compressed_files)}: {pdf_file.name}"
                        self.logger.info(msg)
                        if self.verbose:
                            print(f"  {msg}")

                        part_md_dir = md_dir / f"part_{i:03d}"
                        part_md_dir.mkdir(exist_ok=True)

                        md_file = mineru_client.convert(pdf_file, part_md_dir)
                        md_files_map[i] = md_file
                        if i not in completed:
                            completed.append(i)
                    except Exception as e:
                        failed[str(i)] = str(e)
                        if self.verbose:
                            print(f"  Failed: {e}")

                    state.update_step(
                        "mineru",
                        status="partial",
                        completed=sorted(set(completed)),
                        failed=dict(failed),
                        error=None,
                    )
                    self.state_manager.save()

                completed = sorted(set(completed))
                if failed:
                    error = None
                    if not completed:
                        error = (
                            "MinerU conversion did not produce any Markdown segments. "
                            "Recovery state was saved; resolve the failed MinerU requests "
                            "and retry this run."
                        )
                    state.update_step(
                        "mineru",
                        status="partial",
                        completed=completed,
                        failed=failed,
                        error=error,
                    )
                else:
                    state.update_step("mineru", status="completed", completed=completed, failed={})
                self.state_manager.save()

                if failed and not completed:
                    self.logger.error(error)
                    raise AllMinerUSegmentsFailedError(error)

                # Step 6: Format fix
                msg = "[6/7] Fixing Markdown format"
                self.logger.info(msg)
                if self.verbose:
                    print(msg)

                existing_format_completed = list(state.get_step_status("format_fix").completed or []) if recovery_mode else []
                format_completed = list(existing_format_completed)
                format_targets = mineru_targets if recovery_mode else completed
                for i in format_targets:
                    if i in md_files_map:
                        md_file = md_files_map[i]
                        if md_file.exists():
                            output_md = final_dir / f"part_{i:03d}.md"
                            format_fix(md_file, output_md, is_translated=translate)
                            if i not in format_completed:
                                format_completed.append(i)

                format_completed = sorted(set(format_completed))
                state.update_step("format_fix", status="completed", completed=format_completed)
                self.state_manager.save()

                # Step 7: Image download
                msg = "[7/7] Downloading images"
                self.logger.info(msg)
                if self.verbose:
                    print(msg)

                images_dir = final_dir / "images"
                images_dir.mkdir(exist_ok=True)

                existing_download_completed = list(state.get_step_status("image_download").completed or []) if recovery_mode else []
                download_completed = list(existing_download_completed)
                download_failed = {}

                download_targets = mineru_targets if recovery_mode else format_completed
                for i in download_targets:
                    md_file = final_dir / f"part_{i:03d}.md"
                    if md_file.exists():
                        source_images_dir = md_dir / f"part_{i:03d}"
                        success, failed_urls = download_images(
                            md_file, images_dir, i, source_images_dir, logger=self.logger
                        )
                        if i not in download_completed:
                            download_completed.append(i)
                        if failed_urls:
                            download_failed[str(i)] = failed_urls

                download_completed = sorted(set(download_completed))
                if download_failed:
                    state.update_step("image_download", status="partial",
                                    completed=download_completed, failed=download_failed)
                else:
                    state.update_step("image_download", status="completed", completed=download_completed, failed={})
                self.state_manager.save()

                # Copy compressed PDFs to final directory
                final_pdfs = final_dir / "compressed_pdfs"
                final_pdfs.mkdir(exist_ok=True)
                for pdf_file in compressed_files:
                    shutil.copy2(pdf_file, final_pdfs / pdf_file.name)

                # S3.1: Generate titles guide
                self._generate_titles_guide(final_dir, state.total_pages, input_pdf.name)

                if self.logger:
                    self.logger.info(f"Pipeline completed successfully: {final_dir}")

                if self.verbose:
                    print(f"\nCompleted! Output: {final_dir}")

                return final_dir

            except KeyboardInterrupt:
                # GracefulExit should have saved state
                if self.logger:
                    self.logger.info("Pipeline interrupted by user")
                raise
            except AllMinerUSegmentsFailedError:
                # The partial MinerU state was saved before raising for recovery.
                raise
            except ScannedPdfHasTextLayerError:
                # The OCR guard persisted an actionable failure before raising.
                raise
            except Exception as e:
                state.update_step(state.current_step or "unknown", status="failed", error=str(e))
                self.state_manager.save()
                if self.logger:
                    self.logger.error(f"Pipeline failed: {e}")
                raise
