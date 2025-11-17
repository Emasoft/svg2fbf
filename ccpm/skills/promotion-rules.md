# Promotion Rules for svg2fbf Pipeline

## Overview

Code flows through the 5-branch pipeline via **merge-based promotion**. Each promotion is a deliberate, human-supervised merge that moves code from one quality gate to the next.

```
dev → testing → review → master → main
 ↓       ↓        ↓        ↓       ↓
alpha   beta     rc     stable  (mirror)
```

## Promotion Commands (Human-Executed)

### 1. `just promote-to-testing` (dev → testing)

**What it does**:
```bash
git checkout testing
git merge dev --no-ff -m "Promote dev to testing"
git push origin testing
```

**When to use**:
- Features on dev are complete and tested locally
- Ready for broader QA testing
- Tests pass on dev (preferred but not required)

**Agent responsibilities BEFORE promotion**:
1. ✅ Run full test suite: `pytest tests/`
2. ✅ Run linting: `ruff check src/ tests/`
3. ✅ Run formatting check: `ruff format --check src/ tests/`
4. ✅ Update documentation if features were added
5. ✅ Commit all changes with conventional commit messages
6. ✅ Push dev branch to origin
7. ✅ Create Draft PR (if not already created)
8. ✅ Notify human: "Ready for promotion to testing"

**Agent responsibilities DURING promotion**:
- ❌ DO NOT execute the promotion command yourself
- ✅ Monitor the merge for conflicts
- ✅ If conflicts, help human resolve them

**Agent responsibilities AFTER promotion**:
- ✅ Switch worktree to testing branch (if needed for bug fixes)
- ✅ Verify promoted features work on testing
- ✅ Report any issues discovered

---

### 2. `just promote-to-review` (testing → review)

**What it does**:
```bash
git checkout review
git merge testing --no-ff -m "Promote testing to review (RC)"
git push origin review
```

**When to use**:
- QA testing on testing branch is complete
- All known bugs are fixed
- Ready for final approval before production

**Agent responsibilities BEFORE promotion**:
1. ✅ ALL tests MUST pass (no exceptions)
2. ✅ Linting MUST pass: `ruff check src/ tests/`
3. ✅ Formatting MUST pass: `ruff format --check src/ tests/`
4. ✅ Security scan MUST pass: `trufflehog git file://. --only-verified`
5. ✅ Documentation MUST be up-to-date
6. ✅ CHANGELOG.md entry created (human-supervised)
7. ✅ All Draft PRs converted to Ready for Review
8. ✅ Request human approval explicitly

**Agent responsibilities DURING promotion**:
- ❌ DO NOT execute the promotion command yourself
- ✅ Monitor CI on review branch (CI is ENABLED)
- ✅ If CI fails, investigate and report findings

**Agent responsibilities AFTER promotion**:
- ✅ Verify CI passes on review branch
- ✅ NO new development work (review is freeze branch)
- ⚠️ Only critical bug fixes allowed (with human supervision)

---

### 3. `just promote-to-stable` (review → master)

**What it does**:
```bash
git checkout master
git merge review --no-ff -m "Promote review to stable"
git push origin master
```

**When to use**:
- Review branch has passed all CI checks
- Human stakeholders approve release
- Ready for production/PyPI publication

**Agent responsibilities BEFORE promotion**:
- ❌ NO agent involvement
- ✅ Human decision ONLY

**Agent responsibilities DURING promotion**:
- ❌ NO agent involvement

**Agent responsibilities AFTER promotion**:
- ✅ Observe release process (learn from it)
- ✅ Update any agent-maintained documentation
- ❌ DO NOT trigger `just publish`

---

### 4. `just sync-main` (master → main)

**What it does**:
```bash
git checkout main
git merge master --ff-only
git push origin main
```

**When to use**:
- After promoting to master
- To keep main in sync (main is protected default branch)

**Agent responsibilities**:
- ❌ NO agent involvement (human or automatic only)

---

## Emergency Override: `just equalize` (DANGEROUS)

**What it does**:
```bash
# Force-syncs ALL branches to current branch
# Destructive operation that overwrites divergent history
```

**When to use**:
- Emergency recovery from catastrophic git corruption
- After manual git surgery that broke normal flow
- **EXTREMELY RARE** - Maybe once per year

**Agent responsibilities**:
- ❌ **NEVER USE THIS COMMAND**
- ❌ **NEVER SUGGEST USING THIS COMMAND**
- ❌ **NEVER INCLUDE IN AUTOMATION**
- ✅ If human mentions using it, ask for confirmation
- ✅ Warn about data loss potential

**Why it's dangerous**:
- Overwrites testing, review, master, main with current branch
- Destroys all divergent work on other branches
- Can lose commits that haven't been merged yet
- Breaks ongoing work by other contributors
- Cannot be undone easily

---

## Promotion Safety Checks

### Pre-Promotion Checklist

Before requesting promotion to ANY branch:

```bash
# 1. Verify clean working tree
git status  # Should show "nothing to commit, working tree clean"

# 2. Run full test suite
pytest tests/

# 3. Run linting
ruff check src/ tests/

# 4. Run formatting check
ruff format --check src/ tests/

# 5. Security scan (testing → review only)
trufflehog git file://. --only-verified

# 6. Verify branch is up-to-date with origin
git fetch origin
git status  # Should NOT show "Your branch is behind 'origin/...'"

# 7. Verify correct branch
git branch --show-current  # Should be dev or testing
```

### Post-Promotion Verification

After human executes promotion:

```bash
# 1. Verify merge was successful
git log --oneline -5  # Check for merge commit

# 2. Pull latest changes
git pull origin <branch-name>

# 3. If CI enabled (review/master/main), check CI status
gh pr checks  # or monitor GitHub Actions UI

# 4. Smoke test key features
pytest tests/test_<critical_feature>.py
```

---

## Merge Conflicts During Promotion

If promotion encounters merge conflicts:

### Agent Role:
1. ✅ Identify conflicting files
2. ✅ Read both versions (current branch and incoming)
3. ✅ Understand why conflict occurred
4. ✅ Suggest resolution strategy to human
5. ❌ DO NOT resolve conflicts yourself (unless supervised)

### Conflict Resolution Process:
```bash
# Human will do:
git checkout <target-branch>
git merge <source-branch>  # Conflict occurs

# Agent assists:
git status  # Show conflicting files
git diff <file>  # Show conflict markers

# Human resolves conflicts and commits
git add <resolved-files>
git commit -m "Merge <source> into <target>: resolve conflicts in <files>"
```

---

## Multi-Channel Release System

Each branch maps to a release channel with different audiences:

| Branch  | Channel | Audience              | Installation (Example)           |
|---------|---------|------------------------|----------------------------------|
| dev     | alpha   | Developers only       | `uv tool install svg2fbf@0.1.11a1` |
| testing | beta    | QA testers            | `uv tool install svg2fbf@0.1.11b1` |
| review  | rc      | Release candidates    | `uv tool install svg2fbf@0.1.11rc1` |
| master  | stable  | Production users      | `uv tool install svg2fbf`        |
| main    | (mirror)| Default branch        | Same as master                   |

**Note**: Prerelease versions require exact version specification (e.g., `@0.1.11a1`). See `ccpm/agent-skills/uv-comprehensive-guide.md` for UV command reference.

**Agent responsibilities**:
- ✅ Understand which channel code is targeting
- ✅ Adjust quality expectations accordingly
- ✅ Test on appropriate channel before promoting
- ❌ NEVER publish to PyPI (production) from pre-release channels

---

## Version Bumping (Human-Supervised)

Versions follow semantic versioning with pre-release markers:

- `0.1.8a0` - Alpha (dev branch)
- `0.1.8b0` - Beta (testing branch)
- `0.1.8rc0` - Release Candidate (review branch)
- `0.1.8` - Stable (master branch)

**Agent responsibilities**:
- ❌ DO NOT manually edit `__version__` in pyproject.toml
- ✅ Version bumps happen via `just publish` (human-executed)
- ✅ Understand version semantics (major.minor.patch)
- ✅ Suggest appropriate version bump (patch vs minor vs major)

**Version bump guidelines**:
- **Patch** (0.1.8 → 0.1.9): Bug fixes only
- **Minor** (0.1.9 → 0.2.0): New features, backward-compatible
- **Major** (0.2.0 → 1.0.0): Breaking changes, API changes

---

## Changelog Integration

During promotions, CHANGELOG.md may be updated:

**Agent responsibilities**:
- ❌ DO NOT edit CHANGELOG.md directly (protected file)
- ✅ CHANGELOG is auto-generated by git-cliff during `just publish`
- ✅ Ensure commit messages follow conventional commits format
- ✅ Understand how commits map to changelog sections:
  - `feat:` → Features section
  - `fix:` → Bug Fixes section
  - `docs:` → Documentation section
  - `chore:` → Miscellaneous section

**Conventional commit format**:
```
<type>(<scope>): <description>

<body>

<footer>
```

**Examples**:
```
feat(svg2fbf): Add support for nested <g> elements
fix(validator): Correct viewBox validation regex
docs(README): Update installation instructions
chore(deps): Bump ruff to 0.8.5
```

---

## Promotion Scenarios

### Scenario 1: Normal Feature Development

1. Agent works on issue-123 in dev worktree
2. Agent commits with `feat(core): Add new feature`
3. Agent runs tests, linting, formatting (all pass)
4. Agent pushes to origin/dev
5. Agent creates Draft PR
6. Agent notifies human: "Ready for promotion to testing"
7. Human executes `just promote-to-testing`
8. Agent verifies on testing branch
9. Agent fixes any bugs discovered during testing
10. Process repeats for testing → review → master

### Scenario 2: Bug Fix on Testing Branch

1. Bug discovered on testing branch during QA
2. Agent creates new worktree from testing
3. Agent commits with `fix(validator): Correct edge case`
4. Agent runs tests (all pass)
5. Agent pushes to origin/testing
6. Agent notifies human: "Bug fix ready for review"
7. Human promotes testing → review → master
8. Human cherry-picks fix back to dev if needed

### Scenario 3: Critical Hotfix on Master

1. Production bug reported
2. Human creates `hotfix/v0.1.9-critical` from master
3. Agent works on hotfix branch (supervised)
4. Agent commits with `fix(security): Patch CVE-2025-12345`
5. Human reviews immediately
6. Human merges hotfix → master
7. Human tags release v0.1.9
8. Human cherry-picks to dev/testing/review

---

## Key Principles

1. **Sequential Flow**: Always dev → testing → review → master (no skipping)
2. **Merge-Based**: Use `git merge --no-ff` to preserve branch history
3. **Human-Supervised**: Agents request, humans execute promotions
4. **Quality Gates**: Each promotion raises quality expectations
5. **No Force-Push**: Respect git history, never rewrite public branches
6. **CI Awareness**: review/master/main have CI, failures block progress
7. **Rollback Safety**: All merges are revertible with `git revert`

## Summary

**Agent Role**: Prepare code for promotion, verify quality, request human approval
**Human Role**: Execute promotion commands, resolve conflicts, approve releases
**Never Use**: `just equalize`, force-push, direct commits to review/master/main
**Always Use**: Conventional commits, testing, linting, human review
