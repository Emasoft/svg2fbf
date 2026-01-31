# JUST COMMANDS REFERENCE SHEET FOR THIS PROJECT

svg2fbf uses `just` to manage the project. Just is a modern cross-platform task runner.

## Why Just?

We use **Just** (https://github.com/casey/just) instead of multiple scripts because:
- ✅ **Cross-platform**: Works on Windows, macOS, Linux
- ✅ **Simple**: One `justfile` instead of many bash/Python scripts
- ✅ **Self-documenting**: `just --list` shows all available commands
- ✅ **Modern**: Better than Make, designed for task running
- ✅ **Fast**: Rust-based, single binary

## Installation

Install Just before starting development:

### macOS / Linux
```bash
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin
```

### macOS (Homebrew)
```bash
brew install just
```

### Windows
```bash
winget install --id Casey.Just
```

### Other Methods
```bash
# Via Cargo (Rust)
cargo install just

# Via
npm install -g just-install
```

Verify installation:
```bash
just --version
```

## Quick Start

```bash
# Clone repository
git clone https://github.com/Emasoft/svg2fbf.git
cd svg2fbf

# Create venv
uv venv

# Sync dependencies
just sync

# Run tests
just test

# Build and install
just reinstall
```

## Available Commands

Run `just --list` to see all commands:

```bash
just --list
```

This project uses Just to manage the common development tasks. Here is the list of Just commands:

### Dependency Management

| Command | Description |
|---------|-------------|
| `just sync` | Sync all dependencies (runtime + dev) without installing svg2fbf in venv |
| `just sync-dev` | Sync only development dependencies |
| `just sync-runtime` | Sync only runtime dependencies |
| `just add <pkg>` | Add a runtime dependency to pyproject.toml and uv sync |
| `just add-dev <pkg>` | Add a development dependency to pyproject.toml and uv sync --dev|
| `just remove <pkg>` | Remove a dependency from pyproject.toml and uv sync|

### Build & Install

| Command | Description |
|---------|-------------|
| `just build` | Build wheel package in dist/ |
| `just bump [type]` | Bump version (default: alpha). Types: alpha, beta, rc, patch, minor, major |
| `just install [python]` | Install as uv tool from latest wheel (default: python 3.10) |
| `just reinstall [type] [python]` | Full rebuild and reinstall with version bump (default: alpha, python 3.10) |

### Testing - Basic

| Command | Description |
|---------|-------------|
| `just test` | Run all tests |
| `just test-cov` | Run tests with coverage report (HTML + terminal) |
| `just test-file <file>` | Run specific test file |
| `just test-match <pattern>` | Run tests matching a pattern (keyword) |
| `just test-list` | List all available test functions |
| `just test-list-file <file>` | List tests in specific file |
| `just test-report` | Open last HTML coverage report in browser |
| `just test-verbose` | Run tests with verbose output (-v -s) |
| `just test-failed` | Re-run only failed tests from last run |

### Testing - Session Management

| Command | Description |
|---------|-------------|
| `just test-create <name> <svg_dir>` | Create new test session from SVG directory |
| `just random-test <n>` | Create random test session with N frames from examples/ (excludes .fbf.svg) |
| `just test-random-w3c <count>` | Create random test session with N frames from W3C SVG 1.1 Test Suite (root level only, no recursion) |
| `just test-sessions` | List all test sessions with metadata |
| `just test-info <session_id>` | Show detailed information for a test session |
| `just test-delete <session_id>` | Delete a specific test session |
| `just test-clean-all` | Clean all test sessions from tests/results/ |

### SVG Utilities

| Command | Description |
|---------|-------------|
| `just svg-repair <path>` | Repair viewBox attributes in SVG files using svg-repair-viewbox |
| `just svg-repair-quiet <path>` | Repair viewBox in quiet mode (no progress output) |
| `just svg-compare <file1> <file2>` | Compare two FBF.SVG files and show differences |
| `just svg-validate <file>` | Validate SVG file structure (viewBox, dimensions, elements) |
| `just svg-info <file>` | Show SVG file information (attributes, element counts, file stats) |

### Code Quality

| Command | Description |
|---------|-------------|
| `just fmt` | Format code with ruff (line length: 320) |
| `just lint` | Lint code with ruff |
| `just lint-fix` | Fix linting issues automatically |
| `just check` | Run all quality checks (lint, format) |

### Cleanup

| Command | Description |
|---------|-------------|
| `just clean-temp [pattern]` | Clean temp directories (default pattern: temp_*) |
| `just clean-build` | Clean build artifacts (build/, dist/, *.egg-info) |
| `just clean-cache` | Clean Python cache (__pycache__, *.pyc, *.pyo) |
| `just clean-all` | Clean everything (temp, build, cache) |

### Development Helpers

| Command | Description |
|---------|-------------|
| `just version` | Show current version from pyproject.toml |
| `just version-installed` | Show installed svg2fbf version |
| `just check-venv` | Check if svg2fbf is in venv (should be empty) |
| `just verify` | Verify installation (version, venv check, commands available) |
| `just repl` | Open interactive Python REPL with project |
| `just workflow` | Show development workflow guide |

### CI/CD

| Command | Description |
|---------|-------------|
| `just ci` | Run CI checks (lint, test-cov) |

### Release Workflow

| Command | Description |
|---------|-------------|
| `just release` | Create GitHub releases for all channels (no PyPI) |
| `just publish` | Create GitHub releases + publish stable to PyPI |
| `just changelog` | Generate/update CHANGELOG.md from git history |
| `just release-tag <version>` | Manually create a release tag |
| `just promote-to-testing` | Merge dev → testing (feature complete) |
| `just promote-to-review` | Merge testing → review (bugs fixed) |
| `just promote-to-stable` | Merge review → master (ready for release) |

**Important:** The release script enforces strict version rules. See [Version Release Rules](#version-release-rules) below.

### Advanced Branch Operations

These commands provide powerful branch management capabilities. Use with caution as they perform complex git operations across multiple branches.

#### just promote

**Usage:** `just promote`

**Description:** Unified promotion command that merges changes through the entire branch pipeline sequentially: `dev → testing → review → master → main`.

**When to use:**
- When you need to promote changes through ALL branches at once
- After completing a development cycle and want to push to production
- To ensure all branches stay in sync with consistent versions

**How it differs from individual promote-to-X commands:**
- `just promote-to-testing` - Merges only `dev → testing` (one step)
- `just promote-to-review` - Merges only `testing → review` (one step)
- `just promote-to-stable` - Merges only `review → master` (one step)
- `just promote` - Runs ALL the above steps in sequence (full pipeline)

**⚠️ Warning:** This command stops on the FIRST merge conflict. If a conflict occurs:
1. The command will abort and leave you on the conflicted branch
2. You must resolve the conflict manually
3. Complete the merge with `git add . && git commit && git push`
4. Run `just promote` again to continue the remaining promotions

**Example:**
```bash
# Promote through entire pipeline
just promote

# Result:
# ✅ dev → testing
# ✅ testing → review
# ✅ review → master
# ✅ master → main
```

**Returns to:** Original branch after completion

---

#### just sync-main

**Usage:** `just sync-main`

**Description:** Makes the `main` branch identical to the `master` branch using a force-push with lease.

**When to use:**
- After promoting changes to `master` to keep `main` in sync
- The `main` and `master` branches serve different purposes:
  - `master` = The stable production branch (releases, PyPI publishing)
  - `main` = Mirror of master (for compatibility with GitHub conventions)

**What it does:**
1. Fetches latest from both `master` and `main`
2. Checks out `main`
3. Resets `main` to match `master` exactly (`git reset --hard master`)
4. Force-pushes to `origin/main` (with `--force-with-lease` for safety)
5. Returns to your original branch

**Example:**
```bash
just sync-main

# Result:
# ✅ main is now synced with master
#    (main and master are identical)
```

**Note:** This is automatically run as the final step of `just promote`

---

#### just equalize

**Usage:** `just equalize`

**Description:** Force-syncs ALL branches by merging through the entire promotion chain with interactive confirmation. This is a powerful emergency recovery tool.

**⚠️ DANGEROUS - Use only for emergency recovery!**

**When to use:**
- When branches have diverged significantly and need to be resynchronized
- After accidentally working on the wrong branch
- For emergency recovery when promotion commands fail
- To reset the entire branch structure to a consistent state

**What it does:**
1. Verifies you're in a git repository
2. Checks for uncommitted changes and warns you
3. Checks for active git worktrees
4. Shows current status of all branches
5. **Asks for confirmation** before proceeding
6. Merges through the chain: `dev → testing → review → master → main`
7. For each merge:
   - Checks if merge is needed (skips if already up to date)
   - Attempts the merge
   - On **conflict**: Aborts and provides detailed resolution instructions
   - On **success**: Pushes to remote

**Interactive prompts:**
- Warns about uncommitted changes
- Warns about multiple worktrees
- Requires explicit "yes" confirmation to proceed
- On conflict: Provides step-by-step resolution guide

**Example:**
```bash
just equalize

# Output:
# 🔄 Equalize All Branches (Promotion Chain)
# ═══════════════════════════════════════════════
#
# Promotion flow: dev → testing → review → master → main
#
# ⚠️  WARNING: This will merge through the promotion chain!
#    Each branch will be merged into the next: dev→testing→review→master→main
#    Merge conflicts will abort the process.
#
# Are you sure you want to continue? (yes/no):
```

**On merge conflict:**
```bash
❌ MERGE CONFLICT DETECTED!
═══════════════════════════════════════════════════════════════

Conflict occurred when merging:
  Source: testing
  Target: review (current branch)

📁 Conflicted files:
  - src/svg2fbf.py
  - pyproject.toml

🔧 To resolve the conflicts:
  1. Open the conflicted files listed above
  2. Look for conflict markers: <<<<<<< HEAD, =======, >>>>>>>
  3. Edit the files to resolve the conflicts
  ...
  9. Resume equalize to continue the promotion chain:
     just equalize
```

**⚠️ Critical warnings:**
- Always commit changes before running
- Check all worktrees for uncommitted changes
- Cannot be undone once merges are pushed
- Stops on first conflict - you must resolve and re-run

---

#### just backport-hotfix

**Usage:** `just backport-hotfix`

**Description:** Interactively backports hotfix commits from stable branches (`master` or `main`) to development branches (`dev`, `testing`, `review`). Used for critical fixes that need to be applied to earlier branches.

**When to use:**
- A critical bug was fixed in `master`/`main`
- The fix needs to be applied to `dev`, `testing`, or `review`
- You want to cherry-pick specific fixes without merging everything

**What it does:**
1. Validates you're on `dev`, `testing`, or `review` branch
2. Determines source branch (`main` preferred, falls back to `master`)
3. Finds all commits in source branch NOT in current branch
4. Shows interactive list of available commits
5. You select which commit to backport
6. Shows commit details (hash, message, author, date)
7. Checks for duplicate commits (same message + author)
8. Shows files that would be changed
9. **Performs conflict check** (dry-run merge)
10. On conflict: Aborts with detailed error and recommendations
11. On clean merge: Shows diff summary and asks for confirmation
12. Cherry-picks the commit if confirmed

**Interactive workflow:**
```bash
# Switch to target branch first
git checkout dev

# Run backport
just backport-hotfix

# Output:
# 🔄 Backport Hotfix from master/main
# ═══════════════════════════════════════════════
# Current branch: dev
# Source branch: master
#
# Commits available for backport:
#  1. abc1234 fix: Critical security patch
#  2. def5678 fix: Memory leak in processor
#  3. ghi9012 fix: Validation error
#
# Enter commit number to backport (or 'q' to quit):
```

**Safety features:**
- Validates source and target branches exist
- Checks for duplicate commits
- Performs conflict detection BEFORE attempting cherry-pick
- Shows file changes and diff summary
- Requires explicit confirmation

**On conflict:**
```bash
⚠️  WARNING: Merge conflicts detected!

Conflicting files:
  - src/processor.py
  - tests/test_processor.py

❌ Cannot safely backport this hotfix

Recommendations:
1. The hotfix may conflict with new code in dev
2. The bug may have been fixed differently in dev
3. The code that was fixed may have been removed/replaced in dev

Options:
  - Cherry-pick manually and resolve conflicts: git cherry-pick abc1234
  - Check if the bug still exists in dev
  - Skip this backport if the code changed significantly
```

**Example:**
```bash
git checkout dev
just backport-hotfix

# Select commit #1
# Review changes
# Confirm: yes

# Result:
# ✅ Hotfix backported successfully!
# Next steps:
# 1. Review the changes: git show HEAD
# 2. Run tests: just test
# 3. Push when ready: git push origin dev
```

---

#### just port-commit

**Usage:** `just port-commit`

**Description:** Interactively ports specific commits from the current branch to one or more target branches. More flexible than `backport-hotfix` as it works between ANY branches, not just stable→dev.

**When to use:**
- You made a commit on `dev` that should also be on `testing`
- You want to cherry-pick specific features between branches
- You need to apply the same fix to multiple branches simultaneously
- More control over which commits go where

**What it does:**
1. Shows list of all available branches (except current)
2. You select a comparison branch
3. Finds commits in current branch NOT in comparison branch
4. You select which commit to port
5. Shows list of target branches to port TO
6. You select one or multiple target branches (or "all")
7. For EACH target branch:
   - Checks for duplicate commits
   - Shows files that would change
   - Performs conflict check
   - Shows diff summary
   - Asks for confirmation (yes/no/skip)
   - Cherry-picks if confirmed
8. Returns to original branch when complete

**Interactive workflow:**
```bash
# Must be on source branch
git checkout dev

just port-commit

# Output:
# 🔄 Port Commit from dev
# ═══════════════════════════════════════════════
#
# Available branches:
#  1. testing
#  2. review
#  3. master
#  4. main
#  5. feature/new-parser
#
# Enter branch number to compare with (or 'q' to quit): 1
#
# Commits available for porting:
#  1. abc1234 feat: Add new validation mode
#  2. def5678 fix: Handle edge case in parser
#
# Enter commit number to port (or 'q' to quit): 2
#
# Port this commit to which branch(es)?
# Available target branches:
#  1. testing
#  2. review
#  3. master
#
# Enter branch numbers separated by spaces (e.g., '1 3 5')
# Or 'all' for all branches, or 'q' to quit
# > 1 2
```

**Multi-branch porting:**
- Can port to multiple branches in one run
- Each branch is processed independently
- Option to skip individual branches if conflicts detected
- Can choose yes/no/skip for each branch

**Safety per branch:**
- Duplicate detection
- Conflict check (dry-run)
- File change preview
- Individual confirmation

**Example - Port to multiple branches:**
```bash
git checkout dev
just port-commit

# 1. Select comparison branch: testing
# 2. Select commit: "fix: Handle edge case"
# 3. Select targets: "1 2" (testing and review)
#
# Processing branch: testing
#   ✅ No conflicts
#   Proceed? yes
#   ✅ Ported successfully
#
# Processing branch: review
#   ⚠️  Conflicts detected
#   Skip this branch? yes
#   ⏭️  Skipping review
#
# ✅ Port operation complete
#
# Next steps:
# 1. Review changes on each branch
# 2. Run tests on each branch
# 3. Push when ready
```

**Conflict handling:**
- Shows conflicting files
- Offers to skip the branch
- Offers to abort cherry-pick if you proceed anyway
- Continues to next branch on skip

**Use cases:**
1. **Port feature to multiple release branches:**
   ```bash
   git checkout feature/new-feature
   just port-commit
   # Port to: dev, testing, review
   ```

2. **Port hotfix from testing to dev:**
   ```bash
   git checkout testing
   just port-commit
   # Compare with: dev
   # Port to: dev
   ```

3. **Selective backporting:**
   ```bash
   git checkout master
   just port-commit
   # Compare with: dev
   # Select specific commit
   # Port to: dev, testing (skip review if conflicts)
   ```

---

## Complete Development Workflow

### 1. Initial Setup

```bash
git clone https://github.com/Emasoft/svg2fbf.git
cd svg2fbf
uv venv
just sync
```

### 3. Add/Remove Dependencies

```bash
# Remove dependency (it will execute uv sync automatically)
just remove requests

# Add dependency (it will execute uv sync automatically)
just add requests

# Add dev dependency (it will execute uv sync automatically)
just add-dev pytest-mock
```

**What happens when adding/removing dependencies with just:**
- `just add` → runs `uv add <package> --no-sync`
- `just sync` → runs `uv sync --no-install-project`
- Dependencies installed, svg2fbf NOT in venv ✓


### 4. Testing Changes

```bash
# Run all tests
just test

# Run with coverage
just test-cov

# Run specific test file
just test-file tests/test_svg2fbf.py

# Run tests matching pattern
just test-match "viewbox"

# Create random test session from W3C test suite
just test-random-w3c 50
```

### 5. Code Quality

```bash
# Format code
just fmt

# Lint code
just lint

# Fix linting issues
just lint-fix

# Run all checks (lint + format)
just check
```

### 6. Building and Installing

```bash
# Bump version and reinstall (default: alpha)
just reinstall

# Bump specific version type
just reinstall beta
just reinstall patch
just reinstall minor
just reinstall major

# Just build (no install)
just build

# Just install (from existing wheel)
just install
```

### 7. Verification

```bash
# Show current version
just version

# Show installed version
just version-installed

# Verify installation
just verify

# Check venv (should be empty)
just check-venv
```

### 8. Cleanup

```bash
# Clean temp directories
just clean-temp

# Clean build artifacts
just clean-build

# Clean Python cache
just clean-cache

# Clean everything
just clean-all
```

## Common Scenarios

### Scenario 1: Fresh Development Setup

```bash
git clone https://github.com/Emasoft/svg2fbf.git
cd svg2fbf
uv venv
just sync
just test
```

### Scenario 2: Add New Feature

```bash
# Add dependencies if needed
just add some-library
just add-dev pytest-mock
just sync

# Make changes to code

# Test
just test
just check

# Build and install
just reinstall
```

### Scenario 3: Update Dependencies

```bash
# Add new dependencies
just add requests
just add-dev pytest-mock
just sync

# Test changes
just test

# Rebuild
just reinstall
```

### Scenario 4: Clean Rebuild

```bash
# Clean everything
just clean-all

# Resync dependencies
just sync

# Rebuild and install
just reinstall
```

## Understanding the Workflow

svg2fbf is distributed as a **uv tool** (installed globally). This means:

- ✅ Users get isolated installation at `~/.local/share/uv/tools/svg2fbf/`
- ✅ Global commands work: `svg2fbf` and `svg-repair-viewbox`
- ✅ No conflicts with other projects and no dependencies hell.

For development:
- ✅ Dependencies available for testing
- ✅ svg2fbf NOT installed in venv (avoids editable install)
- ✅ Use `just reinstall` to test as end-users will use it

### How `just sync` Works

```bash
just sync
# Runs: uv sync --no-install-project --quiet
```

This:
1. Syncs all dependencies from `uv.lock`
2. Installs them in `.venv/`
3. **Skips** installing svg2fbf itself (no editable install)

### How `just reinstall` Works

```bash
just reinstall
# Runs in sequence:
# 1. uv version --bump alpha --no-sync
# 2. uv sync --no-install-project
# 3. uv build --wheel
# 4. uv tool install dist/svg2fbf-<version>.whl
```

This:
1. Bumps version in `pyproject.toml`
2. Syncs dependencies
3. Builds wheel in `dist/`
4. Installs as isolated uv tool

## Verification

### Check Venv Status

```bash
just check-venv
```

Expected output:
```
✓ svg2fbf not in venv (correct)
```

### Check Installation

```bash
just verify
```

Expected output:
```
Project version: 0.1.2a12
Installed version: 0.1.2a12
✓ svg2fbf not in venv (correct)
Commands available:
  svg2fbf
  svg-repair-viewbox
```

## Troubleshooting

### svg2fbf appears in venv

If `just check-venv` shows svg2fbf, it was accidentally installed:

```bash
# Remove from venv
uv pip uninstall svg2fbf

# Resync
just sync
```

### Dependencies missing

```bash
# Resync all dependencies
just sync

# Verify
uv pip list | grep -E "lxml|numpy|pyyaml|tomli-w"
```

### Tool command not found

If `svg2fbf` or `svg-repair-viewbox` commands are not found:

```bash
# Reinstall as uv tool
just reinstall

# Verify
just verify
```

### Just command not found

If `just` command is not found, install it:

```bash
# macOS
brew install just

# Windows
winget install --id Casey.Just

# Via cargo
cargo install just
```

## Best Practices

1. **Always use `just add`** when adding/removing dependencies. It will synch automatically.
   ```bash
   just add requests
   ```

2. **Never run `uv sync` directly** - it will install svg2fbf in editable mode
   ```bash
   # ❌ DON'T DO THIS
   uv sync

   # ✅ DO THIS INSTEAD
   just sync
   ```

3. **Test before building**
   ```bash
   just test
   just check
   just reinstall
   ```

4. **Keep venv clean** - verify svg2fbf is not installed
   ```bash
   just check-venv
   ```

5. **Use version bumps** - follow semantic versioning
   ```bash
   just reinstall alpha  # 0.1.2a1 → 0.1.2a2
   just reinstall beta   # 0.1.2a5 → 0.1.2b1
   just reinstall patch  # 0.1.2b1 → 0.1.2
   just reinstall minor  # 0.1.2 → 0.2.0
   just reinstall major  # 0.2.0 → 1.0.0
   ```

## CI/CD

The justfile includes a `ci` recipe that runs all checks:

```bash
just ci
```

This runs:
1. Linting (`just lint`)
2. Tests with coverage (`just test-cov`)

Use this locally before pushing to ensure CI will pass.

## Technical Details

### Directory Structure

```
svg2fbf/
├── justfile                 # Task definitions
├── pyproject.toml          # Project config
├── .venv/                  # Virtual environment (deps only, no svg2fbf)
├── dist/                   # Built wheels
├── src/                    # Source code
└── tests/                  # Tests
```

### Installation Locations

```
~/.local/
├── bin/
│   ├── svg2fbf              # Global command (symlink)
│   └── svg-repair-viewbox   # Global command (symlink)
└── share/
    └── uv/
        └── tools/
            └── svg2fbf/     # Isolated tool installation
                ├── lib/python3.10/site-packages/
                └── share/svg2fbf/
                    ├── node_scripts/
                    ├── package.json
                    └── node_modules/  # Puppeteer
```

## Version Release Rules

The release script (`scripts/release.sh`) enforces strict version progression rules to maintain a clean release history.

### The Three Publishing Rules

1. **Single Stage Rule**: Only ONE stage of any version can exist at a time
   - Cannot have 0.1.2a1 and 0.1.2b1 simultaneously
   - Versions progress: alpha → beta → rc → stable

2. **Stage Progression Rule**: Each version stage must be LOWER than the previous version's stage
   - After 0.1.2 (stable), next can be 0.1.3a1 (alpha)
   - After 0.1.2rc1, next can only be alpha or beta of 0.1.3

3. **RC Gateway Rule**: Alpha/beta of next version only allowed if previous version reached RC or stable
   - Prevents orphaned pre-releases that never reach production

### Branch-Stage Mapping

| Branch   | Stage  | Publishes to |
|----------|--------|--------------|
| dev      | alpha  | GitHub only  |
| testing  | beta   | GitHub only  |
| review   | rc     | GitHub only  |
| master   | stable | GitHub + PyPI|

### Release Workflow Example

```bash
# 1. Promote through branches
just promote-to-testing    # dev → testing (alpha → beta)
just promote-to-review     # testing → review (beta → rc)
just promote-to-stable     # review → master (rc → stable)

# 2. Create releases
just release               # GitHub only (all channels)
just publish               # GitHub + PyPI (all channels)
```

### What Happens on Violation

If you try to release a version that violates the rules:
- The release script will abort with a clear error message
- The version bump in pyproject.toml will be rolled back
- No commits or tags will be created

## Reference

- [Just documentation](https://just.systems/man/)
- [uv documentation](https://docs.astral.sh/uv/)
- [uv tool documentation](https://docs.astral.sh/uv/guides/tools/)

## Migration Notes

All project workflows have been consolidated into the justfile for consistency and cross-platform support. The justfile provides all necessary functionality with simpler, more maintainable commands.
