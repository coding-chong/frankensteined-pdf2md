#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script to create test PDF files for OCR Flow."""

import fitz  # PyMuPDF
from pathlib import Path


def create_text_pdf(output_path: Path):
    """Create a simple text PDF for testing."""
    doc = fitz.open()

    # Page 1
    page = doc.new_page()
    text = """OCR Flow Test Document - Page 1

This is a test PDF file for OCR Flow pipeline.

Features to test:
1. PDF splitting
2. Ghostscript compression
3. MinerU API conversion
4. Markdown format fixing
5. Image downloading

This document contains text that should be extractable without OCR.

Section 1: Introduction
Lorem ipsum dolor sit amet, consectetur adipiscing elit.

Section 2: Technical Details
- Memory Address: 0x20000000
- Register: GPIO_MODER
- Value: 0xABCD1234

Section 3: Code Example
void main(void) {
    printf("Hello, OCR Flow!");
}
"""
    page.insert_text((50, 50), text, fontsize=10)

    doc.save(output_path)
    doc.close()
    print(f"Created: {output_path}")


def create_scanned_pdf(output_path: Path):
    """Create a scanned-style PDF (image-based) for testing.

    Note: This creates a PDF with an image of text, simulating a scanned document.
    For real testing, you may want to use an actual scanned PDF.
    """
    from PIL import Image, ImageDraw, ImageFont
    import io

    # Create an image with text
    img = Image.new('RGB', (600, 800), color='white')
    draw = ImageDraw.Draw(img)

    # Use default font
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except:
        font = ImageFont.load_default()

    text = """OCR Flow Test Document - Scanned

This is a simulated scanned PDF for testing OCR functionality.

The text in this document is rendered as an image,
which requires OCR to extract.

Section 1: Scanner Test
This simulates a document scanned from paper.

Section 2: OCR Language
The OCR engine should recognize English text.

Section 3: Layout Detection
Header
-------
Body text goes here.

End of test document.
"""

    draw.text((20, 20), text, fill='black', font=font)

    # Convert to PDF
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PDF')
    img_buffer.seek(0)

    # Save PDF
    with open(output_path, 'wb') as f:
        f.write(img_buffer.read())

    print(f"Created: {output_path}")


def main():
    """Create all test assets."""
    test_dir = Path(__file__).parent / "test_assets"
    test_dir.mkdir(exist_ok=True)

    create_text_pdf(test_dir / "test_page_text.pdf")

    try:
        create_scanned_pdf(test_dir / "test_page_scanned.pdf")
    except ImportError:
        print("PIL not installed, skipping scanned PDF creation")
        print("Install with: pip install Pillow")


if __name__ == "__main__":
    main()
