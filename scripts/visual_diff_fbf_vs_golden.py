#!/usr/bin/env python3
"""
Per-frame visual diff harness comparing a freshly produced FBF.SVG to
the committed golden FBF.SVG (Docker E2E test T12).

For each frame index 1..N, this script:
  1. Calls `extract_fbf_frame.py` twice to extract frame N from BOTH the
     produced FBF and the golden FBF as standalone SVGs.
  2. Runs `sbb-compare` on the pair (Chrome via Puppeteer; sbb-compare
     renders both SVGs to PNG internally and reports per-pixel diff stats
     as JSON).
  3. Passes if every frame's `diffPercentage` is at or below the
     configured threshold (default 3 %).

The threshold is intentionally relaxed because svg2fbf's --text2path mode
rasterises <text> into glyph <path d="…"> coordinates using fontconfig +
the system DejaVu glyph table. The same DejaVu Sans on two different
fresh `apt-get install fonts-dejavu` runs can produce paths that differ
by sub-pixel coordinates, so byte-exact comparison is fundamentally
non-deterministic across container builds. Visual comparison at the
pixel level is the right invariant: "the FBF still LOOKS like the
golden".

`sbb-compare` v1.0.14 sandboxes file paths to ``process.cwd()`` and has
no ``--allow-paths`` flag, so the harness stages both extracted SVGs
into ``--workdir`` and invokes ``sbb-compare`` with ``cwd=workdir`` and
relative paths.

Exit codes:
  0   — all frames within threshold
  1   — at least one frame exceeded threshold (or a tool failed)
  2   — invocation error (missing files, bad args)

Pure stdlib, no third-party deps. Designed to run inside the Docker
container where `sbb-compare` is guaranteed.

Reference: scripts/test_release_clean.sh (T12).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], log_path: Path, cwd: Path | None = None) -> tuple[int, str]:
    """Run cmd, tee combined output to log_path, return (exit_code, stdout)."""
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )
    log_path.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
    return proc.returncode, proc.stdout or ""


def _parse_diff_pct(stdout_json: str) -> float | None:
    """Parse diffPercentage from sbb-compare's --json output.

    sbb-compare emits a JSON object on stdout when --json is passed;
    locate `diffPercentage` and coerce to float. Returns None if parsing
    fails so the caller can flag a tool error rather than a real diff.
    """
    try:
        obj = json.loads(stdout_json.strip())
        v = obj.get("diffPercentage")
        if isinstance(v, (int, float)):
            return float(v)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0] if __doc__ else "T12 visual diff",
    )
    parser.add_argument("--produced", type=Path, required=True, help="Path to the freshly produced FBF.svg")
    parser.add_argument("--golden", type=Path, required=True, help="Path to the committed golden FBF.svg")
    parser.add_argument("--frame-count", type=int, default=5, help="Number of frames to compare (default 5)")
    parser.add_argument(
        "--max-diff-pct",
        type=float,
        default=3.0,
        help="Max allowed sbb-compare diffPercentage per frame (default 3.0)",
    )
    parser.add_argument(
        "--pixel-threshold",
        type=int,
        default=32,
        help="sbb-compare --threshold (1-255, per-channel pixel cutoff; default 32 ignores AA fringe drift)",
    )
    parser.add_argument("--workdir", type=Path, default=Path("/tmp/t12"), help="Where to write extracted SVGs and logs")
    parser.add_argument(
        "--extractor",
        type=Path,
        default=Path("/test/extract_fbf_frame.py"),
        help="Path to extract_fbf_frame.py",
    )
    args = parser.parse_args(argv)

    if not args.produced.is_file():
        print(f"FAIL: produced FBF not found: {args.produced}", file=sys.stderr)
        return 2
    if not args.golden.is_file():
        print(f"FAIL: golden FBF not found: {args.golden}", file=sys.stderr)
        return 2
    if not args.extractor.is_file():
        print(f"FAIL: extractor not found: {args.extractor}", file=sys.stderr)
        return 2

    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for n in range(1, args.frame_count + 1):
        # sbb-compare locks paths to ``process.cwd()`` and has no
        # ``--allow-paths`` flag in v1.0.14. Extract both frames
        # directly into ``workdir`` and invoke sbb-compare with
        # ``cwd=workdir`` + relative paths so the sandbox is satisfied.
        prod_svg = workdir / f"produced_{n}.svg"
        gold_svg = workdir / f"golden_{n}.svg"
        diff_png = workdir / f"diff_{n}.png"
        ext_prod_log = workdir / f"ext_prod_{n}.log"
        ext_gold_log = workdir / f"ext_gold_{n}.log"
        cmp_log = workdir / f"sbb_cmp_{n}.log"

        rc_prod, _ = _run(
            ["python3", str(args.extractor), str(args.produced), str(n), "--output", str(prod_svg)],
            ext_prod_log,
        )
        if rc_prod != 0:
            failures.append(f"frame {n}: produced extractor rc={rc_prod} (see {ext_prod_log})")
            continue

        rc_gold, _ = _run(
            ["python3", str(args.extractor), str(args.golden), str(n), "--output", str(gold_svg)],
            ext_gold_log,
        )
        if rc_gold != 0:
            failures.append(f"frame {n}: golden extractor rc={rc_gold} (see {ext_gold_log})")
            continue

        # sbb-compare: --threshold is per-pixel-channel (1-255). Pixels
        # are flagged "different" when any RGBA channel differs by more
        # than threshold/256. Glyph coordinates that drift by sub-pixel
        # amounts produce AA fringe pixels that differ by ~5-15 channel
        # values; --pixel-threshold=32 (~12 % per channel) ignores that
        # fringe drift while still flagging missing or shifted glyphs.
        # The binary's exit code is 0/1/2 (identical/differ/error); we
        # parse `diffPercentage` from --json output and apply our own
        # max-diff-pct so the test pass/fail decision is aligned with
        # the documented tolerance.
        cmp_cmd = [
            "sbb-compare",
            prod_svg.name,
            gold_svg.name,
            "--threshold",
            str(args.pixel_threshold),
            "--out-diff",
            diff_png.name,
            "--json",
            "--no-html",
        ]
        rc_cmp, cmp_stdout = _run(cmp_cmd, cmp_log, cwd=workdir)
        diff_pct = _parse_diff_pct(cmp_stdout)
        if rc_cmp == 2 or diff_pct is None:
            failures.append(f"frame {n}: sbb-compare error rc={rc_cmp}\n        cmd: {' '.join(cmp_cmd)}\n        log:\n{cmp_log.read_text(encoding='utf-8', errors='replace').rstrip()}")
            continue

        passed = diff_pct <= args.max_diff_pct
        status = "PASS" if passed else "FAIL"
        print(f"    frame {n}: {status} diffPercentage={diff_pct:.4f} (max={args.max_diff_pct})")
        if not passed:
            failures.append(f"frame {n}: diffPercentage={diff_pct:.4f} > max-diff-pct={args.max_diff_pct} (diff image: {diff_png})")

    if failures:
        print("\nT12 failures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
