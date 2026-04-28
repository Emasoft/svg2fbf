# TRDD-c2a3199d — Docker E2E test for deterministic text→path rendering

**TRDD ID:** `c2a3199d-f7ec-47b6-983b-51f7fa57a713`
**Filename:** `design/tasks/TRDD-c2a3199d-f7ec-47b6-983b-51f7fa57a713-text2path-docker-e2e.md`
**Tracked in:** this repo (design/tasks/ is git-tracked)
**Status:** Approved (rev 3 — threshold relaxed, calibration loop added)

## Goal

Add a deterministic Docker E2E test that proves svg2fbf's `--text2path`
conversion (auto-installing Bun + using bundled `svg-text2path`/HarfBuzz)
renders text correctly across an animation sequence, so future changes to
the text→path pipeline cannot silently regress text rendering.

## Toolchain (revision 2 — Emasoft tools only)

All rendering, bbox computation, and visual comparison goes through tools
authored in this account:

| Tool | Provider | Role in the test |
|---|---|---|
| **svg-bbox** (npm: `svg-bbox`) | `Emasoft/SVG-BBOX` | Provides `sbb-svg2png` (Chrome-based renderer, accurate text), `sbb-compare` (pixel diff with optional diff-image output), `sbb-extract` (extract by id), `sbb-getbbox` (visual bbox). |
| **svg-text2path** (PyPI: `svg-text2path`) | `Emasoft/svg-text2path` | Already a runtime dep of svg2fbf and what `--text2path` invokes. Also exposes `text2path compare --pixel-perfect` (wraps `sbb-compare`). |
| **svg-matrix-python** (PyPI: `svg-matrix`) | `Emasoft/svg-matrix-python` | Provides `psvglinter` for SVG validation, `psvgfonts` for font reporting. Replaces `xmllint` in the new tests. |
| **SVG-MATRIX** (npm) | `Emasoft/SVG-MATRIX` | Underlying Node toolkit that `svg-matrix-python` wraps; pulled in transitively. |

Explicitly **not** used: `librsvg2-bin`, `imagemagick compare`, `xmllint`
(except where it already exists in the run_tests.sh harness for legacy
tests). No third-party renderer touches the new test.

## What "deterministic" means here

1. The Docker image pre-installs an exact, well-known set of fonts via
   `apt` so `svg-text2path`'s HarfBuzz shaper has the exact metrics it
   expects — no fontconfig fall-through.
2. Input fixture SVG frames reference those fonts BY EXACT FAMILY NAME
   and STYLE (`font-family="DejaVu Sans"`, `font-weight="700"`, etc.).
3. Frame fixtures are produced by a checked-in deterministic Python
   generator (any pseudo-random positioning seeded with a fixed integer).
4. The output is verified two ways:
   - **Byte-exact** match against a checked-in golden FBF.
   - **Per-frame visual diff** via `sbb-svg2png` (Chrome rendering) +
     `sbb-compare` (pixel-by-pixel) between the input frame and the
     extracted FBF frame.

## Font selection

| apt package | Family | Weight | Style |
|---|---|---|---|
| `fonts-dejavu` | DejaVu Sans | 400 | normal |
| `fonts-dejavu` | DejaVu Sans | 700 | bold |
| `fonts-dejavu` | DejaVu Serif | 400 | normal |
| `fonts-liberation` | Liberation Mono | 400 | normal |

All are ubiquitous Latin-script fonts shipped in every major Linux distro,
with stable metrics across releases. No Arabic, no symbols, no display
faces.

## Fixture frames

5 frames, 200×200 viewBox, white background. Per frame:

- 1 white `<rect width="200" height="200" fill="#ffffff">` background
- 1 `<defs>` with a curved `<path id="curve_N">` (curvature varies
  per frame so the textPath visibly animates)
- 4 `<text>` elements:
  - DejaVu Sans 400, `transform="translate(x,y) rotate(deg)"`, content "Hello"
  - DejaVu Sans 700, scaled via `transform`, content "World"
  - DejaVu Serif 400, rotated −15°, content "svg2fbf"
  - Liberation Mono 400, content "frame N"
- 1 `<text>` containing a `<textPath xlink:href="#curve_N">` with content
  "Animation along curve" using DejaVu Sans 400.

Per-frame placement and rotation are computed deterministically from
`random.seed(42)` plus `frame_index` so positions move smoothly across
the 5 frames. The generator script and all 5 SVG outputs are committed.

## Files added

| Path | Purpose |
|---|---|
| `tests/fixtures/e2e/text_frames/generate_frames.py` | Deterministic generator (seeded). Emits frame00001.svg…frame00005.svg into the same dir. Idempotent. |
| `tests/fixtures/e2e/text_frames/frame00001.svg` … `frame00005.svg` | Generated fixtures (committed). |
| `tests/fixtures/e2e/text_frames/expected.fbf.svg` | Golden FBF output (committed). |
| `tests/fixtures/e2e/text_frames/COMMAND.txt` | Records the exact `svg2fbf` invocation used to produce the golden. |
| `scripts/regen_text_e2e_reference.sh` | Regenerates the golden when fonts or svg-text2path versions bump. Mirrors `regen_e2e_reference.sh`. |
| `scripts/extract_fbf_frame.py` | Helper called inside the Docker test: extracts `<g id="FRAMENNNNN">` from an FBF.svg and wraps it in a minimal SVG document with the same viewBox + white background. Pure stdlib (xml.etree). |

## Files modified

`scripts/test_release_clean.sh` — Dockerfile + `run_tests.sh`.

### Dockerfile changes
- Append to apt-get install: `fonts-dejavu fonts-liberation`.
- COPY the 5 text fixtures and `expected.fbf.svg` into
  `/test/tests/fixtures/e2e/text_frames/`.
- COPY `scripts/extract_fbf_frame.py` into `/test/`.
- **Do not** install Node.js / svg-bbox in the Dockerfile — the
  verification harness (svg-bbox CLI) is installed by `run_tests.sh`
  AFTER the existing T6 test (`svg2fbf --auto-repair-viewbox bootstraps
  Node+Puppeteer`). That test bootstraps Node.js as a side effect, so by
  the time the new tests run we already have `npm` available without
  contaminating the "minimal image" property the existing tests rely on.

### run_tests.sh — new test cases (placed AFTER the existing E2E byte-exact test)

**T_setup: bootstrap verification harness**
- `npm install -g svg-bbox svg-matrix` (Node and npm exist after T6).
- Sanity: `which sbb-svg2png && which sbb-compare && which sbb-extract && which psvglinter`.

**T11: `svg2fbf --text2path bootstraps Bun and converts text → paths`**
- Pre-condition: `which bun` is empty (clean state for this test).
- Run: `svg2fbf -i tests/fixtures/e2e/text_frames -o /tmp/text-out --no-browser --skip-date --text2path -s 2.0 -a once -d 6 -c 6 -q`
- Post-conditions:
  - exit code 0
  - `which bun` now returns a path (Bun auto-install path was exercised)
  - `/tmp/text-out/animation.fbf.svg` exists
  - `psvglinter --errors-only /tmp/text-out/animation.fbf.svg` returns 0
  - The FBF output contains zero `<text` elements (every `<text>` was converted)
  - The FBF output contains many `<path` elements

**T12: `text fixture E2E byte-exact (text2path mode)`**
- Same command as T11.
- `cmp` the generated FBF against
  `tests/fixtures/e2e/text_frames/expected.fbf.svg`.
- On mismatch surface a `diff | head -30`.

**T13: `text rendering frame-by-frame visual diff (sbb-svg2png + sbb-compare)`**
- For each `frame00001.svg` … `frame00005.svg`:
  1. `python3 /test/extract_fbf_frame.py /tmp/text-out/animation.fbf.svg N > /tmp/extracted_N.svg`
  2. `sbb-svg2png tests/fixtures/e2e/text_frames/frame0000N.svg /tmp/in_N.png --width 400 --height 400`
  3. `sbb-svg2png /tmp/extracted_N.svg /tmp/out_N.png --width 400 --height 400`
  4. `sbb-compare /tmp/in_N.png /tmp/out_N.png --threshold 0.03 --out-diff /tmp/diff_N.png`
  5. Print the actual measured diff (`sbb-compare`'s reported metric)
     for each frame so future tightening / loosening is data-driven.

- **Threshold rationale**: 3 % default. Text rendered as `<text>` goes
  through fontconfig + freetype hinting (which snaps glyphs to pixel
  grid for legibility), while text rendered as `<path>` (after svg2fbf
  --text2path conversion) is unhinted geometry. At 400 px wide / 200 px
  tall renders the per-glyph drift can reach ~2 % RMS on small Latin
  text and slightly more on serif faces with complex stroke contrast.
  3 % is permissive enough to absorb that without becoming so loose
  that font fallback or wrong-glyph errors slip through.

- **Calibration loop during implementation**: first run logs the
  actual RMS per frame and per-font; if every observed value sits at
  ≤ 1.8 % with comfortable headroom, tighten to 2.5 %. If serif/bold
  faces routinely exceed 2.5 %, leave at 3 %. This is recorded in
  the implementation report.

- The exact flag name will be confirmed by `sbb-compare --help`
  during implementation; if `sbb-compare` doesn't accept the value as
  a fraction (e.g. uses 0–100 percent or a per-channel threshold), the
  test invocation adapts but the 3 % policy stays the same. Fallback
  if `sbb-compare` lacks a numeric threshold flag at all:
  `text2path compare --pixel-perfect --threshold 3.0` (docs say it
  accepts a percentage value).

## Why this catches the right regressions

- **Bun auto-install regression**: T11 fails if `which bun` is empty
  AFTER svg2fbf runs, or if svg2fbf returns non-zero.
- **HarfBuzz / svg-text2path shaping regression**: T12 byte-exact fails
  on any change in path coordinates produced by the bundled
  `svg-text2path` (font version bump, version bump, conversion bug).
- **Visual fidelity regression**: T13 catches "the path generation
  succeeded but glyph or transform is wrong" — including font fallback
  silently kicking in or `<textPath>` curve placement getting dropped.
  Because input and extracted FBF frame are rendered with the same
  Chrome (via `sbb-svg2png`) on the same fonts, the diff is intrinsically
  near-zero when text2path is correct.

## Implementation order

1. Write `generate_frames.py`, run it locally to produce the 5
   committed frames; eyeball frame00001 in a browser.
2. Write `extract_fbf_frame.py` (stdlib only).
3. Update Dockerfile (apt fonts, COPYs).
4. Update `run_tests.sh` with T_setup, T11, T12, T13.
5. Run `bash scripts/test_release_clean.sh` once. T12 will fail because
   `expected.fbf.svg` doesn't exist yet — capture the freshly generated
   `/tmp/text-out/animation.fbf.svg` from the failing run as the golden,
   commit it, re-run.
6. Add `regen_text_e2e_reference.sh` (mirrors existing
   `regen_e2e_reference.sh`).
7. Re-run end-to-end. All previous 10 + 4 new tests must pass.
8. Commit (one fixtures commit + one tooling commit).

## Open decisions for user approval

- **Renderer for visual diff**: `sbb-svg2png` (Chrome via Puppeteer, your
  library). Confirmed.
- **Diff threshold**: 3 % via `sbb-compare`, with first-run
  calibration that logs the actual measured RMS per frame so the value
  can be tightened later if observed margin allows. Per user feedback
  ("font hinting that beats any svg path rendering engine"), 2 % was
  too tight for hinted-vs-path comparisons; 3 % is the upper bound
  user said they'd accept.
- **Frame count**: 5 (per your spec).
- **Fonts**: DejaVu Sans (400/700) + DejaVu Serif (400) + Liberation
  Mono (400). Replaceable.
- **SVG validation**: `psvglinter --errors-only` from svg-matrix-python,
  replacing `xmllint` for the new tests.
- **Bootstrap order**: install svg-bbox + svg-matrix via `npm install
  -g` AFTER T6 has already pulled Node into the container. Acceptable,
  or do you want the verification harness pre-installed in the Docker
  image instead? Pre-installing would mean the container is no longer a
  clean "Python only" baseline for the auto-repair-viewbox test, so I
  recommend the post-T6 install.

## Out of scope

- Right-to-left scripts (Arabic/Hebrew). Excluded per your spec.
- Complex emoji / CJK / display faces.
- macOS local-test-path text rendering. macOS has a different font set
  and isn't deterministic across host versions; the new test runs only
  in the Docker phase.
