"""
Puppeteer Renderer - Python wrapper for Node.js Puppeteer scripts

Provides Python interface to:
- Render SVG files to PNG
- Capture frames from FBF animation

Uses subprocess to call Node.js scripts with Puppeteer.
"""

import shutil
import subprocess
from pathlib import Path


class PuppeteerRenderer:
    """
    Python wrapper for Puppeteer-based SVG rendering

    Calls Node.js scripts to render SVGs and capture animation frames.
    """

    def __init__(self, node_scripts_dir: Path):
        """
        Initialize Puppeteer renderer

        Args:
            node_scripts_dir: Path to directory containing Node.js scripts
                             (render_svg.js, render_fbf_animation.js)

        Raises:
            RuntimeError: If Node.js or required scripts are not found
        """
        self.node_scripts_dir = node_scripts_dir
        self._verify_setup()

    def _verify_setup(self):
        """
        Verify Node.js and required scripts are available

        Why: Fail fast if environment is not properly configured
        """
        # Check Node.js is installed
        # Why: Need Node.js to run Puppeteer scripts
        if not shutil.which("node"):
            raise RuntimeError("Node.js not found. Please install Node.js: https://nodejs.org/")

        # Check required scripts exist
        # Why: Need these scripts to render SVGs and animations
        render_svg_script = self.node_scripts_dir / "render_svg.js"
        render_fbf_script = self.node_scripts_dir / "render_fbf_animation.js"

        if not render_svg_script.exists():
            raise RuntimeError(f"render_svg.js not found at: {render_svg_script}")

        if not render_fbf_script.exists():
            raise RuntimeError(f"render_fbf_animation.js not found at: {render_fbf_script}")

        # Check Puppeteer is installed
        # Why: Scripts won't work without Puppeteer
        node_modules = self.node_scripts_dir.parent / "node_modules"
        if not node_modules.exists():
            raise RuntimeError(f"node_modules not found. Run 'npm install' in {self.node_scripts_dir.parent}")

    def render_svg_to_png(
        self,
        svg_path: Path,
        output_png_path: Path,
        width: int = 1920,
        height: int = 1080,
        transform: str | None = None,
        viewbox: str | None = None,
        preserve_aspect_ratio: str = "xMidYMid meet",
    ) -> bool:
        """
        Render a single SVG file to PNG

        Uses Puppeteer to load SVG in headless Chrome and capture screenshot.

        Args:
            svg_path: Path to input SVG file
            output_png_path: Path where PNG should be saved
            width: Viewport width in pixels (default: 1920)
            height: Viewport height in pixels (default: 1080)
            transform: Optional SVG transform string to apply to the SVG root
                      (e.g., "matrix(0.42 0.0 0.0 0.42 0.0 0.0)")
                      This is the EXACT transform calculated by svg2fbf.py's
                      add_transform_to_match_input_frame_viewbox() function.
                      First frame should have None (no transform).
                      Subsequent frames get transforms to match first frame dimensions.
            viewbox: Optional viewBox string to use for rendering
                    (e.g., "0 0 600 400")
                    When transform is provided, this should be the FIRST frame's
                    viewBox, not the current frame's viewBox. This ensures the
                    rendered output uses the same coordinate space as the FBF
                    animation. If None, viewBox is extracted from the SVG file
                    itself.
            preserve_aspect_ratio: Optional preserveAspectRatio value
                                  (e.g., "xMidYMid meet", "none")
                                  Default: "xMidYMid meet"
                                  Use "none" for animations with negative viewBox
                                  coordinates

        Returns:
            True if rendering succeeded, False otherwise

        Why:
            Need ground truth PNGs from input SVGs with EXACT same transforms
            that svg2fbf applies. By using svg2fbf's actual transform calculation
            (via svg2fbf_frame_processor), we ensure pixel-perfect matching.
        """
        # Ensure paths are absolute
        # Why: Node.js script may have different working directory
        svg_path = svg_path.resolve()
        output_png_path = output_png_path.resolve()

        # Ensure output directory exists
        # Why: script can't create parent directories
        output_png_path.parent.mkdir(parents=True, exist_ok=True)

        # Build command
        # Why: Call Node.js script with proper arguments
        render_script = self.node_scripts_dir / "render_svg.js"
        cmd = [
            "node",
            str(render_script),
            str(svg_path),
            str(output_png_path),
            str(width),
            str(height),
        ]

        # Add transform if provided
        # Why: Apply svg2fbf's exact per-frame transform
        if transform:
            cmd.append(transform)
        else:
            cmd.append("")  # Why: Empty string placeholder to maintain argument positions

        # Add viewbox if provided
        # Why: Use first frame's viewBox for subsequent frames (matches FBF animation)
        if viewbox:
            cmd.append(viewbox)
        else:
            cmd.append("")  # Why: Empty string placeholder to maintain argument positions

        # Add preserveAspectRatio (always, even if empty string)
        # Why: Control aspect ratio behavior for SVGs with negative viewBox
        #      coordinates
        # CRITICAL: Always append to maintain argument position, empty string =
        #           omit attribute
        # Why: Empty string tells render_svg.js to NOT SET the
        #      preserveAspectRatio attribute. This is needed for SVGs with
        #      negative viewBox coordinates
        cmd.append(preserve_aspect_ratio if preserve_aspect_ratio is not None else "")

        try:
            # Execute Node.js script
            # Why: Puppeteer runs in Node.js, not Python
            _ = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,  # Why: Give enough time for Chrome to launch and render
            )

            # Check if output file was created
            # Why: Script might exit 0 but fail to create file
            if not output_png_path.exists():
                print("⚠️  render_svg.js exited successfully but output file not created")
                return False

            return True

        except subprocess.TimeoutExpired:
            print(f"⚠️  Timeout rendering SVG: {svg_path.name}")
            return False

        except subprocess.CalledProcessError as e:
            print(f"⚠️  Error rendering SVG: {svg_path.name}")
            print(f"   stdout: {e.stdout}")
            print(f"   stderr: {e.stderr}")
            return False

        except Exception as e:
            print(f"⚠️  Unexpected error rendering SVG: {svg_path.name}")
            print(f"   {str(e)}")
            return False

    def render_fbf_animation_frames(
        self,
        fbf_svg_path: Path,
        output_dir: Path,
        frame_count: int,
        fps: float = 10.0,
        width: int = 1920,
        height: int = 1080,
    ) -> list[Path]:
        """
        Capture frames from FBF animation as PNG files

        Uses Puppeteer to load FBF SVG animation in headless Chrome and
        capture frames at precise intervals.

        Args:
            fbf_svg_path: Path to FBF SVG file
            output_dir: Directory to save captured frame PNGs
            frame_count: Number of frames to capture
            fps: Frames per second (must match svg2fbf --speed argument)
            width: Viewport width in pixels (default: 1920)
            height: Viewport height in pixels (default: 1080)

        Returns:
            List of paths to captured PNG frames, in order (frame_0001.png, etc.)
            Empty list if capture failed

        Why:
            Need to verify FBF animation renders frames identical to inputs
        """
        # Ensure paths are absolute
        # Why: Node.js script may have different working directory
        fbf_svg_path = fbf_svg_path.resolve()
        output_dir = output_dir.resolve()

        # Ensure output directory exists
        # Why: Need place to save frames
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build command
        # Why: Call Node.js script with animation parameters
        render_script = self.node_scripts_dir / "render_fbf_animation.js"
        cmd = [
            "node",
            str(render_script),
            str(fbf_svg_path),
            str(output_dir),
            str(frame_count),
            str(fps),
            str(width),
            str(height),
        ]

        try:
            # Execute Node.js script
            # Why: Puppeteer handles SMIL animation timing and frame capture
            # Timeout: Give 5 seconds per frame + 30 second overhead
            timeout = (frame_count * 5) + 30
            _ = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)

            # Collect captured frame paths
            # Why: Return paths in order for comparison
            frame_paths = []
            for i in range(1, frame_count + 1):
                frame_name = f"frame_{i:04d}.png"
                frame_path = output_dir / frame_name

                if not frame_path.exists():
                    print(f"⚠️  Expected frame not found: {frame_name}")
                    return []  # Partial capture = failure

                frame_paths.append(frame_path)

            return frame_paths

        except subprocess.TimeoutExpired:
            print(f"⚠️  Timeout capturing animation frames (timeout: {timeout}s)")
            print(f"   Animation: {fbf_svg_path.name}")
            print(f"   Frames: {frame_count}, FPS: {fps}")
            return []

        except subprocess.CalledProcessError as e:
            print(f"⚠️  Error capturing animation frames: {fbf_svg_path.name}")
            print(f"   stdout: {e.stdout}")
            print(f"   stderr: {e.stderr}")
            return []

        except Exception as e:
            print(f"⚠️  Unexpected error capturing frames: {fbf_svg_path.name}")
            print(f"   {str(e)}")
            return []
