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
trap 'rm -rf "$WORK_DIR"' EXIT

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

echo "  - ruff lint..."
if ! uv run ruff check src/ tests/ scripts/ >/tmp/ruff-lint.log 2>&1; then
    echo "    ✗ ruff lint failed:"
    sed 's/^/      /' /tmp/ruff-lint.log | tail -20
    exit 1
fi

echo "  - ruff format check..."
if ! uv run ruff format --check src/ tests/ scripts/ >/tmp/ruff-fmt.log 2>&1; then
    echo "    ✗ ruff format check failed:"
    sed 's/^/      /' /tmp/ruff-fmt.log | tail -20
    exit 1
fi

echo "  - pyright type check (errors only)..."
if ! uv run pyright src/ >/tmp/pyright.log 2>&1; then
    if grep -q "error:" /tmp/pyright.log; then
        echo "    ✗ pyright reported errors:"
        grep "error:" /tmp/pyright.log | sed 's/^/      /' | head -20
        exit 1
    fi
    # exit code may be non-zero due to warnings only — accept that
fi

echo "  - pytest..."
if ! uv run pytest tests/ -q --no-header >/tmp/pytest.log 2>&1; then
    echo "    ✗ pytest failed:"
    sed 's/^/      /' /tmp/pytest.log | tail -30
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

    run_local() {
        local name="$1"; shift
        if "$@" >/tmp/local-test-out 2>&1; then
            echo "  ✓ $name"
            LOCAL_PASS=$((LOCAL_PASS + 1))
        else
            echo "  ✗ $name"
            sed 's/^/    /' /tmp/local-test-out | tail -10
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
    run_local "E2E byte-exact (fixtures → reference, byte-for-byte)" bash -c "
        cd '$PROJECT_ROOT'
        rm -rf '$WORK_DIR/local-e2e-out'
        '$LOCAL_VENV/bin/svg2fbf' \\
            -i tests/fixtures/e2e/frames \\
            -o '$WORK_DIR/local-e2e-out' \\
            --no-browser --skip-date -s 2.0 -a once -d 6 -c 6 -q
        if ! cmp '$WORK_DIR/local-e2e-out/animation.fbf.svg' '$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg'; then
            echo 'BYTE-EXACT MISMATCH — first diff:' >&2
            diff '$WORK_DIR/local-e2e-out/animation.fbf.svg' '$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg' | head -10 >&2
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

RUN apt-get update && \\
    apt-get install -y --no-install-recommends libxml2-utils $EXTRA_PKGS && \\
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

COPY run_tests.sh /test/run_tests.sh
RUN chmod +x /test/run_tests.sh
CMD ["/test/run_tests.sh"]
DOCKERFILE

        cat > "$WORK_DIR/run_tests.sh" <<'INNER'
#!/bin/bash
set -u
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
    if ! cmp /tmp/e2e-out/animation.fbf.svg /test/tests/fixtures/e2e/expected.fbf.svg; then
        echo "BYTE-EXACT MISMATCH:"
        diff /tmp/e2e-out/animation.fbf.svg /test/tests/fixtures/e2e/expected.fbf.svg | head -10
        exit 1
    fi
'

echo "  Docker result: $PASS passed, $FAIL failed"
[[ $FAIL -gt 0 ]] && { for f in "${FAILS[@]}"; do echo "    - $f"; done; exit 1; }
exit 0
INNER
        chmod +x "$WORK_DIR/run_tests.sh"

        IMG="svg2fbf-clean-test:latest"
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
            if ! docker run --platform="$DOCKER_PLATFORM" --rm "$IMG"; then
                OVERALL_FAIL=1
            fi
        fi
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
