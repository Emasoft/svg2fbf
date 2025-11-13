#!/usr/bin/env python3
"""
FBF.SVG Validator

Validates FBF.SVG (Frame-by-Frame SVG) documents against the FBF.SVG specification.

Usage:
    python validate_fbf.py <input.fbf.svg> [--strict] [--verbose]

Exit Codes:
    0 - Valid FBF.SVG document
    1 - Invalid structure
    2 - Invalid metadata
    3 - Security violation
    4 - XML parsing error

Reference:
    FBF.SVG Specification: docs/FBF_SVG_SPECIFICATION.md
    XSD Schema: docs/fbf-svg.xsd

Author: Emasoft (713559+Emasoft@users.noreply.github.com)
License: Apache-2.0
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from lxml import etree

    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    print("Warning: lxml not installed. XSD validation disabled.", file=sys.stderr)
    print("Install with: pip install lxml", file=sys.stderr)


# ============================================================================
# Configuration
# ============================================================================

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
FBF_NS = "http://opentoonz.github.io/fbf/1.0#"

REQUIRED_IDS = {
    "ANIMATION_BACKDROP",
    "ANIMATION_STAGE",
    "ANIMATED_GROUP",
    "PROSKENION",
    "SHARED_DEFINITIONS",
}

FRAME_ID_PATTERN = re.compile(r"^FRAME[0-9]{5}$")


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class ValidationError:
    """Represents a validation error."""

    level: str  # "error", "warning"
    category: str  # "structure", "metadata", "security", "animation"
    message: str
    element: str | None = None


@dataclass
class ValidationResult:
    """Validation result with errors and warnings."""

    valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationError]
    conformance_level: str  # "none", "basic", "full"

    def __str__(self):
        if self.valid:
            return f"✅ VALID FBF.SVG ({self.conformance_level.upper()} CONFORMANCE)"
        else:
            error_count = len(self.errors)
            warning_count = len(self.warnings)
            return f"❌ INVALID ({error_count} errors, {warning_count} warnings)"


# ============================================================================
# Validator Class
# ============================================================================


class FBFValidator:
    """
    FBF.SVG document validator.

    Performs comprehensive validation including:
    - XML well-formedness
    - SVG basic validation
    - FBF structural requirements
    - Metadata validation
    - Security checks
    - Animation validation
    """

    def __init__(self, strict: bool = False, verbose: bool = False):
        """
        Initialize validator.

        Args:
            strict: If True, warnings are treated as errors
            verbose: If True, print detailed validation progress
        """
        self.strict = strict
        self.verbose = verbose
        self.errors: list[ValidationError] = []
        self.warnings: list[ValidationError] = []

    def log(self, message: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[INFO] {message}", file=sys.stderr)

    def error(self, category: str, message: str, element: str = None):
        """Add validation error."""
        self.errors.append(ValidationError("error", category, message, element))

    def warning(self, category: str, message: str, element: str = None):
        """Add validation warning."""
        if self.strict:
            self.errors.append(ValidationError("error", category, message, element))
        else:
            self.warnings.append(ValidationError("warning", category, message, element))

    def validate(self, filepath: Path) -> ValidationResult:
        """
        Validate FBF.SVG document.

        Args:
            filepath: Path to FBF.SVG file

        Returns:
            ValidationResult with validation status and errors
        """
        self.errors = []
        self.warnings = []

        self.log(f"Validating: {filepath}")

        # Step 1: XML parsing
        tree, root = self._parse_xml(filepath)
        if root is None:
            return ValidationResult(False, self.errors, self.warnings, "none")

        # Step 2: SVG basic checks
        self._validate_svg_root(root)

        # Step 3: Structural validation
        self._validate_structure(root)

        # Step 4: Metadata validation
        has_metadata = self._validate_metadata(root)

        # Step 5: Security checks
        self._validate_security(root)

        # Step 6: Animation validation
        self._validate_animation(root)

        # Step 7: XSD validation (if lxml available)
        if LXML_AVAILABLE:
            self._validate_xsd(filepath)

        # Determine conformance level
        conformance_level = self._determine_conformance_level(has_metadata)

        valid = len(self.errors) == 0
        return ValidationResult(valid, self.errors, self.warnings, conformance_level)

    def _parse_xml(self, filepath: Path) -> tuple[ET.ElementTree | None, ET.Element | None]:
        """Parse XML file."""
        self.log("Parsing XML...")
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            self.log(f"✓ XML parsed successfully (root: {root.tag})")
            return tree, root
        except ET.ParseError as e:
            self.error("xml", f"XML parsing failed: {e}")
            return None, None
        except Exception as e:
            self.error("xml", f"Failed to read file: {e}")
            return None, None

    def _validate_svg_root(self, root: ET.Element):
        """Validate SVG root element."""
        self.log("Validating SVG root element...")

        # Check root tag
        if not root.tag.endswith("svg"):
            self.error("structure", f"Root element must be <svg>, found: {root.tag}")
            return

        # Check xmlns - ElementTree embeds namespace in tag as {namespace}tagname
        # Extract namespace from tag
        if root.tag.startswith("{"):
            xmlns = root.tag[1 : root.tag.index("}")]
            if xmlns != SVG_NS:
                self.error(
                    "structure",
                    f"Missing or incorrect xmlns, expected: {SVG_NS}, found: {xmlns}",
                )
        else:
            self.error("structure", "Missing xmlns attribute, root element has no namespace")

        # Check xmlns:xlink
        xlink_xmlns = root.get(f"{{{XLINK_NS}}}xlink") or root.get("xmlns:xlink")
        if xlink_xmlns != XLINK_NS:
            self.warning("structure", "Missing xmlns:xlink declaration")

        # Check viewBox
        viewBox = root.get("viewBox")
        if not viewBox:
            self.error("structure", "Missing required viewBox attribute on root <svg>")
        else:
            # Validate viewBox format: "minX minY width height"
            parts = viewBox.split()
            if len(parts) != 4:
                self.error(
                    "structure",
                    f"Invalid viewBox format: {viewBox} (expected 4 values)",
                )
            else:
                try:
                    minX, minY, width, height = map(float, parts)
                    if width <= 0 or height <= 0:
                        self.error("structure", "viewBox width and height must be positive")
                except ValueError:
                    self.error("structure", f"viewBox values must be numeric: {viewBox}")

        self.log("✓ SVG root element validated")

    def _validate_structure(self, root: ET.Element):
        """Validate FBF structural requirements with strict ordering."""
        self.log("Validating FBF structure...")

        # Find all elements with IDs
        id_map = {}
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                if elem_id in id_map:
                    self.error("structure", f"Duplicate ID: {elem_id}")
                id_map[elem_id] = elem

        # Check required IDs
        for required_id in REQUIRED_IDS:
            if required_id not in id_map:
                self.error("structure", f"Missing required element with id='{required_id}'")

        # Validate strict document structure order
        self._validate_document_order(root)

        # Validate ANIMATION_BACKDROP
        if "ANIMATION_BACKDROP" in id_map:
            backdrop = id_map["ANIMATION_BACKDROP"]
            if not backdrop.tag.endswith("g"):
                self.error("structure", "ANIMATION_BACKDROP must be a <g> element")

            # Validate strict hierarchy
            self._validate_backdrop_hierarchy(backdrop)

        # Validate PROSKENION xlink:href (if exists)
        if "PROSKENION" in id_map:
            proskenion = id_map["PROSKENION"]
            href = proskenion.get(f"{{{XLINK_NS}}}href") or proskenion.get("href")
            if not href:
                self.error("structure", "PROSKENION must have xlink:href attribute")
            elif not href.startswith("#FRAME"):
                self.error(
                    "structure",
                    f"PROSKENION xlink:href must reference a frame (e.g., #FRAME00001), found: {href}",
                )

        # Validate defs
        defs = root.find(".//{http://www.w3.org/2000/svg}defs")
        if defs is None:
            defs = root.find(".//defs")
        if defs is None:
            self.error("structure", "Missing required <defs> element")
        else:
            # Must contain SHARED_DEFINITIONS
            if "SHARED_DEFINITIONS" not in id_map:
                self.error("structure", "<defs> must contain SHARED_DEFINITIONS")

            # Check for frame groups
            frame_count = 0
            for child in defs:
                child_id = child.get("id")
                if child_id and FRAME_ID_PATTERN.match(child_id):
                    frame_count += 1

            if frame_count == 0:
                self.error(
                    "structure",
                    "No frame groups found in <defs> (expected FRAMExxxxx IDs)",
                )
            else:
                self.log(f"✓ Found {frame_count} frame groups")

        # Validate frame sequence
        self._validate_frame_sequence(id_map)

        self.log("✓ FBF structure validated")

    def _validate_backdrop_hierarchy(self, backdrop: ET.Element):
        """
        Validate strict ANIMATION_BACKDROP → STAGE_BACKGROUND → STAGE →
        STAGE_FOREGROUND hierarchy.
        """
        self.log("Validating ANIMATION_BACKDROP hierarchy...")

        children = list(backdrop)
        backdrop_children = {child.get("id"): (i, child) for i, child in enumerate(children) if child.get("id")}

        # Validate STAGE_BACKGROUND (must be first structural element)
        if "STAGE_BACKGROUND" not in backdrop_children:
            self.error(
                "structure",
                "ANIMATION_BACKDROP must contain STAGE_BACKGROUND as direct child",
            )
        else:
            bg_pos, bg_elem = backdrop_children["STAGE_BACKGROUND"]
            if not bg_elem.tag.endswith("g"):
                self.error("structure", "STAGE_BACKGROUND must be a <g> element")
            self.log("✓ STAGE_BACKGROUND found")

        # Validate ANIMATION_STAGE (must be direct child)
        if "ANIMATION_STAGE" not in backdrop_children:
            self.error(
                "structure",
                "ANIMATION_BACKDROP must contain ANIMATION_STAGE as direct child",
            )
            return

        stage_pos, stage = backdrop_children["ANIMATION_STAGE"]
        if not stage.tag.endswith("g"):
            self.error("structure", "ANIMATION_STAGE must be a <g> element")
        self.log("✓ ANIMATION_STAGE found")

        # Validate STAGE_FOREGROUND (must be after STAGE)
        if "STAGE_FOREGROUND" not in backdrop_children:
            self.error(
                "structure",
                "ANIMATION_BACKDROP must contain STAGE_FOREGROUND as direct child",
            )
        else:
            fg_pos, fg_elem = backdrop_children["STAGE_FOREGROUND"]
            if not fg_elem.tag.endswith("g"):
                self.error("structure", "STAGE_FOREGROUND must be a <g> element")
            if "ANIMATION_STAGE" in backdrop_children and fg_pos < stage_pos:
                self.error("structure", "STAGE_FOREGROUND must come after ANIMATION_STAGE")
            self.log("✓ STAGE_FOREGROUND found")

        # Validate ordering: STAGE_BACKGROUND < ANIMATION_STAGE < STAGE_FOREGROUND
        if all(k in backdrop_children for k in ["STAGE_BACKGROUND", "ANIMATION_STAGE", "STAGE_FOREGROUND"]):
            bg_pos = backdrop_children["STAGE_BACKGROUND"][0]
            st_pos = backdrop_children["ANIMATION_STAGE"][0]
            fg_pos = backdrop_children["STAGE_FOREGROUND"][0]

            if not (bg_pos < st_pos < fg_pos):
                self.error(
                    "structure",
                    "Invalid order in ANIMATION_BACKDROP: expected STAGE_BACKGROUND → ANIMATION_STAGE → STAGE_FOREGROUND",
                )

        # Find ANIMATED_GROUP (must be direct child of STAGE)
        animated_group = None
        stage_children = list(stage)

        for child in stage_children:
            if child.get("id") == "ANIMATED_GROUP":
                animated_group = child
                break

        if animated_group is None:
            self.error(
                "structure",
                "ANIMATION_STAGE must contain ANIMATED_GROUP as direct child",
            )
            return

        if not animated_group.tag.endswith("g"):
            self.error("structure", "ANIMATED_GROUP must be a <g> element")

        # Find PROSKENION (must be direct child of ANIMATED_GROUP)
        proskenion = None
        animated_children = list(animated_group)

        for child in animated_children:
            if child.get("id") == "PROSKENION":
                proskenion = child
                break

        if proskenion is None:
            self.error("structure", "ANIMATED_GROUP must contain PROSKENION as direct child")
            return

        if not proskenion.tag.endswith("use"):
            self.error("structure", "PROSKENION must be a <use> element")

        # PROSKENION must contain exactly one animate child
        proskenion_children = list(proskenion)
        animate_children = [c for c in proskenion_children if c.tag.endswith("animate")]

        if len(animate_children) == 0:
            self.error("structure", "PROSKENION must contain exactly one <animate> child")
        elif len(animate_children) > 1:
            self.error(
                "structure",
                f"PROSKENION must contain exactly ONE <animate> child, found {len(animate_children)}",
            )

        self.log("✓ ANIMATION_BACKDROP hierarchy validated (BACKDROP → STAGE_BACKGROUND → STAGE → ANIMATED_GROUP → PROSKENION → STAGE_FOREGROUND)")

    def _validate_document_order(self, root: ET.Element):
        """Validate strict document element ordering for streaming optimization."""
        self.log("Validating strict document order...")

        # Get direct children of root in order
        children = list(root)
        if len(children) == 0:
            self.error("structure", "Root SVG element has no children")
            return

        expected_order = []
        child_index = 0

        # Optional metadata first
        if child_index < len(children) and children[child_index].tag.endswith("metadata"):
            expected_order.append("metadata")
            child_index += 1

        # Required desc element
        if child_index < len(children) and children[child_index].tag.endswith("desc"):
            expected_order.append("desc")
            child_index += 1
        else:
            self.error(
                "structure",
                "Missing or misplaced <desc> element (must come after <metadata> if present)",
            )

        # Required ANIMATION_BACKDROP group
        backdrop_found = False
        while child_index < len(children):
            child = children[child_index]
            if child.tag.endswith("g") and child.get("id") == "ANIMATION_BACKDROP":
                expected_order.append("ANIMATION_BACKDROP")
                backdrop_found = True
                child_index += 1
                break
            elif child.tag.endswith("defs"):
                # Found defs before backdrop - error
                break
            child_index += 1

        if not backdrop_found:
            self.error(
                "structure",
                "ANIMATION_BACKDROP must come before OVERLAY_LAYER and <defs>",
            )

        # Required OVERLAY_LAYER group
        overlay_found = False
        while child_index < len(children):
            child = children[child_index]
            if child.tag.endswith("g") and child.get("id") == "OVERLAY_LAYER":
                expected_order.append("OVERLAY_LAYER")
                overlay_found = True
                child_index += 1
                break
            elif child.tag.endswith("defs"):
                # Found defs before overlay - error
                break
            child_index += 1

        if not overlay_found:
            self.error(
                "structure",
                "OVERLAY_LAYER must come after ANIMATION_BACKDROP and before <defs>",
            )

        # Required defs element
        defs_found = False
        while child_index < len(children):
            child = children[child_index]
            if child.tag.endswith("defs"):
                expected_order.append("defs")
                defs_found = True
                self._validate_defs_order(child)
                child_index += 1
                break
            child_index += 1

        if not defs_found:
            self.error("structure", "<defs> element must come after OVERLAY_LAYER")

        # Optional script (must be last)
        if child_index < len(children):
            remaining = children[child_index:]
            script_count = sum(1 for c in remaining if c.tag.endswith("script"))
            if script_count > 0:
                if not remaining[-1].tag.endswith("script"):
                    self.error(
                        "structure",
                        "<script> element must be the last child of root SVG",
                    )

        self.log(f"✓ Document order validated: {' → '.join(expected_order)}")

    def _validate_defs_order(self, defs: ET.Element):
        """Validate strict ordering within <defs> element."""
        children = list(defs)
        if len(children) == 0:
            self.error("structure", "<defs> element is empty")
            return

        # First child must be SHARED_DEFINITIONS
        if not (children[0].tag.endswith("g") and children[0].get("id") == "SHARED_DEFINITIONS"):
            self.error("structure", "First child of <defs> must be SHARED_DEFINITIONS group")

        # Remaining children should be FRAME groups in order
        frame_children = [c for c in children[1:] if c.get("id", "").startswith("FRAME")]
        if len(frame_children) == 0:
            self.error("structure", "No FRAME groups found in <defs> after SHARED_DEFINITIONS")

    def _validate_frame_sequence(self, id_map: dict):
        """Validate that frame IDs are sequential."""
        self.log("Validating frame sequence...")

        # Collect all frame IDs
        frame_ids = sorted([id for id in id_map.keys() if FRAME_ID_PATTERN.match(id)])

        if len(frame_ids) == 0:
            return  # Already reported in structure validation

        # Extract frame numbers
        frame_numbers = []
        for frame_id in frame_ids:
            try:
                num = int(frame_id[5:])  # Skip "FRAME" prefix
                frame_numbers.append(num)
            except ValueError:
                continue

        # Check if sequential starting from 1
        expected = 1
        for _i, num in enumerate(sorted(frame_numbers)):
            if num != expected:
                self.error(
                    "structure",
                    f"Frame IDs must be sequential starting from FRAME00001. Expected FRAME{expected:05d}, found FRAME{num:05d}",
                )
                break
            expected += 1

        self.log(f"✓ Found {len(frame_ids)} sequential frames (FRAME{frame_numbers[0]:05d} to FRAME{frame_numbers[-1]:05d})")

    def _validate_metadata(self, root: ET.Element) -> bool:
        """Validate RDF/XML metadata - STRICT mode requires ALL fields."""
        self.log("Validating metadata...")

        # Find metadata element
        metadata = root.find(".//{http://www.w3.org/2000/svg}metadata")
        if metadata is None:
            metadata = root.find(".//metadata")

        if metadata is None:
            self.error("metadata", "No <metadata> element found (REQUIRED)")
            return False

        # Check for RDF structure
        rdf_elem = metadata.find(f".//{{{RDF_NS}}}RDF")
        if rdf_elem is None:
            self.error("metadata", "No RDF structure found in <metadata>")
            return False

        # Check for RDF Description
        desc_elem = rdf_elem.find(f"{{{RDF_NS}}}Description")
        if desc_elem is None:
            self.error("metadata", "No RDF Description found")
            return False

        # Define ALL required metadata fields (strict validation)
        # Dublin Core fields
        dc_fields = [
            "title",
            "creator",
            "description",
            "date",
            "language",
            "rights",
            "source",
        ]

        # FBF authoring fields
        fbf_authoring_fields = [
            "episodeNumber",
            "episodeTitle",
            "creators",
            "originalCreators",
            "copyrights",
            "website",
            "originalLanguage",
            "keywords",
            "sourceFramesPath",
        ]

        # FBF animation properties (MUST have values)
        fbf_animation_fields_required = [
            "frameCount",
            "fps",
            "duration",
            "playbackMode",
            "width",
            "height",
            "viewBox",
        ]

        # FBF animation properties (can be empty)
        fbf_animation_fields_optional = [
            "aspectRatio",
            "firstFrameWidth",
            "firstFrameHeight",
        ]

        # FBF generator information (MUST have values)
        fbf_generator_fields_required = [
            "generator",
            "generatorVersion",
            "generatedDate",
            "formatVersion",
            "precisionDigits",
            "precisionCDigits",
        ]

        # FBF content features (can be empty)
        fbf_content_fields = [
            "useCssClasses",
            "hasBackdropImage",
            "useExternalMedia",
            "useExternalFonts",
            "useEmbeddedImages",
            "useMeshGradient",
            "hasInteractivity",
            "interactivityType",
            "hasJavaScript",
            "hasCSS",
            "containsText",
            "colorProfile",
        ]

        # FBF optimization metrics (can be empty)
        fbf_optimization_fields = [
            "totalElements",
            "sharedElements",
            "uniqueElements",
            "deduplicationRatio",
            "originalSize",
            "optimizedSize",
            "compressionRatio",
            "processingTime",
        ]

        # FBF quality fields (can be empty)
        fbf_quality_fields = [
            "browserCompatibility",
            "estimatedMemory",
            "maxFrameComplexity",
            "avgFrameComplexity",
            "hasNegativeCoords",
            "usesTransforms",
            "usesGradients",
            "usesFilters",
            "usesPatterns",
        ]

        # FBF technical fields (can be empty)
        fbf_technical_fields = [
            "keepXmlSpace",
            "keepAspectRatio",
            "quiet",
            "maxFramesLimit",
            "inputFrameFormat",
            "frameNumberingStart",
        ]

        # Check Dublin Core fields (all must be present, but can be empty)
        for field in dc_fields:
            elem = desc_elem.find(f".//{{{DC_NS}}}{field}")
            if elem is None:
                # Try without namespace
                elem = desc_elem.find(f".//{field}")
            if elem is None:
                self.error("metadata", f"Missing REQUIRED Dublin Core field: dc:{field}")

        # Check FBF fields that MUST be present (all categories)
        all_fbf_fields = fbf_authoring_fields + fbf_animation_fields_required + fbf_animation_fields_optional + fbf_generator_fields_required + fbf_content_fields + fbf_optimization_fields + fbf_quality_fields + fbf_technical_fields

        for field in all_fbf_fields:
            elem = desc_elem.find(f".//{{{FBF_NS}}}{field}")
            if elem is None:
                # Try without namespace
                elem = desc_elem.find(f".//{field}")
            if elem is None:
                self.error("metadata", f"Missing REQUIRED FBF field: fbf:{field}")

        # Check that required fields have non-empty values
        for field in fbf_animation_fields_required + fbf_generator_fields_required:
            elem = desc_elem.find(f".//{{{FBF_NS}}}{field}")
            if elem is None:
                elem = desc_elem.find(f".//{field}")
            if elem is not None:
                if elem.text is None or elem.text.strip() == "":
                    self.warning(
                        "metadata",
                        f"Field fbf:{field} is REQUIRED to have a value (found empty)",
                    )

        self.log("✓ Metadata validated (strict mode)")
        return True

    def _validate_security(self, root: ET.Element):
        """Validate security constraints."""
        self.log("Validating security constraints...")

        # Check for external resource references
        for elem in root.iter():
            # Check xlink:href attributes
            href = elem.get(f"{{{XLINK_NS}}}href") or elem.get("href")
            if href:
                if href.startswith("http://") or href.startswith("https://") or href.startswith("//"):
                    self.error(
                        "security",
                        f"External resource reference forbidden: {href}",
                        elem.tag,
                    )
                elif not href.startswith("#") and not href.startswith("data:"):
                    # Could be external file reference
                    self.warning(
                        "security",
                        f"Potential external resource reference: {href}",
                        elem.tag,
                    )

            # Check for event handlers
            for attr_name in elem.attrib:
                if attr_name.startswith("on"):  # onclick, onload, etc.
                    self.error(
                        "security",
                        f"Event handler attribute forbidden: {attr_name}",
                        elem.tag,
                    )

        # Check for script elements
        script_count = 0
        for _script in root.iter(f"{{{SVG_NS}}}script"):
            script_count += 1

        if script_count > 1:
            self.error(
                "security",
                f"Found {script_count} <script> elements (maximum 1 allowed for mesh gradient polyfill)",
            )
        elif script_count == 1:
            # Check if mesh gradients present
            meshgradient_count = len(list(root.iter(f"{{{SVG_NS}}}meshgradient")))
            if meshgradient_count == 0:
                self.error(
                    "security",
                    "<script> element present but no <meshgradient> elements found (polyfill only allowed for mesh gradients)",
                )
            else:
                self.log(f"✓ Script element allowed (mesh gradient polyfill for {meshgradient_count} meshgradients)")

        self.log("✓ Security constraints validated")

    def _validate_animation(self, root: ET.Element):
        """Validate SMIL animation."""
        self.log("Validating SMIL animation...")

        # Find animate element
        animate = None
        for elem in root.iter():
            if elem.get("id") == "PROSKENION":
                for child in elem:
                    if child.tag.endswith("animate"):
                        animate = child
                        break
                break

        if animate is None:
            self.error("animation", "No <animate> element found in PROSKENION")
            return

        # Check attributeName
        attr_name = animate.get("attributeName")
        if attr_name != "xlink:href" and attr_name != "href":
            self.error(
                "animation",
                f"animate attributeName must be 'xlink:href' or 'href', found: {attr_name}",
            )

        # Check values attribute
        values = animate.get("values")
        if not values:
            self.error("animation", "animate element missing 'values' attribute")
        else:
            # Parse frame references
            frame_refs = values.split(";")
            if len(frame_refs) < 2:
                self.error(
                    "animation",
                    f"animate values must contain at least 2 frames, found {len(frame_refs)}",
                )

            # Check frame reference format
            for frame_ref in frame_refs:
                if not frame_ref.startswith("#FRAME"):
                    self.error(
                        "animation",
                        f"Invalid frame reference: {frame_ref} (must start with #FRAME)",
                    )
                else:
                    frame_id = frame_ref[1:]  # Remove #
                    if not FRAME_ID_PATTERN.match(frame_id):
                        self.error(
                            "animation",
                            f"Invalid frame ID format: {frame_id} (expected FRAMExxxxx)",
                        )

        # Check dur attribute
        dur = animate.get("dur")
        if not dur:
            self.error("animation", "animate element missing 'dur' attribute")
        elif not re.match(r"^[0-9]+(\.[0-9]+)?s$", dur):
            self.error(
                "animation",
                f"Invalid dur format: {dur} (expected decimal followed by 's', e.g., '2.5s')",
            )

        # Check repeatCount attribute
        repeat_count = animate.get("repeatCount")
        if not repeat_count:
            self.error("animation", "animate element missing 'repeatCount' attribute")
        elif repeat_count != "indefinite" and not repeat_count.isdigit():
            self.error(
                "animation",
                f"Invalid repeatCount: {repeat_count} (expected 'indefinite' or positive integer)",
            )

        self.log("✓ SMIL animation validated")

    def _validate_xsd(self, filepath: Path):
        """Validate against XSD schema using lxml."""
        if not LXML_AVAILABLE:
            self.warning("xsd", "lxml not available, XSD validation skipped")
            return

        self.log("Validating against XSD schema...")

        # Find XSD schema file
        schema_path = Path(__file__).parent / "docs" / "fbf-svg.xsd"
        if not schema_path.exists():
            self.warning("xsd", f"XSD schema not found at {schema_path}")
            return

        try:
            # Parse schema
            with open(schema_path, "rb") as f:
                schema_doc = etree.parse(f)
            schema = etree.XMLSchema(schema_doc)

            # Parse document
            with open(filepath, "rb") as f:
                doc = etree.parse(f)

            # Validate
            if not schema.validate(doc):
                for error in schema.error_log:
                    self.warning("xsd", f"XSD validation: {error.message}")
            else:
                self.log("✓ XSD validation passed")

        except Exception as e:
            self.warning("xsd", f"XSD validation failed: {e}")

    def _determine_conformance_level(self, has_metadata: bool) -> str:
        """Determine FBF conformance level."""
        if len(self.errors) > 0:
            return "none"
        elif has_metadata and len(self.warnings) == 0:
            return "full"
        elif len(self.warnings) == 0:
            return "basic"
        else:
            return "basic"


# ============================================================================
# CLI Interface
# ============================================================================


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate FBF.SVG (Frame-by-Frame SVG) documents",
        epilog="Reference: docs/FBF_SVG_SPECIFICATION.md",
    )
    parser.add_argument("input", type=Path, help="Input FBF.SVG file")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Check input file exists
    if not args.input.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 4

    # Validate
    validator = FBFValidator(strict=args.strict, verbose=args.verbose)
    result = validator.validate(args.input)

    # Print result
    print(f"\n{result}\n")

    # Print errors
    if result.errors:
        print("ERRORS:")
        for error in result.errors:
            element_info = f" [{error.element}]" if error.element else ""
            print(f"  ❌ [{error.category.upper()}] {error.message}{element_info}")
        print()

    # Print warnings
    if result.warnings:
        print("WARNINGS:")
        for warning in result.warnings:
            element_info = f" [{warning.element}]" if warning.element else ""
            print(f"  ⚠️  [{warning.category.upper()}] {warning.message}{element_info}")
        print()

    # Exit with appropriate code
    if not result.valid:
        if result.errors and result.errors[0].category == "xml":
            return 4
        elif any(e.category == "security" for e in result.errors):
            return 3
        elif any(e.category == "metadata" for e in result.errors):
            return 2
        else:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
