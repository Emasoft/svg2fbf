# UV Tool Management Skill

**Purpose**: Provide correct uv tool syntax for installing, upgrading, and managing uv-distributed Python tools.

**When to use this skill**: When documenting installation instructions, writing release notes, updating README files, or helping users install/upgrade tools distributed via PyPI and installable with uv.

---

## Core UV Tool Commands

### Installing a Tool (First Time)

```bash
# Install latest stable version
uv tool install <package-name>

# Install specific version
uv tool install <package-name>@<version>

# Install latest version (explicit)
uv tool install <package-name>@latest

# Install prerelease version (specific version required)
uv tool install <package-name>@0.1.10a1
```

**Examples for svg2fbf**:
```bash
# Latest stable
uv tool install svg2fbf

# Specific version
uv tool install svg2fbf@0.1.11

# Alpha/beta/rc version (must specify exact version)
uv tool install svg2fbf@0.1.10a1  # Alpha
uv tool install svg2fbf@0.1.10b1  # Beta
uv tool install svg2fbf@0.1.10rc1 # Release Candidate
```

### Upgrading an Existing Tool

```bash
# Upgrade to latest version (respects original constraints)
uv tool upgrade <package-name>

# Upgrade to specific version (reinstall)
uv tool install <package-name>@<version>
```

**Examples for svg2fbf**:
```bash
# Upgrade to latest
uv tool upgrade svg2fbf

# Upgrade to specific version (use install)
uv tool install svg2fbf@0.1.12
```

### Temporary Execution (No Installation)

```bash
# Run tool without installing
uvx <package-name> <args>

# Run specific version
uvx <package-name>@<version> <args>
```

**Examples for svg2fbf**:
```bash
# Try without installing
uvx svg2fbf --version

# Use specific version temporarily
uvx svg2fbf@0.1.10 examples/test.yaml
```

### Other Useful Commands

```bash
# List installed tools
uv tool list

# Uninstall a tool
uv tool uninstall <package-name>

# Show tool information
uv tool show <package-name>
```

---

## Common Mistakes to Avoid

### ❌ WRONG Syntax

```bash
# These commands DO NOT exist:
uv tool install --upgrade <package>     # No --upgrade flag
uv tool install <package> --prerelease allow  # Wrong flag (pip syntax)
pip install <package>                   # Not recommended for tools
python -m pip install <package>         # Not recommended for tools
```

### ✅ CORRECT Syntax

```bash
# First time install:
uv tool install svg2fbf

# Upgrade existing:
uv tool upgrade svg2fbf

# Install specific prerelease:
uv tool install svg2fbf@0.1.10a1
```

---

## Documentation Templates

### For Issue Comments / Release Notes

```markdown
**Install/Upgrade:**

```bash
# If not installed yet:
uv tool install svg2fbf

# If already installed:
uv tool upgrade svg2fbf

# Verify installation:
svg2fbf --version
```
```

### For README / Installation Docs

```markdown
## Installation

### Recommended: Using uv (fastest)

```bash
uv tool install svg2fbf
```

### Alternative: Using pip

```bash
pip install svg2fbf
```

### Upgrading

```bash
# With uv:
uv tool upgrade svg2fbf

# With pip:
pip install --upgrade svg2fbf
```

### Verifying Installation

```bash
svg2fbf --version
```
```

### For Multi-Channel Releases

```markdown
## Installation by Channel

| Channel | Version Example | Installation Command |
|---------|----------------|----------------------|
| Stable  | `0.1.11`       | `uv tool install svg2fbf` |
| RC      | `0.1.11rc1`    | `uv tool install svg2fbf@0.1.11rc1` |
| Beta    | `0.1.11b1`     | `uv tool install svg2fbf@0.1.11b1` |
| Alpha   | `0.1.11a1`     | `uv tool install svg2fbf@0.1.11a1` |

**Upgrading:**
- Stable: `uv tool upgrade svg2fbf`
- Prerelease: `uv tool install svg2fbf@<version>` (reinstall with specific version)
```

---

## Key Principles

1. **`uv tool install`** = First time installation or reinstall with specific version
2. **`uv tool upgrade`** = Upgrade existing installation to latest (respects constraints)
3. **`uvx`** = Temporary run without installation
4. **Prerelease versions** = Must specify exact version with `@version`
5. **No `--upgrade` flag** = The command is `upgrade`, not a flag
6. **No `--prerelease` flag** = Use exact version specification instead

---

## Reference

Official documentation: https://docs.astral.sh/uv/concepts/tools/

---

## Agent Behavior Rules

When writing documentation or helping users:

1. ✅ **ALWAYS use `uv tool install` for first-time installation**
2. ✅ **ALWAYS use `uv tool upgrade` for upgrading existing installations**
3. ✅ **ALWAYS specify exact version for prereleases** (e.g., `@0.1.10a1`)
4. ✅ **ALWAYS provide both install and upgrade commands** in documentation
5. ✅ **ALWAYS verify with `--version` after install/upgrade**
6. ❌ **NEVER use `uv tool install --upgrade`** (syntax doesn't exist)
7. ❌ **NEVER use `--prerelease allow`** (wrong context, that's for pip)
8. ❌ **NEVER assume pip is the recommended method** (uv is preferred for this project)

---

## Testing Your Knowledge

### Quiz: Which command is correct?

**Q1**: User wants to install svg2fbf for the first time.
- ❌ `uv tool install --upgrade svg2fbf`
- ✅ `uv tool install svg2fbf`
- ❌ `pip install svg2fbf`

**Q2**: User has svg2fbf 0.1.10 and wants the latest version.
- ❌ `uv tool install --upgrade svg2fbf`
- ✅ `uv tool upgrade svg2fbf`
- ❌ `uv tool install svg2fbf@latest`

**Q3**: User wants to test alpha version 0.1.11a1.
- ❌ `uv tool install svg2fbf --prerelease allow`
- ✅ `uv tool install svg2fbf@0.1.11a1`
- ❌ `uv tool upgrade svg2fbf@0.1.11a1`

**Q4**: User wants to try svg2fbf once without installing.
- ❌ `uv tool install svg2fbf --temporary`
- ✅ `uvx svg2fbf --version`
- ❌ `uv run svg2fbf --version`

All correct answers are marked with ✅.
