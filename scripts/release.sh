#!/usr/bin/env bash

# Enable strict error handling so that any failing command stops the script immediately.
# Treat use of unset variables as errors to avoid subtle bugs from typos or missing values.
# Make pipelines fail when any component fails, not just the last command in the pipeline.
set -euo pipefail

# Determine the directory where this script resides.
# Use this to find the project root directory reliably regardless of where the script is invoked from.
# Resolve symlinks to get the actual script location, not a symlink path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The project root is the parent directory of the scripts/ directory.
# Change to the project root so all git and file operations happen in the correct location.
# This ensures cleanup, builds, and git operations work correctly regardless of invocation path.
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Store the project root for cleanup to use later.
# This ensures cleanup always operates on the correct directory even if something changes cwd.
readonly PROJECT_ROOT

# Start the definition of the print_help function that displays usage information.
# Use this function to show detailed documentation when users request help.
# Keep all descriptive text inside this function so it can be reused easily.
print_help() {
  # Begin a here-document that prints the help text to standard output using cat.
  # Use single quotes on the EOF marker so variables in the help text are not expanded.
  # Preserve all formatting and examples exactly as written inside the here-document.
  cat <<'EOF'
release.sh - multi-channel uv + git-cliff + GitHub + PyPI release helper

USAGE:
  ./release.sh [OPTIONS]

CHANNEL OPTIONS (each maps a release channel to a branch name):

  --stable <branch>   Build & release from this branch as a STABLE release.
                      - Uses `uv version --bump` to move to the next stable version.
                      - Regenerates CHANGELOG.md using git-cliff.
                      - Builds wheels/sdist with `uv build`.
                      - Creates a Git tag "v<version>" and a GitHub Release.
                      - Uses git-cliff output as GitHub release notes.
                      - Publishes the release to PyPI with `uv publish`.

  --alpha  <branch>   Build & release from this branch as an ALPHA pre-release.
                      - Uses `uv version --bump` to manage "aN" pre-releases.
                      - Regenerates CHANGELOG.md using git-cliff.
                      - Creates a Git tag "v<version>" and a GitHub pre-release.
                      - Uses git-cliff output as GitHub release notes.
                      - Does NOT publish to PyPI.

  --beta   <branch>   Build & release from this branch as a BETA pre-release.
                      - Uses `uv version --bump` to manage "bN" pre-releases.
                      - Regenerates CHANGELOG.md using git-cliff.
                      - Creates a GitHub pre-release only (no PyPI publish).

  --rc     <branch>   Build & release from this branch as a RELEASE CANDIDATE.
                      - Uses `uv version --bump` to manage "rcN" pre-releases.
                      - Regenerates CHANGELOG.md using git-cliff.
                      - Creates a GitHub pre-release only (no PyPI publish).

GENERAL OPTIONS:

  --no-pypi           Skip PyPI publishing for stable releases. Creates GitHub release
                      only, without running `uv publish`. This flag only affects stable
                      channel releases; alpha/beta/rc never publish to PyPI.

  -h, --help          Show this help text and exit.

CHANGELOG EXPECTATIONS:

  • Expect a changelog file named CHANGELOG.md in the repository.
  • Use git-cliff to generate and regenerate this changelog automatically.
  • CHANGELOG.md is fully regenerated from git history on each release; manual edits
    to this file will be overwritten by git-cliff runs.
  • Typical setup:
        git cliff --init
        git cliff -o CHANGELOG.md
    Configure the behavior in cliff.toml to match your preferred style.

BEHAVIOR SUMMARY:

  • You can specify one or more channels in a single run:
      ./release.sh --alpha dev --beta testing --rc review --stable master

    The script will process them in this fixed order:
      alpha → beta → rc → stable

  • For each channel, the script:
      1. Checks out the configured branch.
      2. Ensures the branch is up to date with origin/<branch>.
      3. Ensures the working tree is clean.
      4. Reads the current version from `uv version`.
      5. Computes bump arguments for `uv version --bump`:
         - alpha:
             - if already "aN", bump alpha;
             - else bump patch + alpha.
         - beta:
             - if already "bN", bump beta;
             - else bump patch + beta.
         - rc:
             - if already "rcN", bump rc;
             - else bump patch + rc.
         - stable:
             - if current is pre-release (a/b/rc), use --bump stable;
             - otherwise bump patch for a new stable version.
      6. Runs `uv version --no-sync` with those arguments.
      7. Uses `git cliff --tag <version> -o CHANGELOG.md` to regenerate the changelog.
      8. Uses `git cliff --tag <version> --latest -o .release-notes-<version>.md`
         to generate release notes for just the latest version section.
      9. Commits pyproject.toml and CHANGELOG.md.
     10. Removes dist/, then runs `uv sync` and `uv build`.
     11. Creates and pushes tag "v<version>".
     12. Creates a GitHub Release (pre-release for alpha/beta/rc).
     13. For stable only: runs `uv publish` to upload to PyPI.

REQUIREMENTS:

  • uv:
      Must be installed and on PATH.
      Used for version bumping, syncing, building, and publishing.

  • gh:
      GitHub CLI must be installed and authenticated (`gh auth login`).

  • git cliff:
      Must be callable as `git cliff`.
      Used to generate CHANGELOG.md and per-release notes.
      Configure via cliff.toml as needed.

  • UV_PUBLISH_TOKEN:
      Required when a stable release is requested so uv can publish to PyPI.
      Example:
        export UV_PUBLISH_TOKEN="pypi-XXXXXXXXXXXX"

EOF
}

# Declare a variable to hold the name of the branch used for stable releases.
# Initialize this variable as an empty string so later code can detect if it was set.
# Expect this variable to be configured via the --stable <branch> command-line option.
stable_branch=""

# Declare a variable to hold the branch name used for alpha pre-releases.
# Initialize this variable as an empty string so alpha releases can be optional.
# Set this variable when parsing the --alpha <branch> command-line option.
alpha_branch=""

# Declare a variable to hold the branch name used for beta pre-releases.
# Start with an empty value so beta releases only run when explicitly configured.
# Assign this variable when the user supplies the --beta <branch> option.
beta_branch=""

# Declare a variable to hold the branch used for release candidate (rc) releases.
# Initialize the value as empty so rc processing is skipped unless configured.
# Fill this variable by reading the branch after the --rc <branch> option.
rc_branch=""

# Declare a flag to control PyPI publishing behavior for stable releases.
# Initialize as false (empty) so stable releases publish to PyPI by default.
# Set to true when the --no-pypi flag is present to skip PyPI publishing.
no_pypi=""

# Capture the current git branch at the beginning of the script execution.
# Use this value to restore the original branch once all release steps are complete.
# Improve developer ergonomics by leaving the repository on the same branch as before.
start_branch="$(git rev-parse --abbrev-ref HEAD)"

# Initialize an array to track temporary release notes files created during the release.
# Each time a release notes file is created, it will be added to this array.
# The cleanup function will delete only the files in this array, nothing else.
# This provides explicit control over what gets deleted instead of using wildcards.
declare -a RELEASE_NOTES_FILES=()

# Define a function to safely switch git branches with validation.
# This function records the current branch and provides a way to return to it.
# Use this instead of raw git checkout to maintain better control over branch state.
switch_to_branch() {
  local target_branch="$1"
  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"

  # Only checkout if we're not already on the target branch
  if [[ "$current_branch" != "$target_branch" ]]; then
    echo "Switching from '$current_branch' to '$target_branch'..." >&2
    git checkout "$target_branch"
  fi
}

# Define a function to safely return to the original branch.
# This encapsulates the logic for restoring the starting branch state.
# Call this in cleanup to ensure the user is left on their original branch.
restore_original_branch() {
  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"

  # Only restore if we're not already on the start branch
  if [[ "$current_branch" != "$start_branch" ]]; then
    echo "Restoring original branch '$start_branch'..." >&2
    git checkout "$start_branch" 2>/dev/null || {
      echo "Warning: Could not restore original branch '$start_branch'" >&2
      echo "Current branch: $current_branch" >&2
      return 1
    }
  fi
}

# Define a function to delete tracked temporary files.
# Call this function explicitly at the end of the script - do NOT use trap.
# Manual cleanup is safer than automatic trap which can have unexpected side effects.
cleanup_temporary_files() {
  # Delete only the temporary release notes files that were explicitly created and tracked.
  # Loop through the RELEASE_NOTES_FILES array and delete each file individually.
  # This approach is safer than wildcards - we only delete what we know we created.
  if [[ ${#RELEASE_NOTES_FILES[@]} -gt 0 ]]; then
    echo "Cleaning up ${#RELEASE_NOTES_FILES[@]} temporary release notes file(s)..." >&2
    for notes_file in "${RELEASE_NOTES_FILES[@]}"; do
      if [[ -f "$PROJECT_ROOT/$notes_file" ]]; then
        rm -f "$PROJECT_ROOT/$notes_file" 2>/dev/null || true
        echo "  ✓ Deleted: $notes_file" >&2
      fi
    done
  fi
}

# Declare an array that records which channels and branches have been requested.
# Use an array of strings like "alpha:dev" or "stable:master" for easy human reading.
# Keep this information available for debugging or logging if needed.
requested_channels=()

# Start a while loop that parses all command-line arguments given to the script.
# Continue looping as long as there is at least one unprocessed argument remaining.
# Use this loop together with a case statement to handle each recognized option.
while [[ $# -gt 0 ]]; do
  # Use a case statement to decide how to interpret the current argument.
  # Match specific options like --stable, --alpha, --beta, --rc, -h, and --help.
  # Fall back to a default branch that reports unknown options and aborts.
  case "$1" in
    # Handle the --stable option to configure a branch for stable releases.
    # Expect a branch name to follow this option on the command line.
    # Store the branch in stable_branch and record the mapping for diagnostics.
    --stable)
      # Check that there is at least one additional argument for the branch name.
      # Abort with an error if the branch name is missing to avoid ambiguous configuration.
      # Ensure the stable channel always has an explicit branch when requested.
      if [[ $# -lt 2 ]]; then
        echo "Error: --stable requires a branch name" >&2
        exit 1
      fi
      # Assign the next argument to the stable_branch variable representing the source branch.
      # Allow later code to use this value when running the stable-channel release flow.
      # Overwrite any previous value for stable_branch with the most recent one.
      stable_branch="$2"
      # Record the stable channel and branch pairing in the requested_channels array.
      # Store this purely for informational use, not for primary control flow decisions.
      # Make it easy to inspect which channels were configured during this run.
      requested_channels+=("stable:$2")
      # Shift the positional parameters left by two positions to consume flag and branch.
      # Move on to the next argument so the parsing loop can continue cleanly.
      # Prevent re-processing the same --stable pair on the next iteration.
      shift 2
      ;;
    # Handle the --alpha option to configure an alpha pre-release branch.
    # Expect a branch name immediately after the option in the argument list.
    # Save this branch name so alpha releases can be built from it.
    --alpha)
      # Validate that another argument is available for the alpha branch name.
      # Report an error and stop if the branch is missing to avoid undefined behavior.
      # Force users to pass a valid branch whenever they request --alpha.
      if [[ $# -lt 2 ]]; then
        echo "Error: --alpha requires a branch name" >&2
        exit 1
      fi
      # Store the user-provided branch in the alpha_branch variable for later use.
      # Use this branch when invoking the release flow for the alpha channel.
      # Replace any previous alpha_branch value with this one if re-specified.
      alpha_branch="$2"
      # Append a descriptive "alpha:<branch>" entry to the requested_channels array.
      # Maintain a record of how the alpha channel is configured in this invocation.
      # Treat this record as helpful metadata rather than essential control data.
      requested_channels+=("alpha:$2")
      # Consume both the --alpha option and the branch name by shifting arguments.
      # Advance the parsing loop to the next remaining option or positional parameter.
      # Avoid infinite loops by ensuring each option is handled exactly once.
      shift 2
      ;;
    # Handle the --beta option to configure the beta pre-release branch.
    # Read the branch name that should follow this option in the arguments.
    # Keep this branch available for beta release operations.
    --beta)
      # Ensure that the --beta option is followed by a branch name argument.
      # Emit an error message and exit if the branch name is not present.
      # Enforce explicit configuration for beta releases to avoid confusion.
      if [[ $# -lt 2 ]]; then
        echo "Error: --beta requires a branch name" >&2
        exit 1
      fi
      # Store the beta branch name into the beta_branch variable for later reference.
      # Use this value when performing beta releases on the chosen branch.
      # Allow the user to override any previous setting by specifying --beta again.
      beta_branch="$2"
      # Add a "beta:<branch>" description to the requested_channels array.
      # Keep this information to aid in understanding which branches were chosen.
      # Remember that the actual release logic checks beta_branch directly.
      requested_channels+=("beta:$2")
      # Remove the processed option and branch argument from the positional parameters.
      # Shift by two elements to ensure parsing continues with the next argument.
      # Maintain a clean progression through all supplied arguments.
      shift 2
      ;;
    # Handle the --rc option to configure a branch for release candidate builds.
    # Expect a branch name after the option indicating where rc releases come from.
    # Store the branch for use when running the rc release flow.
    --rc)
      # Verify that --rc has a corresponding branch name argument after it.
      # Print an error and exit if the script does not find this required argument.
      # Guarantee that the rc channel has a clearly defined source branch.
      if [[ $# -lt 2 ]]; then
        echo "Error: --rc requires a branch name" >&2
        exit 1
      fi
      # Assign the given branch name to the rc_branch variable.
      # Use this value later when running the release flow for the rc channel.
      # Permit reconfiguration by allowing subsequent --rc values to override this.
      rc_branch="$2"
      # Log the rc channel and branch pair in the requested_channels array.
      # Use a string like "rc:<branch>" to make inspection simple and human-readable.
      # Keep this log as auxiliary information, separate from the primary logic.
      requested_channels+=("rc:$2")
      # Shift arguments left by two to consume the flag and the branch parameter.
      # Continue parsing with the remaining arguments after these are removed.
      # Preserve correct command-line parsing order across all supplied options.
      shift 2
      ;;
    # Handle the --no-pypi flag to skip PyPI publishing for stable releases.
    # Set the no_pypi flag so the release_channel function skips uv publish.
    # Use this when creating GitHub releases without publishing to PyPI.
    --no-pypi)
      # Mark the no_pypi flag as true to indicate PyPI publishing should be skipped.
      # This affects only stable channel releases; other channels never publish to PyPI.
      # Allow stable releases to be created on GitHub without PyPI deployment.
      no_pypi="true"
      # Shift the positional parameters left by one to consume the flag.
      # Continue parsing with the next argument in the list.
      # Make sure each --no-pypi flag is processed exactly once.
      shift
      ;;
    # Handle the -h and --help options that request usage documentation.
    # Invoke the print_help function to display the full help text.
    # Exit successfully after printing help so no release actions follow.
    -h|--help)
      # Call print_help to show detailed usage, options, and examples to the user.
      # Write the multi-line help text to standard output so it appears in the console.
      # Provide full documentation to guide users before they run actual releases.
      print_help
      # Exit the script with a zero status code after printing help.
      # Avoid performing any release logic when the user only wants assistance.
      # Make help a read-only and side-effect-free operation.
      exit 0
      ;;
    # Handle any argument that does not match the expected options.
    # Treat such arguments as errors and provide guidance to the user.
    # Abort execution to prevent unintended behavior from unknown flags.
    *)
      # Print an error message describing the unrecognized option that was found.
      # Include the offending argument so the user can see exactly what to correct.
      # Send this message to stderr to distinguish it from normal script output.
      echo "Error: Unknown option: $1" >&2
      # Suggest running the script with --help to see valid usage and options.
      # Help the user quickly discover the correct syntax and supported flags.
      # Provide this hint on stderr along with the error message above.
      echo "Run ./release.sh --help for usage." >&2
      # Exit the script with a non-zero status indicating invalid invocation.
      # Prevent further actions when an unknown or unsupported option is used.
      # Maintain strict argument validation for consistent behavior.
      exit 1
      ;;
  esac
done

# Check whether any release channel branch has been configured by the user.
# Consider stable, alpha, beta, and rc branches, and see if all are still empty.
# Abort with an error and show help if no channels were specified at all.
if [[ -z "$stable_branch" && -z "$alpha_branch" && -z "$beta_branch" && -z "$rc_branch" ]]; then
  # Report that no release channels were configured when invoking the script.
  # Explain that at least one of --stable, --alpha, --beta, or --rc is required.
  # Write this message to stderr to mark it as an error condition.
  echo "Error: No channels specified. Use --stable/--alpha/--beta/--rc." >&2
  # Call print_help to show detailed usage guidance after reporting the error.
  # Give the user immediate access to correct syntax and options.
  # Keep users from having to run the command again solely to see help.
  print_help
  # Exit with a non-zero status code to indicate that no work was performed.
  # Signal to callers and CI systems that the invocation did not succeed.
  # Prevent the script from continuing when channels were not configured.
  exit 1
fi

# Check for unsafe reuse of the same branch across multiple channels.
# Create an associative array to track which branches have already been assigned.
# Abort if a branch name appears for more than one channel to avoid footguns.
declare -A seen_branches
for channel_config in "${requested_channels[@]}"; do
  # Extract the branch name from the channel:branch pair stored in requested_channels.
  # Use parameter expansion to remove everything up to and including the colon.
  # Store only the branch portion in a temporary variable for checking.
  branch="${channel_config#*:}"
  # Test whether this branch name has already been seen in a previous channel configuration.
  # Use the seen_branches associative array to track branch usage.
  # Abort if the same branch appears more than once across channels.
  if [[ -n "${seen_branches[$branch]-}" ]]; then
    echo "Error: Branch '$branch' used for multiple channels." >&2
    echo "This is not recommended. Use different branches per channel." >&2
    exit 1
  fi
  # Mark this branch as seen in the associative array to detect future duplicates.
  # Use a dummy value such as 1 since only the existence of the key matters here.
  # Continue checking any remaining channel configurations after this entry.
  seen_branches[$branch]=1
done

# Check that the uv command is available on the PATH for this script.
# Test its presence quietly by using command -v and discarding its output.
# Fail early with an explanatory message if uv cannot be found.
if ! command -v uv >/dev/null 2>&1; then
  # Inform the user that the uv tool is missing or not visible in the current PATH.
  # Emphasize that uv must be installed for versioning, syncing, building, and publishing.
  # Direct this message to stderr to highlight it as an error.
  echo "Error: 'uv' is not installed or not on PATH." >&2
  # Exit the script with a non-zero status code due to this missing requirement.
  # Avoid running any release-related commands without uv available.
  # Keep the failure mode explicit and localized to this prerequisite check.
  exit 1
fi

# Verify that the GitHub CLI gh is installed and accessible in the PATH.
# Use command -v to probe for the presence of gh silently.
# If gh is absent, abort because GitHub releases cannot be created.
if ! command -v gh >/dev/null 2>&1; then
  # Print an error indicating that the GitHub CLI is not installed or not accessible.
  # Suggest installing gh and running gh auth login to configure authentication.
  # Write the error details to stderr to separate them from normal output.
  echo "Error: GitHub CLI 'gh' is not installed or not on PATH." >&2
  echo "Install from: https://cli.github.com/ and run 'gh auth login'." >&2
  # Exit with a non-zero status to indicate that this required tool is missing.
  # Prevent further release processing from proceeding without GitHub CLI support.
  # Preserve a clear and direct error path for this dependency check.
  exit 1
fi

# Verify that git-cliff is available as the `git cliff` subcommand for changelog generation.
# Use a simple `git cliff -h` to confirm that the command works without error.
# Abort the script if git-cliff is not present or not functioning.
if ! git cliff -h >/dev/null 2>&1; then
  # Inform the user that git-cliff does not seem to be installed or accessible.
  # Instruct the user to install git-cliff and ensure that `git cliff` runs correctly.
  # Send these messages to stderr so they are recognized as error diagnostics.
  echo "Error: 'git cliff' (git-cliff) is not available." >&2
  echo "Install git-cliff and ensure 'git cliff' works in this repository." >&2
  # Exit with a non-zero status code to prevent running without changelog support.
  # Maintain consistent behavior by stopping when required tools are missing.
  # Avoid generating incomplete releases that lack proper changelog content.
  exit 1
fi

# Ensure that a pyproject.toml file exists in the current working directory.
# Use a simple file existence test to check for this core configuration file.
# Exit with an error if pyproject.toml is missing, since uv relies on it.
if [[ ! -f pyproject.toml ]]; then
  # Notify the user that pyproject.toml could not be found where the script is running.
  # Imply that the script should be executed from the project root where this file resides.
  # Output this message to stderr to highlight that it indicates an error.
  echo "Error: pyproject.toml not found in current directory." >&2
  # Terminate the script with a non-zero status due to the missing project configuration.
  # Avoid invoking uv or any release logic in a directory lacking pyproject.toml.
  # Keep the release process tied to the correct project root.
  exit 1
fi

# Define the ensure_clean function that verifies a clean git working tree.
# Check for both unstaged changes and staged but uncommitted changes.
# Exit with an error if any such changes are present, enforcing clean releases.
ensure_clean() {
  # Test for unstaged changes by comparing the working tree against HEAD with git diff.
  # Also test for staged but uncommitted changes by comparing the index against HEAD.
  # Consider the repository unclean if either comparison shows differences.
  if ! git diff --quiet || ! git diff --cached --quiet; then
    # Print an error indicating that the current branch has uncommitted changes.
    # Include the branch name so the user knows where to commit or stash work.
    # Direct the message to stderr so that it is recognized as diagnostic output.
    echo "Error: Uncommitted changes in branch $(git rev-parse --abbrev-ref HEAD)." >&2
    echo "Please commit or stash your changes before running this script." >&2
    # Exit with a non-zero status to prevent performing a release from a dirty tree.
    # Preserve the invariant that releases are only created from clean source states.
    # Keep the commit history tidy by avoiding release commits mixed with other changes.
    exit 1
  fi
}

# Define the compute_bump_args function used to construct uv bump flags.
# Accept the release channel and the current version as positional arguments.
# Emit a list of arguments such as "--bump patch --bump alpha" for uv to consume.
compute_bump_args() {
  # Read the channel argument to determine which release type is being processed.
  # Expect values like alpha, beta, rc, or stable to guide the logic.
  # Use this channel to decide whether to bump a pre-release component or patch.
  local channel="$1"
  # Read the current version string as reported by uv version before bumping.
  # Use shell pattern matching on this value to detect alpha, beta, or rc suffixes.
  # Feed this knowledge into conditional logic to choose bump behavior.
  local current_version="$2"
  # Initialize an empty array to hold all bump-related arguments for uv.
  # Append elements like --bump and specific bump targets such as patch or alpha.
  # Combine these later into the uv version command invocation.
  local bump=()

  # Switch on the channel type to decide how to manipulate the version string.
  # Use a case statement to keep logic for alpha, beta, rc, and stable separated.
  # Append the appropriate bump flags to the bump array for each channel.
  case "$channel" in
    # Handle alpha channel bumps for alpha pre-release versions.
    # Bump only the alpha counter when already in an alpha series.
    # Otherwise bump patch first and then alpha to start a new alpha cycle.
    alpha)
      # Check whether the current version ends with an alpha suffix like "a1" or "a2".
      # Use a glob pattern matching "a" followed by digits anywhere in the version string.
      # Use this pattern result to decide whether to bump alpha alone or patch+alpha.
      if [[ "$current_version" == *a[0-9]* ]]; then
        # Append a bump directive that increments the alpha pre-release component.
        # Keep the base numeric version (major.minor.patch) unchanged in this case.
        # Rely on uv to convert versions such as "1.2.3a1" into "1.2.3a2".
        bump+=(--bump alpha)
      else
        # Append bump directives that first increment the patch component of the version.
        # Follow the patch bump with an alpha bump to begin a new alpha series.
        # Expect uv to turn "1.2.3" into "1.2.4a1" with these combined flags.
        bump+=(--bump patch --bump alpha)
      fi
      ;;
    # Handle beta channel bumps for beta pre-release versions.
    # Mirror the alpha behavior but operate on beta suffixes such as "b1".
    # Decide between bumping beta alone or bumping patch then beta.
    beta)
      # Test whether the current version includes a beta suffix that looks like "bN".
      # Use a glob pattern to detect "b" followed by digits in the version string.
      # Use this detection to choose the correct bump strategy for beta.
      if [[ "$current_version" == *b[0-9]* ]]; then
        # Append a directive to bump only the beta pre-release component of the version.
        # Keep the underlying major.minor.patch numbers identical while incrementing beta.
        # Expect uv to turn "1.2.3b1" into "1.2.3b2" as a result.
        bump+=(--bump beta)
      else
        # Append a patch bump followed by a beta bump to start a new beta sequence.
        # Apply this when the current version is not already a beta pre-release.
        # Expect uv to transform "1.2.3" into "1.2.4b1" for example.
        bump+=(--bump patch --bump beta)
      fi
      ;;
    # Handle rc channel bumps for release candidate versions.
    # Apply similar rules as alpha and beta but look for "rcN" suffixes.
    # Choose whether to bump rc alone or bump patch plus rc.
    rc)
      # Detect whether the current version has a release candidate suffix.
      # Use a glob pattern that picks up "rc" followed by digits anywhere in the string.
      # Use this information to select between bumping rc or patch+rc.
      if [[ "$current_version" == *rc[0-9]* ]]; then
        # Add a bump directive to increment only the rc pre-release component.
        # Leave the underlying base version unchanged while stepping rc forward.
        # Expect uv to convert "1.2.3rc1" into "1.2.3rc2" under this directive.
        bump+=(--bump rc)
      else
        # Add combined bump directives to increment patch and then rc.
        # Use this when transitioning from a stable version into a new rc cycle.
        # Expect uv to change "1.2.3" into "1.2.4rc1" under these conditions.
        bump+=(--bump patch --bump rc)
      fi
      ;;
    # Handle stable channel bumps for final non-pre-release versions.
    # Convert pre-release versions into stable or bump patch for already-stable versions.
    # Use simple checks for alpha, beta, or rc suffixes to guide the behavior.
    stable)
      # Determine whether the current version includes any pre-release suffix.
      # Look for alpha, beta, or rc styles in the version string.
      # Use this information to decide between a stable bump or a patch bump.
      if [[ "$current_version" == *a[0-9]* || "$current_version" == *b[0-9]* || "$current_version" == *rc[0-9]* ]]; then
        # Append a bump directive that converts a pre-release into a stable version.
        # Leave the numeric base unchanged while removing the pre-release marker.
        # Expect uv to turn "1.2.3rc1" into "1.2.3" by applying this bump.
        bump+=(--bump stable)
      else
        # Append a bump directive that simply increments the patch component.
        # Use this when the current version is already a stable release.
        # Expect uv to convert "1.2.3" into "1.2.4" using this simple bump.
        bump+=(--bump patch)
      fi
      ;;
  esac

  # Output the constructed bump arguments as a single space-separated string.
  # Allow the caller to capture this output and include it in a uv version command.
  # Keep this logic isolated so all bump rules live in one place.
  echo "${bump[@]}"
}

# Define a helper function to generate changelog and release notes with git-cliff.
# Accept the new version string as the first argument for tagging in the changelog.
# Return the path to the generated notes file so GitHub release creation can use it.
generate_changelog_and_notes() {
  # Capture the new version value from the first positional argument.
  # Use this version identifier with git-cliff to label the changelog section.
  # Make sure this matches the version produced by uv version earlier in the flow.
  local new_version="$1"
  # Build a filename for the release notes that incorporates the version string.
  # Use this file as the target for git-cliff to write per-release notes.
  # Rely on this same file later as the input to gh release --notes-file.
  local notes_file=".release-notes-${new_version}.md"

  # Regenerate the full CHANGELOG.md using git-cliff and the provided tag.
  # Use the --tag option so git-cliff writes a new section for this version.
  # Be aware that this overwrites any manual edits with freshly generated content.
  git cliff --tag "$new_version" -o CHANGELOG.md
  # Generate notes for the latest version section only using git-cliff.
  # Use the --tag and --latest flags so only the most recent version block is written.
  # Write these notes into the version-specific notes_file for later use with gh.
  git cliff --tag "$new_version" --latest -o "$notes_file"

  # Track this file in the global array so cleanup can delete it explicitly.
  # Add the notes_file to the RELEASE_NOTES_FILES array for later cleanup.
  # This ensures we only delete files we explicitly created, not random files.
  RELEASE_NOTES_FILES+=("$notes_file")

  # Print the notes_file path so callers can use it when creating GitHub releases.
  # Allow release_channel to pass this file to gh release --notes-file.
  # Keep this function focused on changelog and notes generation logic.
  echo "$notes_file"
}

# Define the release_channel function that performs the full release pipeline.
# Accept a channel name (alpha/beta/rc/stable) and a branch name as arguments.
# Execute checkout, branch sync, cleanliness check, version bump, changelog generation, build, tag, push, GitHub release, and optional PyPI publish.
release_channel() {
  # Read the channel argument that indicates which type of release to perform.
  # Use this value to determine bump rules and whether to treat the release as a prerelease.
  # Accept values like "alpha", "beta", "rc", and "stable" for different behaviors.
  local channel="$1"
  # Read the branch argument that names the git branch to release from.
  # Check out this branch before doing any other operations in the function.
  # Assume the caller has passed a valid branch name that exists in the repository.
  local branch="$2"

  # Print a blank line to visually separate release logs from earlier output.
  # Print a descriptive header stating which channel and branch are being released.
  # Use these lines to make the script’s output easier to scan during multi-channel runs.
  echo
  echo "=== Releasing channel '$channel' from branch '$branch' ==="

  # Check out the target branch so that all subsequent commands operate on its content.
  # Use the switch_to_branch function for safer, more controlled branch switching.
  # Ensure that uv, git-cliff, and build operations always run from the correct branch state.
  switch_to_branch "$branch"

  # Fetch the latest changes for this branch from the origin remote.
  # Use git fetch to update remote-tracking references without merging anything.
  # Make sure the script has an accurate view of origin/$branch for comparison.
  git fetch origin "$branch"

  # Compare the local HEAD with the remote origin/$branch to detect divergence.
  # Abort if the local branch is not exactly at the same commit as origin/$branch.
  # Require users to sync their branch before releasing to avoid shipping stale code.
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$branch")" ]]; then
    echo "Error: Branch '$branch' is not in sync with origin/$branch." >&2
    echo "Please pull or rebase to align with origin before releasing." >&2
    exit 1
  fi

  # Run the ensure_clean function to verify that the current branch has no uncommitted changes.
  # Make sure both staged and unstaged modifications are absent before releasing.
  # Abort if any pending changes are found to keep release commits clean and focused.
  ensure_clean

  # Call uv version to query the project’s current version string.
  # Capture the full output, which typically includes both project name and version.
  # Prepare to parse the version number from this combined string.
  local version_line
  version_line="$(uv version)"
  # Extract the version component by stripping everything up to the last space.
  # Use parameter expansion to remove the project name portion from version_line.
  # Store only the clean version string in current_version for bump logic.
  local current_version="${version_line##* }"

  # Declare an array to hold the bump arguments returned by compute_bump_args.
  # Use a local array so each call to release_channel has its own bump arguments.
  # Avoid storing the bump arguments in a plain string to prevent incorrect splitting.
  local -a bump_args=()
  # Populate the bump_args array by reading words from the compute_bump_args output.
  # Use read -r -a to split the output into separate array elements based on whitespace.
  # Preserve each bump flag as its own element so uv receives distinct arguments.
  read -r -a bump_args <<<"$(compute_bump_args "$channel" "$current_version")"

  # Print the current version for the branch so users can see the starting point.
  # Show the bump arguments that will be passed to uv for transparency and debugging.
  # Help verify that the channel-specific bump logic is behaving as intended.
  echo "Current version: $current_version"
  echo "Bump args for channel '$channel': ${bump_args[*]}"

  # Call uv version with the computed bump arguments applied to the current project.
  # Use "${bump_args[@]}" so each array element becomes a separate uv argument.
  # Keep this expansion quoted to satisfy ShellCheck and avoid unintended word splitting.
  uv version --no-sync "${bump_args[@]}"

  # Query uv again after the bump to see the updated version details.
  # Capture the full output line including project name and new version.
  # Prepare to extract just the new version number from the combined string.
  local new_line
  new_line="$(uv version)"
  # Use parameter expansion to strip the project name from the uv version output.
  # Keep only the portion after the last space, which is the new version.
  # Assign this clean version string to new_version for subsequent steps.
  local new_version="${new_line##* }"

  # Build a git tag name by prefixing the new version with the letter v.
  # Follow a common convention of tagging releases as "v<version>".
  # Store this tag string in the tag variable for use when tagging and creating releases.
  local tag="v${new_version}"

  # Print a concise summary of the version change for this channel and branch.
  # Display the transition from old version to new version alongside the tag name.
  # Help users confirm that the bump and tag naming are consistent with expectations.
  echo "Bumped version: $current_version → $new_version (tag: $tag)"

  # Run git-cliff-based changelog and release notes generation for the new version.
  # Call generate_changelog_and_notes to update CHANGELOG.md and create a notes file.
  # Capture the path to the notes file so GitHub release creation can use it.
  local notes_file
  notes_file="$(generate_changelog_and_notes "$new_version")"

  # Stage the pyproject.toml file so that the version bump is recorded in git.
  # Ensure this file is part of the upcoming release commit.
  # Help keep project metadata synchronized with release history.
  git add pyproject.toml
  # Stage the CHANGELOG.md file if it exists in the repository.
  # Include the regenerated changelog in the release commit for documentation.
  # Rely on git-cliff having created or updated this file before this stage.
  [[ -f CHANGELOG.md ]] && git add CHANGELOG.md

  # Create a commit that encapsulates both the version bump and the changelog update.
  # Use a descriptive commit message including channel and version information.
  # Treat this commit as the canonical representation of the release in git history.
  # Use --no-verify to skip pre-commit hooks that might interfere with release automation.
  git commit --no-verify -m "Release ${channel} ${new_version}"

  # Remove any previously built artifacts under the dist directory.
  # Clean the build output so no stale artifacts from earlier releases remain.
  # Prepare a fresh build environment for uv build to run in the next step.
  rm -rf dist/

  # Run uv sync to align the local environment with project dependency specifications.
  # Ensure that any changes in pyproject or lockfile are applied before building.
  # Help promote reproducible builds across different machines or CI environments.
  uv sync
  # Run uv build to create distribution artifacts for the project.
  # Expect uv to build wheels and source distributions into the dist directory.
  # Use these artifacts later when creating GitHub releases and publishing to PyPI.
  uv build

  # Commit uv.lock changes that may occur during sync/build.
  # Pre-commit hooks are skipped to avoid stashing/interference with release automation.
  if [[ -n $(git status --porcelain uv.lock) ]]; then
    git add uv.lock
    git commit --no-verify -m "chore: Update uv.lock for ${channel} ${new_version}" || true
  fi

  # Commit the built wheel to the branch so each branch tracks its versioned artifact.
  # This allows `just install` to work directly from the branch's committed wheel.
  # Each branch shows only its own versioned wheel in dist/.
  git add dist/
  git commit --no-verify -m "Add built wheel for ${channel} ${new_version}" || true

  # Create a git tag pointing to the newly created release commit.
  # Use the tag name constructed earlier (for example, v1.2.3).
  # Use this tag as the reference for GitHub releases and version identification.
  git tag "$tag"
  # Push both the branch and the new tag to the origin remote repository.
  # Ensure that the remote’s view of the repository includes this release state.
  # Allow GitHub to discover and use the tag for release creation.
  git push origin "$branch" "$tag"

  # Prepare a release title matching the tag for use in GitHub’s release listing.
  # Create a simple fallback notes message if no notes file is present or used.
  # Keep both values ready so gh release create can construct a complete release.
  local title="$tag"
  local fallback_notes="Automated ${channel} release ${new_version}"

  # Decide whether to mark the GitHub release as a pre-release based on the channel.
  # Treat alpha, beta, and rc channels as prereleases in GitHub’s UI.
  # Treat stable releases as fully official, non-prerelease releases.
  if [[ "$channel" == "alpha" || "$channel" == "beta" || "$channel" == "rc" ]]; then
    # Check for the presence of a non-empty notes file created by git-cliff.
    # Prefer to use this notes file as the GitHub release body when it exists.
    # Fall back to a short text description if the notes file is missing or empty.
    if [[ -n "$notes_file" && -s "$notes_file" ]]; then
      gh release create "$tag" dist/* --title "$title" --notes-file "$notes_file" --prerelease
    else
      gh release create "$tag" dist/* --title "$title" --notes "$fallback_notes" --prerelease
    fi
  else
    # Handle the GitHub release behavior for stable (non-prerelease) channels.
    # Again, prefer a notes file when available, otherwise use fallback text.
    # Avoid marking stable releases as prereleases in the GitHub interface.
    if [[ -n "$notes_file" && -s "$notes_file" ]]; then
      gh release create "$tag" dist/* --title "$title" --notes-file "$notes_file"
    else
      gh release create "$tag" dist/* --title "$title" --notes "$fallback_notes"
    fi
  fi

  # Decide whether to publish this release to PyPI based on the channel type and no_pypi flag.
  # Restrict PyPI uploading to stable releases and skip it for alpha/beta/rc.
  # Also skip PyPI if the --no-pypi flag was passed, even for stable releases.
  # Keep pre-release artifacts available only as GitHub releases by design.
  if [[ "$channel" == "stable" && -z "$no_pypi" ]]; then
    # CRITICAL SAFETY CHECK: Verify version string contains NO pre-release markers
    # This is a belt-and-suspenders check to prevent accidental PyPI publication of RC/beta/alpha
    # Only versions without "a", "b", or "rc" suffixes should reach PyPI
    if [[ "$new_version" == *a[0-9]* || "$new_version" == *b[0-9]* || "$new_version" == *rc[0-9]* ]]; then
      echo "❌ SAFETY ABORT: Version ${new_version} contains pre-release marker!" >&2
      echo "❌ Pre-release versions (alpha/beta/rc) must NEVER be published to PyPI!" >&2
      echo "❌ This indicates a configuration error. Please review channel settings." >&2
      exit 1
    fi

    # Ensure that UV_PUBLISH_TOKEN is set in the environment for stable releases.
    # Abort the script with a clear error if the token is missing.
    # Help avoid confusing authentication failures inside uv publish itself.
    if [[ -z "${UV_PUBLISH_TOKEN-}" ]]; then
      echo "Error: UV_PUBLISH_TOKEN is not set but a stable release was requested." >&2
      echo "Please export your PyPI token as UV_PUBLISH_TOKEN and rerun." >&2
      echo "Or use --no-pypi to skip PyPI publishing." >&2
      exit 1
    fi

    # Final confirmation before PyPI publish with explicit safety messaging
    echo ""
    echo "🚨 PUBLISHING TO PyPI 🚨"
    echo "  Channel: ${channel}"
    echo "  Version: ${new_version}"
    echo "  Branch:  ${branch}"
    echo ""

    # Inform the user that the stable version is being published to PyPI now.
    # Show the exact version being uploaded to aid in tracking and debugging.
    # Invoke uv publish directly, relying on UV_PUBLISH_TOKEN already being exported.
    echo "Publishing stable version ${new_version} to PyPI with uv publish..."
    uv publish

    echo ""
    echo "✅ Successfully published version ${new_version} to PyPI"
    echo ""
  else
    # Log that PyPI publishing is intentionally skipped.
    # Provide clear reasoning based on either channel type or no_pypi flag.
    # Keep this message informational so users understand the publish policy.
    if [[ "$channel" == "stable" && -n "$no_pypi" ]]; then
      echo "Skipping PyPI publish for stable channel (--no-pypi flag set)."
    else
      echo "Skipping PyPI publish for non-stable channel '${channel}'."
    fi
  fi

  # Remove the temporary notes file immediately after use (belt-and-suspenders cleanup).
  # This file was created by git-cliff and is already tracked in RELEASE_NOTES_FILES array.
  # Clean it up right after the release for tidiness, though trap cleanup will also catch it.
  # This provides immediate cleanup rather than waiting until script exit.
  if [[ -n "$notes_file" && -f "$PROJECT_ROOT/$notes_file" ]]; then
    rm -f "$PROJECT_ROOT/$notes_file" 2>/dev/null || true
    echo "✓ Cleaned up: $notes_file" >&2
  fi

  # Print a final message indicating completion of release work for this channel.
  # Include the channel and branch in the message to provide clear context.
  # Follow with a blank line to visually separate this release from any subsequent one.
  echo "Finished release for channel '${channel}' (branch '${branch}')."

  # Sync master branch to main after stable releases to keep them identical.
  # This ensures main always reflects the latest stable production code.
  # Only perform this sync when releasing the stable channel from master branch.
  if [[ "$channel" == "stable" && "$branch" == "master" ]]; then
    echo ""
    echo "🔄 Syncing master → main (keeping main up to date)..."

    # Checkout main branch to prepare for sync using the safe switch function
    switch_to_branch main

    # Reset main to exactly match master (hard reset)
    git reset --hard master

    # Push main to origin, forcing if necessary to ensure sync
    git push origin main --force-with-lease

    echo "✅ main branch synced with master"
  fi

  echo
}

# Announce the start of the multi-channel release process for this run.
# Print a single line so users know the script is beginning its work.
# Rely on later detailed logs from release_channel for more granular information.
echo "Starting multi-channel release (if configured)..."

# Check whether an alpha branch has been configured for this invocation.
# Call release_channel for the alpha channel if alpha_branch is non-empty.
# Skip alpha release entirely if alpha_branch was never set.
if [[ -n "$alpha_branch" ]]; then
  release_channel "alpha" "$alpha_branch"
fi

# Check whether a beta branch has been configured for this invocation.
# Invoke release_channel for the beta channel when beta_branch has a value.
# Skip beta release if beta_branch remains empty.
if [[ -n "$beta_branch" ]]; then
  release_channel "beta" "$beta_branch"
fi

# Check whether an rc branch has been configured for this script run.
# Run release_channel for the rc channel when rc_branch is set.
# Skip rc processing when rc_branch is not specified.
if [[ -n "$rc_branch" ]]; then
  release_channel "rc" "$rc_branch"
fi

# Check whether a stable branch has been configured for this script run.
# Invoke release_channel for the stable channel when stable_branch is non-empty.
# Skip stable release when stable_branch was left unset.
if [[ -n "$stable_branch" ]]; then
  release_channel "stable" "$stable_branch"
fi

# Print a final confirmation that all requested channels were processed.
# Mention the branch that was originally active so users know the initial context.
echo "All requested channels processed. Original branch was '$start_branch'."
echo ""

# Explicitly clean up temporary files created during the release process.
# This deletes only the files we explicitly tracked in RELEASE_NOTES_FILES array.
# Manual cleanup is safer than automatic trap which can have unexpected side effects.
cleanup_temporary_files

# Explicitly restore the original branch that was active when the script started.
# Manual branch restoration gives us full control and visibility over branch state.
# This ensures the user is left on their original branch after the script completes.
restore_original_branch
