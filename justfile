# svg2fbf Development Tasks
# =========================
# Cross-platform task runner using Just (https://github.com/casey/just)
#
# Installation:
#   macOS/Linux:  curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin
#   Windows:      winget install --id Casey.Just
#   Or via package managers: brew install just, cargo install just, etc.
#
# Usage:
#   just --list                  # Show all available commands
#   just add                     # Add and sync dependencies
#   just add-dev                 # Add dev dependencies and sync
#   just remove                  # Remove and sync dependencies
#   just build                   # Build wheel (NO version bump)
#   just install                 # Install current wheel from dist/
#   just install-alpha           # Install alpha from GitHub (dev branch)
#   just install-beta            # Install beta from GitHub (testing branch)
#   just install-rc              # Install rc from GitHub (review branch)
#   just install-stable          # Install stable from GitHub (master branch)
#   just reinstall               # Full rebuild and reinstall (NO version bump)
#   just promote-to-testing      # Merge dev → testing (feature complete)
#   just promote-to-review       # Merge testing → review (bugs fixed)
#   just promote-to-stable       # Merge review → master (ready for release)
#   just sync-main               # Sync main branch with master (keep identical)
#   just equalize                # Equalize all branches from current branch (with confirmation)
#   just release                 # Release all 4 channels to GitHub (no PyPI)
#   just publish                 # Release all + publish stable to PyPI
#   just changelog               # Generate/update CHANGELOG.md from git history
#   just release-tag <version>   # Manually create release tag (e.g., v1.0.0)
#   just clean                   # Clean temp directories
#   just test                    # Run tests

# Default recipe (runs when you just type "just")
default:
    @just --list

# ============================================================================
# Dependency Management
# ============================================================================

# Sync all dependencies (runtime + dev) without installing svg2fbf in venv
sync:
    @echo "📦 Syncing dependencies..."
    uv sync --no-install-project --quiet
    @echo "✅ Dependencies synced"
    @echo ""
    @echo "Verify svg2fbf not in venv:"
    @uv pip list | grep svg2fbf || echo "✓ svg2fbf not in venv (correct)"

# Sync only development dependencies
sync-dev:
    @echo "📦 Syncing dev dependencies only..."
    uv sync --no-install-project --only-dev --quiet
    @echo "✅ Dev dependencies synced"
    @echo "Verify svg2fbf not in venv:"
    @uv pip list | grep svg2fbf || echo "✓ svg2fbf not in venv (correct)"

# Sync only runtime dependencies
sync-runtime:
    @echo "📦 Syncing runtime dependencies only..."
    uv sync --no-install-project --no-dev --quiet
    @echo "✅ Runtime dependencies synced"
    @echo "Verify svg2fbf not in venv:"
    @uv pip list | grep svg2fbf || echo "✓ svg2fbf not in venv (correct)"

# Add a runtime dependency
add pkg:
    @echo "➕ Adding dependency: {{pkg}}"
    uv add {{pkg}} --no-sync
    @echo "✅ Added to pyproject.toml"
    @echo ""
    @echo "📦 Syncing dependencies..."
    uv sync --no-install-project --quiet
    @echo "✅ Dependencies synced"
    @echo ""
    @echo "Verify svg2fbf not in venv:"
    @uv pip list | grep svg2fbf || echo "✓ svg2fbf not in venv (correct)"

# Add a development dependency
add-dev pkg:
    @echo "➕ Adding dev dependency: {{pkg}}"
    uv add --dev {{pkg}} --no-sync
    @echo "✅ Added to pyproject.toml"
    @echo ""
    @echo "📦 Syncing dev dependencies only..."
    uv sync --no-install-project --only-dev --quiet
    @echo "✅ Dev dependencies synced"
    @echo "Verify svg2fbf not in venv:"
    @uv pip list | grep svg2fbf || echo "✓ svg2fbf not in venv (correct)"
    
# Remove a dependency
remove pkg:
    @echo "➖ Removing dependency: {{pkg}}"
    uv remove {{pkg}} --no-sync
    @echo "✅ Removed from pyproject.toml"
    @echo ""
    @echo "📦 Syncing dependencies..."
    uv sync --no-install-project --quiet
    @echo "✅ Dependencies synced"
    @echo ""
    @echo "Verify svg2fbf not in venv:"
    @uv pip list | grep svg2fbf || echo "✓ svg2fbf not in venv (correct)"


# ============================================================================
# Build & Install
# ============================================================================

# Build wheel package (NO version bump - versions only bumped during releases)
# Adds +dev.{git_hash} suffix to distinguish development builds from releases
build:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🔨 Building development wheel..."

    # Get current version
    BASE_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

    # Get short git hash for local version identifier
    GIT_HASH=$(git rev-parse --short HEAD)

    # Create local version: version+dev.hash (PEP 440 compliant)
    DEV_VERSION="${BASE_VERSION}+dev.${GIT_HASH}"

    echo "Base version: $BASE_VERSION"
    echo "Dev version:  $DEV_VERSION"
    echo ""

    # Temporarily update version in pyproject.toml
    sed -i.bak "s/^version = \".*\"/version = \"${DEV_VERSION}\"/" pyproject.toml

    # Build wheel with dev version
    echo "🔨 Building wheel..."
    uv build --wheel --quiet --out-dir dist

    # Restore original version
    mv pyproject.toml.bak pyproject.toml

    echo "✅ Development wheel built:"
    ls -t dist/svg2fbf-*+dev.*.whl | head -1
    echo ""
    echo "📦 Development version: $DEV_VERSION"
    echo ""
    echo "Note: This is a development build with +dev.${GIT_HASH} suffix."
    echo "      Release versions (clean, no suffix) are created by 'just release' or 'just publish'."

# Install current wheel as uv tool (installs existing wheel from dist/)
# Works with both development wheels (+dev.hash) and release wheels (clean)
install python="3.10":
    #!/usr/bin/env bash
    set -euo pipefail

    echo "📥 Installing current wheel as uv tool..."
    echo ""

    # Find latest wheel by modification time (most recently created)
    WHEEL=$(ls -t dist/svg2fbf-*.whl 2>/dev/null | head -1)

    if [ -z "$WHEEL" ]; then
        echo "❌ Error: No wheel found in dist/"
        echo "Run 'just build' first to create a wheel"
        exit 1
    fi

    # Get version from wheel filename (handles both +dev.hash and clean versions)
    WHEEL_VERSION=$(basename "$WHEEL" | sed 's/svg2fbf-\(.*\)-py3.*/\1/')
    echo "Found wheel: $WHEEL_VERSION"

    # Check if it's a development build
    if [[ "$WHEEL_VERSION" == *"+dev."* ]]; then
        echo "Type: Development build"
    else
        echo "Type: Release build"
    fi
    echo ""

    # Uninstall existing
    echo "🗑️  Uninstalling existing tool..."
    uv tool uninstall svg2fbf 2>/dev/null || true

    # Install
    echo "📦 Installing: $WHEEL"
    uv tool install "$WHEEL" --python {{python}}

    echo ""
    echo "✅ Installation complete!"
    echo ""
    echo "Commands available:"
    echo "  - svg2fbf"
    echo "  - svg-repair-viewbox"
    echo ""
    echo "📦 Verifying installation..."
    INSTALLED_VERSION=$(~/.local/share/uv/tools/svg2fbf/bin/svg2fbf --version 2>/dev/null || echo "ERROR")
    if [ "$INSTALLED_VERSION" = "ERROR" ]; then
        echo "⚠️  Could not verify installation"
    else
        echo "✅ Installed version: $INSTALLED_VERSION"
    fi

# Install alpha release from GitHub
install-alpha python="3.10":
    @echo "📥 Installing latest alpha release from GitHub..."
    @echo ""
    uv tool install git+https://github.com/Emasoft/svg2fbf.git@dev --python {{python}}
    @echo ""
    @echo "✅ Alpha version installed!"
    @svg2fbf --version

# Install beta release from GitHub
install-beta python="3.10":
    @echo "📥 Installing latest beta release from GitHub..."
    @echo ""
    uv tool install git+https://github.com/Emasoft/svg2fbf.git@testing --python {{python}}
    @echo ""
    @echo "✅ Beta version installed!"
    @svg2fbf --version

# Install rc release from GitHub
install-rc python="3.10":
    @echo "📥 Installing latest rc release from GitHub..."
    @echo ""
    uv tool install git+https://github.com/Emasoft/svg2fbf.git@review --python {{python}}
    @echo ""
    @echo "✅ RC version installed!"
    @svg2fbf --version

# Install stable release from GitHub
install-stable python="3.10":
    @echo "📥 Installing latest stable release from GitHub..."
    @echo ""
    uv tool install git+https://github.com/Emasoft/svg2fbf.git@master --python {{python}}
    @echo ""
    @echo "✅ Stable version installed!"
    @svg2fbf --version

# Full rebuild and reinstall (cleans, builds, installs - NO version bump)
reinstall python="3.10":
    @echo "🔄 Full reinstall (clean build + install)..."
    @echo ""
    @echo "Note: This does NOT bump version. Use 'just publish' for releases."
    @echo ""
    just clean-build
    @echo ""
    just sync
    @echo ""
    just build
    @echo ""
    just install {{python}}
    @echo ""
    @echo "✅ Reinstall complete!"
    @echo "Test with: svg2fbf --version"

# ============================================================================
# Testing
# ============================================================================

# Run all tests
test:
    @echo "🧪 Running tests..."
    pytest

# Run tests with coverage
test-cov:
    @echo "🧪 Running tests with coverage..."
    pytest --cov=src --cov-report=html --cov-report=term

# Run specific test file
test-file file:
    @echo "🧪 Running test file: {{file}}"
    pytest {{file}}

# Run tests matching a pattern
test-match pattern:
    @echo "🧪 Running tests matching: {{pattern}}"
    pytest -k "{{pattern}}"

# List all available tests
test-list:
    @echo "📋 Available tests:"
    @pytest --collect-only -q

# List tests in specific file
test-list-file file:
    @echo "📋 Tests in {{file}}:"
    @pytest {{file}} --collect-only -q

# Show test results from last run
test-report:
    @echo "📊 Opening last test report..."
    @if [ -f htmlcov/index.html ]; then \
        open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || echo "Report: htmlcov/index.html"; \
    else \
        echo "No coverage report found. Run 'just test-cov' first."; \
    fi

# Run tests verbosely with output
test-verbose:
    @echo "🧪 Running tests (verbose)..."
    pytest -v -s

# Run failed tests from last run
test-failed:
    @echo "🧪 Re-running failed tests..."
    pytest --lf

# ============================================================================
# Test Session Management
# ============================================================================

# Create a new test session from SVG directory
test-create name svg_dir:
    @echo "🆕 Creating test session: {{name}}"
    @echo "   Source: {{svg_dir}}"
    @python3 -c "from pathlib import Path; from src.testrunner import create_session; create_session(Path('{{svg_dir}}'), session_name='{{name}}', verbose=True)"

# List all test sessions
test-sessions:
    @echo "📋 Listing all test sessions..."
    PYTHONPATH=. uv run python tests/testrunner.py list

# Run a specific test session by ID
test-session session_id:
    @echo "🧪 Running test session {{session_id}}..."
    PYTHONPATH=. uv run python tests/testrunner.py run {{session_id}}

# Run ALL E2E test sessions (excludes unit tests)
test-e2e-all:
    #!/usr/bin/env python3
    from pathlib import Path
    import subprocess
    import json

    sessions_dir = Path("tests/sessions")
    if not sessions_dir.exists():
        print("❌ No test sessions found")
        exit(1)

    # Get all test session folders
    sessions = sorted([d for d in sessions_dir.iterdir()
                      if d.is_dir() and d.name.startswith("test_session_")])

    if not sessions:
        print("❌ No test sessions found")
        exit(1)

    print(f"🚀 Running {len(sessions)} E2E test sessions...\n")

    passed = 0
    failed = 0
    for i, session in enumerate(sessions, 1):
        # Extract session ID (e.g., "test_session_014_35frames" -> "14")
        session_id = session.name.split("_")[2]

        print(f"[{i}/{len(sessions)}] Running session {session_id} ({session.name})...")

        result = subprocess.run(
            ["env", "PYTHONPATH=.", "uv", "run", "python", "tests/testrunner.py", "run", session_id],
            capture_output=True
        )

        if result.returncode == 0:
            passed += 1
            print(f"   ✅ PASSED\n")
        else:
            failed += 1
            print(f"   ❌ FAILED\n")

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(sessions)} total")
    print("=" * 70)

    if failed > 0:
        exit(1)

# Run the most recent test session (convenience shortcut)
test-rerun:
    #!/usr/bin/env python3
    from pathlib import Path
    import subprocess
    import json

    sessions_dir = Path("tests/sessions")
    if not sessions_dir.exists():
        print("❌ No test sessions found")
        exit(1)

    # Get all session folders (test_session_NNN_Nframes format)
    sessions = sorted([d for d in sessions_dir.iterdir()
                      if d.is_dir() and d.name.startswith("test_session_")],
                     key=lambda x: x.stat().st_mtime, reverse=True)

    if not sessions:
        print("❌ No test sessions found")
        exit(1)

    latest_session = sessions[0].name
    # Extract session ID (e.g., "test_session_014_35frames" -> "14")
    session_id = latest_session.split("_")[2]

    print(f"🔄 Re-running latest test session: {session_id} ({latest_session})")
    subprocess.run(["env", "PYTHONPATH=.", "uv", "run", "python", "tests/testrunner.py", "run", session_id])

# Create random test session from examples directory
random-test n:
    @echo "🎲 Creating random test session with {{n}} frames from examples/"
    @python3 tests/testrunner.py create --random {{n}} -- examples/

# Create random test session from W3C SVG 1.1 Test Suite
test-random-w3c count:
    @echo "🎲 Creating random test session with {{count}} frames from W3C SVG 1.1 Test Suite"
    uv run python tests/testrunner.py create --random {{count}} -- "FBF.SVG/SVG 1.1 W3C Test Suit/w3c_50frames/"

# Show detailed info for a test session
test-info session_id:
    #!/usr/bin/env python3
    from pathlib import Path
    import json

    session_dir = Path("tests/results") / "{{session_id}}"
    if not session_dir.exists():
        print(f"❌ Test session not found: {{session_id}}")
        print(f"   Path: {session_dir}")
        exit(1)

    metadata_file = session_dir / "metadata.json"
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())
        print(f"📊 Test Session: {{session_id}}")
        print("=" * 70)
        for key, value in metadata.items():
            print(f"  {key}: {value}")
        print("=" * 70)
    else:
        print(f"📊 Test Session: {{session_id}}")
        print(f"Path: {session_dir}")
        print("(No metadata.json found)")

# Delete a test session
test-delete session_id:
    #!/usr/bin/env python3
    from pathlib import Path
    import shutil

    session_dir = Path("tests/results") / "{{session_id}}"
    if not session_dir.exists():
        print(f"❌ Test session not found: {{session_id}}")
        exit(1)

    print(f"🗑️  Deleting test session: {{session_id}}")
    print(f"   Path: {session_dir}")

    try:
        shutil.rmtree(session_dir)
        print(f"✅ Deleted: {{session_id}}")
    except Exception as e:
        print(f"❌ Failed to delete: {e}")
        exit(1)

# Clean all test sessions
test-clean-all:
    #!/usr/bin/env python3
    from pathlib import Path
    import shutil

    results_dir = Path("tests/results")
    if not results_dir.exists():
        print("No test sessions to clean")
    else:
        sessions = [d for d in results_dir.iterdir() if d.is_dir()]
        if not sessions:
            print("No test sessions to clean")
        else:
            print(f"🧹 Cleaning {len(sessions)} test session(s)...")
            for session in sessions:
                try:
                    shutil.rmtree(session)
                    print(f"  ✓ Removed: {session.name}")
                except Exception as e:
                    print(f"  ✗ Failed: {session.name}: {e}")

# ============================================================================
# SVG Utilities
# ============================================================================

# Repair viewBox attributes in SVG files
svg-repair path:
    @echo "🔧 Repairing viewBox attributes..."
    @echo "   Path: {{path}}"
    svg-repair-viewbox {{path}}

# Repair viewBox (quiet mode)
svg-repair-quiet path:
    @echo "🔧 Repairing viewBox (quiet)..."
    svg-repair-viewbox --quiet {{path}}

# Compare two FBF.SVG files
svg-compare file1 file2:
    #!/usr/bin/env python3
    from pathlib import Path
    import sys

    file1 = Path("{{file1}}")
    file2 = Path("{{file2}}")

    if not file1.exists():
        print(f"❌ File not found: {file1}")
        sys.exit(1)
    if not file2.exists():
        print(f"❌ File not found: {file2}")
        sys.exit(1)

    print(f"🔍 Comparing FBF.SVG files:")
    print(f"   File 1: {file1}")
    print(f"   File 2: {file2}")
    print()

    # Read both files
    content1 = file1.read_text()
    content2 = file2.read_text()

    # Basic comparison
    if content1 == content2:
        print("✅ Files are identical")
    else:
        print("❌ Files differ")
        print()

        # Show file sizes
        print(f"File 1 size: {len(content1)} bytes")
        print(f"File 2 size: {len(content2)} bytes")
        print()

        # Show line counts
        lines1 = content1.split('\n')
        lines2 = content2.split('\n')
        print(f"File 1 lines: {len(lines1)}")
        print(f"File 2 lines: {len(lines2)}")

        # Detailed diff using difflib
        import difflib
        diff = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=str(file1),
            tofile=str(file2),
            lineterm=''
        ))

        if diff:
            print()
            print("Differences (first 50 lines):")
            print("=" * 70)
            for line in diff[:50]:
                print(line)
            if len(diff) > 50:
                print(f"... and {len(diff) - 50} more lines")

# Validate SVG file structure
svg-validate file:
    #!/usr/bin/env python3
    from pathlib import Path
    from lxml import etree
    import sys

    svg_file = Path("{{file}}")
    if not svg_file.exists():
        print(f"❌ File not found: {svg_file}")
        sys.exit(1)

    print(f"🔍 Validating SVG: {svg_file.name}")
    print()

    try:
        tree = etree.parse(str(svg_file))
        root = tree.getroot()

        # Check namespace
        if 'svg' not in root.tag.lower():
            print("⚠️  Warning: Root element is not <svg>")
        else:
            print("✓ Valid SVG root element")

        # Check viewBox
        viewbox = root.get('viewBox')
        if viewbox:
            print(f"✓ Has viewBox: {viewbox}")
        else:
            print("⚠️  No viewBox attribute")

        # Check width/height
        width = root.get('width')
        height = root.get('height')
        if width and height:
            print(f"✓ Has dimensions: {width} x {height}")
        else:
            print("⚠️  No width/height attributes")

        # Count child elements
        children = len(root)
        print(f"✓ Child elements: {children}")

        # Check for animation elements
        animations = tree.findall('.//*[@class="fbf-frame"]')
        if animations:
            print(f"✓ FBF frames found: {len(animations)}")

        print()
        print("✅ SVG is well-formed")

    except etree.XMLSyntaxError as e:
        print(f"❌ XML Syntax Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

# Show SVG file info
svg-info file:
    #!/usr/bin/env python3
    from pathlib import Path
    from lxml import etree
    import sys

    svg_file = Path("{{file}}")
    if not svg_file.exists():
        print(f"❌ File not found: {svg_file}")
        sys.exit(1)

    print(f"📊 SVG File Info: {svg_file.name}")
    print("=" * 70)

    # File stats
    print(f"Path: {svg_file}")
    print(f"Size: {svg_file.stat().st_size:,} bytes")
    print()

    try:
        tree = etree.parse(str(svg_file))
        root = tree.getroot()

        # Attributes
        print("Attributes:")
        for attr, value in root.attrib.items():
            print(f"  {attr}: {value}")
        print()

        # Count elements by type
        print("Element counts:")
        elements = {}
        for elem in tree.iter():
            tag = elem.tag.split('}')[-1]  # Remove namespace
            elements[tag] = elements.get(tag, 0) + 1

        for tag, count in sorted(elements.items(), key=lambda x: -x[1])[:10]:
            print(f"  {tag}: {count}")

        if len(elements) > 10:
            print(f"  ... and {len(elements) - 10} more element types")

    except Exception as e:
        print(f"❌ Error reading SVG: {e}")

# ============================================================================
# Code Quality
# ============================================================================

# Format code with ruff
fmt:
    @echo "✨ Formatting code..."
    uv run ruff format src/ tests/

# Lint code with ruff
lint:
    @echo "🔍 Linting code..."
    uv run ruff check src/ tests/

# Fix linting issues
lint-fix:
    @echo "🔧 Fixing linting issues..."
    uv run ruff check --fix src/ tests/

# Type check with mypy (DISABLED - not in use)
# typecheck:
#     @echo "🔍 Type checking..."
#     uv run mypy src/

# Run all quality checks
check:
    @echo "🔍 Running all quality checks..."
    @echo ""
    just lint
    @echo ""
    # just typecheck  # Disabled - mypy not in use
    @echo ""
    just fmt
    @echo ""
    @echo "✅ All checks passed!"

# Full validation (same as pre-push hook) - lint, format, tests, secrets
validate:
    @./scripts/validate.sh

# Quick validation (skip tests) - lint, format, secrets only
validate-quick:
    @./scripts/validate.sh --quick

# ============================================================================
# Cleanup
# ============================================================================

# Clean temp directories
clean-temp pattern="temp_*":
    #!/usr/bin/env python3
    import shutil
    from pathlib import Path

    pattern = "{{pattern}}"
    cwd = Path.cwd()
    temp_dirs = list(cwd.glob(pattern))

    if not temp_dirs:
        print(f"No temp directories found matching: {pattern}")
    else:
        print(f"🧹 Cleaning up temp directories: {pattern}")
        for temp_dir in temp_dirs:
            if temp_dir.is_dir():
                try:
                    shutil.rmtree(temp_dir)
                    print(f"✓ Removed: {temp_dir.name}")
                except Exception as e:
                    print(f"✗ Failed: {temp_dir.name}: {e}")
        print(f"Cleaned up {len(temp_dirs)} directories")

# Clean build artifacts
clean-build:
    @echo "🧹 Cleaning build artifacts..."
    rm -rf build/ dist/ *.egg-info .eggs/
    @echo "✅ Build artifacts cleaned"

# Clean Python cache files
clean-cache:
    @echo "🧹 Cleaning Python cache..."
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete
    @echo "✅ Cache cleaned"

# Clean everything (temp, build, cache)
clean-all:
    @echo "🧹 Cleaning everything..."
    @echo ""
    just clean-temp
    @echo ""
    just clean-build
    @echo ""
    just clean-cache
    @echo ""
    @echo "✅ All cleaned!"

# ============================================================================
# Git Hooks
# ============================================================================

# Install git hooks (pre-commit + custom hooks from scripts/hooks/)
install-hooks:
    @echo "🔗 Installing git hooks..."
    @./scripts/install-hooks.sh

# ============================================================================
# Branch Promotion (Development Pipeline)
# ============================================================================
# Development workflow: dev → testing → review → master
# Each command merges and pushes to the next stage in the pipeline

# Promote dev branch to testing (feature complete, ready for testing)
promote-to-testing:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🚀 Promoting dev → testing"
    echo ""

    # Save current branch
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    # Ensure dev and testing branches exist
    if ! git show-ref --verify --quiet refs/heads/dev; then
        echo "❌ Error: 'dev' branch does not exist" >&2
        exit 1
    fi
    if ! git show-ref --verify --quiet refs/heads/testing; then
        echo "❌ Error: 'testing' branch does not exist" >&2
        exit 1
    fi

    # Check for uncommitted changes
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "❌ Error: You have uncommitted changes. Please commit or stash them first." >&2
        exit 1
    fi

    echo "1. Checking out testing branch..."
    git checkout testing

    echo "2. Pulling latest from origin/testing..."
    git pull origin testing

    echo "3. Merging dev into testing..."
    git merge dev --no-ff -m "Merge dev into testing - feature complete, ready for testing"

    echo "4. Pushing to origin/testing..."
    git push origin testing

    echo "5. Returning to $ORIGINAL_BRANCH..."
    git checkout "$ORIGINAL_BRANCH"

    echo ""
    echo "✅ Successfully promoted dev → testing"
    echo ""
    echo "Next steps:"
    echo "  - Test the 'testing' branch thoroughly"
    echo "  - When bugs are fixed, run: just promote-to-review"

# Promote testing branch to review (bugs fixed, ready for RC)
promote-to-review:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🚀 Promoting testing → review"
    echo ""

    # Save current branch
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    # Ensure testing and review branches exist
    if ! git show-ref --verify --quiet refs/heads/testing; then
        echo "❌ Error: 'testing' branch does not exist" >&2
        exit 1
    fi
    if ! git show-ref --verify --quiet refs/heads/review; then
        echo "❌ Error: 'review' branch does not exist" >&2
        exit 1
    fi

    # Check for uncommitted changes
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "❌ Error: You have uncommitted changes. Please commit or stash them first." >&2
        exit 1
    fi

    echo "1. Checking out review branch..."
    git checkout review

    echo "2. Pulling latest from origin/review..."
    git pull origin review

    echo "3. Merging testing into review..."
    git merge testing --no-ff -m "Merge testing into review - bugs fixed, ready for release candidate"

    echo "4. Pushing to origin/review..."
    git push origin review

    echo "5. Returning to $ORIGINAL_BRANCH..."
    git checkout "$ORIGINAL_BRANCH"

    echo ""
    echo "✅ Successfully promoted testing → review"
    echo ""
    echo "Next steps:"
    echo "  - Review the 'review' branch for final approval"
    echo "  - When approved, run: just promote-to-stable"

# Promote review branch to master (review passed, ready for stable release)
promote-to-stable:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🚀 Promoting review → master"
    echo ""

    # Save current branch
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    # Ensure review and master branches exist
    if ! git show-ref --verify --quiet refs/heads/review; then
        echo "❌ Error: 'review' branch does not exist" >&2
        exit 1
    fi
    if ! git show-ref --verify --quiet refs/heads/master; then
        echo "❌ Error: 'master' branch does not exist" >&2
        exit 1
    fi

    # Check for uncommitted changes
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "❌ Error: You have uncommitted changes. Please commit or stash them first." >&2
        exit 1
    fi

    echo "1. Checking out master branch..."
    git checkout master

    echo "2. Pulling latest from origin/master..."
    git pull origin master

    echo "3. Merging review into master..."
    git merge review --no-ff -m "Merge review into master - ready for stable release"

    echo "4. Pushing to origin/master..."
    git push origin master

    echo "5. Returning to $ORIGINAL_BRANCH..."
    git checkout "$ORIGINAL_BRANCH"

    echo ""
    echo "✅ Successfully promoted review → master"
    echo ""
    echo "Next steps:"
    echo "  - Run releases: ./scripts/release.sh --stable master"
    echo "  - Or full pipeline: ./scripts/release.sh --alpha dev --beta testing --rc review --stable master"

# Sync main branch with master (keeps them identical)
sync-main:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🔄 Syncing master → main..."
    echo ""
    echo "This will make main identical to master."
    echo ""

    # Save current branch
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    # Fetch latest
    git fetch origin master main

    # Checkout main
    git checkout main

    # Reset main to match master exactly
    git reset --hard master

    # Push to origin (force with lease for safety)
    git push origin main --force-with-lease

    # Return to original branch
    git checkout "$ORIGINAL_BRANCH"

    echo ""
    echo "✅ main is now synced with master"
    echo "   (main and master are identical)"

# Equalize all branches using promotion chain (dev→testing→review→master→main)
equalize:
    #!/usr/bin/env bash
    set -euo pipefail

    # Verify we're in a git repository
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        echo "❌ Error: Not a git repository" >&2
        exit 1
    fi

    # Get current branch for later restoration
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    # Check for detached HEAD state
    if [ "$ORIGINAL_BRANCH" = "HEAD" ]; then
        echo "❌ Error: You are in a detached HEAD state" >&2
        echo "   Please checkout a branch first with: git checkout <branch-name>" >&2
        exit 1
    fi

    # Check for uncommitted changes in current branch
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo "⚠️  Warning: You have uncommitted changes on branch: $ORIGINAL_BRANCH"
        echo ""
        git status --short
        echo ""
        echo "It's recommended to commit or stash changes before equalizing."
        read -p "Continue anyway? (yes/no): " -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo "❌ Equalize cancelled"
            exit 0
        fi
    fi

    # Check for active worktrees that might have uncommitted changes
    if command -v git worktree >/dev/null 2>&1; then
        WORKTREE_COUNT=$(git worktree list | wc -l)
        if [ "$WORKTREE_COUNT" -gt 1 ]; then
            echo "⚠️  Warning: Multiple git worktrees detected ($WORKTREE_COUNT worktrees)"
            echo "   Make sure all worktrees have committed their changes before equalizing."
            echo ""
            git worktree list
            echo ""
            read -p "Continue anyway? (yes/no): " -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                echo "❌ Equalize cancelled"
                exit 0
            fi
        fi
    fi

    # Define promotion chain: dev → testing → review → master → main
    PROMOTION_CHAIN=("dev" "testing" "review" "master" "main")

    echo "🔄 Equalize All Branches (Promotion Chain)"
    echo "═══════════════════════════════════════════════"
    echo ""

    # Check if there's an ongoing merge from a previous run
    if [ -f .git/MERGE_HEAD ]; then
        echo "⚠️  ONGOING MERGE DETECTED!"
        echo ""
        echo "There is an unfinished merge in progress on branch: $ORIGINAL_BRANCH"
        echo ""

        # Check if there are unresolved conflicts
        if git diff --name-only --diff-filter=U | grep -q .; then
            echo "❌ You still have unresolved merge conflicts:"
            git diff --name-only --diff-filter=U | sed 's/^/  - /'
            echo ""
            echo "Please resolve the conflicts first, then run 'just equalize' again."
            echo ""
            echo "To resolve:"
            echo "  1. Edit the conflicted files"
            echo "  2. git add <resolved-files>"
            echo "  3. git commit"
            echo "  4. git push origin $ORIGINAL_BRANCH"
            echo "  5. just equalize"
            exit 1
        else
            echo "✅ Conflicts appear to be resolved, but merge not committed yet."
            echo ""
            echo "Please complete the merge:"
            echo "  1. git commit"
            echo "  2. git push origin $ORIGINAL_BRANCH"
            echo "  3. just equalize"
            exit 1
        fi
    fi

    echo "Promotion flow: dev → testing → review → master → main"
    echo ""

    # Fetch latest from all remotes with error handling
    echo "📡 Fetching latest from remote..."
    if ! git fetch --all --quiet; then
        echo "⚠️  Warning: Could not fetch from remote (network issue or no remote configured)" >&2
        echo "   Continuing with local branches only..." >&2
        echo ""
    else
        echo ""
    fi

    # Show current status of all branches
    echo "📊 Current branch status:"
    for branch in "${PROMOTION_CHAIN[@]}"; do
        if git show-ref --verify --quiet "refs/heads/$branch"; then
            LATEST_COMMIT=$(git log --oneline -1 "$branch")
            echo "  $branch: $LATEST_COMMIT"
        else
            echo "  $branch: ❌ does not exist"
        fi
    done
    echo ""

    echo "⚠️  WARNING: This will merge through the promotion chain!"
    echo "   Each branch will be merged into the next: dev→testing→review→master→main"
    echo "   Merge conflicts will abort the process."
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "❌ Equalize cancelled"
        git checkout "$ORIGINAL_BRANCH" 2>/dev/null || true
        exit 0
    fi

    echo "🚀 Starting promotion chain merge..."
    echo ""

    # Iterate through promotion chain: merge each branch into the next
    for i in {0..3}; do
        SOURCE_BRANCH="${PROMOTION_CHAIN[$i]}"
        TARGET_BRANCH="${PROMOTION_CHAIN[$i+1]}"

        echo "📤 Promoting: $SOURCE_BRANCH → $TARGET_BRANCH"

        # Verify source branch exists
        if ! git show-ref --verify --quiet "refs/heads/$SOURCE_BRANCH"; then
            echo "  ❌ Error: Source branch '$SOURCE_BRANCH' does not exist" >&2
            git checkout "$ORIGINAL_BRANCH" 2>/dev/null || true
            exit 1
        fi

        # Verify target branch exists
        if ! git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
            echo "  ❌ Error: Target branch '$TARGET_BRANCH' does not exist" >&2
            git checkout "$ORIGINAL_BRANCH" 2>/dev/null || true
            exit 1
        fi

        # Checkout target branch
        git checkout "$TARGET_BRANCH"

        # Check if merge is needed
        if git merge-base --is-ancestor "$SOURCE_BRANCH" "$TARGET_BRANCH"; then
            echo "  ⏭️  Already up to date (no merge needed)"
        else
            # Attempt merge
            if git merge "$SOURCE_BRANCH" --no-edit -m "chore: Merge $SOURCE_BRANCH into $TARGET_BRANCH (equalize)"; then
                echo "  ✅ Merge successful"

                # Push to remote with error handling
                if git push origin "$TARGET_BRANCH"; then
                    echo "  ✅ Pushed to remote"
                else
                    echo "  ⚠️  Warning: Failed to push to remote" >&2
                    echo "     You may need to push manually later: git push origin $TARGET_BRANCH" >&2
                    echo "     Continuing with local merges..." >&2
                fi
            else
                # Merge conflict detected
                echo ""
                echo "═══════════════════════════════════════════════════════════════"
                echo "❌ MERGE CONFLICT DETECTED!"
                echo "═══════════════════════════════════════════════════════════════"
                echo ""
                echo "Conflict occurred when merging:"
                echo "  Source: $SOURCE_BRANCH"
                echo "  Target: $TARGET_BRANCH (current branch)"
                echo ""

                # Show conflicted files
                echo "📁 Conflicted files:"
                git diff --name-only --diff-filter=U | sed 's/^/  - /'
                echo ""

                echo "🔧 To resolve the conflicts:"
                echo ""
                echo "  1. Open the conflicted files listed above"
                echo "  2. Look for conflict markers: <<<<<<< HEAD, =======, >>>>>>>"
                echo "  3. Edit the files to resolve the conflicts"
                echo "  4. Remove the conflict markers"
                echo "  5. Test your changes if needed"
                echo ""
                echo "  6. Stage the resolved files:"
                echo "     git add <resolved-files>"
                echo ""
                echo "  7. Complete the merge:"
                echo "     git commit -m \"chore: Merge $SOURCE_BRANCH into $TARGET_BRANCH (equalize)\""
                echo ""
                echo "  8. Push the merge:"
                echo "     git push origin $TARGET_BRANCH"
                echo ""
                echo "  9. Resume equalize to continue the promotion chain:"
                echo "     just equalize"
                echo ""
                echo "═══════════════════════════════════════════════════════════════"
                echo ""
                echo "⚠️  You are currently on branch: $TARGET_BRANCH"
                echo "   The merge is in progress. Resolve conflicts before switching branches."
                echo ""
                exit 1
            fi
        fi
        echo ""
    done

    # Return to original branch
    echo "🔙 Returning to $ORIGINAL_BRANCH..."
    git checkout "$ORIGINAL_BRANCH"

    echo ""
    echo "✅ All branches equalized successfully!"
    echo ""
    echo "Promotion chain complete: dev → testing → review → master → main"

# Backport hotfix from master/main to current dev/testing/review branch (interactive, safe)
backport-hotfix:
    #!/usr/bin/env bash
    set -euo pipefail

    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    echo "🔄 Backport Hotfix from master/main"
    echo "═══════════════════════════════════════════════"
    echo ""
    echo "Current branch: $CURRENT_BRANCH"
    echo ""

    # Validate current branch is dev, testing, or review
    if [[ ! "$CURRENT_BRANCH" =~ ^(dev|testing|review)$ ]]; then
        echo "❌ Error: Can only backport to dev, testing, or review branches"
        echo "Current branch: $CURRENT_BRANCH"
        echo ""
        echo "Usage: git checkout dev && just backport-hotfix"
        exit 1
    fi

    # Determine which stable branch to source from (prefer main, fallback to master)
    if git rev-parse --verify main >/dev/null 2>&1; then
        SOURCE_BRANCH="main"
    elif git rev-parse --verify master >/dev/null 2>&1; then
        SOURCE_BRANCH="master"
    else
        echo "❌ Error: Cannot find main or master branch"
        exit 1
    fi

    echo "Source branch: $SOURCE_BRANCH"
    echo ""

    # Fetch latest
    git fetch origin "$SOURCE_BRANCH" --quiet

    # Find commits in source that are NOT in current branch
    echo "🔍 Finding commits in $SOURCE_BRANCH not in $CURRENT_BRANCH..."
    echo ""

    # Get list of commits
    COMMITS=$(git log --oneline "$CURRENT_BRANCH..$SOURCE_BRANCH" --no-merges)

    if [ -z "$COMMITS" ]; then
        echo "✅ No commits to backport - $CURRENT_BRANCH is up to date with $SOURCE_BRANCH"
        exit 0
    fi

    echo "Commits available for backport:"
    echo ""
    git log --oneline --no-merges "$CURRENT_BRANCH..$SOURCE_BRANCH" | nl -w2 -s". "
    echo ""

    # Ask user to select a commit
    read -p "Enter commit number to backport (or 'q' to quit): " -r
    echo ""

    if [[ $REPLY == "q" ]]; then
        echo "❌ Backport cancelled"
        exit 0
    fi

    # Get the selected commit hash
    COMMIT_HASH=$(git log --oneline --no-merges "$CURRENT_BRANCH..$SOURCE_BRANCH" | sed -n "${REPLY}p" | awk '{print $1}')

    if [ -z "$COMMIT_HASH" ]; then
        echo "❌ Error: Invalid selection"
        exit 1
    fi

    # Get commit details
    COMMIT_MESSAGE=$(git log -1 --pretty=format:"%s" "$COMMIT_HASH")
    COMMIT_AUTHOR=$(git log -1 --pretty=format:"%an" "$COMMIT_HASH")
    COMMIT_DATE=$(git log -1 --pretty=format:"%ad" --date=short "$COMMIT_HASH")

    echo "Selected Commit:"
    echo "  Hash: $COMMIT_HASH"
    echo "  Message: $COMMIT_MESSAGE"
    echo "  Author: $COMMIT_AUTHOR"
    echo "  Date: $COMMIT_DATE"
    echo ""

    # Check if commit already exists (by checking commit message and author)
    if git log --all --pretty=format:"%s|%an" | grep -q "^${COMMIT_MESSAGE}|${COMMIT_AUTHOR}$"; then
        echo "⚠️  WARNING: A commit with same message and author already exists in $CURRENT_BRANCH"
        echo "This might be a duplicate. Continue anyway?"
        read -p "(yes/no): " -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo "❌ Backport cancelled"
            exit 0
        fi
    fi

    # Show what files would be affected
    echo "📁 Files that would be changed:"
    git diff --name-only "$CURRENT_BRANCH" "$COMMIT_HASH" | head -20
    FILE_COUNT=$(git diff --name-only "$CURRENT_BRANCH" "$COMMIT_HASH" | wc -l | tr -d ' ')
    if [ "$FILE_COUNT" -gt 20 ]; then
        echo "... and $((FILE_COUNT - 20)) more files"
    fi
    echo ""

    # Check for conflicts (dry-run)
    echo "🔍 Checking for merge conflicts..."

    # Try merge in dry-run mode (using merge-tree)
    if git merge-tree $(git merge-base HEAD "$COMMIT_HASH") HEAD "$COMMIT_HASH" | grep -q "^<<<<<"; then
        echo "⚠️  WARNING: Merge conflicts detected!"
        echo ""
        echo "Conflicting files:"
        git merge-tree $(git merge-base HEAD "$COMMIT_HASH") HEAD "$COMMIT_HASH" | grep -B2 "^<<<<<" | grep "^+++ " | sed 's/^+++ b\//  - /' | sort -u
        echo ""
        echo "❌ Cannot safely backport this hotfix"
        echo ""
        echo "Recommendations:"
        echo "1. The hotfix may conflict with new code in $CURRENT_BRANCH"
        echo "2. The bug may have been fixed differently in $CURRENT_BRANCH"
        echo "3. The code that was fixed may have been removed/replaced in $CURRENT_BRANCH"
        echo ""
        echo "Options:"
        echo "  - Cherry-pick manually and resolve conflicts: git cherry-pick $COMMIT_HASH"
        echo "  - Check if the bug still exists in $CURRENT_BRANCH"
        echo "  - Skip this backport if the code changed significantly"
        exit 1
    fi

    echo "✅ No conflicts detected - safe to merge"
    echo ""

    # Show the diff summary
    echo "📊 Changes summary:"
    git diff --stat "$CURRENT_BRANCH" "$COMMIT_HASH"
    echo ""

    # Ask for confirmation
    echo "⚠️  This will cherry-pick the hotfix commit into $CURRENT_BRANCH"
    echo ""
    read -p "Do you want to proceed? (yes/no): " -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "❌ Backport cancelled"
        exit 0
    fi

    # Perform the cherry-pick
    echo "🚀 Cherry-picking commit..."
    if git cherry-pick "$COMMIT_HASH"; then
        echo ""
        echo "✅ Hotfix backported successfully!"
        echo ""
        echo "Next steps:"
        echo "1. Review the changes: git show HEAD"
        echo "2. Run tests: just test"
        echo "3. Push when ready: git push origin $CURRENT_BRANCH"
    else
        echo ""
        echo "❌ Cherry-pick failed (this shouldn't happen - we checked for conflicts!)"
        echo ""
        echo "To abort: git cherry-pick --abort"
        echo "To resolve and continue: fix conflicts, then: git cherry-pick --continue"
        exit 1
    fi

# Port commit from current branch to selected target branch(es) (interactive, safe)
port-commit:
    #!/usr/bin/env bash
    set -euo pipefail

    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    echo "🔄 Port Commit from $CURRENT_BRANCH"
    echo "═══════════════════════════════════════════════"
    echo ""

    # Get list of all branches (local and remote, excluding current)
    ALL_BRANCHES=$(git branch -a | grep -v "^*" | grep -v "HEAD" | sed 's/remotes\/origin\///' | sed 's/^[* ] //' | sort -u | grep -v "^${CURRENT_BRANCH}$")

    if [ -z "$ALL_BRANCHES" ]; then
        echo "❌ Error: No other branches found"
        exit 1
    fi

    echo "Available branches:"
    echo ""
    echo "$ALL_BRANCHES" | nl -w2 -s". "
    echo ""

    # Ask user to select target branch
    read -p "Enter branch number to compare with (or 'q' to quit): " -r
    echo ""

    if [[ $REPLY == "q" ]]; then
        echo "❌ Port cancelled"
        exit 0
    fi

    # Get the selected branch
    TARGET_BRANCH=$(echo "$ALL_BRANCHES" | sed -n "${REPLY}p")

    if [ -z "$TARGET_BRANCH" ]; then
        echo "❌ Error: Invalid selection"
        exit 1
    fi

    echo "Comparing $CURRENT_BRANCH with $TARGET_BRANCH"
    echo ""

    # Fetch latest
    git fetch origin "$TARGET_BRANCH" --quiet 2>/dev/null || true

    # Find commits in current branch that are NOT in target branch
    echo "🔍 Finding commits in $CURRENT_BRANCH not in $TARGET_BRANCH..."
    echo ""

    # Get list of commits
    COMMITS=$(git log --oneline "$TARGET_BRANCH..$CURRENT_BRANCH" --no-merges 2>/dev/null)

    if [ -z "$COMMITS" ]; then
        echo "✅ No commits to port - $TARGET_BRANCH has all commits from $CURRENT_BRANCH"
        exit 0
    fi

    echo "Commits available for porting:"
    echo ""
    git log --oneline --no-merges "$TARGET_BRANCH..$CURRENT_BRANCH" | nl -w2 -s". "
    echo ""

    # Ask user to select a commit
    read -p "Enter commit number to port (or 'q' to quit): " -r
    echo ""

    if [[ $REPLY == "q" ]]; then
        echo "❌ Port cancelled"
        exit 0
    fi

    # Get the selected commit hash
    COMMIT_HASH=$(git log --oneline --no-merges "$TARGET_BRANCH..$CURRENT_BRANCH" | sed -n "${REPLY}p" | awk '{print $1}')

    if [ -z "$COMMIT_HASH" ]; then
        echo "❌ Error: Invalid selection"
        exit 1
    fi

    # Get commit details
    COMMIT_MESSAGE=$(git log -1 --pretty=format:"%s" "$COMMIT_HASH")
    COMMIT_AUTHOR=$(git log -1 --pretty=format:"%an" "$COMMIT_HASH")
    COMMIT_DATE=$(git log -1 --pretty=format:"%ad" --date=short "$COMMIT_HASH")

    echo "Selected Commit:"
    echo "  Hash: $COMMIT_HASH"
    echo "  Message: $COMMIT_MESSAGE"
    echo "  Author: $COMMIT_AUTHOR"
    echo "  Date: $COMMIT_DATE"
    echo ""

    # Now ask which branches to port to
    echo "Port this commit to which branch(es)?"
    echo ""
    echo "Available target branches:"
    AVAILABLE_TARGETS=$(git branch -a | grep -v "^*" | grep -v "HEAD" | sed 's/remotes\/origin\///' | sed 's/^[* ] //' | sort -u | grep -v "^${CURRENT_BRANCH}$")
    echo "$AVAILABLE_TARGETS" | nl -w2 -s". "
    echo ""
    echo "Enter branch numbers separated by spaces (e.g., '1 3 5')"
    echo "Or 'all' for all branches, or 'q' to quit"
    read -p "> " -r
    echo ""

    if [[ $REPLY == "q" ]]; then
        echo "❌ Port cancelled"
        exit 0
    fi

    # Build list of target branches
    if [[ $REPLY == "all" ]]; then
        TARGET_BRANCHES=($AVAILABLE_TARGETS)
    else
        TARGET_BRANCHES=()
        for num in $REPLY; do
            branch=$(echo "$AVAILABLE_TARGETS" | sed -n "${num}p")
            if [ -n "$branch" ]; then
                TARGET_BRANCHES+=("$branch")
            fi
        done
    fi

    if [ ${#TARGET_BRANCHES[@]} -eq 0 ]; then
        echo "❌ Error: No valid branches selected"
        exit 1
    fi

    echo "Will port commit to: ${TARGET_BRANCHES[*]}"
    echo ""

    # Process each target branch
    for branch in "${TARGET_BRANCHES[@]}"; do
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Processing branch: $branch"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""

        # Check if branch exists locally
        if ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
            # Try to create from remote
            if git rev-parse --verify "origin/$branch" >/dev/null 2>&1; then
                echo "Creating local branch $branch from origin/$branch..."
                git branch "$branch" "origin/$branch"
            else
                echo "⚠️  WARNING: Branch $branch not found locally or remotely - skipping"
                echo ""
                continue
            fi
        fi

        # Checkout target branch
        git checkout "$branch" --quiet

        # Check if commit already exists
        if git log --all --pretty=format:"%s|%an" | grep -q "^${COMMIT_MESSAGE}|${COMMIT_AUTHOR}$"; then
            echo "⚠️  WARNING: A commit with same message and author already exists in $branch"
            echo "This might be a duplicate. Continue anyway?"
            read -p "(yes/no/skip): " -r
            echo ""
            if [[ $REPLY == "skip" ]]; then
                echo "⏭️  Skipping $branch"
                echo ""
                continue
            elif [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                echo "❌ Port to $branch cancelled"
                echo ""
                continue
            fi
        fi

        # Show what files would be affected
        echo "📁 Files that would be changed:"
        git diff --name-only "$branch" "$COMMIT_HASH" | head -20
        FILE_COUNT=$(git diff --name-only "$branch" "$COMMIT_HASH" | wc -l | tr -d ' ')
        if [ "$FILE_COUNT" -gt 20 ]; then
            echo "... and $((FILE_COUNT - 20)) more files"
        fi
        echo ""

        # Check for conflicts (dry-run)
        echo "🔍 Checking for merge conflicts..."

        # Try merge in dry-run mode (using merge-tree)
        if git merge-tree $(git merge-base HEAD "$COMMIT_HASH") HEAD "$COMMIT_HASH" | grep -q "^<<<<<"; then
            echo "⚠️  WARNING: Merge conflicts detected!"
            echo ""
            echo "Conflicting files:"
            git merge-tree $(git merge-base HEAD "$COMMIT_HASH") HEAD "$COMMIT_HASH" | grep -B2 "^<<<<<" | grep "^+++ " | sed 's/^+++ b\//  - /' | sort -u
            echo ""
            echo "❌ Cannot safely port to $branch - conflicts detected"
            echo ""
            echo "Recommendations:"
            echo "1. The commit may conflict with code in $branch"
            echo "2. The change may have been applied differently in $branch"
            echo "3. The code may have been removed/replaced in $branch"
            echo ""
            echo "Options:"
            echo "  - Cherry-pick manually and resolve conflicts: git checkout $branch && git cherry-pick $COMMIT_HASH"
            echo "  - Skip this branch"
            echo ""
            read -p "Skip this branch? (yes/no): " -r
            echo ""
            if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                echo "⏭️  Skipping $branch"
                echo ""
                continue
            else
                echo "❌ Port to $branch cancelled"
                echo ""
                continue
            fi
        fi

        echo "✅ No conflicts detected - safe to merge"
        echo ""

        # Show the diff summary
        echo "📊 Changes summary:"
        git diff --stat "$branch" "$COMMIT_HASH"
        echo ""

        # Ask for confirmation
        echo "⚠️  This will cherry-pick the commit into $branch"
        echo ""
        read -p "Do you want to proceed? (yes/no/skip): " -r
        echo ""

        if [[ $REPLY == "skip" ]]; then
            echo "⏭️  Skipping $branch"
            echo ""
            continue
        elif [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo "❌ Port to $branch cancelled"
            echo ""
            continue
        fi

        # Perform the cherry-pick
        echo "🚀 Cherry-picking commit to $branch..."
        if git cherry-pick "$COMMIT_HASH"; then
            echo ""
            echo "✅ Commit ported to $branch successfully!"
            echo ""
        else
            echo ""
            echo "❌ Cherry-pick failed"
            echo ""
            echo "To abort: git cherry-pick --abort"
            echo "To resolve and continue: fix conflicts, then: git cherry-pick --continue"
            echo ""
            read -p "Abort cherry-pick? (yes/no): " -r
            if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                git cherry-pick --abort
                echo "Cherry-pick aborted"
            fi
            echo ""
        fi
    done

    # Return to original branch
    git checkout "$CURRENT_BRANCH" --quiet

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ Port operation complete"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Back on branch: $CURRENT_BRANCH"
    echo ""
    echo "Next steps:"
    echo "1. Review changes on each branch: git checkout <branch> && git show HEAD"
    echo "2. Run tests on each branch: git checkout <branch> && just test"
    echo "3. Push when ready: git push origin <branch>"

# ============================================================================
# Branch Promotions & Releases
# ============================================================================

# Promote changes through all branches sequentially (dev → testing → review → master)
# Ensures no branch is left behind - maintains consistent version across all branches
promote:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🔄 Promoting changes through all branches..."
    echo ""
    echo "Branch flow: dev → testing → review → master"
    echo ""

    # Save current branch
    ORIGINAL_BRANCH=$(git branch --show-current)

    # Function to safely merge
    merge_branch() {
        local from=$1
        local to=$2

        echo "📤 Promoting: $from → $to"
        git checkout "$to"
        git pull origin "$to"

        if git merge "$from" --no-edit; then
            git push origin "$to"
            echo "  ✅ Successfully promoted to $to"
        else
            echo "  ❌ Merge conflict detected in $to"
            echo "     Please resolve conflicts manually and run:"
            echo "     git add . && git commit && git push origin $to"
            exit 1
        fi
        echo ""
    }

    # Promote through all branches
    echo "1️⃣  Promoting dev → testing..."
    merge_branch "dev" "testing"

    echo "2️⃣  Promoting testing → review..."
    merge_branch "testing" "review"

    echo "3️⃣  Promoting review → master..."
    merge_branch "review" "master"

    echo "4️⃣  Syncing master → main..."
    git checkout main
    git pull origin main
    git reset --hard master
    git push origin main --force-with-lease
    echo "  ✅ main synced with master"
    echo ""

    # Restore original branch
    echo "🔙 Returning to original branch: $ORIGINAL_BRANCH"
    git checkout "$ORIGINAL_BRANCH"

    echo ""
    echo "✅ All branches promoted successfully!"
    echo ""
    echo "Branch status:"
    echo "  dev      ← Development (alpha)"
    echo "  testing  ← Beta testing"
    echo "  review   ← Release candidate"
    echo "  master   ← Stable (production)"
    echo "  main     ← Mirror of master"

# Run the multi-channel release script to create GitHub releases with auto-generated changelogs

# Release all channels (alpha, beta, rc, stable) to GitHub
# Does NOT publish stable to PyPI - use 'just publish' for that
release:
    @echo "🚀 Creating GitHub releases for all channels (without PyPI)..."
    @echo ""
    @echo "Channels:"
    @echo "  • alpha  (from dev branch)"
    @echo "  • beta   (from testing branch)"
    @echo "  • rc     (from review branch)"
    @echo "  • stable (from master branch) → GitHub only (no PyPI)"
    @echo ""
    @echo "Note: This creates releases on GitHub but does NOT publish to PyPI."
    @echo "      Use 'just publish' to publish stable to PyPI."
    @echo ""
    @./scripts/release.sh --alpha dev --beta testing --rc review --stable master --no-pypi

# Release all channels (alpha, beta, rc, stable) and publish stable to PyPI
# Requires UV_PUBLISH_TOKEN environment variable
publish:
    @echo "🚀 Creating GitHub releases for ALL channels and publishing to PyPI..."
    @echo ""
    @echo "Channels:"
    @echo "  • alpha  (from dev branch) → GitHub only"
    @echo "  • beta   (from testing branch) → GitHub only"
    @echo "  • rc     (from review branch) → GitHub only"
    @echo "  • stable (from master branch) → GitHub + PyPI ✨"
    @echo ""
    @if [ -z "${UV_PUBLISH_TOKEN-}" ]; then \
        echo "❌ Error: UV_PUBLISH_TOKEN not set"; \
        echo "Please export your PyPI token:"; \
        echo "  export UV_PUBLISH_TOKEN=\"pypi-XXXXXXXXXXXX\""; \
        exit 1; \
    fi
    @echo "✓ UV_PUBLISH_TOKEN is set"
    @echo ""
    @./scripts/release.sh --alpha dev --beta testing --rc review --stable master

# ============================================================================
# Changelog
# ============================================================================

# Generate/update CHANGELOG.md from git history
changelog:
    @echo "📝 Generating CHANGELOG.md..."
    uv run git-cliff --output CHANGELOG.md
    @echo "✅ CHANGELOG.md updated"

# Generate changelog for unreleased changes only
changelog-unreleased:
    @echo "📝 Generating unreleased changes..."
    uv run git-cliff --unreleased

# Generate changelog for specific version/tag
changelog-tag tag:
    @echo "📝 Generating changelog for {{tag}}..."
    uv run git-cliff --tag {{tag}}

# Preview changelog without writing to file
changelog-preview:
    @echo "📝 Preview of CHANGELOG.md:"
    @echo ""
    uv run git-cliff

# Manually update changelog and create a release tag (for custom/manual releases)
release-tag version:
    @echo "🚀 Manually preparing release tag {{version}}..."
    @echo ""
    @echo "1. Updating CHANGELOG.md..."
    uv run git-cliff --tag {{version}} --output CHANGELOG.md
    @echo ""
    @echo "2. Committing changelog..."
    git add CHANGELOG.md
    git commit -m "chore(release): update CHANGELOG for {{version}}"
    @echo ""
    @echo "3. Creating git tag..."
    git tag -a {{version}} -m "Release {{version}}"
    @echo ""
    @echo "✅ Release {{version}} prepared!"
    @echo ""
    @echo "To push:"
    @echo "  git push origin main"
    @echo "  git push origin {{version}}"
    @echo ""
    @echo "Note: For automated multi-channel releases, use 'just release' or 'just publish'"

# ============================================================================
# Development Helpers
# ============================================================================

# Show current version
version:
    @grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'

# Show installed svg2fbf version
version-installed:
    @svg2fbf --version 2>/dev/null || echo "Not installed as tool"

# Check if svg2fbf is in venv (should be empty)
check-venv:
    @echo "Checking if svg2fbf is in venv..."
    @uv pip list | grep svg2fbf || echo "✓ svg2fbf not in venv (correct)"

# Verify installation
verify:
    @echo "🔍 Verifying installation..."
    @echo ""
    @echo "Project version:"
    @just version
    @echo ""
    @echo "Installed version:"
    @just version-installed
    @echo ""
    @echo "Venv check:"
    @just check-venv
    @echo ""
    @echo "Commands available:"
    @which svg2fbf || echo "  svg2fbf: NOT FOUND"
    @which svg-repair-viewbox || echo "  svg-repair-viewbox: NOT FOUND"

# Open interactive Python with project in path
repl:
    @echo "🐍 Starting Python REPL with project..."
    uv run python

# ============================================================================
# Documentation
# ============================================================================

# Show development workflow
workflow:
    @echo ""
    @echo "📚 svg2fbf Development Workflow"
    @echo "==============================="
    @echo ""
    @echo "0. Setup (first time or after .git recreation):"
    @echo "   just install-hooks           # Install git hooks"
    @echo ""
    @echo "1. Add dependencies:"
    @echo "   just add <package>           # Add runtime dependency and sync"
    @echo "   just add-dev <package>       # Add dev dependency and sync"
    @echo ""
    @echo "2. Make changes and test:"
    @echo "   just test                    # Run tests"
    @echo "   just check                   # Run quality checks"
    @echo ""
    @echo "3. Build and install:"
    @echo "   just build                   # Build (auto-bump version)"
    @echo "   just install                 # Smart install (builds if needed)"
    @echo "   just reinstall               # Full reinstall (alpha bump)"
    @echo ""
    @echo "4. Clean up:"
    @echo "   just clean-temp              # Clean temp directories"
    @echo "   just clean-all               # Clean everything"
    @echo ""
    @echo "For more commands: just --list"
    @echo ""

# ============================================================================
# CI/CD Helpers
# ============================================================================

# Run CI checks (what runs on GitHub Actions)
ci:
    @echo "🤖 Running CI checks..."
    @echo ""
    just lint
    @echo ""
    # just typecheck  # Disabled - mypy not in use
    @echo ""
    just test-cov
    @echo ""
    @echo "✅ CI checks passed!"
