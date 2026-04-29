#!/usr/bin/env python3
"""
Extract a single frame from an FBF.SVG into a standalone, renderable SVG.

The FBF format collects all animation frames as `<g id="FRAMENNNNN">`
elements inside the document's `<defs>`, often with shared geometry
deduplicated into `<g id="SHARED_DEFINITIONS">` and referenced from each
frame via `<use xlink:href="#...">`. To compare a frame against its
input source visually, we need that frame as a self-contained SVG with
the exact same viewBox.

Usage:
    extract_fbf_frame.py <fbf.svg> <frame_index> [--output PATH]

Writes the standalone SVG to stdout (or `--output PATH`). Frame index
is 1-based and matches the `FRAMENNNNN` numbering inside the FBF.

Exits non-zero with a descriptive message if the frame is missing or
the FBF is malformed. Pure stdlib (xml.etree) — no third-party deps.

Reference: design/tasks/TRDD-c2a3199d-...-text2path-docker-e2e.md.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _id_match(elem: ET.Element, target: str) -> bool:
    return elem.attrib.get("id") == target


def _find_by_id(root: ET.Element, target: str) -> ET.Element | None:
    """Depth-first search for an element with the given `id` attribute."""
    if _id_match(root, target):
        return root
    for child in root:
        found = _find_by_id(child, target)
        if found is not None:
            return found
    return None


def _strip_namespace(elem: ET.Element) -> None:
    """Strip Clark-notation namespace prefixes from tag names recursively.

    `ET.parse` decorates every tag with `{ns}local` when an `xmlns` is
    declared on the document. Re-serialising those tags inside a fresh
    SVG document we build by hand would emit `ns0:` prefixes everywhere
    (the same trap that bit svg-viewbox-repair). Easier to flatten tags
    to their local names and let the wrapper SVG's `xmlns` declaration
    handle resolution.
    """
    if isinstance(elem.tag, str) and elem.tag.startswith("{"):
        elem.tag = elem.tag.split("}", 1)[1]
    # Re-key attributes that are themselves namespaced. xlink:href is
    # the most common — preserve it as `xlink:href` for the renderer.
    for attr in list(elem.attrib):
        if attr.startswith("{"):
            ns, _, local = attr[1:].partition("}")
            if ns == XLINK_NS:
                new_key = f"xlink:{local}"
            elif ns == SVG_NS:
                new_key = local
            else:
                new_key = local  # Fallback: drop unknown namespace.
            elem.attrib[new_key] = elem.attrib.pop(attr)
    for child in elem:
        _strip_namespace(child)


def _serialize(elem: ET.Element) -> str:
    """Serialise an element tree to UTF-8 string without the XML decl."""
    return ET.tostring(elem, encoding="unicode", xml_declaration=False)


def extract_frame(fbf_path: Path, frame_index: int) -> str:
    if not fbf_path.is_file():
        raise FileNotFoundError(f"FBF file not found: {fbf_path}")

    # Register namespaces so ET round-trips without `ns0:` prefixes if
    # we ever serialise the tree directly. We work on detached copies
    # below, but registering keeps debugging output sane.
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)

    tree = ET.parse(fbf_path)
    root = tree.getroot()
    if root is None:
        raise ValueError(f"Empty XML root in {fbf_path}")

    view_box = root.attrib.get("viewBox") or root.attrib.get(f"{{{SVG_NS}}}viewBox")
    if not view_box:
        raise ValueError(f"FBF root has no viewBox attribute: {fbf_path}")

    frame_id = f"FRAME{frame_index:05d}"
    frame_elem = _find_by_id(root, frame_id)
    if frame_elem is None:
        raise KeyError(f"Frame '{frame_id}' not found in {fbf_path}")

    shared = _find_by_id(root, "SHARED_DEFINITIONS")

    # Detach frame + shared so we can safely serialize without leaking
    # the rest of the FBF document (metadata, other frames, etc.).
    frame_copy = ET.fromstring(_serialize(frame_elem))
    shared_copy = ET.fromstring(_serialize(shared)) if shared is not None else None
    _strip_namespace(frame_copy)
    if shared_copy is not None:
        _strip_namespace(shared_copy)

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="{view_box}">\n')
    # White background — matches both the original input frames and the
    # FBF's default canvas, so the visual diff isn't perturbed by a
    # missing background.
    # Pull width/height from the viewBox so the renderer doesn't have
    # to guess. viewBox format is "minX minY width height".
    vb_parts = view_box.split()
    if len(vb_parts) == 4:
        try:
            vb_w = float(vb_parts[2])
            vb_h = float(vb_parts[3])
            parts.append(f'  <rect width="{vb_w}" height="{vb_h}" fill="#ffffff"/>\n')
        except ValueError:
            # Non-numeric viewBox — fall back to a 100% rect that the
            # renderer will resolve once it picks a target size.
            parts.append('  <rect width="100%" height="100%" fill="#ffffff"/>\n')
    else:
        parts.append('  <rect width="100%" height="100%" fill="#ffffff"/>\n')

    if shared_copy is not None:
        parts.append("  <defs>\n")
        parts.append("    " + _serialize(shared_copy) + "\n")
        parts.append("  </defs>\n")

    parts.append("  " + _serialize(frame_copy) + "\n")
    parts.append("</svg>\n")
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    description = (__doc__ or "Extract a single frame from an FBF.SVG.").split("\n", 1)[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("fbf", type=Path, help="Path to the FBF .svg file")
    parser.add_argument("frame", type=int, help="1-based frame index")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path (default: stdout)",
    )
    args = parser.parse_args(argv)

    try:
        body = extract_frame(args.fbf, args.frame)
    except (FileNotFoundError, KeyError, ValueError, ET.ParseError) as e:
        print(f"extract_fbf_frame: {e}", file=sys.stderr)
        return 1

    if args.output is None:
        sys.stdout.write(body)
    else:
        args.output.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
