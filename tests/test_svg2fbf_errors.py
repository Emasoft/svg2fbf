"""
Unit tests for svg2fbf error handling

Tests cover:
- Missing viewBox attribute detection
- Error message correctness
- Exit code verification
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Path to the svg2fbf.py script
SVG2FBF_SCRIPT = Path(__file__).parent.parent / "src" / "svg2fbf.py"


class TestMissingViewBoxError:
    """Test svg2fbf detects and reports missing viewBox attribute"""

    def test_svg2fbf_exits_on_missing_viewbox(self, tmp_path):
        """svg2fbf exits with error code 1 when input SVG lacks viewBox"""
        # Create SVG without viewBox attribute
        svg_without_viewbox = tmp_path / "no_viewbox.svg"
        svg_without_viewbox.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect x="10" y="10" width="80" height="80" fill="blue"/>
</svg>"""
        )

        # Create second frame to make it an animation
        svg_frame2 = tmp_path / "frame_00002.svg"
        svg_frame2.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect x="10" y="10" width="80" height="80" fill="red"/>
</svg>"""
        )

        # Rename first file to match frame pattern
        svg_frame1 = tmp_path / "frame_00001.svg"
        svg_without_viewbox.rename(svg_frame1)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Run svg2fbf - should fail with exit code 1
        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                f"--input_folder={tmp_path}",
                f"--output_path={output_dir}",
                "--filename=test.fbf.svg",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",  # Required for Windows to decode UTF-8 box characters
        )

        # Verify exit code
        assert result.returncode == 1, f"Expected exit code 1 (error), got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"

    def test_missing_viewbox_error_message_content(self, tmp_path):
        """Error message contains correct guidance for missing viewBox"""
        # Create SVG without viewBox
        svg_file = tmp_path / "frame_00001.svg"
        svg_file.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <circle cx="50" cy="50" r="40" fill="green"/>
</svg>"""
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Run svg2fbf
        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                f"--input_folder={tmp_path}",
                f"--output_path={output_dir}",
                "--filename=test.fbf.svg",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",  # Required for Windows to decode UTF-8 box characters
        )

        # Verify error message content
        combined_output = (result.stdout or "") + (result.stderr or "")

        # Check for key phrases in error message
        assert "ERROR IMPORTING FRAMES" in combined_output, "Missing 'ERROR IMPORTING FRAMES' in output"
        assert "missing the viewBox attribute" in combined_output, "Missing 'missing the viewBox attribute' in output"
        assert "svg-repair-viewbox" in combined_output, "Missing 'svg-repair-viewbox' command reference in output"

    def test_svg_with_viewbox_does_not_error(self, tmp_path):
        """svg2fbf succeeds when input SVG has proper viewBox"""
        # Create SVG WITH viewBox attribute
        svg_with_viewbox = tmp_path / "frame_00001.svg"
        svg_with_viewbox.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80" fill="blue"/>
</svg>"""
        )

        # Create second frame with viewBox
        svg_frame2 = tmp_path / "frame_00002.svg"
        svg_frame2.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80" fill="red"/>
</svg>"""
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Run svg2fbf - should succeed
        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                f"--input_folder={tmp_path}",
                f"--output_path={output_dir}",
                "--filename=test.fbf.svg",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",  # Required for Windows to decode UTF-8 box characters
            timeout=30,
        )

        # Verify success
        assert result.returncode == 0, f"Expected exit code 0 (success), got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"

        # Verify FBF file was created
        fbf_file = output_dir / "test.fbf.svg"
        assert fbf_file.exists(), f"FBF output file not created: {fbf_file}"

    def test_error_message_includes_file_path(self, tmp_path):
        """Error message includes the specific file path that's missing viewBox"""
        # Create SVG without viewBox
        svg_file = tmp_path / "frame_00001.svg"
        svg_file.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon points="50,10 90,90 10,90" fill="purple"/>
</svg>"""
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Run svg2fbf
        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                f"--input_folder={tmp_path}",
                f"--output_path={output_dir}",
                "--filename=test.fbf.svg",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",  # Required for Windows to decode UTF-8 box characters
        )

        combined_output = (result.stdout or "") + (result.stderr or "")

        # Verify file path is mentioned in error
        assert "frame_00001.svg" in combined_output, "Error message should include the problematic filename"


class TestViewBoxErrorGuidance:
    """Test that error message provides actionable guidance"""

    def test_error_mentions_global_command(self, tmp_path):
        """Error message mentions svg-repair-viewbox as a global command"""
        svg_file = tmp_path / "frame_00001.svg"
        svg_file.write_text(('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect/></svg>'))

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                f"--input_folder={tmp_path}",
                f"--output_path={output_dir}",
                "--filename=test.fbf.svg",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",  # Required for Windows to decode UTF-8 box characters
        )

        combined_output = (result.stdout or "") + (result.stderr or "")

        # Check for global command mention
        assert "global command" in combined_output.lower(), "Error should mention 'global command'"
        assert "svg-repair-viewbox" in combined_output, "Error should reference svg-repair-viewbox tool"

    def test_error_provides_directory_option(self, tmp_path):
        """Error message shows how to repair entire directory"""
        svg_file = tmp_path / "frame_00001.svg"
        svg_file.write_text(('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><ellipse/></svg>'))

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(SVG2FBF_SCRIPT),
                f"--input_folder={tmp_path}",
                f"--output_path={output_dir}",
                "--filename=test.fbf.svg",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",  # Required for Windows to decode UTF-8 box characters
        )

        combined_output = (result.stdout or "") + (result.stderr or "")

        # Check for directory repair option
        assert "<input_folder>" in combined_output or "directory" in combined_output.lower(), "Error should show how to repair a directory of SVG files"
