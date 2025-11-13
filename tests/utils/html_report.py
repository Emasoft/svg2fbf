"""
HTML Report Generator for Frame Comparison Tests

Generates visual comparison reports showing:
- Side-by-side input vs output frames
- Percentage differences
- Grayscale diff maps
"""

import base64
from datetime import datetime
from pathlib import Path
from typing import Any


class HTMLReportGenerator:
    """
    Generates HTML reports for frame comparison test results

    Why:
        Visual inspection is crucial for understanding rendering differences
        HTML format allows easy sharing and archiving of test results
    """

    @staticmethod
    def generate_comparison_report(
        report_path: Path,
        test_config: dict[str, Any],
        frame_comparisons: list[dict[str, Any]],
        batch_info: dict[str, Any],
        navigation_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Generate comprehensive HTML comparison report

        Args:
            report_path: Path to save HTML report
            test_config: Test configuration (FPS, resolution, etc.)
            frame_comparisons: List of comparison results for each frame
                Each dict should contain:
                - frame_num: int
                - input_png: Path
                - output_png: Path
                - diff_red: Path (optional, red highlight diff)
                - diff_gray: Path (grayscale diff map)
                - diff_percentage: float
                - diff_pixels: int
                - total_pixels: int
                - source_svg: Path
            batch_info: Batch generation information
            navigation_data: Optional dict with:
                - report_paths: list[Path] - All report paths in batch
                - current_index: int - Index of this report (0-based)

        Why:
            Comprehensive report allows visual inspection of all frames
        """
        # Start HTML document
        # Why: Self-contained HTML with embedded CSS
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "    <meta charset='UTF-8'>",
            ("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>"),
            "    <title>svg2fbf Frame Comparison Report</title>",
            "    <style>",
            HTMLReportGenerator._get_css(),
            "    </style>",
            "</head>",
            "<body>",
            "    <!-- Navigation placeholder for batch test navigation -->",
            "    <div id='batch-navigation'></div>",
            "    <div class='container'>",
        ]

        # Report header
        # Why: Context about test run
        html_parts.append(HTMLReportGenerator._generate_header(test_config, batch_info))

        # Summary section
        # Why: Quick overview before diving into frames
        html_parts.append(HTMLReportGenerator._generate_summary(frame_comparisons))

        # Frame comparisons
        # Why: Side-by-side visual comparison for each frame
        for comparison in frame_comparisons:
            html_parts.append(HTMLReportGenerator._generate_frame_comparison(comparison))

        # Close main container
        html_parts.append("    </div>")

        # Add navigation bar for batch runs (if applicable)
        if navigation_data:
            report_paths = navigation_data["report_paths"]
            current_index = navigation_data["current_index"]
            total_reports = len(report_paths)

            # Convert paths to file:// URLs
            report_urls = [f"file://{str(path.absolute())}" for path in report_paths]

            # Determine navigation state
            is_first = current_index == 0
            is_last = current_index == total_reports - 1
            prev_index = (current_index - 1) % total_reports  # Circular
            next_index = (current_index + 1) % total_reports  # Circular

            # Build navigation buttons with proper styling
            first_btn_style = "opacity: 0.5; cursor: not-allowed;" if is_first else "cursor: pointer;"
            last_btn_style = "opacity: 0.5; cursor: not-allowed;" if is_last else "cursor: pointer;"

            html_parts.extend(
                [
                    "",
                    "    <script>",
                    "        // Navigation for batch test runs",
                    f"        const reportUrls = {report_urls};",
                    "",
                    "        function navigateToReport(index) {",
                    "            if (index >= 0 && index < reportUrls.length) {",
                    "                window.location.href = reportUrls[index];",
                    "            }",
                    "        }",
                    "",
                    "        // Create navigation bar on page load",
                    "        window.addEventListener('DOMContentLoaded', function() {",
                    ("            const navBar = document.getElementById('batch-navigation');"),
                    "            const navDiv = document.createElement('div');",
                    (
                        "            navDiv.style.cssText = 'position: fixed; "
                        "top: 0; left: 0; right: 0; "
                        "background: rgba(255, 255, 255, 0.95); "
                        "border-bottom: 2px solid #3498db; "
                        "padding: 10px 20px; z-index: 1000; "
                        "box-shadow: 0 2px 10px rgba(0,0,0,0.1); "
                        "display: flex; justify-content: center; "
                        "align-items: center; gap: 15px;';"
                    ),
                    "",
                    "            // First button",
                    "            const firstBtn = document.createElement('button');",
                    "            firstBtn.textContent = '⏮ First';",
                    f"            firstBtn.disabled = {str(is_first).lower()};",
                    (f"            firstBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; border: 1px solid #3498db; background: #fff; border-radius: 4px; {first_btn_style}';"),
                    "            firstBtn.onclick = () => navigateToReport(0);",
                    "            navDiv.appendChild(firstBtn);",
                    "",
                    "            // Previous button",
                    "            const prevBtn = document.createElement('button');",
                    "            prevBtn.textContent = '◀ Previous';",
                    ("            prevBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; border: 1px solid #3498db; background: #fff; border-radius: 4px; cursor: pointer;';"),
                    (f"            prevBtn.onclick = () => navigateToReport({prev_index});"),
                    "            navDiv.appendChild(prevBtn);",
                    "",
                    "            // Counter",
                    "            const counter = document.createElement('span');",
                    (f"            counter.textContent = '{current_index + 1} / {total_reports}';"),
                    ("            counter.style.cssText = 'font-weight: bold; color: #333; padding: 0 10px; min-width: 80px; text-align: center;';"),
                    "            navDiv.appendChild(counter);",
                    "",
                    "            // Next button",
                    "            const nextBtn = document.createElement('button');",
                    "            nextBtn.textContent = 'Next ▶';",
                    ("            nextBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; border: 1px solid #3498db; background: #fff; border-radius: 4px; cursor: pointer;';"),
                    (f"            nextBtn.onclick = () => navigateToReport({next_index});"),
                    "            navDiv.appendChild(nextBtn);",
                    "",
                    "            // Last button",
                    "            const lastBtn = document.createElement('button');",
                    "            lastBtn.textContent = 'Last ⏭';",
                    f"            lastBtn.disabled = {str(is_last).lower()};",
                    (f"            lastBtn.style.cssText = 'padding: 8px 16px; font-size: 14px; border: 1px solid #3498db; background: #fff; border-radius: 4px; {last_btn_style}';"),
                    (f"            lastBtn.onclick = () => navigateToReport({total_reports - 1});"),
                    "            navDiv.appendChild(lastBtn);",
                    "",
                    "            navBar.appendChild(navDiv);",
                    "            document.body.style.paddingTop = '60px';",
                    "        });",
                    "    </script>",
                ]
            )

        html_parts.extend(["</body>", "</html>"])

        # Write report
        # Why: Save to disk for inspection
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))

    @staticmethod
    def _get_css() -> str:
        """
        Get CSS styles for report

        Why: Clean, professional styling for readability
        """
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }

        .container {
            max-width: 1800px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header .timestamp {
            opacity: 0.9;
            font-size: 0.9em;
        }

        .config-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }

        .config-item {
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 5px;
        }

        .config-item label {
            display: block;
            font-size: 0.85em;
            opacity: 0.8;
            margin-bottom: 5px;
        }

        .config-item value {
            font-size: 1.2em;
            font-weight: bold;
        }

        .summary {
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .summary h2 {
            margin-bottom: 20px;
            color: #667eea;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }

        .summary-item {
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }

        .summary-item .label {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }

        .summary-item .value {
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }

        .summary-item.fail {
            border-left-color: #e74c3c;
        }

        .summary-item.fail .value {
            color: #e74c3c;
        }

        .summary-item.pass {
            border-left-color: #27ae60;
        }

        .summary-item.pass .value {
            color: #27ae60;
        }

        .frame-comparison {
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .frame-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }

        .frame-header h3 {
            font-size: 1.5em;
            color: #333;
        }

        .frame-status {
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
        }

        .frame-status.pass {
            background: #d4edda;
            color: #155724;
        }

        .frame-status.fail {
            background: #f8d7da;
            color: #721c24;
        }

        .frame-info {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 0.9em;
        }

        .frame-info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 10px;
        }

        .frame-info-item {
            display: flex;
            align-items: center;
        }

        .frame-info-item strong {
            min-width: 180px;
            color: #667eea;
        }

        .frame-info-item .path {
            font-family: monospace;
            font-size: 0.85em;
            color: #666;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .images-container {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-top: 20px;
        }

        .image-panel {
            background: #fafafa;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }

        .image-panel h4 {
            margin-bottom: 10px;
            color: #555;
            font-size: 1em;
        }

        .image-panel img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            cursor: pointer;
            transition: transform 0.2s;
            object-fit: contain;
        }

        .image-panel img:hover {
            transform: scale(1.02);
        }

        .diff-stats {
            margin-top: 10px;
            padding: 10px;
            background: white;
            border-radius: 5px;
            font-size: 0.85em;
        }

        .diff-stats-item {
            display: flex;
            align-items: center;
            margin: 8px 0;
        }

        .color-box {
            display: inline-block;
            width: 20px;
            height: 20px;
            margin-right: 10px;
            border: 1px solid #ccc;
            border-radius: 3px;
            flex-shrink: 0;
        }

        .color-box.black {
            background: #000000;
        }

        .color-box.gray {
            background: linear-gradient(to right, #404040, #e0e0e0);
        }

        .color-box.white {
            background: #ffffff;
        }

        .diff-stats-item .label {
            color: #666;
        }

        .diff-stats-item .value {
            font-weight: bold;
            color: #333;
        }

        .diff-percentage {
            font-size: 1.5em;
            font-weight: bold;
            text-align: center;
            margin: 10px 0;
            padding: 10px;
            color: white;
            border-radius: 5px;
        }

        .diff-percentage.pass {
            background: #00C853;
        }

        .diff-percentage.fail {
            background: #7B1FA2;
        }

        @media (max-width: 1400px) {
            .images-container {
                grid-template-columns: 1fr;
            }
        }

        /* Batch navigation - placeholder (populated by JavaScript if part of batch) */
        #batch-navigation {
            /* Styling is applied via JavaScript for batch runs */
        }

        #batch-navigation .nav-title {
            font-size: 0.85em;
            color: #666;
            margin-bottom: 8px;
            text-align: center;
        }

        #batch-navigation .nav-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        #batch-navigation a {
            padding: 8px 16px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 0.9em;
            transition: background 0.2s;
        }

        #batch-navigation a:hover {
            background: #5568d3;
        }

        #batch-navigation .nav-disabled {
            padding: 8px 16px;
            background: #e0e0e0;
            color: #999;
            border-radius: 4px;
            font-size: 0.9em;
            cursor: not-allowed;
            display: inline-block;
        }
        """

    @staticmethod
    def _generate_header(test_config: dict[str, Any], batch_info: dict[str, Any]) -> str:
        """Generate report header with test configuration"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_id = test_config.get("session_id", "N/A")

        # Extract numeric test ID from session_id
        # (e.g., "test_session_008_2frames" -> "8")
        test_id_display = "N/A"
        if session_id != "N/A" and "test_session_" in session_id:
            try:
                # Extract the numeric part after "test_session_"
                # Format: test_session_NNN_Xframes
                parts = session_id.split("_")
                if len(parts) >= 3:
                    test_id_num = int(parts[2])  # "008" -> 8
                    test_id_display = str(test_id_num)
            except (ValueError, IndexError):
                test_id_display = "N/A"

        # Input batch directory (session-level, always exists)
        batch_dir = batch_info.get("batch_dir", "N/A")
        batch_dir_url = f"file://{batch_dir}" if batch_dir != "N/A" else "#"

        # Output frames directory (run-level, may not exist if test failed)
        output_frames_dir = test_config.get("output_frames_dir", "N/A")
        output_frames_url = f"file://{output_frames_dir}" if output_frames_dir != "N/A" else "#"
        output_frames_display = str(output_frames_dir) if output_frames_dir != "N/A" else "n.a."

        # FBF animation file (may not exist if generation failed)
        fbf_file = test_config.get("fbf_file", "N/A")
        fbf_file_url = f"file://{fbf_file}" if fbf_file != "N/A" else "#"
        fbf_file_display = str(fbf_file) if fbf_file != "N/A" else "n.a."

        return f"""
        <div class='header'>
            <div style='display: flex; justify-content: space-between;
                align-items: center; margin-bottom: 10px;'>
                <h1 style='margin: 0;'>🎬 svg2fbf Frame Comparison Report</h1>
                <div style='font-size: 2em; font-weight: bold; color: #ffffff;
                    letter-spacing: 2px;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.5);'>
                    TEST ID: {test_id_display}
                </div>
            </div>
            <div class='timestamp'>Generated: {timestamp}</div>
            <div style='background: rgba(255,255,255,0.15); padding: 15px;
                border-radius: 8px; margin-top: 15px;
                border-left: 4px solid rgba(255,255,255,0.5);'>
                <div style='font-size: 0.9em; opacity: 0.8;
                    margin-bottom: 5px;'>
                    📋 E2E Test Session ID
                </div>
                <div style='font-size: 1.4em; font-weight: bold;
                    font-family: monospace; letter-spacing: 1px;'
                    title='Unique identifier for this E2E test session'>
                    {session_id}
                </div>
                <div style='font-size: 0.85em; opacity: 0.7; margin-top: 5px;'>
                    Use this ID to reference or rerun this E2E test session
                </div>
            </div>

            <div style='background: rgba(255,255,255,0.15); padding: 12px 15px;
                border-radius: 8px; margin-top: 10px;
                border-left: 4px solid rgba(255,255,255,0.5);'>
                <div style='font-size: 0.9em; opacity: 0.8; margin-bottom: 8px;'>
                    📁 Test Directories & Files
                </div>

                <div style='margin-bottom: 8px;'>
                    <div style='font-size: 0.85em; opacity: 0.7;
                        margin-bottom: 3px;'>
                        Input Batch (SVG source files):
                    </div>
                    <a href="{batch_dir_url}" target="_blank"
                        title='Click to open input batch folder in browser'
                        style='font-size: 1.0em; font-family: monospace;
                        color: rgba(255,255,255,0.95); text-decoration: none;
                        word-break: break-all; display: block;
                        transition: opacity 0.2s;'
                        onmouseover='this.style.opacity="0.7"'
                        onmouseout='this.style.opacity="1"'>
                        {batch_dir}
                    </a>
                </div>

                <div style='margin-bottom: 8px;'>
                    <div style='font-size: 0.85em; opacity: 0.7;
                        margin-bottom: 3px;'>
                        Output Frames (FBF captured frames):
                    </div>
                    <a href="{output_frames_url}" target="_blank"
                        title='Click to open output frames folder in browser'
                        style='font-size: 1.0em; font-family: monospace;
                        color: rgba(255,255,255,0.95); text-decoration: none;
                        word-break: break-all; display: block;
                        transition: opacity 0.2s;'
                        onmouseover='this.style.opacity="0.7"'
                        onmouseout='this.style.opacity="1"'>
                        {output_frames_display}
                    </a>
                </div>

                <div>
                    <div style='font-size: 0.85em; opacity: 0.7;
                        margin-bottom: 3px;'>
                        FBF Animation File:
                    </div>
                    <a href="{fbf_file_url}" target="_blank"
                        title='Click to view FBF animation in new tab'
                        style='font-size: 1.0em; font-family: monospace;
                        color: rgba(255,255,255,0.95); text-decoration: none;
                        word-break: break-all; display: block;
                        transition: opacity 0.2s;'
                        onmouseover='this.style.opacity="0.7"'
                        onmouseout='this.style.opacity="1"'>
                        {fbf_file_display}
                    </a>
                </div>
            </div>

            <div class='config-grid'>
                <div class='config-item'
                    title='Number of frames tested in this session'>
                    <label>Frames Tested</label>
                    <value>{test_config.get("frame_count", "N/A")}</value>
                </div>
                <div class='config-item'
                    title='Original SVG resolution from first frame viewBox'>
                    <label>SVG Resolution (First Frame)</label>
                    <value>{int(test_config.get("svg_width", 0)) if test_config.get("svg_width") != "N/A" else "N/A"}×{int(test_config.get("svg_height", 0)) if test_config.get("svg_height") != "N/A" else "N/A"}</value>
                </div>
                <div class='config-item'
                    title='Browser viewport size used for rendering'>
                    <label>Rendering Viewport</label>
                    <value>{test_config.get("width", "N/A")}×{test_config.get("height", "N/A")}</value>
                </div>
                <div class='config-item'
                    title='Percentage of pixels allowed to differ'>
                    <label>Image Tolerance</label>
                    <value>{test_config.get("tolerance", 0.0):.4f}% pixels</value>
                </div>
                <div class='config-item'
                    title='Per-pixel RGB difference threshold (~1/256 ≈ 1 RGB value)'>
                    <label>Pixel Tolerance</label>
                    <value>{test_config.get("pixel_tolerance", 0.0):.4f} RGB</value>
                </div>
                <div class='config-item'
                    title='Frames per second (animation playback speed)'>
                    <label>FPS</label>
                    <value>{test_config.get("fps", "N/A")}</value>
                </div>
                <div class='config-item'
                    title='Animation playback mode (once, loop, or pingpong)'>
                    <label>Animation Type</label>
                    <value>{test_config.get("animation_type", "N/A")}</value>
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _generate_summary(frame_comparisons: list[dict[str, Any]]) -> str:
        """Generate summary statistics"""
        total_frames = len(frame_comparisons)
        # Use is_identical (respects tolerance) instead of checking diff_percentage
        # Why: Frames may pass with tolerance, summary should reflect that
        failed_frames = sum(1 for fc in frame_comparisons if not fc.get("is_identical", fc["diff_percentage"] == 0))
        passed_frames = total_frames - failed_frames

        total_diff_pixels = sum(fc["diff_pixels"] for fc in frame_comparisons)
        total_pixels = sum(fc["total_pixels"] for fc in frame_comparisons)
        avg_diff_percentage = (total_diff_pixels / total_pixels * 100) if total_pixels > 0 else 0.0

        max_diff = max((fc["diff_percentage"] for fc in frame_comparisons), default=0.0)

        # Big pass/fail indicator
        # Why: User wants at-a-glance visual feedback
        all_passed = failed_frames == 0
        if all_passed:
            status_banner = """
            <div style='background: linear-gradient(135deg, #27ae60, #2ecc71);
                color: white; padding: 30px; border-radius: 15px;
                text-align: center; margin: 20px 0;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                <div style='font-size: 48px; font-weight: bold;
                    margin-bottom: 10px;'>
                    ✅ ALL TESTS PASSED! 🎉
                </div>
                <div style='font-size: 18px; opacity: 0.9;'>
                    All frames rendered identically within tolerance
                </div>
            </div>
            """
        else:
            status_banner = f"""
            <div style='background: linear-gradient(135deg, #e74c3c, #c0392b);
                color: white; padding: 30px; border-radius: 15px;
                text-align: center; margin: 20px 0;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                <div style='font-size: 48px; font-weight: bold;
                    margin-bottom: 10px;'>
                    ❌ TEST FAILED ⚠️
                </div>
                <div style='font-size: 18px; opacity: 0.9;'>
                    {failed_frames} of {total_frames} frames failed
                </div>
            </div>
            """

        return f"""
        <div class='summary'>
            <h2>📊 Test Summary</h2>
            {status_banner}
            <div class='summary-grid'>
                <div class='summary-item'>
                    <div class='label'>Total Frames</div>
                    <div class='value'>{total_frames}</div>
                </div>
                <div class='summary-item pass'>
                    <div class='label'>Passed (Identical)</div>
                    <div class='value'>{passed_frames}</div>
                </div>
                <div class='summary-item fail'>
                    <div class='label'>Failed (Different)</div>
                    <div class='value'>{failed_frames}</div>
                </div>
                <div class='summary-item'>
                    <div class='label'>Average Difference</div>
                    <div class='value'>{avg_diff_percentage:.4f}%</div>
                </div>
                <div class='summary-item'>
                    <div class='label'>Maximum Difference</div>
                    <div class='value'>{max_diff:.4f}%</div>
                </div>
                <div class='summary-item'>
                    <div class='label'>Total Different Pixels</div>
                    <div class='value'>{total_diff_pixels:,}</div>
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _generate_frame_comparison(comparison: dict[str, Any]) -> str:
        """Generate comparison section for single frame"""
        frame_num = comparison["frame_num"]
        diff_percentage = comparison["diff_percentage"]
        diff_pixels = comparison["diff_pixels"]
        total_pixels = comparison["total_pixels"]

        # Use is_identical from comparison (respects tolerance)
        # Why: Test may pass with tolerance, HTML should reflect that
        is_identical = comparison.get("is_identical", diff_percentage == 0)

        status = "pass" if is_identical else "fail"
        status_text = "✅ IDENTICAL" if is_identical else "❌ DIFFERENT"

        # Convert images to base64 for embedding
        # Why: Self-contained HTML, no external dependencies
        input_img_b64 = HTMLReportGenerator._image_to_base64(comparison["input_png"])
        output_img_b64 = HTMLReportGenerator._image_to_base64(comparison["output_png"])
        diff_gray_b64 = HTMLReportGenerator._image_to_base64(comparison.get("diff_gray", Path()))

        # Get image dimensions for tooltips
        input_width, input_height = HTMLReportGenerator._get_image_dimensions(comparison["input_png"])
        output_width, output_height = HTMLReportGenerator._get_image_dimensions(comparison["output_png"])
        diff_width, diff_height = HTMLReportGenerator._get_image_dimensions(comparison.get("diff_gray", Path()))

        source_svg_path = comparison.get("source_svg", "N/A")
        source_svg_name = Path(source_svg_path).name if source_svg_path != "N/A" else "Unknown"
        source_svg_url = f"file://{source_svg_path}" if source_svg_path != "N/A" else "#"

        return f"""
        <div class='frame-comparison'>
            <div class='frame-header'>
                <h3>Frame {frame_num}</h3>
                <div class='frame-status {status}'>{status_text}</div>
            </div>

            <div class='frame-info'>
                <div class='frame-info-grid'>
                    <div class='frame-info-item'>
                        <strong>Source SVG:</strong>
                        <a href="{source_svg_url}" target="_blank" class='path'
                            title='Click to view source SVG file: {source_svg_path}'
                            style='color: inherit; text-decoration: underline;
                            cursor: pointer;'>
                            {source_svg_name}
                        </a>
                    </div>
                    <div class='frame-info-item'>
                        <strong>Different Pixels:</strong>
                        <span>{diff_pixels:,} / {total_pixels:,}</span>
                    </div>
                    <div class='frame-info-item'>
                        <strong>Difference:</strong>
                        <span style='font-weight: bold;
                            color: {"#27ae60" if diff_percentage == 0 else "#e74c3c"};'>
                            {diff_percentage:.4f}%
                        </span>
                    </div>
                </div>
            </div>

            <div class='images-container'>
                <div class='image-panel'>
                    <h4>📥 Input Frame (Ground Truth)</h4>
                    <img src='data:image/png;base64,{input_img_b64}'
                        alt='Input Frame {frame_num}'
                        data-filepath='{comparison["input_png"]}'
                        title='Resolution: {input_width}×{input_height} pixels.
                        Click to open actual file in new tab'
                        onclick='window.open("file://{comparison["input_png"]}",
                        "_blank")'
                        style='cursor: pointer;'>
                </div>

                <div class='image-panel'>
                    <h4>📤 Output Frame (FBF Animation)</h4>
                    <img src='data:image/png;base64,{output_img_b64}'
                        alt='Output Frame {frame_num}'
                        data-filepath='{comparison["output_png"]}'
                        title='Resolution: {output_width}×{output_height} pixels.
                        Click to open actual file in new tab'
                        onclick='window.open("file://{comparison["output_png"]}",
                        "_blank")'
                        style='cursor: pointer;'>
                </div>

                <div class='image-panel'>
                    <h4>🔍 Grayscale Diff Map</h4>
                    <img src='data:image/png;base64,{diff_gray_b64}'
                        alt='Diff Map Frame {frame_num}'
                        data-filepath='{comparison.get("diff_gray", "")}'
                        title='Resolution: {diff_width}×{diff_height} pixels.
                        Click to open actual file in new tab'
                        onclick='window.open("file://{comparison.get("diff_gray", "")}",
                        "_blank")'
                        style='cursor: pointer;'>
                    <div class='diff-percentage {status}'>{"✔︎ PASS (within tolerance)" if is_identical else f"✖︎ FAIL ({diff_percentage:.4f}% different)"}</div>
                    <div class='diff-stats'>
                        <div style='font-weight: bold; margin-bottom: 10px;
                            color: #555;'>
                            Color Meanings:
                        </div>
                        <div class='diff-stats-item'>
                            <div class='color-box black'></div>
                            <span>0% (no differences)</span>
                        </div>
                        <div class='diff-stats-item'>
                            <div class='color-box gray'></div>
                            <span>
                                difference magnitude between 0% and 100%
                                (the more different are the pixels,
                                the darker is the color)
                            </span>
                        </div>
                        <div class='diff-stats-item'>
                            <div class='color-box white'></div>
                            <span>100% (completely different)</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _get_image_dimensions(image_path: Path) -> tuple[int, int]:
        """
        Get image dimensions (width, height)

        Args:
            image_path: Path to image file

        Returns:
            Tuple of (width, height) or (0, 0) if unable to read
        """
        if not image_path or not Path(image_path).exists():
            return (0, 0)

        try:
            from PIL import Image

            with Image.open(image_path) as img:
                width, height = img.size
                return (width, height)
        except Exception:
            return (0, 0)

    @staticmethod
    def _image_to_base64(image_path: Path) -> str:
        """
        Convert image to base64 string for embedding in HTML

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded string

        Why:
            Self-contained HTML with no external file dependencies
        """
        if not image_path or not Path(image_path).exists():
            # Return 1x1 transparent pixel as fallback
            # Why: Prevent broken images in HTML
            return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
                return base64.b64encode(image_data).decode("utf-8")
        except Exception:
            # Return 1x1 transparent pixel as fallback
            return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
