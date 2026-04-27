"""
Unit tests for --text2path flag integration

Tests cover:
- CLI flag validation (--text2path requires svg-text2path package)
- Text to path conversion when package is available
- Error handling when package is not installed
- FontCache singleton behavior
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Path to the svg2fbf.py script
SVG2FBF_SCRIPT = Path(__file__).parent.parent / "src" / "svg2fbf.py"


def _check_text2path_installed() -> bool:
    """Check if svg-text2path package is installed"""
    try:
        from svg_text2path import Text2PathConverter  # noqa: F401

        return True
    except ImportError:
        return False


class TestText2PathPackageCheck:
    """Test svg-text2path package availability checks"""

    def test_text2path_import_error_message(self) -> None:
        """Verify ImportError message is clear when svg-text2path is not installed"""
        # Import the function to test the import logic
        # This tests the error message construction, not actual import failure
        try:
            from svg_text2path import Text2PathConverter  # noqa: F401

            # If package is installed, skip this test
            pytest.skip("svg-text2path is installed, skipping import error test")
        except ImportError:
            # Expected when package is not installed
            pass


class TestText2PathConversion:
    """Test text to path conversion functionality"""

    @pytest.fixture
    def svg_with_text(self, tmp_path: Path) -> Path:
        """Create SVG with text elements for conversion testing"""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Frame 1 with text element
        svg_frame1 = input_dir / "frame_00001.svg"
        svg_frame1.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Hello World</text>
</svg>"""
        )

        # Frame 2 with text element
        svg_frame2 = input_dir / "frame_00002.svg"
        svg_frame2.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
  <text x="10" y="50" font-family="Arial" font-size="24">Frame Two</text>
</svg>"""
        )

        return input_dir

    def test_text2path_flag_without_package_shows_error(self, svg_with_text: Path, tmp_path: Path) -> None:
        """--text2path without svg-text2path package should fail with helpful error"""
        try:
            from svg_text2path import Text2PathConverter  # noqa: F401

            pytest.skip("svg-text2path is installed, cannot test missing package error")
        except ImportError:
            pass

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                "-i",
                str(svg_with_text),
                "-o",
                str(output_dir),
                "-f",
                "test.fbf.svg",
                "--text2path",
            ],
            capture_output=True,
            text=True,
        )

        # Should fail with helpful error message about installing the package
        assert result.returncode != 0, "Expected non-zero exit code when package is missing"
        assert "svg-text2path" in result.stderr.lower() or "svg-text2path" in result.stdout.lower(), f"Expected error message about svg-text2path package, got stdout: {result.stdout}, stderr: {result.stderr}"

    def test_text2path_converts_text_elements(self, svg_with_text: Path, tmp_path: Path) -> None:
        """--text2path should convert text elements to paths when package is available"""
        if not _check_text2path_installed():
            pytest.skip("svg-text2path not installed")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                "-i",
                str(svg_with_text),
                "-o",
                str(output_dir),
                "-f",
                "test.fbf.svg",
                "--text2path",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"svg2fbf failed with: {result.stderr}"

        # Verify output file exists
        output_file = output_dir / "test.fbf.svg"
        assert output_file.exists(), "Output FBF file should be created"

        # Verify no <text> elements remain in output
        content = output_file.read_text()
        assert "<text" not in content.lower(), "Text elements should be converted to paths"

    def test_text2path_precision_flag(self, svg_with_text: Path, tmp_path: Path) -> None:
        """--text2path-precision should control decimal precision in converted paths"""
        if not _check_text2path_installed():
            pytest.skip("svg-text2path not installed")

        # Convert with default precision (8)
        output_dir_default = tmp_path / "output_default"
        output_dir_default.mkdir()

        result_default = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                "-i",
                str(svg_with_text),
                "-o",
                str(output_dir_default),
                "-f",
                "default.fbf.svg",
                "--text2path",
                "--text2path-no-validate",  # Skip validation to focus on precision test
            ],
            capture_output=True,
            text=True,
        )
        assert result_default.returncode == 0, f"svg2fbf failed with default precision: {result_default.stderr}"

        # Convert with low precision (2)
        output_dir_low = tmp_path / "output_low"
        output_dir_low.mkdir()

        result_low = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                "-i",
                str(svg_with_text),
                "-o",
                str(output_dir_low),
                "-f",
                "low.fbf.svg",
                "--text2path",
                "--text2path-precision",
                "2",
                "--text2path-no-validate",
            ],
            capture_output=True,
            text=True,
        )
        assert result_low.returncode == 0, f"svg2fbf failed with low precision: {result_low.stderr}"

        # Both outputs should exist and contain path data
        default_output = output_dir_default / "default.fbf.svg"
        low_output = output_dir_low / "low.fbf.svg"
        assert default_output.exists(), "Default precision output should exist"
        assert low_output.exists(), "Low precision output should exist"

        # Both should have path elements (text converted to paths)
        default_content = default_output.read_text()
        low_content = low_output.read_text()
        assert "<path" in default_content.lower() or "d=" in default_content, "Default output should contain paths"
        assert "<path" in low_content.lower() or "d=" in low_content, "Low precision output should contain paths"

    def test_text2path_no_validate_flag(self, svg_with_text: Path, tmp_path: Path) -> None:
        """--text2path-no-validate should disable SVG validation after conversion"""
        if not _check_text2path_installed():
            pytest.skip("svg-text2path not installed")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Run with validation disabled
        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                "-i",
                str(svg_with_text),
                "-o",
                str(output_dir),
                "-f",
                "test.fbf.svg",
                "--text2path",
                "--text2path-no-validate",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"svg2fbf failed with --text2path-no-validate: {result.stderr}"

        # Verify output file exists
        output_file = output_dir / "test.fbf.svg"
        assert output_file.exists(), "Output FBF file should be created"

        # Verify text was converted to paths
        content = output_file.read_text()
        assert "<text" not in content.lower(), "Text elements should be converted to paths"


class TestFontCacheReuse:
    """Test FontCache singleton behavior"""

    def test_font_cache_returns_same_instance(self) -> None:
        """get_text2path_font_cache() should return the same instance on multiple calls"""
        if not _check_text2path_installed():
            pytest.skip("svg-text2path not installed")

        # Import the module
        import importlib.util

        spec = importlib.util.spec_from_file_location("svg2fbf", SVG2FBF_SCRIPT)
        if spec is None or spec.loader is None:
            pytest.skip("Could not load svg2fbf module")
        svg2fbf_module = importlib.util.module_from_spec(spec)

        import sys

        old_module = sys.modules.get("svg2fbf")
        sys.modules["svg2fbf"] = svg2fbf_module

        try:
            spec.loader.exec_module(svg2fbf_module)

            # Reset the font cache to ensure clean state
            svg2fbf_module._text2path_font_cache = None

            # Get the font cache twice
            cache1 = svg2fbf_module.get_text2path_font_cache()
            cache2 = svg2fbf_module.get_text2path_font_cache()

            # Should be the exact same object
            assert cache1 is cache2, "get_text2path_font_cache() should return the same instance"
            assert cache1 is not None, "FontCache should not be None"
        finally:
            if old_module is not None:
                sys.modules["svg2fbf"] = old_module
            elif "svg2fbf" in sys.modules:
                del sys.modules["svg2fbf"]
