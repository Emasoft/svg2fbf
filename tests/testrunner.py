#!/usr/bin/env python3
"""
svg2fbf Test Runner - Comprehensive E2E test session management for svg2fbf

USAGE:
    # Run existing or create E2E test session from input folder
    testrunner.py [input_folder] [options]

    # Create E2E test session from folder with validation and auto-numbering
    testrunner.py create -- /path/to/folder

    # Create E2E test session from individual files with deterministic auto-numbering
    testrunner.py create -- file1.svg file2.svg file3.svg ...

    # Create E2E test session from mixed inputs (folders + files)
    testrunner.py create -- /path/to/folder file1.svg file2.svg

    # Rerun existing E2E test session
    testrunner.py --use-session 100

DETERMINISTIC AUTO-NUMBERING:
    When creating E2E test sessions from individual files or mixed inputs, files are
    automatically numbered using a sophisticated candidates ladder system:

    - Files always get the same numbers regardless of input order
    - Existing numbering patterns in filenames are preserved
    - Priority-based matching: _NNNNN.svg > -NNNNN.svg > .NNNNN.svg > embedded
    - Example: "frame_00007.svg" → frame 7, "other.svg" → first available number

For detailed help, run: testrunner.py --help
"""

import atexit
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import yaml

# Handle tomli/tomllib for different Python versions
try:
    import tomllib  # type: ignore[import-not-found]  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Python < 3.11

# Add tests dir to Python path
# Why: testrunner.py is in tests/, imports are from tests/utils/
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

# ============================================================================
# SIGNAL HANDLING - Graceful shutdown on SIGINT (Ctrl+C) and SIGTERM
# ============================================================================

_cleanup_handlers = []


def register_cleanup(func: Any) -> None:
    """Register a cleanup function to be called on exit or signal."""
    _cleanup_handlers.append(func)


def cleanup_all() -> None:
    """Execute all registered cleanup handlers."""
    for handler in reversed(_cleanup_handlers):
        try:
            handler()
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}", file=sys.stderr)


def signal_handler(signum: int, frame: Any) -> None:
    """Handle termination signals gracefully."""
    signal_name = signal.Signals(signum).name
    print(f"\n\n🛑 Received {signal_name} - Cleaning up and exiting...")
    cleanup_all()
    sys.exit(128 + signum)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_all)

# Import svg2fbf functions for frame transformation
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from utils.CONSTANTS import (  # noqa: E402
    ANIMATION_TYPE,
    AUTO_START,  # Non-configurable test value for auto-starting animations
    # Browser detection: See get_preferred_browser() function
    DEFAULT_CREATE_SESSION_ENCODING,
    DEFAULT_FRAME_NUMBER_FORMAT,
    # Configurable defaults
    DEFAULT_IMAGE_TOLERANCE,
    DEFAULT_MAX_FRAMES,
    DEFAULT_PIXEL_TOLERANCE,
    DEFAULT_PRECISION_CDIGITS,
    DEFAULT_PRECISION_DIGITS,
    DIR_DIFF_PNG,
    DIR_FBF_OUTPUT,
    DIR_INPUT_FRAMES,
    DIR_INPUT_FRAMES_PNG,
    DIR_NODE_SCRIPTS,
    DIR_OUTPUT_FRAMES_PNG,
    # Directory names
    DIR_RESULTS,
    DIR_TESTS,
    # File names
    FILE_SESSION_METADATA,
    FILE_TEST_ANIMATION,
    # Non-configurable test values
    FPS,
    PLAY_ON_CLICK,  # Non-configurable test value for click-to-play behavior
    PNG_DIFF_FRAME_FORMAT,
    # PNG formats
    PNG_INPUT_FRAME_FORMAT,
    PRESERVE_ASPECT_RATIO,
    SEPARATOR_WIDTH,
    # Misc
    SESSION_ID_FORMAT,
    SESSION_ID_TEMP_SUFFIX,
    TIMEOUT_BBOX_CALCULATION,
    TIMEOUT_SVG2FBF_CONVERSION,
    TIMESTAMP_FORMAT,
    VIEWBOX_COMPONENT_COUNT,
)
from utils.html_report import HTMLReportGenerator  # noqa: E402
from utils.image_comparison import ImageComparator  # noqa: E402
from utils.puppeteer_renderer import PuppeteerRenderer  # noqa: E402
from utils.svg2fbf_frame_processor import (  # noqa: E402
    JAVASCRIPT_EXCEPTIONS,
    SVG2FBFFrameProcessor,
    contains_javascript,
    contains_media_elements,
    contains_nested_svg,
    contains_smil_animations,
)

# ============================================================================
# CONFIGURATION MANAGEMENT - Centralized source of truth
# ============================================================================


# REMOVED: ensure_pyproject_config() function
# This function created tests/pyproject.toml which caused UV to create tests/.venv
# Configuration is now loaded only from the project root pyproject.toml


class SessionConfig:
    """
    Centralized test configuration loaded from pyproject.toml.

    This class provides a single source of truth for all configuration values,
    avoiding hardcoded constants scattered throughout the code.
    """

    def __init__(self, pyproject_path: Path):
        """
        Load configuration from pyproject.toml.

        Args:
            pyproject_path: Path to pyproject.toml file

        Raises:
            FileNotFoundError: If pyproject.toml not found
            tomllib.TOMLDecodeError: If pyproject.toml is malformed
        """
        if not pyproject_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {pyproject_path}")

        try:
            with open(pyproject_path, "rb") as f:
                config = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Malformed pyproject.toml: {e}") from e

        test_config = config.get("tool", {}).get("svg2fbf", {}).get("test", {})

        # Test tolerances (configurable, using defaults from CONSTANTS.py)
        self.image_tolerance: float = test_config.get("image_tolerance", DEFAULT_IMAGE_TOLERANCE)
        self.pixel_tolerance: float = test_config.get("pixel_tolerance", DEFAULT_PIXEL_TOLERANCE)
        self.max_frames: int = test_config.get("max_frames", DEFAULT_MAX_FRAMES)

        # Animation settings (NON-CONFIGURABLE in tests, using constants from
        # CONSTANTS.py)
        # Why: These values are essential for test automation and deterministic
        # behavior
        self.fps: float = test_config.get("fps", FPS)
        self.animation_type: str = test_config.get("animation_type", ANIMATION_TYPE)

        # Precision settings (configurable, using defaults from CONSTANTS.py)
        self.precision_digits: int = test_config.get("precision_digits", DEFAULT_PRECISION_DIGITS)
        self.precision_cdigits: int = test_config.get("precision_cdigits", DEFAULT_PRECISION_CDIGITS)

        # E2E test session creation settings (configurable, using defaults
        # from CONSTANTS.py)
        self.frame_number_format: str = test_config.get("frame_number_format", DEFAULT_FRAME_NUMBER_FORMAT)
        self.create_session_encoding: str = test_config.get("create_session_encoding", DEFAULT_CREATE_SESSION_ENCODING)

    def format_frame_filename(self, frame_number: int) -> str:
        """
        Format frame filename using configured format.

        Args:
            frame_number: Frame number (1-indexed)

        Returns:
            Formatted filename (e.g., "frame00001.svg")
        """
        return self.frame_number_format.format(frame_number)


def get_preferred_browser() -> tuple[list[str], str]:
    """
    Detect preferred browser for opening HTML reports.

    Priority:
    1. Chrome (recommended for svg2fbf - best SVG rendering)
    2. System default browser (fallback)

    Returns:
        Tuple of (command_list, browser_name) for opening files
        - command_list: List of command parts for subprocess.run()
        - browser_name: Human-readable browser name for logging

    Why Chrome preferred:
        Chrome has the best SVG rendering engine and is recommended for svg2fbf.
        If Chrome isn't installed, fall back to system default browser.

    Examples:
        On macOS with Chrome installed:
            (["open", "-a", "Google Chrome"], "Chrome")

        On macOS without Chrome:
            (["open"], "default browser")
    """
    # Check if Chrome is installed (macOS)
    # Why: Use `which` to check if Chrome exists in /Applications
    try:
        # Try to find Chrome in standard macOS location
        chrome_path = Path("/Applications/Google Chrome.app")
        if chrome_path.exists():
            return (["open", "-a", "Google Chrome"], "Chrome")
    except Exception:
        # If any error occurs, fall back to default browser
        pass

    # Fallback: Use system default browser
    # Why: No specific browser flag means macOS will use default
    return (["open"], "default browser")


def find_project_pyproject_toml() -> Path:
    """
    Find the project root pyproject.toml using heuristics.

    Uses multiple validation strategies to ensure we're loading from
    the correct project root, not a subdirectory or wrong location.

    Returns:
        Path to verified project root pyproject.toml

    Raises:
        FileNotFoundError: If pyproject.toml not found or validation failed

    Why multiple heuristics:
        - Prevents accidentally reading wrong pyproject.toml
        - Prevents accidentally creating pyproject.toml in tests/
        - Ensures configuration consistency across all runs
    """
    # Strategy 1: Calculate path from testrunner.py location
    # testrunner.py is in: project_root/tests/testrunner.py
    # pyproject.toml is in: project_root/pyproject.toml
    testrunner_path = Path(__file__).resolve()
    calculated_path = testrunner_path.parent.parent / "pyproject.toml"

    # CRITICAL SAFEGUARD: Prevent reading from dangerous locations
    # Never allow pyproject.toml DIRECTLY in system directories
    dangerous_dirs = [
        Path("/"),
        Path("/System"),
        Path("/Library"),
        Path("/usr"),
        Path("/bin"),
    ]
    calculated_parent = calculated_path.parent

    for dangerous in dangerous_dirs:
        # Check if pyproject.toml is DIRECTLY in a dangerous directory
        # (not just if dangerous dir is an ancestor - that would reject all paths)
        if calculated_parent == dangerous:
            raise FileNotFoundError(f"Refusing to load pyproject.toml from system directory: {calculated_path}\npyproject.toml should be in a user project directory, not {dangerous}")

    # SAFEGUARD: Ensure we're NOT loading from tests/ directory
    if calculated_path.parent.name == "tests":
        raise FileNotFoundError(f"Refusing to load pyproject.toml from tests/ directory: {calculated_path}\nThis would cause UV to create tests/.venv. Configuration must be in project root.")

    # Validate the path exists
    if not calculated_path.exists():
        raise FileNotFoundError(f"Project pyproject.toml not found at expected location: {calculated_path}\nCalculated from testrunner.py: {testrunner_path}")

    # Heuristic 1: Verify this is a Python project root
    # Check for common project root markers
    project_root = calculated_path.parent
    has_src_dir = (project_root / "src").exists()
    has_tests_dir = (project_root / "tests").exists()
    has_readme = any((project_root / name).exists() for name in ["README.md", "README.rst", "README.txt"])

    if not (has_src_dir or has_tests_dir):
        raise FileNotFoundError(f"pyproject.toml found at {calculated_path}, but directory doesn't look like project root.\nExpected to find 'src/' or 'tests/' directory in {project_root}")

    # Heuristic 2: Verify pyproject.toml contains svg2fbf configuration
    try:
        # Python 3.11+ has tomllib, older versions use tomli
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(calculated_path, "rb") as f:
            config = tomllib.load(f)

        # Check for svg2fbf project markers
        has_svg2fbf_config = "svg2fbf" in config.get("tool", {})
        has_project_name = config.get("project", {}).get("name") == "svg2fbf"

        if not (has_svg2fbf_config or has_project_name):
            raise FileNotFoundError(f"pyproject.toml found at {calculated_path}, but doesn't contain svg2fbf configuration.\nThis may be the wrong project's pyproject.toml.")

    except Exception as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise FileNotFoundError(f"Failed to validate pyproject.toml at {calculated_path}: {e}") from e

    return calculated_path


def validate_and_repair_config(pyproject_path: Path) -> None:
    """
    Validate pyproject.toml has all required test configuration keys.
    If keys are missing, add them with default values.

    Args:
        pyproject_path: Path to project root pyproject.toml

    Why:
        Configuration may be incomplete or corrupted. This ensures
        all required keys exist with sensible defaults.

    IMPORTANT SAFEGUARDS:
        - Only modifies files in verified project root
        - Creates backup before modification
        - Uses atomic write (write to temp, then rename)
        - Validates TOML syntax before and after modification
    """
    # Python 3.11+ has tomllib, older versions use tomli
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    import shutil

    # Required configuration with defaults
    REQUIRED_CONFIG = {
        "tool": {
            "svg2fbf": {
                "test": {
                    "image_tolerance": 0.05,
                    "pixel_tolerance": 0.004,
                    "max_frames": 50,
                    "fps": 1.0,
                    "animation_type": "once",
                    "precision_digits": 28,
                    "precision_cdigits": 28,
                    "frame_number_format": "frame{:05d}.svg",
                    "create_session_encoding": "utf-8",
                    "default_frames": 2,
                }
            }
        }
    }

    # Read current configuration
    try:
        with open(pyproject_path, "rb") as f:
            current_config = tomllib.load(f)
    except Exception as e:
        raise ValueError(f"Cannot read pyproject.toml at {pyproject_path}: {e}") from e

    # Check if all required keys exist
    tool_config = current_config.get("tool", {})
    svg2fbf_config = tool_config.get("svg2fbf", {})
    test_config = svg2fbf_config.get("test", {})

    missing_keys = []
    for key, _default_value in REQUIRED_CONFIG["tool"]["svg2fbf"]["test"].items():
        if key not in test_config:
            missing_keys.append(f"tool.svg2fbf.test.{key}")

    if not missing_keys:
        # All keys present - no repair needed
        return

    print(f"\n⚠️  WARNING: pyproject.toml missing {len(missing_keys)} configuration keys:")
    for key in missing_keys:
        print(f"   - {key}")
    print("\n🔧 Repairing configuration with default values...")

    # SAFEGUARD: Create backup before modification
    backup_path = pyproject_path.with_suffix(".toml.backup")
    try:
        shutil.copy2(pyproject_path, backup_path)
        print(f"   ✓ Backup created: {backup_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to create backup of pyproject.toml: {e}") from e

    # Merge missing keys into current configuration
    if "tool" not in current_config:
        current_config["tool"] = {}
    if "svg2fbf" not in current_config["tool"]:
        current_config["tool"]["svg2fbf"] = {}
    if "test" not in current_config["tool"]["svg2fbf"]:
        current_config["tool"]["svg2fbf"]["test"] = {}

    for key, default_value in REQUIRED_CONFIG["tool"]["svg2fbf"]["test"].items():
        if key not in current_config["tool"]["svg2fbf"]["test"]:
            current_config["tool"]["svg2fbf"]["test"][key] = default_value
            print(f"   + Added: tool.svg2fbf.test.{key} = {default_value}")

    # SAFEGUARD: Atomic write using temporary file
    # Write to temp file, then rename (atomic on POSIX systems)
    try:
        # Try tomlkit first (preserves formatting and comments)
        import tomlkit  # type: ignore[import-not-found]

        with open(pyproject_path, encoding="utf-8") as f:
            doc = tomlkit.load(f)

        # Update the document
        if "tool" not in doc:
            doc["tool"] = {}
        if "svg2fbf" not in doc["tool"]:
            doc["tool"]["svg2fbf"] = {}
        if "test" not in doc["tool"]["svg2fbf"]:
            doc["tool"]["svg2fbf"]["test"] = {}

        for key, default_value in REQUIRED_CONFIG["tool"]["svg2fbf"]["test"].items():
            if key not in doc["tool"]["svg2fbf"]["test"]:
                doc["tool"]["svg2fbf"]["test"][key] = default_value

        # Write to temporary file first
        temp_fd, temp_path = tempfile.mkstemp(suffix=".toml", prefix="pyproject_", dir=pyproject_path.parent)
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                tomlkit.dump(doc, f)

            # SAFEGUARD: Validate the temporary file is valid TOML
            with open(temp_path, "rb") as f:
                tomllib.load(f)

            # Atomic rename (replaces original)
            os.replace(temp_path, pyproject_path)
            print(f"   ✓ Configuration repaired: {pyproject_path}")

        except Exception as e:
            # Clean up temp file on error
            if Path(temp_path).exists():
                os.unlink(temp_path)
            raise RuntimeError(f"Failed to write repaired configuration: {e}") from e

    except ImportError:
        # Fallback to tomli_w (doesn't preserve formatting as well)
        try:
            import tomli_w

            # Use tomli_w as fallback (will lose formatting/comments)
            print("   ℹ️  Using tomli_w for repair (formatting may change)")

            # Write to temporary file first
            temp_fd, temp_path = tempfile.mkstemp(suffix=".toml", prefix="pyproject_", dir=pyproject_path.parent)
            try:
                with os.fdopen(temp_fd, "wb") as f:
                    tomli_w.dump(current_config, f)

                # SAFEGUARD: Validate the temporary file is valid TOML
                with open(temp_path, "rb") as f:
                    tomllib.load(f)

                # Atomic rename (replaces original)
                os.replace(temp_path, pyproject_path)
                print(f"   ✓ Configuration repaired: {pyproject_path}")
                print("   ⚠️  Note: File formatting was not preserved (install tomlkit for better results)")

            except Exception as e:
                # Clean up temp file on error
                if Path(temp_path).exists():
                    os.unlink(temp_path)
                raise RuntimeError(f"Failed to write repaired configuration: {e}") from e

        except ImportError:
            # Neither tomlkit nor tomli_w available
            print("   ❌ Cannot repair: No TOML writer available")
            print("   Install with: uv pip install tomlkit  (or tomli-w)")
            raise RuntimeError("Missing configuration keys and cannot repair (no TOML writer available)") from None


def load_test_config() -> dict[str, Any]:
    """
    Load test configuration from pyproject.toml with validation and repair.

    This function uses heuristics to find the correct project root pyproject.toml,
    validates it contains required configuration, and repairs missing keys if needed.

    Returns:
        Dictionary with configuration values

    Raises:
        FileNotFoundError: If pyproject.toml not found or validation failed
        ValueError: If configuration is invalid or cannot be repaired

    Why this approach:
        - Prevents loading from wrong pyproject.toml (e.g., tests/pyproject.toml)
        - Detects and repairs missing configuration automatically
        - Provides clear error messages when configuration is broken
    """
    # Use heuristics to find and validate pyproject.toml
    pyproject_path = find_project_pyproject_toml()

    # Validate and repair configuration if needed
    try:
        validate_and_repair_config(pyproject_path)
    except Exception as e:
        print(f"⚠️  Warning: Configuration validation failed: {e}", file=sys.stderr)
        # Continue anyway - SessionConfig will use defaults for missing keys

    try:
        config = SessionConfig(pyproject_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)

    return {
        "image_tolerance": config.image_tolerance,
        "pixel_tolerance": config.pixel_tolerance,
        "max_frames": config.max_frames,
        "fps": config.fps,
        "animation_type": config.animation_type,
        "precision_digits": config.precision_digits,
        "precision_cdigits": config.precision_cdigits,
        "frame_number_format": config.frame_number_format,
        "create_session_encoding": config.create_session_encoding,
    }


# ============================================================================
# E2E TEST SESSION CREATION HELPERS
# ============================================================================


def validate_svg_has_viewbox(svg_path: Path) -> tuple[bool, str]:
    """
    Validate that an SVG file has a viewBox attribute.

    Args:
        svg_path: Path to SVG file

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if viewBox present, False otherwise
        - error_message: Error description if invalid, empty string if valid
    """
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()

        # Check for viewBox in root element
        # Handle both with and without namespace
        viewbox = root.get("viewBox") or root.get("{http://www.w3.org/2000/svg}viewBox")

        if not viewbox:
            return False, "Missing viewBox attribute"

        # Validate viewBox format (should be "x y width height")
        # Why: viewBox must have exactly 4 components (from CONSTANTS.py)
        parts = viewbox.strip().split()
        if len(parts) != VIEWBOX_COMPONENT_COUNT:
            return (
                False,
                f"Invalid viewBox format: '{viewbox}' (expected {VIEWBOX_COMPONENT_COUNT} values)",
            )

        # Validate values are numeric
        try:
            [float(p) for p in parts]
        except ValueError:
            return False, f"Invalid viewBox values: '{viewbox}' (must be numeric)"

        return True, ""

    except ET.ParseError as e:
        return False, f"XML parse error: {e}"
    except Exception as e:
        return False, f"Error reading SVG: {e}"


def calculate_svg_bbox(svg_path: Path) -> dict[str, float]:
    """
    Calculate bounding box of SVG using Puppeteer/headless Chrome.

    This function uses getBBox() in the browser to get accurate bounds
    including fill, stroke, and markers.

    Args:
        svg_path: Path to SVG file

    Returns:
        Dict with keys: x, y, width, height

    Raises:
        RuntimeError: If bbox calculation fails
    """
    # Path to Node.js script (using directory constants from CONSTANTS.py)
    script_path = PROJECT_ROOT / DIR_TESTS / DIR_NODE_SCRIPTS / "calculate_bbox.js"

    if not script_path.exists():
        raise RuntimeError(f"calculate_bbox.js not found at {script_path}")

    # Run Node.js script to calculate bbox
    # Why timeout: Generous timeout for complex SVGs (from CONSTANTS.py)
    try:
        result = subprocess.run(
            ["node", str(script_path), str(svg_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_BBOX_CALCULATION,
            check=False,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Failed to calculate bbox: {error_msg}")

        # Parse JSON output
        bbox = cast(dict[str, float], json.loads(result.stdout.strip()))

        # Validate bbox structure
        required_keys = {"x", "y", "width", "height"}
        if not all(k in bbox for k in required_keys):
            raise RuntimeError(f"Invalid bbox JSON: {bbox}")

        return bbox

    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Bbox calculation timed out after 30 seconds") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse bbox JSON: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {e}") from e


def add_viewbox_to_svg(svg_path: Path, bbox: dict[str, float]) -> None:
    """
    Add or update viewBox attribute in SVG file.

    Args:
        svg_path: Path to SVG file
        bbox: Bounding box dict with keys: x, y, width, height

    Raises:
        RuntimeError: If SVG update fails
    """
    try:
        # Read SVG file
        with open(svg_path, encoding="utf-8") as f:
            content = f.read()

        # Parse XML
        tree = ET.parse(svg_path)
        root = tree.getroot()

        # Create viewBox string
        viewbox_str = f"{bbox['x']} {bbox['y']} {bbox['width']} {bbox['height']}"

        # Check if viewBox already exists
        existing_viewbox = root.get("viewBox") or root.get("{http://www.w3.org/2000/svg}viewBox")

        if existing_viewbox:
            # Update existing viewBox
            root.set("viewBox", viewbox_str)
        else:
            # Add new viewBox attribute
            # Find the <svg opening tag and add viewBox
            # CRITICAL: Handle multiline <svg> tags
            svg_tag_match = re.search(r"<svg[\s\S]*?>", content)
            if not svg_tag_match:
                raise RuntimeError("Could not find <svg> tag in file")

            svg_tag = svg_tag_match.group(0)

            # Insert viewBox attribute before closing >
            # Find position before the last >
            insert_pos = svg_tag.rfind(">")
            if insert_pos == -1:
                raise RuntimeError("Malformed <svg> tag")

            # Build new tag with viewBox
            new_svg_tag = svg_tag[:insert_pos] + f' viewBox="{viewbox_str}"' + svg_tag[insert_pos:]

            # Replace in content
            content = content.replace(svg_tag, new_svg_tag, 1)

            # Write back
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(content)

            return

        # For existing viewBox, use lxml to write back
        # This preserves XML structure better
        tree.write(str(svg_path), encoding="utf-8", xml_declaration=True)

    except Exception as e:
        raise RuntimeError(f"Failed to update SVG file: {e}") from e


def calculate_union_bbox(svg_files: list[Path], verbose: bool = True) -> dict[str, float]:
    """
    Calculate union bounding box across multiple SVG frames.

    This is essential for animation sequences where all frames must share
    the same viewBox to prevent frame-to-frame jumping.

    Args:
        svg_files: List of SVG file paths
        verbose: Whether to print progress messages

    Returns:
        Dict with keys: x, y, width, height representing the union bbox
        that encompasses all frames

    Raises:
        RuntimeError: If bbox calculation fails for any frame
    """
    if verbose:
        print(f"\n   📐 Calculating union bbox across {len(svg_files)} frames...")

    bboxes = []

    # Calculate bbox for each frame
    for i, svg_file in enumerate(svg_files, 1):
        try:
            bbox = calculate_svg_bbox(svg_file)
            bboxes.append(bbox)

            if verbose:
                print(f"      Frame {i:02d}: x={bbox['x']:7.2f}, y={bbox['y']:7.2f}, w={bbox['width']:7.2f}, h={bbox['height']:7.2f}")

        except Exception as e:
            raise RuntimeError(f"Failed to calculate bbox for {svg_file.name}: {e}") from e

    # Calculate union bbox
    # x = minimum x coordinate (can be negative)
    min_x = min(b["x"] for b in bboxes)

    # y = minimum y coordinate (can be negative)
    min_y = min(b["y"] for b in bboxes)

    # width = extent from min_x to furthest right edge
    max_x_extent = max(b["x"] + b["width"] for b in bboxes)
    union_width = max_x_extent - min_x

    # height = extent from min_y to furthest bottom edge
    max_y_extent = max(b["y"] + b["height"] for b in bboxes)
    union_height = max_y_extent - min_y

    union_bbox = {"x": min_x, "y": min_y, "width": union_width, "height": union_height}

    if verbose:
        print(f"\n   ✅ Union bbox: x={union_bbox['x']:.2f}, y={union_bbox['y']:.2f}, width={union_bbox['width']:.2f}, height={union_bbox['height']:.2f}")
        print(f"      This viewBox will be applied to ALL {len(svg_files)} frames\n")

    return union_bbox


def repair_animation_sequence_viewbox(svg_files: list[Path], verbose: bool = True) -> int:
    """
    Repair viewBox for animation sequence using union bbox strategy.

    For animation sequences, all frames MUST have the same viewBox to prevent
    frame-to-frame jumping. This function:
    1. Calculates bbox for each frame
    2. Computes union bbox that encompasses all frames
    3. Applies the SAME viewBox to ALL frames

    Args:
        svg_files: List of SVG file paths (animation frames)
        verbose: Whether to print progress messages

    Returns:
        Number of files that were repaired (had viewBox added/updated)

    Raises:
        RuntimeError: If repair fails
    """
    if verbose:
        print("\n" + "=" * 70)
        print("   🎬 ANIMATION SEQUENCE VIEWBOX REPAIR")
        print("=" * 70)

    # Separate files into those with and without viewBox
    files_with_viewbox = []
    files_without_viewbox = []

    for svg_file in svg_files:
        is_valid, _ = validate_svg_has_viewbox(svg_file)
        if is_valid:
            files_with_viewbox.append(svg_file)
        else:
            files_without_viewbox.append(svg_file)

    if verbose:
        print(f"   Files with viewBox: {len(files_with_viewbox)}")
        print(f"   Files missing viewBox: {len(files_without_viewbox)}")

    # If all files have viewBox, check if they're consistent
    if len(files_without_viewbox) == 0:
        if verbose:
            print("   ✓ All frames have viewBox - checking consistency...")

        # Extract viewBox from each file
        viewboxes = []
        for svg_file in svg_files:
            with open(svg_file, encoding="utf-8") as f:
                content = f.read()
            match = re.search(r'viewBox="([^"]+)"', content)
            if match:
                viewboxes.append(match.group(1))

        # Check if all viewBoxes are identical
        if len(set(viewboxes)) == 1:
            if verbose:
                print(f"   ✅ All frames have identical viewBox: {viewboxes[0]}")
                print("   No repair needed!\n")
            return 0
        else:
            # CRITICAL: Frames have DIFFERENT viewBoxes - MUST repair for animation!
            # Why: Different viewBoxes cause frame-to-frame jumping/scaling issues
            #      Animation frames MUST share the same viewBox
            if verbose:
                print("   ⚠️  Frames have DIFFERENT viewBoxes!")
                for i, vb in enumerate(viewboxes[:5], 1):
                    print(f"      Frame {i}: {vb}")
                if len(viewboxes) > 5:
                    print(f"      ... and {len(viewboxes) - 5} more")
                print("\n   🔧 Calculating union bbox to unify all frames...")
            # Continue to calculate union bbox below (don't return early!)

    # Calculate union bbox across ALL frames (even those with viewBox)
    union_bbox = calculate_union_bbox(svg_files, verbose=verbose)

    # Apply union bbox to ALL frames
    if verbose:
        print("   🔧 Applying union viewBox to all frames...")

    repair_count = 0
    for i, svg_file in enumerate(svg_files, 1):
        try:
            # Always apply union bbox (overwrites existing viewBox if present)
            add_viewbox_to_svg(svg_file, union_bbox)
            repair_count += 1

            if verbose:
                print(f"      ✓ Frame {i:02d}: {svg_file.name}")

        except Exception as e:
            if verbose:
                print(f"      ❌ Frame {i:02d}: {svg_file.name} - {e}")
            raise RuntimeError(f"Failed to repair {svg_file.name}: {e}") from e

    if verbose:
        print(f"\n   ✅ Successfully applied union viewBox to {repair_count} frames!")
        print("=" * 70 + "\n")

    return repair_count


def repair_svg_viewbox(svg_path: Path, verbose: bool = True) -> bool:
    """
    Repair SVG file by calculating and adding missing viewBox attribute.

    Args:
        svg_path: Path to SVG file
        verbose: Whether to print progress messages

    Returns:
        True if viewBox was added/repaired, False if already valid

    Raises:
        RuntimeError: If repair fails
    """
    # Check if viewBox is already present and valid
    is_valid, error_msg = validate_svg_has_viewbox(svg_path)

    if is_valid:
        if verbose:
            print(f"   ✓ {svg_path.name} - viewBox already valid")
        return False

    if verbose:
        print(f"   🔧 {svg_path.name} - Missing viewBox, calculating...")

    # Calculate bounding box
    try:
        bbox = calculate_svg_bbox(svg_path)

        if verbose:
            print(f"      Calculated bbox: x={bbox['x']}, y={bbox['y']}, width={bbox['width']}, height={bbox['height']}")

        # Add viewBox to SVG
        add_viewbox_to_svg(svg_path, bbox)

        # Verify the repair worked
        is_valid, error_msg = validate_svg_has_viewbox(svg_path)
        if not is_valid:
            raise RuntimeError(f"Repair verification failed: {error_msg}")

        if verbose:
            print(f"   ✅ {svg_path.name} - viewBox added successfully!")

        return True

    except Exception as e:
        if verbose:
            print(f"   ❌ {svg_path.name} - Repair failed: {e}")
        raise RuntimeError(f"Failed to repair {svg_path.name}: {e}") from e


def validate_svg_numbering(svg_files: list[Path]) -> tuple[bool, str]:
    """
    Validate that SVG files are numbered sequentially starting from 1.

    Args:
        svg_files: List of SVG file paths (must be sorted)

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Extract numbers from filenames
    number_pattern = re.compile(r"(\d+)")

    for i, svg_file in enumerate(svg_files):
        expected_num = i + 1

        # Find all numbers in filename
        numbers = number_pattern.findall(svg_file.stem)

        if not numbers:
            return (
                False,
                f"Frame {expected_num}: No number found in filename '{svg_file.name}'",
            )

        # Get the last number (most likely to be the frame number)
        actual_num_str = numbers[-1]
        actual_num = int(actual_num_str)

        if actual_num != expected_num:
            return False, (f"Frame {expected_num}: Expected frame number {expected_num}, found {actual_num} in '{svg_file.name}'")

    return True, ""


def detect_has_numerical_suffix(filename: str) -> bool:
    """
    Detect if a filename has a proper numerical suffix matching svg2fbf format.

    Format: filename_NNNNN.svg (where N is a digit, exactly 5 digits required)

    Args:
        filename: Filename to check (e.g., "frame_00001.svg")

    Returns:
        True if filename has proper numerical suffix, False otherwise

    Examples:
        "frame_00001.svg" -> True
        "paul02_00001.svg" -> True
        "frame.svg" -> False
        "frame001.svg" -> False (no underscore separator)
        "frame_abc.svg" -> False (not numerical)
        "test_3.svg" -> False (only 1 digit, not 5)
    """
    # Pattern: _NNNNN.svg where exactly 5 digits after underscore
    # Why 5 digits: This is the svg2fbf standard format (e.g., _00001, _00002)
    pattern = re.compile(r"_(\d{5})\.svg$")
    return bool(pattern.search(filename))


def extract_suffix_number(filename: str) -> int | None:
    """
    Extract the numerical suffix from a filename if it exists.

    Args:
        filename: Filename (e.g., "frame_00001.svg")

    Returns:
        Suffix number as int, or None if no valid suffix

    Examples:
        "frame_00001.svg" -> 1
        "paul02_00123.svg" -> 123
        "frame.svg" -> None
        "test_3.svg" -> None (only 1 digit, not 5)
    """
    # Pattern: _NNNNN.svg where exactly 5 digits after underscore
    pattern = re.compile(r"_(\d{5})\.svg$")
    match = pattern.search(filename)
    if match:
        return int(match.group(1))
    return None


# ============================================================================
# CANDIDATES LADDER - Central constants for deterministic frame numbering
# ============================================================================


# Priority base values - lower value = higher priority for frame number assignment
# These constants provide a single source of truth for the candidates ladder system
class FrameNumberPriority:
    """
    Priority levels for frame number candidates ladder.

    Lower values indicate higher priority for frame number assignment.
    Each priority range represents a different naming pattern quality.
    """

    # Perfect format: underscore separator with .svg extension (_00035.svg)
    UNDERSCORE_SVG = 0

    # Dash separator with .svg extension (-00035.svg)
    DASH_SVG = 100

    # Underscore with extra extensions (_.bak.svg, _.old.svg, _.svg.svg)
    UNDERSCORE_EXTRA_EXT = 200

    # Dash with extra extensions (-.bak.svg, -.old.svg, -.svg.svg)
    DASH_EXTRA_EXT = 230

    # Dot separator (.NNNNN.svg)
    DOT_SVG = 300

    # Number at start (NNNNN.svg)
    START_NUMBER = 400

    # Brackets (_[NNNNN].svg, -[NNNNN].svg, etc.)
    BRACKETS = 500

    # Embedded numbers (any number in filename - lowest priority)
    EMBEDDED = 600


# Priority adjustments based on digit count
# Ideal: 5 digits (00001-99999) matches svg2fbf standard format
class DigitCountAdjustment:
    """Priority adjustments based on number of digits in frame number."""

    FIVE_DIGITS = 0  # Perfect: 00035
    FOUR_DIGITS = 1  # Good: 0035
    THREE_DIGITS = 2  # OK: 035
    TWO_DIGITS = 3  # Minimal: 35
    ONE_DIGIT = 4  # Very minimal: 5
    SIX_DIGITS = 5  # One extra: 000035
    SEVEN_DIGITS = 6  # Two extra: 0000035
    OTHER = 7  # Unusual digit count


# Collision resolution constants
# When multiple files have the same name, we add a deterministic suffix to
# preserve alphabetical ordering
FBFTEST_SUFFIX_PATTERN = re.compile(r"___FBFTEST\[\d+\]___")  # Pattern to detect/strip suffix
# Format for adding suffix: ___FBFTEST[0]___, ___FBFTEST[1]___, etc.
FBFTEST_SUFFIX_FORMAT = "___FBFTEST[{}]___"


# Compiled regex patterns for frame number extraction
# Each pattern is compiled once at module load for performance
# Format: (compiled_pattern, base_priority, description)
FRAME_NUMBER_PATTERNS = [
    # ===== Priority 0-99: Underscore separator with .svg extension =====
    (
        re.compile(r"_(\d+)\.svg$"),
        FrameNumberPriority.UNDERSCORE_SVG,
        "underscore_.svg",
    ),
    # ===== Priority 100-199: Dash separator with .svg extension =====
    (re.compile(r"-(\d+)\.svg$"), FrameNumberPriority.DASH_SVG, "dash-.svg"),
    # ===== Priority 200-299: Underscore with extra extensions =====
    (
        re.compile(r"_(\d+)\.bak\.svg$"),
        FrameNumberPriority.UNDERSCORE_EXTRA_EXT,
        "underscore_.bak.svg",
    ),
    (
        re.compile(r"_(\d+)\.old\.svg$"),
        FrameNumberPriority.UNDERSCORE_EXTRA_EXT + 10,
        "underscore_.old.svg",
    ),
    (
        re.compile(r"_(\d+)\.svg\.svg$"),
        FrameNumberPriority.UNDERSCORE_EXTRA_EXT + 20,
        "underscore_.svg.svg",
    ),
    # ===== Priority 230-299: Dash with extra extensions =====
    (
        re.compile(r"-(\d+)\.bak\.svg$"),
        FrameNumberPriority.DASH_EXTRA_EXT,
        "dash-.bak.svg",
    ),
    (
        re.compile(r"-(\d+)\.old\.svg$"),
        FrameNumberPriority.DASH_EXTRA_EXT + 10,
        "dash-.old.svg",
    ),
    (
        re.compile(r"-(\d+)\.svg\.svg$"),
        FrameNumberPriority.DASH_EXTRA_EXT + 20,
        "dash-.svg.svg",
    ),
    # ===== Priority 300-399: Dot separator =====
    (re.compile(r"\.(\d+)\.svg$"), FrameNumberPriority.DOT_SVG, "dot.NNNNN.svg"),
    (
        re.compile(r"\.(\d+)\.bak\.svg$"),
        FrameNumberPriority.DOT_SVG + 10,
        "dot.NNNNN.bak.svg",
    ),
    (
        re.compile(r"\.(\d+)\.old\.svg$"),
        FrameNumberPriority.DOT_SVG + 20,
        "dot.NNNNN.old.svg",
    ),
    (
        re.compile(r"\.(\d+)\.svg\.svg$"),
        FrameNumberPriority.DOT_SVG + 30,
        "dot.NNNNN.svg.svg",
    ),
    # ===== Priority 400-499: Number at start (NNNNN.svg) =====
    (re.compile(r"^(\d+)\.svg$"), FrameNumberPriority.START_NUMBER, "start_NNNNN.svg"),
    (
        re.compile(r"^(\d+)\.bak\.svg$"),
        FrameNumberPriority.START_NUMBER + 10,
        "start_NNNNN.bak.svg",
    ),
    (
        re.compile(r"^(\d+)\.old\.svg$"),
        FrameNumberPriority.START_NUMBER + 20,
        "start_NNNNN.old.svg",
    ),
    (
        re.compile(r"^(\d+)\.svg\.svg$"),
        FrameNumberPriority.START_NUMBER + 30,
        "start_NNNNN.svg.svg",
    ),
    # ===== Priority 500-599: Brackets =====
    (
        re.compile(r"_\[(\d+)\]\.svg$"),
        FrameNumberPriority.BRACKETS,
        "underscore_[NNNNN].svg",
    ),
    (
        re.compile(r"-\[(\d+)\]\.svg$"),
        FrameNumberPriority.BRACKETS + 10,
        "dash-[NNNNN].svg",
    ),
    (
        re.compile(r"\.\[(\d+)\]\.svg$"),
        FrameNumberPriority.BRACKETS + 20,
        "dot.[NNNNN].svg",
    ),
    (
        re.compile(r"^\[(\d+)\]\.svg$"),
        FrameNumberPriority.BRACKETS + 30,
        "start_[NNNNN].svg",
    ),
    (
        re.compile(r"_\[(\d+)\]"),
        FrameNumberPriority.BRACKETS + 40,
        "underscore_[NNNNN]_name.svg",
    ),
    (
        re.compile(r"-\[(\d+)\]"),
        FrameNumberPriority.BRACKETS + 50,
        "dash-[NNNNN]-name.svg",
    ),
    (re.compile(r"\[(\d+)\]"), FrameNumberPriority.BRACKETS + 60, "[NNNNN]name.svg"),
    # ===== Priority 600+: Embedded numbers (lowest priority - catches any number) =====
    (re.compile(r"(\d+)"), FrameNumberPriority.EMBEDDED, "embedded_number"),
]


def get_exact_file_size(file_path: Path) -> int:
    """
    Get exact file size in bytes, regardless of filesystem block granularity.

    Args:
        file_path: Path to file

    Returns:
        Exact size in bytes

    Raises:
        OSError: If file cannot be accessed
    """
    return file_path.stat().st_size


def update_svg_dependency_references(svg_path: Path, reference_mapping: dict[str, str], encoding: str = "utf-8") -> None:
    """
    Update dependency references in SVG file content.

    This function replaces all occurrences of original dependency filenames
    with their UUID-prefixed equivalents in the SVG content.

    Handles various SVG reference formats:
    - href="path/to/file.png"
    - xlink:href="path/to/file.png"
    - url(path/to/file.woff)
    - @import url(path/to/file.css)

    Args:
        svg_path: Path to SVG file to update
        reference_mapping: Dict mapping original filename → UUID-prefixed filename
                          Example: {"font.woff": "abc123-uuid_font.woff"}
        encoding: File encoding (default: utf-8)

    Raises:
        OSError: If file cannot be read/written
        UnicodeDecodeError: If encoding is incorrect

    Example:
        >>> mapping = {"tahoma.woff": "a1b2c3_tahoma.woff"}
        >>> update_svg_dependency_references(svg_path, mapping)

        Before: <text font-family="url(fonts/tahoma.woff)">
        After:  <text font-family="url(fonts/a1b2c3_tahoma.woff)">
    """
    if not reference_mapping:
        return  # Nothing to update

    # Read SVG content
    try:
        with open(svg_path, encoding=encoding) as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise RuntimeError(f"Failed to read SVG file '{svg_path}': {e}") from e

    # Replace all references
    # We need to be careful to replace the most specific paths first to avoid
    # partial replacements
    # Sort by length (longest first) to ensure "fonts/tahoma.woff" is replaced
    # before "tahoma.woff"
    sorted_refs = sorted(reference_mapping.items(), key=lambda x: len(x[0]), reverse=True)

    original_content = content
    for original_ref, new_ref in sorted_refs:
        # Replace in content (case-sensitive, whole occurrences only)
        content = content.replace(original_ref, new_ref)

    # Only write if content changed
    if content != original_content:
        try:
            with open(svg_path, "w", encoding=encoding) as f:
                f.write(content)
        except OSError as e:
            raise RuntimeError(f"Failed to write updated SVG file '{svg_path}': {e}") from e


def resolve_filename_collisions(
    files_to_copy: list[tuple[Path, str]],
    svg_dependencies: dict[Path, set[Path]] | None = None,
    svg_original_references: dict[Path, dict[Path, str]] | None = None,
) -> tuple[dict[Path, str], dict[Path, str], dict[Path, dict[str, str]]]:
    """
    Resolve filename collisions using UUID-based dependency isolation.

    This function implements the correct UUID architecture:
    1. Generate a unique UUID for EACH root SVG file
    2. ALL dependencies for that SVG get that UUID as a SUFFIX (not prefix)
    3. Format: originalname_<uuid>.extension
    4. SVG files with same name get a deterministic ___FBFTEST[n]___ suffix
       based on file size

    UUID Architecture:
    - Each root SVG gets a unique UUID (8 chars from uuid.uuid4())
    - ALL dependencies of that SVG are renamed with UUID suffix
    - Format: filename_<uuid>.extension (e.g., Blocky_abc123de.woff)
    - This ensures complete isolation between different SVGs' dependencies
    - Even if no collision exists, dependencies ALWAYS get UUID suffix

    Args:
        files_to_copy: List of (source_path, dest_name) tuples
        svg_dependencies: Optional dict mapping SVG Path → set of dependency Paths
        svg_original_references: Optional dict mapping SVG Path →
            {dependency_path: original_ref_string}
            Example: {svg_path: {Path("/path/font.woff"): "../fonts/font.woff"}}

    Returns:
        Tuple of (resolved_names, svg_uuids, svg_reference_mappings):
        - resolved_names: Dict mapping source_path → collision-resolved dest_name
        - svg_uuids: Dict mapping SVG source_path → UUID string
        - svg_reference_mappings: Dict mapping SVG source_path →
            {original_ref: uuid_suffixed_ref}

    Raises:
        TypeError: If files_to_copy is not a list of tuples
        ValueError: If input validation fails

    Example:
        Input:
            files_to_copy = [
                (Path("/a/frame.svg"), "frame.svg"),
                (Path("/a/font.woff"), "fonts/font.woff"),  # Dep of /a/frame.svg
                (Path("/b/frame.svg"), "frame.svg"),  # Collision!
                # Dep of /b/frame.svg, same name!
                (Path("/b/font.woff"), "fonts/font.woff"),
            ]

            svg_dependencies = {
                Path("/a/frame.svg"): {Path("/a/font.woff")},
                Path("/b/frame.svg"): {Path("/b/font.woff")},
            }

        Output:
            resolved_names = {
                Path("/a/frame.svg"): "frame.svg",  # Larger SVG
                # UUID suffix from /a/frame.svg
                Path("/a/font.woff"): "fonts/font_abc123de.woff",
                Path("/b/frame.svg"): "frame___FBFTEST[1]___.svg",  # Smaller SVG
                # UUID suffix from /b/frame.svg
                Path("/b/font.woff"): "fonts/font_def456ab.woff",
            }

            svg_uuids = {
                Path("/a/frame.svg"): "abc123de",
                Path("/b/frame.svg"): "def456ab",
            }

            svg_reference_mappings = {
                Path("/a/frame.svg"): {"fonts/font.woff": "fonts/font_abc123de.woff"},
                Path("/b/frame.svg"): {"fonts/font.woff": "fonts/font_def456ab.woff"},
            }
    """
    # Input validation
    if not isinstance(files_to_copy, list):
        raise TypeError(f"files_to_copy must be a list, got {type(files_to_copy).__name__}")

    if not files_to_copy:
        return {}, {}, {}

    # Validate structure
    for i, item in enumerate(files_to_copy):
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError(f"files_to_copy[{i}] must be a tuple of (Path, str), got {type(item).__name__}")

        source_path, dest_name = item
        if not isinstance(source_path, Path):
            raise TypeError(f"files_to_copy[{i}][0] must be a Path, got {type(source_path).__name__}")

        if not isinstance(dest_name, str):
            raise TypeError(f"files_to_copy[{i}][1] must be a str, got {type(dest_name).__name__}")

        if not source_path.exists():
            raise ValueError(f"Source file does not exist: {source_path}")

    # === STEP 1: Separate root SVGs from dependency SVGs ===
    # Root SVGs are those NOT in any dependency set
    all_dependency_paths: set[Path] = set()
    if svg_dependencies:
        for deps in svg_dependencies.values():
            all_dependency_paths.update(deps)

    root_svgs = [(src, dest) for src, dest in files_to_copy if dest.endswith(".svg") and src not in all_dependency_paths]
    dependency_svgs = [(src, dest) for src, dest in files_to_copy if dest.endswith(".svg") and src in all_dependency_paths]
    non_svg_deps = [(src, dest) for src, dest in files_to_copy if not dest.endswith(".svg")]

    # Generate UUIDs for root SVGs only
    svg_uuids: dict[Path, str] = {}
    for source_path, _ in root_svgs:
        # Generate unique UUID for this SVG (8 characters is sufficient)
        svg_uuid = uuid.uuid4().hex[:8]
        svg_uuids[source_path] = svg_uuid

    result: dict[Path, str] = {}
    svg_reference_mappings: dict[Path, dict[str, str]] = {}

    # === STEP 2: Handle ALL dependencies (both SVG and non-SVG) with UUID suffixing ===
    # ALL dependencies get UUID suffix, regardless of collision
    all_dependencies = dependency_svgs + non_svg_deps  # Combine both types

    if svg_dependencies:
        # Build reverse mapping: dependency → SVG(s) that reference it
        dep_to_svg: dict[Path, list[Path]] = defaultdict(list)
        for svg_path, deps in svg_dependencies.items():
            for dep_path in deps:
                dep_to_svg[dep_path].append(svg_path)

        for source_path, dest_name in all_dependencies:
            # Find which SVG(s) reference this dependency
            parent_svgs = dep_to_svg.get(source_path, [])

            if parent_svgs:
                # Use first parent SVG's UUID (deterministic)
                # Sort parent SVGs by path for determinism if multiple parents
                parent_svgs.sort(key=str)
                parent_svg = parent_svgs[0]
                parent_uuid = svg_uuids.get(parent_svg)

                if parent_uuid:
                    # Apply UUID suffix to dependency
                    # Format: path/to/filename_<uuid>.extension
                    dest_path = Path(dest_name)
                    stem = dest_path.stem  # Filename without extension
                    suffix = dest_path.suffix  # Extension including dot

                    # Handle fragment identifiers (e.g., SVGFreeSans.svg#ascii)
                    if "#" in suffix:
                        # Split extension and fragment
                        ext_parts = suffix.split("#", 1)
                        base_suffix = ext_parts[0]
                        fragment = "#" + ext_parts[1]
                        suffixed_name = f"{stem}_{parent_uuid}{base_suffix}{fragment}"
                    else:
                        suffixed_name = f"{stem}_{parent_uuid}{suffix}"

                    new_dest_name = str(dest_path.parent / suffixed_name)

                    result[source_path] = new_dest_name

                    # Track reference mapping for SVG content update
                    # Map original reference to new UUID-suffixed reference
                    # WHY: We need to use the ACTUAL reference string from the SVG
                    # file, not the dest_name which may differ (e.g.,
                    # "../resources/file.svg" vs "fonts/file.svg")
                    if parent_svg not in svg_reference_mappings:
                        svg_reference_mappings[parent_svg] = {}

                    # Find the original reference string for this dependency
                    original_ref = None
                    if svg_original_references and parent_svg in svg_original_references:
                        original_ref = svg_original_references[parent_svg].get(source_path)

                    if original_ref:
                        # Use actual reference string from SVG file
                        # This handles cases like "../resources/SVGFreeSans.svg#ascii"
                        svg_reference_mappings[parent_svg][original_ref] = new_dest_name
                    else:
                        # Fallback: use dest_name (for backward compatibility)
                        svg_reference_mappings[parent_svg][dest_name] = new_dest_name
                else:
                    # Parent SVG not found (shouldn't happen), keep original
                    result[source_path] = dest_name
            else:
                # No parent SVG found, keep original name
                result[source_path] = dest_name
    else:
        # No dependency tracking, keep original names for all dependencies
        for source_path, dest_name in all_dependencies:
            result[source_path] = dest_name

    # === STEP 3: Handle root SVG files with collision resolution ===
    # Group root SVG files by destination name (dependencies already handled in STEP 2)
    svg_groups: dict[str, list[tuple[Path, int]]] = defaultdict(list)

    for source_path, dest_name in root_svgs:
        # Get exact file size in bytes (not filesystem blocks)
        file_size = get_exact_file_size(source_path)
        svg_groups[dest_name].append((source_path, file_size))

    # Process each group
    for dest_name, files_in_group in svg_groups.items():
        if len(files_in_group) == 1:
            # No collision - keep original name
            source_path, _ = files_in_group[0]
            result[source_path] = dest_name
        else:
            # Collision detected - apply deterministic resolution
            # Sort by file size (largest first) for deterministic ordering
            # If sizes are equal, use source path as tiebreaker for determinism
            files_in_group.sort(key=lambda x: (-x[1], str(x[0])))

            # Add ___FBFTEST[n]___ suffix to all files in collision group
            # Position 0 = largest file (keeps original name)
            for position, (source_path, _file_size) in enumerate(files_in_group):
                if position == 0:
                    # Largest file keeps original name
                    result[source_path] = dest_name
                else:
                    # Smaller files get suffix
                    # Insert suffix before .svg extension
                    base_name = dest_name[:-4]  # Remove .svg
                    suffix = FBFTEST_SUFFIX_FORMAT.format(position)
                    new_name = f"{base_name}{suffix}.svg"
                    result[source_path] = new_name

    return result, svg_uuids, svg_reference_mappings


def _calculate_priority_adjustment(digit_count: int) -> int:
    """
    Calculate priority adjustment based on digit count.

    svg2fbf standard format uses 5 digits (00001-99999).
    Files closer to this format get lower (better) priority adjustment.

    Args:
        digit_count: Number of digits in the frame number

    Returns:
        Priority adjustment value (0 = perfect, higher = worse)
    """
    if digit_count == 5:
        return DigitCountAdjustment.FIVE_DIGITS
    elif digit_count == 4:
        return DigitCountAdjustment.FOUR_DIGITS
    elif digit_count == 3:
        return DigitCountAdjustment.THREE_DIGITS
    elif digit_count == 2:
        return DigitCountAdjustment.TWO_DIGITS
    elif digit_count == 1:
        return DigitCountAdjustment.ONE_DIGIT
    elif digit_count == 6:
        return DigitCountAdjustment.SIX_DIGITS
    elif digit_count == 7:
        return DigitCountAdjustment.SEVEN_DIGITS
    else:
        return DigitCountAdjustment.OTHER


# ============================================================================
# DETERMINISTIC FRAME NUMBERING - Candidates Ladder Implementation
# ============================================================================


def extract_number_candidates_from_filename(filename: str) -> list[tuple[int, int]]:
    """
    Extract all possible frame numbers from filename with priority scores.

    Uses the candidates ladder priority system to rank different naming patterns.
    Lower priority score = higher priority for frame number assignment.

    **CRITICAL:** This function strips the ___FBFTEST[n]___ collision resolution
    suffix before pattern matching. This ensures that files like
    "frame_00007___FBFTEST[2]___.svg" are correctly identified as frame 7
    candidates, not frame 2 candidates.

    Priority levels (lower = better):
    - 0-99: Underscore separator (_NNNNN.svg)
    - 100-199: Dash separator (-NNNNN.svg)
    - 200-299: Extra extensions (.bak.svg, .old.svg, .svg.svg)
    - 300-399: Dot separator (.NNNNN.svg)
    - 400-499: Number at start (NNNNN.svg)
    - 500-599: Brackets (_[NNNNN].svg)
    - 600+: Embedded numbers (lowest priority)

    Args:
        filename: Filename to analyze
            (e.g., "frame_0035.svg", "myframe07___FBFTEST[1]___.svg")

    Returns:
        List of (number, priority_score) tuples. Empty list if no numbers found.

    Raises:
        TypeError: If filename is not a string
        ValueError: If filename is empty or invalid

    Examples:
        >>> extract_number_candidates_from_filename("frame_00035.svg")
        [(35, 0)]  # Top priority: 5 digits with underscore

        >>> extract_number_candidates_from_filename("frame_00035___FBFTEST[2]___.svg")
        [(35, 0)]  # FBFTEST suffix ignored for pattern matching

        >>> extract_number_candidates_from_filename("frame-00035.svg")
        [(35, 100)]  # Dash separator
    """
    # Input validation (fail-fast pattern)
    if not isinstance(filename, str):
        raise TypeError(f"filename must be a string, got {type(filename).__name__}")

    if not filename:
        raise ValueError("filename cannot be empty")

    if not filename.endswith(".svg"):
        raise ValueError(f"filename must end with .svg, got '{filename}'")

    # CRITICAL: Strip collision resolution suffix before pattern matching
    # This ensures "frame_00007___FBFTEST[2]___.svg" is seen as "frame_00007.svg"
    # for frame number extraction, not confused with frame 2
    filename_for_matching = FBFTEST_SUFFIX_PATTERN.sub("", filename)

    candidates = []

    # Apply all patterns from central constants
    # Patterns are pre-compiled at module load for performance
    for compiled_pattern, base_priority, _description in FRAME_NUMBER_PATTERNS:
        for match in compiled_pattern.finditer(filename_for_matching):
            number_str = match.group(1)
            number = int(number_str)

            # Calculate priority adjustment based on digit count
            digit_count = len(number_str)
            priority_adj = _calculate_priority_adjustment(digit_count)

            final_priority = base_priority + priority_adj
            candidates.append((number, final_priority))

    # Remove duplicates, keeping the best (lowest) priority for each number
    # Why: A file like "035_frame_077.svg" matches multiple patterns
    number_to_priority: dict[int, int] = {}
    for num, priority in candidates:
        if num not in number_to_priority or priority < number_to_priority[num]:
            number_to_priority[num] = priority

    return list(number_to_priority.items())


def build_candidates_ladder(files: list[Path]) -> dict[int, list[Path]]:
    """
    Build candidates ladder mapping frame numbers to priority-ordered file lists.

    The ladder is a dict where:
    - Key: frame number (1 to len(files))
    - Value: list of Path objects in priority order (best candidate first)

    For each frame number, we find all files that could be candidates
    (files that have that number in their name) and order them by priority.

    Files can appear in multiple frame numbers' candidate lists - this is NORMAL.
    The assignment algorithm will resolve this deterministically.

    Args:
        files: List of SVG file paths (must be non-empty)

    Returns:
        Candidates ladder dict mapping frame number → priority-ordered file list

    Raises:
        TypeError: If files is not a list or contains non-Path objects
        ValueError: If files list is empty or contains non-SVG files

    Example:
        >>> files = [Path("frame_00007.svg"), Path("myframe07.svg"), Path("other.svg")]
        >>> ladder = build_candidates_ladder(files)
        >>> ladder[7]
        [Path("frame_00007.svg"), Path("myframe07.svg")]  # Ordered by priority
    """
    # Input validation (fail-fast pattern)
    if not isinstance(files, list):
        raise TypeError(f"files must be a list, got {type(files).__name__}")

    if not files:
        raise ValueError("files list cannot be empty")

    # Validate all items are Path objects pointing to .svg files
    for i, file in enumerate(files):
        if not isinstance(file, Path):
            raise TypeError(f"files[{i}] must be a Path object, got {type(file).__name__}")

        if not file.name.endswith(".svg"):
            raise ValueError(f"files[{i}] must be an SVG file, got '{file.name}'")

    ladder = defaultdict(list)

    # Extract candidates from each file
    # This maps each file to its list of (frame_number, priority) candidates
    file_candidates: dict[Path, list[tuple[int, int]]] = {}
    for file in files:
        try:
            candidates = extract_number_candidates_from_filename(file.name)
            file_candidates[file] = candidates
        except (TypeError, ValueError):
            # If filename extraction fails, file gets no candidates
            # This is OK - file will be assigned in second pass of assignment algorithm
            file_candidates[file] = []

    # For each possible frame number (1 to total file count)
    for frame_num in range(1, len(files) + 1):
        # Find all files that could be candidates for this number
        candidates_for_num: list[tuple[int, Path]] = []

        for file, file_cands in file_candidates.items():
            # Check if this file has frame_num as a candidate
            for num, priority in file_cands:
                if num == frame_num:
                    candidates_for_num.append((priority, file))
                    break  # Only add file once per frame number

        # Sort by priority (lower is better), then alphabetically as tiebreaker
        # IMPORTANT: Alphabetical tiebreaker ensures determinism when multiple files
        # have the same priority for a given frame number
        candidates_for_num.sort(key=lambda x: (x[0], x[1].name))
        ladder[frame_num] = [file for _, file in candidates_for_num]

    return dict(ladder)


def assign_numbers_deterministically(files: list[Path]) -> dict[Path, int]:
    """
    Assign frame numbers to files using the candidates ladder for deterministic
    assignment.

    This ensures that:
    1. Files always get the same number regardless of argument order
    2. Existing numbering is preserved when possible
    3. Files with number hints in their names get the appropriate numbers

    Algorithm:
    1. Build candidates ladder mapping frame numbers → priority-ordered file lists
    2. For each frame number (1 to N) in sequence:
       - Check the candidates priority list for that number
       - Assign to the first unassigned candidate
    3. For remaining files (no number hints or all hints already assigned):
       - Assign to remaining frame numbers in sequential order

    Args:
        files: List of SVG file paths (must be non-empty, no duplicates)

    Returns:
        Dict mapping Path → assigned frame number (1-indexed)

    Raises:
        TypeError: If files is not a list or contains non-Path objects
        ValueError: If files list is empty, has duplicates, or contains non-SVG files

    Example:
        >>> files = [Path("other.svg"), Path("frame_00007.svg"), Path("myframe08.svg")]
        >>> result = assign_numbers_deterministically(files)
        >>> result
        {
            Path("frame_00007.svg"): 7,  # Gets 7 (best candidate for 7)
            Path("myframe08.svg"): 8,     # Gets 8 (best candidate for 8)
            Path("other.svg"): 1          # Gets 1 (no hints, first available)
        }
    """
    # Input validation (fail-fast pattern)
    if not isinstance(files, list):
        raise TypeError(f"files must be a list, got {type(files).__name__}")

    if not files:
        raise ValueError("files list cannot be empty")

    # Validate all items are Path objects pointing to .svg files
    for i, file in enumerate(files):
        if not isinstance(file, Path):
            raise TypeError(f"files[{i}] must be a Path object, got {type(file).__name__}")

        if not file.name.endswith(".svg"):
            raise ValueError(f"files[{i}] must be an SVG file, got '{file.name}'")

    # Check for duplicates (fail-fast)
    # Why: Duplicate paths would cause ambiguous assignments
    seen_paths = set()
    for i, file in enumerate(files):
        if file in seen_paths:
            raise ValueError(f"Duplicate file path at index {i}: {file}")
        seen_paths.add(file)

    # Build the candidates ladder
    ladder = build_candidates_ladder(files)

    assignments: dict[Path, int] = {}
    assigned_files: set[Path] = set()
    assigned_numbers: set[int] = set()

    # First pass: assign based on ladder priorities
    #
    # IMPORTANT: Files can appear in multiple keys' candidate lists - this is
    # NORMAL and EXPECTED!
    # Example: "035_filename_077.svg" appears in BOTH key 35 and key 77
    # candidates lists.
    #
    # The algorithm answers for each key K: "Which unassigned file is most
    # likely intended for frame K?"
    # We only exclude files that are ALREADY ASSIGNED to a frame number.
    #
    # Process:
    # - For each frame number K (in order: 1, 2, 3, ..., N)
    # - Look at K's priority-ordered candidate list
    # - Pick the first candidate that is NOT YET ASSIGNED
    # - Assign it to frame K
    # - Mark it as assigned (unavailable for remaining keys)
    #
    # This reduces guessing errors: "myframe024.svg" → frame 24 (likely), not frame 40
    for frame_num in range(1, len(files) + 1):
        candidates = ladder.get(frame_num, [])
        for candidate in candidates:
            if candidate not in assigned_files:  # ← Only criterion: not already assigned
                # Found an unassigned candidate for this number
                assignments[candidate] = frame_num
                assigned_files.add(candidate)
                assigned_numbers.add(frame_num)
                break

    # Second pass: assign remaining files to remaining numbers
    # These are files with no number hints or files whose hints were already taken
    remaining_files = [f for f in files if f not in assigned_files]
    remaining_numbers = sorted([n for n in range(1, len(files) + 1) if n not in assigned_numbers])

    # Assign in order (deterministic because files list order is preserved)
    for file, num in zip(remaining_files, remaining_numbers, strict=False):
        assignments[file] = num
        assigned_files.add(file)
        assigned_numbers.add(num)

    return assignments


def autonumber_svg_files(folder_path: Path) -> dict[str, str]:
    """
    Auto-number SVG files that don't have proper numerical suffixes.

    Algorithm:
    1. Sort all SVG files by name (natural sort, like `ls`)
    2. Identify files WITHOUT proper suffix (_NNNNN.svg format)
    3. Collect all existing suffix numbers to avoid collisions
    4. For each file without suffix:
       - Start with position number (1, 2, 3, ...)
       - If that number is already used, increment until finding free number
       - Rename file: "filename.svg" -> "filename_NNNNN.svg"
    5. Files with proper suffix remain unchanged
    6. **Gap Detection & Fix**:
       - After initial renaming, check if sequence has gaps (missing numbers)
       - If gaps found (e.g., 00002, 00004, 00007 - missing 1, 3, 5, 6):
         * Renumber ALL files sequentially: 00001, 00002, 00003
         * Preserves sort order, just fills gaps

    Args:
        folder_path: Path to folder containing SVG files

    Returns:
        Dict mapping old filename -> new filename (only renamed files)

    Examples:
        Input files (sorted):
          00r.svg, 01k.svg, paul02_00001.svg, wipers.svg

        After initial renaming:
          00r_00001.svg, 01k_00002.svg, paul02_00001.svg (unchanged), wipers_00003.svg

        Gap detected! (missing nothing in this case, but if there were gaps...)

        Example with gaps:
          Input: file_00002.svg, file_00005.svg (missing 1, 3, 4)
          Output: file_00001.svg, file_00002.svg (renumbered sequentially)
    """
    # Find all SVG files and sort naturally (like `ls`)
    svg_files = sorted(folder_path.glob("*.svg"))

    if not svg_files:
        return {}

    # Collect existing suffix numbers to avoid collisions
    used_numbers: set[int] = set()
    files_with_suffix: set[str] = set()
    files_without_suffix: list[Path] = []

    for svg_file in svg_files:
        if detect_has_numerical_suffix(svg_file.name):
            suffix_num = extract_suffix_number(svg_file.name)
            if suffix_num is not None:
                used_numbers.add(suffix_num)
                files_with_suffix.add(svg_file.name)
        else:
            files_without_suffix.append(svg_file)

    # Track renames
    renames: dict[str, str] = {}

    # Auto-number files without suffix
    next_candidate = 1  # Start numbering from 1

    for svg_file in files_without_suffix:
        # Find next available number
        while next_candidate in used_numbers:
            next_candidate += 1

        # Use this number for current file
        base_name = svg_file.stem  # filename without .svg
        new_name = f"{base_name}_{next_candidate:05d}.svg"
        new_path = folder_path / new_name

        # Perform rename
        svg_file.rename(new_path)

        # Track the rename
        renames[svg_file.name] = new_name

        # Mark this number as used
        used_numbers.add(next_candidate)
        next_candidate += 1

    # ============================================================================
    # STEP 2: Gap Detection and Sequential Renumbering
    # ============================================================================
    # ALWAYS check for gaps in the sequence, regardless of whether files
    # were renamed in step 1 or not. This ensures sequences like
    # 00001, 00002, 00004, 00005 get renumbered to 00001, 00002, 00003, 00004

    # Re-scan folder to get all SVG files (including newly renamed ones)
    # IMPORTANT: Keep natural filename order (like `ls`)
    all_svg_files = sorted(folder_path.glob("*.svg"))

    # Extract all suffix numbers IN FILENAME ORDER
    # We want to check if the i-th file has suffix i (1, 2, 3, ...)
    file_numbers: list[tuple[Path, int]] = []
    for svg_file in all_svg_files:
        suffix_num = extract_suffix_number(svg_file.name)
        if suffix_num is not None:
            file_numbers.append((svg_file, suffix_num))

    # DO NOT sort by suffix! We need to preserve filename order.
    # Check if suffixes are sequential: position 1 should have suffix 1, etc.
    needs_renumbering = False
    for position, (_svg_file, suffix_num) in enumerate(file_numbers, start=1):
        if suffix_num != position:
            needs_renumbering = True
            break

    if needs_renumbering:
        # Gaps detected! Renumber ALL files sequentially to fill gaps
        for position, (svg_file, old_number) in enumerate(file_numbers, start=1):
            if old_number != position:
                # Need to renumber this file
                base_name = svg_file.stem.rsplit("_", 1)[0]  # Remove old suffix
                new_name = f"{base_name}_{position:05d}.svg"
                new_path = folder_path / new_name

                # Perform rename
                old_name = svg_file.name
                svg_file.rename(new_path)

                # Track the rename (update if already in renames dict)
                if old_name in renames.values():
                    # This file was already renamed in step 1, update the mapping
                    for orig_name, renamed in list(renames.items()):
                        if renamed == old_name:
                            renames[orig_name] = new_name
                            break
                else:
                    # This file had a suffix originally but needs renumbering
                    renames[old_name] = new_name

    return renames


def extract_reference_strings(svg_path: Path, dependency_paths: set[Path], encoding: str = "utf-8") -> dict[Path, str]:
    """
    Extract the original reference strings that point to each dependency.

    This function scans the SVG file content to find the exact reference strings
    used to reference each dependency file. These original strings are needed
    to update SVG references when dependencies are renamed with UUID suffixes.

    Args:
        svg_path: Path to SVG file
        dependency_paths: Set of dependency file paths (absolute)
        encoding: File encoding to use when reading SVG (default: utf-8)

    Returns:
        Dict mapping dependency_path -> original_reference_string
        Example: {Path("/path/to/font.woff"): "../fonts/font.woff"}
        Example: {Path("/path/to/font.svg"): "../resources/SVGFreeSans.svg#ascii"}

    Note:
        - Returns FULL original reference including fragment identifiers
        - Only returns references that resolve to known dependencies
        - Handles relative paths correctly
    """
    ref_strings: dict[Path, str] = {}

    try:
        # Read SVG content as text
        try:
            content = svg_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            # Fallback to latin-1 if UTF-8 fails
            content = svg_path.read_text(encoding="latin-1")
        except Exception:
            return ref_strings

        # Same patterns as extract_svg_dependencies
        patterns = [
            r'xlink:href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']+)["\']',
            r'url\(["\']?([^"\'\)\s]+)["\']?\)',
            r'src=["\']([^"\']+)["\']',
            r'@import\s+["\']([^"\']+)["\']',
        ]

        svg_dir = svg_path.parent

        for pattern in patterns:
            try:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    ref = match.group(1).strip()

                    # Skip empty references
                    if not ref:
                        continue

                    # Skip URLs, data URIs, fragment-only references
                    if any(ref.startswith(p) for p in ["http://", "https://", "data:", "#", "//"]):
                        continue

                    # Remove fragment to resolve file path
                    # BUT keep the full ref with fragment for mapping
                    ref_without_fragment = ref.split("#")[0] if "#" in ref else ref
                    if not ref_without_fragment:
                        continue

                    # Resolve to absolute path
                    # WHY: Use same fallback logic as extract_svg_dependencies to
                    # ensure matching
                    try:
                        ref_path = (svg_dir / ref_without_fragment).resolve()

                        # Check if file exists at expected path
                        if ref_path.exists() and ref_path.is_file():
                            resolved_path = ref_path
                        else:
                            # Fallback: Same logic as extract_svg_dependencies
                            # Try alternative locations if file doesn't exist at
                            # expected path
                            from pathlib import Path as PathLib

                            filename = PathLib(ref_without_fragment).name

                            # Try parent directory
                            parent_path = (svg_dir / ".." / filename).resolve()
                            if parent_path.exists() and parent_path.is_file():
                                resolved_path = parent_path
                            # Try grandparent directory
                            elif (grandparent_path := (svg_dir / "../.." / filename).resolve()).exists() and grandparent_path.is_file():
                                resolved_path = grandparent_path
                            # Try same directory as SVG
                            elif (same_dir_path := (svg_dir / filename).resolve()).exists() and same_dir_path.is_file():
                                resolved_path = same_dir_path
                            else:
                                # No fallback found
                                continue

                        # Check if this matches any of our dependencies
                        if resolved_path in dependency_paths:
                            # Store FULL original reference (with fragment if present)
                            # WHY: We need to replace the exact string that appears
                            # in the SVG
                            ref_strings[resolved_path] = ref
                    except Exception:
                        continue

            except re.error:
                continue

    except Exception:
        pass

    return ref_strings


def extract_svg_dependencies(svg_path: Path, encoding: str = "utf-8") -> set[Path]:
    """
    Extract all file dependencies from an SVG file (images, fonts, external resources).

    This function parses the SVG content to find references to external files such as:
    - Images (href, src attributes)
    - Fonts (url() in CSS, @font-face declarations, xlink:href in font-face-uri)
    - External SVG files (xlink:href, href)
    - CSS imports (@import statements)

    Args:
        svg_path: Path to SVG file
        encoding: File encoding to use when reading SVG (default: utf-8)

    Returns:
        Set of absolute file paths that the SVG depends on

    Note:
        - Ignores HTTP/HTTPS URLs (remote resources)
        - Ignores data: URIs (embedded data)
        - Strips fragment identifiers from file paths
            (e.g., "file.svg#id" -> "file.svg")
        - Ignores pure fragment references (starting with #)
        - If a referenced file doesn't exist at the specified path, searches for it:
          1. In the parent directory
          2. In the grandparent directory
          3. In the same directory as the SVG file
        - Only returns files that actually exist on disk
    """
    dependencies: set[Path] = set()
    svg_dir = svg_path.parent

    try:
        # Read SVG content as text to find all file references
        # Use specified encoding with error handling
        try:
            content = svg_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            # Fallback to latin-1 if UTF-8 fails
            print(f"⚠️  Warning: UTF-8 decode failed for {svg_path.name}, trying latin-1...")
            content = svg_path.read_text(encoding="latin-1")
        except Exception as e:
            print(f"⚠️  Warning: Cannot read {svg_path.name}: {e}")
            return dependencies

        # Patterns to match file references
        # Order matters - more specific patterns first
        patterns = [
            (r'xlink:href=["\']([^"\']+)["\']', "xlink:href"),
            (r'href=["\']([^"\']+)["\']', "href"),
            (r'url\(["\']?([^"\')\s]+)["\']?\)', "url()"),
            (r'src=["\']([^"\']+)["\']', "src"),
            (r'@import\s+["\']([^"\']+)["\']', "@import"),
        ]

        for pattern, pattern_name in patterns:
            try:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    ref = match.group(1).strip()

                    # Skip empty references
                    if not ref:
                        continue

                    # Skip URLs, data URIs, and pure fragment identifiers
                    if any(ref.startswith(prefix) for prefix in ["http://", "https://", "data:", "#", "//"]):
                        continue

                    # Strip fragment identifiers from the end (e.g., "file.svg#id"
                    # -> "file.svg")
                    # This handles cases like
                    # xlink:href="../resources/SVGFreeSans.svg#ascii"
                    # where we need the file path but not the fragment
                    if "#" in ref:
                        ref = ref.split("#")[0]
                        # Skip if nothing remains after removing fragment
                        if not ref:
                            continue

                    # Resolve relative path
                    try:
                        ref_path = (svg_dir / ref).resolve()

                        # Check if file exists and is readable
                        if ref_path.exists() and ref_path.is_file():
                            dependencies.add(ref_path)
                        else:
                            # Fallback: If file doesn't exist at expected path, try
                            # alternative locations
                            # This handles cases where W3C test suite has incorrect
                            # paths like
                            # ../resources/file.svg when file is actually at ../file.svg
                            from pathlib import Path as PathLib

                            filename = PathLib(ref).name  # Get just the filename

                            # Try parent directory
                            parent_path = (svg_dir / ".." / filename).resolve()
                            if parent_path.exists() and parent_path.is_file():
                                dependencies.add(parent_path)
                                continue

                            # Try grandparent directory
                            grandparent_path = (svg_dir / "../.." / filename).resolve()
                            if grandparent_path.exists() and grandparent_path.is_file():
                                dependencies.add(grandparent_path)
                                continue

                            # Try same directory as SVG
                            same_dir_path = (svg_dir / filename).resolve()
                            if same_dir_path.exists() and same_dir_path.is_file():
                                dependencies.add(same_dir_path)
                                continue
                    except (ValueError, OSError):
                        # Invalid path or permission error - skip silently
                        continue

            except re.error as e:
                print(f"⚠️  Warning: Regex error in pattern {pattern_name}: {e}")
                continue

    except Exception as e:
        print(f"⚠️  Warning: Could not extract dependencies from {svg_path.name}: {e}")

    return dependencies


def create_session_from_folder(folder_path: Path, sessions_dir: Path, config: dict[str, Any]) -> tuple[str, Path]:
    """
    Create a new test E2E test session from a folder containing numbered SVG frames.

    Validates:
    - SVG files are numbered sequentially from 00001
    - Each SVG has a viewBox attribute

    Copies:
    - SVG frames (up to max_frames limit from config) + dependencies

    Args:
        folder_path: Path to folder containing SVG frames
        sessions_dir: Path to tests/sessions/ directory
        config: Test configuration dictionary with max_frames setting

    Returns:
        Tuple of (session_id, session_dir)
    """
    print("📦 Creating E2E test session from folder...")
    print(f"   Source: {folder_path}\n")

    # Find all SVG files
    svg_files = sorted(folder_path.glob("*.svg"))

    if not svg_files:
        print(f"❌ Error: No SVG files found in {folder_path}")
        sys.exit(1)

    print(f"   Found {len(svg_files)} SVG files")

    # Apply max_frames limit from config
    max_frames = config.get("max_frames", 50)
    if len(svg_files) > max_frames:
        print(f"   ⚠️  Limiting to first {max_frames} frames (max_frames from pyproject.toml)")
        svg_files = svg_files[:max_frames]

    print(f"   Using {len(svg_files)} frames for E2E test session")

    # ⚠️ CRITICAL: Filter unsupported files BEFORE validation and copying
    #
    # WHY THIS IS NECESSARY:
    # ======================
    # Previously, ALL files were copied to input_frames, then filtered later.
    # This caused off-by-one errors because:
    #   1. Testrunner filters frame00039.svg (SMIL animation)
    #   2. Creates batch_svg_files with 44 frames (00001-00050 minus 6 skipped)
    #   3. BUT svg2fbf also filters independently, creates different frame numbers
    #   4. Frame 40 input = frame00040.svg, but FBF output = FRAME00041 content
    #
    # SOLUTION:
    # =========
    # Filter unsupported files BEFORE copying to input_frames.
    # Then renumber the VALID files sequentially (frame00001, frame00002, etc.)
    # This ensures svg2fbf and testrunner use the SAME frame numbering.
    #
    # Unsupported files to filter:
    #   - SMIL animations (animate, animateTransform, animateMotion, set)
    #   - Nested SVG elements (not supported in FBF format)
    #   - JavaScript (interactive content not supported)
    #   - EXCEPTION: mesh gradient polyfill is OK (svg2fbf adds it back)
    #
    # HISTORY:
    # ========
    # Bug discovered in Frame 40-44 testing (2025-11-10):
    # - Frame 40 showed content from frame00045.svg instead of frame00040.svg
    # - Off-by-one error after frame00039.svg was skipped (SMIL animation)
    # - Root cause: Filtering happened AFTER copying, causing numbering mismatch
    #
    # TESTING:
    # ========
    # Changes must be tested with E2E test session 5 (50 frames with SMIL animations)
    #
    print("   Filtering unsupported SVG files...")
    valid_svg_files = []
    skipped_files = []

    for svg_file in svg_files:
        # Check for SMIL animations
        if contains_smil_animations(svg_file):
            skipped_files.append((svg_file.name, "SMIL animation"))
        # Check for JavaScript (with exceptions for polyfills like meshgradient)
        elif contains_javascript(svg_file, exceptions=JAVASCRIPT_EXCEPTIONS):
            skipped_files.append((svg_file.name, "JavaScript/scripting"))
        # Check for nested SVG elements
        elif contains_nested_svg(svg_file):
            skipped_files.append((svg_file.name, "nested SVG"))
        # Check for multimedia elements (video/audio/iframe/canvas/foreignObject)
        elif contains_media_elements(svg_file):
            skipped_files.append((svg_file.name, "multimedia"))
        else:
            valid_svg_files.append(svg_file)

    if skipped_files:
        print(f"   ⏭️  Skipped {len(skipped_files)} unsupported file(s):")
        for filename, reason in skipped_files:
            print(f"        - {filename} ({reason})")

    print(f"   ✓ {len(valid_svg_files)} valid frames after filtering")

    # Update svg_files to contain only valid files
    # WHY: Remaining code (validation, viewBox repair) should only process valid files
    svg_files = valid_svg_files

    # Validate SVG numbering
    print("   Validating frame numbering...")
    is_valid, error_msg = validate_svg_numbering(svg_files)
    if not is_valid:
        print(f"❌ Error: {error_msg}")
        print("\n   SVG files must be numbered sequentially starting from 1")
        print("   Examples: frame001.svg, frame002.svg OR frame00001.svg, frame00002.svg")
        sys.exit(1)
    print("   ✓ Frame numbering valid")

    # Validate viewBox in each SVG (with automatic union bbox repair for animations)
    print("   Validating viewBox attributes...")

    # Use union bbox strategy for animation sequences
    # This ensures all frames have the SAME viewBox (prevents jumping)
    try:
        repair_animation_sequence_viewbox(svg_files, verbose=True)
    except RuntimeError as e:
        print(f"❌ Failed to repair viewBox: {e}")
        sys.exit(1)

    # Create session
    session_num = find_next_session_number(sessions_dir)
    frame_count = len(svg_files)
    session_id = SESSION_ID_FORMAT.format(session_num, frame_count)
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create input_frames and runs directories
    # Why: Directory names from CONSTANTS.py
    input_frames_dir = session_dir / DIR_INPUT_FRAMES
    input_frames_dir.mkdir()
    runs_dir = session_dir / "runs"
    runs_dir.mkdir()

    # ⚠️ CRITICAL: Renumber valid SVG files sequentially before copying
    #
    # WHY THIS IS NECESSARY:
    # ======================
    # After filtering out unsupported files, we have gaps in frame numbering.
    # Example: frame00001, frame00002, [frame00003 skipped], frame00004...
    #
    # svg2fbf expects sequential frame numbering: frame00001, frame00002, frame00003...
    # If we copy files with gaps, svg2fbf and testrunner will have different frame IDs.
    #
    # SOLUTION:
    # =========
    # Renumber the valid files sequentially before copying:
    #   Original: frame00001.svg, frame00002.svg, [skip frame00003], frame00004.svg...
    #   Renumbered: frame00001.svg, frame00002.svg, frame00003.svg (was frame00004)...
    #
    # This ensures both svg2fbf and testrunner use frames 1, 2, 3, 4... without gaps.
    #
    print("   Copying and renumbering files to E2E test session directory...")

    # Copy SVG frames with sequential numbering
    for i, svg_file in enumerate(svg_files, start=1):
        # Generate new sequential filename
        # WHY: Preserve original filename format (frameXXXXX.svg with 5 digits)
        new_filename = f"frame{i:05d}.svg"
        shutil.copy2(svg_file, input_frames_dir / new_filename)

        if svg_file.name != new_filename:
            print(f"        {svg_file.name} → {new_filename}")
        else:
            print(f"        {svg_file.name}")

    # Copy non-SVG dependency files (fonts, images, etc.)
    dependency_files = [f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() != ".svg"]
    for file in dependency_files:
        shutil.copy2(file, input_frames_dir / file.name)

    total_files = len(svg_files) + len(dependency_files)
    print(f"   ✓ Copied {len(svg_files)} SVG frames + {len(dependency_files)} dependency files = {total_files} total\n")

    # Create session metadata
    fingerprint = compute_session_fingerprint(svg_files)
    metadata = {
        "fingerprint": fingerprint,
        "frame_count": frame_count,
        "created_at": datetime.now().isoformat(),
        "input_folder": str(folder_path.absolute()),
        "svg_files": [f.name for f in svg_files],
        "creation_mode": "folder",
        "max_frames_applied": len(svg_files) < len(sorted(folder_path.glob("*.svg"))),
    }

    # Why: Filename from CONSTANTS.py
    metadata_file = session_dir / FILE_SESSION_METADATA
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    return session_id, session_dir


def create_session_from_files(
    svg_file_paths: list[Path],
    sessions_dir: Path,
    config: dict[str, Any] | None = None,
) -> tuple[str, Path]:
    """
    Create a new test E2E test session from a list of SVG files.

    Features:
    - Auto-numbers files based on argument order (first=00001, second=00002, etc.)
    - Validates each SVG has viewBox
    - Extracts and copies all dependencies (fonts, images, etc.)
    - Converts paths to relative within input_frames/

    Args:
        svg_file_paths: List of SVG file paths (order determines frame number)
        sessions_dir: Path to tests/sessions/ directory
        config: Optional configuration dictionary (loaded if not provided)

    Returns:
        Tuple of (session_id, session_dir)

    Raises:
        FileNotFoundError: If SVG file not found
        PermissionError: If cannot create session directory or copy files
        ValueError: If SVG file invalid (no viewBox, malformed XML, etc.)
    """
    # Load config if not provided
    if config is None:
        config = load_test_config()

    print("📦 Creating E2E test session from file list...")
    print(f"   Files: {len(svg_file_paths)}\n")

    # Validate all files exist and are readable
    print("   Validating file paths...")
    for i, svg_path in enumerate(svg_file_paths, start=1):
        # Check existence
        if not svg_path.exists():
            raise FileNotFoundError(f"Frame {i}: File not found: {svg_path}\n   Ensure file path is correct and accessible")

        # Check if it's a file (not directory)
        if not svg_path.is_file():
            raise ValueError(f"Frame {i}: Not a regular file: {svg_path}\n   Path points to a directory or special file")

        # Check file extension
        if svg_path.suffix.lower() != ".svg":
            raise ValueError(f"Frame {i}: Not an SVG file: {svg_path}\n   File must have .svg extension (found: {svg_path.suffix})")

        # Check read permission
        if not svg_path.is_file() or not svg_path.stat().st_size > 0:
            raise ValueError(f"Frame {i}: File is empty or not readable: {svg_path}")
    print(f"   ✓ All {len(svg_file_paths)} files validated")

    # Validate viewBox in each SVG (with automatic union bbox repair for animations)
    print("   Validating viewBox attributes...")

    # Use union bbox strategy for animation sequences
    # This ensures all frames have the SAME viewBox (prevents jumping)
    try:
        repair_animation_sequence_viewbox(svg_file_paths, verbose=True)
    except RuntimeError as e:
        raise ValueError(f'Failed to repair viewBox: {e}\n   viewBox calculation failed\n   Manual fix: Add viewBox attribute to SVG root element\n   Example: <svg viewBox="0 0 1200 674" ...>') from e

    # Create session directory with error handling
    session_num = find_next_session_number(sessions_dir)
    frame_count = len(svg_file_paths)
    session_id = SESSION_ID_FORMAT.format(session_num, frame_count)
    session_dir = sessions_dir / session_id

    try:
        session_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(f"Cannot create session directory: {session_dir}\n   Check write permissions for: {sessions_dir}") from e

    # Create input_frames and runs directories
    # Why: Directory names from CONSTANTS.py
    input_frames_dir = session_dir / DIR_INPUT_FRAMES
    runs_dir = session_dir / "runs"

    try:
        input_frames_dir.mkdir(exist_ok=True)
        runs_dir.mkdir(exist_ok=True)
    except PermissionError as e:
        raise PermissionError(f"Cannot create session directories: {session_dir}") from e

    # Setup cleanup handler in case of failure
    def cleanup_on_failure() -> None:
        if session_dir.exists():
            try:
                shutil.rmtree(session_dir)
                print(f"   🧹 Cleaned up partial E2E test session: {session_dir.name}")
            except Exception:
                pass

    register_cleanup(cleanup_on_failure)

    try:
        # Extract dependencies from all SVG files
        print("   Extracting dependencies from SVG files...")
        all_dependencies = set()
        for svg_path in svg_file_paths:
            deps = extract_svg_dependencies(svg_path, encoding=config["create_session_encoding"])
            all_dependencies.update(deps)

        if all_dependencies:
            print(f"   Found {len(all_dependencies)} dependency files")

        # Copy SVG files with auto-numbering (use config format)
        print("   Copying and renumbering SVG files...")
        copied_svg_names = []

        # Get TestConfig instance for frame formatting
        # Why: Use heuristics to find and validate project root pyproject.toml
        pyproject_path = find_project_pyproject_toml()
        test_config = SessionConfig(pyproject_path)

        for i, svg_path in enumerate(svg_file_paths, start=1):
            # Generate new filename using configured format
            new_name = test_config.format_frame_filename(i)
            dest_path = input_frames_dir / new_name

            try:
                shutil.copy2(svg_path, dest_path)
            except (PermissionError, OSError) as e:
                raise PermissionError(f"Failed to copy frame {i}: {svg_path.name}\n   Destination: {dest_path}\n   Error: {e}") from e

            copied_svg_names.append(new_name)
            print(f"   ✓ Frame {i}: {svg_path.name} → {new_name}")

        # Copy dependencies preserving relative structure
        if all_dependencies:
            print("\n   Copying dependencies...")
            # Group dependencies by their relative structure
            for dep_path in all_dependencies:
                # Find which SVG referenced this dependency
                referencing_svg = None
                for svg_path in svg_file_paths:
                    if dep_path in extract_svg_dependencies(svg_path, encoding=config["create_session_encoding"]):
                        referencing_svg = svg_path
                        break

                if referencing_svg:
                    # Calculate relative path from SVG to dependency
                    try:
                        rel_path = dep_path.relative_to(referencing_svg.parent)
                        dest_path = input_frames_dir / rel_path
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(dep_path, dest_path)
                        print(f"   ✓ {rel_path}")
                    except ValueError:
                        # Dependency is outside SVG's directory tree
                        # Copy to input_frames root with original name
                        dest_path = input_frames_dir / dep_path.name
                        shutil.copy2(dep_path, dest_path)
                        print(f"   ✓ {dep_path.name} (moved to root)")

        print()

        # Create session metadata
        # Use copied SVG names for fingerprint
        fingerprint = hashlib.sha256("|".join(sorted(copied_svg_names)).encode()).hexdigest()[:16]

        metadata = {
            "fingerprint": fingerprint,
            "frame_count": frame_count,
            "created_at": datetime.now().isoformat(),
            "input_folder": "multiple_files",
            "svg_files": copied_svg_names,
            "original_files": [str(p.absolute()) for p in svg_file_paths],
            "creation_mode": "file_list",
        }

        # Why: Filename from CONSTANTS.py
        metadata_file = session_dir / FILE_SESSION_METADATA
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    except Exception as e:
        # Cleanup will be handled by registered cleanup_on_failure handler
        raise RuntimeError(f"Failed to create session from file list: {e}\n   Session directory: {session_dir}\n   Partial files have been cleaned up") from e

    # Success - unregister cleanup handler
    if cleanup_on_failure in _cleanup_handlers:
        _cleanup_handlers.remove(cleanup_on_failure)

    return session_id, session_dir


def create_session_from_inputs(
    input_paths: list[Path],
    sessions_dir: Path,
    config: dict[str, Any] | None = None,
    recursive: bool = False,
) -> tuple[str, Path]:
    """
    Create a new test E2E test session from mixed inputs (folders and/or files).

    This unified function handles all input types:
    - Directories: Copies all contents (recursively if --recursive flag is set)
    - Individual files: Copies specified files + extracts and copies dependencies
    - Mixed: Any combination of directories and files

    Process:
    1. Copy all inputs to input_frames subfolder (preserving relative structure)
    2. For individual SVG files: extract and copy dependencies (images, fonts, etc.)
    3. Validate collected SVG files (numbering, viewBox)
    4. Categorize and move defective files:
       - Defective SVGs → examples_dev/defective_svg/
       - Obsolete FBF formats → examples_dev/obsolete_fbf_format/

    Args:
        input_paths: List of Path objects (can be mixed directories and files)
        sessions_dir: Path to tests/sessions/ directory
        config: Optional configuration dictionary (loaded if not provided)
        recursive: If True, scan directories recursively. If False, only scan root
            level. Default: False

    Returns:
        Tuple of (session_id, session_dir)

    Raises:
        FileNotFoundError: If input path not found
        PermissionError: If cannot create session directory or copy files
        ValueError: If no valid SVG files found after validation
    """
    # Load config if not provided
    if config is None:
        config = load_test_config()

    print("📦 Creating E2E test session from inputs...")
    print(f"   Input paths: {len(input_paths)}\n")

    # Validate all input paths exist
    print("   Validating input paths...")
    for i, input_path in enumerate(input_paths, start=1):
        if not input_path.exists():
            raise FileNotFoundError(f"Input {i}: Path not found: {input_path}\n   Ensure path is correct and accessible")
    print(f"   ✓ All {len(input_paths)} input paths validated")

    # Create temporary session directory
    session_num = find_next_session_number(sessions_dir)
    # Use placeholder for session_id (will be updated after we count valid SVGs)
    temp_session_id = f"test_session_{session_num:03d}{SESSION_ID_TEMP_SUFFIX}"
    session_dir = sessions_dir / temp_session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create input_frames and runs directories
    # Why: Directory names from CONSTANTS.py
    input_frames_dir = session_dir / DIR_INPUT_FRAMES
    input_frames_dir.mkdir(exist_ok=True)
    runs_dir = session_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

    # Setup cleanup handler in case of failure
    def cleanup_on_failure() -> None:
        if session_dir.exists():
            try:
                shutil.rmtree(session_dir)
                print(f"   🧹 Cleaned up partial E2E test session: {session_dir.name}")
            except Exception:
                pass

    register_cleanup(cleanup_on_failure)

    try:
        # ========================================================================
        # STEP 1: Collect all files to copy with collision resolution
        # ========================================================================
        # This multi-phase approach ensures deterministic file naming even when
        # multiple input sources have files with the same names.
        #
        # Phase 1a: Collect all files to copy
        # Phase 1b: Extract dependencies and build svg_dependencies mapping
        # Phase 1c: Run collision resolution with UUID prefixing
        # Phase 1d: Copy files with resolved names
        # Phase 1e: Update SVG references to use UUID-prefixed dependency names
        # ========================================================================

        print("\n   📋 Phase 1a: Collecting files to copy...")

        # Collect tuples of (source_path, dest_name)
        files_to_copy: list[tuple[Path, str]] = []
        svg_source_paths: set[Path] = set()  # Track which files are SVG files
        root_input_svg_paths: set[Path] = set()  # Track ROOT input SVGs (not dependencies)
        # WHY: Dependencies should NOT be assigned frame numbers
        # Only root input files become test frames

        for input_path in input_paths:
            if input_path.is_dir():
                scan_mode = "recursively" if recursive else "root level only"
                print(f"   📁 Scanning directory: {input_path.name}/ ({scan_mode})")

                # Collect files from directory (recursive or non-recursive based on
                # flag)
                # WHY: By default, don't recurse into subdirectories
                # Subdirectories typically contain helper elements (fonts, images)
                # Use --recursive flag to include subdirectories in frame selection
                glob_pattern = "**/*" if recursive else "*"
                iterator = input_path.glob(glob_pattern) if not recursive else input_path.rglob("*")

                for item in iterator:
                    if item.is_file():
                        # Calculate relative path from input directory
                        try:
                            rel_path = item.relative_to(input_path)
                            dest_name = str(rel_path)
                        except ValueError:
                            # If relative_to fails, use just the filename
                            dest_name = item.name

                        files_to_copy.append((item, dest_name))

                        # Track SVG files (exclude FBF files)
                        if item.suffix.lower() == ".svg" and ".fbf.svg" not in item.name:
                            svg_source_paths.add(item)
                            # Mark as root input (from direct user input, not a
                            # dependency)
                            root_input_svg_paths.add(item)

                file_count = sum(1 for f, _ in files_to_copy if input_path in f.parents or f.parent == input_path)
                print(f"      ✓ Found {file_count} files")

            elif input_path.is_file():
                print(f"   📄 Adding file: {input_path.name}")

                # Individual file goes to input_frames root
                dest_name = input_path.name
                files_to_copy.append((input_path, dest_name))

                # Track SVG files (exclude FBF files)
                if input_path.suffix.lower() == ".svg" and ".fbf.svg" not in input_path.name:
                    svg_source_paths.add(input_path)
                    # Mark as root input (from direct user input, not a dependency)
                    root_input_svg_paths.add(input_path)

                print("      ✓ File added")

            else:
                print(f"   ⚠️  Warning: Skipping non-file/non-directory: {input_path}")

        print(f"\n   ✓ Collected {len(files_to_copy)} total files to copy")
        print(f"   ✓ Found {len(svg_source_paths)} SVG files")

        # ========================================================================
        # Phase 1a.5: Filter unsupported SVG files BEFORE dependency extraction
        # ========================================================================
        #
        # ⚠️ CRITICAL: Filter incompatible files BEFORE dependency extraction
        #
        # WHY THIS IS NECESSARY:
        # ======================
        # Previously, ALL SVG files were processed for dependencies and copied,
        # then filtered later during test execution. This caused off-by-one errors:
        #   1. Testrunner filters frame00039.svg (SMIL animation) during execution
        #   2. Creates batch_svg_files with 44 frames (minus 6 skipped)
        #   3. BUT svg2fbf also filters independently, creates different frame numbers
        #   4. Frame 40 input = frame00040.svg, but FBF output = FRAME00041 content
        #
        # SOLUTION:
        # =========
        # Filter unsupported files BEFORE extracting dependencies and copying.
        # Only process dependencies for compatible SVG files.
        # This ensures svg2fbf and testrunner use the SAME files and frame numbering.
        #
        # Compatibility checks:
        #   - NO SMIL animations (animate, animateTransform, animateMotion, set)
        #   - NO nested SVG elements (not supported in FBF format)
        #   - NO JavaScript (interactive content not supported)
        #   - EXCEPTION: mesh gradient polyfill is OK (svg2fbf adds it back)
        #
        # IMPORTANT: Only filter ROOT-LEVEL SVG files from input
        # Dependencies in subdirectories should NOT be filtered
        # (they are helper elements loaded by the main SVGs)
        #
        # HISTORY:
        # ========
        # Bug discovered in Frame 40-44 testing (2025-11-10):
        # - Frame 40 showed content from frame00045.svg instead of frame00040.svg
        # - Off-by-one error after frame00039.svg was skipped (SMIL animation)
        # - Root cause: Filtering happened AFTER copying, causing numbering mismatch
        #
        # TESTING:
        # ========
        # Changes must be tested with W3C test suite containing SMIL animations
        #
        print("\n   🔍 Phase 1a.5: Filtering incompatible SVG files...")

        # STEP 1: Use the root_input_svg_paths we already tracked in Phase 1a
        # WHY: These are the files directly provided by the user (not dependencies)
        # Only these files should be filtered and become test frames
        print(f"      Found {len(root_input_svg_paths)} root-level SVG files to check")

        # STEP 2: Filter root input SVGs for compatibility
        # WHY: Check SMIL animations and JavaScript separately for better
        # diagnostics
        # NOTE: Dependencies are NOT filtered - they're just support files
        compatible_root_svg_paths: set[Path] = set()
        incompatible_files: list[tuple[Path, str]] = []

        for svg_path in root_input_svg_paths:
            # Check for SMIL animations
            if contains_smil_animations(svg_path):
                incompatible_files.append((svg_path, "SMIL animation"))
            # Check for JavaScript (with exceptions for polyfills like
            # meshgradient)
            elif contains_javascript(svg_path, exceptions=JAVASCRIPT_EXCEPTIONS):
                incompatible_files.append((svg_path, "JavaScript/scripting"))
            # Check for nested SVG elements
            elif contains_nested_svg(svg_path):
                incompatible_files.append((svg_path, "nested SVG"))
            # Check for multimedia elements
            # (video/audio/iframe/canvas/foreignObject)
            elif contains_media_elements(svg_path):
                incompatible_files.append((svg_path, "multimedia"))
            else:
                compatible_root_svg_paths.add(svg_path)

        # STEP 3: Report filtering results
        if incompatible_files:
            print(f"      ⏭️  Filtered out {len(incompatible_files)} incompatible file(s):")
            for file_path, reason in incompatible_files:
                print(f"          - {file_path.name} ({reason})")

        print(f"      ✓ {len(compatible_root_svg_paths)} compatible root SVG files")

        # STEP 4: Remove incompatible ROOT files from files_to_copy list
        # ========================================================================
        # WHY: Don't waste disk space copying incompatible files that will never
        # be used as test frames. Only copy compatible root files + their
        # dependencies.
        #
        # NOTE: We extract the set of incompatible file paths from the tuple
        # list
        # ====================================================================
        incompatible_paths = {path for path, reason in incompatible_files}
        files_to_copy = [(src, dest) for src, dest in files_to_copy if src not in incompatible_paths]
        print(f"      ✓ Removed {len(incompatible_paths)} incompatible files from copy list")

        # STEP 5: Create NEW clean dictionary of ONLY compatible files
        # ========================================================================
        # CRITICAL FIX (2025-11-11): Separate filtering from import phases
        # ========================================================================
        # WHY THIS IS NECESSARY:
        # ======================
        # Previously, we updated root_input_svg_paths but then Phase 1b extracted
        # dependencies from svg_source_paths which still contained ALL files
        # (compatible + incompatible). This caused dependencies to be extracted
        # from incompatible files that would never become test frames!
        #
        # SOLUTION:
        # =========
        # 1. Create a NEW clean set containing ONLY compatible root SVG files
        # 2. Use this clean set for ALL subsequent operations:
        #    - Dependency extraction (Phase 1b)
        #    - File copying (Phase 1d)
        #    - Frame numbering (Step 2)
        #
        # This ensures we ONLY process compatible files throughout the pipeline.
        # ========================================================================

        # Update root_input_svg_paths to the clean compatible set
        root_input_svg_paths = compatible_root_svg_paths

        # Create clean svg_source_paths containing ONLY compatible files
        # WHY: All subsequent operations should use this clean set, not the old
        # one
        svg_source_paths = compatible_root_svg_paths.copy()

        # ====================================================================
        # Phase 1b: Extract dependencies ONLY from compatible files
        # ====================================================================
        print("\n   🔍 Phase 1b: Extracting dependencies from compatible files...")

        svg_dependencies: dict[Path, set[Path]] = {}
        all_dependencies: set[Path] = set()
        svg_original_references: dict[Path, dict[Path, str]] = {}  # Will be populated if dependencies found

        # CRITICAL: Extract dependencies ONLY from compatible root SVG files
        # WHY: Incompatible files will never become test frames, so their
        # dependencies are irrelevant and should not be copied
        for svg_path in svg_source_paths:
            try:
                deps = extract_svg_dependencies(svg_path, encoding=config["create_session_encoding"])
                if deps:
                    svg_dependencies[svg_path] = deps
                    all_dependencies.update(deps)
            except Exception as e:
                print(f"      ⚠️  Warning: Failed to extract dependencies from {svg_path.name}: {e}")

        if all_dependencies:
            print(f"   ✓ Found {len(all_dependencies)} dependency files from {len(svg_dependencies)} SVGs")

            # Extract original reference strings from SVG files
            # WHY: We need the ACTUAL reference strings (e.g.,
            # "../resources/file.svg#ascii") to properly update SVG content when
            # dependencies are renamed with UUID suffixes
            for svg_path, deps in svg_dependencies.items():
                if deps:
                    # Extract original reference strings for this SVG's
                    # dependencies
                    ref_strings = extract_reference_strings(svg_path, deps, encoding=config["create_session_encoding"])
                    if ref_strings:
                        svg_original_references[svg_path] = ref_strings

            # Add dependencies to files_to_copy list
            for dep_path in all_dependencies:
                # Find parent SVG for this dependency
                parent_svg = None
                for svg_path, deps in svg_dependencies.items():
                    if dep_path in deps:
                        parent_svg = svg_path
                        break

                if parent_svg:
                    # Calculate relative path from SVG to dependency
                    try:
                        rel_path = dep_path.relative_to(parent_svg.parent)
                        dest_name = str(rel_path)
                    except ValueError:
                        # Dependency is outside SVG's directory tree
                        dest_name = dep_path.name

                    # Only add if not already in list
                    if (dep_path, dest_name) not in files_to_copy:
                        files_to_copy.append((dep_path, dest_name))
        else:
            print("   ✓ No dependencies found")

        # ====================================================================
        # Phase 1c: Run collision resolution with UUID prefixing
        # ====================================================================
        print("\n   🔀 Phase 1c: Resolving filename collisions...")

        resolved_names, svg_uuids, svg_reference_mappings = resolve_filename_collisions(files_to_copy, svg_dependencies, svg_original_references)

        # Count collisions
        collision_count = sum(1 for dest_name in resolved_names.values() if "___FBFTEST[" in dest_name)
        uuid_prefix_count = sum(1 for dest_name in resolved_names.values() if not dest_name.endswith(".svg") and any(uuid_val in dest_name for uuid_val in svg_uuids.values()))

        if collision_count > 0:
            print(f"   ✓ Resolved {collision_count} SVG filename collisions")
        if uuid_prefix_count > 0:
            print(f"   ✓ Applied UUID prefixes to {uuid_prefix_count} dependency files")
        if collision_count == 0 and uuid_prefix_count == 0:
            print("   ✓ No collisions detected")

        # ====================================================================
        # Phase 1d: Copy files with resolved names
        # ====================================================================
        # CRITICAL FIX (2025-11-11): Place dependencies in subdirectory
        # ========================================================================
        # WHY: svg2fbf processes ALL *.svg files in input_frames/ directory.
        # If dependencies (fonts, images, etc.) are in the root input_frames/,
        # svg2fbf will process them as frames!
        #
        # SOLUTION: Place dependencies in input_frames/dependencies/ subdirectory.
        # svg2fbf won't recurse into subdirectories, so it only processes
        # root-level frame files (frame00001.svg, frame00002.svg, etc.)
        # ========================================================================
        print("\n   📦 Phase 1d: Copying files with resolved names...")

        # Create dependencies subdirectory
        dependencies_dir = input_frames_dir / "dependencies"
        dependencies_dir.mkdir(exist_ok=True)

        copied_files = []
        # Track which copied files are root inputs (for frame numbering)
        copied_root_svg_files = []
        dependency_file_mapping = {}  # Track old path -> new path for dependencies
        copy_count = 0

        for source_path, resolved_dest_name in resolved_names.items():
            # Determine if this is a root input or dependency
            is_root_input = source_path in root_input_svg_paths

            if is_root_input:
                # Root inputs go to input_frames/ root
                dest_path = input_frames_dir / resolved_dest_name
            else:
                # Dependencies go to input_frames/dependencies/
                dest_path = dependencies_dir / resolved_dest_name
                # Track mapping for reference updates: old relative path ->
                # new relative path
                dependency_file_mapping[resolved_dest_name] = f"dependencies/{resolved_dest_name}"

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copy2(source_path, dest_path)
                copied_files.append(dest_path)

                # CRITICAL: Track root input SVGs separately from dependencies
                # WHY: Only root inputs should get frame numbers, not dependencies
                # Dependencies are just support files (fonts, images, etc.)
                if is_root_input:
                    copied_root_svg_files.append(dest_path)

                copy_count += 1
            except (PermissionError, OSError) as e:
                print(f"      ⚠️  Warning: Failed to copy {source_path.name}: {e}")

        print(f"   ✓ Copied {copy_count} files to input_frames")
        print(f"   ✓ Including {len(copied_root_svg_files)} root SVG files (for frame numbering)")
        dependency_count = copy_count - len(copied_root_svg_files)
        if dependency_count > 0:
            print(f"   ✓ Placed {dependency_count} dependencies in dependencies/ subfolder")

        # ====================================================================
        # Phase 1e: Update SVG references with UUID-suffixed dependency names
        # ====================================================================
        # CRITICAL ARCHITECTURE (2025-11-11):
        # =====================================
        # WHY: Dependencies are now in input_frames/dependencies/ subdirectory
        # with UUID suffixes to ensure isolation between different SVG frames.
        #
        # UUID SUFFIX ARCHITECTURE:
        # - Each root SVG has a unique UUID (generated in Phase 1c)
        # - ALL dependencies of that SVG are renamed with UUID suffix
        # - Format: filename_<uuid>.extension (e.g., Blocky_abc123de.woff)
        # - This ensures complete isolation: different SVGs can have different
        #   versions of the same dependency file without conflict
        #
        # EXAMPLE:
        # Old reference: xlink:href="woffs/Blocky.woff"
        # New reference: xlink:href="dependencies/Blocky_abc123de.woff"
        #
        # Old reference: xlink:href="../resources/SVGFreeSans.svg#ascii"
        # New reference: xlink:href="dependencies/SVGFreeSans_abc123de.svg#ascii"
        #
        # The svg_reference_mappings from Phase 1c already contains the correct
        # mappings: {original_ref: "path/to/filename_uuid.ext"}
        # We just need to add the dependencies/ prefix and update the SVG files.
        # ====================================================================
        if svg_reference_mappings:
            print("\n   🔧 Phase 1e: Updating SVG dependency references...")

            update_count = 0
            for source_path, ref_mapping in svg_reference_mappings.items():
                # Find the copied SVG file
                if source_path in resolved_names:
                    resolved_svg_name = resolved_names[source_path]
                    copied_svg_path = input_frames_dir / resolved_svg_name

                    # Add dependencies/ prefix to all UUID-suffixed dependency paths
                    # ref_mapping now contains: {original_ref_with_fragment:
                    # "path/to/filename_uuid.ext"}
                    # Example: {"../resources/SVGFreeSans.svg#ascii":
                    # "fonts/SVGFreeSans_abc123de.svg"}
                    # We need: {"../resources/SVGFreeSans.svg#ascii":
                    # "dependencies/SVGFreeSans_abc123de.svg#ascii"}
                    prefixed_mapping = {}
                    for old_ref, uuid_suffixed_path in ref_mapping.items():
                        # Extract just the filename from the UUID-suffixed path
                        # "fonts/Blocky_abc123de.woff" -> "Blocky_abc123de.woff"
                        filename_with_uuid = Path(uuid_suffixed_path).name

                        # Build new reference with dependencies/ prefix
                        # The old_ref may already contain a fragment identifier
                        if "#" in old_ref:
                            # Old ref contains fragment:
                            # "../resources/file.svg#id"
                            # Extract the fragment from the old ref and apply to
                            # the new filename
                            fragment = old_ref.split("#", 1)[1]
                            new_ref = f"dependencies/{filename_with_uuid}#{fragment}"
                        else:
                            # No fragment in old ref
                            new_ref = f"dependencies/{filename_with_uuid}"

                        prefixed_mapping[old_ref] = new_ref

                    if prefixed_mapping:
                        try:
                            update_svg_dependency_references(
                                copied_svg_path,
                                prefixed_mapping,
                                encoding=config["create_session_encoding"],
                            )
                            update_count += 1
                        except RuntimeError as e:
                            print(f"      ⚠️  Warning: Failed to update references in {copied_svg_path.name}: {e}")

            print(f"   ✓ Updated references in {update_count} SVG files")

        print()

        # ========================================================================
        # Step 2: Prepare root SVG files for frame numbering
        # ========================================================================
        # CRITICAL CHANGE (2025-11-11):
        # ===============================
        # Previously, we used: svg_files = sorted(input_frames_dir.rglob(
        # "*.svg"))
        # This was WRONG because it included ALL SVG files, including
        # DEPENDENCIES!
        #
        # PROBLEM:
        # --------
        # When struct-image-12-b-nocycle.svg references struct-image-12-b.svg,
        # the dependency struct-image-12-b.svg was copied to input_frames/ and
        # then INCORRECTLY assigned a frame number (frame00039.svg).
        #
        # But if struct-image-12-b.svg contains nested SVG (incompatible),
        # it would fail during test execution!
        #
        # SOLUTION:
        # ---------
        # Use copied_root_svg_files which we tracked in Phase 1d.
        # This list contains ONLY files from root_input_svg_paths (user inputs),
        # NOT dependencies.
        #
        # Dependencies remain in input_frames/ for svg2fbf to reference,
        # but are NOT assigned frame numbers or processed as test frames.
        # ========================================================================
        print("\n   🔍 Preparing SVG files for frame numbering...")

        # Use the root SVG files we tracked during copying (NOT all SVG
        # files!)
        svg_files = sorted(copied_root_svg_files)

        # Also find FBF files for obsolete format handling
        fbf_files = sorted(input_frames_dir.rglob("*.fbf.svg"))

        print(f"   Root SVG files (for testing): {len(svg_files)}")
        print(f"   FBF files (obsolete): {len(fbf_files)}")

        # Count dependency files for informational purposes
        all_svg_files_count = len(list(input_frames_dir.rglob("*.svg")))
        all_svg_files_count -= len([f for f in input_frames_dir.rglob("*.svg") if ".fbf.svg" in f.name])
        dependency_count = all_svg_files_count - len(svg_files)
        if dependency_count > 0:
            print(f"   Dependency files (not numbered): {dependency_count}")

        if not svg_files:
            raise ValueError("No valid SVG files found in inputs!\n   Ensure inputs contain .svg files (not .fbf.svg)")

        # Step 3: Move defective/obsolete files
        defective_svg_dir = Path(__file__).parent / "examples_dev" / "defective_svg"
        obsolete_fbf_dir = Path(__file__).parent / "examples_dev" / "obsolete_fbf_format"

        defective_svg_dir.mkdir(parents=True, exist_ok=True)
        obsolete_fbf_dir.mkdir(parents=True, exist_ok=True)

        # Move any FBF files to obsolete_fbf_format
        if fbf_files:
            print(f"\n   🗂️  Moving {len(fbf_files)} FBF files to examples_dev/obsolete_fbf_format/...")
            for fbf_file in fbf_files:
                dest = obsolete_fbf_dir / fbf_file.name
                shutil.move(str(fbf_file), str(dest))
                print(f"      ✓ Moved: {fbf_file.name}")

        # Step 4: Determine deterministic frame order
        # ================================================================
        # CRITICAL CHANGE (2025-11-11):
        # We determine frame order here but create the generation card
        # AFTER the session directory is renamed to its final name.
        # This ensures paths in the generation card point to the correct
        # final directory, not the temporary one.
        # ================================================================
        print("\n   📋 Determining frame sequence order...")

        # Use candidates ladder for deterministic ordering
        # This ensures files always get the same order regardless of input method
        assignments = assign_numbers_deterministically(svg_files)

        # Sort frames by assigned number to get final order
        ordered_frames = [svg_file for svg_file, _ in sorted(assignments.items(), key=lambda x: x[1])]

        print(f"   ✓ Frame sequence determined: {len(ordered_frames)} frames in deterministic order")

        # Update svg_files list with final sorted order
        svg_files = ordered_frames

        # Step 5: Validate viewBox (but don't require bbox calculation)
        # Why: Files may have dynamic content (JavaScript-generated) or
        # percentage dimensions. In these cases, existing viewBox attributes
        # are sufficient
        print("\n   🔍 Validating viewBox attributes...")

        # Check if all files have viewBox
        files_with_viewbox = []
        files_without_viewbox = []

        for svg_file in svg_files:
            is_valid, _ = validate_svg_has_viewbox(svg_file)
            if is_valid:
                files_with_viewbox.append(svg_file)
            else:
                files_without_viewbox.append(svg_file)

        print(f"   Files with viewBox: {len(files_with_viewbox)}")
        print(f"   Files without viewBox: {len(files_without_viewbox)}")

        # If some files are missing viewBox, warn but continue
        # svg2fbf will handle viewBox processing during conversion
        if len(files_without_viewbox) > 0:
            print(f"\n   ⚠️  Warning: {len(files_without_viewbox)} files missing viewBox")
            print("   svg2fbf will attempt to process these during test execution")
        else:
            print("   ✅ All files have viewBox attributes")

        # Step 6: Update session ID with correct frame count
        frame_count = len(svg_files)
        final_session_id = SESSION_ID_FORMAT.format(session_num, frame_count)
        final_session_dir = sessions_dir / final_session_id

        # Rename session directory to final name
        session_dir.rename(final_session_dir)
        session_dir = final_session_dir

        # Step 7: Create session metadata
        # NOTE: Generation card will be created during RUN, not here
        # Why: Generation card must capture the exact frame order used during
        # PNG rendering, which happens in the run command's timestamped directory
        fingerprint = compute_session_fingerprint(svg_files)

        # Determine input source for metadata
        if len(input_paths) == 1 and input_paths[0].is_dir():
            input_source = str(input_paths[0].absolute())
            creation_mode = "folder"
        elif all(p.is_file() for p in input_paths):
            input_source = "multiple_files"
            creation_mode = "file_list"
        else:
            input_source = "mixed_inputs"
            creation_mode = "mixed"

        metadata = {
            "fingerprint": fingerprint,
            "frame_count": frame_count,
            "created_at": datetime.now().isoformat(),
            "input_folder": input_source,
            "svg_files": [f.name for f in svg_files],
            "original_inputs": [str(p.absolute()) for p in input_paths],
            "creation_mode": creation_mode,
        }

        # Why: Filename from CONSTANTS.py
        metadata_file = session_dir / FILE_SESSION_METADATA
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        print("\n✅ E2E Test Session created successfully!")
        print(f"   E2E Test Session ID: {final_session_id}")
        print(f"   Frame count: {frame_count}")
        print(f"   Location: {session_dir}\n")

    except Exception as e:
        # Cleanup will be handled by registered cleanup_on_failure handler
        raise RuntimeError(f"Failed to create session from inputs: {e}\n   Partial files have been cleaned up") from e

    # Success - unregister cleanup handler
    if cleanup_on_failure in _cleanup_handlers:
        _cleanup_handlers.remove(cleanup_on_failure)

    return final_session_id, session_dir


# ============================================================================
# E2E TEST SESSION MANAGEMENT
# ============================================================================


def compute_session_fingerprint(svg_files: list[Path]) -> str:
    """
    Compute unique fingerprint for a set of SVG files.

    Args:
        svg_files: List of SVG file paths (ONLY .svg files!)

    Returns:
        SHA256 hash of sorted filenames (unique identifier for this set of frames)

    CRITICAL: This fingerprint uniquely identifies an E2E test session based
    on SVG filenames.
    - Same filenames (regardless of order) → same fingerprint → reuses
      existing E2E test session
    - Different filenames → different fingerprint → creates new E2E test
      session
    - Only .svg files are considered; other files (images, data, etc.) are
      ignored
    """
    # Sort filenames and create hash (only SVG filenames!)
    filenames = sorted([f.name for f in svg_files])
    fingerprint_string = "|".join(filenames)
    return hashlib.sha256(fingerprint_string.encode()).hexdigest()[:16]


def find_existing_session(sessions_dir: Path, fingerprint: str, frame_count: int) -> str | None:
    """
    Find existing E2E test session with matching fingerprint.

    Args:
        sessions_dir: Path to tests/sessions/ directory
        fingerprint: Session fingerprint to search for
        frame_count: Number of frames (for display only)

    Returns:
        Session ID (e.g., "session_001_35frames") if found, None otherwise
    """
    if not sessions_dir.exists():
        return None

    for session_dir in sessions_dir.glob("test_session_*"):
        if not session_dir.is_dir():
            continue

        # Why: Filename from CONSTANTS.py
        metadata_file = session_dir / FILE_SESSION_METADATA
        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)
                if metadata.get("fingerprint") == fingerprint:
                    return session_dir.name
            except (json.JSONDecodeError, KeyError):
                continue

    return None


def find_next_session_number(sessions_dir: Path) -> int:
    """
    Find the next available session number.

    Args:
        sessions_dir: Path to tests/sessions/ directory

    Returns:
        Next session number (1 if no sessions exist)
    """
    if not sessions_dir.exists():
        return 1

    max_num = 0
    for session_dir in sessions_dir.glob("test_session_*"):
        if session_dir.is_dir():
            try:
                # Extract number from "session_NNN_Nframes"
                num_str = session_dir.name.split("_")[2]
                num = int(num_str)
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                continue

    return max_num + 1


def find_or_create_session(sessions_dir: Path, svg_files: list[Path], input_folder: Path) -> tuple[str, Path, bool]:
    """
    Find existing E2E test session for this set of frames, or create new one.

    Args:
        sessions_dir: Path to tests/sessions/ directory
        svg_files: List of SVG file paths (ONLY .svg files!)
        input_folder: Original input folder path

    Returns:
        Tuple of (session_id, session_dir, is_new_session)

    CRITICAL: Frame count is ALWAYS determined by counting SVG files, NEVER a
    user choice. The session ID's frame count (e.g., "session_100_35frames")
    reflects the EXACT number of .svg files in the input_frames folder. Other
    files are ignored.
    """
    # CRITICAL: frame_count is determined ONLY by counting SVG files
    frame_count = len(svg_files)
    fingerprint = compute_session_fingerprint(svg_files)

    # Try to find existing E2E test session
    existing_session_id = find_existing_session(sessions_dir, fingerprint, frame_count)

    if existing_session_id:
        session_dir = sessions_dir / existing_session_id
        print(f"📦 Found existing E2E test session: {existing_session_id}")
        print("   Using input_frames from previous runs\n")
        return existing_session_id, session_dir, False

    # Create new session
    session_num = find_next_session_number(sessions_dir)
    session_id = SESSION_ID_FORMAT.format(session_num, frame_count)
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create session metadata
    metadata = {
        "fingerprint": fingerprint,
        "frame_count": frame_count,
        "created_at": datetime.now().isoformat(),
        "input_folder": str(input_folder.absolute()),
        "svg_files": [f.name for f in svg_files],
    }

    # Why: Filename from CONSTANTS.py
    metadata_file = session_dir / FILE_SESSION_METADATA
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"📦 Created new E2E test session: {session_id}")

    return session_id, session_dir, True


def print_help() -> None:
    """Print comprehensive help information."""
    help_text = """
═══════════════════════════════════════════════════════════════════════════════
                        SVG2FBF TEST RUNNER - HELP
═══════════════════════════════════════════════════════════════════════════════

DESCRIPTION:
    Comprehensive E2E test session management for svg2fbf frame-by-frame animations.
    Create, run, and validate test sessions with pixel-perfect comparison.

═══════════════════════════════════════════════════════════════════════════════
USAGE MODES:
═══════════════════════════════════════════════════════════════════════════════

1. LIST SESSIONS
   ───────────────────────────────────────────────────────────────────────────
   uv run python tests/testrunner.py list

   Lists all available test sessions with:
   • Session ID number
   • Frame count
   • Last run outcome (PASS/FAIL/NEVER_RUN)
   • Original source paths

2. RUN TEST SESSION
   ───────────────────────────────────────────────────────────────────────────
   uv run python tests/testrunner.py run <session_id> [options]

   Executes a test session and opens the HTML comparison report.
   This is the main command for running tests.

   Options:
   --image-tolerance N   Override image tolerance (default from pyproject.toml)
   --pixel-tolerance N   Override pixel tolerance (default from pyproject.toml)

   Examples:
   uv run python tests/testrunner.py run 77
   uv run python tests/testrunner.py run session_077_23frames
   uv run python tests/testrunner.py run 77 --image-tolerance 0.05

3. OPEN SESSION RESULTS
   ───────────────────────────────────────────────────────────────────────────
   uv run python tests/testrunner.py results <session_id>

   Opens the HTML comparison report for the specified session.
   Uses the latest run if the session has been run multiple times.

   Examples:
   uv run python tests/testrunner.py results 77
   uv run python tests/testrunner.py results session_077_23frames

4. DELETE SESSION
   ───────────────────────────────────────────────────────────────────────────
   uv run python tests/testrunner.py delete <session_id> [--non-interactive]
       [--only-clean-runs]

   Delete a test session or just its run directories.

   Options:
   --non-interactive     Skip confirmation prompt
   --only-clean-runs    Delete only run directories, keep session and input_frames

   Examples:
   uv run python tests/testrunner.py delete 77
   uv run python tests/testrunner.py delete 77 --only-clean-runs
   uv run python tests/testrunner.py delete session_077_23frames --non-interactive

5. PURGE OLD RUNS
   ───────────────────────────────────────────────────────────────────────────
   uv run python tests/testrunner.py purge-old [--until YYYY/MM/DD] [--non-interactive]

   Delete old test runs across all sessions.

   Options:
   --until YYYY/MM/DD   Delete runs older than this date (default: 3 months ago)
   --non-interactive    Skip confirmation prompt

   Examples:
   uv run python tests/testrunner.py purge-old
   uv run python tests/testrunner.py purge-old --until 2025/01/15
   uv run python tests/testrunner.py purge-old --non-interactive

6. CREATE SESSION (unified input handling)
   ───────────────────────────────────────────────────────────────────────────
   uv run python tests/testrunner.py create [options] -- <path1> [path2] [path3] ...

   Accepts mixed inputs:
   • Folders: Recursively copies all contents (SVG frames + dependencies)
   • Individual files: Copies specified files + extracts dependencies
   • Mixed: Any combination of folders and files

   Options (before --):
   --image-tolerance N   Override image tolerance (saved in session config)
   --pixel-tolerance N   Override pixel tolerance (saved in session config)
   --autonumber         Auto-number SVG files if they lack numerical suffixes

   Features:
   • Auto-detects input type using Path.is_dir() and Path.is_file()
   • Auto-numbers files if they lack numerical suffixes
   • Extracts and copies ALL dependencies (fonts, images, etc.)
   • Preserves relative paths within input_frames/
   • Validates viewBox in all SVG files
   • Moves defective SVGs to examples_dev/defective_svg/
   • Moves obsolete FBF files to examples_dev/obsolete_fbf_format/

   What happens:
   • Copies all inputs to input_frames/ directory
   • For individual SVG files: extracts and copies dependencies
   • Validates and repairs viewBox attributes (union bbox for animations)
   • Auto-numbers frames sequentially if needed
   • Creates new session ID: session_XXX_Nframes
   • Reports session ID and how to run it

   Examples:
   # Single folder
   uv run python tests/testrunner.py create -- /path/to/folder

   # Multiple individual files
   uv run python tests/testrunner.py create -- file1.svg file2.svg file3.svg

   # Mixed inputs (folders + files)
   uv run python tests/testrunner.py create -- /path/to/folder1
       /path/to/folder2 extra_file.svg

   # With auto-numbering
   uv run python tests/testrunner.py create --autonumber -- /path/to/folder

   # With tolerance overrides
   uv run python tests/testrunner.py create --image-tolerance 0.05 -- /path/to/folder

═══════════════════════════════════════════════════════════════════════════════
SESSION MANAGEMENT:
═══════════════════════════════════════════════════════════════════════════════

Session ID Format: session_XXX_Nframes
  XXX = Sequential session number (001, 002, ...)
  N   = Frame count (ALWAYS matches number of .svg files)

Frame Count Rules:
  • Determined by counting .svg files ONLY (never a user choice)
  • Other files (images, fonts, data) are IGNORED when counting
  • Adding/removing SVG files → creates NEW session ID
  • Session integrity validated on every run

Directory Structure:
  tests/sessions/
  └── session_100_35frames/
      ├── input_frames/              # Original SVG files + dependencies
      ├── session_metadata.json      # E2E test session fingerprint
      └── 20251106_182100/          # Run (timestamped)
          ├── input_frames_png/     # Ground truth PNGs
          ├── output_frames_png/    # FBF captured PNGs
          ├── fbf_output/           # Generated FBF animation
          ├── diff_png/             # Difference maps
          └── comparison_report.html

═══════════════════════════════════════════════════════════════════════════════
EXAMPLES:
═══════════════════════════════════════════════════════════════════════════════

# List all E2E test sessions
uv run python tests/testrunner.py list

# Run a E2E test session
uv run python tests/testrunner.py run 77

# Run a E2E test session with tolerance override
uv run python tests/testrunner.py run 77 --image-tolerance 0.05

# Open results for a specific E2E test session
uv run python tests/testrunner.py results 77

# Delete an E2E test session
uv run python tests/testrunner.py delete 77

# Delete only run directories (keep E2E test session and input_frames)
uv run python tests/testrunner.py delete 77 --only-clean-runs

# Purge old test runs (older than 3 months by default)
uv run python tests/testrunner.py purge-old

# Purge runs older than specific date
uv run python tests/testrunner.py purge-old --until 2025/01/15

# Create E2E test session from folder
uv run python tests/testrunner.py create -- examples/anime_girl/

# Create E2E test session from multiple files
uv run python tests/testrunner.py create -- file1.svg file2.svg file3.svg

# Create E2E test session from mixed inputs
uv run python tests/testrunner.py create -- /path/to/folder1 file1.svg file2.svg

# Create E2E test session with auto-numbering
uv run python tests/testrunner.py create --autonumber -- examples/anime_girl/

# Create E2E test session with tolerance overrides
uv run python tests/testrunner.py create --image-tolerance 0.05
    --pixel-tolerance 0.6 -- examples/anime_girl/

═══════════════════════════════════════════════════════════════════════════════
VALIDATION:
═══════════════════════════════════════════════════════════════════════════════

Frame Numbering:
  ✓ Files with sequential numbers (frame001.svg, frame002.svg, frame003.svg)
  ✓ Files without numbers (will be auto-numbered)
  ✗ Files with gaps (frame001.svg, frame003.svg) - will be auto-numbered
  ✗ Files not starting at 1 (frame002.svg, frame003.svg) - will be auto-numbered

ViewBox Requirement:
  All SVG files MUST have viewBox attribute:
  <svg viewBox="0 0 1200 674" ...>

  If missing, viewBox will be auto-calculated and added.
  For animations, all frames use union bbox (prevents jumping).

Dependency Extraction:
  Automatically finds and copies:
  • Images (href, src attributes)
  • Fonts (url() in CSS, @font-face)
  • External files (xlink:href)
  • Preserves relative paths

═══════════════════════════════════════════════════════════════════════════════

For more information, see tests/CLAUDE.md and tests/README.md
"""
    print(help_text)


def open_session_results(sessions_dir: Path, session_input: str) -> None:
    """
    Open the HTML report for a specific test session.

    Finds the latest run for the given session and opens its HTML report in the
    preferred browser (Chrome if available, or system default browser).

    Args:
        sessions_dir: Path to results directory containing session folders
        session_input: Session ID (short like "100" or full like "session_100_35frames")
    """
    # Support short session ID (e.g., "100") or full ID (e.g., "session_100_35frames")
    session_num: int | str
    if session_input.isdigit():
        session_num = int(session_input)
        matching_sessions = list(sessions_dir.glob(f"test_session_{session_num:03d}_*"))

        if not matching_sessions:
            print(f"❌ Error: No E2E test session found with ID {session_num}")
            print("\nAvailable E2E test sessions:")
            for s in sorted(sessions_dir.glob("test_session_*")):
                try:
                    num = int(s.name.split("_")[2])
                    print(f"   - {num} ({s.name})")
                except (ValueError, IndexError):
                    print(f"   - {s.name}")
            sys.exit(1)

        if len(matching_sessions) > 1:
            print(f"⚠️  Warning: Multiple E2E test sessions found for ID {session_num}:")
            for s in matching_sessions:
                print(f"   - {s.name}")
            print(f"   Using: {matching_sessions[0].name}")

        session_dir = matching_sessions[0]
    else:
        # Full session ID provided
        session_dir = sessions_dir / session_input

    if not session_dir.exists():
        print(f"❌ Error: E2E Test Session not found: {session_input}")
        print("\nUse 'testrunner.py list' to see available E2E test sessions")
        sys.exit(1)

    # Find all run directories in runs/ subdirectory
    runs_dir = session_dir / "runs"
    run_dirs = sorted(runs_dir.iterdir()) if runs_dir.exists() else []

    if not run_dirs:
        print(f"❌ Error: No test runs found for E2E test session {session_dir.name}")
        print("\nThis E2E test session has never been run.")
        print(f"Run it with: testrunner.py --use-session {session_input}")
        sys.exit(1)

    # Use the latest run
    latest_run = run_dirs[-1]
    report_path = latest_run / "comparison_report.html"

    if not report_path.exists():
        print(f"❌ Error: No HTML report found in {latest_run.name}")
        print("\nThe test run may have been incomplete or failed.")
        sys.exit(1)

    # Extract session number for display
    try:
        session_num = int(session_dir.name.split("_")[2])
    except (ValueError, IndexError):
        session_num = "?"

    print(f"\n📊 Opening results for E2E test session {session_num}")
    print(f"   E2E E2E Test Session: {session_dir.name}")
    print(f"   Run: {latest_run.name}")
    print(f"   Report: {report_path}")
    print()

    # Open in preferred browser (Chrome or default)
    browser_cmd, browser_name = get_preferred_browser()
    subprocess.run([*browser_cmd, str(report_path)])
    print(f"   ✓ Report opened in {browser_name}\n")


def list_test_sessions(sessions_dir: Path) -> None:
    """
    List all available E2E test sessions with their details.

    Displays:
    - Session ID number
    - Frame count
    - Last run outcome (PASS/FAIL/NEVER_RUN)
    - Original source paths

    Args:
        sessions_dir: Path to results directory containing session folders
    """
    # Find all session directories
    session_dirs = sorted(sessions_dir.glob("test_session_*"))

    if not session_dirs:
        print("No E2E test sessions found.")
        print("\nCreate an E2E test session with: testrunner.py create -- <path>")
        return

    print("\n📋 Available Test E2E Test Sessions")
    print("=" * 100)
    print()

    for session_dir in session_dirs:
        # Extract session number from "test_session_NNN_Xframes"
        try:
            parts = session_dir.name.split("_")
            session_num = int(parts[2])
            frame_count = int(parts[3].replace("frames", ""))
        except (ValueError, IndexError):
            print(f"⚠️  Skipping invalid E2E test session: {session_dir.name}")
            continue

        # Read session metadata
        # Why: Filename from CONSTANTS.py
        metadata_file = session_dir / FILE_SESSION_METADATA
        if not metadata_file.exists():
            print(f"{session_num:3d} - ⚠️  No metadata file (corrupted session)")
            continue

        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
        except json.JSONDecodeError:
            print(f"{session_num:3d} - ⚠️  Corrupted metadata file")
            continue

        # Get source paths from metadata
        creation_mode = metadata.get("creation_mode", "unknown")

        if creation_mode == "folder":
            # Single folder input
            source_paths = [metadata.get("input_folder", "unknown")]
        elif creation_mode == "unified":
            # Multiple inputs (folders and/or files)
            source_paths = metadata.get("input_paths", ["unknown"])
        else:
            source_paths = [metadata.get("input_folder", "unknown")]

        # Shorten paths for display (use ~ for home directory)
        display_paths = []
        for path in source_paths:
            path_obj = Path(path)
            try:
                # Try to make relative to home directory
                rel_path = path_obj.relative_to(Path.home())
                display_paths.append(f"~/{rel_path}")
            except ValueError:
                # Not under home, use as-is but shorten if too long
                path_str = str(path)
                if len(path_str) > 50:
                    display_paths.append(f"...{path_str[-47:]}")
                else:
                    display_paths.append(path_str)

        # Find latest run and determine outcome
        runs_dir = session_dir / "runs"
        run_dirs = sorted(runs_dir.iterdir()) if runs_dir.exists() else []

        if not run_dirs:
            outcome = "NEVER_RUN"
            outcome_color = "⚪"
        else:
            # Check latest run for result
            latest_run = run_dirs[-1]
            result_file = latest_run / "test_result.json"

            if result_file.exists():
                try:
                    with open(result_file) as f:
                        result = json.load(f)

                    if result.get("all_passed", False):
                        outcome = "PASS"
                        outcome_color = "✅"
                    else:
                        passed = result.get("passed_count", 0)
                        failed = result.get("failed_count", 0)
                        outcome = f"FAIL ({passed}/{passed + failed})"
                        outcome_color = "❌"
                except (OSError, json.JSONDecodeError):
                    outcome = "UNKNOWN"
                    outcome_color = "⚠️ "
            else:
                # No result file - check if HTML report exists (older runs)
                html_report = latest_run / "comparison_report.html"
                if html_report.exists():
                    outcome = "UNKNOWN"
                    outcome_color = "❓"
                else:
                    outcome = "INCOMPLETE"
                    outcome_color = "⏸️ "

        # Format output
        paths_str = ", ".join(display_paths)
        if len(paths_str) > 80:
            paths_str = paths_str[:77] + "..."

        print(f"{session_num:3d} - Frames: {frame_count:3d} | {outcome_color} {outcome:20s} | {paths_str}")

    print()
    print("=" * 100)
    print(f"\nTotal E2E test sessions: {len(session_dirs)}")
    print("\nTo run an E2E test session: testrunner.py --use-session <ID>")
    print("To create a new E2E test session: testrunner.py create -- <path>")
    print()


def delete_session(
    sessions_dir: Path,
    session_input: str,
    non_interactive: bool = False,
    only_clean_runs: bool = False,
) -> None:
    """
    Delete a test session or just its run directories.

    Args:
        sessions_dir: Path to results directory
        session_input: Session ID (short like "77" or full like "session_077_23frames")
        non_interactive: If True, skip confirmation prompt
        only_clean_runs: If True, only delete run directories, not the session itself
    """
    # Find session directory
    if session_input.isdigit():
        session_num = int(session_input)
        matching_sessions = list(sessions_dir.glob(f"test_session_{session_num:03d}_*"))

        if not matching_sessions:
            print(f"❌ Error: No E2E test session found with ID {session_num}")
            print("   Available E2E test sessions:")
            for s in sorted(sessions_dir.glob("test_session_*")):
                try:
                    num = int(s.name.split("_")[2])
                    print(f"   - {num} ({s.name})")
                except (ValueError, IndexError):
                    print(f"   - {s.name}")
            sys.exit(1)

        if len(matching_sessions) > 1:
            print(f"⚠️  Warning: Multiple E2E test sessions found for ID {session_num}:")
            for s in matching_sessions:
                print(f"   - {s.name}")
            print(f"   Using: {matching_sessions[0].name}")

        session_dir = matching_sessions[0]
    else:
        # Full session ID provided
        session_dir = sessions_dir / session_input

    if not session_dir.exists():
        print(f"❌ Error: E2E Test Session not found: {session_input}")
        print("   Available E2E test sessions:")
        for s in sorted(sessions_dir.glob("test_session_*")):
            try:
                num = int(s.name.split("_")[2])
                print(f"   - {num} ({s.name})")
            except (ValueError, IndexError):
                print(f"   - {s.name}")
        sys.exit(1)

    # Load session metadata to show details
    # Why: Filename from CONSTANTS.py
    metadata_file = session_dir / FILE_SESSION_METADATA
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)
    else:
        metadata = {}

    # Get source paths for display
    creation_mode = metadata.get("creation_mode", "unknown")
    if creation_mode == "folder":
        source_paths = [metadata.get("input_folder", "unknown")]
    elif creation_mode == "unified":
        source_paths = metadata.get("input_paths", ["unknown"])
    else:
        source_paths = ["unknown"]

    # Format source paths for display
    home_dir = Path.home()
    formatted_paths = []
    for path in source_paths:
        try:
            path_obj = Path(path)
            if path_obj.is_relative_to(home_dir):
                formatted_paths.append(f"~/{path_obj.relative_to(home_dir)}")
            else:
                formatted_paths.append(str(path))
        except Exception:
            formatted_paths.append(str(path))

    paths_str = ", ".join(formatted_paths)
    if len(paths_str) > 80:
        paths_str = paths_str[:77] + "..."

    # Get frame count from directory name
    try:
        session_id_parts = session_dir.name.split("_")
        session_num = int(session_id_parts[1])
        frame_count = int(session_id_parts[2].replace("frames", ""))
    except (ValueError, IndexError):
        session_num = 0
        frame_count = 0

    # Get run directories in runs/ subdirectory
    runs_dir = session_dir / "runs"
    run_dirs = sorted(runs_dir.iterdir()) if runs_dir.exists() else []

    # Determine last run status
    if not run_dirs:
        outcome = "NEVER_RUN"
        outcome_color = "⚪"
    else:
        latest_run = run_dirs[-1]
        result_file = latest_run / "test_result.json"

        if result_file.exists():
            try:
                with open(result_file) as f:
                    result = json.load(f)

                if result.get("all_passed", False):
                    outcome = "PASS"
                    outcome_color = "✅"
                else:
                    passed = result.get("passed_count", 0)
                    failed = result.get("failed_count", 0)
                    outcome = f"FAIL ({passed}/{passed + failed})"
                    outcome_color = "❌"
            except Exception:
                outcome = "UNKNOWN"
                outcome_color = "❓"
        else:
            outcome = "INCOMPLETE"
            outcome_color = "⏸️"

    if only_clean_runs:
        # Delete only run directories
        if not run_dirs:
            print(f"ℹ️  No run directories found in E2E test session {session_dir.name}")
            sys.exit(0)

        print(f"🗑️  Delete RUNS from E2E test session {session_num}")
        print("\n   Test Details:")
        print(f"   {session_num:3d} - Frames: {frame_count:3d} | {outcome_color} {outcome:20s} | {paths_str}")
        print(f"\n   Action: Delete {len(run_dirs)} test run(s), KEEP E2E test session")
        print(f"   E2E Test Session directory: {session_dir}")
        print("\n   Runs to delete:")
        for run_dir in run_dirs:
            print(f"      - {run_dir.name}")
        print("\n   Will be preserved:")
        print("      - E2E Test Session metadata")
        print("      - input_frames/ (original SVG files)")

        if not non_interactive:
            response = input(f"\n⚠️  Delete {len(run_dirs)} run(s) but KEEP test session {session_num}? [y/N]: ")
            if response.lower() not in ["y", "yes"]:
                print("❌ Deletion cancelled")
                sys.exit(0)

        # Delete run directories
        deleted_count = 0
        for run_dir in run_dirs:
            try:
                shutil.rmtree(run_dir)
                deleted_count += 1
            except Exception as e:
                print(f"   ⚠️  Failed to delete {run_dir.name}: {e}")

        print(f"\n✅ Deleted {deleted_count} run(s)")
        print(f"   E2E Test Session {session_num} still exists with input_frames")
    else:
        # Delete entire session
        print(f"🗑️  Delete ENTIRE E2E TEST SESSION {session_num}")
        print("\n   Test Details:")
        print(f"   {session_num:3d} - Frames: {frame_count:3d} | {outcome_color} {outcome:20s} | {paths_str}")
        print("\n   Action: Delete entire E2E test session (cannot be undone)")
        print(f"   E2E Test Session directory: {session_dir}")
        print("\n   Will delete:")
        print("      - input_frames/ (original SVG files)")
        print("      - E2E Test Session metadata")
        if run_dirs:
            print(f"      - {len(run_dirs)} test run(s)")

        if not non_interactive:
            response = input(f"\n⚠️  DELETE entire test session {session_num}? [y/N]: ")
            if response.lower() not in ["y", "yes"]:
                print("❌ Deletion cancelled")
                sys.exit(0)

        # Delete entire session directory
        try:
            shutil.rmtree(session_dir)
            print(f"\n✅ E2E Test Session {session_num} deleted successfully")
        except Exception as e:
            print(f"\n❌ Failed to delete E2E test session: {e}")
            sys.exit(1)


def purge_old_runs(sessions_dir: Path, until_date_str: str | None = None, non_interactive: bool = False) -> None:
    """
    Delete old test runs across all sessions.

    Args:
        sessions_dir: Path to results directory
        until_date_str: Date string in YYYY/MM/DD format. Runs older than this
                       will be deleted. If None, defaults to 3 months ago.
        non_interactive: If True, skip confirmation prompt
    """
    from datetime import datetime, timedelta

    # Parse cutoff date
    if until_date_str:
        try:
            # Parse YYYY/MM/DD format
            cutoff_date = datetime.strptime(until_date_str, "%Y/%m/%d")
        except ValueError:
            print(f"❌ Error: Invalid date format '{until_date_str}'")
            print("   Expected format: YYYY/MM/DD")
            print("   Example: 2025/01/15")
            sys.exit(1)
    else:
        # Default to 3 months ago
        cutoff_date = datetime.now() - timedelta(days=90)

    print("🗑️  Purge old test runs")
    print(f"   Cutoff date: {cutoff_date.strftime('%Y/%m/%d')}")
    print("   Runs older than this will be deleted\n")

    # Scan all sessions
    session_dirs = sorted(sessions_dir.glob("test_session_*"))

    if not session_dirs:
        print("ℹ️  No E2E test sessions found")
        sys.exit(0)

    # Collect old runs
    old_runs = []
    for session_dir in session_dirs:
        if not session_dir.is_dir():
            continue

        # Get run directories in runs/ subdirectory
        runs_dir = session_dir / "runs"
        run_dirs = list(runs_dir.iterdir()) if runs_dir.exists() else []

        for run_dir in run_dirs:
            # Parse timestamp from directory name (YYYYMMDD_HHMMSS)
            try:
                run_timestamp = datetime.strptime(run_dir.name, "%Y%m%d_%H%M%S")
                if run_timestamp < cutoff_date:
                    old_runs.append((session_dir, run_dir, run_timestamp))
            except ValueError:
                # Skip directories that don't match timestamp format
                continue

    if not old_runs:
        print(f"✅ No runs older than {cutoff_date.strftime('%Y/%m/%d')} found")
        sys.exit(0)

    # Group by session for display
    runs_by_session: dict[Path, list[tuple[Path, datetime]]] = {}
    for session_dir, run_dir, run_timestamp in old_runs:
        if session_dir not in runs_by_session:
            runs_by_session[session_dir] = []
        runs_by_session[session_dir].append((run_dir, run_timestamp))

    # Display what will be deleted
    print(f"   Found {len(old_runs)} old test run(s) in {len(runs_by_session)} E2E test session(s):\n")
    for session_dir, runs in sorted(runs_by_session.items()):
        # Get session number from directory name
        try:
            session_num = int(session_dir.name.split("_")[2])
            frame_count = int(session_dir.name.split("_")[3].replace("frames", ""))
        except (ValueError, IndexError):
            session_num = 0
            frame_count = 0

        print(f"   Test E2E E2E Test Session {session_num} ({frame_count} frames):")
        for run_dir, run_timestamp in sorted(runs):
            print(f"      - Run: {run_dir.name} ({run_timestamp.strftime('%Y/%m/%d %H:%M:%S')})")

    print("\n   Note: This will delete TEST RUNS only, not the E2E test sessions themselves")
    print("   E2E Test Sessions will be preserved with their input_frames")

    if not non_interactive:
        response = input(f"\n⚠️  Delete {len(old_runs)} old test run(s) from {len(runs_by_session)} session(s)? [y/N]: ")
        if response.lower() not in ["y", "yes"]:
            print("❌ Purge cancelled")
            sys.exit(0)

    # Delete old runs
    deleted_count = 0
    failed_count = 0
    for session_dir, run_dir, _ in old_runs:
        try:
            shutil.rmtree(run_dir)
            deleted_count += 1
        except Exception as e:
            print(f"   ⚠️  Failed to delete {session_dir.name}/{run_dir.name}: {e}")
            failed_count += 1

    print("\n✅ Purge complete:")
    print(f"   Deleted: {deleted_count} test run(s)")
    if failed_count > 0:
        print(f"   Failed: {failed_count} test run(s)")
    print("   All E2E test sessions preserved with their input_frames")


def run_pytest_units(filters: list[str]) -> None:
    """
    Run pytest unit tests with optional regex filters.

    Args:
        filters: List of regex patterns for filtering tests (OR logic)

    Examples:
        run_pytest_units([])  # Run all tests
        run_pytest_units(["test_frame"])  # Run tests matching "test_frame"
        run_pytest_units(["test_frame", "test_viewbox"])  # Run tests matching
            either pattern
    """
    import subprocess

    # Build pytest command
    pytest_args = ["pytest", "-v", "--tb=short"]

    if filters:
        # Combine filters with OR logic using -k option
        # pytest -k "pattern1 or pattern2 or pattern3"
        filter_expr = " or ".join(filters)
        pytest_args.extend(["-k", filter_expr])

        print(f"\n🧪 Running pytest unit tests with filter: {filter_expr}\n")
    else:
        print("\n🧪 Running all pytest unit tests\n")

    # Run pytest from the project root
    project_root = Path(__file__).parent
    result = subprocess.run(pytest_args, cwd=project_root)

    sys.exit(result.returncode)


def collect_random_svgs(source_folders: list[Path], count: int, recursive: bool = False) -> list[Path]:
    """
    Randomly select SVG files from source folders.

    Args:
        source_folders: List of folders to scan for SVG files
        count: Number of SVG files to randomly select
        recursive: If True, scan subdirectories. If False, only scan root level.
                  Default: False

    Returns:
        List of randomly selected SVG file paths

    Features:
        - Scans folders (recursive or root-only based on flag)
        - Excludes .fbf.svg files
        - Random selection using random.sample()
        - Raises error if not enough SVG files found
    """
    import random

    all_svgs = []

    print("🔍 Scanning source folders for SVG files...")
    for folder in source_folders:
        if not folder.exists():
            print(f"⚠️  Warning: Folder not found: {folder}")
            continue

        if not folder.is_dir():
            print(f"⚠️  Warning: Not a directory: {folder}")
            continue

        # Find .svg files (recursive or root-only based on flag)
        # WHY: By default, don't recurse into subdirectories
        # Subdirectories typically contain helper elements (fonts, images)
        # Use recursive=True to include subdirectories in frame selection
        if recursive:
            svgs_in_folder = [svg for svg in folder.rglob("*.svg") if svg.is_file() and ".fbf.svg" not in svg.name.lower()]
        else:
            svgs_in_folder = [svg for svg in folder.glob("*.svg") if svg.is_file() and ".fbf.svg" not in svg.name.lower()]

        scan_mode = "recursively" if recursive else "root level only"
        print(f"   {folder.name}: Found {len(svgs_in_folder)} SVG file(s) ({scan_mode})")
        all_svgs.extend(svgs_in_folder)

    print(f"\n📊 Total SVG files found: {len(all_svgs)}")

    if len(all_svgs) == 0:
        raise ValueError("No SVG files found in source folders!\n   Ensure folders contain .svg files (not .fbf.svg)")

    if len(all_svgs) < count:
        raise ValueError(f"Not enough SVG files! Requested {count}, but only {len(all_svgs)} found.\n   Either reduce count or add more source folders.")

    # Randomly select n files
    selected = random.sample(all_svgs, count)
    print(f"🎲 Randomly selected {count} file(s)")

    return selected


def main() -> None:
    # Configuration is loaded from project root pyproject.toml (not
    # tests/pyproject.toml). No need to create tests/pyproject.toml - it
    # causes UV to create tests/.venv

    # Handle --help or -h manually (before argparse)
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h", "help"]:
        print_help()
        sys.exit(0)

    # Handle "list" command
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        # Why: Directory name from CONSTANTS.py
        sessions_dir = PROJECT_ROOT / DIR_RESULTS
        list_test_sessions(sessions_dir)
        sys.exit(0)

    # Handle "run_units" command - run pytest unit tests
    if len(sys.argv) > 1 and sys.argv[1] == "run_units":
        # Parse filter arguments after '--' separator
        filters = []

        for i, arg in enumerate(sys.argv[2:], start=2):
            if arg == "--":
                # All remaining arguments after '--' are filters
                filters = sys.argv[i + 1 :]
                break
            elif not arg.startswith("--"):
                # No separator, error on unexpected argument
                print(f"❌ Error: Unexpected argument: {arg}")
                print("\nUsage:")
                print("  testrunner.py run_units                    # Run all tests")
                print("  testrunner.py run_units -- REGEX [REGEX]   # Run tests matching patterns (OR logic)")
                print("\nExamples:")
                print("  testrunner.py run_units")
                print('  testrunner.py run_units -- "test_frame"')
                print('  testrunner.py run_units -- "test_frame" "test_viewbox"')
                sys.exit(1)

        run_pytest_units(filters)
        sys.exit(0)

    # Handle "results" command
    if len(sys.argv) > 1 and sys.argv[1] == "results":
        if len(sys.argv) < 3:
            print("❌ Error: E2E E2E Test Session ID required")
            print("\nUsage:")
            print("  testrunner.py results <session_id>  # Open results for an E2E test session")
            print("\nExamples:")
            print("  testrunner.py results 77")
            print("  testrunner.py results session_077_23frames")
            print("\nUse 'testrunner.py list' to see available E2E test sessions")
            sys.exit(1)

        # Why: Directory name from CONSTANTS.py
        sessions_dir = PROJECT_ROOT / DIR_RESULTS
        session_id = sys.argv[2]
        open_session_results(sessions_dir, session_id)
        sys.exit(0)

    # Handle "delete" command - delete a E2E test session
    if len(sys.argv) > 1 and sys.argv[1] == "delete":
        if len(sys.argv) < 3:
            print("❌ Error: E2E E2E Test Session ID required")
            print("\nUsage:")
            print("  testrunner.py delete <session_id> [--non-interactive] [--only-clean-runs]")
            print("\nExamples:")
            print("  testrunner.py delete 77")
            print("  testrunner.py delete 77 --only-clean-runs")
            print("  testrunner.py delete session_077_23frames --non-interactive")
            print("\nUse 'testrunner.py list' to see available E2E test sessions")
            sys.exit(1)

        # Why: Directory name from CONSTANTS.py
        sessions_dir = PROJECT_ROOT / DIR_RESULTS
        session_id = sys.argv[2]

        # Parse flags
        non_interactive = "--non-interactive" in sys.argv
        only_clean_runs = "--only-clean-runs" in sys.argv

        delete_session(sessions_dir, session_id, non_interactive, only_clean_runs)
        sys.exit(0)

    # Handle "purge-old" command - delete old test runs
    if len(sys.argv) > 1 and sys.argv[1] == "purge-old":
        # Why: Directory name from CONSTANTS.py
        sessions_dir = PROJECT_ROOT / DIR_RESULTS

        # Parse flags and date
        non_interactive = "--non-interactive" in sys.argv
        until_date = None

        # Find --until parameter
        for i, arg in enumerate(sys.argv):
            if arg == "--until" and i + 1 < len(sys.argv):
                until_date = sys.argv[i + 1]
                break

        purge_old_runs(sessions_dir, until_date, non_interactive)
        sys.exit(0)

    # Handle "run" command - execute one or more E2E test sessions
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        if len(sys.argv) < 3:
            print("❌ Error: At least one E2E test session ID required")
            print("\nUsage:")
            print("  testrunner.py run <session_id> [<session_id> ...] [--image-tolerance N] [--pixel-tolerance N]")
            print("\nExamples:")
            print("  testrunner.py run 77")
            print("  testrunner.py run 88 45 7 193")
            print("  testrunner.py run 77 --image-tolerance 0.05")
            print("\nUse 'testrunner.py list' to see available E2E test sessions")
            sys.exit(1)

        # Why: Directory name from CONSTANTS.py
        sessions_dir = PROJECT_ROOT / DIR_RESULTS

        # Collect session IDs (everything before options)
        session_ids = []
        i = 2
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg.startswith("--"):
                # Reached options, stop collecting session IDs
                break
            session_ids.append(arg)
            i += 1

        if not session_ids:
            print("❌ Error: At least one E2E test session ID required")
            sys.exit(1)

        # Parse optional tolerance overrides
        config = load_test_config()
        while i < len(sys.argv):
            if sys.argv[i] == "--image-tolerance" and i + 1 < len(sys.argv):
                config["image_tolerance"] = float(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--pixel-tolerance" and i + 1 < len(sys.argv):
                config["pixel_tolerance"] = float(sys.argv[i + 1])
                i += 2
            else:
                print(f"❌ Error: Unknown option: {sys.argv[i]}")
                sys.exit(1)

        # Execute all E2E E2E test sessions
        report_paths = []
        is_batch = len(session_ids) > 1

        for session_id in session_ids:
            print(f"\n{'=' * 80}")
            print(f"📦 Running E2E test session {session_id} ({session_ids.index(session_id) + 1}/{len(session_ids)})")
            print(f"{'=' * 80}\n")

            # Execute session without opening browser (will open all at once at the end)
            report_path = execute_test_session(session_id, config, sessions_dir, open_in_browser=False)
            report_paths.append(report_path)

        # Inject batch navigation for multiple sessions
        if is_batch:
            print(f"\n{'=' * 80}")
            print(f"🔗 Adding navigation bar to {len(report_paths)} reports...")
            print(f"{'=' * 80}\n")
            inject_batch_navigation(report_paths)
            print("   ✓ Navigation added to all reports\n")

        # Open all reports in browser (Chrome preferred, or default browser)
        browser_cmd, browser_name = get_preferred_browser()
        print(f"\n{'=' * 80}")
        if is_batch:
            print(f"🌐 Opening {len(report_paths)} HTML reports in {browser_name}...")
        else:
            print(f"🌐 Opening HTML report in {browser_name}...")
        print(f"{'=' * 80}\n")

        for report_path in report_paths:
            subprocess.run([*browser_cmd, str(report_path)])
            print(f"   ✓ {report_path}")

        print(f"\n{'=' * 80}")
        print("✅ All E2E E2E test sessions complete!")
        print(f"{'=' * 80}")

        sys.exit(0)

    # Handle "create" command with special syntax
    if len(sys.argv) > 1 and sys.argv[1] == "create":
        # Why: Directory name from CONSTANTS.py
        sessions_dir = PROJECT_ROOT / DIR_RESULTS
        sessions_dir.mkdir(parents=True, exist_ok=True)

        if len(sys.argv) < 4:
            print("❌ Error: Invalid create syntax")
            print("\n" + "=" * 80)
            print("TESTRUNNER.PY - CREATE E2E TEST SESSION COMMAND")
            print("=" * 80)
            print("\nUsage:")
            print("  testrunner.py create [options] -- <path1> [path2] [path3] ...")
            print("\nOptions:")
            print("  --image-tolerance N   Override image tolerance (default from pyproject.toml)")
            print("  --pixel-tolerance N   Override pixel tolerance (default from pyproject.toml)")
            print("  --autonumber         Auto-number SVG files in directories")
            print("  --recursive          Scan directories recursively (default: root level only)")
            print("  --random N           Randomly select N SVG files from source folders (excludes .fbf.svg)")
            print("\nImportant Notes:")
            print("  • By default, directory scanning is NON-RECURSIVE (root level only)")
            print("  • Use --recursive to include subdirectories in frame selection")
            print("  • Subdirectories typically contain helper elements (fonts, images)")
            print("  • Root-level SVGs are frames; subdirectory SVGs are dependencies")
            print("  • Incompatible files (SMIL animations, JS, multimedia) are filtered BEFORE processing")
            print("\nExamples:")
            print("\n  Basic Usage:")
            print("    testrunner.py create -- /path/to/folder")
            print("    testrunner.py create -- file1.svg file2.svg file3.svg")
            print("    testrunner.py create --image-tolerance 0.05 -- /path/to/folder")
            print("    testrunner.py create --autonumber -- /path/to/folder1 /path/to/folder2")
            print("\n  Random Selection (root level only, recommended for W3C test suite):")
            print("    testrunner.py create --random 50 -- 'FBF.SVG/SVG 1.1 W3C Test Suit/w3c_50frames/'")
            print("    just test-random-w3c 50  # Convenient alias")
            print("\n  Random Selection (recursive, for nested directories):")
            print("    testrunner.py create --random 50 --recursive -- examples/")
            print("    just random-test 50  # Convenient alias")
            print("\n  W3C Test Suite Structure:")
            print("    w3c_50frames/")
            print("      ├── test1.svg           ← Root level: test frames (SCANNED)")
            print("      ├── test2.svg           ← Root level: test frames (SCANNED)")
            print("      └── subdirs/")
            print("          └── helper.svg      ← Subdirectory: dependency (NOT SCANNED by default)")
            print("\nFor more help: testrunner.py --help")
            sys.exit(1)

        # Parse options before '--' separator
        config = load_test_config()
        autonumber = False
        random_count = None
        recursive = False
        separator_index = None

        for i, arg in enumerate(sys.argv[2:], start=2):
            if arg == "--":
                separator_index = i
                break
            elif arg == "--autonumber":
                autonumber = True
            elif arg == "--recursive":
                recursive = True
            elif arg == "--random":
                if i + 1 >= len(sys.argv):
                    print("❌ Error: --random requires a count value")
                    sys.exit(1)
                try:
                    random_count = int(sys.argv[i + 1])
                    if random_count <= 0:
                        raise ValueError("Count must be positive")
                except ValueError as e:
                    print(f"❌ Error: --random requires a positive integer: {e}")
                    sys.exit(1)
            elif arg == "--image-tolerance":
                if i + 1 >= len(sys.argv):
                    print("❌ Error: --image-tolerance requires a value")
                    sys.exit(1)
                config["image_tolerance"] = float(sys.argv[i + 1])
            elif arg == "--pixel-tolerance":
                if i + 1 >= len(sys.argv):
                    print("❌ Error: --pixel-tolerance requires a value")
                    sys.exit(1)
                config["pixel_tolerance"] = float(sys.argv[i + 1])

        if separator_index is None:
            print("❌ Error: Missing '--' separator")
            print("   Use '--' to separate options from input paths")
            print("\nExamples:")
            print("  testrunner.py create -- /path/to/folder")
            print("  testrunner.py create --image-tolerance 0.05 -- /path/to/folder")
            print("  testrunner.py create --random 50 -- 'FBF.SVG/SVG 1.1 W3C Test Suit/w3c_50frames/'")
            print("  just test-random-w3c 50  # Convenient alias")
            print("\nFor more help: testrunner.py --help")
            sys.exit(1)

        # Get all input paths after -- separator
        input_path_args = sys.argv[separator_index + 1 :]

        if not input_path_args:
            print("❌ Error: No input paths specified after '--'")
            print("\nUsage:")
            print("  testrunner.py create [options] -- <path1> [path2] [path3] ...")
            print("\nExamples:")
            print("  testrunner.py create -- /path/to/folder")
            print("  testrunner.py create -- file1.svg file2.svg file3.svg")
            print("  testrunner.py create --image-tolerance 0.05 -- /path/to/folder")
            sys.exit(1)

        # Convert all input paths to Path objects
        input_paths = [Path(p) for p in input_path_args]

        # Handle random selection if requested
        if random_count is not None:
            print(f"\n🎲 Random selection mode: {random_count} file(s)")
            print(f"   Source folders: {len(input_paths)}")
            print()

            # Use random selection function
            try:
                input_paths = collect_random_svgs(input_paths, random_count, recursive=recursive)
                print()
            except ValueError as e:
                print("\n❌ Random selection failed:")
                print(f"   {e}")
                sys.exit(1)

        # Auto-number files if requested (only works for directory inputs)
        if autonumber:
            print("🔢 Auto-numbering SVG files in directories...")

            for input_path in input_paths:
                if input_path.is_dir():
                    renames = autonumber_svg_files(input_path)
                    if renames:
                        print(f"\n   Directory: {input_path.name}")
                        print(f"   ✓ Renamed {len(renames)} file(s):")
                        for old_name, new_name in sorted(renames.items()):
                            print(f"      {old_name} → {new_name}")
                    else:
                        print(f"\n   Directory: {input_path.name}")
                        print("   ✓ All files already have proper numerical suffixes")
                        print("   ✓ No gaps detected in sequence")

            print()

        # Create session using unified function
        try:
            session_id, session_dir = create_session_from_inputs(input_paths, sessions_dir, config, recursive)

            print("To run this E2E E2E test session:")
            print(f"   uv run python testrunner.py run {session_id.split('_')[1]}")
            sys.exit(0)

        except Exception as e:
            print("\n❌ Failed to create E2E test session:")
            print(f"   {e}")
            sys.exit(1)

    # If we get here, the command was not recognized
    print("❌ Error: Unknown command")
    print("\nAvailable commands:")
    print("  list                - List all E2E test sessions")
    print("  run <id>            - Execute an E2E test session")
    print("  results <id>        - Open HTML report for an E2E test session")
    print("  create -- <paths>   - Create a new E2E test session")
    print("  delete <id>         - Delete a E2E test session")
    print("  purge-old           - Delete old test runs")
    print("\nFor detailed help: testrunner.py --help")
    sys.exit(1)


def inject_batch_navigation(report_paths: list[Path]) -> None:
    """
    Inject batch navigation bar into HTML reports.

    Args:
        report_paths: List of all report paths in the batch

    Why:
        Navigation bar allows easy browsing between multiple test session reports
    """

    for idx, report_path in enumerate(report_paths):
        if not report_path.exists():
            continue

        # Read existing report
        with open(report_path, encoding="utf-8") as f:
            html_content = f.read()

        # Build navigation JavaScript
        report_urls = [f"file://{str(path.absolute())}" for path in report_paths]
        is_first = idx == 0
        is_last = idx == len(report_paths) - 1
        prev_index = (idx - 1) % len(report_paths)
        next_index = (idx + 1) % len(report_paths)

        first_btn_style = "opacity: 0.5; cursor: not-allowed;" if is_first else "cursor: pointer;"
        last_btn_style = "opacity: 0.5; cursor: not-allowed;" if is_last else "cursor: pointer;"

        nav_script = f"""
    <script>
        // Navigation for batch test runs
        const reportUrls = {report_urls};

        function navigateToReport(index) {{
            if (index >= 0 && index < reportUrls.length) {{
                window.location.href = reportUrls[index];
            }}
        }}

        // Create navigation bar on page load
        window.addEventListener('DOMContentLoaded', function() {{
            const navBar = document.getElementById('batch-navigation');
            const navDiv = document.createElement('div');
            navDiv.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; ' +
                'background: rgba(255, 255, 255, 0.95); ' +
                'border-bottom: 2px solid #3498db; padding: 10px 20px; ' +
                'z-index: 1000; box-shadow: 0 2px 10px rgba(0,0,0,0.1); ' +
                'display: flex; justify-content: center; align-items: center; ' +
                'gap: 15px;';

            // First button
            const firstBtn = document.createElement('button');
            firstBtn.textContent = '⏮ First';
            firstBtn.disabled = {str(is_first).lower()};
            firstBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; ' +
                'border: 1px solid #3498db; background: #fff; ' +
                'border-radius: 4px; {first_btn_style}';
            firstBtn.onclick = () => navigateToReport(0);
            navDiv.appendChild(firstBtn);

            // Previous button
            const prevBtn = document.createElement('button');
            prevBtn.textContent = '◀ Previous';
            prevBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; ' +
                'border: 1px solid #3498db; background: #fff; ' +
                'border-radius: 4px; cursor: pointer;';
            prevBtn.onclick = () => navigateToReport({prev_index});
            navDiv.appendChild(prevBtn);

            // Counter
            const counter = document.createElement('span');
            counter.textContent = '{idx + 1} / {len(report_paths)}';
            counter.style.cssText = 'font-weight: bold; color: #333; ' +
                'padding: 0 10px; min-width: 80px; text-align: center;';
            navDiv.appendChild(counter);

            // Next button
            const nextBtn = document.createElement('button');
            nextBtn.textContent = 'Next ▶';
            nextBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; ' +
                'border: 1px solid #3498db; background: #fff; ' +
                'border-radius: 4px; cursor: pointer;';
            nextBtn.onclick = () => navigateToReport({next_index});
            navDiv.appendChild(nextBtn);

            // Last button
            const lastBtn = document.createElement('button');
            lastBtn.textContent = 'Last ⏭';
            lastBtn.disabled = {str(is_last).lower()};
            lastBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; ' +
                'border: 1px solid #3498db; background: #fff; ' +
                'border-radius: 4px; {last_btn_style}';
            lastBtn.onclick = () => navigateToReport({len(report_paths) - 1});
            navDiv.appendChild(lastBtn);

            navBar.appendChild(navDiv);
            document.body.style.paddingTop = '60px';
        }});
    </script>
"""

        # Inject navigation script before </body> tag
        html_content = html_content.replace("</body>", f"{nav_script}</body>")

        # Write updated report
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)


def execute_test_session(
    session_input: str,
    config: dict[str, Any],
    sessions_dir: Path,
    open_in_browser: bool = True,
    navigation_data: dict[str, Any] | None = None,
) -> Path:
    """
    Execute a test session by ID.

    Args:
        session_input: Session ID (short like "77" or full like "session_077_23frames")
        config: Test configuration dictionary with tolerance settings
        sessions_dir: Path to results directory
        open_in_browser: If True, open report in preferred browser after
            completion (default: True). Preferred browser: Chrome (if installed),
            or system default browser
        navigation_data: Optional dict for batch navigation with:
            - report_paths: list[Path] - All report paths in batch
            - current_index: int - Index of this report (0-based)

    Returns:
        Path to the generated HTML report
    """
    # Find session directory
    if session_input.isdigit():
        session_num = int(session_input)
        matching_sessions = list(sessions_dir.glob(f"test_session_{session_num:03d}_*"))

        if not matching_sessions:
            print(f"❌ Error: No E2E test session found with ID {session_num}")
            print("   Available E2E test sessions:")
            for s in sorted(sessions_dir.glob("test_session_*")):
                try:
                    num = int(s.name.split("_")[2])
                    print(f"   - {num} ({s.name})")
                except (ValueError, IndexError):
                    print(f"   - {s.name}")
            sys.exit(1)

        if len(matching_sessions) > 1:
            print(f"⚠️  Warning: Multiple E2E test sessions found for ID {session_num}:")
            for s in matching_sessions:
                print(f"   - {s.name}")
            print(f"   Using: {matching_sessions[0].name}")

        session_dir = matching_sessions[0]
    else:
        # Full session ID provided
        session_dir = sessions_dir / session_input

    if not session_dir.exists():
        print(f"❌ Error: E2E Test Session not found: {session_input}")
        print("   Available E2E test sessions:")
        for s in sorted(sessions_dir.glob("test_session_*")):
            try:
                num = int(s.name.split("_")[2])
                print(f"   - {num} ({s.name})")
            except (ValueError, IndexError):
                print(f"   - {s.name}")
        sys.exit(1)

    # Load session metadata
    # Why: Filename from CONSTANTS.py
    metadata_file = session_dir / FILE_SESSION_METADATA
    if not metadata_file.exists():
        print(f"❌ Error: E2E Test Session metadata not found in {session_dir.name}")
        sys.exit(1)

    with open(metadata_file) as f:
        metadata = json.load(f)

    # Get actual SVG files from input_frames folder
    # Why: Directory name from CONSTANTS.py
    input_frames_dir = session_dir / DIR_INPUT_FRAMES
    if not input_frames_dir.exists():
        print(f"❌ Error: input_frames folder not found in session {session_dir.name}")
        sys.exit(1)

    # CRITICAL FIX (2025-11-11):
    # ==========================
    # Only count NUMBERED frame files (frame00001.svg, frame00002.svg, etc.)
    # NOT dependency files (fonts, images, etc.)
    #
    # WHY: After switching to generation card approach (2025-11-11),
    # files keep their original names (no more frame00001.svg renaming).
    # Dependencies are stored in input_frames/dependencies/ subdirectory.
    #
    # We need to count root-level SVG files ONLY (exclude dependencies/).
    # This matches the frame count in the session ID.
    all_svg_files = list(input_frames_dir.glob("*.svg"))
    # Exclude any SVG files in subdirectories (like dependencies/)
    svg_files = sorted([f for f in all_svg_files if f.parent == input_frames_dir])

    # Store original count before applying limit
    original_svg_count = len(svg_files)

    # Apply max_frames limit from config
    max_frames = config.get("max_frames", 50)
    if len(svg_files) > max_frames:
        print(f"⚠️  Session has {original_svg_count} frames, limiting to first {max_frames} (max_frames from pyproject.toml)")
        svg_files = svg_files[:max_frames]

    # Validate session integrity
    try:
        session_id_parts = session_dir.name.split("_")
        # Why: parts[3] contains frame count for test_session_NNN_Mframes naming
        declared_frame_count = int(session_id_parts[3].replace("frames", ""))
    except (ValueError, IndexError):
        print(f"❌ Error: Invalid session directory name format: {session_dir.name}")
        sys.exit(1)

    actual_frame_count = original_svg_count  # Use original count for integrity check

    if actual_frame_count != declared_frame_count:
        print("❌ CRITICAL ERROR: E2E Test Session integrity violation!")
        print(f"   E2E Test Session ID declares: {declared_frame_count} frames")
        print(f"   Actual SVG files found: {actual_frame_count} frames")
        print(f"   E2E Test Session folder: {session_dir}")
        print(f"   input_frames folder: {input_frames_dir}")
        print()
        print("   This indicates either:")
        print("   1. E2E Test Session folder was manually corrupted")
        print("   2. SVG files were added/removed from input_frames folder")
        print()
        print("   The frame count in E2E test session ID is ALWAYS determined by the")
        print("   exact number of SVG files in input_frames folder.")
        print("   Any change = new E2E test session with different ID!")
        sys.exit(1)

    session_id = session_dir.name
    input_folder = Path(metadata.get("input_folder", metadata.get("source_path")))

    print("🎬 svg2fbf Test Runner (Rerun)")
    print("=" * SEPARATOR_WIDTH)
    print(f"E2E Test E2E Test Session ID:   {session_id}")
    print(f"Input folder: {input_folder}")
    print(f"Frame count:  {len(svg_files)}")
    print("=" * SEPARATOR_WIDTH)
    print()

    # Create runs directory if it doesn't exist
    runs_dir = session_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

    # Create timestamped run directory inside runs/
    # Why: Timestamp format from CONSTANTS.py ensures consistent directory naming
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    output_dir = runs_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run-level subdirectories (names from CONSTANTS.py)
    input_frames_png_dir = output_dir / DIR_INPUT_FRAMES_PNG  # Rendered PNGs from input SVGs
    output_frames_png_dir = output_dir / DIR_OUTPUT_FRAMES_PNG  # Captured PNGs from FBF
    fbf_output_dir = output_dir / DIR_FBF_OUTPUT
    diff_png_dir = output_dir / DIR_DIFF_PNG  # Grayscale difference maps

    input_frames_png_dir.mkdir()
    output_frames_png_dir.mkdir()
    fbf_output_dir.mkdir()
    diff_png_dir.mkdir()

    print(f"📋 E2E Test Session: {session_id}")
    print(f"📁 Run directory: {output_dir}\n")

    # Initialize renderers and frame processor
    # Why: Directory paths use constants from CONSTANTS.py for consistency
    node_scripts_dir = PROJECT_ROOT / DIR_TESTS / DIR_NODE_SCRIPTS
    renderer = PuppeteerRenderer(node_scripts_dir=node_scripts_dir)
    comparator = ImageComparator()

    # CRITICAL: Use svg2fbf's frame processor to calculate transforms
    # Why: Ensures test uses EXACT same logic as svg2fbf for transforms
    # Precision values from CONSTANTS.py (maximum precision for accuracy)
    frame_processor = SVG2FBFFrameProcessor(digits=DEFAULT_PRECISION_DIGITS, cdigits=DEFAULT_PRECISION_CDIGITS)

    # Session-level input_frames directory (original SVGs)
    # Why: Directory name from CONSTANTS.py
    session_input_frames_dir = session_dir / DIR_INPUT_FRAMES

    # Get SVG files from session-level input_frames
    # WHY: Files in input_frames are already filtered and renumbered during
    # E2E test session creation (see create_session_from_folder() lines
    # 1749-1769). All files here should be valid, sequential, and ready for
    # testing
    #
    # CRITICAL FIX (2025-11-11):
    # ==========================
    # Get root-level SVG files (exclude dependencies/ subdirectory)
    # WHY: After switching to generation card approach (2025-11-11),
    # files keep their original names (no frame*.svg pattern).
    # Dependencies are in input_frames/dependencies/ subdirectory.
    all_test_svg_files = list(session_input_frames_dir.glob("*.svg"))
    batch_svg_files = sorted([f for f in all_test_svg_files if f.parent == session_input_frames_dir])

    # SAFETY CHECK: Verify no incompatible content slipped through
    # This should never happen if session was created correctly, but check anyway
    # NOTE: We only check NUMBERED frames, not dependencies
    incompatible_found = []
    for svg_file in batch_svg_files:
        if contains_smil_animations(svg_file):
            incompatible_found.append((svg_file.name, "SMIL animation"))
        elif contains_javascript(svg_file, exceptions=JAVASCRIPT_EXCEPTIONS):
            incompatible_found.append((svg_file.name, "JavaScript/scripting"))
        elif contains_nested_svg(svg_file):
            incompatible_found.append((svg_file.name, "nested SVG"))
        elif contains_media_elements(svg_file):
            incompatible_found.append((svg_file.name, "multimedia"))

    if incompatible_found:
        print(f"❌ CRITICAL ERROR: Found {len(incompatible_found)} file(s) with incompatible content in input_frames!")
        print("   These should have been filtered during E2E test session creation.")
        for filename, reason in incompatible_found:
            print(f"     - {filename} ({reason})")
        print("\n   This indicates either:")
        print("   1. E2E Test Session folder was manually corrupted")
        print("   2. SVG files were manually added to input_frames folder")
        print("   3. Bug in create_session_from_folder() filtering logic")
        sys.exit(1)

    # Step 1: Render input SVGs to PNG (per run, for ground truth comparison)
    print(f"🎨 Step 1: Rendering {len(batch_svg_files)} input SVGs to PNG...")

    # Get first frame dimensions using svg2fbf logic
    first_svg = batch_svg_files[0]
    first_width, first_height, first_viewbox, _, _ = frame_processor.process_frame(first_svg)

    print(f"   First frame dimensions: {first_width} x {first_height}")
    print(f"   First frame viewBox: {first_viewbox}")

    # Store first frame dimensions for subsequent frames
    first_frame_dimensions = (first_width, first_height, first_viewbox)

    input_pngs = []
    for i, svg_file in enumerate(batch_svg_files):
        # Why: PNG filename format from CONSTANTS.py for consistency
        png_path = input_frames_png_dir / PNG_INPUT_FRAME_FORMAT.format(i + 1)

        # CRITICAL: Use svg2fbf's exact frame processing logic
        # Why: properlySizeDoc() modifies the SVG DOM to fix dimensions/viewBox
        # We must render the MODIFIED SVG, not the original file with transforms applied
        if i == 0:
            # First frame: process to get fixed SVG
            width, height, viewbox, transform, svg_doc = frame_processor.process_frame(svg_file, first_frame_dimensions=None)

            # ⚠️ CRITICAL SAFETY FIX: Ensure SVG root has width/height
            # attributes for Puppeteer
            #
            # WHY THIS IS NECESSARY:
            # ======================
            # Some SVG files have viewBox but no width/height attributes.
            # Without explicit width/height, Puppeteer renders at the viewBox's
            # dimensions.
            #
            # Example problem (Frame 9, viewBox="0 0 80 60", no width/height):
            #   - Puppeteer renders at 80x60 pixels (tiny!)
            #   - Content appears as a tiny box in the corner
            #
            # Solution: Add width/height to scale viewBox to target size:
            #   <svg viewBox="0 0 80 60" width="480" height="360">
            #   - Browser scales 80x60 coordinate space to 480x360 pixels (6x scale)
            #   - Content fills entire canvas correctly
            #
            # IMPORTANT:
            # ==========
            # 1. Must use pixel values (not percentages) - Puppeteer viewport doesn't
            #    properly scale percentage-based SVG dimensions
            # 2. DON'T modify viewBox - it defines the coordinate system that
            #    content uses
            # 3. render_svg.js is configured to preserve both width/height AND viewBox
            #    (see render_svg.js:169-207 for detailed explanation)
            #
            # TESTING: Changes to this logic must be tested with Frame 9, 18, 26, 34
            #
            svg_root = svg_doc.documentElement  # type: ignore[attr-defined]
            if not svg_root.getAttribute("width"):
                svg_root.setAttribute("width", str(int(first_width)))
            if not svg_root.getAttribute("height"):
                svg_root.setAttribute("height", str(int(first_height)))
            # Ensure preserveAspectRatio is set for consistent rendering
            if not svg_root.getAttribute("preserveAspectRatio"):
                svg_root.setAttribute("preserveAspectRatio", PRESERVE_ASPECT_RATIO)

            # Save modified SVG to temp file
            temp_svg = input_frames_png_dir / f"temp_frame_{i + 1:05d}.svg"
            with open(temp_svg, "w", encoding="utf-8") as f:
                svg_doc.writexml(f, encoding="utf-8")  # type: ignore[attr-defined]
        else:
            # Subsequent frames: process with first frame dimensions
            width, height, viewbox, transform, svg_doc = frame_processor.process_frame(svg_file, first_frame_dimensions=first_frame_dimensions)

            # ⚠️ CRITICAL SAFETY FIX: Ensure SVG root has width/height
            # attributes for Puppeteer
            #
            # WHY THIS IS NECESSARY:
            # ======================
            # Some SVG files have viewBox but no width/height attributes.
            # Without explicit width/height, Puppeteer renders at the viewBox's
            # dimensions.
            #
            # Example problem (Frame 9, viewBox="0 0 80 60", no width/height):
            #   - Puppeteer renders at 80x60 pixels (tiny!)
            #   - Content appears as a tiny box in the corner
            #
            # Solution: Add width/height to scale viewBox to target size:
            #   <svg viewBox="0 0 80 60" width="480" height="360">
            #   - Browser scales 80x60 coordinate space to 480x360 pixels (6x scale)
            #   - Content fills entire canvas correctly
            #
            # IMPORTANT:
            # ==========
            # 1. Must use pixel values (not percentages) - Puppeteer viewport doesn't
            #    properly scale percentage-based SVG dimensions
            # 2. DON'T modify viewBox - it defines the coordinate system that
            #    content uses
            # 3. render_svg.js is configured to preserve both width/height AND viewBox
            #    (see render_svg.js:169-207 for detailed explanation)
            #
            # TESTING: Changes to this logic must be tested with Frame 9, 18, 26, 34
            #
            svg_root = svg_doc.documentElement  # type: ignore[attr-defined]
            if not svg_root.getAttribute("width"):
                svg_root.setAttribute("width", str(int(first_width)))
            if not svg_root.getAttribute("height"):
                svg_root.setAttribute("height", str(int(first_height)))
            # Ensure preserveAspectRatio is set for consistent rendering
            if not svg_root.getAttribute("preserveAspectRatio"):
                svg_root.setAttribute("preserveAspectRatio", PRESERVE_ASPECT_RATIO)

            # Save modified SVG to temp file
            temp_svg = input_frames_png_dir / f"temp_frame_{i + 1:05d}.svg"
            with open(temp_svg, "w", encoding="utf-8") as f:
                svg_doc.writexml(f, encoding="utf-8")  # type: ignore[attr-defined]

        # Render the MODIFIED SVG
        # Why: The SVG already has the transform embedded in a <g> wrapper by
        # svg2fbf's create_scaled_group_for_svg() and width/height attributes
        # set by the code above. No additional transform needed during
        # rendering.
        success = renderer.render_svg_to_png(
            svg_path=temp_svg,
            output_png_path=png_path,
            width=int(first_width),
            height=int(first_height),
            transform=None,  # Transform already embedded in SVG structure
            viewbox=viewbox,
            preserve_aspect_ratio=PRESERVE_ASPECT_RATIO,
        )

        if not success:
            print(f"   ❌ Failed to render {svg_file.name}")
            sys.exit(1)

        input_pngs.append(png_path)
        if transform:
            print(f"   ✓ Frame {i + 1}: {svg_file.name} (transform: {transform[:40]}...)")
        else:
            print(f"   ✓ Frame {i + 1}: {svg_file.name}")

    print(f"   ✓ All {len(batch_svg_files)} input frames rendered\n")

    # Step 1.5: Create generation card with exact rendering order
    # ================================================================
    # CRITICAL ARCHITECTURE DECISION (2025-11-11):
    # Generation card is created HERE, during the run, NOT during E2E test
    # session creation. Why: We must capture the EXACT frame order used for
    # PNG rendering above. This guarantees svg2fbf uses the identical order -
    # perfect alignment!
    # ================================================================
    print("📋 Step 1.5: Creating generation card with rendered frame sequence...")

    # Get config for test parameters
    # Why: Use heuristics to find and validate project root pyproject.toml
    pyproject_path = find_project_pyproject_toml()
    test_config = SessionConfig(pyproject_path)

    # Create generation card with the exact batch_svg_files order we just used
    generation_card = {
        "metadata": {
            "title": f"Test Run - {len(batch_svg_files)} frames",
            "creators": "svg2fbf test system",
            "description": f"Test animation run with {len(batch_svg_files)} frames",
            "keywords": "test, animation, automated",
            "language": "en",
            "rights": "Test data - not for distribution",
        },
        "generation_parameters": {
            # CRITICAL: Use 'frames' list with exact order from rendering
            # This gives us absolute control - svg2fbf will use this exact order
            "frames": [str(svg_file.absolute()) for svg_file in batch_svg_files],
            "output_path": "./fbf_output",  # Will be overridden by CLI -o arg
            "filename": FILE_TEST_ANIMATION,
            "speed": float(FPS),
            "animation_type": ANIMATION_TYPE,
            "digits": DEFAULT_PRECISION_DIGITS,
            "cdigits": DEFAULT_PRECISION_CDIGITS,
            "preserve_aspect_ratio": PRESERVE_ASPECT_RATIO,
            "auto_start": AUTO_START,
            "play_on_click": PLAY_ON_CLICK,
        },
    }

    # Save generation card to THIS run directory, not session dir
    generation_card_path = output_dir / "generation_card.yaml"
    with open(generation_card_path, "w", encoding="utf-8") as f:
        yaml.dump(generation_card, f, default_flow_style=False, sort_keys=False)

    print(f"   ✓ Generation card created: {generation_card_path.name}")
    print(f"   ✓ Frame sequence: {len(batch_svg_files)} frames in exact rendering order\n")

    # Step 2: Run svg2fbf with generation card
    print("🔨 Step 2: Running svg2fbf with generation card...")
    # Why: FBF filename from CONSTANTS.py
    fbf_file = fbf_output_dir / FILE_TEST_ANIMATION

    # Why: Use --config to pass generation card
    # This ensures svg2fbf uses the EXACT frame sequence testrunner decided
    # No filtering, no reordering - absolute alignment guaranteed
    # Override output_path with CLI arg to ensure output goes to run directory
    svg2fbf_cmd = [
        "uv",
        "run",
        "svg2fbf",
        "--config",
        str(generation_card_path),
        "-o",
        str(fbf_output_dir.absolute()),  # Absolute path to run's fbf_output
        "--no-browser",  # Don't open browser during automated tests
    ]

    # Run from project root to avoid uv creating .venv in tests/
    # Generation card uses absolute paths so no need to be in output_dir
    # Why: Timeout from CONSTANTS.py (generous for large animations)
    project_root = Path(__file__).parent.parent  # tests/ -> project root
    result = subprocess.run(
        svg2fbf_cmd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SVG2FBF_CONVERSION,
        cwd=str(project_root),  # Run from project root
    )

    if result.returncode != 0:
        print("   ❌ svg2fbf failed:")
        print(f"   stdout: {result.stdout}")
        print(f"   stderr: {result.stderr}")
        sys.exit(1)

    if not fbf_file.exists():
        print(f"   ❌ FBF file not created: {fbf_file}")
        sys.exit(1)

    print(f"   ✓ FBF animation generated: {fbf_file.name}\n")

    # Step 3: Render FBF frames
    print(f"📹 Step 3: Capturing {len(batch_svg_files)} frames from FBF animation...")

    # Why: FPS from CONSTANTS.py (NON-CONFIGURABLE for deterministic timing)
    output_pngs = renderer.render_fbf_animation_frames(
        fbf_svg_path=fbf_file,
        output_dir=output_frames_png_dir,
        frame_count=len(batch_svg_files),
        fps=FPS,
        width=int(first_width),
        height=int(first_height),
    )

    if len(output_pngs) != len(batch_svg_files):
        print(f"   ❌ Expected {len(batch_svg_files)} frames, got {len(output_pngs)}")
        sys.exit(1)

    print(f"   ✓ All {len(batch_svg_files)} FBF frames captured\n")

    # Step 4: Compare frames
    print(f"🔍 Step 4: Comparing {len(batch_svg_files)} frame pairs...")

    frame_comparisons = []
    passed_count = 0
    failed_count = 0

    for i in range(len(batch_svg_files)):
        input_png = input_pngs[i]
        output_png = output_pngs[i]
        source_svg = batch_svg_files[i]

        # Compare frames using config from pyproject.toml
        is_match, diff_info = comparator.compare_images_pixel_perfect(
            input_png,
            output_png,
            tolerance=config["image_tolerance"],
            pixel_tolerance=config["pixel_tolerance"],
        )

        # Generate diff map (saved in diff_png folder)
        # Why: Diff PNG filename format from CONSTANTS.py
        diff_gray_path = diff_png_dir / PNG_DIFF_FRAME_FORMAT.format(i + 1)
        comparator.generate_grayscale_diff_map(input_png, output_png, diff_gray_path)

        diff_percentage = diff_info.get("diff_percentage", 0.0)
        diff_pixels = diff_info.get("diff_pixels", 0)
        total_pixels = diff_info.get("total_pixels", 0)

        frame_comparisons.append(
            {
                "frame_num": i + 1,
                "input_png": input_png,
                "output_png": output_png,
                "diff_gray": diff_gray_path,
                "diff_percentage": diff_percentage,
                "diff_pixels": diff_pixels,
                "total_pixels": total_pixels,
                "source_svg": source_svg,
                "is_identical": is_match,  # Add pass/fail status for HTML report
            }
        )

        status = "✓" if is_match else "✗"
        print(f"   {status} Frame {i + 1}: {diff_percentage:.4f}% difference")

        if is_match:
            passed_count += 1
        else:
            failed_count += 1

    print()
    print(f"   Summary: {passed_count} passed, {failed_count} failed\n")

    # Step 5: Generate HTML report
    print("📊 Step 5: Generating HTML comparison report...")

    # Extract SVG viewBox dimensions (format: "x y width height")
    svg_width = 0
    svg_height = 0
    if first_viewbox:
        try:
            viewbox_parts = str(first_viewbox).split()
            if len(viewbox_parts) >= 4:
                svg_width = int(float(viewbox_parts[2]))  # viewBox width
                svg_height = int(float(viewbox_parts[3]))  # viewBox height
        except (ValueError, IndexError):
            pass  # Keep defaults if parsing fails

    # Why: Test config values from CONSTANTS.py (NON-CONFIGURABLE for tests)
    report_config: dict[str, Any] = {
        "session_id": session_id,  # Use session_id instead of testrun timestamp
        "frame_count": len(batch_svg_files),
        "fps": FPS,
        "animation_type": ANIMATION_TYPE,
        "width": int(first_width),
        "height": int(first_height),
        "svg_width": svg_width,  # Original SVG viewBox width
        "svg_height": svg_height,  # Original SVG viewBox height
        "precision_digits": DEFAULT_PRECISION_DIGITS,
        "precision_cdigits": DEFAULT_PRECISION_CDIGITS,
        "tolerance": config["image_tolerance"],  # Add tolerance for HTML report
        "pixel_tolerance": config["pixel_tolerance"],  # Add pixel tolerance for HTML report
        "output_frames_dir": output_frames_png_dir,  # Path to output PNG
        # frames directory
        "fbf_file": fbf_file,  # Path to FBF animation file
    }

    batch_info = {
        "batch_dir": session_input_frames_dir,  # Use session-level input_frames path
        "svg_sources": sorted(session_input_frames_dir.glob("*.svg")),  # Use session SVGs
    }

    report_path = output_dir / "comparison_report.html"
    HTMLReportGenerator.generate_comparison_report(
        report_path=report_path,
        test_config=report_config,
        frame_comparisons=frame_comparisons,
        batch_info=batch_info,
        navigation_data=navigation_data,
    )

    print(f"   ✓ HTML report: {report_path}\n")

    # Save E2E test sessions for session listing
    result_data = {
        "timestamp": timestamp,
        "session_id": session_id,
        "frame_count": len(batch_svg_files),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "all_passed": failed_count == 0,
        "tolerance": config["image_tolerance"],
        "pixel_tolerance": config["pixel_tolerance"],
    }

    result_file = output_dir / "test_result.json"
    with open(result_file, "w") as f:
        json.dump(result_data, f, indent=2)

    # Step 6: Open in browser (optional for batch runs)
    if open_in_browser:
        # Why: Detect Chrome (recommended) or fall back to default browser
        browser_cmd, browser_name = get_preferred_browser()
        print(f"🌐 Step 6: Opening HTML report in {browser_name}...")
        subprocess.run([*browser_cmd, str(report_path)])
        print("   ✓ Report opened\n")

        print("=" * SEPARATOR_WIDTH)
        print("✅ Test complete!")
        print(f"📁 Results: {output_dir}")
        print(f"📊 Report:  {report_path}")
        print("=" * SEPARATOR_WIDTH)
    else:
        print("=" * SEPARATOR_WIDTH)
        print("✅ Test complete!")
        print(f"📁 Results: {output_dir}")
        print(f"📊 Report:  {report_path}")
        print("=" * SEPARATOR_WIDTH)

    return report_path


if __name__ == "__main__":
    main()
