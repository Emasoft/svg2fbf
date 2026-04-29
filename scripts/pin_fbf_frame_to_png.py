#!/usr/bin/env python3
"""
Render frame N of an FBF.SVG to PNG by pinning the animation timeline.

This is a calibration utility for the text→path Docker E2E test. Its job
is to verify that golden FBF references are faithful conversions of the
original input frames — i.e. that text elements were converted to paths
without visible drift. Compare its PNG output against the same-frame
input rendered through `sbb-svg2png` (also from svg-bbox) and inspect
diffs by eye or via `sbb-compare`.

How it differs from `extract_fbf_frame.py` (also in this folder):

  extract_fbf_frame.py
    XML-lifts <g id="FRAMENNNNN"> + <g id="SHARED_DEFINITIONS"> into a
    fresh standalone SVG and emits THAT SVG. Loses ancestor inheritance
    from ANIMATION_BACKDROP > ANIMATION_STAGE > ANIMATED_GROUP > PROSKENION
    and any STAGE_FOREGROUND / OVERLAY_LAYER content.

  pin_fbf_frame_to_png.py (this script)
    Mutates a copy of the FBF.SVG so PROSKENION's xlink:href points at
    FRAMENNNNN and drops the <animate> child. Renders the mutated FBF
    via sbb-svg2png. Preserves all ancestor inheritance, foreground/
    overlay layers, and root SVG attributes — i.e. exactly what a
    viewer sees at frame N.

The "advance the SMIL timeline" capability would belong upstream in
sbb-svg2png itself; tracked at:
    https://github.com/Emasoft/SVG-BBOX/issues/3

Pure stdlib + an `sbb-svg2png` subprocess.

Exit codes:
  0  — PNG rendered successfully
  1  — sbb-svg2png returned a non-zero exit code
  2  — invocation error (bad args, missing file, frame not found, etc.)
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
PROSKENION_ID = "PROSKENION"
FRAME_ID_RE = re.compile(r"^FRAME(\d+)$")


def _find_by_id(root: ET.Element, target_id: str) -> ET.Element | None:
    for elem in root.iter():
        if elem.attrib.get("id") == target_id:
            return elem
    return None


def _frame_index_to_id(root: ET.Element, frame_index: int) -> str:
    """Map a 1-based frame index to the actual element id used in this FBF.

    Different FBF outputs may use different zero-padding (FRAME0001 vs
    FRAME00001). We discover the padding from the FBF itself by scanning
    every ``id`` matching ``FRAME\\d+`` and matching the numeric part.
    """
    matches: list[tuple[int, str]] = []
    for elem in root.iter():
        elem_id = elem.attrib.get("id", "")
        m = FRAME_ID_RE.match(elem_id)
        if m:
            matches.append((int(m.group(1)), elem_id))
    if not matches:
        raise ValueError("FBF has no <g id='FRAME…'> elements — not an FBF.SVG?")
    for num, elem_id in matches:
        if num == frame_index:
            return elem_id
    available = sorted(num for num, _ in matches)
    raise ValueError(f"Frame {frame_index} not found. Available frames: {available[:5]}" + (f" … (+{len(available) - 5} more)" if len(available) > 5 else ""))


def _pin_proskenion(root: ET.Element, target_frame_id: str) -> None:
    """Set PROSKENION's xlink:href to #target_frame_id and drop its <animate> child."""
    proskenion = _find_by_id(root, PROSKENION_ID)
    if proskenion is None:
        raise ValueError(f"FBF has no <use id='{PROSKENION_ID}'> — not an FBF.SVG?")

    new_href = f"#{target_frame_id}"
    href_attr_xlink = f"{{{XLINK_NS}}}href"
    if href_attr_xlink in proskenion.attrib:
        proskenion.attrib[href_attr_xlink] = new_href
    if "href" in proskenion.attrib:
        # SVG2 uses bare ``href``. Keep both in sync if both are present.
        proskenion.attrib["href"] = new_href
    if href_attr_xlink not in proskenion.attrib and "href" not in proskenion.attrib:
        proskenion.attrib[href_attr_xlink] = new_href

    # Remove <animate> children that target xlink:href / href so the
    # SMIL playback can't override our pinned value.
    for child in list(proskenion):
        tag = child.tag
        local = tag.split("}", 1)[1] if "}" in tag else tag
        if local != "animate":
            continue
        attr_name = child.attrib.get("attributeName", "")
        if attr_name in ("xlink:href", "href"):
            proskenion.remove(child)


def render(
    fbf_path: Path,
    frame_index: int,
    output_png: Path,
    sbb_svg2png: str,
    extra_args: list[str],
) -> int:
    if not fbf_path.is_file():
        raise FileNotFoundError(f"FBF not found: {fbf_path}")

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)

    tree = ET.parse(fbf_path)
    root = tree.getroot()
    if root is None:
        raise ValueError(f"Empty XML root in {fbf_path}")
    target_frame_id = _frame_index_to_id(root, frame_index)
    _pin_proskenion(root, target_frame_id)

    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_png_abs = output_png.resolve()

    with tempfile.TemporaryDirectory(prefix="pin_fbf_") as tmpdir:
        tmp_root = Path(tmpdir)
        pinned_svg = tmp_root / "pinned.svg"
        tmp_png = tmp_root / "out.png"
        tree.write(pinned_svg, encoding="utf-8", xml_declaration=True)

        # sbb-svg2png locks file paths to process.cwd() (no --allow-paths
        # flag exists). Stage the render entirely inside `tmpdir` with
        # relative paths, then copy the PNG to the user's chosen output.
        cmd = [sbb_svg2png, "pinned.svg", "out.png", *extra_args]
        proc = subprocess.run(cmd, cwd=str(tmp_root), check=False)
        if proc.returncode != 0:
            return proc.returncode
        if not tmp_png.is_file():
            print(
                f"pin_fbf_frame_to_png: sbb-svg2png returned 0 but no PNG at {tmp_png}",
                file=sys.stderr,
            )
            return 1
        shutil.copyfile(tmp_png, output_png_abs)
        return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a single frame of an FBF.SVG to PNG by pinning PROSKENION.")
    parser.add_argument("fbf", type=Path, help="Path to the FBF .svg file")
    parser.add_argument("frame", type=int, help="1-based frame index")
    parser.add_argument("output", type=Path, help="Output PNG path")
    parser.add_argument(
        "--sbb-svg2png",
        default=None,
        help="Path to sbb-svg2png (default: search PATH)",
    )
    parser.add_argument(
        "--scale",
        type=str,
        default=None,
        help="Resolution multiplier passed straight to sbb-svg2png (default: tool's own default)",
    )
    parser.add_argument(
        "--background",
        type=str,
        default=None,
        help="Background color passed straight to sbb-svg2png",
    )
    parser.add_argument(
        "--width",
        type=str,
        default=None,
        help="Output width in pixels (forwarded to sbb-svg2png)",
    )
    parser.add_argument(
        "--height",
        type=str,
        default=None,
        help="Output height in pixels (forwarded to sbb-svg2png)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    sbb_svg2png = args.sbb_svg2png or shutil.which("sbb-svg2png")
    if not sbb_svg2png:
        print(
            "pin_fbf_frame_to_png: sbb-svg2png not found on PATH. Install svg-bbox toolkit or pass --sbb-svg2png /path/to/sbb-svg2png.",
            file=sys.stderr,
        )
        return 2

    extra: list[str] = []
    if args.scale is not None:
        extra += ["--scale", args.scale]
    if args.background is not None:
        extra += ["--background", args.background]
    if args.width is not None:
        extra += ["--width", args.width]
    if args.height is not None:
        extra += ["--height", args.height]

    try:
        return render(args.fbf, args.frame, args.output, sbb_svg2png, extra)
    except (FileNotFoundError, ValueError, ET.ParseError) as e:
        print(f"pin_fbf_frame_to_png: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
