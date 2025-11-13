#!/usr/bin/env python3
"""
Monitor tests/ directory for .venv creation and issue warnings.

This script uses watchdog to monitor the tests/ directory for any .venv
directory creation and immediately alerts the user.

Usage:
    uv run python tests/monitor_venv.py
"""

import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class VenvWatcher(FileSystemEventHandler):
    """Monitor for .venv directory creation."""

    def __init__(self, watch_path: Path):
        self.watch_path = watch_path
        self.venv_path = watch_path / ".venv"

    def on_created(self, event):
        """Handle creation events."""
        if event.is_directory:
            created_path = Path(event.src_path)
            if created_path.name == ".venv" and created_path.parent == self.watch_path:
                self.alert_venv_creation(created_path)

    def on_moved(self, event):
        """Handle move/rename events."""
        if event.is_directory:
            dest_path = Path(event.dest_path)
            if dest_path.name == ".venv" and dest_path.parent == self.watch_path:
                self.alert_venv_creation(dest_path)

    def alert_venv_creation(self, venv_path: Path):
        """Issue alert when .venv is detected."""
        print("\n" + "=" * 80)
        print("⚠️  CRITICAL WARNING: .venv DETECTED IN tests/ DIRECTORY!")
        print("=" * 80)
        print(f"\n📂 Location: {venv_path}")
        print(f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("\n🔴 This is INCORRECT! The project should have only ONE venv at project root:")
        print("   svg2fbf/.venv/  ← THE ONLY VENV")
        print("\n❌ NEVER create: svg2fbf/tests/.venv/")
        print("\n📋 Action Required:")
        print(f"   rm -rf {venv_path}")
        print("\n💡 Common Causes:")
        print("   • Running 'uv venv' from tests/ directory")
        print("   • IDE auto-creating venv")
        print("   • Script calling installer from tests/")
        print("\n📖 See: tests/README_VENV.md for details")
        print("=" * 80 + "\n")
        sys.stdout.flush()


def main():
    """Run the venv monitor."""
    tests_dir = Path(__file__).parent.resolve()
    venv_path = tests_dir / ".venv"

    print("🔍 Venv Monitor Started")
    print(f"📂 Watching: {tests_dir}")
    print(f"🎯 Target: {venv_path}")
    print("⏳ Monitoring for .venv creation... (Press Ctrl+C to stop)\n")

    # Check if .venv already exists
    if venv_path.exists():
        print("⚠️  WARNING: .venv ALREADY EXISTS!")
        print(f"📂 Location: {venv_path}")
        print("❌ This should be deleted immediately:")
        print(f"   rm -rf {venv_path}\n")

    # Set up file system monitoring
    event_handler = VenvWatcher(tests_dir)
    observer = Observer()
    observer.schedule(event_handler, str(tests_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
