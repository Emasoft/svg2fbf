#!/usr/bin/env python3
"""
Automatic dependency installer for svg-repair-viewbox.

Detects the system and automatically installs Node.js and Puppeteer
using the appropriate package manager.
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(command) is not None


def run_command(cmd: list[str], description: str, check: bool = True, cwd: str | None = None) -> tuple[bool, str]:
    """
    Run a shell command and return success status and output.

    Args:
        cmd: Command and arguments as list
        description: Human-readable description for error messages
        check: Whether to raise on non-zero exit code
        cwd: Optional working directory for command execution

    Returns:
        Tuple of (success: bool, output: str)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max
            check=check,
            cwd=cwd,
        )
        return True, result.stdout + result.stderr
    except subprocess.CalledProcessError as e:
        return False, f"{description} failed: {e.stderr}"
    except subprocess.TimeoutExpired:
        return False, f"{description} timed out after 5 minutes"
    except Exception as e:
        return False, f"{description} error: {e}"


def detect_package_manager() -> str | None:
    """
    Detect the best package manager for the current system.

    Returns:
        Package manager name: 'brew', 'apt', 'dnf', 'pacman', 'choco', or None
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        if check_command_exists("brew"):
            return "brew"
        return None

    elif system == "Linux":
        # Check in order of preference
        if check_command_exists("apt-get"):
            return "apt"
        elif check_command_exists("dnf"):
            return "dnf"
        elif check_command_exists("yum"):
            return "yum"
        elif check_command_exists("pacman"):
            return "pacman"
        elif check_command_exists("zypper"):
            return "zypper"
        return None

    elif system == "Windows":
        if check_command_exists("choco"):
            return "choco"
        elif check_command_exists("winget"):
            return "winget"
        return None

    return None


def install_nodejs(package_manager: str) -> tuple[bool, str]:
    """
    Install Node.js using the detected package manager.

    Returns:
        Tuple of (success: bool, message: str)
    """
    print("📦 Installing Node.js...")

    if package_manager == "brew":
        success, output = run_command(["brew", "install", "node"], "brew install node", check=False)

    elif package_manager == "apt":
        # Update package list first
        run_command(["sudo", "apt-get", "update", "-qq"], "apt update", check=False)
        success, output = run_command(
            ["sudo", "apt-get", "install", "-y", "nodejs", "npm"],
            "apt install",
            check=False,
        )

    elif package_manager in ["dnf", "yum"]:
        success, output = run_command(
            ["sudo", package_manager, "install", "-y", "nodejs", "npm"],
            f"{package_manager} install",
            check=False,
        )

    elif package_manager == "pacman":
        success, output = run_command(
            ["sudo", "pacman", "-S", "--noconfirm", "nodejs", "npm"],
            "pacman install",
            check=False,
        )

    elif package_manager == "zypper":
        success, output = run_command(
            ["sudo", "zypper", "install", "-y", "nodejs", "npm"],
            "zypper install",
            check=False,
        )

    elif package_manager == "choco":
        success, output = run_command(["choco", "install", "nodejs", "-y"], "choco install", check=False)

    elif package_manager == "winget":
        success, output = run_command(["winget", "install", "OpenJS.NodeJS"], "winget install", check=False)

    else:
        return False, f"Unsupported package manager: {package_manager}"

    if success:
        # Verify installation
        if check_command_exists("node") and check_command_exists("npm"):
            node_version = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
            return True, f"✅ Node.js installed successfully ({node_version})"
        else:
            return (
                False,
                "⚠️  Node.js installed but not found in PATH. Please restart your terminal.",
            )

    return False, f"❌ Failed to install Node.js:\n{output}"


def install_puppeteer(scripts_dir: Path | None = None) -> tuple[bool, str]:
    """
    Install Puppeteer locally in the scripts directory.

    Args:
        scripts_dir: Path to scripts directory (where package.json is located)

    Returns:
        Tuple of (success: bool, message: str)
    """
    print("📦 Installing Puppeteer (this will download ~170MB Chromium)...")

    # If scripts_dir not provided, try to find it
    if scripts_dir is None:
        try:
            from .svg_viewbox_repair import get_node_scripts_dir

            scripts_dir = get_node_scripts_dir().parent
        except Exception:
            scripts_dir = None

    if scripts_dir and scripts_dir.exists():
        # Install locally in scripts directory
        print(f"   Installing in: {scripts_dir}")
        success, output = run_command(
            ["npm", "install"],
            "npm install",
            check=False,
            cwd=str(scripts_dir),
        )

        if success:
            return True, "✅ Puppeteer installed successfully"
        else:
            return False, f"❌ Failed to install Puppeteer locally:\n{output}"

    # Fallback: try global install
    print("   Attempting global install...")
    success, output = run_command(["npm", "install", "-g", "puppeteer"], "npm install puppeteer", check=False)

    if success:
        return True, "✅ Puppeteer installed globally"

    # If global install fails, try with sudo
    if "permission denied" in output.lower() or "EACCES" in output:
        print("   ⚠️  Global install requires permissions, trying with sudo...")
        success, output = run_command(
            ["sudo", "npm", "install", "-g", "puppeteer"],
            "npm install puppeteer",
            check=False,
        )

        if success:
            return True, "✅ Puppeteer installed successfully with sudo"

    return False, f"❌ Failed to install Puppeteer:\n{output}"


def setup_dependencies(silent: bool = False) -> bool:
    """
    Automatically install all required dependencies.

    Args:
        silent: If True, suppress output

    Returns:
        True if all dependencies are available, False otherwise
    """
    if not silent:
        print("=" * 70)
        print("🔧 svg-repair-viewbox Automatic Dependency Setup")
        print("=" * 70)
        print()

    # Check if Node.js is already installed
    has_node = check_command_exists("node")
    has_npm = check_command_exists("npm")

    if not has_node or not has_npm:
        if not silent:
            print("📋 Node.js not found - will install automatically")
            print()

        # Detect package manager
        pkg_manager = detect_package_manager()

        if not pkg_manager:
            print("❌ Could not detect a supported package manager")
            print()
            print("Please install Node.js manually:")
            print()
            system = platform.system()
            if system == "Darwin":
                print("  macOS: brew install node")
            elif system == "Linux":
                print("  Ubuntu/Debian: sudo apt install nodejs npm")
                print("  Fedora/RHEL: sudo dnf install nodejs npm")
            elif system == "Windows":
                print("  Download from: https://nodejs.org")
            print()
            return False

        if not silent:
            print(f"🎯 Detected package manager: {pkg_manager}")
            print()

        # Install Node.js
        success, message = install_nodejs(pkg_manager)
        if not silent:
            print(message)
            print()

        if not success:
            return False

        # Update has_npm flag
        has_npm = check_command_exists("npm")

    else:
        if not silent:
            node_version = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
            print(f"✅ Node.js already installed ({node_version})")
            print()

    # Check if Puppeteer is installed locally in scripts directory
    has_puppeteer_local = False
    try:
        from .svg_viewbox_repair import get_node_scripts_dir

        scripts_dir = get_node_scripts_dir().parent
        node_modules = scripts_dir / "node_modules" / "puppeteer"
        has_puppeteer_local = node_modules.exists()
    except Exception:
        pass

    if not has_puppeteer_local:
        if not silent:
            print("📋 Puppeteer not found - will install automatically")
            print()

        success, message = install_puppeteer()
        if not silent:
            print(message)
            print()

        if not success:
            return False

    else:
        if not silent:
            print("✅ Puppeteer already installed")
            print()

    if not silent:
        print("=" * 70)
        print("✅ All dependencies installed successfully!")
        print("=" * 70)
        print()

    return True


def check_dependencies() -> tuple[bool, str]:
    """
    Check if all dependencies are available.

    Returns:
        Tuple of (ready: bool, message: str)
    """
    # Check Node.js
    if not check_command_exists("node"):
        return False, "Node.js not found"

    if not check_command_exists("npm"):
        return False, "npm not found"

    # Check Puppeteer - must be installed locally in scripts directory
    # Global installations don't work reliably for packaged tools
    try:
        from .svg_viewbox_repair import get_node_scripts_dir

        scripts_dir = get_node_scripts_dir().parent

        # Check if Puppeteer is installed locally in scripts directory
        node_modules = scripts_dir / "node_modules" / "puppeteer"
        if node_modules.exists():
            return True, "All dependencies available (Puppeteer installed locally)"
    except Exception:
        pass

    return False, "Puppeteer not found"


if __name__ == "__main__":
    # Can be run standalone for testing
    import argparse

    parser = argparse.ArgumentParser(description="Install dependencies for svg-repair-viewbox")
    parser.add_argument("--check", action="store_true", help="Only check if dependencies are installed")
    parser.add_argument("--silent", action="store_true", help="Silent mode (minimal output)")

    args = parser.parse_args()

    if args.check:
        ready, message = check_dependencies()
        print(message)
        sys.exit(0 if ready else 1)
    else:
        success = setup_dependencies(silent=args.silent)
        sys.exit(0 if success else 1)
