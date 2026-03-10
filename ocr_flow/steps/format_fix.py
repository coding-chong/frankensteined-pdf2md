#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Markdown format fixing module.

This module fixes common formatting issues in OCR-generated Markdown.
Based on confuse_md_fix/fix_markdown.py
"""

import re
from pathlib import Path


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace characters."""
    text = re.sub(r'[\x0b\x0c\x85\u2028\u2029]', '\n', text)
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    text = re.sub(r'[\x00-\x08\x0e-\x1f\x7f-\x9f]', '', text)
    return text


def fix_spaces_around_cjk(text: str) -> str:
    """Fix spacing issues around CJK characters."""
    text = re.sub(r'([\u4e00-\u9fff]) +([\u4e00-\u9fff])', r'\1\2', text)
    text = re.sub(r'([，。、；：？！""''（）【】《】]) ', r'\1', text)
    return text


def fix_latex_math(text: str) -> str:
    """Fix LaTeX math formula formatting."""
    def fix_math_content(match):
        content = match.group(1)
        content = re.sub(r'\s*=\s*', '=', content)
        content = re.sub(r' +', ' ', content)
        content = content.strip()
        return f'${content}$'

    text = re.sub(r'\$\s*([^$\n]+?)\s*\$', fix_math_content, text)

    def fix_latex_cmd(match):
        cmd = match.group(1)
        content = match.group(2)
        content = ' '.join(content.split())
        return f'\\{cmd}{{{content}}}'

    text = re.sub(r'\\(\w+)\s*\{\s*([^}]+?)\s*\}', fix_latex_cmd, text)

    return text


def fix_headings(text: str) -> str:
    """Fix heading formatting."""
    lines = text.split('\n')
    result = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith('#'):
            level = 0
            for c in stripped:
                if c == '#':
                    level += 1
                else:
                    break
            content = stripped[level:].lstrip()
            line = '#' * level + ' ' + content
            line = re.sub(r'\s+#+$', '', line)
        result.append(line)

    return '\n'.join(result)


def fix_bold_italic(text: str) -> str:
    """Fix bold and italic markers."""
    text = re.sub(r'\*\*\s+([^*\n]+?)\s+\*\*', r'**\1**', text)
    text = re.sub(r'(?<!\*)\*\s+([^*\n]+?)\s+\*(?!\*)', r'*\1*', text)
    return text


def fix_links_images(text: str) -> str:
    """Fix link and image formatting."""
    text = re.sub(r'\[\s*([^\]\n]*?)\s*\]\(\s*([^)\n]+?)\s*\)', r'[\1](\2)', text)
    text = re.sub(r'!\[\s*([^\]\n]*?)\s*\]\(\s*([^)\n]+?)\s*\)', r'![\1](\2)', text)
    return text


def fix_line_spacing(text: str) -> str:
    """Fix line spacing and empty lines."""
    lines = text.split('\n')
    result = []
    prev_was_heading = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_heading = bool(re.match(r'^#{1,6}\s', stripped))

        if is_heading and not prev_was_heading and i > 0 and result and result[-1].strip():
            result.append('')

        result.append(line.rstrip())
        prev_was_heading = is_heading

    final_result = []
    empty_count = 0

    for line in result:
        if line == '':
            empty_count += 1
            if empty_count <= 2:
                final_result.append(line)
        else:
            empty_count = 0
            final_result.append(line)

    return '\n'.join(final_result)


def fix_ocr_specific_issues(text: str) -> str:
    """Fix OCR-specific issues."""
    text = re.sub(r' +([.,;:!?])', r'\1', text)
    text = re.sub(r' +([)\]])', r'\1', text)
    text = re.sub(r'([(\[]) +', r'\1', text)
    text = re.sub(r' {2,}', ' ', text)
    return text


def fix_markdown(text: str) -> str:
    """Main fix function that applies all fixes."""
    code_blocks = []
    inline_codes = []

    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f'\n__CODE_BLOCK_{len(code_blocks)-1}__\n'

    def save_inline_code(match):
        inline_codes.append(match.group(0))
        return f'__INLINE_CODE_{len(inline_codes)-1}__'

    # Protect code blocks
    text = re.sub(r'```[\s\S]*?```', save_code_block, text)
    text = re.sub(r'`[^`\n]+`', save_inline_code, text)

    # Apply fixes
    text = normalize_whitespace(text)
    text = fix_spaces_around_cjk(text)
    text = fix_latex_math(text)
    text = fix_headings(text)
    text = fix_bold_italic(text)
    text = fix_links_images(text)
    text = fix_ocr_specific_issues(text)
    text = fix_line_spacing(text)

    # Restore code blocks
    for i, code in enumerate(code_blocks):
        text = text.replace(f'\n__CODE_BLOCK_{i}__\n', code)
    for i, code in enumerate(inline_codes):
        text = text.replace(f'__INLINE_CODE_{i}__', code)

    return text


def add_page_hints(content: str, is_translated: bool) -> str:
    """Add page hints to the content."""
    header = """---
> 📖 **提示 / Note**: 本文档是分页内容的一部分。若内容不完整，请查阅相邻页面。
> This document is part of a paginated series. If incomplete, please refer to adjacent pages.
---
"""

    footer = """
---
> 📖 **提示 / Note**: 本节内容若不完整，请继续阅读下一页。
> If this section appears incomplete, please continue to the next page.
"""

    return header + "\n" + content + "\n" + footer


def format_fix(
    input_path: Path,
    output_path: Path,
    is_translated: bool = False,
) -> Path:
    """Fix Markdown format and add page hints.

    Args:
        input_path: Path to input Markdown file
        output_path: Path to output Markdown file
        is_translated: Whether the content is translated (bilingual)

    Returns:
        Path to the output file
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Read input
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix format
    content = fix_markdown(content)

    # Add page hints
    content = add_page_hints(content, is_translated)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return output_path
