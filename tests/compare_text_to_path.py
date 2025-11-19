#!/usr/bin/env python3
"""
Text-to-Path Visual Comparison Tool

Compares text-rendered SVG with path-converted SVG using anti-aliasing tolerance.
Uses validated 30/255 threshold to filter out anti-aliasing differences.

Usage:
    python compare_text_to_path.py text_version.png paths_version.png
    python compare_text_to_path.py text_version.png paths_version.png --threshold 40
"""

import sys
from pathlib import Path
from typing import Tuple

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Error: Required dependencies not installed", file=sys.stderr)
    print("Install with: pip install pillow numpy", file=sys.stderr)
    sys.exit(1)


def compare_images_with_threshold(img1_path: Path, img2_path: Path, threshold: int = 30) -> Tuple[int, int, float]:
    """
    Compare two images with anti-aliasing tolerance.

    Args:
        img1_path: Path to first image (text version)
        img2_path: Path to second image (paths version)
        threshold: Pixel difference threshold (0-255, default: 30)
                  Pixels differing by <= threshold are considered identical

    Returns:
        Tuple of (different_pixels, total_pixels, percentage)
    """
    # Load images
    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")

    # Verify same dimensions
    if img1.size != img2.size:
        raise ValueError(f"Image dimensions don't match: {img1.size} vs {img2.size}")

    # Convert to numpy arrays
    arr1 = np.array(img1, dtype=np.int32)
    arr2 = np.array(img2, dtype=np.int32)

    # Calculate per-channel absolute difference
    diff = np.abs(arr1 - arr2)

    # Max difference across RGB channels for each pixel
    max_channel_diff = np.max(diff, axis=2)

    # Count pixels exceeding threshold
    total_pixels = arr1.shape[0] * arr1.shape[1]
    significant_diff = max_channel_diff > threshold
    different_pixels = np.sum(significant_diff)

    percentage = (different_pixels / total_pixels) * 100

    return different_pixels, total_pixels, percentage


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare text-rendered and path-converted SVG images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare with default threshold (30/255)
  %(prog)s text.png paths.png

  # Compare with custom threshold
  %(prog)s text.png paths.png --threshold 40

  # Test multiple thresholds
  %(prog)s text.png paths.png --range 20 50

Threshold Guidelines:
  30/255  - Recommended for production (filters anti-aliasing)
  40/255  - More lenient (may hide minor differences)
  50/255  - Very lenient (for heavily aliased text)
  1/255   - Raw pixel comparison (no tolerance)
""",
    )

    parser.add_argument("image1", type=Path, help="Text-rendered image")
    parser.add_argument("image2", type=Path, help="Path-converted image")
    parser.add_argument("--threshold", "-t", type=int, default=30, help="Pixel difference threshold (0-255, default: 30)")
    parser.add_argument("--range", "-r", nargs=2, type=int, metavar=("MIN", "MAX"), help="Test range of thresholds (e.g., --range 20 50)")
    parser.add_argument("--requirement", "-q", type=float, default=0.4, help="Required maximum difference percentage (default: 0.4)")

    args = parser.parse_args()

    # Validate inputs
    if not args.image1.exists():
        parser.error(f"Image 1 not found: {args.image1}")
    if not args.image2.exists():
        parser.error(f"Image 2 not found: {args.image2}")

    if args.threshold < 0 or args.threshold > 255:
        parser.error("Threshold must be between 0 and 255")

    try:
        if args.range:
            # Test range of thresholds
            min_t, max_t = args.range
            if min_t >= max_t:
                parser.error("Range MIN must be less than MAX")

            print(f"Testing thresholds from {min_t} to {max_t}:")
            print("=" * 80)

            for threshold in range(min_t, max_t + 1, 5):
                diff_pixels, total_pixels, pct = compare_images_with_threshold(args.image1, args.image2, threshold)

                status = "✓ PASS" if pct < args.requirement else "✗ FAIL"
                print(f"Threshold {threshold:3d}/255: {diff_pixels:7,} pixels ({pct:6.3f}%) {status}")

            print("=" * 80)

        else:
            # Single threshold comparison
            diff_pixels, total_pixels, pct = compare_images_with_threshold(args.image1, args.image2, args.threshold)

            print("Image Comparison Results")
            print("=" * 80)
            print(f"Image 1:          {args.image1}")
            print(f"Image 2:          {args.image2}")
            print(f"Dimensions:       {Image.open(args.image1).size}")
            print(f"Total pixels:     {total_pixels:,}")
            print(f"Threshold:        {args.threshold}/255")
            print(f"Different pixels: {diff_pixels:,}")
            print(f"Percentage:       {pct:.3f}%")
            print(f"Requirement:      <{args.requirement}%")
            print("=" * 80)

            if pct < args.requirement:
                print(f"✓ SUCCESS: Difference {pct:.3f}% is below {args.requirement}% threshold")
                sys.exit(0)
            else:
                print(f"✗ FAILURE: Difference {pct:.3f}% exceeds {args.requirement}% threshold")
                sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
