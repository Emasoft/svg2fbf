# UV Command Reference

Complete reference with command-specific options. Docs: https://docs.astral.sh/uv/

---

## Tool Management

### `uv tool install <pkg>[@version]`
Install command-line tool.
- `-w, --with <pkg>` - Install with additional packages
- `--with-requirements <file>` - Install with packages from file
- `-e, --editable` - Install as editable
- `--with-editable <path>` - Include editable package
- `--with-executables-from <pkg>` - Use executables from this package
- `--force` - Force reinstall
- `--python <version>` - Python version to use

**Examples:**
```bash
uv tool install svg2fbf                    # Latest
uv tool install svg2fbf@0.1.11             # Specific version
uv tool install svg2fbf@0.1.10a1           # Prerelease (exact version required)
uv tool install ruff --with ruff-lsp       # With additional package
```

❌ NO `--extra` flag (use `--with` instead)
❌ NO `--upgrade` flag (use `uv tool upgrade` instead)

### `uv tool upgrade <pkg>`
Upgrade installed tool.
- `--all` - Upgrade all tools

### `uv tool run <pkg>` (or `uvx`)
Run tool without installing.

### Other: `list`, `uninstall`, `update-shell`, `dir`

---

## Project Management

### `uv init [path]`
Create new project.
- `--name <name>` - Project name
- `--lib` - Library project
- `--app` - Application project
- `--script` - Script file
- `--bare` - Only pyproject.toml
- `--package` / `--no-package` - Setup as package
- `--build-backend <backend>` - uv|hatch|flit|pdm|poetry|setuptools|maturin|scikit
- `--vcs <vcs>` - git|none
- `--python <version>` - Python version

### `uv add <pkg>`
Add dependency.
- `--dev` - Add to dev dependencies
- `--optional <extra>` - Add to optional dependencies
- `--group <group>` - Add to dependency group
- `--editable` - Add as editable
- `--raw` - Add as provided (no version constraint)
- `--bounds <type>` - Version specifier: lower|major|minor|exact
- `--rev <commit>` - Git commit
- `--tag <tag>` - Git tag
- `--branch <branch>` - Git branch
- `--extra <extra>` - Enable extras for THIS dependency
- `-r, --requirements <file>` - Add from file
- `--package <pkg>` - Add to workspace package
- `--script <script>` - Add to Python script
- `--no-sync` - Don't sync after adding

**Examples:**
```bash
uv add requests                           # Add package
uv add "ruff>=0.8"                        # With version constraint
uv add --dev pytest                       # Dev dependency
uv add --group test pytest coverage       # Dependency group
uv add --optional viz matplotlib          # Optional dependency
uv add sqlalchemy --extra asyncio         # With extras for sqlalchemy
uv add my-pkg --editable ./local-pkg      # Editable local package
uv add pkg --git https://github.com/o/r   # From Git
```

### `uv remove <pkg>`
Remove dependency.
- `--dev` - Remove from dev dependencies
- `--optional <extra>` - Remove from optional
- `--group <group>` - Remove from group
- `--package <pkg>` - Remove from workspace package

### `uv sync`
Sync environment to lockfile.
- `--extra <extra>` - Include optional dependency extra
- `--all-extras` - Include all extras
- `--no-extra <extra>` - Exclude extra (with --all-extras)
- `--dev` / `--no-dev` / `--only-dev` - Dev dependencies
- `--group <group>` / `--no-group <group>` / `--only-group <group>` / `--all-groups` - Dependency groups
- `--no-install-project` - Don't install project itself
- `--no-install-workspace` - Don't install workspace members
- `--frozen` - Don't update lockfile
- `--locked` - Assert lockfile unchanged
- `--inexact` - Don't remove extraneous packages
- `--check` - Check if synced

**Examples:**
```bash
uv sync                          # Sync all
uv sync --no-dev                 # Skip dev deps
uv sync --all-extras             # Include all extras
uv sync --group test --group docs  # Specific groups
uv sync --frozen                 # Don't update lock
```

### `uv lock`
Update lockfile.
- `--check` - Check if up-to-date
- `--check-exists` - Assert uv.lock exists
- `--dry-run` - Don't write lockfile

### `uv run <cmd|script>`
Run command/script in project environment.
- `-m, --module` - Run Python module
- `--extra <extra>` - Include optional extra
- `--all-extras` - Include all extras
- `--dev` / `--no-dev` / `--only-dev` - Dev dependencies
- `--group <group>` / `--only-group <group>` / `--all-groups` - Dependency groups
- `-w, --with <pkg>` - Temporary additional packages
- `--with-editable <path>` - Temporary editable package
- `--with-requirements <file>` - Temporary packages from file
- `--isolated` - Isolated environment
- `--no-sync` - Don't sync before running
- `--env-file <file>` - Load .env file
- `-s, --script` - Treat as Python script
- `--package <pkg>` - Run in workspace package

**Examples:**
```bash
uv run script.py                      # Run script
uv run -m pytest                      # Run module
uv run --with requests script.py      # With temporary package
uv run --all-extras pytest            # With all extras
uv run --isolated test.py             # Isolated environment
```

---

## Version Management

### `uv version [value]`
Read or update project version.
- `--bump <type>` - Bump version: major|minor|patch|stable|alpha|beta|rc|post|dev
- `--short` - Show version only
- `--dry-run` - Don't write to pyproject.toml
- `--package <pkg>` - Update workspace package

**Examples:**
```bash
uv version                   # Show: 0.1.9
uv version 0.2.0             # Set to 0.2.0
uv version --bump patch      # 0.1.9 → 0.1.10
uv version --bump minor      # 0.1.9 → 0.2.0
uv version --bump major      # 0.1.9 → 1.0.0
uv version --bump alpha      # 0.1.9 → 0.1.10a0
uv version --bump beta       # 0.1.10a1 → 0.1.10b0
uv version --bump rc         # 0.1.10b1 → 0.1.10rc0
uv version --bump stable     # 0.1.10rc1 → 0.1.10
```

---

## Build & Publish

### `uv build [path]`
Build distributions (sdist and wheel).
- `--sdist` - Build source distribution only
- `--wheel` - Build wheel only
- `-o, --out-dir <dir>` - Output directory (default: dist/)
- `--package <pkg>` - Build workspace package
- `--all-packages` - Build all workspace packages
- `--clear` - Clear output directory first
- `--no-build-logs` - Hide build backend logs
- `-b, --build-constraints <file>` - Constrain build dependencies

**Examples:**
```bash
uv build                     # Build sdist + wheel
uv build --sdist             # Source distribution only
uv build --wheel             # Wheel only
uv build -o releases/        # Custom output directory
uv build --package my-pkg    # Specific workspace package
```

### `uv publish [files...]`
Upload distributions to PyPI.
- `-t, --token <token>` - PyPI token (env: UV_PUBLISH_TOKEN)
- `-u, --username <user>` - Username
- `-p, --password <pass>` - Password
- `--index <name>` - Named index from config
- `--publish-url <url>` - Upload endpoint URL
- `--check-url <url>` - Check for existing files
- `--trusted-publishing <mode>` - automatic|always|never
- `--dry-run` - Don't upload

**Examples:**
```bash
uv publish                                 # Publish dist/*
uv publish --token $UV_PUBLISH_TOKEN       # With token
uv publish dist/pkg-0.1.0*                 # Specific files
uv publish --publish-url https://test.pypi.org/legacy/  # Test PyPI
uv publish --dry-run                       # Preview
```

---

## Pip Interface

### `uv pip install <pkg>`
- `-r, --requirements <file>` - Install from file
- `-e, --editable <path>` - Editable install
- `--extra <extra>` - Include optional extras
- `--all-extras` - Include all extras
- `--system` - Install to system Python (not recommended)
- `--target <dir>` - Install to directory
- `--reinstall` - Force reinstall
- `--upgrade` / `-U` - Allow upgrades

### `uv pip compile <in-file>`
Compile requirements.in → requirements.txt (replaces pip-compile).
- `-o, --output-file <file>` - Output file
- `--extra <extra>` - Include optional extras
- `--all-extras` - Include all extras
- `-U, --upgrade` - Allow package upgrades
- `-P, --upgrade-package <pkg>` - Upgrade specific package
- `--python-version <ver>` - Target Python version
- `--python-platform <platform>` - Target platform

### `uv pip sync <req-file>`
Sync environment to requirements.txt (replaces pip-sync).
- `--exact` - Remove extraneous packages
- `--python-version <ver>` - Target Python version

### Other: `uninstall`, `list`, `show`, `freeze`, `tree`, `check`

---

## Python Management

### `uv python install <version>`
Install Python version.
- Multiple versions: `uv python install 3.11 3.12`

### `uv python upgrade [version]`
Upgrade Python installations.

### `uv python pin <version>`
Pin Python version for project.

### Other: `list`, `find`, `uninstall`, `update-shell`, `dir`

---

## Utilities

### `uv export`
Export lockfile to alternate format.
- `--format <fmt>` - requirements.txt | pylock.toml
- `-o, --output-file <file>` - Output file
- `--no-dev` - Exclude dev dependencies
- `--extra <extra>` / `--all-extras` - Extras
- `--package <pkg>` - Export workspace package

### `uv tree`
Display dependency tree.
- `-d, --depth <N>` - Max depth (default: 255)
- `--invert` - Show reverse dependencies
- `--prune <pkg>` - Prune package
- `--package <pkg>` - Show specific package
- `--outdated` - Show latest versions
- `--show-sizes` - Show wheel sizes

### `uv format [paths]`
Format Python code (uses Ruff).
- `--check` - Check without applying
- `--diff` - Show diff without applying
- `--version <ver>` - Ruff version to use

### `uv cache`
- `clean [pkg]` - Clean cache
- `prune` - Remove unreachable objects
- `dir` - Show cache directory
- `size` - Show cache size

### `uv auth`
- `login <index>` - Login to index
- `logout <index>` - Logout
- `token <index>` - Show token
- `dir` - Show credentials directory

### `uv venv [name]`
Create virtual environment.
- `--python <version>` - Python version
- `--system-site-packages` - Include system packages

### `uv self`
- `update` - Update uv itself
- `version` - Show uv version

### `uv generate-shell-completion <shell>`
bash|zsh|fish|powershell|elvish|nushell

---

## Global Options

All commands support:
- `-q, --quiet` - Quiet output
- `-v, --verbose` - Verbose output
- `--color <mode>` - never|always|auto
- `--offline` - No network
- `--no-cache` - Disable cache
- `--cache-dir <dir>` - Custom cache
- `--directory <dir>` - Working directory
- `--project <dir>` - Project directory
- `--python <version>` - Python version
- `--no-progress` - Hide progress

---

## Key Differences

| Feature | uv tool install | uv add | uv sync | uv run |
|---------|----------------|--------|---------|--------|
| Extras | ❌ (use `--with`) | ✅ `--extra` (for dep) | ✅ `--extra` (from project) | ✅ `--extra` |
| Dev deps | ❌ | ✅ `--dev` | ✅ `--dev/--no-dev` | ✅ `--dev` |
| Groups | ❌ | ✅ `--group` | ✅ `--group` | ✅ `--group` |
| Temp packages | ✅ `--with` | ❌ | ❌ | ✅ `--with` |
| Editable | ✅ `--editable` | ✅ `--editable` | ✅ `--no-editable` | ❌ |
| Git source | ❌ | ✅ `--rev/--tag/--branch` | ❌ | ❌ |

---

## Common Errors

❌ **WRONG:**
```bash
uv tool install svg2fbf --extra viz        # NO --extra for tools!
uv tool install --upgrade svg2fbf          # NO --upgrade flag!
uv tool install svg2fbf --prerelease allow # Wrong syntax!
uv version --bump 0.2.0                    # --bump takes TYPE not value!
```

✅ **CORRECT:**
```bash
uv tool install svg2fbf --with viz-package  # Use --with for additional packages
uv tool upgrade svg2fbf                     # Use upgrade command
uv tool install svg2fbf@0.1.10a1            # Exact version for prereleases
uv version --bump minor                     # Use semantic type
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Install tool | `uv tool install pkg` |
| Upgrade tool | `uv tool upgrade pkg` |
| Tool + extras | `uv tool install pkg --with extra-pkg` |
| Run once | `uvx pkg` |
| New project | `uv init` |
| Add dep | `uv add pkg` |
| Add dev dep | `uv add --dev pkg` |
| Add with extras | `uv add sqlalchemy --extra asyncio` |
| Remove dep | `uv remove pkg` |
| Sync (no dev) | `uv sync --no-dev` |
| Sync with extras | `uv sync --all-extras` |
| Lock | `uv lock` |
| Run with extras | `uv run --all-extras pytest` |
| Run with temp pkg | `uv run --with requests script.py` |
| Bump version | `uv version --bump patch` |
| Build | `uv build` |
| Publish | `uv publish --token $TOKEN` |
| Pip compile | `uv pip compile requirements.in` |
| Pip sync | `uv pip sync requirements.txt` |
| Create venv | `uv venv` |
| Install Python | `uv python install 3.12` |
| Format code | `uv format` |
| Update uv | `uv self update` |
