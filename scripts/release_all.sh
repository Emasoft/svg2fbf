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

# Re-exec under setsid so we are guaranteed to be the leader of our own
# process group / session. This makes `kill -- -$$` in the memory
# watchdog deterministic: it targets exactly the pgid we just created,
# and the kernel cannot route the signal to the parent shell or runner.
# Without this, when stdin is not a tty (CI runners, sourced from
# another script, piped through tee, etc.), bash often does NOT make
# this script the pgid leader and the watchdog's kill becomes a
# permission-denied no-op — exactly the failure mode the watchdog is
# supposed to prevent.
if [[ -z "${RELEASE_ALL_REEXEC:-}" ]]; then
    export RELEASE_ALL_REEXEC=1
    if command -v setsid >/dev/null 2>&1; then
        # Linux setsid; -w waits for the child so exit codes propagate.
        exec setsid -w "$0" "$@"
    else
        # macOS lacks setsid(1). Use bash -c with job-control mode to
        # force a new pgid for the inner exec. The double-exec trick
        # ensures the inner bash IS the pgid leader.
        exec /usr/bin/env bash -c 'set -m; exec "$0" "$@"' "$0" "$@"
    fi
fi

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

# Background watchdog: every 2s, if host swap usage grows above 4 GB
# (a sane proxy for "memory leak running away"), kill our own pgid so
# all docker subprocesses die. Without this, a Chromium leak inside
# Docker Desktop or under Rosetta can balloon swap to 200GB+ on a
# 64GB host and freeze the user's machine. Tracked separately from
# the container's --memory cap because Docker Desktop on macOS uses a
# Linux VM, and memory accounting between the VM and the host is not
# direct.
#
# Why 2s / 4 GB instead of 10s / 8 GB: empirically Chromium under
# emulation can grow swap by tens of GB per second when leaking. With
# a 10 s poll on a 100 GB/min leak, the *effective* trigger ends up
# closer to 25 GB even though we wanted to abort at 8 GB. Polling
# every 2 s with a 4 GB threshold catches the runaway much sooner; the
# awk cost every 2 s is negligible.
WATCHDOG_PID=
start_memory_watchdog() {
    (
        while true; do
            sleep 2
            if [[ "$(uname -s)" == "Darwin" ]]; then
                # macOS: swap used in MB (sysctl returns "M = 1234.50").
                # MUST force LC_ALL=C — sysctl localizes the decimal
                # separator to ',' under de_DE / fr_FR / it_IT, which the
                # gsub below would strip and then print 100x the real
                # value, instantly tripping the watchdog.
                SWAP_GB=$(LC_ALL=C sysctl vm.swapusage 2>/dev/null \
                    | awk '{for(i=1;i<=NF;i++)if($i=="used"){gsub(/[^0-9.]/,"",$(i+2));print int($(i+2)/1024+0.5);exit}}')
            else
                # Linux: /proc/meminfo SwapTotal-SwapFree, in GB
                SWAP_GB=$(awk '/SwapTotal/{tot=$2}/SwapFree/{free=$2}END{print int((tot-free)/1024/1024+0.5)}' /proc/meminfo 2>/dev/null || echo 0)
            fi
            SWAP_GB=${SWAP_GB:-0}
            if (( SWAP_GB > 4 )); then
                err "🚨 MEMORY WATCHDOG: host swap usage is ${SWAP_GB}GB — aborting to protect the system."
                err "   Likely cause: Chromium leak inside Docker. Killing our process group."
                # Kill our entire process group, which includes Docker
                # subprocesses we spawned.
                kill -TERM -- -$$ 2>&1 || true
                sleep 2
                kill -KILL -- -$$ 2>&1 || true
                exit 0
            fi
        done
    ) &
    WATCHDOG_PID=$!
    # Make sure the watchdog dies with us on any exit path.
    trap 'kill "$WATCHDOG_PID" 2>/dev/null || true' EXIT
}

abort() {
    err "$1"
    [[ -n "${WATCHDOG_PID:-}" ]] && kill "$WATCHDOG_PID" 2>/dev/null || true
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

# Check the docker DAEMON is actually reachable. The Docker quality
# gate fails halfway through if the daemon is down or the active
# context points at a broken socket — fail fast here with a clearer
# message. List active context to make it obvious which one is
# selected (helps when the user has multiple: Docker Desktop, OrbStack,
# remote Docker, etc.).
if ! docker info >/dev/null 2>&1; then
    err "Docker daemon is not reachable."
    err "Active context: $(docker context show 2>/dev/null || echo unknown)"
    err "Available contexts:"
    docker context ls 2>&1 | sed 's/^/    /' >&2 || true
    abort "Start the docker engine, or switch context with: docker context use <name>" 1
fi
ok "Docker daemon reachable (context: $(docker context show 2>/dev/null), engine: $(docker info --format '{{.OperatingSystem}}' 2>/dev/null))"

# Memory pre-flight: refuse to run if the host has less than 8 GB free.
# Why: Puppeteer's Chromium under emulation has been observed leaking
# host memory hard (a previous run pushed swap to 225GB on a 64GB host
# and forced the user to kill iTerm). The container memory cap
# prevents this in the gate, but we also want a host-level guard that
# fails fast BEFORE we start any builds.
if [[ "$(uname -s)" == "Darwin" ]]; then
    # macOS: vm_stat reports memory in pages; page size differs between
    # Intel (4096) and Apple Silicon (16384) — must read it from sysctl,
    # NOT hardcode. Force LC_ALL=C so awk and sysctl produce '.' decimals
    # regardless of user locale.
    PAGE_SIZE="$(LC_ALL=C sysctl -n hw.pagesize)"
    PAGE_USED="$(LC_ALL=C vm_stat | awk -v ps="$PAGE_SIZE" '/Pages free|Pages inactive|Pages purgeable/{sum+=$3+0} END{print sum*ps}')"
    HOST_FREE_GB=$(( PAGE_USED / 1024 / 1024 / 1024 ))
else
    # Linux: /proc/meminfo
    HOST_FREE_GB=$(awk '/MemAvailable/{print int($2/1024/1024)}' /proc/meminfo 2>/dev/null || echo 0)
fi
if (( HOST_FREE_GB < 4 )); then
    err "Host has only ${HOST_FREE_GB}GB available memory."
    err "The Docker gate caps each container at 4GB but launching it"
    err "alongside Docker Desktop/OrbStack itself needs more than 4GB free."
    abort "Free up memory (close apps) or run on a host with more RAM." 1
fi
ok "Host has ${HOST_FREE_GB}GB free memory (>=4GB required)"

# Also issue a hard-limit reminder so the user sees the cap
echo "  Docker memory cap: 4 GB per container, swap disabled, pids-limit 512"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "dev" ]]; then
    abort "Must be on 'dev' branch (currently on '$CURRENT_BRANCH')" 1
fi
ok "On dev branch"

# Use --untracked-files=no — untracked files that ARE gitignored are fine
# (agent runtime state, IDE caches, etc.). Only fail on tracked changes
# OR untracked files that aren't covered by .gitignore.
TRACKED_DIRTY="$(git status --porcelain --untracked-files=no)"
UNTRACKED_NONIGNORED="$(git ls-files --others --exclude-standard)"
if [[ -n "$TRACKED_DIRTY" ]]; then
    err "Tracked files have uncommitted changes:"
    echo "$TRACKED_DIRTY" | sed 's/^/    /' >&2
    abort "Commit or stash first." 1
fi
if [[ -n "$UNTRACKED_NONIGNORED" ]]; then
    err "Untracked files not covered by .gitignore:"
    echo "$UNTRACKED_NONIGNORED" | sed 's/^/    /' >&2
    abort "Either commit them or add them to .gitignore." 1
fi
ok "Working tree clean (tracked + untracked)"

# Verify origin reachable
if ! git ls-remote --exit-code origin HEAD >/dev/null 2>&1; then
    abort "Cannot reach origin. Check network / GitHub token." 1
fi
ok "Origin reachable"

# ---------- 2. QUALITY GATE ----------
log "STEP 2/6: Running full quality gate (lint + types + tests + Docker E2E)"

# Arm the host-side memory watchdog before the heavy Docker work
# starts. Watchdog auto-kills the process group if host swap usage
# exceeds 4 GB (poll every 2 s).
start_memory_watchdog
ok "Memory watchdog armed (pid $WATCHDOG_PID, threshold: 4GB swap, poll: 2s)"

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

    # Snapshot source's tip BEFORE the merge so we can verify afterwards
    # that $target now contains $source's commits (defensive check
    # against a force-pushed/rebased $source making the merge a silent
    # no-op).
    local source_sha
    source_sha="$(git rev-parse "$source")"

    git checkout "$target" || abort "Cannot checkout $target" 3
    # CRITICAL: this MUST abort on persistent failure, not silently break
    # out and proceed to merge. Otherwise an unreachable origin during
    # the inner pull would let us merge against a stale base, push, and
    # publish a release that does not contain origin/$target's commits.
    i=0
    until git -c http.lowSpeedLimit=100 -c http.lowSpeedTime=300 pull --ff-only origin "$target" 2>&1; do
        i=$((i + 1))
        [[ $i -ge 5 ]] && abort "Cannot fast-forward $target from origin (ran out of retries)" 3
        sleep 4
    done

    if ! git merge --no-ff "$source" -m "merge: forward $source → $target via release_all.sh" 2>/dev/null; then
        # Resolve known version-bump conflicts using `--theirs`, where
        # `--theirs` = the incoming branch (the one we are merging FROM).
        # For dev → testing, that's dev; for testing → review, that's
        # testing (which already contains dev's bumps from the previous
        # step); for review → master, that's review. In all three steps
        # this picks the version-bump artifacts from the upstream branch
        # of the chain, which is what we want — pyproject.toml, uv.lock
        # and CHANGELOG.md are always sourced from the upstream branch
        # during a forward-merge release.
        local conflicts
        conflicts="$(git diff --name-only --diff-filter=U)"
        if [[ -n "$conflicts" ]]; then
            for f in pyproject.toml uv.lock CHANGELOG.md; do
                if echo "$conflicts" | grep -qx "$f"; then
                    git checkout --theirs "$f" || abort "Cannot resolve $f" 3
                    git add "$f"
                fi
            done
            # Any unresolved conflicts left? Bail — but FIRST run
            # `git merge --abort` so we leave the working tree on $target
            # at its pre-merge state instead of in a half-merged state
            # that requires manual `git merge --abort` before the user
            # can rerun the script.
            if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
                local unresolved
                unresolved="$(git diff --name-only --diff-filter=U | tr '\n' ' ')"
                git merge --abort 2>/dev/null || true
                abort "Unresolved conflicts on $target: $unresolved" 3
            fi
            git commit --no-edit || abort "Cannot finalize merge on $target" 3
        else
            # Merge failed but produced no conflict markers (e.g. hook
            # rejection, pre-commit failure). Reset back to a clean
            # state so the script is rerunnable without manual recovery.
            git merge --abort 2>/dev/null || true
            abort "Merge $source → $target failed for unknown reason" 3
        fi
    fi

    # Verify the merge actually advanced $target to include $source's
    # tip. If $source was force-pushed/rebased between the snapshot
    # above and the merge, the merge could appear to succeed but leave
    # $target without $source's commits — and we'd then publish a
    # release whose contents don't match the dev branch the user expected.
    if ! git merge-base --is-ancestor "$source_sha" HEAD; then
        abort "After merge, $target does NOT contain $source ($source_sha) — was $source force-pushed during the release?" 3
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

    # Wait for PyPI to make the new version visible. PyPI's CDN (Fastly
    # + CloudFront origin shield) can take 2-5 minutes to serve a
    # newly-published release on every edge — we've seen ~3 min lag in
    # practice. 5 min total budget = 30 attempts × 10 s.
    log "  Waiting for PyPI index to refresh (up to 5 min)..."
    PYPI_CHECK_FILE="$(mktemp -t svg2fbf-pypi-check-XXXXXX.json)"
    for i in $(seq 1 30); do
        if curl -sf "https://pypi.org/pypi/svg2fbf/$PUBLISHED_VERSION/json" -o "$PYPI_CHECK_FILE"; then
            ok "  PyPI sees v$PUBLISHED_VERSION"
            rm -f "$PYPI_CHECK_FILE"
            break
        fi
        sleep 10
        if [[ $i -eq 30 ]]; then
            rm -f "$PYPI_CHECK_FILE"
            abort "PyPI did not pick up v$PUBLISHED_VERSION within 5 min" 5
        fi
    done

    # Run the Docker gate against the PyPI version (NOT the local wheel)
    # Match the host CPU arch exactly via --platform so we test the
    # binary users on this arch will actually receive.
    HOST_ARCH="$(uname -m)"
    case "$HOST_ARCH" in
        arm64|aarch64) DOCKER_PLATFORM="linux/arm64" ;;
        x86_64|amd64)  DOCKER_PLATFORM="linux/amd64" ;;
        *)             DOCKER_PLATFORM="linux/$HOST_ARCH" ;;
    esac
    log "  Using --platform=$DOCKER_PLATFORM (host: $HOST_ARCH)"

    PYPI_VERIFY_DIR="$(mktemp -d -t svg2fbf-pypi-verify-XXXXXX)"
    # Make sure the temp dir AND the verify image are removed even if
    # the script aborts mid-verification (build failure, byte-exact
    # mismatch, signal). Chain the existing watchdog trap so we don't
    # clobber it.
    cleanup_verify() {
        rm -rf "$PYPI_VERIFY_DIR" 2>/dev/null || true
        docker rmi -f "svg2fbf-pypi-verify:$PUBLISHED_VERSION" >/dev/null 2>&1 || true
    }
    trap 'cleanup_verify; kill "$WATCHDOG_PID" 2>/dev/null || true' EXIT
    # FIRST heredoc: UNQUOTED `<<DOCKERFILE` — this is intentional. We
    # WANT $PUBLISHED_VERSION (and the literal-escaped \\, \$ pairs) to
    # be expanded by the parent shell BEFORE the file is written, so the
    # version pin gets baked into the Dockerfile. Anything you add here
    # that uses `$VAR` will be expanded by bash; use `\$VAR` to keep it
    # literal for Docker.
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
    # Guard each fixture copy: if a fixture is missing, `cat` on a
    # non-existent file would print to stderr and create an empty
    # destination, leaving the Docker build to silently produce a
    # broken byte-exact comparison instead of aborting now.
    for src in \
        "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00001.svg" \
        "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00002.svg" \
        "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00003.svg" \
        "$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg"
    do
        [[ -s "$src" ]] || abort "PyPI verification fixture missing or empty: $src" 5
    done
    cat "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00001.svg" > "$PYPI_VERIFY_DIR/f1.svg" || abort "Cannot copy fixture frame00001.svg" 5
    cat "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00002.svg" > "$PYPI_VERIFY_DIR/f2.svg" || abort "Cannot copy fixture frame00002.svg" 5
    cat "$PROJECT_ROOT/tests/fixtures/e2e/frames/frame00003.svg" > "$PYPI_VERIFY_DIR/f3.svg" || abort "Cannot copy fixture frame00003.svg" 5
    cat "$PROJECT_ROOT/tests/fixtures/e2e/expected/animation.fbf.svg" > "$PYPI_VERIFY_DIR/expected.fbf.svg" || abort "Cannot copy fixture animation.fbf.svg" 5
    # SECOND heredoc: QUOTED `<<'DOCKERFILE2'` — this is intentional.
    # No shell expansion; everything goes through verbatim. Adding a
    # line that needs $PUBLISHED_VERSION here would NOT expand — switch
    # to the unquoted heredoc above instead.
    cat >> "$PYPI_VERIFY_DIR/Dockerfile" <<'DOCKERFILE2'
COPY f1.svg /test/tests/fixtures/e2e/frames/frame00001.svg
COPY f2.svg /test/tests/fixtures/e2e/frames/frame00002.svg
COPY f3.svg /test/tests/fixtures/e2e/frames/frame00003.svg
COPY expected.fbf.svg /test/tests/fixtures/e2e/expected.fbf.svg
CMD ["bash", "-c", "cd /test && rm -rf /tmp/o && svg2fbf -i tests/fixtures/e2e/frames -o /tmp/o --no-browser --skip-date -s 2.0 -a once -d 6 -c 6 -q && cmp /tmp/o/animation.fbf.svg /test/tests/fixtures/e2e/expected.fbf.svg && echo BYTE-EXACT-OK"]
DOCKERFILE2
    if ! docker build --platform="$DOCKER_PLATFORM" -q -t "svg2fbf-pypi-verify:$PUBLISHED_VERSION" "$PYPI_VERIFY_DIR" >/dev/null 2>"$PYPI_VERIFY_DIR/build.log"; then
        cat "$PYPI_VERIFY_DIR/build.log" >&2
        abort "PyPI verification: Docker build failed" 5
    fi
    # See test_release_clean.sh for why these limits are required.
    # Memory bumped to 6g (from 4g): puppeteer first-install peak is
    # ~3.1 GB and growing ~10% per minor; 4g leaves <500 MB headroom and
    # has been getting OOM-killed mid-install on recent puppeteer
    # versions. 6g is still safely under the host swap watchdog limit.
    # Capture both stdout/stderr AND the docker exit code separately.
    # Without `set -e`, a non-zero docker exit (e.g. container OOM-killed
    # AFTER printing BYTE-EXACT-OK, or an unrelated docker daemon error)
    # would silently pass the grep below and falsely greenlight a broken
    # release. The `|| RC=$?` pattern works under `set -uo pipefail`
    # because the parens make `RC=0` the default initialiser.
    RC=0
    OUT="$(docker run \
        --platform="$DOCKER_PLATFORM" \
        --memory=6g --memory-swap=6g --pids-limit=512 --shm-size=512m \
        --rm "svg2fbf-pypi-verify:$PUBLISHED_VERSION" 2>&1)" || RC=$?
    docker rmi -f "svg2fbf-pypi-verify:$PUBLISHED_VERSION" >/dev/null 2>&1 || true
    if (( RC != 0 )); then
        echo "$OUT" >&2
        abort "PyPI verification: docker run exited with code $RC" 5
    fi
    if ! echo "$OUT" | grep -q BYTE-EXACT-OK; then
        echo "$OUT" >&2
        abort "PyPI verification: byte-exact comparison FAILED against published artifact" 5
    fi
    rm -rf "$PYPI_VERIFY_DIR"
    # Restore the simple watchdog-only EXIT trap now that verify is
    # complete and the temp dir is gone — no more verify resources to
    # clean up.
    trap 'kill "$WATCHDOG_PID" 2>/dev/null || true' EXIT
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
