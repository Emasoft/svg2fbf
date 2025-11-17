# FBF.SVG Examples

![SVG Animation Examples](../assets/svg_animation_examples_header_onion_skin.webp)

This directory contains validated FBF.SVG animation examples.

## Structure

Each example follows this structure:

```
example_name/
├── input_frames/          # Source SVG frames (if available)
├── fbf_output/            # Generated FBF.SVG animation
└── example_name.yaml      # Configuration file
```

## Examples

### splat_button
Interactive animated button with click-triggered splash effect.
- **Source frames**: ✅ Available in `input_frames/`
- **FBF Status**: ✅ VALID (passes FBF.SVG validation)
- **Regenerate**: `uv run python svg2fbf.py examples/splat_button/splat_button.yaml`

### walk_cycle
Frame-by-frame walk cycle animation.
- **Source frames**: ❌ Not available (lost)
- **FBF Status**: ✅ VALID (passes FBF.SVG validation)
- **Pre-generated FBF file** in `fbf_output/`

### panther_bird
Multi-group animation featuring panther and bird.
- **Source frames**: ❌ Not available (non-standard multi-group format)
- **FBF Status**: ⚠️  Non-standard (multi-group animation, documented exception)
- **Pre-generated FBF file** in `fbf_output/`

## Using YAML Configuration Files

### With svg2fbf.py

To generate or regenerate an FBF animation:

```bash
uv run python svg2fbf.py examples/<example_name>/<example_name>.yaml
```

The YAML file contains all metadata and generation parameters needed to reproduce the exact same output.

### With testrunner.py

The same YAML configuration files can be used with testrunner.py for testing:

```bash
uv run python testrunner.py --config examples/<example_name>/<example_name>.yaml
```

This allows you to:
- Generate the FBF animation from source frames
- Render the animation frames with Puppeteer
- Compare against expected output
- Generate HTML comparison reports

### YAML File Structure

Example YAML structure with all available fields:

```yaml
metadata:
  title: "Animation Title"
  creators: "Creator Name"
  description: "Description of the animation"
  keywords: "keyword1, keyword2, keyword3"
  language: "en"
  rights: "Apache-2.0"
  # Optional fields:
  # episode_number: 1
  # episode_title: "Episode Title"
  # original_creators: "Original Creator"
  # copyrights: "Copyright Notice"
  # website: "https://example.com"
  # original_language: "en"
  # source: "Source information"

generation_parameters:
  input_folder: examples/example_name/input_frames
  output_path: examples/example_name/fbf_output
  filename: example_name.fbf.svg
  speed: 12.0
  animation_type: loop  # once, loop, pingpong_loop, etc.
  play_on_click: false
  quiet: false
  # Optional parameters:
  # digits: 28
  # cdigits: 28
  # backdrop: "None"
  # keep_xml_space: false
  # max_frames: null
```

## Validation

All examples except `panther_bird` pass FBF.SVG validation:

```bash
uv run python validate_fbf.py examples/splat_button/fbf_output/splat_button.fbf.svg
uv run python validate_fbf.py examples/walk_cycle/fbf_output/walk_cycle.fbf.svg
```

`panther_bird` is a non-standard multi-group animation that demonstrates advanced FBF.SVG capabilities beyond the standard specification.

## Development Examples

Test and development examples are in `examples_dev/` (not tracked by git).
