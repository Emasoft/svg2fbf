#!/usr/bin/env bash
# validate.sh - Shared code quality validation for pre-push and release
#
# This script runs all validation checks to ensure code quality.
# It is used by:
#   - scripts/hooks/pre-push (before git push)
#   - scripts/release.sh (before releasing)
#   - Manually via: ./scripts/validate.sh
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
#
# Usage:
#   ./scripts/validate.sh           # Run all checks
#   ./scripts/validate.sh --quick   # Skip tests (lint/format only)
#   ./scripts/validate.sh --quiet   # Minimal output

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
QUICK_MODE=false
QUIET_MODE=false
for arg in "$@"; do
    case $arg in
        --quick) QUICK_MODE=true ;;
        --quiet) QUIET_MODE=true ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --quick    Skip tests (lint/format only)"
            echo "  --quiet    Minimal output"
            echo "  -h, --help Show this help"
            exit 0
            ;;
    esac
done

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Verify we're in the right place
if [[ ! -f "pyproject.toml" ]]; then
    echo -e "${RED}❌ Error: pyproject.toml not found in $PROJECT_ROOT${NC}" >&2
    exit 1
fi

# Track failures
FAILED=0
CHECKS_RUN=0
CHECKS_PASSED=0

# ============================================================================
# Helper Functions
# ============================================================================

log_header() {
    if [[ "$QUIET_MODE" == "false" ]]; then
        echo ""
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${BLUE}  $1${NC}"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
    fi
}

log_step() {
    local step_num=$1
    local total=$2
    local emoji=$3
    local msg=$4

    if [[ "$QUIET_MODE" == "false" ]]; then
        echo -e "${YELLOW}[$step_num/$total]${NC} $emoji $msg"
    fi
}

log_pass() {
    if [[ "$QUIET_MODE" == "false" ]]; then
        echo -e "      ${GREEN}✓ $1${NC}"
    fi
    ((CHECKS_PASSED++))
}

log_fail() {
    echo -e "      ${RED}✗ $1${NC}" >&2
    FAILED=1
}

log_warn() {
    if [[ "$QUIET_MODE" == "false" ]]; then
        echo -e "      ${YELLOW}⚠ $1${NC}"
    fi
}

# ============================================================================
# Validation Checks
# ============================================================================

run_lint_check() {
    ((CHECKS_RUN++))
    log_step "$CHECKS_RUN" "$TOTAL_CHECKS" "🔍" "Running lint check (ruff)..."

    if uv run ruff check src/ tests/ --quiet 2>/dev/null; then
        log_pass "Lint check passed"
        return 0
    else
        log_fail "Lint check failed"
        if [[ "$QUIET_MODE" == "false" ]]; then
            echo ""
            echo "      Fix lint errors with:"
            echo "        uv run ruff check --fix src/ tests/"
            echo "      Or run: just lint-fix"
            echo ""
        fi
        return 1
    fi
}

run_format_check() {
    ((CHECKS_RUN++))
    log_step "$CHECKS_RUN" "$TOTAL_CHECKS" "✨" "Running format check (ruff format)..."

    if uv run ruff format --check src/ tests/ 2>/dev/null; then
        log_pass "Format check passed"
        return 0
    else
        log_fail "Format check failed"
        if [[ "$QUIET_MODE" == "false" ]]; then
            echo ""
            echo "      Fix formatting with:"
            echo "        uv run ruff format src/ tests/"
            echo "      Or run: just fmt"
            echo ""
        fi
        return 1
    fi
}

run_tests() {
    ((CHECKS_RUN++))
    log_step "$CHECKS_RUN" "$TOTAL_CHECKS" "🧪" "Running tests (pytest)..."

    if uv run pytest -q --tb=no 2>/dev/null; then
        log_pass "All tests passed"
        return 0
    else
        log_fail "Tests failed"
        if [[ "$QUIET_MODE" == "false" ]]; then
            echo ""
            echo "      Run tests manually for details:"
            echo "        pytest -v"
            echo "      Or run: just test"
            echo ""
        fi
        return 1
    fi
}

run_secret_scan() {
    ((CHECKS_RUN++))
    log_step "$CHECKS_RUN" "$TOTAL_CHECKS" "🔐" "Running secret scan (trufflehog)..."

    if ! command -v trufflehog &> /dev/null; then
        log_warn "trufflehog not installed (skipping)"
        echo "      Install with: brew install trufflehog"
        return 0
    fi

    # Build trufflehog command
    local TRUFFLEHOG_CMD
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        TRUFFLEHOG_CMD="trufflehog git file://. --since-commit origin/main --branch HEAD --results=verified,unknown --fail"
    else
        TRUFFLEHOG_CMD="trufflehog filesystem --results=verified,unknown --fail ."
    fi

    # Add exclude paths if file exists
    if [[ -f ".trufflehog-exclude-paths.txt" ]]; then
        TRUFFLEHOG_CMD="$TRUFFLEHOG_CMD --exclude-paths .trufflehog-exclude-paths.txt"
    fi

    if eval "$TRUFFLEHOG_CMD" 2>/dev/null; then
        log_pass "No secrets detected"
        return 0
    else
        log_fail "Potential secrets detected!"
        if [[ "$QUIET_MODE" == "false" ]]; then
            echo ""
            echo "      Review the trufflehog output and either:"
            echo "        - Remove the secrets from the commit"
            echo "        - Add false positives to .trufflehog-exclude-paths.txt"
            echo ""
        fi
        return 1
    fi
}

# ============================================================================
# Main
# ============================================================================

# Calculate total checks
if [[ "$QUICK_MODE" == "true" ]]; then
    TOTAL_CHECKS=3  # lint, format, secrets
else
    TOTAL_CHECKS=4  # lint, format, tests, secrets
fi

log_header "CODE QUALITY VALIDATION"

# Run checks
run_lint_check || true
run_format_check || true

if [[ "$QUICK_MODE" == "false" ]]; then
    run_tests || true
fi

run_secret_scan || true

# ============================================================================
# Results
# ============================================================================

if [[ "$QUIET_MODE" == "false" ]]; then
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
fi

if [[ $FAILED -eq 1 ]]; then
    echo -e "${RED}❌ VALIDATION FAILED${NC} ($CHECKS_PASSED/$CHECKS_RUN checks passed)"

    if [[ "$QUIET_MODE" == "false" ]]; then
        echo ""
        echo "Quick fixes:"
        echo "  just lint-fix    # Auto-fix lint issues"
        echo "  just fmt         # Auto-fix formatting"
        echo "  just test        # Run tests with details"
        echo ""
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    fi
    exit 1
else
    echo -e "${GREEN}✅ VALIDATION PASSED${NC} ($CHECKS_PASSED/$CHECKS_RUN checks passed)"

    if [[ "$QUIET_MODE" == "false" ]]; then
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    fi
    exit 0
fi
