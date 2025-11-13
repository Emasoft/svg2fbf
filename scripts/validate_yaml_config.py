#!/usr/bin/env python3
"""
YAML Configuration Validator for FBF.SVG
Validates YAML configuration files used by both svg2fbf.py and testrunner.py

Usage:
    uv run python validate_yaml_config.py <config.yaml>
    uv run python validate_yaml_config.py examples/splat_button/splat_button.yaml

Exit codes:
    0: Valid YAML configuration
    1: Invalid YAML configuration (errors found)
    2: File not found or cannot be read
"""

import sys
from pathlib import Path

import yaml

# Valid animation types (from svg2fbf.py TYPE_CHOICES)
VALID_ANIMATION_TYPES = [
    "once",
    "once_reversed",
    "loop",
    "loop_reversed",
    "pingpong_once",
    "pingpong_loop",
    "pingpong_once_reversed",
    "pingpong_loop_reversed",
]

# Valid metadata fields (Dublin Core + FBF custom)
VALID_METADATA_FIELDS = {
    # Dublin Core standard fields
    "title": {"type": str, "required": False, "description": "Animation title"},
    "creator": {
        "type": str,
        "required": False,
        "description": "Legacy single creator field (use 'creators' instead)",
    },
    "creators": {
        "type": str,
        "required": False,
        "description": "Primary creators (comma-separated)",
    },
    "original_creators": {
        "type": str,
        "required": False,
        "description": "Original creators if adapted",
    },
    "description": {
        "type": str,
        "required": False,
        "description": "Animation description",
    },
    "keywords": {
        "type": str,
        "required": False,
        "description": "Keywords (comma-separated)",
    },
    "language": {
        "type": str,
        "required": False,
        "description": "Language code (e.g., 'en', 'es')",
    },
    "original_language": {
        "type": str,
        "required": False,
        "description": "Original language if translated",
    },
    "rights": {
        "type": str,
        "required": False,
        "description": "License/rights (e.g., 'Apache-2.0', 'CC-BY-4.0')",
    },
    "source": {"type": str, "required": False, "description": "Source information"},
    "date": {
        "type": str,
        "required": False,
        "description": "Creation/publication date (ISO 8601)",
    },
    # Episode/series information
    "episode_number": {
        "type": (int, str),
        "required": False,
        "description": "Episode number",
    },
    "episode_title": {"type": str, "required": False, "description": "Episode title"},
    # Website and copyright
    "website": {
        "type": str,
        "required": False,
        "description": "Creator/project website URL",
    },
    "copyrights": {"type": str, "required": False, "description": "Copyright notice"},
}

# Valid generation parameters
VALID_GENERATION_PARAMS = {
    # Required paths
    "input_folder": {
        "type": str,
        "required": False,
        "description": "Path to input SVG frames folder",
    },
    "output_path": {
        "type": str,
        "required": False,
        "description": "Path to output directory",
    },
    "filename": {"type": str, "required": False, "description": "Output FBF filename"},
    # Animation settings
    "speed": {
        "type": (int, float),
        "required": False,
        "min": 0.1,
        "max": 120.0,
        "description": "Frame rate (fps)",
    },
    "animation_type": {
        "type": str,
        "required": False,
        "enum": VALID_ANIMATION_TYPES,
        "description": "Animation playback mode",
    },
    "play_on_click": {
        "type": bool,
        "required": False,
        "description": "Enable click-to-play interaction",
    },
    # Optional parameters
    "quiet": {
        "type": bool,
        "required": False,
        "description": "Suppress output messages",
    },
    "digits": {
        "type": int,
        "required": False,
        "min": 1,
        "max": 64,
        "description": "Precision digits for coordinates",
    },
    "cdigits": {
        "type": int,
        "required": False,
        "min": 1,
        "max": 64,
        "description": "Precision digits for control points",
    },
    "backdrop": {"type": str, "required": False, "description": "Backdrop image path"},
    "keep_xml_space": {
        "type": bool,
        "required": False,
        "description": "Keep xml:space attributes",
    },
    "max_frames": {
        "type": (int, type(None)),
        "required": False,
        "min": 1,
        "description": "Maximum number of frames to process",
    },
    # Explicit frame list (alternative to input_folder)
    "frames": {
        "type": list,
        "required": False,
        "description": "Explicit list of frame file paths",
    },
}


class YAMLConfigValidator:
    """Validator for FBF.SVG YAML configuration files."""

    def __init__(self, strict: bool = False):
        """
        Initialize validator.

        Args:
            strict: If True, warnings are treated as errors
        """
        self.strict = strict
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, category: str, message: str):
        """Add an error message."""
        self.errors.append(f"❌ [{category}] {message}")

    def warning(self, category: str, message: str):
        """Add a warning message."""
        if self.strict:
            self.errors.append(f"❌ [{category}] {message}")
        else:
            self.warnings.append(f"⚠️  [{category}] {message}")

    def validate_yaml_syntax(self, file_path: Path) -> dict | None:
        """
        Validate YAML syntax and load the file.

        Args:
            file_path: Path to YAML file

        Returns:
            Loaded YAML dict or None if invalid
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if config is None:
                self.error("SYNTAX", "YAML file is empty")
                return None

            if not isinstance(config, dict):
                self.error(
                    "SYNTAX",
                    f"YAML root must be a dictionary, got {type(config).__name__}",
                )
                return None

            return config

        except yaml.YAMLError as e:
            self.error("SYNTAX", f"YAML parsing error: {str(e)}")
            return None
        except Exception as e:
            self.error("SYNTAX", f"Error reading file: {str(e)}")
            return None

    def validate_structure(self, config: dict) -> bool:
        """
        Validate high-level YAML structure.

        Args:
            config: Loaded YAML configuration

        Returns:
            True if structure is valid
        """
        valid = True

        # Check for valid top-level sections
        valid_sections = {"metadata", "generation_parameters"}
        found_sections = set(config.keys())

        # Unknown sections
        unknown = found_sections - valid_sections
        if unknown:
            for section in unknown:
                self.warning("STRUCTURE", f"Unknown top-level section: '{section}'")

        # At least one section should be present
        if not found_sections:
            self.error(
                "STRUCTURE",
                ("No valid sections found (expected 'metadata' and/or 'generation_parameters')"),
            )
            valid = False

        # Validate section types
        if "metadata" in config and not isinstance(config["metadata"], dict):
            self.error(
                "STRUCTURE",
                (f"'metadata' must be a dictionary, got {type(config['metadata']).__name__}"),
            )
            valid = False

        if "generation_parameters" in config and not isinstance(config["generation_parameters"], dict):
            self.error(
                "STRUCTURE",
                (f"'generation_parameters' must be a dictionary, got {type(config['generation_parameters']).__name__}"),
            )
            valid = False

        return valid

    def validate_metadata(self, metadata: dict) -> bool:
        """
        Validate metadata section.

        Args:
            metadata: Metadata dictionary

        Returns:
            True if valid
        """
        valid = True

        for field, value in metadata.items():
            if field not in VALID_METADATA_FIELDS:
                self.warning("METADATA", f"Unknown metadata field: '{field}'")
                continue

            spec = VALID_METADATA_FIELDS[field]

            # Type validation
            expected_type = spec["type"]
            if not isinstance(value, expected_type):
                if isinstance(expected_type, tuple):
                    type_names = " or ".join(t.__name__ for t in expected_type)
                else:
                    type_names = expected_type.__name__
                self.error(
                    "METADATA",
                    f"Field '{field}' must be {type_names}, got {type(value).__name__}",
                )
                valid = False

        # Check required fields
        for field, spec in VALID_METADATA_FIELDS.items():
            if spec.get("required", False) and field not in metadata:
                self.error("METADATA", f"Required field missing: '{field}'")
                valid = False

        # Recommended fields
        recommended = ["title", "creators", "description", "language", "rights"]
        missing_recommended = [f for f in recommended if f not in metadata or not metadata[f]]
        if missing_recommended:
            self.warning(
                "METADATA",
                (f"Recommended fields missing or empty: {', '.join(missing_recommended)}"),
            )

        return valid

    def validate_generation_parameters(self, params: dict) -> bool:
        """
        Validate generation_parameters section.

        Args:
            params: Generation parameters dictionary

        Returns:
            True if valid
        """
        valid = True

        for field, value in params.items():
            if field not in VALID_GENERATION_PARAMS:
                self.warning("GENERATION", f"Unknown generation parameter: '{field}'")
                continue

            spec = VALID_GENERATION_PARAMS[field]

            # Type validation
            expected_type = spec["type"]
            if not isinstance(value, expected_type):
                if isinstance(expected_type, tuple):
                    type_names = " or ".join(t.__name__ if t is not type(None) else "null" for t in expected_type)
                else:
                    type_names = expected_type.__name__
                self.error(
                    "GENERATION",
                    (f"Parameter '{field}' must be {type_names}, got {type(value).__name__}"),
                )
                valid = False
                continue

            # Enum validation
            if "enum" in spec and value not in spec["enum"]:
                self.error(
                    "GENERATION",
                    (f"Parameter '{field}' has invalid value '{value}'. Valid values: {', '.join(spec['enum'])}"),
                )
                valid = False

            # Range validation
            if "min" in spec and isinstance(value, (int, float)) and value < spec["min"]:
                self.error(
                    "GENERATION",
                    f"Parameter '{field}' value {value} is below minimum {spec['min']}",
                )
                valid = False

            if "max" in spec and isinstance(value, (int, float)) and value > spec["max"]:
                self.error(
                    "GENERATION",
                    f"Parameter '{field}' value {value} exceeds maximum {spec['max']}",
                )
                valid = False

        # Check for input specification (either input_folder or frames list)
        has_input_folder = "input_folder" in params and params["input_folder"]
        has_frames_list = "frames" in params and params["frames"]

        if not has_input_folder and not has_frames_list:
            self.warning(
                "GENERATION",
                "No input specified (expected 'input_folder' or 'frames' list)",
            )

        if has_input_folder and has_frames_list:
            self.warning(
                "GENERATION",
                ("Both 'input_folder' and 'frames' specified; 'frames' list will take precedence"),
            )

        # Check for output specification
        if "output_path" not in params or not params["output_path"]:
            self.warning("GENERATION", "No 'output_path' specified")

        if "filename" not in params or not params["filename"]:
            self.warning("GENERATION", "No 'filename' specified")

        return valid

    def validate(self, file_path: Path) -> bool:
        """
        Validate a YAML configuration file.

        Args:
            file_path: Path to YAML file

        Returns:
            True if valid
        """
        self.errors = []
        self.warnings = []

        # Load and validate syntax
        config = self.validate_yaml_syntax(file_path)
        if config is None:
            return False

        # Validate structure
        if not self.validate_structure(config):
            return False

        # Validate metadata section
        if "metadata" in config:
            self.validate_metadata(config["metadata"])

        # Validate generation_parameters section
        if "generation_parameters" in config:
            self.validate_generation_parameters(config["generation_parameters"])

        return len(self.errors) == 0

    def print_results(self, file_path: Path, is_valid: bool):
        """Print validation results."""
        print()

        if is_valid and not self.warnings:
            print("✅ VALID YAML CONFIGURATION")
        elif is_valid:
            print(f"✅ VALID YAML CONFIGURATION ({len(self.warnings)} warnings)")
        else:
            print(f"❌ INVALID YAML CONFIGURATION ({len(self.errors)} errors, {len(self.warnings)} warnings)")

        print()

        if self.errors:
            print("ERRORS:")
            for error in self.errors:
                print(f"  {error}")
            print()

        if self.warnings:
            print("WARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")
            print()


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: uv run python validate_yaml_config.py <config.yaml>")
        print()
        print("Example:")
        print("  uv run python validate_yaml_config.py examples/splat_button/splat_button.yaml")
        sys.exit(2)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"❌ ERROR: File not found: {file_path}")
        sys.exit(2)

    if not file_path.is_file():
        print(f"❌ ERROR: Not a file: {file_path}")
        sys.exit(2)

    # Run validation
    validator = YAMLConfigValidator(strict=False)
    is_valid = validator.validate(file_path)
    validator.print_results(file_path, is_valid)

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
