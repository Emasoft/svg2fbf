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


# Windows defaults stdout/stderr to cp1252 (or whatever the active code page
# is) which cannot encode the emoji used in our status messages — the
# resulting UnicodeEncodeError aborts the auto-installer mid-flight on real
# Windows boxes, before any install actually happens. Reconfigure to UTF-8
# at import time, matching what `python -X utf8` or `PYTHONIOENCODING=utf-8`
# would do, with errors='replace' so a broken codec elsewhere can't kill us.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            # reconfigure is missing on some embedded interpreters and on
            # streams that aren't TextIOWrapper. Falling through is safe —
            # callers will still see the underlying UnicodeEncodeError if
            # one fires, just no worse than today.
            pass


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


# ---------------------------------------------------------------------------
# Windows-specific helpers.
#
# Why a dedicated cluster: the auto-install lane on Windows hits four bugs
# that don't exist on Linux/macOS — npm being a `.cmd` batch wrapper that
# CreateProcess refuses to launch, the running process keeping a stale
# PATH after choco/winget mutate the registry, the 260-char MAX_PATH
# limit choking Puppeteer's nested node_modules, and the lack of a
# package manager when none of choco/winget/scoop are installed. Each
# helper below addresses exactly one of those.
# ---------------------------------------------------------------------------

# Pinned LTS — bumped manually rather than fetching the latest at runtime
# so the portable fallback is reproducible and survives nodejs.org outages
# (the URL format below is stable across LTS releases).
_PORTABLE_NODE_VERSION = "20.18.1"
_PORTABLE_NODE_URL_FMT = "https://nodejs.org/dist/v{ver}/node-v{ver}-win-{arch}.zip"


def _is_windows_admin() -> bool:
    """Return True iff this Python process is running with Administrator
    privileges on Windows. Always True on non-Windows (so admin-gated
    branches treat the platform as already privileged).

    Why: choco install needs an elevated shell, but winget and scoop
    install to user scope without admin. Picking the right manager up
    front gives clearer errors than blindly trying choco and watching
    UAC reject it.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def _refresh_path_from_registry_windows() -> None:
    """Re-read the system + user PATH from the Windows registry and merge
    into ``os.environ['PATH']``.

    Why: choco/winget/scoop write the new install dir to the registry's
    Path values, but the running Python process keeps the PATH it was
    launched with. Without this refresh, ``check_command_exists("node")``
    returns False right after a successful Node.js install — the file
    is on disk and visible to a NEW shell, but invisible to us. Calling
    this after every successful install_nodejs() resolves the surprise.
    """
    if sys.platform != "win32":
        return
    try:
        import winreg
    except ImportError:
        return
    parts: list[str] = []
    for hive, sub in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value:
                    parts.append(str(value))
        except OSError:
            continue
    if not parts:
        return
    merged = os.pathsep.join(parts)
    existing = os.environ.get("PATH", "")
    # Drop duplicates, preserving order. Registry entries come first so
    # the newly-installed binary wins over any old shadowed copy.
    seen: set[str] = set()
    new_path: list[str] = []
    for chunk in (merged, existing):
        for p in chunk.split(os.pathsep):
            if p and p not in seen:
                seen.add(p)
                new_path.append(p)
    os.environ["PATH"] = os.pathsep.join(new_path)


def _check_long_paths_enabled_windows() -> tuple[bool, str]:
    """Detect Windows long-path support (>260 chars) via the registry.

    Returns ``(enabled, hint)``: hint is the user-facing fix instruction
    when long paths are OFF, empty when ON. Off is the default on
    Windows 10 + 11 — Puppeteer's nested node_modules tree routinely
    exceeds 260 chars when installed under a long user profile path,
    and the resulting failure is opaque ("ENOENT, mkdir 'C:\\…'").
    """
    if sys.platform != "win32":
        return True, ""
    try:
        import winreg
    except ImportError:
        return True, ""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            if int(value) == 1:
                return True, ""
    except OSError:
        pass
    return False, (
        "⚠️  Windows long-path support is OFF (MAX_PATH=260). Puppeteer's\n"
        "    nested node_modules can exceed this and the install will fail\n"
        "    with an opaque ENOENT. Enable it once from an elevated shell:\n"
        "        reg add HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem \\\n"
        "            /v LongPathsEnabled /t REG_DWORD /d 1 /f\n"
        "    Then sign out and back in, or reboot."
    )


def _needs_shell_on_windows(cmd: list[str]) -> bool:
    """Return True iff ``cmd`` needs ``shell=True`` to launch on Windows.

    Why: ``subprocess.Popen([...])`` on Windows uses ``CreateProcess``,
    which refuses to launch ``.cmd``/``.bat`` batch wrappers directly —
    it raises ``FileNotFoundError`` even though the file is on PATH.
    npm is shipped as ``npm.cmd`` on Windows, so every Popen call to
    ``["npm", ...]`` fails opaquely without this guard. The fix is to
    route batch wrappers through ``cmd.exe`` via ``shell=True``.
    """
    if sys.platform != "win32" or not cmd:
        return False
    resolved = shutil.which(cmd[0])
    if resolved is None:
        return False
    return resolved.lower().endswith((".cmd", ".bat"))


def _install_portable_nodejs_windows(version: str = _PORTABLE_NODE_VERSION) -> tuple[bool, str]:
    """Last-resort fallback: download a portable Node.js zip from
    nodejs.org and extract it under ``%LOCALAPPDATA%\\svg2fbf\\runtime\\``.
    Used when choco/winget/scoop are all unavailable. Needs no admin
    rights — pure user-space install.

    On success, prepends the extracted bin dir to ``os.environ['PATH']``
    so the rest of setup_dependencies finds node + npm immediately.
    """
    if sys.platform != "win32":
        return False, "portable install only runs on Windows"

    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "x86"
    url = _PORTABLE_NODE_URL_FMT.format(ver=version, arch=arch)

    runtime_root = Path(os.environ.get("LOCALAPPDATA", os.environ.get("USERPROFILE", str(Path.home())))) / "svg2fbf" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    extract_root = runtime_root / "node"
    bin_dir = extract_root / f"node-v{version}-win-{arch}"

    # Re-use a previously-extracted runtime so repeated svg2fbf runs are
    # cheap (the zip is ~30 MB and a hot loop of installs is a real
    # workflow when iterating on FBF generation).
    if (bin_dir / "node.exe").exists():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        return True, f"✅ Portable Node.js {version} reused from {bin_dir}"

    import urllib.request
    import zipfile

    zip_path = runtime_root / f"node-v{version}-win-{arch}.zip"
    print(f"📥 Downloading portable Node.js {version} ({arch}) from nodejs.org...")
    try:
        urllib.request.urlretrieve(url, zip_path)
    except Exception as e:
        return False, f"failed to download {url}: {e}"

    print(f"📦 Extracting to {extract_root}...")
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_root)
    except zipfile.BadZipFile as e:
        zip_path.unlink(missing_ok=True)
        return False, f"downloaded zip is invalid: {e}"
    finally:
        zip_path.unlink(missing_ok=True)

    if not (bin_dir / "node.exe").exists():
        return False, f"portable extraction did not produce {bin_dir / 'node.exe'}"

    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    return True, f"✅ Portable Node.js {version} installed at {bin_dir}"


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
        # On Windows, batch wrappers (.cmd/.bat — used by npm, choco, etc.)
        # cannot be launched via CreateProcess directly; they have to be
        # routed through cmd.exe via shell=True. list2cmdline produces a
        # properly-quoted command string for the shell.
        if _needs_shell_on_windows(cmd):
            popen_arg: str | list[str] = subprocess.list2cmdline(cmd)
            kwargs["shell"] = True
        else:
            popen_arg = cmd
        proc = subprocess.Popen(popen_arg, **kwargs)
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
        # Order matters. choco needs admin elevation; winget and scoop
        # install to user scope without it. When the process is NOT
        # admin we prefer the no-admin paths to avoid an opaque UAC
        # rejection during install. When admin IS present, choco wins
        # because it has the broadest package coverage.
        has_choco = check_command_exists("choco")
        has_winget = check_command_exists("winget")
        has_scoop = check_command_exists("scoop")

        if _is_windows_admin():
            preferred = ("choco", "winget", "scoop")
        else:
            preferred = ("winget", "scoop", "choco")

        for name in preferred:
            if name == "choco" and has_choco:
                if not _is_windows_admin():
                    print(
                        "⚠️  Falling back to choco — note: choco needs an elevated\n    shell. If install fails with a UAC prompt rejection,\n    re-run from an Administrator PowerShell, or install\n    winget/scoop (which work without admin).",
                        file=sys.stderr,
                    )
                return "choco"
            if name == "winget" and has_winget:
                return "winget"
            if name == "scoop" and has_scoop:
                return "scoop"
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
        # --silent + --accept-source-agreements + --accept-package-agreements
        # make winget non-interactive (default behavior on a fresh runner is
        # to prompt for source acceptance the first time, which deadlocks
        # an automated install).
        success, output = run_command(
            [
                "winget",
                "install",
                "OpenJS.NodeJS",
                "--silent",
                "--accept-source-agreements",
                "--accept-package-agreements",
                "--disable-interactivity",
            ],
            "winget install",
            check=False,
        )

    elif package_manager == "scoop":
        # scoop installs to %USERPROFILE%\scoop\apps and PATH is updated
        # in the user-scoped registry; nodejs-lts is the canonical bucket
        # name. No admin needed.
        success, output = run_command(["scoop", "install", "nodejs-lts"], "scoop install", check=False)

    else:
        return False, f"Unsupported package manager: {package_manager}"

    # On Windows, choco/winget/scoop write the new install dir to the
    # registry but the running process keeps a stale PATH. Refresh from
    # the registry before the in-PATH check below — without this, the
    # check spuriously fails right after a successful install.
    _refresh_path_from_registry_windows()

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
            # On Windows, fall back to a portable Node.js download from
            # nodejs.org before giving up. This handles the surprisingly
            # common "fresh corporate Windows laptop with no choco/winget/
            # scoop" case — no admin needed, no extra tooling required.
            if platform.system() == "Windows":
                if not silent:
                    print("📋 No Windows package manager (choco/winget/scoop) found —")
                    print("    falling back to a portable Node.js download.")
                    print()
                portable_ok, portable_msg = _install_portable_nodejs_windows()
                if not silent:
                    print(portable_msg)
                    print()
                if portable_ok:
                    has_npm = check_command_exists("npm")
                    if not has_npm:
                        return False
                    pkg_manager = None  # signal: skip Node.js install_nodejs() below
                else:
                    return False
            else:
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
                print()
                return False

        if pkg_manager is not None:
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
        # else: portable Node.js path already populated PATH and the
        # subsequent has_npm check sees it.

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

        # Surface the Windows long-path warning before npm install kicks
        # off, so a user whose install fails with an opaque ENOENT can
        # immediately spot the cause and apply the fix instead of
        # debugging upstream npm logs.
        long_paths_ok, long_paths_hint = _check_long_paths_enabled_windows()
        if not long_paths_ok and not silent:
            print(long_paths_hint)
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
