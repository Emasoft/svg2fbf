#!/usr/bin/env bash
# Setup branch protection for svg2fbf 5-branch workflow
set -euo pipefail

echo "🔒 Setting up branch protection for svg2fbf..."
echo ""

# Main branch (mirror, no direct pushes)
echo "📌 Protecting main (mirror branch, no direct pushes)..."
gh api repos/Emasoft/svg2fbf/branches/main/protection \
  --method PUT \
  --field enforce_admins=true \
  --field required_pull_request_reviews[required_approving_review_count]=0 \
  --field allow_force_pushes=false \
  --field allow_deletions=false \
  --field required_conversation_resolution=true \
  --silent || echo "  ⚠️  Failed to protect main"

# Master branch (production, requires review)
echo "📌 Protecting master (production, requires 1 review)..."
gh api repos/Emasoft/svg2fbf/branches/master/protection \
  --method PUT \
  --field enforce_admins=false \
  --field required_pull_request_reviews[required_approving_review_count]=1 \
  --field required_pull_request_reviews[dismiss_stale_reviews]=true \
  --field allow_force_pushes=false \
  --field allow_deletions=false \
  --field required_conversation_resolution=true \
  --silent || echo "  ⚠️  Failed to protect master"

# Review branch (RC, CI required)
echo "📌 Protecting review (release candidate, CI must pass)..."
gh api repos/Emasoft/svg2fbf/branches/review/protection \
  --method PUT \
  --field enforce_admins=false \
  --field required_status_checks[strict]=true \
  --field required_status_checks[contexts][]=[] \
  --field allow_force_pushes=false \
  --field allow_deletions=false \
  --silent || echo "  ⚠️  Failed to protect review"

# Testing branch (beta)
echo "📌 Protecting testing (beta, no force pushes)..."
gh api repos/Emasoft/svg2fbf/branches/testing/protection \
  --method PUT \
  --field enforce_admins=false \
  --field allow_force_pushes=false \
  --field allow_deletions=false \
  --silent || echo "  ⚠️  Failed to protect testing"

# Dev branch (allow force push for rebasing, prevent deletion)
echo "📌 Protecting dev (development, allow force push but no deletion)..."
gh api repos/Emasoft/svg2fbf/branches/dev/protection \
  --method PUT \
  --field enforce_admins=false \
  --field allow_force_pushes=true \
  --field allow_deletions=false \
  --silent || echo "  ⚠️  Failed to protect dev"

echo ""
echo "✅ Branch protection configured!"
echo ""
echo "Verifying protected branches:"
gh api repos/Emasoft/svg2fbf/branches --jq '.[] | select(.protected == true) | "  ✓ \(.name)"'
echo ""
echo "Summary of protection rules:"
echo "  • main:    No force push, no deletion, sync from master only"
echo "  • master:  Requires 1 review, no force push, no deletion"
echo "  • review:  CI required, no force push, no deletion"
echo "  • testing: No force push, no deletion"
echo "  • dev:     Force push allowed, no deletion"
