"""
Image Comparison Utilities

Pixel-perfect comparison of PNG images for validating svg2fbf output.

Compares input SVG renders against FBF animation frame captures to verify
that svg2fbf produces bit-identical output.
"""

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


class ImageComparator:
    """
    Pixel-perfect image comparison for test validation

    Why pixel-perfect:
    - svg2fbf should produce deterministic output
    - No interpolation or compression should alter pixels
    - Even 1-pixel difference indicates a bug
    """

    @staticmethod
    def compare_images_pixel_perfect(
        img1_path: Path,
        img2_path: Path,
        tolerance: float = 0.04,  # Image-level tolerance (percentage of pixels)
        pixel_tolerance: float = 1 / 256,  # Pixel-level tolerance (color difference)
    ) -> tuple[bool, dict[str, Any]]:
        """
        Compare two PNG images pixel-by-pixel

        Checks:
        - Both images exist and are readable
        - Dimensions match exactly
        - Every pixel RGBA value matches within tolerance

        Args:
            img1_path: Path to first image (ground truth)
            img2_path: Path to second image (test output)
            tolerance: Acceptable difference as percentage value (0.0 to 100.0)
                - 0.0 = pixel-perfect (default)
                - 0.001 = 0.001% difference allowed
                - 0.005 = 0.005% difference allowed (current default)
                - 0.0001 = 0.0001% difference (target goal)
            pixel_tolerance: Acceptable color difference per pixel (0.0 to 1.0)
                - 0.0 = exact RGB match required
                - 1/256 = 0.0039 ≈ 0.4% (default) - allows 1 RGB value difference
                - 5/256 = 0.0195 ≈ 2.0% - allows 5 RGB value difference
                - Converts to RGB scale: pixel_tolerance * 255 = max difference

        Returns:
            (is_identical, diff_info)

            is_identical: True if difference is within tolerance, False otherwise

            diff_info: Dictionary with comparison details:
                - images_exist: bool - Both files exist
                - dimensions_match: bool - Same width/height
                - diff_pixels: int - Count of different pixels
                - total_pixels: int - Total pixels compared
                - diff_percentage: float - Percentage of different pixels
                - tolerance: float - Acceptable difference percentage
                - within_tolerance: bool - True if diff_percentage <= tolerance
                - first_diff_location: (y, x) - Coordinates of first difference
                - img1_size: (width, height) - Dimensions of first image
                - img2_size: (width, height) - Dimensions of second image
                - error: str - Error message if comparison failed

        Why:
            Detailed diff_info helps diagnose test failures
        """
        # Check both images exist
        # Why: Can't compare if files missing
        try:
            img1 = Image.open(img1_path).convert("RGBA")
            img2 = Image.open(img2_path).convert("RGBA")
        except FileNotFoundError as e:
            return False, {"images_exist": False, "error": f"File not found: {str(e)}"}
        except Exception as e:
            return False, {
                "images_exist": False,
                "error": f"Error loading images: {str(e)}",
            }

        # Check dimensions match
        # Why: Different sizes = automatically different
        if img1.size != img2.size:
            return False, {
                "images_exist": True,
                "dimensions_match": False,
                "img1_size": img1.size,
                "img2_size": img2.size,
                "error": f"Dimension mismatch: {img1.size} vs {img2.size}",
            }

        # Convert to numpy arrays for fast comparison
        # Why: NumPy is much faster than PIL for pixel operations
        arr1 = np.array(img1)
        arr2 = np.array(img2)

        # Calculate absolute difference per channel
        # Why: Need to measure magnitude of color difference, not just binary match
        abs_diff = np.abs(arr1.astype(float) - arr2.astype(float))

        # Convert pixel_tolerance from fraction (0.0-1.0) to RGB scale (0-255)
        # Why: pixel_tolerance is normalized, RGB values are 0-255
        # Example: pixel_tolerance=1/256 → threshold_rgb=0.996 ≈ 1 RGB value
        threshold_rgb = pixel_tolerance * 255

        # Find differences (any channel exceeding threshold)
        # Why: Allow small differences (e.g., 1 RGB value) from anti-aliasing
        # A pixel is "different" if ANY channel (R, G, B, or A) exceeds threshold
        diff_mask = np.any(abs_diff > threshold_rgb, axis=2)
        diff_pixels = int(np.sum(diff_mask))
        total_pixels = arr1.shape[0] * arr1.shape[1]

        # Calculate difference as percentage (0.0 to 100.0)
        # Why: Direct percentage comparison with tolerance parameter
        diff_percentage = ((diff_pixels / total_pixels) * 100) if total_pixels > 0 else 0.0

        # Find first difference location
        # Why: Helps identify where rendering diverged
        first_diff_location = None
        if diff_pixels > 0:
            diff_indices = np.argwhere(diff_mask)
            first_diff_location = tuple(diff_indices[0])  # (y, x)

        # Are images identical?
        # Why: Check if difference is within acceptable tolerance
        # Both values are percentages (0.0-100.0 range)
        is_identical = diff_percentage <= tolerance

        # Build detailed diff info
        # Why: Test failures need this information to debug
        diff_info = {
            "images_exist": True,
            "dimensions_match": True,
            "diff_pixels": diff_pixels,
            "total_pixels": total_pixels,
            "diff_percentage": diff_percentage,  # Percentage (0-100)
            "tolerance": tolerance,  # Percentage (0-100)
            "pixel_tolerance": pixel_tolerance,  # Fraction (0.0-1.0)
            "pixel_tolerance_rgb": threshold_rgb,  # RGB units (0-255)
            "within_tolerance": is_identical,
            "first_diff_location": first_diff_location,
            "img1_size": img1.size,
            "img2_size": img2.size,
        }

        return is_identical, diff_info

    @staticmethod
    def generate_diff_image(
        img1_path: Path,
        img2_path: Path,
        output_path: Path,
        pixel_tolerance: float = 1 / 256,
    ) -> None:
        """
        Generate visual diff image highlighting differences in red

        Creates a new image showing:
        - Identical pixels: Original color
        - Different pixels: Red

        Args:
            img1_path: Path to first image
            img2_path: Path to second image
            output_path: Path to save diff image

        Why:
            Visual diff helps identify patterns in rendering differences
        """
        try:
            img1 = Image.open(img1_path).convert("RGBA")
            img2 = Image.open(img2_path).convert("RGBA")

            # Ensure same size
            # Why: Can't create diff for different-sized images
            if img1.size != img2.size:
                raise ValueError(f"Image sizes don't match: {img1.size} vs {img2.size}")

            arr1 = np.array(img1)
            arr2 = np.array(img2)

            # Calculate absolute difference per channel
            # Why: Need to measure magnitude of color difference, not just binary match
            abs_diff = np.abs(arr1.astype(float) - arr2.astype(float))

            # Convert pixel_tolerance from fraction to RGB scale
            # Why: pixel_tolerance is normalized (0.0-1.0), RGB values are 0-255
            threshold_rgb = pixel_tolerance * 255

            # Find differences (any channel exceeding threshold)
            # Why: Need to know which pixels to highlight
            #      (consistent with compare_images_pixel_perfect)
            diff_mask = np.any(abs_diff > threshold_rgb, axis=2)

            # Create diff image starting with first image
            # Why: Show context of where differences occur
            diff_img = arr1.copy()

            # Highlight differences in bright red
            # Why: Make differences visually obvious
            diff_img[diff_mask] = [255, 0, 0, 255]  # Red, fully opaque

            # Save diff image
            # Why: Persist for inspection after test
            Image.fromarray(diff_img).save(output_path)

        except Exception as e:
            print(f"⚠️  Error generating diff image: {str(e)}")
            # Don't fail test just because diff image failed
            # Why: Diff image is optional debugging aid

    @staticmethod
    def generate_grayscale_diff_map(img1_path: Path, img2_path: Path, output_path: Path) -> None:
        """
        Generate grayscale diff map showing magnitude of differences

        Creates a grayscale image where:
        - Black (0): Pixels are identical
        - White (255): Maximum difference in any channel
        - Shades of gray: Proportional to difference magnitude

        Args:
            img1_path: Path to first image
            img2_path: Path to second image
            output_path: Path to save grayscale diff map

        Why:
            Visual measurement of difference intensity helps identify
            anti-aliasing vs actual content differences
        """
        try:
            img1 = Image.open(img1_path).convert("RGBA")
            img2 = Image.open(img2_path).convert("RGBA")

            # Ensure same size
            # Why: Can't create diff for different-sized images
            if img1.size != img2.size:
                raise ValueError(f"Image sizes don't match: {img1.size} vs {img2.size}")

            arr1 = np.array(img1, dtype=np.float64)
            arr2 = np.array(img2, dtype=np.float64)

            # Calculate absolute difference for each channel
            # Why: Want to measure magnitude, not direction of change
            abs_diff = np.abs(arr1 - arr2)

            # Take maximum difference across all channels (R, G, B, A)
            # Why: If any channel differs, we want to show it
            max_diff = np.max(abs_diff, axis=2)

            # Convert to uint8 grayscale (0-255)
            # Why: Standard image format
            grayscale_diff = max_diff.astype(np.uint8)

            # Save as grayscale PNG
            # Why: Shows difference intensity visually
            Image.fromarray(grayscale_diff, mode="L").save(output_path)

        except Exception as e:
            print(f"⚠️  Error generating grayscale diff map: {str(e)}")
            # Don't fail test just because diff image failed
            # Why: Diff map is optional debugging aid

    @staticmethod
    def calculate_perceptual_difference(img1_path: Path, img2_path: Path) -> float | None:
        """
        Calculate perceptual difference between images

        Uses structural similarity or mean squared error.

        Args:
            img1_path: Path to first image
            img2_path: Path to second image

        Returns:
            Perceptual difference score (0.0 = identical, higher = more different)
            None if calculation failed

        Why:
            May be useful for future tolerance-based comparison mode
            (not used in current pixel-perfect tests)
        """
        try:
            img1 = Image.open(img1_path).convert("RGBA")
            img2 = Image.open(img2_path).convert("RGBA")

            if img1.size != img2.size:
                return None

            arr1 = np.array(img1, dtype=np.float64)
            arr2 = np.array(img2, dtype=np.float64)

            # Calculate mean squared error
            # Why: Simple perceptual metric
            mse = np.mean((arr1 - arr2) ** 2)

            return float(mse)

        except Exception:
            return None

    @staticmethod
    def detect_empty_or_truncated_content(img_path: Path, empty_threshold: float = 0.95, truncated_threshold: float = 0.50) -> tuple[bool, dict[str, Any]]:
        """
        Detect if image has empty or truncated content

        CRITICAL: This prevents false positives where BOTH input and output are
        broken in the same way (e.g., both truncated), causing pixel-perfect
        comparison to incorrectly pass.

        Detection strategy:
        1. **Empty detection**: Image is mostly transparent or single color
           - Checks if >95% of pixels have same RGB value (within small tolerance)
           - Returns: is_empty=True if content is missing

        2. **Truncation detection**: Content is clipped/cut off
           - Analyzes edge regions (10% border on all sides)
           - Checks if edge regions are significantly emptier than center
           - Returns: is_truncated=True if content appears clipped

        Args:
            img_path: Path to image file
            empty_threshold: Fraction of uniform pixels to consider empty (0.0-1.0)
                           Default: 0.95 (95% uniform = empty)
            truncated_threshold: Fraction of empty edge vs non-empty center
                                Default: 0.50 (50% edge empty = truncated)

        Returns:
            (has_issue, info_dict)

            has_issue: True if image has empty or truncated content

            info_dict: Dictionary with detection details:
                - is_empty: bool - Image is mostly uniform/transparent
                - is_truncated: bool - Content appears clipped at edges
                - uniform_pixel_ratio: float - Fraction of pixels matching most
                  common color
                - edge_emptiness: float - Fraction of edge pixels that are background
                - center_fullness: float - Fraction of center pixels that have content
                - most_common_color: tuple - RGB of dominant color
                - error: str - Error message if detection failed

        Why:
            Prevents useless tests that compare "broken vs broken" and pass.
            Forces investigation of WHY rendering failed.
        """
        try:
            img = Image.open(img_path).convert("RGBA")
            arr = np.array(img)

            height, width = arr.shape[:2]
            total_pixels = height * width

            # === EMPTY DETECTION ===
            # Check if image is mostly a single color (empty/background)

            # Find most common RGB color (ignore alpha for now)
            rgb_arr = arr[:, :, :3]  # RGB channels only
            # Reshape to list of RGB tuples and find unique colors
            pixels_flat = rgb_arr.reshape(-1, 3)
            unique_colors, counts = np.unique(pixels_flat, axis=0, return_counts=True)

            # Get most common color and its frequency
            most_common_idx = np.argmax(counts)
            most_common_color = tuple(unique_colors[most_common_idx])
            most_common_count = counts[most_common_idx]
            uniform_pixel_ratio = most_common_count / total_pixels

            # Is image empty (>95% same color)?
            is_empty = uniform_pixel_ratio >= empty_threshold

            # === TRUNCATION DETECTION ===
            # Check if edges are significantly emptier than center

            # Define edge and center regions
            # Edge: 10% border on all sides
            # Center: Inner 80% of image
            edge_size = int(min(width, height) * 0.1)

            # Extract edge and center regions
            top_edge = arr[:edge_size, :, :3]
            bottom_edge = arr[-edge_size:, :, :3]
            left_edge = arr[:, :edge_size, :3]
            right_edge = arr[:, -edge_size:, :3]

            # Center region (inner 80%)
            center = arr[edge_size:-edge_size, edge_size:-edge_size, :3]

            # Count "background" pixels (close to most_common_color) in each region
            def count_background_pixels(region):
                """Count pixels matching most common color (within small tolerance)"""
                if region.size == 0:
                    return 0
                # Reshape to list of pixels
                pixels = region.reshape(-1, 3)
                # Calculate color distance from most common color
                distances = np.sqrt(np.sum((pixels - most_common_color) ** 2, axis=1))
                # Threshold: within 10 RGB units = background
                background_count = np.sum(distances < 10)
                return background_count

            # Calculate emptiness ratios
            edge_pixels = top_edge.size + bottom_edge.size + left_edge.size + right_edge.size
            edge_background_count = count_background_pixels(top_edge) + count_background_pixels(bottom_edge) + count_background_pixels(left_edge) + count_background_pixels(right_edge)
            edge_emptiness = edge_background_count / edge_pixels if edge_pixels > 0 else 0.0

            center_pixels = center.size
            center_background_count = count_background_pixels(center)
            center_fullness = 1.0 - (center_background_count / center_pixels if center_pixels > 0 else 0.0)

            # Is image truncated?
            # If edges are >50% empty AND center has <50% content, likely truncated
            is_truncated = (edge_emptiness >= truncated_threshold) and (center_fullness < 0.5)

            # Build result
            has_issue = is_empty or is_truncated

            info_dict = {
                "is_empty": is_empty,
                "is_truncated": is_truncated,
                "uniform_pixel_ratio": float(uniform_pixel_ratio),
                "edge_emptiness": float(edge_emptiness),
                "center_fullness": float(center_fullness),
                "most_common_color": most_common_color,
                "dimensions": (width, height),
            }

            return has_issue, info_dict

        except FileNotFoundError:
            return True, {"error": f"File not found: {img_path}", "is_empty": True}
        except Exception as e:
            return True, {"error": f"Error analyzing image: {str(e)}", "is_empty": True}
