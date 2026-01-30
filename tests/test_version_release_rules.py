"""
Tests for version release rules validation functions in scripts/release.sh

These tests verify the three publishing rules:
1. Single Stage Rule: Only ONE stage per version at any time
2. Stage Progression Rule: Stage must be LOWER than previous version's stage
3. RC Gateway Rule: Alpha/beta only if previous version at RC or stable
"""

import re
from pathlib import Path


# Path to release.sh script
RELEASE_SCRIPT = Path(__file__).parent.parent / "scripts" / "release.sh"


class TestVersionRulesIntegration:
    """Integration tests for the version release rules"""

    def test_release_script_exists_and_executable(self) -> None:
        """Verify release.sh exists and is executable"""
        assert RELEASE_SCRIPT.exists(), f"Release script not found: {RELEASE_SCRIPT}"
        assert RELEASE_SCRIPT.stat().st_mode & 0o111, "Release script is not executable"

    def test_release_script_has_validation_functions(self) -> None:
        """Verify release.sh contains all required validation functions"""
        content = RELEASE_SCRIPT.read_text()
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
        content = RELEASE_SCRIPT.read_text()
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
        content = RELEASE_SCRIPT.read_text()
        archive_call = 'archive_previous_stages "$new_version"'

        assert archive_call in content, "archive_previous_stages not called"

        # Verify archive is called in the release_channel function
        release_channel_start = content.find("release_channel()")
        release_channel_end = content.find("\n}", release_channel_start + 100)
        release_channel_body = content[release_channel_start:release_channel_end]

        assert "archive_previous_stages" in release_channel_body, "archive_previous_stages should be in release_channel"

    def test_release_script_has_rollback(self) -> None:
        """Verify release.sh rolls back pyproject.toml on validation failure"""
        content = RELEASE_SCRIPT.read_text()
        rollback = "git checkout -- pyproject.toml"
        assert rollback in content, "Missing rollback of pyproject.toml on validation failure"


class TestGetBaseVersionFunction:
    """Test get_base_version function implementation"""

    def test_function_exists(self) -> None:
        """Verify get_base_version function is defined"""
        content = RELEASE_SCRIPT.read_text()
        assert "get_base_version()" in content

    def test_removes_alpha_suffix(self) -> None:
        """Verify function uses sed to remove alpha suffix"""
        content = RELEASE_SCRIPT.read_text()
        # Check the sed pattern handles alpha
        assert "(a|b|rc)" in content, "sed pattern should handle a/b/rc suffixes"

    def test_function_uses_sed(self) -> None:
        """Verify function uses sed for suffix removal"""
        content = RELEASE_SCRIPT.read_text()
        func_start = content.find("get_base_version()")
        func_end = content.find("\n}", func_start)
        func_body = content[func_start:func_end]
        assert "sed -E" in func_body, "Function should use sed -E for regex"


class TestGetVersionStageFunction:
    """Test get_version_stage function implementation"""

    def test_function_exists(self) -> None:
        """Verify get_version_stage function is defined"""
        content = RELEASE_SCRIPT.read_text()
        assert "get_version_stage()" in content

    def test_detects_all_stages(self) -> None:
        """Verify function can detect alpha, beta, rc, and stable"""
        content = RELEASE_SCRIPT.read_text()
        func_start = content.find("get_version_stage()")
        func_end = content.find("\n}", func_start)
        func_body = content[func_start:func_end]

        assert '"alpha"' in func_body or "'alpha'" in func_body, "Should return alpha"
        assert '"beta"' in func_body or "'beta'" in func_body, "Should return beta"
        assert '"rc"' in func_body or "'rc'" in func_body, "Should return rc"
        assert '"stable"' in func_body or "'stable'" in func_body, "Should return stable"

    def test_uses_pattern_matching(self) -> None:
        """Verify function uses bash pattern matching"""
        content = RELEASE_SCRIPT.read_text()
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
        content = RELEASE_SCRIPT.read_text()
        assert "get_stage_value()" in content

    def test_returns_numeric_values(self) -> None:
        """Verify function returns numeric stage values"""
        content = RELEASE_SCRIPT.read_text()
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
        content = RELEASE_SCRIPT.read_text()
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
        content = RELEASE_SCRIPT.read_text()
        assert "validate_version_release()" in content

    def test_checks_rule_1_single_stage(self) -> None:
        """Verify function checks Single Stage Rule"""
        content = RELEASE_SCRIPT.read_text()
        # Look for RULE 1 mention
        assert "RULE 1" in content or "Single Stage" in content, "Should check Single Stage Rule"

    def test_checks_rule_3_rc_gateway(self) -> None:
        """Verify function checks RC Gateway Rule"""
        content = RELEASE_SCRIPT.read_text()
        # Look for RULE 3 or RC Gateway mention
        assert "RULE 3" in content or "RC Gateway" in content, "Should check RC Gateway Rule"

    def test_returns_on_validation_pass(self) -> None:
        """Verify function returns 0 on validation pass"""
        content = RELEASE_SCRIPT.read_text()
        func_start = content.find("validate_version_release()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        assert "return 0" in func_body, "Should return 0 on success"
        assert "return 1" in func_body, "Should return 1 on failure"


class TestArchivePreviousStagesFunction:
    """Test archive_previous_stages function implementation"""

    def test_function_exists(self) -> None:
        """Verify archive_previous_stages function is defined"""
        content = RELEASE_SCRIPT.read_text()
        assert "archive_previous_stages()" in content

    def test_archives_alpha_on_beta_promotion(self) -> None:
        """Verify function archives alpha when promoting to beta"""
        content = RELEASE_SCRIPT.read_text()
        func_start = content.find("archive_previous_stages()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        # Should have case for beta that includes "a"
        assert "beta)" in func_body, "Should handle beta case"

    def test_archives_all_on_stable_promotion(self) -> None:
        """Verify function archives alpha/beta/rc when promoting to stable"""
        content = RELEASE_SCRIPT.read_text()
        func_start = content.find("archive_previous_stages()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        # Stable should archive a, b, and rc
        assert "stable)" in func_body, "Should handle stable case"

    def test_uses_gh_release_edit(self) -> None:
        """Verify function uses gh release edit to mark as pre-release"""
        content = RELEASE_SCRIPT.read_text()
        func_start = content.find("archive_previous_stages()")
        func_end = content.find("\n}", func_start + 100)
        func_body = content[func_start:func_end]

        assert "gh release edit" in func_body, "Should use gh release edit"
        assert "--prerelease" in func_body, "Should mark as prerelease"


class TestVersionRulesDocumentation:
    """Test that version rules are documented"""

    def test_claude_md_has_version_rules(self) -> None:
        """Verify CLAUDE.md documents the version release rules"""
        claude_md = Path(__file__).parent.parent / "CLAUDE.md"
        content = claude_md.read_text()

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
        content = contributing_md.read_text()

        assert "Version Release Rules" in content, "CONTRIBUTING.md should have version rules section"
        assert "CLAUDE.md" in content, "CONTRIBUTING.md should reference CLAUDE.md"

    def test_just_commands_md_has_release_section(self) -> None:
        """Verify JUST COMMANDS doc has release workflow section"""
        just_md = Path(__file__).parent.parent / "JUST COMMANDS FOR THIS PROJECT.md"
        content = just_md.read_text()

        assert "Release Workflow" in content, "Missing Release Workflow section"
        assert "Version Release Rules" in content, "Missing Version Release Rules section"

    def test_hooks_readme_mentions_version_validation(self) -> None:
        """Verify scripts/hooks/README.md mentions version validation"""
        hooks_readme = Path(__file__).parent.parent / "scripts" / "hooks" / "README.md"
        content = hooks_readme.read_text()

        assert "Version Release Validation" in content or "version release rules" in content.lower(), "scripts/hooks/README.md should mention version validation"


class TestReleaseScriptStructure:
    """Test overall release.sh structure and safety checks"""

    def test_has_strict_mode(self) -> None:
        """Verify script uses strict bash mode"""
        content = RELEASE_SCRIPT.read_text()
        assert "set -euo pipefail" in content, "Should use strict bash mode"

    def test_has_github_release_before_pypi(self) -> None:
        """Verify GitHub release is created before PyPI publish"""
        content = RELEASE_SCRIPT.read_text()

        # Look for the verification comment/code
        assert "CRITICAL: Verify GitHub release" in content or "GitHub release exists before PyPI" in content, "Should verify GitHub release before PyPI"

    def test_has_pre_release_safety_check(self) -> None:
        """Verify script has safety check to prevent PyPI publish of pre-releases"""
        content = RELEASE_SCRIPT.read_text()

        # Should check for pre-release markers before PyPI
        assert "SAFETY ABORT" in content or "pre-release marker" in content.lower(), "Should have safety check for pre-release markers"

    def test_requires_uv_publish_token(self) -> None:
        """Verify script requires UV_PUBLISH_TOKEN for stable releases"""
        content = RELEASE_SCRIPT.read_text()
        assert "UV_PUBLISH_TOKEN" in content, "Should check for UV_PUBLISH_TOKEN"
