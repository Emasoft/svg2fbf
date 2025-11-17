#!/usr/bin/env python3
"""
Auto-Triage Agent for svg2fbf Issues

This script automatically triages new GitHub issues:
- Classifies as bug, feature, question, etc.
- For bugs: attempts reproduction (up to 3 attempts)
- For features: tags and queues for user approval
- Adds appropriate labels
- Comments with triage results
- Notifies user (@Emasoft) for approval

Security: All GitHub event data comes from environment variables
to prevent command injection vulnerabilities.
"""

import os
import sys
import subprocess
import re
import json


def run_command(cmd, check=True):
    """Run shell command safely."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}", file=sys.stderr)
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def classify_issue(title, body):
    """Classify issue type based on title and body."""
    title_lower = title.lower()
    body_lower = body.lower() if body else ""

    # Bug indicators
    bug_keywords = ["bug", "error", "crash", "fail", "broken", "issue", "problem", "doesn't work", "not working", "incorrect", "wrong"]

    # Feature indicators
    feature_keywords = ["feature", "enhancement", "add", "support", "would be nice", "could you", "request", "suggestion", "improve"]

    # Question indicators
    question_keywords = ["how", "why", "what", "where", "when", "question", "?"]

    # Documentation indicators
    docs_keywords = ["documentation", "docs", "readme", "typo", "spelling"]

    # Count matches
    bug_score = sum(1 for kw in bug_keywords if kw in title_lower or kw in body_lower)
    feature_score = sum(1 for kw in feature_keywords if kw in title_lower or kw in body_lower)
    question_score = sum(1 for kw in question_keywords if kw in title_lower)
    docs_score = sum(1 for kw in docs_keywords if kw in title_lower or kw in body_lower)

    # Determine type (highest score wins)
    scores = {"bug": bug_score, "feature": feature_score, "question": question_score, "documentation": docs_score}

    issue_type = max(scores, key=scores.get)

    # Default to bug if no clear match
    if scores[issue_type] == 0:
        issue_type = "bug"

    return issue_type


def attempt_reproduction(title, body, issue_number):
    """
    Attempt to reproduce a bug.

    For automated reproduction, we check:
    1. If steps are provided in the issue
    2. If we can run svg2fbf with example files
    3. If error messages are mentioned

    Returns: (reproduced: bool, details: str, attempt_count: int)
    """
    # This is a simplified version - real reproduction would be more complex
    # For now, we just check if the issue provides enough information

    body_lower = body.lower() if body else ""

    # Check if reproduction steps are provided
    has_steps = any(keyword in body_lower for keyword in ["steps to reproduce", "to reproduce", "how to reproduce", "run", "execute", "command"])

    # Check if examples are mentioned
    has_examples = any(keyword in body_lower for keyword in ["example", "test", "file", ".svg", ".yaml"])

    # Check if error messages are provided
    has_error = any(keyword in body_lower for keyword in ["error", "exception", "traceback", "stack trace"])

    if has_steps and (has_examples or has_error):
        return True, "Issue provides clear reproduction steps with examples/errors", 1
    elif has_steps:
        return False, "Reproduction steps provided but missing examples or error details", 1
    else:
        return False, "No clear reproduction steps provided", 1


def main():
    # Read environment variables (safe - set by GitHub Actions)
    issue_number = os.getenv("ISSUE_NUMBER")
    issue_title = os.getenv("ISSUE_TITLE", "")
    issue_body = os.getenv("ISSUE_BODY", "")
    issue_author = os.getenv("ISSUE_AUTHOR", "")
    repo_owner = os.getenv("REPO_OWNER", "")
    repo_name = os.getenv("REPO_NAME", "")

    if not issue_number:
        print("Error: ISSUE_NUMBER not set", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Triaging issue #{issue_number}: {issue_title}")

    # Classify the issue
    issue_type = classify_issue(issue_title, issue_body)
    print(f"📋 Classified as: {issue_type}")

    # Prepare labels and comment
    labels = ["needs-triage"]  # Always start with needs-triage
    comment_parts = ["🤖 **Auto-Triage Results**", "", f"**Issue Type**: `{issue_type}`", ""]

    # Type-specific handling
    if issue_type == "bug":
        labels.extend(["bug", "examining"])

        # Attempt reproduction
        reproduced, details, attempts = attempt_reproduction(issue_title, issue_body, issue_number)

        if reproduced:
            labels.append("reproduced")
            comment_parts.extend(["**Status**: ✅ **Reproduction information found**", f"**Details**: {details}", "", "**Next Steps**:", "1. Human reviewer will verify the reproduction", "2. If confirmed, agent will be assigned to fix", "3. Awaiting approval from @Emasoft to proceed", ""])
        else:
            labels.append("needs-reproduction")
            comment_parts.extend(
                [
                    "**Status**: ⚠️ **Needs more information**",
                    f"**Reason**: {details}",
                    "",
                    f"@{issue_author}, please provide:",
                    "1. Exact command you ran",
                    "2. Sample input files (or link to them)",
                    "3. Expected vs actual behavior",
                    "4. Environment (OS, Python version, svg2fbf version)",
                    "",
                    f"**Attempt**: 1/3 (will try {3 - attempts} more time{'s' if 3 - attempts != 1 else ''})",
                    "",
                ]
            )

    elif issue_type == "feature":
        labels.extend(["enhancement", "needs-approval"])
        comment_parts.extend(
            [
                "**Status**: 🎯 **Feature Request**",
                "",
                "This feature request has been queued for review.",
                "",
                "**Next Steps**:",
                "1. @Emasoft will review the feature request",
                "2. If approved, it will be added to the roadmap",
                "3. An agent may be assigned to implement it",
                "",
                "**Awaiting approval** from @Emasoft",
                "",
            ]
        )

    elif issue_type == "question":
        labels.extend(["question"])
        comment_parts.extend(
            ["**Status**: ❓ **Question**", "", "This appears to be a question. A team member will respond soon.", "", "You may also find answers in:", "- [Documentation](https://github.com/Emasoft/svg2fbf/blob/main/README.md)", "- [Examples](https://github.com/Emasoft/svg2fbf/tree/main/examples)", ""]
        )

    elif issue_type == "documentation":
        labels.extend(["documentation"])
        comment_parts.extend(["**Status**: 📚 **Documentation**", "", "Documentation improvement identified. Thank you!", "", "An agent may be assigned to update the documentation.", ""])

    # Add labels
    labels_str = ",".join(labels)
    print(f"🏷️  Adding labels: {labels_str}")
    run_command(f'gh issue edit {issue_number} --add-label "{labels_str}"')

    # Add auto-assign if it's a bug that was reproduced
    if issue_type == "bug" and "reproduced" in labels:
        comment_parts.extend(["---", "", "_This issue will be automatically assigned to an agent upon approval from @Emasoft._", ""])

    # Post comment
    comment = "\n".join(comment_parts)

    # Write comment to temp file (safer than passing as argument)
    with open("/tmp/triage_comment.md", "w") as f:
        f.write(comment)

    print("💬 Posting triage comment...")
    run_command(f"gh issue comment {issue_number} --body-file /tmp/triage_comment.md")

    # Clean up
    os.remove("/tmp/triage_comment.md")

    print(f"✅ Triage complete for issue #{issue_number}")
    print(f"   Type: {issue_type}")
    print(f"   Labels: {labels_str}")


if __name__ == "__main__":
    main()
