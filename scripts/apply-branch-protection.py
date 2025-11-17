#!/usr/bin/env python3
"""
Apply GitHub branch protection rules from .github_protection.yml

This script:
1. Auto-detects the current repository (owner/name)
2. Reads branch protection rules from .github_protection.yml
3. Applies rules via GitHub CLI (gh api)
4. Reports what was configured

Usage:
    python scripts/apply-branch-protection.py
    python scripts/apply-branch-protection.py --config custom.yml
    python scripts/apply-branch-protection.py --dry-run

Requirements:
    - gh CLI installed and authenticated
    - .github_protection.yml file in repo root (or specify --config)
    - Write access to the repository
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:
    print("❌ Error: PyYAML not installed")
    print("Install with: pip install pyyaml")
    sys.exit(1)


class BranchProtectionManager:
    """Manages GitHub branch protection rules via gh CLI."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.repo_info = self._get_repo_info()

    def _get_repo_info(self) -> Dict[str, str]:
        """Get current repository information via gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner,name,owner"],
                capture_output=True,
                text=True,
                check=True,
            )
            info = json.loads(result.stdout)
            return {
                "full_name": info["nameWithOwner"],
                "name": info["name"],
                "owner": info["owner"]["login"],
            }
        except subprocess.CalledProcessError as e:
            print("❌ Error: Failed to get repository info via gh CLI")
            print(f"   {e.stderr}")
            print("\nMake sure:")
            print("  1. gh CLI is installed (https://cli.github.com)")
            print("  2. You're authenticated (gh auth login)")
            print("  3. You're in a git repository")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Failed to parse gh output: {e}")
            sys.exit(1)

    def load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load branch protection configuration from YAML file."""
        if not config_path.exists():
            print(f"❌ Error: Config file not found: {config_path}")
            print("\nCreate it with:")
            print("  cp templates/.github_protection.yml .github_protection.yml")
            sys.exit(1)

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            return config
        except yaml.YAMLError as e:
            print(f"❌ Error: Invalid YAML in {config_path}")
            print(f"   {e}")
            sys.exit(1)

    def apply_branch_protection(self, branch: str, rules: Dict[str, Any]) -> bool:
        """Apply protection rules to a branch via gh API."""
        if not rules.get("enabled", False):
            print(f"⏭️  Skipping {branch} (disabled in config)")
            return True

        print(f"📌 Protecting {branch}...")

        # Build protection payload
        payload = self._build_protection_payload(rules)

        if self.dry_run:
            print("   [DRY RUN] Would apply:")
            print(f"   {json.dumps(payload, indent=2)}")
            return True

        # Apply via gh API
        try:
            cmd = [
                "gh",
                "api",
                f"repos/{self.repo_info['full_name']}/branches/{branch}/protection",
                "--method",
                "PUT",
            ]

            # Add payload fields
            for key, value in payload.items():
                if value is None:
                    cmd.extend(["--field", f"{key}=null"])
                elif isinstance(value, bool):
                    cmd.extend(["--field", f"{key}={str(value).lower()}"])
                elif isinstance(value, dict):
                    # Nested objects need special handling
                    for subkey, subvalue in value.items():
                        if isinstance(subvalue, list):
                            if len(subvalue) == 0:
                                cmd.extend(["--field", f"{key}[{subkey}][]="])
                            else:
                                for item in subvalue:
                                    cmd.extend(["--field", f"{key}[{subkey}][]={item}"])
                        elif isinstance(subvalue, bool):
                            cmd.extend(["--field", f"{key}[{subkey}]={str(subvalue).lower()}"])
                        elif isinstance(subvalue, int):
                            cmd.extend(["--field", f"{key}[{subkey}]={subvalue}"])
                        else:
                            cmd.extend(["--field", f"{key}[{subkey}]={subvalue}"])
                else:
                    cmd.extend(["--field", f"{key}={value}"])

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"   ✅ Protected {branch}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"   ❌ Failed to protect {branch}")
            print(f"      {e.stderr}")
            return False

    def _build_protection_payload(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Build API payload from config rules."""
        payload = {}

        # Enforce admins
        if "enforce_admins" in rules:
            payload["enforce_admins"] = rules["enforce_admins"]

        # Required pull request reviews
        if "required_pull_request_reviews" in rules:
            if rules["required_pull_request_reviews"] is None:
                payload["required_pull_request_reviews"] = None
            else:
                payload["required_pull_request_reviews"] = rules["required_pull_request_reviews"]

        # Required status checks
        if "required_status_checks" in rules:
            if rules["required_status_checks"] is None:
                payload["required_status_checks"] = None
            else:
                payload["required_status_checks"] = rules["required_status_checks"]

        # Allow force pushes
        if "allow_force_pushes" in rules:
            payload["allow_force_pushes"] = rules["allow_force_pushes"]

        # Allow deletions
        if "allow_deletions" in rules:
            payload["allow_deletions"] = rules["allow_deletions"]

        # Required conversation resolution
        if "required_conversation_resolution" in rules:
            payload["required_conversation_resolution"] = rules["required_conversation_resolution"]

        # Restrictions (who can push)
        if "restrictions" in rules:
            payload["restrictions"] = rules["restrictions"]

        # Block creations (optional)
        if "block_creations" in rules:
            payload["block_creations"] = rules["block_creations"]

        return payload

    def create_codeowners(self, codeowners_config: Dict[str, Any]) -> bool:
        """Create .github/CODEOWNERS file if enabled."""
        if not codeowners_config.get("enabled", False):
            return True

        codeowners_path = Path(".github/CODEOWNERS")
        codeowners_path.parent.mkdir(exist_ok=True)

        content = "# CODEOWNERS - Auto-generated from .github_protection.yml\n"
        content += "# See: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners\n\n"

        for item in codeowners_config.get("patterns", []):
            pattern = item.get("pattern", "*")
            owners = item.get("owners", [])
            if owners:
                content += f"{pattern} {' '.join(owners)}\n"

        if self.dry_run:
            print("[DRY RUN] Would create .github/CODEOWNERS:")
            print(content)
            return True

        with open(codeowners_path, "w") as f:
            f.write(content)

        print("✅ Created .github/CODEOWNERS")
        return True

    def verify_protection(self) -> None:
        """Verify which branches are protected."""
        print("\n🔍 Verifying protected branches...")
        try:
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{self.repo_info['full_name']}/branches",
                    "--jq",
                    ".[] | select(.protected == true) | .name",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            protected = result.stdout.strip().split("\n")
            if protected and protected[0]:
                for branch in protected:
                    print(f"  ✓ {branch}")
            else:
                print("  (no protected branches)")
        except subprocess.CalledProcessError as e:
            print(f"  ❌ Failed to verify: {e.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Apply GitHub branch protection from .github_protection.yml")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".github_protection.yml"),
        help="Path to config file (default: .github_protection.yml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without applying changes",
    )
    args = parser.parse_args()

    # Initialize manager
    manager = BranchProtectionManager(dry_run=args.dry_run)

    print("🔒 GitHub Branch Protection Manager")
    print(f"   Repository: {manager.repo_info['full_name']}")
    print(f"   Config: {args.config}")
    if args.dry_run:
        print("   Mode: DRY RUN (no changes will be made)")
    print()

    # Load configuration
    config = manager.load_config(args.config)

    # Apply branch protection rules
    branches = config.get("branches", {})
    if not branches:
        print("⚠️  No branch protection rules found in config")
        sys.exit(0)

    success_count = 0
    for branch, rules in branches.items():
        if manager.apply_branch_protection(branch, rules):
            success_count += 1

    # Create CODEOWNERS if enabled
    if "codeowners" in config:
        manager.create_codeowners(config["codeowners"])

    # Verify results
    if not args.dry_run:
        manager.verify_protection()

    # Summary
    print()
    if args.dry_run:
        print(f"✅ Dry run complete ({success_count}/{len(branches)} branches would be protected)")
    else:
        print(f"✅ Applied protection to {success_count}/{len(branches)} branches")


if __name__ == "__main__":
    main()
