# Contributing to svg2fbf

This document specifies contribution guidelines for the **svg2fbf tool and related implementation components**.

> **📐 Contributing to the FBF.SVG format specification?** See **[CONTRIBUTING_STANDARD.md](CONTRIBUTING_STANDARD.md)** instead.
>
> **📚 For development setup, testing, and building instructions, see [DEVELOPMENT.md](DEVELOPMENT.md).**

---

## Table of Contents

- [Two Types of Contributions](#two-types-of-contributions)
  - [🔧 Tool Development (This Document)](#-tool-development-this-document)
  - [📐 Standard Development](#-standard-development-contributing_standardmd)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
- [Development Workflow](#development-workflow)
  - [Code Style](#code-style)
  - [Testing](#testing)
- [Development Setup (UV-only)](#development-setup-uv-only)
- [Security Practices](#security-practices)
  - [Installing Pre-commit Hooks](#installing-pre-commit-hooks)
  - [Never Commit Secrets](#never-commit-secrets)
  - [TruffleHog Secret Scanning](#trufflehog-secret-scanning)
  - [Allowed Public Information](#allowed-public-information)
  - [Reporting Security Vulnerabilities](#reporting-security-vulnerabilities)
  - [Security Checklist for Contributors](#security-checklist-for-contributors)
- [Submitting Changes](#submitting-changes)
  - [Pull Request Process](#pull-request-process)
  - [Pull Request Guidelines](#pull-request-guidelines)
  - [Commit Message Format](#commit-message-format)
- [AI Agent Contributions](#ai-agent-contributions)
  - [CCPM Plugin Workflow](#ccpm-plugin-workflow)
  - [Agent Permissions](#agent-permissions)
  - [Prohibited Agent Actions](#prohibited-agent-actions)
  - [Protected Files](#protected-files)
- [Reporting Issues](#reporting-issues)
  - [Bug Reports](#bug-reports)
  - [Feature Requests](#feature-requests)
- [Code of Conduct](#code-of-conduct)
  - [Expected Behavior](#expected-behavior)
  - [Prohibited Conduct](#prohibited-conduct)
- [License](#license)
- [Questions and Support](#questions-and-support)

---

## Two Types of Contributions

This project maintains **two distinct contribution tracks**:

### 🔧 Tool Development (This Document)
Contributions to **implementation components**:
- `svg2fbf` converter (Python)
- Streaming server/client implementations
- FBF.SVG player implementations
- Testing and validation tools

**Scope**: Software implementation - code, tests, bug fixes, feature development.

### 📐 Standard Development ([CONTRIBUTING_STANDARD.md](CONTRIBUTING_STANDARD.md))
Contributions to the **FBF.SVG format specification**:
- Specification text and requirements
- Use cases and documentation
- Validation rules and test cases
- W3C standardization process

**Scope**: Standards development - specifications, documentation, formal definitions.

**Contribution Track Selection Criteria**:
- Code implementation or bug fixes → This document (tool development)
- Format specification or requirement definition → [CONTRIBUTING_STANDARD.md](CONTRIBUTING_STANDARD.md) (standard development)

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- [yq](https://github.com/mikefarah/yq) - YAML/JSON/XML processor
- Basic knowledge of SVG and Python

**Installing yq:**
```bash
# macOS
brew install yq

# Linux (download latest binary)
wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/local/bin/yq
chmod +x /usr/local/bin/yq

# Windows (using Chocolatey)
choco install yq

# Or download from: https://github.com/mikefarah/yq/releases
```

For detailed development environment setup, see **[DEVELOPMENT.md](DEVELOPMENT.md)**.

## Development Workflow

### Code Style

This project uses:
- **ruff** for linting and formatting
- **mypy** for type checking

Before submitting changes:

```bash
# Format code
uv run ruff format svg2fbf.py tests/

# Check linting
uv run ruff check svg2fbf.py tests/

# Type checking
uv run mypy svg2fbf.py
```

### Testing

All changes should include appropriate tests:

```bash
# Run all tests
uv run pytest tests/

# Run specific test
uv run pytest tests/test_frame_rendering.py

# Run with coverage
uv run pytest tests/ --cov=svg2fbf
```

## Development Setup (UV-only)

1. Install global tools (one-time):
   ```bash
   uv tool install ruff@latest
   uv tool install trufflehog@latest
   uv tool install pre-commit --with pre-commit-uv
   pre-commit install --hook-type pre-commit --hook-type pre-push
   ```

2. Before pushing your branch:
   ```bash
   ruff format
   ruff check --fix
   trufflehog git file://. --since-commit origin/main --branch HEAD --results=verified,unknown --fail
   ```

3. Inline exceptions:
   - Official TruffleHog: add `# trufflehog:ignore` at end of a known-safe line.
   - If using trufflehog3 (Python): add `# nosecret` or `# nosecret: <rule>`.

## Security Practices

Security is a top priority for svg2fbf. Please follow these guidelines when contributing.

> **📚 For detailed security information, see [SECURITY.md](SECURITY.md).**

### Installing Pre-commit Hooks

**REQUIRED**: Install pre-commit hooks before making any commits:

```bash
# Install pre-commit hooks
pre-commit install

# Test the hooks
pre-commit run --all-files
```

Pre-commit hooks will automatically:
- ✅ Scan for secrets with TruffleHog
- ✅ Check code style with Ruff
- ✅ Run type checks with MyPy
- ✅ Detect private keys and large files
- ✅ Check YAML, JSON, and TOML syntax
- ✅ Prevent commits to protected branches

### Never Commit Secrets

**CRITICAL**: Never commit sensitive information:

❌ **DO NOT commit:**
- API keys, tokens, or passwords
- Private keys or certificates
- Database credentials
- Cloud service credentials
- `.env` files with secrets
- Personal information

✅ **DO use:**
- Environment variables
- `.env` files (gitignored)
- Secrets management tools
- GitHub Secrets for CI/CD

**Example - DON'T:**
```python
API_KEY = "sk_live_1234567890abcdef"  # ❌ NEVER do this!
```

**Example - DO:**
```python
import os
API_KEY = os.environ.get("API_KEY")  # ✅ Good practice
```

### TruffleHog Secret Scanning

All commits are automatically scanned for secrets:

- **Pre-commit**: TruffleHog runs locally before each commit
- **CI/CD**: GitHub Actions scans all pushes and PRs
- **Configuration**: See `.trufflehog.yaml` for allowlist

If TruffleHog detects a secret:
1. **DO NOT force-commit** the secret
2. Remove the secret from your code
3. Use environment variables instead
4. If already committed, see [Removing Secrets from Git History](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

### Allowed Public Information

These values are **safe to commit** (configured in `.trufflehog.yaml`):

- GitHub Username: `Emasoft`
- GitHub No-Reply Email: `713559+Emasoft@users.noreply.github.com`
- Repository URL: `https://github.com/Emasoft/svg2fbf`
- Package Name: `svg2fbf`

### Reporting Security Vulnerabilities

**DO NOT** report security vulnerabilities in public issues!

Instead:
1. Go to [Security tab](https://github.com/Emasoft/svg2fbf/security)
2. Click "Report a vulnerability"
3. Or email: 713559+Emasoft@users.noreply.github.com

See [SECURITY.md](SECURITY.md) for full details.

### Security Checklist for Contributors

Before submitting a PR, verify:

- [ ] No hardcoded secrets or credentials
- [ ] No sensitive information in commit messages
- [ ] All tests pass (including security checks)
- [ ] Pre-commit hooks are installed and passing
- [ ] No large files or binaries committed
- [ ] `.gitignore` properly configured
- [ ] Environment variables used for configuration

## Version Release Rules

The project enforces strict version progression rules to maintain a clean release history. **A version can only exist in ONE stage at any time.**

### Branch-Stage Mapping

| Branch   | Stage  | Publishes to |
|----------|--------|--------------|
| dev      | alpha  | GitHub only  |
| testing  | beta   | GitHub only  |
| review   | rc     | GitHub only  |
| master   | stable | GitHub + PyPI|

### Progression Rules

1. **Single Stage Rule**: Only ONE stage per version (no 0.1.2a AND 0.1.2b)
2. **Stage Progression Rule**: Stage must be LOWER than previous version's stage
3. **RC Gateway Rule**: Alpha/beta of next version only if previous reached RC or stable

For detailed rules and examples, see **[CLAUDE.md](CLAUDE.md#version-release-rules-critical)**.

### Release Workflow

```bash
# Promote through branches
just promote-to-testing    # dev → testing
just promote-to-review     # testing → review
just promote-to-stable     # review → master

# Create releases
just release               # GitHub only (all channels)
just publish               # GitHub + PyPI (stable to PyPI)
```

---

## Submitting Changes

### Pull Request Process

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following the code style guidelines
3. **Add tests** for new functionality
4. **Update documentation** if needed
5. **Run tests and linting** to ensure everything passes
6. **Submit a pull request** with a clear description of changes

### Pull Request Guidelines

- Keep changes focused and atomic
- Write clear commit messages
- Update README.md if adding user-facing features
- Add entry to CHANGELOG.md for notable changes

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style/formatting
- `refactor`: Code refactoring
- `test`: Test additions/changes
- `chore`: Build/tooling changes

Example:
```
feat: Add support for gradient optimization

Implement gradient deduplication to reduce file size.
Adds new function detect_duplicate_gradients() and tests.

Closes #123
```

## AI Agent Contributions

> **⚠️ EXPERIMENTAL**: AI agent workflow is in early development (Phase 1). This section documents current practices and safeguards.

AI agents can contribute to svg2fbf through the **CCPM (Controlled Concurrent Project Management)** plugin, which provides worktree-based issue isolation with comprehensive safety mechanisms.

### CCPM Plugin Workflow

**IMPORTANT**: The CCPM plugin is **local-only** (not committed to the repository). If you're an AI agent or working with AI agents:

1. **Read the skills documentation** (located in `ccpm/skills/`):
   - `5-branch-workflow.md` - Branch hierarchy and permissions
   - `promotion-rules.md` - How code moves through the pipeline
   - `release-process.md` - Release system (observation only)
   - `recovery-procedures.md` - Error recovery procedures

2. **Use isolated worktrees** for all work:
   ```bash
   # Start work on an issue
   ./ccpm/commands/issue-start.sh <issue-number> dev

   # Check status
   ./ccpm/commands/issue-status.sh

   # Finish and create PR
   ./ccpm/commands/issue-finish.sh <issue-number>

   # Abort if needed
   ./ccpm/commands/issue-abort.sh <issue-number>
   ```

3. **Quality checks are mandatory**:
   - Pre-flight checks validate preconditions before starting
   - Pre-commit hooks block protected file modifications
   - Post-flight checks ensure quality before PR creation

4. **All actions are logged** to `~/.cache/svg2fbf-audit-logs/` for accountability

### Agent Permissions

**Allowed branches** (agents may work here):
- ✅ `dev` - Primary development branch
- ✅ `testing` - Bug fixes and QA
- ⚠️ `hotfix/*` - Critical fixes (supervised only)

**Forbidden branches** (agents must NOT work here):
- ❌ `review` - Release candidates (human-supervised only)
- ❌ `master` - Stable releases (humans only)
- ❌ `main` - Protected default branch (read-only mirror)

**Allowed operations**:
- Create feature branches from `dev`
- Commit code following conventional commit format
- Run tests, linting, and formatting
- Create Draft PRs
- Request human review

### Prohibited Agent Actions

**NEVER do these (safeguards will block)**:

1. ❌ **Modify protected files**:
   - `justfile`, `scripts/release.sh`, `cliff.toml`
   - `.github/workflows/*` (CI/CD pipelines)
   - `CHANGELOG.md` (auto-generated)
   - `pyproject.toml` (except dependencies with approval)

2. ❌ **Run dangerous commands**:
   - `just equalize` (force-syncs all branches)
   - `just publish` (triggers releases)
   - `git push --force` (rewrites history)

3. ❌ **Bypass safeguards**:
   - Merge own PRs
   - Skip promotion stages (must go dev→testing→review→master)
   - Work on multiple issues in same worktree
   - Commit without running quality checks

4. ❌ **Access production branches**:
   - Never checkout `master` or `main` directly
   - Never push to `review`, `master`, or `main`

### Protected Files

The following files are **strictly off-limits** for AI agents (enforced by pre-commit hook):

**Build & Release Infrastructure**:
- `justfile` - Build commands and workflows
- `scripts/release.sh` - Release automation
- `cliff.toml` - Changelog configuration

**CI/CD**:
- `.github/workflows/*` - All GitHub Actions workflows

**Auto-Generated**:
- `CHANGELOG.md` - Generated by git-cliff
- `.release-notes-*.md` - Temporary release files

**Configuration**:
- `pyproject.toml` - Project metadata (except dependencies with review)

**Security**:
- `.github/SECURITY.md` - Security policy

**CCPM Plugin** (self-preservation):
- `ccpm/**/*` - Plugin code, skills, hooks, rules

### Recovery from Mistakes

If an agent makes a mistake, see `ccpm/skills/recovery-procedures.md` for detailed recovery steps covering:
- Broke tests on dev
- Pushed to wrong branch
- Modified protected files
- Lost commits
- Merge conflicts
- CI failures
- And more...

**Human escalation required** for:
- Pushed to `master` or `main` by mistake
- Modified `CHANGELOG.md` or `justfile`
- Triggered `just publish` or `just equalize`
- Git corruption detected
- CI failing on `review`/`master` for >1 hour

### Audit Trail

All agent actions are logged to `~/.cache/svg2fbf-audit-logs/YYYY-MM-DD.json` with:
- Timestamp and agent ID
- Action type (commit, push, PR create, etc.)
- Files modified
- Branch and commit information

This audit trail ensures accountability and aids in debugging issues.

---

## Reporting Issues

### Bug Reports

Include:
- SVG2FBF version
- Python version
- Operating system
- Minimal reproduction example
- Expected vs actual behavior
- Error messages and stack traces

### Feature Requests

Include:
- Clear description of the feature
- Use cases and benefits
- Possible implementation approach (if you have ideas)

## Code of Conduct

### Expected Behavior

- Maintain professional and inclusive communication
- Accept constructive feedback with professionalism
- Prioritize community interests over individual preferences
- Demonstrate respect for diverse perspectives and expertise

### Prohibited Conduct

- Harassment, discrimination, or deliberately disruptive behavior
- Unauthorized disclosure of private information
- Conduct inconsistent with professional collaborative environments

## License

By contributing to svg2fbf, you agree that your contributions will be licensed under the Apache License 2.0.

## Questions and Support

Open an issue for:
- Contribution process clarifications
- Development environment setup assistance
- Feature proposal discussions

Contributions to svg2fbf advance the FBF.SVG ecosystem and are valued by the community.
