# svg2fbf Release Workflow

Complete guide for the svg2fbf development and release pipeline.

## Branch Strategy

svg2fbf uses a **4-stage development pipeline** with corresponding release channels:

```
dev      → alpha    (Development: new features/patches)
  ↓
testing  → beta     (Testing: bug fixes/debugging)
  ↓
review   → rc       (Review: release candidate)
  ↓
master   → stable   (Production: stable release + PyPI)
  ↓
main     (Mirror)   (Auto-synced with master for GitHub default branch)
```

### Branch Purposes

| Branch   | Purpose                          | Release Channel | Published To      |
|----------|----------------------------------|-----------------|-------------------|
| `dev`    | Active development               | alpha           | GitHub only       |
| `testing`| Beta testing and debugging       | beta            | GitHub only       |
| `review` | Release candidate review         | rc              | GitHub only       |
| `master` | Production-ready stable releases | stable          | GitHub + PyPI     |
| `main`   | Mirror of master (GitHub default)| (none)          | Auto-synced       |

**Note:** The `main` branch is automatically synced with `master` after every stable release. This provides redundancy and keeps GitHub's default branch up to date.

## Development Workflow

### 1. Development Phase (dev branch)

Work on new features and patches:

```bash
git checkout dev
# ... make changes, commit, test ...
git push origin dev
```

**Note:** CI/CD is **disabled** on `dev` branch. Developers manually decide when to run tests and checks.

When feature is complete and ready for testing:
```bash
just promote-to-testing
```

This will:
- ✓ Verify branches exist
- ✓ Check for uncommitted changes
- ✓ Checkout `testing` branch
- ✓ Pull latest from origin
- ✓ Merge `dev` into `testing` (with --no-ff)
- ✓ Push to origin
- ✓ Return to your original branch

### 2. Testing Phase (testing branch)

Testers work with the `testing` branch to find and report bugs.

Developers fix bugs on `testing`:
```bash
git checkout testing
# ... fix bugs, commit, test ...
git push origin testing
```

**Note:** CI/CD is **disabled** on `testing` branch. Tests are expected to fail here - that's the point! Only when all tests pass should you promote to review.

When all bugs are fixed and ready for review:
```bash
just promote-to-review
```

### 3. Review Phase (review branch)

Final review before stable release:
```bash
git checkout review
# ... final checks, documentation review ...
```

**Note:** CI/CD is **enabled** on `review` branch. All tests must pass before merging to master.

When review is approved and ready for production:
```bash
just promote-to-stable
```

### 4. Stable Release (master branch)

The `master` branch contains production-ready code.

**Note:** CI/CD is **enabled** on `master` and `main` branches. All checks must pass.

## CI/CD Behavior by Branch

Understanding when automated checks run:

| Branch   | CI/CD Status | Pre-commit Hooks | Rationale                                    |
|----------|--------------|------------------|----------------------------------------------|
| `dev`    | **Disabled** | Manual           | Active development, expected breakage        |
| `testing`| **Disabled** | Manual           | Bug hunting, tests expected to fail          |
| `review` | **Enabled**  | Available        | Final QA, must be stable before release      |
| `master` | **Enabled**  | Available        | Production code, strict enforcement          |
| `main`   | **Enabled**  | Available        | Mirror of master, strict enforcement         |

**Why disable CI on dev/testing?**
- `dev`: Developers iterate quickly, breakage is normal
- `testing`: Purpose is to find bugs - tests should fail!
- Manual testing: Developers run `just test`, `just lint` when ready
- Promotion gates: `review` and `master` enforce all checks

**Manual Testing on dev/testing:**
```bash
# When you want to check your work on dev/testing:
just test          # Run tests
just lint          # Check linting
just check         # Run all checks
```

## Release Process

### Quick Release Commands

**Simplest way to release:**

```bash
# Release pre-release channels only (GitHub releases, no PyPI)
just release

# Release all channels + publish stable to PyPI
just publish
```

That's it! No need to remember branch names or flags. ✨

### Creating Releases (Detailed)

#### One-Command Releases (Recommended)

```bash
# Release alpha, beta, rc to GitHub (no PyPI)
just release

# Release alpha, beta, rc, stable to GitHub + publish stable to PyPI
just publish
```

**What happens:**
- `just release`: Creates GitHub releases for all 4 branches (alpha, beta, rc, stable) **without PyPI**
- `just publish`: Same as `release` but **publishes stable to PyPI** ✨

#### Manual Release Script Usage

For more control, use the `scripts/release.sh` script directly:

**Individual Channel Release:**

```bash
# Alpha release from dev
./scripts/release.sh --alpha dev

# Beta release from testing
./scripts/release.sh --beta testing

# RC release from review
./scripts/release.sh --rc review

# Stable release from master (publishes to PyPI)
./scripts/release.sh --stable master
```

**Full Pipeline Release:**

Release all channels at once:
```bash
./scripts/release.sh --alpha dev --beta testing --rc review --stable master
```

This will:
1. Create alpha release from `dev` (e.g., `v0.1.3a1`)
2. Create beta release from `testing` (e.g., `v0.1.3b1`)
3. Create rc release from `review` (e.g., `v0.1.3rc1`)
4. Create stable release from `master` (e.g., `v0.1.3`) and **publish to PyPI**

### What the Release Script Does

For each channel, the script:

1. **Checkout** the branch
2. **Sync check** - ensures branch is up to date with origin
3. **Clean check** - ensures no uncommitted changes
4. **Version bump** - automatically bumps version:
   - `alpha`: `0.1.2` → `0.1.3a1` or `0.1.2a1` → `0.1.2a2`
   - `beta`: `0.1.2` → `0.1.3b1` or `0.1.2b1` → `0.1.2b2`
   - `rc`: `0.1.2` → `0.1.3rc1` or `0.1.2rc1` → `0.1.2rc2`
   - `stable`: `0.1.2rc1` → `0.1.2` or `0.1.2` → `0.1.3`
5. **Changelog** - regenerates CHANGELOG.md with git-cliff
6. **Commit** - commits version bump + changelog
7. **Build** - builds wheel and sdist with `uv build`
8. **Tag** - creates git tag (e.g., `v0.1.3`)
9. **Push** - pushes branch and tag to origin
10. **GitHub Release** - creates GitHub release (pre-release for alpha/beta/rc)
11. **PyPI Publish** - publishes to PyPI (**stable only**)

### Release Notes

Release notes are automatically generated from git commit history using git-cliff.

**Important:** Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```bash
# Good commit messages
git commit -m "feat: Add new SVG optimization algorithm"
git commit -m "fix: Resolve viewBox calculation bug"
git commit -m "docs: Update installation instructions"

# Bad commit messages
git commit -m "updates"
git commit -m "fix stuff"
```

Commit types:
- `feat:` - New features → "Added" section
- `fix:` - Bug fixes → "Fixed" section
- `perf:` - Performance improvements → "Performance" section
- `refactor:` - Code refactoring → "Changed" section
- `docs:` - Documentation → "Documentation" section
- `chore:` - Maintenance tasks → "Miscellaneous" section

## Complete Workflow Example

### Scenario: Adding a new feature

```bash
# 1. Start development
git checkout dev
git pull origin dev

# 2. Implement feature
git commit -m "feat: Add SVG compression support"
git push origin dev

# 3. Feature complete → move to testing
just promote-to-testing
# Output: ✅ Successfully promoted dev → testing

# 4. Testing discovers bugs
git checkout testing
git commit -m "fix: Handle empty SVG elements in compression"
git push origin testing

# 5. Bugs fixed → move to review
just promote-to-review
# Output: ✅ Successfully promoted testing → review

# 6. Review approved → move to stable
just promote-to-stable
# Output: ✅ Successfully promoted review → master

# 7. Create releases and publish to PyPI
just publish

# This creates:
# - v0.1.3a1 from dev (GitHub release)
# - v0.1.3b1 from testing (GitHub release)
# - v0.1.3rc1 from review (GitHub release)
# - v0.1.3 from master (GitHub release + PyPI) ✨
```

### Quick Development Cycle (Pre-releases only)

If you want to create pre-release versions without publishing to PyPI:

```bash
# Work on dev, testing, review branches...

# Create alpha, beta, rc releases on GitHub (no PyPI)
just release

# This creates:
# - v0.1.3a1 from dev (GitHub release)
# - v0.1.3b1 from testing (GitHub release)
# - v0.1.3rc1 from review (GitHub release)
# No PyPI publish - perfect for testing releases!
```

## Version Numbering

svg2fbf follows [Semantic Versioning](https://semver.org/) with pre-release identifiers:

- **Alpha**: `0.1.3a1`, `0.1.3a2`, ... (early development)
- **Beta**: `0.1.3b1`, `0.1.3b2`, ... (testing phase)
- **RC**: `0.1.3rc1`, `0.1.3rc2`, ... (release candidate)
- **Stable**: `0.1.3` (production release)

### Version Bumping Rules

The release script automatically bumps versions:

| Current Version | Channel | Next Version | Rule                          |
|-----------------|---------|--------------|-------------------------------|
| `0.1.2`         | alpha   | `0.1.3a1`    | Bump patch + add alpha        |
| `0.1.2a1`       | alpha   | `0.1.2a2`    | Bump alpha counter            |
| `0.1.2`         | beta    | `0.1.3b1`    | Bump patch + add beta         |
| `0.1.2b1`       | beta    | `0.1.2b2`    | Bump beta counter             |
| `0.1.2`         | rc      | `0.1.3rc1`   | Bump patch + add rc           |
| `0.1.2rc1`      | rc      | `0.1.2rc2`   | Bump rc counter               |
| `0.1.2rc1`      | stable  | `0.1.2`      | Remove pre-release identifier |
| `0.1.2`         | stable  | `0.1.3`      | Bump patch                    |

## Prerequisites

### Required Tools

```bash
# uv - Python package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# gh - GitHub CLI
brew install gh  # or: https://cli.github.com/
gh auth login

# git-cliff - Changelog generator
cargo install git-cliff  # or: brew install git-cliff

# just - Task runner
brew install just  # or: cargo install just
```

### Environment Variables

For stable releases (PyPI publishing):
```bash
# Export PyPI token
export UV_PUBLISH_TOKEN="pypi-XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

Get token from: https://pypi.org/manage/account/token/

### Branch Setup

Create the 4-branch structure (first time only):
```bash
# Create branches from main/master
git branch dev main
git branch testing main
git branch review main
git branch master main  # if not exists

# Push all branches
git push origin dev testing review master
```

## Safety Features

Both promote commands and release script have safety checks:

### Promote Commands

- ✓ Verify branches exist
- ✓ Check for uncommitted changes
- ✓ Pull latest from origin before merging
- ✓ Use `--no-ff` for clear merge commits
- ✓ Return to original branch after completion

### Release Script

- ✓ Verify tools installed (uv, gh, git-cliff)
- ✓ Prevent same branch on multiple channels
- ✓ Ensure branch synced with origin
- ✓ Check working tree is clean
- ✓ Auto-restore original branch on error (cleanup trap)
- ✓ Require UV_PUBLISH_TOKEN for stable releases

## Troubleshooting

### "Branch not in sync with origin"

```bash
git pull origin <branch>
# or if you want to overwrite local
git reset --hard origin/<branch>
```

### "Uncommitted changes"

```bash
# Commit changes
git add .
git commit -m "fix: your message"

# Or stash temporarily
git stash
# ... run command ...
git stash pop
```

### Release script fails mid-execution

The script has a cleanup trap that restores your original branch on error. If you still end up on wrong branch:

```bash
git checkout main  # or your original branch
```

### PyPI publish fails

Check UV_PUBLISH_TOKEN is set:
```bash
echo $UV_PUBLISH_TOKEN
```

If empty, export it:
```bash
export UV_PUBLISH_TOKEN="pypi-XXXXXXXXXXXX"
```

### Want to skip PyPI publish for testing

Use a non-stable channel:
```bash
# These DON'T publish to PyPI
./scripts/release.sh --alpha dev
./scripts/release.sh --beta testing
./scripts/release.sh --rc review
```

### Main branch out of sync with master

The `main` branch is automatically synced after stable releases, but if you need to manually sync:

```bash
just sync-main
```

This ensures `main` is identical to `master`.

## Quick Reference

### Promote Commands

```bash
just promote-to-testing   # dev → testing
just promote-to-review    # testing → review
just promote-to-stable    # review → master
just sync-main            # Sync main with master (manual)
```

### Release Commands

```bash
# Individual releases
./scripts/release.sh --alpha dev
./scripts/release.sh --beta testing
./scripts/release.sh --rc review
./scripts/release.sh --stable master

# Full pipeline
./scripts/release.sh --alpha dev --beta testing --rc review --stable master
```

### Other Useful Commands

```bash
just --list              # Show all available commands
just build               # Build wheel (NO version bump)
just install             # Install as uv tool
just changelog           # Generate CHANGELOG.md
just version             # Show current version
git cliff --unreleased   # Preview unreleased changes
```

**Note:** Version bumping is handled exclusively by the release pipeline (`just release` or `just publish`).

## Best Practices

1. **Work on dev** - All new development starts on `dev` branch
2. **Test thoroughly** - Use `testing` branch for comprehensive testing
3. **Review carefully** - Use `review` for final checks before release
4. **Keep master clean** - Only promote reviewed, tested code to `master`
5. **Use conventional commits** - Ensures good changelog generation
6. **Release all channels** - Run full pipeline to keep versions consistent
7. **Version in git** - Never manually edit version in pyproject.toml, let the script handle it

## Support

For issues or questions:
- GitHub Issues: https://github.com/Emasoft/svg2fbf/issues
- Review this guide: `docs/RELEASE_WORKFLOW.md`
- Check justfile help: `just --list`
- Release script help: `./scripts/release.sh --help`
