#!/usr/bin/env bash
# Install git hooks (pre-commit framework + custom hooks)
# This script can be run after cloning or if .git/ is recreated

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔗 Installing git hooks..."
echo ""

# Check if .git exists
if [ ! -d ".git" ]; then
    echo "❌ Error: Not a git repository (.git not found)"
    echo "   Run: git init"
    exit 1
fi

# ============================================================================
# 1. Install pre-commit framework hooks
# ============================================================================

if [ -f ".pre-commit-config.yaml" ]; then
    echo "📦 Installing pre-commit framework hooks..."

    # Check if pre-commit is available
    if command -v pre-commit &> /dev/null; then
        pre-commit install --install-hooks
        pre-commit install --hook-type pre-push
        echo "✅ Pre-commit hooks installed"
    else
        echo "⚠️  pre-commit not found. Install with:"
        echo "   uv pip install pre-commit"
        echo "   or: pip install pre-commit"
    fi
    echo ""
else
    echo "ℹ️  No .pre-commit-config.yaml found (skipping)"
    echo ""
fi

# ============================================================================
# 2. Install custom hooks from scripts/hooks/
# ============================================================================

CUSTOM_HOOKS_DIR="$SCRIPT_DIR/hooks"

if [ -d "$CUSTOM_HOOKS_DIR" ] && [ "$(ls -A "$CUSTOM_HOOKS_DIR" 2>/dev/null)" ]; then
    echo "📦 Installing custom hooks from scripts/hooks/..."

    for hook_file in "$CUSTOM_HOOKS_DIR"/*; do
        if [ -f "$hook_file" ]; then
            hook_name=$(basename "$hook_file")

            # Skip README or non-executable files
            if [[ "$hook_name" == "README"* ]] || [[ "$hook_name" == "."* ]]; then
                continue
            fi

            echo "  → Installing: $hook_name"

            # Copy to .git/hooks/
            cp "$hook_file" ".git/hooks/$hook_name"
            chmod +x ".git/hooks/$hook_name"

            echo "    ✓ Installed: .git/hooks/$hook_name"
        fi
    done

    echo "✅ Custom hooks installed"
    echo ""
else
    echo "ℹ️  No custom hooks in scripts/hooks/ (skipping)"
    echo ""
fi

# ============================================================================
# Summary
# ============================================================================

echo "✅ Git hooks installation complete!"
echo ""
echo "Installed hooks:"
ls -1 .git/hooks/ | grep -v sample | grep -v "\.bak$" || echo "  (none)"
echo ""
echo "To test hooks:"
echo "  git commit -m \"test\""
echo ""
echo "To skip hooks (use sparingly):"
echo "  git commit --no-verify -m \"message\""
