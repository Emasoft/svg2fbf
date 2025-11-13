"""
SVG Frame Processor using svg2fbf.py Logic

This module provides a thin wrapper around svg2fbf.py to process SVG frames
with the EXACT same dimension extraction and transformation logic that svg2fbf
uses when generating FBF animations.

The key principle: Instead of duplicating or extracting code from svg2fbf.py,
we IMPORT it directly. This ensures the test framework automatically stays
synchronized when svg2fbf.py changes.

Architecture:
    svg2fbf.py (unchanged)
        ↓ import
    svg2fbf_frame_processor.py (thin wrapper)
        ↓ calls
    test_frame_rendering.py
        ↓ subprocess
    render_svg.js (applies what Python calculated)

Usage:
    processor = SVG2FBFFrameProcessor()

    # Process first frame (establishes canonical dimensions)
    width, height, viewbox, transform = processor.process_frame(
        'frame_001.svg'
    )

    # Process subsequent frames (transforms to match first frame)
    width, height, viewbox, transform = processor.process_frame(
        'frame_002.svg',
        first_frame_dimensions=(width, height, viewbox)
    )
"""

import copy
import sys
from decimal import Context
from pathlib import Path

# Add src directory to path to import svg2fbf
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

import svg2fbf  # noqa: E402  # Import after path modification is intentional


class SVG2FBFFrameProcessor:
    """
    Wrapper around svg2fbf.py functions for processing individual SVG frames.

    This class ensures that SVG frames are processed with the EXACT same logic
    that svg2fbf.py uses, including:
    - Dimension extraction and defaults (1024x768)
    - ViewBox normalization
    - Uniform scaling transforms for subsequent frames

    Global State Management:
        svg2fbf.py uses global variables. This class saves/restores them
        before/after processing to ensure isolated execution in test context.
    """

    def __init__(self, digits: int = 28, cdigits: int = 28):
        """
        Initialize the frame processor.

        Args:
            digits: Coordinate precision (decimal digits).
                Default: 28 (maximum precision)
            cdigits: Control point precision (decimal digits).
                Default: 28 (maximum precision)

        Why maximum precision:
            Transform calculation adds one processing step to the chain, increasing
            potential rounding errors. Using maximum precision minimizes accumulated
            floating-point errors across the processing pipeline.
        """
        self.digits = digits
        self.cdigits = cdigits
        # Store svg2fbf globals that we'll need to save/restore
        self._saved_globals = {}

    def process_frame(
        self,
        svg_path: Path,
        first_frame_dimensions: tuple[float, float, str] | None = None,
    ) -> tuple[float, float, str, str | None, any]:
        """
        Process an SVG frame using svg2fbf's exact logic.

        This method calls properlySizeDoc() which transforms the frame content
        to match the first frame's dimensions when necessary. This transformation
        is ESSENTIAL for FBF animations where all frames must use the same
        resolution and viewBox as the first frame.

        Args:
            svg_path: Path to the SVG file to process
            first_frame_dimensions: Optional tuple of (width, height, viewBox_string)
                                   from the first frame. If provided, calculates
                                   transform to match first frame dimensions.

        Returns:
            Tuple of (width, height, viewBox_string, transform_string, svg_doc):
            - width: Calculated frame width
                (AFTER properlySizeDoc modifications)
            - height: Calculated frame height
                (AFTER properlySizeDoc modifications)
            - viewBox_string: ViewBox attribute value
                (AFTER properlySizeDoc modifications)
            - transform_string: SVG transform to apply (None for first frame)
            - svg_doc: Modified SVG document (minidom Document object)

        The logic follows svg2fbf.py's frame processing:
        1. First frame:
           - Load SVG
           - Call properlySizeDoc() to ensure width/height/viewBox
           - Extract final dimensions and viewBox
           - Returns (width, height, viewBox, None)

        2. Subsequent frames:
           - Load SVG
           - Call properlySizeDoc() to ensure width/height/viewBox
           - Call add_transform_to_match_input_frame_viewbox() with first frame dims
           - Extract transform from added <g> element
           - Returns (width, height, viewBox, transform)
        """
        # Save svg2fbf global state
        self._save_globals()

        try:
            # Create a minimal options object with required fields
            # Based on svg2fbf's command line parser defaults
            # IMPORTANT: Use instance precision settings for consistency
            # with FBF generation
            options = type(
                "Options",
                (),
                {
                    "output_filename": "animation.fbf.svg",
                    "output_path": "./",
                    "input_folder": "svg_frames/",
                    "fps": 1.0,
                    "animation_type": "once",
                    "max_frames": None,
                    "keep_xml_space_attribute": False,
                    "play_on_click": False,
                    "backdrop": "None",
                    "digits": self.digits,
                    "cdigits": self.cdigits,
                    "quiet_mode": False,
                    "show_copyright_info": False,
                },
            )()

            # Initialize svg2fbf globals that are normally set in
            # generate_fbfsvg_animation()
            # These are required by scourUnitlessLength() function
            svg2fbf.scouringContext = Context(prec=options.digits)
            svg2fbf.scouringContextC = Context(prec=options.cdigits)

            # Load SVG document using svg2fbf's load_svg function
            # This ensures we use the same parsing logic
            # Note: svg2fbf returns xml.dom.minidom.Document
            # svg2fbf.py may call sys.exit() on errors, so we catch SystemExit
            try:
                svg_doc = svg2fbf.load_svg(str(svg_path), options)
            except SystemExit as e:
                # Capture error log from svg2fbf if available
                error_msg = f"svg2fbf.load_svg() failed for {svg_path}"
                if hasattr(svg2fbf, "log") and svg2fbf.log:
                    error_msg += f"\nsvg2fbf error log:\n{svg2fbf.log}"
                raise RuntimeError(error_msg) from e

            # Get the root SVG element (minidom API)
            doc_element = svg_doc.documentElement

            # Call properlySizeDoc to ensure width/height/viewBox are properly set
            # This applies svg2fbf's defaults (1024x768) if dimensions are missing
            svg2fbf.current_filepath = str(svg_path)  # Set global for logging
            svg2fbf.properlySizeDoc(doc_element, options)

            # Get the viewBox using svg2fbf's exact logic
            # getViewBox returns: (vbX, vbY, vbWidth, vbHeight, doc_width, doc_height)
            # where vb* are viewBox values and doc_* are width/height attribute values
            vbX, vbY, vbWidth, vbHeight, doc_width, doc_height = svg2fbf.getViewBox(doc_element, options)

            # Use viewBox dimensions as the canonical width/height
            # (this matches svg2fbf's behavior)
            width = vbWidth
            height = vbHeight

            # Construct viewBox string
            viewbox_str = f"{vbX} {vbY} {vbWidth} {vbHeight}"

            # Initialize transform
            transform_str = None

            # If this is NOT the first frame, calculate transform to match first frame
            if first_frame_dimensions is not None:
                first_width, first_height, first_viewbox = first_frame_dimensions

                # CRITICAL: Return FIRST frame's viewBox for rendering,
                # NOT current frame's!
                # Why: FBF animation has ONE root SVG with first frame's viewBox
                # Individual frames are <g> groups with transforms,
                # not separate SVG elements
                # Example FBF structure:
                #   <svg viewBox="1200 0 1200 674">
                #     ← First frame's viewBox for entire animation
                #   <g id="FRAME00001">...</g>  ← No transform
                #   <g id="FRAME00002" transform="matrix(15.3...)">...</g>
                #     ← Scaled to fit
                # When rendering INPUT frames for comparison,
                # we must use the same approach:
                #   viewport=1200x674, viewBox="1200 0 1200 674",
                #   transform=matrix(...)
                viewbox_str = first_viewbox
                width = first_width
                height = first_height

                # Create a temporary <g> element to hold the transform
                # (svg2fbf's function adds transform to this element)
                current_frame_group = svg_doc.createElement("g")

                # Call svg2fbf's transform calculation function
                svg2fbf.add_transform_to_match_input_frame_viewbox(doc_element, first_viewbox, current_frame_group)

                # Extract the transform attribute that was added (minidom API)
                if current_frame_group.hasAttribute("transform"):
                    transform_str = current_frame_group.getAttribute("transform")

            return (width, height, viewbox_str, transform_str, svg_doc)

        finally:
            # Restore svg2fbf global state
            self._restore_globals()

    def _save_globals(self):
        """
        Save svg2fbf global variables before processing.

        This ensures that processing frames in test context doesn't
        affect svg2fbf's global state.
        """
        # Save globals that svg2fbf functions might use/modify
        if hasattr(svg2fbf, "current_filepath"):
            self._saved_globals["current_filepath"] = svg2fbf.current_filepath
        if hasattr(svg2fbf, "options"):
            self._saved_globals["options"] = copy.deepcopy(svg2fbf.options) if svg2fbf.options else None
        if hasattr(svg2fbf, "scouringContext"):
            self._saved_globals["scouringContext"] = svg2fbf.scouringContext
        if hasattr(svg2fbf, "scouringContextC"):
            self._saved_globals["scouringContextC"] = svg2fbf.scouringContextC
        if hasattr(svg2fbf, "log"):
            self._saved_globals["log"] = svg2fbf.log

    def _restore_globals(self):
        """
        Restore svg2fbf global variables after processing.
        """
        for key, value in self._saved_globals.items():
            setattr(svg2fbf, key, value)
        self._saved_globals.clear()


# Convenience function for standalone usage
def process_svg_frame(
    svg_path: Path,
    first_frame_dimensions: tuple[float, float, str] | None = None,
    digits: int = 28,
    cdigits: int = 28,
) -> tuple[float, float, str, str | None]:
    """
    Convenience function to process a single SVG frame.

    Args:
        svg_path: Path to SVG file
        first_frame_dimensions: Optional first frame dimensions
            for transform calculation
        digits: Coordinate precision (default: 28)
        cdigits: Control point precision (default: 28)

    See SVG2FBFFrameProcessor.process_frame() for details.
    """
    processor = SVG2FBFFrameProcessor(digits=digits, cdigits=cdigits)
    return processor.process_frame(svg_path, first_frame_dimensions)


def contains_smil_animations(svg_path: Path) -> bool:
    """
    Check if an SVG file contains SMIL animation elements.

    This function performs a fast text search for animation elements without
    fully parsing the XML, making it suitable for filtering large batches of files.

    Args:
        svg_path: Path to SVG file to check

    Returns:
        True if the file contains any SMIL animation elements, False otherwise

    SMIL Animation Elements Detected:
        - <animate>: Animates attribute values over time
        - <animateTransform>: Animates transformation attributes
        - <animateMotion>: Animates element position along a path
        - <animateColor>: Animates color attributes (deprecated but still used)
        - <set>: Sets attribute value at a specific time

    Why Filter SMIL Animations:
        FBF.SVG is designed for static frame-by-frame animations. SMIL animations
        are time-based and cannot be meaningfully converted to static frames.
        Including them would result in:
        - Incorrect rendering (only first frame state captured)
        - Unpredictable timing behavior
        - Misleading test results

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency when
        processing large batches of SVG files.
    """
    try:
        # Read file content as text for fast searching
        # Using 'utf-8' with error handling for robustness
        content = svg_path.read_text(encoding="utf-8", errors="ignore")

        # Check for SMIL animation elements
        # Using simple string search for performance
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
        # (will fail later with a more specific error)
        return False


# Backward compatibility alias (will be removed in future versions)
def contains_animations(svg_path: Path) -> bool:
    """Deprecated: Use contains_smil_animations() instead."""
    return contains_smil_animations(svg_path)


# JavaScript exceptions list - patterns that should NOT trigger filtering
JAVASCRIPT_EXCEPTIONS = [
    "meshgradient",  # Mesh gradient polyfill is allowed
    # Future exceptions can be added here
]


def contains_nested_svg(svg_path: Path) -> bool:
    """
    Check if an SVG file contains nested <svg> elements.

    Nested SVG elements can cause issues in FBF format, as they create
    separate coordinate systems and rendering contexts that don't translate
    well to static frame-by-frame animations.

    Args:
        svg_path: Path to SVG file to check

    Returns:
        True if the file contains nested <svg> elements, False otherwise

    Why Filter Nested SVG:
        - FBF.SVG expects a single root SVG element per frame
        - Nested SVG elements create complex coordinate transformations
        - May cause unexpected scaling or positioning in rendered frames
        - Can lead to rendering inconsistencies between browsers

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency.
    """
    try:
        content = svg_path.read_text(encoding="utf-8", errors="ignore")

        # Count <svg occurrences (case-insensitive)
        content_lower = content.lower()
        svg_count = content_lower.count("<svg")

        # More than one <svg tag means nested SVG
        # (one is the root, any additional are nested)
        return svg_count > 1

    except Exception:
        # If we can't read the file, assume it's safe to process
        return False


def contains_media_elements(svg_path: Path) -> bool:
    """
    Check if an SVG file contains multimedia elements.

    SVG 2.0 introduced several multimedia elements (video, audio, iframe, canvas,
    foreignObject) that are not suitable for static frame-by-frame animations.
    These elements represent time-based content, external media, or require
    runtime execution that cannot be meaningfully captured in static frames.

    Note: This does NOT filter static embedded content like fonts
    (<font>, <glyph>) or images (<image>), which are fully supported
    and render correctly in static frames.

    Args:
        svg_path: Path to SVG file to check

    Returns:
        True if the file contains any multimedia elements, False otherwise

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
        - May cause rendering issues or performance problems
        - FBF.SVG is designed for pure SVG visual content only

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency.
    """
    try:
        content = svg_path.read_text(encoding="utf-8", errors="ignore")
        content_lower = content.lower()

        # Check for SVG 2.0 multimedia elements
        # Note: We use lowercase for case-insensitive matching
        # These are elements for time-based media, external content,
        # or runtime execution
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


def contains_javascript(svg_path: Path, exceptions: list[str] = None) -> bool:
    """
    Check if an SVG file contains JavaScript or event handlers.

    This function detects JavaScript in SVG files, which can cause rendering
    issues in static frame-by-frame animations. However, certain JavaScript
    (like polyfills) may be allowed via an exceptions list.

    Args:
        svg_path: Path to SVG file to check
        exceptions: List of case-insensitive patterns to exempt from filtering.
                   If None, uses JAVASCRIPT_EXCEPTIONS constant.

    Returns:
        True if the file contains JavaScript (not in exceptions list), False otherwise

    JavaScript Patterns Detected:
        - <script> tags (with or without CDATA)
        - Event attributes: onload, onclick, onmouseover, onmouseout, etc.
        - javascript: URLs in href/xlink:href attributes

    Exceptions:
        Some JavaScript is necessary for SVG features
        (e.g., mesh gradient polyfills). The exceptions list allows these
        to pass through. For example, if "meshgradient" is in the exceptions
        list, any <script> tag containing "meshgradient" will be allowed.

    Why Filter JavaScript:
        - FBF.SVG focuses on static visual content, not interactive behavior
        - JavaScript may execute during rendering, causing non-deterministic output
        - Event handlers like onload can interfere with automated testing
        - Static frames should render identically regardless of execution context

    Performance Note:
        Uses fast string search rather than XML parsing for efficiency.
    """
    if exceptions is None:
        exceptions = JAVASCRIPT_EXCEPTIONS

    try:
        # Read file content as text for fast searching
        content = svg_path.read_text(encoding="utf-8", errors="ignore")

        # Convert to lowercase for case-insensitive matching
        content_lower = content.lower()

        # Check for <script> tags
        if "<script" in content_lower:
            # Check if this script matches any exception pattern
            is_excepted = False
            for exception_pattern in exceptions:
                if exception_pattern.lower() in content_lower:
                    is_excepted = True
                    break

            if not is_excepted:
                return True

        # Check for event handler attributes
        # Common SVG event attributes
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
        # (will fail later with a more specific error)
        return False


if __name__ == "__main__":
    """
    Test the frame processor with sample SVG files.
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python svg2fbf_frame_processor.py <svg_file> [<svg_file2> ...]")
        print()
        print("Examples:")
        print("  python svg2fbf_frame_processor.py frame_001.svg")
        print("  python svg2fbf_frame_processor.py frame_001.svg frame_002.svg frame_003.svg")
        sys.exit(1)

    svg_files = [Path(f) for f in sys.argv[1:]]

    print("=" * 70)
    print("SVG2FBF Frame Processor Test")
    print("=" * 70)
    print()

    processor = SVG2FBFFrameProcessor()
    first_dims = None

    for idx, svg_file in enumerate(svg_files):
        if not svg_file.exists():
            print(f"❌ File not found: {svg_file}")
            continue

        print(f"Frame {idx + 1}: {svg_file.name}")
        print("-" * 70)

        width, height, viewbox, transform = processor.process_frame(svg_file, first_frame_dimensions=first_dims)

        # Save first frame dimensions for subsequent frames
        if idx == 0:
            first_dims = (width, height, viewbox)

        print(f"  Width:    {width}")
        print(f"  Height:   {height}")
        print(f"  ViewBox:  {viewbox}")
        print(f"  Transform: {transform if transform else '(none - first frame)'}")
        print()

    print("=" * 70)
    print("✅ Processing complete")
    print("=" * 70)
