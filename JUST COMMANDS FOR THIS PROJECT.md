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
| `just sync-main` | Sync main branch with master |

**Important:** The release script enforces strict version rules. See [Version Release Rules](#version-release-rules) below.

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
