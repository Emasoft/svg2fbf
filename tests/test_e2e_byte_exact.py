"""End-to-end byte-exact regression test for svg2fbf.

Why a byte-exact test:
    Source-level tests (lint, types, unit tests) catch correctness
    bugs in isolation but cannot catch subtle drift in the actual
    serialized output — attribute ordering, whitespace, optimization
    pass changes, namespace prefix shifts. Any such drift CHANGES the
    bytes users get on disk, even when every other test passes. The
    only way to catch this is to compare the published output to a
    known-good reference, byte-for-byte.

Determinism contract:
    Output is byte-deterministic when --skip-date is passed (omits the
    fbf:generatedDate field) and the CLI invocation matches
    tests/fixtures/e2e/expected/COMMAND.txt verbatim. If you
    intentionally change input frames or the CLI invocation, regenerate
    the reference with scripts/regen_e2e_reference.sh — and commit the
    regen in the same PR as the change that prompted it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "e2e"
INPUT_FRAMES = FIXTURES / "frames"
EXPECTED_DIR = FIXTURES / "expected"
EXPECTED_OUTPUT = EXPECTED_DIR / "animation.fbf.svg"


def test_fixture_inputs_present():
    """All input SVGs and the expected reference exist (sanity check)."""
    assert INPUT_FRAMES.is_dir(), f"Missing input fixture dir: {INPUT_FRAMES}"
    frames = sorted(INPUT_FRAMES.glob("frame*.svg"))
    assert len(frames) >= 2, f"Need at least 2 input frames, found {len(frames)}"
    assert EXPECTED_OUTPUT.is_file(), f"Missing reference output: {EXPECTED_OUTPUT}"


def test_e2e_byte_exact(tmp_path: Path):
    """
    Run svg2fbf on the fixture frames and compare the output to the
    reference, byte-for-byte. Failure means the wire format drifted —
    review the diff and either fix the code or regenerate the reference
    deliberately via scripts/regen_e2e_reference.sh.
    """
    out_dir = tmp_path / "out"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    # Use the SAME relative paths that the reference was generated with —
    # the input path string is embedded in the output (<fbf:sourceFramesPath>)
    # and absolute paths would diverge between machines and runs.
    cmd = [
        sys.executable,
        "src/svg2fbf.py",
        "-i",
        "tests/fixtures/e2e/frames",
        "-o",
        str(out_dir),
        "--no-browser",
        "--skip-date",
        "-s",
        "2.0",
        "-a",
        "once",
        "-d",
        "6",
        "-c",
        "6",
        "-q",
    ]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"svg2fbf exited with code {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    actual_output = out_dir / "animation.fbf.svg"
    assert actual_output.is_file(), f"svg2fbf did not produce {actual_output}"

    expected_bytes = EXPECTED_OUTPUT.read_bytes()
    actual_bytes = actual_output.read_bytes()

    if expected_bytes != actual_bytes:
        # Save the actual output next to the expected one for inspection
        debug_copy = EXPECTED_DIR / "ACTUAL_DIFF.fbf.svg"
        shutil.copy(actual_output, debug_copy)

        # Find the first differing byte for a useful failure message
        first_diff = next(
            (i for i, (e, a) in enumerate(zip(expected_bytes, actual_bytes)) if e != a),
            min(len(expected_bytes), len(actual_bytes)),
        )
        ctx_start = max(0, first_diff - 40)
        ctx_end = first_diff + 40
        pytest.fail(
            f"E2E byte-exact mismatch:\n"
            f"  expected size: {len(expected_bytes)} bytes\n"
            f"  actual size:   {len(actual_bytes)} bytes\n"
            f"  first diff at byte {first_diff}\n"
            f"  expected near diff: {expected_bytes[ctx_start:ctx_end]!r}\n"
            f"  actual near diff:   {actual_bytes[ctx_start:ctx_end]!r}\n\n"
            f"  Actual output saved to: {debug_copy}\n"
            f"  If the change is intentional, regenerate the reference with:\n"
            f"    ./scripts/regen_e2e_reference.sh"
        )
