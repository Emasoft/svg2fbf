#!/usr/bin/env bash
# tests/scripts/test_promotion_pipeline.sh
#
# Smoke test for the four auto-promotion workflows introduced in
# TRDD-bbd4b1f0. Runs static checks that catch the cheapest class of
# breakage — YAML syntax, required-permissions blocks, cross-workflow
# references, and `release.sh --from-ci` discoverability — without
# pretending to simulate a real promotion (which would require Docker,
# scratch branches, and a fake CI). The corresponding GitHub Actions
# workflow runs this on `workflow_dispatch` only.
#
# Failure modes intentionally NOT tested here (require integration env):
#   - actual workflow_run wiring on GitHub
#   - branch-protection enforcement
#   - PyPI publish (release.sh --stable)
#   - auto-opened PR review→master
#
# Local invocation:
#   ./tests/scripts/test_promotion_pipeline.sh

set -euo pipefail

# Resolve project root regardless of caller cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

WORKFLOW_DIR=".github/workflows"
RELEASE_SH="scripts/release.sh"

pass=0
fail=0
failures=()

check() {
  local name="$1"
  shift
  if "$@" >/tmp/pp-out 2>&1; then
    pass=$((pass + 1))
    printf '  ✓ %s\n' "$name"
  else
    fail=$((fail + 1))
    failures+=("$name")
    printf '  ✗ %s\n' "$name"
    sed 's/^/      /' </tmp/pp-out
  fi
}

# ---- 1. Required workflow files exist -----------------------------------
echo "[1/5] Required workflow files exist"
required_files=(
  "$WORKFLOW_DIR/auto-promote-testing-to-review.yml"
  "$WORKFLOW_DIR/auto-promote-review-to-stable.yml"
  "$WORKFLOW_DIR/auto-publish-stable.yml"
  "$WORKFLOW_DIR/pipeline-failure-notifier.yml"
  "$WORKFLOW_DIR/cross-platform-verify.yml"
)
for f in "${required_files[@]}"; do
  check "exists: $f" test -f "$f"
done

# ---- 2. YAML parseability ----------------------------------------------
# The repo already exercises ruff/python tooling in CI, so Python is a
# safe assumption. If pyyaml is missing we fall back to yamllint or skip.
echo "[2/5] YAML parses cleanly"
if python3 -c "import yaml" 2>/dev/null; then
  for f in "${required_files[@]}"; do
    check "yaml.safe_load: $f" python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$f"
  done
elif command -v yamllint >/dev/null 2>&1; then
  for f in "${required_files[@]}"; do
    check "yamllint: $f" yamllint -d "{rules: {document-start: disable, line-length: disable, truthy: disable, comments: disable, indentation: disable}}" "$f"
  done
else
  echo "  ! Skipping (no python3+yaml or yamllint available)"
fi

# ---- 3. Cross-workflow references --------------------------------------
echo "[3/5] Cross-workflow references resolve"
for f in auto-promote-testing-to-review auto-promote-review-to-stable auto-publish-stable; do
  check "$f references pipeline-failure-notifier.yml" \
    grep -q "uses: ./.github/workflows/pipeline-failure-notifier.yml" "$WORKFLOW_DIR/$f.yml"
done

# Required permissions: each promotion workflow must declare contents:write
echo "[3/5] Required permissions declared"
for f in auto-promote-testing-to-review auto-promote-review-to-stable auto-publish-stable; do
  check "$f declares contents: write" \
    grep -q "contents: write" "$WORKFLOW_DIR/$f.yml"
done

# ---- 4. release.sh --from-ci flag is wired up ---------------------------
echo "[4/5] release.sh --from-ci wiring"
check "release.sh exists" test -f "$RELEASE_SH"
check "release.sh has --from-ci in argument parser" grep -q -- "--from-ci)" "$RELEASE_SH"
check "release.sh has from_ci variable" grep -q "^from_ci=" "$RELEASE_SH"
check "release.sh skips approval prompt when from_ci=true" \
  grep -q 'if \[\[ "$from_ci" == "true" \]\]' "$RELEASE_SH"
check "release.sh --help mentions --from-ci" \
  grep -q -- "--from-ci" "$RELEASE_SH"
check "release.sh syntactically valid (bash -n)" bash -n "$RELEASE_SH"

# ---- 5. Approver allowlist logic (literal grep, not execution) ---------
echo "[5/5] APPROVERS_ALLOWLIST handling"
check "auto-promote-review-to-stable references vars.APPROVERS_ALLOWLIST" \
  grep -q "vars.APPROVERS_ALLOWLIST" "$WORKFLOW_DIR/auto-promote-review-to-stable.yml"
check "fail-closed: empty allowlist refuses to merge" \
  grep -q "APPROVERS_ALLOWLIST repository variable is empty" "$WORKFLOW_DIR/auto-promote-review-to-stable.yml"
check "auto-publish-stable rejects non-bot pushes to master" \
  grep -q "github-actions\[bot\]" "$WORKFLOW_DIR/auto-publish-stable.yml"

# ---- 6. Cross-Platform Verify gate is wired up -------------------------
echo "[6/6] Cross-Platform Verify gating"
check "cross-platform-verify covers all 3 OSes" \
  bash -c "grep -q 'ubuntu-latest' $WORKFLOW_DIR/cross-platform-verify.yml && grep -q 'macos-latest' $WORKFLOW_DIR/cross-platform-verify.yml && grep -q 'windows-latest' $WORKFLOW_DIR/cross-platform-verify.yml"
check "cross-platform-verify covers Python 3.11/3.12/3.13" \
  bash -c "grep -q '\"3.11\"' $WORKFLOW_DIR/cross-platform-verify.yml && grep -q '\"3.12\"' $WORKFLOW_DIR/cross-platform-verify.yml && grep -q '\"3.13\"' $WORKFLOW_DIR/cross-platform-verify.yml"
check "cross-platform-verify has NO path filter (always fires)" \
  bash -c "! grep -B1 -A1 'paths:' $WORKFLOW_DIR/cross-platform-verify.yml | grep -q 'pyproject\\|src/'"
check "cross-platform-verify smoke covers numpy + svg_text2path + uharfbuzz" \
  bash -c "grep -q 'import numpy' $WORKFLOW_DIR/cross-platform-verify.yml && grep -q 'import svg_text2path' $WORKFLOW_DIR/cross-platform-verify.yml && grep -q 'uharfbuzz' $WORKFLOW_DIR/cross-platform-verify.yml"
check "auto-publish-stable's publish job depends on wait-for-cross-platform" \
  grep -q "needs: wait-for-cross-platform" "$WORKFLOW_DIR/auto-publish-stable.yml"
check "wait-for-cross-platform polls 'Cross-Platform Verify' workflow by name" \
  grep -q '"Cross-Platform Verify"' "$WORKFLOW_DIR/auto-publish-stable.yml"
check "wait-for-cross-platform fails closed on non-success conclusion" \
  grep -q "Refusing to publish — fix the platform-specific" "$WORKFLOW_DIR/auto-publish-stable.yml"

# ---- Summary -----------------------------------------------------------
echo
echo "=================================================================="
echo "  passed: $pass"
echo "  failed: $fail"
if (( fail > 0 )); then
  echo "  failures:"
  for f in "${failures[@]}"; do
    echo "    - $f"
  done
  echo "=================================================================="
  exit 1
fi
echo "=================================================================="
echo "  All promotion-pipeline smoke checks passed."
