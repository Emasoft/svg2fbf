#!/usr/bin/env bash
# scripts/setup_release_environment.sh
#
# ONE-TIME SETUP for the consolidated `release-pipeline.yml`'s
# human-approval gate. Creates the `stable-release` GitHub
# Environment with required reviewer = Emasoft (or whoever owns
# this repo) and ties it to the master + main branches.
#
# Idempotent: safe to re-run. Skips work that is already done.
#
# WHY THE ENVIRONMENT
#   The new `release-pipeline.yml` has an `await-approval` job that
#   declares `environment: stable-release`. GitHub blocks that job
#   from starting until a required reviewer of the named environment
#   approves the run via the Actions UI ("Review deployment" prompt).
#   This is GitHub's canonical mechanism for human-in-the-loop gates,
#   replacing the old `pull_request_review`-based approval that the
#   legacy `auto-promote-review-to-stable.yml` workflow used.
#
# USAGE
#   ./scripts/setup_release_environment.sh
#
# REQUIREMENTS
#   gh CLI authenticated against this repo with `repo` admin scope
#   (the user who runs this script must be a repo owner or admin —
#   environment configuration is admin-only).
#
# REFERENCES
#   - GitHub Environments: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
#   - Required reviewers: https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/reviewing-deployments

set -euo pipefail

REPO="${1:-Emasoft/svg2fbf}"
ENV_NAME="${2:-stable-release}"
REVIEWERS_VAR="${APPROVERS_ALLOWLIST:-Emasoft}"

echo "▶ Configuring GitHub Environment '${ENV_NAME}' on repo '${REPO}'..."
echo "  Reviewers (from APPROVERS_ALLOWLIST or default): ${REVIEWERS_VAR}"
echo ""

# 1. Resolve each comma-separated login to a numeric user ID.
#    The environments API takes user IDs, not logins.
reviewer_ids=()
IFS=',' read -ra logins <<< "$REVIEWERS_VAR"
for login in "${logins[@]}"; do
  login="$(echo "$login" | xargs)"   # trim whitespace
  [[ -z "$login" ]] && continue
  echo "  Resolving login '$login'..."
  uid=$(GH_HTTP_TIMEOUT=300 gh api "users/$login" --jq '.id')
  if [[ -z "$uid" || "$uid" == "null" ]]; then
    echo "  ✗ Could not resolve login '$login' to a user ID — skipping." >&2
    continue
  fi
  echo "    → id $uid"
  reviewer_ids+=("$uid")
done

if [[ ${#reviewer_ids[@]} -eq 0 ]]; then
  echo "✗ No valid reviewers resolved. Set APPROVERS_ALLOWLIST or pass valid GitHub logins." >&2
  exit 1
fi

# 2. Build the reviewers JSON array for the API call.
#    Format: [{"type":"User","id":<id>}, ...]
reviewers_json="["
for i in "${!reviewer_ids[@]}"; do
  [[ $i -gt 0 ]] && reviewers_json+=", "
  reviewers_json+="{\"type\":\"User\",\"id\":${reviewer_ids[$i]}}"
done
reviewers_json+="]"

# 3. PUT the environment configuration. This both creates the
#    environment if it doesn't exist and updates it if it does.
#    `wait_timer=0` means no enforced waiting period before
#    reviewers can approve. `prevent_self_review=false` lets a
#    reviewer approve their own run (ok for a single-maintainer
#    repo; tighten for larger teams).
echo ""
echo "▶ PUT /repos/${REPO}/environments/${ENV_NAME} with reviewers ${reviewers_json}"
GH_HTTP_TIMEOUT=300 gh api -X PUT \
  "repos/${REPO}/environments/${ENV_NAME}" \
  --input - <<JSON
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "reviewers": ${reviewers_json},
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
JSON

# 4. Tie the environment to master + main branches only — no other
#    branch can deploy through it.
echo ""
echo "▶ Configuring deployment branch policies (master, main)..."
for branch in master main; do
  # The branch-policy API rejects duplicate names, so we list first
  # and only POST if missing.
  existing=$(GH_HTTP_TIMEOUT=300 gh api \
    "repos/${REPO}/environments/${ENV_NAME}/deployment-branch-policies" \
    --jq ".branch_policies[] | select(.name==\"${branch}\") | .id" 2>/tmp/policy.err || true)
  if [[ -n "$existing" ]]; then
    echo "  ✓ branch policy '${branch}' already exists (id $existing)"
    continue
  fi
  GH_HTTP_TIMEOUT=300 gh api -X POST \
    "repos/${REPO}/environments/${ENV_NAME}/deployment-branch-policies" \
    --field "name=${branch}" \
    --field "type=branch" >/tmp/policy.out 2>&1 || true
  echo "  ✓ added branch policy '${branch}'"
done

echo ""
echo "✓ Environment '${ENV_NAME}' configured."
echo ""
echo "VERIFY in the GitHub UI:"
echo "  https://github.com/${REPO}/settings/environments/${ENV_NAME}"
echo ""
echo "NEXT STEP:"
echo "  Trigger the new pipeline via:"
echo "    gh workflow run 'Release Pipeline' -f start_from=testing"
echo "  When the pipeline reaches 'Await human approval', GitHub"
echo "  shows a 'Review deployment' button on the run page. Click"
echo "  it to approve and let the chain advance to master + PyPI."
