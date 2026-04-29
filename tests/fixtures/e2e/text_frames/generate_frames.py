#!/usr/bin/env python3
"""
Deterministic generator for the text→path Docker E2E fixtures.

Emits frame00001.svg .. frame00005.svg next to this file. Each frame is a
200×200 white-background SVG containing four `<text>` elements and one
`<textPath>` element placed along a curve, all using fonts that the test
container guarantees via apt (`fonts-dejavu` + `fonts-liberation`).

The fonts are referenced by exact family + weight (no generic
`sans-serif` fallback, no `font-style` shortcuts) so HarfBuzz inside
svg-text2path resolves the same face every time and the FBF output is
deterministic.

Per-frame element positions / rotations are derived from a fixed seed
(`random.seed(42)`) plus the frame index, so the sequence visibly
animates while remaining bit-identical across runs.

Run:
    uv run python tests/fixtures/e2e/text_frames/generate_frames.py

Reference: design/tasks/TRDD-c2a3199d-...-text2path-docker-e2e.md.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
FRAME_COUNT = 5
SIZE = 200  # square viewBox in user units
SEED = 42

# Fonts the test container guarantees via apt. Each entry is
# (family-name, weight, style, content-key).
FONT_FAMILIES = [
    ("DejaVu Sans", 400, "normal"),
    ("DejaVu Sans", 700, "normal"),
    ("DejaVu Serif", 400, "normal"),
    ("Liberation Mono", 400, "normal"),
]

# Short Latin-only content per text element. Keeping content stable across
# frames means only position/rotation/transform differ — easier to spot
# regressions in the byte-exact reference.
TEXTS = ["Hello", "World", "svg2fbf", "frame{n}"]

# Content rendered along the per-frame curved path.
TEXTPATH_CONTENT = "Animation along curve"


def _curve_path_for_frame(frame_idx: int) -> str:
    """Return the `d` attribute of the per-frame textPath curve.

    The curve is a smooth cubic Bezier whose control points shift with the
    frame index so the textPath visibly animates. End points stay near the
    left/right edges so the full text fits inside the viewBox at every
    frame.
    """
    # Phase shifts the control points along a sine wave; amplitude is
    # capped so the curve stays comfortably inside the 200×200 box.
    phase = (frame_idx - 1) / max(1, FRAME_COUNT - 1)
    cy1 = 70 + 30 * math.sin(phase * math.pi)
    cy2 = 130 - 30 * math.sin(phase * math.pi)
    return f"M 20,{120:.1f} C 70,{cy1:.1f} 130,{cy2:.1f} 180,{120:.1f}"


def _text_attrs_for_frame(rng: random.Random, frame_idx: int, slot: int) -> dict[str, float]:
    """Return per-element placement attributes for a given frame + slot.

    `slot` is 0..3 for the four `<text>` elements. Keeping a slot's seed
    stable across frames (slot index folded into the per-frame Random)
    means slot N moves on a continuous trajectory rather than jumping.
    """
    # Per-slot deterministic offset baseline.
    base_x = 30 + 35 * slot
    base_y = 40 + 22 * slot
    # Add per-frame motion: small wave with slot-dependent phase.
    phase = (frame_idx - 1) / max(1, FRAME_COUNT - 1)
    dx = 15 * math.sin(phase * math.pi * 2 + slot * 1.2)
    dy = 10 * math.cos(phase * math.pi * 2 + slot * 0.7)
    # Per-frame rotation: a small angle that varies smoothly.
    rotation = 12 * math.sin(phase * math.pi + slot * 0.4) - (5 if slot == 2 else 0)
    # Per-slot scale: slot 1 (DejaVu Sans Bold) is scaled up subtly so
    # the bold weight is visible.
    scale = 1.0
    if slot == 1:
        scale = 1.15 + 0.05 * math.cos(phase * math.pi)
    # Throwaway random call so future tweaks (e.g. jitter) can be added
    # without changing this slot's positions for now.
    _ = rng.random()
    return {
        "x": base_x + dx,
        "y": base_y + dy,
        "rotation": rotation,
        "scale": scale,
    }


def _build_text_element(family: str, weight: int, style: str, content: str, attrs: dict[str, float]) -> str:
    """Render a single `<text>` element as an SVG fragment string."""
    cx = attrs["x"]
    cy = attrs["y"]
    rotation = attrs["rotation"]
    scale = attrs["scale"]
    # Compose transform attribute. Keep the order
    # translate → rotate → scale so the rotation pivots at the glyph
    # baseline anchor rather than the canvas origin.
    transform = f"translate({cx:.2f},{cy:.2f}) rotate({rotation:.2f}) scale({scale:.3f})"
    # font-size is kept small enough that several elements fit inside
    # 200×200 without overlap blowing up the visual diff.
    return f'  <text font-family="{family}" font-weight="{weight}" font-style="{style}" font-size="14" fill="#000000" transform="{transform}">{content}</text>\n'


def _build_textpath_element(curve_id: str, family: str) -> str:
    """Render the per-frame `<textPath>` fragment using the shared curve."""
    return f'  <text font-family="{family}" font-weight="400" font-size="12" fill="#0033aa">\n    <textPath href="#{curve_id}" xlink:href="#{curve_id}">{TEXTPATH_CONTENT}</textPath>\n  </text>\n'


def _build_frame(frame_idx: int) -> str:
    rng = random.Random(SEED + frame_idx)
    curve_id = f"curve_{frame_idx:05d}"
    curve_d = _curve_path_for_frame(frame_idx)

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">\n')
    # Defs holding the textPath curve.
    parts.append("  <defs>\n")
    parts.append(f'    <path id="{curve_id}" d="{curve_d}" fill="none"/>\n')
    parts.append("  </defs>\n")
    # White background — matches the FBF compositor's default canvas.
    parts.append(f'  <rect width="{SIZE}" height="{SIZE}" fill="#ffffff"/>\n')

    # Four <text> elements, one per font face/weight slot.
    for slot, ((family, weight, style), content_template) in enumerate(zip(FONT_FAMILIES, TEXTS, strict=True)):
        attrs = _text_attrs_for_frame(rng, frame_idx, slot)
        content = content_template.format(n=frame_idx)
        parts.append(_build_text_element(family, weight, style, content, attrs))

    # One textPath element following the per-frame curve.
    parts.append(_build_textpath_element(curve_id, "DejaVu Sans"))

    parts.append("</svg>\n")
    return "".join(parts)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(1, FRAME_COUNT + 1):
        body = _build_frame(i)
        path = OUT_DIR / f"frame{i:05d}.svg"
        path.write_text(body, encoding="utf-8")
        print(f"wrote {path.relative_to(OUT_DIR.parents[3])}")


if __name__ == "__main__":
    main()
