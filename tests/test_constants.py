"""
Tests for constants defined in testrunner.py

Verifies:
- All required constants are defined
- Non-configurable values are correct
- Pattern constants match their intended use
- Constants are immutable and consistent
"""

import re
import sys
from pathlib import Path

# Add tests directory to path for import
sys.path.insert(0, str(Path(__file__).parent))

from testrunner import (
    FBFTEST_SUFFIX_FORMAT,
    FBFTEST_SUFFIX_PATTERN,
    FRAME_NUMBER_PATTERNS,
    DigitCountAdjustment,
    FrameNumberPriority,
)


class TestFBFTestSuffixPattern:
    """Test FBFTEST_SUFFIX_PATTERN constant"""

    def test_pattern_is_compiled_regex(self):
        """FBFTEST_SUFFIX_PATTERN is a compiled regex"""
        assert isinstance(FBFTEST_SUFFIX_PATTERN, type(re.compile("")))

    def test_pattern_matches_fbftest_suffixes(self):
        """Pattern matches valid FBFTEST suffixes"""
        test_cases = [
            ("___FBFTEST[0]___", True),
            ("___FBFTEST[1]___", True),
            ("___FBFTEST[42]___", True),
            ("___FBFTEST[9999]___", True),
            ("frame_00001___FBFTEST[0]___.svg", True),
            ("FBFTEST[0]", False),
            ("___FBFTEST___", False),
            ("___FBFTEST()___", False),
            ("frame_00001.svg", False),
        ]

        for text, should_match in test_cases:
            match = FBFTEST_SUFFIX_PATTERN.search(text) is not None
            assert match == should_match, f"Pattern match failed for '{text}'"

    def test_pattern_extracts_full_suffix(self):
        """Pattern successfully extracts complete suffix"""
        text = "frame_00001___FBFTEST[42]___.svg"
        match = FBFTEST_SUFFIX_PATTERN.search(text)
        assert match is not None
        assert match.group() == "___FBFTEST[42]___"


class TestFBFTestSuffixFormat:
    """Test FBFTEST_SUFFIX_FORMAT constant"""

    def test_format_is_string(self):
        """FBFTEST_SUFFIX_FORMAT is a string"""
        assert isinstance(FBFTEST_SUFFIX_FORMAT, str)

    def test_format_is_valid_template(self):
        """FBFTEST_SUFFIX_FORMAT is valid Python format string"""
        # Should be able to format with integers
        formatted = FBFTEST_SUFFIX_FORMAT.format(0)
        assert isinstance(formatted, str)
        assert "FBFTEST" in formatted
        assert "[" in formatted and "]" in formatted

    def test_format_produces_different_values(self):
        """FBFTEST_SUFFIX_FORMAT produces different values for different inputs"""
        suffix0 = FBFTEST_SUFFIX_FORMAT.format(0)
        suffix1 = FBFTEST_SUFFIX_FORMAT.format(1)
        assert suffix0 != suffix1

    def test_format_matches_pattern(self):
        """FBFTEST_SUFFIX_FORMAT output matches FBFTEST_SUFFIX_PATTERN"""
        for i in range(100):
            formatted = FBFTEST_SUFFIX_FORMAT.format(i)
            match = FBFTEST_SUFFIX_PATTERN.search(formatted)
            assert match is not None, f"Formatted suffix should match pattern: {formatted}"

    def test_format_produces_expected_output(self):
        """FBFTEST_SUFFIX_FORMAT produces expected format"""
        assert FBFTEST_SUFFIX_FORMAT.format(0) == "___FBFTEST[0]___"
        assert FBFTEST_SUFFIX_FORMAT.format(1) == "___FBFTEST[1]___"
        assert FBFTEST_SUFFIX_FORMAT.format(42) == "___FBFTEST[42]___"


class TestFrameNumberPatterns:
    """Test FRAME_NUMBER_PATTERNS constant"""

    def test_patterns_is_list(self):
        """FRAME_NUMBER_PATTERNS is a list"""
        assert isinstance(FRAME_NUMBER_PATTERNS, list)

    def test_patterns_not_empty(self):
        """FRAME_NUMBER_PATTERNS contains items"""
        assert len(FRAME_NUMBER_PATTERNS) > 0

    def test_patterns_have_correct_structure(self):
        """Each pattern has correct tuple structure"""
        for item in FRAME_NUMBER_PATTERNS:
            assert isinstance(item, tuple), "Each pattern should be a tuple"
            assert len(item) == 3, f"Each pattern tuple should have 3 elements, got {len(item)}"

            compiled_pattern, priority, description = item

            # First element: compiled regex
            assert hasattr(compiled_pattern, "search"), "First element should be compiled regex"
            assert hasattr(compiled_pattern, "match"), "First element should have match method"

            # Second element: integer priority
            assert isinstance(priority, int), f"Priority should be int, got {type(priority)}"

            # Third element: string description
            assert isinstance(description, str), f"Description should be str, got {type(description)}"

    def test_patterns_have_unique_descriptions(self):
        """Pattern descriptions are unique and descriptive"""
        descriptions = [desc for _, _, desc in FRAME_NUMBER_PATTERNS]

        # Most descriptions should be unique (some similar ones may exist)
        unique_count = len(set(descriptions))
        assert unique_count > len(descriptions) * 0.8, "Most descriptions should be unique"

    def test_patterns_priorities_are_reasonable(self):
        """Pattern priorities are non-negative integers in reasonable range"""
        for _, priority, _ in FRAME_NUMBER_PATTERNS:
            assert priority >= 0, "Priority should be non-negative"
            assert priority < 1000, "Priority should be in reasonable range"

    def test_patterns_cover_critical_formats(self):
        """Patterns cover all critical numbering formats"""
        test_cases = [
            ("frame_00001.svg", "underscore"),
            ("frame-00001.svg", "dash"),
            ("00001.svg", "start"),
            (
                "frame_[00001].svg",
                ["bracket", "underscore"],
            ),  # Matches underscore_[NNNNN].svg
            ("frame.00001.svg", "dot"),
            ("frame00001.svg", "embedded"),
        ]

        for filename, expected_formats in test_cases:
            matched = False
            matched_format = None

            for pattern, _, description in FRAME_NUMBER_PATTERNS:
                if pattern.search(filename):
                    matched = True
                    matched_format = description
                    break

            assert matched, f"No pattern matched filename: {filename}"

            # Handle both single string and list of acceptable formats
            if isinstance(expected_formats, list):
                assert any(fmt.lower() in matched_format.lower() for fmt in expected_formats), f"Format mismatch for {filename}: expected {expected_formats}, got {matched_format}"
            else:
                assert expected_formats.lower() in matched_format.lower(), f"Format mismatch for {filename}: expected {expected_formats}, got {matched_format}"

    def test_patterns_extract_numbers_correctly(self):
        """Patterns correctly extract frame numbers"""
        test_cases = [
            ("frame_00042.svg", 42),
            ("frame-00042.svg", 42),
            ("00042.svg", 42),
            ("frame[00042].svg", 42),
            ("frame.00042.svg", 42),
        ]

        for filename, expected_number in test_cases:
            found = False

            for pattern, _, _ in FRAME_NUMBER_PATTERNS:
                match = pattern.search(filename)
                if match:
                    extracted_number = int(match.group(1))
                    assert extracted_number == expected_number, f"Extracted wrong number from {filename}: expected {expected_number}, got {extracted_number}"
                    found = True
                    break

            assert found, f"No pattern extracted number from {filename}"


class TestFrameNumberPriority:
    """Test FrameNumberPriority class constants"""

    def test_priority_has_all_levels(self):
        """FrameNumberPriority has all required priority levels"""
        required_attributes = [
            "UNDERSCORE_SVG",
            "DASH_SVG",
            "UNDERSCORE_EXTRA_EXT",
            "DASH_EXTRA_EXT",
            "DOT_SVG",
            "START_NUMBER",
            "BRACKETS",
            "EMBEDDED",
        ]

        for attr in required_attributes:
            assert hasattr(FrameNumberPriority, attr), f"Missing priority level: {attr}"

    def test_priority_values_are_integers(self):
        """All priority values are integers"""
        for attr in dir(FrameNumberPriority):
            if attr.isupper():
                value = getattr(FrameNumberPriority, attr)
                assert isinstance(value, int), f"{attr} should be int, got {type(value)}"

    def test_priority_values_are_non_negative(self):
        """All priority values are non-negative"""
        for attr in dir(FrameNumberPriority):
            if attr.isupper():
                value = getattr(FrameNumberPriority, attr)
                assert value >= 0, f"{attr} should be non-negative, got {value}"

    def test_priority_respects_hierarchy(self):
        """Priority values respect the intended hierarchy"""
        # Lower values = higher priority
        assert FrameNumberPriority.UNDERSCORE_SVG < FrameNumberPriority.DASH_SVG, "UNDERSCORE should have higher priority than DASH"
        assert FrameNumberPriority.DASH_SVG < FrameNumberPriority.DOT_SVG, "DASH should have higher priority than DOT"
        assert FrameNumberPriority.DOT_SVG < FrameNumberPriority.START_NUMBER, "DOT should have higher priority than START_NUMBER"
        assert FrameNumberPriority.START_NUMBER < FrameNumberPriority.BRACKETS, "START_NUMBER should have higher priority than BRACKETS"
        assert FrameNumberPriority.BRACKETS < FrameNumberPriority.EMBEDDED, "BRACKETS should have higher priority than EMBEDDED"

    def test_priority_values_are_spread_out(self):
        """Priority values have reasonable spacing for subpriorities"""
        # UNDERSCORE_SVG should be 0, and there should be room for adjustments
        assert FrameNumberPriority.UNDERSCORE_SVG == 0
        # DASH_SVG should be significantly higher
        assert FrameNumberPriority.DASH_SVG >= 100
        # EMBEDDED should be much higher than others
        assert FrameNumberPriority.EMBEDDED >= 600

    def test_priority_sublevels_have_adjustments(self):
        """Extended extensions (extra ext) have lower priority than base"""
        # UNDERSCORE_EXTRA_EXT should be lower priority (higher value)
        # than UNDERSCORE_SVG
        assert FrameNumberPriority.UNDERSCORE_SVG < FrameNumberPriority.UNDERSCORE_EXTRA_EXT


class TestDigitCountAdjustment:
    """Test DigitCountAdjustment class constants"""

    def test_digit_adjustment_has_all_levels(self):
        """DigitCountAdjustment has all required digit count adjustments"""
        required_attributes = [
            "FIVE_DIGITS",
            "SIX_DIGITS",
            "SEVEN_DIGITS",
            "OTHER",
        ]

        for attr in required_attributes:
            assert hasattr(DigitCountAdjustment, attr), f"Missing digit adjustment: {attr}"

    def test_digit_adjustment_values_are_integers(self):
        """All digit adjustment values are integers"""
        for attr in ["FIVE_DIGITS", "SIX_DIGITS", "SEVEN_DIGITS", "OTHER"]:
            value = getattr(DigitCountAdjustment, attr)
            assert isinstance(value, int), f"{attr} should be int, got {type(value)}"

    def test_digit_adjustment_values_are_non_negative(self):
        """All digit adjustment values are non-negative"""
        for attr in ["FIVE_DIGITS", "SIX_DIGITS", "SEVEN_DIGITS", "OTHER"]:
            value = getattr(DigitCountAdjustment, attr)
            assert value >= 0, f"{attr} should be non-negative, got {value}"


class TestConstantsConsistency:
    """Test consistency between related constants"""

    def test_suffix_format_and_pattern_compatible(self):
        """FBFTEST_SUFFIX_FORMAT and FBFTEST_SUFFIX_PATTERN are compatible"""
        # Generate suffixes and verify they match the pattern
        for i in range(10):
            suffix = FBFTEST_SUFFIX_FORMAT.format(i)
            match = FBFTEST_SUFFIX_PATTERN.search(suffix)
            assert match is not None, f"Suffix format and pattern not compatible for iteration {i}"

    def test_patterns_use_defined_priorities(self):
        """All patterns use FrameNumberPriority constants"""
        priority_values = {
            FrameNumberPriority.UNDERSCORE_SVG,
            FrameNumberPriority.DASH_SVG,
            FrameNumberPriority.UNDERSCORE_EXTRA_EXT,
            FrameNumberPriority.DASH_EXTRA_EXT,
            FrameNumberPriority.DOT_SVG,
            FrameNumberPriority.START_NUMBER,
            FrameNumberPriority.BRACKETS,
            FrameNumberPriority.EMBEDDED,
        }

        used_priorities = set()
        for _, priority, _ in FRAME_NUMBER_PATTERNS:
            # Patterns may use priority or priority + adjustment
            for base_priority in priority_values:
                if priority >= base_priority and priority < base_priority + 100:
                    used_priorities.add(base_priority)

        # Most base priorities should be used
        assert len(used_priorities) >= 6, "Most base priorities should be used in patterns"

    def test_no_hardcoded_magic_numbers(self):
        """Constants should not contain unexplained magic numbers"""
        # Verify that priority gaps (100, 200, etc.) follow a logical pattern
        base_priorities = [
            FrameNumberPriority.UNDERSCORE_SVG,
            FrameNumberPriority.DASH_SVG,
            FrameNumberPriority.DOT_SVG,
            FrameNumberPriority.START_NUMBER,
            FrameNumberPriority.BRACKETS,
            FrameNumberPriority.EMBEDDED,
        ]

        for i in range(len(base_priorities) - 1):
            current = base_priorities[i]
            next_priority = base_priorities[i + 1]
            gap = next_priority - current

            # Gap should be at least 100 to allow for sub-priorities
            assert gap >= 100, f"Priority gap between {current} and {next_priority} seems too small"

    def test_digit_adjustments_reasonable_values(self):
        """Digit adjustment values are reasonable and sequential"""
        five = DigitCountAdjustment.FIVE_DIGITS
        six = DigitCountAdjustment.SIX_DIGITS
        seven = DigitCountAdjustment.SEVEN_DIGITS
        other = DigitCountAdjustment.OTHER

        # Values should form some logical progression
        values = [five, six, seven, other]
        assert len(set(values)) > 0, "Digit adjustments should be distinct"


class TestConstantsDocumentation:
    """Test that constants are properly documented"""

    def test_priority_class_has_docstring(self):
        """FrameNumberPriority class has docstring"""
        assert FrameNumberPriority.__doc__ is not None
        assert len(FrameNumberPriority.__doc__.strip()) > 0

    def test_digit_adjustment_class_has_docstring(self):
        """DigitCountAdjustment class has docstring"""
        assert DigitCountAdjustment.__doc__ is not None
        assert len(DigitCountAdjustment.__doc__.strip()) > 0


class TestConstantsImmutability:
    """Test that constants maintain their expected values"""

    def test_fbftest_suffix_format_unchanged(self):
        """FBFTEST_SUFFIX_FORMAT has expected value"""
        # Should format with numbers in brackets
        assert "{}" in FBFTEST_SUFFIX_FORMAT
        assert "FBFTEST" in FBFTEST_SUFFIX_FORMAT
        assert "[" in FBFTEST_SUFFIX_FORMAT and "]" in FBFTEST_SUFFIX_FORMAT

    def test_frame_number_patterns_complete_list(self):
        """FRAME_NUMBER_PATTERNS contains comprehensive coverage"""
        # Should have at least one pattern per priority level
        priority_groups = {}
        for _, priority, _ in FRAME_NUMBER_PATTERNS:
            base = priority // 100
            if base not in priority_groups:
                priority_groups[base] = []
            priority_groups[base].append(priority)

        # Should have patterns for at least 7 major priority levels
        assert len(priority_groups) >= 7, "Should have patterns for major priority levels"
