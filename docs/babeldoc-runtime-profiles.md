# coding-chong/frankensteined-pdf2md: BabelDOC Runtime Profiles

coding-chong/frankensteined-pdf2md owns the default BabelDOC Runtime used by Translation Enrichment. A
normal user only needs the commands in Normal Setup; external checkouts and
DirectML are advanced operator operations. A normal user does not clone
BabelDOC, configure an absolute path, or patch backend source. The supported
runtime is BabelDOC `v0.6.3` at
`28f784ca6b437dbba040bfd9c67110373cd0924b`, installed below the checkout at:

```text
.ocr-flow-runtime/BabelDOC
```

The runtime directory is ignored by Git. Its source URL, revision, lock-file
digest, provider-file blobs, and optional patch are in
`ocr_flow/runtime_profiles/babeldoc-v0.6.3.json`. These profile assets are
included in the built `ocr_flow` wheel, so a non-editable installation uses the
same manifest, lock, and DirectML patch as a source checkout.

## Normal Setup

From a coding-chong/frankensteined-pdf2md checkout after its Python environment is available:

```powershell
uv run --locked --extra windows ocr-flow runtime setup
uv run --locked --extra windows ocr-flow runtime smoke --input test_assets\test_page_text.pdf
uv run --locked --extra windows ocr-flow runtime status
```

`setup` clones the canonical HTTPS upstream source when the managed checkout
is absent. On every invocation it cleans the project-managed runtime directory,
force-checks out the exact pinned revision, copies the profile-owned lock file,
runs `uv sync --locked`, verifies the BabelDOC CLI, and records a local setup
marker. A prior managed branch, version, DirectML patch, or generated file is
therefore discarded before the selected profile is installed. It never edits a
user-maintained external checkout unless that checkout is explicitly passed to
`--path`.

When CPU-safe setup follows a DirectML setup, it also reinstalls the locked
generic `onnxruntime` package. The CPU and DirectML distributions share Python
module paths, so ordinary dependency metadata alone is not enough to prove the
generic runtime files survived the provider switch.

Translation Enrichment resolves this verified managed runtime by default and
invokes it using its own `uv run --locked` environment. It never falls back to
a global `babeldoc` executable. Before setup it fails with the actionable
command above.

`ocr-flow runtime status` reports the runtime from the most recent successful
setup marker and queries canonical upstream tags without changing any checkout.
A newer upstream release is advisory only: it becomes the default only after
coding-chong/frankensteined-pdf2md pins its commit, regenerates the profile lock, reviews any patch,
passes CPU and DirectML smoke tests, and passes a translated API smoke
conversion.

## Existing Git Checkout (Destructive)

An existing BabelDOC Git checkout can be used only through this explicit
normalization command:

```powershell
uv run --locked --extra windows ocr-flow runtime setup --path C:\work\BabelDOC
uv run --locked --extra windows ocr-flow runtime smoke --path C:\work\BabelDOC --input test_assets\test_page_text.pdf
```

`runtime setup --path` is destructive: it requires the supplied path to be the
Git worktree root, obtains the pinned `v0.6.3` commit from canonical upstream
when necessary, runs `git clean -fd`, removes the prior profile lock, and force
checks out `28f784ca6b437dbba040bfd9c67110373cd0924b` in detached HEAD state.
Tracked, staged, unstaged, and untracked work in that supplied checkout is
discarded. No other BabelDOC checkout is touched.

After successful setup, configure that exact checkout for Translation
Enrichment:

```toml
[babeldoc]
path = "C:/work/BabelDOC"
```

The configuration path is accepted only when it exactly matches the recorded
setup marker, pinned revision, selected profile, source-patch state, and
profile lock. An unprepared or changed path fails with
`ocr-flow runtime setup --path <checkout>` guidance; it never falls back to
the managed or global executable. Omit `babeldoc.path` to use the managed
default.

## Windows DirectML Opt-In

CPU-safe is the default. On a Windows machine where the user has chosen and
tested DirectML, install the explicit profile:

```powershell
uv run --locked --extra windows ocr-flow runtime setup --profile windows-directml
uv run --locked --extra windows ocr-flow runtime smoke --profile windows-directml --input test_assets\test_page_text.pdf
```

The profile installs the locked `directml` extra, reinstalls
`onnxruntime-directml==1.24.4` into the BabelDOC environment, and applies a
revision-locked patch to *layout* provider selection only. It enables
`DmlExecutionProvider` with CPU fallback and keeps CUDA disabled.

BabelDOC 0.6 retired the RapidOCR table detector. The old v0.5 table DirectML
patch is deliberately not carried forward: the smoke test requires DirectML
layout inference and asserts that the retired table detector returns no boxes.
This profile is performance-only, Windows-only, and never the implicit default.

The same explicit profile applies to an existing Git checkout:

```powershell
uv run --locked --extra windows ocr-flow runtime setup --path C:\work\BabelDOC --profile windows-directml
uv run --locked --extra windows ocr-flow runtime smoke --path C:\work\BabelDOC --profile windows-directml --input test_assets\test_page_text.pdf
```

The CPU-safe profile leaves the pinned upstream source unmodified. Only the
Windows DirectML profile applies the revision-locked layout patch.

## Runtime Selection

coding-chong/frankensteined-pdf2md supports exactly one BabelDOC version: the tested `v0.6.3` profile.
`babeldoc.path` is not a version override. It only selects an external Git
checkout that `runtime setup --path` has already forced to that version and
verified. The configuration wizard preserves this explicit path and reminds
the user to run setup before translation.

```toml
[babeldoc]
primary_font_family = "serif" # optional: serif, sans-serif, script, or empty
```

## Fonts

`primary_font_family` maps to BabelDOC's public
`--primary-font-family serif|sans-serif|script` option. Omitting it preserves
BabelDOC automatic selection based on source text style.

This is a family preference, not an exact font-file selector. BabelDOC owns
the exact font map, which includes output language, weight, italic state, and
glyph fallbacks. A specific font face requires a new versioned BabelDOC Runtime
Profile with the asset and font-map changes recorded and a translated-PDF
validation. Do not make a hand edit in a shared checkout.

## UMI OCR Runtime

UMI OCR is separate from BabelDOC. A scanned Conversion Run discovers
`umiocr_local` first and starts its bundled Python launcher automatically. It
can be verified with:

```powershell
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path umiocr_local
uv run --locked --extra windows ocr-flow doctor --ocr --start-ocr
```

The UMI manifest verifies its executable, launcher, and English/Chinese model
configurations; it does not treat a large vendor binary as an undocumented
source fork.

### CPU-only Rapid Runtime

The Paddle command above selects the backward-compatible default manifest. It
does not validate Rapid. A CPU-only Windows host must use the separate Rapid
v2.1.5 manifest and service contract:

~~~powershell
uv run --locked --extra windows python scripts/verify_umiocr_runtime.py --path C:\Tools\Umi-OCR_Rapid_v2.1.5 --engine rapid
uv run --locked --extra windows python scripts/validate_umiocr_layered_pdf.py --input test_assets\test_page_scanned.pdf --output output\rapid-local-smoke\result.pdf --umiocr C:\Tools\Umi-OCR_Rapid_v2.1.5\Umi-OCR.exe --engine rapid --lang en
~~~

Rapid accepts English and 简体中文 through the document API, whereas Paddle
uses model path values. The config engine field and GET /api/doc/get_options
readiness check prevent the two values from being interchanged. This Umi-OCR
contract is independent of BabelDOC: Rapid performs scanned OCR; cpu-safe
BabelDOC performs translation layout inference without DirectML.
