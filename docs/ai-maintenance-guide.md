# coding-chong/frankensteined-pdf2md: AI Maintenance Guide

This is repository-owned maintenance documentation. It is intentionally
separate from README.md, which is for people installing and using
coding-chong/frankensteined-pdf2md.
Do not create or track vendor-specific assistant instruction files as a
substitute for this document.

## Required Reading Order

Read in this order before changing behavior or deployment documentation:

1. README.md for the human entry point and command convention.
2. docs/fresh-clone-setup.md for Windows clone, external dependencies,
   CPU-only Rapid, and remote-cost boundaries.
3. docs/runtime-pipeline.md for stage ownership, output, recovery, and
   MinerU download boundaries.
4. docs/babeldoc-runtime-profiles.md for v0.6.3 runtime/profile constraints.
5. docs/complex-pdf-live-matrix.md for fixture, live-service, and visual
   validation contracts.
6. Active Trellis task artifacts and workspace specifications, when present.
7. The implementation and focused tests named in the ownership table below.

README is the canonical complete human workflow. The fresh-clone guide owns
the detailed new-machine, CPU-only Rapid, acquisition, and diagnostic
extension. Keep shared commands aligned; do not create a competing installation
sequence in a subsystem document or treat either page as a replacement for the
other.

## Source Ownership Index

| Concern | Owning code | Focused tests or verification |
| --- | --- | --- |
| Persisted Umi-OCR engine and language mapping | ocr_flow/config.py | tests/test_config.py |
| OCR upload payload and selected document language | ocr_flow/steps/ocr.py and ocr_flow/pipeline.py | tests/test_ocr.py and tests/test_pipeline.py |
| Running Umi-OCR service options/readiness | ocr_flow/self_check.py | tests/test_self_check.py |
| Umi-OCR engine manifests | ocr_flow/runtime.py and ocr_flow/runtime_profiles | tests/test_runtime_profiles.py and verify_umiocr_runtime.py |
| Credential-free layered PDF proof | scripts/validate_umiocr_layered_pdf.py | tests/test_umiocr_validation.py plus a real local run |
| BabelDOC runtime version, patch, and profile state | ocr_flow/babeldoc_runtime.py and ocr_flow/runtime.py | tests/test_runtime_profiles.py and runtime smoke |
| MinerU result ZIP retrieval | ocr_flow/steps/mineru.py | tests/test_mineru.py; real CDN success is a separate live fact |
| Markdown image localization | ocr_flow/steps/image_download.py | tests/test_image_download.py |
| Complex matrix orchestration | scripts/run_live_complex_pdf_matrix.py and tests/live_complex_pdf_matrix.py | tests/test_complex_pdf_assets.py and tests/test_live_matrix_validation.py |
| Human onboarding content | README.md and docs/fresh-clone-setup.md | Markdown link and command/reference checks |

## Umi-OCR Contract

UmiOcrConfig has an explicit engine. Only paddle and rapid are supported.
Missing engine remains paddle for backward compatibility. Do not add a third
engine by adding an unchecked string value; update the central validation,
mapping, manifest selection, readiness check, matrix isolated config, tests,
and documentation together.

| Engine | English document value | Chinese document value | Manifest |
| --- | --- | --- | --- |
| paddle | models/config_en.txt | models/config_chinese.txt | umiocr-paddle-neoengine-v1.4.json |
| rapid | English | 简体中文 | umiocr-rapid-v2.1.5.json |

GET /api/doc/get_options is the runtime truth. A file manifest proves that the
chosen executable/plugin files match an expected release; it does not prove
that the currently running process at the configured URL is that engine.
Read the options response before upload and reject a language mismatch.

Rapid CPU-only acceptance requires both:

~~~powershell
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path <rapid-root> --engine rapid
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py --input test_assets\test_page_scanned.pdf --output <local-output.pdf> --umiocr <rapid-root>\Umi-OCR.exe --engine rapid --lang en
~~~

The local output must have matching page count and extractable text. A mocked
options response or a unit test never replaces the real layered-PDF result.

The default Paddle manifest is the project-local `chapterv/umi-paddle-neoengine`
plugin, version 1.4 at commit
`e1acb9d22a8b4f343cd0c6d18dec694d809d02e7`, using ONNX Runtime CPU. Its dynamic
readiness boundary is the plugin-local Python environment plus the cached
`PP-OCRv6_medium_det_onnx` and `PP-OCRv6_medium_rec_onnx` models:

~~~powershell
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py `
  --path <umi-root> --engine paddle --check-environment
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py `
  --input test_assets\true_scanned_test.pdf `
  --output <local-output.pdf> --umiocr <umi-root>\Umi-OCR.exe `
  --engine paddle --lang en --timeout 21600 --report <report.json>
~~~

The old `win7_x64_PaddleOCR-json` plugin is retained outside the active
directory in the task's timestamped rollback artifact. Do not delete it while
diagnosing a failed upgrade; restore it together with the saved Umi settings
only when an explicit rollback is required. The paid MinerU/translation matrix
is a separate gate and is not implied by this local OCR evidence.

## Fresh Clone and External Boundaries

The repository tracks source, uv.lock, .python-version, manifests, tests,
fixture PDFs, and documentation. It deliberately does not track:

- user credentials, API_KEYS.md, or credential configs;
- vendor Umi-OCR binaries and project-local umiocr_local;
- .venv, managed BabelDOC checkout, output, build artifacts, or egg-info;
- local PDFs, temporary clones, historical handoffs, and unrelated WIP;
- vendor-specific assistant files.

New-machine setup must use checkout-root commands:

~~~powershell
uv python install 3.13.12
uv sync --locked --extra windows --extra dev
uv lock --check
uv run --locked --extra windows ocr-flow --help
~~~

pythonnet is a locked Windows extra used only for the .NET WebClient fallback
when MinerU result-ZIP retrieval fails after requests and curl. It is not a
general proxy package. PySocks is neither imported nor locked and must not be
introduced into installation instructions without a separately justified code
path and lock update.

MinerU has two separate data flows:

1. Result ZIP retrieval preserves system CA validation. Standard requests,
   curl, .NET WebClient, and PowerShell inherit proxy policy. A final
   OpenXLab-only direct fallback may resolve a global IPv4 through HTTPS DoH
   and use `curl --resolve`; it must preserve hostname/SNI validation, restrict
   redirects to HTTPS, and never log the signed URL or resolved address.
2. Markdown image localization copies local extracted assets first, then
   downloads only remote HTTP image URLs.

Do not treat mock coverage as proof for a public-DNS, proxy, or CDN workaround.
A successful mock test is only a command-construction contract; support needs
a real matrix where standard methods fail and the secure fallback succeeds.
Never accept `verify=False`, `curl -k`, TrustAll callbacks, or removed proxy
variables as a compatibility fix. A network that cannot complete with valid
certificates must fail early and remain unsupported or `UNVERIFIED` pending a
separately evidenced secure design.

## Deployment Diagnostic Contract

`ocr_flow/deployment.py` owns the typed, read-only result model used by
`ocr-flow doctor --deployment [--json <path>]`. Check IDs and schema version
are public support APIs. The CLI renders them but must not duplicate verdict,
redaction, or secret-scan logic. Existing doctor modes remain compatible.

Deployment checks may perform temporary create/write/rename/delete probes in
the selected directories and local HTTP readiness reads. They must remove
their probe files, consume no provider quota, start no service, install no
runtime, change no global proxy/security policy, and upload no report. Evidence
uses path categories, presence-only credentials, versions, booleans, and
resource counts; never pass raw runtime messages into JSON because those may
contain user paths or commands.

The supported baseline is unified. A standard Windows user must complete all
normal workflows and the four-case CPU/Rapid matrix with 24 MinerU parts, two
translations, retained evidence, secret scan, and human visual review.
Portable Ghostscript is the replaceable no-admin path. Different Windows
kernels, physical no-GPU hardware, real EDR, enterprise TLS inspection, and
genuine low-memory hardware stay `UNVERIFIED` until exercised. Never convert
an `UNVERIFIED` result into compatibility language based on mocks or one host.

## CPU-only BabelDOC and Matrix Contract

cpu-safe is the only profile named in CPU-only documentation and commands.
It must not select DirectML or CUDA. windows-directml is explicit optional
acceleration and must not be selected by inference from host hardware.

The live matrix receives a sanitized temporary config. An explicit Umi-OCR
executable override must be paired with the intended engine override so its
isolated config cannot silently retain Paddle. The CPU/Rapid command uses:

~~~powershell
uv run --locked --extra windows --extra dev python scripts/run_live_complex_pdf_matrix.py --config <credential-config> --ghostscript <gswin64c.exe> --umiocr <rapid-root>\Umi-OCR.exe --umiocr-engine rapid --profile cpu-safe
~~~

The four cases are text_no_translate, scan_no_translate,
text_translate_uncompressed, and scan_translate_compressed. One profile makes
24 MinerU conversions and two translation requests. Request explicit user
approval immediately before this command; do not infer approval from a prior
offline test or a prior profile run.

Success requires retained state, Markdown, readable PDFs, redacted report,
progress log, contact sheets, and human visual inspection. A green pytest exit
alone is insufficient for formulas, OCR text layers, Chinese glyphs, layout,
or compressed content.

## Documentation Ownership

When behavior changes:

- Update README.md if a human's first command, prerequisite, or high-level
  output expectation changes.
- Update docs/fresh-clone-setup.md for ordered installation, acquisition,
  version, location, verification, remediation, CPU-only, or cost changes.
- Update docs/runtime-pipeline.md for pipeline boundaries, output, recovery,
  config/engine, or MinerU/image ownership changes.
- Update docs/complex-pdf-live-matrix.md for fixture, case, command, cost,
  retained evidence, or visual acceptance changes.
- Update this guide for implementation ownership, AI-maintainer safety, or
  required validation changes.
- Update the applicable Trellis specification after the behavior is verified.

Keep commands checkout-root, locked uv commands. Keep token paths and values
as placeholders. Never add a claim that a vendor runtime, provider, or network
path works unless the corresponding real validation evidence exists.

## Completion Gate

Before commit or push:

1. Run focused tests for changed runtime/config/document behavior.
2. Run fixture verify mode after changing assets or matrix contracts.
3. Run targeted lint/type checks and record pre-existing baseline failures
   separately from newly introduced failures.
4. Check links, stale dependency instructions, Git scope, and diff whitespace.
5. Run the Trellis quality workflow and update the reusable specification.
6. Review staged paths. Do not stage credentials, vendor binaries, output,
   local WIP, or unrelated dirty files.
7. For paid matrix work, stop for a fresh explicit quota approval before
   execution; for push, require the user authorization already in scope.
