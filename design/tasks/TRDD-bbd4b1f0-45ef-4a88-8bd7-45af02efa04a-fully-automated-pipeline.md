# TRDD-bbd4b1f0 — Fully Automated Release Pipeline

**TRDD ID:** `bbd4b1f0-45ef-4a88-8bd7-45af02efa04a`
**Filename:** `design/tasks/TRDD-bbd4b1f0-45ef-4a88-8bd7-45af02efa04a-fully-automated-pipeline.md`
**Tracked in:** this repo (design/tasks/ is git-tracked)
**Status:** Spec — not yet implemented. Pickup-ready for the next session.
**Author note:** drafted at the end of a long session that already
landed cross-platform CI (Linux/macOS/Windows auto-install + release
dry-run) and partially-implemented promotion gates. This TRDD is the
self-contained brief for the next session, which will start from a
compacted context.

---

## 1. Context

### 1.1 Project owner's policy (verbatim, simplified)

- **dev**: the *only* branch where the developer intervenes manually.
  Expected to be broken at any time.
- **testing (beta)**, **review (rc)**, **master (stable)**, **main**
  (mirror): handled exclusively by automation. The developer should
  not touch them, ever.
- **testing → review**: must pass *all* CI checks first.
- **review → master**: must wait for user/AI review approval.
- **master**: where the PyPI publish happens via `scripts/release.sh`.

### 1.2 What's already in place at the time this TRDD is written

- Cross-platform CI for the auto-install lane:
  - `.github/workflows/linux-autoinstall.yml`
  - `.github/workflows/macos-autoinstall.yml`
  - `.github/workflows/windows-autoinstall.yml`
- Release-blocking gate as a CI job:
  - `.github/workflows/release-dry-run.yml` runs
    `scripts/test_release_clean.sh --docker-only` on push/PR to
    testing/review/master/main.
- Promotion-gate CI verification (manual `just`-invoked):
  - `just promote-to-review` now refuses to merge if any CI run on
    `origin/testing@HEAD` is not `success`.
  - `just promote-to-stable` does the same for `origin/review@HEAD`
    plus an explicit `read -r -p` approval prompt
    (`PROMOTE_TO_STABLE_APPROVED=y` for non-interactive).
- All the above is path-filtered to keep CI minutes bounded; `dev`
  is excluded from every trigger because dev is WIP.

### 1.3 What's missing — the gap this TRDD closes

The promotion *gates* exist but the *promotion itself* is still a
manual `just promote-to-…` invocation. The owner's vision is "the
developer only thinks about dev"; that means the three downstream
hops have to fire automatically once their preconditions are met,
not when the developer remembers to type a command.

## 2. Architecture: four GitHub Actions workflows

### 2.1 `auto-promote-testing-to-review.yml`

**Purpose:** when *every* CI check on `testing@HEAD` succeeds, fast-
forward-merge testing into review and push.

**Trigger:**
```yaml
on:
  workflow_run:
    workflows:
      - "Linux Auto-Install"
      - "macOS Auto-Install"
      - "Windows Auto-Install"
      - "Release Dry-Run (Docker E2E)"
      - "CI/CD Pipeline"     # the existing ci.yml's lint/test/build
      - "Quality (Ruff + Secrets via UV)"
    types: [completed]
    branches: [testing]
```

**Logic:**
1. Resolve `origin/testing@HEAD` SHA.
2. List **all** workflow runs for that SHA via `gh run list --commit`.
3. Require: every run's `conclusion == "success"` (treat `skipped`
   as success). If anything is `in_progress` / `failure` /
   `cancelled` / `action_required`, no-op and exit 0 (silently
   waiting for the next check_suite.completed event).
4. Once all green, merge testing into review with `--no-ff` and a
   commit message like
   `auto: testing → review (all CI green at <SHA>)`. Push.
5. On any error, `gh issue create` with title
   `pipeline: auto-promote testing → review failed at <SHA>`
   and body containing the failure detail + log links.

**Permissions:**
```yaml
permissions:
  contents: write   # for the merge + push
  actions: read     # for gh run list
  issues: write     # for the failure issue
```

### 2.2 `auto-promote-review-to-stable.yml`

**Purpose:** when a designated approver (human or AI) signs off on
the `review` branch's HEAD, fast-forward-merge review into master
and push.

**Trigger:**
```yaml
on:
  pull_request_review:        # human or AI review approvals
    types: [submitted]
  workflow_dispatch:          # manual escape hatch
    inputs:
      approved_sha:
        description: "review SHA being approved"
        required: true
```

**Logic:**
1. If event is `pull_request_review`: only proceed if
   `review.state == 'approved'` AND `review.user.login` is in the
   project's approver allowlist (set via repository variable
   `APPROVERS_ALLOWLIST`, comma-separated).
2. Resolve the SHA being approved (the PR head, or
   `inputs.approved_sha` for `workflow_dispatch`). It MUST be on
   the `review` branch — refuse otherwise.
3. Re-verify CI on that SHA (defense in depth — same all-green
   check as 2.1) — even though release-dry-run already gated it
   into review, an interim push to review could have introduced
   drift.
4. Merge review into master with `--no-ff` and message
   `auto: review → master (approved by <user> at <SHA>)`.
5. Push.
6. On error: `gh issue create` (same pattern as 2.1).

**Permissions:**
```yaml
permissions:
  contents: write
  pull-requests: read
  actions: read
  issues: write
```

### 2.3 `auto-publish-stable.yml`

**Purpose:** when master receives a new commit (always from
auto-promote-review-to-stable, never from a direct push — see
§3.1), run `scripts/release.sh --stable master` to bump version,
tag, create the GitHub release, and publish to PyPI.

**Trigger:**
```yaml
on:
  push:
    branches: [master]
```

**Logic:**
1. Verify the head commit author is the GitHub Actions bot
   (rejects accidental human pushes — see §3.1).
2. Run the existing `./scripts/release.sh --stable master`. The
   script already handles version bump, changelog regen, tag,
   GitHub release, and PyPI publish via `uv publish`.
3. Sync the `main` branch to `master` (existing
   `just sync-main` recipe).
4. On error: `gh issue create`.

**Secrets needed:**
- `PYPI_API_TOKEN` (already required by current release.sh).

**Permissions:**
```yaml
permissions:
  contents: write     # for the tag + main sync
  id-token: write     # for trusted PyPI publishing
  issues: write
```

### 2.4 `pipeline-failure-notifier.yml` (cross-cutting)

Centralise the "auto-promotion silently can't proceed" failure
mode. Subscribed workflows POST a summary to a single sticky GitHub
issue ("Pipeline status: <last update>"); 2.1/2.2/2.3 each call it
on failure instead of opening their own issues. Avoids the
notification-fatigue trap the owner already flagged.

## 3. Branch-protection requirements (one-time setup)

### 3.1 master, main

- `Require a pull request before merging`: ON.
- `Require status checks`: all three auto-install workflows + the
  release-dry-run + ci.yml/quality.yml.
- `Restrict who can push`: only the GitHub Actions bot.
- `Require linear history`: ON (no merge bubbles).

### 3.2 review

- Same status-check requirements.
- `Require a pull request before merging`: ON (since 2.2 needs a
  PR to attach the approval to).

### 3.3 testing

- `Require status checks`: same set, but allow direct push (since
  `just promote-to-testing` from dev is a developer action, not a
  PR).

### 3.4 dev

No protection. Developer playground.

## 4. Promotion-gate code already in justfile (keep as belt-and-suspenders)

`just promote-to-review` and `just promote-to-stable` already
verify CI green via `gh run list --commit`. Even after the auto-
promotion workflows land, keep the just recipes — they're useful
for emergency manual operation when the auto-pipeline itself is
broken (chicken-and-egg). Both currently honor a
`PROMOTE_FORCE=y` env var to skip the gate; that should remain
documented as the only manual escape hatch.

## 5. File-by-file implementation plan

| File | What |
|---|---|
| `.github/workflows/auto-promote-testing-to-review.yml` | NEW. Per §2.1. |
| `.github/workflows/auto-promote-review-to-stable.yml` | NEW. Per §2.2. |
| `.github/workflows/auto-publish-stable.yml` | NEW. Per §2.3. |
| `.github/workflows/pipeline-failure-notifier.yml` | NEW. Per §2.4. |
| `scripts/release.sh` | small change — accept `--from-ci` flag that skips the interactive sanity prompts. |
| `docs/RELEASE_WORKFLOW.md` | rewrite the "Development Workflow" + "Release Process" sections to reflect dev-only-developer model. |
| `CONTRIBUTING.md` | new "How releases happen" subsection. |
| `CLAUDE.md` | branch-policy summary update. |
| `tests/scripts/test_promotion_pipeline.sh` | NEW. Smoke test that simulates the whole chain on a scratch branch set (push to testing → CI → auto-promote → auto-publish). Runs in `workflow_dispatch` only. |

## 6. Sequence of work for the next session

1. Read this TRDD top-to-bottom.
2. Verify the current state of CI: `gh run list -R Emasoft/svg2fbf --limit 10` — last known-good commits noted in §1.2.
3. Configure branch protection rules per §3 via `gh api` calls
   (or `cpv-setup-branch-rules` skill if applicable).
4. Implement `auto-promote-testing-to-review.yml`. Test by pushing
   a no-op change to testing and watching it auto-promote.
5. Implement `auto-promote-review-to-stable.yml`. Test by opening
   a PR onto review and approving it.
6. Implement `auto-publish-stable.yml`. Test by merging into
   master via a dry-run that doesn't actually publish (use
   `--no-pypi` flag on release.sh).
7. Implement `pipeline-failure-notifier.yml` and wire 2.1-2.3 to
   it.
8. Update docs.
9. Tag the change as `chore: fully automated pipeline (TRDD-bbd4b1f0)`.

## 7. Open questions for the next session

- Approver allowlist for §2.2: who counts as an "AI reviewer"?
  Suggestion: a designated GitHub App (e.g., a Claude PR-review
  bot) whose login goes into `APPROVERS_ALLOWLIST`. Need owner
  decision on the bot identity.
- Should the auto-promotion run on a *cron* fallback in case the
  `workflow_run` event misses a check completion? Defensive belt-
  and-suspenders or YAGNI?
- The pipeline TRDD-ad386cb7 (§3.1 — pin Bun + svg-text2path
  versions) is still open and could land in parallel. Decision:
  do that *before* turning on auto-publish, since unpinned upstream
  drift would silently publish a different artifact than what was
  reviewed.

## 8. Non-goals

- This TRDD does not propose changing the four-branch model itself
  (dev → testing → review → master + main mirror). That structure
  is sound; only the *operation* of moving code through it is being
  automated.
- This TRDD does not touch the developer's `just promote-to-testing`
  command — that's the single manual gesture the owner explicitly
  wants to keep.
- This TRDD does not propose CI on `dev`. dev is WIP and expected
  to fail; gating it would defeat its purpose.
