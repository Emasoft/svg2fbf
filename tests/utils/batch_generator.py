"""
Test Batch Generator

Generates random batches of SVG files for testing svg2fbf.

Features:
- Recursively scans examples/ folder for SVG files
- Validates each SVG before including in test pool
- Generates random test batches with proper frame numbering
- Supports configurable batch sizes (2, 5, 10, 50 frames, etc.)
- Automatically repairs viewBox for animation consistency
"""

import random
import shutil
import sys
from pathlib import Path

from .svg_validator import SVGValidator

# Import viewBox repair function from testrunner
# Why: Batch frames need consistent viewBox for animation rendering
sys.path.insert(0, str(Path(__file__).parent.parent))
from testrunner import repair_animation_sequence_viewbox


class BatchGenerator:
    """
    Generates randomized test batches from validated SVG pool

    Why randomization:
    - Different frame combinations can expose bugs
    - Tests are more comprehensive than fixed sequences
    - Each test run exercises different paths through code
    """

    def __init__(self, examples_dir: Path, svg_validator: SVGValidator):
        """
        Initialize batch generator

        Args:
            examples_dir: Path to examples/ folder containing SVG test data
            svg_validator: SVGValidator instance for validating SVGs

        Why:
            Need validator to filter out problematic SVGs before testing
        """
        self.examples_dir = examples_dir
        self.svg_validator = svg_validator
        self.svg_pool = self._collect_valid_svgs()

        if not self.svg_pool:
            raise RuntimeError(f"No valid SVG files found in {examples_dir}. Check that examples/ folder exists and contains SVG files.")

    def _collect_valid_svgs(self) -> list[Path]:
        """
        Recursively find all VALID SVG files in examples/ folder

        Only includes SVGs that pass all validation checks.
        Invalid SVGs are cached and skipped on future runs.

        Returns:
            List of paths to valid SVG files

        Why:
            Test failures should indicate bugs in svg2fbf, not invalid inputs
        """
        # Find all .svg and .svgz files recursively
        # Why: Examples may be organized in subdirectories
        # IMPORTANT: Exclude *.fbf.svg files (FBF animations, not source frames)
        all_svgs = []
        for ext in ["*.svg", "*.svgz"]:
            all_matches = self.examples_dir.rglob(ext)
            # Filter out FBF animation files
            # Why: FBF files are animations, not source frames for testing
            filtered = [p for p in all_matches if not p.name.endswith(".fbf.svg")]
            all_svgs.extend(filtered)

        if not all_svgs:
            print(f"⚠️  No SVG files found in {self.examples_dir}")
            return []

        print(f"\n🔍 Validating {len(all_svgs)} SVG files from examples/...")

        # Validate each SVG
        # Why: Filter out files that would cause test failures
        valid_svgs = []
        invalid_count = 0

        for svg_path in all_svgs:
            is_valid, reason = self.svg_validator.is_valid(svg_path)

            if is_valid:
                valid_svgs.append(svg_path)
            else:
                invalid_count += 1
                # Show relative path for readability
                relative_path = svg_path.relative_to(self.examples_dir)
                print(f"  ⚠️  Skipping invalid: {relative_path}")
                print(f"     Reason: {reason}")

        print(f"\n✓ Found {len(valid_svgs)} valid SVGs, {invalid_count} invalid")

        # Show cache statistics
        # Why: Help user understand how many SVGs are cached as invalid
        stats = self.svg_validator.get_cache_stats()
        print(f"📋 Invalid SVG cache: {stats['total_invalid']} entries\n")

        return valid_svgs

    def generate_batch(
        self,
        frame_count: int,
        output_dir: Path,
        batch_name: str = None,
        seed: int = None,
    ) -> dict:
        """
        Generate a random test batch with specified number of frames

        Creates a temporary folder with:
        - Randomly selected SVG files from valid pool
        - Proper frame numbering (frame_FRAME00001.svg, etc.)
        - Metadata about batch composition

        Args:
            frame_count: Number of frames in this batch
            output_dir: Parent directory for batch folder
            batch_name: Optional name for batch folder (default: auto-generated)
            seed: Optional random seed for reproducibility

        Returns:
            Dictionary with batch information:
            - batch_dir: Path to batch folder
            - frame_count: Number of frames
            - svg_sources: List of source SVG paths used
            - frame_files: List of frame files in batch

        Why:
            svg2fbf expects numbered input files in specific format
        """
        # Set random seed if provided
        # Why: Allows reproducible test runs for debugging
        if seed is not None:
            random.seed(seed)

        # Generate batch name if not provided
        # Why: Need unique folder name for each batch
        if batch_name is None:
            batch_name = f"batch_{frame_count}frames"

        batch_dir = output_dir / batch_name
        batch_dir.mkdir(parents=True, exist_ok=True)

        # Randomly select SVGs from pool (with replacement)
        # Why: With replacement allows testing same SVG in different positions
        #      Useful for exposing position-dependent bugs
        if frame_count > len(self.svg_pool):
            # Allow reusing SVGs if we need more frames than available
            selected_svgs = random.choices(self.svg_pool, k=frame_count)
        else:
            # Prefer unique SVGs if we have enough
            selected_svgs = random.sample(self.svg_pool, k=frame_count)

        # Copy and rename with proper frame numbering
        # Why: svg2fbf expects frame_FRAME00001.svg format
        frame_files = []
        for i, svg_path in enumerate(selected_svgs):
            # Frame numbering: 00001, 00002, 00003, ...
            # Why: svg2fbf sorts alphanumerically, needs zero-padding
            frame_num = str(i + 1).zfill(5)
            dest_name = f"frame_FRAME{frame_num}.svg"
            dest_path = batch_dir / dest_name

            # Copy SVG to batch folder
            # Why: Keep original files unchanged
            shutil.copy(svg_path, dest_path)
            frame_files.append(dest_path)

        # CRITICAL: Repair viewBox for animation consistency
        # Why: Source SVGs may have missing/incorrect viewBox attributes
        #      Animation frames MUST have same viewBox to prevent frame jumping
        #      This is testrunner's responsibility, NOT svg2fbf's
        # NOTE: svg2fbf.py is incompatible with svg-repair-viewbox and never calls it
        try:
            repair_animation_sequence_viewbox(frame_files, verbose=False)
        except RuntimeError as e:
            # Don't fail batch generation - some SVGs may work without repair
            # Why: Tests can still run, and failures will be caught by rendering
            #      validation
            print(f"⚠️  Warning: ViewBox repair failed for batch: {e}")

        # Return batch metadata
        # Why: Tests need to know what was generated
        return {
            "batch_dir": batch_dir,
            "frame_count": frame_count,
            "svg_sources": selected_svgs,  # Original source paths
            "frame_files": frame_files,  # Numbered copies in batch folder
            "batch_name": batch_name,
        }

    def cleanup_batch(self, batch_dir: Path):
        """
        Remove test batch directory and all contents

        Args:
            batch_dir: Path to batch folder to remove

        Why:
            Clean up temporary files after test completion
        """
        if batch_dir.exists() and batch_dir.is_dir():
            shutil.rmtree(batch_dir)

    def get_svg_pool_size(self) -> int:
        """
        Get number of valid SVGs in the pool

        Returns:
            Count of valid SVGs available for testing

        Why:
            Useful for debugging and test configuration
        """
        return len(self.svg_pool)

    def get_svg_pool_paths(self) -> list[Path]:
        """
        Get list of all valid SVG paths in the pool

        Returns:
            List of paths to valid SVG files

        Why:
            May be useful for test debugging or inspection
        """
        return self.svg_pool.copy()
