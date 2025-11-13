"""
Utility to add batch navigation to HTML reports

This module provides functionality to add circular navigation links
between multiple HTML test reports generated in a batch.
"""

import re
from pathlib import Path


def add_navigation_to_reports(report_paths: list[Path]) -> None:
    """
    Add navigation links to a batch of HTML reports

    Args:
        report_paths: List of paths to HTML report files

    The navigation includes:
    - First button: Always goes to first report (grayed out if already at first)
    - Previous button: Goes to previous report (grayed out if at first)
    - Next button: Goes to next report (grayed out if at last)
    - Last button: Always goes to last report (grayed out if already at last)

    All buttons are fixed at the top-right of the page.
    """
    if not report_paths or len(report_paths) == 0:
        return

    total_reports = len(report_paths)

    for idx, report_path in enumerate(report_paths):
        if not report_path.exists():
            print(f"  ⚠️  Report not found: {report_path}")
            continue

        # Read current HTML content
        with open(report_path, encoding="utf-8") as f:
            html_content = f.read()

        # Build navigation HTML with circular navigation
        nav_html = _build_navigation_html(idx=idx, total=total_reports, report_paths=report_paths)

        # Replace the navigation placeholder with actual navigation
        # Look for <div id='batch-navigation'></div> and replace it
        updated_html = re.sub(
            r"<div id='batch-navigation'></div>",
            f"<div id='batch-navigation'>{nav_html}</div>",
            html_content,
        )

        # Write updated HTML
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(updated_html)

        print(f"  ✓ Added navigation to: {report_path}")


def _build_navigation_html(idx: int, total: int, report_paths: list[Path]) -> str:
    """
    Build navigation HTML for a single report

    Args:
        idx: Index of current report (0-based)
        total: Total number of reports
        report_paths: List of all report paths

    Returns:
        HTML string for navigation
    """
    first_report = report_paths[0]
    last_report = report_paths[-1]

    # Convert to absolute file:// URLs
    def to_file_url(path: Path) -> str:
        return f"file://{path.absolute()}"

    parts = [
        f"<div class='nav-title'>Test Run {idx + 1}/{total}</div>",
        "<div class='nav-buttons'>",
    ]

    # First button - always goes to first page, disabled if already at first
    if idx == 0:
        parts.append("<span class='nav-disabled' title='Already at first'>⏮ First</span>")
    else:
        parts.append(f"<a href='{to_file_url(first_report)}'>⏮ First</a>")

    # Previous button - circular (goes to last if at first)
    if idx > 0:
        prev_report = report_paths[idx - 1]
        parts.append(f"<a href='{to_file_url(prev_report)}'>← Prev</a>")
    else:
        # At first page, wrap to last page (circular)
        parts.append(f"<a href='{to_file_url(last_report)}' title='Go to last (circular)'>← Prev</a>")

    # Next button - circular (goes to first if at last)
    if idx < total - 1:
        next_report = report_paths[idx + 1]
        parts.append(f"<a href='{to_file_url(next_report)}'>Next →</a>")
    else:
        # At last page, wrap to first page (circular)
        parts.append(f"<a href='{to_file_url(first_report)}' title='Go to first (circular)'>Next →</a>")

    # Last button - always goes to last page, disabled if already at last
    if idx == total - 1:
        parts.append("<span class='nav-disabled' title='Already at last'>Last ⏭</span>")
    else:
        parts.append(f"<a href='{to_file_url(last_report)}'>Last ⏭</a>")

    parts.append("</div>")  # Close nav-buttons

    return "\n".join(parts)


if __name__ == "__main__":
    # Command-line interface for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python add_batch_navigation.py <report1.html> <report2.html> ...")
        sys.exit(1)

    report_paths = [Path(p) for p in sys.argv[1:]]
    add_navigation_to_reports(report_paths)
    print(f"\n✅ Added navigation to {len(report_paths)} reports")
