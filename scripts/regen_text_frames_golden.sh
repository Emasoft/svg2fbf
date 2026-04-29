#!/usr/bin/env bash
# regen_text_frames_golden.sh — regenerate the text→path E2E golden
# inside a Docker container.
#
# WHY:
#   svg2fbf's --text2path mode rasterizes each <text> element into glyph
#   <path d="…"> data using fontconfig + the system fonts. Linux DejaVu
#   Sans and macOS DejaVu Sans have slightly different glyph metric
#   tables, so the rendered pixels differ between the two platforms.
#   The Docker E2E test (T12) is now a per-frame visual diff
#   (`sbb-compare --json`, <3% diffPercentage per frame) — it tolerates
#   sub-pixel font drift but still flags real regressions. The golden
#   must still be generated on Linux to keep the calibrated baseline
#   near 0% rather than the ~1-2% cross-platform AA drift floor.
#   Running this on the macOS host would produce a non-Linux golden
#   that gives T12 less headroom for legitimate Linux-side font drift.
#
#   This script always regenerates the golden inside a clean Linux
#   container that mirrors the T12/T13 image (python:3.12-slim with
#   fonts-dejavu + fonts-liberation), so the output is the closest
#   visual match to what the Docker T12 test produces on every run.
#
# DOES NOT REGENERATE the non-text golden (tests/fixtures/e2e/expected/
# animation.fbf.svg) — that one has no font-rasterized content, so
# host vs Docker doesn't matter, and `scripts/regen_e2e_reference.sh`
# is the right tool for it.
#
# SAFE TO RE-RUN: idempotent, leaves no state behind, cleans its image
# tag on exit.
#
# USAGE:
#   ./scripts/regen_text_frames_golden.sh
#
# REGEN_TEXT_GOLDEN_CONFIRM=y skips the interactive confirmation prompt
# (mirrors regen_e2e_reference.sh).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

GOLDEN="tests/fixtures/e2e/text_frames/expected.fbf.svg"
TAG="svg2fbf-regen-text-golden:$(date +%s)"
WORK_DIR="$(mktemp -d -t svg2fbf-regen-text-XXXXXX)"
trap 'docker image rm -f "$TAG" >/dev/null 2>&1 || true; rm -rf "$WORK_DIR"' EXIT

echo "▶ Building wheel from current source..."
uv build --wheel >/dev/null
WHEEL="$(ls -1t dist/svg2fbf-*.whl | head -1)"
[[ -z "$WHEEL" ]] && { echo "✗ uv build did not produce a wheel" >&2; exit 1; }
WHEEL_NAME="$(basename "$WHEEL")"
cp "$WHEEL" "$WORK_DIR/$WHEEL_NAME"

# Stage the input fixture frames (NOT the golden — we are regenerating
# it). The Dockerfile copies these into /work/input.
mkdir -p "$WORK_DIR/input"
for n in 1 2 3 4 5; do
    cp "tests/fixtures/e2e/text_frames/frame0000$n.svg" "$WORK_DIR/input/"
done

# Detect arch — Apple Silicon needs system chromium because Puppeteer's
# bundled Chrome is x86_64-only on Linux. Mirrors test_release_clean.sh.
#
# HOST_ARCH override: allows regenerating on a different platform than
# the host (e.g., amd64 emulation on arm64 Mac via Docker buildx) so
# the golden matches what CI's amd64 runners produce. Defaults to the
# host's actual arch when unset. Common override:
#   HOST_ARCH=x86_64 ./scripts/regen_text_frames_golden.sh
HOST_ARCH="${HOST_ARCH:-$(uname -m)}"
case "$HOST_ARCH" in
    arm64|aarch64)
        PLATFORM=linux/arm64
        EXTRA_PKGS="chromium chromium-driver"
        EXTRA_ENV='ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true'$'\n''ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium'
        ;;
    *)
        PLATFORM=linux/amd64
        EXTRA_PKGS=""
        EXTRA_ENV=""
        ;;
esac

cat > "$WORK_DIR/Dockerfile" <<DOCKERFILE
# Mirrors test_release_clean.sh's image so the regenerated golden is
# guaranteed to match what the T12/T13 test compares against.
FROM python:3.12-slim
RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        libxml2-utils \\
        fonts-dejavu fonts-liberation \\
        curl ca-certificates unzip git \\
        $EXTRA_PKGS && \\
    rm -rf /var/lib/apt/lists/*
$EXTRA_ENV
COPY $WHEEL_NAME /tmp/$WHEEL_NAME
RUN pip install --no-cache-dir /tmp/$WHEEL_NAME
WORKDIR /work
DOCKERFILE

echo "▶ Building Docker image (mirroring test_release_clean.sh)..."
docker build --platform="$PLATFORM" -t "$TAG" "$WORK_DIR" >/dev/null

echo "▶ Running svg2fbf --text2path inside Docker..."
mkdir -p "$WORK_DIR/output"
# Mount the inputs at the SAME relative path that T12 expects
# (tests/fixtures/e2e/text_frames/) so the <fbf:sourceFramesPath>
# embedded in the FBF matches what the test harness produces. Anything
# else here would force a manual sed-fix on the regenerated golden.
docker run --rm --platform="$PLATFORM" \
    -v "$WORK_DIR/input:/work/tests/fixtures/e2e/text_frames:ro" \
    -v "$WORK_DIR/output:/work/output" \
    "$TAG" \
    bash -c '
        set -euo pipefail
        cd /work
        svg2fbf -i tests/fixtures/e2e/text_frames -o output \
            --no-browser --skip-date --text2path \
            -s 2.0 -a once -d 6 -c 6 -q
    '

NEW_GOLDEN="$WORK_DIR/output/animation.fbf.svg"
[[ -f "$NEW_GOLDEN" ]] || { echo "✗ svg2fbf did not produce $NEW_GOLDEN" >&2; exit 1; }

if [[ -f "$GOLDEN" ]] && cmp -s "$GOLDEN" "$NEW_GOLDEN"; then
    echo "✓ $GOLDEN is already up to date — no regen needed."
    exit 0
fi

echo ""
echo "Diff between current golden and freshly-regenerated output:"
{ diff -u "$GOLDEN" "$NEW_GOLDEN" || true; } | head -60
echo ""

if [[ "${REGEN_TEXT_GOLDEN_CONFIRM:-}" =~ ^[yY]$ ]]; then
    confirm=y
else
    read -r -p "Apply this change to $GOLDEN? [y/N]: " confirm
fi
if [[ ! "$confirm" =~ ^[yY]$ ]]; then
    echo "Aborted — golden NOT updated."
    exit 1
fi

cp "$NEW_GOLDEN" "$GOLDEN"
echo "✓ Updated $GOLDEN"
echo ""
echo "Now commit explicitly:"
echo "  git add $GOLDEN"
echo "  git commit -m 'test: regen text_frames golden (<reason>)'"
