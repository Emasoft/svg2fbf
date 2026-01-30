#!/usr/bin/env python
#
# svg2fbf - A cli tool to create a FBFSVG animation from svg frames
#
# Copyright © 2024 Emanuele Sabetta
#
# This tool uses some code from Scour, http://www.codedread.com/scour/
#
# Those parts should be credited to their rightful authors:
#
# 	Copyright © 2010 Jeff Schiller
# 	Copyright © 2010 Louis Simard
# 	Copyright © 2013-2014 Tavendo GmbH
#
# svg2fbf is licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#
# You may obtain a copy of the License at
#
# 	https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import cProfile
import decimal
import math
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.parse
import uuid
import warnings
import webbrowser
import xml.dom.minidom
import xml.parsers.expat
from collections import defaultdict, namedtuple
from datetime import datetime, timezone
from decimal import Context, Decimal, InvalidOperation, getcontext
from functools import partial
import argparse
from argparse import ArgumentParser, Namespace
from pathlib import Path
from pstats import SortKey
from xml.dom import Node

import numpy as np
import yaml

COPYRIGHT_INFO = """
svg2fbf - A cli tool to create a FBFSVG animation from svg frames

Copyright © 2022 Emanuele Sabetta

This tool uses some code from Scour, http://www.codedread.com/scour/

Those parts should be credited to their rightful authors:
    Copyright © 2010 Jeff Schiller
    Copyright © 2010 Louis Simard
    Copyright © 2013-2014 Tavendo GmbH

svg2fbf is licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""


# Version is dynamically loaded from pyproject.toml
def _get_version():
    """
    Read version from installed package metadata.

    Returns:
        Version string from installed package, or fallback "0.1.0" if unavailable
    """
    try:
        # Use importlib.metadata to get the installed package version
        from importlib.metadata import version

        return version("svg2fbf")
    except Exception:
        # Fallback for development/uninstalled scenarios
        try:
            pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
            if not pyproject_path.exists():
                return "0.1.0"

            # Use tomllib (Python 3.11+) or tomli (Python < 3.11)
            # for proper TOML parsing
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    # Fallback to simple parsing if no TOML library
                    with open(pyproject_path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("version") and "=" in line:
                                # Extract: version = "0.1.2a12"
                                version_raw = line.split("=", 1)[1].strip()
                                version_val = version_raw.strip('"').strip("'")
                                if version_val:
                                    return version_val
                    return "0.1.0"

            # Proper TOML parsing
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                version_str = data.get("project", {}).get("version", "0.1.0")
                return version_str

        except Exception:
            # Silent fallback - don't break execution if version reading fails
            return "0.1.0"


SEMVERSION = _get_version()

EPSILON = sys.float_info.epsilon
FLOAT_RE = re.compile(r"[-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[Ee][+-]?\d+)?")
COLOR_RE = re.compile("#?([0-9A-Fa-f]+)$")
COLOR_RGB_RE = re.compile(r"\s*(rgba?|hsl)\(([^\)]+)\)\s*")
TRANSFORM_RE = re.compile(r"\s*(translate|scale|rotate|skewX|skewY|matrix)\s*\(([^\)]+)\)\s*")
BBox = tuple[float, float, float, float]


XML_ENTS_NO_QUOTES = {"<": "&lt;", ">": "&gt;", "&": "&amp;"}
XML_ENTS_ESCAPE_APOS = XML_ENTS_NO_QUOTES.copy()
XML_ENTS_ESCAPE_APOS["'"] = "&apos;"
XML_ENTS_ESCAPE_QUOT = XML_ENTS_NO_QUOTES.copy()
XML_ENTS_ESCAPE_QUOT['"'] = "&quot;"

# Used to split values where "x y" or "x,y" or a mix of the two is allowed
RE_COMMA_WSP = re.compile(r"\s*[\s,]\s*")

NS = {
    "SVG": "http://www.w3.org/2000/svg",
    "XLINK": "http://www.w3.org/1999/xlink",
    "SODIPODI": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
    "SODIPODI2": "http://inkscape.sourceforge.net/DTD/sodipodi-0.dtd",
    "INKSCAPE": "http://www.inkscape.org/namespaces/inkscape",
    "ADOBE_ILLUSTRATOR": "http://ns.adobe.com/AdobeIllustrator/10.0/",
    "ADOBE_GRAPHS": "http://ns.adobe.com/Graphs/1.0/",
    "ADOBE_SVG_VIEWER": "http://ns.adobe.com/AdobeSVGViewerExtensions/3.0/",
    "ADOBE_VARIABLES": "http://ns.adobe.com/Variables/1.0/",
    "ADOBE_SFW": "http://ns.adobe.com/SaveForWeb/1.0/",
    "ADOBE_EXTENSIBILITY": "http://ns.adobe.com/Extensibility/1.0/",
    "ADOBE_FLOWS": "http://ns.adobe.com/Flows/1.0/",
    "ADOBE_IMAGE_REPLACEMENT": "http://ns.adobe.com/ImageReplacement/1.0/",
    "ADOBE_CUSTOM": "http://ns.adobe.com/GenericCustomNamespace/1.0/",
    "ADOBE_XPATH": "http://ns.adobe.com/XPath/1.0/",
    "SKETCH": "http://www.bohemiancoding.com/sketch/ns",
    "SERIF": "http://www.serif.com/",
    "VECTORNATOR": "http://vectornator.io",
}
UNWANTED_NS = [
    NS["SODIPODI"],
    NS["SODIPODI2"],
    NS["INKSCAPE"],
    NS["ADOBE_ILLUSTRATOR"],
    NS["ADOBE_GRAPHS"],
    NS["ADOBE_SVG_VIEWER"],
    NS["ADOBE_VARIABLES"],
    NS["ADOBE_SFW"],
    NS["ADOBE_EXTENSIBILITY"],
    NS["ADOBE_FLOWS"],
    NS["ADOBE_IMAGE_REPLACEMENT"],
    NS["ADOBE_CUSTOM"],
    NS["ADOBE_XPATH"],
    NS["SKETCH"],
    NS["SERIF"],
    NS["VECTORNATOR"],
]


colors = {
    "aliceblue": "rgb(240, 248, 255)",
    "antiquewhite": "rgb(250, 235, 215)",
    "aqua": "rgb( 0, 255, 255)",
    "aquamarine": "rgb(127, 255, 212)",
    "azure": "rgb(240, 255, 255)",
    "beige": "rgb(245, 245, 220)",
    "bisque": "rgb(255, 228, 196)",
    "black": "rgb( 0, 0, 0)",
    "blanchedalmond": "rgb(255, 235, 205)",
    "blue": "rgb( 0, 0, 255)",
    "blueviolet": "rgb(138, 43, 226)",
    "brown": "rgb(165, 42, 42)",
    "burlywood": "rgb(222, 184, 135)",
    "cadetblue": "rgb( 95, 158, 160)",
    "chartreuse": "rgb(127, 255, 0)",
    "chocolate": "rgb(210, 105, 30)",
    "coral": "rgb(255, 127, 80)",
    "cornflowerblue": "rgb(100, 149, 237)",
    "cornsilk": "rgb(255, 248, 220)",
    "crimson": "rgb(220, 20, 60)",
    "cyan": "rgb( 0, 255, 255)",
    "darkblue": "rgb( 0, 0, 139)",
    "darkcyan": "rgb( 0, 139, 139)",
    "darkgoldenrod": "rgb(184, 134, 11)",
    "darkgray": "rgb(169, 169, 169)",
    "darkgreen": "rgb( 0, 100, 0)",
    "darkgrey": "rgb(169, 169, 169)",
    "darkkhaki": "rgb(189, 183, 107)",
    "darkmagenta": "rgb(139, 0, 139)",
    "darkolivegreen": "rgb( 85, 107, 47)",
    "darkorange": "rgb(255, 140, 0)",
    "darkorchid": "rgb(153, 50, 204)",
    "darkred": "rgb(139, 0, 0)",
    "darksalmon": "rgb(233, 150, 122)",
    "darkseagreen": "rgb(143, 188, 143)",
    "darkslateblue": "rgb( 72, 61, 139)",
    "darkslategray": "rgb( 47, 79, 79)",
    "darkslategrey": "rgb( 47, 79, 79)",
    "darkturquoise": "rgb( 0, 206, 209)",
    "darkviolet": "rgb(148, 0, 211)",
    "deeppink": "rgb(255, 20, 147)",
    "deepskyblue": "rgb( 0, 191, 255)",
    "dimgray": "rgb(105, 105, 105)",
    "dimgrey": "rgb(105, 105, 105)",
    "dodgerblue": "rgb( 30, 144, 255)",
    "firebrick": "rgb(178, 34, 34)",
    "floralwhite": "rgb(255, 250, 240)",
    "forestgreen": "rgb( 34, 139, 34)",
    "fuchsia": "rgb(255, 0, 255)",
    "gainsboro": "rgb(220, 220, 220)",
    "ghostwhite": "rgb(248, 248, 255)",
    "gold": "rgb(255, 215, 0)",
    "goldenrod": "rgb(218, 165, 32)",
    "gray": "rgb(128, 128, 128)",
    "grey": "rgb(128, 128, 128)",
    "green": "rgb( 0, 128, 0)",
    "greenyellow": "rgb(173, 255, 47)",
    "honeydew": "rgb(240, 255, 240)",
    "hotpink": "rgb(255, 105, 180)",
    "indianred": "rgb(205, 92, 92)",
    "indigo": "rgb( 75, 0, 130)",
    "ivory": "rgb(255, 255, 240)",
    "khaki": "rgb(240, 230, 140)",
    "lavender": "rgb(230, 230, 250)",
    "lavenderblush": "rgb(255, 240, 245)",
    "lawngreen": "rgb(124, 252, 0)",
    "lemonchiffon": "rgb(255, 250, 205)",
    "lightblue": "rgb(173, 216, 230)",
    "lightcoral": "rgb(240, 128, 128)",
    "lightcyan": "rgb(224, 255, 255)",
    "lightgoldenrodyellow": "rgb(250, 250, 210)",
    "lightgray": "rgb(211, 211, 211)",
    "lightgreen": "rgb(144, 238, 144)",
    "lightgrey": "rgb(211, 211, 211)",
    "lightpink": "rgb(255, 182, 193)",
    "lightsalmon": "rgb(255, 160, 122)",
    "lightseagreen": "rgb( 32, 178, 170)",
    "lightskyblue": "rgb(135, 206, 250)",
    "lightslategray": "rgb(119, 136, 153)",
    "lightslategrey": "rgb(119, 136, 153)",
    "lightsteelblue": "rgb(176, 196, 222)",
    "lightyellow": "rgb(255, 255, 224)",
    "lime": "rgb( 0, 255, 0)",
    "limegreen": "rgb( 50, 205, 50)",
    "linen": "rgb(250, 240, 230)",
    "magenta": "rgb(255, 0, 255)",
    "maroon": "rgb(128, 0, 0)",
    "mediumaquamarine": "rgb(102, 205, 170)",
    "mediumblue": "rgb( 0, 0, 205)",
    "mediumorchid": "rgb(186, 85, 211)",
    "mediumpurple": "rgb(147, 112, 219)",
    "mediumseagreen": "rgb( 60, 179, 113)",
    "mediumslateblue": "rgb(123, 104, 238)",
    "mediumspringgreen": "rgb( 0, 250, 154)",
    "mediumturquoise": "rgb( 72, 209, 204)",
    "mediumvioletred": "rgb(199, 21, 133)",
    "midnightblue": "rgb( 25, 25, 112)",
    "mintcream": "rgb(245, 255, 250)",
    "mistyrose": "rgb(255, 228, 225)",
    "moccasin": "rgb(255, 228, 181)",
    "navajowhite": "rgb(255, 222, 173)",
    "navy": "rgb( 0, 0, 128)",
    "oldlace": "rgb(253, 245, 230)",
    "olive": "rgb(128, 128, 0)",
    "olivedrab": "rgb(107, 142, 35)",
    "orange": "rgb(255, 165, 0)",
    "orangered": "rgb(255, 69, 0)",
    "orchid": "rgb(218, 112, 214)",
    "palegoldenrod": "rgb(238, 232, 170)",
    "palegreen": "rgb(152, 251, 152)",
    "paleturquoise": "rgb(175, 238, 238)",
    "palevioletred": "rgb(219, 112, 147)",
    "papayawhip": "rgb(255, 239, 213)",
    "peachpuff": "rgb(255, 218, 185)",
    "peru": "rgb(205, 133, 63)",
    "pink": "rgb(255, 192, 203)",
    "plum": "rgb(221, 160, 221)",
    "powderblue": "rgb(176, 224, 230)",
    "purple": "rgb(128, 0, 128)",
    "red": "rgb(255, 0, 0)",
    "rosybrown": "rgb(188, 143, 143)",
    "royalblue": "rgb( 65, 105, 225)",
    "saddlebrown": "rgb(139, 69, 19)",
    "salmon": "rgb(250, 128, 114)",
    "sandybrown": "rgb(244, 164, 96)",
    "seagreen": "rgb( 46, 139, 87)",
    "seashell": "rgb(255, 245, 238)",
    "sienna": "rgb(160, 82, 45)",
    "silver": "rgb(192, 192, 192)",
    "skyblue": "rgb(135, 206, 235)",
    "slateblue": "rgb(106, 90, 205)",
    "slategray": "rgb(112, 128, 144)",
    "slategrey": "rgb(112, 128, 144)",
    "snow": "rgb(255, 250, 250)",
    "springgreen": "rgb( 0, 255, 127)",
    "steelblue": "rgb( 70, 130, 180)",
    "tan": "rgb(210, 180, 140)",
    "teal": "rgb( 0, 128, 128)",
    "thistle": "rgb(216, 191, 216)",
    "tomato": "rgb(255, 99, 71)",
    "turquoise": "rgb( 64, 224, 208)",
    "violet": "rgb(238, 130, 238)",
    "wheat": "rgb(245, 222, 179)",
    "white": "rgb(255, 255, 255)",
    "whitesmoke": "rgb(245, 245, 245)",
    "yellow": "rgb(255, 255, 0)",
    "yellowgreen": "rgb(154, 205, 50)",
}

# A list of all SVG presentation properties
#
# Sources for this list:
# 	https://www.w3.org/TR/SVG/propidx.html				(implemented)
# 	https://www.w3.org/TR/SVGTiny12/attributeTable.html	(implemented)
# 	https://www.w3.org/TR/SVG2/propidx.html				(not yet implemented)
#
SVG_ATTRIBUTES = [
    # SVG 1.1
    "alignment-baseline",
    "baseline-shift",
    "clip",
    "clip-path",
    "clip-rule",
    "color",
    "color-interpolation",
    "color-interpolation-filters",
    "color-profile",
    "color-rendering",
    "cursor",
    "direction",
    "display",
    "dominant-baseline",
    "enable-background",
    "fill",
    "fill-opacity",
    "fill-rule",
    "filter",
    "flood-color",
    "flood-opacity",
    "font",
    "font-family",
    "font-size",
    "font-size-adjust",
    "font-stretch",
    "font-style",
    "font-variant",
    "font-weight",
    "glyph-orientation-horizontal",
    "glyph-orientation-vertical",
    "image-rendering",
    "kerning",
    "letter-spacing",
    "lighting-color",
    "marker",
    "marker-end",
    "marker-mid",
    "marker-start",
    "mask",
    "opacity",
    "overflow",
    "pointer-events",
    "shape-rendering",
    "stop-color",
    "stop-opacity",
    "stroke",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-opacity",
    "stroke-width",
    "text-anchor",
    "text-decoration",
    "text-rendering",
    "unicode-bidi",
    "visibility",
    "word-spacing",
    "writing-mode",
    # SVG 1.2 Tiny
    "audio-level",
    "buffered-rendering",
    "display-align",
    "line-increment",
    "solid-color",
    "solid-opacity",
    "text-align",
    "vector-effect",
    "viewport-fill",
    "viewport-fill-opacity",
]

# a dict of CSS to SVG corresponding properties
CSS_TO_SVG_DICT = {
    "alignment-baseline": "alignment-baseline",
    "background-color": "fill",
    "baseline-shift": "baseline-shift",
    "clip": "clip",
    "clip-path": "clip-path",
    "clip-rule": "clip-rule",
    "color": "color",
    "color-interpolation-filters": "color-interpolation-filters",
    "content-visibility": "visibility",
    "cursor": "cursor",
    "direction": "direction",
    "display": "display",
    "dominant-baseline": "dominant-baseline",
    "fill": "fill",
    "fill-color": "fill",
    "fill-opacity": "fill-opacity",
    "fill-rule": "fill-rule",
    "filter": "filter",
    "flood-color": "flood-color",
    "flood-opacity": "flood-opacity",
    "font": "font",
    "font-family": "font-family",
    "font-size": "font-size",
    "font-size-adjust": "font-size-adjust",
    "font-stretch": "font-stretch",
    "font-style": "font-style",
    "font-variant": "font-variant",
    "font-weight": "font-weight",
    "glyph-orientation-vertical": "glyph-orientation-vertical",
    "height": "height",
    "image-rendering": "image-rendering",
    "letter-spacing": "letter-spacing",
    "lighting-color": "lighting-color",
    "marker": "marker",
    "marker-end": "marker-end",
    "marker-mid": "marker-mid",
    "marker-start": "marker-start",
    "mask": "mask",
    "opacity": "opacity",
    "overflow": "overflow",
    "pointer-events": "pointer-events",
    "stroke": "stroke",
    "stroke-color": "stroke",
    "stroke-dasharray": "stroke-dasharray",
    "stroke-dashcorner": "stroke-dashcorner",
    "stroke-dashoffset": "stroke-dashoffset",
    "stroke-linecap": "stroke-linecap",
    "stroke-linejoin": "stroke-linejoin",
    "stroke-miterlimit": "stroke-miterlimit",
    "stroke-opacity": "stroke-opacity",
    "stroke-width": "stroke-width",
    "text-align": "text-align",
    "text-anchor": "text-anchor",
    "text-decoration": "text-decoration",
    "transform": "transform",
    "unicode-bidi": "unicode-bidi",
    "visibility": "visibility",
    "width": "width",
    "word-spacing": "word-spacing",
    "writing-mode": "writing-mode",
}

SVG_ONLY_PROPERTIES = [
    "color-interpolation",
    "color-profile",
    "color-rendering",
    "enable-background",
    "glyph-orientation-horizontal",
    "kerning",
    "shape-rendering",
    "stop-color",
    "stop-opacity",
    "text-rendering",
    "audio-level",
    "buffered-rendering",
    "display-align",
    "line-increment",
    "solid-color",
    "solid-opacity",
    "vector-effect",
    "viewport-fill",
    "viewport-fill-opacity",
]

VALID_SVG_ELEMENTS = [
    # SVG 1.1
    "a",
    "altGlyph",
    "altGlyphDef",
    "altGlyphItem",
    "animate",
    "animateColor",
    "animateMotion",
    "animateTransform",
    "circle",
    "clipPath",
    "color-profile",
    "cursor",
    "defs",
    "desc",
    "ellipse",
    "feBlend",
    "feColorMatrix",
    "feComponentTransfer",
    "feComposite",
    "feConvolveMatrix",
    "feDiffuseLighting",
    "feDisplacementMap",
    "feDistantLight",
    "feFlood",
    "feFuncA",
    "feFuncB",
    "feFuncG",
    "feFuncR",
    "feGaussianBlur",
    "feImage",
    "feMerge",
    "feMergeNode",
    "feMorphology",
    "feOffset",
    "fePointLight",
    "feSpecularLighting",
    "feSpotLight",
    "feTile",
    "feTurbulence",
    "filter",
    "font",
    "font-face",
    "font-face-format",
    "font-face-name",
    "font-face-src",
    "font-face-uri",
    "foreignObject",
    "g",
    "glyph",
    "glyphRef",
    "hkern",
    "image",
    "line",
    "linearGradient",
    "marker",
    "mask",
    "metadata",
    "missing-glyph",
    "mpath",
    "path",
    "pattern",
    "polygon",
    "polyline",
    "radialGradient",
    "rect",
    "script",
    "set",
    "stop",
    "style",
    "svg",
    "switch",
    "symbol",
    "text",
    "textPath",
    "title",
    "tref",
    "tspan",
    "use",
    "view",
    "vkern",
    # SVG 2.0
    "hatch",
    "hatchpath",
    "mesh",
    "meshgradient",
    "meshpatch",
    "meshrow",
    "solidColor"
    # Tiny SVG 1.2
    "audio",
    "discard",
    "handler",
    "listener",
    "prefetch",
    "tbreak",
    "textArea",
    "video"
    # if xmlns:html="http://www.w3.org/1999/xhtml" is defined
    "html:audio",
    "html:canvas",
    "html:iframe",
    "html:source",
    "html:track",
    "html:video",
]


ELEMENTS_NOT_TO_HASH = [
    # SVG 1.1
    "altGlyphDef",
    "altGlyphItem",
    "animate",
    "animateColor",
    "animateMotion",
    "animateTransform",
    # "circle",
    "color-profile",
    "cursor",
    "desc",
    "defs",
    # "ellipse",
    "feBlend",
    "feColorMatrix",
    "feComponentTransfer",
    "feComposite",
    "feConvolveMatrix",
    "feDiffuseLighting",
    "feDisplacementMap",
    "feDistantLight",
    "feFlood",
    "feFuncA",
    "feFuncB",
    "feFuncG",
    "feFuncR",
    "feGaussianBlur",
    "feImage",
    "feMerge",
    "feMergeNode",
    "feMorphology",
    "feOffset",
    "fePointLight",
    "feSpecularLighting",
    "feSpotLight",
    "feTile",
    "feTurbulence",
    "font-face",
    "font-face-format",
    "font-face-name",
    "font-face-src",
    "font-face-uri",
    "foreignObject",
    "glyphRef",
    "hkern",
    # "line",
    "metadata",
    "mpath",
    # "rect",
    "script",
    "set",
    "stop",
    "style",
    "switch",
    "title",
    "tref",
    "tspan",
    "use",
    "view",
    "vkern",
    # SVG 2.0
    "hatch",
    "hatchpath",
    "mesh",
    "meshgradient",
    "meshpatch",
    "meshrow",
    "solidColor"
    # Tiny SVG 1.2
    "discard",
    "handler",
    "listener",
    "prefetch",
    "tbreak",
    # if xmlns:html="http://www.w3.org/1999/xhtml" is defined
    "html:canvas",
    "html:source",
    "html:track",
]

# Filter Primitives (SVG 1.1)
# The set of child elements that control
# the output of a filter element.
FILTER_PRIMITIVES = [
    "feSpotLight",
    "feBlend",
    "feColorMatrix",
    "feComponentTransfer",
    "feComposite",
    "feConvolveMatrix",
    "feDiffuseLighting",
    "feDisplacementMap",
    "feDropShadow",
    "feFlood",
    "feGaussianBlur",
    "feImage",
    "feMerge",
    "feMorphology",
    "feOffset",
    "feSpecularLighting",
    "feTile",
    "feTurbulence",
]


# Transfer Function Elements (SVG 1.1)
# The child elements of a feComponentTransfer element that specify
# the transfer functions for the four channels:
TRANSFER_FUNCTION_ELEMENTS = ["feFuncR", "feFuncG", "feFuncB", "feFuncA"]


# Container Element (SVG 1.1)
# An element which can have graphics elements and
# other container elements as child elements.
CONTAINER_ELEMENTS = [
    "a",
    "defs",
    "glyph",
    "g",
    "marker",
    "mask",
    "missing-glyph",
    "pattern",
    "svg",
    "switch",
    "symbol",
]

# Graphics Element (SVG 1.1)
# One of the element types that can cause graphics
# to be drawn onto the target canvas.
GRAPHICS_ELEMENTS = [
    "circle",
    "ellipse",
    "image",
    "line",
    "path",
    "polygon",
    "polyline",
    "rect",
    "text",
    "use",
]


# Graphics Referencing Element (SVG 1.1)
# A graphics element which uses a reference to
# a different document or element as the source
# of its graphical content.
GRAPHICS_REFERENCING_ELEMENTS = ["image", "use"]


# Animation Element (SVG 1.1)
# An animation element is an element that can be
# used to animate the attribute or property value
# of another element.
ANIMATION_ELEMENTS = [
    "animateColor",
    "animateMotion",
    "animateTransform",
    "animate",
    "set",
]


MAIN_ATTRIBUTES_DICT = {
    "path": "d",
    "polyline": "points",
    "polygon": "points",
    "image": "href",
    "text": "child-nodes",
}

# Presentation attributes that must be preserved on text elements in shared masters
# WHY: When text is converted to <use> elements, presentation attributes on <use>
# do NOT affect the referenced <text>. These attributes must stay on the <text> element.
TEXT_PRESENTATION_ATTRIBUTES = [
    # Font properties
    "font-family",
    "font-size",
    "font-style",
    "font-variant",
    "font-weight",
    "font-stretch",
    "font-size-adjust",
    "kerning",
    "letter-spacing",
    "word-spacing",
    "text-decoration",
    "text-anchor",
    "direction",
    "unicode-bidi",
    "writing-mode",
    "glyph-orientation-horizontal",
    "glyph-orientation-vertical",
    # Fill and stroke
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-width",
    "stroke-opacity",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-dashoffset",
    # Other presentation
    "opacity",
    "visibility",
    "display",
    "color",
    "color-interpolation",
    "color-rendering",
    "paint-order",
    "clip-rule",
    "mask",
    "filter",
    # Text-specific
    "baseline-shift",
    "dominant-baseline",
    "alignment-baseline",
    "text-rendering",
    "shape-rendering",
]


RESERVED_OUTPUT_IDS = [
    "ANIMATED_GROUP",
    "ANIMATION_STAGE",
    "STAGE_BACKGROUND",
    "STAGE_FOREGROUND",
    "ANIMATION_BACKDROP",
    "OVERLAY_LAYER",
    "PROSKENION",
    "SHARED_DEFINITIONS",
]


# Basic Shape (SVG 1.1)
# Standard geometric shapes which are predefined in SVG
# as a convenience for common graphical operations.
BASIC_SHAPES = ["circle", "ellipse", "line", "polygon", "polyline", "rect"]


# Elements allowed as children of a clipPath (SVG 1.1)
# A clipping path is defined with a 'clipPath' element.
# A clipping path is used/referenced using the 'clip-path' property.
# A 'clipPath' element can contain 'path' elements, 'text' elements,
# basic shapes (such as 'circle') or a 'use' element.
# If a 'use' element is a child of a 'clipPath' element,
# it must directly reference 'path', 'text' or basic shape elements.
# Indirect references are an error (i.e. 'use' referencing another 'use').
ALLOWED_CHILDREN_OF_CLIPPATH = [
    "path",
    "text",
    "use",
    "circle",
    "ellipse",
    "line",
    "polygon",
    "polyline",
    "rect",
]


# Conditional Processing Attribute (SVG 1.1)
# A conditional processing attribute is one that controls
# whether or not the element on which it appears is
# processed. Most elements, but not all, may have conditional
# processing attributes specified on them.
CONDITIONAL_PROCESSING_ATTRIBUTES = [
    "requiredExtensions",
    "requiredFeatures",
    "systemLanguage",
]
ELEMENTS_AFFECTED_BY_CONDITIONAL_ATTRIBUTES = [
    "a",
    "altGlyph",
    "foreignObject",
    "textPath",
    "tref",
    "tspan",
    "animate",
    "animateColor",
    "animateMotion",
    "animateTransform",
    "set",
]


# Descriptive Element (SVG 1.1)
# An element which provides supplementary descriptive
# information about its parent.
DESCRIPTIVE_ELEMENTS = ["desc", "metadata", "title"]


# Elements Allowed to be Children of a mask element (SVG 1.1)
# In SVG, you can specify that any other graphics object
# or 'g' element can be used as an alpha mask for compositing
# the current object into the background.
# A mask is defined with a 'mask' element.
# A mask is used/referenced using the 'mask' property.
ALLOWED_CHILDREN_OF_MASK = [
    "circle",
    "ellipse",
    "image",
    "line",
    "path",
    "polygon",
    "polyline",
    "rect",
    "text",
    "use",
    "g",
]


TYPE_CHOICES = [
    "once",
    "once_reversed",
    "loop",
    "loop_reversed",
    "pingpong_once",
    "pingpong_loop",
    "pingpong_once_reversed",
    "pingpong_loop_reversed",
]


# element to discard when copying from svg frames to output svg
ELEMENTS_TO_DISCARD = [
    "defs",
    "desc",
    "style",
    "script",
    "title",
    "metadata",
    "font",
    "set",
    "svg",
    "audio",
    "handler",
    "input",
    "switch",
    "discard",
    "foreignObject",
    "view",
    "video",
    "animate",
    "animateMotion",
    "animateColor",
    "animateTransform",
]


ELEMENTS_NEVER_RENDERED_DIRECTLY = [
    "symbol",
    "linearGradient",
    "radialGradient",
    "filter",
    "marker",
    "pattern",
    "mask",
    "stop",
    "meshpatch",
    "meshrow",
    "clipPath",
    "hatchpath",
]


# elements that can be deleted
# if duplicates exists, with just the need
# to retarget the nodes referencing to it
# to its master. No use required, because
# they are never rendered directly.
RETARGETABLE_ELEMENTS = [
    "symbol",
    "linearGradient",
    "radialGradient",
    "filter",
    "marker",
    "pattern",
    "mask",
    "clipPath",
    "hatchpath",
    "font",
]

# elements that can be replaced by an use
# element if duplicates exists, with also
# the need to retarget the nodes referencing
# to it to its master. Unless they are in
# the defs section, they are always rendered
# directly. NOTE: rect, circle, line and ellipse
# are reusable but the gain in saved characters
# is negligible, so reuse is not advisable.
REUSABLE_SVG_ELEMENTS = [
    # "circle",
    # "ellipse",
    "image",
    # "line",
    "hatch",
    "mesh",
    "meshgradient",
    "path",
    "polygon",
    "polyline",
    # "rect",
    # "text",  # WHY: Text elements cannot be converted to <use> references
    #          # in FBF format because embedded SVG fonts don't work when
    #          # text is referenced via <use>. Since FBF requires all
    #          # resources to be embedded (no external loading), text
    #          # elements must remain inline to ensure fonts render correctly.
]

# those should be moved to output svg as they are
SVG_ELEMENTS_TO_ALWAYS_MOVE = ["rect", "line", "circle", "ellipse", "g"]


NON_REUSABLE_ELEMENTS = [
    "linearGradient",
    "radialGradient",
    "filter",
    "marker",
    "pattern",
    "mask",
    "tspan",
    "clipPath",
    "hatchpath",
    "use",
    "foreignObject",
    "switch",
    "defs",
    "desc",
    "style",
    "script",
    "title",
    "metadata",
    "font",
    "set",
    "svg",
    "rect",
    "circle",
    "line",
    "ellipse",
    # WHY: Text elements cannot be converted to <use> in FBF
    # (embedded fonts don't work)
    "text",
    "meshpatch",
    "meshrow",
    "solidColor",
    "mpath",
    "stop",
    "g",
]

NODE_TYPES_TO_IGNORE = [
    # xml.dom.minidom.Node.ELEMENT_NODE,
    xml.dom.minidom.Node.ATTRIBUTE_NODE,
    xml.dom.minidom.Node.TEXT_NODE,
    xml.dom.minidom.Node.CDATA_SECTION_NODE,
    xml.dom.minidom.Node.ENTITY_REFERENCE_NODE,
    xml.dom.minidom.Node.ENTITY_NODE,
    xml.dom.minidom.Node.PROCESSING_INSTRUCTION_NODE,
    xml.dom.minidom.Node.COMMENT_NODE,
    # xml.dom.minidom.Node.DOCUMENT_NODE,
    xml.dom.minidom.Node.DOCUMENT_TYPE_NODE,
    xml.dom.minidom.Node.DOCUMENT_FRAGMENT_NODE,
    xml.dom.minidom.Node.NOTATION_NODE,
]

###################
# Helper Functions
###################


# Sentinel.
class _EOF:
    def __repr__(self):
        return "EOF"


EOF = _EOF()

lexicon_path = [
    ("float", r"[-+]?(?:(?:[0-9]*\.[0-9]+)|(?:[0-9]+\.?))(?:[Ee][-+]?[0-9]+)?"),
    ("int", r"[-+]?[0-9]+"),
    ("command", r"[AaCcHhLlMmQqSsTtVvZz]"),
]


lexicon_transform = [
    ("float", r"[-+]?(?:(?:[0-9]*\.[0-9]+)|(?:[0-9]+\.?))(?:[Ee][-+]?[0-9]+)?"),
    ("int", r"[-+]?[0-9]+"),
    ("command", r"(?:matrix|translate|scale|rotate|skew[XY])"),
    ("coordstart", r"\("),
    ("coordend", r"\)"),
]


class Lexer:
    """Break SVG path data into tokens.

    The SVG spec requires that tokens are greedy. This lexer relies on Python's
    regexes defaulting to greediness.

    This style of implementation was inspired by this article:

            http://www.gooli.org/blog/a-simple-lexer-in-python/
    """

    def __init__(self, lexicon):
        self.lexicon = lexicon
        parts = []
        for name, regex in lexicon:
            parts.append(f"(?P<{name}>{regex})")
        self.regex_string = "|".join(parts)
        self.regex = re.compile(self.regex_string)

    def lex(self, text):
        """Yield (token_type, str_data) tokens.

        The last token will be (EOF, None) where EOF is the singleton object
        defined in this module.
        """
        for match in self.regex.finditer(text):
            for name, _ in self.lexicon:
                m = match.group(name)
                if m is not None:
                    yield (name, m)
                    break
        yield (EOF, None)


svg_lexer_path = Lexer(lexicon_path)
svg_lexer_transform = Lexer(lexicon_transform)


class SVGPathParser:
    """Parse SVG <path> data into a list of commands.

    Each distinct command will take the form of a tuple (command, data). The
    `command` is just the character string that starts the command group in the
    <path> data, so 'M' for absolute moveto, 'm' for relative moveto, 'Z' for
    closepath, etc. The kind of data it carries with it depends on the command.
    For 'Z' (closepath), it's just None. The others are lists of individual
    argument groups. Multiple elements in these lists usually mean to repeat the
    command. The notable exception is 'M' (moveto) where only the first element
    is truly a moveto. The remainder are implicit linetos.

    See the SVG documentation for the interpretation of the individual elements
    for each command.

    The main method is `parse(text)`. It can only consume actual strings, not
    filelike objects or iterators.
    """

    def __init__(self, lexer):
        self.lexer = lexer

        self.command_dispatch = {
            "Z": self.rule_closepath,
            "z": self.rule_closepath,
            "M": self.rule_moveto_or_lineto,
            "m": self.rule_moveto_or_lineto,
            "L": self.rule_moveto_or_lineto,
            "l": self.rule_moveto_or_lineto,
            "H": self.rule_orthogonal_lineto,
            "h": self.rule_orthogonal_lineto,
            "V": self.rule_orthogonal_lineto,
            "v": self.rule_orthogonal_lineto,
            "C": self.rule_curveto3,
            "c": self.rule_curveto3,
            "S": self.rule_curveto2,
            "s": self.rule_curveto2,
            "Q": self.rule_curveto2,
            "q": self.rule_curveto2,
            "T": self.rule_curveto1,
            "t": self.rule_curveto1,
            "A": self.rule_elliptical_arc,
            "a": self.rule_elliptical_arc,
        }

        # 		self.number_tokens = set(['int', 'float'])
        self.number_tokens = ["int", "float"]

    def parse(self, text):
        """Parse a string of SVG <path> data."""
        gen = self.lexer.lex(text)
        next_val_fn = partial(next, gen)
        token = next_val_fn()

        commands = []
        while token[0] is not EOF:
            if token[0] != "command":
                raise SyntaxError(f"expecting a command; got {token!r}")
            rule = self.command_dispatch[token[1]]
            command_group, token = rule(next_val_fn, token)
            commands.append(command_group)
        return commands

    def rule_closepath(self, next_val_fn, token):
        command = token[1]
        token = next_val_fn()
        return (command, []), token

    def rule_moveto_or_lineto(self, next_val_fn, token):
        command = token[1]
        token = next_val_fn()
        coordinates = []
        while token[0] in self.number_tokens:
            pair, token = self.rule_coordinate_pair(next_val_fn, token)
            coordinates.extend(pair)
        return (command, coordinates), token

    def rule_orthogonal_lineto(self, next_val_fn, token):
        command = token[1]
        token = next_val_fn()
        coordinates = []
        while token[0] in self.number_tokens:
            coord, token = self.rule_coordinate(next_val_fn, token)
            coordinates.append(coord)
        return (command, coordinates), token

    def rule_curveto3(self, next_val_fn, token):
        command = token[1]
        token = next_val_fn()
        coordinates = []
        while token[0] in self.number_tokens:
            pair1, token = self.rule_coordinate_pair(next_val_fn, token)
            pair2, token = self.rule_coordinate_pair(next_val_fn, token)
            pair3, token = self.rule_coordinate_pair(next_val_fn, token)
            coordinates.extend(pair1)
            coordinates.extend(pair2)
            coordinates.extend(pair3)
        return (command, coordinates), token

    def rule_curveto2(self, next_val_fn, token):
        command = token[1]
        token = next_val_fn()
        coordinates = []
        while token[0] in self.number_tokens:
            pair1, token = self.rule_coordinate_pair(next_val_fn, token)
            pair2, token = self.rule_coordinate_pair(next_val_fn, token)
            coordinates.extend(pair1)
            coordinates.extend(pair2)
        return (command, coordinates), token

    def rule_curveto1(self, next_val_fn, token):
        command = token[1]
        token = next_val_fn()
        coordinates = []
        while token[0] in self.number_tokens:
            pair1, token = self.rule_coordinate_pair(next_val_fn, token)
            coordinates.extend(pair1)
        return (command, coordinates), token

    def rule_elliptical_arc(self, next_val_fn, token):
        command = token[1]
        token = next_val_fn()
        arguments = []
        while token[0] in self.number_tokens:
            rx = Decimal(token[1]) * 1
            if rx < Decimal("0.0"):
                raise SyntaxError(f"expecting a nonnegative number; got {token!r}")

            token = next_val_fn()
            if token[0] not in self.number_tokens:
                raise SyntaxError(f"expecting a number; got {token!r}")
            ry = Decimal(token[1]) * 1
            if ry < Decimal("0.0"):
                raise SyntaxError(f"expecting a nonnegative number; got {token!r}")

            token = next_val_fn()
            if token[0] not in self.number_tokens:
                raise SyntaxError(f"expecting a number; got {token!r}")
            axis_rotation = Decimal(token[1]) * 1

            token = next_val_fn()
            if token[1][0] not in ("0", "1"):
                raise SyntaxError(f"expecting a boolean flag; got {token!r}")
            large_arc_flag = Decimal(token[1][0]) * 1

            if len(token[1]) > 1:
                token = list(token)
                token[1] = token[1][1:]
            else:
                token = next_val_fn()
            if token[1][0] not in ("0", "1"):
                raise SyntaxError(f"expecting a boolean flag; got {token!r}")
            sweep_flag = Decimal(token[1][0]) * 1

            if len(token[1]) > 1:
                token = list(token)
                token[1] = token[1][1:]
            else:
                token = next_val_fn()
            if token[0] not in self.number_tokens:
                raise SyntaxError(f"expecting a number; got {token!r}")
            x = Decimal(token[1]) * 1

            token = next_val_fn()
            if token[0] not in self.number_tokens:
                raise SyntaxError(f"expecting a number; got {token!r}")
            y = Decimal(token[1]) * 1

            token = next_val_fn()
            arguments.extend([rx, ry, axis_rotation, large_arc_flag, sweep_flag, x, y])

        return (command, arguments), token

    def rule_coordinate(self, next_val_fn, token):
        if token[0] not in self.number_tokens:
            raise SyntaxError(f"expecting a number; got {token!r}")
        x = getcontext().create_decimal(token[1])
        token = next_val_fn()
        return x, token

    def rule_coordinate_pair(self, next_val_fn, token):
        # Inline these since this rule is so common.
        if token[0] not in self.number_tokens:
            raise SyntaxError(f"expecting a number; got {token!r}")
        x = getcontext().create_decimal(token[1])
        token = next_val_fn()
        if token[0] not in self.number_tokens:
            raise SyntaxError(f"expecting a number; got {token!r}")
        y = getcontext().create_decimal(token[1])
        token = next_val_fn()
        return [x, y], token


# ------------------------------------------------------------------------------
# SVGTransformationParser Class
# ------------------------------------------------------------------------------
class SVGTransformationParser:
    """Parse SVG transform="" data into a list of commands.

    Each distinct command will take the form of a tuple (type, data). The
    `type` is the character string that defines the type of transformation in the
    transform data, so either of "translate", "rotate", "scale", "matrix",
    "skewX" and "skewY". Data is always a list of numbers contained within the
    transformation's parentheses.

    See the SVG documentation for the interpretation of the individual elements
    for each transformation.

    The main method is `parse(text)`. It can only consume actual strings, not
    filelike objects or iterators.
    """

    def __init__(self, lexer):
        self.lexer = lexer
        self.command_dispatch = {
            "translate": self.rule_1or2numbers,
            "scale": self.rule_1or2numbers,
            "skewX": self.rule_1number,
            "skewY": self.rule_1number,
            "rotate": self.rule_1or3numbers,
            "matrix": self.rule_6numbers,
        }
        self.number_tokens = ["int", "float"]

    def parse(self, text: str) -> tuple:
        """Parse SVG transform text into command and arguments tuple.

        Args:
            text: The transform string to parse

        Returns:
            Tuple of (command, arguments)

        Raises:
            SyntaxError: If the transform syntax is invalid
        """
        try:
            gen = self.lexer.lex(text)
            next_val_fn = partial(next, gen)
            token = next_val_fn()

            if not isinstance(token, (list, tuple)) or len(token) < 2:
                raise SyntaxError("invalid token format")

            token_type = str(token[0])
            token_value = str(token[1])

            if token_type != "command":
                raise SyntaxError(f"expecting command, got {token_type}")

            if token_value not in self.command_dispatch:
                raise SyntaxError(f"invalid command: {token_value}")

            rule = self.command_dispatch[token_value]
            return rule(next_val_fn, token)

        except (StopIteration, IndexError, TypeError, AttributeError) as e:
            raise SyntaxError(f"invalid transform syntax: {str(e)}") from e

    def rule_1or2numbers(self, next_val_fn, token):
        numbers = []
        # 1st number is mandatory
        token = next_val_fn()
        number, token = self.rule_number(next_val_fn, token)
        numbers.append(number)
        # 2nd number is optional
        number, token = self.rule_optional_number(next_val_fn, token)
        if number is not None:
            numbers.append(number)

        return numbers, token

    def rule_1number(self, next_val_fn, token):
        # this number is mandatory
        token = next_val_fn()
        number, token = self.rule_number(next_val_fn, token)
        numbers = [number]
        return numbers, token

    def rule_1or3numbers(self, next_val_fn, token):
        numbers = []
        # 1st number is mandatory
        token = next_val_fn()
        number, token = self.rule_number(next_val_fn, token)
        numbers.append(number)
        # 2nd number is optional
        number, token = self.rule_optional_number(next_val_fn, token)
        if number is not None:
            # but, if the 2nd number is provided, the 3rd is mandatory.
            # we can't have just 2.
            numbers.append(number)

            number, token = self.rule_number(next_val_fn, token)
            numbers.append(number)

        return numbers, token

    def rule_6numbers(self, next_val_fn, token):
        numbers = []
        token = next_val_fn()
        # all numbers are mandatory
        for _i in range(6):
            number, token = self.rule_number(next_val_fn, token)
            numbers.append(number)
        return numbers, token

    def rule_number(self, next_val_fn, token):
        if token[0] not in self.number_tokens:
            raise SyntaxError(f"expecting a number; got {token!r}")
        x = Decimal(token[1]) * 1
        token = next_val_fn()
        return x, token

    def rule_optional_number(self, next_val_fn, token):
        if token[0] not in self.number_tokens:
            return None, token
        else:
            x = Decimal(token[1]) * 1
            token = next_val_fn()
            return x, token


svg_path_parser = SVGPathParser(svg_lexer_path)
svg_transform_parser = SVGTransformationParser(svg_lexer_transform)


# ------------------------------------------------------------------------------
# ConcatenatedSVGTransformations Class
# ------------------------------------------------------------------------------
class ConcatenatedSVGTransformations:
    __slots__ = ["m", "_m_inv"]

    def __init__(self, matrix=None, matrix_inv=None):
        if matrix is None:
            self.m = np.identity(3)
            self._m_inv = self.m
        else:
            self.m = matrix
            self._m_inv = matrix_inv

    def __matmul__(self, other):
        # Replace @ with np.dot()
        return ConcatenatedSVGTransformations(np.dot(self.m, other.m))

    @property
    def invert(self):
        if self._m_inv is None:
            self._m_inv = np.linalg.inv(self.m)
        return ConcatenatedSVGTransformations(self._m_inv, self.m)

    def __call__(self, points):
        if len(points) == 0:
            return points
        return np.dot(points, self.m[:2, :2].T) + self.m[:2, 2]

    def apply(self):
        M = self.m[:2, :2].T
        B = self.m[:2, 2]
        return lambda points: np.dot(points, M) + B

    def matrix(self, m00, m01, m02, m10, m11, m12):
        transform_matrix = np.array([[m00, m01, m02], [m10, m11, m12], [0, 0, 1]])
        return ConcatenatedSVGTransformations(np.dot(self.m, transform_matrix))

    def translate(self, tx: float, ty: float):
        translation_matrix = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]])
        return ConcatenatedSVGTransformations(np.dot(self.m, translation_matrix))

    def scale(self, sx, sy=None):
        sy = sx if sy is None else sy
        scale_matrix = np.array([[sx, 0, 0], [0, sy, 0], [0, 0, 1]])
        return ConcatenatedSVGTransformations(np.dot(self.m, scale_matrix))

    def rotate(self, angle):
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        rotation_matrix = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]])
        return ConcatenatedSVGTransformations(np.dot(self.m, rotation_matrix))

    def skew(self, ax, ay):
        skew_matrix = np.array([[1, math.tan(ax), 0], [math.tan(ay), 1, 0], [0, 0, 1]])
        return ConcatenatedSVGTransformations(np.dot(self.m, skew_matrix))

    def __repr__(self):
        return str(np.around(self.m, 4).tolist()[:2])

    def no_translate(self):
        m = self.m.copy()
        m[0, 2] = 0
        m[1, 2] = 0
        return ConcatenatedSVGTransformations(m)


# ---------------------------
#  Parse Transform attribute
# ---------------------------


def string2svgtransformations(input):
    """Parse SVG transform"""
    if input is None:
        return None

    def args_err(name, args_len, needs):
        raise ValueError(f"`{name}` transform requires {args_len} arguments {needs} where given")

    tr = ConcatenatedSVGTransformations()
    input = input.strip().replace(",", " ")
    while input:
        match = TRANSFORM_RE.match(input)
        if match is None:
            raise ValueError(f"failed to parse transform: {input}")
        input = input[len(match.group(0)) :]

        op, args = match.groups()
        args = list(filter(None, args.split(" ")))
        args_len = len(args)
        if op == "matrix":
            args = list(map(float, args))
            if args_len != 6:
                args_err("matrix", args_len, 6)
            a, b, c, d, e, f = args
            tr = tr.matrix(a, c, e, b, d, f)
        elif op == "translate":
            args = list(map(float, args))
            if args_len == 2:
                tx, ty = args
            elif args_len == 1:
                tx, ty = args[0], 0
            else:
                args_err("translate", args_len, "{1,2}")
            tr = tr.translate(tx, ty)
        elif op == "scale":
            args = list(map(float, args))
            if args_len == 2:
                sx, sy = args
            elif args_len == 1:
                sx, sy = args[0], args[0]
            else:
                args_err("scale", args_len, "{1,2}")
            tr = tr.scale(sx, sy)
        elif op == "rotate":
            if args_len == 1:
                tr = tr.rotate(svg_angle(args[0]))
            elif args_len == 3:
                a = svg_angle(args[0])
                x, y = list(map(float, args[1:]))
                tr = tr.translate(x, y).rotate(a).translate(-x, -y)
            else:
                args_err("rotate", args_len, "{1,3}")
        elif op == "skewX":
            if args_len != 1:
                args_err("skewX", args_len, 1)
            tr = tr.skew(svg_angle(args[0]), 0)
        elif op == "skewY":
            if args_len != 1:
                args_err("skewY", args_len, 1)
            tr = tr.skew(0, svg_angle(args[0]))
        else:
            raise ValueError(f"invalid transform operation: {op}")

    return tr


def svg_float(text):
    if isinstance(text, float):
        return text
    if text is None:
        return None
    text = text.strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    elif text.endswith("px") or text.endswith("pt"):
        return float(text[:-2])
    else:
        return float(text)


def svg_floats(text, min=None, max=None):
    if text is None:
        return None
    floats = [float(v) for v in text.replace(",", " ").split(" ") if v]
    if min is not None and len(floats) < min:
        raise ValueError(f"expected at least {min} arguments")
    if max is not None and len(floats) > max:
        raise ValueError(f"expected at most {max} arguments")
    return floats


def svg_angle(angle):
    """Convert SVG angle to radians"""
    angle = angle.strip()
    if angle.endswith("deg"):
        return float(angle[:-3]) * math.pi / 180
    elif angle.endswith("rad"):
        return float(angle[:-3])
    return float(angle) * math.pi / 180


# Default font size in pixels
FONT_SIZE = 16


def svg_size(size, default=None, dpi=96):
    if size is None:
        return default
    if isinstance(size, (int, float)):
        return float(size)
    size = size.strip().lower()
    match = FLOAT_RE.match(size)
    if match is None:
        warnings.warn(f"invalid size: {size}", stacklevel=2)
        return default
    value = float(match.group(0))
    units = size[match.end() :].strip()
    if not units or units == "px":
        return value
    elif units == "in":
        return value * dpi
    elif units == "cm":
        return value * dpi / 2.54
    elif units == "mm":
        return value * dpi / 25.4
    elif units == "pt":
        return value * dpi / 72.0
    elif units == "pc":
        return value * dpi / 6.0
    elif units == "em":
        return value * FONT_SIZE
    elif units == "ex":
        return value * FONT_SIZE / 2.0
    elif units == "%":
        warnings.warn("size in % is not supported", stacklevel=2)
        return value


def svg_url(url, ids):
    """Resolve SVG url"""
    match = re.match(r"url\(\#([^)]+)\)", url.strip())
    if match is None:
        return None
    target = ids.get(match.group(1))
    if target is None:
        warnings.warn(f"failed to resolve url: {url}", stacklevel=2)
        return None
    return target


def is_same_sign(a, b):
    return (a <= 0 and b <= 0) or (a >= 0 and b >= 0)


def is_same_direction(x1: float, y1: float, x2: float, y2: float) -> bool:
    """Check if two vectors point in the same direction.

    Args:
        x1: X component of first vector
        y1: Y component of first vector
        x2: X component of second vector
        y2: Y component of second vector

    Returns:
        True if vectors point in same direction, False otherwise
    """
    if is_same_sign(x1, x2) and is_same_sign(y1, y2):
        try:
            if x1 == 0 or x2 == 0:
                return y1 == y2 == 0
            diff = y1 / x1 - y2 / x2
            return abs(diff) < sys.float_info.epsilon
        except ZeroDivisionError:
            return False
    return False


scinumber = re.compile(r"[-+]?(\d*\.?)?\d+[eE][-+]?\d+")
number = re.compile(r"[-+]?(\d*\.?)?\d+")
sciExponent = re.compile(r"[eE]([-+]?\d+)")
unit = re.compile("(em|ex|px|pt|pc|cm|mm|in|%){1,1}$")


class Unit:
    # Integer constants for units.
    INVALID = -1
    NONE = 0
    PCT = 1
    PX = 2
    PT = 3
    PC = 4
    EM = 5
    EX = 6
    CM = 7
    MM = 8
    IN = 9

    # String to Unit. Basically, converts unit strings to their integer constants.
    s2u = {
        "": NONE,
        "%": PCT,
        "px": PX,
        "pt": PT,
        "pc": PC,
        "em": EM,
        "ex": EX,
        "cm": CM,
        "mm": MM,
        "in": IN,
    }

    # Unit to String. Basically, converts unit integer constants to their
    # corresponding strings.
    u2s = {
        NONE: "",
        PCT: "%",
        PX: "px",
        PT: "pt",
        PC: "pc",
        EM: "em",
        EX: "ex",
        CM: "cm",
        MM: "mm",
        IN: "in",
    }

    #  @staticmethod
    def get(self):
        if self is None:
            return Unit.NONE
        try:
            return Unit.s2u[self]
        except KeyError:
            return Unit.INVALID

    #  @staticmethod
    def str(self):
        try:
            return Unit.u2s[self]
        except KeyError:
            return "INVALID"

    get = staticmethod(get)
    str = staticmethod(str)


class SVGLength:
    def __init__(self, str):
        try:  # simple unitless and no scientific notation
            self.value = float(str)
            if int(self.value) == self.value:
                self.value = int(self.value)
            self.units = Unit.NONE
        except ValueError:
            # we know that the length string has an exponent, a unit, both or is invalid

            # parse out number, exponent and unit
            self.value = 0
            unitBegin = 0
            scinum = scinumber.match(str)
            if scinum is not None:
                # this will always match, no need to check it
                numMatch = number.match(str)
                expMatch = sciExponent.search(str, numMatch.start(0))
                self.value = float(numMatch.group(0)) * 10 ** float(expMatch.group(1))
                unitBegin = expMatch.end(1)
            else:
                # unit or invalid
                numMatch = number.match(str)
                if numMatch is not None:
                    self.value = float(numMatch.group(0))
                    unitBegin = numMatch.end(0)

            if int(self.value) == self.value:
                self.value = int(self.value)

            if unitBegin != 0:
                unitMatch = unit.search(str, unitBegin)
                if unitMatch is not None:
                    self.units = Unit.get(unitMatch.group(0))

            # invalid
            else:
                # TODO: this needs to set the default for the given attribute (how?)
                self.value = 0
                self.units = Unit.INVALID


def print_version_banner():
    """
    Display version banner with unicode borders.

    Handles terminal encoding errors gracefully by falling back to ASCII.
    """
    try:
        # Calculate padding to maintain alignment (62 chars total width)
        # Account for: "║  📦 Version " (13 visible chars + emoji) + version + " ║"
        version_line = f"║  📦 Version {SEMVERSION}"
        # Pad to 61 chars (62 - 1 for closing ║)
        padding_needed = 61 - len(version_line)
        version_line_padded = version_line + " " * padding_needed + "║"

        banner = f"""
╔══════════════════════════════════════════════════════════════╗
║  🎬 svg2fbf - SVG Frame-by-Frame Animation Generator        ║
{version_line_padded}
║  ⚖️  License: Apache 2.0                                     ║
╚══════════════════════════════════════════════════════════════╝
"""
        print(banner)
    except UnicodeEncodeError:
        # Fallback to ASCII banner if terminal doesn't support Unicode
        print(f"""
+--------------------------------------------------------------+
|  svg2fbf - SVG Frame-by-Frame Animation Generator           |
|  Version {SEMVERSION:<50} |
|  License: Apache 2.0                                         |
+--------------------------------------------------------------+
""")


def print_version_only():
    """Print version for machine consumption (--version flag)"""
    print(SEMVERSION)


class ColoredHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """
    Custom help formatter that adds ANSI colors to argparse help output.

    Color scheme:
    - Section headers (USAGE, OPTIONS, etc.): Bright cyan, bold
    - Option flags (-f, --filename): Bright green
    - Option metavars (FILENAME, PATH): Yellow
    - Descriptions: White (default terminal color)
    - Example commands: Bright yellow
    - URLs: Bright blue with underline
    - Version numbers: Bright magenta
    """

    # ANSI color codes
    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Text decorations
    UNDERLINE = "\033[4m"

    def _format_usage(self, usage, actions, groups, prefix):
        """Format the usage line with colors"""
        if prefix is None:
            prefix = f"{self.BOLD}{self.BRIGHT_CYAN}USAGE:{self.RESET} "
        return super()._format_usage(usage, actions, groups, prefix)

    def _format_action(self, action):
        """Format each option/argument with colors"""
        # Get the original formatted action
        parts = super()._format_action(action).split("\n")

        # Color the option strings (e.g., -f, --filename)
        colored_parts = []
        for i, part in enumerate(parts):
            if i == 0 and part.strip():  # First line with option flags
                # Color option flags (but only at word boundaries to avoid coloring mid-word hyphens)
                part = re.sub(r"(?<!\w)(-{1,2}[\w-]+)(?=\s|,|$)", f"{self.BRIGHT_GREEN}\\1{self.RESET}", part)
                # Color metavars (uppercase words in descriptions)
                part = re.sub(r"\b([A-Z_]{2,})\b", f"{self.YELLOW}\\1{self.RESET}", part)
            colored_parts.append(part)

        return "\n".join(colored_parts)

    def start_section(self, heading):
        """Format section headings with colors"""
        if heading:
            heading = f"{self.BOLD}{self.BRIGHT_CYAN}{heading.upper()}{self.RESET}"
        return super().start_section(heading)


def setup_command_line_parser():
    """
    Set up the command-line argument parser with colored help output.

    Returns:
        ArgumentParser: Configured argument parser ready for parsing sys.argv
    """
    # Color helper for creating colored text
    C = ColoredHelpFormatter

    # Create description with colors
    description = f"""
{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}
  {C.BOLD}SVG Frame-by-Frame Animation Generator{C.RESET}
{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}

Creates frame-by-frame SVG animations (FBF format) from a sequence
of SVG files using SMIL animation.

{C.BOLD}Simplest usage - convert a folder:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf -i svg_frames -o output -f animation.fbf.svg -s 24{C.RESET}

{C.BOLD}Or use a YAML config file:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf scene_1.yaml{C.RESET}
"""

    # Create epilog with examples and animation types
    epilog = f"""
{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}
  {C.BOLD}{C.BRIGHT_CYAN}EXAMPLES{C.RESET}
{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}

{C.BOLD}Convert a folder of SVG frames:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf -i svg_frames -o output -f animation.fbf.svg -s 24{C.RESET}

{C.BOLD}Loop animation:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf -i frames -o out -f loop.fbf.svg -a loop -s 12{C.RESET}

{C.BOLD}With custom precision:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf -i frames -o out -f anim.fbf.svg -s 30 -d 5 -c 3{C.RESET}

{C.BOLD}Play on click:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf -i frames -o out -f click.fbf.svg -p{C.RESET}

{C.BOLD}Using YAML config file:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf scene_1.yaml{C.RESET}

{C.BOLD}Override YAML settings with CLI options:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf scene_1.yaml --speed 24.0 --title "My Animation"{C.RESET}

{C.BOLD}Traditional --config flag syntax:{C.RESET}
  {C.BRIGHT_YELLOW}svg2fbf --config scene_1.yaml --speed 12.0{C.RESET}

{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}
  {C.BOLD}{C.BRIGHT_CYAN}ANIMATION TYPES{C.RESET}
{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}

  {C.BRIGHT_GREEN}once{C.RESET}                      → START to END, then STOP
  {C.BRIGHT_GREEN}once_reversed{C.RESET}             → END to START, then STOP
  {C.BRIGHT_GREEN}loop{C.RESET}                      → START to END, repeat FOREVER
  {C.BRIGHT_GREEN}loop_reversed{C.RESET}             → END to START, repeat FOREVER
  {C.BRIGHT_GREEN}pingpong_once{C.RESET}             → START to END to START, then STOP
  {C.BRIGHT_GREEN}pingpong_loop{C.RESET}             → START to END to START, repeat FOREVER
  {C.BRIGHT_GREEN}pingpong_once_reversed{C.RESET}    → END to START to END, then STOP
  {C.BRIGHT_GREEN}pingpong_loop_reversed{C.RESET}    → END to START to END, repeat FOREVER

{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}
  For more information: {C.BRIGHT_BLUE}{C.UNDERLINE}https://github.com/Emasoft/svg2fbf{C.RESET}
{C.BRIGHT_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}
"""

    # Create parser with custom formatter
    parser = ArgumentParser(
        prog="svg2fbf",
        description=description,
        epilog=epilog,
        formatter_class=ColoredHelpFormatter,
        add_help=False,  # We'll add custom help option
    )

    # Positional argument for YAML config
    parser.add_argument("config_file", nargs="?", help="YAML configuration file (optional)", metavar="CONFIG.YAML")

    # Version and help options
    parser.add_argument("-v", "--version", action="store_true", dest="show_version", help="show version number and exit", default=False)
    parser.add_argument("-h", "--help", action="store_true", dest="show_help", help="show this help message and exit", default=False)

    # File options
    parser.add_argument("-f", "--filename", dest="output_filename", help="📄 define output filename (default: animation.fbf.svg)", default="animation.fbf.svg", metavar="FILENAME")
    parser.add_argument("-o", "--output_path", dest="output_path", help="📁 output path for the resulting FBF animation file (default: ./)", default="./", metavar="PATH")
    parser.add_argument("-i", "--input_folder", dest="input_folder", help="📂 input folder containing SVG frames (required unless using YAML config with explicit frames)", default=None, metavar="FOLDER")
    parser.add_argument("-s", "--speed", dest="fps", type=float, help="⏱️  frame rate in frames per second (default: 1.0)", default=1.0, metavar="FPS")
    parser.add_argument("-a", "--animation_type", choices=TYPE_CHOICES, dest="animation_type", default="loop", help="🎞️  animation type: once, loop, pingpong_once, pingpong_loop, etc. (default: loop)", metavar="TYPE")
    parser.add_argument("-m", "--max_frames", dest="max_frames", type=int, help="🔢 limit the maximum number of SVG files to load", default=None, metavar="N")
    parser.add_argument("--keep-xml-space", action="store_true", dest="keep_xml_space_attribute", default=False, help='won\'t remove the xml:space="preserve" attribute from the root SVG element')
    parser.add_argument("--no-keep-ratio", action="store_true", dest="no_keep_ratio", default=False, help="don't add preserveAspectRatio attribute to the output SVG (useful for animations with negative viewBox coordinates)")
    parser.add_argument("--align-mode", choices=["top-left", "center"], dest="align_mode", default="center", help="📐 alignment mode for fitting frames: 'center' (default, matches preserveAspectRatio='xMidYMid meet') or 'top-left'", metavar="MODE")
    parser.add_argument("-p", "--play_on_click", action="store_true", dest="play_on_click", default=False, help="make the svg animation start on click (require the 'object' tag instead of the 'img' tag in the html)")
    parser.add_argument("-b", "--backdrop", dest="backdrop", help="path to an image with the same w:h ratio to use as backdrop (e.g.: -b sky.jpg)", default="None", metavar="IMAGE")
    parser.add_argument("-d", "--digits", dest="digits", type=int, help="🔬 coordinate precision in significant digits (default: 28)", default=28, metavar="N")
    parser.add_argument("-c", "--cdigits", dest="cdigits", type=int, help="🔬 control point precision in significant digits (default: 28)", default=28, metavar="N")
    parser.add_argument("-q", "--quiet", action="store_true", dest="quiet_mode", help="🔇 don't print status messages to stdout", default=False)
    parser.add_argument("--no-browser", action="store_true", dest="no_browser", help="🚫 don't automatically open the generated FBF animation in browser", default=False)
    parser.add_argument("-r", "--copyright", action="store_true", dest="show_copyright_info", help="⚖️  show legal information and exit", default=False)

    # Metadata options - Authoring & Provenance
    metadata_group = parser.add_argument_group("metadata options")
    metadata_group.add_argument("--title", dest="title", help="📝 animation title", default=None, metavar="TITLE")
    metadata_group.add_argument("--episode-number", dest="episode_number", type=int, help="🎬 episode number in series", default=None, metavar="N")
    metadata_group.add_argument("--episode-title", dest="episode_title", help="🎬 episode-specific title", default=None, metavar="TITLE")
    metadata_group.add_argument("--creators", dest="creators", help="👥 current animation creators, comma-separated (e.g., 'John Doe, Jane Smith')", default=None, metavar="NAMES")
    metadata_group.add_argument("--original-creators", dest="original_creators", help="👥 original content creators", default=None, metavar="NAMES")
    metadata_group.add_argument("--copyrights", dest="copyrights", help="© copyright statement (e.g., '© 2025 Company Name')", default=None, metavar="TEXT")
    metadata_group.add_argument("--website", dest="website", help="🌐 official website or info page URL", default=None, metavar="URL")
    metadata_group.add_argument("--language", dest="language", help="🌍 content language code (e.g., 'en', 'it', 'fr')", default=None, metavar="CODE")
    metadata_group.add_argument("--original-language", dest="original_language", help="🌍 original production language (e.g., 'en-US', 'it-IT')", default=None, metavar="CODE")
    metadata_group.add_argument("--keywords", dest="keywords", help="🏷️  search keywords, comma-separated (e.g., 'animation, cartoon, comedy')", default=None, metavar="WORDS")
    metadata_group.add_argument("--description", dest="description", help="📄 animation description or synopsis", default=None, metavar="TEXT")
    metadata_group.add_argument("--rights", dest="rights", help="⚖️  license or usage rights (e.g., 'CC BY-SA 4.0', 'All Rights Reserved')", default=None, metavar="TEXT")
    metadata_group.add_argument("--source", dest="source", help="🎨 original source software or tool used to create the animation", default=None, metavar="SOFTWARE")

    # Configuration file option
    parser.add_argument("--config", dest="config", help="⚙️  path to YAML configuration file containing metadata and options", default=None, metavar="FILE")

    # Text-to-path conversion options
    parser.add_argument("--text2path", action="store_true", dest="text2path", default=False, help="convert all text elements to paths using svg-text2path (requires: uv tool install svg2fbf[text2path])")
    parser.add_argument("--text2path-strict", action="store_true", dest="text2path_strict", default=False, help="fail if any font is missing during text-to-path conversion")

    return parser


###################################################
# YAML Configuration Support Functions
###################################################


def load_yaml_config(config_path):
    """
    Load metadata and generation parameters from a YAML configuration file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Dictionary with 'metadata' and 'generation_parameters' sections,
        or None if file doesn't exist or cannot be loaded

    Example YAML structure:
        metadata:
            title: "Animation Title"
            creators: "Artist Name"
            # ... etc

        generation_parameters:
            frames:  # Explicit frame list (optional)
                - "path/to/frame1.svg"
                - "path/to/frame2.svg"
            input_folder: "examples/seagull/"  # Alternative
            speed: 12.0
            animation_type: "loop"
            # ... etc
    """
    # Handle None or empty path - Return None gracefully, file not found
    # is not an error in this context
    if config_path is None or config_path == "":
        return None

    config_path = Path(config_path)

    # Check if file exists - Return None gracefully, missing config is optional
    if not config_path.exists():
        ppp(f"⚠️  Configuration file not found: {config_path}")
        return None

    try:
        # Load YAML file using safe loader to prevent code execution vulnerabilities
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Validate structure - Ensure we have the expected top-level sections
        if config is None:
            ppp(f"⚠️  Configuration file is empty: {config_path}")
            return None

        # Initialize sections if not present - Gracefully handle partial configs
        if "metadata" not in config:
            config["metadata"] = {}
        if "generation_parameters" not in config:
            config["generation_parameters"] = {}

        ppp(f"✓ Loaded configuration from: {config_path}")
        return config

    except yaml.YAMLError as e:
        # YAML parsing error - Show error but don't crash, allow CLI to work
        # without config
        ppp(f"⚠️  Error parsing YAML file {config_path}:")
        ppp(f"   {str(e)}")
        return None
    except Exception as e:
        # Any other error loading the file - Log and continue without config
        ppp(f"⚠️  Error loading configuration file {config_path}:")
        ppp(f"   {str(e)}")
        return None


def merge_config_with_cli(yaml_config, cli_options):
    """
    Merge YAML configuration with CLI options.

    Priority order: CLI arguments > YAML config > defaults
    CLI arguments always take precedence when explicitly provided.

    Args:
        yaml_config: Dictionary loaded from YAML file (or None)
        cli_options: Parsed CLI options object from argparse (Namespace)

    Returns:
        Updated cli_options object with YAML values applied where CLI didn't specify

    Implementation note:
        - Only applies YAML values if CLI option is None (not explicitly set)
        - Handles both metadata and generation_parameters sections
        - Maps snake_case YAML keys to CLI option names
    """
    if yaml_config is None:
        return cli_options

    metadata = yaml_config.get("metadata", {})
    gen_params = yaml_config.get("generation_parameters", {})

    # Metadata fields - Only set if CLI didn't provide value
    # (None check ensures CLI priority)
    if cli_options.title is None and "title" in metadata:
        cli_options.title = metadata["title"]
    if cli_options.episode_number is None and "episode_number" in metadata:
        cli_options.episode_number = metadata["episode_number"]
    if cli_options.episode_title is None and "episode_title" in metadata:
        cli_options.episode_title = metadata["episode_title"]
    if cli_options.creators is None and "creators" in metadata:
        cli_options.creators = metadata["creators"]
    if cli_options.original_creators is None and "original_creators" in metadata:
        cli_options.original_creators = metadata["original_creators"]
    if cli_options.copyrights is None and "copyrights" in metadata:
        cli_options.copyrights = metadata["copyrights"]
    if cli_options.website is None and "website" in metadata:
        cli_options.website = metadata["website"]
    if cli_options.language is None and "language" in metadata:
        cli_options.language = metadata["language"]
    if cli_options.original_language is None and "original_language" in metadata:
        cli_options.original_language = metadata["original_language"]
    if cli_options.keywords is None and "keywords" in metadata:
        cli_options.keywords = metadata["keywords"]
    if cli_options.description is None and "description" in metadata:
        cli_options.description = metadata["description"]
    if cli_options.rights is None and "rights" in metadata:
        cli_options.rights = metadata["rights"]
    if cli_options.source is None and "source" in metadata:
        cli_options.source = metadata["source"]

    # Generation parameters - Apply YAML values if CLI used defaults
    # Check against defaults to detect if user explicitly set CLI values
    if "output_path" in gen_params and cli_options.output_path == "./":
        cli_options.output_path = gen_params["output_path"]
    if "filename" in gen_params and cli_options.output_filename == "animation.fbf.svg":
        cli_options.output_filename = gen_params["filename"]
    if "input_folder" in gen_params and cli_options.input_folder is None:
        cli_options.input_folder = gen_params["input_folder"]
    if "speed" in gen_params and cli_options.fps == 1.0:
        cli_options.fps = float(gen_params["speed"])
    if "animation_type" in gen_params and cli_options.animation_type == "loop":
        cli_options.animation_type = gen_params["animation_type"]
    if "digits" in gen_params and cli_options.digits == 28:
        cli_options.digits = int(gen_params["digits"])
    if "cdigits" in gen_params and cli_options.cdigits == 28:
        cli_options.cdigits = int(gen_params["cdigits"])
    if "backdrop" in gen_params and cli_options.backdrop == "None":
        cli_options.backdrop = gen_params["backdrop"]
    if "play_on_click" in gen_params and not cli_options.play_on_click:
        cli_options.play_on_click = gen_params["play_on_click"]
    if "keep_xml_space" in gen_params and not cli_options.keep_xml_space_attribute:
        cli_options.keep_xml_space_attribute = gen_params["keep_xml_space"]
    if "align_mode" in gen_params and cli_options.align_mode == "center":
        align_mode_value = gen_params["align_mode"]
        if align_mode_value not in ["top-left", "center"]:
            add2log(f"WARNING: Invalid align_mode '{align_mode_value}' in YAML config. Using default 'center'.")
        else:
            cli_options.align_mode = align_mode_value
    if "quiet" in gen_params and not cli_options.quiet_mode:
        cli_options.quiet_mode = gen_params["quiet"]
    if "max_frames" in gen_params and cli_options.max_frames is None:
        cli_options.max_frames = int(gen_params["max_frames"])

    return cli_options


def get_frame_list_from_config(yaml_config, input_folder):
    """
    Get the list of frame files to process.

    Priority:
    1. If yaml_config has explicit 'frames' list → use that
    2. Otherwise → fall back to scanning input_folder

    Args:
        yaml_config: Dictionary loaded from YAML file (or None)
        input_folder: Path to folder containing SVG frames (fallback)

    Returns:
        List of Path objects for frame files, or None to use default scanning

    Raises:
        SystemExit: If explicit frames list contains non-existent files

    Implementation note:
        - Validates that all explicitly listed frame paths exist
        - Allows mixing relative and absolute paths in frames list
        - Returns None if no explicit frames list, signaling to use normal
          folder scanning
    """
    if yaml_config is None:
        return None

    gen_params = yaml_config.get("generation_parameters", {})

    # Check for explicit frames list in YAML - This overrides input_folder scanning
    if "frames" in gen_params and gen_params["frames"]:
        frames = gen_params["frames"]
        frame_paths = []

        ppp(f"📋 Using explicit frame list from YAML config ({len(frames)} frames)")

        # Validate and convert each frame path - Fail fast if any path is invalid
        for frame_str in frames:
            frame_path = Path(frame_str)

            # Make relative paths relative to config file location if possible
            # This allows portable config files with relative frame paths
            if not frame_path.is_absolute():
                # If frame path is relative, it's relative to current working directory
                # User should ensure they run svg2fbf from the correct directory
                frame_path = Path.cwd() / frame_path

            if not frame_path.exists():
                ppp(f"❌ ERROR: Frame file not found: {frame_str}")
                ppp(f"   Resolved to: {frame_path}")
                sys.exit(1)

            if frame_path.suffix.lower() not in [".svg"]:
                ppp(f"⚠️  WARNING: Frame file is not an SVG: {frame_str}")

            frame_paths.append(frame_path)

        ppp(f"✓ All {len(frame_paths)} frame files validated")
        return frame_paths

    # No explicit frames list - return None to signal default folder scanning
    return None


def tryint(s: str) -> int | str:
    """Convert string to int if possible, otherwise return original string.

    Args:
        s: String to convert

    Returns:
        Integer if conversion successful, original string otherwise
    """
    try:
        return int(s)
    except ValueError:
        return s


def alphanum_key(s):
    """Turn a string into a list of string and number chunks.
    "z23a" -> ["z", 23, "a"]
    """
    return [tryint(c) for c in re.split("([0-9]+)", s)]


def sort_input_paths(input_paths, parse_ending_numbers_as_ints):
    # checking that we have at least 1 file
    if (input_paths is None) or (len(input_paths) < 1):
        ppp("ERROR - Insufficient number of frames in input folder.\nExiting.")
        sys.exit()

    # Special case: single frame doesn't need sorting
    if len(input_paths) == 1:
        return [str(input_paths[0])]

    if parse_ending_numbers_as_ints is None:
        parse_ending_numbers_as_ints = True

    output_paths = None
    if parse_ending_numbers_as_ints is True:
        # this is the default (for lists as: file1.svg, file2.svg..file10.svg..)
        output_paths = [str(path) for path in input_paths]
        output_paths.sort(key=alphanum_key)
    # 		ppp("DEBUG: output_paths (sorted by parsing ending numbers as int)")
    # 		[ppp(f'\t{element}') for element in output_paths]
    # 		ppp("DEBUG END\n")
    else:
        # no int parsing (i.e. for padded lists as: file0001,..,file0010.svg..)
        sorted_paths = sorted(input_paths)
        output_paths = [str(path) for path in sorted_paths]
    # 		ppp("DEBUG: output_paths (sorted as strings, requires number padding)")
    # 		[ppp(f'\t{element}') for element in output_paths]
    # 		ppp("DEBUG END\n")

    return output_paths


def change_extension_to_fbfsvg(file_name):
    filename_without_extension = file_name.split(".")[0]
    return filename_without_extension + ".fbf.svg"


# my simpler, more compatible print function
#
def ppp(txt=""):
    txt = txt.replace("\n", "\n\r")
    try:
        sys.stdout.write("\r" + txt + "\n\r")
    except UnicodeEncodeError:
        # Windows console encoding issue - try UTF-8
        # Why: Windows cmd.exe defaults to cp1252 which doesn't support Unicode box chars
        try:
            sys.stdout.buffer.write(("\r" + txt + "\n\r").encode("utf-8"))
        except Exception:
            # Last resort: strip problematic Unicode characters
            import unicodedata

            txt_ascii = "".join(c if ord(c) < 128 else "?" for c in txt)
            sys.stdout.write("\r" + txt_ascii + "\n\r")


def pppd(txt="", function_name=None):
    if function_name is None:
        ppp("DEBUG START:")
        ppp(txt)
        ppp("DEBUG END.")
    else:
        ppp(f"DEBUG FUNCTION {function_name} START:")
        ppp(txt)
        ppp(f"DEBUG FUNCTION {function_name} END.")
    return


def ppx(xml_doc):
    ppp("DEBUG XML DOC START:")
    ppp(xml_doc.toprettyxml())
    ppp("DEBUG XML DOC END.")
    ppp()
    return


# my simple log function
# TODO: add a "save log to file" option
#
def add2log(txt=""):
    global log
    txt = txt.replace("\n", "\n\r")
    if log is None:
        log = "\r\n\r"
        log += "\r   ┌─┬─┬─┬─┬─┬─┬─┬─┬─┐\n\r"
        log += "\r   │E│R│R│O│R│ │L│O│G│\n\r"
        log += "\r╾──┴─┴─┴─┴─┴─┴─┴─┴─┴─┴──╼\n\r"

    log += "\r" + txt + "\n\r"


def print_log_and_exit(exit_code=1):
    """Print the accumulated error log and exit with the given code."""
    global log
    if log is not None:
        ppp(log)
    sys.exit(exit_code)


def open_in_browser(filepath):
    """
    Open the generated FBF SVG file in Chrome/Chromium browser, with fallback to default browser.

    Why: Provide immediate visual feedback of the generated animation
    Why: Try Chrome first, then Chromium (both have excellent SVG/SMIL support),
         fall back to default if neither available

    Args:
        filepath: Path to the generated FBF SVG file
    """
    # Convert to absolute path and file:// URL
    # Why: Browsers need absolute file:// URLs to open local files
    abs_path = os.path.abspath(filepath)
    file_url = f"file://{abs_path}"

    try:
        # Try Chrome first (best SVG animation support)
        # Why: Chrome has excellent SMIL/SVG animation support
        chrome_paths = {
            "darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
            "linux": "google-chrome",  # Linux
            "linux2": "google-chrome",  # Linux (older Python)
            "win32": "chrome",  # Windows
        }

        chrome_path = chrome_paths.get(sys.platform)

        if chrome_path:
            try:
                # Why: Use subprocess for Chrome to avoid blocking and get better error handling
                if sys.platform == "darwin":
                    # macOS: use 'open -a' for proper app launching
                    subprocess.Popen(["open", "-a", chrome_path, file_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # Linux/Windows: direct chrome executable
                    subprocess.Popen([chrome_path, file_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if not options.quiet_mode:
                    ppp(f"🌐 Opening in Chrome: {filepath}")
                return
            except (FileNotFoundError, OSError):
                # Chrome not found, try Chromium
                pass

        # Try Chromium if Chrome not available
        # Why: Chromium has the same excellent SVG/SMIL support as Chrome
        chromium_paths = {
            "darwin": "/Applications/Chromium.app/Contents/MacOS/Chromium",  # macOS
            "linux": "chromium-browser",  # Linux (Debian/Ubuntu)
            "linux2": "chromium-browser",  # Linux (older Python)
            "win32": "chromium",  # Windows
        }

        chromium_path = chromium_paths.get(sys.platform)

        if chromium_path:
            try:
                # Why: Use subprocess for Chromium to avoid blocking and get better error handling
                if sys.platform == "darwin":
                    # macOS: use 'open -a' for proper app launching
                    subprocess.Popen(["open", "-a", chromium_path, file_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # Linux/Windows: direct chromium executable
                    # Why: Try both 'chromium' and 'chromium-browser' for different Linux distros
                    try:
                        subprocess.Popen([chromium_path, file_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except (FileNotFoundError, OSError):
                        # Try alternate chromium command name
                        subprocess.Popen(["chromium", file_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if not options.quiet_mode:
                    ppp(f"🌐 Opening in Chromium: {filepath}")
                return
            except (FileNotFoundError, OSError):
                # Chromium not found, fall through to default browser
                pass

        # Fallback to default browser
        # Why: If Chrome and Chromium fail or not available, use system default browser
        if webbrowser.open(file_url, new=2):  # new=2 opens in new tab if possible
            if not options.quiet_mode:
                ppp(f"🌐 Opening in default browser: {filepath}")
        else:
            # Browser opening failed
            if not options.quiet_mode:
                ppp(f"⚠️  Could not open browser automatically. Please open manually: {filepath}")

    except Exception as e:
        # Don't fail the whole program if browser opening fails
        # Why: Browser opening is a convenience feature, not critical functionality
        if not options.quiet_mode:
            ppp(f"⚠️  Could not open browser: {e}")


# simple function to remove prefixes
# (TODO: check if python is > v3.9 and use standard
# function remove_prefixes). Also if you know the number
# of letters in advance you could just use mytextstring[n:0]
# where n is the number of letters of the prefix.
def remove_prefix(text, prefix):
    if text.startswith(prefix):  # only modify the text if it starts with the prefix
        text = text.replace(prefix, "", 1)  # remove one instance of prefix
    return text


# a simple padding function for keeping the 0s before the number.
# I don't use zfill() because I need to be sure of type (integer).
def paddedNum(input_integer: int, number_of_digits: int) -> str:
    return "{num:0{width}}".format(num=int(input_integer), width=int(number_of_digits))


# a function to truncate floats and decimals to a
# given number of digits for printing purposes
#
def truncDec(dec: Decimal, digits: int) -> decimal.Decimal:
    round_down_ctx = decimal.getcontext()
    round_down_ctx.rounding = decimal.ROUND_DOWN
    new_dec = round_down_ctx.create_decimal(dec)
    return round(new_dec, digits)


# global variables
log = None
current_filepath = None
options: Namespace | None = None
scouringContext: Context | None = None
scouringContextC: Context | None = None

# List of properties that can reference other elements
referencingProps = [
    "fill",
    "stroke",
    "filter",
    "clip-path",
    "mask",
    "marker-start",
    "marker-end",
    "marker-mid",
]
xml_output_doc = None
xml_output_svg = None
xml_output_defs = None
xml_output_shared = None
frames_sequence_ids = None
input_nodes_flagged_as_not_to_move = None
xml_input_svg = None
output_duplicates_list = None
inputReferencingElementsDict = None
outputReferencingElementsDict = None

# styles for elems and frame group
style_rules_for_elements = None
framerules = None

# hash dictionaries
elementsInputHashDict = None
elementsOutputHashDict = None


# viewbox
vbXdoc = None
vbYdoc = None
vbWdoc = None
vbHdoc = None
output_vbstring = None

# frame size
wdoc = None
hdoc = None


#####################################################################
# Content Feature Detection Functions
# These functions scan SVG files to automatically detect metadata
# fields like useMeshGradient, useEmbeddedImages, etc.
#####################################################################


def detect_mesh_gradients(svg_files):
    """
    Detect if any SVG file contains mesh gradient elements.

    Scans the provided SVG files for <meshgradient> or <svg:meshgradient>
    elements using efficient regex patterns.

    Args:
        svg_files: List of file paths to SVG files to scan

    Returns:
        bool: True if any file contains mesh gradients, False otherwise

    Example:
        >>> svg_files = ["/path/to/frame1.svg", "/path/to/frame2.svg"]
        >>> has_mesh = detect_mesh_gradients(svg_files)
        >>> print(f"Uses mesh gradients: {has_mesh}")
    """
    import re

    # WHY: Regex pattern to match both namespaced and non-namespaced mesh gradient tags
    # Supports: <meshgradient>, <svg:meshgradient>, and variants with attributes
    mesh_pattern = re.compile(r"<(?:svg:)?meshgradient[\s>]", re.IGNORECASE)

    for svg_file in svg_files:
        try:
            # WHY: Use 'rb' mode to handle both regular and gzipped SVG files
            with maybe_gziped_file(svg_file, mode="rb") as f:
                content = f.read()
                # WHY: Decode bytes to string for regex matching
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="ignore")

                # WHY: Return immediately on first match for efficiency
                if mesh_pattern.search(content):
                    return True
        except OSError as e:
            # WHY: Gracefully handle file read errors, continue with other files
            add2log(f"WARNING: Could not read {svg_file} for mesh gradient detection: {e}")
            continue

    return False


def detect_embedded_images(svg_files):
    """
    Detect if any SVG file contains base64-encoded embedded images.

    Scans for <image> elements with base64 data URIs in xlink:href attributes.
    Looks for patterns like xlink:href="data:image/png;base64,..."

    Args:
        svg_files: List of file paths to SVG files to scan

    Returns:
        bool: True if any file contains embedded images, False otherwise

    Example:
        >>> svg_files = ["/path/to/frame1.svg"]
        >>> has_embedded = detect_embedded_images(svg_files)
        >>> print(f"Uses embedded images: {has_embedded}")
    """
    import re

    # WHY: Pattern matches data URIs with base64-encoded images in image elements
    # Supports both xlink:href and href attributes (SVG 1.1 and SVG 2.0)
    # Also handles namespaced svg:image elements
    embedded_image_pattern = re.compile(r'<(?:svg:)?image[^>]*(?:xlink:)?href\s*=\s*["\']data:image/', re.IGNORECASE)

    for svg_file in svg_files:
        try:
            with maybe_gziped_file(svg_file, mode="rb") as f:
                content = f.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="ignore")

                if embedded_image_pattern.search(content):
                    return True
        except OSError as e:
            add2log(f"WARNING: Could not read {svg_file} for embedded image detection: {e}")
            continue

    return False


def detect_css_classes(svg_files):
    """
    Detect if any SVG file contains elements with CSS class attributes.

    Scans for class="..." attributes on any SVG elements.

    Args:
        svg_files: List of file paths to SVG files to scan

    Returns:
        bool: True if any elements use CSS classes, False otherwise

    Example:
        >>> svg_files = ["/path/to/styled.svg"]
        >>> has_classes = detect_css_classes(svg_files)
        >>> print(f"Uses CSS classes: {has_classes}")
    """
    import re

    # WHY: Pattern matches class attributes with non-empty, non-whitespace values
    # Avoids false positives from empty class="" or class="   " attributes
    # Must contain at least one non-whitespace character
    css_class_pattern = re.compile(r'\sclass\s*=\s*["\'][^"\'\s]+[^"\']*["\']', re.IGNORECASE)

    for svg_file in svg_files:
        try:
            with maybe_gziped_file(svg_file, mode="rb") as f:
                content = f.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="ignore")

                if css_class_pattern.search(content):
                    return True
        except OSError as e:
            add2log(f"WARNING: Could not read {svg_file} for CSS class detection: {e}")
            continue

    return False


def detect_external_fonts(svg_files):
    """
    Detect if any SVG file references external font files.

    Scans for:
    - <style> blocks containing @font-face rules
    - <link> elements pointing to external stylesheets
    - References to .woff, .woff2, .ttf, .otf font files

    Args:
        svg_files: List of file paths to SVG files to scan

    Returns:
        bool: True if external fonts are referenced, False otherwise

    Example:
        >>> svg_files = ["/path/to/custom_font.svg"]
        >>> has_fonts = detect_external_fonts(svg_files)
        >>> print(f"Uses external fonts: {has_fonts}")
    """
    import re

    # WHY: Multiple patterns to catch different font reference methods
    # @font-face in style blocks, font file extensions, external stylesheet links
    font_patterns = [
        re.compile(r"@font-face\s*\{", re.IGNORECASE),
        re.compile(r'\.(woff2?|ttf|otf)["\'\s)]', re.IGNORECASE),
        re.compile(r'<link[^>]*rel\s*=\s*["\']stylesheet["\'][^>]*>', re.IGNORECASE),
    ]

    for svg_file in svg_files:
        try:
            with maybe_gziped_file(svg_file, mode="rb") as f:
                content = f.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="ignore")

                # WHY: Check all patterns, return True on first match
                for pattern in font_patterns:
                    if pattern.search(content):
                        return True
        except OSError as e:
            add2log(f"WARNING: Could not read {svg_file} for external font detection: {e}")
            continue

    return False


def detect_external_media(svg_files):
    """
    Detect if any SVG file references external media files.

    Scans for <image> elements with xlink:href pointing to external files
    (not base64 data URIs). Looks for references to .png, .jpg, .jpeg, .gif,
    .webp, and other common image formats.

    Args:
        svg_files: List of file paths to SVG files to scan

    Returns:
        bool: True if external media files are referenced, False otherwise

    Example:
        >>> svg_files = ["/path/to/frame.svg"]
        >>> has_external = detect_external_media(svg_files)
        >>> print(f"Uses external media: {has_external}")
    """
    import re

    # WHY: Pattern matches image elements with href to external files
    # Excludes data: URIs (those are embedded, not external)
    # Matches common image file extensions
    # Also handles namespaced svg:image elements
    external_media_pattern = re.compile(
        r'<(?:svg:)?image[^>]*(?:xlink:)?href\s*=\s*["\'](?!data:)[^"\']*\.(png|jpe?g|gif|webp|bmp|svg)["\']',
        re.IGNORECASE,
    )

    for svg_file in svg_files:
        try:
            with maybe_gziped_file(svg_file, mode="rb") as f:
                content = f.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="ignore")

                if external_media_pattern.search(content):
                    return True
        except OSError as e:
            add2log(f"WARNING: Could not read {svg_file} for external media detection: {e}")
            continue

    return False


# ============================================================================
# SVG CONTENT FILTERING FUNCTIONS
# ============================================================================
# These functions detect incompatible SVG content that cannot be converted
# to static frame-by-frame animations. They are used during file loading
# to skip incompatible files before processing begins.


# JavaScript exceptions list - patterns that should NOT trigger filtering
JAVASCRIPT_EXCEPTIONS = [
    "meshgradient",  # Mesh gradient polyfill is allowed
    # Future exceptions can be added here
]


def contains_smil_animations(svg_path):
    """
    Check if an SVG file contains SMIL animation elements.

    SMIL (Synchronized Multimedia Integration Language) animations are time-based
    and cannot be converted to static frame-by-frame animations. This function
    detects all SMIL animation elements in SVG files.

    Args:
        svg_path: Path (string) to SVG file to check

    Returns:
        bool: True if the file contains SMIL animations, False otherwise

    SMIL Animation Elements Detected:
        - <animate>: Animates attribute values over time
        - <animateTransform>: Animates transformation attributes
        - <animateMotion>: Animates element position along a path
        - <animateColor>: Animates color attributes (deprecated but still used)
        - <set>: Sets attribute value at a specific time

    Why Filter SMIL Animations:
        FBF.SVG is designed for static frame-by-frame animations where each frame
        is explicitly defined. SMIL animations are time-based and require runtime
        execution to interpolate between states, which cannot be represented in
        the FBF format.

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency.
    """
    try:
        with open(svg_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Check for SMIL animation tags
        # WHY: Match both self-closing and opening tags with space or >
        animation_tags = [
            "<animate ",
            "<animate>",
            "<animateTransform ",
            "<animateTransform>",
            "<animateMotion ",
            "<animateMotion>",
            "<animateColor ",
            "<animateColor>",
            "<set ",
            "<set>",
        ]

        for tag in animation_tags:
            if tag in content:
                return True

        return False

    except Exception:
        # If we can't read the file, assume it's safe to process
        return False


def contains_javascript(svg_path, exceptions=None):
    """
    Check if an SVG file contains JavaScript or event handlers.

    JavaScript in SVG files requires runtime execution and cannot be converted
    to static frames. This function detects JavaScript while allowing specific
    exceptions for necessary polyfills.

    Args:
        svg_path: Path (string) to SVG file to check
        exceptions: List of exception patterns (default: JAVASCRIPT_EXCEPTIONS)

    Returns:
        bool: True if file contains non-excepted JavaScript, False otherwise

    JavaScript Patterns Detected:
        - <script> tags (with or without CDATA)
        - Event attributes: onload, onclick, onmouseover, onmouseout, etc.
        - javascript: URLs in href/xlink:href attributes

    Exceptions:
        Some JavaScript is necessary for SVG features (e.g., mesh gradient polyfills).
        The exceptions list allows these to pass through filtering.

    Why Filter JavaScript:
        - Requires runtime execution environment
        - Interactive behavior cannot be captured in static frames
        - May modify DOM dynamically in ways incompatible with FBF format

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency.
    """
    if exceptions is None:
        exceptions = JAVASCRIPT_EXCEPTIONS

    try:
        with open(svg_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        content_lower = content.lower()

        # Check for <script> tags with exceptions
        if "<script" in content_lower:
            is_excepted = False
            for exception_pattern in exceptions:
                if exception_pattern.lower() in content_lower:
                    is_excepted = True
                    break
            if not is_excepted:
                return True

        # Check for event handler attributes
        event_handlers = [
            "onload=",
            "onclick=",
            "onmouseover=",
            "onmouseout=",
            "onmousemove=",
            "onmousedown=",
            "onmouseup=",
            "onfocus=",
            "onblur=",
            "onactivate=",
            "onbegin=",
            "onend=",
            "onrepeat=",
        ]
        for handler in event_handlers:
            if handler in content_lower:
                return True

        # Check for javascript: URLs
        if "javascript:" in content_lower:
            return True

        return False

    except Exception:
        # If we can't read the file, assume it's safe to process
        return False


def contains_nested_svg(svg_path):
    """
    Check if an SVG file contains nested <svg> elements.

    Nested SVG elements create separate coordinate systems and viewports,
    which can cause rendering inconsistencies when converted to FBF format.

    Args:
        svg_path: Path (string) to SVG file to check

    Returns:
        bool: True if file contains nested SVG elements, False otherwise

    Why Filter Nested SVG:
        - Creates multiple coordinate systems within one document
        - Viewport calculations become complex and error-prone
        - FBF format assumes single root SVG coordinate system
        - May render differently across browsers/implementations

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency.
    """
    try:
        with open(svg_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        content_lower = content.lower()

        # Count <svg occurrences (case-insensitive)
        # More than one <svg tag means nested SVG
        svg_count = content_lower.count("<svg")

        return svg_count > 1

    except Exception:
        # If we can't read the file, assume it's safe to process
        return False


def contains_media_elements(svg_path):
    """
    Check if an SVG file contains multimedia elements.

    SVG 2.0 introduced several multimedia elements (video, audio, iframe, canvas,
    foreignObject) that are not suitable for static frame-by-frame animations.
    These elements represent time-based content, external media, or require
    runtime execution that cannot be meaningfully captured in static frames.

    Note: This does NOT filter static embedded content like fonts
    (<font>, <glyph>) or images (<image>), which are fully supported and
    render correctly in static frames.

    Args:
        svg_path: Path (string) to SVG file to check

    Returns:
        bool: True if file contains any multimedia elements, False otherwise

    Multimedia Elements Detected:
        - <video>: Embedded video content (SVG 2.0)
          https://www.w3.org/TR/2014/WD-SVG2-20140211/embedded.html#VideoElement
          Time-based content that cannot be represented in a single frame

        - <audio>: Embedded audio content (SVG 2.0)
          https://www.w3.org/TR/2014/WD-SVG2-20140211/embedded.html#AudioElement
          Audio has no visual representation for static frames

        - <iframe>: Embedded HTML iframe (SVG 2.0)
          https://www.w3.org/TR/2014/WD-SVG2-20140211/embedded.html#IframeElement
          External web content/HTML requiring runtime loading

        - <canvas>: HTML5 canvas element (SVG 2.0)
          https://www.w3.org/TR/2014/WD-SVG2-20140211/embedded.html#CanvasElement
          Requires JavaScript for drawing, no static visual content

        - <foreignObject>: Non-SVG content container (SVG 1.1/2.0)
          https://www.w3.org/TR/2014/WD-SVG2-20140211/extend.html#ForeignObjectElement
          Can contain arbitrary HTML/MathML/scripts that won't render correctly

    Elements NOT Filtered (static embedded content allowed):
        - <image>: Raster images (PNG, JPEG, etc.) - static visual content
        - <font>, <glyph>: SVG fonts - static embedded font definitions
        - Base64 data URIs: Inline embedded images/fonts - static content

    Why Filter Multimedia Elements:
        - Video/audio are time-based and cannot be represented in static frames
        - iframe contains external web/HTML content requiring runtime execution
        - canvas requires JavaScript to draw, has no static content
        - foreignObject can contain arbitrary HTML/scripts that won't render
        - Including them would result in incomplete or misleading visual output

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency.
    """
    try:
        with open(svg_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        content_lower = content.lower()

        # Check for SVG 2.0 multimedia elements
        # WHY: Use lowercase for case-insensitive matching
        # These are elements for time-based media, external content, or
        # runtime execution
        multimedia_tags = [
            "<video",  # Video element (time-based multimedia)
            "<audio",  # Audio element (no visual representation)
            "<iframe",  # iFrame element (external web/HTML content)
            "<canvas",  # Canvas element (requires JavaScript to draw)
            "<foreignobject",  # foreignObject (can contain HTML/scripts)
        ]

        for tag in multimedia_tags:
            if tag in content_lower:
                return True

        return False

    except Exception:
        # If we can't read the file, assume it's safe to process
        return False


def infer_content_features(svg_files):
    """
    Automatically infer all content feature metadata by scanning SVG files.

    Calls all detection functions and returns a dictionary with boolean
    values for each feature. This is the main function to use for automatic
    metadata detection.

    Args:
        svg_files: List of file paths to SVG files to scan

    Returns:
        dict: Dictionary with detected feature flags:
            {
                'useMeshGradient': bool,
                'useEmbeddedImages': bool,
                'useCssClasses': bool,
                'useExternalFonts': bool,
                'useExternalMedia': bool
            }

    Example:
        >>> svg_files = ["/path/to/frame1.svg", "/path/to/frame2.svg"]
        >>> features = infer_content_features(svg_files)
        >>> print(f"Mesh gradients: {features['useMeshGradient']}")
        >>> print(f"Embedded images: {features['useEmbeddedImages']}")
    """
    # WHY: Call all detection functions to build complete feature dictionary
    # This provides a single entry point for all content feature detection
    return {
        "useMeshGradient": detect_mesh_gradients(svg_files),
        "useEmbeddedImages": detect_embedded_images(svg_files),
        "useCssClasses": detect_css_classes(svg_files),
        "useExternalFonts": detect_external_fonts(svg_files),
        "useExternalMedia": detect_external_media(svg_files),
    }


#####################################################################
# End of Content Feature Detection Functions
#####################################################################


def applyStyleRulesToElements(style_rules):
    for rule in style_rules:
        applyStyleRuleToElementsByTag(rule, rule["selector"])


def applyStyleRuleToElementsByTag(rule, tag):
    elements_to_style = xml_input_svg.getElementsByTagName(tag)
    for node in elements_to_style:
        for propname in rule["properties"]:
            if propname.isspace() is False and propname.strip() in CSS_TO_SVG_DICT:
                corr_propname = CSS_TO_SVG_DICT.get(propname.strip())
                if corr_propname.isspace() is False:
                    if node.hasAttribute(corr_propname.strip()) is False:
                        node.setAttribute(corr_propname.strip(), rule["properties"][propname].strip())


def generate_fbfsvg_animation():
    """Generate FBFSVG animation from input SVG files.

    Raises:
        OSError: If input/output paths are invalid
        ValueError: If input parameters are invalid
        xml.parsers.expat.ExpatError: If XML parsing fails
    """
    global options
    global scouringContext
    global scouringContextC
    global log
    global current_filepath
    global xml_output_doc
    global xml_output_svg
    global xml_output_defs
    global xml_output_shared
    global frames_sequence_ids
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS
    global RETARGETABLE_ELEMENTS
    global SVG_ELEMENTS_TO_ALWAYS_MOVE
    global xml_input_svg
    global output_duplicates_list
    global inputReferencingElementsDict
    global outputReferencingElementsDict

    # viewbox
    global vbXdoc
    global vbYdoc
    global vbWdoc
    global vbHdoc
    global output_vbstring

    # frame size
    global wdoc
    global hdoc

    # default or invalid value
    if options.cdigits < 0:
        options.cdigits = options.digits

    # create decimal contexts with reduced precision for scouring numbers
    # calculations should be done in the default context (precision defaults
    # to 28 significant digits) to minimize errors
    scouringContext = Context(prec=options.digits)
    scouringContextC = Context(prec=options.cdigits)

    # svg fill & stroke color
    svg_fill = None
    svg_stroke = None

    # output hash dictionary
    global elementsInputHashDict
    global elementsOutputHashDict
    global output_duplicates_list
    global input_duplicates_list
    elementsInputHashDict = {}
    elementsOutputHashDict = {}

    # styles fr elems and frame groups
    global framerules
    global style_rules_for_elements

    frame_duration = 1.0 / float(options.fps)

    try:
        # Validate and create input/output paths
        # Why: input_folder is optional when explicit frames are provided
        # Only use input_folder if explicit frames are not provided
        if hasattr(options, "explicit_frames") and options.explicit_frames is not None:
            # Using explicit frames from generation card - no need for input_folder
            svginputpath = None
        elif options.input_folder:
            svginputpath = Path(options.input_folder).resolve()
        else:
            # No input_folder and no explicit frames
            svginputpath = None

        svgoutputfolder = Path(options.output_path).resolve()

        # Force correct extension in the filename
        animation_file_name = os.path.basename(options.output_filename)
        animation_file_name = change_extension_to_fbfsvg(animation_file_name)
        options.output_filename = animation_file_name

        svgoutputpath = os.path.join(svgoutputfolder, options.output_filename)

        # Validate input path (only if using folder scanning mode)
        # Why: Generation cards with explicit frames don't need input_folder validation
        if svginputpath is not None:
            if not svginputpath.exists():
                raise OSError(f"Input path not found: {svginputpath}")
            if not os.access(svginputpath, os.R_OK):
                raise OSError(f"Cannot read input path: {svginputpath}")

        # Create output directory if needed
        svgoutputfolder.mkdir(parents=True, exist_ok=True)

        # Validate output path
        if not os.access(svgoutputfolder, os.W_OK):
            raise OSError(f"Cannot write to output path: {svgoutputfolder}")

        # Check if output file already exists
        if os.path.exists(svgoutputpath):
            backup_path = svgoutputpath + ".bak"
            os.rename(svgoutputpath, backup_path)
            add2log(f"Backed up existing output file to {backup_path}")

        # Find and validate input files
        # Priority: explicit frames from YAML config > folder scanning
        # Why: Generation cards specify exact frames, bypassing folder discovery
        unsorted_input_svg_paths = []
        skipped_animations = []

        # Check if we have an explicit frame list from generation card YAML
        if hasattr(options, "explicit_frames") and options.explicit_frames is not None:
            # Use explicit frame list from YAML config (generation card mode)
            # Why: Generation cards pre-specify frames with dependency
            # resolution
            ppp(f"📋 Using {len(options.explicit_frames)} frames from generation card")
            unsorted_input_svg_paths = [str(path) for path in options.explicit_frames]
        else:
            # Fall back to folder scanning (traditional mode)
            # Why: No explicit frames specified, discover all SVG files
            # in folder
            if svginputpath is None:
                raise ValueError("No input folder specified and no explicit frames provided in YAML config")
            for entry in svginputpath.iterdir():
                if entry.is_file():
                    filepath = str(entry)
                    if filepath.lower().endswith(
                        (
                            ".svg",
                            ".svgz",
                        )
                    ) and not os.path.basename(filepath).startswith("~"):
                        try:
                            # Validate each SVG file
                            with open(filepath, "rb") as f:
                                header = f.read(5)
                                if header.startswith(b"<?xml") or header.startswith(b"<svg "):
                                    # Check for incompatible SVG content
                                    # Why: FBF.SVG is for static frame-by-frame
                                    # animations. SMIL animations, JavaScript,
                                    # nested SVG, and multimedia are incompatible
                                    try:
                                        # Check for SMIL animations
                                        if contains_smil_animations(filepath):
                                            skipped_animations.append(
                                                (
                                                    os.path.basename(filepath),
                                                    "SMIL animation",
                                                )
                                            )
                                            add2log(f"Skipping frame with SMIL animation: {os.path.basename(filepath)}")
                                        # Check for JavaScript (with exceptions
                                        # for polyfills)
                                        elif contains_javascript(filepath, exceptions=JAVASCRIPT_EXCEPTIONS):
                                            skipped_animations.append(
                                                (
                                                    os.path.basename(filepath),
                                                    "JavaScript/scripting",
                                                )
                                            )
                                            add2log(f"Skipping frame with JavaScript: {os.path.basename(filepath)}")
                                        # Check for nested SVG elements
                                        elif contains_nested_svg(filepath):
                                            skipped_animations.append(
                                                (
                                                    os.path.basename(filepath),
                                                    "nested SVG",
                                                )
                                            )
                                            add2log(f"Skipping frame with nested SVG: {os.path.basename(filepath)}")
                                        # Check for multimedia elements
                                        elif contains_media_elements(filepath):
                                            skipped_animations.append(
                                                (
                                                    os.path.basename(filepath),
                                                    "multimedia",
                                                )
                                            )
                                            add2log(f"Skipping frame with multimedia elements: {os.path.basename(filepath)}")
                                        else:
                                            # File passed all filters
                                            unsorted_input_svg_paths.append(str(entry))
                                    except OSError:
                                        # If we can't read for filtering checks, include
                                        # it anyway
                                        unsorted_input_svg_paths.append(str(entry))
                                else:
                                    add2log(f"WARNING: Skipping invalid SVG file: {filepath}")
                        except OSError as e:
                            add2log(f"WARNING: Cannot read file {filepath}: {str(e)}")

            # Report filtering summary
            if skipped_animations:
                ppp(f"\n⏭️  Skipped {len(skipped_animations)} incompatible frame(s):")
                for filename, reason in skipped_animations:
                    ppp(f"     - {filename} ({reason})")
                ppp("")

        if not unsorted_input_svg_paths:
            # Provide appropriate error message based on input mode
            if svginputpath is not None:
                raise ValueError(f"No valid SVG files found in {svginputpath}")
            else:
                raise ValueError("No valid SVG files found in explicit frames list")

        sorted_input_svg_paths = sort_input_paths(unsorted_input_svg_paths, True)

        # DEBUG: Print sorted file list
        ppp("[DEBUG] svg2fbf sorted input files:")
        for i, path in enumerate(sorted_input_svg_paths):
            ppp(f"  Frame {i + 1}: {os.path.basename(path)}")

        total_number_of_frames = len(sorted_input_svg_paths)

        # we do not put the number of digits according to the max
        # frames allowed, but according to the real number of files
        # found in the folder. So we can be able to pinpoint the
        # frames from the ids even when only a partial number of
        # frames is processed.
        # FBF.SVG specification requires exactly 5 digits after FRAME
        # (FRAME00001, FRAME00002, etc.)
        # Code uses "FRAME0" prefix + 4 digits = FRAME00001
        number_of_digits = 4

        if options.quiet_mode is False:
            ppp()
            ppp(" ╔" + "═" * 58 + "╗ ")
            ppp(" ║" + " " * 58 + "║ ")
            ppp(" ║              ✅ IMPORT COMPLETE - READY TO PROCESS            ║ ")
            ppp(" ║" + " " * 58 + "║ ")
            ppp(" ╚" + "═" * 58 + "╝ ")
            ppp()
            # Show import results and configuration
            frames_text = f"Frames imported: {total_number_of_frames}"
            ppp(f" {frames_text}")
            ppp(" All frames validated: ✅ Pass")
            ppp()
            ppp(" Configuration:")
            ppp(f"   Animation Type       : {options.animation_type}")
            ppp(f"   Frame Rate           : {options.fps} fps")
            ppp(f"   Frame Duration       : {round(frame_duration, 4)} seconds")
            ppp(f"   Max Frames           : {options.max_frames}")
            ppp(f"   Backdrop             : {options.backdrop}")
            ppp(f"   Play On Click        : {options.play_on_click}")
            ppp(f"   Precision            : {options.digits} significant digits")
            ppp(f"   CPoints Precision    : {options.cdigits} significant digits")
            ppp(f"   Keep XML Space       : {options.keep_xml_space_attribute}")
            ppp(f"   Input Folder         : {options.input_folder}")
            ppp(f"   Output Path          : {options.output_path}")
            ppp(f"   Output File          : {options.output_filename}")
            ppp()
            ppp(" Generating FBF.SVG animation...")
            ppp()

        if options.max_frames is not None:
            if total_number_of_frames > int(options.max_frames):
                ppp(f"Processing only the first {options.max_frames} frames.")
            max_frame_num = int(options.max_frames)
        else:
            max_frame_num = total_number_of_frames

        # Build comprehensive metadata dictionary for FBF output
        # Why: Provide rich metadata in FBF files for cataloging and discovery
        metadata_dict = {}

        # User-specified metadata (from CLI/YAML)
        # Why: Preserve author-provided metadata fields
        if hasattr(options, "title") and options.title:
            metadata_dict["title"] = options.title
        if hasattr(options, "episode_number") and options.episode_number:
            metadata_dict["episodeNumber"] = options.episode_number
        if hasattr(options, "episode_title") and options.episode_title:
            metadata_dict["episodeTitle"] = options.episode_title
        if hasattr(options, "creators") and options.creators:
            metadata_dict["creators"] = options.creators
        if hasattr(options, "original_creators") and options.original_creators:
            metadata_dict["originalCreators"] = options.original_creators
        if hasattr(options, "copyrights") and options.copyrights:
            metadata_dict["copyrights"] = options.copyrights
        if hasattr(options, "website") and options.website:
            metadata_dict["website"] = options.website
        if hasattr(options, "language") and options.language:
            metadata_dict["language"] = options.language
        if hasattr(options, "original_language") and options.original_language:
            metadata_dict["originalLanguage"] = options.original_language
        if hasattr(options, "keywords") and options.keywords:
            metadata_dict["keywords"] = options.keywords
        if hasattr(options, "description") and options.description:
            metadata_dict["description"] = options.description
        if hasattr(options, "rights") and options.rights:
            metadata_dict["rights"] = options.rights
        if hasattr(options, "source") and options.source:
            metadata_dict["source"] = options.source

        # Auto-inferred animation properties
        # Why: Document animation characteristics for proper playback
        metadata_dict["frameCount"] = max_frame_num  # Number of frames to process
        metadata_dict["fps"] = options.fps  # Frames per second
        metadata_dict["duration"] = round(max_frame_num / options.fps, 3)  # Total duration in seconds
        metadata_dict["playbackMode"] = options.animation_type  # Animation mode (loop, once, pingpong, etc.)

        # Generator information
        # Why: Track tool version for compatibility and debugging
        metadata_dict["generator"] = "svg2fbf"
        metadata_dict["generatorVersion"] = SEMVERSION
        metadata_dict["generatedDate"] = datetime.now(timezone.utc).isoformat()
        metadata_dict["formatVersion"] = "1.0"
        metadata_dict["precisionDigits"] = options.digits
        metadata_dict["precisionCDigits"] = options.cdigits

        # Content features detection
        # Why: Identify special features that require specific renderer
        # capabilities
        features = infer_content_features(sorted_input_svg_paths[0:max_frame_num])
        metadata_dict["useMeshGradient"] = features["useMeshGradient"]
        metadata_dict["useEmbeddedImages"] = features["useEmbeddedImages"]
        metadata_dict["useCssClasses"] = features["useCssClasses"]
        metadata_dict["useExternalFonts"] = features["useExternalFonts"]
        metadata_dict["useExternalMedia"] = features["useExternalMedia"]

        # Additional features
        # Why: Document special FBF features and options used
        # hasBackdropImage: true only if user provided external backdrop image
        # file via --backdrop flag
        metadata_dict["hasBackdropImage"] = options.backdrop is not None and options.backdrop != "None"
        metadata_dict["hasInteractivity"] = options.play_on_click
        metadata_dict["interactivityType"] = "click_to_start" if options.play_on_click else "none"
        metadata_dict["keepXmlSpace"] = options.keep_xml_space_attribute
        metadata_dict["sourceFramesPath"] = str(options.input_folder) if options.input_folder else None

        # Note: Canvas dimensions (width, height, viewBox) will be added after
        # first frame is processed because they depend on the first frame's
        # viewBox which is only known after loading it

        # NINE STEPS TO ADD A NEW FRAME TO OUR SVG ANIMATION
        # 1 - rename all ids adding "_FBF" + current svg frame number
        # 2 - check if PATH and IMAGE elements are already present in the
        #     output defs node
        # 3 - replace each of those redundant PATH and IMAGE elements with an
        #     use element referencing those defs
        # 4 - change all the svg references from the redundant id to the id of
        #     the already existing global defs elements
        # 5 - move all the new non redundant defs elements in the output defs
        #     node
        # 6 - move all non defs elements in the output defs node under a NEW
        #     group with id="FRAME0"+frame_num
        # 7 - setup the 'animation_backdrop' group with a background rectangle
        #     (or image) with the same size of the frames
        # 8 - setup the 'animation_stage' group, with the 'animated_group'
        #     containing the 'proskenion' use element
        # 9 - setup the 'proskenion' use element with the 'animate' attribute
        #     and all frames ids as href references

        frame_num = ""
        frames_sequence_ids = []

        for index, svg in enumerate(sorted_input_svg_paths[0:max_frame_num]):
            # update progress bar
            progress_bar(count=index, total=max_frame_num)

            current_filepath = svg
            input_doc = load_svg(svg, options)
            input_svg = input_doc.documentElement

            # reset the current global xml_input_svg
            xml_input_svg = input_svg

            # merge defs
            merge_all_defs_into_one(input_doc, options)

            # apply stylesheet rules to elements by tag (if any)
            if style_rules_for_elements is not None:
                if len(style_rules_for_elements) > 0:
                    applyStyleRulesToElements(style_rules_for_elements)

            # reset the list of flagged nodes
            input_nodes_flagged_as_not_to_move = []

            # getting the viewbox of the first frame
            # (the entire animation will use that)
            if index == 0:
                # set the output viewBox values based on first frame
                (vbXdoc, vbYdoc, vbWdoc, vbHdoc, wdoc, hdoc) = getViewBox(input_svg, options)
                # CRITICAL: Must preserve first frame's viewBox offset
                # (X, Y coordinates)
                # The first frame establishes the canonical coordinate system
                # for the entire animation
                output_vbstring = f"{vbXdoc} {vbYdoc} {vbWdoc} {vbHdoc}"
                # output_vbstring = "0 0 %s %s" % (vbWdoc, vbHdoc)
                # BUG: This was zeroing the viewBox offset!
                # ppp("_----output_vbstring---- "+output_vbstring)

                # Add canvas dimensions to metadata
                # (now that we have first frame viewBox)
                # Why: Document the animation canvas size for proper rendering
                metadata_dict["width"] = "100%"  # Canvas width (responsive)
                metadata_dict["height"] = "100%"  # Canvas height (responsive)
                metadata_dict["viewBox"] = output_vbstring  # ViewBox coordinates
                metadata_dict["firstFrameWidth"] = wdoc  # Original first frame width
                metadata_dict["firstFrameHeight"] = hdoc  # Original first frame height

                # we get the empty template and make it the output doc
                # Why: Pass metadata_dict to embed RDF/XML metadata in the FBF document
                xml_output_doc = xml.dom.minidom.parseString(
                    get_empty_document(
                        vbWdoc,
                        vbHdoc,
                        "100%",
                        "100%",
                        options.no_keep_ratio,
                        metadata_dict,
                    )
                )

                # we find the documentElement (the 'svg' element just below the root)
                # and reference it as a global called xml_output_svg
                xml_output_svg = xml_output_doc.documentElement

                # we check if the namespace of the documentElement is right
                # otherwise we exit the script
                if xml_output_svg.namespaceURI != NS["SVG"]:
                    ppp("ERROR: namespaceURI of the default empty document is not SVG " + xml_output_svg.namespaceURI)
                    sys.exit()
                xml_output_defs = xml_output_doc.getElementsByTagName("defs")[0]
                xml_output_shared = ElementByIdAndTag("SHARED_DEFINITIONS", "g", xml_output_defs)
                elementsInputHashDict = {}
                elementsOutputHashDict = {}

            # get fill, stroke, etc. attribs from the svg element in case someone
            # put those there by error. We will fix them later when we build
            # the frame group.
            svg_fill = input_svg.getAttribute("fill")
            svg_fillrule = input_svg.getAttribute("fill-rule")
            svg_fillopacity = input_svg.getAttribute("fill-opacity")
            svg_stroke = input_svg.getAttribute("stroke")
            svg_strokeopacity = input_svg.getAttribute("stroke-opacity")
            svg_strokewidth = input_svg.getAttribute("stroke-width")
            svg_strokelinecap = input_svg.getAttribute("stroke-linecap")
            svg_strokelinejoin = input_svg.getAttribute("stroke-linejoin")
            svg_strokedasharray = input_svg.getAttribute("stroke-dasharray")
            svg_strokedashoffset = input_svg.getAttribute("stroke-dashoffset")
            svg_strokemiterlimit = input_svg.getAttribute("stroke-miterlimit")
            svg_viewbox = input_svg.getAttribute("viewBox")

            # STEP 1
            # we rename all ids adding "_FBF" + current svg frame number
            #
            postfix = paddedNum(index + 1, number_of_digits)
            renaming_all_ids_with_frame_number_postfix(input_svg, "", options, "_FBF0" + postfix)

            frame_num = postfix

            ppp(f"Processing frame n.{frame_num} from file: {current_filepath}")

            # we store the frame id in the sequence list
            frames_sequence_ids.append("#FRAME0" + frame_num)

            # STEP 2 & 3 & 4
            # check if the input defs elements are already present in the
            # output defs node and replace each of those elements with
            # an use element referencing to the matching output defs element
            #

            # create/update an elements HASH dictionary for the OUTPUT doc defs
            if index == 0:
                elementsOutputHashDict = generateHashKeyDictionary(xml_output_defs)

            # create a elements HASH Dictionary for this INPUT svg frame
            elementsInputHashDict = generateHashKeyDictionary(input_svg)

            # create a new inputReferencingElementDict for this frame
            inputReferencingElementsDict = findReferencedElements(input_svg)

            # remove duplicates from input (call this only after findReferencedElements)
            remove_duplicates_elements(input_svg, elementsInputHashDict, inputReferencingElementsDict)

            # Shallow reuse for non renderable elements.
            # Non renderable elements must not be replaced by use,
            # only their referring nodes have to be redirected.
            # This function does not touch deeply nested elements.
            for elem_tag in [
                "symbol",
                "pattern",
                "filter",
                "clipPath",
                "meshgradient",
                "mesh",
                "linearGradient",
                "radialGradient",
            ]:
                reuse_elements_if_they_are_already_in_output_defs(
                    input_svg,
                    elem_tag,
                    inputReferencingElementsDict,
                    elementsOutputHashDict,
                )

            # Deep reuse (acts even on nested elements)
            for elem_tag in ["path", "polyline", "polygon", "image", "text"]:
                deep_reuse_elem_if_they_are_already_in_output_defs(
                    input_svg,
                    options,
                    frame_num,
                    inputReferencingElementsDict,
                    elem_tag,
                )

            # STEP 5
            # add all the new defs elements in the output defs node
            # and rename the id with "_FBFAll"
            move_all_input_defs_elements_to_the_output_defs(
                input_svg,
                options,
                frame_num,
                inputReferencingElementsDict,
                elementsOutputHashDict,
            )

            # STEP 6
            # move all non defs elements (both normal and use) in the output defs
            # node under a NEW group with id="FRAME0"+frame_num
            move_all_non_defs_input_elements_as_frames_to_the_output_defs(
                input_svg,
                options,
                frame_num,
                inputReferencingElementsDict,
                elementsOutputHashDict,
            )

            # Get the frame group element
            current_frame_group = ElementByIdAndTag("FRAME0" + frame_num, "g", xml_output_doc)

            # SMART INHERITANCE: Apply presentation attributes from SVG root
            # to child elements that don't already have them
            #
            # Why we do this instead of setting on parent <g>:
            # 1. Parent attributes force CSS cascade inheritance to ALL children
            # 2. Children with stroke="none" would inherit stroke="#000" (unwanted)
            # 3. By setting on individual elements, we respect explicit child attributes
            #
            # This supports both:
            # - Legacy/optimized SVGs that rely on root-level inheritance ✅
            # - Modern CSS-based SVGs with explicit element styling ✅
            inherited_attrs = {}
            if svg_fill:
                inherited_attrs["fill"] = svg_fill
            if svg_fillrule:
                inherited_attrs["fill-rule"] = svg_fillrule
            if svg_fillopacity:
                inherited_attrs["fill-opacity"] = svg_fillopacity
            if svg_stroke:
                inherited_attrs["stroke"] = svg_stroke
            if svg_strokeopacity:
                inherited_attrs["stroke-opacity"] = svg_strokeopacity
            if svg_strokewidth:
                inherited_attrs["stroke-width"] = svg_strokewidth
            if svg_strokelinecap:
                inherited_attrs["stroke-linecap"] = svg_strokelinecap
            if svg_strokelinejoin:
                inherited_attrs["stroke-linejoin"] = svg_strokelinejoin
            if svg_strokedasharray:
                inherited_attrs["stroke-dasharray"] = svg_strokedasharray
            if svg_strokedashoffset:
                inherited_attrs["stroke-dashoffset"] = svg_strokedashoffset
            if svg_strokemiterlimit:
                inherited_attrs["stroke-miterlimit"] = svg_strokemiterlimit

            # Apply inherited attributes to children that lack them
            if inherited_attrs:
                apply_inherited_attributes_to_children(current_frame_group, inherited_attrs)
            if framerules is not None:
                for rule in framerules:
                    for propname in rule["properties"]:
                        if propname.isspace() is False and propname.strip() in CSS_TO_SVG_DICT:
                            corr_propname = CSS_TO_SVG_DICT.get(propname.strip())
                            if corr_propname.isspace() is False:
                                fix_svg_attribute(
                                    corr_propname,
                                    rule["properties"][propname],
                                    current_frame_group,
                                    add_warning=False,
                                )
            add_transform_to_match_input_frame_viewbox(input_svg, output_vbstring, current_frame_group)

            # MEMORY CLEANUP
            # free the memory to make space for the next frame
            inputReferencingElementsDict = None
            elementsInputHashDict = None
            framerules = None
            style_rules_for_elements = None
            input_svg = None
            # Why: Wrap unlink() in try-except to handle Python DOM bug with namespaced attributes
            # Bug: Python's xml.dom.minidom.unlink() fails with KeyError when unlinking elements
            # with namespaced attributes like xlink:href because it tries to delete 'href'
            # instead of the full namespaced name from _attrs dict
            try:
                input_doc.unlink()
            except KeyError:
                # If unlink() fails due to namespaced attribute bug, just skip it
                # The memory will be freed by Python's garbage collector anyway
                pass

        current_filepath = None

        # STEP 7
        # setup the 'animation_backdrop' group with a background rectangle
        # (or image) with the same size of the frames
        animation_backdrop = ElementByIdAndTag("ANIMATION_BACKDROP", "g", xml_output_doc)

        # STEP 7.1: Add backdrop image/SVG to STAGE_BACKGROUND if provided
        if options.backdrop is not None and options.backdrop != "None":
            backdrop_path = Path(options.backdrop)

            if not backdrop_path.exists():
                ppp(f"WARNING: Backdrop file not found: {backdrop_path}")
            else:
                stage_background = ElementByIdAndTag("STAGE_BACKGROUND", "g", xml_output_doc)

                if stage_background is not None:
                    backdrop_ext = backdrop_path.suffix.lower()

                    # Check if it's an SVG file
                    if backdrop_ext in [".svg", ".svgz"]:
                        # SVG backdrop: preprocess and wrap content in scaled group
                        try:
                            # Load and preprocess backdrop
                            backdrop_doc = load_svg(str(backdrop_path), options)
                            backdrop_root = backdrop_doc.documentElement

                            # Wrap backdrop content in transform group
                            # (modifies in-place)
                            target_viewbox = (vbXdoc, vbYdoc, vbWdoc, vbHdoc)
                            create_scaled_group_for_svg(backdrop_root, target_viewbox, align_mode="center")

                            # Now backdrop_root contains a wrapper group
                            # with transform
                            # Copy all children (including the wrapper group)
                            # to STAGE_BACKGROUND
                            for child in backdrop_root.childNodes:
                                if child.nodeType == child.ELEMENT_NODE:
                                    # The wrapper group will be copied here
                                    if child.nodeName == "g":
                                        imported_node = xml_output_doc.importNode(child, deep=True)
                                        imported_node.setAttribute("id", "BACKDROP_CONTENT")
                                        stage_background.appendChild(imported_node)
                                        break

                            ppp(f"✓ Added SVG backdrop from {backdrop_path.name}")

                            backdrop_doc.unlink()

                        except Exception as e:
                            ppp(f"WARNING: Failed to process SVG backdrop: {e}")

                    else:
                        # Bitmap backdrop: create <image> element in STAGE_BACKGROUND
                        try:
                            import base64

                            # Read and encode image as base64
                            with open(backdrop_path, "rb") as img_file:
                                img_data = img_file.read()
                                img_base64 = base64.b64encode(img_data).decode("utf-8")

                            # Determine MIME type
                            mime_types = {
                                ".png": "image/png",
                                ".jpg": "image/jpeg",
                                ".jpeg": "image/jpeg",
                                ".gif": "image/gif",
                                ".webp": "image/webp",
                                ".bmp": "image/bmp",
                            }
                            mime_type = mime_types.get(backdrop_ext, "image/png")

                            # Create <image> element
                            image_elem = xml_output_doc.createElement("image")
                            image_elem.setAttribute("id", "BACKDROP_IMAGE")
                            image_elem.setAttribute("x", str(vbXdoc))
                            image_elem.setAttribute("y", str(vbYdoc))
                            image_elem.setAttribute("width", str(vbWdoc))
                            image_elem.setAttribute("height", str(vbHdoc))
                            image_elem.setAttribute("href", f"data:{mime_type};base64,{img_base64}")
                            image_elem.setAttribute("preserveAspectRatio", "xMidYMid slice")

                            stage_background.appendChild(image_elem)
                            ppp(f"✓ Added bitmap backdrop from {backdrop_path.name}")

                        except Exception as e:
                            ppp(f"WARNING: Failed to process bitmap backdrop: {e}")

        # STEP 8
        # setup the 'animation_stage' group, with the 'animated_group'
        # containing the 'proskenion' use element
        animation_stage = ElementByIdAndTag("ANIMATION_STAGE", "g", xml_output_doc)
        # if animation_stage is not None:
        # animation_stage.setAttribute("width", str(vbWdoc) + "px")
        # 3animation_stage.setAttribute("height", str(vbHdoc) + "px")
        # animation_stage.setAttribute("fill", "rgb(255, 255, 255)")

        # STEP 9
        # setup the 'proskenion' use element with the 'animate' attribute and
        # all frames ids as href references

        if frames_sequence_ids is None:
            ppp("ERROR : frame sequence must not be null. Exiting.")
            sys.exit(1)
        elif len(frames_sequence_ids) < 2:
            ppp("ERROR : animation sequence must be at least 2 frames. Exiting.")
            sys.exit(1)

        frames = ";".join(frames_sequence_ids)
        framesReversed = ";".join(reversed(frames_sequence_ids))
        framesPingPong = ";".join(frames_sequence_ids + list(reversed(frames_sequence_ids))[1:])
        framesPingPongReversed = ";".join(list(reversed(frames_sequence_ids)) + frames_sequence_ids[1:])

        proskenion = ElementByIdAndTag("PROSKENION", "use", xml_output_doc)
        if proskenion is None:
            ppp("ERROR: cannot find the proskenion use element. Exiting.")
            sys.exit(1)

        animElem = proskenion.getElementsByTagName("animate")[0]

        if animElem is None:
            ppp("ERROR: cannot find the animation node of the proskenion use element. Exiting.")
            sys.exit(1)

        # proskenion.setAttribute("width", str(vbWdoc) + "px")
        # proskenion.setAttribute("height", str(vbHdoc) + "px")
        proskenion.setAttributeNS(NS["XLINK"], "href", frames_sequence_ids[0])
        animElem.setAttribute("begin", "0s")

        # set animation type
        #
        # possible values:
        # once : start to end then stop
        # once_reversed : end to start then stop
        # loop : start to end, then start to end again, forever
        # loop_reversed : end to start, then end to start again, forever
        # pingpong_once : start to end, then end to start then stop
        # pingpong_loop : start to end, then end to start, forever
        # pingpong_once_reversed : end to start, then start to end then stop
        # pingpong_loop_reversed : end to start, then start to end, forever
        #
        if options.animation_type == "once":
            animElem.setAttribute("repeatCount", "1")
            animElem.setAttribute("values", frames)
        if options.animation_type == "once_reversed":
            animElem.setAttribute("repeatCount", "1")
            animElem.setAttribute("values", framesReversed)
        elif options.animation_type == "loop":
            animElem.setAttribute("repeatCount", "indefinite")
            animElem.setAttribute("values", frames)
        elif options.animation_type == "loop_reversed":
            animElem.setAttribute("repeatCount", "indefinite")
            animElem.setAttribute("values", framesReversed)
        elif options.animation_type == "pingpong_once":
            animElem.setAttribute("repeatCount", "1")
            animElem.setAttribute("values", framesPingPong)
        elif options.animation_type == "pingpong_loop":
            animElem.setAttribute("repeatCount", "indefinite")
            animElem.setAttribute("values", framesPingPong)
        elif options.animation_type == "pingpong_once_reversed":
            animElem.setAttribute("repeatCount", "1")
            animElem.setAttribute("values", framesPingPongReversed)
        elif options.animation_type == "pingpong_loop_reversed":
            animElem.setAttribute("repeatCount", "indefinite")
            animElem.setAttribute("values", framesPingPongReversed)
        else:
            # default is loop mode
            animElem.setAttribute("repeatCount", "1")
            animElem.setAttribute("values", frames)

        animElem.setAttribute("dur", f"{round(frame_duration * max_frame_num, 4)}s")
        if options.play_on_click is True:
            animElem.setAttribute("begin", "click")

        # FINALLY we set the viewBox of the generated FBFSVG animation
        xml_output_svg.setAttribute("viewBox", output_vbstring)

        # Final cleaning and optimization, also
        # purging the resulting OUTPUT SVG from duplicates
        move_all_non_renderable_elements_to_defs_shared(xml_output_doc)

        outputReferencingElementsDict = findReferencedElements(xml_output_svg)
        elementsOutputHashDict = generateHashKeyDictionary(xml_output_svg)
        remove_duplicates_elements(xml_output_svg, elementsOutputHashDict, outputReferencingElementsDict)
        Minor_Optimize_SVG_Helper(xml_output_doc, options)

        # let's format the svg to make it prettier
        # TODO: add option to minify
        pretty_serialized_output_xml = serialize_svg_doc_to_string(xml_output_doc, options)

        # Inject mesh gradient polyfill (conditional - only if meshgradient
        # elements are present)
        # Why: Ensures cross-browser mesh gradient support (only permitted
        # JavaScript in FBF)
        # Why: Saves ~16KB when no mesh gradients are used
        pretty_serialized_output_xml = inject_mesh_gradient_polyfill(pretty_serialized_output_xml)

        # prepare output file path
        output_filepath = os.path.join(options.output_path, options.output_filename)

        # update progress bar (final 100%)
        # Why: Show completion status to user (only if not quiet)
        if options.quiet_mode is False:
            progress_bar(count=total_number_of_frames, total=max_frame_num)
            ppp(f"\nSaving file... {output_filepath}")

        # Save output with proper error handling
        # Why: ALWAYS save the file, regardless of quiet mode (this was a critical bug!)
        temp_output = output_filepath + ".tmp"
        try:
            with open(temp_output, "w", encoding="utf-8") as f:
                f.write(pretty_serialized_output_xml)
            os.replace(temp_output, output_filepath)
        except OSError as e:
            if os.path.exists(temp_output):
                os.unlink(temp_output)
            raise OSError(f"Failed to write output file: {str(e)}") from e

        # Success!
        # Why: Print success message only if not quiet
        if not options.quiet_mode:
            ppp("\nFBFSVG ANIMATION CREATED SUCCESSFULLY.\n")

        # Open in browser (unless --no-browser flag is set)
        # Why: Provide immediate visual feedback of the generated animation
        if not options.no_browser:
            open_in_browser(output_filepath)

    except Exception as e:
        add2log(f"ERROR: {str(e)}")
        add2log("\nFull traceback:")
        add2log(traceback.format_exc())
        print_log_and_exit(1)
    finally:
        # Cleanup temporary files
        if "temp_output" in locals():
            if os.path.exists(temp_output):
                try:
                    os.unlink(temp_output)
                except OSError:
                    pass

    return


ALL_UNITS = [
    "em",
    "ex",
    "%",
    "px",
    "cm",
    "mm",
    "in",
    "pt",
    "pc",
    "ch",
    "rem",
    "vh",
    "vw",
    "vmin",
    "vmax",
]

SVG_UNITS = ["%", "px", "pt", "pc", "em", "ex", "cm", "mm", "in"]

MATH_CHARS = [
    ".",
    ",",
    ":",
    "-",
    "+",
    "~",
    "#",
    "!",
    "^",
    "&",
    "*",
    "/",
    "|",
    ";",
    ">",
    "<",
    "?",
    "(",
    ")",
    "{",
    "}",
    "[",
    "]",
    "@",
]


def is_in_valid_units(in_value):
    unit_str = extract_str(in_value)
    if unit_str in SVG_UNITS:
        if extract_nbr(in_value) != "":
            return True
    else:
        return False


def extract_nbr(input_str):
    if input_str is None or input_str == "" or input_str.strip().isspace():
        return "0"
    input_str = input_str.strip()
    out_numbers = [float(s) for s in re.findall(r"[0-9]+\.[0-9]+", input_str)]
    if out_numbers:
        return str(out_numbers[0])
    else:
        return "0"


def extract_str(input_str):
    if input_str is None or input_str == "" or input_str.strip().isspace():
        return ""
    input_str = input_str.strip()
    out_string = ""
    for ele in input_str:
        if ele.isdigit() is False:
            if ele not in MATH_CHARS and ele.isspace() is False:
                out_string += ele
    return out_string


def get_attribute_value_in_valid_units(attr_name, attr_value):
    if attr_value != "" and attr_value.isspace() is False:
        if attr_name == "width":
            if is_in_valid_units(attr_value) is False:
                attr_value = extract_nbr(attr_value) + "px"
            else:
                return attr_value
        elif attr_name == "height":
            if is_in_valid_units(attr_value) is False:
                attr_value = extract_nbr(attr_value) + "px"
            else:
                return attr_value
        elif attr_name == "stroke-width":
            if is_in_valid_units(attr_value) is False:
                attr_value = extract_nbr(attr_value) + "px"
            else:
                return attr_value
        elif attr_name == "stroke-miterlimit":
            if is_in_valid_units(attr_value) is False:
                attr_value = extract_nbr(attr_value)
            else:
                return attr_value
        elif attr_name == "stroke-dashoffset":
            if is_in_valid_units(attr_value) is False:
                attr_value = extract_nbr(attr_value)
            else:
                return attr_value
        else:
            return attr_value
    else:
        return attr_value


def isNon0Val(val):
    global current_filepath
    try:
        if val is not None and val.isspace() is False and float(val) > 0:
            return True
        else:
            return False
    except ValueError:
        add2log(f"ERROR: viewBox value of file {current_filepath} is invalid!!")
        return False


def add_transform_to_match_input_frame_viewbox(docElement, output_vbstring, current_frame_group):
    global current_filepath
    if output_vbstring is None or output_vbstring == "" or output_vbstring.isspace() is True:
        return
    output_vbSep = RE_COMMA_WSP.split(output_vbstring)

    vbX_original = 0.0
    vbY_original = 0.0
    isvalid = False
    # parse viewBox attribute
    if docElement.hasAttribute("viewBox") is False:
        isvalid = False
    else:
        vbSep = RE_COMMA_WSP.split(docElement.getAttribute("viewBox"))
        if len(vbSep) == 4 and vbSep[0] and vbSep[1] and vbSep[2] and vbSep[3]:
            if isNon0Val(vbSep[2]) and isNon0Val(vbSep[3]):
                try:
                    # if x or y are specified and non-zero then it is not ok
                    # to overwrite it
                    vbX = float(vbSep[0])
                    vbY = float(vbSep[1])
                    vbWidth = float(vbSep[2])
                    vbHeight = float(vbSep[3])
                    output_vbWidth = float(output_vbSep[2])
                    output_vbHeight = float(output_vbSep[3])
                    if vbX != 0 or vbY != 0:
                        vbX_original = vbX
                        # DO NOT zero the viewBox! First frame viewBox must
                        # never be modified! It is the canonical viewBox for
                        # the entire animation
                        vbY_original = vbY
                        # vbX = 0  # REMOVED: This was corrupting the first
                        #            frame's viewBox
                        # vbY = 0  # REMOVED: This was corrupting the first
                        #            frame's viewBox
                    isvalid = True
                # if the viewBox did not parse properly it is invalid and ok
                # to overwrite it
                except ValueError:
                    add2log(f"ERROR: viewBox of file {current_filepath} is invalid!!")
                    isvalid = False
                    pass

    if isvalid is True:
        tr = ConcatenatedSVGTransformations()
        if current_frame_group.hasAttribute("transform"):
            attr = current_frame_group.getAttribute("transform")
            tr = string2svgtransformations(str(attr))

        # Parse target (first frame) viewBox components
        output_vbX = float(output_vbSep[0])
        output_vbY = float(output_vbSep[1])
        output_vbWidth = float(output_vbSep[2])
        output_vbHeight = float(output_vbSep[3])

        # Calculate uniform scale factor (proportional contain fit)
        # Use minimum to ensure content fits inside BOTH width AND
        # height
        width_scale = float(output_vbWidth / vbWidth)
        height_scale = float(output_vbHeight / vbHeight)
        scale_factor = min(width_scale, height_scale)

        # IMPORTANT: Transform calculation follows the standard FBF algorithm
        # Algorithm pseudocode:
        #   STEP 1: Read viewBoxes
        #     x1, y1, w1, h1 = first_frame_viewBox
        #     x2, y2, w2, h2 = current_frame_viewBox
        #
        #   STEP 2: Compute uniform contain scale factor
        #     sx = w1 / w2
        #     sy = h1 / h2
        #     s = min(sx, sy)
        #
        #   STEP 3: Compute translation based on align_mode
        #     if align_mode == "top-left":
        #       tx = x1 - s * x2
        #       ty = y1 - s * y2
        #     elif align_mode == "center":
        #       c1x = x1 + w1 / 2.0
        #       c1y = y1 + h1 / 2.0
        #       c2x = x2 + w2 / 2.0
        #       c2y = y2 + h2 / 2.0
        #       tx = c1x - s * c2x
        #       ty = c1y - s * c2y
        #
        #   STEP 4: Build transform string
        #     transform = matrix(s, 0, 0, s, tx, ty)

        # Calculate translation values for transform based on selected
        # alignment mode
        # Transform composition: T(translate_x, translate_y) × S(s, s) ×
        # T(-vbX, -vbY)
        # Results in: matrix(s, 0, 0, s, translate_x - s*vbX,
        # translate_y - s*vbY)
        #
        # For top-left mode: want final tx = x1 - s*x2, so translate_x = x1
        # = output_vbX
        # For center mode: want final tx = c1x - s*c2x, so translate_x =
        # output_vbX + (w1/2 - s*w2/2)

        # Get alignment mode (default to "top-left" if not set)
        # Why: options may be None in test contexts, or align_mode may not
        # be set in older code
        # Validation: CLI parser enforces choices=["top-left", "center"],
        # YAML merge validates too
        align_mode = getattr(options, "align_mode", "top-left") if options else "top-left"

        if align_mode == "center":
            # Center alignment: align centers of both viewBoxes
            # From pseudocode: tx = (x1 + w1/2) - s*(x2 + w2/2) = x1 + w1/2
            # - s*x2 - s*w2/2
            # Rewrite as: tx = (x1 - s*x2) + (w1/2 - s*w2/2)
            # With transform T(translate_x, translate_y) × S(s) ×
            # T(-x2, -y2):
            # Result is: tx = translate_x - s*x2
            # We need: translate_x - s*x2 = x1 - s*x2 + (w1/2 - s*w2/2)
            # Therefore: translate_x = x1 + (w1/2 - s*w2/2)
            center_offset_x = output_vbWidth / 2.0 - scale_factor * vbWidth / 2.0
            center_offset_y = output_vbHeight / 2.0 - scale_factor * vbHeight / 2.0
            translate_x = output_vbX + center_offset_x
            translate_y = output_vbY + center_offset_y
        else:
            # Top-left alignment (default): align top-left corners
            # From pseudocode: tx = x1 - s*x2
            # With transform T(translate_x, translate_y) × S(s) × T(-x2, -y2):
            # Result is: tx = translate_x - s*x2
            # We need: translate_x - s*x2 = x1 - s*x2
            # Therefore: translate_x = x1
            translate_x = output_vbX
            translate_y = output_vbY

        # Build transform matrix in REVERSE order (right-to-left application)
        # Application sequence: T(translate_x, translate_y) × S(s, s) × T(-vbX, -vbY)
        # Result: matrix(s, 0, 0, s, translate_x - s*vbX, translate_y - s*vbY)
        tr = tr.translate(translate_x, translate_y)  # Added FIRST, applied LAST
        tr = tr.scale(scale_factor, scale_factor)  # Added SECOND, applied SECOND
        tr = tr.translate(0.0 - vbX_original, 0.0 - vbY_original)  # Added LAST, applied FIRST
        # scourLength
        # np.array(((values[0], values[2], values[4]),
        # (values[1], values[3], values[5]), (0, 0, 1)))
        # tr = tr.matrix(a, c, e, b, d, f)
        # matrix(1,0,0,1,tx,ty) a,d,b,e,c,f
        # a b c	a c e	0 2 4
        # translate: matrix([1,0,tx][0,1,ty][0,0,1])
        # d e f	b d f	1 3 5	a b  c  d e  f
        # 0 0 1	0 0 1	6 7 8	C-order	0,2,4,1,3,5,6,7,8
        # args = list(map(float, args))
        matrix_args = list(tr.m.flatten())
        a, b, c, d, e, f, g, h, i = matrix_args
        str_transform = f"matrix({a} {d} {b} {e} {c} {f})"  # (a, c, e, b, d, f)
        current_frame_group.setAttribute("transform", str_transform)


# TODO tr


def fix_svg_attribute(attr_name, attr_value, current_frame_group, add_warning=True):
    global current_filepath
    if attr_value != "":
        attr_value = get_attribute_value_in_valid_units(attr_name, attr_value)
        if add_warning is True:
            add2log(f"WARNING: the <svg> element of the file {current_filepath} has an invalid attribute ('{attr_name}'). The <svg> element doesn't accept fill=, stroke= etc.! Moving the attribute to the frame group as temporary fix.")
        current_frame_group.setAttribute(attr_name, attr_value)
        # if it is 'fill' we need to add a rectangle background to
        # the frame group to simulate the svg background color.
        if attr_name == "fill":
            bg_rect = xml_output_doc.createElementNS(NS["SVG"], "rect")
            bg_rect.setAttribute("width", "100%")
            bg_rect.setAttribute("height", "100%")
            bg_rect.setAttribute("fill", attr_value)
            current_frame_group.appendChild(bg_rect)
            current_frame_group.insertBefore(bg_rect, current_frame_group.firstChild)

    return


def apply_inherited_attributes_to_children(frame_group, inherited_attrs):
    """
    Apply inherited presentation attributes to child elements that don't
    already have them.

    This provides proper inheritance for legacy/optimized SVGs while respecting explicit
    attributes in CSS-based SVGs. Instead of setting attributes on the parent group
    (which forces inheritance via CSS cascade), we selectively apply them to individual
    child elements.

    Why this approach:
    - Legacy SVGs: Children without attributes get inherited values ✅
    - CSS-based SVGs: Children with explicit attributes keep them ✅
    - No unwanted CSS cascade forcing inheritance ✅

    Args:
        frame_group: The frame group <g> element
        inherited_attrs: Dict of {attr_name: attr_value} to potentially inherit
    """
    from xml.dom import Node

    # List of inheritable presentation attributes
    # Only include attributes that CSS cascade would inherit
    inheritable_attrs = [
        "fill",
        "fill-rule",
        "fill-opacity",
        "stroke",
        "stroke-opacity",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-miterlimit",
    ]

    # Traverse all descendant elements (recursive)
    for node in frame_group.getElementsByTagName("*"):
        if node.nodeType == Node.ELEMENT_NODE:
            # For each inheritable attribute
            for attr_name in inheritable_attrs:
                if attr_name in inherited_attrs and inherited_attrs[attr_name]:
                    # Only set if element doesn't already have this attribute
                    # This respects explicit attributes on elements
                    if not node.hasAttribute(attr_name):
                        node.setAttribute(attr_name, inherited_attrs[attr_name])

    return


def maybe_gziped_file(filename, mode="rb"):
    if os.path.splitext(filename)[1].lower() in (".svgz", ".gz"):
        import gzip

        add2log(f"WARNING: input file {current_filepath} is in compressed format. Extracting.")
        return gzip.GzipFile(filename, mode)
    return open(filename, mode)


def convert_text_to_paths_if_enabled(svg_content: bytes, filepath: str, options) -> bytes:
    """Convert text elements to paths using svg-text2path if --text2path flag is enabled.

    Args:
        svg_content: Raw SVG file content as bytes
        filepath: Path to the SVG file (for logging)
        options: Program options (checks text2path flag)

    Returns:
        Converted SVG content as bytes (or original if conversion disabled/unavailable)

    Raises:
        ImportError: If --text2path is used but svg-text2path is not installed
        ValueError: If --text2path-strict is set and conversion fails
    """
    if not getattr(options, "text2path", False):
        return svg_content

    # Try to import svg-text2path (optional dependency)
    try:
        from svg_text2path import Text2PathConverter
    except ImportError as e:
        raise ImportError("svg-text2path is required for --text2path flag. Install with: uv tool install svg2fbf[text2path]") from e

    # Decode bytes to string for conversion
    try:
        svg_string = svg_content.decode("utf-8")
    except UnicodeDecodeError:
        svg_string = svg_content.decode("utf-8", errors="replace")
        add2log(f"WARNING: Non-UTF8 characters in {filepath}, some may be lost")

    # Count text elements before conversion
    import re

    text_pattern = re.compile(r"<(text|tspan|textPath)[\s>]", re.IGNORECASE)
    text_before = len(text_pattern.findall(svg_string))

    basename = os.path.basename(filepath)

    # Perform conversion
    try:
        converter = Text2PathConverter()
        output_svg = converter.convert_string(svg_string)
    except Exception as e:
        if getattr(options, "text2path_strict", False):
            raise ValueError(f"Text-to-path conversion failed for {basename}: {str(e)}")
        else:
            add2log(f"WARNING: Text-to-path conversion failed for {basename}: {str(e)}")
            return svg_content  # Return original if conversion fails in non-strict mode

    # Count text elements after conversion
    text_after = len(text_pattern.findall(output_svg))

    # Log results
    if text_before > 0:
        converted = text_before - text_after
        ppp(f"  [text2path] {basename}: converted {converted}/{text_before} text elements")

    # Verify no text elements remain (validation)
    if text_after > 0:
        if getattr(options, "text2path_strict", False):
            raise ValueError(f"{text_after} text element(s) could not be converted in {basename}")
        else:
            add2log(f"WARNING: {text_after} text element(s) could not be converted in {basename}")

    return output_svg.encode("utf-8")


def load_svg(filepath: str, options) -> xml.dom.minidom.Document:
    """Load and parse SVG file with error handling.

    Args:
        filepath: Path to SVG file
        options: Program options

    Returns:
        Parsed XML document

    Raises:
        OSError: If file cannot be read
        xml.parsers.expat.ExpatError: If XML is invalid
    """
    try:
        if not os.path.exists(filepath):
            raise OSError(f"File not found: {filepath}")

        with maybe_gziped_file(filepath, "rb") as f:
            try:
                in_string = f.read()
            except Exception as e:
                raise OSError(f"Failed to read file {filepath}: {str(e)}") from e

        # Convert text to paths if --text2path flag is enabled
        # Why: Must convert before XML parsing since svg-text2path works on strings
        try:
            in_string = convert_text_to_paths_if_enabled(in_string, filepath, options)
        except (ImportError, ValueError) as e:
            add2log(f"ERROR: {str(e)}")
            print_log_and_exit(1)

        try:
            doc = xml.dom.minidom.parseString(in_string)
        except xml.parsers.expat.ExpatError as e:
            raise xml.parsers.expat.ExpatError(f"Invalid XML in {filepath}: {str(e)}") from e
        except Exception as e:
            raise Exception(f"Failed to parse XML in {filepath}: {str(e)}") from e

        try:
            minifiedSvg = preprocess_svg_file(doc, options, filepath)
            return minifiedSvg
        except Exception as e:
            raise Exception(f"Failed to preprocess SVG {filepath}: {str(e)}") from e

    except Exception as e:
        add2log(f"ERROR: {str(e)}")
        print_log_and_exit(1)


# progress bar
# usage:
# 	for i in range(1,101):
# 		progress_bar(count=i,total=100)
# 		time.sleep(0.01) # place you job here
#
def progress_bar(
    count: int,
    total: int,
    suffix: str = "percentage",
    size: int = 40,
    sides: str = "[]",
    full: str = "█",
    empty: str = "░",
    prefix: str = "Progress:",
    completed: bool = False,
) -> None:
    """Display a progress bar.

    Args:
        count: Current progress value
        total: Total value representing 100%
        suffix: Display mode - "percentage" or "counter"
        size: Width of progress bar
        sides: Characters for bar edges
        full: Character for completed portion
        empty: Character for remaining portion
        prefix: Text to show before bar
        completed: Whether progress is complete

    Raises:
        ValueError: If total < 2 or count > total or invalid suffix
    """
    try:
        # Input validation
        if total < 2:
            raise ValueError("Total number of elements must be at least 2")
        if total == 0:
            raise ValueError("Total cannot be zero")
        if count > total:
            raise ValueError("Count must not be higher than total")
        if suffix not in ("percentage", "counter"):
            raise ValueError("Suffix must be 'percentage' or 'counter'")

        # Calculate progress
        try:
            x = int(size * count / total)
            percent = f"{int((count / total) * 100)}%"
        except ZeroDivisionError as e:
            raise ValueError("Cannot divide by zero total") from e

        # Format counter
        try:
            counter = f"{str(count).rjust(len(str(total)))}/{total}"
        except Exception as e:
            raise ValueError(f"Failed to format counter: {str(e)}") from e

        # Build progress bar
        try:
            bar = f"\r{prefix}{sides[0]}{full * x}{empty * (size - x)}{sides[1]} "
            bar += percent if suffix == "percentage" else counter
        except Exception as e:
            raise ValueError(f"Failed to build progress bar: {str(e)}") from e

        # Write to stdout
        try:
            sys.stdout.write(bar)
            if count == total and not completed:
                sys.stdout.write(" Completed.\n\r")
                sys.stdout.flush()
        except OSError as e:
            raise OSError(f"Failed to write to stdout: {str(e)}") from e

    except Exception as e:
        add2log(f"ERROR: Progress bar failed: {str(e)}")
        # Don't exit on progress bar failure
        return


##############################################################
#   functions to compose the animation from the svg frames   #
##############################################################


# ensure that there is only one defs section in the svg document
def merge_all_defs_into_one(doc, options):
    if doc is None:
        ppp("ERROR: svg document empty. Exiting.")
        sys.exit(1)

    defs = doc.documentElement.getElementsByTagName("defs")

    if len(defs) == 0:
        # if there is no defs, we create a new <defs>
        # element in the input svg
        # We need the Document for this.
        maindefs = doc.createElementNS(NS["SVG"], "defs")
        doc.documentElement.appendChild(maindefs)

    if len(defs) == 1:
        maindefs = defs[0]

    if len(defs) > 1:
        maindefs = defs[0]
        # Move all xml childs from the other defs to the first defs
        elemsToMove = []
        for aDef in defs:
            if aDef.parentNode is not None:
                if aDef.parentNode is not doc.documentElement:
                    # this is needed to avoid trouble with nested defs
                    doc.documentElement.appendChild(aDef)
        for aDef in defs:
            if aDef is not maindefs:
                if aDef.hasChildNodes():
                    for child in aDef.childNodes:
                        elemsToMove.append(child)
        for elem in elemsToMove:
            maindefs.appendChild(elem)

        for aDef in defs:
            if aDef is not maindefs:
                if aDef.parentNode is not None:
                    aDef.parentNode.removeChild(aDef)
                    aDef.unlink()

    # move all non renderable elements to defs
    for tagtype in RETARGETABLE_ELEMENTS:
        elemsList = doc.documentElement.getElementsByTagName(tagtype)
        for nr_elem in elemsList:
            if nr_elem.parentNode is not maindefs:
                maindefs.appendChild(nr_elem)
    return


def move_all_non_renderable_elements_to_defs_shared(doc):
    global elementsOutputHashDict
    global ELEMENTS_TO_DISCARD
    global RETARGETABLE_ELEMENTS
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS

    if doc is not None:
        elemsToMove = []
        for elemType in RETARGETABLE_ELEMENTS:
            elemsList = doc.documentElement.getElementsByTagName(elemType)
            for nr_elem in elemsList:
                if nr_elem is not None and nr_elem.nodeType not in NODE_TYPES_TO_IGNORE:
                    if nr_elem.parentNode is not xml_output_shared:
                        doc.documentElement.appendChild(nr_elem)
                        elemsToMove.append(nr_elem)

        for node in elemsToMove:
            if node.parentNode is not xml_output_shared:
                xml_output_shared.appendChild(node)
                addElementToHashDict(elementsOutputHashDict, node)
    return


def renaming_all_ids_with_frame_number_postfix(input_svg, prefix, options, postfix):
    """
    Add frame number postfix to all ids
    """
    num = 0

    identifiedElements = findElementsWithId(input_svg)
    # This map contains maps the (original) ID to the nodes referencing it.
    # At the end of this function, it will no longer be valid and while we
    # could keep it up to date, it will complicate the code for no gain
    # (as we do not reuse the data structure beyond this function).
    referencedIDs = findReferencedElements(input_svg)

    # Make idList (list of idnames) sorted by reference count
    # descending, so the highest reference count is first.
    # First check that there's actually a defining element for the current ID name.
    # (Cyn: I've seen documents with #id references but no element with that ID!)
    idList = [(len(referencedIDs[rid]), rid) for rid in referencedIDs if rid in identifiedElements]
    idList.sort(reverse=True)
    idList = [rid for count, rid in idList]

    # Add unreferenced IDs to end of idList in arbitrary order
    idList.extend([rid for rid in identifiedElements if rid not in idList])
    # Ensure we do not reuse a protected ID by accident
    # 	protectedIDs = protected_ids(identifiedElements, options)
    # IDs that have been allocated and should not be remapped.
    consumedIDs = set()

    # List of IDs that need to be assigned a new ID.  The list is ordered
    # such that earlier entries will be assigned a shorter ID than those
    # later in the list.  IDs in this list *can* obtain an ID that is
    # longer than they already are.

    id_allocations = list(compute_id_lengths(len(idList) + 1))
    # Reverse so we can use it as a stack and still work from "shortest to
    # longest" ID.
    id_allocations.reverse()

    curIdNum = 1

    for old_id in idList:
        new_id = intToIDPostfix(curIdNum, prefix, postfix)

        # Skip ahead if the new ID has already been used or is protected.
        while new_id in consumedIDs:
            curIdNum += 1
            new_id = intToIDPostfix(curIdNum, prefix, postfix)

        # Now that we have found the first available ID, do the remap.
        num += renameID(old_id, new_id, identifiedElements, referencedIDs.get(old_id))
        curIdNum += 1

    return num


def move_all_non_defs_input_elements_as_frames_to_the_output_defs(input_svg, options, frame_num, referencingElementsDict, elementsHashDict):
    global elementsOutputHashDict
    global ELEMENTS_TO_DISCARD
    global SVG_ELEMENTS_TO_ALWAYS_MOVE
    global RETARGETABLE_ELEMENTS
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS

    # Move all new elements OUTSIDE the DEFS to the output xml defs.
    # Note: Elements outside the DEFS section, even if redundant, must be
    # moved to the FRAMES, because they were supposed to be visible.
    # This is why redundant elements outside the Defs must be
    # replaced by an "use" element. The 'use' element
    # must stay in place to hold the position in the svg view hierarchy.
    # Only the first element of its kind found among all the imported svg,
    # the "master element" we may call it, must be moved to the output def
    # as is, since it is going to be referenced and instanced by the other
    # elements in the FRAMES groups.
    nodesToMoveList = []

    # create a temporary list of the input nodes from the new frame.
    # we call this list 'nodesToMoveList'.

    for node in input_svg.childNodes:
        if node is not None and node.nodeType not in NODE_TYPES_TO_IGNORE:
            tag = findTag(node)
            if tag not in ELEMENTS_TO_DISCARD:
                nodesToMoveList.append(node)

    # Create a <g> element from scratch in the output defs to
    # use as our new FRAME.
    # We need the Document for this.
    group = xml_output_doc.createElementNS(NS["SVG"], "g")
    group.setAttribute("id", "FRAME0" + frame_num)
    # Include the group among the xml_output_defs children.
    xml_output_defs.appendChild(group)

    # check if any element in the nodesToMoveList needs to be
    # converted to an 'use' element because is redundant.
    for node in nodesToMoveList:
        if node is not None and node.nodeType not in NODE_TYPES_TO_IGNORE and node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
            nodesInDict = check_if_element_already_exists_in_hash_dict(node, xml_output_defs, elementsOutputHashDict)
            if nodesInDict is not None and len(nodesInDict) > 0:
                # an identical element is already present in the defs
                # we need to preserve frame elements, so we convert it to 'use'
                (master_node_id, master_node) = nodesInDict[0]
                new_element_id = getElementId(node)
                if new_element_id == master_node_id:
                    input_nodes_flagged_as_not_to_move.append(new_element_id)
                    continue
                if node.nodeName in NON_REUSABLE_ELEMENTS:
                    # This element cannot be converted to an USE element
                    # Just retarget all his referencing nodes to the master
                    # and add its ID to the list of input_nodes_to_discard
                    retarget_redundant_element_referencing_nodes_to_master(node, master_node_id, new_element_id, referencingElementsDict)
                    if node.hasChildNodes() is False and node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
                        input_nodes_flagged_as_not_to_move.append(new_element_id)
                else:
                    # This element can be converted to USE element
                    convert_redundant_element_to_use_element(node, master_node_id, new_element_id, referencingElementsDict)

    # else we do nothing, because the element must be new.

    # now the all the redundant elements in the nodesToMoveList have
    # been converted in 'use' elements referencing the elements in the
    # output defs. We can add the whole nodesToMoveList to the new FRAME
    # group now, respecting the order.
    for node in nodesToMoveList:
        move_elem_to_output_svg_defs(node, elementsHashDict, group)

    return


def move_elem_to_output_svg_defs(node, elementsHashDict, frame_group=None):
    global elementsOutputHashDict
    global ELEMENTS_TO_DISCARD
    global RETARGETABLE_ELEMENTS
    global SVG_ELEMENTS_TO_ALWAYS_MOVE
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS
    global output_duplicates_list

    if node is not None and node.nodeType not in NODE_TYPES_TO_IGNORE:
        if node.hasAttribute("id") or node.getAttribute("id") != "":
            nodeid = node.getAttribute("id")
            if nodeid in input_nodes_flagged_as_not_to_move and node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
                return
            imported_node = xml_output_doc.importNode(node, True)
            if node.nodeName in RETARGETABLE_ELEMENTS:
                xml_output_shared.appendChild(imported_node)
                addElementToHashDict(elementsOutputHashDict, imported_node)
            else:
                if frame_group is not None:
                    frame_group.appendChild(imported_node)
                else:
                    xml_output_shared.appendChild(imported_node)
                # we need to add to the dictionary the element not the frame group.
                addElementToHashDict(elementsOutputHashDict, imported_node)


#
# Move all new input defs elements to the output defs
#
def move_all_input_defs_elements_to_the_output_defs(input_svg, options, frame_num, referencingElementsDict, elementsHashDict):
    global elementsOutputHashDict
    global ELEMENTS_TO_DISCARD
    global RETARGETABLE_ELEMENTS
    global SVG_ELEMENTS_TO_ALWAYS_MOVE
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS

    # MOVE all new ELEMENTS in the DEFS to the output xml defs.
    # Note: The elements inside the DEFS, when redundant, can be
    # ignored instead of being replaced with a "use"
    # element, because they are not in the Frames groups
    # and consequently they are not supposed to be visible.
    # The only function of elements inside the DEFS is to be
    # referenced and instanced by other elements in the frames, so
    # since they are redundant we can avoid moving them in the output
    # defs and just retarget the referencing elements pointing them
    # to the first of its kind that we already moved in the defs
    # (we call it 'master' element)

    nodesToMoveList = []

    defs_elements = input_svg.getElementsByTagName("defs")

    if len(defs_elements) < 1:
        return

    xml_input_defs = defs_elements[0]

    for node in xml_input_defs.childNodes:
        if node is not None and node.nodeType not in NODE_TYPES_TO_IGNORE:
            new_element_id = getElementId(node)
            nodesInDict = check_if_element_already_exists_in_hash_dict(node, xml_output_defs, elementsOutputHashDict)
            if nodesInDict is not None and len(nodesInDict) > 0:
                # an identical element is already present in the defs
                # we don't need to move this element anymore, because is a
                # defs element not supposed to be rendered. Let's just change
                # all referencing elements targets to the master element id.
                (master_node_id, master_node) = nodesInDict[0]
                if new_element_id == master_node_id:
                    input_nodes_flagged_as_not_to_move.append(new_element_id)
                    continue
                retarget_redundant_element_referencing_nodes_to_master(node, master_node_id, new_element_id, referencingElementsDict)
                # even if its a path, since it is already present in
                # the output defs, and since it was in the defs
                # section of the input svg to begin with, now that
                # we have retargeted his buddies, we don'need to move
                # it anymore.
                # if node.hasChildNodes() is False:
                if node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
                    input_nodes_flagged_as_not_to_move.append(new_element_id)
            else:
                # no identical element found in the output svg defs.
                # This is going to be the first of its kind, maybe a
                # a master element!
                # let's move it to the output defs shared group...
                nodesToMoveList.append(node)

    # Now that we retargeted all redundant nodes, we can move all
    # selected new defs element to the output defs shared section
    for node in nodesToMoveList:
        move_elem_to_output_svg_defs(node, elementsOutputHashDict)

    return


def retarget_redundant_element_referencing_nodes_to_master(node, master_id, new_node_id, referencingElementsDict):
    # we just need to change the reference target of the new elements
    # in the current input svg frame. No item in the output svg can
    # possibly target our element because it is from a new frame
    if referencingElementsDict is not None:
        refNodes = referencingElementsDict.get(new_node_id)
        if refNodes is not None:
            replace_all_element_references_with_new_id(new_node_id, master_id, refNodes)

    # Do we need to remove the node from the referencingElementsDict too?
    # Not sure if somehow the id or the node is going to be called by
    # the code after we remove it (maybe some gradient referenced by
    # the elem will be deleted and then we go looking for the referencing
    # node in the referencingElementsDict, but it is gone from it?
    # Let's assume so for now. In the future we may have to flag the
    # gone id keys (i.e. putting them in a list) and test it against
    # any id before passing it as a key to the referencingElementsDict.
    # TODO?

    return


def remove_duplicates_elements(xml_doc, elementsHashDict, referencingElementsDict):
    # remove duplicates and retarget referring buddies
    for _node_hash, nodesIdList in elementsHashDict.items():
        masterId = None
        for index in range(len(nodesIdList)):
            (nodeId, node) = nodesIdList[index]
            if node.nodeName not in ["g", "use", "stop", "meshrow", "meshpatch"] and node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
                if index == 0:
                    masterId = nodeId
                if index > 0:
                    if node.nodeName in NON_REUSABLE_ELEMENTS:
                        retarget_redundant_element_referencing_nodes_to_master(node, masterId, nodeId, referencingElementsDict)
                        if node.nodeName in RETARGETABLE_ELEMENTS:
                            if node.parentNode is not None:
                                node.parentNode.removeChild(node)
                    else:
                        if nodeId.endswith("_SMN"):
                            retarget_redundant_element_referencing_nodes_to_master(node, masterId, nodeId, referencingElementsDict)
                            if node.parentNode is not None:
                                node.parentNode.removeChild(node)
                        else:
                            if node.nodeName in REUSABLE_SVG_ELEMENTS:
                                convert_redundant_element_to_use_element(node, masterId, nodeId, referencingElementsDict)


def convert_redundant_element_to_use_element(node, master_id, new_node_id, referencingElementsDict):
    global elementsOutputHashDict
    global ELEMENTS_TO_DISCARD
    global RETARGETABLE_ELEMENTS
    global SVG_ELEMENTS_TO_ALWAYS_MOVE
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS

    if node.nodeName in SVG_ELEMENTS_TO_ALWAYS_MOVE:
        return

    # PHASE 1 : CONVERSION TO USE ELEMENT
    #
    # We need to change the directly-rendered-elements in use
    # elements, and skip the never-rendered-directly-elements.
    # This is because the latters are not usable in an use href
    # element, but only references by other elements in their properties.
    # So we just need to redirect the referencing elements and leave
    # those alone, since they are not going to be moved to the
    # output defs. We don't need to delete them since we will discard
    # the entire input svg document after we process each frame.
    if node is not None and node.nodeType not in NODE_TYPES_TO_IGNORE:
        if node.nodeName in REUSABLE_SVG_ELEMENTS and new_node_id.endswith("_SMN") is False:
            # strip element of attributes and convert it to 'use'
            # element
            attribs_to_remove = list(node.attributes.keys())
            for key in attribs_to_remove:
                # TODO: check if some attributes are differents from master
                # and do not remove them, leaving them attributes of the use
                # element (if we compared using the hash dict, they should
                # be identical but if we used deep reuse functions we may
                # have some differences since they only check the node main
                # attributes, not all attributes or its children).
                if key not in ["id", "xlink:href"]:
                    node.removeAttribute(key)
            # TODO: check if we need to remove child elements too.
            # (if we compared using the hash dict, they should
            # be identical but if we used deep reuse functions we may
            # have some differences since they only check the node
            # and not its children).
            if node.hasChildNodes() and node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
                for nodeChild in node.childNodes:
                    node.removeChild(nodeChild)

            node.setAttributeNS(NS["XLINK"], "href", "#" + master_id)
            node.tagName = "use"
            node.nodeName = "use"

        # PHASE 2 : REDIRECTION OF REFERENCES
        #
        # Now we can change all references to the element to point at the
        # master element.
        # we just need to change the reference target of the new elements
        # in the current input svg frame. No item in the output svg can
        # possibly target our element because it is from a new frame
        if referencingElementsDict is not None:
            refNodes = referencingElementsDict.get(new_node_id)
            if refNodes is not None:
                replace_all_element_references_with_new_id(new_node_id, master_id, refNodes)

    return


#############################
# HASH DICTIONARY FUNCTIONS #
#############################


def generateHashKeyDictionary(xml_doc):
    # this function generate the hash dictionary of a svg document
    # All nodes are hashed recursively.
    hash_id_dict = defaultdict(list)
    generate_hash_id_dict_recursively(xml_doc, hash_id_dict)
    # printDictionary(hash_id_dict)

    return hash_id_dict


def printDictionary(mydict):
    index = 0
    ppp("DEBUG DICTIONARY")
    for key, values in mydict.items():
        ppp("KEY:" + str(key))
        for id_, node_ in values:
            ppp("	index:" + str(index))
            ppp("	ID:" + str(id_))
            ppp("	NODE:" + node_.toprettyxml())
            ppp()
            index = index + 1
    ppp("DEBUG DICTIONARY END...")


# traverse all ids from a node and its childrens recursively
# storing the id and the hash in a dictionary
def generate_hash_id_dict_recursively(node, hash_id_dict):
    if node.nodeType not in NODE_TYPES_TO_IGNORE:
        if node.hasAttribute("id"):
            nodeId = node.getAttribute("id")
            if nodeId not in RESERVED_OUTPUT_IDS:
                node_hash = generateHashKeyFromElement(node)
                matching_nodes = hash_id_dict.get(node_hash)
                if matching_nodes is None or len(matching_nodes) < 1:
                    if node.nodeName not in ELEMENTS_NOT_TO_HASH:
                        hash_id_dict[node_hash].append((nodeId, node))
                else:
                    if nodeId not in dict(matching_nodes):
                        if node.nodeName not in ELEMENTS_NOT_TO_HASH:
                            hash_id_dict[node_hash].append((nodeId, node))
        if node.hasChildNodes():
            for nodeChild in node.childNodes:
                generate_hash_id_dict_recursively(nodeChild, hash_id_dict)
    return


# remove all ids from a node and its childrens recursively
def remove_all_ids_recursively(node):
    if node.nodeType not in NODE_TYPES_TO_IGNORE:
        if node.hasAttribute("id"):
            node.removeAttribute("id")
        if node.hasChildNodes():
            for nodeChild in node.childNodes:
                remove_all_ids_recursively(nodeChild)
    return


# generate an hash key from a string
def generateHashFromString(txt):
    return hash(txt)


# return hashlib.sha256(txt.encode()).hexdigest().upper()


# generate an hash key from a node
def generateHashKeyFromElement(node):
    if node is None:
        return None
    if node.nodeType in NODE_TYPES_TO_IGNORE:
        return None
    if node.nodeName in ELEMENTS_NOT_TO_HASH:
        return None
    cnode = node.cloneNode(True)
    remove_all_ids_recursively(cnode)
    return generateHashFromString(cnode.toxml())


# check if an element is present in the hash dict and return the list of
# duplicates id if it does, and None if it does not.
def check_if_element_already_exists_in_hash_dict(node, xml_doc, elementsHashDict):
    if node.nodeType in NODE_TYPES_TO_IGNORE:
        return None
    if node.nodeName in ELEMENTS_NOT_TO_HASH:
        return None
    hashkey = generateHashKeyFromElement(node)
    nodesIdsInDict = elementsHashDict.get(hashkey)
    if nodesIdsInDict is None or len(nodesIdsInDict) < 1:
        return None
    else:
        return nodesIdsInDict


# add an element to hash dict and return the list of duplicates id
def addElementToHashDict(elementsHashDict, node):
    # simple hash dictionary to avoid making too comparisons
    if node is not None and (node.nodeType not in NODE_TYPES_TO_IGNORE) and (node.nodeName not in ELEMENTS_NOT_TO_HASH):
        tag = findTag(node)
        if tag not in ELEMENTS_TO_DISCARD and tag != "g":
            if node.hasAttribute("id") is False or node.getAttribute("id") == "":
                ppp("ERROR ADDING NODE TO HASH DICTIONARY - node has no id: " + node.toprettyxml())
                sys.exit(1)
            else:
                nodeId = node.getAttribute("id")
                duplicatesIds = addNodeToHashDictHelper(elementsHashDict, node, nodeId)
                return duplicatesIds
    return None


# add a node to the hash dict and return the list of duplicates id
def addNodeToHashDictHelper(elementsHashDict, node, nodeId):
    if nodeId != "dummyId" and nodeId not in RESERVED_OUTPUT_IDS:
        hashkey = generateHashKeyFromElement(node)
        nodesIdsInDict = elementsHashDict.get(hashkey)
        if nodesIdsInDict is None or len(nodesIdsInDict) < 1:
            elementsHashDict[hashkey].append((nodeId, node))
            return None
        else:
            if nodeId not in dict(nodesIdsInDict):
                elementsHashDict[hashkey].append((nodeId, node))
            return nodesIdsInDict


#######################
# HASH DICTIONARY END #
#######################


# reuse elements if they are already in output defs
def reuse_elements_if_they_are_already_in_output_defs(input_svg, element_tag_name, referencingElementsDict, elementsHashDict):
    global ELEMENTS_TO_DISCARD
    global RETARGETABLE_ELEMENTS
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS

    input_elements_nodes = input_svg.getElementsByTagName(element_tag_name)

    if len(input_elements_nodes) < 1:
        return

    for node in input_elements_nodes:
        if node.hasAttribute("id") and (node.getAttribute("id") != ""):
            new_element_id = node.getAttribute("id")
            nodesInDict = check_if_element_already_exists_in_hash_dict(node, xml_output_defs, elementsOutputHashDict)
            if nodesInDict is not None and len(nodesInDict) > 0:
                # an identical element is already present in the defs
                # we don't need to move this element anymore, because is a
                # defs element not supposed to be rendered. Let's just change
                # all referencing elements targets to the master element id.
                (master_node_id, master_node) = nodesInDict[0]
                if new_element_id == master_node_id:
                    input_nodes_flagged_as_not_to_move.append(new_element_id)
                    continue
                convert_redundant_element_to_use_element(node, master_node_id, new_element_id, referencingElementsDict)
            else:
                # element does not exist in the output xml def.
                # we can leave it intact. In the future it will
                # be added to the output defs frame group by the
                # 'move_all_*' methods.
                return
    return


def getText(nodelist) -> str:
    """Extract text content from XML nodes.

    Args:
        nodelist: List of XML nodes

    Returns:
        Concatenated text content

    Raises:
        ValueError: If nodelist is None or invalid
    """
    if nodelist is None:
        raise ValueError("Nodelist cannot be None")

    try:
        rc = []
        for node in nodelist:
            if not hasattr(node, "nodeType"):
                continue

            if node.nodeType == node.TEXT_NODE:
                if hasattr(node, "data"):
                    rc.append(node.data)
            else:
                # Recursive
                if hasattr(node, "childNodes"):
                    rc.append(getText(node.childNodes))

        return "".join(rc)

    except Exception as e:
        add2log(f"WARNING: Failed to get text content: {str(e)}")
        return ""


# Reconstruct this element's body XML from dom nodes
def getChildXMLAsString(elem):
    out = ""
    for c in elem.childNodes:
        if c.nodeType == Node.TEXT_NODE:
            out += c.nodeValue
        else:
            if c.nodeType == Node.ELEMENT_NODE:
                if c.childNodes.length == 0:
                    out += "<" + c.nodeName + "/>"
                else:
                    out += "<" + c.nodeName + ">"
                    cs = ""
                    cs = getChildXMLAsString(c)
                    out += cs
                    out += "</" + c.nodeName + ">"
    return out


def getElementMainData(node, main_attr):
    main_data = None
    if main_attr == "child-nodes":
        main_data = getText(node.childNodes)
    else:
        if node.hasAttribute(main_attr) and node.getAttribute(main_attr) != "":
            main_data = node.getAttribute(main_attr)

    return main_data


def removeElementMainData(node, main_attr):
    if main_attr == "child-nodes":
        nodes_to_remove = []
        if node.hasChildNodes:
            for nodeChild in node.childNodes:
                nodes_to_remove.append(nodeChild)

            for goner_node in nodes_to_remove:
                goner_node.parentNode.removeChild(goner_node)
    else:
        if node.hasAttribute(main_attr):
            node.removeAttribute(main_attr)


def deep_reuse_elem_if_they_are_already_in_output_defs(input_svg, options, frame_num, referencingElementsDict, element_tag_name):
    global ELEMENTS_TO_DISCARD
    global RETARGETABLE_ELEMENTS
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS
    global outputReferencingElementsDict
    global inputReferencingElementsDict

    inputElementsKeyDict = defaultdict(list)
    input_elements_id_dict = {}
    output_elements_id_dict = {}
    outputElementsKeyDict = defaultdict(list)

    # lets get the name of the main attribute for this element type
    if element_tag_name in MAIN_ATTRIBUTES_DICT:
        main_attr = MAIN_ATTRIBUTES_DICT.get(element_tag_name)
    else:
        return

    # create a dictionary of all elements of the requested tag in the
    # input document
    input_elements_nodes = input_svg.getElementsByTagName(element_tag_name)
    if len(input_elements_nodes) < 1:
        return
    for node in input_elements_nodes:
        main_data = getElementMainData(node, main_attr)
        if main_data is not None:
            if main_data.strip() != "":
                key = "d:" + main_data
                node_id = node.getAttribute("id")
                if input_elements_id_dict is None:
                    input_elements_id_dict = {}
                input_elements_id_dict.update({node_id: node})
                existing_ids = inputElementsKeyDict.get(key)
                if existing_ids is None or len(existing_ids) < 1:
                    inputElementsKeyDict[key].append(node_id)
                else:
                    if node_id not in existing_ids:
                        inputElementsKeyDict[key].append(node_id)

    # create a dictionary of all elements of the requested tag in the
    # output document
    if outputElementsKeyDict is None or len(outputElementsKeyDict.items()) == 0:
        for node in xml_output_defs.getElementsByTagName(element_tag_name):
            main_data = getElementMainData(node, main_attr)
            if main_data is not None:
                if main_data.strip() != "":
                    key = "d:" + main_data
                    node_id = node.getAttribute("id")
                    if output_elements_id_dict is None:
                        output_elements_id_dict = {}
                    output_elements_id_dict.update({node_id: node})
                    existing_ids = outputElementsKeyDict.get(key)
                    if existing_ids is None or len(existing_ids) < 1:
                        outputElementsKeyDict[key].append(node_id)
                    else:
                        if node_id not in existing_ids:
                            outputElementsKeyDict[key].append(node_id)

    for key in inputElementsKeyDict.keys():
        # let's check if elements from input svg already exist in the
        # output svg
        matching_ids_in_output_doc = outputElementsKeyDict.get(key)

        matching_ids_in_input_doc = inputElementsKeyDict.get(key)
        if matching_ids_in_output_doc is not None and len(matching_ids_in_output_doc) > 0:
            # since there are matching elements already in the output svg
            # we need to convert this to use element and referencing it
            # to a SMN or a master
            master_id = list(matching_ids_in_output_doc)[0]
            master_node = output_elements_id_dict.get(master_id)
            shared_master_node = create_shared_master_elem(master_id, master_node)
            if shared_master_node is not None:
                shared_master_node_id = shared_master_node.getAttribute("id")
                # now we convert to use all input elements matching the output master
                for node_id in list(matching_ids_in_input_doc):
                    duplicate_node = input_elements_id_dict[node_id]
                    deep_convert_redundant_element_to_use_element(
                        duplicate_node,
                        shared_master_node_id,
                        node_id,
                        inputReferencingElementsDict,
                    )
                for node_id in list(matching_ids_in_output_doc):
                    duplicate_node = output_elements_id_dict[node_id]
                    deep_convert_redundant_element_to_use_element(
                        duplicate_node,
                        shared_master_node_id,
                        node_id,
                        outputReferencingElementsDict,
                    )
            else:
                # if we cannot create a SMN then we just convert the
                # node to use in the usual way
                for node_id in list(matching_ids_in_input_doc):
                    duplicate_node = input_elements_id_dict[node_id]
                    convert_redundant_element_to_use_element(duplicate_node, master_id, node_id, inputReferencingElementsDict)

    return


def check_id_existence(elem_id):
    return ElementById(elem_id, xml_output_shared)


# Create a Shared Master Node (SMN) from a node and add it to
# the def shared section of the output svg, as part of the
# DEEP REUSE protocol.
def create_shared_master_elem(master_id, master_node):
    global elementsOutputHashDict
    global SVG_ELEMENTS_TO_ALWAYS_MOVE

    if master_node.nodeName in NON_REUSABLE_ELEMENTS or master_node.nodeName in SVG_ELEMENTS_TO_ALWAYS_MOVE:
        return None

    # avoid creating shared master node twice for the same master id
    if master_id.endswith("_SMN"):
        return ElementById(master_id, xml_output_shared)

    # avoid creating the SMN if it already exists in def shared
    elem_SMN = ElementById(master_id + "_SMN", xml_output_shared)
    if elem_SMN is not None:
        return elem_SMN

    # return NONE if the element is not deep reusable
    if master_node.nodeName in MAIN_ATTRIBUTES_DICT:
        main_attr = MAIN_ATTRIBUTES_DICT.get(master_node.nodeName)
    else:
        return None

    shared_master_node = master_node.cloneNode(True)
    attribs_to_remove = list(shared_master_node.attributes.keys())
    for key in attribs_to_remove:
        # For text elements, preserve presentation attributes that affect rendering
        # WHY: Presentation attributes on <use> do NOT affect referenced <text>
        if master_node.nodeName == "text" and key in TEXT_PRESENTATION_ATTRIBUTES:
            continue  # Keep this attribute on the text element
        if key != "id" and key != main_attr:
            shared_master_node.removeAttribute(key)
    if shared_master_node.hasChildNodes():
        for childNode in shared_master_node.childNodes:
            if main_attr != "child-nodes":
                shared_master_node.removeChild(childNode)

    xml_output_shared.appendChild(shared_master_node)
    shared_master_node.setAttribute("id", master_id + "_SMN")

    addElementToHashDict(elementsOutputHashDict, shared_master_node)

    return shared_master_node


def deep_convert_redundant_element_to_use_element(node, master_id, new_node_id, referencingElementsDict):
    global elementsOutputHashDict
    global ELEMENTS_TO_DISCARD
    global RETARGETABLE_ELEMENTS
    global SVG_ELEMENTS_TO_ALWAYS_MOVE
    global xml_output_doc
    global xml_output_defs
    global xml_output_shared
    global sml_output_svg
    global input_nodes_flagged_as_not_to_move
    global NON_REUSABLE_ELEMENTS

    # PHASE 1 : CONVERSION TO USE ELEMENT
    #
    # We need to change the directly-rendered-elements in use
    # elements, and skip the never-rendered-directly-elements.
    # This is because the latters are not usable in an use href
    # element, but only references by other elements in their properties.
    # So we just need to redirect the referencing elements to his master id,
    # and leave those alone, since they are not going to be moved to
    # the output defs. We don't need to delete them since we will discard
    # the entire input svg document after we process each frame.
    if node is not None and node.nodeType not in NODE_TYPES_TO_IGNORE and node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
        # check if node is a Shared Master Node, if true leave it
        if new_node_id.endswith("_SMN"):
            return
        # check if master node is a Shared Master Node, if not returns
        if master_id.endswith("_SMN") is False:
            return
        if node.nodeName in MAIN_ATTRIBUTES_DICT:
            main_attr = MAIN_ATTRIBUTES_DICT[node.nodeName]
        if node.nodeName not in NON_REUSABLE_ELEMENTS:
            # strip element of the main attribute and convert it to 'use'
            # (the deep reuse need to keep all attributes but the main attr)
            node.setAttributeNS(NS["XLINK"], "href", "#" + master_id)
            removeElementMainData(node, main_attr)
            node.tagName = "use"
            node.nodeName = "use"
            # TODO: check SVG specs if we need to do this to container elements
            # converted to use.
            # Unless we are converting container elements we do not need
            # to remove the children
            if node.hasChildNodes() and main_attr == "child-nodes":
                for nodeChild in node.childElements:
                    node.removeChild(nodeChild)
        else:
            # the node is not reusable, so being a duplicate we just flag it
            # to be ignored when we move the nodes. We are redirecting
            # the referencing nodes to his master id, so it is useless.
            if node.hasChildNodes() is False and node.nodeName not in SVG_ELEMENTS_TO_ALWAYS_MOVE:
                input_nodes_flagged_as_not_to_move.append(node)

        # PHASE 2 : REDIRECTION OF REFERENCES
        #
        # Now we can change all references to the element to point at the
        # master element.
        # we just need to change the reference target of the new elements
        # in the current input svg frame. No item in the output svg can
        # possibly target our element because it is from a new frame
        if referencingElementsDict is not None:
            refNodes = referencingElementsDict.get(new_node_id)
            if refNodes is not None:
                replace_all_element_references_with_new_id(new_node_id, master_id, refNodes)
    return


def replace_all_element_references_with_new_id(old_id, new_id, referencingElems):
    func_iri = None
    if referencingElems is not None:
        # 		duplicates_ids = [d.getAttribute("id") for d in referenced_ids[old_id]]
        if func_iri is None:
            # matches url(#<ANY_OLD_ID>), url('#<ANY_OLD_ID>')
            # and url("#<ANY_OLD_ID>")
            # old_id_regex = "|".join(duplicates_ids)
            # func_iri = re.compile('url\\([\'"]?#(?:' +
            # old_id_regex + ')[\'"]?\\)')
            func_iri = re.compile("url\\(['\"]?#(?:" + old_id + ")['\"]?\\)")
        for elem in referencingElems:
            # ⚠️ CRITICAL: Do NOT retarget feImage xlink:href references
            #
            # WHY THIS MATTERS:
            # =================
            # When a <use> element is converted to a shared master node (_SMN),
            # normal elements can be retargeted to reference the _SMN directly.
            # However, feImage filter primitives have special requirements:
            #
            # Problem Case:
            #   1. Original: <path id="Blue100" fill="#00ffff" .../>
            #   2. svg2fbf converts to:
            #      - <use id="a_FBF00020" fill="#0ff" xlink:href="#a_FBF00020_SMN"/>
            #      - <path id="a_FBF00020_SMN" d="..."/> (NO FILL!)
            #   3. feImage reference: <feImage xlink:href="#a_FBF00020"/>
            #   4. If retargeted to: <feImage xlink:href="#a_FBF00020_SMN"/>
            #   5. Result: feImage sees path with NO fill → renders BLACK ✗
            #
            # Correct Behavior:
            #   feImage should reference the <use> element (which HAS fill attribute)
            #   The <use> element's presentation attributes ARE applied by feImage
            #   Result: feImage sees colored path → renders correctly ✓
            #
            # HISTORY:
            # ========
            # Bug discovered in Frame 28 testing (filters-composite-02-b.svg):
            # - Triangles with magenta/cyan fills rendered as black
            # - feImage references were being retargeted from <use> to _SMN
            # - _SMN paths had no fill attributes (stripped during SMN creation)
            # - Fix: Skip retargeting for feImage elements
            #
            # ⚠️ DO NOT CHANGE THIS LOGIC WITHOUT TESTING FRAME 28!
            #
            if elem.nodeName == "feImage":
                # Skip retargeting for feImage - it needs to reference the <use> element
                # to preserve presentation attributes like fill, stroke, opacity, etc.
                continue

            # find out which attribute referenced the old id
            for attr in referencingProps:
                v = elem.getAttribute(attr)
                (v_new, n) = func_iri.subn("url(#" + new_id + ")", v)
                if n > 0:
                    elem.setAttribute(attr, v_new)
            if elem.getAttributeNS(NS["XLINK"], "href") == "#" + old_id:
                elem.setAttributeNS(NS["XLINK"], "href", "#" + new_id)
            styles = _getStyle(elem)
            for style in styles:
                v = styles[style]
                (v_new, n) = func_iri.subn("url(#" + new_id + ")", v)
                if n > 0:
                    styles[style] = v_new
            _setStyle(elem, styles)


# null coalescing operator
def COAL(item):
    return "" if item is None else item


def PathById(elementId, xml_doc):
    elements = xml_doc.getElementsByTagName("path")
    for element in elements:
        if element is not None and element.nodeType == element.ELEMENT_NODE:
            if element.hasAttribute("id") and element.getAttribute("id") == elementId:
                # return only the first element we found
                # (supposing no duplicate ids)
                return element
    return None


def PolygonById(elementId, xml_doc):
    elements = xml_doc.getElementsByTagName("polygon")
    for element in elements:
        if element is not None and element.nodeType == element.ELEMENT_NODE:
            if element.hasAttribute("id") and element.getAttribute("id") == elementId:
                # return only the first element we found
                # (supposing no duplicate ids)
                return element
    return None


def PolylineById(elementId, xml_doc):
    elements = xml_doc.getElementsByTagName("polyline")
    for element in elements:
        if element is not None and element.nodeType == element.ELEMENT_NODE:
            if element.hasAttribute("id") and element.getAttribute("id") == elementId:
                # return only the first element we found
                # (supposing no duplicate ids)
                return element
    return None


def ImageById(elementId, xml_doc):
    elements = xml_doc.getElementsByTagName("image")
    for element in elements:
        if element is not None and element.nodeType == element.ELEMENT_NODE:
            if element.hasAttribute("id") and element.getAttribute("id") == elementId:
                # return only the first element we found
                # (supposing no duplicate ids)
                return element
    return None


def ElementByIdAndTag(elementId, elementTag, xml_doc):
    elements = xml_doc.getElementsByTagName(elementTag)
    for element in elements:
        if element is not None and element.nodeType == element.ELEMENT_NODE:
            if element.hasAttribute("id") and element.getAttribute("id") == elementId:
                # return only the first element we found
                # (supposing no duplicate ids)
                return element
    return None


def ElementById(elementId, xml_doc):
    elements = xml_doc.getElementsByTagName("*")
    for element in elements:
        if element is not None and element.nodeType == element.ELEMENT_NODE:
            if element.hasAttribute("id") and element.getAttribute("id") == elementId:
                # return only the first element we found
                # (supposing no duplicate ids)
                return element
    return None


def getElementId(elem):
    if elem.hasAttribute("id"):
        elementId = elem.getAttribute("id")
        return elementId
    return None


def findTag(node):
    if node is not None and node.nodeType not in NODE_TYPES_TO_IGNORE:
        if node.nodeName is not None:
            return node.nodeName
    return None


def getViewBox(docElement, options):
    # get doc width and height
    w = SVGLength(docElement.getAttribute("width"))
    h = SVGLength(docElement.getAttribute("height"))

    # if width/height are not unitless or px then it is not ok to rewrite
    # them into a viewBox.
    # well, it may be OK for Web browsers and vector editors, but not for
    # librsvg.
    if (w.units != Unit.NONE and w.units != Unit.PX) or (h.units != Unit.NONE and h.units != Unit.PX):
        add2log(f"WARNING: viewBox values of file {current_filepath} are not unitless or in px!")
    # TODO: convert values to unitless

    # parse viewBox attribute
    vbSep = RE_COMMA_WSP.split(docElement.getAttribute("viewBox"))
    # if we have a valid viewBox we need to check it
    if len(vbSep) == 4:
        try:
            # if x or y are specified and non-zero then it is not ok to
            # overwrite it
            vbX = float(vbSep[0])
            vbY = float(vbSep[1])
            if vbX != 0 or vbY != 0:
                add2log(f"WARNING: viewBox X and Y coordinates if file {current_filepath} are not 0!")

            # if width or height are not equal to doc width/height then it
            # is not ok to overwrite it
            vbWidth = float(vbSep[2])
            vbHeight = float(vbSep[3])
            if vbWidth != w.value or vbHeight != h.value:
                add2log(f"WARNING: viewBox width and height of file {current_filepath} do not match document width and height!")

        # if the viewBox did not parse properly it is invalid and ok to
        # overwrite it
        except ValueError:
            add2log(f"WARNING: viewBox of file {current_filepath} is invalid!!")
            pass

    return (vbX, vbY, vbWidth, vbHeight, w.value, h.value)


######################################################
#   svg minification functions (courtesy of Scour)   #
######################################################


def preprocess_svg_file(doc, options, filepath):
    # We need to remove unneeded elements from the input svg frames
    # this will help making the output file smaller and with
    # a smaller memory footprint when animated.

    convert_css_stylesheet_to_svg_attributes(doc, options)

    # remove unneeded namespaced elements/attributes added by common editors
    # if options.keep_editor_data is False:
    removeNamespacedElements(doc.documentElement, UNWANTED_NS)
    removeNamespacedAttributes(doc.documentElement, UNWANTED_NS)

    # determine number of flowRoot elements in input document
    # flowRoot elements don't render at all on current browsers
    determine_number_of_flowRoot_elements(doc, options, filepath)

    # remove the xmlns declarations
    remove_xmlns_declarations(doc)

    # ensure valid namespace for SVG is declared
    ensure_valid_svg_namespace_is_declared(doc, options, filepath)

    # remove all animations from elements because we need a static frame
    # TODO: clean all animations elements
    remove_all_animations(doc, options)

    # remove all embedded or linked audio files because we need a silent frame
    # TODO: clean all audio elements and references

    # check for redundant and unused SVG namespace declarations
    remove_unused_and_reduntant_namespace_declarations(doc, options)

    # remove comments
    # if options.keep_comments is False:
    remove_comments(doc)

    # remove xml space attributes
    if options.keep_xml_space_attribute is False and doc.documentElement.hasAttribute("xml:space"):
        doc.documentElement.removeAttribute("xml:space")

    # repair style (remove unnecessary style properties and change them
    # into XML attributes)
    repairStyle(doc.documentElement, options)

    # convert colors to #RRGGBB format
    convertColors(doc.documentElement)

    # remove descriptive elements
    remove_descriptive_elements(doc, options)

    # remove unreferenced gradients/patterns outside of defs
    # and most unreferenced elements inside of defs
    while remove_unreferenced_elements(doc, False) > 0:
        pass

    # remove empty elements
    remove_empty_elements(doc, options)

    while remove_duplicate_gradient_stops(doc, options) > 0:
        pass

    # remove gradients that are only referenced by one other gradient
    while collapse_singly_referenced_gradients(doc, options) > 0:
        pass

    # remove duplicate gradients
    removeDuplicateGradients(doc)

    # merge sibiling groups
    mergeSiblingGroupsWithCommonAttributes(doc.documentElement)

    # create <g> elements if there are runs of elements with the same attributes.
    # this MUST be before moveCommonAttributesToParentGroup.
    create_groups_for_common_attributes(doc.documentElement)

    # move common attributes to parent group
    # NOTE: the if the <svg> element's immediate children
    # all have the same value for an attribute, it must not
    # get moved to the <svg> element. The <svg> element's doesn't accept
    # fill=, stroke= etc.!
    referencedIds = findReferencedElements(doc.documentElement)
    for child in doc.documentElement.childNodes:
        moveCommonAttributesToParentGroup(child, referencedIds)

    # remove unused attributes from parent
    removeUnusedAttributesOnParent(doc.documentElement)

    # Collapse groups LAST, because we've created groups. If done before
    # moveAttributesToParentGroup, empty <g>'s may remain.
    while remove_nested_groups(doc.documentElement) > 0:
        pass

    # NOT NEEDED FOR NOW
    # remove unnecessary closing point of polygons and scour points
    # 	for polygon in doc.documentElement.getElementsByTagName('polygon'):
    # 		clean_polygon(polygon, options)

    # NOT NEEDED FOR NOW
    # scour points of polyline
    # 	for polyline in doc.documentElement.getElementsByTagName('polyline'):
    # 		cleanPolyline(polyline, options)

    # NOT NEEDED FOR NOW
    # clean path data
    # 	for elem in doc.documentElement.getElementsByTagName('path'):
    # 		if elem.getAttribute('d') == '':
    # 			elem.parentNode.removeChild(elem)
    # 		else:
    # 			clean_path(elem, options)

    # find elements without Id and add a random Id to them
    findElementsWithoutIdAndAddId(doc.documentElement)

    # shorten ID names as much as possible
    shortenIDs(doc, options)

    # REDUCE PRECISION
    # scour lengths (including coordinates)
    for type in [
        "svg",
        "image",
        "rect",
        "circle",
        "ellipse",
        "line",
        "linearGradient",
        "radialGradient",
        "stop",
        "filter",
    ]:
        for elem in doc.getElementsByTagName(type):
            for attr in [
                "x",
                "y",
                "width",
                "height",
                "cx",
                "cy",
                "r",
                "rx",
                "ry",
                "x1",
                "y1",
                "x2",
                "y2",
                "fx",
                "fy",
                "offset",
            ]:
                if elem.getAttribute(attr) != "":
                    elem.setAttribute(attr, scourLength(elem.getAttribute(attr)))
    viewBox = doc.documentElement.getAttribute("viewBox")
    if viewBox:
        lengths = RE_COMMA_WSP.split(viewBox)
        lengths = [scourUnitlessLength(length) for length in lengths]
        doc.documentElement.setAttribute("viewBox", " ".join(lengths))

    # REDUCE PRECISION MORE
    # more length scouring in this function
    reducePrecision(doc.documentElement)

    # more length scouring in this function
    reducePrecision(doc.documentElement)

    # remove default values of attributes
    removeDefaultAttributeValues(doc.documentElement, options)

    # reduce the length of transformation attributes
    # 	optimizeTransforms(doc.documentElement, options)

    # convert rasters references to base64-encoded strings
    # TODO: solve the crash when trying to encode
    # for elem in doc.documentElement.getElementsByTagName("image"):
    #     embed_rasters(elem, options)

    # properly size the SVG document (ideally width/height should be 100%
    # with a viewBox)
    properlySizeDoc(doc.documentElement, options)

    # output the document as a pretty string with a single space for indent
    # 	minified_svg_string = serialize_svg_doc_to_string(doc, options)

    return doc


def Minor_Optimize_SVG_Helper(doc, options):
    # remove unreferenced gradients/patterns outside of defs
    # and most unreferenced elements inside of defs
    while remove_unreferenced_elements(doc, False) > 0:
        pass

    # remove empty elements
    remove_empty_elements(doc, options)

    while remove_duplicate_gradient_stops(doc, options) > 0:
        pass

    # remove gradients that are only referenced by one other gradient
    while collapse_singly_referenced_gradients(doc, options) > 0:
        pass

    # remove duplicate gradients
    removeDuplicateGradients(doc)

    # remove unused attributes from parent
    removeUnusedAttributesOnParent(doc.documentElement)

    # Collapse groups LAST, because we've created groups. If done before
    # moveAttributesToParentGroup, empty <g>'s may remain.
    while remove_nested_groups(doc.documentElement) > 0:
        pass

    return


def convert_css_stylesheet_to_svg_attributes(xml_doc, options):
    style_nodes = xml_doc.getElementsByTagName("style")
    nodes_to_remove = []
    for node in style_nodes:
        # if this node is a style element, parse its text into CSS
        if node.nodeName == "style" and node.namespaceURI == NS["SVG"]:
            node.normalize()
            stylesheet = "".join(child.nodeValue for child in node.childNodes)
            stylesheet = stylesheet.strip()
            cssClassesDict = {}
            if stylesheet != "":
                cssRules = parseCssString(stylesheet)
                if cssRules:
                    for rule in cssRules:
                        rule_class_name = rule["selector"]
                        cssClassesDict.update({rule_class_name: rule})
                    convert_all_nodes_with_class_to_style(xml_doc, cssClassesDict)
        nodes_to_remove.append(node)
    for goner in nodes_to_remove:
        if goner.parentNode is not None:
            goner.parentNode.removeChild(goner)
    return


def convert_all_nodes_with_class_to_style(xml_doc, cssClassesDict):
    class_names_list = cssClassesDict.keys()
    for node in xml_doc.getElementsByTagName("*"):
        if node.nodeType not in NODE_TYPES_TO_IGNORE:  # == Node.ELEMENT_NODE:
            if node.hasAttribute("class"):
                node_class = "." + node.getAttribute("class")
                if node_class in list(class_names_list):
                    rule = cssClassesDict[node_class]
                    r_properties = []
                    for propname in rule["properties"]:
                        if propname.isspace() is False and propname.strip() in CSS_TO_SVG_DICT:
                            corr_propname = CSS_TO_SVG_DICT[propname.strip()]
                            if corr_propname.isspace() is False:
                                r_properties.append(corr_propname + ":" + rule["properties"][propname])
                    s_properties = ";".join(str(c) for c in r_properties)
                    if node.hasAttribute("style"):
                        style_attribute = node.getAttribute("style")
                        if style_attribute:
                            style_attribute = style_attribute + s_properties
                            node.setAttribute("style", style_attribute)
                        else:
                            node.setAttribute("style", s_properties)
                    else:
                        node.setAttribute("style", s_properties)
                node.removeAttribute("class")

    return


def remove_all_animations(node, options):
    childElements = []
    for child in node.childNodes:
        if child.nodeType != NODE_TYPES_TO_IGNORE:
            childElements.append(child)
        else:  # doctypes, entities, comments
            return

    # for each child element
    for childNum in range(len(childElements)):
        child = childElements[childNum]
        if child.localName in [
            "set",
            "animate",
            "animateColor",
            "animateTransform",
            "animateMotion",
        ]:
            node.removeChild(child)
            return
        else:
            remove_all_animations(child, options)


def serialize_svg_doc_to_string(doc, options):
    out_string = serializeXML(doc.documentElement, options) + "\n"

    # return the string with its XML prolog and surrounding comments
    string_output = '<?xml version="1.0" encoding="UTF-8"'
    if doc.standalone:
        string_output += ' standalone="yes"'
    string_output += "?>\n"

    for child in doc.childNodes:
        if child.nodeType == Node.ELEMENT_NODE:
            string_output += out_string
        else:  # doctypes, entities, comments
            string_output += child.toxml() + "\n"

    return string_output


def make_well_formed(text, quote_dict=None):
    if quote_dict is None:
        quote_dict = XML_ENTS_NO_QUOTES
    if not any(c in text for c in quote_dict):
        # The quote-able characters are quite rare in SVG (they mostly only
        # occur in text elements in practice).  Therefore it make sense to
        # optimize for this common case
        return text
    return "".join(quote_dict[c] if c in quote_dict else c for c in text)


def choose_quote_character(value):
    quot_count = value.count('"')
    if quot_count == 0 or quot_count <= value.count("'"):
        # Fewest "-symbols (if there are 0, we pick this to avoid spending
        # time counting the '-symbols as it won't matter)
        quote = '"'
        xml_ent = XML_ENTS_ESCAPE_QUOT
    else:
        quote = "'"
        xml_ent = XML_ENTS_ESCAPE_APOS
    return quote, xml_ent


TEXT_CONTENT_ELEMENTS = [
    "text",
    "tspan",
    "tref",
    "textPath",
    "altGlyph",
    "flowDiv",
    "flowPara",
    "flowSpan",
    "flowTref",
    "flowLine",
]


KNOWN_ATTRS = (
    [
        # TODO: Maybe update with full list from https://www.w3.org/TR/SVG/attindex.html
        # (but should be kept intuitively ordered)
        "id",
        "xml:id",
        "class",
        "transform",
        "x",
        "y",
        "z",
        "width",
        "height",
        "x1",
        "x2",
        "y1",
        "y2",
        "dx",
        "dy",
        "rotate",
        "startOffset",
        "method",
        "spacing",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "fx",
        "fy",
        "d",
        "points",
    ]
    + sorted(SVG_ATTRIBUTES)
    + ["style"]
)

KNOWN_ATTRS_ORDER_BY_NAME = defaultdict(lambda: len(KNOWN_ATTRS), {name: order for order, name in enumerate(KNOWN_ATTRS)})


# use custom order for known attributes and alphabetical order for the rest
def _attribute_sort_key_function(attribute):
    name = attribute.name
    order_value = KNOWN_ATTRS_ORDER_BY_NAME[name]
    return order_value, name


def attributes_ordered_for_output(element):
    if not element.hasAttributes():
        return []
    attribute = element.attributes
    # The .item(i) call is painfully slow (bpo#40689). Therefore we ensure we
    # call it at most once per attribute.
    # - it would be many times faster to use `attribute.values()` but sadly
    #   that is an "experimental" interface.
    return sorted(
        (attribute.item(i) for i in range(attribute.length)),
        key=_attribute_sort_key_function,
    )


# hand-rolled serialization function that has the following benefits:
# - pretty printing
# - somewhat judicious use of whitespace
# - ensure id attributes are first
def serializeXML(element, options, indent_depth: int = 0, preserveWhitespace: bool = False) -> str:
    """Serialize XML element to string with formatting.

    Args:
        element: XML element to serialize
        options: Serialization options
        indent_depth: Current indentation level
        preserveWhitespace: Whether to preserve whitespace

    Returns:
        Serialized XML string
    """
    outParts = []

    indent_type = "\t"
    newline = "\n"

    outParts.extend([(indent_type * indent_depth), "<", element.nodeName])

    # now serialize the other attributes
    attrs = attributes_ordered_for_output(element)
    for attr in attrs:
        if attr.nodeValue is None or attr.nodeValue.isspace():
            continue
        attrValue = attr.nodeValue
        quote, xml_ent = choose_quote_character(attrValue)
        attrValue = make_well_formed(attrValue, xml_ent)

        if attr.nodeName == "style":
            # sort declarations
            attrValue = ";".join(sorted(attrValue.split(";")))

        outParts.append(" ")
        # preserve xmlns: if it is a namespace prefix declaration
        if attr.prefix is not None:
            outParts.extend([attr.prefix, ":"])
        elif attr.namespaceURI is not None:
            if attr.namespaceURI == "http://www.w3.org/2000/xmlns/" and attr.nodeName.find("xmlns") == -1:
                outParts.append("xmlns:")
            elif attr.namespaceURI == "http://www.w3.org/1999/xlink":
                outParts.append("xlink:")
        outParts.extend([attr.localName, "=", quote, attrValue, quote])

        if attr.nodeName == "xml:space":
            if attrValue == "preserve":
                preserveWhitespace = True
            elif attrValue == "default":
                preserveWhitespace = False

    children = element.childNodes
    if children.length == 0:
        outParts.append("/>")
    else:
        outParts.append(">")

    onNewLine = False
    for child in element.childNodes:
        # element node
        if child.nodeType == Node.ELEMENT_NODE:
            # do not indent inside text content elements as in SVG there's
            # a difference between "text1\ntext2" and "text1\n text2"
            # see https://www.w3.org/TR/SVG/text.html#WhiteSpace
            if preserveWhitespace or element.nodeName in TEXT_CONTENT_ELEMENTS:
                outParts.append(serializeXML(child, options, 0, preserveWhitespace))
            else:
                outParts.extend(
                    [
                        newline,
                        serializeXML(child, options, indent_depth + 1, preserveWhitespace),
                    ]
                )
                onNewLine = True
        # text node
        elif child.nodeType == Node.TEXT_NODE:
            text_content = child.nodeValue
            if not preserveWhitespace:
                # strip / consolidate whitespace according to spec, see
                # https://www.w3.org/TR/SVG/text.html#WhiteSpace
                if element.nodeName in TEXT_CONTENT_ELEMENTS:
                    text_content = text_content.replace("\n", "")
                    text_content = text_content.replace("\t", " ")
                    if child == element.firstChild:
                        text_content = text_content.lstrip()
                    elif child == element.lastChild:
                        text_content = text_content.rstrip()
                    while "  " in text_content:
                        text_content = text_content.replace("  ", " ")
                else:
                    text_content = text_content.strip()
            outParts.append(make_well_formed(text_content))
        # CDATA node
        elif child.nodeType == Node.CDATA_SECTION_NODE:
            outParts.extend(["<![CDATA[", child.nodeValue, "]]>"])
        # Comment node
        elif child.nodeType == Node.COMMENT_NODE:
            outParts.extend(
                [
                    newline,
                    indent_type * (indent_depth + 1),
                    "<!--",
                    child.nodeValue,
                    "-->",
                ]
            )
        # TODO: entities, processing instructions, what else?
        else:  # ignore the rest
            pass

    # Only add closing tag if element has children (not self-closing)
    if children.length > 0:
        if onNewLine:
            outParts.append(newline)
            outParts.append(indent_type * indent_depth)
        outParts.extend(["</", element.nodeName, ">"])

    return "".join(outParts)


# A list of default attributes that are safe to remove if all conditions
# are fulfilled
#
# Each default attribute is an object of type 'DefaultAttribute' with the
# following fields:
# name - name of the attribute to be matched
# value - default value of the attribute
# units - the unit(s) for which 'value' is valid (see 'Unit' class for
#         possible specifications)
# elements - name(s) of SVG element(s) for which the attribute
#            specification is valid
# conditions - additional conditions that have to be fulfilled for removal
#              of the specified default attribute implemented as lambda
#              functions with one argument (an xml.dom.minidom node)
#              evaluating to either True or False
# When not specifying a field value, it will be ignored (i.e. always matches)
#
# Sources for this list:
# 	 https://www.w3.org/TR/SVG/attindex.html			 (mostly implemented)
# 	 https://www.w3.org/TR/SVGTiny12/attributeTable.html (not yet implemented)
# 	 https://www.w3.org/TR/SVG2/attindex.html			(not yet implemented)
#
DefaultAttribute = namedtuple("DefaultAttribute", ["name", "value", "units", "elements", "conditions"])
DefaultAttribute.__new__.__defaults__ = (None,) * len(DefaultAttribute._fields)
default_attributes = [
    # unit systems
    DefaultAttribute("clipPathUnits", "userSpaceOnUse", elements=["clipPath"]),
    DefaultAttribute("filterUnits", "objectBoundingBox", elements=["filter"]),
    DefaultAttribute(
        "gradientUnits",
        "objectBoundingBox",
        elements=["linearGradient", "radialGradient"],
    ),
    DefaultAttribute("maskUnits", "objectBoundingBox", elements=["mask"]),
    DefaultAttribute("maskContentUnits", "userSpaceOnUse", elements=["mask"]),
    DefaultAttribute("patternUnits", "objectBoundingBox", elements=["pattern"]),
    DefaultAttribute("patternContentUnits", "userSpaceOnUse", elements=["pattern"]),
    DefaultAttribute("primitiveUnits", "userSpaceOnUse", elements=["filter"]),
    DefaultAttribute(
        "externalResourcesRequired",
        "false",
        elements=[
            "a",
            "altGlyph",
            "animate",
            "animateColor",
            "animateMotion",
            "animateTransform",
            "circle",
            "clipPath",
            "cursor",
            "defs",
            "ellipse",
            "feImage",
            "filter",
            "font",
            "foreignObject",
            "g",
            "image",
            "line",
            "linearGradient",
            "marker",
            "mask",
            "mpath",
            "path",
            "pattern",
            "polygon",
            "polyline",
            "radialGradient",
            "rect",
            "script",
            "set",
            "svg",
            "switch",
            "symbol",
            "text",
            "textPath",
            "tref",
            "tspan",
            "use",
            "view",
        ],
    ),
    # svg elements
    DefaultAttribute("width", 100, Unit.PCT, elements=["svg"]),
    DefaultAttribute("height", 100, Unit.PCT, elements=["svg"]),
    DefaultAttribute("baseProfile", "none", elements=["svg"]),
    DefaultAttribute(
        "preserveAspectRatio",
        "xMidYMid meet",
        elements=["feImage", "image", "marker", "pattern", "svg", "symbol", "view"],
    ),
    # common attributes / basic types
    DefaultAttribute(
        "x",
        0,
        elements=[
            "cursor",
            "fePointLight",
            "feSpotLight",
            "foreignObject",
            "image",
            "pattern",
            "rect",
            "svg",
            "text",
            "use",
        ],
    ),
    DefaultAttribute(
        "y",
        0,
        elements=[
            "cursor",
            "fePointLight",
            "feSpotLight",
            "foreignObject",
            "image",
            "pattern",
            "rect",
            "svg",
            "text",
            "use",
        ],
    ),
    DefaultAttribute("z", 0, elements=["fePointLight", "feSpotLight"]),
    DefaultAttribute("x1", 0, elements=["line"]),
    DefaultAttribute("y1", 0, elements=["line"]),
    DefaultAttribute("x2", 0, elements=["line"]),
    DefaultAttribute("y2", 0, elements=["line"]),
    DefaultAttribute("cx", 0, elements=["circle", "ellipse"]),
    DefaultAttribute("cy", 0, elements=["circle", "ellipse"]),
    # markers
    DefaultAttribute("markerUnits", "strokeWidth", elements=["marker"]),
    DefaultAttribute("refX", 0, elements=["marker"]),
    DefaultAttribute("refY", 0, elements=["marker"]),
    DefaultAttribute("markerHeight", 3, elements=["marker"]),
    DefaultAttribute("markerWidth", 3, elements=["marker"]),
    DefaultAttribute("orient", 0, elements=["marker"]),
    # text / textPath / tspan / tref
    DefaultAttribute("lengthAdjust", "spacing", elements=["text", "textPath", "tref", "tspan"]),
    DefaultAttribute("startOffset", 0, elements=["textPath"]),
    DefaultAttribute("method", "align", elements=["textPath"]),
    DefaultAttribute("spacing", "exact", elements=["textPath"]),
    # filters and masks
    DefaultAttribute("x", -10, Unit.PCT, ["filter", "mask"]),
    DefaultAttribute(
        "x",
        -0.1,
        Unit.NONE,
        ["filter", "mask"],
        conditions=lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse",
    ),
    DefaultAttribute("y", -10, Unit.PCT, ["filter", "mask"]),
    DefaultAttribute(
        "y",
        -0.1,
        Unit.NONE,
        ["filter", "mask"],
        conditions=lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse",
    ),
    DefaultAttribute("width", 120, Unit.PCT, ["filter", "mask"]),
    DefaultAttribute(
        "width",
        1.2,
        Unit.NONE,
        ["filter", "mask"],
        conditions=lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse",
    ),
    DefaultAttribute("height", 120, Unit.PCT, ["filter", "mask"]),
    DefaultAttribute(
        "height",
        1.2,
        Unit.NONE,
        ["filter", "mask"],
        conditions=lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse",
    ),
    # gradients
    DefaultAttribute("x1", 0, elements=["linearGradient"]),
    DefaultAttribute("y1", 0, elements=["linearGradient"]),
    DefaultAttribute("y2", 0, elements=["linearGradient"]),
    DefaultAttribute("x2", 100, Unit.PCT, elements=["linearGradient"]),
    DefaultAttribute(
        "x2",
        1,
        Unit.NONE,
        elements=["linearGradient"],
        conditions=(lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse"),
    ),
    # remove fx/fy before cx/cy to catch the case where fx = cx = 50%
    # or fy = cy = 50% respectively
    DefaultAttribute(
        "fx",
        elements=["radialGradient"],
        conditions=(lambda node: node.getAttribute("fx") == node.getAttribute("cx")),
    ),
    DefaultAttribute(
        "fy",
        elements=["radialGradient"],
        conditions=(lambda node: node.getAttribute("fy") == node.getAttribute("cy")),
    ),
    DefaultAttribute("r", 50, Unit.PCT, elements=["radialGradient"]),
    DefaultAttribute(
        "r",
        0.5,
        Unit.NONE,
        elements=["radialGradient"],
        conditions=(lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse"),
    ),
    DefaultAttribute("cx", 50, Unit.PCT, elements=["radialGradient"]),
    DefaultAttribute(
        "cx",
        0.5,
        Unit.NONE,
        elements=["radialGradient"],
        conditions=(lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse"),
    ),
    DefaultAttribute("cy", 50, Unit.PCT, elements=["radialGradient"]),
    DefaultAttribute(
        "cy",
        0.5,
        Unit.NONE,
        elements=["radialGradient"],
        conditions=(lambda node: node.getAttribute("gradientUnits") != "userSpaceOnUse"),
    ),
    DefaultAttribute("spreadMethod", "pad", elements=["linearGradient", "radialGradient"]),
    # filter effects
    # TODO: Some numerical attributes allow an optional second value
    # ("number-optional-number")
    # and are currently handled as strings to avoid an exception in
    # 'SVGLength', see
    # https://github.com/scour-project/scour/pull/192
    DefaultAttribute("amplitude", 1, elements=["feFuncA", "feFuncB", "feFuncG", "feFuncR"]),
    DefaultAttribute("azimuth", 0, elements=["feDistantLight"]),
    DefaultAttribute("baseFrequency", "0", elements=["feFuncA", "feFuncB", "feFuncG", "feFuncR"]),
    DefaultAttribute("bias", 1, elements=["feConvolveMatrix"]),
    DefaultAttribute("diffuseConstant", 1, elements=["feDiffuseLighting"]),
    DefaultAttribute("edgeMode", "duplicate", elements=["feConvolveMatrix"]),
    DefaultAttribute("elevation", 0, elements=["feDistantLight"]),
    DefaultAttribute("exponent", 1, elements=["feFuncA", "feFuncB", "feFuncG", "feFuncR"]),
    DefaultAttribute("intercept", 0, elements=["feFuncA", "feFuncB", "feFuncG", "feFuncR"]),
    DefaultAttribute("k1", 0, elements=["feComposite"]),
    DefaultAttribute("k2", 0, elements=["feComposite"]),
    DefaultAttribute("k3", 0, elements=["feComposite"]),
    DefaultAttribute("k4", 0, elements=["feComposite"]),
    DefaultAttribute("mode", "normal", elements=["feBlend"]),
    DefaultAttribute("numOctaves", 1, elements=["feTurbulence"]),
    DefaultAttribute("offset", 0, elements=["feFuncA", "feFuncB", "feFuncG", "feFuncR"]),
    DefaultAttribute("operator", "over", elements=["feComposite"]),
    DefaultAttribute("operator", "erode", elements=["feMorphology"]),
    DefaultAttribute("order", "3", elements=["feConvolveMatrix"]),
    DefaultAttribute("pointsAtX", 0, elements=["feSpotLight"]),
    DefaultAttribute("pointsAtY", 0, elements=["feSpotLight"]),
    DefaultAttribute("pointsAtZ", 0, elements=["feSpotLight"]),
    DefaultAttribute("preserveAlpha", "false", elements=["feConvolveMatrix"]),
    DefaultAttribute("radius", "0", elements=["feMorphology"]),
    DefaultAttribute("scale", 0, elements=["feDisplacementMap"]),
    DefaultAttribute("seed", 0, elements=["feTurbulence"]),
    DefaultAttribute("specularConstant", 1, elements=["feSpecularLighting"]),
    DefaultAttribute("specularExponent", 1, elements=["feSpecularLighting", "feSpotLight"]),
    DefaultAttribute("stdDeviation", "0", elements=["feGaussianBlur"]),
    DefaultAttribute("stitchTiles", "noStitch", elements=["feTurbulence"]),
    DefaultAttribute("surfaceScale", 1, elements=["feDiffuseLighting", "feSpecularLighting"]),
    DefaultAttribute("type", "matrix", elements=["feColorMatrix"]),
    DefaultAttribute("type", "turbulence", elements=["feTurbulence"]),
    DefaultAttribute("xChannelSelector", "A", elements=["feDisplacementMap"]),
    DefaultAttribute("yChannelSelector", "A", elements=["feDisplacementMap"]),
]


# A list of default poperties that are safe to remove
#
# Sources for this list:
# 	 https://www.w3.org/TR/SVG/propidx.html			  (implemented)
# 	 https://www.w3.org/TR/SVGTiny12/attributeTable.html (implemented)
# 	 https://www.w3.org/TR/SVG2/propidx.html			 (not yet implemented)
#
# excluded all properties with 'auto' as default.
#
# excluded visibility:visible, since visibility can
# be defined on an element inside an hidden group
# and it will override group inheritance.
# TODO: check if other default properties are overriding group inheritance.
#
default_properties = {
    # SVG 1.1 presentation attributes
    "baseline-shift": "baseline",
    "clip-path": "none",
    "clip-rule": "nonzero",
    "color": "#000",
    "color-interpolation-filters": "linearRGB",
    "color-interpolation": "sRGB",
    "direction": "ltr",
    "display": "inline",
    "enable-background": "accumulate",
    "fill": "#000",
    "fill-opacity": "1",
    "fill-rule": "nonzero",
    "filter": "none",
    "flood-color": "#000",
    "flood-opacity": "1",
    "font-size-adjust": "none",
    "font-size": "medium",
    "font-stretch": "normal",
    "font-style": "normal",
    "font-variant": "normal",
    "font-weight": "normal",
    "glyph-orientation-horizontal": "0deg",
    "letter-spacing": "normal",
    "lighting-color": "#fff",
    "marker": "none",
    "marker-start": "none",
    "marker-mid": "none",
    "marker-end": "none",
    "mask": "none",
    "opacity": "1",
    "pointer-events": "visiblePainted",
    "stop-color": "#000",
    "stop-opacity": "1",
    "stroke": "none",
    "stroke-dasharray": "none",
    "stroke-dashoffset": "0",
    "stroke-linecap": "butt",
    "stroke-linejoin": "miter",
    "stroke-miterlimit": "4",
    "stroke-opacity": "1",
    "stroke-width": "1",
    "text-anchor": "start",
    "text-decoration": "none",
    "unicode-bidi": "normal",
    "word-spacing": "normal",
    "writing-mode": "lr-tb",
    # SVG 1.2 tiny properties
    "audio-level": "1",
    "solid-color": "#000",
    "solid-opacity": "1",
    "text-align": "start",
    "vector-effect": "none",
    "viewport-fill": "none",
    "viewport-fill-opacity": "1",
}


# split to increase lookup performance
# TODO: 'default_attributes_universal' is actually empty right now
# - will we ever need it?
# list containing attributes valid for all elements
default_attributes_universal = []
# dict containing lists of attributes valid for individual elements
default_attributes_per_element = defaultdict(list)
for default_attribute in default_attributes:
    if default_attribute.elements is None:
        default_attributes_universal.append(default_attribute)
    else:
        for element in default_attribute.elements:
            default_attributes_per_element[element].append(default_attribute)


def removeDefaultAttributeValues(node, options, tainted=None):
    """'tainted' keeps a set of attributes defined in parent nodes.

    For such attributes, we don't delete attributes with default values."""
    num = 0
    if node.nodeType != Node.ELEMENT_NODE:
        return 0

    if tainted is None:
        tainted = set()

    # Conditionally remove all default attributes defined in
    # 'default_attributes' (a list of 'DefaultAttribute's)
    #
    # For increased performance do not iterate the whole list for each
    # element but run only on valid subsets
    # - 'default_attributes_universal' (attributes valid for all elements)
    # - 'default_attributes_per_element' (attributes specific to one
    #   specific element type)
    for attribute in default_attributes_universal:
        num += removeDefaultAttributeValue(node, attribute)
    if node.nodeName in default_attributes_per_element:
        for attribute in default_attributes_per_element[node.nodeName]:
            num += removeDefaultAttributeValue(node, attribute)

    # Summarily get rid of default properties
    attributes = [node.attributes.item(i).nodeName for i in range(node.attributes.length)]
    for attribute in attributes:
        if attribute not in tainted:
            if attribute in default_properties:
                if node.getAttribute(attribute) == default_properties[attribute]:
                    node.removeAttribute(attribute)
                    num += 1
                else:
                    tainted = taint(tainted, attribute)
    # Properties might also occur as styles, remove them too
    styles = _getStyle(node)
    for attribute in list(styles):
        if attribute not in tainted:
            if attribute in default_properties:
                if styles[attribute] == default_properties[attribute]:
                    del styles[attribute]
                    num += 1
                else:
                    tainted = taint(tainted, attribute)
    _setStyle(node, styles)

    # recurse for our child elements
    for child in node.childNodes:
        num += removeDefaultAttributeValues(child, options, tainted.copy())

    return num


def removeDefaultAttributeValue(node, attribute):
    """
    Removes the DefaultAttribute 'attribute' from 'node' if specified
    conditions are fulfilled

    Warning: Does NOT check if the attribute is actually valid for the
    passed element type for increased performance!
    """
    if not node.hasAttribute(attribute.name):
        return 0

    # differentiate between text and numeric values
    if isinstance(attribute.value, str):
        if node.getAttribute(attribute.name) == attribute.value:
            if (attribute.conditions is None) or attribute.conditions(node):
                node.removeAttribute(attribute.name)
                return 1
    else:
        nodeValue = SVGLength(node.getAttribute(attribute.name))
        if (attribute.value is None) or ((nodeValue.value == attribute.value) and not (nodeValue.units == Unit.INVALID)):
            if (attribute.units is None) or (nodeValue.units == attribute.units) or (isinstance(attribute.units, list) and nodeValue.units in attribute.units):
                if (attribute.conditions is None) or attribute.conditions(node):
                    node.removeAttribute(attribute.name)
                    return 1

    return 0


def taint(taintedSet, taintedAttribute):
    """Adds an attribute to a set of attributes.

    Related attributes are also included."""
    taintedSet.add(taintedAttribute)
    if taintedAttribute == "marker":
        taintedSet |= {"marker-start", "marker-mid", "marker-end"}
    if taintedAttribute in ["marker-start", "marker-mid", "marker-end"]:
        taintedSet.add("marker")
    return taintedSet


def moveCommonAttributesToParentGroup(elem, referencedElements):
    """
    This recursively calls this function on all children of the passed in
    element and then iterates over all child elements and removes common
    inheritable attributes from the children and places them in the parent
    group.  But only if the parent contains nothing but element children and
    whitespace.  The attributes are only removed from the children if the
    children are not referenced by other elements in the document.
    """
    num = 0

    childElements = []
    # recurse first into the children (depth-first)
    for child in elem.childNodes:
        if child.nodeType == Node.ELEMENT_NODE:
            # only add and recurse if the child is not referenced elsewhere
            if child.getAttribute("id") not in referencedElements:
                childElements.append(child)
                num += moveCommonAttributesToParentGroup(child, referencedElements)
        # else if the parent has non-whitespace text children, do not
        # try to move common attributes
        elif child.nodeType == Node.TEXT_NODE and child.nodeValue.strip():
            return num

    # only process the children if there are more than one element
    if len(childElements) <= 1:
        return num

    commonAttrs = {}
    # add all inheritable properties of the first child element
    # FIXME: Note there is a chance that the first child is a set/animate in which case
    # its fill attribute is not what we want to look at, we should look for the first
    # non-animate/set element
    attrList = childElements[0].attributes
    for index in range(attrList.length):
        attr = attrList.item(index)
        # this is most of the inheritable properties from http://www.w3.org/TR/SVG11/propidx.html
        # and http://www.w3.org/TR/SVGTiny12/attributeTable.html
        if attr.nodeName in [
            "clip-rule",
            "display-align",
            "fill",
            "fill-opacity",
            "fill-rule",
            "font",
            "font-family",
            "font-size",
            "font-size-adjust",
            "font-stretch",
            "font-style",
            "font-variant",
            "font-weight",
            "letter-spacing",
            "pointer-events",
            "shape-rendering",
            "stroke",
            "stroke-dasharray",
            "stroke-dashoffset",
            "stroke-linecap",
            "stroke-linejoin",
            "stroke-miterlimit",
            "stroke-opacity",
            "stroke-width",
            "text-anchor",
            "text-decoration",
            "text-rendering",
            "visibility",
            "word-spacing",
            "writing-mode",
        ]:
            # we just add all the attributes from the first child
            commonAttrs[attr.nodeName] = attr.nodeValue

    # for each subsequent child element
    for childNum in range(len(childElements)):
        # skip first child
        if childNum == 0:
            continue

        child = childElements[childNum]
        # if we are on an animateXXX/set element, ignore it
        # (due to the 'fill' attribute)
        if child.localName in [
            "set",
            "animate",
            "animateColor",
            "animateTransform",
            "animateMotion",
        ]:
            continue

        distinctAttrs = []
        # loop through all current 'common' attributes
        for name in commonAttrs:
            # if this child doesn't match that attribute, schedule it for
            # removal
            if child.getAttribute(name) != commonAttrs[name]:
                distinctAttrs.append(name)
        # remove those attributes which are not common
        for name in distinctAttrs:
            del commonAttrs[name]

    # commonAttrs now has all the inheritable attributes which are common
    # among all child elements
    for name in commonAttrs:
        for child in childElements:
            child.removeAttribute(name)
        elem.setAttribute(name, commonAttrs[name])

    # update our statistic (we remove N*M attributes and add back in M attributes)
    num += (len(childElements) - 1) * len(commonAttrs)
    return num


def remove_comments(element):
    """
    Removes comments from the element and its children.
    """

    if isinstance(element, xml.dom.minidom.Comment):
        element.parentNode.removeChild(element)
    else:
        for subelement in list(element.childNodes):
            if subelement.nodeType == Node.COMMENT_NODE:
                element.removeChild(subelement)
            elif subelement.nodeType == Node.ELEMENT_NODE:
                remove_comments(subelement)


def findReferencingProperty(node, prop, val, ids):
    global referencingProps
    if prop in referencingProps and val != "":
        if len(val) >= 7 and val[0:5] == "url(#":
            id = val[5 : val.find(")")]
            if id in ids:
                ids[id].add(node)
            else:
                ids[id] = {node}
        # if the url has a quote in it, we need to compensate
        elif len(val) >= 8:
            id = None
            # double-quote
            if val[0:6] == 'url("#':
                id = val[6 : val.find('")')]
            # single-quote
            elif val[0:6] == "url('#":
                id = val[6 : val.find("')")]
            if id is not None:
                if id in ids:
                    ids[id].add(node)
                else:
                    ids[id] = {node}
    if prop == "values" and val != "":
        id = remove_prefix(val, "#")
        if id is not None:
            if id in ids:
                ids[id].add(node)
            else:
                ids[id] = {node}


def removeUnusedDefs(doc, defElem, elemsToRemove=None, referencedIDs=None):
    if elemsToRemove is None:
        elemsToRemove = []

    # removeUnusedDefs do not change the XML itself; therefore there is no point in
    # recomputing findReferencedElements when we recurse into child nodes.
    if referencedIDs is None:
        referencedIDs = findReferencedElements(doc.documentElement)

    # keepTags = ["font", "style", "metadata", "script", "title", "desc"]
    keepTags = ["font", "style"]
    for elem in defElem.childNodes:
        # only look at it if an element and not referenced anywhere else
        if elem.nodeType != Node.ELEMENT_NODE:
            continue

        elem_id = elem.getAttribute("id")

        if elem_id == "" or elem_id not in referencedIDs:
            # we only inspect the children of a group in a defs if the group
            # is not referenced anywhere else
            if elem.nodeName == "g" and elem.namespaceURI == NS["SVG"]:
                elemsToRemove = removeUnusedDefs(doc, elem, elemsToRemove, referencedIDs=referencedIDs)
            # we only remove if it is not one of our tags we always keep (see above)
            elif elem.nodeName not in keepTags:
                elemsToRemove.append(elem)
    return elemsToRemove


def remove_unreferenced_elements(doc, keepDefs):
    """
    Removes all unreferenced elements except for <svg>, <font>, <metadata>,
    <title>, and <desc>.
    Also vacuums the defs of any non-referenced renderable elements.

    Returns the number of unreferenced elements removed from the document.
    """
    num = 0

    # Remove certain unreferenced elements outside of defs
    removeTags = ["linearGradient", "radialGradient", "pattern"]

    identifiedElements = findElementsWithId(doc.documentElement)
    referencedIDs = findReferencedElements(doc.documentElement)

    if not keepDefs:
        # Remove most unreferenced elements inside defs
        defs = doc.documentElement.getElementsByTagName("defs")
        for aDef in defs:
            elemsToRemove = removeUnusedDefs(doc, aDef, referencedIDs=referencedIDs)
            for elem in elemsToRemove:
                elem.parentNode.removeChild(elem)
            num += len(elemsToRemove)

    for id in identifiedElements:
        if id not in referencedIDs:
            goner = identifiedElements[id]
            if goner is not None and goner.nodeName in removeTags and goner.parentNode is not None and goner.parentNode.tagName != "defs" and goner.parentNode.nodeName != "defs":
                goner.parentNode.removeChild(goner)
                num += 1

    return num


def remove_duplicate_gradient_stops(doc, options):
    num = 0

    for gradType in ["linearGradient", "radialGradient"]:
        for grad in doc.getElementsByTagName(gradType):
            stops = {}
            stopsToRemove = []
            for stop in grad.getElementsByTagName("stop"):
                # convert percentages into a floating point number
                offsetU = SVGLength(stop.getAttribute("offset"))
                if offsetU.units == Unit.PCT:
                    offset = offsetU.value / 100.0
                elif offsetU.units == Unit.NONE:
                    offset = offsetU.value
                else:
                    offset = 0
                # set the stop offset value to the integer or floating point equivalent
                if int(offset) == offset:
                    stop.setAttribute("offset", str(int(offset)))
                else:
                    stop.setAttribute("offset", str(offset))

                color = stop.getAttribute("stop-color")
                opacity = stop.getAttribute("stop-opacity")
                style = stop.getAttribute("style")
                if offset in stops:
                    oldStop = stops[offset]
                    if oldStop[0] == color and oldStop[1] == opacity and oldStop[2] == style:
                        stopsToRemove.append(stop)
                stops[offset] = [color, opacity, style]

            for stop in stopsToRemove:
                stop.parentNode.removeChild(stop)
            num += len(stopsToRemove)

    return num


def collapse_singly_referenced_gradients(doc, options):
    num = 0

    identifiedElements = findElementsWithId(doc.documentElement)

    # make sure to reset the ref'ed ids for when we are running this in testscour
    for rid, nodes in findReferencedElements(doc.documentElement).items():
        # Make sure that there's actually a defining element for the current ID name.
        # (Cyn: I've seen documents with #id references but no element with that ID!)
        if len(nodes) == 1 and rid in identifiedElements:
            elem = identifiedElements[rid]
            if elem is not None and elem.nodeType == Node.ELEMENT_NODE and elem.nodeName in ["linearGradient", "radialGradient"] and elem.namespaceURI == NS["SVG"]:
                # found a gradient that is referenced by only 1 other element
                refElem = nodes.pop()
                if refElem.nodeType == Node.ELEMENT_NODE and refElem.nodeName in ["linearGradient", "radialGradient"] and refElem.namespaceURI == NS["SVG"]:
                    # elem is a gradient referenced by only one other
                    # gradient (refElem)

                    # add the stops to the referencing gradient
                    # (this removes them from elem)
                    if len(refElem.getElementsByTagName("stop")) == 0:
                        stopsToAdd = elem.getElementsByTagName("stop")
                        for stop in stopsToAdd:
                            refElem.appendChild(stop)

                    # adopt the gradientUnits, spreadMethod,
                    # gradientTransform attributes if unspecified on refElem
                    for attr in ["gradientUnits", "spreadMethod", "gradientTransform"]:
                        if refElem.getAttribute(attr) == "" and not elem.getAttribute(attr) == "":
                            refElem.setAttributeNS(None, attr, elem.getAttribute(attr))

                    # if both are radialGradients, adopt elem's
                    # fx,fy,cx,cy,r attributes if unspecified on refElem
                    if elem.nodeName == "radialGradient" and refElem.nodeName == "radialGradient":
                        for attr in ["fx", "fy", "cx", "cy", "r"]:
                            if refElem.getAttribute(attr) == "" and not elem.getAttribute(attr) == "":
                                refElem.setAttributeNS(None, attr, elem.getAttribute(attr))

                    # if both are linearGradients, adopt elem's
                    # x1,y1,x2,y2 attributes if unspecified on refElem
                    if elem.nodeName == "linearGradient" and refElem.nodeName == "linearGradient":
                        for attr in ["x1", "y1", "x2", "y2"]:
                            if refElem.getAttribute(attr) == "" and not elem.getAttribute(attr) == "":
                                refElem.setAttributeNS(None, attr, elem.getAttribute(attr))

                    target_href = elem.getAttributeNS(NS["XLINK"], "href")
                    if target_href:
                        # If the elem node had an xlink:href, then the
                        # refElem have to point to it as well to
                        # preserve the semantics of the image.
                        refElem.setAttributeNS(NS["XLINK"], "href", target_href)
                    else:
                        # The elem node had no xlink:href reference,
                        # so we can simply remove the attribute.
                        refElem.removeAttributeNS(NS["XLINK"], "href")

                    # now delete elem
                    elem.parentNode.removeChild(elem)
                    num += 1

    return num


def computeGradientBucketKey(grad):
    # Compute a key (hashable opaque value; here a string) from each
    # gradient such that "key(grad1) == key(grad2)" is the same as
    # saying that grad1 is a duplicate of grad2.
    gradBucketAttr = [
        "gradientUnits",
        "spreadMethod",
        "gradientTransform",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "fx",
        "fy",
        "r",
    ]
    gradStopBucketsAttr = ["offset", "stop-color", "stop-opacity", "style"]

    # A linearGradient can never be a duplicate of a
    # radialGradient (and vice versa)
    subKeys = [grad.getAttribute(a) for a in gradBucketAttr]
    subKeys.append(grad.getAttributeNS(NS["XLINK"], "href"))
    stops = grad.getElementsByTagName("stop")
    if stops.length:
        for i in range(stops.length):
            stop = stops.item(i)
            for attr in gradStopBucketsAttr:
                stopKey = stop.getAttribute(attr)
                subKeys.append(stopKey)

    # Use a raw ASCII "record separator" control character as it is
    # not likely to be used in any of these values (without having to
    # be escaped).
    return "\x1e".join(subKeys)


def detect_duplicate_gradients(*grad_lists):
    """Detects duplicate gradients from each iterable/generator given as
    argument

    Yields (master_id, duplicates_id, duplicates) tuples where:
      * master_id: The ID attribute of the master element. This will
            always be non-empty and not None as long at least one of the
            gradients have a valid ID.
      * duplicates_id: List of ID attributes of the duplicate gradients
            elements (can be empty where the gradient had no ID attribute)
      * duplicates: List of elements that are duplicates of the
            `master` element. Will never include the `master` element.
            Has the same order as `duplicates_id` - i.e.
            `duplicates[X].getAttribute("id") == duplicates_id[X]`.
    """
    for grads in grad_lists:
        grad_buckets = defaultdict(list)

        for grad in grads:
            key = computeGradientBucketKey(grad)
            grad_buckets[key].append(grad)

        for bucket in grad_buckets.values():
            if len(bucket) < 2:
                # The gradient must be unique if it is the only one in
                # this bucket.
                continue
            master = bucket[0]
            duplicates = bucket[1:]
            duplicates_ids = [d.getAttribute("id") for d in duplicates]
            master_id = master.getAttribute("id")
            if not master_id:
                # If our selected "master" copy does not have an ID,
                # then replace it with one that does (assuming any of
                # them have one).  This avoids broken images like we
                # saw in GH#203
                for i in range(len(duplicates_ids)):
                    dup_id = duplicates_ids[i]
                    if dup_id:
                        # We do not bother updating the master field
                        # as it is not used any more.
                        master_id = duplicates_ids[i]
                        duplicates[i] = master
                        # Clear the old id to avoid a redundant remapping
                        duplicates_ids[i] = ""
                        break

            yield master_id, duplicates_ids, duplicates


def dedup_gradient(master_id, duplicates_ids, duplicates, referenced_ids):
    func_iri = None
    for dup_id, dup_grad in zip(duplicates_ids, duplicates, strict=False):
        # if the duplicate gradient no longer has a parent that means it was
        # already re-mapped to another master gradient
        if not dup_grad.parentNode:
            continue

        # With --keep-unreferenced-defs, we can end up with
        # unreferenced gradients.  See GH#156.
        if dup_id in referenced_ids:
            if func_iri is None:
                # matches url(#<ANY_DUP_ID>), url('#<ANY_DUP_ID>')
                # and url("#<ANY_DUP_ID>")
                dup_id_regex = "|".join(duplicates_ids)
                func_iri = re.compile("url\\(['\"]?#(?:" + dup_id_regex + ")['\"]?\\)")
            for elem in referenced_ids[dup_id]:
                # find out which attribute referenced the duplicate gradient
                for attr in ["fill", "stroke"]:
                    v = elem.getAttribute(attr)
                    (v_new, n) = func_iri.subn("url(#" + master_id + ")", v)
                    if n > 0:
                        elem.setAttribute(attr, v_new)
                if elem.getAttributeNS(NS["XLINK"], "href") == "#" + dup_id:
                    elem.setAttributeNS(NS["XLINK"], "href", "#" + master_id)
                styles = _getStyle(elem)
                for style in styles:
                    v = styles[style]
                    (v_new, n) = func_iri.subn("url(#" + master_id + ")", v)
                    if n > 0:
                        styles[style] = v_new
                _setStyle(elem, styles)

        # now that all referencing elements have been re-mapped to the master
        # it is safe to remove this gradient from the document
        dup_grad.parentNode.removeChild(dup_grad)

    # If the gradients have an ID, we update referenced_ids to match
    # the newly remapped IDs. This enable us to avoid calling
    # findReferencedElements once per loop, which is helpful as it is
    # one of the slowest functions in scour.
    if master_id:
        try:
            master_references = referenced_ids[master_id]
        except KeyError:
            master_references = set()

        for dup_id in duplicates_ids:
            references = referenced_ids.pop(dup_id, None)
            if references is None:
                continue
            master_references.update(references)

        # Only necessary but needed if the master gradient did
        # not have any references originally
        referenced_ids[master_id] = master_references


def removeDuplicateGradients(doc):
    prev_num = -1
    num = 0

    # get a collection of all elements that are referenced and their
    # referencing elements
    referenced_ids = findReferencedElements(doc.documentElement)

    while prev_num != num:
        prev_num = num

        linear_gradients = doc.getElementsByTagName("linearGradient")
        radial_gradients = doc.getElementsByTagName("radialGradient")

        for master_id, duplicates_ids, duplicates in detect_duplicate_gradients(linear_gradients, radial_gradients):
            dedup_gradient(master_id, duplicates_ids, duplicates, referenced_ids)
            num += len(duplicates)

    return num


def embed_rasters(element, options):
    """
    Converts raster references to inline images.
    NOTE: there are size limits to base64-encoding handling in browsers
    """
    num_rasters_embedded = 0

    href = element.getAttributeNS(NS["XLINK"], "href")

    # if xlink:href is set, then grab the id
    if href != "" and len(href) > 1:
        ext = os.path.splitext(os.path.basename(href))[1].lower()[1:]

        # only operate on files with 'png', 'jpg', and 'gif' file extensions
        if ext in ["png", "jpg", "gif"]:
            # fix common issues with file paths
            href_fixed = href.replace("\\", "/")
            href_fixed = re.sub("file:/+", "file:///", href_fixed)

            # parse the URI to get scheme and path
            parsed_href = urllib.parse.urlparse(href_fixed)

            # assume locations without protocol point to local files
            # (and should use the 'file:' protocol)
            if parsed_href.scheme == "":
                parsed_href = parsed_href._replace(scheme="file")
                if href_fixed[0] == "/":
                    href_fixed = "file://" + href_fixed
                else:
                    href_fixed = "file:" + href_fixed

            # relative local paths are relative to the input file,
            # therefore temporarily change the working dir
            working_dir_old = None
            if parsed_href.scheme == "file" and parsed_href.path[0] != "/":
                if options.infilename:
                    working_dir_old = os.getcwd()
                    working_dir_new = os.path.abspath(os.path.dirname(options.infilename))
                    os.chdir(working_dir_new)

            # open/download the file
            try:
                file = urllib.request.urlopen(href_fixed)
                rasterdata = file.read()
                file.close()
            except Exception as e:
                add2log("WARNING: could not open file '" + href + "' for embedding. The raster image will be kept as " + "a reference but might be invalid. File: " + f"{current_filepath}" + "(Exception details: " + str(e) + ")")
                rasterdata = ""
            finally:
                # always restore initial working directory if we changed it above
                if working_dir_old is not None:
                    os.chdir(working_dir_old)

            if rasterdata != "":
                # base64-encode raster
                b64eRaster = base64.b64encode(rasterdata)

                # set href attribute to base64-encoded equivalent
                if b64eRaster != "":
                    # PNG and GIF both have MIME Type 'image/[ext]', but
                    # JPEG has MIME Type 'image/jpeg'
                    if ext == "jpg":
                        ext = "jpeg"

                    element.setAttributeNS(
                        NS["XLINK"],
                        "href",
                        "data:image/" + ext + ";base64," + b64eRaster.decode(),
                    )
                    num_rasters_embedded += 1
                    del b64eRaster
    return num_rasters_embedded


def properlySizeDoc(docElement, options):
    # get doc width and height
    if docElement.hasAttribute("width"):
        w = SVGLength(docElement.getAttribute("width"))
    else:
        w = SVGLength("1024px")

    if docElement.hasAttribute("height"):
        h = SVGLength(docElement.getAttribute("height"))
    else:
        h = SVGLength("768px")

    # if width/height are not unitless or px then it is not ok to
    # rewrite them into a viewBox. well, it may be OK for Web browsers
    # and vector editors, but not for librsvg.
    # if options.renderer_workaround:
    #     if ((w.units != Unit.NONE and w.units != Unit.PX) or
    #             (h.units != Unit.NONE and h.units != Unit.PX)):
    #         return

    # else we have a statically sized image and we should try to
    # remedy that

    if docElement.hasAttribute("viewBox") is False:
        # CRITICAL: svg2fbf requires viewBox for frame-by-frame
        # animations
        # Why: Defaulting to arbitrary dimensions causes inconsistent
        # frame sizing
        ppp(f'\n❌ ERROR IMPORTING FRAMES: The file "{current_filepath}" is missing the viewBox attribute.')
        ppp(f'   Use the global command "svg-repair-viewbox {current_filepath}" to fix it.')
        ppp("   Or run: svg-repair-viewbox <input_folder>/ to fix all SVG files in a directory.\n")
        sys.exit(1)

    # parse viewBox attribute
    vbSep = RE_COMMA_WSP.split(docElement.getAttribute("viewBox"))
    # if we have a valid viewBox we need to check it
    if len(vbSep) == 4:
        try:
            # if x or y are specified and non-zero then it is not ok to overwrite it
            vbX = float(vbSep[0])
            vbY = float(vbSep[1])
            if vbX != 0 or vbY != 0:
                return

            # if width or height are not equal to doc width/height then
            # it is not ok to overwrite it
            vbWidth = float(vbSep[2])
            vbHeight = float(vbSep[3])
            if vbWidth != w.value or vbHeight != h.value:
                return
        # if the viewBox did not parse properly it is invalid and ok
        # to overwrite it
        except ValueError:
            pass

    # at this point it's safe to set the viewBox and remove width/height
    docElement.setAttribute("viewBox", f"0 0 {w.value} {h.value}")
    if docElement.hasAttribute("width"):
        docElement.removeAttribute("width")
    if docElement.hasAttribute("height"):
        docElement.removeAttribute("height")


def get_viewbox_from_svg(svg_root):
    """Get viewBox as (x, y, w, h), synthesizing from width/height if missing."""
    vb_str = svg_root.getAttribute("viewBox")

    if vb_str and vb_str.strip():
        vbSep = RE_COMMA_WSP.split(vb_str)
        if len(vbSep) == 4:
            return tuple(float(v) for v in vbSep)

    # No viewBox: synthesize from width/height
    width_str = svg_root.getAttribute("width")
    height_str = svg_root.getAttribute("height")

    if width_str and height_str:
        w = SVGLength(width_str).value
        h = SVGLength(height_str).value
        return 0.0, 0.0, w, h

    raise Exception("Cannot determine viewBox: missing both viewBox and usable width/height")


def create_scaled_group_for_svg(svg_root, target_viewbox, align_mode="center"):
    """Wrap svg_root content in a group with transform to fit into target_viewbox.

    Modifies svg_root in-place by:
    1. Wrapping all content in a transform group
    2. Setting svg_root's width, height, viewBox to match target

    Args:
        svg_root: Source SVG root element (will be modified in-place)
        target_viewbox: Tuple (x, y, w, h) of target viewBox
        align_mode: "center" or "top-left"

    Returns:
        The modified svg_root element with target dimensions
    """
    # Get source viewBox
    x2, y2, w2, h2 = get_viewbox_from_svg(svg_root)
    x1, y1, w1, h1 = target_viewbox

    # Compute uniform contain scale factor
    sx = w1 / w2 if w2 > 0 else 1.0
    sy = h1 / h2 if h2 > 0 else 1.0
    s = min(sx, sy)

    # Compute translation based on align_mode
    if align_mode == "top-left":
        tx = x1 - s * x2
        ty = y1 - s * y2
    elif align_mode == "center":
        c1x = x1 + w1 / 2.0
        c1y = y1 + h1 / 2.0
        c2x = x2 + w2 / 2.0
        c2y = y2 + h2 / 2.0
        tx = c1x - s * c2x
        ty = c1y - s * c2y
    else:
        raise Exception("Unknown align_mode, use 'top-left' or 'center'")

    # Build transform string (matrix(a b c d e f))
    transform_str = f"matrix({s} 0 0 {s} {tx} {ty})"

    # Create wrapper group (using same document as svg_root)
    wrapper_g = svg_root.ownerDocument.createElement("g")
    wrapper_g.setAttribute("transform", transform_str)

    # Move all children from svg_root into wrapper_g
    children_to_move = []
    for child in svg_root.childNodes:
        if child.nodeType == child.ELEMENT_NODE:
            # Skip metadata, title, desc
            if child.nodeName not in ["metadata", "title", "desc"]:
                children_to_move.append(child)

    for child in children_to_move:
        svg_root.removeChild(child)
        wrapper_g.appendChild(child)

    # Append wrapper_g to svg_root
    svg_root.appendChild(wrapper_g)

    # STEP 8: Set svg_root's dimensions and viewBox to match target
    # Now svg_root has scaled content and should have target's resolution
    svg_root.setAttribute("width", f"{w1}px")
    svg_root.setAttribute("height", f"{h1}px")
    svg_root.setAttribute("viewBox", f"{x1} {y1} {w1} {h1}")

    return svg_root


def findElementsWithId(node, elems=None):
    """
    Returns all elements with id attributes
    """
    if elems is None:
        elems = {}
    id = node.getAttribute("id")
    if id != "":
        elems[id] = node
    if node.hasChildNodes():
        for child in node.childNodes:
            # from http://www.w3.org/TR/DOM-Level-2-Core/idl-definitions.html
            # we are only really interested in nodes of type Element (1)
            if child.nodeType not in NODE_TYPES_TO_IGNORE:
                findElementsWithId(child, elems)
    return elems


def findElementsWithoutIdAndAddId(node, elems=None):
    """
    Find all elements without id attributes and add a randomly
    generated id to them.
    """
    if node.nodeType not in NODE_TYPES_TO_IGNORE:  # == Node.ELEMENT_NODE:
        if elems is None:
            elems = {}
        id = node.getAttribute("id")
        if id == "" or id is None:
            newid = "FB" + str(uuid.uuid4().hex)
            node.setAttribute("id", newid)
            elems[newid] = node

    if node.hasChildNodes():
        for child in node.childNodes:
            # from http://www.w3.org/TR/DOM-Level-2-Core/idl-definitions.html
            # we are only really interested in nodes of type Element (1)
            if child.nodeType not in NODE_TYPES_TO_IGNORE:  # == Node.ELEMENT_NODE:
                findElementsWithoutIdAndAddId(child, elems)
    return elems


def _getStyle(node):
    """Returns the style attribute of a node as a dictionary."""
    if node.nodeType != Node.ELEMENT_NODE:
        return {}
    style_attribute = node.getAttribute("style")
    if style_attribute:
        styleMap = {}
        rawStyles = style_attribute.split(";")
        for style in rawStyles:
            propval = style.split(":")
            if len(propval) == 2:
                styleMap[propval[0].strip()] = propval[1].strip()
        return styleMap
    else:
        return {}


def _setStyle(node, styleMap):
    """Sets the style attribute of a node to the dictionary ``styleMap``."""
    fixedStyle = ";".join(prop + ":" + styleMap[prop] for prop in styleMap)
    if fixedStyle != "":
        node.setAttribute("style", fixedStyle)
    elif node.getAttribute("style"):
        node.removeAttribute("style")
    return node


def repairStyle(node, options):
    num = 0
    global framerules
    styleMap = _getStyle(node)
    if styleMap:
        # I've seen this enough to know that I need to correct it:
        # fill: url(#linearGradient4918) rgb(0, 0, 0);
        for prop in ["fill", "stroke"]:
            if prop in styleMap:
                chunk = styleMap[prop].split(") ")
                if len(chunk) == 2 and (chunk[0][:5] == "url(#" or chunk[0][:6] == 'url("#' or chunk[0][:6] == "url('#") and chunk[1] == "rgb(0, 0, 0)":
                    styleMap[prop] = chunk[0] + ")"
                    num += 1

        # Here is where we can weed out unnecessary styles
        # TODO: check if attribute/style is not animated, otherwise
        # do not remove it!

        #  opacity:1
        if "opacity" in styleMap:
            opacity = float(styleMap["opacity"])
            # if opacity='0' then all fill and stroke properties are
            # useless, remove them
            if opacity == 0.0:
                for uselessStyle in [
                    "fill",
                    "fill-opacity",
                    "fill-rule",
                    "stroke",
                    "stroke-linejoin",
                    "stroke-opacity",
                    "stroke-miterlimit",
                    "stroke-linecap",
                    "stroke-dasharray",
                    "stroke-dashoffset",
                    "stroke-opacity",
                ]:
                    if uselessStyle in styleMap and not styleInheritedByChild(node, uselessStyle):
                        del styleMap[uselessStyle]
                        num += 1

        #  if stroke:none, then remove all stroke-related properties
        #  (stroke-width, etc)
        #  TODO: should also detect if the computed value of this
        #  element is stroke="none"
        if "stroke" in styleMap and styleMap["stroke"] == "none":
            for strokestyle in [
                "stroke-width",
                "stroke-linejoin",
                "stroke-miterlimit",
                "stroke-linecap",
                "stroke-dasharray",
                "stroke-dashoffset",
                "stroke-opacity",
            ]:
                if strokestyle in styleMap and not styleInheritedByChild(node, strokestyle):
                    del styleMap[strokestyle]
                    num += 1
            # we need to properly calculate computed values
            if not styleInheritedByChild(node, "stroke"):
                if styleInheritedFromParent(node, "stroke") in [None, "none"]:
                    del styleMap["stroke"]
                    num += 1

        #  if fill:none, then remove all fill-related properties (fill-rule, etc)
        if "fill" in styleMap and styleMap["fill"] == "none":
            for fillstyle in ["fill-rule", "fill-opacity"]:
                if fillstyle in styleMap and not styleInheritedByChild(node, fillstyle):
                    del styleMap[fillstyle]
                    num += 1

        #  fill-opacity: 0
        if "fill-opacity" in styleMap:
            fillOpacity = float(styleMap["fill-opacity"])
            if fillOpacity == 0.0:
                for uselessFillStyle in ["fill", "fill-rule"]:
                    if uselessFillStyle in styleMap and not styleInheritedByChild(node, uselessFillStyle):
                        del styleMap[uselessFillStyle]
                        num += 1

        #  stroke-opacity: 0
        if "stroke-opacity" in styleMap:
            strokeOpacity = float(styleMap["stroke-opacity"])
            if strokeOpacity == 0.0:
                for uselessStrokeStyle in [
                    "stroke",
                    "stroke-width",
                    "stroke-linejoin",
                    "stroke-linecap",
                    "stroke-dasharray",
                    "stroke-dashoffset",
                ]:
                    if uselessStrokeStyle in styleMap and not styleInheritedByChild(node, uselessStrokeStyle):
                        del styleMap[uselessStrokeStyle]
                        num += 1

        # stroke-width: 0
        if "stroke-width" in styleMap:
            strokeWidth = SVGLength(styleMap["stroke-width"])
            if strokeWidth.value == 0.0:
                for uselessStrokeStyle in [
                    "stroke",
                    "stroke-linejoin",
                    "stroke-linecap",
                    "stroke-dasharray",
                    "stroke-dashoffset",
                    "stroke-opacity",
                ]:
                    if uselessStrokeStyle in styleMap and not styleInheritedByChild(node, uselessStrokeStyle):
                        del styleMap[uselessStrokeStyle]
                        num += 1

        # remove font properties for non-text elements
        # I've actually observed this in real SVG content
        if not mayContainTextNodes(node):
            for fontstyle in [
                "font-family",
                "font-size",
                "font-stretch",
                "font-size-adjust",
                "font-style",
                "font-variant",
                "font-weight",
                "letter-spacing",
                "line-height",
                "kerning",
                "text-align",
                "text-anchor",
                "text-decoration",
                "text-rendering",
                "unicode-bidi",
                "word-spacing",
                "writing-mode",
            ]:
                if fontstyle in styleMap:
                    del styleMap[fontstyle]
                    num += 1

        # remove inkscape-specific styles
        # TODO: need to get a full list of these
        for inkscapeStyle in ["-inkscape-font-specification"]:
            if inkscapeStyle in styleMap:
                del styleMap[inkscapeStyle]
                num += 1

        if "overflow" in styleMap:
            # remove overflow from elements to which it does not apply,
            # see https://www.w3.org/TR/SVG/masking.html#OverflowProperty
            if node.nodeName not in [
                "svg",
                "symbol",
                "image",
                "foreignObject",
                "marker",
                "pattern",
            ]:
                del styleMap["overflow"]
                num += 1
            # if the node is not the root <svg> element the SVG's user
            # agent style sheet overrides the initial (i.e. default)
            # value with the value 'hidden', which can consequently be
            # removed (see last bullet point in the link above)
            elif node != node.ownerDocument.documentElement:
                if styleMap["overflow"] == "hidden":
                    del styleMap["overflow"]
                    num += 1
            # on the root <svg> element the CSS2 default
            # overflow="visible" is the initial value and we can remove it
            elif styleMap["overflow"] == "visible":
                del styleMap["overflow"]
                num += 1

        # now if any of the properties match known SVG attributes we prefer attributes
        # over style so emit them and remove them from the style map
        props = {}
        rule = {}
        for propName in list(styleMap):
            if node != node.ownerDocument.documentElement:
                if propName in SVG_ATTRIBUTES:
                    node.setAttribute(propName, styleMap[propName])
                    del styleMap[propName]
            else:
                # in case the style was on the svg element, we move it
                # to the frame group
                props[propName.strip()] = styleMap[propName].strip()
                del styleMap[propName]

        # add the frame group props to the framerules for later
        if len(props.items()) > 0:
            if node == node.ownerDocument.documentElement:
                rule["properties"] = props
                rule["selector"] = "svg"
            if framerules is None:
                framerules = []
            framerules.append(rule)

        _setStyle(node, styleMap)

    # recurse for our child elements
    for child in node.childNodes:
        num += repairStyle(child, options)

    return num


def styleInheritedFromParent(node, style):
    """
    Returns the value of 'style' that is inherited from the parents of
    the passed-in node

    Warning: This method only considers presentation attributes and
             inline styles, any style sheets are ignored!
    """
    parentNode = node.parentNode

    # return None if we reached the Document element
    if parentNode.nodeType == Node.DOCUMENT_NODE:
        return None

    # check styles first (they take precedence over presentation attributes)
    styles = _getStyle(parentNode)
    if style in styles:
        value = styles[style]
        if not value == "inherit":
            return value

    # check attributes
    value = parentNode.getAttribute(style)
    if value not in ["", "inherit"]:
        return parentNode.getAttribute(style)

    # check the next parent recursively if we did not find a value yet
    return styleInheritedFromParent(parentNode, style)


def styleInheritedByChild(node, style, nodeIsChild=False):
    """
    Returns whether 'style' is inherited by any children of the passed-in node

    If False is returned, it is guaranteed that 'style' can safely be removed
    from the passed-in node without influencing visual output of it's children

    If True is returned, the passed-in node should not have its
    text-based attributes removed.

    Warning: This method only considers presentation attributes and
             inline styles, any style sheets are ignored!
    """
    # Comment, text and CDATA nodes don't have attributes and aren't
    # containers so they can't inherit attributes
    if node.nodeType != Node.ELEMENT_NODE:
        return False

    if nodeIsChild:
        # if the current child node sets a new value for 'style'
        # we can stop the search in the current branch of the DOM tree

        # check attributes
        if node.getAttribute(style) not in ["", "inherit"]:
            return False
        # check styles
        styles = _getStyle(node)
        if (style in styles) and not (styles[style] == "inherit"):
            return False
    else:
        # if the passed-in node does not have any children 'style'
        # can obviously not be inherited
        if not node.childNodes:
            return False

    # If we have child nodes recursively check those
    if node.childNodes:
        for child in node.childNodes:
            if styleInheritedByChild(child, style, True):
                return True

    # If the current element is a container element the inherited
    # style is meaningless (since we made sure it's not inherited
    # by any of its children)
    if node.nodeName in [
        "a",
        "defs",
        "glyph",
        "g",
        "marker",
        "mask",
        "missing-glyph",
        "pattern",
        "svg",
        "switch",
        "symbol",
    ]:
        return False

    # in all other cases we have to assume the inherited value of
    # 'style' is meaningful and has to be kept (e.g nodes without
    # children at the end of the DOM tree, text nodes, ...)
    return True


def mayContainTextNodes(node):
    """
    Returns True if the passed-in node is probably a text element, or at least
    one of its descendants is probably a text element.

    If False is returned, it is guaranteed that the passed-in node has no
    business having text-based attributes.

    If True is returned, the passed-in node should not have its text-based
    attributes removed.
    """
    # Cached result of a prior call?
    try:
        return node.mayContainTextNodes
    except AttributeError:
        pass

    result = True  # Default value
    # Comment, text and CDATA nodes don't have attributes and aren't containers
    if node.nodeType != Node.ELEMENT_NODE:
        result = False
    # Non-SVG elements? Unknown elements!
    elif node.namespaceURI != NS["SVG"]:
        result = True
    # Blacklisted elements. Those are guaranteed not to be text elements.
    elif node.nodeName in [
        "rect",
        "circle",
        "ellipse",
        "line",
        "polygon",
        "polyline",
        "path",
        "image",
        "stop",
    ]:
        result = False
    # Group elements. If we're missing any here, the default of True is used.
    elif node.nodeName in [
        "g",
        "clipPath",
        "marker",
        "mask",
        "pattern",
        "linearGradient",
        "radialGradient",
        "meshgradient",
        "meshPatch",
        "meshpatchsymbol",
    ]:
        result = False
        for child in node.childNodes:
            if mayContainTextNodes(child):
                result = True
    # Everything else should be considered a future SVG-version text
    # element at best, or an unknown element at worst. result will
    # stay True.

    # Cache this result before returning it.
    node.mayContainTextNodes = result
    return result


def shortenIDs(doc, options):
    """
    Shortens ID names used in the document. ID names referenced the
    most often are assigned the shortest ID names.

    Returns the number of bytes saved by shortening ID names in the
    document.
    """
    num = 0

    # findElementsWithoutIdAndAddId(doc.documentElement)
    identifiedElements = findElementsWithId(doc.documentElement)
    # This map contains maps the (original) ID to the nodes referencing it.
    # At the end of this function, it will no longer be valid and while we
    # could keep it up to date, it will complicate the code for no gain
    # (as we do not reuse the data structure beyond this function).
    referencedIDs = findReferencedElements(doc.documentElement)

    # Make idList (list of idnames) sorted by reference count
    # descending, so the highest reference count is first.
    # First check that there's actually a defining element for the current ID name.
    # (Cyn: I've seen documents with #id references but no element with that ID!)
    idList = [(len(referencedIDs[rid]), rid) for rid in referencedIDs if rid in identifiedElements]
    idList.sort(reverse=True)
    idList = [rid for count, rid in idList]

    # Add unreferenced IDs to end of idList in arbitrary order
    idList.extend([rid for rid in identifiedElements if rid not in idList])

    # IDs that have been allocated and should not be remapped.
    consumedIDs = set()

    # List of IDs that need to be assigned a new ID.  The list is ordered
    # such that earlier entries will be assigned a shorter ID than those
    # later in the list.  IDs in this list *can* obtain an ID that is
    # longer than they already are.
    need_new_id = []

    id_allocations = list(compute_id_lengths(len(idList) + 1))
    # Reverse so we can use it as a stack and still work from "shortest to
    # longest" ID.
    id_allocations.reverse()

    # Here we loop over all current IDs (that we /might/ want to remap)
    # and group them into two.  1) The IDs that already have a perfect
    # length (these are added to consumedIDs) and 2) the IDs that need
    # to change length (these are appended to need_new_id).
    optimal_id_length, id_use_limit = 0, 0
    for current_id in idList:
        # If we are out of IDs of the current length, then move on
        # to the next length
        if id_use_limit < 1:
            optimal_id_length, id_use_limit = id_allocations.pop()
        # Reserve an ID from this length
        id_use_limit -= 1
        # We check for strictly equal to optimal length because our ID
        # remapping may have to assign one node a longer ID because
        # another node needs a shorter ID.
        if len(current_id) == optimal_id_length:
            # This rid is already of optimal length - lets just keep it.
            consumedIDs.add(current_id)
        else:
            # Needs a new (possibly longer) ID.
            need_new_id.append(current_id)

    curIdNum = 1

    for old_id in need_new_id:
        new_id = intToID(curIdNum, "")

        # Skip ahead if the new ID has already been used or is protected.
        while new_id in consumedIDs:
            curIdNum += 1
            new_id = intToID(curIdNum, "")

        # Now that we have found the first available ID, do the remap.
        num += renameID(old_id, new_id, identifiedElements, referencedIDs.get(old_id))
        curIdNum += 1

    return num


def compute_id_lengths(highest):
    """Compute how many IDs are available of a given size

    Example:
            >>> lengths = list(compute_id_lengths(512))
            >>> lengths
            [(1, 26), (2, 676)]
            >>> total_limit = sum(x[1] for x in lengths)
            >>> total_limit
            702
            >>> intToID(total_limit, "")
            'zz'

    Which tells us that we got 26 IDs of length 1 and up to 676 IDs of length two
    if we need to allocate 512 IDs.

    :param highest: Highest ID that need to be allocated
    :return: An iterator that returns tuples of (id-length, use-limit).  The
     use-limit applies only to the given id-length (i.e. it is excluding IDs
     of shorter length).  Note that the sum of the use-limit values is always
     equal to or greater than the highest param.
    """
    step = 26
    id_length = 0
    use_limit = 1
    while highest:
        id_length += 1
        use_limit *= step
        yield (id_length, use_limit)
        highest = int((highest - 1) / step)


def intToID(idnum, prefix):
    """
    Returns the ID name for the given ID number, spreadsheet-style, i.e. from a to z,
    then from aa to az, ba to bz, etc., until zz.
    """
    rid = ""

    while idnum > 0:
        idnum -= 1
        rid = chr((idnum % 26) + ord("a")) + rid
        idnum = int(idnum / 26)

    return prefix + rid


def intToIDPostfix(idnum, prefix, postfix):
    """
    Returns the ID name for the given ID number, spreadsheet-style, i.e. from a to z,
    then from aa to az, ba to bz, etc., until zz.
    """
    rid = ""

    while idnum > 0:
        idnum -= 1
        rid = chr((idnum % 26) + ord("a")) + rid
        idnum = int(idnum / 26)

    return prefix + rid + postfix


def renameID(idFrom, idTo, identifiedElements, referringNodes):
    """
    Changes the ID name from idFrom to idTo, on the declaring element
    as well as all nodes in referringNodes.

    Updates identifiedElements.

    Returns the number of bytes saved by this replacement.
    """

    num = 0

    definingNode = identifiedElements[idFrom]
    definingNode.setAttribute("id", idTo)
    num += len(idFrom) - len(idTo)

    # Update references to renamed node
    if referringNodes is not None:
        # Look for the idFrom ID name in each of the referencing elements,
        # exactly like findReferencedElements would.
        # Cyn: Duplicated processing!

        for node in referringNodes:
            # if this node is a style element, parse its text into CSS
            if node.nodeName == "style" and node.namespaceURI == NS["SVG"]:
                # node.firstChild will be either a CDATA or a Text node now
                if node.firstChild is not None:
                    # concatenate the value of all children, in case
                    # there's a CDATASection node surrounded by whitespace
                    # nodes
                    # (node.normalize() will NOT work here, it only acts on Text nodes)
                    oldValue = "".join(child.nodeValue for child in node.childNodes)
                    # not going to reparse the whole thing
                    newValue = oldValue.replace("url(#" + idFrom + ")", "url(#" + idTo + ")")
                    newValue = newValue.replace("url('#" + idFrom + "')", "url(#" + idTo + ")")
                    newValue = newValue.replace('url("#' + idFrom + '")', "url(#" + idTo + ")")
                    # and now replace all the children with this new stylesheet.
                    # again, this is in case the stylesheet was a CDATASection
                    node.childNodes[:] = [node.ownerDocument.createTextNode(newValue)]

            # if xlink:href is set to #idFrom, then change the id
            href = node.getAttributeNS(NS["XLINK"], "href")
            if href == "#" + idFrom:
                node.setAttributeNS(NS["XLINK"], "href", "#" + idTo)

            # if the style has url(#idFrom), then change the id
            styles = node.getAttribute("style")
            if styles != "":
                newValue = styles.replace("url(#" + idFrom + ")", "url(#" + idTo + ")")
                newValue = newValue.replace("url('#" + idFrom + "')", "url(#" + idTo + ")")
                newValue = newValue.replace('url("#' + idFrom + '")', "url(#" + idTo + ")")
                node.setAttribute("style", newValue)

            # now try the fill, stroke, filter attributes
            for attr in referencingProps:
                oldValue = node.getAttribute(attr)
                if oldValue != "":
                    newValue = oldValue.replace("url(#" + idFrom + ")", "url(#" + idTo + ")")
                    newValue = newValue.replace("url('#" + idFrom + "')", "url(#" + idTo + ")")
                    newValue = newValue.replace('url("#' + idFrom + '")', "url(#" + idTo + ")")
                    node.setAttribute(attr, newValue)

    return num


def remove_nested_groups(node):
    """
    This walks further and further down the tree, removing groups
    which do not have any attributes or a title/desc child and
    promoting their children up one level
    """
    num = 0

    groupsToRemove = []
    # Only consider <g> elements for promotion if this element isn't a <switch>.
    # (partial fix for bug 594930, required by the SVG spec however)
    if not (node.nodeType == Node.ELEMENT_NODE and node.nodeName == "switch"):
        for child in node.childNodes:
            if child.nodeName == "g" and child.namespaceURI == NS["SVG"] and len(child.attributes) == 0:
                # only collapse group if it does not have a title or desc as a
                # direct descendant,
                if g_tag_is_mergeable(child):
                    groupsToRemove.append(child)

    for g in groupsToRemove:
        while g.childNodes.length > 0:
            g.parentNode.insertBefore(g.firstChild, g)
        g.parentNode.removeChild(g)

    num += len(groupsToRemove)

    # now recurse for children
    for child in node.childNodes:
        if child.nodeType not in NODE_TYPES_TO_IGNORE:
            num += remove_nested_groups(child)
    return num


def g_tag_is_mergeable(node):
    """Check if a <g> tag can be merged or not

    <g> tags with a title or descriptions should generally be left alone.

    if any(
            True
            for n in node.childNodes
            if n.nodeType == Node.ELEMENT_NODE
            and n.nodeName in ("title", "desc")
            and n.namespaceURI == NS["SVG"]
    ):
            return False
    """
    return True


def removeUnusedAttributesOnParent(elem):
    """
    This recursively calls this function on all children of the element passed in,
    then removes any unused attributes on this elem if none of the children inherit it
    """
    num = 0

    childElements = []
    # recurse first into the children (depth-first)
    for child in elem.childNodes:
        if child.nodeType not in NODE_TYPES_TO_IGNORE:
            childElements.append(child)
            num += removeUnusedAttributesOnParent(child)

    # only process the children if there are more than one element
    if len(childElements) <= 1:
        return num

    # IMPORTANT: Skip text elements - their presentation attributes (font-family, etc.)
    # are essential for rendering and should not be removed even if children don't
    # explicitly inherit them. Text nodes don't have attributes, so the inheritance
    # check below would incorrectly remove these critical attributes.
    if elem.nodeName == "text":
        return num

    # get all attribute values on this parent
    attrList = elem.attributes
    unusedAttrs = {}
    for index in range(attrList.length):
        attr = attrList.item(index)
        if attr.nodeName in [
            "clip-rule",
            "display-align",
            "fill",
            "fill-opacity",
            "fill-rule",
            "font",
            "font-family",
            "font-size",
            "font-size-adjust",
            "font-stretch",
            "font-style",
            "font-variant",
            "font-weight",
            "letter-spacing",
            "pointer-events",
            "shape-rendering",
            "stroke",
            "stroke-dasharray",
            "stroke-dashoffset",
            "stroke-linecap",
            "stroke-linejoin",
            "stroke-miterlimit",
            "stroke-opacity",
            "stroke-width",
            "text-anchor",
            "text-decoration",
            "text-rendering",
            "visibility",
            "word-spacing",
            "writing-mode",
        ]:
            unusedAttrs[attr.nodeName] = attr.nodeValue

    # for each child, if at least one child inherits the parent's attribute, then remove
    for child in childElements:
        inheritedAttrs = []
        for name in unusedAttrs:
            val = child.getAttribute(name)
            if val == "" or val == "inherit":
                inheritedAttrs.append(name)
        for a in inheritedAttrs:
            del unusedAttrs[a]

    # unusedAttrs now has all the parent attributes that are unused
    for name in unusedAttrs:
        elem.removeAttribute(name)
        num += 1

    return num


referencingProps = [
    "fill",
    "stroke",
    "filter",
    "clip-path",
    "mask",
    "marker-start",
    "marker-end",
    "marker-mid",
]


def findReferencedElements(node, ids=None):
    """
    Returns IDs of all referenced elements
    - node is the node at which to start the search.
    - returns a map which has the id as key and
      each value is is a set of nodes

    Currently looks at 'xlink:href' and all attributes in 'referencingProps'
    """
    global referencingProps
    if ids is None:
        ids = {}
    # if this node is a style element, parse its text into CSS
    if node.nodeName == "style" and node.namespaceURI == NS["SVG"]:
        stylesheet = "".join(child.nodeValue for child in node.childNodes)
        if stylesheet != "":
            cssRules = parseCssString(stylesheet)
            for rule in cssRules:
                for propname in rule["properties"]:
                    propval = rule["properties"][propname]
                    findReferencingProperty(node, propname, propval, ids)
        return ids

    # else if xlink:href is set, then grab the id
    href = node.getAttributeNS(NS["XLINK"], "href")
    if href != "" and len(href) > 1 and href[0] == "#":
        id = href[1:]
        if id in ids:
            ids[id].add(node)
        else:
            ids[id] = {node}

    # now get all style properties and the fill, stroke, filter attributes
    styles = node.getAttribute("style")
    if styles:
        for style in styles.split(";"):
            if ":" in style:
                prop, val = style.split(":", 1)
                findReferencingProperty(node, prop.strip(), val.strip(), ids)

    for attr in referencingProps:
        val = node.getAttribute(attr).strip()
        if val:
            findReferencingProperty(node, attr, val, ids)

    if node.hasAttribute("values"):
        keyvalues = node.getAttribute("values").split(";")
        for value in keyvalues:
            val = value.strip()
            if val:
                findReferencingProperty(node, "values", val, ids)

    if node.hasChildNodes():
        for child in node.childNodes:
            if child.nodeType not in NODE_TYPES_TO_IGNORE:
                findReferencedElements(child, ids)
    return ids


def parseCssString(style_string):
    rules = []
    global style_rules_for_elements
    global framerules
    if framerules is None:
        framerules = []
    if style_rules_for_elements is None:
        style_rules_for_elements = []

    style_string = style_string.replace("\n", "")

    # first, split on } to get the rule chunks
    chunks = style_string.split("}")

    for chunk in chunks:
        if chunk.strip() == "":
            continue
        # second, split on { to get the selector and the list of properties
        bits = chunk.split("{")
        if len(bits) != 2:
            continue
        if ":" in bits[0]:
            continue
        rule = {}
        rule["selector"] = bits[0].strip()
        # third, split on ; to get the property declarations
        bites = bits[1].strip().split(";")
        if len(bites) < 1:
            continue
        props = {}
        for bite in bites:
            if bite.strip() == "":
                continue
            # fourth, split on : to get the property name and value
            nibbles = [x.strip() for x in bite.strip().split(":")]
            if len(nibbles) != 2:
                continue
            props[nibbles[0].strip()] = nibbles[1].strip()
        rule["properties"] = props

        candidate_rules = []
        subselectors = [x.strip() for x in rule["selector"].split(",") if not x.isspace()]
        if len(subselectors) > 0:
            for sub in subselectors:
                newrule = {}
                newrule["selector"] = sub
                newrule["properties"] = props
                candidate_rules.append(newrule)

        # candidate_rules.append(rule)
        for crule in candidate_rules:
            if crule["selector"] == "svg":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'svg' element. Moving the attribute to the frame group as temporary fix.")
                framerules.append(crule)
            elif crule["selector"] == "body":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'body' element. Ignoring.")
                style_rules_for_elements.append(crule)
            elif crule["selector"] == "text":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'text' elements. Adding the attribute to those elements as temporary fix.")
                style_rules_for_elements.append(crule)
            elif crule["selector"] == "circle":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'circle' elements. Adding the attribute to those elements as temporary fix.")
                style_rules_for_elements.append(crule)
            elif crule["selector"] == "path":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'path' elements. Adding the attribute to those elements as temporary fix.")
                style_rules_for_elements.append(crule)
            elif crule["selector"] == "rect":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'rect' elements. Adding the attribute to those elements as temporary fix.")
                style_rules_for_elements.append(crule)
            elif crule["selector"] == "polyline":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'polyline' elements. Adding the attribute to those elements as temporary fix.")
                style_rules_for_elements.append(crule)
            elif rule["selector"] == "polygon":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'polygon' elements. Adding the attribute to those elements as temporary fix.")
                style_rules_for_elements.append(crule)
            elif crule["selector"] == "image":
                add2log(f"WARNING: style section of the file {current_filepath} contains CSS rules targeting 'image' elements. Adding the attribute to those elements as temporary fix.")
                style_rules_for_elements.append(crule)
            else:
                rules.append(crule)
    return rules


def create_groups_for_common_attributes(elem):
    """
    Creates <g> elements to contain runs of 3 or more
    consecutive child elements having at least one common attribute.

    Common attributes are not promoted to the <g> by this function.
    This is handled by moveCommonAttributesToParentGroup.

    If all children have a common attribute, an extra <g> is not created.

    This function acts recursively on the given element.
    """

    # TODO perhaps all of the Presentation attributes in http://www.w3.org/TR/SVG/struct.html#GElement
    # could be added here
    # Cyn: These attributes are the same as in moveAttributesToParentGroup,
    # and must always be
    for curAttr in [
        "clip-rule",
        "display-align",
        "fill",
        "fill-opacity",
        "fill-rule",
        "font",
        "font-family",
        "font-size",
        "font-size-adjust",
        "font-stretch",
        "font-style",
        "font-variant",
        "font-weight",
        "letter-spacing",
        "pointer-events",
        "shape-rendering",
        "stroke",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-opacity",
        "stroke-width",
        "text-anchor",
        "text-decoration",
        "text-rendering",
        "visibility",
        "word-spacing",
        "writing-mode",
    ]:
        # Iterate through the children in reverse order, so item(i) for
        # items we have yet to visit still returns the correct nodes.
        curChild = elem.childNodes.length - 1
        while curChild >= 0:
            childNode = elem.childNodes.item(curChild)

            if (
                childNode.nodeType == Node.ELEMENT_NODE
                and childNode.getAttribute(curAttr) != ""
                and childNode.nodeName
                in [
                    # only attempt to group elements that the content model
                    # allows to be children of a <g> (SVG 1.1)
                    # (see https://www.w3.org/TR/SVG/struct.html#GElement)
                    "animate",
                    "animateColor",
                    "animateMotion",
                    "animateTransform",
                    "set",  # animation elements
                    "desc",
                    "metadata",
                    "title",  # descriptive elements
                    "circle",
                    "ellipse",
                    "line",
                    "path",
                    "polygon",
                    "polyline",
                    "rect",  # shape elements
                    "defs",
                    "g",
                    "svg",
                    "symbol",
                    "use",  # structural elements
                    "linearGradient",
                    "radialGradient",  # gradient elements
                    "a",
                    "altGlyphDef",
                    "clipPath",
                    "color-profile",
                    "cursor",
                    "filter",
                    "font",
                    "font-face",
                    "foreignObject",
                    "image",
                    "marker",
                    "mask",
                    "pattern",
                    "script",
                    "style",
                    "switch",
                    "text",
                    "view",
                    # SVG 2.0
                    "hatch",
                    "hatchpath",
                    "mesh",
                    "meshgradient",
                    "meshpatch",
                    "meshrow",
                    # SVG 1.2 (see https://www.w3.org/TR/SVGTiny12/elementTable.html)
                    "animation",
                    "audio",
                    "discard",
                    "handler",
                    "listener",
                    "prefetch",
                    "solidColor",
                    "textArea",
                    "video",
                ]
            ):
                # We're in a possible run! Track the value and run length.
                value = childNode.getAttribute(curAttr)
                runStart, runEnd = curChild, curChild
                # Run elements includes only element tags, no whitespace/comments/etc.
                # Later, we calculate a run length which includes these.
                runElements = 1

                # Backtrack to get all the nodes having the same
                # attribute value, preserving any nodes in-between.
                while runStart > 0:
                    nextNode = elem.childNodes.item(runStart - 1)
                    if nextNode.nodeType == Node.ELEMENT_NODE:
                        if nextNode.getAttribute(curAttr) != value:
                            break
                        else:
                            runElements += 1
                            runStart -= 1
                    else:
                        runStart -= 1

                if runElements >= 3:
                    # Include whitespace/comment/etc. nodes in the run.
                    while runEnd < elem.childNodes.length - 1:
                        if elem.childNodes.item(runEnd + 1).nodeType == Node.ELEMENT_NODE:
                            break
                        else:
                            runEnd += 1

                    runLength = runEnd - runStart + 1
                    if runLength == elem.childNodes.length:  # Every child has this
                        # If the current parent is a <g> already,
                        if elem.nodeName == "g" and elem.namespaceURI == NS["SVG"]:
                            # do not act altogether on this attribute; all the
                            # children have it in common.
                            # Let moveCommonAttributesToParentGroup do it.
                            curChild = -1
                            continue
                    # otherwise, it might be an <svg> element, and
                    # even if all children have the same attribute value,
                    # it's going to be worth making the <g> since
                    # <svg> doesn't support attributes like 'stroke'.
                    # Fall through.

                    # Create a <g> element from scratch.
                    # We need the Document for this.
                    document = elem.ownerDocument
                    group = document.createElementNS(NS["SVG"], "g")
                    # Move the run of elements to the group.
                    # a) ADD the nodes to the new group.
                    group.childNodes[:] = elem.childNodes[runStart : runEnd + 1]
                    for child in group.childNodes:
                        child.parentNode = group
                    # b) REMOVE the nodes from the element.
                    elem.childNodes[runStart : runEnd + 1] = []
                    # Include the group in elem's children.
                    elem.childNodes.insert(runStart, group)
                    group.parentNode = elem
                    curChild = runStart - 1
                else:
                    curChild -= 1
            else:
                curChild -= 1

    # each child gets the same treatment, recursively
    for childNode in elem.childNodes:
        if childNode.nodeType not in NODE_TYPES_TO_IGNORE:
            create_groups_for_common_attributes(childNode)


def mergeSiblingGroupsWithCommonAttributes(elem):
    """
    Merge two or more sibling <g> elements with the identical attributes.

    This function acts recursively on the given element.
    """

    num = 0
    i = elem.childNodes.length - 1
    while i >= 0:
        currentNode = elem.childNodes.item(i)
        if currentNode.nodeType != Node.ELEMENT_NODE or currentNode.nodeName != "g" or currentNode.namespaceURI != NS["SVG"]:
            i -= 1
            continue
        attributes = {a.nodeName: a.nodeValue for a in currentNode.attributes.values()}
        if not attributes:
            i -= 1
            continue
        runStart, runEnd = i, i
        runElements = 1
        while runStart > 0:
            nextNode = elem.childNodes.item(runStart - 1)
            if nextNode.nodeType == Node.ELEMENT_NODE:
                if nextNode.nodeName != "g" or nextNode.namespaceURI != NS["SVG"]:
                    break
                nextAttributes = {a.nodeName: a.nodeValue for a in nextNode.attributes.values()}
                if attributes != nextAttributes or not g_tag_is_mergeable(nextNode):
                    break
                else:
                    runElements += 1
                    runStart -= 1
            else:
                runStart -= 1

        # Next loop will start from here
        i = runStart - 1

        if runElements < 2:
            continue

        # Find the <g> entry that starts the run (we might have run
        # past it into a text node or a comment node.
        while True:
            node = elem.childNodes.item(runStart)
            if node.nodeType == Node.ELEMENT_NODE and node.nodeName == "g" and node.namespaceURI == NS["SVG"]:
                break
            runStart += 1
        primaryGroup = elem.childNodes.item(runStart)
        runStart += 1
        nodes = elem.childNodes[runStart : runEnd + 1]
        for node in nodes:
            if node.nodeType == Node.ELEMENT_NODE and node.nodeName == "g" and node.namespaceURI == NS["SVG"]:
                # Merge
                for child in node.childNodes[:]:
                    primaryGroup.appendChild(child)
                elem.removeChild(node).unlink()
            else:
                primaryGroup.appendChild(node)

    # each child gets the same treatment, recursively
    for childNode in elem.childNodes:
        if childNode.nodeType not in NODE_TYPES_TO_IGNORE:
            num += mergeSiblingGroupsWithCommonAttributes(childNode)

    return num


def remove_empty_elements(doc, options):
    # remove empty defs, metadata, g
    # NOTE: these elements will be removed if they just have whitespace-only text nodes
    for tag in ["defs", "title", "desc", "metadata", "g"]:
        for elem in doc.documentElement.getElementsByTagName(tag):
            removeElem = not elem.hasChildNodes()
            if removeElem is False:
                for child in elem.childNodes:
                    if child.nodeType in [
                        Node.ELEMENT_NODE,
                        Node.CDATA_SECTION_NODE,
                        Node.COMMENT_NODE,
                        Node.DOCUMENT_NODE,
                    ]:
                        break
                    elif child.nodeType == Node.TEXT_NODE and not child.nodeValue.isspace():
                        break
            else:
                removeElem = True
            if removeElem:
                elem.parentNode.removeChild(elem)

    return


rgb = re.compile(r"\s*rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*")
rgbp = re.compile(r"\s*rgb\(\s*(\d*\.?\d+)%\s*,\s*(\d*\.?\d+)%\s*,\s*(\d*\.?\d+)%\s*\)\s*")


def convertColor(value):
    """
    Converts the input color string and returns a #RRGGBB (or #RGB if possible) string
    """
    s = value

    if s in colors:
        s = colors[s]

    rgbpMatch = rgbp.match(s)
    if rgbpMatch is not None:
        r = int(float(rgbpMatch.group(1)) * 255.0 / 100.0)
        g = int(float(rgbpMatch.group(2)) * 255.0 / 100.0)
        b = int(float(rgbpMatch.group(3)) * 255.0 / 100.0)
        s = f"#{r:02x}{g:02x}{b:02x}"
    else:
        rgbMatch = rgb.match(s)
        if rgbMatch is not None:
            r = int(rgbMatch.group(1))
            g = int(rgbMatch.group(2))
            b = int(rgbMatch.group(3))
            s = f"#{r:02x}{g:02x}{b:02x}"

    if s[0] == "#":
        s = s.lower()
        if len(s) == 7 and s[1] == s[2] and s[3] == s[4] and s[5] == s[6]:
            s = "#" + s[1] + s[3] + s[5]

    return s


def convertColors(element):
    """
    Recursively converts all color properties into #RRGGBB format if shorter
    """
    numBytes = 0

    if element.nodeType != Node.ELEMENT_NODE:
        return 0

    # set up list of color attributes for each element type
    attrsToConvert = []
    if element.nodeName in [
        "rect",
        "circle",
        "ellipse",
        "polygon",
        "line",
        "polyline",
        "path",
        "g",
        "a",
    ]:
        attrsToConvert = ["fill", "stroke"]
    elif element.nodeName in ["stop"]:
        attrsToConvert = ["stop-color"]
    elif element.nodeName in ["solidColor"]:
        attrsToConvert = ["solid-color"]

    # now convert all the color formats
    styles = _getStyle(element)
    for attr in attrsToConvert:
        oldColorValue = element.getAttribute(attr)
        if oldColorValue != "":
            newColorValue = convertColor(oldColorValue)
            oldBytes = len(oldColorValue)
            newBytes = len(newColorValue)
            if oldBytes > newBytes:
                element.setAttribute(attr, newColorValue)
                numBytes += oldBytes - len(element.getAttribute(attr))
        # colors might also hide in styles
        if attr in styles:
            oldColorValue = styles[attr]
            newColorValue = convertColor(oldColorValue)
            oldBytes = len(oldColorValue)
            newBytes = len(newColorValue)
            if oldBytes > newBytes:
                styles[attr] = newColorValue
                numBytes += oldBytes - newBytes
    _setStyle(element, styles)

    # now recurse for our child elements
    for child in element.childNodes:
        numBytes += convertColors(child)

    return numBytes


def determine_number_of_flowRoot_elements(doc, options, filepath):
    flowText_el = doc.getElementsByTagName("flowRoot")
    cnt_flowText_el = len(flowText_el)
    if cnt_flowText_el:
        errmsg = f"SVG input document {filepath} uses {cnt_flowText_el} flow text element(s), which won't render on browsers. Removing."
        for ftel in flowText_el:
            if ftel.parentNode is not None:
                ftel.parentNode.removeChild(ftel)
        # raise Exception(errmsg)
        add2log(f"WARNING: {errmsg}")  # , file=sys.stderr)
    return


def ensure_valid_svg_namespace_is_declared(doc, options, filepath):
    if doc.documentElement.getAttribute("xmlns") != "http://www.w3.org/2000/svg":
        doc.documentElement.setAttribute("xmlns", "http://www.w3.org/2000/svg")
        errmsg = f"SVG input document {filepath} has invalid namespace, fixing it to http://www.w3.org/2000/svg."
        add2log(f"WARNING: {errmsg}")  # , file=sys.stderr)
    return


NAMESPACES_TO_KEEP = [NS["SVG"], NS["XLINK"]]


def removeNamespacedElements(node, namespaces):
    if node.nodeType == Node.ELEMENT_NODE:
        # remove all namespace'd child nodes from this element
        childList = node.childNodes
        childrenToRemove = []
        for child in childList:
            # we need to be more strict than scour when it cames to NS
            # only default namespaces are allowed
            if child is not None:
                if child.namespaceURI is None:
                    continue
                elif child.namespaceURI not in NAMESPACES_TO_KEEP:
                    childrenToRemove.append(child)
        for child in childrenToRemove:
            node.removeChild(child)

    # now recurse for children
    for child in node.childNodes:
        removeNamespacedElements(child, namespaces)
    return


def removeNamespacedAttributes(node, namespaces):
    num = 0
    if node.nodeType == Node.ELEMENT_NODE:
        # remove all namespace'd attributes from this element
        if node.hasAttribute("data-name"):
            node.removeAttribute("data-name")
        attrList = node.attributes
        attrsToRemove = []
        for attrNum in range(attrList.length):
            attr = attrList.item(attrNum)
            if attr is not None and attr.namespaceURI in namespaces:
                attrsToRemove.append(
                    (
                        attr,
                        attr.nodeName,
                        attr.namespaceURI,
                        attr.localName,
                    )
                )

        for attr, _attNodeName, _attNamespaceURI, _attLocalName in attrsToRemove:
            node.removeAttributeNode(attr)
        # node.removeAttribute(attNodeName)
        # if node.hasAttributeNS(attNamespaceURI, attLocalName):
        # 	node.removeAttributeNS(attNamespaceURI, attLocalName)
        num += len(attrsToRemove)

    # now recurse for children
    for child in node.childNodes:
        num += removeNamespacedAttributes(child, namespaces)
    return num


def remove_descriptive_elements(doc, options):
    elementTypes = []

    elementTypes.extend(("title", "desc", "metadata", "script", "input"))

    elementsToRemove = []
    for elementType in elementTypes:
        elementsToRemove.extend(doc.documentElement.getElementsByTagName(elementType))

    for element in elementsToRemove:
        element.parentNode.removeChild(element)

    return len(elementsToRemove)


def remove_xmlns_declarations(doc):
    xmlnsDeclsToRemove = []
    attrList = doc.documentElement.attributes
    for index in range(attrList.length):
        attr = attrList.item(index)
        if attr.nodeValue in UNWANTED_NS:
            xmlnsDeclsToRemove.append(attr.nodeName)

    for attr in xmlnsDeclsToRemove:
        doc.documentElement.removeAttribute(attr)

    return len(xmlnsDeclsToRemove)


def remove_unused_and_reduntant_namespace_declarations(doc, options):
    attrList = doc.documentElement.attributes
    xmlnsDeclsToRemove = []
    redundantPrefixes = []
    for i in range(attrList.length):
        attr = attrList.item(i)
        name = attr.nodeName
        val = attr.nodeValue
        if name.startswith("xmlns:"):
            if val == "http://www.w3.org/2000/svg":
                redundantPrefixes.append(name[6:])
                xmlnsDeclsToRemove.append(name)
            elif xmlnsUnused(doc, name[6:], val):
                xmlnsDeclsToRemove.append(name)

    for attrName in xmlnsDeclsToRemove:
        doc.documentElement.removeAttribute(attrName)

    for prefix in redundantPrefixes:
        remapNamespacePrefix(doc.documentElement, prefix, "")

    return len(xmlnsDeclsToRemove)


def xmlnsUnused(doc, prefix, namespace):
    if doc.getElementsByTagNameNS(namespace, "*"):
        return False
    else:
        for element in doc.getElementsByTagName("*"):
            for attribute in element.attributes.values():
                if attribute.name.startswith(prefix):
                    return False
    return True


def remapNamespacePrefix(node, oldprefix, newprefix):
    if node is None or node.nodeType != Node.ELEMENT_NODE:
        return

    if node.prefix == oldprefix:
        localName = node.localName
        namespace = node.namespaceURI
        doc = node.ownerDocument
        parent = node.parentNode

        # create a replacement node
        if newprefix != "":
            newNode = doc.createElementNS(namespace, newprefix + ":" + localName)
        else:
            newNode = doc.createElement(localName)

        # add all the attributes
        attrList = node.attributes
        for i in range(attrList.length):
            attr = attrList.item(i)
            newNode.setAttributeNS(attr.namespaceURI, attr.name, attr.nodeValue)

        # clone and add all the child nodes
        for child in node.childNodes:
            newNode.appendChild(child.cloneNode(True))

        # replace old node with new node
        parent.replaceChild(newNode, node)
        # set the node to the new node in the remapped namespace prefix
        node = newNode

    # now do all child nodes
    for child in node.childNodes:
        remapNamespacePrefix(child, oldprefix, newprefix)

    return


#################################
# PATH and TRANSFORM functions
#################################


# optimize svg path commands
def clean_path(element, options):
    """
    Cleans the path string (d attribute) of the element
    """

    # keep track of some stats for debug
    num_path_segments_removed = 0
    num_bytes_saved_in_path_data = 0

    # this gets the parser object from svg_regex.py
    oldPathStr = element.getAttribute("d")
    path = svg_path_parser.parse(oldPathStr)
    style = _getStyle(element)

    # This determines whether the stroke has round or square linecaps.
    # If it does, we do not want to collapse empty segments, as they
    # are actually rendered (as circles or squares with
    # diameter/dimension matching the path-width).
    has_round_or_square_linecaps = element.getAttribute("stroke-linecap") in ["round", "square"] or "stroke-linecap" in style and style["stroke-linecap"] in ["round", "square"]

    # This determines whether the stroke has intermediate markers.
    # If it does, we do not want to collapse straight segments running
    # in the same direction, as markers are rendered on the
    # intermediate nodes.
    has_intermediate_markers = element.hasAttribute("marker") or element.hasAttribute("marker-mid") or "marker" in style or "marker-mid" in style

    # The first command must be a moveto, and whether it's relative (m)
    # or absolute (M), the first set of coordinates *is* absolute. So
    # the first iteration of the loop below will get x,y and startx,starty.

    # convert absolute coordinates into relative ones.
    # Reuse the data structure 'path', since we're not adding or
    # removing subcommands. Also reuse the coordinate lists since we're
    # not adding or removing any.
    x = y = 0
    for pathIndex in range(len(path)):
        # Changes to cmd don't get through to the data structure
        cmd, data = path[pathIndex]
        i = 0
        # adjust abs to rel
        # only the A command has some values that we don't want to
        # adjust (radii, rotation, flags)
        if cmd == "A":
            for j in range(i, len(data), 7):
                data[j + 5] -= x
                data[j + 6] -= y
                x += data[j + 5]
                y += data[j + 6]
            path[pathIndex] = ("a", data)
        elif cmd == "a":
            x += sum(data[5::7])
            y += sum(data[6::7])
        elif cmd == "H":
            for j in range(i, len(data)):
                data[j] -= x
                x += data[j]
            path[pathIndex] = ("h", data)
        elif cmd == "h":
            x += sum(data)
        elif cmd == "V":
            for j in range(i, len(data)):
                data[j] -= y
                y += data[j]
            path[pathIndex] = ("v", data)
        elif cmd == "v":
            y += sum(data)
        elif cmd == "M":
            startx, starty = data[0], data[1]
            # If this is a path starter, don't convert its first
            # coordinate to relative; that would just make it (0, 0)
            if pathIndex != 0:
                data[0] -= x
                data[1] -= y

            x, y = startx, starty
            i = 2
            for j in range(i, len(data), 2):
                data[j] -= x
                data[j + 1] -= y
                x += data[j]
                y += data[j + 1]
            path[pathIndex] = ("m", data)
        elif cmd in ["L", "T"]:
            for j in range(i, len(data), 2):
                data[j] -= x
                data[j + 1] -= y
                x += data[j]
                y += data[j + 1]
            path[pathIndex] = (cmd.lower(), data)
        elif cmd in ["m"]:
            if pathIndex == 0:
                # START OF PATH - this is an absolute moveto
                # followed by relative linetos
                startx, starty = data[0], data[1]
                x, y = startx, starty
                i = 2
            else:
                startx = x + data[0]
                starty = y + data[1]
            for j in range(i, len(data), 2):
                x += data[j]
                y += data[j + 1]
        elif cmd in ["l", "t"]:
            x += sum(data[0::2])
            y += sum(data[1::2])
        elif cmd in ["S", "Q"]:
            for j in range(i, len(data), 4):
                data[j] -= x
                data[j + 1] -= y
                data[j + 2] -= x
                data[j + 3] -= y
                x += data[j + 2]
                y += data[j + 3]
            path[pathIndex] = (cmd.lower(), data)
        elif cmd in ["s", "q"]:
            x += sum(data[2::4])
            y += sum(data[3::4])
        elif cmd == "C":
            for j in range(i, len(data), 6):
                data[j] -= x
                data[j + 1] -= y
                data[j + 2] -= x
                data[j + 3] -= y
                data[j + 4] -= x
                data[j + 5] -= y
                x += data[j + 4]
                y += data[j + 5]
            path[pathIndex] = ("c", data)
        elif cmd == "c":
            x += sum(data[4::6])
            y += sum(data[5::6])
        elif cmd in ["z", "Z"]:
            x, y = startx, starty
            path[pathIndex] = ("z", data)

    # remove empty segments and redundant commands
    # Reuse the data structure 'path' and the coordinate lists, even if we're
    # deleting items, because these deletions are relatively cheap.
    if not has_round_or_square_linecaps:
        # remove empty path segments
        for pathIndex in range(len(path)):
            cmd, data = path[pathIndex]
            i = 0
            if cmd in ["m", "l", "t"]:
                if cmd == "m":
                    # It might be tempting to rewrite "m0 0 ..." into
                    # "l..." here.  However, this is an unsound
                    # optimization in general as "m0 0 ..." is
                    # different from "l...z".
                    #
                    # To do such a rewrite, we need to understand the
                    # full subpath.  This logic happens after this
                    # loop.
                    i = 2
                while i < len(data):
                    if data[i] == data[i + 1] == 0:
                        del data[i : i + 2]
                        num_path_segments_removed += 1
                    else:
                        i += 2
            elif cmd == "c":
                while i < len(data):
                    if data[i] == data[i + 1] == data[i + 2] == data[i + 3] == data[i + 4] == data[i + 5] == 0:
                        del data[i : i + 6]
                        num_path_segments_removed += 1
                    else:
                        i += 6
            elif cmd == "a":
                while i < len(data):
                    if data[i + 5] == data[i + 6] == 0:
                        del data[i : i + 7]
                        num_path_segments_removed += 1
                    else:
                        i += 7
            elif cmd == "q":
                while i < len(data):
                    if data[i] == data[i + 1] == data[i + 2] == data[i + 3] == 0:
                        del data[i : i + 4]
                        num_path_segments_removed += 1
                    else:
                        i += 4
            elif cmd in ["h", "v"]:
                oldLen = len(data)
                path[pathIndex] = (cmd, [coord for coord in data if coord != 0])
                num_path_segments_removed += len(path[pathIndex][1]) - oldLen

        # remove no-op commands
        pathIndex = len(path)
        subpath_needs_anchor = False
        # NB: We can never rewrite the first m/M command (expect if it
        # is the only command)
        while pathIndex > 1:
            pathIndex -= 1
            cmd, data = path[pathIndex]
            if cmd == "z":
                next_cmd, next_data = path[pathIndex - 1]
                if next_cmd == "m" and len(next_data) == 2:
                    # mX Yz -> mX Y

                    # note the len check on next_data as it is not
                    # safe to rewrite "m0 0 1 1z" in general (it is a
                    # question of where the "pen" ends - you can
                    # continue a draw on the same subpath after a
                    # "z").
                    del path[pathIndex]
                    num_path_segments_removed += 1
                else:
                    # it is not safe to rewrite "m0 0 ..." to "l..."
                    # because of this "z" command.
                    subpath_needs_anchor = True
            elif cmd == "m":
                if len(path) - 1 == pathIndex and len(data) == 2:
                    # Ends with an empty move (but no line/draw
                    # following it)
                    del path[pathIndex]
                    num_path_segments_removed += 1
                    continue
                if subpath_needs_anchor:
                    subpath_needs_anchor = False
                elif data[0] == data[1] == 0:
                    # unanchored, i.e. we can replace "m0 0 ..." with
                    # "l..." as there is no "z" after it.
                    path[pathIndex] = ("l", data[2:])
                    num_path_segments_removed += 1

    # fixup: Delete subcommands having no coordinates.
    path = [elem for elem in path if len(elem[1]) > 0 or elem[0] == "z"]

    # convert straight curves into lines
    newPath = [path[0]]
    for cmd, data in path[1:]:
        i = 0
        newData = data
        if cmd == "c":
            newData = []
            while i < len(data):
                # since all commands are now relative, we can think of
                # previous point as (0,0) and new point (dx,dy) is
                # (data[i+4],data[i+5]) eqn of line will be
                # y = (dy/dx)*x or if dx=0 then eqn of line is x=0
                (p1x, p1y) = (data[i], data[i + 1])
                (p2x, p2y) = (data[i + 2], data[i + 3])
                dx = data[i + 4]
                dy = data[i + 5]

                foundStraightCurve = False

                if dx == 0:
                    if p1x == 0 and p2x == 0:
                        foundStraightCurve = True
                else:
                    m = dy / dx
                    if p1y == m * p1x and p2y == m * p2x:
                        foundStraightCurve = True

                if foundStraightCurve:
                    # flush any existing curve coords first
                    if newData:
                        newPath.append((cmd, newData))
                        newData = []
                    # now create a straight line segment
                    newPath.append(("l", [dx, dy]))
                else:
                    newData.extend(data[i : i + 6])

                i += 6
        if newData or cmd == "z" or cmd == "Z":
            newPath.append((cmd, newData))
    path = newPath

    # collapse all consecutive commands of the same type into one
    # command
    prevCmd = ""
    prevData = []
    newPath = []
    for cmd, data in path:
        if prevCmd == "":
            # initialize with current path cmd and data
            prevCmd = cmd
            prevData = data
        else:
            # collapse if:
            # - cmd is not moveto (explicit moveto commands are not
            #   drawn)
            # - the previous and current commands are the same type,
            # - the previous command is moveto and the current is lineto
            #   (subsequent moveto pairs are treated as implicit lineto
            #   commands)
            if cmd != "m" and (cmd == prevCmd or (cmd == "l" and prevCmd == "m")):
                prevData.extend(data)
            # else flush the previous command if it is not the same
            # type as the current command
            else:
                newPath.append((prevCmd, prevData))
                prevCmd = cmd
                prevData = data
    # flush last command and data
    newPath.append((prevCmd, prevData))
    path = newPath

    # convert to shorthand path segments where possible
    newPath = []
    for cmd, data in path:
        # convert line segments into h,v where possible
        if cmd == "l":
            i = 0
            lineTuples = []
            while i < len(data):
                if data[i] == 0:
                    # vertical
                    if lineTuples:
                        # flush the existing line command
                        newPath.append(("l", lineTuples))
                        lineTuples = []
                    # append the v and then the remaining line coords
                    newPath.append(("v", [data[i + 1]]))
                    num_path_segments_removed += 1
                elif data[i + 1] == 0:
                    if lineTuples:
                        # flush the line command, then append the h and
                        # then the remaining line coords
                        newPath.append(("l", lineTuples))
                        lineTuples = []
                    newPath.append(("h", [data[i]]))
                    num_path_segments_removed += 1
                else:
                    lineTuples.extend(data[i : i + 2])
                i += 2
            if lineTuples:
                newPath.append(("l", lineTuples))
        # also handle implied relative linetos
        elif cmd == "m":
            i = 2
            lineTuples = [data[0], data[1]]
            while i < len(data):
                if data[i] == 0:
                    # vertical
                    if lineTuples:
                        # flush the existing m/l command
                        newPath.append((cmd, lineTuples))
                        lineTuples = []
                        cmd = "l"  # dealing with linetos now
                    # append the v and then the remaining line coords
                    newPath.append(("v", [data[i + 1]]))
                    num_path_segments_removed += 1
                elif data[i + 1] == 0:
                    if lineTuples:
                        # flush the m/l command, then append the h and
                        # then the remaining line coords
                        newPath.append((cmd, lineTuples))
                        lineTuples = []
                        cmd = "l"  # dealing with linetos now
                    newPath.append(("h", [data[i]]))
                    num_path_segments_removed += 1
                else:
                    lineTuples.extend(data[i : i + 2])
                i += 2
            if lineTuples:
                newPath.append((cmd, lineTuples))
        # convert Bézier curve segments into s where possible
        elif cmd == "c":
            # set up the assumed bezier control point as the current point,
            # i.e. (0,0) since we're using relative coords
            bez_ctl_pt = (0, 0)
            # however if the previous command was 's'
            # the assumed control point is a reflection of the previous
            # control point at the current point
            if len(newPath):
                (prevCmd, prevData) = newPath[-1]
                if prevCmd == "s":
                    bez_ctl_pt = (
                        prevData[-2] - prevData[-4],
                        prevData[-1] - prevData[-3],
                    )
            i = 0
            curveTuples = []
            while i < len(data):
                # rotate by 180deg means negate both coordinates
                # if the previous control point is equal then we can substitute a
                # shorthand bezier command
                if bez_ctl_pt[0] == data[i] and bez_ctl_pt[1] == data[i + 1]:
                    if curveTuples:
                        newPath.append(("c", curveTuples))
                        curveTuples = []
                    # append the s command
                    newPath.append(
                        (
                            "s",
                            [data[i + 2], data[i + 3], data[i + 4], data[i + 5]],
                        )
                    )
                    num_path_segments_removed += 1
                else:
                    j = 0
                    while j <= 5:
                        curveTuples.append(data[i + j])
                        j += 1

                # set up control point for next curve segment
                bez_ctl_pt = (data[i + 4] - data[i + 2], data[i + 5] - data[i + 3])
                i += 6

            if curveTuples:
                newPath.append(("c", curveTuples))
        # convert quadratic curve segments into t where possible
        elif cmd == "q":
            quad_ctl_pt = (0, 0)
            i = 0
            curveTuples = []
            while i < len(data):
                if quad_ctl_pt[0] == data[i] and quad_ctl_pt[1] == data[i + 1]:
                    if curveTuples:
                        newPath.append(("q", curveTuples))
                        curveTuples = []
                    # append the t command
                    newPath.append(("t", [data[i + 2], data[i + 3]]))
                    num_path_segments_removed += 1
                else:
                    j = 0
                    while j <= 3:
                        curveTuples.append(data[i + j])
                        j += 1

                quad_ctl_pt = (data[i + 2] - data[i], data[i + 3] - data[i + 1])
                i += 4

            if curveTuples:
                newPath.append(("q", curveTuples))
        else:
            newPath.append((cmd, data))
    path = newPath

    # For each m, l, h or v, collapse unnecessary coordinates that
    # run in the same direction i.e. "h-100-100" becomes "h-200" but
    # "h300-100" does not change. If the path has intermediate markers
    # we have to preserve intermediate nodes, though. Reuse the data
    # structure 'path', since we're not adding or removing subcommands.
    # Also reuse the coordinate lists, even if we're deleting items,
    # because these deletions are relatively cheap.
    if not has_intermediate_markers:
        for pathIndex in range(len(path)):
            cmd, data = path[pathIndex]

            # h / v expects only one parameter and we start drawing
            # with the first (so we need at least 2)
            if cmd in ["h", "v"] and len(data) >= 2:
                coordIndex = 0
                while coordIndex + 1 < len(data):
                    if is_same_sign(data[coordIndex], data[coordIndex + 1]):
                        data[coordIndex] += data[coordIndex + 1]
                        del data[coordIndex + 1]
                        num_path_segments_removed += 1
                    else:
                        coordIndex += 1

            # l expects two parameters and we start drawing with the
            # first (so we need at least 4)
            elif cmd == "l" and len(data) >= 4:
                coordIndex = 0
                while coordIndex + 2 < len(data):
                    if is_same_direction(*data[coordIndex : coordIndex + 4]):
                        data[coordIndex] += data[coordIndex + 2]
                        data[coordIndex + 1] += data[coordIndex + 3]
                        del data[coordIndex + 2]  # delete the next two elements
                        del data[coordIndex + 2]
                        num_path_segments_removed += 1
                    else:
                        coordIndex += 2

            # m expects two parameters but we have to skip the first
            # pair as it's not drawn (so we need at least 6)
            elif cmd == "m" and len(data) >= 6:
                coordIndex = 2
                while coordIndex + 2 < len(data):
                    if is_same_direction(*data[coordIndex : coordIndex + 4]):
                        data[coordIndex] += data[coordIndex + 2]
                        data[coordIndex + 1] += data[coordIndex + 3]
                        del data[coordIndex + 2]  # delete the next two elements
                        del data[coordIndex + 2]
                        num_path_segments_removed += 1
                    else:
                        coordIndex += 2

    # it is possible that we have consecutive h, v, c, t commands now
    # so again collapse all consecutive commands of the same type into
    # one command
    prevCmd = ""
    prevData = []
    newPath = [path[0]]
    for cmd, data in path[1:]:
        # flush the previous command if it is not the same type as the
        # current command
        if prevCmd != "":
            if cmd != prevCmd or cmd == "m":
                newPath.append((prevCmd, prevData))
                prevCmd = ""
                prevData = []

        # if the previous and current commands are the same type,
        # collapse
        if cmd == prevCmd and cmd != "m":
            prevData.extend(data)

        # save last command and data
        else:
            prevCmd = cmd
            prevData = data
    # flush last command and data
    if prevCmd != "":
        newPath.append((prevCmd, prevData))
    path = newPath

    newPathStr = serializePath(path, options)

    # if for whatever reason we actually made the path longer don't
    # use it
    # TODO: maybe we could compare path lengths after each
    # optimization step and use the shortest
    if len(newPathStr) <= len(oldPathStr):
        num_bytes_saved_in_path_data += len(oldPathStr) - len(newPathStr)
        element.setAttribute("d", newPathStr)

    return num_path_segments_removed, num_bytes_saved_in_path_data


def parseListOfPoints(s):
    """
    Parse string into a list of points.

    Returns a list containing an even number of coordinate strings
    """
    i = 0

    # (wsp)? comma-or-wsp-separated coordinate pairs (wsp)?
    # coordinate-pair = coordinate comma-or-wsp coordinate
    # coordinate = sign? integer
    # comma-wsp: (wsp+ comma? wsp*) | (comma wsp*)
    ws_nums = RE_COMMA_WSP.split(s.strip())
    nums = []

    # also, if 100-100 is found, split it into two also
    #  <polygon points="100,-100,100-100,100-100-100,-100-100" />

    for i in range(len(ws_nums)):
        negcoords = ws_nums[i].split("-")

        # this string didn't have any negative coordinates
        if len(negcoords) == 1:
            nums.append(negcoords[0])
        # we got negative coords
        else:
            for j in range(len(negcoords)):
                # first number could be positive
                if j == 0:
                    if negcoords[0] != "":
                        nums.append(negcoords[0])
                # otherwise all other strings will be negative
                else:
                    # unless we accidentally split a number that was in
                    # scientific notation and had a negative exponent
                    # (500.00e-1)
                    prev = ""
                    if len(nums):
                        prev = nums[len(nums) - 1]
                    if prev and prev[len(prev) - 1] in ["e", "E"]:
                        nums[len(nums) - 1] = prev + "-" + negcoords[j]
                    else:
                        nums.append("-" + negcoords[j])

    # if we have an odd number of points, return empty
    if len(nums) % 2 != 0:
        return []

    # now resolve into Decimal values
    i = 0
    while i < len(nums):
        try:
            nums[i] = getcontext().create_decimal(nums[i])
            nums[i + 1] = getcontext().create_decimal(nums[i + 1])
        except InvalidOperation:  # one of the lengths had a unit or is an invalid number
            return []

        i += 2

    return nums


def clean_polygon(elem, options):
    """
    Remove unnecessary closing point of polygon points attribute
    """
    num_points_removed_from_polygon = 0

    pts = parseListOfPoints(elem.getAttribute("points"))
    N = len(pts) / 2
    if N >= 2:
        (startx, starty) = pts[:2]
        (endx, endy) = pts[-2:]
        if startx == endx and starty == endy:
            del pts[-2:]
            num_points_removed_from_polygon += 1
    elem.setAttribute("points", scourCoordinates(pts, options, True))
    return num_points_removed_from_polygon


def cleanPolyline(elem, options):
    """
    Scour the polyline points attribute
    """
    pts = parseListOfPoints(elem.getAttribute("points"))
    elem.setAttribute("points", scourCoordinates(pts, options, True))


def controlPoints(cmd, data):
    """
    Checks if there are control points in the path data

    Returns the indices of all values in the path data which are control points
    """
    cmd = cmd.lower()
    if cmd in ["c", "s", "q"]:
        indices = range(len(data))
        if cmd == "c":  # c: (x1 y1 x2 y2 x y)+
            return [index for index in indices if (index % 6) < 4]
        elif cmd in ["s", "q"]:  # s: (x2 y2 x y)+   q: (x1 y1 x y)+
            return [index for index in indices if (index % 4) < 2]

    return []


def flags(cmd, data):
    """
    Checks if there are flags in the path data

    Returns the indices of all values in the path data which are flags
    """
    if cmd.lower() == "a":  # a: (rx ry x-axis-rotation large-arc-flag sweep-flag x y)+
        indices = range(len(data))
        return [index for index in indices if (index % 7) in [3, 4]]

    return []


def serializePath(pathObj, options):
    """
    Reserializes the path data with some cleanups.
    """
    # elliptical arc commands must have comma/wsp separating the coordinates
    # this fixes an issue outlined in Fix https://bugs.launchpad.net/scour/+bug/412754
    return "".join(
        cmd
        + scourCoordinates(
            data,
            options,
            control_points=controlPoints(cmd, data),
            flags=flags(cmd, data),
        )
        for cmd, data in pathObj
    )


def serializeTransform(transformObj):
    """
    Reserializes the transform data with some cleanups.
    """
    return " ".join(command + "(" + " ".join(scourUnitlessLength(number) for number in numbers) + ")" for command, numbers in transformObj)


def scourCoordinates(data, options, force_whitespace=False, control_points=None, flags=None):
    """
    Serializes coordinate data with some cleanups:
       - removes all trailing zeros after the decimal
       - integerize coordinates if possible
       - removes extraneous whitespace
       - adds spaces between values in a subcommand if required
         (or if force_whitespace is True)
    """
    if flags is None:
        flags = []
    if control_points is None:
        control_points = []
    if data is not None:
        newData = []
        c = 0
        previousCoord = ""
        for coord in data:
            is_control_point = c in control_points
            scouredCoord = scourUnitlessLength(
                coord,
                renderer_workaround=options.renderer_workaround,
                is_control_point=is_control_point,
            )
            # don't output a space if this number starts with a dot (.) or
            # minus sign (-); we only need a space if:
            #   - this number starts with a digit
            #   - this number starts with a dot but the previous number had
            #     *no* dot or exponent
            #     i.e. '1.3 0.5' -> '1.3.5' or '1e3 0.5' -> '1e3.5' is fine
            #     but '123 0.5' -> '123.5' is obviously not
            #   - 'force_whitespace' is explicitly set to 'True'
            # we never need a space after flags (occurring in elliptical arcs),
            # but librsvg struggles without it
            if c > 0 and (force_whitespace or scouredCoord[0].isdigit() or (scouredCoord[0] == "." and not ("." in previousCoord or "e" in previousCoord))) and ((c - 1 not in flags) or options.renderer_workaround):
                newData.append(" ")

            # add the scoured coordinate to the path string
            newData.append(scouredCoord)
            previousCoord = scouredCoord
            c += 1

    return ""


def scourLength(length):
    """
    Scours a length. Accepts units.
    """
    length = SVGLength(length)

    return scourUnitlessLength(length.value) + Unit.str(length.units)


def scourUnitlessLength(length, renderer_workaround=False, is_control_point=False):  # length is of a numeric type
    """
    Scours the numeric part of a length only. Does not accept units.

    This is faster than scourLength on elements guaranteed not to
    contain units.
    """
    if not isinstance(length, Decimal):
        length = getcontext().create_decimal(str(length))
    initial_length = length

    # reduce numeric precision
    # plus() corresponds to the unary prefix plus operator and applies
    # context precision and rounding
    if is_control_point:
        length = scouringContextC.plus(length)
    else:
        length = scouringContext.plus(length)

    # remove trailing zeroes as we do not care for significance
    intLength = length.to_integral_value()
    if length == intLength:
        length = Decimal(intLength)
    else:
        length = length.normalize()

    # Gather the non-scientific notation version of the coordinate.
    # Re-quantize from the initial value to prevent unnecessary loss of precision
    # (e.g. 123.4 should become 123, not 120 or even 100)
    nonsci = f"{length:f}"
    nonsci = f"{initial_length.quantize(Decimal(nonsci)):f}"
    if not renderer_workaround:
        if len(nonsci) > 2 and nonsci[:2] == "0.":
            nonsci = nonsci[1:]  # remove the 0, leave the dot
        elif len(nonsci) > 3 and nonsci[:3] == "-0.":
            nonsci = "-" + nonsci[2:]  # remove the 0, leave the minus and dot
    return_value = nonsci

    # Gather the scientific notation version of the coordinate which
    # can only be shorter if the length of the number is at least
    # 4 characters (e.g. 1000 = 1e3).
    if len(nonsci) > 3:
        # We have to implement this ourselves since both 'normalize()'
        # and 'to_sci_string()' don't handle negative exponents in a
        # reasonable way (e.g. 0.000001 remains unchanged)
        exponent = length.adjusted()  # how far do we have to shift the dot?
        length = length.scaleb(-exponent).normalize()  # shift the dot and remove potential trailing zeroes

        sci = str(length) + "e" + str(exponent)

        if len(sci) < len(nonsci):
            return_value = sci

    return return_value


def reducePrecision(element):
    """
    Because opacities, letter spacings, stroke widths and all that don't need
    to be preserved in SVG files with 9 digits of precision.

    Takes all of these attributes, in the given element node and its children,
    and reduces their precision to the current Decimal context's precision.
    Also checks for the attributes actually being lengths, not 'inherit', 'none'
    or anything that isn't an SVGLength.

    Returns the number of bytes saved after performing these reductions.
    """
    num = 0

    styles = _getStyle(element)
    for lengthAttr in [
        "opacity",
        "flood-opacity",
        "fill-opacity",
        "stroke-opacity",
        "stop-opacity",
        "stroke-miterlimit",
        "stroke-dashoffset",
        "letter-spacing",
        "word-spacing",
        "kerning",
        "font-size-adjust",
        "font-size",
        "stroke-width",
    ]:
        val = element.getAttribute(lengthAttr)
        if val != "":
            valLen = SVGLength(val)
            if valLen.units != Unit.INVALID:  # not an absolute/relative size or inherit, can be % though
                newVal = scourLength(val)
                if len(newVal) < len(val):
                    num += len(val) - len(newVal)
                    element.setAttribute(lengthAttr, newVal)
        # repeat for attributes hidden in styles
        if lengthAttr in styles:
            val = styles[lengthAttr]
            valLen = SVGLength(val)
            if valLen.units != Unit.INVALID:
                newVal = scourLength(val)
                if len(newVal) < len(val):
                    num += len(val) - len(newVal)
                    styles[lengthAttr] = newVal
    _setStyle(element, styles)

    for child in element.childNodes:
        if child.nodeType == Node.ELEMENT_NODE:
            num += reducePrecision(child)

    return num


def optimizeAngle(angle):
    """
    Because any rotation can be expressed within 360 degrees
    of any given number, and since negative angles sometimes
    are one character longer than corresponding positive angle,
    we shorten the number to one in the range to [-90, 270[.
    """
    # First, we put the new angle in the range ]-360, 360[.
    # The modulo operator yields results with the sign of the
    # divisor, so for negative dividends, we preserve the sign
    # of the angle.
    if angle < 0:
        angle %= -360
    else:
        angle %= 360
    # 720 degrees is unnecessary, as 360 covers all angles.
    # As "-x" is shorter than "35x" and "-xxx" one character
    # longer than positive angles <= 260, we constrain angle
    # range to [-90, 270[ (or, equally valid: ]-100, 260]).
    if angle >= 270:
        angle -= 360
    elif angle < -90:
        angle += 360
    return angle


# helper of optimizeTransforms
def optimizeTransform(transform):
    """
    Optimises a series of transformations parsed from a single
    transform="" attribute.

    The transformation list is modified in-place.
    """
    # FIXME: reordering these would optimize even more cases:
    #   first: Fold consecutive runs of the same transformation
    #   extra: Attempt to cast between types to create sameness:
    # 		  "matrix(0 1 -1 0 0 0) rotate(180) scale(-1)" all
    # 		  are rotations (90, 180, 180) -- thus "rotate(90)"
    #  second: Simplify transforms where numbers are optional.
    #   third: Attempt to simplify any single remaining matrix()
    #
    # if there's only one transformation and it's a matrix,
    # try to make it a shorter non-matrix transformation
    # NOTE: as matrix(a b c d e f) in SVG means the matrix:
    # |¯  a  c  e  ¯|   make constants   |¯  A1  A2  A3  ¯|
    # |   b  d  f   |  translating them  |   B1  B2  B3   |
    # |_  0  0  1  _|  to more readable  |_  0	0   1  _|
    if len(transform) == 1 and transform[0][0] == "matrix":
        matrix = A1, B1, A2, B2, A3, B3 = transform[0][1]
        # |¯  1  0  0  ¯|
        # |   0  1  0   |  Identity matrix (no transformation)
        # |_  0  0  1  _|
        if matrix == [1, 0, 0, 1, 0, 0]:
            del transform[0]
        # |¯  1  0  X  ¯|
        # |   0  1  Y   |  Translation by (X, Y).
        # |_  0  0  1  _|
        elif A1 == 1 and A2 == 0 and B1 == 0 and B2 == 1:
            transform[0] = ("translate", [A3, B3])
        # |¯  X  0  0  ¯|
        # |   0  Y  0   |  Scaling by (X, Y).
        # |_  0  0  1  _|
        elif A2 == 0 and A3 == 0 and B1 == 0 and B3 == 0:
            transform[0] = ("scale", [A1, B2])
        # |¯  cos(A) -sin(A)	0	¯|  Rotation by angle A,
        # |   sin(A)  cos(A)	0	 |  clockwise, about the origin.
        # |_	0	   0	   1	_|  A is in degrees, [-180...180].
        elif (
            A1 == B2
            and -1 <= A1 <= 1
            and A3 == 0
            and -B1 == A2
            and -1 <= B1 <= 1
            and B3 == 0
            # as cos² A + sin² A == 1 and as decimal trig is approximate:
            # FIXME: the "epsilon" term here should really be some function
            # 		of the precision of the (sin|cos)_A terms, not 1e-15:
            and abs((B1**2) + (A1**2) - 1) < Decimal("1e-15")
        ):
            sin_A, cos_A = B1, A1
            # while asin(A) and acos(A) both only have an 180° range
            # the sign of sin(A) and cos(A) varies across quadrants,
            # letting us hone in on the angle the matrix represents:
            # -- => < -90 | -+ => -90..0 | ++ => 0..90 | +- => >= 90
            #
            # http://en.wikipedia.org/wiki/File:Sine_cosine_plot.svg
            # shows asin has the correct angle the middle quadrants:
            A = Decimal(str(math.degrees(math.asin(float(sin_A)))))
            if cos_A < 0:  # otherwise needs adjusting from the edges
                if sin_A < 0:
                    A = -180 - A
                else:
                    A = 180 - A
            transform[0] = ("rotate", [A])

    # Simplify transformations where numbers are optional.
    for type, args in transform:
        if type == "translate":
            # Only the X coordinate is required for translations.
            # If the Y coordinate is unspecified, it's 0.
            if len(args) == 2 and args[1] == 0:
                del args[1]
        elif type == "rotate":
            args[0] = optimizeAngle(args[0])  # angle
            # Only the angle is required for rotations.
            # If the coordinates are unspecified, it's the origin (0, 0).
            if len(args) == 3 and args[1] == args[2] == 0:
                del args[1:]
        elif type == "scale":
            # Only the X scaling factor is required.
            # If the Y factor is unspecified, it's the same as X.
            if len(args) == 2 and args[0] == args[1]:
                del args[1]

    # Attempt to coalesce runs of the same transformation.
    # Translations followed immediately by other translations,
    # rotations followed immediately by other rotations,
    # scaling followed immediately by other scaling,
    # are safe to add.
    # Identity skewX/skewY are safe to remove, but how do they accrete?
    # |¯	1	 0	0	¯|
    # |   tan(A)  1	0	 |  skews X coordinates by angle A
    # |_	0	 0	1	_|
    #
    # |¯	1  tan(A)  0	¯|
    # |	 0	 1	0	 |  skews Y coordinates by angle A
    # |_	0	 0	1	_|
    #
    # FIXME: A matrix followed immediately by another matrix
    #   would be safe to multiply together, too.
    i = 1
    while i < len(transform):
        currType, currArgs = transform[i]
        prevType, prevArgs = transform[i - 1]
        # Translation followed immediately by another translation:
        if currType == prevType == "translate":
            prevArgs[0] += currArgs[0]  # x
            # for y, only add if the second translation has an explicit y
            if len(currArgs) == 2:
                if len(prevArgs) == 2:
                    prevArgs[1] += currArgs[1]  # y
                elif len(prevArgs) == 1:
                    prevArgs.append(currArgs[1])  # y
            del transform[i]
            if prevArgs[0] == prevArgs[1] == 0:
                # Identity translation!
                i -= 1
                del transform[i]
        # Rotation followed immediately by another rotation:
        elif currType == prevType == "rotate" and len(prevArgs) == len(currArgs) == 1:
            # Only coalesce if both rotations are from the origin.
            prevArgs[0] = optimizeAngle(prevArgs[0] + currArgs[0])
            del transform[i]
        # Scaling followed immediately by another scaling:
        elif currType == prevType == "scale":
            prevArgs[0] *= currArgs[0]  # x
            # handle an implicit y
            if len(prevArgs) == 2 and len(currArgs) == 2:
                # y1 * y2
                prevArgs[1] *= currArgs[1]
            elif len(prevArgs) == 1 and len(currArgs) == 2:
                # create y2 = uniformscalefactor1 * y2
                prevArgs.append(prevArgs[0] * currArgs[1])
            elif len(prevArgs) == 2 and len(currArgs) == 1:
                # y1 * uniformscalefactor2
                prevArgs[1] *= currArgs[0]
            del transform[i]
            # if prevArgs is [1] or [1, 1], then it is effectively an
            # identity matrix and can be removed.
            # Identity matrix followed by scaling:
            if prevArgs[0] == 1 and (len(prevArgs) == 1 or prevArgs[1] == 1):
                # Identity scale!
                i -= 1
                del transform[i]
        else:
            i += 1

    # Some fixups are needed for single-element transformation lists, since
    # the loop above was to coalesce elements with their predecessors in the
    # list, and thus it required 2 elements.
    i = 0
    while i < len(transform):
        currType, currArgs = transform[i]
        if (currType == "skewX" or currType == "skewY") and len(currArgs) == 1 and currArgs[0] == 0:
            # Identity skew!
            del transform[i]
        elif (currType == "rotate") and len(currArgs) == 1 and currArgs[0] == 0:
            # Identity rotation!
            del transform[i]
        else:
            i += 1


def optimizeTransforms(element, options):
    """
    Attempts to optimise transform specifications on the given node and its children.

    Returns the number of bytes saved after performing these reductions.
    """
    num = 0

    for transformAttr in ["transform", "patternTransform", "gradientTransform"]:
        val = element.getAttribute(transformAttr)
        if val != "":
            transform = svg_transform_parser.parse(val)

            optimizeTransform(transform)

            newVal = serializeTransform(transform)

            if len(newVal) < len(val):
                if len(newVal):
                    element.setAttribute(transformAttr, newVal)
                else:
                    element.removeAttribute(transformAttr)
                num += len(val) - len(newVal)

    for child in element.childNodes:
        if child.nodeType == Node.ELEMENT_NODE:
            num += optimizeTransforms(child, options)

    return num


#################################################
# 	helper methods to generate svg elements	#
#################################################


def get_empty_document(
    vbwidth: float,
    vbheight: float,
    docWeight: float,
    docHeight: float,
    no_keep_ratio: bool = False,
    metadata_dict: dict = None,
) -> str:
    """Generate empty SVG document with specified dimensions.

    Args:
        vbwidth: Viewbox width
        vbheight: Viewbox height
        docWeight: Document width
        docHeight: Document height
        no_keep_ratio: If True, don't add preserveAspectRatio attribute
            (for negative viewBox coordinates)
        metadata_dict: Optional dictionary with FBF metadata fields. If
            None, uses minimal metadata. See generate_fbf_metadata() for
            supported keys.

    Returns:
        SVG document string
    """
    doc_parts = []
    doc_parts.append(get_document_begin(vbwidth, vbheight, docWeight, docHeight, no_keep_ratio, metadata_dict))
    doc_parts.append(get_document_desc())
    doc_parts.append(get_animation_scene(vbwidth, vbheight))
    doc_parts.append(get_document_defs(vbwidth, vbheight))
    doc_parts.append(get_document_end())

    s = "".join(doc_parts)

    return s


def generate_fbf_metadata(metadata_dict):
    """Generate comprehensive FBF metadata block according to FBF_METADATA_SPEC.md.

    Args:
        metadata_dict: Dictionary containing metadata fields. Supported keys:

            # Animation Properties (required in spec)
            - frameCount: Total number of frames (integer)
            - fps: Frames per second (decimal)
            - duration: Total duration in seconds (decimal)
            - playbackMode: Animation playback mode (enum: once, loop,
              pingpong_loop, etc.)
            - width: Canvas width in pixels (integer)
            - height: Canvas height in pixels (integer)
            - viewBox: ViewBox coordinates (string, e.g., "0 0 800 600")
            - aspectRatio: Aspect ratio (string, e.g., "4:3", "16:9")
            - firstFrameWidth: Original first frame width (integer)
            - firstFrameHeight: Original first frame height (integer)

            # Authoring & Provenance
            - title: Animation title (dc:title)
            - episodeNumber: Episode number in series (integer)
            - episodeTitle: Episode-specific title (string)
            - creators: Current animation creators, comma-separated (string)
            - originalCreators: Original content creators (string)
            - creator: Primary creator - legacy single value (dc:creator)
            - description: Animation description (dc:description)
            - date: Creation date ISO8601 (dc:date)
            - language: Content language code (dc:language, e.g., "en",
              "it")
            - originalLanguage: Original production language (e.g.,
              "en-US", "ja-JP")
            - copyrights: Copyright statement (string)
            - rights: License/usage rights (dc:rights)
            - website: Official website or info page (URL)
            - keywords: Search keywords, comma-separated (string)
            - source: Original source/software (dc:source)
            - sourceFramesPath: Original frames location (string)

            # Generator Information (required in spec)
            - generator: Generator software name (string, default "svg2fbf")
            - generatorVersion: Generator version semver (string)
            - generatedDate: File generation timestamp ISO8601 (string)
            - formatVersion: FBF spec version (string, default "1.0")
            - precisionDigits: Coordinate precision (integer)
            - precisionCDigits: Control point precision (integer)

            # Content Features
            - useCssClasses: Contains CSS classes (boolean)
            - hasBackdropImage: Has static backdrop bitmap (boolean)
            - useExternalMedia: References external media files
              (boolean)
            - useExternalFonts: References external fonts (boolean)
            - useEmbeddedImages: Contains base64-embedded images (boolean)
            - useMeshGradient: Uses SVG 2.0 mesh gradients (boolean,
              required)
            - hasInteractivity: Has interactive elements (boolean)
            - interactivityType: Type of interactivity (enum: none,
              click_to_start, etc.)
            - hasJavaScript: Contains JavaScript (boolean)
            - hasCSS: Contains CSS styles (boolean)
            - containsText: Contains text elements (boolean)
            - colorProfile: Color profile used (string, e.g., "sRGB")

    Returns:
        String containing complete <metadata> XML block with RDF/XML
        structure
    """
    # Why: Start building the metadata block with proper namespace
    # declarations
    # Why: Use rdf:Description instead of cc:Work to allow fbf:
    # namespace fields
    lines = []
    lines.append("    <metadata>")
    lines.append('    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"')
    lines.append('             xmlns:dc="http://purl.org/dc/elements/1.1/"')
    lines.append('             xmlns:cc="http://creativecommons.org/ns#"')
    lines.append('             xmlns:fbf="http://opentoonz.github.io/fbf/1.0#">')
    lines.append('        <rdf:Description rdf:about="">')

    # Why: Add mandatory format and type fields as per SVG/RDF spec
    lines.append("        <dc:format>image/svg+xml</dc:format>")
    lines.append('        <dc:type rdf:resource="http://purl.org/dc/dcmitype/MovingImage" />')

    # Why: Helper function to add metadata field - ALWAYS adds field
    # even if empty (strict validation requirement)
    def add_field(key, namespace_prefix, xml_tag, value_formatter=None):
        """Add metadata field - ALWAYS includes the field even if empty.

        Args:
            key: Dictionary key to look up
            namespace_prefix: XML namespace prefix (dc, fbf, etc.)
            xml_tag: XML tag name
            value_formatter: Optional function to format the value

        Note:
            Following strict FBF.SVG validation requirements, all fields
            must be present. Empty/missing optional fields are
            represented as empty XML elements.
        """
        if key in metadata_dict and metadata_dict[key] is not None and metadata_dict[key] != "":
            value = metadata_dict[key]
            # Why: Apply custom formatter if provided
            if value_formatter:
                value = value_formatter(value)
            # Why: Format boolean values as lowercase strings
            if isinstance(value, bool):
                value = str(value).lower()
            lines.append(f"        <{namespace_prefix}:{xml_tag}>{value}</{namespace_prefix}:{xml_tag}>")
        else:
            # Why: Add empty element for missing/empty fields
            # (strict validation requirement)
            lines.append(f"        <{namespace_prefix}:{xml_tag} />")

    # Why: Animation Properties section - organize metadata by
    # category for readability
    # Why: dc:title is Dublin Core standard field
    add_field("title", "dc", "title")
    add_field("creator", "dc", "creator")
    add_field("description", "dc", "description")
    add_field("date", "dc", "date")
    add_field("language", "dc", "language")
    add_field("rights", "dc", "rights")
    add_field("source", "dc", "source")

    # Why: FBF-specific authoring fields
    add_field("episodeNumber", "fbf", "episodeNumber")
    add_field("episodeTitle", "fbf", "episodeTitle")
    add_field("creators", "fbf", "creators")
    add_field("originalCreators", "fbf", "originalCreators")
    add_field("copyrights", "fbf", "copyrights")
    add_field("website", "fbf", "website")
    add_field("originalLanguage", "fbf", "originalLanguage")
    add_field("keywords", "fbf", "keywords")
    add_field("sourceFramesPath", "fbf", "sourceFramesPath")

    # Why: Animation properties - dimensions and timing
    add_field("frameCount", "fbf", "frameCount")
    add_field("fps", "fbf", "fps")
    add_field("duration", "fbf", "duration")
    add_field("playbackMode", "fbf", "playbackMode")
    add_field("width", "fbf", "width")
    add_field("height", "fbf", "height")
    add_field("viewBox", "fbf", "viewBox")
    add_field("aspectRatio", "fbf", "aspectRatio")
    add_field("firstFrameWidth", "fbf", "firstFrameWidth")
    add_field("firstFrameHeight", "fbf", "firstFrameHeight")

    # Why: Generator information - required by spec
    add_field("generator", "fbf", "generator")
    add_field("generatorVersion", "fbf", "generatorVersion")
    add_field("generatedDate", "fbf", "generatedDate")
    add_field("formatVersion", "fbf", "formatVersion")
    add_field("precisionDigits", "fbf", "precisionDigits")
    add_field("precisionCDigits", "fbf", "precisionCDigits")

    # Why: Content features - what the FBF file contains
    add_field("useCssClasses", "fbf", "useCssClasses")
    add_field("hasBackdropImage", "fbf", "hasBackdropImage")
    add_field("useExternalMedia", "fbf", "useExternalMedia")
    add_field("useExternalFonts", "fbf", "useExternalFonts")
    add_field("useEmbeddedImages", "fbf", "useEmbeddedImages")
    add_field("useMeshGradient", "fbf", "useMeshGradient")
    add_field("hasInteractivity", "fbf", "hasInteractivity")
    add_field("interactivityType", "fbf", "interactivityType")
    add_field("hasJavaScript", "fbf", "hasJavaScript")
    add_field("hasCSS", "fbf", "hasCSS")
    add_field("containsText", "fbf", "containsText")
    add_field("colorProfile", "fbf", "colorProfile")

    # Why: Close the RDF structure
    lines.append("        </rdf:Description>")
    lines.append("    </rdf:RDF>")
    lines.append("    </metadata>")

    # Why: Join all lines with newlines and return as single string
    return "\n".join(lines)


def get_document_begin(vbwidth, vbheight, docWidth, docHeight, no_keep_ratio=False, metadata_dict=None):
    """Generate SVG document beginning with optional comprehensive metadata.

    Args:
        vbwidth: ViewBox width
        vbheight: ViewBox height
        docWidth: Document width
        docHeight: Document height
        no_keep_ratio: If True, don't add preserveAspectRatio attribute
            (for negative viewBox coordinates)
        metadata_dict: Optional dictionary with FBF metadata fields. If
            None, uses minimal metadata. See generate_fbf_metadata() for
            supported keys.

    Returns:
        String containing SVG opening tag with metadata block
    """
    # Why: Build preserveAspectRatio attribute conditionally based on
    # --no-keep-ratio flag
    # Why: Some animations with negative viewBox coordinates need
    # preserveAspectRatio="none" or omitted
    preserve_aspect_ratio_attr = "" if no_keep_ratio else '\n    preserveAspectRatio="xMidYMid meet"'

    # Why: Generate comprehensive or minimal metadata based on
    # parameter
    # Why: If metadata_dict is provided, use new comprehensive
    # generator; otherwise fall back to minimal
    if metadata_dict is not None:
        metadata_block = generate_fbf_metadata(metadata_dict)
    else:
        # Why: Fallback to minimal metadata for backwards compatibility
        metadata_block = """    <metadata>
    <rdf:RDF>
        <cc:Work
            rdf:about="">
        <dc:format>image/svg+xml</dc:format>
        <dc:type
            rdf:resource="http://purl.org/dc/dcmitype/MovingImage" />
        <dc:title></dc:title>
        </cc:Work>
    </rdf:RDF>
    </metadata>"""

    return (
        '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<svg
    xmlns:svg="http://www.w3.org/2000/svg"
    xmlns="http://www.w3.org/2000/svg"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    baseProfile="full"
    version="1.1"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:cc="http://creativecommons.org/ns#"
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'''
        + ('\n    xmlns:fbf="http://opentoonz.github.io/fbf/1.0#"' if metadata_dict is not None else "")
        + '''
    image-rendering="optimizeSpeed"'''
        + preserve_aspect_ratio_attr
        + '''
    width="'''
        + str(docWidth)
        + '''"
    height="'''
        + str(docHeight)
        + """"
    viewBox="0 0 """
        + str(vbwidth)
        + """px """
        + str(vbheight)
        + """px"
    >
     <!--	FILE GENERATED BY svg2fbf v"""
        + SEMVERSION
        + """	-->
"""
        + metadata_block
        + """

"""
    )


def get_document_desc():
    return """
    <desc>
__________________________________________________________

    ╔════════════════════════════════════════╗
    ║	This is a FBF.SVG animation file	 ║
    ╚════════════════════════════════════════╝

FBF.SVG stands for "Frame-By-Frame SVG".

FBF.SVG is a format meant to be the MPEG of vector animations.
It is designed to be compact, portable, and optimized for streaming.

The FBF.SVG format originated from the OpenToonz community
(https://opentoonz.github.io), created as an open standard for
frame-by-frame vector animations exported from OpenToonz and other
professional 2D animation software.

The following are some of the mandatory specifications:

    - The FBF.SVG format is a subset of the SVG 1.1 Full profile.

    - No CSS or external JavaScript allowed. No imperative scripting.

    - Only exception: mesh gradient polyfill script (if meshgradients present).

    - The file is minified because it is a format meant for the
      exchange and playback of vector encoded video animations,
      like those exported by OpenToonz or other vector applications.

    - The FBF.SVG format is designed to be played as an XML stream, so
      each frame is encoded in a way to include only the
      differences from the previous frame and minimize the size.

    - The structure of the FBF.SVG file must follow the schema
      available online[1], and it should be composed by the
      following parts disposed in this exact order:

        SVG Root

        ├── metadata (optional)

        ├── desc (required)

        ├── ANIMATION_BACKDROP

        │   ├── STAGE_BACKGROUND (Z-order: behind animation)

        │   ├── ANIMATION_STAGE

        │   │   └── ANIMATED_GROUP

        │   │       └── PROSKENION

        │   │           └── &lt;animate&gt;

        │   └── STAGE_FOREGROUND (Z-order: in front of animation)

        ├── OVERLAY_LAYER (Z-order: superimposed on all)

        ├── defs

        │   ├── SHARED_DEFINITIONS

        │   └── FRAME00001, FRAME00002, ...

        └── script (optional, last)

    - The PROSKENION Animation element must always have the
      following attributes set at these values:

                attributeName=\"xlink:href\"

                begin=\"0s\"

                calcMode=\"discrete\"

                repeatCount=\"indefinite\"

    - The 'values' attribute must contain a string with the
      concatenated id of all the group frames present in the
      'FRAMES' group under the 'defs' section. The order is
      the same order of the playback.

    - The frame group IDs must have the form: 'FRAME0...1',
      where the digits are the left-zero-padded frame numbers,
      with the frame count starting from 1 not 0. The number of
      digits varies according to the number of frames, but
      there should always be an additional 0 before the other
      digits. Frame group IDs like 'FRAME1' are not allowed.

    - The attribute 'repeatCount' can be changed to allow looping,
      repeat once or ping-pong modes.

    - The PROSKENION 'use' element should have the xlink:href
      attribute set with the value of the first frame id, for
      example:

                xlink:href=\"#FRAME0001\"

    - The value of the 'dur' attribute of the PROSKENION animation should be
      expressed in seconds. The value represents the duration of the
      entire animated sequence. For example if you have "1.0s"
      this is equal to each frame duration multiplied by the number of
      frames. For example: for an animation of 3 frames, "1.0s" means 0.333*3,
      where 0.333s is the 'Frame Duration' (FD) in seconds. A FD of 1.0 means
      1 frame per second (1 fps). For 60fps the frame duration is "0.01667s".
      For 24fps you have "0.04167" seconds. To get it just divide 1 second
      for the number of frames per second (fps) that you want.
      More explicitly:

                fps = 60

                FD = 1/60=0.0166666... approx: 0.01667s

                NumberOfFrames = 3

                dur = 0.01667*3 = 0.05001s

        The general formula for 'dur' then is:

                dur = (1/fps)*NumberOfFrames

        And the inverse formulas for fps and FD are:

                fps = NumberOfFrames/dur

                FD  = 1/fps

    - The FBF.SVG files extension must ALWAYS be ".fbf.svg".

    - Document has always the attributes height and width set at 100%.

    - SVG attribute preserveAspectRatio must be set as "xMidYMid meet".

    - Viewport values are mandatory and should be defined in pixels,
      with the first two values always set to 0.

    - Any rendering server recognizing this format must render it
      only in SECURE ANIMATED MODE.[2]

    - No external resources allowed (except optional meshgradient polyfill).

    - All resources must be embedded in base64.

METADATA:

    - FBF.SVG files include comprehensive RDF/XML metadata in the
      &lt;metadata&gt; element

    - Metadata uses Dublin Core (dc:), Creative Commons (cc:), and
      FBF.SVG (fbf:) namespaces

    - Required metadata fields include: title, creator, date, format,
      language

    - Optional fields: description, subject, rights, license, source

    - FBF-specific fields: frameCount, frameRate, duration,
      generatorName, generatorVersion

    - All metadata is machine-readable and follows the FBF.SVG
      metadata specification[3]



    For more information about the FBF.SVG format and svg2fbf:

    https://github.com/Emasoft/svg2fbf

    For information about OpenToonz:

    https://opentoonz.github.io

    https://github.com/opentoonz/opentoonz



[1] Schema and specification: https://github.com/Emasoft/svg2fbf

[2] Secure animated mode:
    https://www.w3.org/TR/SVG/conform.html#secure-animated-mode

[3] Metadata specification:
    https://github.com/Emasoft/svg2fbf/blob/main/docs/FBF_METADATA_SPEC.md



___________________________________________________________________



    </desc>

    """


def get_document_group(group_id):
    return (
        '''
    <g id="'''
        + group_id
        + """">

    </g>
    """
    )


def get_animation_scene(width, height):
    return """
<!--	ANIMATION BACKDROP	  -->
<g id="ANIMATION_BACKDROP" >

<!--	STAGE BACKGROUND (Z-order: behind animation)	-->
<g id="STAGE_BACKGROUND" >
     <!-- Empty group for background SVG elements (dynamic API) -->
</g>
<!--	END OF STAGE BACKGROUND	-->

<!--	ANIMATION STAGE	-->
 <g id="ANIMATION_STAGE" >

<!--	ANIMATED GROUP	 -->
<g id="ANIMATED_GROUP" >
  <use id="PROSKENION" xlink:href="#FRAME0001"  overflow="visible"  >
       <animate attributeName="xlink:href"
      values="#FRAME0001"
      begin="0s" repeatCount="1" dur="1.00s" calcMode="discrete" />
  </use>
</g>
  <!--	END OF ANIMATED GROUP	-->
</g>
    <!--	END OF ANIMATION STAGE	 -->

<!--	STAGE FOREGROUND (Z-order: in front of animation)	-->
<g id="STAGE_FOREGROUND" >
     <!-- Empty group for foreground SVG elements (dynamic API) -->

</g>
<!--	END OF STAGE FOREGROUND	-->

</g>
<!--	END OF ANIMATION BACKDROP	  -->

<!--	OVERLAY LAYER (Z-order: superimposed on all)	-->
<g id="OVERLAY_LAYER" >
     <!-- Empty group for badges, titles, logos, subtitles, borders, -->
     <!-- PiP (dynamic API) -->
</g>
<!--	END OF OVERLAY LAYER	-->

"""


def get_document_defs(width, height):
    return """
    <defs>

     <g id="SHARED_DEFINITIONS">


     </g>

    <!--	FRAMES	 -->

    </defs>
    """


def get_document_end():
    return """  \n</svg>"""


##############
# 	main	#
##############


def main():
    global log

    if options.show_copyright_info:
        ppp(COPYRIGHT_INFO)
        exit()

    if options.input_folder[-1] != "/":
        options.input_folder += "/"

    if options.output_path[-1] != "/":
        options.output_path += "/"

    doProfiling = False

    # START PROFILING #####
    if doProfiling:
        pr = cProfile.Profile()
        pr.enable()
    ###########################

    start = time.time()
    generate_fbfsvg_animation()
    end = time.time()
    # calculate run-time in ms
    duration = int(round((end - start) * 1000.0))
    ppp(f"Total processing time: {round(duration / 1000.0, 2)} seconds ({duration} ms)")
    if log is not None:
        ppp(log)

    # END PROFILING ######
    if doProfiling:
        pr.disable()
        pr.print_stats(sort=SortKey.CUMULATIVE)
    # pr.dump_stats("prof.txt")
    ###########################

    return


#########################
# 	CLI entry point	#
#########################


###################################################
# Mesh Gradient Polyfill Injection
###################################################


def load_mesh_gradient_polyfill():
    """
    Load the mesh gradient polyfill from the extracted polyfill file.

    The polyfill is the official Inkscape mesh gradient polyfill, extracted
    complete with <script> tags and already properly HTML-entity escaped.

    Returns:
        str: The complete polyfill (including <script> tags, already escaped)

    Raises:
        FileNotFoundError: If meshgradient_polyfill.txt is not found
    """
    polyfill_path = os.path.join(os.path.dirname(__file__), "meshgradient_polyfill.txt")

    try:
        with open(polyfill_path, encoding="utf-8") as f:
            polyfill_content = f.read().strip()
        return polyfill_content
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Mesh gradient polyfill not found at: {polyfill_path}\nThe FBF format requires meshgradient_polyfill.txt for cross-browser compatibility.") from e


def inject_mesh_gradient_polyfill(svg_string):
    """
    Inject the mesh gradient polyfill into the SVG string (only if
    meshgradient elements are present).

    The polyfill is loaded from meshgradient_polyfill.txt which
    contains the official Inkscape polyfill already properly escaped
    and wrapped in <script> tags. We insert it as-is before the closing
    </svg> tag.

    Args:
        svg_string (str): The serialized SVG document

    Returns:
        str: SVG string with injected polyfill (or unchanged if no
             meshgradients)
    """
    import re

    # Check if the SVG actually contains meshgradient elements
    # Why: Only inject polyfill if needed - saves ~16KB when not
    # using mesh gradients
    if not re.search(r"<meshgradient[\s>]", svg_string, re.IGNORECASE):
        return svg_string

    # Load polyfill (already includes <script> tags and is properly
    # escaped)
    polyfill_element = load_mesh_gradient_polyfill()

    # Find the closing </svg> tag and inject the polyfill before it
    # Use case-insensitive search since XML tags could be uppercase
    # Pattern matches </svg> with optional whitespace and
    # case-insensitive
    pattern = re.compile(r"(\s*</svg>\s*)$", re.IGNORECASE)

    match = pattern.search(svg_string)
    if match:
        # Insert polyfill before </svg>
        injection_point = match.start()
        svg_with_polyfill = svg_string[:injection_point] + "\n" + polyfill_element + "\n" + svg_string[injection_point:]
        return svg_with_polyfill
    else:
        # Fallback: append at end if </svg> not found
        # (should never happen)
        return svg_string + "\n" + polyfill_element + "\n</svg>\n"


def cli():
    """
    CLI entry point function for the svg2fbf command-line tool.

    # EXAMPLE ARGS:
    sys.argv = [
        "svg2fbf.py",
        "--input_folder=./examples/quaticK2_oca",
        "--output_path=./fbfsvg_output",
        "--filename=quaticK2_oca.fbf.svg",
        "--play_on_click",
        "--speed=23.0",
        "--animation_type=loop",
    ]
    """
    global options

    cl_parser = setup_command_line_parser()
    options = cl_parser.parse_args()

    # Handle positional YAML config file argument
    # Why: Enable simple usage like `svg2fbf scene_1.yaml` instead of
    # requiring --config flag
    if options.config_file:
        if options.config_file.endswith((".yaml", ".yml")):
            # If both positional config and --config are provided,
            # --config takes priority with a warning
            if options.config and options.config != options.config_file:
                add2log(f"⚠️  Both positional config '{options.config_file}' and --config '{options.config}' provided. Using --config value.")
            else:
                options.config = options.config_file
        else:
            cl_parser.error(f"Unknown positional argument: {options.config_file}\nDid you mean to specify a YAML config file? File should end with .yaml or .yml")

    # Load YAML configuration if provided - Merge with CLI options
    # Why: Allow batch processing with config files, CLI args take priority
    yaml_config = load_yaml_config(options.config)
    options = merge_config_with_cli(yaml_config, options)

    # Get explicit frame list from config if provided (generation cards)
    # Why: Generation cards specify exact frames with dependencies,
    # bypassing folder scanning
    explicit_frames = get_frame_list_from_config(yaml_config, options.input_folder)
    if explicit_frames is not None:
        options.explicit_frames = explicit_frames
    else:
        options.explicit_frames = None

    # Handle --version flag
    if options.show_version:
        print_version_only()
        sys.exit(0)

    # Handle --help flag
    if options.show_help:
        print_version_banner()
        cl_parser.print_help()
        sys.exit(0)

    # Show version banner (unless in quiet mode)
    if not options.quiet_mode:
        print_version_banner()

    # make sure enough args are passed
    # Why: input_folder is optional when explicit frames are provided
    # via generation card
    if not all((options.output_path, options.output_filename)):
        cl_parser.error("Incorrect number of arguments - must specify output_path, output_filename")
    # Check input_folder only if no explicit frames provided
    if not hasattr(options, "explicit_frames") or options.explicit_frames is None:
        if not options.input_folder:
            cl_parser.error("Must specify input_folder (or provide explicit frames list in YAML config)")
    if float(options.fps) <= 0.0:
        cl_parser.error("fps value cannot be 0 or negative")
    if options.max_frames is not None and (int(options.max_frames) <= 1):
        cl_parser.error("max frames cannot be lower than 2")
    if options.animation_type not in TYPE_CHOICES:
        cl_parser.error("incorrect animation type name")

    if options.digits < 1:
        cl_parser.error("Number of significant digits has to be larger than zero, see --help")
    if options.cdigits > options.digits:
        cl_parser.error("WARNING: The value for '--cdigits' should be equal or lower than the value for '--digits', see --help")

    # Validate text2path flags
    if options.text2path:
        try:
            from svg_text2path import Text2PathConverter  # noqa: F401
        except ImportError:
            cl_parser.error("--text2path requires svg-text2path package. Install with: uv tool install svg2fbf[text2path]")
    if options.text2path_strict and not options.text2path:
        cl_parser.error("--text2path-strict requires --text2path flag")

    # Create output directory if it doesn't exist
    # Why: User convenience - don't force manual directory creation
    if options.output_path:
        try:
            output_dir = Path(options.output_path)
            if not output_dir.exists():
                output_dir.mkdir(parents=True, exist_ok=True)
                add2log(f"✓ Created output directory: {options.output_path}")
        except PermissionError:
            add2log(f"❌ Error: Cannot create output directory '{options.output_path}' - Permission denied")
            print_log_and_exit(1)
        except Exception as e:
            add2log(f"❌ Error: Cannot create output directory '{options.output_path}' - {e}")
            print_log_and_exit(1)

    main()


if __name__ == "__main__":
    cli()
