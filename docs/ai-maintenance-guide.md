# AI Maintenance Guide

This document is the repository-owned guide for AI maintenance work. It is
separate from `README.md`, which is written for people installing and using
OCR Flow. Do not move agent policies or internal maintenance rules into the
README.

## Read Before Changing Behavior

Use the narrowest authoritative source for the change:

| Concern | Source of truth |
| --- | --- |
| User commands, setup, and normal output | `README.md` |
| Pipeline ownership and recovery | `docs/runtime-pipeline.md` |
| Managed BabelDOC profiles and font behavior | `docs/babeldoc-runtime-profiles.md` |
| Complex-PDF release matrix | `docs/complex-pdf-live-matrix.md` |
| Executable matrix contract | Active Trellis workspace specification, when present |
| Runtime patch and profile contract | Active Trellis workspace runtime-profile specification, when present |
| Current task scope and acceptance evidence | Active Trellis task artifacts, when present |

Read the affected implementation and its existing tests before changing a
contract. Use the Trellis workflow in the workspace root for planning,
pre-development specifications, checks, spec updates, and commit review.

## Pipeline Contracts

The processing order is fixed:

```text
input -> OCR for scanned PDFs -> optional translation -> split -> optional
compression -> MinerU -> Markdown normalization -> image localization
```

- Text inputs skip UMI OCR. Scanned inputs must produce a layered OCR PDF
  before splitting.
- Translation uses the verified managed BabelDOC runtime when
  `babeldoc.path` is empty. Do not fall back to a global BabelDOC executable.
- Translated output is a dual PDF with alternating translated and source
  pages. It is retained in `intermediate/*.dual.pdf`.
- Non-translated runs use Ghostscript for split PDFs. Translated runs skip
  Ghostscript by default to preserve BabelDOC font subsetting; `--compress`
  explicitly enables it and writes parts to `final/compressed_pdfs/`.
- MinerU state and completed/failed parts live in `.state.json`. Recover a
  partial run instead of resubmitting successful parts.

## Runtime Safety

- `ocr-flow runtime setup` owns only the project-managed runtime.
- `ocr-flow runtime setup --path <checkout>` is destructive: it can discard
  tracked, staged, unstaged, and untracked files in the chosen BabelDOC
  checkout. Never run it without explicit user authorization for that path.
- Do not hand-edit a managed BabelDOC checkout. Change a versioned profile
  manifest, lock, and patch together, then validate the selected profile.
- The OCR workaround preserves source raster only for `figure` and `table`
  regions. `figure_caption` and `table_caption` remain semantic text and must
  be translated independently.

## Secrets and External Services

- Never print, commit, or paste MinerU tokens, translation keys, signed upload
  URLs, or raw credential configs.
- Use `--config <credential-config>` in examples. The live runner creates a
  sanitized temporary config and must not modify the supplied config.
- The complex-PDF matrix makes real UMI OCR, BabelDOC, Ghostscript, MinerU,
  and translation calls. It consumes API quota; run it only after the user has
  explicitly approved that cost.

## Complex PDF Validation

The fixed fixture pair is:

```text
test_assets/4_gs_prepress_300dpi.pdf
test_assets/4_gs_prepress_300dpi_scanned_300dpi.pdf
```

Use the offline checks before any service call:

```powershell
uv run python scripts/generate_complex_pdf_scan.py --verify
uv run pytest tests/test_complex_pdf_assets.py tests/test_live_matrix_validation.py -q
```

The credentialed command is deliberately separate:

```powershell
uv run python scripts/run_live_complex_pdf_matrix.py `
  --config <credential-config> `
  --profile cpu-safe
```

On Windows, use `--all-profiles` only when validating both CPU-safe and
DirectML. A passed run requires four cases per profile, 24 MinerU parts,
readable PDFs and Markdown, redacted reports, and human review of contact
sheets. Automated success alone is insufficient for formula, glyph, and
layout acceptance.

## Documentation Ownership

- Update `README.md` for a changed user command, prerequisite, output
  location, or release-facing validation summary.
- Update the matching document in `docs/` for detail that would make the
  README harder to scan.
- Update this guide for an AI-relevant ownership boundary, safety constraint,
  or validation gate.
- Keep the audiences separate. The README may link to human documentation but
  should not contain agent workflow, internal repair history, or provider
  specific instructions.

## Completion Checklist

Before presenting a change as complete:

1. Run focused offline tests for the touched behavior.
2. Run lint/type checks required by the active task.
3. Inspect `git diff --check` and verify documentation links/paths.
4. Do not stage generated output, credentials, managed runtimes, or unrelated
   local PDFs.
5. When the project is managed by Trellis, record reusable contracts in its
   workspace specifications and request one-shot commit confirmation before
   committing.
