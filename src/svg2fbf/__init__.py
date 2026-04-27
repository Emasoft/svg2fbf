"""
svg2fbf package - SVG to Frame-By-Frame SVG converter

This package provides utilities for converting SVG sequences into
Frame-By-Frame SVG (FBF.SVG) format with deduplication and optimization.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("svg2fbf")
except PackageNotFoundError:
    # Package not installed (running from source)
    __version__ = "0.0.0-dev"
