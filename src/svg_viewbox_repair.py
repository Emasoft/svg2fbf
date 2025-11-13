#!/usr/bin/env python3
"""
SVG ViewBox Repair Utility

This module provides tools to automatically calculate and add viewBox attributes
to SVG files using Puppeteer/headless Chrome for accurate bounding box calculation.

For animation sequences, it uses a union bbox strategy to ensure all frames
share the same viewBox, preventing frame-to-frame jumping.

Usage:
    From command line:
        svg-repair-viewbox file1.svg file2.svg file3.svg
        svg-repair-viewbox /path/to/svg/directory

    From Python:
        from svg_viewbox_repair import repair_animation_sequence_viewbox
        repair_animation_sequence_viewbox([Path("frame1.svg"), Path("frame2.svg")])
"""

import json
import os
import re
import subprocess
import sys
import sysconfig
import xml.etree.ElementTree as ET
from pathlib import Path

# Constants
VIEWBOX_COMPONENT_COUNT = 4  # viewBox must have exactly 4 values: x y width height
TIMEOUT_BBOX_CALCULATION = 30  # seconds


def get_node_scripts_dir() -> Path:
    """
    Find the node_scripts directory for the installed package.

    Returns:
        Path to node_scripts directory

    Raises:
        RuntimeError: If node_scripts directory cannot be found
    """
    # Method 1: Try installed package location (shared-data)
    # When installed via wheel, scripts are in share/svg2fbf/node_scripts
    try:
        # Get the data directory for the current environment
        data_dir = Path(sysconfig.get_path("data"))
        installed_scripts = data_dir / "share" / "svg2fbf" / "node_scripts"

        if installed_scripts.exists():
            return installed_scripts
    except Exception:
        pass

    # Method 2: Try development/source installation
    # When running from source, __file__ is in project/src/
    current = Path(__file__).resolve().parent

    # Try to find project root by looking for pyproject.toml
    search_path = current
    while search_path != search_path.parent:
        if (search_path / "pyproject.toml").exists():
            source_scripts = search_path / "tests" / "node_scripts"
            if source_scripts.exists():
                return source_scripts
            break
        search_path = search_path.parent

    # Method 3: Check if we're in editable install (common location)
    # When installed with `pip install -e .` or `uv pip install -e .`
    editable_scripts = current.parent / "tests" / "node_scripts"
    if editable_scripts.exists():
        return editable_scripts

    # Build error message with path information
    data_dir_path = data_dir / "share" / "svg2fbf" / "node_scripts" if "data_dir" in locals() else "N/A"
    search_path_path = search_path / "tests" / "node_scripts" if "search_path" in locals() else "N/A"

    raise RuntimeError(
        "❌ Cannot find node_scripts directory\n\n"
        "The viewBox repair utility requires Node.js scripts that should be\n"
        "included with svg2fbf installation.\n\n"
        "Tried locations:\n"
        f"  - {data_dir_path}\n"
        f"  - {search_path_path}\n"
        f"  - {editable_scripts}\n\n"
        "Try reinstalling svg2fbf:\n"
        "  uv tool uninstall svg2fbf\n"
        "  uv tool install svg2fbf"
    )


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
    # Find the node_scripts directory
    try:
        scripts_dir = get_node_scripts_dir()
    except RuntimeError as e:
        raise RuntimeError(str(e)) from e

    script_path = scripts_dir / "calculate_bbox.js"

    if not script_path.exists():
        raise RuntimeError(f"❌ calculate_bbox.js not found at {script_path}\n\nThis script is required for calculating bounding boxes.\nScripts directory found at: {scripts_dir}\n\nTry reinstalling svg2fbf:\n  uv tool uninstall svg2fbf\n  uv tool install svg2fbf")

    # Run Node.js script to calculate bbox
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

            # Check if error is due to missing puppeteer
            if "Cannot find module 'puppeteer'" in error_msg or "MODULE_NOT_FOUND" in error_msg:
                raise RuntimeError(
                    "❌ Puppeteer not found\n\n"
                    "The viewBox repair utility requires Puppeteer to be installed.\n\n"
                    "To install Puppeteer:\n\n"
                    "  Option 1 - Install globally (recommended):\n"
                    "    npm install -g puppeteer\n\n"
                    "  Option 2 - Install in scripts directory:\n"
                    f"    cd {scripts_dir.parent}\n"
                    "    npm install\n\n"
                    "For more information, see:\n"
                    "https://github.com/Emasoft/svg2fbf#svg-viewbox-repair-utility"
                )

            raise RuntimeError(f"Failed to calculate bbox: {error_msg}")

        # Parse JSON output
        bbox_raw = json.loads(result.stdout.strip())

        # Validate bbox structure and type
        required_keys = {"x", "y", "width", "height"}
        if not isinstance(bbox_raw, dict) or not all(k in bbox_raw for k in required_keys):
            raise RuntimeError(f"Invalid bbox JSON: {bbox_raw}")

        # Type-safe bbox construction
        bbox: dict[str, float] = {
            "x": float(bbox_raw["x"]),
            "y": float(bbox_raw["y"]),
            "width": float(bbox_raw["width"]),
            "height": float(bbox_raw["height"]),
        }

        return bbox

    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Bbox calculation timed out after {TIMEOUT_BBOX_CALCULATION} seconds") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse bbox JSON: {e}") from e
    except FileNotFoundError as e:
        raise RuntimeError(
            "❌ Node.js not found\n\n"
            "The viewBox repair utility requires Node.js and Puppeteer.\n\n"
            "To install:\n\n"
            "  macOS:\n"
            "    brew install node\n"
            "    npm install -g puppeteer\n\n"
            "  Linux:\n"
            "    sudo apt install nodejs npm\n"
            "    npm install -g puppeteer\n\n"
            "  Windows:\n"
            "    Download from https://nodejs.org\n"
            "    npm install -g puppeteer\n\n"
            "For more information, see the svg2fbf documentation:\n"
            "https://github.com/Emasoft/svg2fbf#svg-viewbox-repair-utility"
        ) from e
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
            svg_tag_match = re.search(r"<svg[\s\S]*?>", content)
            if not svg_tag_match:
                raise RuntimeError("Could not find <svg> tag in file")

            svg_tag = svg_tag_match.group(0)

            # Insert viewBox attribute before closing >
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

        # For existing viewBox, use ElementTree to write back
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
    min_x = min(b["x"] for b in bboxes)
    min_y = min(b["y"] for b in bboxes)
    max_x_extent = max(b["x"] + b["width"] for b in bboxes)
    max_y_extent = max(b["y"] + b["height"] for b in bboxes)

    union_width = max_x_extent - min_x
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
    1. Checks if all frames have viewBox
    2. If any are missing, calculates bbox for each frame
    3. Computes union bbox that encompasses all frames
    4. Applies the SAME viewBox to ALL frames

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
            if verbose:
                print("   ⚠️  Frames have DIFFERENT viewBoxes!")
                for i, vb in enumerate(viewboxes[:5], 1):
                    print(f"      Frame {i}: {vb}")
                if len(viewboxes) > 5:
                    print(f"      ... and {len(viewboxes) - 5} more")
                print("\n   ℹ️  Calculating union bbox to harmonize viewBoxes...")

    # Calculate union bbox across ALL frames
    union_bbox = calculate_union_bbox(svg_files, verbose=verbose)

    # Apply union bbox to ALL frames
    if verbose:
        print("   🔧 Applying union viewBox to all frames...")

    repair_count = 0
    for i, svg_file in enumerate(svg_files, 1):
        try:
            # Apply union bbox (overwrites existing viewBox if present)
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


def ensure_dependencies() -> bool:
    """
    Ensure all dependencies (Node.js, Puppeteer) are available.
    Automatically installs them if missing.

    Returns:
        True if dependencies are ready, False if installation failed
    """
    try:
        from . import auto_install_deps

        # First check if dependencies are already available
        ready, _ = auto_install_deps.check_dependencies()
        if ready:
            return True

        # Dependencies missing - try auto-install
        print("\n⚙️  First-time setup: Installing required dependencies...")
        print()
        return auto_install_deps.setup_dependencies(silent=False)

    except ImportError:
        # auto_install_deps not available (shouldn't happen)
        return False
    except Exception as e:
        print(f"\n⚠️  Automatic dependency installation failed: {e}\n", file=sys.stderr)
        return False


def cli() -> None:
    """Command-line interface for SVG viewBox repair utility."""
    import argparse

    # Detect if run with "uv run" which creates unwanted .venv directories
    # (and potentially pyproject.toml, .git/)
    if Path.cwd() != Path.home() and (Path.cwd() / ".venv").exists() and "UV_PROJECT_ENVIRONMENT" in os.environ:
        print("\n⚠️  WARNING: Detected 'uv run' usage which creates unwanted artifacts!")
        print("    UV may have created: .venv/, pyproject.toml, .git/, hello.py")
        print("    This is NOT the recommended way to use svg-repair-viewbox.\n")
        print("    Recommended installation:")
        print("      uv tool install svg2fbf\n")
        print("    Then use directly:")
        print("      svg-repair-viewbox file.svg\n")
        print("    Cleanup: rm -rf .venv/ pyproject.toml .git/ hello.py README.md\n")
        print("    Continuing anyway...\n")

    parser = argparse.ArgumentParser(
        description=("Repair SVG viewBox attributes using Puppeteer/headless Chrome for accurate bbox calculation"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Repair a single SVG file
  svg-repair-viewbox image.svg

  # Repair multiple SVG files (animation sequence)
  svg-repair-viewbox frame001.svg frame002.svg frame003.svg

  # Repair all SVG files in a directory
  svg-repair-viewbox /path/to/svg/directory

  # Quiet mode (no progress output)
  svg-repair-viewbox --quiet *.svg

Notes:
  - For animation sequences, all frames will get the SAME viewBox (union bbox)
  - This prevents frame-to-frame jumping in animations
  - Requires Node.js to be installed for Puppeteer
        """,
    )

    parser.add_argument("paths", nargs="+", help="SVG file(s) or directory containing SVG files")

    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")

    # Get version from package metadata
    try:
        from importlib.metadata import version as get_version

        pkg_version = get_version("svg2fbf")
    except Exception:
        pkg_version = "0.1.0"

    parser.add_argument(
        "--version",
        action="version",
        version=f"svg-repair-viewbox {pkg_version}",
        help="Show version and exit",
    )

    args = parser.parse_args()

    # Ensure dependencies are installed (auto-install if missing)
    if not ensure_dependencies():
        print("\n❌ Failed to install required dependencies", file=sys.stderr)
        print("\nPlease install manually:", file=sys.stderr)
        print("  1. Node.js: https://nodejs.org", file=sys.stderr)
        print("  2. Puppeteer: npm install -g puppeteer", file=sys.stderr)
        print("\nFor more help, see:", file=sys.stderr)
        print(
            "  https://github.com/Emasoft/svg2fbf#svg-viewbox-repair-utility",
            file=sys.stderr,
        )
        sys.exit(1)

    # Collect SVG files
    svg_files = []

    for path_str in args.paths:
        path = Path(path_str)

        if not path.exists():
            print(f"❌ Error: Path does not exist: {path}", file=sys.stderr)
            sys.exit(1)

        if path.is_dir():
            # Collect all SVG files in directory
            dir_svgs = sorted(path.glob("*.svg"))
            if not dir_svgs:
                print(f"⚠️  Warning: No SVG files found in {path}", file=sys.stderr)
            else:
                svg_files.extend(dir_svgs)

        elif path.is_file():
            if path.suffix.lower() != ".svg":
                print(f"⚠️  Warning: {path} is not an SVG file, skipping", file=sys.stderr)
            else:
                svg_files.append(path)
        else:
            print(f"❌ Error: {path} is not a file or directory", file=sys.stderr)
            sys.exit(1)

    if not svg_files:
        print("❌ Error: No SVG files found", file=sys.stderr)
        sys.exit(1)

    verbose = not args.quiet

    if verbose:
        print(f"Found {len(svg_files)} SVG file(s)")
        print()

    # Repair viewBoxes
    try:
        repair_count = repair_animation_sequence_viewbox(svg_files, verbose=verbose)

        if verbose:
            if repair_count == 0:
                print("✅ All files already have correct viewBox attributes")
            else:
                print(f"✅ Successfully repaired {repair_count} file(s)")

        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user", file=sys.stderr)
        sys.exit(130)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback

        if verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli()
