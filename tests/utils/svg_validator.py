"""
SVG Validator for Test Suite

Validates SVG files before using them in tests to ensure:
- Valid XML syntax
- Proper font definitions (system fonts, embedded fonts, web fonts)
- Accessible image resources (local files, remote URLs, data URIs)
- Successful browser rendering

Maintains a persistent cache of invalid SVGs to avoid re-validation.
"""

import base64
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

import requests
from lxml import etree
from PIL import Image


class SVGValidator:
    """
    Validates SVG files for use in rendering tests

    Performs multi-layer validation:
    1. Syntax validation (XML parsing)
    2. Font validation (definitions and accessibility)
    3. Image resource validation (local/remote/embedded)
    4. Browser rendering validation (optional, if Puppeteer available)

    Results are cached in invalid_svg_example_frames.json to avoid re-validation.
    """

    # System fonts that are always available on most systems
    # Why: These fonts don't need to be embedded or checked
    SAFE_FONTS = {
        "arial",
        "helvetica",
        "times",
        "times new roman",
        "courier",
        "courier new",
        "verdana",
        "georgia",
        "palatino",
        "garamond",
        "bookman",
        "comic sans ms",
        "trebuchet ms",
        "impact",
        "sans-serif",
        "serif",
        "monospace",
        "cursive",
        "fantasy",
    }

    def __init__(self, cache_file: Path, puppeteer_renderer=None):
        """
        Initialize SVG validator

        Args:
            cache_file: Path to invalid_svg_example_frames.json cache file
            puppeteer_renderer: Optional PuppeteerRenderer instance for browser
                validation
        """
        self.cache_file = cache_file
        self.puppeteer_renderer = puppeteer_renderer
        self.cache = self._load_cache()
        self.validation_cache = {}  # In-memory cache for current session

    def _load_cache(self) -> dict:
        """
        Load cache of previously validated invalid SVGs

        Why: Avoid re-validating known-bad files on every test run
        """
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    return json.load(f)
            except Exception:
                # Cache corrupted, start fresh
                return self._create_empty_cache()
        return self._create_empty_cache()

    def _create_empty_cache(self) -> dict:
        """Create empty cache structure"""
        return {
            "version": "1.0",
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "invalid_svgs": {},
        }

    def _save_cache(self):
        """
        Save cache to disk

        Why: Persist validation results across test runs and share with team via git
        """
        self.cache["last_updated"] = datetime.utcnow().isoformat() + "Z"
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f, indent=2)

    def is_valid(self, svg_path: Path) -> tuple[bool, str | None]:
        """
        Check if SVG is valid for testing

        Uses cache to avoid re-validating known-invalid SVGs.

        Args:
            svg_path: Path to SVG file to validate

        Returns:
            (is_valid, reason_if_invalid)
            - is_valid: True if SVG passed all validation checks
            - reason_if_invalid: Human-readable description of failure (if any)
        """
        svg_path_str = str(svg_path)

        # Check persistent cache first (known invalid files)
        # Why: Skip expensive validation for files we've already checked
        if svg_path_str in self.cache["invalid_svgs"]:
            cached_info = self.cache["invalid_svgs"][svg_path_str]
            reason = cached_info.get("reason", "Unknown cached reason")
            return False, f"Cached invalid: {reason}"

        # Check in-memory cache (current session)
        if svg_path_str in self.validation_cache:
            return self.validation_cache[svg_path_str]

        # Perform full validation
        result = self._validate_svg(svg_path)

        # Cache result in memory
        self.validation_cache[svg_path_str] = result

        # If invalid, add to persistent cache
        # Why: Share this knowledge with future test runs
        if not result[0]:
            self._add_to_invalid_cache(svg_path_str, result[1])

        return result

    def _validate_svg(self, svg_path: Path) -> tuple[bool, str | None]:
        """
        Perform full multi-layer validation

        Validation order (fast → slow):
        1. File exists and readable
        2. Minimum size check
        3. XML syntax parsing
        4. SVG root element check
        5. Font validation
        6. Image resource validation
        7. Browser rendering (optional)

        Returns:
            (is_valid, reason_if_invalid)
        """
        # Check 1: File exists and readable
        # Why: Fail fast if file is missing
        if not svg_path.exists():
            return False, "File does not exist"

        try:
            content = svg_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Try reading as latin-1 (some SVGs use this encoding)
            try:
                content = svg_path.read_text(encoding="latin-1")
            except Exception as e:
                return False, f"Cannot read file: {str(e)}"
        except Exception as e:
            return False, f"Cannot read file: {str(e)}"

        # Check 2: Minimum size
        # Why: Empty or near-empty files are invalid
        if len(content) < 100:
            return False, "File too small (< 100 bytes, likely empty or corrupted)"

        # Check 3: XML syntax
        # Why: Malformed XML cannot be rendered
        try:
            tree = etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            return False, f"XML syntax error: {str(e)}"

        # Check 4: Has SVG root element
        # Why: Must be an actual SVG file, not some other XML
        if not tree.tag.endswith("svg"):
            return False, f"No <svg> root element (found <{tree.tag}> instead)"

        # Check 5: Font validation
        # Why: Missing fonts cause rendering failures or incorrect output
        font_result = self._validate_fonts(tree, content, svg_path)
        if not font_result[0]:
            return font_result

        # Check 6: Image resource validation
        # Why: Missing images cause rendering failures
        image_result = self._validate_images(tree, svg_path)
        if not image_result[0]:
            return image_result

        # Check 7: Browser rendering validation (if available)
        # Why: Catch runtime issues that static analysis misses
        if self.puppeteer_renderer:
            render_result = self._validate_browser_rendering(svg_path)
            if not render_result[0]:
                return render_result

        # All checks passed!
        return True, None

    def _validate_fonts(self, tree: etree.Element, content: str, svg_path: Path) -> tuple[bool, str | None]:
        """
        Validate font definitions and usage

        Checks:
        - All referenced fonts are either system fonts, embedded, or web fonts
        - Font files/URLs are accessible

        Args:
            tree: Parsed XML tree
            content: Raw SVG content (for searching)
            svg_path: Path to SVG file

        Returns:
            (is_valid, reason_if_invalid)
        """
        # Find all font-family references in the SVG
        # Why: We need to know which fonts are actually used
        font_families = set()

        # Check style attributes: style="font-family: Arial"
        for elem in tree.iter():
            style = elem.get("style") or ""  # Why: elem.get() can return None
            font_family = elem.get("font-family") or ""  # Why: elem.get() can return None

            # Parse font-family from style attribute
            if "font-family" in style:
                match = re.search(r"font-family\s*:\s*([^;]+)", style)
                if match:
                    fonts_str = match.group(1).strip().strip("\"'")
                    # Handle comma-separated fallback fonts
                    for font in fonts_str.split(","):
                        font_families.add(font.strip().strip("\"'").lower())

            # Parse font-family attribute
            if font_family:
                font_families.add(font_family.strip().strip("\"'").lower())

        # Check <style> element for font-family declarations
        # Why: CSS rules may define fonts for selectors
        for style_elem in tree.findall(".//{http://www.w3.org/2000/svg}style"):
            if style_elem.text:
                matches = re.findall(r"font-family\s*:\s*([^;}]+)", style_elem.text)
                for match in matches:
                    for font in match.split(","):
                        font_families.add(font.strip().strip("\"'").lower())

        # Validate each font
        # Why: Ensure all fonts are available for rendering
        for font in font_families:
            if not font or font == "inherit" or font == "initial":
                continue

            # Check if it's a safe system font
            # Why: System fonts don't need embedding
            if any(safe in font for safe in self.SAFE_FONTS):
                continue

            # Check for @font-face definition
            # Why: Embedded fonts via @font-face are self-contained
            if "@font-face" in content:
                # Look for this specific font in @font-face rules
                font_face_pattern = r'@font-face\s*{[^}]*font-family\s*:\s*["\']?' + re.escape(font)
                if re.search(font_face_pattern, content, re.IGNORECASE):
                    continue

            # Check for embedded font in <defs> with <font> element
            # Why: SVG fonts can be defined inline
            if "<font" in content:
                if f'id="{font}"' in content or f"id='{font}'" in content:
                    continue

            # Check for web font imports (Google Fonts, etc.)
            # Why: Web fonts are loaded at runtime
            if "<link" in content or "@import" in content:
                # Check if this font is mentioned in the import
                if "fonts.googleapis.com" in content or "fonts.gstatic.com" in content:
                    # Google Fonts present, assume this font is loaded
                    # (We could make this stricter by parsing the actual font names)
                    continue

            # Font not found in any expected location!
            # Why: Undefined fonts will cause rendering issues
            return (
                False,
                f"Font '{font}' is used but not defined, embedded, or available as system font",
            )

        # All fonts are properly defined
        return True, None

    def _validate_images(self, tree: etree.Element, svg_path: Path) -> tuple[bool, str | None]:
        """
        Validate image resources (local files, remote URLs, data URIs)

        Checks:
        - Local image files exist and are valid
        - Remote image URLs are accessible
        - Data URIs have valid base64 encoding

        Args:
            tree: Parsed XML tree
            svg_path: Path to SVG file

        Returns:
            (is_valid, reason_if_invalid)
        """
        svg_dir = svg_path.parent

        # Find all <image> elements with href attributes
        # Why: Images referenced by SVG must be accessible
        namespaces = {
            "svg": "http://www.w3.org/2000/svg",
            "xlink": "http://www.w3.org/1999/xlink",
        }

        for img_elem in tree.findall(".//svg:image", namespaces):
            # Get href (can be 'href' or 'xlink:href')
            href = img_elem.get("href") or img_elem.get("{http://www.w3.org/1999/xlink}href")

            if not href:
                continue  # No image reference, skip

            # Case 1: Data URI (already embedded)
            # Why: Data URIs are self-contained, always valid
            if href.startswith("data:"):
                # Validate base64 encoding if present
                if "base64," in href:
                    try:
                        data = href.split("base64,")[1]
                        base64.b64decode(data, validate=True)
                    except Exception as e:
                        return False, f"Invalid base64 data URI in image: {str(e)}"
                continue

            # Case 2: Remote URL
            # Why: Remote images must be accessible for rendering
            if href.startswith("http://") or href.startswith("https://"):
                try:
                    # Send HEAD request to check accessibility
                    # Why: Avoid downloading entire image, just check if it exists
                    response = requests.head(href, timeout=5, allow_redirects=True)
                    if response.status_code >= 400:
                        return (
                            False,
                            f"Remote image returns HTTP {response.status_code}: {href}",
                        )

                    # Verify it's actually an image
                    content_type = response.headers.get("content-type", "")
                    if content_type and not content_type.startswith("image/"):
                        return (
                            False,
                            f"Remote URL is not an image (content-type: {content_type}): {href}",
                        )
                except requests.RequestException as e:
                    return False, f"Cannot reach remote image: {href} ({str(e)})"
                continue

            # Case 3: Local file path
            # Why: Local images must exist and be valid
            # Try path relative to SVG file location first
            local_path = svg_dir / href
            if not local_path.exists():
                # Try as absolute path
                local_path = Path(href)
                if not local_path.exists():
                    return (
                        False,
                        f"Local image not found: {href} (tried relative to SVG and absolute)",
                    )

            # Verify it's a valid image file
            # Why: Corrupted images cause rendering failures
            try:
                with Image.open(local_path) as img:
                    img.verify()
            except Exception as e:
                return False, f"Invalid/corrupted image file: {href} ({str(e)})"

        # All image resources are valid
        return True, None

    def _validate_browser_rendering(self, svg_path: Path) -> tuple[bool, str | None]:
        """
        Validate SVG renders correctly in browser

        Uses Puppeteer to catch runtime errors that static analysis misses.
        This is the most comprehensive but slowest validation check.

        Args:
            svg_path: Path to SVG file

        Returns:
            (is_valid, reason_if_invalid)
        """
        if not self.puppeteer_renderer:
            # Puppeteer not available, skip this check
            # Why: Browser validation is optional but recommended
            return True, None

        try:
            # Try to render SVG to PNG
            # Why: If rendering fails, SVG has runtime issues
            with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
                tmp_path = Path(tmp.name)

                success = self.puppeteer_renderer.render_svg_to_png(svg_path=svg_path, output_png_path=tmp_path, width=800, height=600)

                if not success:
                    return False, "Failed to render in browser (Puppeteer error)"

                # Verify rendered image is not blank/corrupted
                # Why: Some SVGs load but render as blank
                try:
                    with Image.open(tmp_path) as img:
                        # Check dimensions are non-zero
                        if img.size[0] == 0 or img.size[1] == 0:
                            return False, "Rendered image has zero dimensions"

                        # Check if image is not completely blank
                        # Why: Blank output indicates rendering failure
                        import numpy as np

                        arr = np.array(img.convert("L"))  # Convert to grayscale
                        if np.all(arr == 0):
                            return (
                                False,
                                "Rendered image is completely black (rendering failed)",
                            )
                        if np.all(arr == 255):
                            return (
                                False,
                                "Rendered image is completely white (no content rendered)",
                            )

                except Exception as e:
                    return False, f"Rendered PNG is corrupted: {str(e)}"

        except Exception as e:
            return False, f"Browser rendering error: {str(e)}"

        # Rendering successful
        return True, None

    def _add_to_invalid_cache(self, svg_path_str: str, reason: str):
        """
        Add invalid SVG to persistent cache

        Why: Share validation results with future test runs and team members
        """
        self.cache["invalid_svgs"][svg_path_str] = {
            "reason": reason,
            "validated_at": datetime.utcnow().isoformat() + "Z",
        }
        self._save_cache()

    def clear_cache_for_file(self, svg_path: Path):
        """
        Remove specific file from invalid cache

        Use this if an SVG was fixed and should be re-validated.

        Args:
            svg_path: Path to SVG file to remove from cache
        """
        svg_path_str = str(svg_path)
        if svg_path_str in self.cache["invalid_svgs"]:
            del self.cache["invalid_svgs"][svg_path_str]
            self._save_cache()

    def get_cache_stats(self) -> dict:
        """
        Get statistics about cached invalid SVGs

        Returns:
            Dictionary with cache statistics:
            - total_invalid: Number of invalid SVGs cached
            - last_updated: Last cache update timestamp
            - invalid_files: List of invalid file paths
        """
        return {
            "total_invalid": len(self.cache["invalid_svgs"]),
            "last_updated": self.cache.get("last_updated", "Unknown"),
            "invalid_files": list(self.cache["invalid_svgs"].keys()),
        }
