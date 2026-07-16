# coding-chong/frankensteined-pdf2md: Historical Managed BabelDOC Runtime Handoff

## Purpose

Continue the active Trellis task
`../.trellis/tasks/07-11-frankensteined-pdf2md-dependency-pipeline` from the
managed BabelDOC Runtime upgrade and finish its quality gate. The task PRD,
design, plan, upstream review, audit, and prior asset report are the source of
record; do not recreate them here.

## Current Outcome

- coding-chong/frankensteined-pdf2md now has an implemented, uncommitted BabelDOC `v0.6.3` managed
  runtime design. It owns `.ocr-flow-runtime/BabelDOC`; a normal user does not
  need an existing BabelDOC checkout or `babeldoc.path`.
- `ocr-flow runtime setup`, `status`, and `smoke` have been added. The default
  profile clones canonical HTTPS upstream, checks out the exact tested commit,
  copies the profile-owned lock, synchronizes with `uv --locked`, and writes a
  local state marker. `status` checks upstream tags without changing anything.
- `babeldoc.path` is intentionally retained only as an advanced explicit
  override. A stale configured override is reported instead of silently
  falling back to a global executable. The current user configuration has such
  a stale override; it was not edited.
- BabelDOC `v0.6.3` was verified as the current canonical upstream release at
  commit `28f784ca6b437dbba040bfd9c67110373cd0924b`.

## Evidence From This Session

- Fresh managed CPU setup completed in
  `.ocr-flow-runtime/BabelDOC`; the runtime reported `babeldoc 0.6.3`.
- CPU smoke on `test_assets/test_page_text.pdf` passed:
  `CPUExecutionProvider`, one layout result, zero table boxes. Zero table
  boxes is expected because BabelDOC 0.6 retired the RapidOCR table detector.
- The isolated `windows-directml` profile passed in
  `.babeldoc-v063-evaluation`: `DmlExecutionProvider, CPUExecutionProvider`,
  one layout result, zero table boxes. Its only source patch is layout-provider
  selection; the former v0.5 table DirectML modification was not carried over.
- Focused tests passed: `87 passed` for runtime, CLI, profile, translation,
  self-check, and CLI test modules. Python compilation passed.
- A real managed-v0.6.3 Translation Enrichment run used
  `test_assets/test_page_text.pdf`. BabelDOC produced both bilingual and mono
  PDFs, and MinerU upload/polling advanced to result download. The command log
  redacted the API key.
- That run's MinerU CDN download failed externally with TLS EOF/connection
  closure across requests, curl, and .NET fallback. State correctly records
  `mineru=partial`; output is retained at
  `output/trellis_v063_managed_live/20260711_151317/test_page_text/`.

## Important Pending Work

1. Fix the pipeline result contract discovered in the live run: when every
   MinerU segment fails, `pipeline.py` currently saves `mineru=partial` but
   continues through post-processing and prints success. Preserve recovery
   state, but raise an actionable error when `failed` is nonempty and no
   segment completed. Add a targeted regression in `tests/test_pipeline.py`.
2. Update the Trellis runtime-profile specification at
   `../.trellis/spec/ocr-flow/backend/runtime-profiles.md`. It still describes
   v0.5.24 and requires a now-retired DirectML table detector. Align it with
   the managed v0.6.3 contract and the layout-only DirectML smoke rule.
3. Update the task validation report at
   `../.trellis/tasks/07-11-frankensteined-pdf2md-dependency-pipeline/validation.md`
   with the v0.6.3 setup/smoke evidence and the external CDN download failure.
   Keep the prior successful asset evidence, but do not claim the new live run
   completed Markdown conversion.
4. Run the full OCR Flow test suite and the Trellis check after the pipeline
   fix. Re-run the one-page translated job only if the external MinerU CDN is
   reachable; do not hide a repeated external TLS failure.
5. Review all dirty files before any commit. The worktree includes many
   pre-existing user/generated files. Do not reset, discard, or commit them
   without explicit classification and the required Trellis confirmation.
6. After all DirectML checks are complete, remove the task-owned evaluation
   worktree via the owning `other_BabelDOC` repository's `git worktree remove`
   command. Do not touch the user-owned `BabelDOC` checkout.

## Key Implementation Paths

- Managed resolution: `ocr_flow/runtime.py`
- Runtime lifecycle and upstream tag check: `ocr_flow/babeldoc_runtime.py`
- Backward-compatible script wrapper: `scripts/babeldoc_runtime.py`
- Profile and lock: `ocr_flow/runtime_profiles/babeldoc-v0.6.3.json` and
  `ocr_flow/runtime_profiles/babeldoc-v0.6.3.uv.lock`
- Layout-only DirectML patch:
  `ocr_flow/runtime_profiles/patches/babeldoc-v0.6.3-windows-directml.patch`
- User commands: `ocr_flow/cli.py`
- Translation command/runtime boundary: `ocr_flow/steps/translate.py`
- Operator documentation: `docs/babeldoc-runtime-profiles.md` and
  `docs/runtime-pipeline.md`

The old v0.5 profile and patch were removed from `ocr_flow/runtime_profiles/`. Existing
user source changes in the workspace `BabelDOC` checkout were not edited.

## Superseding External-Checkout Requirement

After this handoff, an explicitly supplied
`ocr-flow runtime setup --path <BabelDOC-git-root>` is authorized to normalize
that user checkout destructively. It fetches or verifies the pinned v0.6.3
commit, discards tracked, staged, unstaged, and untracked work, force-checks
out the detached revision, installs the selected profile, and records the
verified path. CPU-safe leaves the source upstream-clean; Windows DirectML
alone applies the layout patch. This supersedes the earlier preservation rule
only for the checkout explicitly supplied to `--path`; all other user
checkouts remain out of scope.

## Suggested Skills

- `$trellis-continue`: restore the current task and phase before editing.
- `$trellis-before-dev`: reload affected backend guidance before the pipeline
  fix or spec-aligned code edits.
- `$trellis-check`: run the required implementation quality gate after tests.
- `$trellis-update-spec`: capture the final v0.6.3 managed-runtime contract.
- `$domain-modeling`: retain the distinction between a Managed BabelDOC Runtime
  and an advanced external override.
