#!/usr/bin/env bash
# release_all.sh — single-entry orchestrator for the FULL release pipeline.
#
# Runs everything from "I have changes on dev that I want to publish" through
# "v0.1.X is on PyPI and verified", as ONE command, with no intermediate
# manual steps.
#
# WHAT IT DOES (in order, gated — any failure aborts the whole pipeline):
#
#   1. PRE-FLIGHT
#      - Verify required tools: uv, gh (authenticated), docker, git
#      - Verify on dev branch with clean working tree
#      - Verify origin is reachable (network up, GitHub token valid)
#
#   2. QUALITY GATE (scripts/test_release_clean.sh)
#      - Source-level: ruff lint, ruff format, pyright (errors), pytest
#      - Build wheel from current source
#      - Local install verification (macOS or Linux host)
#      - Docker install verification (clean python:3.12-slim, NO node/npm)
#      - Byte-exact E2E (fixture frames → reference output, byte-for-byte)
#      - --auto-repair-viewbox bootstrap (svg2fbf installs Node+Puppeteer
#        and processes broken-viewBox frames end-to-end)
#
#   3. FORWARD-MERGE (dev → testing → review → master)
#      - Each step uses dev's pyproject.toml/uv.lock/CHANGELOG.md (those
#        are version-bump artifacts where dev is the source of truth).
#      - All four branches end up containing the same source.
#
#   4. MULTI-CHANNEL RELEASE (scripts/release.sh)
#      - Runs the channel sequence alpha → beta → rc → stable.
#      - Each channel re-runs the quality gate inside release.sh.
#      - Stable channel publishes to PyPI.
#
#   5. POST-PUBLISH VERIFICATION
#      - Re-run the Docker quality gate against the version freshly
#        downloaded from PyPI (NOT the local wheel) — final proof that
#        what users will pip install actually works.
#      - Verify the new version shows on PyPI's API.
#
#   6. REPORT
#      - PyPI URL, GitHub release URL, version number, SHA-256 of the
#        published wheel.
#
# WARNING: this script direct-pushes to protected branches. PR-based
# migration is tracked in TRDD-eb937ddf-85b1-4e9d-86b9-97a606e3541b.
# Until that lands, only run as a maintainer with direct-push permission.
#
# USAGE:
#   ./scripts/release_all.sh                    # interactive (asks before publish)
#   ./scripts/release_all.sh --yes              # non-interactive
#   ./scripts/release_all.sh --no-pypi          # GitHub releases only, skip PyPI
#   ./scripts/release_all.sh --gate-only        # just run the quality gate, no release
#   ./scripts/release_all.sh --skip-verify      # skip post-publish PyPI verification
#
# EXIT CODES:
#   0  — all steps passed, release published, post-verification passed
#   1  — pre-flight failed
#   2  — quality gate failed (no release was attempted)
#   3  — forward-merge failed
#   4  — release.sh failed mid-pipeline
#   5  — post-publish verification failed (release IS live but may be broken)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ---------- argument parsing ----------
YES=false
NO_PYPI=false
GATE_ONLY=false
SKIP_VERIFY=false

for arg in "$@"; do
    case "$arg" in
        --yes)         YES=true ;;
        --no-pypi)     NO_PYPI=true ;;
        --gate-only)   GATE_ONLY=true ;;
        --skip-verify) SKIP_VERIFY=true ;;
        --help|-h)
            sed -n '2,75p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Run with --help for usage." >&2
            exit 1
            ;;
    esac
done

# ---------- helpers ----------
log()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
err()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }
abort() {
    err "$1"
    [[ $# -ge 2 ]] && exit "$2" || exit 1
}

# ---------- 1. PRE-FLIGHT ----------
log "STEP 1/6: Pre-flight checks"

for tool in uv gh docker git python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        abort "Required tool not on PATH: $tool" 1
    fi
done
ok "All required tools present"

if ! gh auth status >/dev/null 2>&1; then
    abort "gh CLI is not authenticated. Run: gh auth login" 1
fi
ok "GitHub CLI authenticated"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "dev" ]]; then
    abort "Must be on 'dev' branch (currently on '$CURRENT_BRANCH')" 1
fi
ok "On dev branch"

if [[ -n "$(git status --porcelain)" ]]; then
    abort "Working tree has uncommitted changes. Commit or stash first." 1
fi
ok "Working tree clean"

# Verify origin reachable
if ! git ls-remote --exit-code origin HEAD >/dev/null 2>&1; then
    abort "Cannot reach origin. Check network / GitHub token." 1
fi
ok "Origin reachable"

# ---------- 2. QUALITY GATE ----------
log "STEP 2/6: Running full quality gate (lint + types + tests + Docker E2E)"

if ! "$PROJECT_ROOT/scripts/test_release_clean.sh"; then
    abort "Quality gate FAILED — release aborted. Fix issues and rerun." 2
fi
ok "Quality gate passed"

if $GATE_ONLY; then
    log "--gate-only specified; stopping after gate."
    ok "Gate passed. No release attempted."
    exit 0
fi

# ---------- approval prompt ----------
if ! $YES; then
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  Quality gate passed. About to:"
    echo "  - Forward-merge dev → testing → review → master"
    echo "  - Push all four branches to origin"
    echo "  - Run release pipeline (alpha + beta + rc + stable)"
    if $NO_PYPI; then
        echo "  - SKIP PyPI publish (--no-pypi specified)"
    else
        echo "  - PUBLISH STABLE TO PyPI"
    fi
    echo "═══════════════════════════════════════════════════════════════════"
    read -r -p "Proceed? [y/N]: " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        ok "Aborted by user. Nothing was changed."
        exit 0
    fi
fi

# ---------- 3. FORWARD-MERGE ----------
log "STEP 3/6: Forward-merging dev → testing → review → master"

# Pull latest dev from origin
i=0
until git -c http.lowSpeedLimit=100 -c http.lowSpeedTime=300 pull --ff-only origin dev; do
    i=$((i + 1))
    [[ $i -ge 5 ]] && abort "Cannot fast-forward dev from origin" 3
    sleep 4
done

forward_merge() {
    local target="$1"
    local source="$2"
    log "  Merge $source → $target"

    git checkout "$target" || abort "Cannot checkout $target" 3
    i=0
    until git -c http.lowSpeedLimit=100 -c http.lowSpeedTime=300 pull --ff-only origin "$target" 2>&1; do
        i=$((i + 1))
        [[ $i -ge 3 ]] && break
        sleep 4
    done

    if ! git merge --no-ff "$source" -m "merge: forward $source → $target via release_all.sh" 2>/dev/null; then
        # Resolve known version-bump conflicts in dev's favor.
        # These three files are version-bump artifacts where dev is always the
        # source of truth during a release pipeline.
        local conflicts
        conflicts="$(git diff --name-only --diff-filter=U)"
        if [[ -n "$conflicts" ]]; then
            for f in pyproject.toml uv.lock CHANGELOG.md; do
                if echo "$conflicts" | grep -qx "$f"; then
                    git checkout --theirs "$f" || abort "Cannot resolve $f" 3
                    git add "$f"
                fi
            done
            # Any unresolved conflicts left? Bail.
            if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
                abort "Unresolved conflicts on $target: $(git diff --name-only --diff-filter=U | tr '\n' ' ')" 3
            fi
            git commit --no-edit || abort "Cannot finalize merge on $target" 3
        else
            abort "Merge $source → $target failed for unknown reason" 3
        fi
    fi
}

forward_merge testing dev
forward_merge review testing
forward_merge master review

# Push all four branches
log "  Pushing dev/testing/review/master to origin"
i=0
until git -c http.lowSpeedLimit=100 -c http.lowSpeedTime=300 push origin dev testing review master 2>&1; do
    i=$((i + 1))
    [[ $i -ge 10 ]] && abort "Cannot push branches to origin" 3
    sleep 4
done

ok "All four branches forward-merged and pushed"

# ---------- 4. MULTI-CHANNEL RELEASE ----------
log "STEP 4/6: Running release.sh for all four channels"

git checkout master || abort "Cannot checkout master" 4

# Source .env if present (UV_PUBLISH_TOKEN, GH_TOKEN, etc.)
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_ROOT/.env"
    set +a
fi

# Build the release.sh argument list
RELEASE_ARGS=(--alpha dev --beta testing --rc review --stable master)
$NO_PYPI && RELEASE_ARGS+=(--no-pypi)

# release.sh asks for stable approval interactively. When --yes is set we
# pipe 'y' to stdin so the prompt is auto-answered.
if $YES; then
    if ! yes y | "$PROJECT_ROOT/scripts/release.sh" "${RELEASE_ARGS[@]}"; then
        abort "release.sh failed mid-pipeline" 4
    fi
else
    if ! "$PROJECT_ROOT/scripts/release.sh" "${RELEASE_ARGS[@]}"; then
        abort "release.sh failed mid-pipeline" 4
    fi
fi
ok "All channels released"

# Find the published version
PUBLISHED_VERSION="$(uv version | awk '{print $2}')"
ok "Published version: $PUBLISHED_VERSION"

# ---------- 5. POST-PUBLISH VERIFICATION ----------
if $SKIP_VERIFY || $NO_PYPI; then
    log "STEP 5/6: Skipping post-publish PyPI verification"
else
    log "STEP 5/6: Re-running clean Docker test against the PyPI release"

    # Wait for PyPI to make the new version visible
    log "  Waiting for PyPI index to refresh..."
    for i in 1 2 3 4 5 6; do
        if curl -sf "https://pypi.org/pypi/svg2fbf/$PUBLISHED_VERSION/json" -o /tmp/pypi-check.json; then
            ok "  PyPI sees v$PUBLISHED_VERSION"
            break
        fi
        sleep 10
        [[ $i -eq 6 ]] && abort "PyPI did not pick up v$PUBLISHED_VERSION within 60s" 5
    done

    # Run the Docker gate against the PyPI version (NOT the local wheel)
    PYPI_VERIFY_DIR="$(mktemp -d -t svg2fbf-pypi-verify-XXXXXX)"
    cat > "$PYPI_VERIFY_DIR/Dockerfile" <<DOCKERFILE
FROM python:3.12-slim
RUN apt-get update && \\
    apt-get install -y --no-install-recommends libxml2-utils chromium && \\
    rm -rf /var/lib/apt/lists/*
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
WORKDIR /test
RUN python -m venv /opt/venv && \\
    /opt/venv/bin/pip install --no-cache-dir "svg2fbf==$PUBLISHED_VERSION"
ENV PATH="/opt/venv/bin:\$PATH"
RUN mkdir -p /test/tests/fixtures/e2e/frames /test/tests/fixtures/e2e/broken_frames
DOCKERFILE
    cat "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00001.svg" > "$PYPI_VERIFY_DIR/f1.svg"
    cat "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00002.svg" > "$PYPI_VERIFY_DIR/f2.svg"
    cat "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00003.svg" > "$PYPI_VERIFY_DIR/f3.svg"
    cat "$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg" > "$PYPI_VERIFY_DIR/expected.fbf.svg"
    cat >> "$PYPI_VERIFY_DIR/Dockerfile" <<'DOCKERFILE2'
COPY f1.svg /test/tests/fixtures/e2e/frames/frame00001.svg
COPY f2.svg /test/tests/fixtures/e2e/frames/frame00002.svg
COPY f3.svg /test/tests/fixtures/e2e/frames/frame00003.svg
COPY expected.fbf.svg /test/tests/fixtures/e2e/expected.fbf.svg
CMD ["bash", "-c", "cd /test && rm -rf /tmp/o && svg2fbf -i tests/fixtures/e2e/frames -o /tmp/o --no-browser --skip-date -s 2.0 -a once -d 6 -c 6 -q && cmp /tmp/o/animation.fbf.svg /test/tests/fixtures/e2e/expected.fbf.svg && echo BYTE-EXACT-OK"]
DOCKERFILE2
    if ! docker build -q -t "svg2fbf-pypi-verify:$PUBLISHED_VERSION" "$PYPI_VERIFY_DIR" >/dev/null 2>"$PYPI_VERIFY_DIR/build.log"; then
        cat "$PYPI_VERIFY_DIR/build.log" >&2
        abort "PyPI verification: Docker build failed" 5
    fi
    OUT="$(docker run --rm "svg2fbf-pypi-verify:$PUBLISHED_VERSION" 2>&1)"
    if ! echo "$OUT" | grep -q BYTE-EXACT-OK; then
        echo "$OUT" >&2
        abort "PyPI verification: byte-exact comparison FAILED against published artifact" 5
    fi
    rm -rf "$PYPI_VERIFY_DIR"
    ok "Post-publish PyPI verification: PyPI artifact matches the byte-exact reference"
fi

# ---------- 6. REPORT ----------
log "STEP 6/6: Final report"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  ✅ RELEASE PIPELINE COMPLETE"
echo "═══════════════════════════════════════════════════════════════════"
echo "  Version:        $PUBLISHED_VERSION"
echo "  GitHub release: https://github.com/Emasoft/svg2fbf/releases/tag/v$PUBLISHED_VERSION"
if ! $NO_PYPI; then
    echo "  PyPI:           https://pypi.org/project/svg2fbf/$PUBLISHED_VERSION/"
    WHEEL="$(ls "$PROJECT_ROOT/dist/svg2fbf-$PUBLISHED_VERSION-py3-none-any.whl" 2>/dev/null | head -1)"
    if [[ -n "$WHEEL" ]]; then
        SHA="$(shasum -a 256 "$WHEEL" 2>/dev/null | awk '{print $1}')"
        [[ -z "$SHA" ]] && SHA="$(sha256sum "$WHEEL" 2>/dev/null | awk '{print $1}')"
        echo "  Wheel SHA-256:  $SHA"
    fi
fi
echo "═══════════════════════════════════════════════════════════════════"
exit 0
