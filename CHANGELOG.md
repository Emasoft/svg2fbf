# Changelog

All notable changes to svg2fbf will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.18] - 2026-01-30

### Other

- Merge review into master - ready for stable release

## [0.1.18rc1] - 2026-01-30

### Other

- Merge testing into review - bugs fixed, ready for release candidate
- Release rc 0.1.18rc1

### Miscellaneous

- Update uv.lock for rc 0.1.18rc1

## [0.1.18b1] - 2026-01-30

### Fixed

- Correct stage promotion bump logic in release.sh

### Other

- Merge dev into testing - feature complete, ready for testing
- Merge dev into testing - feature complete, ready for testing
- Release beta 0.1.18b1

### Miscellaneous

- Update uv.lock for beta 0.1.18b1

## [0.1.18a1] - 2026-01-30

### Added

- Implement version release rules enforcement in release.sh

### Other

- Release alpha 0.1.18a1

### Documentation

- Add version release rules documentation and tests

### Miscellaneous

- Enforce GitHub release before PyPI publish
- Update uv.lock
- Update uv.lock for alpha 0.1.18a1

## [0.1.17] - 2026-01-30

### Fixed

- Resolve CLI entry point import error
- Correct CLI entry points for package installation

### Other

- Merge branch 'review'

### Miscellaneous

- Bump version to 0.1.16 for CLI entry point fix

## [0.1.16] - 2026-01-30

### Other

- Release stable 0.1.16

### Miscellaneous

- Update uv.lock for stable 0.1.16

## [0.1.15] - 2026-01-30

### Added

- Make 'just equalize' auto-detect most up-to-date branch [**BREAKING**]
- Improve merge conflict handling in just equalize
- Add comprehensive edge case handling to just equalize
- Add GitHub theme-aware logo display
- Add text-to-path conversion with SVG spec compliance
- Add production-ready text-to-path conversion tool
- Convert all SVG text elements to paths
- Convert remaining SVG text elements to paths
- Add --text2path flag for text-to-path conversion
- Add comprehensive pre-push validation hook

### Fixed

- Correct logo filename in README

### Other

- Release stable 0.1.15

### Changed

- Change equalize to use merge-based promotion chain

### Documentation

- Update equalize command documentation
- Enforce pipeline rule - all PRs must target dev branch
- Add branch protection rules and update PR checklist

### Miscellaneous

- Update uv.lock for stable 0.1.15

## [0.1.14] - 2025-11-18

### Added

- Add generic GitHub branch protection with YAML config [**BREAKING**]

### Fixed

- Improve ccpm/ gitignore pattern

### Other

- Release stable 0.1.14

Includes CCPM cleanup commits that were on dev branch:
- GitHub branch protection configuration
- CCPM plugin separation
- Improved gitignore patterns

### Changed

- Separate CCPM plugin from svg2fbf project

### Documentation

- Add GitHub branch protection guide and setup script

## [0.1.13] - 2025-11-18

### Other

- Release stable 0.1.13

This release corrects a version regression where 0.1.10 was accidentally
published to PyPI after 0.1.12 was already released. This happened due to
git history cleanup that removed local knowledge of versions 0.1.11 and 0.1.12.

Version 0.1.13 is identical to 0.1.12 in functionality, with only version
number changes to restore proper version ordering on PyPI.

## [0.1.12] - 2025-11-17

### Fixed

- Remove empty test.yml workflow causing CI failures

### Other

- Release stable 0.1.12

### Documentation

- Add UV tool management documentation and fix incorrect syntax
- Add comprehensive UV command reference
- Update uv reference in promotion-rules.md
- Replace with concise UV command reference
- Minor clarification in UV reference note
- Fix UV command reference with command-specific options
- Fix incorrect uv syntax in project documentation
- Remove --force flag recommendation (can leave remnants)
- Update GETTING_STARTED.md with correct uv installation

### Miscellaneous

- Update uv.lock for stable 0.1.12

## [0.1.11] - 2025-11-17

### Other

- Release stable 0.1.11

### Miscellaneous

- Update uv.lock for stable 0.1.11

## [0.1.10] - 2025-11-17

### Added

- Split commit porting into two specialized commands
- Add critical hotfix workflow for agents
- Add auto-triage GitHub Actions workflow

### Fixed

- **ui:** Replace duplicate header with import results
- Change splat button animation from loop to ping-pong once

### Other

- Merge dev into testing - feature complete, ready for testing
- Merge testing into review - bugs fixed, ready for release candidate
- Merge review into master - ready for stable release
- Release stable 0.1.10

### Documentation

- **README:** Add FBF.SVG official logo and update .gitignore
- Add comprehensive AI agent workflow documentation
- Add onion skin header image to animation examples
- Correct branch workflow understanding and add hotfix backport

### Miscellaneous

- Update uv.lock for stable 0.1.10

## [0.1.9] - 2025-11-13

### Fixed

- Ensure release notes files are always deleted
- Ensure release script always operates from project root

### Other

- Release stable 0.1.9

### Changed

- Replace wildcard cleanup with explicit file tracking
- Remove trap-based cleanup in favor of explicit manual cleanup

### Miscellaneous

- Ignore temporary release notes files
- Update uv.lock for stable 0.1.9

## [0.1.8] - 2025-11-13

### Other

- Release stable 0.1.8

### Miscellaneous

- Update anime_girl animation to 10 fps and remove broken files
- Update uv.lock for stable 0.1.8

## [0.1.7] - 2025-11-13

### Added

- Add 'just sync_all' command to sync all branches
- Add branch-ahead warning to sync_all command

### Fixed

- Handle Windows Unicode encoding in ppp() function
- Add UTF-8 encoding to subprocess calls in Windows tests
- Use ppp() instead of print() for viewBox error message

### Other

- Release stable 0.1.7

### Changed

- Rename sync_all to equalize for clarity

### Documentation

- Add comprehensive documentation for 'just equalize' command
- Add comprehensive upgrade and uninstall instructions
- Add comprehensive Table of Contents to README
- Add comprehensive Table of Contents to DEVELOPMENT.md and CONTRIBUTING.md

### Miscellaneous

- Update uv.lock for stable 0.1.7

## [0.1.6] - 2025-11-13

### Added

- Add automatic browser opening and change default animation to loop

### Fixed

- Change default animation type from 'once' to 'loop'

### Other

- Release stable 0.1.6

### Miscellaneous

- Update uv.lock for stable 0.1.6

## [0.1.5] - 2025-11-13

### Fixed

- Make CI use project's ruff configuration
- Add critical safety check to prevent RC/beta/alpha from reaching PyPI
- Make MyPy respect pyproject.toml exclusions in CI
- Make CI use project's ruff configuration
- Add critical safety check to prevent RC/beta/alpha from reaching PyPI
- Make MyPy respect pyproject.toml exclusions in CI
- Remove default input_folder to prevent accidental path resolution

### Other

- Merge main: Critical fix for input_folder default value
- Release stable 0.1.5

### Miscellaneous

- Format validation scripts with ruff
- Update uv.lock for stable 0.1.5

## [0.1.4] - 2025-11-13

### Other

- Release stable 0.1.4

### Miscellaneous

- Update uv.lock for stable 0.1.4

## [0.1.3] - 2025-11-13

### Fixed

- Add colored CLI help and fix Python DOM unlink bug

### Other

- Release stable 0.1.3

### Miscellaneous

- Update uv.lock for stable 0.1.3

## [0.1.2] - 2025-11-13

### Added

- Add automated changelog generation with git-cliff
- Add 4-branch release pipeline automation
- Disable CI/CD on dev and testing branches
- Add channel-specific install commands and remove version bumping
- Track dist/ wheels in each branch for direct installation
- Add development build versioning with PEP 440 local identifiers
- Exclude large test data from releases

### Fixed

- Remove auto-version bumping from build commands
- Skip pre-commit hooks in release script

### Other

- Initial commit with all GitHub setup fixes

Fixed all 6 critical issues from GPT-5 analysis:

1. ✅ Entry Points Configuration
   - Removed src. prefix from both entry points
   - Changed: svg2fbf = "src.svg2fbf:cli" → "svg2fbf:cli"
   - Changed: svg-repair-viewbox = "src.svg_viewbox_repair:cli" → "svg_viewbox_repair:cli"
   - Verified: Both commands work correctly after global tool install

2. ✅ Hatch Build Configuration
   - Changed packages = ["src"] → sources = ["src"]
   - Added force-include section for flat layout:
     * src/svg2fbf.py → svg2fbf.py
     * src/svg_viewbox_repair.py → svg_viewbox_repair.py
     * src/auto_install_deps.py → auto_install_deps.py
   - Verified: Wheel builds successfully, modules at root level

3. ✅ Duplicate tomli Dependencies
   - Changed to conditional in dependencies only: tomli>=2.0.0; python_version < '3.11'
   - Removed tomli from dev dependencies entirely
   - Reason: Python 3.11+ has built-in tomllib

4. ✅ TruffleHog Configuration Format
   - Deleted .trufflehog.yaml (wrong YAML format)
   - Using .trufflehog-exclude-paths.txt (correct plain text format)
   - Updated all TruffleHog commands with --exclude-paths flag
   - Updated flags: --results=verified,unknown --fail

5. ✅ Puppeteer/Chrome CI Installation
   - Created separate .github/workflows/e2e.yml for E2E tests
   - Added Chrome installation via browser-actions/setup-chrome@v2
   - Changed to build wheel + global tool install (uv tool install)
   - Set PUPPETEER_SKIP_DOWNLOAD=true
   - Set PUPPETEER_EXECUTABLE_PATH to system Chrome
   - Set NODE_PATH for global module resolution
   - Set CI=true environment variable

6. ✅ CI Workflow Structure
   - quality.yml: Fast quality checks (Ruff + TruffleHog)
   - ci.yml: Basic test suite (cleaned up, no E2E setup)
   - e2e.yml: Comprehensive E2E tests (NEW, separate workflow)
   - All workflows updated with correct TruffleHog flags

Additional Fixes:
- Updated pre-commit Ruff version to v0.14.4
- Reordered pre-commit hooks (ruff before ruff-format)
- Added TruffleHog exclude paths + fallback to pre-commit
- Removed Black from dev dependencies (using Ruff format)

Completion: 17/23 issues fixed (74%), all 6 critical issues resolved (100%)

Documentation:
- docs_dev/COMPLETE_ISSUE_STATUS_2025-11-12.md
- docs_dev/WORKFLOW_SEPARATION_COMPLETE_2025-11-12.md
- docs_dev/GITHUB_SETUP_ANALYSIS.md
- docs_dev/GITHUB_SETUP_ACTION_PLAN.md
- docs_dev/GITHUB_SETUP_QUICK_REF.md

Verification:
- Build: uv build ✅
- Wheel structure: Modules at root level ✅
- Installation: uv tool install dist/svg2fbf-*.whl ✅
- Entry points: svg2fbf --version, svg-repair-viewbox --help ✅
- Git initialized, pre-commit hooks installed ✅

Ready for: GitHub repository creation → CI testing
- Fix e2e.yml: Remove npm cache (no package-lock.json in root)
- Fix 3 critical GitHub workflow configuration errors

This commit resolves all issues that caused workflow failures:

1. TruffleHog --fail flag duplication (quality.yml, ci.yml)
   - TruffleHog GitHub Action automatically adds --fail, --no-update, --github-actions
   - We were duplicating --fail in extra_args, causing "flag cannot be repeated" error
   - Fixed by removing --fail from extra_args in both workflows
   - Added comments explaining automatic flags to prevent future confusion

2. Pre-commit deprecated stage name (.pre-commit-config.yaml)
   - Changed stages: [push] to stages: [pre-push]
   - Fixes deprecation warning from pre-commit
   - Future-proofs hook configuration

3. npm cache issue (e2e.yml) - Already fixed in previous commit
   - Removed cache: "npm" as our package-lock.json is in tests/ not root

Complete analysis and investigation documented in:
docs_dev/FINAL_FIXES_2025-11-12.md

All fixes verified locally. Ready for comprehensive testing before GitHub publication.
- Add missing test session run commands to justfile

Added three new justfile recipes for running test sessions:

1. test-session <id> - Run a specific test session by ID
2. test-rerun - Re-run the most recent test session
3. Fixed test-sessions to use correct path (tests/sessions/)

These commands integrate with the testrunner.py to provide
convenient shortcuts for E2E test execution.

Usage:
  just test-session 14
  just test-rerun
  just test-sessions

Fixes the missing 'just test-e2e' functionality user requested.
- Add test-e2e-all command to run all E2E test sessions

Added new justfile recipe 'test-e2e-all' that:
- Runs all E2E test sessions in sequence
- Shows progress for each session
- Reports summary (passed/failed counts)
- Excludes unit tests (pytest)

This addresses user request for running E2E tests only,
separate from unit tests.

Usage: just test-e2e-all
- Remove /tmp reference for cross-platform compatibility

CRITICAL FIX: Removed hardcoded Unix-specific /tmp path from pytest
configuration to ensure cross-platform compatibility (Windows, macOS,
Linux).

Changes:
- pyproject.toml: Removed --basetemp=/tmp/pytest-svg2fbf
  * pytest now uses system temp directory (tempfile.gettempdir())
  * Added comment explaining cross-platform compatibility

Why this matters:
- /tmp is Unix-specific and doesn't exist on Windows
- Hardcoded paths can be dangerous if variables expand incorrectly
- Using pytest's default temp directory ensures consistent behavior
  across all platforms

Note: scripts_dev/ files also had /tmp references but are gitignored
as development-only tools. Updated them to use tests/temp/ for local
development consistency.
- Fix critical CI failures - repository now GitHub-ready

CRITICAL FIXES for GitHub Actions CI:

1. ci.yml (line 61): Fix MyPy path
   - BEFORE: uv run mypy svg2fbf.py --ignore-missing-imports
   - AFTER:  uv run mypy src/svg2fbf.py --ignore-missing-imports
   - WHY: File is at src/svg2fbf.py, not root - would cause CI to fail

2. tests/conftest.py: Add sys.path setup
   - ADDED: sys.path.insert(0, str(Path(__file__).parent.parent))
   - WHY: Allows pytest to run without PYTHONPATH=. in CI environments
   - IMPACT: Tests can now import 'from tests.utils' without errors

VERIFICATION:
✅ All 75 unit tests PASS without PYTHONPATH
✅ Ruff format --check: 23 files formatted
✅ Ruff check: All checks passed
✅ UV sync: Dependencies resolved
✅ Build: Package built successfully
✅ Twine check: Metadata valid
✅ MyPy: 82 warnings (continue-on-error enabled)

Comprehensive CI simulation completed successfully:
- quality.yml: PASS
- ci.yml lint job: PASS
- ci.yml test job: PASS (75/75 tests)
- ci.yml build job: PASS

Repository is now READY for GitHub publication with zero CI failures.
- "Claude PR Assistant workflow"
- "Claude Code Review workflow"
- Merge pull request #1 from Emasoft/add-claude-github-actions-1763000003542

Add Claude Code GitHub Workflow
- Update funding information in FUNDING.yml
- Fix broken FBF schema diagram link in README

The README was referencing docs/fbf_schema.svg but the actual file
is located at FBF.SVG/fbf_schema.svg. This fix corrects the image
path so the schema diagram displays properly on GitHub.

Changed line 813 from:
  <img src="docs/fbf_schema.svg" ...
To:
  <img src="FBF.SVG/fbf_schema.svg" ...
- Remove nonsensical 'print media' row from comparison table

Animation formats are for displaying animations, not for print media.
This comparison was irrelevant and misleading.
- Remove misleading claims and add video game support

Removed nonsensical claims:
- Removed all "print media" references (animations can't be printed)
- Removed "office software" (PowerPoint/Keynote) claims
- Changed "competitors" to "alternatives"

Added important capabilities:
- Added "Works in video games and console games" row
- FBF.SVG is the ONLY format that works natively in game engines
  (Unity, Godot, Unreal) as texture/sprite sequences
- No other format can work on consoles without web runtime

Other fixes:
- Changed "print" to "games" in platform lists
- Replaced PowerPoint examples with game engine examples
- Made claims more accurate and less hyperbolic
- Add Alembic (.abc) to comparison tables with clarification

Added Alembic to both README and detailed comparison tables to address
common confusion about using it for 2D animation export from OpenToonz.

**What is Alembic?**
- 3D geometry interchange format (stores vertices, transforms, normals)
- Sponsored by Lucasfilm and Sony Pictures Imageworks
- Designed for VFX production pipelines (Maya, Houdini, Blender)
- Open source (BSD license)
- File format: .abc (binary)

**Why include it in comparison?**
Many people suggest using Alembic to export animations from OpenToonz,
but this is a misunderstanding of what Alembic is designed for.

**Why it's NOT an alternative to FBF.SVG:**
- Cannot be played in web browsers (not for web)
- Cannot be played in mobile apps (not for mobile)
- Stores 3D geometry, not 2D vector graphics
- Requires specialized 3D software to view/edit
- Not deployable to end users
- VFX pipeline tool, not animation format for public consumption

**Comparison results:**
- Works in browsers: ❌ NO (3D geometry format)
- Works in mobile: ❌ NO (VFX pipeline format)
- Works in games: ⚠️ PARTIAL (can import .abc as 3D assets, not runtime)
- Video editors: ✅ YES (via 3D render pipeline)
- Interchange format: ✅ YES (that's its primary purpose)

**Clarification added:**
Both tables now include a note explaining that Alembic is NOT a true
alternative to FBF.SVG or other 2D animation formats. It's included
only to clarify why it's the wrong choice for 2D animation deployment.
- Clarify Alembic handles 2D layered scenes with z-depth

Updated Alembic descriptions to acknowledge it can handle 2D layered
scenes (with z-index for parallax scrolling) in addition to 3D, not
just 3D geometry. Emphasized its value for production pipeline
interoperability (OpenToonz ↔ Blender, Maya ↔ Houdini) while
maintaining clarity that it's NOT a standard vector video format
for end-user deployment.
- Emphasize Alembic as scene hierarchy editing format

Clarified key distinction using proper technical terminology:
- Alembic = scene hierarchy EDITING format for production pipelines
- FBF.SVG = vector video OUTPUT format for end-user deployment

These serve different purposes that don't interfere with each other.
Use Alembic for interchange (OpenToonz ↔ Blender ↔ Maya ↔ Houdini).
Use FBF.SVG for deploying to end users (web, mobile, games).
- Update uv.lock after dependency resolution
- Add CCPM as Claude Code plugin with manifest and documentation

Created comprehensive Claude Code plugin structure for CCPM (Claude Code PM):

Plugin Files Added:
- plugin.json - Complete plugin manifest with metadata, commands, agents, rules
- PLUGIN_README.md - Plugin-specific documentation and usage guide
- PLUGIN_INSTALL.md - Detailed installation instructions for plugin version
- Updated main README.md - Added note about plugin availability

Plugin Manifest (plugin.json) Includes:
- 45 registered slash commands (/pm:*, /context:*, /testing:*)
- 4 specialized agents (parallel-worker, test-runner, file-analyzer, code-analyzer)
- 11 operational rules (worktree, github, paths, agent coordination, etc.)
- 17 utility scripts for PM operations
- 1 git hook (bash-worktree-fix)
- Dependency specifications (gh CLI >=2.0.0, git >=2.0.0)
- Installation and configuration details

CCPM Plugin Structure:
- ccpm/plugin.json - Plugin manifest
- ccpm/ccpm/ - Plugin content (.claude directory structure)
  - agents/ - 4 specialized agents
  - commands/ - 45 slash commands (pm, context, testing)
  - rules/ - 11 operational guidelines
  - scripts/ - 17 utility scripts
  - hooks/ - Git workflow enhancements
  - context/ - Context storage
  - epics/ - PM workspace
  - prds/ - PRD storage

Features:
- Spec-driven development workflow (PRD → Epic → Task → Code)
- GitHub Issues integration for team collaboration
- Git worktree isolation for parallel work
- Multi-agent parallel execution
- Context preservation across sessions
- Full traceability from idea to production

Installation:
- Single command: curl -sSL https://automaze.io/ccpm/install | bash
- Or manual: Copy ccpm/* to .claude/ directory
- Then run: /pm:init

Benefits:
- 89% less context switching
- 5-8 parallel tasks vs 1
- 75% reduction in bug rates
- Up to 3x faster feature delivery

License: MIT
Author: Automaze (automazeio)
Homepage: https://github.com/automazeio/ccpm
- Revert "Add CCPM as Claude Code plugin with manifest and documentation"

This reverts commit d0672aa3858d335dd9c47e30d638091e55582067.
- Add ccpm/ to .gitignore (private plugin)
- Fix version detection to use importlib.metadata

- Changed _get_version() to first try importlib.metadata.version()
- This reads from installed package metadata (standard approach)
- Fallback to reading pyproject.toml from parent directory for dev
- Fixes version mismatch: package was 0.1.2a12 but --version showed 0.1.0
- Fixed line length issues in modified section to comply with 88 char limit

Note: Pre-existing E501 errors in other parts of file not addressed in this commit
- Fix version detection and installation instructions

- Version now read from importlib.metadata (package metadata)
- No more hardcoded versions in code
- Fixed README installation to use simple git-based install
- Auto-detects latest version, no manual typing needed
- Verified working: uv tool version shows correct 0.1.2a12

Installation now simple one-liner:
uv tool install git+https://github.com/Emasoft/svg2fbf.git --python 3.10
- Add --version support to svg-repair-viewbox

- Both entry points now show version from package metadata
- svg2fbf --version shows 0.1.2a12
- svg-repair-viewbox --version shows 0.1.2a12
- No more hardcoded versions (0.1.0 is fallback only)
- Add smart version bumping and conditional builds

- 'just build' auto-bumps version (alpha if alpha, patch if stable)
- 'just install' only builds if code changed since last version
- Both commands print version after completion
- Version verification after install
- Clean up version detection (removed debug output)
- Add resilient git hooks system

- Created scripts/hooks/ for version-controlled hooks
- Created scripts/install-hooks.sh to reinstall hooks after .git deletion
- Added 'just install-hooks' command
- Hooks preserved in: scripts/hooks/ and .pre-commit-config.yaml
- Created comprehensive setup guide in scripts/SETUP.md

Now hooks survive .git folder deletion and can be easily reinstalled.
- Merge main into master - Add release pipeline automation
- Merge main: Disable CI on dev/testing + add branch workflow docs
- Merge main: Remove auto-version bumping from build commands
- Merge main: Add channel-specific install commands and remove version bumping
- Add built wheel for main branch (0.1.2a15)
- Merge main: Track dist/ wheels in each branch
- Merge branch 'main'
- Merge branch 'main'
- Release stable 0.1.2
- Add built wheel for stable 0.1.2

### Documentation

- Add comprehensive branch workflow table to DEVELOPMENT.md
- Document test data exclusion from releases
- Emphasize developers must clone repo, recommend gh CLI
- Add branch checkout instructions for gh CLI
- Add 'Clone & Checkout' column to branch workflow table
- Document all gh repo clone syntax formats
- Clarify git branch syntax and update installation commands
- Remove all hardcoded version numbers
- Remove all mentions of obsolete reinstall.sh script

### Miscellaneous

- Update uv.lock for stable 0.1.2

---

## Version History Notes

This project was previously developed privately and is now being prepared for open source release. The version history prior to 0.1.0 is not publicly documented.
