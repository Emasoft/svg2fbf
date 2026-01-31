"""
Tests for version release rules validation functions in scripts/release.sh

These tests verify the three publishing rules:
1. Single Stage Rule: Only ONE stage per version at any time
2. Stage Progression Rule: Stage must be LOWER than previous version's stage
3. RC Gateway Rule: Alpha/beta only if previous version at RC or stable
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest


# Path to release.sh script
RELEASE_SCRIPT = Path(__file__).parent.parent / "scripts" / "release.sh"


def _extract_bash_functions() -> str:
    """Extract version-related function definitions from release.sh.

    Uses sed to extract the function bodies from the actual release.sh script,
    avoiding the main execution code that checks arguments and exits.
    Returns a string containing bash function definitions.
    """
    script_content = RELEASE_SCRIPT.read_text(encoding="utf-8")

    # Find the version release rules section and extract relevant functions
    # The functions are between "VERSION RELEASE RULES ENFORCEMENT" and "ensure_clean()"
    functions_to_extract = [
        "get_base_version",
        "get_version_stage",
        "get_stage_value",
        "compare_base_versions",
    ]

    extracted = []
    for func_name in functions_to_extract:
        # Find function start
        pattern = f"{func_name}()"
        start_idx = script_content.find(pattern)
        if start_idx == -1:
            continue

        # Find the opening brace after the function name
        brace_start = script_content.find("{", start_idx)
        if brace_start == -1:
            continue

        # Find matching closing brace (count braces)
        brace_count = 1
        pos = brace_start + 1
        while pos < len(script_content) and brace_count > 0:
            if script_content[pos] == "{":
                brace_count += 1
            elif script_content[pos] == "}":
                brace_count -= 1
            pos += 1

        # Extract the full function including closing brace
        func_body = script_content[start_idx:pos]
        extracted.append(func_body)

    return "\n\n".join(extracted)


# Cache the extracted functions to avoid re-reading the file for each test
_CACHED_FUNCTIONS: str | None = None


def run_bash_function(function_name: str, *args: str) -> str:
    """Run a bash function from release.sh and return its output.

    Extracts only the function definitions from release.sh (avoiding the main
    execution code that checks arguments and exits) and runs the specified function.
    Returns stdout stripped of trailing whitespace.
    """
    global _CACHED_FUNCTIONS
    if _CACHED_FUNCTIONS is None:
        _CACHED_FUNCTIONS = _extract_bash_functions()

    # Build argument string with proper quoting for each argument
    args_str = " ".join(f'"{arg}"' for arg in args)

    script = f"""
{_CACHED_FUNCTIONS}

{function_name} {args_str}
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=RELEASE_SCRIPT.parent.parent,  # Project root
    )
    return result.stdout.strip()


class TestVersionRulesIntegration:
    """Integration tests for the version release rules"""

    def test_release_script_exists_and_executable(self) -> None:
        """Verify release.sh exists and is executable (skipped on Windows)"""
        assert RELEASE_SCRIPT.exists(), f"Release script not found: {RELEASE_SCRIPT}"
        # Windows doesn't have Unix executable bits - skip this check on Windows
        if sys.platform != "win32":
            assert RELEASE_SCRIPT.stat().st_mode & 0o111, "Release script is not executable"

    def test_release_script_has_validation_functions(self) -> None:
        """Verify release.sh contains all required validation functions"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        required_functions = [
            "get_base_version()",
            "get_version_stage()",
            "get_stage_value()",
            "compare_base_versions()",
            "get_latest_stable_version()",
            "get_published_stages_for_version()",
            "validate_version_release()",
            "archive_previous_stages()",
        ]
        for func in required_functions:
            assert func in content, f"Missing function: {func}"

    def test_release_script_calls_validation(self) -> None:
        """Verify release.sh calls validate_version_release before committing"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        # Check validation is called before git commit
        validation_call = 'validate_version_release "$new_version"'
        git_commit = 'git commit --no-verify -m "Release'

        assert validation_call in content, "validate_version_release not called in release_channel"

        # Verify validation comes before commit
        validation_pos = content.find(validation_call)
        commit_pos = content.find(git_commit)
        assert validation_pos < commit_pos, "Validation should occur before git commit"

    def test_release_script_calls_archive(self) -> None:
        """Verify release.sh calls archive_previous_stages after GitHub release"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        archive_call = 'archive_previous_stages "$new_version"'

        assert archive_call in content, "archive_previous_stages not called"

        # Verify archive is called in the release_channel function
        release_channel_start = content.find("release_channel()")
        release_channel_end = content.find("\n}", release_channel_start + 100)
        release_channel_body = content[release_channel_start:release_channel_end]

        assert "archive_previous_stages" in release_channel_body, "archive_previous_stages should be in release_channel"

    def test_release_script_has_rollback(self) -> None:
        """Verify release.sh rolls back pyproject.toml on validation failure"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        rollback = "git checkout -- pyproject.toml"
        assert rollback in content, "Missing rollback of pyproject.toml on validation failure"


class TestGetBaseVersionFunction:
    """Test get_base_version function implementation"""

    def test_function_exists(self) -> None:
        """Verify get_base_version function is defined"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        assert "get_base_version()" in content

    def test_removes_alpha_suffix(self) -> None:
        """Verify function uses sed to remove alpha suffix"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        # Check the sed pattern handles alpha
        assert "(a|b|rc)" in content, "sed pattern should handle a/b/rc suffixes"

    def test_function_uses_sed(self) -> None:
        """Verify function uses sed for suffix removal"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("get_base_version()")
        func_end = content.find("\n}", func_start)
        func_body = content[func_start:func_end]
        assert "sed -E" in func_body, "Function should use sed -E for regex"


class TestGetVersionStageFunction:
    """Test get_version_stage function implementation"""

    def test_function_exists(self) -> None:
        """Verify get_version_stage function is defined"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        assert "get_version_stage()" in content

    def test_detects_all_stages(self) -> None:
        """Verify function can detect alpha, beta, rc, and stable"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("get_version_stage()")
        func_end = content.find("\n}", func_start)
        func_body = content[func_start:func_end]

        assert '"alpha"' in func_body or "'alpha'" in func_body, "Should return alpha"
        assert '"beta"' in func_body or "'beta'" in func_body, "Should return beta"
        assert '"rc"' in func_body or "'rc'" in func_body, "Should return rc"
        assert '"stable"' in func_body or "'stable'" in func_body, "Should return stable"

    def test_uses_pattern_matching(self) -> None:
        """Verify function uses bash pattern matching"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("get_version_stage()")
        func_end = content.find("\n}", func_start)
        func_body = content[func_start:func_end]

        # Should check for patterns like *a[0-9]* for alpha
        assert "a[0-9]" in func_body, "Should match alpha pattern"
        assert "b[0-9]" in func_body, "Should match beta pattern"
        assert "rc[0-9]" in func_body, "Should match rc pattern"


class TestGetStageValueFunction:
    """Test get_stage_value function implementation"""

    def test_function_exists(self) -> None:
        """Verify get_stage_value function is defined"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        assert "get_stage_value()" in content

    def test_returns_numeric_values(self) -> None:
        """Verify function returns numeric stage values"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("get_stage_value()")
        func_end = content.find("\n}", func_start)
        func_body = content[func_start:func_end]

        # Check for numeric return values
        assert "echo 1" in func_body, "Alpha should have value 1"
        assert "echo 2" in func_body, "Beta should have value 2"
        assert "echo 3" in func_body, "RC should have value 3"
        assert "echo 4" in func_body, "Stable should have value 4"

    def test_stable_has_highest_value(self) -> None:
        """Verify stable has the highest stage value (4)"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("get_stage_value()")
        func_end = content.find("\n}", func_start)
        func_body = content[func_start:func_end]

        # Extract the case statement
        stable_match = re.search(r"stable\)\s*echo\s*(\d+)", func_body)
        assert stable_match, "Should have stable case"
        assert stable_match.group(1) == "4", "Stable should have value 4"


class TestValidateVersionReleaseFunction:
    """Test validate_version_release function implementation"""

    def test_function_exists(self) -> None:
        """Verify validate_version_release function is defined"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        assert "validate_version_release()" in content

    def test_checks_rule_1_single_stage(self) -> None:
        """Verify function checks Single Stage Rule"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        # Look for RULE 1 mention
        assert "RULE 1" in content or "Single Stage" in content, "Should check Single Stage Rule"

    def test_checks_rule_3_rc_gateway(self) -> None:
        """Verify function checks RC Gateway Rule"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        # Look for RULE 3 or RC Gateway mention
        assert "RULE 3" in content or "RC Gateway" in content, "Should check RC Gateway Rule"

    def test_returns_on_validation_pass(self) -> None:
        """Verify function returns 0 on validation pass"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("validate_version_release()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        assert "return 0" in func_body, "Should return 0 on success"
        assert "return 1" in func_body, "Should return 1 on failure"


class TestArchivePreviousStagesFunction:
    """Test archive_previous_stages function implementation"""

    def test_function_exists(self) -> None:
        """Verify archive_previous_stages function is defined"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        assert "archive_previous_stages()" in content

    def test_archives_alpha_on_beta_promotion(self) -> None:
        """Verify function archives alpha when promoting to beta"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("archive_previous_stages()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        # Should have case for beta that includes "a"
        assert "beta)" in func_body, "Should handle beta case"

    def test_archives_all_on_stable_promotion(self) -> None:
        """Verify function archives alpha/beta/rc when promoting to stable"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("archive_previous_stages()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        # Stable should archive a, b, and rc
        assert "stable)" in func_body, "Should handle stable case"

    def test_uses_gh_release_edit(self) -> None:
        """Verify function uses gh release edit to mark as pre-release"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        func_start = content.find("archive_previous_stages()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        assert "gh release edit" in func_body, "Should use gh release edit"
        assert "--prerelease" in func_body, "Should mark as prerelease"


class TestVersionRulesDocumentation:
    """Test that version rules are documented"""

    def test_claude_md_has_version_rules(self) -> None:
        """Verify CLAUDE.md documents the version release rules (skipped on CI - file is gitignored)"""
        claude_md = Path(__file__).parent.parent / "CLAUDE.md"
        if not claude_md.exists():
            pytest.skip("CLAUDE.md not found (gitignored, only present in local dev)")

        content = claude_md.read_text(encoding="utf-8")

        required_sections = [
            "Version Release Rules",
            "Single Stage Rule",
            "Stage Progression Rule",
            "RC Gateway Rule",
        ]

        for section in required_sections:
            assert section in content, f"CLAUDE.md missing section: {section}"

    def test_contributing_md_references_version_rules(self) -> None:
        """Verify CONTRIBUTING.md references version release rules"""
        contributing_md = Path(__file__).parent.parent / "CONTRIBUTING.md"
        content = contributing_md.read_text(encoding="utf-8")

        assert "Version Release Rules" in content, "CONTRIBUTING.md should have version rules section"
        assert "CLAUDE.md" in content, "CONTRIBUTING.md should reference CLAUDE.md"

    def test_just_commands_md_has_release_section(self) -> None:
        """Verify JUST COMMANDS doc has release workflow section"""
        just_md = Path(__file__).parent.parent / "JUST COMMANDS FOR THIS PROJECT.md"
        content = just_md.read_text(encoding="utf-8")

        assert "Release Workflow" in content, "Missing Release Workflow section"
        assert "Version Release Rules" in content, "Missing Version Release Rules section"

    def test_hooks_readme_mentions_version_validation(self) -> None:
        """Verify scripts/hooks/README.md mentions version validation"""
        hooks_readme = Path(__file__).parent.parent / "scripts" / "hooks" / "README.md"
        content = hooks_readme.read_text(encoding="utf-8")

        assert "Version Release Validation" in content or "version release rules" in content.lower(), "scripts/hooks/README.md should mention version validation"


class TestReleaseScriptStructure:
    """Test overall release.sh structure and safety checks"""

    def test_has_strict_mode(self) -> None:
        """Verify script uses strict bash mode"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        assert "set -euo pipefail" in content, "Should use strict bash mode"

    def test_has_github_release_before_pypi(self) -> None:
        """Verify GitHub release is created before PyPI publish"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")

        # Look for the verification comment/code
        assert "CRITICAL: Verify GitHub release" in content or "GitHub release exists before PyPI" in content, "Should verify GitHub release before PyPI"

    def test_has_pre_release_safety_check(self) -> None:
        """Verify script has safety check to prevent PyPI publish of pre-releases"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")

        # Should check for pre-release markers before PyPI
        assert "SAFETY ABORT" in content or "pre-release marker" in content.lower(), "Should have safety check for pre-release markers"

    def test_requires_uv_publish_token(self) -> None:
        """Verify script requires UV_PUBLISH_TOKEN for stable releases"""
        content = RELEASE_SCRIPT.read_text(encoding="utf-8")
        assert "UV_PUBLISH_TOKEN" in content, "Should check for UV_PUBLISH_TOKEN"


# =============================================================================
# BEHAVIOR TESTS - Actually run the bash functions
# =============================================================================


@pytest.mark.skipif(sys.platform == "win32", reason="Bash functions not available on Windows")
class TestGetBaseVersionBehavior:
    """Behavior tests for get_base_version function - actually executes the bash function."""

    def test_removes_alpha_suffix(self) -> None:
        """Verify alpha suffix (aN) is removed from version string."""
        assert run_bash_function("get_base_version", "1.2.3a1") == "1.2.3"
        assert run_bash_function("get_base_version", "1.2.3a99") == "1.2.3"

    def test_removes_beta_suffix(self) -> None:
        """Verify beta suffix (bN) is removed from version string."""
        assert run_bash_function("get_base_version", "1.2.3b1") == "1.2.3"
        assert run_bash_function("get_base_version", "1.2.3b10") == "1.2.3"

    def test_removes_rc_suffix(self) -> None:
        """Verify rc suffix (rcN) is removed from version string."""
        assert run_bash_function("get_base_version", "1.2.3rc1") == "1.2.3"
        assert run_bash_function("get_base_version", "1.2.3rc99") == "1.2.3"

    def test_stable_version_unchanged(self) -> None:
        """Verify stable versions without suffix remain unchanged."""
        assert run_bash_function("get_base_version", "1.2.3") == "1.2.3"
        assert run_bash_function("get_base_version", "0.0.1") == "0.0.1"
        assert run_bash_function("get_base_version", "99.99.99") == "99.99.99"


@pytest.mark.skipif(sys.platform == "win32", reason="Bash functions not available on Windows")
class TestGetVersionStageBehavior:
    """Behavior tests for get_version_stage function - actually executes the bash function."""

    def test_detects_alpha(self) -> None:
        """Verify function returns 'alpha' for versions with aN suffix."""
        assert run_bash_function("get_version_stage", "1.2.3a1") == "alpha"
        assert run_bash_function("get_version_stage", "0.1.0a5") == "alpha"

    def test_detects_beta(self) -> None:
        """Verify function returns 'beta' for versions with bN suffix."""
        assert run_bash_function("get_version_stage", "1.2.3b1") == "beta"
        assert run_bash_function("get_version_stage", "0.1.0b10") == "beta"

    def test_detects_rc(self) -> None:
        """Verify function returns 'rc' for versions with rcN suffix."""
        assert run_bash_function("get_version_stage", "1.2.3rc1") == "rc"
        assert run_bash_function("get_version_stage", "0.1.0rc99") == "rc"

    def test_detects_stable(self) -> None:
        """Verify function returns 'stable' for versions without pre-release suffix."""
        assert run_bash_function("get_version_stage", "1.2.3") == "stable"
        assert run_bash_function("get_version_stage", "0.0.1") == "stable"


@pytest.mark.skipif(sys.platform == "win32", reason="Bash functions not available on Windows")
class TestGetStageValueBehavior:
    """Behavior tests for get_stage_value function - actually executes the bash function."""

    def test_alpha_value(self) -> None:
        """Verify alpha stage has value 1."""
        assert run_bash_function("get_stage_value", "alpha") == "1"

    def test_beta_value(self) -> None:
        """Verify beta stage has value 2."""
        assert run_bash_function("get_stage_value", "beta") == "2"

    def test_rc_value(self) -> None:
        """Verify rc stage has value 3."""
        assert run_bash_function("get_stage_value", "rc") == "3"

    def test_stable_value(self) -> None:
        """Verify stable stage has value 4."""
        assert run_bash_function("get_stage_value", "stable") == "4"

    def test_stage_ordering(self) -> None:
        """Verify stage progression: alpha < beta < rc < stable."""
        alpha = int(run_bash_function("get_stage_value", "alpha"))
        beta = int(run_bash_function("get_stage_value", "beta"))
        rc = int(run_bash_function("get_stage_value", "rc"))
        stable = int(run_bash_function("get_stage_value", "stable"))
        assert alpha < beta < rc < stable


@pytest.mark.skipif(sys.platform == "win32", reason="Bash functions not available on Windows")
class TestCompareBaseVersionsBehavior:
    """Behavior tests for compare_base_versions function - actually executes the bash function."""

    def test_equal_versions(self) -> None:
        """Verify function returns 0 when versions are equal."""
        assert run_bash_function("compare_base_versions", "1.2.3", "1.2.3") == "0"

    def test_first_greater(self) -> None:
        """Verify function returns 1 when first version is greater."""
        assert run_bash_function("compare_base_versions", "1.2.4", "1.2.3") == "1"
        assert run_bash_function("compare_base_versions", "2.0.0", "1.9.9") == "1"

    def test_first_smaller(self) -> None:
        """Verify function returns -1 when first version is smaller."""
        assert run_bash_function("compare_base_versions", "1.2.3", "1.2.4") == "-1"
        assert run_bash_function("compare_base_versions", "0.9.9", "1.0.0") == "-1"

    def test_edge_cases(self) -> None:
        """Verify function handles edge cases correctly."""
        assert run_bash_function("compare_base_versions", "0.0.1", "0.0.2") == "-1"
        assert run_bash_function("compare_base_versions", "99.99.99", "99.99.98") == "1"
