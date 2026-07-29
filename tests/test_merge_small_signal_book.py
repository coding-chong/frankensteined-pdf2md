"""Tests for deterministic assembly of the recovered small-signal book."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import merge_small_signal_book as merger


def _make_chunk(
    output_root: Path,
    start: int,
    end: int,
    timestamp: str,
    *,
    missing_local_page: int | None = None,
) -> Path:
    final_dir = (
        output_root
        / "chunk1_subchunks_run"
        / timestamp
        / f"chunk1_sub_p{start:03d}-{end:03d}"
        / "final"
    )
    final_dir.mkdir(parents=True)
    for local_page in range(1, end - start + 2):
        if local_page == missing_local_page:
            continue
        (final_dir / f"part_{local_page:03d}.md").write_text(
            f"# Page {start + local_page - 1}\n", encoding="utf-8"
        )
    return final_dir


def test_discovery_prefers_latest_complete_chunk_and_ignores_partial(tmp_path):
    output_root = tmp_path / "output"
    old = _make_chunk(output_root, 1, 2, "20260101_000000")
    latest = _make_chunk(output_root, 1, 2, "20260101_000200")
    _make_chunk(
        output_root,
        1,
        2,
        "20260101_000300",
        missing_local_page=2,
    )
    tail = _make_chunk(output_root, 3, 4, "20260101_000400")

    chunks = merger.discover_source_chunks(output_root, total_pages=4)

    assert [chunk.final_dir for chunk in chunks] == [latest, tail]
    assert old not in [chunk.final_dir for chunk in chunks]


@pytest.mark.parametrize(
    "ranges, message",
    [
        ([(1, 2), (4, 4)], "gap"),
        ([(1, 3), (3, 4)], "overlap"),
    ],
)
def test_source_coverage_rejects_gaps_and_overlaps(tmp_path, ranges, message):
    chunks = [
        merger.SourceChunk(start, end, "stamp", tmp_path / str(index))
        for index, (start, end) in enumerate(ranges)
    ]

    with pytest.raises(merger.MergeError, match=message):
        merger._validate_source_coverage(chunks, total_pages=4)


def test_page_scoped_image_paths_are_mapped_to_physical_pages(tmp_path):
    chunk = merger.SourceChunk(487, 496, "stamp", tmp_path)
    text = "![](images/p001/first.jpg) ![](images\\p010\\last.jpg)"

    assert merger._rewrite_page_image_paths(text, chunk) == (
        "![](images/p487/first.jpg) ![](images/p496/last.jpg)"
    )


def test_root_image_collision_requires_identical_bytes(tmp_path):
    staging = tmp_path / "staging"
    chunks = []
    for index, content in enumerate((b"same", b"same", b"different"), start=1):
        final_dir = tmp_path / f"source-{index}"
        image = final_dir / "images" / "shared.jpg"
        image.parent.mkdir(parents=True)
        image.write_bytes(content)
        chunks.append(merger.SourceChunk(index, index, str(index), final_dir))

    collisions = []
    merger._copy_chunk_images(chunks[0], staging, collisions)
    merger._copy_chunk_images(chunks[1], staging, collisions)
    assert len(collisions) == 1

    with pytest.raises(merger.MergeError, match="Conflicting assets"):
        merger._copy_chunk_images(chunks[2], staging, collisions)


def test_missing_final_html_image_is_recovered_from_matching_intermediate_page(
    tmp_path,
):
    final_dir = _make_chunk(tmp_path / "output", 1, 1, "stamp")
    (final_dir / "part_001.md").write_text(
        '<img src="images/table-cell.jpg"/>\n', encoding="utf-8"
    )
    recovery = (
        final_dir.parent
        / "intermediate"
        / "mineru_md"
        / "part_001"
        / "images"
        / "table-cell.jpg"
    )
    recovery.parent.mkdir(parents=True)
    recovery.write_bytes(b"cell image")
    chunk = merger.SourceChunk(1, 1, "stamp", final_dir)
    staging = tmp_path / "staging"

    merger._copy_recovery_images(chunk, staging, [])

    assert (staging / "images" / "table-cell.jpg").read_bytes() == b"cell image"
    assert recovery in merger._source_files(chunk)


def test_build_package_generates_transformer_style_indexes_and_book(tmp_path):
    output_root = tmp_path / "output"
    final_dir = _make_chunk(output_root, 1, 537, "20260101_000000")
    (final_dir / "part_001.md").write_text(
        "# First\n\n![](images/p001/first.jpg)\n", encoding="utf-8"
    )
    (final_dir / "part_002.md").write_text(
        '<table><tr><td><img src="images/shared.jpg"/></td></tr></table>\n',
        encoding="utf-8",
    )
    page_image = final_dir / "images" / "p001" / "first.jpg"
    page_image.parent.mkdir(parents=True)
    page_image.write_bytes(b"page image")
    root_image = final_dir / "images" / "shared.jpg"
    root_image.write_bytes(b"root image")
    destination = output_root / "merged" / "book" / "final"

    report = merger.build_package(
        tmp_path, output_root, destination, total_pages=537
    )

    assert report["status"] == "passed"
    assert report["coverage"]["page_count"] == 537
    assert report["source"] == {
        "selected_chunk_count": 1,
        "source_files_unchanged": True,
    }
    assert len(list(destination.glob("part_*.md"))) == 537
    assert (destination / "images" / "p001" / "first.jpg").is_file()
    assert (destination / "images" / "shared.jpg").is_file()
    assert (destination / "chapters" / "ch01_小信号建模分析简介" / "README.md").is_file()

    book = (destination / "book.md").read_text(encoding="utf-8")
    assert book.count("<!-- physical-page:") == 537
    assert book.index("<!-- physical-page: 001 -->") < book.index(
        "<!-- physical-page: 537 -->"
    )
    index = json.loads((destination / "book_index.json").read_text(encoding="utf-8"))
    assert index["part_count"] == 537
    assert index["chapters"][0]["start_part"] == "part_012.md"
    assert index["chapters"][-1]["end_part"] == "part_521.md"


def test_build_package_refuses_to_replace_existing_destination(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()

    with pytest.raises(merger.MergeError, match="Destination already exists"):
        merger.build_package(tmp_path, tmp_path / "output", destination)


def test_default_destination_is_relative_to_selected_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["merge_small_signal_book.py", "--checkout-root", str(tmp_path)]
    )

    args = merger.parse_args()
    destination = (
        args.destination
        or args.checkout_root.resolve() / merger.DEFAULT_DESTINATION_RELATIVE
    )

    assert destination.is_relative_to(tmp_path)
