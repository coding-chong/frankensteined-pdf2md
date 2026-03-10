#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pipeline orchestration for OCR Flow."""

from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import shutil

from .config import Config
from .state import State, StateManager
from .steps.split import split_pdf
from .steps.compress import compress_pdf, find_ghostscript
from .steps.mineru import MinerUClient
from .steps.format_fix import format_fix
from .steps.image_download import download_images


class Pipeline:
    """Main processing pipeline."""

    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.state_manager: Optional[StateManager] = None

    def run(
        self,
        input_pdf: Path,
        output_dir: Path,
        pdf_type: str = "text",
        language: str = "en",
        translate: bool = False,
    ) -> Path:
        """Run the full pipeline on a PDF file.

        Args:
            input_pdf: Path to input PDF
            output_dir: Base output directory
            pdf_type: 'text' or 'scanned'
            language: 'en' or 'zh'
            translate: Whether to translate to Chinese

        Returns:
            Path to the final output directory
        """
        input_pdf = Path(input_pdf)
        output_dir = Path(output_dir)

        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = input_pdf.stem
        work_dir = output_dir / timestamp / stem
        work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state
        options = {
            'pdf_type': pdf_type,
            'language': language,
            'translate': translate,
        }
        self.state_manager = StateManager(work_dir)
        state = self.state_manager.load_or_create(input_pdf, options)

        # Setup directories
        intermediate_dir = work_dir / "intermediate"
        intermediate_dir.mkdir(exist_ok=True)
        final_dir = work_dir / "final"
        final_dir.mkdir(exist_ok=True)

        # Data flow: current_pdf tracks the current file being processed
        current_pdf = input_pdf

        try:
            # Step 1: OCR (optional, for scanned PDFs)
            if pdf_type == "scanned":
                if self.verbose:
                    print(f"[1/7] OCR processing: {input_pdf}")
                from .steps.ocr import ocr_pdf
                ocr_output = intermediate_dir / "ocr_result.pdf"
                current_pdf = ocr_pdf(current_pdf, ocr_output, self.config)
                self.state_manager.backup_file("ocr", current_pdf)
                state.update_step("ocr", status="completed", output=str(current_pdf))
                self.state_manager.save()
            else:
                state.update_step("ocr", status="skipped")
                self.state_manager.save()

            # Step 2: Translate (optional)
            if translate:
                if self.verbose:
                    print(f"[2/7] Translating: {current_pdf}")
                from .steps.translate import translate_pdf
                translate_output = intermediate_dir / "translated.dual.pdf"
                current_pdf = translate_pdf(current_pdf, translate_output, self.config)
                self.state_manager.backup_file("translate", current_pdf)
                state.update_step("translate", status="completed", output=str(current_pdf))
                self.state_manager.save()
            else:
                state.update_step("translate", status="skipped")
                self.state_manager.save()

            # Step 3: Split
            if self.verbose:
                print(f"[3/7] Splitting PDF: {current_pdf}")
            pages_per_part = 2 if translate else 1
            split_dir = intermediate_dir / "split"
            split_files = split_pdf(current_pdf, split_dir, pages_per_part)
            state.update_step("split", status="completed", output_dir=str(split_dir),
                            files=[f.name for f in split_files])
            self.state_manager.save()

            # Step 4: Compress
            if self.verbose:
                print(f"[4/7] Compressing PDF files...")
            compress_dir = intermediate_dir / "compressed"
            compress_dir.mkdir(exist_ok=True)
            compressed_files = []
            for split_file in split_files:
                compressed = compress_pdf(split_file, compress_dir, self.config)
                compressed_files.append(compressed)
                self.state_manager.backup_file("compress", compressed)

            state.update_step("compress", status="completed", output_dir=str(compress_dir),
                            files=[f.name for f in compressed_files])
            state.total_pages = len(compressed_files)
            self.state_manager.save()

            # Step 5: MinerU API
            if self.verbose:
                print(f"[5/7] Converting to Markdown via MinerU API...")

            mineru_client = MinerUClient(self.config)
            md_dir = intermediate_dir / "mineru_md"
            md_dir.mkdir(exist_ok=True)

            completed = []
            failed = {}
            md_files_map = {}  # part_num -> md_file_path

            for i, pdf_file in enumerate(compressed_files, 1):
                try:
                    if self.verbose:
                        print(f"  Processing part {i}/{len(compressed_files)}: {pdf_file.name}")

                    # Create subdirectory for this part
                    part_md_dir = md_dir / f"part_{i:03d}"
                    part_md_dir.mkdir(exist_ok=True)

                    md_file = mineru_client.convert(pdf_file, part_md_dir)
                    md_files_map[i] = md_file
                    completed.append(i)
                except Exception as e:
                    failed[str(i)] = str(e)
                    if self.verbose:
                        print(f"  Failed: {e}")

            if failed:
                state.update_step("mineru", status="partial", completed=completed, failed=failed)
            else:
                state.update_step("mineru", status="completed", completed=completed)
            self.state_manager.save()

            # Step 6: Format fix
            if self.verbose:
                print(f"[6/7] Fixing Markdown format...")

            format_completed = []
            for i in completed:
                if i in md_files_map:
                    md_file = md_files_map[i]
                    if md_file.exists():
                        output_md = final_dir / f"part_{i:03d}.md"
                        format_fix(md_file, output_md, is_translated=translate)
                        format_completed.append(i)

            state.update_step("format_fix", status="completed", completed=format_completed)
            self.state_manager.save()

            # Step 7: Image download
            if self.verbose:
                print(f"[7/7] Downloading images...")

            images_dir = final_dir / "images"
            images_dir.mkdir(exist_ok=True)

            download_completed = []
            download_failed = {}

            for i in format_completed:
                md_file = final_dir / f"part_{i:03d}.md"
                if md_file.exists():
                    success, failed_urls = download_images(md_file, images_dir, i)
                    download_completed.append(i)
                    if failed_urls:
                        download_failed[str(i)] = failed_urls

            if download_failed:
                state.update_step("image_download", status="partial",
                                completed=download_completed, failed=download_failed)
            else:
                state.update_step("image_download", status="completed", completed=download_completed)
            self.state_manager.save()

            # Copy compressed PDFs to final directory
            final_pdfs = final_dir / "compressed_pdfs"
            final_pdfs.mkdir(exist_ok=True)
            for pdf_file in compressed_files:
                shutil.copy2(pdf_file, final_pdfs / pdf_file.name)

            if self.verbose:
                print(f"\nCompleted! Output: {final_dir}")

            return final_dir

        except Exception as e:
            state.update_step(state.current_step or "unknown", status="failed", error=str(e))
            self.state_manager.save()
            raise
