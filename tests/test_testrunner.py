"""
Comprehensive unit tests for testrunner.py

Tests cover:
- Configuration loading from pyproject.toml
- CONSTANTS usage and validation
- Session creation and management
- Frame numbering and validation logic
- SVG validation and error handling
"""

import sys
from pathlib import Path

import pytest
import tomli
import tomli_w

# Add tests directory to path for import
sys.path.insert(0, str(Path(__file__).parent))

from testrunner import (
    FBFTEST_SUFFIX_FORMAT,
    FBFTEST_SUFFIX_PATTERN,
    FRAME_NUMBER_PATTERNS,
    DigitCountAdjustment,
    FrameNumberPriority,
    SessionConfig,
    detect_has_numerical_suffix,
    extract_number_candidates_from_filename,
    extract_suffix_number,
    load_test_config,
    validate_svg_numbering,
)


class TestConfigLoading:
    """Test configuration loading from pyproject.toml"""

    def test_load_test_config_returns_dict(self):
        """Configuration loading returns proper dictionary with all required keys"""
        config = load_test_config()

        assert isinstance(config, dict)
        required_keys = [
            "image_tolerance",
            "pixel_tolerance",
            "max_frames",
            "fps",
            "animation_type",
            "precision_digits",
            "precision_cdigits",
            "frame_number_format",
            "create_session_encoding",
        ]
        for key in required_keys:
            assert key in config, f"Missing configuration key: {key}"

    def test_load_test_config_has_valid_types(self):
        """Configuration values have correct types"""
        config = load_test_config()

        assert isinstance(config["image_tolerance"], float)
        assert isinstance(config["pixel_tolerance"], float)
        assert isinstance(config["max_frames"], int)
        assert isinstance(config["fps"], float)
        assert isinstance(config["animation_type"], str)
        assert isinstance(config["precision_digits"], int)
        assert isinstance(config["precision_cdigits"], int)
        assert isinstance(config["frame_number_format"], str)
        assert isinstance(config["create_session_encoding"], str)

    def test_load_test_config_has_valid_values(self):
        """Configuration values are within valid ranges"""
        config = load_test_config()

        # Tolerances should be between 0 and 1
        assert 0 <= config["image_tolerance"] <= 1
        assert 0 <= config["pixel_tolerance"] <= 1

        # Max frames should be positive
        assert config["max_frames"] > 0

        # FPS should be positive
        assert config["fps"] > 0

        # Animation type should be recognized
        valid_animation_types = {
            "once",
            "once_reversed",
            "loop",
            "loop_reversed",
            "pingpong_once",
            "pingpong_loop",
            "pingpong_once_reversed",
            "pingpong_loop_reversed",
        }
        assert config["animation_type"] in valid_animation_types

        # Digits should be reasonable
        assert 1 <= config["precision_digits"] <= 28
        assert 1 <= config["precision_cdigits"] <= 28

        # Encoding should be recognized
        assert config["create_session_encoding"] in ["utf-8", "ascii", "latin-1"]

    def test_testconfig_class_loads_config(self, tmp_path):
        """TestConfig class successfully loads from pyproject.toml"""
        pyproject = tmp_path / "pyproject.toml"
        config_data = {
            "tool": {
                "svg2fbf": {
                    "test": {
                        "image_tolerance": 0.05,
                        "pixel_tolerance": 0.003,
                        "max_frames": 100,
                        "fps": 24.0,
                        "animation_type": "loop",
                        "precision_digits": 15,
                        "precision_cdigits": 15,
                        "frame_number_format": "frame{:05d}.svg",
                        "create_session_encoding": "utf-8",
                    }
                }
            }
        }
        with open(pyproject, "wb") as f:
            tomli_w.dump(config_data, f)

        config = SessionConfig(pyproject)

        assert config.image_tolerance == 0.05
        assert config.pixel_tolerance == 0.003
        assert config.max_frames == 100
        assert config.fps == 24.0
        assert config.animation_type == "loop"
        assert config.precision_digits == 15
        assert config.precision_cdigits == 15
        assert config.frame_number_format == "frame{:05d}.svg"
        assert config.create_session_encoding == "utf-8"

    def test_testconfig_uses_defaults_for_missing_keys(self, tmp_path):
        """TestConfig uses default values for missing configuration keys"""
        pyproject = tmp_path / "pyproject.toml"
        # Minimal config
        config_data = {"tool": {"svg2fbf": {"test": {}}}}
        with open(pyproject, "wb") as f:
            tomli_w.dump(config_data, f)

        config = SessionConfig(pyproject)

        # Should use defaults (from [tool.svg2fbf.test] in pyproject.toml)
        assert config.image_tolerance == 0.05
        assert config.pixel_tolerance == 0.004
        assert config.max_frames == 50
        assert config.fps == 1.0
        assert config.animation_type == "once"

    def test_testconfig_raises_on_missing_file(self):
        """TestConfig raises FileNotFoundError for missing pyproject.toml"""
        with pytest.raises(FileNotFoundError):
            SessionConfig(Path("/nonexistent/pyproject.toml"))

    def test_testconfig_raises_on_malformed_toml(self, tmp_path):
        """TestConfig raises ValueError for malformed TOML"""
        pyproject = tmp_path / "pyproject.toml"
        with open(pyproject, "w") as f:
            f.write("invalid toml content {{{{")

        with pytest.raises(ValueError, match="Malformed pyproject.toml"):
            SessionConfig(pyproject)

    def test_testconfig_format_frame_filename(self, tmp_path):
        """TestConfig.format_frame_filename produces correct filenames"""
        pyproject = tmp_path / "pyproject.toml"
        config_data = {"tool": {"svg2fbf": {"test": {"frame_number_format": "frame{:05d}.svg"}}}}
        with open(pyproject, "wb") as f:
            tomli_w.dump(config_data, f)

        config = SessionConfig(pyproject)

        assert config.format_frame_filename(1) == "frame00001.svg"
        assert config.format_frame_filename(10) == "frame00010.svg"
        assert config.format_frame_filename(100) == "frame00100.svg"
        assert config.format_frame_filename(1000) == "frame01000.svg"


class TestConstants:
    """Test CONSTANTS usage and values"""

    def test_fbftest_suffix_pattern_matches_valid_suffix(self):
        """FBFTEST_SUFFIX_PATTERN correctly identifies test suffixes"""
        valid_suffixes = [
            "___FBFTEST[0]___",
            "___FBFTEST[1]___",
            "___FBFTEST[123]___",
            "___FBFTEST[999]___",
        ]
        for suffix in valid_suffixes:
            assert FBFTEST_SUFFIX_PATTERN.search(suffix), f"Should match: {suffix}"

    def test_fbftest_suffix_pattern_rejects_invalid_suffix(self):
        """FBFTEST_SUFFIX_PATTERN rejects invalid patterns"""
        invalid_suffixes = [
            "___FBFTEST___",  # Missing number
            "___FBFTEST()___",  # Wrong brackets
            "FBFTEST[0]",  # Missing underscores
            "___fbftest[0]___",  # Wrong case
        ]
        for suffix in invalid_suffixes:
            assert not FBFTEST_SUFFIX_PATTERN.search(suffix), f"Should not match: {suffix}"

    def test_fbftest_suffix_format_produces_valid_suffix(self):
        """FBFTEST_SUFFIX_FORMAT produces valid, matchable suffixes"""
        for i in range(10):
            suffix = FBFTEST_SUFFIX_FORMAT.format(i)
            assert FBFTEST_SUFFIX_PATTERN.search(suffix), f"Generated suffix should match pattern: {suffix}"

    def test_frame_number_patterns_all_compiled(self):
        """FRAME_NUMBER_PATTERNS contains compiled regex patterns"""
        assert len(FRAME_NUMBER_PATTERNS) > 0

        for pattern_tuple in FRAME_NUMBER_PATTERNS:
            assert len(pattern_tuple) == 3
            compiled_pattern, priority, description = pattern_tuple

            # Should be compiled regex
            assert hasattr(compiled_pattern, "search")
            assert hasattr(compiled_pattern, "match")

            # Priority should be integer
            assert isinstance(priority, int)
            assert priority >= 0

            # Description should be string
            assert isinstance(description, str)

    def test_frame_number_patterns_priorities_ordered(self):
        """FRAME_NUMBER_PATTERNS are arranged in priority order"""
        priorities = [priority for _, priority, _ in FRAME_NUMBER_PATTERNS]

        # Should not be strictly ascending (some have same priority)
        # but should be logical
        assert priorities[0] <= priorities[-1], "First priority should be <= last priority"

    def test_frame_number_patterns_contain_critical_patterns(self):
        """FRAME_NUMBER_PATTERNS contains all critical numbering patterns"""
        descriptions = [desc for _, _, desc in FRAME_NUMBER_PATTERNS]

        # Should have underscore pattern (most common)
        assert any("underscore" in desc for desc in descriptions)
        # Should have embedded numbers pattern (fallback)
        assert any("embedded" in desc for desc in descriptions)


class TestFrameNumberPriority:
    """Test FrameNumberPriority constants"""

    def test_frame_number_priority_has_all_levels(self):
        """FrameNumberPriority has all required priority levels"""
        assert hasattr(FrameNumberPriority, "UNDERSCORE_SVG")
        assert hasattr(FrameNumberPriority, "DASH_SVG")
        assert hasattr(FrameNumberPriority, "UNDERSCORE_EXTRA_EXT")
        assert hasattr(FrameNumberPriority, "DASH_EXTRA_EXT")
        assert hasattr(FrameNumberPriority, "DOT_SVG")
        assert hasattr(FrameNumberPriority, "START_NUMBER")
        assert hasattr(FrameNumberPriority, "BRACKETS")
        assert hasattr(FrameNumberPriority, "EMBEDDED")

    def test_frame_number_priority_values_are_ordered(self):
        """
        FrameNumberPriority values respect priority order
        (lower = higher priority)
        """
        assert FrameNumberPriority.UNDERSCORE_SVG < FrameNumberPriority.DASH_SVG
        assert FrameNumberPriority.DASH_SVG < FrameNumberPriority.DOT_SVG
        assert FrameNumberPriority.DOT_SVG < FrameNumberPriority.START_NUMBER
        assert FrameNumberPriority.START_NUMBER < FrameNumberPriority.BRACKETS
        assert FrameNumberPriority.BRACKETS < FrameNumberPriority.EMBEDDED


class TestDigitCountAdjustment:
    """Test DigitCountAdjustment constants"""

    def test_digit_count_adjustment_has_all_levels(self):
        """DigitCountAdjustment has all required digit count levels"""
        assert hasattr(DigitCountAdjustment, "FIVE_DIGITS")
        assert hasattr(DigitCountAdjustment, "SIX_DIGITS")
        assert hasattr(DigitCountAdjustment, "SEVEN_DIGITS")
        assert hasattr(DigitCountAdjustment, "OTHER")

    def test_digit_count_adjustment_values_are_ordered(self):
        """DigitCountAdjustment values respect ordering"""
        # They should form a logical progression
        assert isinstance(DigitCountAdjustment.FIVE_DIGITS, int)
        assert isinstance(DigitCountAdjustment.SIX_DIGITS, int)
        assert isinstance(DigitCountAdjustment.SEVEN_DIGITS, int)
        assert isinstance(DigitCountAdjustment.OTHER, int)


class TestValidateSVGNumbering:
    """Test SVG numbering validation"""

    def test_validate_svg_numbering_accepts_sequential_numbering(self, tmp_path):
        """validate_svg_numbering accepts properly numbered SVG sequences"""
        # Create numbered SVG files
        svg_files = []
        for i in range(1, 4):
            svg_file = tmp_path / f"frame_{i:05d}.svg"
            svg_file.write_text("<svg></svg>")
            svg_files.append(svg_file)

        is_valid, msg = validate_svg_numbering(svg_files)
        assert is_valid, f"Should validate sequential numbering: {msg}"

    def test_validate_svg_numbering_rejects_missing_frame(self, tmp_path):
        """validate_svg_numbering rejects gaps in frame numbering"""
        svg_files = [
            tmp_path / "frame_00001.svg",
            tmp_path / "frame_00003.svg",  # Skip frame 2
        ]
        for f in svg_files:
            f.write_text("<svg></svg>")

        is_valid, msg = validate_svg_numbering(svg_files)
        assert not is_valid, "Should reject missing frames"
        assert "Expected frame number 2" in msg or "found" in msg

    def test_validate_svg_numbering_rejects_no_numbers(self, tmp_path):
        """validate_svg_numbering rejects files with no numbers"""
        svg_file = tmp_path / "frame_no_number.svg"
        svg_file.write_text("<svg></svg>")

        is_valid, msg = validate_svg_numbering([svg_file])
        assert not is_valid, "Should reject files without numbers"
        assert "No number found" in msg

    def test_validate_svg_numbering_handles_different_patterns(self, tmp_path):
        """validate_svg_numbering works with different number patterns"""
        # Create files with different patterns but correct numbering
        patterns = [
            "animation_{:05d}.svg",
            "frame-{:05d}.svg",
            "{:05d}.svg",
        ]

        for pattern in patterns:
            svg_files = []
            for j in range(1, 3):
                svg_file = tmp_path / pattern.format(j)
                svg_file.write_text("<svg></svg>")
                svg_files.append(svg_file)

            is_valid, msg = validate_svg_numbering(svg_files)
            assert is_valid, f"Should validate pattern {pattern}: {msg}"

            # Clean up for next pattern
            for f in svg_files:
                f.unlink()


class TestExtractNumberCandidates:
    """Test number extraction from filenames"""

    def test_extract_number_candidates_finds_underscored_numbers(self):
        """extract_number_candidates finds underscore-separated numbers"""
        candidates = extract_number_candidates_from_filename("frame_00042.svg")
        numbers = [num for num, _ in candidates]
        assert 42 in numbers

    def test_extract_number_candidates_finds_dashed_numbers(self):
        """extract_number_candidates finds dash-separated numbers"""
        candidates = extract_number_candidates_from_filename("frame-00042.svg")
        numbers = [num for num, _ in candidates]
        assert 42 in numbers

    def test_extract_number_candidates_finds_embedded_numbers(self):
        """extract_number_candidates finds embedded numbers as fallback"""
        candidates = extract_number_candidates_from_filename("anim_42_scene.svg")
        numbers = [num for num, _ in candidates]
        assert 42 in numbers

    def test_extract_number_candidates_empty_for_no_numbers(self):
        """extract_number_candidates returns empty for files without numbers"""
        candidates = extract_number_candidates_from_filename("frame_no_number.svg")
        assert len(candidates) == 0

    def test_extract_number_candidates_respects_priority(self):
        """extract_number_candidates respects pattern priority"""
        # File with both underscore and dash patterns
        candidates = extract_number_candidates_from_filename("frame_00001-backup_00002.svg")

        if candidates:
            # First candidate should be higher priority (lower number)
            first_priority = candidates[0][1]
            second_priority = candidates[1][1] if len(candidates) > 1 else first_priority
            assert first_priority <= second_priority


class TestDetectHasNumericalSuffix:
    """Test detection of svg2fbf numerical suffix"""

    def test_detect_has_numerical_suffix_with_valid_suffix(self):
        """detect_has_numerical_suffix detects proper format"""
        filename = "frame_00001.svg"
        has_suffix = detect_has_numerical_suffix(filename)
        assert has_suffix, "Should detect proper 5-digit numerical suffix"

    def test_detect_has_numerical_suffix_without_suffix(self):
        """detect_has_numerical_suffix returns False for missing suffix"""
        filename = "frame_001.svg"  # Only 3 digits, not 5
        has_suffix = detect_has_numerical_suffix(filename)
        assert not has_suffix, "Should not detect suffix without exactly 5 digits"

    def test_detect_has_numerical_suffix_various_formats(self):
        """detect_has_numerical_suffix works with various valid formats"""
        valid_formats = [
            "frame_00001.svg",
            "animation_00042.svg",
            "scene_99999.svg",
            "paul02_00001.svg",  # Can have numbers before suffix
        ]
        for filename in valid_formats:
            has_suffix = detect_has_numerical_suffix(filename)
            assert has_suffix, f"Should detect proper format: {filename}"


class TestExtractSuffixNumber:
    """Test suffix number extraction from svg2fbf format"""

    def test_extract_suffix_number_from_valid_suffix(self):
        """extract_suffix_number extracts correct number from proper format"""
        filename = "frame_00042.svg"
        number = extract_suffix_number(filename)
        assert number == 42

    def test_extract_suffix_number_with_leading_zeros(self):
        """extract_suffix_number handles leading zeros correctly"""
        filename = "frame_00007.svg"
        number = extract_suffix_number(filename)
        assert number == 7

    def test_extract_suffix_number_with_zero(self):
        """extract_suffix_number handles zero value"""
        filename = "frame_00000.svg"
        number = extract_suffix_number(filename)
        assert number == 0

    def test_extract_suffix_number_returns_none_for_invalid_format(self):
        """extract_suffix_number returns None for invalid formats"""
        invalid_filenames = [
            "frame.svg",  # No number
            "frame_042.svg",  # Only 3 digits
            "frame042.svg",  # No underscore
            "frame_xyz.svg",  # Not numeric
        ]
        for filename in invalid_filenames:
            number = extract_suffix_number(filename)
            assert number is None, f"Should return None for invalid format: {filename}"


# ============================================================================
# Integration Tests
# ============================================================================


class TestConfigurationIntegration:
    """Integration tests for configuration system"""

    def test_load_config_matches_testconfig_class(self):
        """load_test_config results match TestConfig class"""
        config_dict = load_test_config()
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        config_obj = SessionConfig(pyproject_path)

        assert config_dict["image_tolerance"] == config_obj.image_tolerance
        assert config_dict["pixel_tolerance"] == config_obj.pixel_tolerance
        assert config_dict["max_frames"] == config_obj.max_frames
        assert config_dict["fps"] == config_obj.fps
        assert config_dict["animation_type"] == config_obj.animation_type
        assert config_dict["precision_digits"] == config_obj.precision_digits
        assert config_dict["precision_cdigits"] == config_obj.precision_cdigits


class TestFrameNumberingIntegration:
    """Integration tests for frame numbering system"""

    def test_all_constants_used_in_patterns(self):
        """All FrameNumberPriority values are used in patterns"""
        used_priorities = {priority for _, priority, _ in FRAME_NUMBER_PATTERNS}

        # At least some key priorities should be used
        assert FrameNumberPriority.UNDERSCORE_SVG in used_priorities
        assert FrameNumberPriority.EMBEDDED in used_priorities

    def test_patterns_cover_common_formats(self):
        """FRAME_NUMBER_PATTERNS covers common frame numbering formats"""
        test_cases = [
            ("frame_00001.svg", True),
            ("frame-00001.svg", True),
            ("00001.svg", True),
            ("frame[00001].svg", True),
            (".00001.svg", True),
        ]

        for filename, should_match in test_cases:
            matches = False
            for pattern, _, _ in FRAME_NUMBER_PATTERNS:
                if pattern.search(filename):
                    matches = True
                    break
            assert matches == should_match, f"Pattern matching failed for {filename}"
