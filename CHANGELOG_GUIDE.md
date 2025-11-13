# Changelog Management Guide

This project uses [git-cliff](https://git-cliff.org/) to automatically generate the CHANGELOG.md from git commit history.

## Quick Start

```bash
# Generate/update CHANGELOG.md
just changelog

# Preview changes without writing
just changelog-preview

# View unreleased changes only
just changelog-unreleased
```

## How It Works

git-cliff reads your git commit history and generates a formatted CHANGELOG.md following the [Keep a Changelog](https://keepachangelog.com/) format.

### Commit Message Format

For best changelog generation, use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

[optional body]

[optional footer]
```

### Recognized Types

Commits are automatically grouped by type:

| Type | Section | Example |
|------|---------|---------|
| `feat:` | **Added** | `feat: Add dark mode support` |
| `add:` | **Added** | `add: New export format` |
| `fix:` | **Fixed** | `fix: Correct viewBox calculation` |
| `bug:` | **Fixed** | `bug: Handle edge case in parser` |
| `perf:` | **Performance** | `perf: Optimize gradient processing` |
| `refactor:` | **Changed** | `refactor: Simplify transform logic` |
| `change:` | **Changed** | `change: Update API response format` |
| `update:` | **Changed** | `update: Migrate to new library` |
| `style:` | **Styling** | `style: Format code with ruff` |
| `test:` | **Testing** | `test: Add integration tests` |
| `doc:` / `docs:` | **Documentation** | `docs: Update installation guide` |
| `chore:` | **Miscellaneous** | `chore: Update dependencies` |
| `ci:` | **CI/CD** | `ci: Add coverage reporting` |
| `build:` | **Build** | `build: Configure production build` |
| `revert:` | **Reverted** | `revert: Undo breaking change` |

### Breaking Changes

Mark breaking changes with `BREAKING:` or `!`:

```bash
# With footer
feat: Add new API endpoint

BREAKING: Old API endpoint removed

# With ! in type
feat!: Change authentication method
```

Breaking changes will be marked with **[BREAKING]** in the changelog.

## Commands

### Generate Changelog

```bash
# Update CHANGELOG.md from all commits
just changelog
```

This:
1. Reads git history from all tags and commits
2. Groups commits by type
3. Formats according to Keep a Changelog
4. Writes to CHANGELOG.md

### Preview Changelog

```bash
# See what the changelog would look like
just changelog-preview
```

Useful for checking before committing.

### Unreleased Changes

```bash
# Show only commits since last tag
just changelog-unreleased
```

Useful for seeing what will be in the next release.

### Generate for Specific Tag

```bash
# Generate changelog up to a specific tag
just changelog-tag v0.2.0
```

### Create Release

```bash
# Full release workflow
just release v0.2.0
```

This:
1. Generates changelog with the new version
2. Commits CHANGELOG.md
3. Creates git tag
4. Prints push instructions

Example output:
```
🚀 Preparing release v0.2.0...

1. Updating CHANGELOG.md...
✅ CHANGELOG.md updated

2. Committing changelog...
[main abc1234] chore(release): update CHANGELOG for v0.2.0

3. Creating git tag...
✅ Tag v0.2.0 created

To push:
  git push origin main
  git push origin v0.2.0
```

## Configuration

Configuration is in `cliff.toml`. Key settings:

### Header & Footer

```toml
[changelog]
header = """
# Changelog
All notable changes...
"""
footer = """
---
Version history notes...
"""
```

### Commit Parsers

```toml
[git]
commit_parsers = [
    { message = "^feat", group = "Added" },
    { message = "^fix", group = "Fixed" },
    # ...
]
```

### Issue Links

Automatically converts issue numbers to links:

```toml
commit_preprocessors = [
    { pattern = '\((\w+\s)?#([0-9]+)\)',
      replace = "([#${2}](https://github.com/Emasoft/svg2fbf/issues/${2}))" },
]
```

Example:
```
fix(parser): Handle edge case (#123)
```
Becomes:
```
fix(parser): Handle edge case ([#123](https://github.com/Emasoft/svg2fbf/issues/123))
```

## Best Practices

### 1. Use Conventional Commits

```bash
# ✅ Good
git commit -m "feat: Add SVG animation support"
git commit -m "fix: Correct gradient rendering"

# ❌ Bad
git commit -m "Added stuff"
git commit -m "WIP"
```

### 2. Write Descriptive Messages

```bash
# ✅ Good
feat: Add support for nested SVG groups

This allows processing of complex SVG structures with
multiple nested <g> elements while preserving hierarchy.

# ❌ Bad
feat: Add thing
```

### 3. Group Related Changes

```bash
# Multiple small commits for same feature
feat: Add animation parser
feat: Add animation renderer
docs: Document animation API

# These will all appear in "Added" section
```

### 4. Update Changelog Before Releases

```bash
# Before creating a release
just changelog
git add CHANGELOG.md
git commit -m "docs: Update CHANGELOG for v0.2.0"

# Then tag
git tag v0.2.0
```

### 5. Use Scopes for Clarity

```bash
feat(parser): Add XML namespace support
fix(renderer): Correct z-index calculation
perf(optimizer): Cache gradient lookups
```

Scopes appear in changelog:
```
### Added
- **parser:** Add XML namespace support

### Fixed
- **renderer:** Correct z-index calculation
```

## Examples

### Example Commit History

```bash
git commit -m "feat: Add YAML configuration support"
git commit -m "feat: Add command-line options"
git commit -m "fix: Handle missing viewBox attribute"
git commit -m "docs: Update README with examples"
git commit -m "test: Add integration tests"
git commit -m "refactor: Simplify path optimization"
```

### Generated Changelog

```markdown
## [0.2.0] - 2025-01-13

### Added
- Add YAML configuration support
- Add command-line options

### Fixed
- Handle missing viewBox attribute

### Changed
- Simplify path optimization

### Documentation
- Update README with examples

### Testing
- Add integration tests
```

## Troubleshooting

### Issue: Commits not appearing in changelog

**Solution:** Check commit message format. Use conventional commit prefixes.

```bash
# This won't appear properly
git commit -m "Added new feature"

# Use this instead
git commit -m "feat: Add new feature"
```

### Issue: Wrong grouping

**Solution:** Check the type prefix matches cliff.toml patterns.

```bash
# Will be grouped as "Other"
git commit -m "added: New feature"

# Use this (lowercase)
git commit -m "feat: Add new feature"
```

### Issue: Breaking changes not marked

**Solution:** Use `BREAKING:` footer or `!` in type.

```bash
# Correct way
feat!: Change API response format

# Or with footer
feat: Change API response format

BREAKING: Old format no longer supported
```

### Issue: Need to skip commits

**Solution:** Use `[skip ci]` or patterns in cliff.toml.

```bash
# Won't appear in changelog
git commit -m "chore(deps): Update dependencies"
git commit -m "chore(pr): Merge pull request"
```

## Integration with Workflow

### Development Flow

```bash
# 1. Make changes
vim src/svg2fbf.py

# 2. Commit with conventional format
git commit -m "feat: Add gradient optimization"

# 3. Preview what changelog will look like
just changelog-preview

# 4. Continue developing...
```

### Release Flow

```bash
# 1. Update changelog
just changelog

# 2. Review CHANGELOG.md
cat CHANGELOG.md

# 3. Commit changelog
git add CHANGELOG.md
git commit -m "docs: Update CHANGELOG for v0.2.0"

# 4. Create release
git tag v0.2.0
git push origin main
git push origin v0.2.0

# Or use automated release:
just release v0.2.0
```

### CI/CD Integration

Consider adding to CI:

```yaml
# .github/workflows/release.yml
- name: Generate Changelog
  run: |
    just changelog
    git diff CHANGELOG.md
```

## References

- [git-cliff documentation](https://git-cliff.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Semantic Versioning](https://semver.org/)

## Summary

| Command | Description |
|---------|-------------|
| `just changelog` | Generate/update CHANGELOG.md |
| `just changelog-preview` | Preview without writing |
| `just changelog-unreleased` | Show unreleased changes |
| `just changelog-tag v0.2.0` | Generate for specific tag |
| `just release v0.2.0` | Full release workflow |

**Key Points:**
- Use conventional commit messages
- `feat:` → Added, `fix:` → Fixed, `docs:` → Documentation
- Mark breaking changes with `BREAKING:` or `!`
- Update changelog before releases
- Configuration in `cliff.toml`
