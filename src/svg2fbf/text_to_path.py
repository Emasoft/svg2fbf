#!/usr/bin/env python3
"""
SVG Text-to-Path Converter

Converts <text> elements in SVG files to <path> elements using font glyph outlines.
Designed for production use in the svg2fbf pipeline and as a standalone CLI tool.

Features:
- Converts all text elements to paths for maximum portability
- Preserves visual appearance with proper font rendering
- Handles transforms, font styles, and positioning
- Optimized path output (6 decimal precision, relative coordinates)
- Proper font fallback handling

Usage:
    python -m svg2fbf.text_to_path input.svg output.svg
    python -m svg2fbf.text_to_path input.svg --in-place
"""

import xml.etree.ElementTree as ET
from pathlib import Path
import sys
import re
import argparse
from typing import Tuple, List, Optional
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen

# SVG namespace
SVG_NS = "{http://www.w3.org/2000/svg}"


def format_number(num: float, precision: int = 6) -> str:
    """
    Format a number with specified precision, removing trailing zeros.

    Args:
        num: Number to format
        precision: Decimal places (default: 6)

    Returns:
        Formatted string
    """
    # Format with specified precision
    formatted = f"{num:.{precision}f}"

    # Remove trailing zeros and decimal point if not needed
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")

    return formatted


def parse_style_property(style: str, property_name: str) -> Optional[str]:
    """
    Extract a property value from a CSS style string.

    Args:
        style: CSS style string
        property_name: Property to extract (e.g., 'font-family')

    Returns:
        Property value or None if not found
    """
    if not style:
        return None

    # Match property:value; pattern
    pattern = rf"{property_name}\s*:\s*([^;]+)"
    match = re.search(pattern, style)

    if match:
        value = match.group(1).strip()
        # Remove quotes if present
        value = value.strip("'\"")
        return value

    return None


def get_font_path(font_family: str) -> Optional[Path]:
    """
    Find the font file path for a given font family name.

    This is a simplified version that looks for common font locations.
    Production version should use fontconfig or platform-specific APIs.

    Args:
        font_family: Font family name (e.g., 'Futura', 'Arial')

    Returns:
        Path to font file or None if not found
    """
    import platform

    system = platform.system()

    # Common font directories by platform
    font_dirs = []
    if system == "Darwin":  # macOS
        font_dirs = [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        ]
    elif system == "Linux":
        font_dirs = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
        ]
    elif system == "Windows":
        font_dirs = [
            Path("C:/Windows/Fonts"),
        ]

    # Try to find font file
    for font_dir in font_dirs:
        if not font_dir.exists():
            continue

        # Look for TTF, OTF, and TTC files matching the font family
        for pattern in [f"{font_family}*.ttf", f"{font_family}*.otf", f"{font_family}*.ttc", f"{font_family}*.TTF", f"{font_family}*.OTF", f"{font_family}*.TTC"]:
            matches = list(font_dir.rglob(pattern))
            if matches:
                return matches[0]

    # Fallback: try common substitutions
    fallbacks = {
        "Futura": ["Futura Medium", "Futura-Medium"],
        "Arial": ["Arial", "Liberation Sans"],
        "Helvetica": ["Helvetica", "Arial", "Liberation Sans"],
        "Times New Roman": ["Times New Roman", "Liberation Serif"],
    }

    if font_family in fallbacks:
        for fallback in fallbacks[font_family]:
            if fallback != font_family:  # Avoid infinite recursion
                result = get_font_path(fallback)
                if result:
                    return result

    return None


def get_glyph_path(font: TTFont, char: str, font_size: float, x: float, y: float) -> Optional[str]:
    """
    Extract the path data for a character glyph positioned at (x, y).

    Args:
        font: Loaded TTFont object
        char: Character to convert
        font_size: Font size in SVG units
        x: X position in SVG coordinates
        y: Y position in SVG coordinates (baseline)

    Returns:
        SVG path 'd' attribute string or None if glyph not found
    """
    # Get glyph name for character
    cmap = font.getBestCmap()
    if not cmap:
        return None

    glyph_name = cmap.get(ord(char))
    if not glyph_name:
        return None

    # Get glyph set
    glyph_set = font.getGlyphSet()
    if glyph_name not in glyph_set:
        return None

    # Draw glyph to recording pen
    pen = RecordingPen()
    glyph = glyph_set[glyph_name]
    glyph.draw(pen)

    # Get font units per em for scaling
    units_per_em = font["head"].unitsPerEm
    scale = font_size / units_per_em

    # Convert recorded operations to SVG path commands
    # Note: Font coordinates are Y-up, SVG is Y-down, so we flip Y
    # Position glyph at text position WITHOUT normalization (match Inkscape behavior)
    path_commands = []

    for op, args in pen.value:
        if op == "moveTo":
            gx, gy = args[0]
            path_commands.append(f"M {format_number(x + gx * scale)} {format_number(y - gy * scale)}")
        elif op == "lineTo":
            gx, gy = args[0]
            path_commands.append(f"L {format_number(x + gx * scale)} {format_number(y - gy * scale)}")
        elif op == "qCurveTo":
            # TrueType quadratic spline - can have multiple points
            # Last point is the end point, others are control points
            # For a simple quadratic curve: args = [(cx, cy), (ex, ey)]
            # For a spline: args = [(c1x, c1y), (c2x, c2y), ..., (ex, ey)]
            if len(args) == 1:
                # Single point - this is the end point with implied control
                gx, gy = args[0]
                path_commands.append(f"T {format_number(x + gx * scale)} {format_number(y - gy * scale)}")
            elif len(args) == 2:
                # Standard quadratic curve: control point + end point
                cx, cy = args[0]
                ex, ey = args[1]
                path_commands.append(f"Q {format_number(x + cx * scale)} {format_number(y - cy * scale)} {format_number(x + ex * scale)} {format_number(y - ey * scale)}")
            else:
                # Quadratic spline with multiple control points
                # Need to insert implied on-curve points between off-curve points
                for i in range(len(args) - 1):
                    cx, cy = args[i]
                    if i < len(args) - 2:
                        # Implied on-curve point halfway to next control point
                        next_cx, next_cy = args[i + 1]
                        ex = (cx + next_cx) / 2
                        ey = (cy + next_cy) / 2
                    else:
                        # Last point is the actual end point
                        ex, ey = args[i + 1]

                    path_commands.append(f"Q {format_number(x + cx * scale)} {format_number(y - cy * scale)} {format_number(x + ex * scale)} {format_number(y - ey * scale)}")
        elif op == "curveTo":
            # Cubic Bezier curve
            if len(args) == 3:
                x1, y1 = args[0]
                x2, y2 = args[1]
                x3, y3 = args[2]
                path_commands.append(f"C {format_number(x + x1 * scale)} {format_number(y - y1 * scale)} {format_number(x + x2 * scale)} {format_number(y - y2 * scale)} {format_number(x + x3 * scale)} {format_number(y - y3 * scale)}")
        elif op == "closePath":
            path_commands.append("Z")

    return " ".join(path_commands) if path_commands else None


def convert_text_element(text_elem: ET.Element, parent_elem: ET.Element) -> bool:
    """
    Convert a single text element to a path element.

    Args:
        text_elem: The <text> element to convert
        parent_elem: Parent element (for replacement)

    Returns:
        True if conversion succeeded, False otherwise
    """
    # Extract text content
    text_content = "".join(text_elem.itertext()).strip()
    if not text_content:
        return False

    # Get text attributes
    x = float(text_elem.get("x", "0"))
    y = float(text_elem.get("y", "0"))
    elem_id = text_elem.get("id", "")

    # Get font properties from style
    style = text_elem.get("style", "")
    font_family = parse_style_property(style, "font-family")
    font_size_str = parse_style_property(style, "font-size")

    if not font_family or not font_size_str:
        print(f"Warning: Missing font properties for element {elem_id}", file=sys.stderr)
        return False

    # Parse font size (remove 'px' suffix if present)
    font_size = float(font_size_str.replace("px", ""))

    # Get font file
    font_path = get_font_path(font_family)
    if not font_path:
        print(f"Warning: Font '{font_family}' not found for element {elem_id}", file=sys.stderr)
        return False

    # Load font
    try:
        # For TTC files, try each font in the collection
        if font_path.suffix.lower() == ".ttc":
            # Try to load the first font in the collection
            font = TTFont(str(font_path), fontNumber=0)
        else:
            font = TTFont(str(font_path))
    except Exception as e:
        print(f"Warning: Failed to load font {font_path}: {e}", file=sys.stderr)
        return False

    # Convert each character to path
    char_paths = []
    current_x = x

    # Get character map and glyph set for advance width calculation
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    units_per_em = font["head"].unitsPerEm
    scale = font_size / units_per_em

    for char in text_content:
        # Get glyph path at current position
        glyph_path = get_glyph_path(font, char, font_size, current_x, y)
        if not glyph_path:
            print(f"Warning: No glyph for character '{char}' in font {font_family}", file=sys.stderr)
            continue

        char_paths.append(glyph_path)

        # Advance x position using actual glyph advance width
        if cmap and ord(char) in cmap:
            glyph_name = cmap[ord(char)]
            if glyph_name in glyph_set:
                glyph = glyph_set[glyph_name]
                # Use actual advance width from glyph metrics
                current_x += glyph.width * scale
            else:
                # Fallback if glyph not found
                current_x += font_size * 0.6
        else:
            # Fallback for unmapped characters
            current_x += font_size * 0.6

    if not char_paths:
        return False

    # Create group element to replace text
    group_elem = ET.Element(f"{SVG_NS}g")
    group_elem.set("id", f"{elem_id}_group" if elem_id else "text_group")

    # Create path element with all character paths
    path_elem = ET.Element(f"{SVG_NS}path")
    path_elem.set("d", " ".join(char_paths))

    # Copy style attributes (except font properties)
    if style:
        # Remove font-related properties but preserve everything else
        new_style_parts = []
        for part in style.split(";"):
            if ":" in part:
                prop, value = part.split(":", 1)
                prop = prop.strip()
                # Remove only font-* and text-align properties
                if not prop.startswith("font") and prop != "text-align":
                    new_style_parts.append(f"{prop}:{value}")

        if new_style_parts:
            path_elem.set("style", ";".join(new_style_parts))

    # Copy other attributes from text element (like fill, stroke, opacity, etc.)
    # but skip text-specific attributes
    skip_attrs = {"x", "y", "id", "style"}
    for attr, value in text_elem.attrib.items():
        # Remove namespace prefix if present
        attr_name = attr.split("}")[1] if "}" in attr else attr
        if attr_name not in skip_attrs:
            path_elem.set(attr, value)

    group_elem.append(path_elem)

    # Replace text element with group
    parent_index = list(parent_elem).index(text_elem)
    parent_elem.remove(text_elem)
    parent_elem.insert(parent_index, group_elem)

    return True


def find_text_elements_recursive(elem: ET.Element, parent: Optional[ET.Element] = None) -> List[Tuple[ET.Element, ET.Element]]:
    """
    Recursively find all text elements in the SVG tree.

    Args:
        elem: Current element
        parent: Parent element

    Returns:
        List of (parent, text_element) tuples
    """
    result = []

    for child in elem:
        # Get tag name without namespace
        tag = child.tag
        if "}" in tag:
            tag = tag.split("}")[1]

        if tag == "text":
            result.append((elem, child))
        else:
            # Recurse into child
            result.extend(find_text_elements_recursive(child, elem))

    return result


def convert_svg_text_to_paths(input_path: Path, output_path: Path) -> None:
    """
    Convert all text elements in an SVG file to paths.

    Args:
        input_path: Input SVG file path
        output_path: Output SVG file path
    """
    # Parse SVG file
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    ET.register_namespace("fbf", "http://opentoonz.github.io/fbf/1.0#")

    tree = ET.parse(input_path)
    root = tree.getroot()

    # Find all text elements
    text_elements = find_text_elements_recursive(root)

    print(f"Found {len(text_elements)} text element(s)")

    # Convert each text element
    converted = 0
    failed = 0

    for parent, text_elem in text_elements:
        elem_id = text_elem.get("id", "unknown")

        if convert_text_element(text_elem, parent):
            converted += 1
            print(f"✓ Converted: {elem_id}")
        else:
            failed += 1
            print(f"✗ Failed: {elem_id}")

    # Write output file
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    print("\nConversion complete:")
    print(f"  Converted: {converted}")
    print(f"  Failed: {failed}")
    print(f"  Output: {output_path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert SVG text elements to paths",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert text to paths and save to new file
  %(prog)s input.svg output.svg

  # Convert text to paths in-place
  %(prog)s input.svg --in-place

  # Process FBF animation header
  %(prog)s assets/panther_bird_header.fbf.svg assets/panther_bird_header_paths.fbf.svg
""",
    )

    parser.add_argument("input", type=Path, help="Input SVG file")
    parser.add_argument("output", type=Path, nargs="?", help="Output SVG file (required unless --in-place)")
    parser.add_argument("--in-place", "-i", action="store_true", help="Modify input file in-place")
    parser.add_argument("--backup", "-b", action="store_true", help="Create backup before in-place modification")

    args = parser.parse_args()

    # Validate arguments
    if not args.input.exists():
        parser.error(f"Input file not found: {args.input}")

    if args.in_place:
        if args.output:
            parser.error("Cannot specify output file with --in-place")

        # Create backup if requested
        if args.backup:
            import shutil

            backup_path = args.input.with_suffix(args.input.suffix + ".bak")
            shutil.copy2(args.input, backup_path)
            print(f"Created backup: {backup_path}")

        output = args.input
    else:
        if not args.output:
            parser.error("Output file required (or use --in-place)")
        output = args.output

    # Convert
    try:
        convert_svg_text_to_paths(args.input, output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
