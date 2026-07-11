# Runtime Pipeline

This document defines the executable PDF-to-Markdown path and the ownership
boundaries that keep a Conversion Run reproducible.

## Dependencies

| Component | Responsibility | Ownership and readiness |
| --- | --- | --- |
| OCR Flow | Orchestrates a Conversion Run and persists recovery state. | `uv sync --all-extras` and `uv run ocr-flow --help` succeed. |
| BabelDOC Runtime Profile | Produces the optional bilingual Working Document. | `ocr-flow runtime setup` installs the managed default; `runtime setup --path` normalizes one explicitly selected Git checkout. It is not imported into OCR Flow's Python environment. |
| ONNX DirectML | Optional Windows layout acceleration for BabelDOC. | Explicit `windows-directml` profile plus a passing layout smoke test. |
| Ghostscript | Compresses Conversion Segments as a system executable. | Installed and upgraded outside OCR Flow; `compress.ghostscript_path` overrides PATH/common-location discovery and `ocr-flow doctor` verifies it. |
| UMI OCR | Supplies OCR Enrichment for scanned documents. | Local document API becomes ready automatically; the vendor runtime is checksum-verified. |
| MinerU | Performs Structural Conversion of each Conversion Segment. | Configured token can upload, poll, download, and extract a result. |

## Configuration Boundaries

The verified managed BabelDOC Runtime is the default translation runtime. An
explicit `babeldoc.path` is accepted only when that exact Git checkout was
normalized by `runtime setup --path` and still matches its recorded v0.6.3
revision, profile, source-patch state, and lock. There is no global-BabelDOC
fallback or user-selected BabelDOC version.

`babeldoc.primary_font_family` is the public BabelDOC family preference:
`serif`, `sans-serif`, `script`, or empty for automatic selection. Exact font
maps and font assets stay inside a versioned BabelDOC Runtime Profile.

Ghostscript is an external system dependency, not part of a BabelDOC Runtime
Profile. It is never installed, reset, or patched by `runtime setup`. OCR Flow
uses it for compression: non-translated runs compress their segments, while
translated runs skip compression by default to preserve BabelDOC font
subsetting and enable it only with `--compress`. This alters compression and
font-embedding behavior, not BabelDOC's font-family or exact-font mapping.

A newer Ghostscript release is not automatically supported merely because its
installer downloads or its signature verifies. Before updating the supported
environment, run OCR Flow's real compression path with that executable and
verify the output opens with the expected page count.

The Windows x64 Ghostscript 10.07.1 release has passed that gate with OCR
Flow: `compress_pdf()` compressed `test_page_text.pdf`, PyMuPDF opened the
result, and the source and result both contained one page. Selecting it remains
an explicit `compress.ghostscript_path` or PATH choice; validation never
rewrites an existing user's Ghostscript configuration.

For scanned documents, OCR Flow discovers project-local `umiocr_local` before
configured paths, PATH, or common installations. It starts the bundled
`UmiOCR-data/runtime/python.exe UmiOCR-data/main.py` launcher when the local
service is unavailable. The supported model identifiers are
`models/config_en.txt` and `models/config_chinese.txt`.

## Conversion Flow

```text
Source Document
  -> OCR Enrichment (scanned documents only)
  -> Translation Enrichment (when --translate is selected)
  -> Split into Conversion Segments
  -> Compression when enabled
  -> MinerU upload, polling, archive download, and extraction
  -> Markdown normalization and asset localization
  -> Final Markdown Pages
```

The UMI OCR boundary is:

```text
GET  /api/doc/get_options
POST /api/doc/upload
POST /api/doc/result
POST /api/doc/download
GET  /api/doc/clear/{task-id}
```

The translation command redacts the OpenAI API key in both console output and
the Conversion Run log. BabelDOC receives the in-memory configured key, but it
is never printed by OCR Flow.

## Commands

```powershell
uv sync --all-extras
uv run ocr-flow runtime setup
uv run ocr-flow runtime smoke --input test_assets\test_page_text.pdf
uv run ocr-flow runtime setup --path C:\work\BabelDOC
uv run ocr-flow runtime smoke --path C:\work\BabelDOC --input test_assets\test_page_text.pdf
uv run ocr-flow runtime setup --path C:\work\BabelDOC --profile windows-directml
uv run ocr-flow runtime smoke --path C:\work\BabelDOC --profile windows-directml --input test_assets\test_page_text.pdf
uv run ocr-flow runtime status
uv run ocr-flow process input.pdf -o output --non-interactive --pdf-type text --lang en --no-translate --no-open-output
uv run ocr-flow process scanned.pdf -o output --non-interactive --pdf-type scanned --lang en --no-translate --no-open-output
uv run ocr-flow process input.pdf -o output --non-interactive --pdf-type text --lang en --translate --no-open-output
```

Use `--config <path>` for project-specific credentials. A translated one-page
run must be used as the API gate after a BabelDOC profile upgrade; setup and
smoke do not require external credentials.

`runtime setup --path` is destructive. It discards tracked, staged, unstaged,
and untracked work in the supplied BabelDOC Git checkout before forcing the
pinned revision. The CPU-safe profile leaves that source upstream-clean; only
the Windows DirectML profile applies its layout patch.

## Artifacts and Recovery

Every Conversion Run creates:

```text
<output-root>/<timestamp>/<source-stem>/
  .state.json
  ocr-flow.log
  intermediate/
  final/
    part_001.md ...
    images/
    compressed_pdfs/
  titles_guide.md
```

`.state.json` is the recovery source of truth. It records skipped optional
stages, completed MinerU segments, and failed segments. Use `--recovery
continue`, `retry`, or `continue_retry` rather than resubmitting completed
work.

## Regression Assets

| Asset | Type | Pages | Primary coverage |
| --- | --- | --- | --- |
| `test_page_text.pdf` | Text | 1 | BabelDOC/API and MinerU smoke gate |
| `true_text_test.pdf` | Text | 15 | Representative text conversion |
| `stress_test_10pages.pdf` | Text | 10 | Compression and multi-page pressure path |
| `test_page_scanned.pdf` | Scanned | 1 | UMI OCR and MinerU smoke test |
| `true_scanned_test.pdf` | Scanned | 15 | Representative scanned conversion |

The task validation report is at
`../.trellis/tasks/07-11-frankensteined-pdf2md-dependency-pipeline/validation.md`.
Inspectable Conversion Run outputs are under `output/trellis_live_validation/`.
