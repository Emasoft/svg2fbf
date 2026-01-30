# Custom Git Hooks

This directory contains custom git hooks that are preserved in version control.

## Why This Exists

Git hooks live in `.git/hooks/` which:
- Is not version controlled
- Gets lost if `.git/` is deleted
- Requires manual setup for each contributor

This directory solves that by:
- Storing hooks in version control (`scripts/hooks/`)
- Auto-installing via `scripts/install-hooks.sh`
- Easy to restore if `.git/` is recreated

## Current Hooks

### pre-push

**Purpose:** Ensure we never push broken or buggy code to GitHub.

**Runs:** `scripts/validate.sh` which performs:
1. **Ruff lint check** - Code must pass linting (no auto-fix)
2. **Ruff format check** - Code must be properly formatted
3. **Pytest** - All tests must pass
4. **TruffleHog** - No secrets in code

**Usage:**
```bash
git push              # Runs validation automatically
git push --no-verify  # Skip validation (use sparingly!)
```

**If validation fails:**
```bash
just lint-fix    # Auto-fix lint issues
just fmt         # Auto-fix formatting
just test        # Run tests with details
just validate    # Run full validation manually
```

## Hook Management

### Pre-commit Framework Hooks

Hooks managed by [pre-commit](https://pre-commit.com/) are defined in `.pre-commit-config.yaml` at project root. These run on the **pre-commit** stage:

- `ruff` - Python linting (with auto-fix)
- `ruff-format` - Python formatting

### Custom Hooks

Custom hooks (not managed by pre-commit) are in this directory:

- `pre-push` - Comprehensive validation before pushing

**To add a custom hook:**

1. Create the hook script in `scripts/hooks/`:
   ```bash
   # Example: scripts/hooks/post-commit
   #!/usr/bin/env bash
   echo "Post-commit hook executed!"
   ```

2. Make it executable:
   ```bash
   chmod +x scripts/hooks/post-commit
   ```

3. Commit it to git:
   ```bash
   git add scripts/hooks/post-commit
   git commit -m "Add post-commit hook"
   ```

4. Reinstall hooks:
   ```bash
   ./scripts/install-hooks.sh
   # or: just install-hooks
   ```

## Installing/Reinstalling Hooks

After cloning or if `.git/` is recreated:

```bash
# Via script
./scripts/install-hooks.sh

# Via justfile
just install-hooks
```

This will:
1. Install pre-commit framework hooks from `.pre-commit-config.yaml`
2. Copy custom hooks from `scripts/hooks/` to `.git/hooks/`
3. Make them executable

## Validation Script

The shared validation script (`scripts/validate.sh`) can be run manually:

```bash
./scripts/validate.sh           # Full validation (lint, format, tests, secrets)
./scripts/validate.sh --quick   # Quick validation (skip tests)
./scripts/validate.sh --quiet   # Minimal output

# Via justfile
just validate                   # Full validation
just validate-quick             # Quick validation
```

## Integration with Release Script

The release script (`scripts/release.sh`) also runs validation before releasing:
- Uses `--quick` mode (skips tests, assumes they passed before merge)
- Ensures we never release broken code to PyPI
- **Enforces version release rules** (see below)

### Version Release Validation

The release script validates version progression rules BEFORE committing:

1. **Single Stage Rule**: Only ONE stage per version at any time
2. **Stage Progression Rule**: Stage must be LOWER than previous version's stage
3. **RC Gateway Rule**: Alpha/beta only if previous version at RC or stable

If validation fails:
- The release is aborted with a clear error message
- The version bump in pyproject.toml is rolled back
- No commits or tags are created

For full details, see [CLAUDE.md](../../CLAUDE.md#version-release-rules-critical).

## Available Hook Types

Git supports these hook types:
- `pre-commit` - Before commit is created (managed by pre-commit framework)
- `prepare-commit-msg` - Before commit message editor opens
- `commit-msg` - After commit message is written
- `post-commit` - After commit is created
- `pre-push` - Before push to remote (**our comprehensive hook**)
- `post-checkout` - After checkout
- `post-merge` - After merge
- And more...

See: https://git-scm.com/docs/githooks

## Bypassing Hooks

Sometimes you need to skip hooks:

```bash
# Skip pre-commit
git commit --no-verify -m "message"

# Skip pre-push
git push --no-verify
```

**Use sparingly!** Hooks exist for a reason.

## Troubleshooting

### Hooks not executing

1. Check if hooks are installed:
   ```bash
   ls -la .git/hooks/
   ```

2. Reinstall:
   ```bash
   ./scripts/install-hooks.sh
   ```

3. Verify permissions:
   ```bash
   chmod +x .git/hooks/*
   ```

### Hook fails but shouldn't

Check the hook script for errors:
```bash
bash -x .git/hooks/pre-push
```

### Validation too slow

Use quick mode for faster feedback:
```bash
just validate-quick  # Skip tests
```

## Notes

- Hooks in `scripts/hooks/` are templates stored in version control
- Actual hooks run from `.git/hooks/`
- Changes to hooks in `scripts/hooks/` require reinstallation
- Pre-commit framework hooks are auto-updated via `.pre-commit-config.yaml`
- Custom hooks override pre-commit hooks of the same type
