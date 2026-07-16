"""Regression checks for fresh-clone and AI-maintenance documentation."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_leads_new_clones_to_the_authoritative_setup_guide():
    readme = _read("README.md")

    assert "docs/fresh-clone-setup.md" in readme
    assert readme.index("docs/fresh-clone-setup.md") < readme.index("日常处理")
    assert "PySocks" not in readme
    assert "uv run --locked --extra windows ocr-flow process" in readme
    assert "完整转换的顺序" in readme
    assert "使用 ocr-flow 交互式配置" in readme
    assert readme.index("使用 ocr-flow 交互式配置") < readme.index(
        "日常处理"
    )
    assert readme.index("日常处理") < readme.index(
        "自动化和批处理（可选）"
    )
    assert 'ocr-flow process "<input.pdf>" -o "<output-dir>" -v' in readme
    for prompt in (
        "MinerU API Token",
        "OpenAI API Key (for BabelDOC translation)",
        "OpenAI model",
        "OpenAI Base URL",
        "BabelDOC Git checkout (leave empty for managed runtime)",
        "BabelDOC primary font family",
        "Ghostscript path",
        "UMI OCR engine",
        "UMI OCR exe path",
    ):
        assert prompt in readme
    assert "普通用户直接按 Enter。不要 clone BabelDOC，也不要填写路径。" in readme
    assert ".ocr-flow-runtime/BabelDOC" in readme
    assert "`ocr-flow config` 没有 `--non-interactive` 参数" in readme
    assert "config.example.toml" in readme
    assert "Copy-Item .\\config.example.toml $credentialConfig" in readme
    assert "`ocr-flow doctor` 只读取它，不能接受\n`--config`" in readme


def test_readme_distinguishes_umiocr_engines_and_names_upstreams():
    readme = _read("README.md")

    for expected in (
        "git-for-windows/git",
        "astral-sh/uv",
        "python/cpython",
        "hiroi-sora/Umi-OCR",
        "ArtifexSoftware/ghostpdl",
        "funstory-ai/BabelDOC",
        "opendatalab/MinerU",
        "Umi-OCR_Paddle_v2.1.5.7z.exe",
        "Umi-OCR_Rapid_v2.1.5.7z.exe",
        "--engine paddle",
        "--engine rapid",
    ):
        assert expected in readme
    assert "扫描件必须使用 Rapid" not in readme


def test_readme_translation_row_names_actual_dependencies():
    readme = _read("README.md")
    translation_row = next(
        line
        for line in readme.splitlines()
        if "需要翻译并保留双语 PDF" in line
    )

    for expected in (
        "opendatalab/MinerU",
        "funstory-ai/BabelDOC",
        "v0.6.3",
        "DeepSeek",
        "deepseek-chat",
        "默认示例",
    ):
        assert expected in translation_row
    assert "BabelDOC cpu-safe runtime" not in translation_row
    assert "兼容 OpenAI API 的翻译服务 key" in translation_row


def test_product_docs_distinguish_repository_package_and_cli_names():
    expected_titles = {
        "README.md": "# coding-chong/frankensteined-pdf2md",
        "docs/ai-maintenance-guide.md": (
            "# coding-chong/frankensteined-pdf2md: AI Maintenance Guide"
        ),
        "docs/babeldoc-runtime-profiles.md": (
            "# coding-chong/frankensteined-pdf2md: BabelDOC Runtime Profiles"
        ),
        "docs/complex-pdf-live-matrix.md": (
            "# coding-chong/frankensteined-pdf2md: Complex PDF Live Matrix"
        ),
        "docs/fresh-clone-setup.md": (
            "# coding-chong/frankensteined-pdf2md: Windows"
        ),
        "docs/runtime-pipeline.md": (
            "# coding-chong/frankensteined-pdf2md: Runtime Pipeline"
        ),
    }

    for path, title in expected_titles.items():
        document = _read(path)
        assert document.startswith(title)
        assert "OCR Flow" not in document
        assert "Frank OCR" not in document


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


def test_docs_define_noncompeting_human_and_maintenance_audiences():
    readme = _read("README.md")
    setup = _read("docs/fresh-clone-setup.md")
    runtime = _read("docs/runtime-pipeline.md")
    profiles = _read("docs/babeldoc-runtime-profiles.md")
    matrix = _read("docs/complex-pdf-live-matrix.md")
    ai_guide = _read("docs/ai-maintenance-guide.md")

    assert "完整转换的顺序" in readme
    assert "不取代\nREADME" in setup
    assert "advanced operators and maintainers" in runtime
    assert "advanced operator operations" in profiles
    assert "release operators and\nmaintainers" in matrix
    assert "canonical complete human workflow" in ai_guide


def test_runtime_network_contract_preserves_tls_and_proxy_policy():
    runtime = _read("docs/runtime-pipeline.md")

    assert "preserving the system CA store and environment proxy policy" in runtime
    assert "curl --noproxy * --resolve" in runtime
    assert "environment proxy settings disabled" not in runtime
    assert "proxy environment variables removed" not in runtime
    assert "Never remove\nglobal proxy variables, disable certificate validation, use `curl -k`" in runtime


def test_historical_agent_material_is_neutral_and_canonically_named():
    plan = _read("docs/superpowers/plans/2026-05-10-ai-friendly-cli-and-docs-plan.md")
    design = _read("docs/superpowers/specs/2026-05-10-ai-friendly-cli-and-docs-design.md")
    handoff = _read("docs/handoffs/2026-07-11-managed-babeldoc-runtime.md")

    for document in (plan, design, handoff):
        assert document.startswith("# coding-chong/frankensteined-pdf2md:")
    assert "Historical planning artifact" in plan
    assert "REQUIRED SUB-SKILL" not in plan
    assert "superpowers:" not in plan
    assert "Frank-owned" not in _read("docs/babeldoc-runtime-profiles.md")


def test_python_version_file_matches_the_documented_uv_interpreter():
    assert _read(".python-version").strip() == "3.13.12"


def test_onboarding_defines_unified_deployment_observability_contract():
    readme = _read("README.md")
    setup = _read("docs/fresh-clone-setup.md")
    ai_guide = _read("docs/ai-maintenance-guide.md")

    for document in (readme, setup, ai_guide):
        assert "doctor --deployment" in document
        assert "UNVERIFIED" in document
    assert "portable Ghostscript" in setup
    assert "24 个\nMinerU parts" in setup
    assert "两个翻译" in setup
    assert "ocr_flow/deployment.py" in ai_guide
    assert "`verify=False`" in setup
    assert "`curl -k`" in setup
