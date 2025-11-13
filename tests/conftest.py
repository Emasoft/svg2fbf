"""
pytest configuration for svg2fbf test suite

Handles:
- Puppeteer installation verification
- Custom CLI options for cache management
- Temporary file cleanup
- Test fixtures
- Artifact preservation to tests/results/
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add project root to path so tests package can be imported
# This allows pytest to run without PYTHONPATH=. in CI environments
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.utils.config import get_test_config


def pytest_configure(config):
    """
    Setup: Install Puppeteer if not already installed

    This runs once before any tests to ensure Puppeteer and Chrome are available.
    """
    tests_dir = Path(__file__).parent
    tests_dir / "package.json"
    node_modules = tests_dir / "node_modules"

    # Check if Puppeteer is installed
    if not node_modules.exists():
        print("\n🔧 Installing Puppeteer (first run only)...")
        try:
            subprocess.run(
                ["npm", "install"],
                cwd=tests_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            print("✓ Puppeteer installed successfully\n")
        except subprocess.CalledProcessError as e:
            print("❌ Failed to install Puppeteer:")
            print(f"   stdout: {e.stdout}")
            print(f"   stderr: {e.stderr}")
            sys.exit(1)
        except FileNotFoundError:
            print("❌ npm not found. Please install Node.js and npm first.")
            sys.exit(1)

    # Handle cache management options
    cache_file = tests_dir / "invalid_svg_example_frames.json"

    if config.getoption("--clear-invalid-cache"):
        if cache_file.exists():
            cache_file.unlink()
            print("✓ Invalid SVG cache cleared\n")
        else:
            print("ℹ️  No cache file to clear\n")
        sys.exit(0)

    if config.getoption("--show-invalid-cache"):
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                invalid_count = len(data.get("invalid_svgs", {}))
                print(f"\n📋 Invalid SVG Cache ({invalid_count} entries):")
                print(f"   Last updated: {data.get('last_updated', 'Unknown')}\n")

                for svg_path, info in data.get("invalid_svgs", {}).items():
                    print(f"  ❌ {svg_path}")
                    print(f"     Reason: {info.get('reason', 'Unknown')}")
                    print(f"     Validated: {info.get('validated_at', 'Unknown')}\n")
            except Exception as e:
                print(f"❌ Error reading cache: {e}")
        else:
            print("ℹ️  No invalid SVG cache found\n")
        sys.exit(0)

    # Handle session listing
    if config.getoption("--list-sessions"):
        from tests.utils.session_manager import SessionManager

        sessions_root = tests_dir / "sessions"
        session_mgr = SessionManager(sessions_root)
        sessions = session_mgr.list_sessions()

        if not sessions:
            print("\nℹ️  No saved test sessions found\n")
        else:
            print(f"\n📚 Saved Test Sessions ({len(sessions)} sessions):\n")
            print("=" * 80)

            for session in sessions:
                metadata = session_mgr.get_session_info(session.session_id)
                print(f"\n  🆔 Session: {session.session_id}")
                print(f"     Frames: {session.frame_count}")
                print(f"     Created: {session.timestamp}")
                if metadata:
                    test_config = metadata.get("test_config", {})
                    width = test_config.get("width", "N/A")
                    height = test_config.get("height", "N/A")
                    fps = test_config.get("fps", "N/A")
                    print(f"     Config: {width}x{height}, {fps} FPS")
                    svg_sources = metadata.get("svg_sources", [])
                    if svg_sources:
                        print(f"     Sources: {len(svg_sources)} SVG files")
                print(f"     Location: {session.input_batch_dir}")

            print("\n" + "=" * 80)
            print("\nUsage: pytest --use-session=<session_id>\n")

        sys.exit(0)


def pytest_addoption(parser):
    """Add custom command-line options"""

    # Load test configuration from pyproject.toml
    # Why: Single source of truth for all defaults - no hardcoded values
    test_config = get_test_config()

    # Cache management options
    parser.addoption(
        "--clear-invalid-cache",
        action="store_true",
        default=False,
        help="Clear invalid SVG cache and exit (forces re-validation on next run)",
    )
    parser.addoption(
        "--show-invalid-cache",
        action="store_true",
        default=False,
        help="Show contents of invalid SVG cache and exit",
    )
    parser.addoption(
        "--skip-validation",
        action="store_true",
        default=False,
        help="Skip SVG validation (use cached results only, fail if not cached)",
    )

    # Test execution options
    parser.addoption(
        "--keep-temp",
        action="store_true",
        default=False,
        help="Keep temporary test files for inspection after test completion",
    )
    parser.addoption(
        "--render-diffs",
        action="store_true",
        default=False,
        help="Generate visual diff images for failed pixel comparisons",
    )
    parser.addoption(
        "--html-report",
        action="store_true",
        default=True,  # Now default (set in pyproject.toml)
        help=("Generate HTML comparison report with all frames side-by-side (disables fail-fast) - DEFAULT"),
    )
    parser.addoption(
        "--no-html-report",
        action="store_false",
        dest="html_report",
        help="Disable HTML report generation (fail-fast on first difference)",
    )
    parser.addoption(
        "--max-frames",
        type=int,
        default=test_config.max_frames,  # Read from pyproject.toml
        help=(f"Maximum number of frames to test in large batches (default: {test_config.max_frames})"),
    )
    parser.addoption(
        "--image-tolerance",
        type=float,
        default=test_config.image_tolerance,  # Read from pyproject.toml
        help=(f"Image-level tolerance: percentage of pixels allowed to differ (0.0-100.0). Default: {test_config.image_tolerance}%%. See tests/ISSUES.md for details."),
    )
    parser.addoption(
        "--pixel-tolerance",
        type=float,
        default=test_config.pixel_tolerance,  # Read from pyproject.toml
        help=(f"Pixel-level tolerance: color difference threshold per pixel (0.0-1.0). Default: {test_config.pixel_tolerance} (~1 RGB value). See tests/ISSUES.md for details."),
    )
    parser.addoption(
        "--no-keep-ratio",
        action="store_true",
        default=False,
        help=("Don't use preserveAspectRatio attribute (useful for animations with negative viewBox coordinates)"),
    )

    # Session management options
    parser.addoption(
        "--save-session",
        type=str,
        default=None,
        metavar="SESSION_ID",
        help=("Save test input batch as named session for future replication (auto-generates ID if not provided)"),
    )
    parser.addoption(
        "--use-session",
        type=str,
        default=None,
        metavar="SESSION_ID",
        help=("Run test using inputs from saved session (enables deterministic replication)"),
    )
    parser.addoption(
        "--list-sessions",
        action="store_true",
        default=False,
        help="List all saved test sessions and exit",
    )


@pytest.fixture(scope="function")
def preserve_artifacts(request, tests_dir):
    """
    Preserve test artifacts to tests/results/<session_id>/<timestamp>/

    Why:
    - /tmp gets wiped on reboot
    - Need permanent record of test results
    - Useful for debugging and comparing multiple runs of same input
    - Results organized by session (input folder) for easy comparison

    Usage in test:
        preserve_artifacts(
            session_id="session_001_3frames",
            fbf_file=fbf_output_file,
            html_report=report_path,
            input_frames_dir=input_frames_dir,
            output_frames_dir=output_frames_dir
        )
    """

    def _preserve(
        session_id=None,
        fbf_file=None,
        html_report=None,
        input_frames_dir=None,
        output_frames_dir=None,
    ):
        """
        Preserve test run results to tests/results/<session_id>/<timestamp>/

        Args:
            session_id: Session ID (input folder identifier) - REQUIRED
            fbf_file: Generated FBF SVG file
            html_report: HTML comparison report
            input_frames_dir: Rendered input frames (PNGs)
            output_frames_dir: Captured output frames (PNGs)

        Returns:
            Path to the results directory created

        Why:
            Results are organized by session_id, with timestamped subdirectories
            for each run. This allows comparing multiple runs of the same input.
        """
        if not session_id:
            raise ValueError("session_id is required for preserving artifacts")

        # SAFEGUARD: Validate session_id format
        # Why: Catch invalid session_id before creating directories
        import re

        if not re.match(r"^session_\d{3}_\d+frames$", session_id):
            raise ValueError(f"Invalid session_id format: '{session_id}'. Expected pattern: 'session_NNN_Mframes' (e.g., 'session_044_3frames'). This indicates a bug in session management or test code.")

        # SAFEGUARD: Validate corresponding session exists in sessions/ directory
        # Why: Catch bugs where session_id doesn't match actual saved session
        sessions_dir = tests_dir / "sessions" / session_id
        if not sessions_dir.exists():
            available = [d.name for d in (tests_dir / "sessions").iterdir() if d.is_dir()]
            raise ValueError(f"Session directory does not exist: {sessions_dir}\nThis indicates:\n  1. Session '{session_id}' was never saved, OR\n  2. Test is using wrong session_id (mismatch bug)\nAvailable sessions: {available}")

        # Create results directory: tests/results/<session_id>/<timestamp>/
        # Why: Group all runs of same input together for easy comparison
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = tests_dir / "results" / session_id / timestamp
        results_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n💾 Preserving test run results to: {results_dir}")

        # Create FBF output subdirectory
        # Why: Keep output structure organized
        if fbf_file and Path(fbf_file).exists():
            fbf_output_dir = results_dir / "fbf_output"
            fbf_output_dir.mkdir(parents=True, exist_ok=True)
            dest_fbf = fbf_output_dir / Path(fbf_file).name
            shutil.copy2(fbf_file, dest_fbf)
            print(f"   ✓ FBF file: {dest_fbf}")

        # Preserve HTML report (with embedded PNGs)
        # Why: Self-contained visual comparison of all frames
        if html_report and Path(html_report).exists():
            dest_report = results_dir / "comparison_report.html"
            shutil.copy2(html_report, dest_report)
            print(f"   ✓ HTML report: {dest_report}")

        # Preserve input frames (for reference)
        # Why: Ground truth PNGs for this run
        if input_frames_dir and Path(input_frames_dir).exists():
            dest_input = results_dir / "input_frames"
            shutil.copytree(input_frames_dir, dest_input, dirs_exist_ok=True)
            print(f"   ✓ Input frames: {dest_input}")

        # Preserve output frames (for reference)
        # Why: What FBF animation actually rendered in this run
        if output_frames_dir and Path(output_frames_dir).exists():
            dest_output = results_dir / "output_frames"
            shutil.copytree(output_frames_dir, dest_output, dirs_exist_ok=True)
            print(f"   ✓ Output frames: {dest_output}")

        return results_dir

    return _preserve


@pytest.fixture(scope="function", autouse=True)
def cleanup_temp_files(request, tmp_path):
    """
    Cleanup temporary files after each test unless --keep-temp flag is set

    This fixture runs automatically for every test function.
    The tmp_path fixture already handles cleanup, but we can prevent it here.
    """
    yield

    if request.config.getoption("--keep-temp"):
        # Print location so user can inspect files
        print(f"\n📁 Test files kept at: {tmp_path}")
    # Otherwise tmp_path auto-cleans on fixture teardown


@pytest.fixture(scope="session")
def tests_dir():
    """Path to tests/ directory"""
    return Path(__file__).parent


@pytest.fixture(scope="session")
def project_root(tests_dir):
    """Path to project root directory"""
    return tests_dir.parent


@pytest.fixture(scope="session")
def examples_dir(project_root):
    """Path to examples/ directory containing SVG test data"""
    return project_root / "examples"


@pytest.fixture(scope="session")
def node_scripts_dir(tests_dir):
    """Path to node_scripts/ directory containing Puppeteer scripts"""
    return tests_dir / "node_scripts"


@pytest.fixture(scope="session")
def session_manager(tests_dir):
    """
    Session manager for saving/loading test sessions

    Why:
        Enable deterministic test replication with saved input batches
    """
    from tests.utils.session_manager import SessionManager

    sessions_root = tests_dir / "sessions"
    return SessionManager(sessions_root)


@pytest.fixture(scope="function")
def test_session(request, session_manager):
    """
    Manages test session save/load for current test

    Returns session info if --use-session provided, else None

    Why:
        Allow test to use saved inputs or save new inputs after run
    """
    use_session_id = request.config.getoption("--use-session")
    save_session_id = request.config.getoption("--save-session")

    # Check for invalid combinations
    if use_session_id and save_session_id:
        raise ValueError("Cannot use both --use-session and --save-session")

    # Load session if requested
    session_data = None
    if use_session_id:
        session = session_manager.load_session(use_session_id)
        if not session:
            raise ValueError(f"Session '{use_session_id}' not found")

        metadata = session_manager.get_session_info(use_session_id)
        session_data = {"session": session, "metadata": metadata, "mode": "load"}
        print(f"\n🔄 Using saved session: {use_session_id}")
        print(f"   Frames: {session.frame_count}")
        print(f"   Created: {session.timestamp}\n")

    # Return session data + save callback
    class SessionContext:
        def __init__(self, data, save_id, mgr):
            self.data = data
            self.save_id = save_id
            self.manager = mgr

        def should_use_saved_inputs(self):
            """Check if test should use saved inputs"""
            return self.data is not None

        def get_saved_batch_dir(self):
            """Get saved batch directory"""
            if self.data:
                return self.data["session"].input_batch_dir
            return None

        def get_saved_metadata(self):
            """Get saved session metadata"""
            if self.data:
                return self.data["metadata"]
            return None

        def save_after_test(self, frame_count, input_batch_dir, test_config, svg_sources):
            """
            Save session after test completes

            SAFEGUARD: This should NEVER be called when replaying a saved session.
            Why: Replaying should reuse existing session_id, not create new one.
            """
            # SAFEGUARD: Detect if we're replaying a session (should_use_saved_inputs)
            # Why: Prevent accidental new session creation when --use-session is active
            if self.data is not None:
                # We're replaying a saved session - should NOT call save_after_test!
                session_id = self.data.get("metadata", {}).get("session_id", "UNKNOWN")
                raise RuntimeError(
                    "CRITICAL BUG: save_after_test() called while replaying "
                    "saved session! This indicates the test code is trying to "
                    "create a NEW session when it should be REUSING the existing "
                    "session_id from loaded metadata. When --use-session is active, "
                    "extract session_id from metadata instead of calling "
                    f"save_after_test(). Loaded session: {session_id}"
                )

            if self.save_id or self.save_id == "":  # "" means auto-generate
                actual_id = self.save_id if self.save_id else None
                return self.manager.save_session(
                    frame_count=frame_count,
                    input_batch_dir=input_batch_dir,
                    test_config=test_config,
                    svg_sources=svg_sources,
                    session_id=actual_id,
                )
            return None

    return SessionContext(session_data, save_session_id, session_manager)
