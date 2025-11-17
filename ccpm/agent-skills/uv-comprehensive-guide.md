# UV Comprehensive Guide

**Purpose**: Complete reference for all uv commands and workflows - project management, tool management, building, publishing, and pip interface.

**When to use this skill**: Any time you're working with uv for Python package management, dependency management, building, publishing, or running Python code.

---

## Table of Contents

1. [Tool Management (`uv tool`)](#tool-management-uv-tool)
2. [Project Management (`uv init`, `uv add`, `uv remove`, `uv sync`, `uv lock`)](#project-management)
3. [Running Code (`uv run`)](#running-code-uv-run)
4. [Building & Publishing (`uv build`, `uv publish`)](#building--publishing)
5. [Pip Interface (`uv pip`)](#pip-interface-uv-pip)
6. [Python Version Management (`uv python`)](#python-version-management)
7. [Environment Management (`uv venv`)](#environment-management-uv-venv)
8. [Utility Commands](#utility-commands)

---

## Tool Management (`uv tool`)

Tools are standalone command-line applications installed from Python packages.

### Installing Tools

```bash
# Install latest stable version
uv tool install <package-name>

# Install specific version
uv tool install <package-name>@<version>

# Install latest version (explicit)
uv tool install <package-name>@latest

# Install prerelease (must specify exact version)
uv tool install <package-name>@0.1.10a1
```

**Examples for svg2fbf**:
```bash
uv tool install svg2fbf              # Latest stable
uv tool install svg2fbf@0.1.11       # Specific version
uv tool install svg2fbf@0.1.10a1     # Alpha
uv tool install svg2fbf@0.1.10b1     # Beta
uv tool install svg2fbf@0.1.10rc1    # RC
```

### Upgrading Tools

```bash
# Upgrade to latest (respects original constraints)
uv tool upgrade <package-name>

# Upgrade to specific version (reinstall)
uv tool install <package-name>@<version>

# Upgrade all tools
uv tool upgrade --all
```

### Running Tools Temporarily

```bash
# Run without installing (uvx = uv tool run)
uvx <package-name> <args>

# Run specific version
uvx <package-name>@<version> <args>
```

**Examples**:
```bash
uvx svg2fbf --version                      # Try without installing
uvx svg2fbf@0.1.10 input.yaml             # Use specific version
uvx ruff check src/                        # Run ruff without installing
```

### Managing Tools

```bash
uv tool list                 # List installed tools
uv tool uninstall <package>  # Uninstall a tool
uv tool show <package>       # Show tool information
uv tool dir                  # Show tools directory
```

### ❌ Common Mistakes

```bash
# WRONG - these don't exist:
uv tool install --upgrade <package>           # No --upgrade flag
uv tool install <package> --prerelease allow  # Wrong syntax
uv tool upgrade svg2fbf@latest                # Upgrade doesn't take version
```

### ✅ Correct Syntax

```bash
# First time:
uv tool install svg2fbf

# Upgrade:
uv tool upgrade svg2fbf

# Specific prerelease:
uv tool install svg2fbf@0.1.10a1
```

---

## Project Management

Projects are Python codebases with `pyproject.toml` and managed dependencies.

### Creating Projects

```bash
# Create new project
uv init                          # Interactive
uv init my-project               # Named project
uv init --lib my-library         # Library project
uv init --app my-application     # Application project
uv init --script my-script.py    # Standalone script
uv init --python 3.12            # Specific Python version
```

### Adding Dependencies

```bash
# Add package
uv add <package-name>

# Add specific version
uv add "ruff==0.8.5"
uv add "requests>=2.31"

# Add development dependency
uv add --dev pytest
uv add --dev --group test pytest coverage

# Add optional dependency
uv add --optional <extra-name> <package>

# Add from requirements file
uv add -r requirements.txt

# Add editable dependency
uv add --editable ./path/to/package

# Add Git dependency
uv add <package> --git https://github.com/owner/repo
uv add <package> --git https://github.com/owner/repo --tag v1.0.0
uv add <package> --git https://github.com/owner/repo --branch main
uv add <package> --git https://github.com/owner/repo --rev abc123
```

### Removing Dependencies

```bash
# Remove package
uv remove <package-name>

# Remove dev dependency
uv remove --dev <package-name>

# Remove from specific group
uv remove --group <group-name> <package>
```

### Syncing Environment

```bash
# Sync project environment (install/update dependencies)
uv sync

# Sync without dev dependencies
uv sync --no-dev

# Sync specific groups
uv sync --group test --group docs

# Sync with all optional dependencies
uv sync --all-extras

# Sync without updating lockfile (frozen)
uv sync --frozen

# Assert lockfile won't change
uv sync --locked

# Dry run (show what would happen)
uv sync --dry-run

# Check if environment is synced
uv sync --check
```

### Locking Dependencies

```bash
# Update lockfile (uv.lock)
uv lock

# Lock without network (use cache only)
uv lock --offline

# Lock with specific Python version
uv lock --python 3.12

# Lock for specific platform
uv lock --python-platform linux
```

---

## Running Code (`uv run`)

Run commands or scripts within the project environment.

### Basic Usage

```bash
# Run Python script
uv run script.py

# Run Python module
uv run -m pytest

# Run command
uv run python --version

# Run with extra dependencies
uv run --extra dev pytest

# Run with all extras
uv run --all-extras python script.py
```

### Advanced Usage

```bash
# Run with temporary dependencies
uv run --with requests --with beautifulsoup4 script.py

# Run with editable dependency
uv run --with-editable ./local-package script.py

# Run from requirements file
uv run --with-requirements requirements.txt script.py

# Run in isolated environment
uv run --isolated pytest

# Run without syncing first
uv run --no-sync python script.py

# Run with frozen lockfile
uv run --frozen pytest

# Load environment variables from .env
uv run --env-file .env python script.py
```

### Python-Specific Options

```bash
# Run specific Python version
uv run --python 3.12 script.py

# Run for specific platform
uv run --python-platform linux script.py
```

---

## Building & Publishing

### Building Distributions

```bash
# Build both sdist and wheel
uv build

# Build from specific directory
uv build path/to/project

# Build only sdist
uv build --sdist

# Build only wheel
uv build --wheel

# Build to specific output directory
uv build --out-dir dist/

# Build specific workspace package
uv build --package my-package

# Build all workspace packages
uv build --all-packages

# Clear output directory first
uv build --clear

# Build with specific Python
uv build --python 3.12
```

### Publishing to PyPI

```bash
# Publish to PyPI (uses dist/* by default)
uv publish

# Publish specific files
uv publish dist/package-0.1.0*

# Publish with token
uv publish --token $UV_PUBLISH_TOKEN

# Publish with username/password
uv publish --username __token__ --password $PYPI_TOKEN

# Publish to Test PyPI
uv publish --publish-url https://test.pypi.org/legacy/

# Publish to named index (from config)
uv publish --index testpypi

# Dry run (don't actually upload)
uv publish --dry-run

# Use trusted publishing (GitHub Actions)
uv publish --trusted-publishing automatic
```

### Publishing Workflow

```bash
# Complete build and publish workflow
uv build
uv publish --token $UV_PUBLISH_TOKEN
```

---

## Pip Interface (`uv pip`)

Drop-in replacement for pip, pip-tools, and virtualenv commands.

### Installing Packages

```bash
# Install package
uv pip install <package>

# Install specific version
uv pip install "ruff==0.8.5"

# Install from requirements file
uv pip install -r requirements.txt

# Install editable package
uv pip install -e .
uv pip install -e ./path/to/package

# Install with extras
uv pip install "package[extra1,extra2]"

# Install from URL
uv pip install https://github.com/owner/repo/archive/main.zip

# Install into system Python (not recommended)
uv pip install --system <package>

# Install to specific target directory
uv pip install --target ./lib <package>

# Reinstall packages
uv pip install --reinstall <package>

# Upgrade packages
uv pip install --upgrade <package>
```

### Managing Packages

```bash
# Uninstall package
uv pip uninstall <package>

# Uninstall from requirements file
uv pip uninstall -r requirements.txt

# List installed packages
uv pip list

# List outdated packages
uv pip list --outdated

# Show package information
uv pip show <package>

# Display dependency tree
uv pip tree

# Check for conflicts
uv pip check

# Freeze dependencies
uv pip freeze

# Freeze to file
uv pip freeze > requirements.txt
```

### Compiling Requirements

```bash
# Compile requirements.in to requirements.txt
uv pip compile requirements.in

# Compile with extras
uv pip compile requirements.in --extra dev

# Compile for specific Python version
uv pip compile requirements.in --python-version 3.12

# Compile with upgrades
uv pip compile requirements.in --upgrade

# Compile for specific platform
uv pip compile requirements.in --python-platform linux

# Output to file
uv pip compile requirements.in -o requirements.txt
```

### Syncing Requirements

```bash
# Sync environment to requirements.txt
uv pip sync requirements.txt

# Exact sync (remove extraneous packages)
uv pip sync --exact requirements.txt

# Sync with Python version
uv pip sync --python-version 3.12 requirements.txt
```

---

## Python Version Management

Manage Python installations with uv.

```bash
# List available Python versions
uv python list

# List installed Python versions
uv python list --only-installed

# Install Python version
uv python install 3.12
uv python install 3.12.1
uv python install 3.11 3.12  # Multiple versions

# Find Python executable
uv python find
uv python find 3.12

# Pin Python version for project
uv python pin 3.12
uv python pin 3.12.1

# Uninstall Python version
uv python uninstall 3.11

# Show Python installation directory
uv python dir
```

---

## Environment Management (`uv venv`)

Create virtual environments.

```bash
# Create venv in .venv/
uv venv

# Create venv with specific name
uv venv my-env

# Create with specific Python
uv venv --python 3.12
uv venv --python python3.12

# Create with system site packages
uv venv --system-site-packages

# Create and activate (bash/zsh)
uv venv && source .venv/bin/activate

# Create and activate (fish)
uv venv && source .venv/bin/activate.fish

# Create and activate (PowerShell)
uv venv && .venv\Scripts\Activate.ps1
```

---

## Utility Commands

### Cache Management

```bash
# Show cache directory
uv cache dir

# Show cache size
uv cache size

# Clean specific package from cache
uv cache clean <package>

# Clean all cache
uv cache clean

# Prune unused cache entries
uv cache prune
```

### Dependency Tree

```bash
# Show project dependency tree
uv tree

# Show inverted tree (dependents)
uv tree --invert

# Show specific depth
uv tree --depth 2

# Include dev dependencies
uv tree --dev
```

### Export

```bash
# Export lockfile to requirements.txt format
uv export

# Export without dev dependencies
uv export --no-dev

# Export with specific format
uv export --format requirements-txt

# Export to file
uv export -o requirements.txt
```

### Version

```bash
# Read project version
uv version

# Update project version
uv version 0.2.0
uv version --bump patch  # 0.1.9 → 0.1.10
uv version --bump minor  # 0.1.9 → 0.2.0
uv version --bump major  # 0.1.9 → 1.0.0
```

### Code Formatting

```bash
# Format Python code in project
uv format

# Check formatting without modifying
uv format --check

# Format specific files
uv format src/ tests/
```

### Authentication

```bash
# Login to index
uv auth login <index-name>

# Logout from index
uv auth logout <index-name>

# Generate token
uv auth token <index-name>

# Show auth directory
uv auth dir
```

### Self Management

```bash
# Update uv itself
uv self update

# Show uv version
uv --version

# Show uv help
uv help
uv help <command>  # Command-specific help
```

---

## Global Options

These options work with all uv commands:

```bash
# Quiet output
uv <command> -q
uv <command> --quiet

# Verbose output
uv <command> -v
uv <command> --verbose

# No color
uv <command> --color never

# Offline mode (no network)
uv <command> --offline

# No cache
uv <command> --no-cache

# Custom cache directory
uv <command> --cache-dir /path/to/cache

# Change working directory
uv <command> --directory /path/to/project

# Specific project directory
uv <command> --project /path/to/project

# Custom config file
uv <command> --config-file /path/to/uv.toml

# No config discovery
uv <command> --no-config

# Hide progress bars
uv <command> --no-progress
```

---

## Common Workflows

### Setting Up a New Project

```bash
# Create project
uv init my-project --python 3.12
cd my-project

# Add dependencies
uv add requests "pydantic>=2.0"

# Add dev dependencies
uv add --dev pytest ruff mypy

# Sync environment
uv sync

# Run tests
uv run pytest
```

### Working on Existing Project

```bash
# Clone project
git clone https://github.com/user/project
cd project

# Sync environment (installs dependencies)
uv sync

# Run application
uv run python main.py

# Run tests
uv run pytest

# Add new dependency
uv add new-package

# Lock and commit
uv lock
git add uv.lock pyproject.toml
git commit -m "Add new-package dependency"
```

### Building and Publishing Package

```bash
# Ensure everything is up to date
uv sync

# Run tests
uv run pytest

# Bump version
uv version --bump patch

# Build distributions
uv build

# Publish to PyPI
uv publish --token $UV_PUBLISH_TOKEN

# Tag release
git tag v$(uv version)
git push --tags
```

### Installing svg2fbf (This Project)

```bash
# Install as tool (recommended)
uv tool install svg2fbf

# Or install in current environment
uv pip install svg2fbf

# Or run without installing
uvx svg2fbf --version

# Upgrade tool
uv tool upgrade svg2fbf

# Install specific version
uv tool install svg2fbf@0.1.11

# Install prerelease
uv tool install svg2fbf@0.1.11a1
```

---

## Key Principles

1. **`uv tool`** for standalone CLI tools (like svg2fbf, ruff, black)
2. **`uv run`** to execute code in project environment
3. **`uv sync`** to install/update project dependencies
4. **`uv pip`** when you need pip-compatible interface
5. **`uv build` + `uv publish`** for distributing packages
6. **Always use exact versions** for prereleases (e.g., `@0.1.10a1`)
7. **No `--upgrade` flag exists** for `uv tool install`
8. **No `--prerelease allow` flag** - use exact version instead
9. **`uvx` = `uv tool run`** (shorthand for temporary execution)
10. **Lock files matter** - commit `uv.lock` to version control

---

## Environment Variables

```bash
# Common environment variables
export UV_INDEX=https://pypi.org/simple
export UV_PYTHON=3.12
export UV_NO_CACHE=1
export UV_CACHE_DIR=/custom/cache
export UV_PUBLISH_TOKEN=pypi-...
export UV_PUBLISH_USERNAME=__token__
export UV_NO_PROGRESS=1
export UV_OFFLINE=1
```

---

## References

- Official documentation: https://docs.astral.sh/uv/
- CLI reference: https://docs.astral.sh/uv/reference/cli/
- Concepts: https://docs.astral.sh/uv/concepts/
- Guides: https://docs.astral.sh/uv/guides/

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Install tool | `uv tool install <package>` |
| Upgrade tool | `uv tool upgrade <package>` |
| Run tool temporarily | `uvx <package> <args>` |
| Create project | `uv init` |
| Add dependency | `uv add <package>` |
| Remove dependency | `uv remove <package>` |
| Sync dependencies | `uv sync` |
| Run script | `uv run script.py` |
| Build package | `uv build` |
| Publish package | `uv publish` |
| Install package (pip) | `uv pip install <package>` |
| Create venv | `uv venv` |
| Install Python | `uv python install 3.12` |
| Update uv | `uv self update` |
