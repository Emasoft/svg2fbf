# Development Guide

This guide covers everything you need to contribute to svg2fbf, including development setup, building, testing, and version management.

For contribution guidelines, pull request process, and code of conduct, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Table of Contents

- [⚠️ AI Agent Workflow Warning](#️-ai-agent-workflow-warning)
  - [🚫 Dangerous Operations - NEVER Do These](#-dangerous-operations---never-do-these)
  - [✅ Safe Agent Operations](#-safe-agent-operations)
  - [📋 Required Agent Workflow](#-required-agent-workflow)
  - [🛡️ CCPM Plugin (Recommended for AI Agents)](#️-ccpm-plugin-recommended-for-ai-agents)
- [Branch Workflow & Development Stages](#branch-workflow--development-stages)
  - [Development Pipeline Overview](#development-pipeline-overview)
  - [Branch Workflow Table](#branch-workflow-table)
  - [Detailed Branch Descriptions](#detailed-branch-descriptions)
  - [Why CI is Disabled on dev/testing](#why-ci-is-disabled-on-devtesting)
  - [Branch Promotion Commands](#branch-promotion-commands)
  - [Branch Equalization Command](#branch-equalization-command)
    - [When to Use `just equalize` vs `just promote-*`](#when-to-use-just-equalize-vs-just-promote-)
    - [Key Differences](#key-differences)
    - [Example Scenarios](#example-scenarios)
    - [Safety Features](#safety-features)
    - [Auto-Generated Commits Are Safe to Lose](#auto-generated-commits-are-safe-to-lose)
  - [Release Commands](#release-commands)
  - [Installing Released Versions](#installing-released-versions)
  - [Common Development Patterns](#common-development-patterns)
- [Setting Up Development Environment](#setting-up-development-environment)
  - [Prerequisites](#prerequisites)
  - [Initial Setup](#initial-setup)
  - [⚠️ CRITICAL: Single Virtual Environment Policy](#️-critical-single-virtual-environment-policy)
- [Installation for Development](#installation-for-development)
  - [Option 1: Editable Installation in Virtual Environment](#option-1-editable-installation-in-virtual-environment)
  - [Option 2: Install as uv Tool (Development Mode)](#option-2-install-as-uv-tool-development-mode)
  - [Option 3: Build and Install from Wheel (Development Build)](#option-3-build-and-install-from-wheel-development-build)
- [Building](#building)
  - [Quick Development Build (Recommended)](#quick-development-build-recommended)
  - [Build Process Details](#build-process-details)
  - [What's Included in Releases](#whats-included-in-releases)
- [Testing](#testing)
  - [⚠️ IMPORTANT: Test-Generated FBF Files Are NOT Valid for Production](#️-important-test-generated-fbf-files-are-not-valid-for-production)
  - [Running Tests](#running-tests)
  - [Test Tolerance System](#test-tolerance-system)
  - [Test Tolerance Presets](#test-tolerance-presets)
  - [Test Documentation](#test-documentation)
- [Code Quality](#code-quality)
  - [Formatting and Linting](#formatting-and-linting)
  - [Type Checking](#type-checking)
  - [Pre-commit Checks](#pre-commit-checks)
- [Version Management](#version-management)
  - [Standard Version Bumps](#standard-version-bumps)
  - [Pre-release Versions](#pre-release-versions)
    - [Creating the First Pre-release](#creating-the-first-pre-release)
    - [Incrementing Pre-release Numbers](#incrementing-pre-release-numbers)
    - [Finalizing a Release](#finalizing-a-release)
  - [Complete Pre-release Workflow Example](#complete-pre-release-workflow-example)
  - [Version Workflow Checklist](#version-workflow-checklist)
  - [Pre-release Distribution](#pre-release-distribution)
  - [Version Naming Convention](#version-naming-convention)
- [Project Structure](#project-structure)
  - [Key Files](#key-files)
- [Development Tips](#development-tips)
  - [Quick Development Cycle](#quick-development-cycle)
  - [Debugging Test Failures](#debugging-test-failures)
  - [Working with YAML Configs](#working-with-yaml-configs)
- [Getting Help](#getting-help)

## ⚠️ AI Agent Workflow Warning

> **CRITICAL FOR AI AGENTS**: If you are an AI agent (or working with AI agents), you **MUST** read this section before making any changes to the repository.

### 🚫 Dangerous Operations - NEVER Do These

AI agents must **NEVER** perform these operations:

1. **❌ NEVER run `just equalize`**
   - This command force-syncs ALL branches to the current branch
   - **Destroys divergent work** on other branches
   - Can cause **catastrophic data loss**
   - **Human-supervised only** for emergency recovery

2. **❌ NEVER run `just publish`**
   - Triggers **production releases** to PyPI
   - **Permanent and irreversible** (cannot delete from PyPI)
   - **Human decision only**

3. **❌ NEVER push to `master`, `main`, or `review` directly**
   - These are **production/pre-production branches**
   - Require human approval and CI validation
   - Use the promotion commands instead

4. **❌ NEVER modify protected files**:
   - `justfile` - Build infrastructure
   - `scripts/release.sh` - Release automation
   - `CHANGELOG.md` - Auto-generated by git-cliff
   - `.github/workflows/*` - CI/CD pipelines
   - `pyproject.toml` - Core configuration

5. **❌ NEVER use `git push --force`**
   - Rewrites public git history
   - Breaks other contributors' work
   - Can lose commits permanently

6. **❌ NEVER merge your own PRs**
   - All PRs require **human review**
   - Wait for maintainer approval

### ✅ Safe Agent Operations

Agents **ARE allowed** to:
- ✅ Work on `dev` or `testing` branches
- ✅ Create feature branches from `dev`
- ✅ Make commits with conventional commit format
- ✅ Run tests, linting, and formatting
- ✅ Create **Draft PRs** (not ready for merge)
- ✅ Request human review

### 📋 Required Agent Workflow

**ALL agents MUST follow this workflow:**

1. **Develop new features in `dev` branch**
   ```bash
   git checkout dev
   # ... develop feature ...
   git commit -m "feat: Add new feature"
   git push origin dev
   ```

2. **Promote to `testing` ONLY when feature is COMPLETE**
   ```bash
   # Feature must be fully implemented before promotion
   just promote-to-testing
   ```

3. **Debug and fix bugs in `testing` branch**
   ```bash
   git checkout testing
   # ... fix bugs found during testing ...
   git commit -m "fix: Fix edge case"
   git push origin testing
   ```

4. **Promote to `review` ONLY when ALL bugs are FIXED**
   ```bash
   # All tests must pass before promotion
   just promote-to-review
   ```

5. **Human reviews and approves in `review` branch**
   - Agents wait for human approval
   - Human runs `just promote-to-stable` when approved

**⚠️ CRITICAL RULES:**
- **NEVER skip stages** - Must go dev → testing → review → master sequentially
- **dev is ALWAYS ahead** - This is correct and expected!
- **Don't equalize branches** - Use promotion commands for normal workflow
- **Each branch has different code** - This is the purpose of the pipeline!

> **💡 KEY CONCEPT**: The dev branch being ahead of testing/review/master is **CORRECT AND EXPECTED**!
>
> - You can develop features in dev while stable is being released
> - You can develop features in dev while hotfixes are applied to master
> - The branches are **supposed** to have different code
> - This is **not a problem** - it's the **design** of the 5-branch workflow!

### 🛡️ CCPM Plugin (Recommended for AI Agents)

For AI agents, use the **CCPM (Controlled Concurrent Project Management)** plugin which provides:

- **Worktree isolation** - Each issue gets its own workspace
- **Pre-flight checks** - Validates preconditions before starting work
- **Pre-commit hooks** - Blocks protected file modifications automatically
- **Post-flight checks** - Ensures quality before PR creation
- **Audit logging** - All actions logged for accountability
- **Mutex locks** - Prevents concurrent work on same issue

**Location**: `ccpm/` directory (local-only, not in git)

**Skills to read** (educate yourself before working):
- `ccpm/skills/5-branch-workflow.md` - Branch permissions
- `ccpm/skills/promotion-rules.md` - How code flows through pipeline
- `ccpm/skills/release-process.md` - Release system (observe only)
- `ccpm/skills/recovery-procedures.md` - How to fix mistakes

**Commands**:
```bash
# Start work on issue
./ccpm/commands/issue-start.sh <issue-number> dev

# Check status
./ccpm/commands/issue-status.sh

# Finish and create PR
./ccpm/commands/issue-finish.sh <issue-number>

# Abort if needed
./ccpm/commands/issue-abort.sh <issue-number>
```

### 🆘 When to Escalate to Humans

**Immediately notify a human** if:
- ❌ You accidentally pushed to `master`, `main`, or `review`
- ❌ You modified a protected file (`justfile`, `CHANGELOG.md`, etc.)
- ❌ You triggered `just equalize` or `just publish`
- ❌ CI is failing on `review` or `master` for >1 hour
- ❌ Git corruption detected
- ❌ You're unsure about branch promotion

**Recovery**: See `ccpm/skills/recovery-procedures.md` for detailed recovery steps.

---

## Branch Workflow & Development Stages

svg2fbf uses a **4-stage branch workflow** to separate development phases and enforce quality gates at the right time.

### Development Pipeline Overview

```
dev → testing → review → master → main
 ↓       ↓        ↓        ↓       ↓
alpha   beta     rc     stable  (mirror)
```

### Branch Workflow Table

| Branch    | Purpose                        | Stage          | CI/CD    | Hooks     | Tests Expected | Clone & Checkout (gh CLI)                  | Promotion Command          | Install Command         | Release Type |
|-----------|--------------------------------|----------------|----------|-----------|----------------|--------------------------------------------|----------------------------|-------------------------|--------------|
| `dev`     | Active feature development     | Development    | Disabled | Manual    | ❌ May fail    | `gh repo clone Emasoft/svg2fbf -- -b dev`  | `just promote-to-testing`  | `just install-alpha`    | alpha        |
| `testing` | Bug hunting & fixing           | Testing/QA     | Disabled | Manual    | ❌ Will fail   | `gh repo clone Emasoft/svg2fbf -- -b testing` | `just promote-to-review`   | `just install-beta`     | beta         |
| `review`  | Final review & approval        | Pre-release    | ✅ Enabled | Available | ✅ Must pass   | `gh repo clone Emasoft/svg2fbf -- -b review` | `just promote-to-stable`   | `just install-rc`       | rc           |
| `master`  | Production-ready stable code   | Production     | ✅ Enabled | Available | ✅ Must pass   | `gh repo clone Emasoft/svg2fbf -- -b master` | (syncs to main)            | `just install-stable`   | stable       |
| `main`    | GitHub default (mirror master) | Production     | ✅ Enabled | Available | ✅ Must pass   | `gh repo clone Emasoft/svg2fbf` (default)  | `just sync-main`           | `just install-stable`   | (none)       |

**Note:** `gh repo clone` accepts multiple formats:
- **Owner/Repo**: `gh repo clone Emasoft/svg2fbf -- -b BRANCH` (shown above)
- **HTTPS URL**: `gh repo clone https://github.com/Emasoft/svg2fbf.git -- -b BRANCH`
- **SSH URL**: `gh repo clone git@github.com:Emasoft/svg2fbf.git -- -b BRANCH`

**Important:** Git URLs do not support embedding branch names in the URL itself. You must always use the `-b` or `--branch` flag. There is no syntax like `git@github.com:user/repo.git#branch` or `git@github.com:user/repo.git@branch` that works.

### Detailed Branch Descriptions

#### 1. **dev** - Development Branch
- **Purpose**: Active feature development and patches
- **Quality Level**: Code may be broken, incomplete, or experimental
- **CI/CD**: ❌ **Disabled** - Developers iterate quickly without CI blocking
- **Pre-commit Hooks**: Available but developers choose when to run
- **Tests**: Expected to fail - work in progress
- **When to use**: All new features start here
- **Promotion**: When feature is complete → `just promote-to-testing`

**Development workflow on dev:**
```bash
git checkout dev
# ... work on features ...
git commit -m "feat: Add new feature"
git push origin dev

# Manually test when ready
just test    # Optional
just lint    # Optional

# When feature complete
just promote-to-testing
```

#### 2. **testing** - Testing/QA Branch
- **Purpose**: Bug hunting, QA testing, debugging
- **Quality Level**: Features complete but bugs expected
- **CI/CD**: ❌ **Disabled** - Tests are supposed to fail here!
- **Pre-commit Hooks**: Available but not enforced
- **Tests**: Expected to fail until all bugs fixed
- **When to use**: After features merged from dev
- **Promotion**: When all bugs fixed and tests pass → `just promote-to-review`

**Testing workflow:**
```bash
git checkout testing
# ... receive code from dev ...
# ... testers find bugs ...

# Developers fix bugs
git commit -m "fix: Handle edge case in parser"
git push origin testing

# Keep fixing until all tests pass
just test

# When all tests pass
just promote-to-review
```

#### 3. **review** - Review/RC Branch
- **Purpose**: Final review before production release
- **Quality Level**: All tests passing, ready for final approval
- **CI/CD**: ✅ **Enabled** - Strict enforcement, all checks must pass
- **Pre-commit Hooks**: Enforced
- **Tests**: Must pass - this is the quality gate
- **When to use**: Final checks before stable release
- **Promotion**: When approved → `just promote-to-stable`

**Review workflow:**
```bash
git checkout review
# ... receive code from testing ...
# ... final review, documentation checks ...

# CI runs automatically - must pass
# Manual final checks
just test
just lint
just check

# When approved
just promote-to-stable
```

#### 4. **master** - Production Branch
- **Purpose**: Stable, production-ready releases
- **Quality Level**: Highest - only fully tested, approved code
- **CI/CD**: ✅ **Enabled** - Strict enforcement
- **Pre-commit Hooks**: Enforced
- **Tests**: Must pass
- **When to use**: Only after review approval
- **Release**: `just publish` - Creates GitHub releases + PyPI publish

**Master workflow:**
```bash
# After promotion from review
git checkout master

# Create releases
just publish  # All 4 channels + PyPI

# main branch auto-syncs with master
```

#### 5. **main** - GitHub Default Branch
- **Purpose**: Mirror of master for GitHub compatibility
- **Quality Level**: Same as master
- **CI/CD**: ✅ **Enabled** - Strict enforcement
- **Sync**: Automatically syncs with master after stable releases
- **Manual sync**: `just sync-main` if needed

### Why CI is Disabled on dev/testing

**The problem**: If CI ran on every push to `dev` or `testing`, it would constantly fail and block your workflow.

**The solution**: Developers manually decide when to run checks:

```bash
# On dev or testing branches, run checks manually when ready:
just test          # Run test suite
just lint          # Check code style
just check         # Run all checks (lint + test)
```

**Quality gates**: CI only enforces on `review`, `master`, and `main` where code must be stable.

### Branch Promotion Commands

```bash
# Promote through the pipeline
just promote-to-testing   # dev → testing (feature complete)
just promote-to-review    # testing → review (bugs fixed)
just promote-to-stable    # review → master (approved)
just sync-main            # master → main (manual sync)
```

### Commit Porting Commands

There are two commands for porting commits between branches:

1. **`just backport-hotfix`** - Specifically for backporting from master/main to development branches
2. **`just port-commit`** - General-purpose commit porting between any branches

#### 1. Backport Hotfix (master/main → dev/testing/review)

When you make a hotfix on `master` or `main`, backport it to development branches:

```bash
# Checkout target development branch
git checkout dev

# Run backport-hotfix (no arguments - sources from master/main automatically)
just backport-hotfix

# It will:
# 1. Auto-detect master or main as source
# 2. Show commits in master/main NOT in current branch
# 3. Let you select which commit to backport
# 4. Check for conflicts
# 5. Apply if safe
```

**What it does:**
1. ✅ Auto-detects source branch (main or master)
2. ✅ Shows numbered list of commits available for backport
3. ✅ Lets you select which commit to backport
4. ✅ Checks for duplicate commits (same message + author)
5. ✅ Shows commit details and files affected
6. ✅ **Checks for merge conflicts** (dry-run)
7. ✅ Shows diff summary
8. ✅ **Asks for confirmation** before proceeding
9. ✅ Cherry-picks the commit if safe

**Safety features:**
- 🔒 Only works on `dev`, `testing`, or `review` branches
- 🔍 **Detects conflicts BEFORE applying** changes
- 🔍 **Detects duplicate commits** before applying
- ⚠️ **Stops if conflicts detected** - provides recommendations
- ✋ Requires "yes" confirmation (not just "y")

**Example:**
```bash
git checkout dev
just backport-hotfix

# Output:
# 🔄 Backport Hotfix from master/main
# Current branch: dev
# Source branch: main
#
# 🔍 Finding commits in main not in dev...
#
# Commits available for backport:
#  1. a1b2c3d security: Fix XSS vulnerability in parser
#  2. b2c3d4e fix: Correct animation timing
#  3. c3d4e5f chore: Update dependencies
#
# Enter commit number to backport (or 'q' to quit): 1
#
# Selected Commit:
#   Hash: a1b2c3d
#   Message: security: Fix XSS vulnerability in parser
#   Author: Developer Name
#   Date: 2025-11-17
#
# 📁 Files that would be changed:
#   src/parser.py
#
# 🔍 Checking for merge conflicts...
# ✅ No conflicts detected - safe to merge
#
# 📊 Changes summary:
#  src/parser.py | 5 +++--
#
# ⚠️  This will cherry-pick the hotfix commit into dev
# Do you want to proceed? (yes/no): yes
#
# 🚀 Cherry-picking commit...
# ✅ Hotfix backported successfully!
```

**When to use:**
- ✅ Hotfix applied to `master`/`main` needs to be in development branches
- ✅ Security patches from stable that affect development
- ✅ Critical bug fixes made directly on `master`/`main`

**When NOT to use:**
- ❌ Normal feature development (use `just promote-*`)
- ❌ Porting commits between development branches (use `just port-commit`)

#### 2. Port Commit (general-purpose porting)

Port commits from ANY branch to ANY other branch(es):

```bash
# Checkout source branch with the commit you want to port
git checkout dev

# Run port-commit
just port-commit

# It will:
# 1. Let you select which branch to compare with
# 2. Show commits in current branch NOT in that branch
# 3. Let you select which commit to port
# 4. Let you select which target branch(es) to port to
# 5. Check for conflicts on each target
# 6. Ask for confirmation for each target
# 7. Apply to all selected targets
```

**What it does:**
1. ✅ Works from ANY branch
2. ✅ Shows all available branches
3. ✅ Lets you compare with any branch
4. ✅ Shows commits missing in comparison branch
5. ✅ Lets you select which commit to port
6. ✅ Lets you select target branch(es) (multiple allowed)
7. ✅ Checks each target for:
   - Duplicate commits (same message + author)
   - Files affected
   - Merge conflicts (dry-run)
8. ✅ Asks for confirmation for EACH target branch
9. ✅ Returns to original branch when done

**Safety features:**
- 🔒 Works on any branch (more flexible than backport-hotfix)
- 🔍 **Detects conflicts BEFORE applying** to each target
- 🔍 **Detects duplicate commits** on each target
- ⚠️ **Per-target confirmation** - you can skip problematic branches
- 🔄 **Automatic branch creation** - creates local branch from remote if needed
- 🔙 **Returns to original branch** when done
- ✋ Requires "yes" confirmation for each target (not just "y")

**Example:**
```bash
git checkout dev
just port-commit

# Output:
# 🔄 Port Commit from dev
#
# Available branches:
#  1. testing
#  2. review
#  3. master
#  4. main
#
# Enter branch number to compare with (or 'q' to quit): 1
#
# Comparing dev with testing
#
# 🔍 Finding commits in dev not in testing...
#
# Commits available for porting:
#  1. a1b2c3d feat: Add new dashboard
#  2. b2c3d4e fix: Correct button styling
#  3. c3d4e5f docs: Update README
#
# Enter commit number to port (or 'q' to quit): 1
#
# Selected Commit:
#   Hash: a1b2c3d
#   Message: feat: Add new dashboard
#   Author: Developer Name
#   Date: 2025-11-17
#
# Port this commit to which branch(es)?
#
# Available target branches:
#  1. testing
#  2. review
#  3. master
#  4. main
#
# Enter branch numbers separated by spaces (e.g., '1 3 5')
# Or 'all' for all branches, or 'q' to quit
# > 1 2
#
# Will port commit to: testing review
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Processing branch: testing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 📁 Files that would be changed:
#   src/dashboard.py
#   src/templates/dashboard.html
#
# 🔍 Checking for merge conflicts...
# ✅ No conflicts detected - safe to merge
#
# 📊 Changes summary:
#  src/dashboard.py           | 45 +++++++++++++++++++++++++++++
#  src/templates/dashboard.html | 23 +++++++++++++++
#  2 files changed, 68 insertions(+)
#
# ⚠️  This will cherry-pick the commit into testing
# Do you want to proceed? (yes/no/skip): yes
#
# 🚀 Cherry-picking commit to testing...
# ✅ Commit ported to testing successfully!
#
# [Similar output for review branch...]
#
# ✅ Port operation complete
# Back on branch: dev
```

**When to use:**
- ✅ Port feature from dev to testing when ready for testing
- ✅ Port bug fix from testing back to dev
- ✅ Port commit to multiple branches at once
- ✅ Selective porting (not full promotion)

**When NOT to use:**
- ❌ Normal sequential promotion (use `just promote-*`)
- ❌ Backporting from master/main (use `just backport-hotfix` - it's simpler)

#### Comparison: backport-hotfix vs port-commit

| Feature | backport-hotfix | port-commit |
|---------|----------------|-------------|
| **Source** | master/main only (auto-detected) | Any branch (you select) |
| **Target** | Current dev/testing/review only | Any branch(es) (you select) |
| **Multi-target** | ❌ Single target (current branch) | ✅ Multiple targets allowed |
| **Use case** | Hotfixes from stable → development | Any commit between any branches |
| **Simplicity** | ⭐⭐⭐ Very simple (no args) | ⭐⭐ More steps (more flexible) |
| **Safety checks** | ✅ Yes (conflicts, duplicates) | ✅ Yes (conflicts, duplicates, per-target) |

---

## Hotfix Workflow for Critical Issues

### When to Work Directly on Master (Exception to "Always Dev First")

**Normal workflow**: ALL development happens in `dev` branch first

**Hotfix exception**: Work directly on `master` when:

1. ✅ **Critical bug in production/stable** that needs immediate fix
2. ✅ **Security vulnerability** affecting current stable release
3. ✅ **Emergency patch** needed for stable users ASAP
4. ✅ **Code in dev has diverged** - the buggy code was changed/removed in dev
5. ✅ **Issue labeled `priority:critical`** or `priority:blocker`

### Decision Tree

```
Is this issue critical/security and affects stable?
  │
  ├─ YES → Work on master first
  │   └─ After fixing:
  │       ├─ Does dev still have the vulnerable code?
  │       │   ├─ YES → Backport to dev using `just backport-hotfix`
  │       │   └─ NO → Dev already fixed/removed it, document and close
  │       └─ Push to master → Release patch version
  │
  └─ NO → Follow normal workflow
      └─ Work on dev → promote through pipeline
```

### Hotfix Process (Step-by-Step)

#### 1. Verify This Is Actually a Hotfix Situation

```bash
# Check issue labels
gh issue view <number> --json labels

# Ask yourself:
# - Is this affecting production users RIGHT NOW?
# - Is this a security vulnerability?
# - Can this wait for normal dev → testing → review → master pipeline?

# If NOT truly critical → work on dev instead!
```

#### 2. Work Directly on Master

```bash
# Switch to master
git checkout master
git pull origin master

# Create the fix
# ... edit files ...

# Commit with clear message
git commit -m "fix(critical): Patch XSS vulnerability in stable #<issue>

Security fix for production release.
This bypasses normal dev pipeline because:
- Critical security issue affecting stable users
- Dev branch already refactored this code

Fixes #<issue>"

# Push to master
git push origin master
```

#### 3. Decide If Dev Needs the Fix

**Check if dev has the same vulnerable code:**

```bash
git checkout dev

# Search for the vulnerable code pattern
# If found → dev needs the fix
# If not found → dev already fixed it differently

# Example:
grep -r "vulnerable_function" src/
# Found → backport needed
# Not found → dev is safe
```

#### 4a. If Dev Needs the Fix → Backport

```bash
git checkout dev
just backport-hotfix

# Select the hotfix commit from the list
# Review the changes
# Confirm to apply

# Test the backport
just test

# Push to dev
git push origin dev
```

#### 4b. If Dev Doesn't Need the Fix → Document

```bash
# Add comment to issue explaining dev is not affected
gh issue comment <number> --body "✅ Hotfix applied to master (v0.1.9).

Dev branch is not affected because the vulnerable code was refactored in commit abc123."

# Close the issue
gh issue close <number> --reason "completed"
```

#### 5. Release Patch Version

```bash
# On master branch
git checkout master

# Bump patch version and release
just release patch

# This will:
# - Bump version (e.g., 0.1.8 → 0.1.9)
# - Generate changelog
# - Create git tag
# - Publish to PyPI
```

### Example: Security Hotfix Workflow

```bash
# Issue #456: XSS vulnerability in parser (priority:critical)

# 1. Verify it's critical
gh issue view 456 --json labels,title
# Labels: bug, security, priority:critical, component:parser
# Title: "XSS vulnerability in SVG attribute parsing"
# ✅ This is truly critical

# 2. Work on master
git checkout master
git pull origin master

# Fix the vulnerability
# Edit src/parser.py
vim src/parser.py

# Commit
git commit -m "fix(critical): Sanitize SVG attributes to prevent XSS #456

Security fix for production release.
Escapes user-provided attribute values before rendering.

This bypasses normal dev pipeline because:
- Critical security vulnerability affecting stable users
- Needs immediate patch release

Fixes #456"

# Push
git push origin master

# 3. Check if dev needs it
git checkout dev
grep -r "dangerous_parse_attributes" src/
# Not found → dev already uses safe_parse_attributes()

# 4. Document that dev is safe
gh issue comment 456 --body "✅ Security hotfix applied to master.

**Patch released**: v0.1.9 (includes XSS fix)

**Dev branch status**: ✅ Not affected
Dev already uses \`safe_parse_attributes()\` which escapes values correctly.

No backport needed."

# Close issue
gh issue close 456 --reason "completed"

# 5. Release patch
git checkout master
just release patch
# Version: 0.1.8 → 0.1.9
# Published to PyPI
```

### When NOT to Use Hotfix Workflow

❌ **DON'T use hotfix workflow for:**
- Non-critical bugs (use dev → testing → review → master)
- New features (ALWAYS start in dev)
- Refactoring (ALWAYS start in dev)
- "Nice to have" fixes (use normal pipeline)
- Anything that can wait a few days (use normal pipeline)

✅ **Only use hotfix workflow for:**
- Security vulnerabilities
- Data loss bugs
- Crash bugs affecting all users
- Compliance issues (GDPR, legal requirements)

### Hotfix Commands Quick Reference

```bash
# Work on master for critical issue
git checkout master
# ... make fix ...
git commit -m "fix(critical): Description #<issue>"
git push origin master

# Backport to dev if needed
git checkout dev
just backport-hotfix
# Select commit, review, confirm

# Release patch
git checkout master
just release patch
```

---

### Branch Equalization Command

The `just equalize` command synchronizes ALL branches to match the current branch. This is different from promotion, which follows the sequential dev→testing→review→master pipeline.

```bash
# Equalize all branches from current branch
just equalize
```

**What it does:**
1. Detects which branch you're currently on
2. Fetches latest from remote
3. **Warns you** if any other branches have commits not in your current branch
4. Shows you which commits would be lost
5. Asks for confirmation ("yes" required, not just "y")
6. Force-syncs all branches (dev, testing, review, master, main) to match current branch
7. Pushes all branches to remote with `--force-with-lease`
8. Returns you to your original branch

**Example output when branches are ahead:**
```
⚠️  WARNING: Some branches have newer commits!
════════════════════════════════════════════════════════════
  ⚠️  dev has 3 commit(s) not in main
      Latest: a1b2c3d feat: Add new feature

If you continue, these commits will be LOST!

💡 Consider switching to one of these branches first:
   git checkout dev && just equalize
```

#### When to Use `just equalize` vs `just promote-*`

**Use `just equalize` when:**
- ✅ **Critical hotfix on master/main** that needs to go everywhere immediately
- ✅ **Emergency security patch** that can't wait for the normal pipeline
- ✅ **Windows CI fixes** or other infrastructure updates needed on all branches
- ✅ **After manual hotfix** that bypassed the normal promotion flow
- ✅ **Synchronizing after recovery** from divergent branch states
- ✅ **Discarding auto-generated release commits** to sync all branches to latest manual work (see "Auto-Generated Commits Are Safe to Lose" below)

**Use `just promote-*` when (NORMAL WORKFLOW):**
- ✅ **ALL feature development** - This is the standard workflow!
- ✅ **Following the quality gates** - Testing catches bugs, review approves
- ✅ **Branches are SUPPOSED to diverge** - dev ahead of testing is CORRECT!
- ✅ **Maintaining development workflow** - dev is always ahead
- ✅ **Want to preserve branch-specific work** - Don't lose commits

**⚠️ IMPORTANT - Normal Branch State:**
```
dev      ← ALWAYS AHEAD with new features in development
  ↓
testing  ← Complete features being debugged
  ↓
review   ← Bug-free features awaiting approval
  ↓
master   ← Stable releases only
  ↓
main     ← Mirror of master
```

**The dev branch should ALWAYS be ahead of other branches!**
- Agents develop new features in `dev`
- Promote to `testing` ONLY when feature is complete
- Promote to `review` ONLY when all bugs are fixed
- Promote to `master` ONLY when review passes

**Equalize is for EMERGENCIES ONLY, not normal workflow!**

#### Key Differences

| Aspect | `just equalize` | `just promote-*` |
|--------|----------------|------------------|
| **Direction** | Any branch → all others | Sequential: dev→testing→review→master |
| **Merge type** | Force-sync (reset) | Merge (preserves history) |
| **Branches affected** | ALL branches | Just the next branch in pipeline |
| **Commit history** | Overwrites everything | Preserves commit history |
| **Use case** | Emergency synchronization | Normal development flow |
| **Risk** | ⚠️ HIGH - Can lose commits | ✅ LOW - Merges preserve work |
| **Warnings** | Shows which commits will be lost | No warnings (safe merge) |

#### Example Scenarios

**Scenario 1: Critical Windows CI Fix** ✅ Use `just equalize`
```bash
# You fixed a critical Windows encoding bug on main
git checkout main
# ... fix the bug ...
git commit -m "fix: Windows Unicode encoding in ppp()"

# Now all branches need this fix immediately
just equalize
# All branches now have the fix
```

**Scenario 2: New Feature Development** ✅ Use `just promote-*`
```bash
# You developed a new feature on dev
git checkout dev
# ... implement feature ...
git commit -m "feat: Add new export format"

# Feature is complete, move to testing
just promote-to-testing
# dev stays ahead with new feature
# testing now has the feature for QA
```

**Scenario 3: Emergency Security Patch** ✅ Use `just equalize`
```bash
# Critical security vulnerability discovered
git checkout master
# ... apply security patch ...
git commit -m "security: Fix XSS vulnerability"

# This needs to be on ALL branches NOW
just equalize
# All branches protected immediately
```

**Scenario 4: Bug Fix During Testing** ✅ Use `just promote-*`
```bash
# Bug found on testing branch
git checkout testing
# ... fix the bug ...
git commit -m "fix: Handle null viewBox attribute"

# Bug is fixed, ready for review
just promote-to-review
# testing stays at current state
# review now has the bug fix
```

**❌ WRONG Scenario: Dev Ahead of Master After Release**
```bash
# After a release, you see:
git log main..dev --oneline
# a1b2c3d feat: Add new dashboard UI
# b2c3d4e feat: Improve performance
# c3d4e5f docs: Update README

# ❌ WRONG - Don't equalize to "sync" branches!
# just equalize  # DON'T DO THIS!

# ✅ CORRECT - This is normal! dev is supposed to be ahead!
# Just continue developing or promote when ready:
just promote-to-testing  # When dashboard UI feature is complete
```

**Why it's wrong:**
- dev being ahead with new features is **CORRECT**!
- Those commits are **real work** that shouldn't be lost
- The branches are **supposed** to have different code
- Use promotion to move features forward when ready

#### Safety Features

The `just equalize` command includes several safety features:
- 🔍 **Detects branch divergence** - Shows which branches have commits not in current
- ⚠️ **Clear warnings** - Tells you exactly what will be lost
- 💡 **Smart suggestions** - Recommends switching to the newer branch first
- 📡 **Fetches before checking** - Ensures you have latest remote state
- 🔒 **Force-with-lease** - Won't overwrite if remote changed since last fetch
- ✋ **Requires "yes"** - Typing just "y" won't work, must type full "yes"

#### Auto-Generated Commits Are Safe to Lose

**⚠️ IMPORTANT**: Some commits are auto-generated and safe to discard during `just equalize`:

**Auto-Generated Release Commits:**
When you see warnings about commits like:
```
⚠️  dev has 2 commit(s) not in main
    Latest: chore: Update uv.lock for alpha 0.1.9a1
⚠️  testing has 2 commit(s) not in main
    Latest: chore: Update uv.lock for beta 0.1.9b1
⚠️  review has 2 commit(s) not in main
    Latest: chore: Update uv.lock for rc 0.1.9rc1
```

These are **automatically generated** by `just release` or `just publish` and include:
- `CHANGELOG.md` - Auto-generated from git history via `git-cliff`
- `pyproject.toml` - Version number updates
- `uv.lock` - Lock file updates

**Safe to Equalize Protocol:**

1. **Check what commits will be lost:**
   ```bash
   git log main..dev --oneline     # Check dev commits
   git log main..testing --oneline # Check testing commits
   git log main..review --oneline  # Check review commits
   ```

2. **If you ONLY see these patterns, it's SAFE to equalize:**
   - ✅ `Release alpha/beta/rc X.Y.Z`
   - ✅ `chore: Update uv.lock for alpha/beta/rc X.Y.Z`
   - ✅ `chore(release): update CHANGELOG for X.Y.Z`

3. **These will be REGENERATED automatically** on next release:
   ```bash
   # After equalization, next release will recreate:
   just release   # Regenerates CHANGELOG.md, versions, uv.lock for all channels
   just publish   # Same + publishes stable to PyPI
   ```

**Why This Works:**
- The release script (`scripts/release.sh`) fully regenerates `CHANGELOG.md` from git history
- Version numbers are calculated from git tags
- Lock files are regenerated from dependencies
- **No manual work is lost** - only auto-generated files

**Example: Safe Equalization**
```bash
# main has your latest documentation/feature work
git checkout main

# Other branches have auto-generated release commits from last release
git log main..dev --oneline
# f4fe0e7 chore: Update uv.lock for alpha 0.1.9a1
# ebfaca3 Release alpha 0.1.9a1

# ✅ SAFE - These are auto-generated, equalize from main
just equalize

# Later, when you release again, they'll be recreated:
just release
# Regenerates CHANGELOG.md, updates versions, creates new release commits
```

**When NOT Safe to Equalize:**
If you see commits like:
- ❌ `feat: Add new feature`
- ❌ `fix: Critical bug fix`
- ❌ `refactor: Improve performance`

These are **manual work** - equalization would **lose real code changes**!

**Simple Rule:**
> Only release-related commits (`Release X.Y.Z`, `Update uv.lock`, `update CHANGELOG`) are safe to lose. Everything else is manual work that should be preserved.

### Release Commands

```bash
# Create releases on GitHub (no PyPI)
just release

# Create releases + publish stable to PyPI
just publish
```

For complete release workflow documentation, see [docs/RELEASE_WORKFLOW.md](docs/RELEASE_WORKFLOW.md).

### Installing Released Versions

Each branch has a corresponding install command to install directly from GitHub:

```bash
# Install from specific branches
just install-alpha    # Install latest from dev branch (alpha)
just install-beta     # Install latest from testing branch (beta)
just install-rc       # Install latest from review branch (rc)
just install-stable   # Install latest from master branch (stable)

# Install local development version
just build            # Build wheel from current code
just install          # Install the built wheel
```

**Use cases:**
- **Testing releases**: Install alpha/beta/rc to test before promoting
- **User installation**: Use `just install-stable` for production
- **Development**: Use `just build && just install` for local testing

### Common Development Patterns

**Pattern 1: New Feature**
```bash
git checkout dev
# ... implement feature ...

# Test locally
just build
just install
svg2fbf --version  # Verify

# Promote when ready
just promote-to-testing
# ... fix bugs found in testing ...
just promote-to-review
# ... final approval ...
just promote-to-stable
just publish
```

**Pattern 2: Hotfix**
```bash
git checkout master
git checkout -b hotfix/critical-bug
# ... fix bug ...
git checkout master
git merge hotfix/critical-bug
git push origin master
just publish
```

**Pattern 3: Testing Pre-releases**
```bash
# Install and test alpha release
just install-alpha
svg2fbf --version
# ... test alpha ...

# Install and test beta release
just install-beta
svg2fbf --version
# ... test beta ...

# Install stable when approved
just install-stable
```

**Pattern 4: Local Development**
```bash
git checkout dev
# ... make changes ...
just test   # Check if tests pass
just lint   # Check code style

# Test local build
just build
just install
svg2fbf --version  # Should show current version

# Continue working or promote if ready
just promote-to-testing
```

## Setting Up Development Environment

### Prerequisites

- **Python**: ≥3.10
- **[uv](https://github.com/astral-sh/uv)**: Package and project manager
- **[yq](https://github.com/mikefarah/yq)**: YAML/JSON/XML processor (install via `brew install yq` on macOS)
- **Node.js**: Required for test suite (Puppeteer rendering)
- **Git**: For version control

### Initial Setup

**⚠️ DEVELOPERS: Always clone the repository, never install from PyPI/releases!**

PyPI and GitHub releases exclude large test data (93MB+ of test sessions). Developers need the full repository with all test suites.

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository (RECOMMENDED: use GitHub CLI)
# Method 1: Owner/Repo format (shortest)
gh repo clone Emasoft/svg2fbf
cd svg2fbf
git checkout dev        # for alpha development (most common)

# Method 2: Clone and checkout in one command (recommended)
# gh repo clone Emasoft/svg2fbf -- -b dev

# Method 3: Using full URL
# gh repo clone https://github.com/Emasoft/svg2fbf.git -- -b dev

# Alternative: standard git clone
# git clone https://github.com/Emasoft/svg2fbf.git
# cd svg2fbf
# git checkout dev

# Create virtual environment with Python 3.12
uv venv --python 3.12

# Activate the virtual environment
source .venv/bin/activate

# Initialize uv project (creates pyproject.toml if needed)
uv init --python 3.12

# Sync dependencies from pyproject.toml
uv sync
```

### ⚠️ CRITICAL: Single Virtual Environment Policy

**IMPORTANT**: This project uses **ONE and ONLY ONE** virtual environment located at the project root:

```
svg2fbf/
└── .venv/        ← THE ONLY VENV (project root)
```

**DO NOT** create additional virtual environments in subdirectories:

```
❌ WRONG: svg2fbf/tests/.venv/
❌ WRONG: svg2fbf/src/.venv/
❌ WRONG: svg2fbf/docs/.venv/
```

**Why this matters:**
- Multiple venvs cause dependency conflicts
- Wasted disk space (each venv is ~50-100MB)
- Confusing execution context (which Python is running?)
- Build and test failures due to missing dependencies

**If you accidentally created a venv in a subdirectory:**
```bash
# Remove it immediately
rm -rf tests/.venv
rm -rf src/.venv
rm -rf docs/.venv

# Always work from project root
cd /path/to/svg2fbf
uv sync
```

**Always run commands from the project root:**
```bash
# ✅ CORRECT: From project root
cd svg2fbf
uv run python tests/testrunner.py run 5

# ❌ WRONG: From subdirectory (creates local .venv!)
cd svg2fbf/tests
uv venv  # DON'T DO THIS!
```

## Installation for Development

There are multiple ways to install svg2fbf for development:

### Option 1: Editable Installation in Virtual Environment

This is the recommended approach for active development:

```bash
# After setting up the virtual environment
uv pip install -e .

# Now you can run svg2fbf from the venv
svg2fbf --version
```

With editable installation (`-e`), changes to `svg2fbf.py` take effect immediately without reinstalling.

### Option 2: Install as uv Tool (Development Mode)

Install svg2fbf globally as a uv tool from your local development folder:

```bash
# Install from current directory as editable tool
uv tool install --editable .

# Or install from a specific local directory
uv tool install --editable /path/to/svg2fbf

# Run from anywhere
svg2fbf --version
```

The `--editable` flag creates an editable installation, so changes to the code take effect immediately.

### Option 3: Build and Install from Wheel (Development Build)

Build a development wheel and install it:

```bash
# Build development wheel
uv build --dev

# This creates:
# - dist/svg2fbf-{version}.tar.gz (source distribution)
# - dist/svg2fbf-{version}-py3-none-any.whl (wheel)

# Install the wheel as a tool
uv tool install dist/svg2fbf-{version}-py3-none-any.whl --python 3.10
```

## Building

### Quick Development Build (Recommended)

For rapid development cycles, use the `just` commands:

```bash
# Build development wheel (NO version bump)
just build

# Install built wheel
just install

# Or do both at once (full rebuild)
just reinstall
```

**What `just build` does:**
1. Gets current version from pyproject.toml
2. Gets short git hash for local version identifier
3. Creates development version with +dev.{hash} suffix (PEP 440 compliant)
4. Builds wheel with development version (e.g., `0.1.2a15+dev.cb48211`)
5. Restores original version in pyproject.toml
6. No version bumping - versions only change during releases

**Development builds** get a unique suffix based on git commit hash, allowing you to:
- Build multiple times without version changes
- Distinguish development builds from releases
- Test code without affecting version numbers

**Release builds** (clean, no suffix) are created by:
- `just release` - Create releases on GitHub (all 4 channels)
- `just publish` - Create releases + publish stable to PyPI

### Build Process Details

#### Development Build

```bash
# Build with development dependencies
uv build --dev

# Output files in dist/:
# - svg2fbf-{version}.tar.gz
# - svg2fbf-{version}-py3-none-any.whl
```

#### Production Build

```bash
# Build for production (no dev dependencies)
uv build --python 3.10

# Specify output directory
uv build --python 3.10 --out-dir build/
```

#### Verify Build

```bash
# Uninstall previous version if installed
uv tool uninstall svg2fbf

# Install built wheel locally to test
uv tool install dist/svg2fbf-*.whl --python 3.10

# Test the installation
svg2fbf --version
svg2fbf -i examples/seagull/ -o /tmp -f test.fbf.svg -s 12
```

### What's Included in Releases

**⚠️ IMPORTANT DISTINCTION:**
- **End users**: Install from PyPI or GitHub releases (small, fast downloads)
- **Developers**: MUST clone the repository (full test data required)

To keep release packages lightweight, **large test data is excluded** from wheels and source distributions:

**Excluded from releases** (developers get these by cloning):
- `tests/sessions/` - 93MB+ of SVG test frames and session data
- `tests/**/*.zip` - Compressed test archives
- Development scripts and tools
- Complete git history

**Included in releases** (end users get these):
- Core source code
- Essential runtime scripts (node_scripts, package.json)
- Unit tests (small, fast-running tests)
- Documentation

**Package sizes**:
- **PyPI/GitHub releases (end users)**: ~129KB wheel
- **Full repo clone (developers)**: ~93MB+

This design allows:
- ✅ Fast PyPI/GitHub releases for end users (129KB)
- ✅ Comprehensive test suites for developers (clone repo)
- ✅ CI/CD can still run tests (GitHub Actions clones full repo)
- ✅ No wasted bandwidth for users who just want to use the tool

## Testing

svg2fbf includes a comprehensive test suite with pixel-perfect validation.

### ⚠️ IMPORTANT: Test-Generated FBF Files Are NOT Valid for Production

**WARNING**: When using the `testrunner.py` helper script, the generated FBF.SVG files are **NOT valid for production use**. Here's why:

1. **Missing Metadata**: Without a proper YAML config file, testrunner.py cannot generate FBF files with proper metadata (title, creators, description, etc.). The generated FBF files lack required RDF/XML metadata for Full Conformance.

2. **Test-Specific Settings**: Test FBF files use specialized generation settings optimized for frame comparison testing:
   - **1 FPS only** (for reliable Puppeteer frame capture)
   - **Auto-start** (`begin="0s"` instead of `begin="click"`)
   - **Play once** (`repeatCount="1"` instead of `"indefinite"`)
   - **No interactivity** (testing requires deterministic playback)

3. **For Production Use**: Always use `svg2fbf.py` directly with a proper YAML configuration file (or pass all metadata via CLI parameters) to generate valid, production-ready FBF.SVG animations.

**Note**: You CAN pass a YAML generation file to testrunner.py using the unified syntax:
```bash
testrunner.py --yamlfile nameoftheyamlfile.yml -- <path1> [path2] [path3] ...
```
The unified `--` separator accepts mixed inputs (folders and/or individual SVG files). Examples:
```bash
# Folder mode
testrunner.py --yamlfile config.yml -- /path/to/folder

# File list mode
testrunner.py --yamlfile config.yml -- frame1.svg frame2.svg frame3.svg

# Mixed inputs
testrunner.py --yamlfile config.yml -- /path/to/folder extra_file.svg

# Random selection from W3C SVG 1.1 Test Suite (root level only, no recursion)
testrunner.py create --random 50 -- "FBF.SVG/SVG 1.1 W3C Test Suit/w3c_50frames/"
just test-random-w3c 50  # Convenient alias
```
However, this is only for special tests that need to actually test the ability of svg2fbf to generate valid FBF.SVG files with valid metadata, or to test the interactivity with Playwright test scripts. Normal tests do not require a YAML file to be passed to testrunner.py.

**Test FBF files are saved in `tests/sessions/session_XXX_Nframes/` directories and should NEVER be distributed or used as examples.**

### Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run with HTML visual comparison report
uv run pytest tests/ --html-report

# Run specific test file
uv run pytest tests/test_frame_rendering.py

# Run with verbose output
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ --cov=svg2fbf --cov-report=html
```

### Test Tolerance System

The test suite uses a **two-level tolerance approach** for image comparison:

1. **Pixel-Level Tolerance** (`--pixel-tolerance`): Color difference threshold per pixel
   - Default: `0.0039` (≈ 1 RGB value difference in normalized 0-1 range)
   - Range: `0.0` (exact match) to `1.0` (any difference accepted)

2. **Image-Level Tolerance** (`--image-tolerance`): Percentage of pixels allowed to differ
   - Default: `0.04%` (0.0004 fraction)
   - Range: `0.0%` (all pixels must match) to `100%` (any number of different pixels)

### Test Tolerance Presets

```bash
# Pixel-perfect comparison (zero tolerance)
uv run pytest tests/ --pixel-tolerance 0.0 --image-tolerance 0.0

# Very strict (sub-pixel differences allowed)
uv run pytest tests/ --pixel-tolerance 0.001 --image-tolerance 0.001

# Default (production setting)
uv run pytest tests/ --pixel-tolerance 0.0039 --image-tolerance 0.04

# Lenient (for development/debugging)
uv run pytest tests/ --pixel-tolerance 0.01 --image-tolerance 0.1
```

| Preset | Pixel Tolerance | Image Tolerance | Use Case |
|--------|----------------|-----------------|----------|
| **Pixel-Perfect** | 0.0 | 0.0 | Exact match required |
| **Very Strict** | 0.001 | 0.001% | Near-perfect (sub-pixel differences) |
| **Default** | 0.0039 | 0.04% | Production setting |
| **Lenient** | 0.01 | 0.1% | Development/debugging |

### Test Documentation

For detailed test documentation:
- [`tests/README.md`](tests/README.md) - Test suite overview
- [`tests/CLAUDE.md`](tests/CLAUDE.md) - Architecture and troubleshooting

## Code Quality

### Formatting and Linting

svg2fbf uses **ruff** for both formatting and linting:

```bash
# Format code (auto-fix)
uv run ruff format svg2fbf.py tests/

# Format with custom line length
uv run ruff format --line-length=320 svg2fbf.py tests/

# Check linting issues
uv run ruff check svg2fbf.py tests/

# Auto-fix linting issues
uv run ruff check --fix svg2fbf.py tests/
```

### Type Checking

```bash
# Run mypy type checker
uv run mypy svg2fbf.py

# Run with strict mode
uv run mypy --strict svg2fbf.py
```

### Pre-commit Checks

Before committing code, run:

```bash
# Format code
uv run ruff format svg2fbf.py tests/

# Check linting
uv run ruff check svg2fbf.py tests/

# Type check
uv run mypy svg2fbf.py

# Run tests
uv run pytest tests/
```

## Version Management

svg2fbf uses **automatic version management** via `uv`. Version is stored in `pyproject.toml` and displayed on every execution.

### Standard Version Bumps

```bash
# Check current version
svg2fbf --version

# Bump patch version (0.1.0 → 0.1.1)
uv version --bump patch

# Bump minor version (0.1.0 → 0.2.0)
uv version --bump minor

# Bump major version (0.1.0 → 1.0.0)
uv version --bump major
```

### Pre-release Versions

Pre-release versions allow you to publish test versions before the final release.

#### Creating the First Pre-release

To create the first alpha, beta, or release candidate, you need to bump both the version level AND the pre-release type:

```bash
# Create first alpha (0.1.0 → 0.1.1a1)
uv version --bump patch --bump alpha

# Create first beta (0.1.0 → 0.1.1b1)
uv version --bump patch --bump beta

# Create first release candidate (0.1.0 → 0.1.1rc1)
uv version --bump patch --bump rc
```

#### Incrementing Pre-release Numbers

Once you're in a pre-release cycle (alpha, beta, or rc), you can increment just the pre-release number **without bumping the patch version**:

```bash
# Increment alpha version (0.1.1a1 → 0.1.1a2)
uv version --bump alpha

# Increment alpha again (0.1.1a2 → 0.1.1a3)
uv version --bump alpha

# Switch to beta (0.1.1a3 → 0.1.1b1)
uv version --bump beta

# Increment beta version (0.1.1b1 → 0.1.1b2)
uv version --bump beta

# Switch to release candidate (0.1.1b2 → 0.1.1rc1)
uv version --bump rc

# Increment rc version (0.1.1rc1 → 0.1.1rc2)
uv version --bump rc
```

#### Finalizing a Release

To finalize a pre-release version to a stable release, bump the patch version:

```bash
# Finalize from pre-release to stable (0.1.1rc2 → 0.1.1)
uv version --bump patch
```

### Complete Pre-release Workflow Example

Here's a typical pre-release cycle for version 0.2.0:

```bash
# Current version: 0.1.5
# Starting development of 0.2.0

# Create first alpha
uv version --bump minor --bump alpha    # → 0.2.0a1

# Fix bugs, increment alpha
uv version --bump alpha                 # → 0.2.0a2
uv version --bump alpha                 # → 0.2.0a3

# Ready for beta testing
uv version --bump beta                  # → 0.2.0b1

# Fix issues, increment beta
uv version --bump beta                  # → 0.2.0b2
uv version --bump beta                  # → 0.2.0b3

# Ready for release candidate
uv version --bump rc                    # → 0.2.0rc1

# Final testing, increment rc if needed
uv version --bump rc                    # → 0.2.0rc2

# Everything looks good, finalize release
uv version --bump minor                 # → 0.2.0 (stable release)
```

### Version Workflow Checklist

1. **Make changes** and test thoroughly
2. **Update CHANGELOG.md** with changes
3. **Bump version**:
   - For pre-release: `uv version --bump <type>`
   - For stable release: `uv version --bump <patch|minor|major>`
4. **Build package**: `uv build --python 3.10`
5. **Test built package**:
   ```bash
   uv tool uninstall svg2fbf
   uv tool install dist/svg2fbf-*.whl --python 3.10
   ```
6. **Run full test suite**: `uv run pytest tests/`
7. **Commit version bump**: `git add pyproject.toml && git commit -m "Bump version to $(svg2fbf --version)"`
8. **Tag release**: `git tag v$(svg2fbf --version | grep -oP '\d+\.\d+\.\d+[a-z]*\d*')`
9. **Push with tags**: `git push && git push --tags`

### Pre-release Distribution

Pre-release versions can be distributed for testing:

```bash
# Build pre-release
uv build --python 3.10

# Uninstall stable version if installed
uv tool uninstall svg2fbf

# Install pre-release for testing
uv tool install dist/svg2fbf-0.2.0a1-py3-none-any.whl --python 3.10

# Test the pre-release
svg2fbf --version  # Should show 0.2.0a1
```

### Version Naming Convention

svg2fbf follows [PEP 440](https://peps.python.org/pep-0440/) versioning:

| Version Format | Example | Description |
|---------------|---------|-------------|
| `X.Y.Z` | `1.2.3` | Stable release |
| `X.Y.ZaN` | `1.2.3a1` | Alpha release (N = alpha number) |
| `X.Y.ZbN` | `1.2.3b1` | Beta release (N = beta number) |
| `X.Y.ZrcN` | `1.2.3rc1` | Release candidate (N = rc number) |

**Version component meanings:**
- **X (major)**: Breaking changes, incompatible API changes
- **Y (minor)**: New features, backwards-compatible
- **Z (patch)**: Bug fixes, backwards-compatible

## Project Structure

```
svg2fbf/
├── svg2fbf.py              # Main module (CLI + conversion logic)
├── pyproject.toml          # Package configuration, dependencies, version
├── uv.lock                 # Locked dependency versions
├── README.md               # User-facing documentation
├── DEVELOPMENT.md          # This file (developer guide)
├── CONTRIBUTING.md         # Contribution guidelines and PR process
├── CHANGELOG.md            # Version history and changes
├── ACKNOWLEDGMENTS.md      # Credits and attributions
├── LICENSE                 # Apache 2.0 license
│
├── docs/                   # Technical documentation
│   ├── FBF_FORMAT.md      # FBF format specification
│   ├── FBF_METADATA_SPEC.md  # Metadata specification
│   └── fbf_schema.svg     # Visual schema diagram
│
├── docs_dev/              # Developer documentation
│   ├── CLAUDE.md          # Technical architecture for AI assistants
│   └── *.md               # Analysis and design documents
│
├── examples/              # Example SVG animations
│   ├── seagull/          # Simple seagull flight (10 frames)
│   ├── anime_girl/       # Complex character animation (35 frames)
│   ├── boat_test/        # Boat animation
│   ├── splat_button/     # Button animation with effects
│   └── ...
│
├── tests/                 # Test suite
│   ├── conftest.py       # Pytest configuration and fixtures
│   ├── test_frame_rendering.py  # Main test suite
│   ├── README.md         # Test documentation
│   ├── CLAUDE.md         # Test architecture documentation
│   │
│   ├── node_scripts/     # Rendering utilities (Node.js/Puppeteer)
│   │   ├── render_svg.js           # SVG → PNG renderer
│   │   └── render_fbf_animation.js # FBF frame extractor
│   │
│   ├── utils/            # Test utilities (Python)
│   │   ├── config.py              # Test configuration
│   │   ├── session_manager.py     # Session tracking
│   │   ├── image_comparison.py    # Pixel comparison logic
│   │   ├── html_report.py         # HTML report generation
│   │   ├── puppeteer_renderer.py  # Puppeteer integration
│   │   └── svg2fbf_frame_processor.py  # FBF processing
│   │
│   ├── results/          # Test outputs (gitignored)
│   │   └── session_XXX_NNframes/YYYYMMDD_HHMMSS/
│   │       ├── original_pngs/     # Rendered original SVGs
│   │       ├── fbf_output/        # Generated FBF files
│   │       ├── fbf_pngs/          # Rendered FBF frames
│   │       ├── diffs/             # Grayscale diff images
│   │       └── comparison_report.html  # Visual comparison
│   │
│   └── input_batches/    # Test batch configurations
│
├── scripts_dev/          # Development utility scripts
│   ├── README.md         # Script documentation
│   ├── quick_validation_test.sh       # Quick viewBox validation
│   ├── test_viewbox_accuracy.py       # Edge clipping detection
│   ├── compare_viewbox_accuracy.py    # ViewBox comparison
│   ├── comprehensive_viewbox_test.py  # Full validation + HTML report
│   └── check_viewbox.py               # Simple viewBox checker
│
└── .serena/              # Serena MCP memory files (gitignored)
    └── memories/         # Codebase knowledge for AI assistants
```

### Key Files

- **`svg2fbf.py`**: Complete implementation (9500+ lines)
  - CLI argument parsing
  - SVG parsing and optimization
  - Element deduplication
  - Gradient/path optimization
  - SMIL animation generation
  - Metadata generation
  - FBF file assembly

- **`pyproject.toml`**: Package configuration
  - Version number (single source of truth)
  - Dependencies (numpy, pyyaml)
  - Entry points for CLI
  - Build system (hatchling)

- **`tests/conftest.py`**: Pytest configuration
  - Custom command-line options
  - Tolerance fixtures
  - Session management
  - HTML report generation

## Development Tips

### Quick Development Cycle

**Fastest workflow** (recommended):
```bash
# 1. Make changes to svg2fbf.py

# 2. Rebuild and reinstall in one command
just reinstall

# 3. Test the installed version
svg2fbf -i examples/seagull/ -o /tmp -f test.fbf.svg -s 12

# 4. Run specific test
just test-file tests/test_frame_rendering.py
```

**Alternative workflow** (without reinstalling):
```bash
# 1. Make changes to svg2fbf.py

# 2. Run quick test directly (uses current source)
uv run python svg2fbf.py -i examples/seagull/ -o /tmp -f test.fbf.svg -s 12

# 3. Run specific test
uv run pytest tests/test_frame_rendering.py::test_seagull_animation -v

# 4. Check code quality
uv run ruff check svg2fbf.py
```

### Debugging Test Failures

```bash
# Run with verbose output and keep test files
uv run pytest tests/ -v --html-report

# Check the generated comparison report
open tests/results/session_XXX/YYYYMMDD_HHMMSS/comparison_report.html

# Examine diff images
ls -l tests/results/session_XXX/YYYYMMDD_HHMMSS/diffs/
```

### Working with YAML Configs

```bash
# Create test config
cat > test_config.yaml <<EOF
metadata:
  title: "Test Animation"
  creators: "Developer"

generation_parameters:
  input_folder: "examples/seagull/"
  output_path: "/tmp/test/"
  filename: "test.fbf.svg"
  speed: 12.0
EOF

# Test with config
uv run python svg2fbf.py test_config.yaml
```

## Getting Help

- 📖 [README.md](README.md) - User documentation
- 🐛 [Issue Tracker](https://github.com/Emasoft/svg2fbf/issues)
- 💬 [Discussions](https://github.com/Emasoft/svg2fbf/discussions)
- 📋 [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines

---

**Happy coding! 🎨**
