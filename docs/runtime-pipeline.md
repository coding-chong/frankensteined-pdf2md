# coding-chong/frankensteined-pdf2md: Runtime Pipeline

This document defines the executable PDF-to-Markdown path, its ownership
boundaries, and the retained evidence for one Conversion Run. For an ordered
Windows installation use [fresh-clone-setup.md](fresh-clone-setup.md) first.

## Dependency Ownership

| Component | Responsibility | Owner and readiness |
| --- | --- | --- |
| coding-chong/frankensteined-pdf2md | Orchestrates a Conversion Run and persists recovery state. | checkout-root uv.lock; uv sync --locked --extra windows and uv run --locked --extra windows ocr-flow --help succeed. |
| Umi-OCR engine | Produces a layered PDF for scanned source documents. | User-acquired Windows runtime; file manifest plus GET /api/doc/get_options prove the selected Paddle or Rapid contract. |
| BabelDOC Runtime Profile | Produces the optional bilingual Working Document. | Project-managed v0.6.3 runtime; cpu-safe is the CPU-only profile. |
| Ghostscript | Compresses Conversion Segments as a system executable. | User-installed system executable; available through config path, PATH, or common Windows locations. |
| MinerU | Performs Structural Conversion for each Conversion Segment. | User token and external service; success requires upload, polling, ZIP download, and extraction. |
| Translation provider | Supplies optional BabelDOC translation requests. | User-selected compatible API and user-owned key. |

The project Python environment is separate from the managed BabelDOC checkout.
The latter is created at checkout/.ocr-flow-runtime/BabelDOC and must not be
treated as an editable project dependency.

## Umi-OCR Engine Contract

Config owns the engine choice:

~~~toml
[umiocr]
engine = "paddle" # backward-compatible default
language = "models/config_en.txt"
exe_path = "C:/path/to/Umi-OCR.exe"
~~~

or the CPU-only Rapid opt-in:

~~~toml
[umiocr]
engine = "rapid"
language = "English"
exe_path = "C:/Tools/Umi-OCR_Rapid_v2.1.5/Umi-OCR.exe"
~~~

The document-language mapping is owned once by ocr_flow.config:

| Engine | --lang en | --lang zh | Manifest |
| --- | --- | --- | --- |
| paddle | models/config_en.txt | models/config_chinese.txt | umiocr-paddle-v2.1.5.json |
| rapid | English | 简体中文 | umiocr-rapid-v2.1.5.json |

Existing configurations that omit engine remain Paddle. When Rapid is selected,
legacy English/Chinese Paddle defaults are translated to Rapid values. Custom
language values are deliberately preserved and the running service must expose
them through GET /api/doc/get_options before OCR uploads begin.

The local document boundary is:

~~~text
GET  /api/doc/get_options
POST /api/doc/upload
POST /api/doc/result
POST /api/doc/download
GET  /api/doc/clear/{task-id}
~~~

coding-chong/frankensteined-pdf2md first checks the options endpoint, then starts a discoverable local
runtime when necessary. A service whose selectable values do not match the
configured engine fails before upload. This prevents a running Paddle service
from being mistaken for Rapid support.

Use both proof layers for a newly acquired runtime:

~~~powershell
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path <umi-root> --engine rapid
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py --input test_assets\test_page_scanned.pdf --output output\rapid-local-smoke\result.pdf --umiocr <umi-root>\Umi-OCR.exe --engine rapid --lang en
~~~

The second command is local only and must leave a readable PDF with matching
page count and extractable text. It is stronger evidence than a manifest-only
check, but a physically GPU-free Windows machine remains the final CPU-only
portability gate.

## BabelDOC and Ghostscript Contract

The managed BabelDOC runtime is fixed to v0.6.3 at revision
28f784ca6b437dbba040bfd9c67110373cd0924b. An empty babeldoc.path selects the
managed checkout. A nonempty path is accepted only after the explicit,
destructive runtime setup --path operation normalized that exact Git worktree.
There is no fallback to a global BabelDOC executable.

For CPU-only work use only:

~~~powershell
uv run --locked --extra windows ocr-flow runtime setup --profile cpu-safe
uv run --locked --extra windows ocr-flow runtime smoke --profile cpu-safe --input test_assets\test_page_text.pdf
~~~

The Windows DirectML profile is optional acceleration, not a prerequisite or
a fallback for CPU-only machines. It must be selected explicitly and is
described in [babeldoc-runtime-profiles.md](babeldoc-runtime-profiles.md).

Ghostscript is external to the profile. coding-chong/frankensteined-pdf2md uses it for non-translated
segments; translated runs skip it by default to retain BabelDOC font
subsetting, and use it only after explicit --compress. A downloaded installer,
signature, or version string is provenance evidence, not compatibility proof.
Compatibility requires an actual compressed PDF that opens with the original
page count.

## Conversion Flow

~~~text
Source Document
  -> OCR Enrichment for scanned documents
  -> optional Translation Enrichment
  -> Split into Conversion Segments
  -> Compression when enabled
  -> MinerU upload, polling, result ZIP download, extraction
  -> Markdown normalization and image localization
  -> Final Markdown Pages
~~~

Text inputs mark OCR skipped. Scanned inputs must create a layered PDF before
splitting. Translation creates an alternating dual PDF; non-translated runs
skip that stage. State records each completion or skip decision so recovery can
avoid resubmitting completed MinerU parts.

The BabelDOC command receives the real in-memory translation key, but coding-chong/frankensteined-pdf2md
redacts it from console output, log files, subprocess error excerpts, matrix
progress, and retained reports.

## MinerU Download Boundary

Result ZIP retrieval belongs to ocr_flow.steps.mineru. The committed chain is:

1. custom TLS requests with environment proxy settings disabled;
2. curl with proxy environment variables removed;
3. Windows .NET WebClient when pythonnet/.NET is available;
4. Windows PowerShell.

These are alternatives for the result ZIP only. curl and PowerShell are
opportunistic Windows tools, not installation prerequisites. The ZIP path
intentionally avoids inherited proxies because CONNECT/TLS failures were an
observed boundary.

Markdown image localization belongs to ocr_flow.steps.image_download. It first
copies relative image assets already extracted from the result package, then
uses requests only for remote HTTP image URLs. It must not be described as a
MinerU ZIP fallback. Do not claim support for uncommitted DNS workarounds or
mock-only network experiments.

## Commands

All commands are checkout-root commands:

~~~powershell
uv sync --locked --extra windows --extra dev
uv run --locked --extra windows ocr-flow doctor
uv run --locked --extra windows ocr-flow doctor --ocr --start-ocr
uv run --locked --extra windows ocr-flow process <input.pdf> -o <output-dir> --config <credential-config> --non-interactive --pdf-type text --lang en --no-translate --no-open-output
uv run --locked --extra windows ocr-flow process <scanned.pdf> -o <output-dir> --config <credential-config> --non-interactive --pdf-type scanned --lang en --no-translate --no-open-output
uv run --locked --extra windows ocr-flow process <input.pdf> -o <output-dir> --config <credential-config> --non-interactive --pdf-type text --lang en --translate --no-open-output
~~~

The doctor command reads the default user config. Process accepts an explicit
credential config. A translated one-page run is the remote API gate after a
BabelDOC profile update; setup and local smoke never prove that a token or
provider account is usable.

## Artifacts and Recovery

Every Conversion Run creates:

~~~text
<output-root>/<timestamp>/<source-stem>/
  .state.json
  ocr-flow.log
  intermediate/
  final/
    part_001.md ...
    images/
    compressed_pdfs/
  titles_guide.md
~~~

The state file is the recovery source of truth. It records skipped optional
stages, completed MinerU segments, and failed segments. Use recovery continue,
retry, or continue_retry rather than resubmitting successful parts.

## Regression Assets

| Asset | Type | Pages | Primary coverage |
| --- | --- | --- | --- |
| test_page_text.pdf | Text | 1 | Local compression and short remote smoke input |
| test_page_scanned.pdf | Scanned | 1 | Local Umi-OCR layered-PDF smoke input |
| true_text_test.pdf | Text | 15 | Representative text conversion |
| true_scanned_test.pdf | Scanned | 15 | Representative scanned conversion |
| 4_gs_prepress_300dpi.pdf | Text | 6 | Formula, circuit, plot, table matrix fixture |
| 4_gs_prepress_300dpi_scanned_300dpi.pdf | Scanned | 6 | Rapid OCR and visual matrix fixture |

The last two fixtures, their JSON manifest, generator, runner, and validators
are portable Git-tracked test assets. See
[complex-pdf-live-matrix.md](complex-pdf-live-matrix.md) for the four case
names, cost boundary, retained evidence, and mandatory visual review.
