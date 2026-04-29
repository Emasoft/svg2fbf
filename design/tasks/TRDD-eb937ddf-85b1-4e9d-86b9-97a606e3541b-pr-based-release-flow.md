# TRDD-eb937ddf-85b1-4e9d-86b9-97a606e3541b — Adapt release.sh to use PR-based promotion (no direct pushes)

**TRDD ID:** `eb937ddf-85b1-4e9d-86b9-97a606e3541b`
**Filename:** `design/tasks/TRDD-eb937ddf-85b1-4e9d-86b9-97a606e3541b-pr-based-release-flow.md`
**Tracked in:** this repo (design/tasks/ is git-tracked)

**Status:** Not started
**Created:** 2026-04-27

---

## User's exact request

> you must adapt the publish script, never push with git directly.. you are bypassing all quality gates and messing with the pip publishing protocol..

This was triggered after the orchestrator (during the v0.1.20 release) used direct `git push origin testing review master` to forward-merge the sudo-fix and tomli-w fix through release branches. Each direct push generated `remote: Bypassed rule violations for refs/heads/<branch>` warnings on the GitHub side, indicating that the protected-branch rules (which require PRs) were being skipped.

## Problem

`scripts/release.sh` currently uses direct git operations on protected release branches:

- Direct `git push origin <branch>` for the version-bump commits and tags
- Direct `git push origin master` for tag and CHANGELOG commits
- Direct `git checkout && git merge --no-ff` between branches when forward-merging
- Direct hard-reset + force-push to sync `main → master` (the most dangerous part)

Effects:
1. Bypasses branch protection rules — a release can be cut even if PR checks would have failed.
2. Bypasses any required PR-review gates (e.g. CODEOWNERS approval).
3. The "main → master" hard reset destroys any commits that landed on `main` directly during the release window (an actual data-loss risk).
4. Forces the human running the script to have direct-push permission, which the project's branch protection is explicitly designed to prevent.

## Goal

Modify `scripts/release.sh` so that every change to a protected branch goes through a Pull Request, while still being scriptable end-to-end (the script should not require manual GitHub-UI clicks).

## Design

### A. Replace direct merges with `gh pr create` + `gh pr merge --auto --merge`

For each channel:

1. Create a temporary release-prep branch off the channel's protected branch:
   ```
   git checkout -b release-prep/<channel>-<version> <channel-branch>
   ```
2. Run `uv version --bump`, regenerate CHANGELOG, commit on the prep branch.
3. Push the prep branch:
   ```
   git push -u origin release-prep/<channel>-<version>
   ```
4. Open a PR via `gh`:
   ```
   gh pr create --base <channel-branch> \
     --head release-prep/<channel>-<version> \
     --title "release: <version>" \
     --body "<git-cliff release notes>"
   ```
5. Wait for required CI checks via `gh pr checks --watch`.
6. Auto-merge once green:
   ```
   gh pr merge --merge --auto --delete-branch
   ```
7. After merge, fast-forward local channel branch to remote, then create the tag:
   ```
   git fetch origin <channel-branch>
   git checkout <channel-branch>
   git reset --hard origin/<channel-branch>
   git tag v<version>
   git push origin v<version>
   ```
8. Create the GitHub Release pointing at the new tag.

### B. Replace forward-merge with PR-based promotion

When promoting `dev → testing → review → master`, instead of:
```
git checkout testing && git merge --no-ff dev
```
do:
```
gh pr create --base testing --head dev --title "promote: <version>"
gh pr merge --merge --auto --delete-branch=false  # keep dev branch
```

### C. Remove the `main ← master` hard-reset sync

The script currently does:
```
git checkout main
git reset --hard master
git push --force-with-lease origin main
```

Replace with a PR `master → main`:
```
gh pr create --base main --head master --title "sync: master → main after <version>"
gh pr merge --merge --auto
```

If `main` and `master` need to be kept identical, configure GitHub to auto-sync via a workflow instead of doing it from the release script.

### D. Pre-flight check

At the top of the script, refuse to run if:
- `gh` CLI is not authenticated (`gh auth status` fails)
- `gh pr` operations are not available (very old `gh` version)
- The branches in question don't have branch protection enabled (we'd be solving a non-problem; warn but allow)

## Files to change

- `scripts/release.sh`: substantial refactor of the per-channel flow
- `.github/workflows/`: may need a new "auto-merge release PR" workflow
- `CONTRIBUTING.md` / docs: document the new release flow

## Test scenarios

1. Run `./scripts/release.sh --beta testing` on a clean branch → should create a PR, wait for CI, auto-merge, tag, push tag, create GitHub release.
2. Run with CI failing on the PR → should NOT auto-merge, NOT create a tag, exit non-zero.
3. Run when `gh` is not authenticated → should fail at pre-flight, not partially.
4. Run all channels (`--beta testing --rc review --stable master`) → each channel's PR should land before the next channel's PR is opened (sequential, not parallel — versions depend on each other).

## Out of scope

- The pre-existing v0.1.20 release happened via the direct-push flow; that won't be retroactively redone.
- Branch protection rule configuration (separate task).
- Adding required CI checks to release PRs (separate task — the protection rules are configured in GitHub, not in the script).

## Why this matters (the "why" the user gave)

> you are bypassing all quality gates and messing with the pip publishing protocol

A PR-based release flow makes the protected branches actually protected, restores the audit trail for each version bump (the PR + its CI run + reviewer approval is the audit), and prevents the script from ever silently shipping a broken version because it could push past failing checks.
