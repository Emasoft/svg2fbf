# Getting Started with FBF.SVG

**A practical introduction to creating Frame-by-Frame SVG animations**

---

## What is FBF.SVG?

FBF.SVG (Frame-by-Frame SVG) is a standardized format for creating vector-based frame-by-frame animations that work natively in web browsers. Think of it as "animated GIF meets SVG" – you define each frame explicitly, but with all the benefits of scalable vector graphics:

✅ **Infinite resolution** - Scales perfectly to any display size
✅ **Small file sizes** - Intelligent deduplication reduces redundancy by 40-70%
✅ **Web-native** - Plays directly in browsers, no plugins needed
✅ **Interactive** - Add clickable elements, tooltips, animations
✅ **Accessible** - Screen readers can access SVG text and labels

---

## Quick Start: Your First Animation

### Prerequisites

**Required**:
- Python 3.10 or higher
- Basic familiarity with SVG (helpful but not required)

**Optional**:
- Inkscape or other SVG editor (for creating frames)

### Installation

```bash
# Recommended: Install as uv tool (globally available)
uv tool install svg2fbf

# Or using pip
pip install svg2fbf

# Verify installation
svg2fbf --version
```

### Creating a Simple Animation

Let's create a 4-frame "hello world" animation.

#### Step 1: Create Frame SVG Files

Create a directory for your frames:

```bash
mkdir hello_animation
cd hello_animation
```

Create four SVG files (`frame_001.svg`, `frame_002.svg`, `frame_003.svg`, `frame_004.svg`):

**frame_001.svg**:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
  <rect width="400" height="200" fill="#f0f0f0"/>
  <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">H</text>
</svg>
```

**frame_002.svg**:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
  <rect width="400" height="200" fill="#f0f0f0"/>
  <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">He</text>
</svg>
```

**frame_003.svg**:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
  <rect width="400" height="200" fill="#f0f0f0"/>
  <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">Hel</text>
</svg>
```

**frame_004.svg**:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
  <rect width="400" height="200" fill="#f0f0f0"/>
  <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">Hello!</text>
</svg>
```

#### Step 2: Convert to FBF.SVG

```bash
svg2fbf -i . -o hello.fbf.svg -f 2
```

**Explanation**:
- `-i .` : Input directory (current directory containing frame_*.svg files)
- `-o hello.fbf.svg` : Output filename
- `-f 2` : Frame rate (2 frames per second)

#### Step 3: View Your Animation

Open `hello.fbf.svg` in any modern web browser:

```bash
# macOS
open hello.fbf.svg

# Linux
xdg-open hello.fbf.svg

# Windows
start hello.fbf.svg
```

You should see the text "Hello!" being typed one letter at a time!

---

## Understanding the FBF.SVG Structure

Let's examine what `svg2fbf` created. Open `hello.fbf.svg` in a text editor:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     xmlns:fbf="http://opentoonz.github.io/fbf/1.0#"
     viewBox="0 0 400 200">

  <!-- Metadata (optional for Basic conformance) -->
  <metadata>
    <rdf:RDF>
      <dc:title>Hello Animation</dc:title>
      <fbf:frameCount>4</fbf:frameCount>
      <fbf:fps>2</fbf:fps>
      <fbf:duration>2.0</fbf:duration>
    </rdf:RDF>
  </metadata>

  <!-- Description -->
  <desc>A simple typing animation</desc>

  <!-- Animation structure -->
  <g id="ANIMATION_BACKDROP">
    <g id="STAGE_BACKGROUND"></g>
    <g id="ANIMATION_STAGE">
      <g id="ANIMATED_GROUP">
        <use id="PROSKENION" xlink:href="#FRAME00001">
          <animate attributeName="xlink:href"
                   values="#FRAME00001;#FRAME00002;#FRAME00003;#FRAME00004"
                   dur="2.0s"
                   repeatCount="indefinite"
                   calcMode="discrete"/>
        </use>
      </g>
    </g>
    <g id="STAGE_FOREGROUND"></g>
  </g>

  <g id="OVERLAY_LAYER"></g>

  <!-- Frame definitions -->
  <defs>
    <g id="SHARED_DEFINITIONS">
      <!-- Shared elements (in this case, the gray background) -->
      <rect id="shared_rect_001" width="400" height="200" fill="#f0f0f0"/>
    </g>

    <g id="FRAME00001">
      <use xlink:href="#shared_rect_001"/>
      <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">H</text>
    </g>

    <g id="FRAME00002">
      <use xlink:href="#shared_rect_001"/>
      <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">He</text>
    </g>

    <g id="FRAME00003">
      <use xlink:href="#shared_rect_001"/>
      <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">Hel</text>
    </g>

    <g id="FRAME00004">
      <use xlink:href="#shared_rect_001"/>
      <text x="200" y="100" text-anchor="middle" font-size="48" fill="blue">Hello!</text>
    </g>
  </defs>
</svg>
```

**Key Components**:

1. **ANIMATION_BACKDROP** - Layered composition container with 3 child groups
2. **STAGE_BACKGROUND** - Background layer (Z-order: behind animation)
3. **ANIMATION_STAGE** - The stage where animation happens
4. **STAGE_FOREGROUND** - Foreground layer (Z-order: in front of animation)
5. **OVERLAY_LAYER** - Overlay layer (Z-order: superimposed on all elements)
6. **PROSKENION** - The element that displays frames (uses SMIL `<animate>`)
7. **SHARED_DEFINITIONS** - Elements that appear in multiple frames (optimized)
8. **FRAME00001, FRAME00002, etc.** - Individual frame definitions

**Notice**: The gray rectangle appears in all 4 frames, so `svg2fbf` automatically:
- Detected it as identical across frames
- Moved it to `SHARED_DEFINITIONS`
- Replaced it with `<use>` references in each frame
- Result: File is smaller than 4 separate copies!

---

## Customizing Your Animation

### Using FBF Generation Cards (Recommended)

Instead of long command lines, you can use **FBF Generation Cards** (YAML files) to specify all settings in one place:

**Create a generation card** (`hello.yaml`):
```yaml
metadata:
  title: "Hello Animation"
  creators: "Your Name"
  description: "A simple typing animation"
  keywords: "hello, typing, animation"
  language: "en"
  rights: "CC-BY-4.0"

generation_parameters:
  input_folder: hello_animation
  output_path: ./
  filename: hello.fbf.svg
  speed: 2
  animation_type: loop
```

**Then run simply:**
```bash
svg2fbf hello.yaml
```

**Benefits:**
- All settings in one file
- Version control friendly
- Self-documenting
- Easy to share
- Reproducible builds

See **[FBF Generation Cards Documentation](FBF_GENERATION_CARDS.md)** for complete details and examples.

### Changing Frame Rate

```bash
# Slower (1 frame per second)
svg2fbf -i frames/ -o slow.fbf.svg -f 1

# Faster (24 frames per second - cinema standard)
svg2fbf -i frames/ -o fast.fbf.svg -f 24

# Very fast (60 frames per second - smooth)
svg2fbf -i frames/ -o smooth.fbf.svg -f 60
```

### Animation Modes

**Loop Forever** (default):
```bash
svg2fbf -i frames/ -o loop.fbf.svg --loop
```

**Play Once**:
```bash
svg2fbf -i frames/ -o once.fbf.svg --once
```

**Play N Times**:
```bash
svg2fbf -i frames/ -o three_times.fbf.svg --count 3
```

**Ping-Pong** (forward then backward):
```bash
svg2fbf -i frames/ -o pingpong.fbf.svg --pingpong
```

### Adding Metadata

```bash
svg2fbf -i frames/ -o animation.fbf.svg \
  --title "My Animation" \
  --creator "Your Name" \
  --description "A cool animation I made" \
  --rights "CC-BY-4.0"
```

### Optimization Options

**Disable optimizations** (for debugging):

```bash
# No path optimization
svg2fbf -i frames/ -o debug.fbf.svg --no-optimize-paths

# No deduplication (keep all frames separate)
svg2fbf -i frames/ -o verbose.fbf.svg --no-deduplicate
```

---

## Creating Frames with Inkscape

Inkscape is a free, open-source SVG editor perfect for creating animation frames.

### Method 1: Manual Frame Creation

1. **Create your first frame** in Inkscape
2. **Save as** `frame_001.svg`
3. **Modify the content** for the next frame
4. **Save as** `frame_002.svg`
5. Repeat for all frames
6. Convert with `svg2fbf`

**Tips**:
- Use layers to organize elements
- Lock background layer to avoid accidental changes
- Use guides for consistent positioning
- Save frequently!

### Method 2: Duplicate and Modify

1. Create your animation in a single Inkscape file using **layers**
2. For each frame:
   - Hide all layers except one
   - Export as `frame_00X.svg`
3. Convert with `svg2fbf`

**Example Layer Structure**:
```
Layers:
├── Background (always visible)
├── Frame 1 (show for frame 1)
├── Frame 2 (show for frame 2)
├── Frame 3 (show for frame 3)
└── Frame 4 (show for frame 4)
```

### Method 3: Using Inkscape's Export Batch

1. Create animation using layers
2. Use Inkscape's command-line batch export:

```bash
for i in {1..10}; do
  inkscape animation.svg \
    --export-id="frame_$i" \
    --export-filename="frame_$(printf '%03d' $i).svg"
done
```

---

## Best Practices

### 1. Design for Deduplication

**Good** (elements are identical):
```xml
<!-- Frame 1 -->
<circle cx="50" cy="50" r="20" fill="red"/>

<!-- Frame 2 (identical circle) -->
<circle cx="50" cy="50" r="20" fill="red"/>
```
Result: Circle defined once, reused in both frames ✅

**Bad** (elements differ slightly):
```xml
<!-- Frame 1 -->
<circle cx="50" cy="50" r="20" fill="red"/>

<!-- Frame 2 (different radius) -->
<circle cx="50" cy="50" r="20.001" fill="red"/>
```
Result: Two separate circles (deduplication fails) ❌

**Tip**: Use consistent precision in your SVG editor settings.

### 2. Reuse Gradients and Patterns

If multiple frames use the same gradient, define it identically:

```xml
<!-- Define once in each frame -->
<linearGradient id="myGradient">
  <stop offset="0%" stop-color="blue"/>
  <stop offset="100%" stop-color="red"/>
</linearGradient>
```

`svg2fbf` will automatically merge identical gradients into `SHARED_DEFINITIONS`.

### 3. Consistent ViewBox

All frames should have the **same viewBox**:

```xml
<!-- All frames -->
<svg viewBox="0 0 800 600">...</svg>
```

If frames have different viewBox values, `svg2fbf` will:
- Warn you
- Automatically transform frames to match the first frame's viewBox
- This may cause unexpected scaling

**Better**: Set consistent viewBox in your editor before exporting.

### 4. Frame Naming Convention

`svg2fbf` expects frames in alphabetical/numerical order:

**Good**:
```
frame_001.svg
frame_002.svg
frame_003.svg
...
frame_100.svg
```

**Bad**:
```
frame_1.svg   # Will sort before frame_10.svg!
frame_10.svg
frame_2.svg
```

**Tip**: Use zero-padded numbers (001, 002, ...) for correct sorting.

### 5. Keep Frames Simple

Complex frames with thousands of elements will:
- Slow down conversion
- Increase file size
- Reduce rendering performance

**Guidelines**:
- Aim for <100 elements per frame
- Simplify paths when possible (Inkscape: Path → Simplify)
- Use symbols for repeated elements
- Avoid excessive filters/effects

---

## Troubleshooting

### Problem: "No SVG files found in input directory"

**Cause**: `svg2fbf` can't find .svg files

**Solution**:
- Check directory path: `ls frames/` should show .svg files
- Ensure files have .svg extension (not .SVG or .svg.txt)
- Use absolute path: `svg2fbf -i /full/path/to/frames/`

### Problem: "Invalid viewBox in frame X"

**Cause**: Frame has different viewBox than frame 1

**Solution**:
- Open all frames in editor
- Set identical viewBox for all: `viewBox="0 0 800 600"`
- Re-export and convert

**Or**: Use `--auto-viewbox` flag (experimental):
```bash
svg2fbf -i frames/ -o output.fbf.svg --auto-viewbox
```

### Problem: Animation plays too fast/slow

**Cause**: Incorrect frame rate calculation

**Solution**:
- Calculate desired FPS: `fps = frameCount / desiredDuration`
- Example: 120 frames in 5 seconds = 24 fps
- Use `-f 24` flag

### Problem: File size is huge

**Cause**: Lack of deduplication or high precision

**Solution**:
- Check for inconsistent elements (see "Design for Deduplication")
- Enable path optimization: `--optimize-paths` (enabled by default)
- Compress manually: `gzip output.fbf.svg` (saves 60-80%)

### Problem: Validation errors

**Cause**: Generated FBF.SVG doesn't meet specification requirements

**Solution**:
```bash
# Validate the file
python validate_fbf.py output.fbf.svg

# Read error messages carefully
# Common issues:
#   - External resource references (fix: embed images as data URIs)
#   - Invalid metadata (fix: use --title, --creator flags)
#   - Script elements (fix: remove scripts from input frames)
```

---

## Next Steps

Now that you've created your first FBF.SVG animation, explore:

1. **[FBF Generation Cards](FBF_GENERATION_CARDS.md)** - Complete guide to YAML configuration files
2. **[FBF.SVG Specification](FBF_SVG_SPECIFICATION.md)** - Complete technical details
3. **[Examples](../examples/)** - Sample animations to learn from (with generation cards)
4. **[Template](../templates/generation-card-template.yaml)** - Ready-to-use generation card template

### Example Projects to Try

**Bouncing Ball**:
- 10-12 frames showing ball arc
- Practice timing and easing
- File: `examples/bouncing_ball/`

**Character Walk Cycle**:
- 8-12 frames of walking motion
- Learn about loops and symmetry
- File: `examples/walk_cycle/`

**Logo Reveal**:
- 20-30 frames of logo animation
- Practice with paths and transforms
- File: `examples/logo_reveal/`

### Join the Community

- **GitHub**: https://github.com/Emasoft/svg2fbf
- **Discussions**: Share your animations, ask questions
- **Issues**: Report bugs, request features
- **Contribute**: Code, docs, examples always welcome!

---

## Quick Reference

### Common Commands

```bash
# Basic conversion
svg2fbf -i frames/ -o output.fbf.svg -f 24

# With metadata
svg2fbf -i frames/ -o output.fbf.svg -f 24 \
  --title "My Animation" \
  --creator "Your Name"

# Play once
svg2fbf -i frames/ -o output.fbf.svg --once

# Ping-pong
svg2fbf -i frames/ -o output.fbf.svg --pingpong

# Validate
python validate_fbf.py output.fbf.svg
```

### File Size Estimates

| Frames | Complexity | Typical Size | Gzipped |
|--------|------------|--------------|---------|
| 10 | Simple | 10-50 KB | 3-15 KB |
| 50 | Medium | 50-200 KB | 15-60 KB |
| 100 | Medium | 100-400 KB | 30-120 KB |
| 200 | Complex | 500 KB - 2 MB | 150-600 KB |

**Note**: Actual sizes depend heavily on element reuse and path complexity.

---

**Happy animating! 🎬**

For questions or help, open an issue on GitHub or join our discussions.
