#!/usr/bin/env python3
"""
Validate GitHub Action SHAs in workflow files.

This script checks that all pinned action SHAs in .github/workflows/*.yml
actually exist in their respective repositories.

Usage:
    python scripts/validate_action_shas.py           # Validate all workflows
    python scripts/validate_action_shas.py --fix    # Validate and offer to fix invalid SHAs

Exit codes:
    0 - All SHAs are valid
    1 - Invalid SHAs found
    2 - Error (network, parsing, etc.)
"""

import re
import subprocess
import sys
from pathlib import Path


def get_workflow_files() -> list[Path]:
    """Find all workflow YAML files."""
    workflows_dir = Path(".github/workflows")
    if not workflows_dir.exists():
        print("ERROR: .github/workflows directory not found")
        sys.exit(2)
    return list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))


def extract_actions_with_shas(workflow_path: Path) -> list[dict]:
    """Extract all actions with pinned SHAs from a workflow file."""
    content = workflow_path.read_text()
    # Match: uses: owner/repo@sha  # optional comment
    # SHA must be 40 hex chars (full SHA) or at least 7 chars (short SHA)
    pattern = r"uses:\s*([^@\s]+)@([a-f0-9]{7,40})(?:\s*#\s*(.*))?"

    actions = []
    for line_num, line in enumerate(content.split("\n"), 1):
        match = re.search(pattern, line)
        if match:
            repo = match.group(1)
            sha = match.group(2)
            comment = match.group(3) or ""
            actions.append({"file": workflow_path, "line": line_num, "repo": repo, "sha": sha, "comment": comment.strip(), "full_line": line.strip()})
    return actions


def validate_sha_exists(repo: str, sha: str) -> tuple[bool, str]:
    """Check if a SHA exists in a GitHub repository."""
    # Use gh api to check if the commit exists
    result = subprocess.run(["gh", "api", f"repos/{repo}/git/commits/{sha}", "--silent"], capture_output=True, text=True)

    if result.returncode == 0:
        return True, "valid"
    elif "Not Found" in result.stderr or result.returncode == 1:
        return False, "SHA does not exist in repository"
    else:
        return False, f"API error: {result.stderr.strip()}"


def get_latest_sha(repo: str, ref: str = "main") -> str | None:
    """Get the latest SHA for a branch/tag in a repository."""
    # Try main first, then master
    for branch in [ref, "main", "master"]:
        result = subprocess.run(["gh", "api", f"repos/{repo}/git/refs/heads/{branch}", "--jq", ".object.sha"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    # Try as a tag
    result = subprocess.run(["gh", "api", f"repos/{repo}/git/refs/tags/{ref}", "--jq", ".object.sha"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    return None


def main():
    fix_mode = "--fix" in sys.argv

    print("=" * 60)
    print("GitHub Actions SHA Validator")
    print("=" * 60)

    workflow_files = get_workflow_files()
    print(f"\nFound {len(workflow_files)} workflow files\n")

    all_actions = []
    for wf in workflow_files:
        actions = extract_actions_with_shas(wf)
        all_actions.extend(actions)

    if not all_actions:
        print("No pinned actions found (actions using @sha format)")
        return 0

    print(f"Found {len(all_actions)} pinned actions to validate\n")

    invalid_actions = []
    valid_count = 0

    for action in all_actions:
        repo = action["repo"]
        sha = action["sha"]

        print(f"Checking {repo}@{sha[:12]}... ", end="", flush=True)

        is_valid, message = validate_sha_exists(repo, sha)

        if is_valid:
            print("✅ valid")
            valid_count += 1
        else:
            print(f"❌ INVALID - {message}")
            invalid_actions.append(action)

    print("\n" + "=" * 60)
    print(f"Results: {valid_count} valid, {len(invalid_actions)} invalid")
    print("=" * 60)

    if invalid_actions:
        print("\n❌ INVALID ACTIONS FOUND:\n")
        for action in invalid_actions:
            print(f"  File: {action['file']}:{action['line']}")
            print(f"  Repo: {action['repo']}")
            print(f"  SHA:  {action['sha']}")
            print(f"  Line: {action['full_line']}")

            if fix_mode:
                # Try to get correct SHA
                latest_sha = get_latest_sha(action["repo"])
                if latest_sha:
                    print(f"  Fix:  Use {latest_sha} (latest main)")
                else:
                    print("  Fix:  Could not determine correct SHA")
            print()

        if not fix_mode:
            print("Run with --fix to see suggested corrections")

        return 1

    print("\n✅ All pinned action SHAs are valid!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
