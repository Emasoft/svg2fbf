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
#   just --list              # Show all available commands
#   just add                 # Add and sync dependencies
#   just add-dev             # Add dev dependencies and sync
#   just remove              # Remove and sync dependencies
#   just build               # Build wheel (auto-bumps: alpha if alpha, patch if stable)
#   just install             # Smart install (builds only if code changed)
#   just reinstall           # Full rebuild and reinstall (default: alpha bump)
#   just reinstall --beta    # Bump beta version
#   just clean               # Clean temp directories
#   just test                # Run tests

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

# Build wheel package (auto-bumps version: alpha if already alpha, patch otherwise)
build:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🔨 Building with auto version bump..."

    # Get current version
    CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
    echo "Current version: $CURRENT_VERSION"

    # Determine bump type: if version contains 'a' (alpha), bump alpha; else bump patch
    if [[ "$CURRENT_VERSION" == *"a"* ]]; then
        BUMP_TYPE="alpha"
        echo "⬆️  Auto-bumping alpha version..."
    else
        BUMP_TYPE="patch"
        echo "⬆️  Auto-bumping patch version..."
    fi

    # Bump version
    uv version --bump "$BUMP_TYPE" --no-sync
    NEW_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
    echo "✅ Bumped to: $NEW_VERSION"
    echo ""

    # Build wheel
    echo "🔨 Building wheel..."
    uv build --wheel --quiet --out-dir dist
    echo "✅ Wheel built:"
    ls -t dist/svg2fbf-*.whl | head -1
    echo ""
    echo "📦 Version: $NEW_VERSION"

# Bump version (alpha, beta, rc, patch, minor, major)
bump type="alpha":
    @echo "⬆️  Bumping {{type}} version..."
    uv version --bump {{type}} --no-sync
    @echo "✅ Version bumped to:"
    @grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'

# Install as uv tool (auto-builds only if code changed)
install python="3.10":
    #!/usr/bin/env bash
    set -euo pipefail

    echo "📥 Smart install (builds only if code changed)..."
    echo ""

    # Find latest wheel
    WHEEL=$(ls -t dist/svg2fbf-*.whl 2>/dev/null | head -1)

    # Check if we need to build
    NEED_BUILD=false

    if [ -z "$WHEEL" ]; then
        echo "ℹ️  No wheel found - will build"
        NEED_BUILD=true
    else
        # Get version from wheel filename (e.g., svg2fbf-0.1.2a12-py3-none-any.whl)
        WHEEL_VERSION=$(basename "$WHEEL" | sed 's/svg2fbf-\(.*\)-py3.*/\1/')
        echo "Found wheel: $WHEEL_VERSION"

        # Get current project version
        PROJECT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
        echo "Project version: $PROJECT_VERSION"

        # Check if versions match
        if [ "$WHEEL_VERSION" != "$PROJECT_VERSION" ]; then
            echo "ℹ️  Version mismatch - will build"
            NEED_BUILD=true
        else
            # Check for changes in src/ since last commit
            if git diff --quiet HEAD -- src/; then
                echo "✓ No code changes since last version"
                NEED_BUILD=false
            else
                echo "ℹ️  Code changes detected in src/ - will build"
                NEED_BUILD=true
            fi
        fi
    fi

    # Build if needed
    if [ "$NEED_BUILD" = true ]; then
        echo ""
        echo "🔨 Building..."
        just build
        echo ""
        # Update WHEEL to the newly built one
        WHEEL=$(ls -t dist/svg2fbf-*.whl 2>/dev/null | head -1)
    else
        echo ""
        echo "⏭️  Skipping build (using existing wheel)"
        echo ""
    fi

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

# Full rebuild and reinstall (default: alpha bump)
reinstall type="alpha" python="3.10":
    @echo "🔄 Full reinstall ({{type}} bump)..."
    @echo ""
    just bump {{type}}
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
    @echo "1. Add dependencies:"
    @echo "   just add <package>           # Add runtime dependency and sync"
    @echo "   just add-dev <package>       # Add dev dependency and sync"
    @echo ""
    @echo "2. Make changes and test:"
    @echo "   just test                    # Run tests"
    @echo "   just check                   # Run quality checks"
    @echo ""
    @echo "3. Build and install:"
    @echo "   just reinstall               # Full reinstall (alpha bump)"
    @echo "   just reinstall beta          # Bump beta version"
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
