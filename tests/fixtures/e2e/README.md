# E2E byte-exact test fixtures

These fixtures back the byte-exact end-to-end test in
`scripts/test_release_clean.sh`. They verify that a freshly-installed
svg2fbf wheel converts a known input set to a byte-identical output —
catching every kind of subtle output drift (formatting, attribute order,
whitespace, optimization changes) that source-level tests miss.

## NO `<text>` ELEMENTS — fonts are non-deterministic across machines

The fixture frames intentionally use ONLY shape primitives (`<rect>`,
`<circle>`, `<path>`) and never `<text>`. Why:

- If `--text2path` is used, glyph outlines come from the user's system
  fonts. Two machines that "have" the same font (e.g. Helvetica)
  may have DIFFERENT glyph data — different versions, different
  weights labeled the same, OS-specific substitutions. The byte
  output will diverge with no real bug to fix.
- If `--text2path` is not used, svg2fbf passes `<text>` through
  literally — but downstream renderers will still render it
  differently per machine.

Either way, fonts make E2E byte comparisons unreliable. We test text
handling at the unit-test level instead.

## Determinism contract

The output is byte-deterministic when:
- The `--skip-date` flag is passed (omits the `<fbf:generatedDate>` field —
  the only otherwise-varying piece in the output)
- The CLI is invoked with the EXACT command in `expected/COMMAND.txt`
- The input frames in `frames/` are unchanged

If you intentionally change the input fixtures or the CLI invocation,
regenerate the expected file with:

```
./scripts/regen_e2e_reference.sh
```

## Files

- `frames/frame00001.svg`, `frame00002.svg`, `frame00003.svg` — input frames
  (already valid: have viewBox, byte-exact-test inputs)
- `broken_frames/frame00001.svg`, `frame00002.svg` — inputs MISSING viewBox.
  Used to exercise the `--auto-repair-viewbox` integration path: copying
  these to a temp dir and running svg2fbf with --auto-repair-viewbox
  triggers the Node.js + Puppeteer auto-install and the viewBox repair.
  These files are NOT byte-compared (the repaired viewBox depends on
  chromium-rendered bbox, which can vary across chromium versions).
- `expected/animation.fbf.svg` — golden reference output, byte-compared on every release
- `expected/COMMAND.txt` — the exact command used to produce the reference
