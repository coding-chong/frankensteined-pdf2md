#!/usr/bin/env python
"""Merge the recovered small-signal book subchunks into one validated package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOK_TITLE = "开关变换器小信号建模——基于电路快速分析技术"
BOOK_ID = "switching_converter_small_signal_modeling_zh_p001_537"
TOTAL_PAGES = 537
PAGE_TO_BOOK_OFFSET = 11
DEFAULT_DESTINATION_RELATIVE = (
    Path("output")
    / "chunked_small_signal_runs"
    / "20260729_merged_full_book"
    / "开关变换器小信号建模_p001-537"
    / "final"
)

RANGE_RE = re.compile(r"_p(?P<start>\d{3})-(?P<end>\d{3})$")
PART_RE = re.compile(r"part_(?P<number>\d{3})\.md$")
PAGE_IMAGE_RE = re.compile(
    r"images[\\/]p(?P<number>\d{3})(?P<separator>[\\/])"
)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?P<target>[^)]+)\)")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\((?P<target>[^)]+)\)")
HTML_IMAGE_RE = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*['\"](?P<target>[^'\"]+)['\"]",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)
BOOK_TEXT_REPLACEMENTS = (
    ("VorpÈrian", "Vorpérian"),
    ("VopÈrian", "Vorpérian"),
    ("VatchÈ VorprÈian", "Vatché Vorpérian"),
    ("ThÈvenin", "Thévenin"),
    ("pp.1218ñ1230", "pp. 1218–1230"),
    ("为ñ163", "为−163"),
    (" ñ ", " – "),
    ("<sup>Æ</sup>", "<sup>®</sup>"),
    ("ì", "“"),
    ("î", "”"),
    ("小信号扰动uà组成", "小信号扰动 $\\hat{u}$ 组成"),
)


@dataclass(frozen=True)
class Chapter:
    chapter_id: str
    chapter_no: int
    title: str
    start_book_page: int
    end_book_page: int
    start_part: int
    end_part: int


CHAPTERS = (
    Chapter("ch01", 1, "小信号建模分析简介", 1, 106, 12, 117),
    Chapter("ch02", 2, "Buck 变换器及其衍生拓扑", 107, 218, 118, 229),
    Chapter("ch03", 3, "Boost 变换器及其衍生拓扑", 219, 337, 230, 348),
    Chapter("ch04", 4, "Buck-Boost 变换器及其衍生拓扑", 338, 459, 349, 470),
    Chapter("ch05", 5, "高阶变换器", 460, 510, 471, 521),
)


@dataclass(frozen=True)
class SourceChunk:
    start_page: int
    end_page: int
    timestamp: str
    final_dir: Path

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1


class MergeError(ValueError):
    """Raised when source or generated package invariants are not satisfied."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_files(chunk: SourceChunk) -> list[Path]:
    markdown = sorted(chunk.final_dir.glob("part_*.md"))
    images_dir = chunk.final_dir / "images"
    images = sorted(path for path in images_dir.rglob("*") if path.is_file())
    return sorted(set(markdown + images + _recovery_assets(chunk)))


def source_digest(chunk: SourceChunk) -> str:
    digest = hashlib.sha256()
    for path in _source_files(chunk):
        relative = path.relative_to(chunk.final_dir.parent).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def _part_numbers(final_dir: Path) -> list[int]:
    numbers = []
    for path in final_dir.glob("part_*.md"):
        match = PART_RE.fullmatch(path.name)
        if match:
            numbers.append(int(match.group("number")))
    return sorted(numbers)


def discover_source_chunks(output_root: Path, total_pages: int) -> list[SourceChunk]:
    candidates: dict[tuple[int, int], list[SourceChunk]] = {}
    for run_root in sorted(output_root.glob("chunk*_subchunks_run")):
        if not run_root.is_dir():
            continue
        for final_dir in sorted(run_root.glob("*/*/final")):
            match = RANGE_RE.search(final_dir.parent.name)
            if not match:
                continue
            start = int(match.group("start"))
            end = int(match.group("end"))
            if start < 1 or end < start or end > total_pages:
                continue
            expected_parts = list(range(1, end - start + 2))
            if _part_numbers(final_dir) != expected_parts:
                continue
            chunk = SourceChunk(start, end, final_dir.parent.parent.name, final_dir)
            candidates.setdefault((start, end), []).append(chunk)

    selected = [
        max(group, key=lambda item: (item.timestamp, item.final_dir.as_posix()))
        for group in candidates.values()
    ]
    selected.sort(key=lambda item: (item.start_page, item.end_page))
    if not selected:
        expected_parts = list(range(1, total_pages + 1))
        final_dirs = set(output_root.glob("*/*/final"))
        if output_root.name == "final":
            final_dirs.add(output_root)
        if (output_root / "final").is_dir():
            final_dirs.add(output_root / "final")

        complete_runs = [
            SourceChunk(1, total_pages, final_dir.parent.parent.name, final_dir)
            for final_dir in sorted(final_dirs)
            if _part_numbers(final_dir) == expected_parts
        ]
        if complete_runs:
            return [
                max(
                    complete_runs,
                    key=lambda item: (item.timestamp, item.final_dir.as_posix()),
                )
            ]

    _validate_source_coverage(selected, total_pages)
    return selected


def _validate_source_coverage(chunks: list[SourceChunk], total_pages: int) -> None:
    expected_start = 1
    for chunk in chunks:
        if chunk.start_page != expected_start:
            relation = "overlap" if chunk.start_page < expected_start else "gap"
            raise MergeError(
                f"Source coverage has a {relation} before page {chunk.start_page}; "
                f"expected page {expected_start}"
            )
        expected_start = chunk.end_page + 1
    if expected_start != total_pages + 1:
        raise MergeError(
            f"Source coverage ends at page {expected_start - 1}; expected {total_pages}"
        )


def _rewrite_page_image_paths(text: str, chunk: SourceChunk) -> str:
    def replace(match: re.Match[str]) -> str:
        local_page = int(match.group("number"))
        if not 1 <= local_page <= chunk.page_count:
            raise MergeError(
                f"Image page p{local_page:03d} falls outside source range "
                f"{chunk.start_page}-{chunk.end_page}"
            )
        global_page = chunk.start_page + local_page - 1
        return f"images/p{global_page:03d}/"

    return PAGE_IMAGE_RE.sub(replace, text)


def _normalize_book_text(text: str) -> str:
    for source, replacement in BOOK_TEXT_REPLACEMENTS:
        text = text.replace(source, replacement)
    return text


def _copy_with_collision_check(
    source: Path,
    destination: Path,
    identical_collisions: list[str],
) -> None:
    if destination.exists():
        if source.stat().st_size == destination.stat().st_size:
            if sha256(source) == sha256(destination):
                identical_collisions.append(destination.as_posix())
                return
        raise MergeError(f"Conflicting assets map to {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_chunk_images(
    chunk: SourceChunk,
    staging: Path,
    identical_collisions: list[str],
) -> None:
    images_dir = chunk.final_dir / "images"
    if not images_dir.is_dir():
        return
    for source in sorted(path for path in images_dir.rglob("*") if path.is_file()):
        relative = source.relative_to(images_dir)
        parts = list(relative.parts)
        page_match = re.fullmatch(r"p(?P<number>\d{3})", parts[0])
        if page_match:
            local_page = int(page_match.group("number"))
            if not 1 <= local_page <= chunk.page_count:
                raise MergeError(
                    f"Image directory {parts[0]} falls outside source range "
                    f"{chunk.start_page}-{chunk.end_page}"
                )
            parts[0] = f"p{chunk.start_page + local_page - 1:03d}"
        destination = staging / "images" / Path(*parts)
        _copy_with_collision_check(source, destination, identical_collisions)


def _root_html_targets(text: str) -> list[Path]:
    targets = []
    for match in HTML_IMAGE_RE.finditer(text):
        target = _clean_link_target(match.group("target")).replace("\\", "/")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("images/"):
            continue
        relative = Path(parsed.path).relative_to("images")
        if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
            raise MergeError(f"Unsafe HTML image target: {target}")
        if re.fullmatch(r"p\d{3}", relative.parts[0]):
            continue
        targets.append(relative)
    return targets


def _recovery_asset_map(chunk: SourceChunk) -> list[tuple[Path, Path]]:
    assets = []
    for local_page in range(1, chunk.page_count + 1):
        markdown = chunk.final_dir / f"part_{local_page:03d}.md"
        text = markdown.read_text(encoding="utf-8")
        for relative in _root_html_targets(text):
            if (chunk.final_dir / "images" / relative).is_file():
                continue
            recovery = (
                chunk.final_dir.parent
                / "intermediate"
                / "mineru_md"
                / f"part_{local_page:03d}"
                / "images"
                / relative
            )
            if not recovery.is_file():
                raise MergeError(
                    f"Referenced HTML image is absent from final and intermediate: "
                    f"{markdown}:images/{relative.as_posix()}"
                )
            assets.append((recovery, relative))
    return sorted(set(assets))


def _recovery_assets(chunk: SourceChunk) -> list[Path]:
    return [source for source, _ in _recovery_asset_map(chunk)]


def _copy_recovery_images(
    chunk: SourceChunk,
    staging: Path,
    identical_collisions: list[str],
) -> None:
    for source, relative in _recovery_asset_map(chunk):
        destination = staging / "images" / relative
        _copy_with_collision_check(source, destination, identical_collisions)


def _chapter_for_part(part_number: int) -> Chapter | None:
    return next(
        (
            chapter
            for chapter in CHAPTERS
            if chapter.start_part <= part_number <= chapter.end_part
        ),
        None,
    )


def _page_type(part_number: int, chapter: Chapter | None) -> str:
    if part_number <= 7:
        return "frontmatter"
    if part_number <= 11:
        return "toc"
    if chapter:
        return "chapter_start" if part_number == chapter.start_part else "body"
    if part_number == 522:
        return "conclusion"
    if part_number in (523, 537):
        return "appendix_start"
    return "appendix"


def _chapter_payload(chapter: Chapter) -> dict[str, Any]:
    folder = f"chapters/{chapter.chapter_id}_{chapter.title}/README.md"
    return {
        "chapter_id": chapter.chapter_id,
        "chapter_no": chapter.chapter_no,
        "title": chapter.title,
        "start_book_page": chapter.start_book_page,
        "end_book_page": chapter.end_book_page,
        "start_part": f"part_{chapter.start_part:03d}.md",
        "end_part": f"part_{chapter.end_part:03d}.md",
        "part_count": chapter.end_part - chapter.start_part + 1,
        "folder": folder,
    }


def _page_payload(part_number: int, text: str) -> dict[str, Any]:
    chapter = _chapter_for_part(part_number)
    return {
        "part_number": part_number,
        "file": f"part_{part_number:03d}.md",
        "relative_path": f"part_{part_number:03d}.md",
        "book_page": part_number - PAGE_TO_BOOK_OFFSET
        if part_number > PAGE_TO_BOOK_OFFSET
        else None,
        "type": _page_type(part_number, chapter),
        "chapter_id": chapter.chapter_id if chapter else None,
        "chapter_no": chapter.chapter_no if chapter else None,
        "chapter_title": chapter.title if chapter else None,
        "headings": [match.group("title") for match in HEADING_RE.finditer(text)],
    }


def _relative_to_checkout(path: Path, checkout_root: Path) -> str:
    try:
        return path.relative_to(checkout_root).as_posix()
    except ValueError as exc:
        raise MergeError(f"Source path is outside checkout root: {path}") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_chapter_readmes(staging: Path) -> None:
    for chapter in CHAPTERS:
        chapter_dir = staging / "chapters" / f"{chapter.chapter_id}_{chapter.title}"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Chapter {chapter.chapter_no} {chapter.title}",
            "",
            f"- Chapter ID: `{chapter.chapter_id}`",
            (
                f"- Book page range: `{chapter.start_book_page}-"
                f"{chapter.end_book_page}`"
            ),
            (
                f"- Part range: [../../part_{chapter.start_part:03d}.md]"
                f"(../../part_{chapter.start_part:03d}.md) - "
                f"[../../part_{chapter.end_part:03d}.md]"
                f"(../../part_{chapter.end_part:03d}.md)"
            ),
            f"- Included parts: `{chapter.end_part - chapter.start_part + 1}`",
            "",
            "## Included parts",
            "",
        ]
        lines.extend(
            f"- [../../part_{part:03d}.md](../../part_{part:03d}.md)"
            for part in range(chapter.start_part, chapter.end_part + 1)
        )
        (chapter_dir / "README.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )


def _write_book_toc(staging: Path) -> None:
    lines = [
        f"# {BOOK_TITLE}",
        "",
        "- Canonical pages: `part_001.md` - `part_537.md`",
        "- Continuous book: [book.md](./book.md)",
        "- Front matter: [part_001.md](./part_001.md) - [part_007.md](./part_007.md)",
        "- TOC: [part_008.md](./part_008.md) - [part_011.md](./part_011.md)",
        "- Conclusion: [part_522.md](./part_522.md)",
        "- Appendix A: [part_523.md](./part_523.md) - [part_536.md](./part_536.md)",
        "- Appendix B: [part_537.md](./part_537.md)",
        "",
        "## Chapters",
        "",
        "| Chapter | Title | Book pages | Parts |",
        "|---|---|---:|---|",
    ]
    for chapter in CHAPTERS:
        lines.append(
            f"| {chapter.chapter_id} | {chapter.title} | "
            f"{chapter.start_book_page}-{chapter.end_book_page} | "
            f"[part_{chapter.start_part:03d}.md](./part_{chapter.start_part:03d}.md) - "
            f"[part_{chapter.end_part:03d}.md](./part_{chapter.end_part:03d}.md) |"
        )
    (staging / "book_toc.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clean_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " " in target:
        target = target.split(" ", 1)[0]
    return target


def _local_target(source_file: Path, raw_target: str, root: Path) -> Path | None:
    target = _clean_link_target(raw_target).replace("\\", "/")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path:
        return None
    if parsed.path.startswith("/"):
        raise MergeError(f"Absolute package reference in {source_file}: {target}")
    resolved = (source_file.parent / parsed.path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise MergeError(f"Reference escapes package in {source_file}: {target}") from exc
    return resolved


def _validate_references(
    files: Iterable[Path], pattern: re.Pattern[str], root: Path
) -> tuple[int, list[str]]:
    count = 0
    missing = []
    for source_file in files:
        text = source_file.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            target = _local_target(source_file, match.group("target"), root)
            if target is None:
                continue
            count += 1
            if not target.is_file():
                missing.append(
                    f"{source_file.relative_to(root).as_posix()}:"
                    f"{match.group('target')}"
                )
    return count, missing


def validate_package(staging: Path, total_pages: int) -> dict[str, Any]:
    expected_names = [f"part_{page:03d}.md" for page in range(1, total_pages + 1)]
    actual_names = sorted(path.name for path in staging.glob("part_*.md"))
    if actual_names != expected_names:
        raise MergeError("Generated canonical page names are incomplete or non-contiguous")

    page_files = [staging / name for name in expected_names]
    book_file = staging / "book.md"
    image_files = page_files + [book_file]
    markdown_refs, markdown_missing = _validate_references(
        image_files, MARKDOWN_IMAGE_RE, staging
    )
    html_refs, html_missing = _validate_references(image_files, HTML_IMAGE_RE, staging)
    navigation_files = [staging / "book_toc.md"] + sorted(
        (staging / "chapters").glob("*/README.md")
    )
    navigation_refs, navigation_missing = _validate_references(
        navigation_files, MARKDOWN_LINK_RE, staging
    )
    missing = markdown_missing + html_missing + navigation_missing
    if missing:
        raise MergeError("Missing generated references: " + "; ".join(missing[:10]))

    boundary_count = book_file.read_text(encoding="utf-8").count(
        "<!-- physical-page:"
    )
    if boundary_count != total_pages:
        raise MergeError(
            f"Continuous book has {boundary_count} page markers; expected {total_pages}"
        )
    images = sorted(path for path in (staging / "images").rglob("*") if path.is_file())
    return {
        "schema_version": 1,
        "status": "passed",
        "coverage": {
            "first_page": 1,
            "last_page": total_pages,
            "page_count": len(page_files),
            "gaps": 0,
            "overlaps": 0,
        },
        "assets": {
            "image_file_count": len(images),
            "image_bytes": sum(path.stat().st_size for path in images),
            "markdown_image_references": markdown_refs,
            "html_image_references": html_refs,
            "missing_references": 0,
        },
        "navigation": {
            "chapter_count": len(CHAPTERS),
            "checked_links": navigation_refs,
            "missing_links": 0,
        },
        "continuous_book": {"page_markers": boundary_count},
    }


def build_package(
    checkout_root: Path,
    output_root: Path,
    destination: Path,
    total_pages: int = TOTAL_PAGES,
) -> dict[str, Any]:
    checkout_root = checkout_root.resolve()
    output_root = output_root.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise MergeError(f"Destination already exists: {destination}")
    chunks = discover_source_chunks(output_root, total_pages)
    initial_digests = {chunk: source_digest(chunk) for chunk in chunks}

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    identical_collisions: list[str] = []
    pages: list[dict[str, Any]] = []
    continuous_parts = [f"# {BOOK_TITLE}\n"]
    try:
        for chunk in chunks:
            for local_page in range(1, chunk.page_count + 1):
                global_page = chunk.start_page + local_page - 1
                source = chunk.final_dir / f"part_{local_page:03d}.md"
                text = _rewrite_page_image_paths(
                    source.read_text(encoding="utf-8"), chunk
                )
                text = _normalize_book_text(text)
                destination_page = staging / f"part_{global_page:03d}.md"
                destination_page.write_text(text, encoding="utf-8")
                pages.append(_page_payload(global_page, text))
                continuous_parts.extend(
                    [
                        "\n---\n",
                        f"<!-- physical-page: {global_page:03d} -->\n",
                        text.rstrip() + "\n",
                    ]
                )
            _copy_chunk_images(chunk, staging, identical_collisions)
            _copy_recovery_images(chunk, staging, identical_collisions)

        (staging / "book.md").write_text(
            "\n".join(continuous_parts), encoding="utf-8"
        )
        _write_book_toc(staging)
        _write_chapter_readmes(staging)

        source_chunks = []
        for chunk in chunks:
            source_chunks.append(
                {
                    "start_page": chunk.start_page,
                    "end_page": chunk.end_page,
                    "page_count": chunk.page_count,
                    "timestamp": chunk.timestamp,
                    "final_dir": _relative_to_checkout(chunk.final_dir, checkout_root),
                    "sha256": initial_digests[chunk],
                }
            )
        index = {
            "book_id": BOOK_ID,
            "book_title": BOOK_TITLE,
            "source_dir": "final",
            "part_count": total_pages,
            "page_offset_from_part_to_book_page": PAGE_TO_BOOK_OFFSET,
            "frontmatter": {
                "start_part": "part_001.md",
                "end_part": "part_007.md",
            },
            "toc": {
                "parts": [f"part_{page:03d}.md" for page in range(8, 12)]
            },
            "conclusion": {"parts": ["part_522.md"], "book_page": 511},
            "appendices": [
                {
                    "appendix_id": "appendix_a",
                    "title": "电路快速分析技术 (FACT)",
                    "start_part": "part_523.md",
                    "end_part": "part_536.md",
                    "start_book_page": 512,
                    "end_book_page": 525,
                },
                {
                    "appendix_id": "appendix_b",
                    "title": "缩略语表",
                    "start_part": "part_537.md",
                    "end_part": "part_537.md",
                    "start_book_page": 526,
                    "end_book_page": 526,
                },
            ],
            "chapters": [_chapter_payload(chapter) for chapter in CHAPTERS],
            "source_chunks": source_chunks,
            "pages": pages,
        }
        _write_json(staging / "book_index.json", index)

        report = validate_package(staging, total_pages)
        report["source"] = {
            "selected_chunk_count": len(chunks),
            "source_files_unchanged": all(
                source_digest(chunk) == initial_digests[chunk] for chunk in chunks
            ),
        }
        report["assets"]["identical_collision_reuses"] = len(
            identical_collisions
        )
        if not report["source"]["source_files_unchanged"]:
            raise MergeError("A selected source changed during the merge")
        _write_json(staging / "validation_report.json", report)
        staging.replace(destination)
        return report
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--source-output", type=Path)
    parser.add_argument("--destination", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checkout_root = args.checkout_root.resolve()
    output_root = (args.source_output or checkout_root / "output").resolve()
    destination = (
        args.destination or checkout_root / DEFAULT_DESTINATION_RELATIVE
    ).resolve()
    report = build_package(checkout_root, output_root, destination)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    print(f"Merged package: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
