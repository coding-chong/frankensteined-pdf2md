#!/usr/bin/env python
"""Generate a deterministic image-only Chinese OCR PDF fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import fitz


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
RENDER_SCALE = 2
FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
)
FIXTURE_VERSION = 1
PAGE_TEXT: List[List[str]] = [
    [
        "中文 OCR 验证页一",
        "这是一个用于 Frank PDF2MD 的简体中文扫描测试。",
        "章节锚点：电力电子、变压器与电感器设计。",
        "数字与符号：2026 年 7 月 30 日，输入电压 220 V，效率 95.6%。",
        "英文混排：NeoEngine ONNX GPU。",
    ],
    [
        "中文 OCR 验证页二",
        "第二页检查多行段落、标点和括号。",
        "关键短语：项目本地模型缓存、CUDA 执行提供器、文本层。",
        "请保持原文顺序，不要删除中文字符。",
        "结束标记：中文 OCR 测试完成。",
    ],
]
ANCHORS = [
    "中文 OCR 验证页一",
    "电力电子",
    "变压器与电感器设计",
    "项目本地模型缓存",
    "CUDA 执行提供器",
    "中文 OCR 测试完成",
]


def resolve_font(path: Path | None = None) -> Path:
    """Resolve a deterministic installed Chinese font."""
    candidates = (path,) if path else FONT_CANDIDATES
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    searched = ", ".join(str(item) for item in candidates if item)
    raise FileNotFoundError(f"No Chinese font found; searched: {searched}")


def _render_page(lines: List[str], fontfile: Path) -> bytes:
    source = fitz.open()
    page = source.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    font = fitz.Font(fontfile=str(fontfile))
    page.insert_textbox(
        fitz.Rect(48, 48, PAGE_WIDTH - 48, PAGE_HEIGHT - 48),
        "\n".join(lines),
        fontname="fixture-cn",
        fontfile=str(fontfile),
        fontsize=20,
        lineheight=1.55,
        color=(0, 0, 0),
    )
    page.insert_text(
        (48, PAGE_HEIGHT - 35),
        f"Page {len(source)}",
        fontname="fixture-cn",
        fontfile=str(fontfile),
        fontsize=9,
        color=(0.35, 0.35, 0.35),
    )
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE),
        alpha=False,
    )
    png = pixmap.tobytes("png")
    source.close()
    return png


def build_fixture(output: Path, manifest_path: Path, font_path: Path | None = None) -> Dict[str, Any]:
    """Build the image-only PDF and its machine-readable manifest."""
    fontfile = resolve_font(font_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    document = fitz.open()
    for lines in PAGE_TEXT:
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page.insert_image(
            page.rect,
            stream=_render_page(lines, fontfile),
            keep_proportion=False,
        )
    document.set_metadata(
        {
            "format": "PDF 1.7",
            "title": "Frank Chinese OCR fixture",
            "author": "frankensteined-pdf2md fixture generator",
            "subject": "Image-only Chinese OCR validation",
            "keywords": "ocr, chinese, neoengine",
            "creator": "generate_chinese_ocr_fixture.py",
            "producer": "PyMuPDF",
        }
    )
    document.save(output, garbage=4, deflate=True, no_new_id=True)
    document.close()

    check = fitz.open(output)
    text_layer = "".join(page.get_text("text") for page in check).strip()
    pages = check.page_count
    check.close()
    if text_layer:
        raise RuntimeError("Generated fixture unexpectedly contains a text layer")

    digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
    manifest: Dict[str, Any] = {
        "fixture_version": FIXTURE_VERSION,
        "filename": output.name,
        "sha256": digest,
        "pages": pages,
        "page_size_points": [PAGE_WIDTH, PAGE_HEIGHT],
        "render_scale": RENDER_SCALE,
        "font": fontfile.name,
        "image_only": True,
        "anchors": ANCHORS,
        "page_text": PAGE_TEXT,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test_assets/chinese_scanned_ocr_test.pdf"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("test_assets/chinese_scanned_ocr_test.json"),
    )
    parser.add_argument("--font", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_fixture(args.output, args.manifest, args.font)
    print(
        f"Generated {args.output} pages={manifest['pages']} "
        f"sha256={manifest['sha256']} font={manifest['font']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
