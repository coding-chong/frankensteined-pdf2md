# Complex PDF Live Matrix

This is the required real-service regression matrix for OCR Flow. It does not
mock UMI OCR, BabelDOC, the translation provider, Ghostscript, or MinerU.

## Assets

The matrix uses the following fixed fixtures:

- `test_assets/4_gs_prepress_300dpi.pdf`: six-page technical paper with
  equations, circuit diagrams, plots, tables, and dense two-column text.
- `test_assets/4_gs_prepress_300dpi_scanned_300dpi.pdf`: a 300 DPI,
  image-only derivative with no text layer.
- `test_assets/complex_pdf_matrix.json`: hashes, page geometry, scan recipe,
  and semantic anchors.

Verify assets without calling any API:

```powershell
uv run python scripts/generate_complex_pdf_scan.py --verify
uv run pytest tests/test_complex_pdf_assets.py -v
```

Regenerate the scan only when deliberately updating the fixture:

```powershell
uv run python scripts/generate_complex_pdf_scan.py --write --verify
```

## Required Live Run

Use an existing OCR Flow credential config. The runner reads it but never
modifies it. It creates a temporary config for the live run with an empty
`babeldoc.path`, so a stale or custom external checkout cannot replace the
verified managed BabelDOC runtime.

```powershell
uv run python scripts/run_live_complex_pdf_matrix.py `
  --config "$env:USERPROFILE\.ocr-flow\config.toml" `
  --ghostscript "C:\path\to\gswin64c.exe" `
  --profile cpu-safe
```

On Windows, validate both BabelDOC profiles:

```powershell
uv run python scripts/run_live_complex_pdf_matrix.py `
  --config "$env:USERPROFILE\.ocr-flow\config.toml" `
  --ghostscript "C:\path\to\gswin64c.exe" `
  --all-profiles
```

The runner fails, rather than skips, when a configured credential, UMI OCR
executable, Ghostscript executable, managed BabelDOC profile, or API call is
not usable. It never changes a user-supplied BabelDOC Git checkout.
Omit `--ghostscript` only when `compress.ghostscript_path` or automatic
discovery already resolves a verified Ghostscript executable.

One profile runs four cases:

| Case | Input | Translation | Compression | Real services |
| --- | --- | --- | --- | --- |
| `text_no_translate` | text fixture | no | pipeline default | Ghostscript, MinerU |
| `scan_no_translate` | image-only scan | no | pipeline default | UMI OCR, Ghostscript, MinerU |
| `text_translate_uncompressed` | text fixture | yes | no | BabelDOC, translation API, MinerU |
| `scan_translate_compressed` | image-only scan | yes | yes | UMI OCR, BabelDOC, translation API, Ghostscript, MinerU |

Each case creates six MinerU parts. One profile therefore consumes 24 MinerU
conversions and two translation requests. `--all-profiles` doubles that work.

## Acceptance Evidence

The default retained output directory is
`output/live_complex_pdf_matrix/<timestamp>/`. It contains one directory per
profile and case, including:

- `.state.json` with the exact stage states and completed MinerU parts;
- OCR, translated, split, and compressed PDFs;
- final Markdown from every MinerU part;
- `live-matrix-report.json` without credentials;
- `live-progress.log`, which streams redacted subprocess progress during the
  run and remains available for diagnosis afterward;
- `visual_review/*.png` contact sheets.

The runner uses pytest output passthrough, so this progress is visible on the
terminal as well as in the retained log. It redacts configured MinerU and
translation credentials before either destination receives a line.

Review every contact sheet after a successful run:

1. Formula pages must show both equations, including the `CSC` / `RSC`
   expressions, without blank regions or overlap.
2. OCR pages must preserve the scanned page visually and have a usable text
   layer containing the paper title/topic terms.
3. Translated pages must show readable Chinese glyphs with no missing-font
   boxes, while the original/formula pages retain their content.

The runner also enforces page counts, OCR text recognition, CJK text and
composite font resources, formula markers in Markdown, readable PDF
intermediates, Ghostscript size reduction, and MinerU completion. For every
translated case it validates both the BabelDOC dual-page PDF and the
post-Ghostscript PDFs. It rejects oversized short OCR spans (the signature of
the previously observed giant black glyph) and compares source-ink coverage in
fixed formula, circuit, and plot regions on pages 3 and 5. The report records
those metrics and the contact-sheet paths. Visual inspection remains
mandatory because a structurally valid PDF can still have poor typography or
formula layout.
