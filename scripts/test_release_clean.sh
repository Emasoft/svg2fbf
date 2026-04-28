#!/usr/bin/env bash
# test_release_clean.sh — End-to-end clean-install test for svg2fbf releases.
#
# WHAT IT DOES:
#   1. Builds a wheel from the current git working tree.
#   2. Installs the wheel into a fresh venv on the LOCAL host (macOS or Linux)
#      and runs a smoke-test that exercises the auto-install code paths.
#   3. Builds a clean Docker image (python:3.12-slim — only Python pre-installed)
#      and runs the same smoke-test inside it. This verifies that svg2fbf can
#      bootstrap its own Node.js + Puppeteer dependencies on a fresh user's
#      machine, with no pre-installed tooling.
#
# WHY:
#   svg-repair-viewbox needs Node.js + Puppeteer at runtime. The project
#   bundles auto_install_deps.py to install these automatically the first
#   time the tool runs. That auto-install code has historically broken in
#   subtle ways:
#     - Broken relative imports (issue #15)
#     - Unconditional 'sudo' usage that fails in containers
#     - Misleading "file not found" errors when Chrome isn't pre-installed
#   This script catches regressions BEFORE a release goes out.
#
# USAGE:
#   ./scripts/test_release_clean.sh                # both macOS local + Linux Docker
#   ./scripts/test_release_clean.sh --local-only   # skip Docker (faster CI)
#   ./scripts/test_release_clean.sh --docker-only  # skip local
#
# EXIT CODE:
#   0 if all enabled platforms pass
#   1 if any platform fails
#
# KNOWN LIMITATION (Apple Silicon hosts):
#   Puppeteer only ships x86_64 Chrome for Linux. On Apple Silicon Macs
#   running the linux/arm64 Docker variant, Puppeteer's bundled Chrome
#   won't launch. The script detects this case and uses system chromium
#   via PUPPETEER_EXECUTABLE_PATH so the END-TO-END pipeline can still
#   be exercised. Real x86_64 Linux servers do not need this workaround.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

WORK_DIR="$(mktemp -d -t svg2fbf-test-XXXXXX)"
# Compose the per-run Docker image tag here (not at the docker-build site)
# so the EXIT trap can remove it even if we abort before reaching the
# Docker section. tag is forced to lowercase because Docker rejects
# uppercase characters in the image-name segment.
IMG="svg2fbf-clean-test:$(basename "$WORK_DIR" | tr '[:upper:]' '[:lower:]')"
trap 'rm -rf "$WORK_DIR"; docker image rm -f "$IMG" >/dev/null 2>&1 || true' EXIT

DO_LOCAL=true
DO_DOCKER=true
for arg in "$@"; do
    case "$arg" in
        --local-only)  DO_DOCKER=false ;;
        --docker-only) DO_LOCAL=false ;;
        --help|-h)
            sed -n '2,40p' "$0" | sed 's/^# //; s/^#//'
            exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 1 ;;
    esac
done

# ----------------------------------------------------------------------
# PRE-FLIGHT: ALL TESTS + ALL LINTERS must pass on the source before we
# even build a wheel. A failed source check means there is no point doing
# the install verification — fix the source first.
# ----------------------------------------------------------------------
echo "▶ Pre-flight: running all source-level checks (lint + types + tests)..."

# Pre-flight log files live under the per-run mktemp $WORK_DIR rather than
# the world-writable /tmp. /tmp paths are predictable, leak across users on
# shared hosts, race between concurrent runs, and are a classic symlink-
# attack target on multi-tenant CI runners.
RUFF_LINT_LOG="$WORK_DIR/ruff-lint.log"
RUFF_FMT_LOG="$WORK_DIR/ruff-fmt.log"
PYRIGHT_LOG="$WORK_DIR/pyright.log"
PYTEST_LOG="$WORK_DIR/pytest.log"

echo "  - ruff lint..."
if ! uv run ruff check src/ tests/ scripts/ >"$RUFF_LINT_LOG" 2>&1; then
    echo "    ✗ ruff lint failed:"
    sed 's/^/      /' "$RUFF_LINT_LOG" | tail -20
    exit 1
fi

echo "  - ruff format check..."
if ! uv run ruff format --check src/ tests/ scripts/ >"$RUFF_FMT_LOG" 2>&1; then
    echo "    ✗ ruff format check failed:"
    sed 's/^/      /' "$RUFF_FMT_LOG" | tail -20
    exit 1
fi

echo "  - pyright type check (errors only)..."
if ! uv run pyright src/ >"$PYRIGHT_LOG" 2>&1; then
    if grep -q "error:" "$PYRIGHT_LOG"; then
        echo "    ✗ pyright reported errors:"
        grep "error:" "$PYRIGHT_LOG" | sed 's/^/      /' | head -20
        exit 1
    fi
    # exit code may be non-zero due to warnings only — accept that
fi

echo "  - pytest..."
if ! uv run pytest tests/ -q --no-header >"$PYTEST_LOG" 2>&1; then
    echo "    ✗ pytest failed:"
    sed 's/^/      /' "$PYTEST_LOG" | tail -30
    exit 1
fi

echo "  ✓ All source-level checks passed"
echo ""

# Build wheel from current source
# ----------------------------------------------------------------------
echo "▶ Building wheel from current source..."
rm -f dist/*.whl dist/*.tar.gz
uv build --wheel >/dev/null 2>&1
WHEEL="$(ls dist/svg2fbf-*-py3-none-any.whl | head -1)"
[[ -z "$WHEEL" ]] && { echo "✗ Wheel build failed"; exit 1; }
WHEEL_NAME="$(basename "$WHEEL")"
echo "  Built: $WHEEL_NAME"

# Copy wheel and fixtures into work dir
cp "$WHEEL" "$WORK_DIR/"
mkdir -p "$WORK_DIR/frames"
cat > "$WORK_DIR/frames/frame00001.svg" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect width="100" height="100" fill="red"/></svg>
EOF
cat > "$WORK_DIR/frames/frame00002.svg" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect width="100" height="100" fill="blue"/></svg>
EOF
cat > "$WORK_DIR/needs_viewbox.svg" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><circle cx="25" cy="25" r="20" fill="green"/></svg>
EOF

# E2E byte-exact reference fixtures — same fixtures the pytest uses,
# but we run them against the INSTALLED WHEEL (not the source) and
# byte-compare to the reference. NO <text> elements — fonts vary
# across machines and would cause spurious failures.
mkdir -p "$WORK_DIR/e2e/frames" "$WORK_DIR/e2e/broken_frames"
cp "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00001.svg" "$WORK_DIR/e2e/frames/"
cp "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00002.svg" "$WORK_DIR/e2e/frames/"
cp "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00003.svg" "$WORK_DIR/e2e/frames/"
cp "$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg" "$WORK_DIR/e2e/expected.fbf.svg"
# Broken frames (missing viewBox) — used to exercise the
# --auto-repair-viewbox install path
cp "$PROJECT_ROOT/tests/fixtures/e2e/broken_frames/frame00001.svg" "$WORK_DIR/e2e/broken_frames/"
cp "$PROJECT_ROOT/tests/fixtures/e2e/broken_frames/frame00002.svg" "$WORK_DIR/e2e/broken_frames/"

# Text→path Docker E2E fixtures (TRDD-c2a3199d). Five SVG frames using
# fonts that the Docker image installs deterministically via apt
# (DejaVu Sans/Serif + Liberation Mono). Plus the golden FBF and the
# stdlib helper that extracts a single frame from an FBF for visual
# diffing inside the container.
mkdir -p "$WORK_DIR/text_frames"
for n in 1 2 3 4 5; do
    cp "$PROJECT_ROOT/tests/fixtures/e2e/text_frames/frame0000$n.svg" "$WORK_DIR/text_frames/"
done
# Golden FBF is committed once captured; on the first run the file may
# be absent (T12 will fail with a clear message instead of crashing).
if [[ -f "$PROJECT_ROOT/tests/fixtures/e2e/text_frames/expected.fbf.svg" ]]; then
    cp "$PROJECT_ROOT/tests/fixtures/e2e/text_frames/expected.fbf.svg" "$WORK_DIR/text_frames/expected.fbf.svg"
fi
cp "$PROJECT_ROOT/scripts/extract_fbf_frame.py" "$WORK_DIR/extract_fbf_frame.py"
cp "$PROJECT_ROOT/scripts/visual_diff_text_frames.py" "$WORK_DIR/visual_diff_text_frames.py"

OVERALL_FAIL=0

# ----------------------------------------------------------------------
# LOCAL TEST (macOS or Linux host)
# ----------------------------------------------------------------------
if $DO_LOCAL; then
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  LOCAL TEST ($(uname -s) $(uname -m))"
    echo "════════════════════════════════════════════════════════════"

    LOCAL_VENV="$WORK_DIR/local-venv"
    uv venv --python 3.12 "$LOCAL_VENV" >/dev/null 2>&1
    uv pip install --python "$LOCAL_VENV/bin/python" "$WORK_DIR/$WHEEL_NAME" >/dev/null 2>&1

    LOCAL_PASS=0; LOCAL_FAIL=0
    LOCAL_TEST_OUT="$WORK_DIR/local-test-out"

    run_local() {
        local name="$1"; shift
        if "$@" >"$LOCAL_TEST_OUT" 2>&1; then
            echo "  ✓ $name"
            LOCAL_PASS=$((LOCAL_PASS + 1))
        else
            echo "  ✗ $name"
            sed 's/^/    /' "$LOCAL_TEST_OUT" | tail -10
            LOCAL_FAIL=$((LOCAL_FAIL + 1))
        fi
    }

    # CLI version
    run_local "CLI version reports svg2fbf 0.1.x"  bash -c "
        '$LOCAL_VENV/bin/svg2fbf' --version | grep -q '0.1.'
    "
    # Imports work (the original #15 bug)
    run_local "Imports (auto_install_deps + svg_viewbox_repair.main + svg2fbf.main)" bash -c "
        '$LOCAL_VENV/bin/python' -c 'import auto_install_deps; from svg_viewbox_repair.main import get_node_scripts_dir; from svg2fbf.main import cli; print(\"OK\")'
    "
    # Core svg2fbf works without Node
    run_local "svg2fbf core pipeline produces valid output" bash -c "
        rm -rf '$WORK_DIR/local-out'
        '$LOCAL_VENV/bin/svg2fbf' -i '$WORK_DIR/frames' -o '$WORK_DIR/local-out' --no-browser >/tmp/svg2fbf-out 2>&1 &&
        [[ -f '$WORK_DIR/local-out/animation.fbf.svg' ]] &&
        grep -q xmlns:fbf '$WORK_DIR/local-out/animation.fbf.svg'
    "
    # check_dependencies doesn't crash on import (the silent-failure bug)
    run_local "check_dependencies does not raise ImportError" bash -c "
        '$LOCAL_VENV/bin/python' -c 'import auto_install_deps; auto_install_deps.check_dependencies()'
    "

    # E2E byte-exact: convert the fixture frames and compare to the
    # golden reference, byte-for-byte. Catches subtle output drift
    # (attribute ordering, whitespace, optimization changes) that
    # other tests miss. Uses --skip-date for determinism.
    # cd into the project root so 'tests/fixtures/e2e/frames' resolves
    # to the same path string that's embedded in the reference output.
    run_local "E2E byte-exact (fixtures → reference, byte-for-byte, version-stripped)" bash -c "
        cd '$PROJECT_ROOT'
        rm -rf '$WORK_DIR/local-e2e-out'
        '$LOCAL_VENV/bin/svg2fbf' \\
            -i tests/fixtures/e2e/frames \\
            -o '$WORK_DIR/local-e2e-out' \\
            --no-browser --skip-date -s 2.0 -a once -d 6 -c 6 -q
        # Strip the two version-pinned lines before comparing — they are
        # runtime metadata (which build produced this), not part of the
        # wire format.
        strip_v() { grep -vE 'FILE GENERATED BY svg2fbf|<fbf:generatorVersion>' \"\$1\"; }
        if ! diff <(strip_v '$WORK_DIR/local-e2e-out/animation.fbf.svg') <(strip_v '$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg') > /dev/null; then
            echo 'BYTE-EXACT MISMATCH [version-stripped] — first diff:' >&2
            diff <(strip_v '$WORK_DIR/local-e2e-out/animation.fbf.svg') <(strip_v '$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg') | head -10 >&2
            exit 1
        fi
    "

    echo "  Local result: $LOCAL_PASS passed, $LOCAL_FAIL failed"
    [[ $LOCAL_FAIL -gt 0 ]] && OVERALL_FAIL=1
fi

# ----------------------------------------------------------------------
# DOCKER LINUX TEST (truly clean container)
# ----------------------------------------------------------------------
if $DO_DOCKER; then
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  DOCKER LINUX TEST (clean python:3.12-slim)"
    echo "════════════════════════════════════════════════════════════"

    if ! command -v docker >/dev/null 2>&1; then
        echo "  ⚠ docker not on PATH; skipping Linux test"
    else
        # Detect host CPU arch and map to Docker platform string.
        # Why: when the host is ARM64 (Apple Silicon, ARM Linux servers,
        # Raspberry Pi) and we don't pass --platform, Docker may run
        # either an emulated x86_64 image (slow, Puppeteer's chromium
        # works) or a native arm64 image (fast, Puppeteer's chromium
        # does NOT work because Puppeteer ships only x86_64 Linux Chrome).
        # Either way, behaviour drifts from "what users on this arch see".
        # Fix: always pass --platform so the container CPU matches the
        # host CPU exactly, and install system chromium when needed.
        HOST_ARCH="$(uname -m)"
        case "$HOST_ARCH" in
            arm64|aarch64)
                DOCKER_PLATFORM="linux/arm64"
                # Puppeteer's bundled chromium is x86_64-only on Linux.
                # On native arm64 containers we MUST install system chromium
                # and route Puppeteer through PUPPETEER_EXECUTABLE_PATH.
                EXTRA_PKGS="chromium"
                EXTRA_ENV='ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium'
                ARCH_NOTE="(arm64: using system chromium — Puppeteer's bundled chromium is x86_64-only)"
                ;;
            x86_64|amd64)
                DOCKER_PLATFORM="linux/amd64"
                # Puppeteer's bundled chromium is fine on x86_64 Linux.
                EXTRA_PKGS=""
                EXTRA_ENV=""
                ARCH_NOTE="(x86_64: using Puppeteer's bundled chromium)"
                ;;
            *)
                # Best-effort fallback for unusual archs (riscv64, ppc64le,
                # s390x). Try a native arm64-like flow with system chromium —
                # if Docker can't pull a matching image the build fails loudly.
                DOCKER_PLATFORM="linux/$HOST_ARCH"
                EXTRA_PKGS="chromium"
                EXTRA_ENV='ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium'
                ARCH_NOTE="(uncommon arch '$HOST_ARCH' — best-effort native build with system chromium)"
                ;;
        esac
        echo "  Host arch: $HOST_ARCH → Docker --platform=$DOCKER_PLATFORM $ARCH_NOTE"

        cat > "$WORK_DIR/Dockerfile" <<DOCKERFILE
# Truly clean: ONLY Python. svg2fbf must auto-install everything else.
FROM python:3.12-slim

# fonts-dejavu + fonts-liberation are required by the text→path Docker
# E2E (T11/T12/T13). They give svg-text2path's HarfBuzz shaper the exact
# Latin font faces our committed fixtures reference by name, so the
# byte-exact and visual-diff comparisons stay deterministic across host
# Linux distributions and CI runners. These add ~14 MB to the image
# and do not affect the auto-install tests (T1–T10), which exercise
# Node/Puppeteer bootstrap and not font resolution.
RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        libxml2-utils \\
        fonts-dejavu fonts-liberation \\
        $EXTRA_PKGS && \\
    rm -rf /var/lib/apt/lists/*

$EXTRA_ENV

WORKDIR /test
COPY $WHEEL_NAME .
RUN python -m venv /opt/svg2fbf-venv && \\
    /opt/svg2fbf-venv/bin/pip install --no-cache-dir ./$WHEEL_NAME
ENV PATH="/opt/svg2fbf-venv/bin:\$PATH"

RUN mkdir -p /test/frames /test/tests/fixtures/e2e/frames
COPY frames/frame00001.svg /test/frames/
COPY frames/frame00002.svg /test/frames/
COPY needs_viewbox.svg /test/

# E2E byte-exact fixtures + reference output.
# Placed at /test/tests/fixtures/e2e/frames/ so that running 'svg2fbf -i
# tests/fixtures/e2e/frames' from /test produces the same
# <fbf:sourceFramesPath> embedded in the SVG as the reference (which was
# generated from the project root with the same relative path). Otherwise
# a path-string mismatch causes a false byte-exact failure.
COPY e2e/frames/frame00001.svg /test/tests/fixtures/e2e/frames/
COPY e2e/frames/frame00002.svg /test/tests/fixtures/e2e/frames/
COPY e2e/frames/frame00003.svg /test/tests/fixtures/e2e/frames/
COPY e2e/expected.fbf.svg /test/tests/fixtures/e2e/expected.fbf.svg
RUN mkdir -p /test/broken_frames
COPY e2e/broken_frames/frame00001.svg /test/broken_frames/
COPY e2e/broken_frames/frame00002.svg /test/broken_frames/

# Text→path E2E fixtures (TRDD-c2a3199d). The five frames live at
# tests/fixtures/e2e/text_frames so svg2fbf's --text2path output embeds
# the same <fbf:sourceFramesPath> as on the host, which is required for
# the byte-exact comparison.
RUN mkdir -p /test/tests/fixtures/e2e/text_frames
COPY text_frames/frame00001.svg /test/tests/fixtures/e2e/text_frames/
COPY text_frames/frame00002.svg /test/tests/fixtures/e2e/text_frames/
COPY text_frames/frame00003.svg /test/tests/fixtures/e2e/text_frames/
COPY text_frames/frame00004.svg /test/tests/fixtures/e2e/text_frames/
COPY text_frames/frame00005.svg /test/tests/fixtures/e2e/text_frames/
# expected.fbf.svg may not yet exist on the very first run — captured
# from the run output and committed afterwards. Use a one-line guard so
# the COPY isn't fatal when missing (BuildKit needed for COPY --link).
COPY text_frames/expected.fbf.sv[g] /test/tests/fixtures/e2e/text_frames/expected.fbf.svg
COPY extract_fbf_frame.py /test/extract_fbf_frame.py
COPY visual_diff_text_frames.py /test/visual_diff_text_frames.py

COPY run_tests.sh /test/run_tests.sh
RUN chmod +x /test/run_tests.sh
CMD ["/test/run_tests.sh"]
DOCKERFILE

        cat > "$WORK_DIR/run_tests.sh" <<'INNER'
#!/bin/bash
# set -eo pipefail: fail fast inside multi-line test blocks. Without -e, a
# crash in an intermediate command (e.g. svg2fbf in a multi-step bash -c)
# would be masked by the final command's exit code, producing false passes.
set -euo pipefail
PASS=0; FAIL=0; FAILS=()
run() {
    local name="$1"; shift
    if "$@" >/tmp/out 2>&1; then echo "  ✓ $name"; PASS=$((PASS+1));
    else echo "  ✗ $name"; sed 's/^/    /' /tmp/out | tail -8; FAIL=$((FAIL+1)); FAILS+=("$name"); fi
}

run "CLI version"         bash -c "svg2fbf --version | grep -q '0.1.'"
run "Imports"             /opt/svg2fbf-venv/bin/python -c "import auto_install_deps; from svg_viewbox_repair.main import get_node_scripts_dir; from svg2fbf.main import cli; print('OK')"
run "check_dependencies clean (Node.js missing, no crash)" bash -c '/opt/svg2fbf-venv/bin/python -c "import auto_install_deps; r,m=auto_install_deps.check_dependencies(); print(r,m); exit(0 if not r else 1)"'
run "svg2fbf core pipeline" bash -c "
    rm -rf /tmp/out2
    svg2fbf -i /test/frames -o /tmp/out2 --no-browser
    [[ -f /tmp/out2/animation.fbf.svg ]] && xmllint --noout /tmp/out2/animation.fbf.svg && grep -q xmlns:fbf /tmp/out2/animation.fbf.svg
"

# Without --auto-repair-viewbox, processing a frame missing viewBox
# must FAIL with a clear error (and NOT trigger the install path).
# This protects users on machines without Node.js from accidentally
# kicking off a 170MB Chromium download.
run "svg2fbf rejects missing viewBox without --auto-repair-viewbox" bash -c '
    rm -rf /tmp/out-broken
    if svg2fbf -i /test/broken_frames -o /tmp/out-broken --no-browser >/tmp/svg2fbf-broken.log 2>&1; then
        echo "FAIL: svg2fbf should have exited non-zero on missing viewBox"
        exit 1
    fi
    grep -q "missing the viewBox" /tmp/svg2fbf-broken.log
'

# THIS is the install-path-via-svg2fbf test. svg2fbf with
# --auto-repair-viewbox sees the missing-viewBox frame, calls
# ensure_dependencies() under the hood, which bootstraps Node.js
# + Puppeteer from a CLEAN container, then runs the repair, then
# completes the FBF generation. Single command drives the whole chain.
run "svg2fbf --auto-repair-viewbox bootstraps Node+Puppeteer and produces FBF" bash -c "
    cp -r /test/broken_frames /tmp/broken-copy
    rm -rf /tmp/out-repair
    svg2fbf -i /tmp/broken-copy -o /tmp/out-repair --no-browser --auto-repair-viewbox --skip-date
    # The repair is in-place on the COPY (we don't want to mutate the fixture)
    grep -q viewBox /tmp/broken-copy/frame00001.svg || { echo 'frame00001 was not repaired'; exit 1; }
    [[ -f /tmp/out-repair/animation.fbf.svg ]] || { echo 'No FBF output produced'; exit 1; }
    xmllint --noout /tmp/out-repair/animation.fbf.svg || { echo 'FBF output is not valid XML'; exit 1; }
    grep -q xmlns:fbf /tmp/out-repair/animation.fbf.svg || { echo 'FBF output missing fbf namespace'; exit 1; }
"

run "check_dependencies after install (Ready=True)" bash -c '
    /opt/svg2fbf-venv/bin/python -c "import auto_install_deps; r,m=auto_install_deps.check_dependencies(); print(r,m); exit(0 if r else 1)"'

# Bonus: explicit svg-repair-viewbox call still works end-to-end on
# a system that's now bootstrapped (regression cover).
run "svg-repair-viewbox direct call (deps already installed)" \
    svg-repair-viewbox /test/needs_viewbox.svg
run "browser-open helper logic" /opt/svg2fbf-venv/bin/python -c "
from svg2fbf.main import _is_browser_available
assert _is_browser_available('python3'); assert not _is_browser_available('this-fake-browser-12345')
assert _is_browser_available('/usr/bin/python3'); assert not _is_browser_available('/applications/nope.app')
print('OK')"

# E2E BYTE-EXACT — convert the fixture frames with the installed wheel
# and compare to the golden reference, byte-for-byte. This is what
# catches "the wheel installs and runs but produces a slightly different
# output that would corrupt user files".
# Run from /test (so tests/fixtures/e2e/frames resolves the same way it
# does on the developer's machine — the path string ends up in the SVG).
run "E2E byte-exact (fixtures → reference)" bash -c '
    cd /test
    rm -rf /tmp/e2e-out
    svg2fbf \
        -i tests/fixtures/e2e/frames \
        -o /tmp/e2e-out \
        --no-browser --skip-date -s 2.0 -a once -d 6 -c 6 -q
    # Strip the two version-pinned lines (`<!-- FILE GENERATED BY svg2fbf vN -->`
    # and `<fbf:generatorVersion>vN</fbf:generatorVersion>`) before comparing.
    # They are runtime metadata, not part of the wire format the byte-exact
    # test is policing — without stripping, every alpha/beta/rc/stable
    # promotion forces a manual golden regen on what is a single-line
    # metadata diff. See tests/test_e2e_byte_exact.py for the matching
    # strip in the host pytest.
    strip_v() { grep -vE "FILE GENERATED BY svg2fbf|<fbf:generatorVersion>" "$1"; }
    if ! diff <(strip_v /tmp/e2e-out/animation.fbf.svg) <(strip_v /test/tests/fixtures/e2e/expected.fbf.svg) > /dev/null; then
        echo "BYTE-EXACT MISMATCH [version-stripped]:"
        diff <(strip_v /tmp/e2e-out/animation.fbf.svg) <(strip_v /test/tests/fixtures/e2e/expected.fbf.svg) | head -10
        exit 1
    fi
'

# ─────────────────────────────────────────────────────────────────────
# Text→path E2E (TRDD-c2a3199d).
#
# These tests run AFTER the auto-repair-viewbox test above so Node.js
# is already bootstrapped in the container. They install the Emasoft
# verification harness (svg-bbox + svg-matrix) into the same global
# npm prefix and then exercise svg2fbf --text2path end-to-end.
# ─────────────────────────────────────────────────────────────────────

# T_setup: install the verification harness (svg-bbox CLI from
# Emasoft/SVG-BBOX). This is internal scaffolding, not a regression
# test of svg2fbf itself, so we exit non-zero only if the install or
# the binary lookup fails.
run "T_setup: install svg-bbox harness via npm" bash -c '
    if ! command -v npm >/dev/null 2>&1; then
        echo "FAIL: npm is not on PATH; the auto-repair test should have bootstrapped Node."
        exit 1
    fi
    npm install -g svg-bbox >/tmp/npm-setup.log 2>&1
    rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "FAIL: npm install -g svg-bbox exited $rc"
        tail -30 /tmp/npm-setup.log
        exit 1
    fi
    for bin in sbb-svg2png sbb-compare sbb-extract sbb-getbbox; do
        if ! command -v "$bin" >/dev/null 2>&1; then
            echo "FAIL: $bin not on PATH after npm install -g svg-bbox"
            exit 1
        fi
    done
'

# T11: --text2path bootstraps Bun (auto-install path) and converts text
# to vector paths via the bundled svg-text2path/HarfBuzz pipeline.
run "T11: svg2fbf --text2path bootstraps Bun + converts text→paths" bash -c '
    cd /test
    # Pre-condition: Bun must NOT be installed yet so we observe the
    # auto-install path of svg2fbf actually firing.
    if command -v bun >/dev/null 2>&1; then
        echo "WARN: bun was already on PATH before T11; uninstalling so the test can verify auto-install."
        npm uninstall -g bun >/dev/null 2>&1 || true
        # Strip any residual symlink directly so the test starts clean.
        rm -f "$(npm config get prefix)/bin/bun" 2>/dev/null || true
    fi
    if command -v bun >/dev/null 2>&1; then
        echo "FAIL: could not remove pre-existing bun before T11."
        exit 1
    fi
    rm -rf /tmp/text-out
    svg2fbf \
        -i tests/fixtures/e2e/text_frames \
        -o /tmp/text-out \
        --no-browser --skip-date --text2path \
        -s 2.0 -a once -d 6 -c 6 -q
    [[ -f /tmp/text-out/animation.fbf.svg ]] || { echo "FAIL: no FBF output produced"; exit 1; }
    # If a host bind-mount is present at /captured (set via
    # CAPTURE_GOLDEN=1 in the host invocation), drop a copy of the
    # freshly generated FBF there so the operator can promote it to
    # the committed golden after the very first run.
    if [[ -d /captured ]]; then
        cp /tmp/text-out/animation.fbf.svg /captured/expected.fbf.svg
        echo "    captured golden FBF -> /captured/expected.fbf.svg"
    fi
    # Validate the FBF output is well-formed XML. xmllint is in the
    # base Docker image (libxml2-utils) and is sufficient for syntax-
    # level validation; FBF spec semantics are exercised by T12
    # (byte-exact match) and T13 (visual diff).
    xmllint --noout /tmp/text-out/animation.fbf.svg \
        || { echo "FAIL: xmllint reported errors on FBF output"; exit 1; }
    # Post-condition: Bun must now be on PATH (svg2fbf auto-installed it
    # for SVG validation during text2path conversion).
    command -v bun >/dev/null 2>&1 \
        || { echo "FAIL: bun was not auto-installed by svg2fbf --text2path"; exit 1; }
    # Conversion sanity: zero <text> elements remain, many <path> elements present.
    text_count=$(grep -c "<text" /tmp/text-out/animation.fbf.svg || true)
    path_count=$(grep -c "<path" /tmp/text-out/animation.fbf.svg || true)
    if [[ "$text_count" != "0" ]]; then
        echo "FAIL: expected 0 <text> elements in FBF output, got $text_count"
        exit 1
    fi
    if [[ "$path_count" -lt 5 ]]; then
        echo "FAIL: expected many <path> elements in FBF output, got $path_count"
        exit 1
    fi
    echo "    text→path conversion verified: <text>=$text_count, <path>=$path_count"
'

# T12: byte-exact match of the text2path output against the committed
# golden FBF. On the very first run the golden is missing — we surface
# a clear actionable message so the operator can capture the freshly
# generated FBF as the new golden.
run "T12: text fixture E2E byte-exact (text2path mode, version-stripped)" bash -c '
    cd /test
    if [[ ! -f /test/tests/fixtures/e2e/text_frames/expected.fbf.svg ]]; then
        echo "FAIL: no golden expected.fbf.svg yet."
        echo "       To capture: run scripts/regen_text_frames_golden.sh on the host."
        exit 1
    fi
    # Strip the two version-pinned lines before comparing — same reason
    # as the non-text2path byte-exact test above.
    strip_v() { grep -vE "FILE GENERATED BY svg2fbf|<fbf:generatorVersion>" "$1"; }
    if ! diff <(strip_v /tmp/text-out/animation.fbf.svg) <(strip_v /test/tests/fixtures/e2e/text_frames/expected.fbf.svg) > /dev/null; then
        echo "BYTE-EXACT MISMATCH (text2path) [version-stripped]:"
        diff <(strip_v /tmp/text-out/animation.fbf.svg) <(strip_v /test/tests/fixtures/e2e/text_frames/expected.fbf.svg) | head -30
        exit 1
    fi
'

# T13: per-frame visual diff via the Python helper that drives
# sbb-svg2png + sbb-compare. The pass threshold is sbb-compare's
# diffPercentage (% of pixels that exceed the per-channel threshold).
# Defaults: --pixel-threshold 32 (per-channel cutoff that ignores AA
# fringe drift between hinted-text and unhinted-path renders) and
# --max-diff-pct 3.0 (max share of differing pixels allowed). Both
# can be overridden from the host shell via T13_PIXEL_THRESHOLD and
# T13_MAX_DIFF_PCT respectively, useful for calibration runs.
run "T13: text rendering frame-by-frame visual diff" \
    python3 /test/visual_diff_text_frames.py \
        --fbf /tmp/text-out/animation.fbf.svg \
        --frames-dir /test/tests/fixtures/e2e/text_frames \
        --frame-count 5 \
        --pixel-threshold "${T13_PIXEL_THRESHOLD:-32}" \
        --max-diff-pct "${T13_MAX_DIFF_PCT:-3.0}" \
        --workdir /tmp/t13 \
        --extractor /test/extract_fbf_frame.py

echo "  Docker result: $PASS passed, $FAIL failed"
[[ $FAIL -gt 0 ]] && { for f in "${FAILS[@]}"; do echo "    - $f"; done; exit 1; }
exit 0
INNER
        chmod +x "$WORK_DIR/run_tests.sh"

        # The per-run image tag $IMG was set at the top of the script so the
        # EXIT trap can clean it up even if we abort before this point.
        # See the trap definition near `mktemp -d` for rationale.
        # Pass --platform on BOTH build and run so the container CPU
        # matches the host exactly. Without --platform Docker falls back
        # to its default (which on multi-arch Docker Desktop is x86_64
        # via emulation even on arm64 hosts) and drifts from the user
        # experience we are trying to verify.
        if ! docker build --platform="$DOCKER_PLATFORM" -q -t "$IMG" "$WORK_DIR" >/dev/null 2>"$WORK_DIR/build.log"; then
            echo "  ✗ Docker build failed"
            sed 's/^/    /' "$WORK_DIR/build.log" | tail -10
            OVERALL_FAIL=1
        else
            # HARD memory limit on the container. Why: a previous run
            # blew the host swap to 225GB on a 64GB machine when
            # Puppeteer's Chromium leaked under emulation. Capping the
            # container forces the leak to surface as an OOM kill INSIDE
            # the container instead of consuming all host swap.
            #   --memory=6g       : RSS cap. Bumped from 4g because
            #                       puppeteer's first-install peak is
            #                       ~3.1 GB and growing ~10% per minor
            #                       version; 4g was getting OOM-killed
            #                       mid-install. 6g is still safely
            #                       below the release_all.sh host-swap
            #                       watchdog (4 GB swap threshold).
            #   --memory-swap=6g  : disable swap (memory-swap == memory)
            #   --pids-limit=512  : prevent fork bombs from spawning
            #                       runaway chromium tabs
            #   --shm-size=512m   : explicit shm so Chromium's /dev/shm
            #                       is bounded (Chromium can otherwise
            #                       consume large amounts of host shm)
            # CAPTURE_GOLDEN=1 enables a host bind-mount at /captured so
            # T11 inside the container can drop the freshly generated
            # text→path FBF on the host filesystem. Used during initial
            # golden capture and after svg-text2path / font version bumps
            # via scripts/regen_text_e2e_reference.sh.
            CAPTURE_VOL_ARGS=()
            if [[ "${CAPTURE_GOLDEN:-0}" = "1" ]]; then
                mkdir -p "$WORK_DIR/captured"
                CAPTURE_VOL_ARGS=(-v "$WORK_DIR/captured:/captured")
                echo "  CAPTURE_GOLDEN=1 — mounting $WORK_DIR/captured:/captured"
            fi
            # CAPTURE_T13=1 mounts /tmp/t13 (where T13 stores PNGs and
            # diff images) so the operator can inspect the rendered
            # frames, the diff overlays, and the sbb-compare logs after
            # the container exits — essential for calibrating the
            # threshold.
            if [[ "${CAPTURE_T13:-0}" = "1" ]]; then
                mkdir -p "$WORK_DIR/t13"
                CAPTURE_VOL_ARGS+=(-v "$WORK_DIR/t13:/tmp/t13")
                echo "  CAPTURE_T13=1 — mounting $WORK_DIR/t13:/tmp/t13"
            fi

            if ! docker run \
                --platform="$DOCKER_PLATFORM" \
                --memory=6g \
                --memory-swap=6g \
                --pids-limit=512 \
                --shm-size=512m \
                --rm \
                "${CAPTURE_VOL_ARGS[@]}" \
                "$IMG"; then
                OVERALL_FAIL=1
            fi
            # If we asked to capture the golden, copy it out of the
            # ephemeral $WORK_DIR (which gets rm -rf'd on EXIT) into a
            # stable user-visible location with a timestamp so the
            # operator can review and promote it.
            if [[ "${CAPTURE_GOLDEN:-0}" = "1" && -f "$WORK_DIR/captured/expected.fbf.svg" ]]; then
                STABLE_DIR="$PROJECT_ROOT/reports/text2path-golden"
                mkdir -p "$STABLE_DIR"
                STABLE_PATH="$STABLE_DIR/$(date +%Y%m%d_%H%M%S%z)-expected.fbf.svg"
                cp "$WORK_DIR/captured/expected.fbf.svg" "$STABLE_PATH"
                echo "  Captured golden FBF: $STABLE_PATH"
                echo "  Promote with: cp '$STABLE_PATH' tests/fixtures/e2e/text_frames/expected.fbf.svg"
            fi
            # Same idea for T13 outputs: copy out the rendered PNGs +
            # diff overlays + logs so the threshold can be calibrated
            # from the actual measured numbers.
            if [[ "${CAPTURE_T13:-0}" = "1" && -d "$WORK_DIR/t13" ]]; then
                STABLE_T13="$PROJECT_ROOT/reports/text2path-t13/$(date +%Y%m%d_%H%M%S%z)"
                mkdir -p "$STABLE_T13"
                cp -R "$WORK_DIR/t13/." "$STABLE_T13/"
                echo "  Captured T13 artifacts: $STABLE_T13"
            fi
        fi
        # Always clean up the test image to prevent disk bloat (each
        # build is ~1GB and we re-build from scratch on every run).
        docker rmi -f "$IMG" >/dev/null 2>&1 || true
    fi
fi

echo ""
echo "════════════════════════════════════════════════════════════"
if [[ $OVERALL_FAIL -eq 0 ]]; then
    echo "  ✓ ALL PLATFORMS PASSED — release ready"
    exit 0
else
    echo "  ✗ SOME PLATFORMS FAILED — do NOT release"
    exit 1
fi
