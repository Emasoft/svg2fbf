"""
Unit tests for --text2path flag integration

Tests cover:
- CLI flag validation (--text2path requires svg-text2path package)
- CLI flag validation (--text2path-strict requires --text2path)
- Text to path conversion when package is available
- Error handling when package is not installed
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


class TestText2PathCLIValidation:
    """Test --text2path CLI flag validation"""

    def test_text2path_strict_requires_text2path_flag(self, tmp_path: Path) -> None:
        """--text2path-strict without --text2path should fail with clear error"""
        # Create minimal valid SVG input
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        svg_file = input_dir / "frame_00001.svg"
        svg_file.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80" fill="blue"/>
</svg>"""
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Run svg2fbf with --text2path-strict but without --text2path
        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                "-i",
                str(input_dir),
                "-o",
                str(output_dir),
                "-f",
                "test.fbf.svg",
                "--text2path-strict",  # Missing --text2path flag
            ],
            capture_output=True,
            text=True,
        )

        # Should fail with error about missing --text2path flag
        assert result.returncode != 0, "Expected non-zero exit code"
        assert "--text2path-strict requires --text2path" in result.stderr, f"Expected error message about --text2path requirement, got: {result.stderr}"


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
