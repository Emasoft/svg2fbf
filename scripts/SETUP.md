# Development Setup Guide

Complete setup guide for svg2fbf development environment.

## Quick Start

```bash
# Clone repository (recommended: use GitHub CLI)
gh repo clone Emasoft/svg2fbf -- -b dev
cd svg2fbf

# Or use URL format:
# gh repo clone https://github.com/Emasoft/svg2fbf.git -- -b dev
# cd svg2fbf

# Install git hooks
./scripts/install-hooks.sh
# or: just install-hooks

# Sync dependencies
just sync

# You're ready! Run tests:
just test
```

**Why `gh repo clone`?** GitHub CLI handles authentication automatically and accepts both `Owner/Repo` format and full URLs. The `-- -b BRANCH` flag checks out the specified branch immediately.

## Detailed Setup

### 1. Prerequisites

**Required:**
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- [just](https://github.com/casey/just) - Task runner
- Git

**Optional:**
- [pre-commit](https://pre-commit.com/) - Git hook framework
- Node.js - For svg-repair-viewbox utility

### 2. Install Tools

#### Install uv (Python package manager)
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip
pip install uv
```

#### Install just (task runner)
```bash
# macOS
brew install just

# Linux
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin

# Windows
winget install --id Casey.Just

# Or via cargo
cargo install just
```

### 3. Clone Repository

**⚠️ IMPORTANT: Developers must clone the full repository to get test data (93MB+)**

PyPI and GitHub releases exclude test sessions to keep downloads small. Use the GitHub CLI for authentication and ease:

```bash
# Recommended: GitHub CLI (handles auth automatically)
# Method 1: Owner/Repo format (shortest)
gh repo clone Emasoft/svg2fbf
cd svg2fbf
git checkout dev        # for alpha development

# Method 2: Clone and checkout in one command (RECOMMENDED)
# gh repo clone Emasoft/svg2fbf -- -b dev
# cd svg2fbf

# Method 3: Using full HTTPS URL
# gh repo clone https://github.com/Emasoft/svg2fbf.git -- -b dev
# cd svg2fbf

# Method 4: Using SSH URL (if you have SSH keys set up)
# gh repo clone git@github.com:Emasoft/svg2fbf.git -- -b dev
# cd svg2fbf

# Alternative: standard git clone (without gh CLI)
# git clone https://github.com/Emasoft/svg2fbf.git
# cd svg2fbf
# git checkout dev
```

**Why clone vs install from PyPI?**
- ✅ Full test suite (93MB+ test sessions)
- ✅ Development tools and scripts
- ✅ Complete git history
- ✅ Ability to contribute changes

### 4. Setup Environment

#### Install Git Hooks (Important!)
```bash
./scripts/install-hooks.sh
```

This installs:
- Pre-commit hooks (ruff linting, formatting, secret scanning)
- Pre-push hooks
- Any custom hooks from `scripts/hooks/`

**Why this matters:** Hooks ensure code quality before commits. They're preserved in `scripts/hooks/` so they survive `.git/` deletion.

#### Sync Dependencies
```bash
just sync
```

This syncs all runtime and dev dependencies without installing svg2fbf in the venv (svg2fbf should only be installed as a uv tool).

### 5. Verify Setup

```bash
just verify
```

Should show:
- Project version
- Installed tool version
- Available commands

## Daily Development Workflow

### Make Changes

```bash
# 1. Create a branch
git checkout -b feature/my-feature

# 2. Make code changes...

# 3. Run tests
just test

# 4. Check code quality
just check

# 5. Build and install for testing
just install  # Smart: only builds if code changed
```

### Commit & Push

```bash
# Commit (hooks will run automatically)
git add .
git commit -m "feat: Add awesome feature"

# Push
git push origin feature/my-feature
```

## Common Tasks

### Managing Dependencies

```bash
# Add runtime dependency
just add numpy

# Add dev dependency
just add-dev pytest

# Remove dependency
just remove old-package

# Sync after manual pyproject.toml edits
just sync
```

### Testing

```bash
# Run all tests
just test

# Run with coverage
just test-cov

# Run specific test file
just test-file tests/test_something.py

# Run tests matching pattern
just test-match "test_transform"
```

### Building & Installing

```bash
# Build wheel (NO version bump - keeps current version)
just build

# Install current wheel from dist/
just install

# Install specific release channels from GitHub
just install-alpha    # Install alpha from dev branch
just install-beta     # Install beta from testing branch
just install-rc       # Install rc from review branch
just install-stable   # Install stable from master branch

# Force full rebuild (clean + build + install, NO version bump)
just reinstall
```

**Note:** Version bumping is handled automatically by the release pipeline. Use `just release` or `just publish` for versioned releases.

### Code Quality

```bash
# Format code
just fmt

# Lint code
just lint

# Fix linting issues
just lint-fix

# Run all checks
just check
```

### Cleanup

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

## If .git/ Gets Deleted

If you need to recreate `.git/` (e.g., moving to a new repo):

```bash
# 1. Reinitialize git
git init

# 2. Reinstall hooks (important!)
./scripts/install-hooks.sh

# 3. Add remote
git remote add origin https://github.com/Emasoft/svg2fbf.git

# 4. Pull history (if needed)
git pull origin main
```

**All hooks are preserved** in `scripts/hooks/` and `.pre-commit-config.yaml`, so you can always reinstall them!

## Troubleshooting

### Hooks Not Running

```bash
# Reinstall hooks
just install-hooks

# Or manually
./scripts/install-hooks.sh
```

### Dependencies Out of Sync

```bash
# Force sync
just sync

# Or manually
uv sync --no-install-project
```

### svg2fbf in venv (wrong!)

svg2fbf should NOT be in the venv. It should only be installed as a uv tool.

```bash
# Check
just check-venv

# If installed in venv, clean and resync
rm -rf .venv
uv sync --no-install-project
```

### Build Fails

```bash
# Clean and rebuild
just clean-build
just build
```

## Development Tips

1. **Use `just --list`** to see all available commands
2. **Use `just workflow`** to see the recommended workflow
3. **Commit often** - hooks will catch issues early
4. **Run tests before push** - `just test`
5. **Use `just install`** for quick iteration - it's smart and only rebuilds when needed

## Editor Setup

### VS Code

Recommended extensions:
- Python
- Ruff
- GitLens
- Just (syntax highlighting for justfile)

Settings (`.vscode/settings.json`):
```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": "explicit",
      "source.organizeImports": "explicit"
    }
  }
}
```

### PyCharm

1. Install Python plugin
2. Set Python interpreter to `.venv/bin/python`
3. Enable ruff in Settings → Tools → External Tools

## Release Workflow

svg2fbf uses a 4-stage branch promotion pipeline:

```
dev → testing → review → master
 ↓       ↓        ↓        ↓
alpha   beta     rc     stable (+ PyPI)
```

### Quick Commands

```bash
# Promote through pipeline
just promote-to-testing   # dev → testing (feature complete)
just promote-to-review    # testing → review (bugs fixed)
just promote-to-stable    # review → master (ready for release)

# Create releases
./scripts/release.sh --alpha dev --beta testing --rc review --stable master
```

**For complete release documentation, see:**
- 📘 [`docs/RELEASE_WORKFLOW.md`](../docs/RELEASE_WORKFLOW.md) - Complete release guide
- 🔧 `./scripts/release.sh --help` - Release script help
- 📋 `just --list` - All available commands

## Next Steps

- Read `justfile` for all available commands
- Check `scripts/hooks/README.md` for custom hooks
- Review `.pre-commit-config.yaml` for hook configuration
- **Read `docs/RELEASE_WORKFLOW.md` for release process** ⭐
- See project README for usage examples
