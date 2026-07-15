"""Regression checks for fresh-clone and AI-maintenance documentation."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_leads_new_clones_to_the_authoritative_setup_guide():
    readme = _read("README.md")

    assert "docs/fresh-clone-setup.md" in readme
    assert readme.index("docs/fresh-clone-setup.md") < readme.index(
        "已建立环境后的最短路径"
    )
    assert "PySocks" not in readme
    assert "uv run --locked --extra windows ocr-flow process" in readme


def test_fresh_clone_guide_indexes_cpu_rapid_and_complex_matrix_contracts():
    guide = _read("docs/fresh-clone-setup.md")

    for expected in (
        "uv python install 3.13.12",
        "uv sync --locked --extra windows --extra dev",
        "pythonnet 3.0.5",
        "Umi-OCR_Rapid_v2.1.5.7z.exe",
        "verify_umiocr_runtime.py --path $umiRoot --engine rapid",
        "validate_umiocr_layered_pdf.py",
        "--umiocr-engine rapid",
        "--profile cpu-safe",
        "text_no_translate",
        "scan_no_translate",
        "text_translate_uncompressed",
        "scan_translate_compressed",
        "24 个 MinerU",
        "visual_review",
    ):
        assert expected in guide


def test_ai_guide_is_repository_neutral_and_indexes_runtime_owners():
    guide = _read("docs/ai-maintenance-guide.md")

    assert "docs/fresh-clone-setup.md" in guide
    assert "ocr_flow/config.py" in guide
    assert "ocr_flow/self_check.py" in guide
    assert "scripts/validate_umiocr_layered_pdf.py" in guide
    assert "vendor-specific assistant instruction files" in guide
    assert "CLAUDE.md" not in guide


def test_python_version_file_matches_the_documented_uv_interpreter():
    assert _read(".python-version").strip() == "3.13.12"
