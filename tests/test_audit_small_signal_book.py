"""Tests for the rebuilt small-signal book content audit."""

from __future__ import annotations

from scripts import audit_small_signal_book as audit


def test_clean_contiguous_package_passes(tmp_path):
    for page in (1, 2):
        (tmp_path / f"part_{page:03d}.md").write_text(
            f"# Page {page}\n\n这是第 {page} 页的正常正文，内容足够长以参与重复段落检测。\n",
            encoding="utf-8",
        )

    report = audit.audit_package(tmp_path, total_pages=2)

    assert report["status"] == "passed"
    assert report["scope"]["missing_pages"] == []
    assert report["summary"]["known_bad_marker_total"] == 0


def test_corruption_marker_and_duplicate_body_fail_the_audit(tmp_path):
    duplicate = (
        "这是一段会被重复的正文内容，用于验证审计能够发现完全相同的正文块。"
        "该段需要足够长，避免把表格后重复出现的短说明或图注误判为双文本层。"
        "同时仍应识别整段正文被再次写入同一页的历史重复层问题。"
    )
    (tmp_path / "part_001.md").write_text(
        "# Cover\n\n封面页正文。\n",
        encoding="utf-8",
    )
    (tmp_path / "part_002.md").write_text(
        f"# Page 1\n\n{duplicate}\n\n{duplicate}\n\n嬏信号 VorpÈrian\n",
        encoding="utf-8",
    )

    report = audit.audit_package(tmp_path, total_pages=3)

    assert report["status"] == "failed"
    assert report["scope"]["missing_pages"] == [3]
    assert report["summary"]["known_bad_marker_counts"]["嬏信号"] == 1
    assert report["summary"]["mojibake_marker_counts"]["È"] == 1
    assert report["summary"]["exact_duplicate_body_groups"] == 1
    assert report["summary"]["actionable_duplicate_body_groups"] == 1
