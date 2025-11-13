"""
Frame Rendering Accuracy Tests

Tests that svg2fbf produces pixel-perfect output by:
1. Rendering input SVG frames to PNG (ground truth)
2. Generating FBF animation with svg2fbf
3. Capturing animation frames as PNG
4. Comparing pixel-by-pixel (fail-fast on first difference)

Test Strategy:
- Random SVG selection from validated pool
- Multiple batch sizes (2, 5, 10, 50 frames)
- Fail-fast: Stop at first frame difference
- Detailed error reporting with frame metadata
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.utils.batch_generator import BatchGenerator
from tests.utils.config import get_test_config
from tests.utils.html_report import HTMLReportGenerator
from tests.utils.image_comparison import ImageComparator
from tests.utils.puppeteer_renderer import PuppeteerRenderer
from tests.utils.svg2fbf_frame_processor import SVG2FBFFrameProcessor
from tests.utils.svg_validator import SVGValidator

# Load test configuration from pyproject.toml
# Why: Single source of truth - all defaults come from pyproject.toml
TEST_CONFIG = get_test_config()

# Test Configuration - ALL values read from pyproject.toml
# NO hardcoded values allowed! Edit pyproject.toml to change defaults.
TEST_FPS = TEST_CONFIG.fps  # Read from pyproject.toml
TEST_ANIMATION_TYPE = TEST_CONFIG.animation_type  # Read from pyproject.toml
TEST_PRECISION_DIGITS = TEST_CONFIG.precision_digits  # Read from pyproject.toml
TEST_PRECISION_CDIGITS = TEST_CONFIG.precision_cdigits  # Read from pyproject.toml
# DEPRECATED: TEST_WIDTH and TEST_HEIGHT are no longer used
# Why: Viewport now dynamically matches first SVG frame's actual dimensions
# This ensures SVGs of any size (4K, custom resolutions) are rendered
# without truncation/distortion
TEST_WIDTH = 1920  # DEPRECATED - kept only for reference, not used
TEST_HEIGHT = 1080  # DEPRECATED - kept only for reference, not used


@pytest.fixture(scope="session")
def svg_validator(tests_dir):
    """
    SVG validator instance (session-scoped)

    Why session scope:
    - Validation cache shared across all tests
    - Avoid re-validating same files multiple times
    """
    cache_file = tests_dir / "invalid_svg_example_frames.json"
    return SVGValidator(cache_file=cache_file, puppeteer_renderer=None)


@pytest.fixture(scope="session")
def batch_generator(examples_dir, svg_validator):
    """
    Test batch generator (session-scoped)

    Creates random batches of validated SVGs for testing.

    Why session scope:
    - SVG pool validation happens once at start
    - Expensive operation, don't repeat per test
    """
    return BatchGenerator(examples_dir=examples_dir, svg_validator=svg_validator)


@pytest.fixture(scope="session")
def puppeteer_renderer(node_scripts_dir):
    """
    Puppeteer renderer instance (session-scoped)

    Renders SVGs and captures animation frames.

    Why session scope:
    - Shared across tests
    - Setup verification happens once
    """
    return PuppeteerRenderer(node_scripts_dir=node_scripts_dir)


@pytest.fixture(scope="session")
def image_comparator():
    """
    Image comparator instance (session-scoped)

    Performs pixel-perfect image comparison.

    Why session scope:
    - Stateless utility, can be shared
    - No per-test initialization needed
    """
    return ImageComparator()


@pytest.mark.parametrize("frame_count", [2, 3, 15])
def test_frame_rendering_accuracy(
    frame_count: int,
    batch_generator: BatchGenerator,
    puppeteer_renderer: PuppeteerRenderer,
    image_comparator: ImageComparator,
    tmp_path: Path,
    request,
    preserve_artifacts,
    test_session,
):
    """
    Test that FBF animation renders frames identical to input SVGs

    Test Flow:
    1. Generate random batch of N SVG frames (validated) OR use saved session
    2. Render each input SVG to PNG (ground truth)
    3. Execute svg2fbf to generate .fbf.svg
    4. Capture animation frames from .fbf.svg as PNGs
    5. Compare input vs output PNGs pixel-by-pixel
    6. FAIL FAST if any difference found, report frame details
    7. Save session if --save-session provided (enables future replication)

    Args:
        frame_count: Number of frames to test (2, 5, 10, or 50)
        batch_generator: Fixture providing validated SVG batches
        puppeteer_renderer: Fixture providing rendering capability
        image_comparator: Fixture providing pixel comparison
        tmp_path: pytest fixture for temporary directory
        request: pytest fixture for test config
        preserve_artifacts: Fixture for preserving test artifacts
        test_session: Fixture for session save/load management

    Why parametrize:
        Different batch sizes can expose different bugs

    Session Management:
        --save-session: Save inputs for deterministic replication
        --use-session: Run test with exact saved inputs (regression testing)
    """
    print(f"\n{'=' * 80}")
    print(f"Testing {frame_count}-frame animation")
    print(f"{'=' * 80}\n")

    # Setup directories
    # Why: Organize intermediate files for debugging
    input_frames_dir = tmp_path / "input_frames"
    output_frames_dir = tmp_path / "output_frames"
    fbf_output_dir = tmp_path / "fbf_output"

    input_frames_dir.mkdir()
    output_frames_dir.mkdir()
    fbf_output_dir.mkdir()

    # Step 1: Generate or load test batch and establish session_id
    # Why: Need session_id for organizing results by input folder
    session_id = None

    if test_session.should_use_saved_inputs():
        # Using saved session - copy saved batch to tmp_path
        saved_batch_dir = test_session.get_saved_batch_dir()
        batch_dir = tmp_path / "batch_from_session"
        shutil.copytree(saved_batch_dir, batch_dir)

        # Reconstruct batch_info from saved metadata
        saved_meta = test_session.get_saved_metadata()
        session_id = saved_meta.get("session_id")
        svg_sources = [Path(p) for p in saved_meta.get("svg_sources", [])]
        frame_files = sorted(batch_dir.glob("frame_FRAME*.svg"))

        # SAFEGUARD: Verify input batch matches saved session
        # Why: Ensure we're testing with exact same inputs as previous runs
        import hashlib  # MOVED: Import at function scope to avoid UnboundLocalError

        saved_input_hashes = []
        current_input_hashes = []

        print("📦 Using saved session batch:")
        print(f"   Session ID: {session_id}")
        print(f"   Batch directory: {batch_dir}")
        print("   Verifying input consistency with saved session...")

        for i, (saved_path, current_file) in enumerate(zip(svg_sources, frame_files, strict=False)):
            # Compute hash of saved SVG (from metadata)
            if saved_path.exists():
                with open(saved_path, "rb") as f:
                    saved_hash = hashlib.sha256(f.read()).hexdigest()[:16]
                saved_input_hashes.append(saved_hash)
            else:
                # Original file deleted - can't verify
                saved_hash = "DELETED"  # FIXED: Define saved_hash in else block for comparison
                saved_input_hashes.append(saved_hash)

            # Compute hash of current batch file (copied to tmp)
            with open(current_file, "rb") as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()[:16]
            current_input_hashes.append(current_hash)

            match_status = "✓" if saved_hash == current_hash else "✗"
            print(f"       Frame {i + 1}: {match_status} (saved={saved_hash}, current={current_hash})")

        # SAFEGUARD: Fail if input files don't match
        # Why: Catch bugs where wrong files were loaded or corrupted
        if saved_input_hashes != current_input_hashes:
            mismatches = [i + 1 for i, (s, c) in enumerate(zip(saved_input_hashes, current_input_hashes, strict=False)) if s != c]
            raise ValueError(
                f"CRITICAL BUG: Input batch files don't match saved session!\nSession: {session_id}\nMismatched frames: {mismatches}\nThis indicates:\n  1. Saved session files were modified/corrupted, OR\n  2. Wrong session was loaded\nSaved hashes:  {saved_input_hashes}\nCurrent hashes: {current_input_hashes}"
            )

        print(f"   ✓ All {len(frame_files)} input files match saved session\n")

        batch_info = {
            "batch_dir": batch_dir,
            "svg_sources": svg_sources,
            "frame_files": frame_files,
        }
    else:
        # Generate new random batch
        print(f"📦 Generating test batch with {frame_count} random SVGs...")
        batch_info = batch_generator.generate_batch(
            frame_count=frame_count,
            output_dir=tmp_path,
            batch_name=f"batch_{frame_count}frames",
        )
        batch_dir = batch_info["batch_dir"]

    # Step 2: Render input SVGs to PNGs (ground truth)
    # Why: These are the expected frame outputs
    print(f"🎨 Rendering {frame_count} input SVGs to PNG (ground truth)...")

    # DEBUG: Show BOTH original sources and copied files
    print("   [DEBUG] Original SVG sources:")
    for i, svg_file in enumerate(batch_info["svg_sources"]):
        print(f"           Frame {i + 1}: {svg_file}")
    print("   [DEBUG] Copied batch files (what test renders):")
    for i, svg_file in enumerate(batch_info["frame_files"]):
        size = Path(svg_file).stat().st_size if Path(svg_file).exists() else 0
        print(f"           Frame {i + 1}: {svg_file} ({size} bytes)")

    # DEBUG: Verify copies match originals
    print("   [DEBUG] Verifying copies:")
    for i in range(len(batch_info["frame_files"])):
        orig = Path(batch_info["svg_sources"][i])
        copy = Path(batch_info["frame_files"][i])
        orig_size = orig.stat().st_size if orig.exists() else 0
        copy_size = copy.stat().st_size if copy.exists() else 0
        match = "✓ MATCH" if orig_size == copy_size else f"✗ MISMATCH ({orig_size} vs {copy_size})"
        print(f"           Frame {i + 1}: {match}")

    # Use svg2fbf_frame_processor to calculate dimensions and transforms
    # Why: Ensures test uses EXACT same logic as svg2fbf.py for transforms
    # This guarantees pixel-perfect matching by using svg2fbf's actual code
    print("   [INFO] Using svg2fbf_frame_processor for dimension/transform calculation")
    # CRITICAL: Use same precision for transform calculation as FBF generation
    # Why: Precision mismatch causes accumulated rounding errors
    frame_processor = SVG2FBFFrameProcessor(digits=TEST_PRECISION_DIGITS, cdigits=TEST_PRECISION_CDIGITS)

    # Process first frame to establish canonical dimensions
    # Why: svg2fbf uses first frame's viewBox as canonical for entire animation
    first_svg_path = batch_info["frame_files"][0]
    first_width, first_height, first_viewbox, _, _ = frame_processor.process_frame(first_svg_path)

    print("   [DEBUG] First frame dimensions (from svg2fbf):")
    print(f"           Width:   {first_width}")
    print(f"           Height:  {first_height}")
    print(f"           ViewBox: {first_viewbox}")

    # Store first frame dimensions for subsequent frames
    first_frame_dimensions = (first_width, first_height, first_viewbox)

    # Determine session_id based on whether we're using saved session
    # or generating new
    # Why: When replaying with --use-session, preserve original session_id
    # for results organization
    if test_session.should_use_saved_inputs():
        # Using saved session: extract session_id from loaded metadata
        # Why: Results should be organized under same session_id for
        # comparison across runs
        saved_metadata = test_session.get_saved_metadata()
        session_id = saved_metadata.get("session_id")

        # SAFEGUARD: Validate session_id was extracted correctly
        # Why: Prevent bug where --use-session creates new session instead
        # of reusing existing
        if not session_id:
            raise ValueError("CRITICAL BUG: session_id is None when replaying saved session! This indicates saved_metadata is missing session_id field. Check session metadata structure.")

        # SAFEGUARD: Validate session_id matches expected pattern
        # Why: Catch corruption or invalid session_id early
        import re

        if not re.match(r"^session_\d{3}_\d+frames$", session_id):
            raise ValueError(f"CRITICAL BUG: Invalid session_id format: '{session_id}'. Expected pattern: 'session_NNN_Mframes' (e.g., 'session_044_3frames'). This indicates session metadata corruption.")

        print(f"\n♻️  Replaying existing session: {session_id}")
        print(f"   Results will be saved to: tests/results/{session_id}/<new_timestamp>/\n")
    else:
        # Generating new inputs: save as new session
        # Why: New inputs need new session_id to preserve input folder for future replay
        session_info = test_session.save_after_test(
            frame_count=frame_count,
            input_batch_dir=batch_dir,
            test_config={
                "width": int(first_width),  # Use actual SVG dimensions, not fixed 1920x1080
                "height": int(first_height),
                "fps": TEST_FPS,
                "animation_type": TEST_ANIMATION_TYPE,
                "digits": TEST_PRECISION_DIGITS,
                "cdigits": TEST_PRECISION_CDIGITS,
            },
            svg_sources=batch_info["svg_sources"],
        )

        # If save_after_test returns None (no --save-session), force auto-save
        # Why: Without saved session, input SVGs are lost (/tmp wiped on reboot)
        if not session_info:
            # Directly call session manager to force save with auto-generated ID
            from tests.utils.session_manager import SessionManager

            session_mgr = SessionManager(Path(__file__).parent / "sessions")
            session_info = session_mgr.save_session(
                frame_count=frame_count,
                input_batch_dir=batch_dir,
                test_config={
                    "width": int(first_width),  # Use actual SVG dimensions, not fixed 1920x1080
                    "height": int(first_height),
                    "fps": TEST_FPS,
                    "animation_type": TEST_ANIMATION_TYPE,
                    "digits": TEST_PRECISION_DIGITS,
                    "cdigits": TEST_PRECISION_CDIGITS,
                },
                svg_sources=batch_info["svg_sources"],
                session_id=None,  # Auto-generate ID
            )

        session_id = session_info.session_id

        # SAFEGUARD: Validate new session_id format
        # Why: Catch session manager bugs early
        import re

        if not re.match(r"^session_\d{3}_\d+frames$", session_id):
            raise ValueError(f"CRITICAL BUG: Session manager generated invalid session_id: '{session_id}'. Expected pattern: 'session_NNN_Mframes'. This indicates a bug in SessionManager.save_session().")

        print(f"\n💾 Session: {session_id}")
        print(f"   Location: tests/sessions/{session_id}/")
        print(f"   Replay with: pytest --use-session={session_id}\n")

    # SAFEGUARD: Final validation that session_id is set
    # Why: Absolute fail-safe to prevent None session_id reaching
    # preserve_artifacts
    assert session_id is not None, "CRITICAL BUG: session_id is None after session management! This should be impossible."
    assert isinstance(session_id, str) and len(session_id) > 0, f"CRITICAL BUG: session_id is invalid: {repr(session_id)}"

    # SAFEGUARD: Store initial session_id for immutability verification
    # Why: Catch bugs where session_id accidentally changes mid-test
    INITIAL_SESSION_ID = session_id  # Must never change throughout test
    print(f"🔒 Session ID locked: {INITIAL_SESSION_ID}\n")

    def verify_session_immutability(location: str):
        """
        SAFEGUARD: Verify session_id hasn't changed since initialization

        Args:
            location: Where in the test this check is happening (for error message)
        """
        if session_id != INITIAL_SESSION_ID:
            raise RuntimeError(f"CRITICAL BUG: session_id changed mid-test at {location}!\nInitial:  {INITIAL_SESSION_ID}\nCurrent:  {session_id}\nThis indicates a catastrophic bug in test code that modifies session_id.")

    def preserve_artifacts_with_verification(location: str, **kwargs):
        """
        SAFEGUARD: Wrap preserve_artifacts() with comprehensive validation

        Verifies:
        1. session_id hasn't changed mid-test
        2. session_id matches the directory structure
        3. Timestamp folder count increases by exactly 1
        4. Results are saved in correct session directory

        Args:
            location: Where this is being called (for error messages)
            **kwargs: Arguments to pass to preserve_artifacts()
        """
        # SAFEGUARD 1: Verify session_id immutability
        verify_session_immutability(f"before preserve_artifacts at {location}")

        # SAFEGUARD 2: Count existing timestamp folders before preserving
        tests_dir = Path(__file__).parent
        session_results_dir = tests_dir / "results" / INITIAL_SESSION_ID

        if session_results_dir.exists():
            existing_timestamps = [d for d in session_results_dir.iterdir() if d.is_dir()]
            timestamp_count_before = len(existing_timestamps)
        else:
            timestamp_count_before = 0

        print(f"\n🔍 Pre-preservation checks at {location}:")
        print(f"   Session ID: {INITIAL_SESSION_ID}")
        print(f"   Existing timestamp folders: {timestamp_count_before}")

        # SAFEGUARD 3: Verify session_id in kwargs matches INITIAL_SESSION_ID
        if "session_id" in kwargs and kwargs["session_id"] != INITIAL_SESSION_ID:
            raise RuntimeError(f"CRITICAL BUG: preserve_artifacts called with wrong session_id!\nExpected (INITIAL): {INITIAL_SESSION_ID}\nReceived (kwargs):  {kwargs['session_id']}\nLocation: {location}")

        # Call actual preserve_artifacts
        result_dir = preserve_artifacts(**kwargs)

        # SAFEGUARD 4: Verify timestamp folder count increased by 1
        existing_timestamps_after = [d for d in session_results_dir.iterdir() if d.is_dir()]
        timestamp_count_after = len(existing_timestamps_after)

        if timestamp_count_after != timestamp_count_before + 1:
            raise RuntimeError(
                f"CRITICAL BUG: Timestamp folder count did not increase by 1!\nBefore: {timestamp_count_before}\nAfter:  {timestamp_count_after}\nExpected: {timestamp_count_before + 1}\nLocation: {location}\nSession: {INITIAL_SESSION_ID}\nThis indicates preserve_artifacts() failed to create new timestamped folder."
            )

        # SAFEGUARD 5: Verify result_dir is in correct session directory
        if not str(result_dir).startswith(str(session_results_dir)):
            raise RuntimeError(f"CRITICAL BUG: Results saved to wrong session directory!\nExpected parent: {session_results_dir}\nActual path:     {result_dir}\nLocation: {location}")

        # SAFEGUARD 6: Verify new timestamp folder exists and is a directory
        if not result_dir.exists() or not result_dir.is_dir():
            raise RuntimeError(f"CRITICAL BUG: Result directory does not exist or is not a directory!\nPath: {result_dir}\nLocation: {location}")

        print(f"   ✓ New timestamp folder created: {result_dir.name}")
        print(f"   ✓ Timestamp folder count: {timestamp_count_before} → {timestamp_count_after}")
        print("   ✓ All integrity checks passed\n")

        return result_dir

    # Render each input frame with svg2fbf's calculated dimensions and
    # transform
    # Why: properlySizeDoc() transforms frames to match first frame dimensions
    # - this is ESSENTIAL when frames have different sizes/viewBox/resolution
    # from the first frame
    input_pngs = []
    for i, svg_file in enumerate(batch_info["frame_files"]):
        png_path = input_frames_dir / f"input_frame_{i + 1:04d}.png"

        # Process frame using svg2fbf's exact logic (including
        # properlySizeDoc())
        # CRITICAL: properlySizeDoc() is NECESSARY to transform content
        # when frames have different dimensions
        # First frame: no transform (None)
        # Subsequent frames: transform to match first frame dimensions
        if i == 0:
            # First frame: no transform needed
            width, height, viewbox, transform = (
                first_width,
                first_height,
                first_viewbox,
                None,
            )
        else:
            # Subsequent frame: calculate transform using svg2fbf's logic
            # This calls properlySizeDoc() which transforms the frame to match
            # first frame dimensions
            width, height, viewbox, transform, _ = frame_processor.process_frame(svg_file, first_frame_dimensions=first_frame_dimensions)

            # SAFEGUARD: Verify subsequent frame has EXACTLY the first frame's
            # dimensions
            # Why: FBF animations require all frames to share the same
            # resolution/viewBox
            if width != first_width:
                raise RuntimeError(f"CRITICAL BUG: Frame {i + 1} has wrong width!\nExpected (first frame): {first_width}\nGot (frame {i + 1}):      {width}\nFrame processor MUST return first frame's width for all subsequent frames!")
            if height != first_height:
                raise RuntimeError(f"CRITICAL BUG: Frame {i + 1} has wrong height!\nExpected (first frame): {first_height}\nGot (frame {i + 1}):      {height}\nFrame processor MUST return first frame's height for all subsequent frames!")
            if viewbox != first_viewbox:
                raise RuntimeError(f"CRITICAL BUG: Frame {i + 1} has wrong viewBox!\nExpected (first frame): {first_viewbox}\nGot (frame {i + 1}):      {viewbox}\nFrame processor MUST return first frame's viewBox for all subsequent frames!")

        print(f"   [DEBUG] Frame {i + 1}:")
        print(f"           Width:       {width}")
        print(f"           Height:      {height}")
        print(f"           ViewBox:     {viewbox}")
        print(f"           Transform:   {transform if transform else '(none - first frame)'}")

        # Render with the viewBox from process_frame()
        # (includes properlySizeDoc() transformations)
        # CRITICAL: Use the transformed viewBox, NOT the original!
        # Why: When frames have different dimensions, properlySizeDoc()
        # transforms them to fit the first frame's resolution/viewBox.
        # Without this, frames won't match!
        # The viewport size determines the PNG pixel dimensions
        # (not the SVG internal coordinates)
        # Check if no-keep-ratio is enabled
        # Why: For animations with negative viewBox, omit preserveAspectRatio
        # to avoid clipping
        # CRITICAL: Use empty string "" (not "none") to omit attribute entirely
        # Why: "none" is a valid SVG value that still affects rendering
        #      Empty string tells render_svg.js to NOT SET the attribute at all
        no_keep_ratio = request.config.getoption("--no-keep-ratio")
        preserve_aspect_ratio_value = "" if no_keep_ratio else "xMidYMid meet"

        success = puppeteer_renderer.render_svg_to_png(
            svg_path=svg_file,
            output_png_path=png_path,
            width=int(first_width),  # Use first frame's width for viewport
            height=int(first_height),  # Use first frame's height for viewport
            transform=transform,  # svg2fbf's exact transform (None for first)
            viewbox=viewbox,  # CRITICAL: Use transformed viewBox!
            preserve_aspect_ratio=preserve_aspect_ratio_value,
        )

        assert success, f"Failed to render input SVG: {svg_file}"
        input_pngs.append(png_path)

    print(f"   ✓ All {frame_count} input frames rendered\n")

    # Step 3: Execute svg2fbf to generate .fbf.svg
    # Why: This is what we're testing - the svg2fbf program
    print("🔨 Executing svg2fbf to generate FBF animation...")
    fbf_output_file = fbf_output_dir / "test_animation.fbf.svg"

    # Get no-keep-ratio option from pytest config
    # Why: Pass to svg2fbf to conditionally omit preserveAspectRatio attribute
    no_keep_ratio = request.config.getoption("--no-keep-ratio")

    svg2fbf_cmd = [
        "uv",
        "run",
        "svg2fbf",
        f"--input_folder={batch_dir}",
        f"--output_path={fbf_output_dir}",
        "--filename=test_animation.fbf.svg",
        f"--speed={TEST_FPS}",
        f"--animation_type={TEST_ANIMATION_TYPE}",  # MUST be "once"
        f"--digits={TEST_PRECISION_DIGITS}",
        f"--cdigits={TEST_PRECISION_CDIGITS}",
        # DEBUG: Removed --quiet to see svg2fbf output
        # "--quiet"
    ]

    # Add --no-keep-ratio if option is enabled
    # Why: For animations with negative viewBox coordinates
    if no_keep_ratio:
        svg2fbf_cmd.append("--no-keep-ratio")

    # DEBUG: Print command being executed
    print("   [DEBUG] svg2fbf command:")
    print(f"           {' '.join(svg2fbf_cmd)}")
    print("   [DEBUG] Input folder contents:")
    for f in sorted(Path(batch_dir).iterdir()):
        print(f"           {f.name}")

    result = subprocess.run(
        svg2fbf_cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 minute timeout for large batches
    )

    # DEBUG: Print svg2fbf output
    print("   [DEBUG] svg2fbf stdout:")
    if result.stdout:
        for line in result.stdout.splitlines()[:20]:  # First 20 lines
            print(f"           {line}")
    print("   [DEBUG] svg2fbf stderr:")
    if result.stderr:
        for line in result.stderr.splitlines()[:20]:
            print(f"           {line}")

    # Check svg2fbf succeeded
    # Why: Can't test output if generation failed
    assert result.returncode == 0, f"svg2fbf failed:\n  stdout: {result.stdout}\n  stderr: {result.stderr}"

    assert fbf_output_file.exists(), f"svg2fbf succeeded but output file not created: {fbf_output_file}"

    print(f"   ✓ FBF animation generated: {fbf_output_file.name}\n")

    # Step 4: Capture animation frames from .fbf.svg
    # Why: Need to see what FBF animation actually renders
    # CRITICAL: Use first frame's dimensions to match input rendering
    print(f"📹 Capturing {frame_count} frames from FBF animation...")
    output_pngs = puppeteer_renderer.render_fbf_animation_frames(
        fbf_svg_path=fbf_output_file,
        output_dir=output_frames_dir,
        frame_count=frame_count,
        fps=TEST_FPS,
        width=int(first_width),  # Use first frame's dimensions, not fixed 1920
        height=int(first_height),  # Use first frame's dimensions, not fixed 1080
    )

    # Check all frames captured
    # Why: Can't compare if frames missing
    assert len(output_pngs) == frame_count, f"Expected {frame_count} output frames, got {len(output_pngs)}"

    print(f"   ✓ All {frame_count} animation frames captured\n")

    # Step 5: Compare frames pixel-by-pixel
    # Why: Validate FBF animation produces identical output
    print(f"🔍 Comparing {frame_count} frame pairs pixel-by-pixel...")

    # Check if HTML report generation is enabled
    # Why: HTML report mode collects all comparisons instead of failing fast
    generate_html_report = request.config.getoption("--html-report")

    # Collect comparison results for HTML report
    # Why: Need all frame data for comprehensive report
    frame_comparisons = []
    failed_frames = []

    # Get tolerance thresholds from CLI options
    # Why: Allow configurable pixel and image-level difference thresholds
    # (see tests/ISSUES.md)
    image_tolerance = request.config.getoption("--image-tolerance")
    pixel_tolerance = request.config.getoption("--pixel-tolerance")

    for i in range(frame_count):
        input_png = input_pngs[i]
        output_png = output_pngs[i]
        source_svg = batch_info["svg_sources"][i]

        # CRITICAL: Detect empty/truncated content BEFORE comparison
        # Why: Prevents false positives where both images are broken
        # identically
        # Example: Both input and output have truncated seagull → pixel match
        # but WRONG result
        input_has_issue, input_issue_info = image_comparator.detect_empty_or_truncated_content(input_png)
        output_has_issue, output_issue_info = image_comparator.detect_empty_or_truncated_content(output_png)

        # FAIL IMMEDIATELY if either image has rendering issues
        if input_has_issue:
            relative_source = source_svg.relative_to(source_svg.parent.parent)
            error_msg = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   INPUT FRAME HAS RENDERING ISSUES                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Frame {i + 1}/{frame_count} input PNG has empty or truncated content!


📍 Frame Information:
   Input PNG:   {input_png.name}
   Source SVG:  {relative_source}
   Full path:   {source_svg}

🔍 Rendering Issue Details:
   Is Empty:         {input_issue_info.get("is_empty", False)}
   Is Truncated:     {input_issue_info.get("is_truncated", False)}
   Uniform Ratio:    {input_issue_info.get("uniform_pixel_ratio", 0.0):.2%}
   Edge Emptiness:   {input_issue_info.get("edge_emptiness", 0.0):.2%}
   Center Fullness:  {input_issue_info.get("center_fullness", 0.0):.2%}
   Most Common Color: {input_issue_info.get("most_common_color", "N/A")}
   Dimensions:       {input_issue_info.get("dimensions", "N/A")}

⚠️  This indicates the INPUT SVG failed to render correctly!
   Possible causes:
   - viewBox doesn't encompass all content (content is clipped)
   - Negative viewBox coordinates causing truncation
   - preserveAspectRatio causing unexpected clipping
   - SVG is actually empty (no visible content)

💡 Next steps:
   1. Inspect the source SVG viewBox attribute
   2. Check if content coordinates extend beyond viewBox bounds
   3. Consider implementing viewBox auto-correction (ISSUES.md #3)
   4. Manually verify SVG renders correctly in browser

📁 File Locations:
   Input PNG:   {input_png}
   Source SVG:  {source_svg}
"""
            pytest.fail(error_msg)

        if output_has_issue:
            relative_source = source_svg.relative_to(source_svg.parent.parent)
            error_msg = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   OUTPUT FRAME HAS RENDERING ISSUES                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Frame {i + 1}/{frame_count} output PNG (from FBF animation) has empty or
truncated content!

📍 Frame Information:
   Output PNG:  {output_png.name}
   FBF file:    {fbf_output_file.name}
   Source SVG:  {relative_source}

🔍 Rendering Issue Details:
   Is Empty:         {output_issue_info.get("is_empty", False)}
   Is Truncated:     {output_issue_info.get("is_truncated", False)}
   Uniform Ratio:    {output_issue_info.get("uniform_pixel_ratio", 0.0):.2%}
   Edge Emptiness:   {output_issue_info.get("edge_emptiness", 0.0):.2%}
   Center Fullness:  {output_issue_info.get("center_fullness", 0.0):.2%}
   Most Common Color: {output_issue_info.get("most_common_color", "N/A")}
   Dimensions:       {output_issue_info.get("dimensions", "N/A")}

⚠️  This indicates the FBF ANIMATION failed to render correctly!
   Possible causes:
   - svg2fbf generated incorrect viewBox/transform
   - Animation timing issue (captured wrong moment)
   - Browser rendering issue in Puppeteer

📁 File Locations:
   Output PNG:  {output_png}
   FBF file:    {fbf_output_file}
   Source SVG:  {source_svg}
"""
            pytest.fail(error_msg)

        # Both images are valid - proceed with pixel comparison
        is_identical, diff_info = image_comparator.compare_images_pixel_perfect(
            input_png,
            output_png,
            tolerance=image_tolerance,
            pixel_tolerance=pixel_tolerance,
        )

        # Generate grayscale diff map for HTML report
        # Why: Visual measurement of difference intensity
        diff_gray_path = None
        if generate_html_report:
            diff_gray_path = output_frames_dir / f"diff_gray_{i + 1:04d}.png"
            image_comparator.generate_grayscale_diff_map(input_png, output_png, diff_gray_path)

        # Store comparison result
        # Why: Need for HTML report generation
        frame_comparisons.append(
            {
                "frame_num": i + 1,
                "input_png": input_png,
                "output_png": output_png,
                "diff_gray": diff_gray_path,
                "diff_percentage": diff_info.get("diff_percentage", 0.0),
                "diff_pixels": diff_info.get("diff_pixels", 0),
                "total_pixels": diff_info.get("total_pixels", 0),
                "source_svg": source_svg,
                "is_identical": is_identical,
            }
        )

        if not is_identical:
            failed_frames.append((i + 1, diff_info, source_svg, input_png, output_png))

            # FAIL FAST mode: Stop at first difference
            # Why: Save time if not generating HTML report
            if not generate_html_report:
                relative_source = source_svg.relative_to(source_svg.parent.parent)

                error_msg = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        FRAME RENDERING MISMATCH DETECTED                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Frame {i + 1}/{frame_count} FAILED pixel-perfect comparison!

📍 Frame Information:
   Input PNG:   {input_png.name}
   Output PNG:  {output_png.name}
   Source SVG:  {relative_source}
   Full path:   {source_svg}

🔬 Difference Details:
   Different pixels:  {diff_info.get("diff_pixels", "N/A"):,}
   Total pixels:      {diff_info.get("total_pixels", "N/A"):,}
   Difference:        {diff_info.get("diff_percentage", 0.0):.4f}%
   First diff at:     {diff_info.get("first_diff_location", "N/A")}
   Dimensions match:  {diff_info.get("dimensions_match", "N/A")}
   Image 1 size:      {diff_info.get("img1_size", "N/A")}
   Image 2 size:      {diff_info.get("img2_size", "N/A")}

⚙️  Test Configuration:
   Batch size:        {frame_count} frames
   FPS:               {TEST_FPS}
   Animation type:    {TEST_ANIMATION_TYPE}
   Viewport:          {int(first_width)}x{int(first_height)} (matches first SVG frame)
   Precision:         digits={TEST_PRECISION_DIGITS}, cdigits={TEST_PRECISION_CDIGITS}

📁 File Locations (for inspection):
   Input frames:      {input_frames_dir}
   Output frames:     {output_frames_dir}
   FBF SVG:           {fbf_output_file}
   Batch dir:         {batch_dir}

💡 Next Steps:
   1. Inspect the differing frames visually
   2. Check if source SVG has special features
   3. Run svg2fbf manually with these inputs for debugging
   4. Re-run with --html-report to see all frames

🛑 STOPPING TEST (fail-fast on first frame difference)
                """

                # Optionally generate diff image
                # Why: Visual diff helps identify patterns
                if request.config.getoption("--render-diffs"):
                    diff_image_path = output_frames_dir / f"diff_frame_{i + 1:04d}.png"
                    image_comparator.generate_diff_image(input_png, output_png, diff_image_path)
                    error_msg += f"\n📊 Diff image saved: {diff_image_path}\n"

                # Preserve artifacts before failing (for debugging/replication)
                # Why: /tmp gets wiped on reboot, need permanent record
                preserve_artifacts_with_verification(
                    location="fail-fast mode",
                    session_id=session_id,
                    fbf_file=fbf_output_file,
                    html_report=None,  # No HTML report in fail-fast mode
                    input_frames_dir=input_frames_dir,
                    output_frames_dir=output_frames_dir,
                )

                pytest.fail(error_msg)
            else:
                # HTML report mode: Continue collecting failures
                # Why: Need to generate comprehensive report with all frames
                print(f"   ✗ Frame {i + 1}/{frame_count} FAILED ({diff_info.get('diff_percentage', 0.0):.2f}% diff)")
        else:
            # Frame matched!
            print(f"   ✓ Frame {i + 1}/{frame_count} matched")

    # Generate HTML report if requested
    # Why: Comprehensive visual comparison of all frames
    if generate_html_report:
        print("\n📊 Generating HTML comparison report...")

        report_path = tmp_path / f"comparison_report_{frame_count}frames.html"

        test_config = {
            "frame_count": frame_count,
            "width": int(first_width),  # Use first frame's actual width (viewport matches SVG)
            "height": int(first_height),  # Use first frame's actual height (viewport matches SVG)
            "svg_width": first_width,  # First frame's actual SVG width
            "svg_height": first_height,  # First frame's actual SVG height
            "fps": TEST_FPS,
            "animation_type": TEST_ANIMATION_TYPE,
            "digits": TEST_PRECISION_DIGITS,
            "image_tolerance": image_tolerance,
            "pixel_tolerance": pixel_tolerance,
        }

        HTMLReportGenerator.generate_comparison_report(
            report_path=report_path,
            test_config=test_config,
            frame_comparisons=frame_comparisons,
            batch_info=batch_info,
        )

        print(f"   ✓ HTML report generated: {report_path}\n")

        # Preserve artifacts (including HTML report) before test completion
        # Why: /tmp gets wiped on reboot, need permanent record for debugging
        preserve_artifacts_with_verification(
            location="HTML report mode",
            session_id=session_id,
            fbf_file=fbf_output_file,
            html_report=report_path,
            input_frames_dir=input_frames_dir,
            output_frames_dir=output_frames_dir,
        )

        # Now fail if there were differences
        # Why: Test should fail even in HTML report mode
        if failed_frames:
            error_msg = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        FRAME RENDERING MISMATCHES DETECTED                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

{len(failed_frames)} of {frame_count} frames FAILED pixel-perfect comparison!

📊 HTML Report Generated: {report_path}

Failed frames: {", ".join(str(fn) for fn, _, _, _, _ in failed_frames)}

📁 File Locations:
   Input frames:      {input_frames_dir}
   Output frames:     {output_frames_dir}
   FBF SVG:           {fbf_output_file}
   Batch dir:         {batch_dir}

💡 Open the HTML report to inspect all frame comparisons visually.
            """
            pytest.fail(error_msg)

    # All frames matched! Preserve artifacts for reference
    # Why: Success artifacts useful for regression testing and documentation
    if not generate_html_report:
        # Only preserve if HTML report mode didn't already preserve
        preserve_artifacts_with_verification(
            location="success mode (non-HTML)",
            session_id=session_id,
            fbf_file=fbf_output_file,
            html_report=None,
            input_frames_dir=input_frames_dir,
            output_frames_dir=output_frames_dir,
        )

    print(f"\n{'=' * 80}")
    print(f"✅ SUCCESS: All {frame_count} frames rendered identically!")
    print(f"✅ Results saved to: tests/results/{session_id}/")
    print(f"{'=' * 80}\n")


def test_svg_pool_not_empty(batch_generator):
    """
    Sanity check: Ensure we have valid SVGs to test with

    Why:
        If no valid SVGs found, other tests will fail confusingly
        This test provides clear error message about the real issue
    """
    pool_size = batch_generator.get_svg_pool_size()

    assert pool_size > 0, "No valid SVG files found in examples/ folder. Check that examples/ exists and contains valid SVG files."

    print(f"\n✓ SVG pool contains {pool_size} valid SVGs\n")


def test_puppeteer_setup(puppeteer_renderer, tmp_path):
    """
    Sanity check: Ensure Puppeteer can render a simple SVG

    Why:
        If Puppeteer isn't working, all tests will fail
        This test isolates Puppeteer issues from svg2fbf issues
    """
    # Create minimal test SVG
    # Why: Don't depend on examples/ folder for this sanity check
    test_svg = tmp_path / "test.svg"
    test_svg.write_text("""
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100" height="100" fill="red"/>
    </svg>
    """)

    output_png = tmp_path / "test.png"

    success = puppeteer_renderer.render_svg_to_png(svg_path=test_svg, output_png_path=output_png, width=800, height=600)

    assert success, "Puppeteer failed to render simple test SVG"
    assert output_png.exists(), "Puppeteer did not create output PNG"

    print("\n✓ Puppeteer is working correctly\n")
