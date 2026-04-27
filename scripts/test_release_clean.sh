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
        HOST_ARCH="$(uname -m)"
        # On Apple Silicon hosts, Puppeteer's chromium isn't ARM64 — install
        # system chromium so the END-TO-END pipeline can be tested. Real
        # x86_64 Linux servers don't need this.
        if [[ "$HOST_ARCH" == "arm64" || "$HOST_ARCH" == "aarch64" ]]; then
            EXTRA_PKGS="chromium"
            EXTRA_ENV='ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium'
            ARCH_NOTE="(ARM64 host: using system chromium since Puppeteer ships x86_64-only)"
        else
            EXTRA_PKGS=""
            EXTRA_ENV=""
            ARCH_NOTE="(x86_64 host: using Puppeteer's bundled Chrome)"
        fi
        echo "  Host arch: $HOST_ARCH $ARCH_NOTE"

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

RUN mkdir -p /test/frames
COPY frames/frame00001.svg /test/frames/
COPY frames/frame00002.svg /test/frames/
COPY needs_viewbox.svg /test/

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
run "svg-repair-viewbox auto-install Node+Puppeteer + repair" \
    svg-repair-viewbox /test/needs_viewbox.svg
run "check_dependencies after install (Ready=True)" bash -c '
    /opt/svg2fbf-venv/bin/python -c "import auto_install_deps; r,m=auto_install_deps.check_dependencies(); print(r,m); exit(0 if r else 1)"'
run "browser-open helper logic" /opt/svg2fbf-venv/bin/python -c "
from svg2fbf.main import _is_browser_available
assert _is_browser_available('python3'); assert not _is_browser_available('this-fake-browser-12345')
assert _is_browser_available('/usr/bin/python3'); assert not _is_browser_available('/applications/nope.app')
print('OK')"

echo "  Docker result: $PASS passed, $FAIL failed"
[[ $FAIL -gt 0 ]] && { for f in "${FAILS[@]}"; do echo "    - $f"; done; exit 1; }
exit 0
INNER
        chmod +x "$WORK_DIR/run_tests.sh"

        IMG="svg2fbf-clean-test:latest"
        if ! docker build -q -t "$IMG" "$WORK_DIR" >/dev/null 2>"$WORK_DIR/build.log"; then
            echo "  ✗ Docker build failed"
            sed 's/^/    /' "$WORK_DIR/build.log" | tail -10
            OVERALL_FAIL=1
        else
            if ! docker run --rm "$IMG"; then
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
