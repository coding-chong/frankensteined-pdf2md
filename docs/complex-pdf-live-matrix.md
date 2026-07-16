# coding-chong/frankensteined-pdf2md: Complex PDF Live Matrix

This is the required real-service regression matrix for release operators and
maintainers of coding-chong/frankensteined-pdf2md. It is not part of a normal
user conversion and does not mock Umi-OCR, BabelDOC, the translation provider,
Ghostscript, or MinerU. Read [fresh-clone-setup.md](fresh-clone-setup.md) for
the installation and CPU-only Rapid preparation sequence before running
anything in this page.

## Tracked Assets and Offline Checks

The following files are Git-tracked and must arrive in every clone:

| File | Purpose |
| --- | --- |
| test_assets/4_gs_prepress_300dpi.pdf | Six-page technical paper with equations, circuits, plots, tables, and dense columns. |
| test_assets/4_gs_prepress_300dpi_scanned_300dpi.pdf | 300 DPI image-only derivative with the same page geometry. |
| test_assets/complex_pdf_matrix.json | Hashes, page geometry, scan recipe, and semantic anchors. |
| scripts/generate_complex_pdf_scan.py | Deliberate scan regeneration and verify command. |
| scripts/run_live_complex_pdf_matrix.py | Credentialed matrix runner. |
| tests/live_complex_pdf_matrix.py | Strict real-service validator. |
| tests/test_complex_pdf_assets.py | Source/scan byte, geometry, and anchor checks. |
| tests/test_live_matrix_validation.py | Offline validator and observability checks. |

Run these before any service call:

~~~powershell
uv run --locked --extra windows python scripts/generate_complex_pdf_scan.py --verify
uv run --locked --extra windows --extra dev pytest tests/test_complex_pdf_assets.py tests/test_live_matrix_validation.py -q
~~~

The verify command must report six pages and the known scanned fixture. A
passing offline suite only proves tracked inputs and validator logic; it does
not prove credentials, remote APIs, Umi-OCR, BabelDOC, or Ghostscript.

## Required Cases

One profile always runs exactly these four cases:

| Case | Input | Translation | Compression | Real services |
| --- | --- | --- | --- | --- |
| text_no_translate | Text fixture | no | pipeline default | Ghostscript, MinerU |
| scan_no_translate | Image-only scan | no | pipeline default | Umi-OCR, Ghostscript, MinerU |
| text_translate_uncompressed | Text fixture | yes | no | BabelDOC, translation API, MinerU |
| scan_translate_compressed | Image-only scan | yes | yes | Umi-OCR, BabelDOC, translation API, Ghostscript, MinerU |

Each case submits six MinerU parts. One BabelDOC profile therefore consumes
24 MinerU conversions and two translation requests. This is an API-cost gate,
not a test to run casually or as a substitute for offline pytest.

## CPU-only Rapid Run

Before the command below:

1. The user explicitly approves the 24 MinerU conversions and two translation
   requests for this profile.
2. Rapid v2.1.5 passes both the selected manifest and layered-PDF local smoke.
3. BabelDOC cpu-safe setup and smoke pass.
4. Ghostscript is a real executable that has passed a local compression smoke.

Use cpu-safe plus an explicit Rapid executable and engine:

~~~powershell
$credentialConfig = "$env:USERPROFILE\.ocr-flow\config.toml"
$umiRoot = "C:\Tools\Umi-OCR_Rapid_v2.1.5"
uv run --locked --extra windows --extra dev python scripts/run_live_complex_pdf_matrix.py --config $credentialConfig --ghostscript "C:\path\to\gswin64c.exe" --umiocr "$umiRoot\Umi-OCR.exe" --umiocr-engine rapid --profile cpu-safe --output output\live_complex_pdf_matrix
~~~

The runner reads the credential config but never modifies it. It creates a
temporary isolated config, clears babeldoc.path, carries the selected
umiocr.engine into that config, and selects the managed cpu-safe runtime. A
Rapid executable without --umiocr-engine rapid would otherwise inherit the
source config engine, so the explicit flag is required for a portable Rapid
override.

CPU-only machines must not use --all-profiles. That option runs both cpu-safe
and Windows DirectML, is Windows-only, and doubles the remote service work.
Use it only for an explicitly approved DirectML release check.

## Retained Evidence and Human Review

The default retained directory is:

~~~text
output/live_complex_pdf_matrix/<timestamp>/
~~~

It contains one directory per profile and case, with:

- runner-summary.json;
- .state.json for exact stage state and completed MinerU parts;
- OCR, translated, split, and compressed PDFs;
- final Markdown for all six parts;
- live-matrix-report.json without credentials;
- live-progress.log with redacted subprocess output;
- visual_review PNG contact sheets.

The automated validator checks state transitions, page/part counts, readable
PDFs, Markdown anchors, CJK composite fonts, formula markers, Ghostscript size
reduction, OCR text, oversized short OCR spans, noisy bottom-margin spans,
caption text, and source-ink loss in technical regions. It also verifies
cpu-safe restoration after a DirectML run.

After success, a person must still inspect every contact sheet and the
corresponding PDFs:

1. Formula pages preserve both equations, including CSC and RSC expressions.
2. Scanned pages retain source raster and expose usable OCR text.
3. Translated pages use readable Chinese glyphs without missing-font boxes.
4. Layout has no giant OCR glyph, blank region, collision, or clipped text.
5. Compressed pages retain the expected content and readable page count.

Exit code zero is not sufficient evidence. A failed run must keep its reports,
state, PDFs, Markdown, and contact sheets for diagnosis; never hide a failed
service prerequisite behind a skip or mock result.
