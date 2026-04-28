#!/usr/bin/env python3
"""
Automatic dependency installer for svg-repair-viewbox.

Detects the system and automatically installs Node.js and Puppeteer
using the appropriate package manager.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(command) is not None


def _sudo_prefix() -> list[str]:
    """Return ['sudo'] if escalation is needed, else [] when already root.

    Why: Linux/macOS package managers normally require root, so the helper
    used to hard-code 'sudo'. But when svg2fbf runs inside a Docker
    container (or any environment that already runs as root), sudo is
    typically not installed and the install fails with "No such file or
    directory: 'sudo'" — the exact bug end users hit on container hosts.

    Use os.geteuid() to detect root. On Windows os.geteuid is not
    available, so we just return [] (the choco/winget paths don't need
    elevation here anyway — Windows handles UAC separately).
    """
    if not hasattr(os, "geteuid"):
        return []
    return [] if os.geteuid() == 0 else ["sudo"]


def run_command(
    cmd: list[str],
    description: str,
    check: bool = True,
    cwd: str | None = None,
    timeout: int = 1800,
) -> tuple[bool, str]:
    """
    Run a shell command and return success status and output.

    Args:
        cmd: Command and arguments as list
        description: Human-readable description for error messages
        check: Whether to raise on non-zero exit code
        cwd: Optional working directory for command execution
        timeout: Per-command timeout in seconds. Defaults to 30 minutes
            because `npm install puppeteer` downloads ~170 MB of Chromium
            and unpacks it; the previous 5-minute cap routinely failed on
            slow networks (cellular tethering, corporate proxies, regions
            far from CDN edges) and reported the install as broken even
            though it would have succeeded.

    Returns:
        Tuple of (success: bool, output: str)
    """
    # Use Popen + start_new_session=True so the command lives in its own
    # process group. On TimeoutExpired we send SIGTERM (then SIGKILL after
    # a short grace period) to the WHOLE process group instead of just the
    # immediate child — `npm install` spawns a tree of node/gyp/curl
    # subprocesses and orphaning them on timeout was the qwen-flagged
    # source of background CPU/network usage long after the CLI exited.
    proc: subprocess.Popen[str] | None = None
    try:
        kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": cwd,
        }
        if hasattr(os, "setsid"):
            # POSIX: create a fresh session+pgid so killpg targets the tree.
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_group(proc)
            return False, f"{description} timed out after {timeout} seconds"
        rc = proc.returncode
        # Why: when check=False, a non-zero exit still has to surface as a
        # failure or a failing `npm install` / `apt install` would silently
        # return success, causing install_puppeteer / install_nodejs to
        # report "✅ installed successfully" on actual failures.
        if rc != 0:
            if check:
                return False, f"{description} failed (exit {rc}): {stdout}{stderr}"
            return False, f"{description} failed: {stdout}{stderr}"
        return True, stdout + stderr
    except FileNotFoundError as e:
        return False, f"{description} error: command not found: {e.filename}"
    except Exception as e:
        if proc is not None and proc.poll() is None:
            _terminate_process_group(proc)
        return False, f"{description} error: {e}"


def _terminate_process_group(proc: "subprocess.Popen[str]") -> None:
    """Best-effort termination of a Popen and its child process tree.

    On POSIX we send SIGTERM to the leader's process group, wait briefly,
    then escalate to SIGKILL. On Windows fall back to ``proc.kill()`` since
    ``os.killpg`` is not available there.
    """
    import signal
    import time

    try:
        if hasattr(os, "killpg") and proc.pid:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            for _ in range(20):  # up to ~2 s grace
                if proc.poll() is not None:
                    return
                time.sleep(0.1)
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        else:
            proc.kill()
    finally:
        # Always reap so the zombie is collected.
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


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
        run_command([*_sudo_prefix(), "apt-get", "update", "-qq"], "apt update", check=False)
        success, output = run_command(
            [*_sudo_prefix(), "apt-get", "install", "-y", "nodejs", "npm"],
            "apt install",
            check=False,
        )

    elif package_manager in ["dnf", "yum"]:
        success, output = run_command(
            [*_sudo_prefix(), package_manager, "install", "-y", "nodejs", "npm"],
            f"{package_manager} install",
            check=False,
        )

    elif package_manager == "pacman":
        success, output = run_command(
            [*_sudo_prefix(), "pacman", "-S", "--noconfirm", "nodejs", "npm"],
            "pacman install",
            check=False,
        )

    elif package_manager == "zypper":
        success, output = run_command(
            [*_sudo_prefix(), "zypper", "install", "-y", "nodejs", "npm"],
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
    # Why: auto_install_deps.py ships as a TOP-LEVEL module (per pyproject.toml
    # force-include), so the `from .svg_viewbox_repair` relative import used
    # before always failed silently — leaving scripts_dir=None and forcing
    # global install (which then check_dependencies() couldn't detect).
    # Wheel layout: svg_viewbox_repair/main.py contains the helper.
    if scripts_dir is None:
        scripts_dir = _find_scripts_dir()

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

    # Fallback: try global install (without sudo for security — npm scripts should not run as root)
    print("   Attempting global install...")
    success, output = run_command(["npm", "install", "-g", "puppeteer"], "npm install puppeteer", check=False)

    if success:
        return True, "✅ Puppeteer installed globally"

    return False, f"❌ Failed to install Puppeteer:\n{output}\n\nTip: If permission denied, use 'npm config set prefix ~/.npm-global' to avoid needing sudo."


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
    scripts_dir = _find_scripts_dir()
    if scripts_dir is not None:
        node_modules = scripts_dir / "node_modules" / "puppeteer"
        has_puppeteer_local = node_modules.exists()

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

    # Check Puppeteer - prefer local install, fall back to global detection.
    # Local install in the bundled scripts dir is preferred because the
    # node_scripts call `require('puppeteer')` from that working dir.
    scripts_dir = _find_scripts_dir()
    if scripts_dir is not None:
        node_modules = scripts_dir / "node_modules" / "puppeteer"
        if node_modules.exists():
            return True, "All dependencies available (Puppeteer installed locally)"

    # Fall back to global puppeteer (the install_puppeteer fallback path).
    # Without this check, a successful global install would still report
    # "Puppeteer not found" — exactly the user-reported issue #15.
    if _is_puppeteer_globally_installed():
        return True, "All dependencies available (Puppeteer installed globally)"

    return False, "Puppeteer not found"


def _find_scripts_dir() -> Path | None:
    """
    Locate the bundled node_scripts directory.

    Tries the wheel-installed location (svg_viewbox_repair.main) first,
    then falls back to a development-mode lookup. Returns the PARENT of
    node_scripts (i.e. the directory that contains node_scripts/ AND
    package.json) so callers can run `npm install` there.
    """
    # Wheel-installed mode: svg_viewbox_repair is a package, helper lives
    # in its `main` submodule (force-included from src/svg_viewbox_repair.py).
    try:
        from svg_viewbox_repair.main import get_node_scripts_dir  # type: ignore[import-not-found]

        return get_node_scripts_dir().parent
    except Exception:
        pass

    # Dev mode (running from src/): the file is a top-level module.
    try:
        import importlib

        mod = importlib.import_module("svg_viewbox_repair")
        if hasattr(mod, "get_node_scripts_dir"):
            return mod.get_node_scripts_dir().parent  # type: ignore[no-any-return]
    except Exception:
        pass

    return None


def _is_puppeteer_globally_installed() -> bool:
    """Detect a global puppeteer install via `npm root -g`."""
    if not check_command_exists("npm"):
        return False
    try:
        result = subprocess.run(
            ["npm", "root", "-g"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return False
        global_root = Path(result.stdout.strip())
        return (global_root / "puppeteer").exists()
    except Exception:
        return False


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
