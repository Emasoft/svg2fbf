#!/usr/bin/env python3
"""
Per-frame visual diff harness for the text→path Docker E2E test (T13).

For each input fixture frame `frame0000N.svg`, this script:
  1. Calls `extract_fbf_frame.py` to extract the matching FBF frame
     into a standalone SVG.
  2. Compares the input fixture SVG against the extracted FBF frame
     SVG with `sbb-compare` (Chrome via Puppeteer; sbb-compare renders
     both SVGs to PNG internally and reports per-pixel diff stats as
     JSON).

The threshold is intentionally relaxed (default 3 %) because the input
frame's text goes through fontconfig + freetype hinting (glyphs snap to
the pixel grid for legibility), while the extracted FBF frame's text is
already vector outlines (no hinting). The drift between hinted and
unhinted renders of the same font at the same size is bounded but
non-zero — see TRDD-c2a3199d for the rationale.

`sbb-compare` v1.0.14 sandboxes file paths to ``process.cwd()`` and has
no ``--allow-paths`` flag, so the harness stages the input fixture into
``--workdir`` and invokes ``sbb-compare`` with ``cwd=workdir`` and
relative paths.

Exit codes:
  0   — all frames within threshold
  1   — at least one frame exceeded threshold (or a tool failed)
  2   — invocation error (missing files, bad args)

Pure stdlib, no third-party deps. Designed to run inside the Docker
container where `sbb-compare` is guaranteed.

Reference: design/tasks/TRDD-c2a3199d-...-text2path-docker-e2e.md.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import json


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


def _stage_into(src: Path, workdir: Path) -> Path:
    """Make sure ``src`` lives under ``workdir`` so the sbb tools (which
    sandbox to ``process.cwd()`` and have no ``--allow-paths`` flag) can
    read it. If ``src`` is already inside ``workdir``, return it as-is.
    Otherwise copy and return the new path.
    """
    src_abs = src.resolve()
    workdir_abs = workdir.resolve()
    try:
        src_abs.relative_to(workdir_abs)
        return src_abs
    except ValueError:
        dst = workdir_abs / src.name
        shutil.copy2(src, dst)
        return dst


def _parse_diff_pct(stdout_json: str) -> float | None:
    """Parse diffPercentage from sbb-compare's --json output.

    The JSON sits in stdout next to other lines; locate the first JSON
    object and pull `diffPercentage`. Returns None if parsing fails.
    """
    # The JSON is the entire stdout when --json is passed; parse straight.
    try:
        obj = json.loads(stdout_json.strip())
        v = obj.get("diffPercentage")
        if isinstance(v, (int, float)):
            return float(v)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0] if __doc__ else "T13 visual diff")
    parser.add_argument("--fbf", type=Path, required=True, help="Path to the produced FBF.svg")
    parser.add_argument("--frames-dir", type=Path, required=True, help="Directory holding fixture frame0000N.svg")
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
    parser.add_argument("--workdir", type=Path, default=Path("/tmp"), help="Where to write PNGs and logs")
    parser.add_argument("--extractor", type=Path, default=Path("/test/extract_fbf_frame.py"), help="Path to extract_fbf_frame.py")
    args = parser.parse_args(argv)

    if not args.fbf.is_file():
        print(f"FAIL: FBF file not found: {args.fbf}", file=sys.stderr)
        return 2
    if not args.frames_dir.is_dir():
        print(f"FAIL: frames dir not found: {args.frames_dir}", file=sys.stderr)
        return 2
    if not args.extractor.is_file():
        print(f"FAIL: extractor not found: {args.extractor}", file=sys.stderr)
        return 2

    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for n in range(1, args.frame_count + 1):
        in_svg_orig = args.frames_dir / f"frame{n:05d}.svg"
        if not in_svg_orig.is_file():
            failures.append(f"frame {n}: input fixture missing ({in_svg_orig})")
            continue

        # sbb-compare locks paths to ``process.cwd()`` (no
        # ``--allow-paths`` flag in v1.0.14). Stage the input fixture
        # under ``workdir`` and run sbb-compare with ``cwd=workdir`` +
        # relative paths so the sandbox is satisfied. sbb-compare takes
        # SVGs and renders them to PNG internally — we do not need a
        # separate sbb-svg2png pass.
        in_svg = _stage_into(in_svg_orig, workdir)
        ex_svg = workdir / f"extracted_{n}.svg"
        diff_png = workdir / f"diff_{n}.png"
        ext_log = workdir / f"ext_{n}.log"
        cmp_log = workdir / f"sbb_cmp_{n}.log"

        rc_ext, _ = _run(
            ["python3", str(args.extractor), str(args.fbf), str(n), "--output", str(ex_svg)],
            ext_log,
        )
        if rc_ext != 0:
            failures.append(f"frame {n}: extractor rc={rc_ext} (see {ext_log})")
            continue

        # sbb-compare: --threshold is per-pixel-channel (1-255). Pixels
        # are flagged "different" when any RGBA channel differs by more
        # than threshold/256. With Latin text rendered as <text> (hinted)
        # vs <path> (unhinted), AA fringe pixels routinely differ by
        # ~5-15 channel values. Set --pixel-threshold to 32 (about 12 %
        # per channel) so we ignore the fringe drift but still flag
        # missing or shifted glyphs as different. The binary's exit
        # code is 0/1/2 (identical/differ/error); we instead parse
        # `diffPercentage` from --json output and apply our own
        # max-diff-pct (default 3 %) so the test pass/fail decision is
        # aligned with the TRDD's stated tolerance.
        cmp_cmd = [
            "sbb-compare",
            in_svg.name,
            ex_svg.name,
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
        print("\nT13 failures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
