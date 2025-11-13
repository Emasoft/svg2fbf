"""
Configuration reader for test settings

Reads all test defaults from pyproject.toml to maintain a single source of truth.
No hardcoded values allowed - all defaults must come from the TOML file.

Why:
- Single source of truth for all test settings
- Prevents inconsistencies across different scripts
- Makes configuration changes easier (edit one file)
- Self-documenting (config file shows all available settings)
"""

import sys
from pathlib import Path
from typing import Any

# Python 3.10 compatibility: tomllib added in 3.11
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        # Fallback to tomllib backport
        import tomllib  # type: ignore[import-not-found]


class ConfigHelper:
    """
    Reads and provides access to test configuration from pyproject.toml

    Usage:
        config = ConfigHelper()
        tolerance = config.tolerance
        max_frames = config.max_frames
    """

    _instance = None
    _config: dict[str, Any] = {}

    def __new__(cls):
        """Singleton pattern - only load config once"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Load configuration from pyproject.toml"""
        # Find pyproject.toml (go up from tests/utils/ to project root)
        current = Path(__file__).parent  # tests/utils/
        project_root = current.parent.parent  # project root
        toml_path = project_root / "pyproject.toml"

        if not toml_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {toml_path}")

        # Load TOML file
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        # Extract test configuration
        if "tool" not in data or "svg2fbf" not in data["tool"] or "test" not in data["tool"]["svg2fbf"]:
            raise ValueError("Missing [tool.svg2fbf.test] section in pyproject.toml. Please add test configuration to pyproject.toml")

        self._config = data["tool"]["svg2fbf"]["test"]

    @property
    def image_tolerance(self) -> float:
        """Image-level tolerance: percentage of pixels allowed to differ
        (e.g., 0.04 = 0.04%)"""
        return self._config.get("image_tolerance", 0.04)

    @property
    def pixel_tolerance(self) -> float:
        """Pixel-level tolerance: color difference threshold per pixel
        (0.0-1.0, e.g., 0.0039 ≈ 1/256)"""
        return self._config.get("pixel_tolerance", 1 / 256)

    @property
    def max_frames(self) -> int:
        """Maximum number of frames to test in large batches"""
        return self._config.get("max_frames", 50)

    @property
    def fps(self) -> float:
        """Animation playback speed (frames per second)"""
        return self._config.get("fps", 1.0)

    @property
    def animation_type(self) -> str:
        """Animation type (must be 'once' for tests)"""
        return self._config.get("animation_type", "once")

    @property
    def precision_digits(self) -> int:
        """svg2fbf coordinate precision"""
        return self._config.get("precision_digits", 28)

    @property
    def precision_cdigits(self) -> int:
        """svg2fbf control point precision"""
        return self._config.get("precision_cdigits", 28)

    @property
    def default_frames(self) -> int:
        """Default frame count for test runner"""
        return self._config.get("default_frames", 2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get any config value by key"""
        return self._config.get(key, default)

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"ConfigHelper({self._config})"


# Convenience function for quick access
def get_test_config() -> ConfigHelper:
    """Get the singleton test configuration instance"""
    return ConfigHelper()
