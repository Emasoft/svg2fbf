# UV Command Reference

Complete, concise reference for all uv commands. For detailed docs: https://docs.astral.sh/uv/

---

## Core Commands

| Command | Description |
|---------|-------------|
| `uv init [project] [--lib\|--app\|--script]` | Create new project |
| `uv add <pkg> [--dev\|--optional\|--group]` | Add dependency |
| `uv remove <pkg> [--dev\|--group]` | Remove dependency |
| `uv sync [--frozen\|--locked\|--no-dev\|--all-extras]` | Sync environment to lockfile |
| `uv lock [--upgrade\|--offline]` | Update lockfile |
| `uv run <cmd\|script> [-m module] [--with pkg]` | Run command in project env |
| `uv build [--sdist\|--wheel] [-o dir]` | Build distributions |
| `uv publish [--token] [--index] [--dry-run]` | Upload to index (PyPI) |

---

## Version Management

| Command | Description |
|---------|-------------|
| `uv version` | Show project version |
| `uv version <value>` | Set version (e.g., `0.2.0`) |
| `uv version --bump <type>` | Bump version (major/minor/patch/stable/alpha/beta/rc/post/dev) |
| `uv version --short` | Show version only |
| `uv version --dry-run` | Show new version without writing |

**Examples:**
```bash
uv version                  # Show: 0.1.9
uv version 0.2.0            # Set to 0.2.0
uv version --bump patch     # 0.1.9 → 0.1.10
uv version --bump minor     # 0.1.9 → 0.2.0
uv version --bump major     # 0.1.9 → 1.0.0
uv version --bump alpha     # 0.1.9 → 0.1.10a0
uv version --bump stable    # 0.1.10a1 → 0.1.10
```

---

## Tool Management (`uv tool`)

| Command | Description |
|---------|-------------|
| `uv tool install <pkg>[@version]` | Install CLI tool |
| `uv tool upgrade <pkg> [--all]` | Upgrade tool(s) |
| `uv tool run <pkg> <args>` (or `uvx`) | Run tool without installing |
| `uv tool list` | List installed tools |
| `uv tool uninstall <pkg>` | Uninstall tool |
| `uv tool update-shell` | Add tool dir to PATH |
| `uv tool dir` | Show tools directory |

**Examples:**
```bash
uv tool install svg2fbf              # Latest
uv tool install svg2fbf@0.1.11       # Specific
uv tool install svg2fbf@0.1.10a1     # Prerelease
uv tool upgrade svg2fbf              # Upgrade
uvx svg2fbf --version                # Run once
```

**❌ WRONG:** `uv tool install --upgrade pkg` or `uv tool install pkg --prerelease allow`
**✅ CORRECT:** `uv tool upgrade pkg` or `uv tool install pkg@version`

---

## Pip Interface (`uv pip`)

| Command | Description |
|---------|-------------|
| `uv pip install <pkg> [-r file] [-e .] [--system]` | Install packages |
| `uv pip uninstall <pkg> [-r file]` | Uninstall packages |
| `uv pip list [--outdated]` | List packages |
| `uv pip show <pkg>` | Show package info |
| `uv pip freeze [> file]` | Output installed packages |
| `uv pip tree [--invert] [--depth N]` | Show dependency tree |
| `uv pip check` | Verify dependencies |
| `uv pip compile <in-file> [-o out-file] [--upgrade]` | Compile requirements |
| `uv pip sync <req-file> [--exact]` | Sync to requirements |

**Examples:**
```bash
uv pip install requests
uv pip install -r requirements.txt
uv pip install -e .
uv pip compile requirements.in -o requirements.txt
uv pip sync requirements.txt
uv pip tree
uv pip check
```

---

## Python Version Management (`uv python`)

| Command | Description |
|---------|-------------|
| `uv python list [--only-installed]` | List Python versions |
| `uv python install <version>` | Install Python |
| `uv python upgrade [<version>]` | Upgrade Python version(s) |
| `uv python find [<version>]` | Find Python executable |
| `uv python pin <version>` | Pin Python for project |
| `uv python uninstall <version>` | Uninstall Python |
| `uv python update-shell` | Add Python dir to PATH |
| `uv python dir` | Show Python install dir |

**Examples:**
```bash
uv python install 3.12
uv python list --only-installed
uv python pin 3.12
uv python find 3.12
```

---

## Environment Management

| Command | Description |
|---------|-------------|
| `uv venv [name] [--python ver] [--system-site-packages]` | Create virtual environment |

**Examples:**
```bash
uv venv                      # Create .venv
uv venv --python 3.12        # Specific Python
source .venv/bin/activate    # Activate (bash/zsh)
```

---

## Utility Commands

### Export
```bash
uv export [-o file] [--no-dev] [--format requirements-txt]
```

### Tree
```bash
uv tree [--invert] [--depth N] [--dev]
```

### Format
```bash
uv format [paths] [--check]
```

### Cache
| Command | Description |
|---------|-------------|
| `uv cache clean [pkg]` | Clean cache |
| `uv cache prune` | Prune unreachable objects |
| `uv cache dir` | Show cache directory |
| `uv cache size` | Show cache size |

### Authentication
| Command | Description |
|---------|-------------|
| `uv auth login <index>` | Login to index |
| `uv auth logout <index>` | Logout from index |
| `uv auth token <index>` | Show auth token |
| `uv auth dir` | Show credentials directory |

### Self Management
| Command | Description |
|---------|-------------|
| `uv self update` | Update uv itself |
| `uv self version` | Show uv version |
| `uv --version` | Show uv version (short) |

### Shell Completion
```bash
uv generate-shell-completion <shell>  # bash|zsh|fish|powershell|elvish|nushell
```

---

## Global Options

Apply to all commands:

| Option | Description |
|--------|-------------|
| `-q, --quiet` | Quiet output |
| `-v, --verbose` | Verbose output |
| `--color <never\|always\|auto>` | Color mode |
| `--offline` | No network access |
| `--no-cache` | Disable cache |
| `--cache-dir <dir>` | Custom cache directory |
| `--directory <dir>` | Change working directory |
| `--project <dir>` | Specify project directory |
| `--config-file <file>` | Custom uv.toml path |
| `--no-config` | Ignore config files |
| `--no-progress` | Hide progress bars |
| `--python <version>` | Specify Python version |
| `--managed-python` | Require uv-managed Python |
| `--no-python-downloads` | Disable auto Python downloads |

---

## Common Workflows

### New Project
```bash
uv init my-project --python 3.12
cd my-project
uv add requests pydantic
uv add --dev pytest ruff mypy
uv sync
uv run pytest
```

### Existing Project
```bash
git clone repo && cd repo
uv sync
uv run python main.py
```

### Build & Publish
```bash
uv version --bump patch
uv build
uv publish --token $UV_PUBLISH_TOKEN
```

### Tool Installation (svg2fbf)
```bash
uv tool install svg2fbf              # Install
uv tool upgrade svg2fbf              # Upgrade
uv tool install svg2fbf@0.1.11a1     # Prerelease
uvx svg2fbf examples/test.yaml       # Try once
```

---

## Important Notes

1. **Tool install:** Use `uv tool install` (first time) or `uv tool upgrade` (upgrade existing)
2. **Prerelease versions:** Must specify exact version with `@version` (e.g., `@0.1.10a1`)
3. **No `--upgrade` flag:** The command is `upgrade`, not a flag to `install`
4. **No `--prerelease` flag:** Use exact version specification instead
5. **`uvx` = `uv tool run`:** Shorthand for temporary execution
6. **Lock files:** Commit `uv.lock` to version control
7. **Version bumping:** Use `uv version --bump <type>` for semantic versioning
8. **pip compile:** Replaces `pip-compile` from pip-tools
9. **pip sync:** Replaces `pip-sync` from pip-tools

---

## Environment Variables

```bash
UV_INDEX=https://pypi.org/simple
UV_PYTHON=3.12
UV_NO_CACHE=1
UV_CACHE_DIR=/custom/cache
UV_PUBLISH_TOKEN=pypi-...
UV_NO_PROGRESS=1
UV_OFFLINE=1
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Install tool | `uv tool install pkg` |
| Upgrade tool | `uv tool upgrade pkg` |
| Run tool once | `uvx pkg` |
| New project | `uv init` |
| Add dep | `uv add pkg` |
| Remove dep | `uv remove pkg` |
| Sync | `uv sync` |
| Lock | `uv lock` |
| Run | `uv run script.py` |
| Build | `uv build` |
| Publish | `uv publish` |
| Pip install | `uv pip install pkg` |
| Pip compile | `uv pip compile in -o out` |
| Create venv | `uv venv` |
| Install Python | `uv python install 3.12` |
| Bump version | `uv version --bump patch` |
| Update uv | `uv self update` |
