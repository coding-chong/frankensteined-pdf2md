# coding-chong/frankensteined-pdf2md: Runtime Pipeline

This document is for advanced operators and maintainers. It defines the
executable PDF-to-Markdown path, its ownership boundaries, and the retained
evidence for one Conversion Run. People running a normal conversion should
follow the complete workflow in [README.md](../README.md); use
[fresh-clone-setup.md](fresh-clone-setup.md) for detailed new-machine and
CPU-only Rapid preparation.

## Dependency Ownership

| Component | Responsibility | Owner and readiness |
| --- | --- | --- |
| coding-chong/frankensteined-pdf2md | Orchestrates a Conversion Run and persists recovery state. | checkout-root uv.lock; uv sync --locked --extra windows and uv run --locked --extra windows ocr-flow --help succeed. |
| Umi-OCR engine | Produces a layered PDF for scanned source documents. | Project-local Umi-OCR v2.1.5 with the NeoEngine Paddle plugin (ONNX CPU) by default, or a separately acquired Rapid runtime; file manifest plus GET /api/doc/get_options prove the selected contract. |
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
| paddle | models/config_en.txt | models/config_chinese.txt | umiocr-paddle-neoengine-v1.4.2.json |
| rapid | English | 简体中文 | umiocr-rapid-v2.1.5.json |

Existing configurations that omit engine remain Paddle. When Rapid is selected,
legacy English/Chinese Paddle defaults are translated to Rapid values. Custom
language values are deliberately preserved and the running service must expose
them through GET /api/doc/get_options before OCR uploads begin.

### Project-local NeoEngine Paddle baseline

The default Paddle profile is `chapterv/umi-paddle-neoengine` version 1.4.2 at
commit `6a87fc4145a13b09104836cb22cf05125b143041`. It runs in the plugin-local
Python 3.12.10 environment with `paddlepaddle==3.2.1`, `paddleocr==3.7.0`, and
`onnxruntime==1.26.0`; `CPUExecutionProvider` is the supported baseline. The
`PP-OCRv6_medium_det_onnx`, `PP-OCRv6_medium_rec_onnx`, and
`PP-LCNet_x1_0_doc_ori_onnx` models must be present in the plugin's package-local
`paddlex/` cache before a run is considered ready. The UTF-8 launcher accepts
both portable and conventional virtual-environment layouts, and the OCR pipe
logs non-JSON stdout noise while waiting for the first valid JSON response.

Verify both the immutable files and the dynamic environment before starting
the host. The plugin-owned status command records the completed CPU environment
for Umi's launcher; the project verifier independently rechecks its claims:

~~~powershell
& "<umi-root>\UmiOCR-data\plugins\win_x64_PaddleOCR_Py\.venv\Scripts\python.exe" `
  "<umi-root>\UmiOCR-data\plugins\win_x64_PaddleOCR_Py\install_status.py" `
  check-env --env cpu --backend onnxruntime --models ready
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py `
  --path <umi-root> --engine paddle --check-environment --provider-mode cpu
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py `
  --input test_assets\test_page_scanned.pdf `
  --output output\paddle-local-smoke\result.pdf `
  --umiocr <umi-root>\Umi-OCR.exe --engine paddle --lang en `
  --provider-mode cpu --report output\paddle-local-smoke\report.json
~~~

The generated `install_status.json` is machine-local and is not a hashed vendor
asset. Its required path, state, model marker, and CPU/GPU backend mapping are
declared in `umiocr-paddle-neoengine-v1.4.2.json`. Missing or stale status fails
readiness even when direct imports happen to succeed.

The Umi host and NeoEngine plugin own Python installations separate from the
project's locked interpreter. `start_umi_ocr` removes inherited `PYTHONHOME`
and `PYTHONPATH` before launching the bundled host; otherwise uv's Python 3.13
stdlib can mix with plugin Python 3.12.10 and fail with `SRE module mismatch`.
All other environment variables remain available to the child process.

Paddle layered-PDF validation defaults to the CPU provider contract. GPU is an
explicit opt-in using the separate `.venv_gpu` and `--provider-mode gpu`; it
requires CUDA and CPU providers, a GPU device, and real Umi engine-log evidence
without a fallback marker. Rapid does not accept this Paddle provider option.

The previous `win7_x64_PaddleOCR-json` plugin and Umi settings remain in the
operator's timestamped rollback copy. To restore it, stop the project-local
Umi host, replace `UmiOCR-data/plugins/win_x64_PaddleOCR_Py` with the saved
legacy directory, and restore `.settings`/`.pre_settings` before restarting.

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
Path existence and Paddle language values alone do not prove NeoEngine OCR V6:
the manifest, plugin environment, provider, model cache, and layered PDF must
all pass their respective gates.

Use both proof layers for a newly acquired runtime:

~~~powershell
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path <umi-root> --engine rapid
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py --input test_assets\test_page_scanned.pdf --output output\rapid-local-smoke\result.pdf --umiocr <umi-root>\Umi-OCR.exe --engine rapid --lang en --report output\rapid-local-smoke\report.json
~~~

The layered-PDF command is local only and must leave a readable PDF with
matching page count and extractable text. Pass `--report` to retain
machine-readable runtime/plugin/backend evidence; this is stronger evidence
than a manifest-only check. A physically GPU-free Windows machine remains the
final CPU-only portability gate.

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
page count. Before MinerU submission, every compressed segment is also checked
against its split input. Whitespace-normalized text must remain equivalent and
the ordered CJK character sequence must be unchanged. Page-count equality
alone is not sufficient because Ghostscript can preserve pages while mutating
an OCR text layer.

## Conversion Flow

~~~text
Source Document
  -> OCR Enrichment for scanned documents
  -> optional Translation Enrichment
  -> Split into Conversion Segments
  -> Compression when enabled
  -> Text-preservation validation; unsafe candidates use the split fallback
  -> MinerU upload, polling, result ZIP download, extraction
  -> Markdown normalization and image localization
  -> Final Markdown Pages
~~~

Text inputs mark OCR skipped. Scanned inputs must create a layered PDF before
splitting. Translation creates an alternating dual PDF; non-translated runs
skip that stage. State records each completion or skip decision so recovery can
avoid resubmitting completed MinerU parts.

When `--pdf-type scanned` is selected explicitly, the pipeline first checks that
the input has no extractable text layer. A text-bearing input fails before any
Umi-OCR service startup or upload, because Umi-OCR would add a second hidden
layer and MinerU could ingest both representations. Use `--pdf-type text` for
an existing text layer, or explicitly preprocess the PDF before requesting
scanned OCR. Auto-detected inputs keep the normal text-versus-scanned choice.

The BabelDOC command receives the real in-memory translation key, but coding-chong/frankensteined-pdf2md
redacts it from console output, log files, subprocess error excerpts, matrix
progress, and retained reports.

## MinerU Download Boundary

Result ZIP retrieval belongs to ocr_flow.steps.mineru. The committed chain is:

1. requests, preserving the system CA store and environment proxy policy;
2. curl, also preserving certificate and proxy policy;
3. only after those standard paths fail, an OpenXLab CDN-specific direct
   fallback that resolves a public IPv4 over HTTPS DoH and uses
   `curl --noproxy * --resolve`; hostname, SNI, certificate validation and
   HTTPS-only redirects remain required;
4. Windows .NET WebClient, preserving Windows proxy and certificate policy;
5. Windows PowerShell, preserving its normal policy.

These are alternatives for the result ZIP only. curl and PowerShell are
opportunistic Windows tools, not installation prerequisites. Never remove
global proxy variables, disable certificate validation, use `curl -k`, or add
an unverified DNS workaround. A network that needs those changes is
unsupported or `UNVERIFIED` until a separately evidenced secure design exists.

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
    compressed/
      compressed_part_*.pdf
      text_safe_part_*.pdf (only when a candidate is rejected)
      compression_validation.json
  final/
    part_001.md ...
    images/
    compressed_pdfs/
  titles_guide.md
~~~

The state file is the recovery source of truth. It records skipped optional
stages, completed MinerU segments, and failed segments. Use recovery continue,
retry, or continue_retry rather than resubmitting successful parts. The
compression step records only the selected MinerU inputs: accepted compressed
candidates or clearly named `text_safe_` split copies. Rejected Ghostscript
candidates and a credential-safe numeric validation report remain available
for diagnosis but are never reloaded as processing inputs.

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
