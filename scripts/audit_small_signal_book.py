#!/usr/bin/env python
"""Audit a rebuilt small-signal book for historical layered-text corruption."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TOTAL_PAGES = 537
MIN_DUPLICATE_BODY_CHARS = 80
DUPLICATE_REVIEW_EXEMPT_PAGES = (1,)
PART_RE = re.compile(r"part_(?P<number>\d{3})\.md$")
KNOWN_BAD_MARKERS = (
    "帀偳",
    "嬏信号",
    "稬1章",
    "帀偳琵路",
    "儆析",
    "线弧",
    "琵路",
)
KNOWN_MOJIBAKE_MARKERS = ("È", "ñ", "Æ", "ì", "î", "uà")


def _body_blocks(markdown: str) -> list[str]:
    blocks = []
    for raw_block in re.split(r"\n\s*\n", markdown):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if not lines or any(line.startswith(("#", "!", ">", "|", "<")) for line in lines):
            continue
        normalized = re.sub(r"\s+", "", "".join(lines))
        if len(normalized) >= MIN_DUPLICATE_BODY_CHARS:
            blocks.append(normalized)
    return blocks


def _page_numbers(package: Path) -> list[int]:
    numbers = []
    for path in package.glob("part_*.md"):
        match = PART_RE.fullmatch(path.name)
        if match:
            numbers.append(int(match.group("number")))
    return sorted(numbers)


def audit_package(package: Path, total_pages: int = TOTAL_PAGES) -> dict[str, Any]:
    package = package.resolve()
    expected = list(range(1, total_pages + 1))
    actual = _page_numbers(package)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))

    pages = []
    marker_totals = Counter({marker: 0 for marker in KNOWN_BAD_MARKERS})
    mojibake_totals = Counter({marker: 0 for marker in KNOWN_MOJIBAKE_MARKERS})
    replacement_total = 0
    duplicate_group_total = 0
    duplicate_excess_total = 0
    actionable_duplicate_group_total = 0

    for page in actual:
        path = package / f"part_{page:03d}.md"
        markdown = path.read_text(encoding="utf-8")
        marker_counts = {
            marker: markdown.count(marker) for marker in KNOWN_BAD_MARKERS
        }
        marker_totals.update(marker_counts)
        mojibake_counts = {
            marker: markdown.count(marker) for marker in KNOWN_MOJIBAKE_MARKERS
        }
        mojibake_totals.update(mojibake_counts)
        replacement_count = markdown.count("\ufffd")
        replacement_total += replacement_count

        block_counts = Counter(_body_blocks(markdown))
        duplicate_counts = [count for count in block_counts.values() if count > 1]
        duplicate_groups = len(duplicate_counts)
        duplicate_excess = sum(count - 1 for count in duplicate_counts)
        duplicate_group_total += duplicate_groups
        duplicate_excess_total += duplicate_excess
        actionable_duplicate_groups = (
            0 if page in DUPLICATE_REVIEW_EXEMPT_PAGES else duplicate_groups
        )
        actionable_duplicate_group_total += actionable_duplicate_groups

        pages.append(
            {
                "physical_page": page,
                "file": path.name,
                "markdown_chars": len(markdown),
                "known_bad_marker_counts": marker_counts,
                "known_bad_marker_total": sum(marker_counts.values()),
                "mojibake_marker_counts": mojibake_counts,
                "mojibake_marker_total": sum(mojibake_counts.values()),
                "replacement_char_count": replacement_count,
                "exact_duplicate_body_groups": duplicate_groups,
                "exact_duplicate_body_excess": duplicate_excess,
                "actionable_duplicate_body_groups": actionable_duplicate_groups,
            }
        )

    passed = (
        actual == expected
        and not missing
        and not extra
        and sum(marker_totals.values()) == 0
        and sum(mojibake_totals.values()) == 0
        and replacement_total == 0
        and actionable_duplicate_group_total == 0
    )
    return {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "scope": {
            "package": str(package),
            "expected_pages": total_pages,
            "actual_pages": len(actual),
            "first_page": actual[0] if actual else None,
            "last_page": actual[-1] if actual else None,
            "missing_pages": missing,
            "extra_pages": extra,
            "duplicate_review_exempt_pages": list(DUPLICATE_REVIEW_EXEMPT_PAGES),
        },
        "summary": {
            "known_bad_marker_counts": dict(marker_totals),
            "known_bad_marker_total": sum(marker_totals.values()),
            "mojibake_marker_counts": dict(mojibake_totals),
            "mojibake_marker_total": sum(mojibake_totals.values()),
            "replacement_char_count": replacement_total,
            "exact_duplicate_body_groups": duplicate_group_total,
            "exact_duplicate_body_excess": duplicate_excess_total,
            "actionable_duplicate_body_groups": actionable_duplicate_group_total,
        },
        "pages": pages,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--total-pages", type=int, default=TOTAL_PAGES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_package(args.package, args.total_pages)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    print(f"Audit report: {args.output.resolve()}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
