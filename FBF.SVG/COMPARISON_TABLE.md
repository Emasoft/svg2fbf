# Web & Mobile Vector Animation Formats: Comprehensive Comparison

**Last Updated:** November 12, 2024
**Version:** 1.1

This document provides detailed, evidence-based comparisons of vector animation formats and tools for **both web and mobile platforms**. All claims are documented with 78 official references.

## Document Structure

This comprehensive analysis includes **TWO main comparison tables:**

1. **[Web Animation Formats](#animation-formats-comparison)** — Detailed comparison of deliverable web animation formats (FBF.SVG, Lottie, OCA, Rive, Adobe Animate, plus implementation methods)
2. **[Mobile Animation Formats](#mobile-animation-formats-comparison)** — Focused comparison for mobile development with iOS/Android library details, per-app fees, and hidden costs

Plus additional sections on JavaScript libraries, authoring tools, and full references.

**🎯 Key Insight:** FBF.SVG is the **only** format that is a **pure image file** (standard SVG) with **ZERO CODE** inside — no JavaScript, no CSS, just pure SVG markup.

> **"Anything can play an FBF.SVG video. Anything! If it supports SVG 1.1, it can reproduce it!"**

It opens in millions of applications: browsers, graphic editors, video editors, design tools, and mobile apps.

**For tool developers:** A company that wants to create a graphic editor for FBF.SVG doesn't need to support the complexity of a CSS rendering engine or a JavaScript runtime — all it needs is to support the plain, bare SVG 1.1 or SVG 2.0 standard.

**For production teams:**
> **"With FBF.SVG there is no need to hire programmers anymore to create animations. Artists are all you need."**

This eliminates the need for expensive programming teams, simplifies hiring, and removes code maintenance overhead.

📥 **[Download Excel Version](../assets/comparison_table.xlsx)** — Spreadsheet version with all data

---

## Table of Contents

- [Animation Formats Comparison](#animation-formats-comparison)
- [JavaScript Libraries Comparison](#javascript-libraries-comparison)
- [Animation Authoring Tools Comparison](#animation-authoring-tools-comparison)
- [Mobile Animation Formats Comparison](#mobile-animation-formats-comparison)
- [References and Documentation](#references-and-documentation)
- [Methodology](#methodology)

---

## Animation Formats Comparison

### Main Comparison Table

| Capability | **FBF.SVG** | Lottie/Bodymovin | OCA (Open Cell Animation) | Rive | Adobe Animate | SMIL (SVG Native) | CSS Animations + SVG | Web Animations API (WAAPI) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **🌐 Website** | [svg2fbf](https://github.com/Emasoft/svg2fbf) | [airbnb.io/lottie](https://airbnb.io/lottie/) | [oca.rxlab.guide](https://oca.rxlab.guide/) | [rive.app](https://rive.app/) | [adobe.com/animate](https://www.adobe.com/products/animate.html) | [W3C SVG](https://www.w3.org/TR/SVG/) | [W3C CSS](https://www.w3.org/TR/css-animations-1/) | [W3C WAAPI](https://www.w3.org/TR/web-animations-1/) |
| **📜 License** | Apache 2.0¹ | MIT² | GPL-3.0³ | MIT⁴ | Commercial⁵ | W3C⁶ | W3C⁶ | W3C⁶ |
| **Full Name** | Frame-by-Frame SVG | Lottie Animation Format | Open Cell Animation | Rive Animation Format | Adobe Animate | Synchronized Multimedia Integration Language | CSS Animations with SVG | Web Animations API |
| **📝 Description** | SVG-based frame animation using SMIL, self-contained single file | JSON-based After Effects animations for web/mobile | Open interchange format for traditional/cel animation | Interactive vector animation with state machines | Professional animation authoring with multiple exports | Native SVG animation standard using XML | Native browser CSS animations applied to SVG | JavaScript API unifying CSS/SVG animations |
| **📁 File Formats** | SVG 1.1/2.0 (single file) | JSON + base64 images | JSON + PNG/WebP sequence | .riv (binary) | SVG, Canvas, Video | SVG with `<animate>` | SVG + CSS | SVG + JavaScript |

### Creation & Workflow Capabilities

| Capability | **FBF.SVG** | Lottie/Bodymovin | OCA | Rive | Adobe Animate | SMIL | CSS + SVG | WAAPI |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Can be created using only free/open source tools?** | ✅ YES!⁷ (Inkscape, Krita, Blender) | ❌ NO⁸ (requires Adobe After Effects $275/yr) | ✅ YES!⁹ (Krita, Blender, OpenToonz) | ✅ YES, but free version limited¹⁰ (paid $168-540/yr for full features) | ❌ NO¹¹ (requires Adobe Animate $275/yr) | ✅ YES (any text editor) | ✅ YES (any text editor) | ✅ YES (any text editor) |
| **Can import standard SVG 1.1 files as source?** | ✅ YES! | ❌ NO (After Effects uses own formats) | ✅ YES, in supported animation apps | ✅ YES, but limited feature support | ✅ YES (full import support) | N/A (is SVG itself) | N/A (is SVG itself) | N/A (is SVG itself) |
| **Can import SVG 2.0 with mesh gradients?** | ✅ YES!¹² | ❌ NO | ❌ NO | ❌ NO | ✅ YES, but limited SVG 2.0 support | N/A (is SVG itself) | ✅ YES, if browser supports it | ✅ YES, if browser supports it |
| **Can export standard SVG 1.1 files?** | ✅ YES! | ❌ NO (exports JSON only) | ❌ NO (exports JSON+PNG or video) | ❌ NO (exports .riv binary only) | ✅ YES, but static only (no animation without deprecated plugins) | N/A (is SVG itself) | N/A (is SVG itself) | N/A (is SVG itself) |
| **Can export animated SVG files?** | ✅ YES! | ❌ NO | ❌ NO | ❌ NO | ❌ NO (requires deprecated Snap.SVG plugin for animated SVG) | N/A (is SVG itself) | N/A (is SVG itself) | N/A (is SVG itself) |
| **Output can be edited by artists without code?** | ✅ YES!¹³ (in any SVG editor: Inkscape, Illustrator, Boxy SVG, etc.) | ❌ NO (requires After Effects) | ✅ YES (in Krita, Blender, OpenToonz) | ❌ NO (requires Rive Editor) | ✅ YES, if exported as static SVG | ✅ YES (edit SVG markup in any editor) | ❌ NO (must edit CSS code) | ❌ NO (must edit JavaScript code) |
| **Can edit output then re-export to same format?** | ✅ YES! (edit SVG → save as SVG) | ❌ NO¹⁴ (AE → JSON is one-way, cannot import JSON back to AE) | ✅ YES (within same animation app) | ❌ NO (cannot import .riv back to editor) | ✅ YES, if using FLA/XFL source (but not for animated SVG) | ✅ YES (SVG → SVG) | ✅ YES (SVG+CSS → SVG+CSS) | ❌ NO (cannot easily reverse-engineer JS animations) |
| **Creation format same as playback format?** | ✅ YES! (SVG → SVG) | ❌ NO (After Effects → JSON) | ❌ NO (animation app → JSON+PNG or video) | ❌ NO (Rive Editor → .riv) | ❌ NO (FLA/XFL → Canvas/Video, or static SVG) | ✅ YES (SVG → SVG) | ✅ YES (SVG+CSS → SVG+CSS) | ❌ NO (authored code → runtime execution) |
| **Usable as exchange format between apps?** | ✅ YES!¹⁵ (SVG is universal standard) | ❌ NO (locked to After Effects workflow) | ✅ YES (OCA's main purpose: cel animation interchange) | ❌ NO (locked to Rive ecosystem) | ✅ YES, for static SVG (FLA/XFL can be opened in other Adobe tools) | ✅ YES (standard SVG) | ✅ YES (standard SVG+CSS) | ❌ NO (code-based, no standard format) |

### Playback & Runtime Capabilities

| Capability | **FBF.SVG** | Lottie/Bodymovin | OCA | Rive | Adobe Animate | SMIL | CSS + SVG | WAAPI |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Can play in browsers without JavaScript?** | ✅ YES!¹⁶ (native SVG support) | ❌ NO¹⁷ (requires lottie-web.js library ~160KB) | ✅ YES, if exported as video (uses HTML5 video tag) | ❌ NO¹⁸ (requires Rive runtime library) | ✅ YES, if exported as video | ✅ YES (native SVG+SMIL support) | ✅ YES (native CSS support) | ❌ NO (requires JavaScript API) |
| **Renders as true vector graphics (not rasterized)?** | ✅ YES! | ✅ YES, unless AE source has rasterized effects¹⁹ | ❌ NO (exports as raster video) | ✅ YES | ✅ YES, if Canvas export; ❌ NO if video export | ✅ YES | ✅ YES | ✅ YES |
| **Self-contained single file with no external dependencies?** | ✅ YES! (everything embedded in one SVG) | ✅ YES (single JSON with base64 embedded images) | ❌ NO (JSON + separate PNG frame files) | ✅ YES (single .riv file) | ✅ YES, if video; ❌ NO if Canvas (requires CreateJS libs) | ✅ YES | ✅ YES (if CSS embedded in SVG) | ❌ NO (SVG + external JavaScript file) |
| **Playback uses vector graphics throughout pipeline?** | ✅ YES! (SVG creation → SVG playback) | ✅ YES²⁰ (vector in AE, vector in JSON, vector rendering) | ❌ NO (cel animation → raster PNG → video) | ✅ YES | ✅ YES (vector creation, vector or video export) | ✅ YES | ✅ YES | ✅ YES |
| **Hardware-accelerated rendering performance?** | ✅ YES²¹ (browser GPU acceleration for SVG) | ✅ YES (Canvas 2D/WebGL rendering) | ✅ YES (hardware video decoding) | ✅ YES (optimized runtime) | ✅ YES (Canvas or video decoding) | ✅ YES, but SMIL deprecated in some browsers²² | ✅ YES (CSS animations use GPU) | ✅ YES (Web Animations API uses GPU) |

### Technical Features

| Capability | **FBF.SVG** | Lottie/Bodymovin | OCA | Rive | Adobe Animate | SMIL | CSS + SVG | WAAPI |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Infinitely scalable (true vector format)?** | ✅ YES | ✅ YES | ❌ NO (rasterized video output) | ✅ YES | ✅ YES | ✅ YES | ✅ YES | ✅ YES |
| **Supports interactive user triggers (click, hover, etc.)?** | ✅ YES (via SVG events) | ✅ YES (via lottie-web API) | ❌ NO (video has no interactivity) | ✅ YES (state machines) | ✅ YES (event handlers) | ✅ YES (SVG events) | ✅ YES (:hover, :active, etc.) | ✅ YES (event listeners) |
| **Supports timeline scrubbing/seeking?** | ✅ YES (via SMIL controls) | ✅ YES (lottie-web API) | ✅ YES (video controls) | ✅ YES (runtime API) | ✅ YES (playback controls) | ✅ YES (SMIL timing) | ✅ YES (animation-play-state) | ✅ YES (Animation API) |
| **Supports looping animation?** | ✅ YES²³ (repeatCount attribute) | ✅ YES (loop parameter) | ✅ YES (video loop) | ✅ YES (loop setting) | ✅ YES | ✅ YES (SMIL repeat) | ✅ YES (animation-iteration-count) | ✅ YES (iterations property) |
| **Supports smooth keyframe interpolation (tweening)?** | ❌ NO, pre-rendered frames (all interpolations precalculated - no runtime computation = faster playback, higher frame rates) | ✅ YES (Bezier easing, full interpolation - computed at runtime) | ❌ NO, frame-based (traditional cel animation) | ✅ YES (full interpolation - computed at runtime) | ✅ YES (shape tweening, motion - computed at runtime) | ✅ YES (SMIL calcMode, keySplines - computed at runtime) | ✅ YES (timing-function, easing - computed at runtime) | ✅ YES (easing, custom curves - computed at runtime) |
| **Supports automatic path interpolation between shapes?** | ❌ NO, pre-rendered (interpolation precalculated into frames - no runtime computation) | ✅ YES (shape interpolation - computed at runtime) | ❌ NO, must be done via explicit frames | ✅ YES (interpolation support - computed at runtime) | ✅ YES (shape interpolation - computed at runtime) | ✅ YES (animate path d attribute - computed at runtime) | ✅ YES, but limited browser support (computed at runtime) | ✅ YES (path interpolation - computed at runtime) |

### Compatibility & Standards

| Capability | **FBF.SVG** | Lottie/Bodymovin | OCA | Rive | Adobe Animate | SMIL | CSS + SVG | WAAPI | **Alembic** (.abc) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Works in all modern web browsers?** | ✅ YES²⁴ (Chrome, Firefox, Safari, Edge - all support SVG 1.1) | ✅ YES (with lottie-web library) | ✅ YES (HTML5 video support universal) | ✅ YES (with Rive runtime) | ✅ YES (Canvas or video output) | ✅ YES, but Chrome deprecated SMIL (still works)²⁵ | ✅ YES (universal CSS animation support) | ✅ YES²⁶ (all modern browsers support Web Animations API) | ❌ NO (scene interchange format, not for web playback) |
| **Works on iOS and Android mobile devices?** | ✅ YES (using free SVG libraries) | ✅ YES (lottie-ios, lottie-android) | ✅ YES (native video players) | ✅ YES (rive-ios, rive-android) | ✅ YES (video or Canvas) | ✅ YES (but limited, Chrome deprecated SMIL) | ✅ YES (CSS animations supported) | ✅ YES (Web Animations API supported) | ❌ NO (production pipeline format, not for mobile) |
| **Works in video games and console games?** | ✅ YES! (as texture/sprite sequence in Unity, Godot, Unreal, etc.) | ❌ NO (requires web runtime, not available on consoles) | ❌ NO (video format not suitable for games) | ❌ NO (runtime not available on consoles) | ❌ NO (proprietary format, limited console support) | ❌ NO (SMIL not supported in game engines) | ❌ NO (CSS requires browser, not available in games) | ❌ NO (WAAPI requires browser, not available in games) | ⚠️ PARTIAL (engines can import .abc for 3D assets, not runtime animation) |
| **Works across multiple platforms (web, video editors, apps)?** | ✅ YES! (SVG works everywhere) | ❌ NO, web/mobile only²⁷ (limited video editor support) | ✅ YES, exports as video (works in all video workflows) | ❌ NO, web/mobile/games only (limited offline use) | ✅ YES (exports to multiple formats: video, Canvas, static SVG) | ✅ YES (SVG works in all contexts) | ❌ NO, web only²⁸ (CSS requires browser, no video editor support) | ❌ NO, web only (JavaScript API requires browser environment) | ❌ NO, VFX pipeline only (Maya, Houdini, Blender) |
| **Based on official W3C web standard (not proprietary)?** | ✅ YES! (SVG 1.1 and SVG 2.0 are W3C standards) | ❌ NO, open specification²⁹ (JSON spec is open but not W3C standardized) | ❌ NO (community-driven GPL-3.0 format, not official standard) | ❌ NO³⁰ (proprietary Rive format) | ❌ NO (proprietary Adobe formats: FLA, XFL) | ✅ YES (SMIL is part of SVG W3C standard) | ✅ YES (CSS Animations is W3C standard) | ✅ YES (Web Animations API is W3C standard) | ❌ NO (open VFX standard, Lucasfilm/Sony-sponsored) |
| **Widely known and familiar to developers?** | 🆕 NEW format (emerging in 2024-2025) | ✅ YES (very popular since 2015) | ❌ NO (niche in animation industry) | ✅ YES, growing rapidly (launched 2020) | ✅ YES (Adobe standard since Flash era) | ✅ YES, but declining (deprecated by Chrome) | ✅ YES (standard web development skill) | ✅ YES, growing (modern API adoption) | ✅ YES (VFX industry standard since 2011) |
| **Supported by many software tools and editors?** | 🆕 Growing³¹ (svg2fbf tool, standard SVG editors work) | ✅ YES³² (After Effects, LottieFiles, many exporters) | ✅ YES³³ (Krita, Blender, OpenToonz, After Effects support OCA) | ✅ YES³⁴ (Rive Editor, Figma plugin, growing ecosystem) | ✅ YES (Adobe Animate, many alternative tools) | ✅ YES (any SVG editor: Inkscape, Illustrator, etc.) | ✅ YES (any code editor, CSS authoring tools) | ✅ YES, growing (JavaScript IDEs, animation libraries) | ✅ YES (Maya, Houdini, Blender, Cinema 4D, many VFX tools) |

### Licensing & Commercial Use

| Capability | **FBF.SVG** | Lottie/Bodymovin | OCA | Rive | Adobe Animate | SMIL | CSS + SVG | WAAPI | **Alembic** (.abc) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Free from runtime/playback license fees?** | ✅ YES! (native browser support, no fees) | ✅ YES (lottie-web is MIT license, free) | ✅ YES (video playback free) | ✅ YES (Rive runtimes are MIT license, free) | ✅ YES (Canvas rendering free, or video) | ✅ YES (native browser support) | ✅ YES (native browser support) | ✅ YES (native browser support) | N/A (interchange format, not playback) |
| **Free creation tools available?** | ✅ YES! (Inkscape, Krita, Blender all free) | ❌ NO³⁶ (requires After Effects subscription $275/year) | ✅ YES (Krita, Blender, OpenToonz all free) | ✅ YES, but limited³⁷ (free tier exists, paid $168-540/year for production) | ❌ NO (Adobe Animate subscription $275/year) | ✅ YES (any text/SVG editor is free) | ✅ YES (any text/SVG editor is free) | ✅ YES (any text editor is free) | ✅ YES (Blender is free, Maya/Houdini are paid) |
| **Can artists create and deploy without programmers?** | ✅ YES! (drag-drop SVG to website, works immediately) | ❌ NO (requires developer to integrate lottie-web library) | ✅ YES (export video, upload anywhere) | ❌ NO (requires developer to integrate Rive runtime) | ✅ YES, if video export; ❌ NO if Canvas (needs integration) | ❌ NO (requires coding/editing SVG markup) | ❌ NO (requires coding CSS) | ❌ NO (requires coding JavaScript) | ❌ NO (production pipeline format, not for end-user deployment) |
| **Can use in commercial projects without fees?** | ✅ YES! (no royalties, no fees, no restrictions) | ✅ YES (output is yours, no fees) | ✅ YES (no fees) | ✅ YES (no fees) | ✅ YES³⁸ (output is yours after subscription paid) | ✅ YES (W3C standard, no fees) | ✅ YES (W3C standard, no fees) | ✅ YES (W3C standard, no fees) | ✅ YES (open source, BSD license) |
| **Can use in closed-source commercial products?** | ✅ YES (Apache 2.0 allows commercial use) | ✅ YES (MIT license allows commercial use) | ❌ NO, GPL-3.0 requires source disclosure³⁹ | ✅ YES (MIT license allows commercial use) | ✅ YES (subscription includes commercial rights) | ✅ YES (W3C standard, no restrictions) | ✅ YES (W3C standard, no restrictions) | ✅ YES (W3C standard, no restrictions) | ✅ YES (BSD license allows commercial use) |
| **Can distribute output files freely?** | ✅ YES! (SVG files are yours, distribute anywhere) | ✅ YES⁴⁰ (JSON files are yours, distribute freely) | ✅ YES (files are yours) | ✅ YES (but viewers need Rive runtime)⁴¹ | ✅ YES (output files are yours) | ✅ YES (SVG files, no restrictions) | ✅ YES (SVG+CSS files, no restrictions) | ✅ YES (but requires runtime environment) | ✅ YES (.abc files are yours, distribute freely) |

**📝 Note on Alembic:** Alembic (.abc) is included in this comparison because it's sometimes suggested for exporting animations from OpenToonz and other animation tools. **Alembic IS valuable for interoperability** - it's a **scene hierarchy editing format** that enables OpenToonz to exchange layered scene hierarchies (both 2D and 3D, including z-depth for parallax scrolling effects) with professional animation and VFX tools like Blender, Maya, and Houdini. This makes it excellent for cross-application workflows in animation production pipelines.

**Important distinction: Alembic and FBF.SVG serve different purposes that don't interfere with each other:**

- **Alembic** = Scene hierarchy **editing format** for interchange between professional animation tools (OpenToonz ↔ Blender ↔ Maya ↔ Houdini)
- **FBF.SVG** = Vector video **output format** for deploying animations to end users (web, mobile, apps, games)

Alembic is designed for production pipelines (sponsored by Lucasfilm and Sony Pictures Imageworks), not for end-user deployment. Key characteristics:

- **Cannot be played in web browsers** - Requires specialized animation/VFX software
- **Cannot be played in mobile apps** - No mobile playback support
- **Not for end-user consumption** - It's a scene hierarchy editing format, not a distribution format
- **Requires professional software** - Maya, Houdini, Blender, or similar tools needed to view/edit scene hierarchies
- **Scene interchange, not playback** - Designed to move scene data between animation tools during production

**When to use Alembic:** Exchanging animation work between professional tools (OpenToonz ↔ Blender, Maya ↔ Houdini, etc.) during production/editing.

**When to use FBF.SVG (or video):** Deploying finished animations for web, mobile, games, or general public consumption.

---

## JavaScript Libraries Comparison

These are programming libraries for manipulating or animating SVG, not animation formats themselves. They require the library to be loaded for playback.

| Library | License | Purpose | Bundle Size | Requires for Playback? | SVG Import | SVG Export |
|---|:---:|---|:---:|:---:|:---:|:---:|
| **Snap.svg**⁴² | Apache 2.0 | SVG manipulation/animation library | ~60KB min | ✅ YES | ❌ NO | ❌ NO |
| **Fabric.js**⁴³ | MIT | Canvas library with SVG import/export | ~200KB min | ✅ YES | ✅ YES | ✅ YES |
| **GraphicsJS**⁴⁴ | BSD-3 | SVG/VML graphics library | ~40KB min | ✅ YES | ❌ NO | ✅ YES |
| **Faces.js**⁴⁵ | Apache 2.0 | Cartoon face avatar generator | ~30KB min | ✅ YES | ❌ NO | ✅ YES (SVG) |
| **GreenSock (GSAP)**⁴⁶ | Commercial/Free | Professional animation library | ~50KB min | ✅ YES | ❌ NO | ❌ NO |
| **Anime.js**⁴⁷ | MIT | Lightweight animation library | ~17KB min | ✅ YES | ❌ NO | ❌ NO |
| **SVG.js**⁴⁸ | MIT | Lightweight SVG manipulation | ~20KB min | ✅ YES | ⚠️ Limited | ✅ YES |

**Note:** All JavaScript libraries require the library to be loaded and executed for playback. They are development tools, not self-contained animation formats.

---

## Animation Authoring Tools Comparison

These are software applications or platforms for creating animations, not file formats. They export to various formats.

| Tool | Type | License/Pricing | Platform | Exports To | Notes |
|---|:---:|---|:---:|---|---|
| **Tumult Hype**⁴⁹ | Desktop App | $99.99 (one-time) | macOS only | HTML5 + CSS + JS | Interactive HTML5 content |
| **Haiku Animator**⁵⁰ | Desktop App | Open Source (MIT) | Cross-platform | Lottie JSON | Now free, was $15/month |
| **Boxy SVG**⁵¹ | Web/Desktop | $9.99 (various plans) | Web, Windows, macOS, Linux | SVG | Online and desktop SVG editor |
| **LottieFiles**⁵² | Platform | Free / $192-495/year | Web | Lottie JSON | Animation marketplace/platform |
| **Creattie**⁵³ | Platform | $14.99-24.99/month | Web | Lottie JSON | Pre-made animation marketplace |
| **Sketch2React**⁵⁴ | Desktop Plugin | Free/Paid | macOS (Sketch) | React components | Sketch to React code converter |
| **Cavalry**⁵⁵ | Desktop App | Free/$24/mo/$599 | Windows, macOS | Various (AE, Lottie) | Motion design and animation |
| **Flow**⁵⁶ | Desktop App | $99 (one-time) | macOS | Video, GIF | Motion graphics tool |

---

## Mobile Animation Formats Comparison

**Key Insight for Mobile:** FBF.SVG uses standard SVG 1.1, which is supported by multiple FREE open-source libraries on both iOS and Android. Unlike proprietary mobile animation formats, there are **NO per-app fees, NO runtime licensing costs, and NO revenue sharing** when using FBF.SVG in mobile applications.

> **"With FBF.SVG in mobile apps, you pay ZERO licensing fees. Not per-app, not per-install, not revenue-based. Just FREE."**

### Main Mobile Animation Formats

| Capability | **FBF.SVG** | **Lottie** | **Rive** | **Spine** | **Flutter SVG** |
|---|:---:|:---:|:---:|:---:|:---:|
| **💰 LICENSING & COSTS** | | | | | |
| **Creation tool cost** | ✅ FREE (Inkscape, Krita, Blender, OpenToonz) | ❌ $275/year⁵⁷ (requires After Effects subscription) | ✅ FREE tier available, ❌ $168-540/year⁵⁸ for full features | ❌ $70-330⁵⁹ one-time purchase (+ optional $3,300/app enterprise) | ✅ FREE (any SVG editor) |
| **Runtime library cost** | ✅ FREE (open source: SVGKit, AndroidSVG, etc.) | ✅ FREE⁶⁰ (lottie-ios/android are MIT/Apache 2.0) | ✅ FREE⁶¹ (rive-ios/android are MIT) | ✅ FREE⁶² (included with Spine license) | ✅ FREE⁶³ (flutter_svg is MIT) |
| **Per-app licensing fees?** | ✅ NO, $0 | ✅ NO, $0 | ✅ NO, $0 | ✅ NO, $0 normally (⚠️ YES $3,300/app⁶⁴ for enterprise option) | ✅ NO, $0 |
| **Per-install or per-user runtime fees?** | ✅ NO, $0 | ✅ NO, $0 | ✅ NO, $0 | ✅ NO, $0 | ✅ NO, $0 |
| **Revenue sharing required with format owner?** | ✅ NO | ✅ NO | ✅ NO | ✅ NO | ✅ NO |
| **Export/production fees for shipping apps?** | ✅ NO, $0 | ✅ NO, $0 | ❌ YES, requires paid subscription⁶⁵ ($168-540/year for full export features) | ✅ NO, $0 (one-time license includes unlimited exports) | ✅ NO, $0 |
| **📱 MOBILE PLATFORM SUPPORT** | | | | | |
| **iOS native support available?** | ✅ YES⁶⁶ (using free libraries: SVGKit, Macaw, SwiftSVG) | ✅ YES (lottie-ios library) | ✅ YES (rive-ios library) | ✅ YES (spine-ios runtime) | ✅ YES (flutter_svg for Flutter apps) |
| **Android native support available?** | ✅ YES⁶⁷ (using free libraries: AndroidSVG, SVG-Android) | ✅ YES (lottie-android library) | ✅ YES (rive-android library) | ✅ YES (spine-android runtime) | ✅ YES (flutter_svg for Flutter apps) |
| **React Native framework support?** | ✅ YES (react-native-svg library) | ✅ YES (lottie-react-native) | ✅ YES (rive-react-native) | ✅ YES (community libraries) | N/A (Flutter only) |
| **Flutter framework support?** | ✅ YES (flutter_svg package) | ✅ YES (lottie package) | ✅ YES (rive package) | ✅ YES (community packages) | ✅ YES (native flutter_svg) |
| **Can play without proprietary runtime library?** | ✅ YES⁶⁸ (uses standard SVG rendering, available on all platforms) | ❌ NO (must bundle lottie-ios/android library) | ❌ NO (must bundle rive-ios/android runtime) | ❌ NO (must bundle spine-ios/android runtime) | ❌ NO (must include flutter_svg package) |
| **🎨 FORMAT & WORKFLOW** | | | | | |
| **Output is standard image file format?** | ✅ YES (standard SVG 1.1 image file) | ❌ NO (JSON data format, not an image) | ❌ NO (.riv proprietary binary format) | ❌ NO (proprietary binary + image atlas) | ✅ YES (standard SVG image file) |
| **Can artists edit output in graphic apps?** | ✅ YES (Inkscape, Illustrator, Affinity Designer, etc.) | ❌ NO (requires After Effects) | ❌ NO (requires Rive Editor) | ❌ NO (requires Spine Editor) | ✅ YES (any SVG editor) |
| **Artists can create without writing code?** | ✅ YES (use visual SVG editors, no coding needed) | ✅ YES, but requires After Effects (no coding in AE, but developer integration needed) | ✅ YES, but free version limited (Rive Editor is visual, but dev integration needed) | ✅ YES (Spine Editor is visual tool, but dev integration needed) | ✅ YES, but developer integration needed (SVG creation visual, Flutter code required) |
| **File format type** | SVG 1.1 (XML text format) | JSON (JavaScript Object Notation) | .riv (proprietary binary) | Binary + separate image atlas | SVG (XML text format) |
| **Based on official industry standard?** | ✅ YES (W3C SVG 1.1/2.0 standard) | ❌ NO, open specification (community JSON spec, not official standard) | ❌ NO (proprietary Rive format) | ❌ NO (proprietary Spine format) | ✅ YES (W3C SVG standard) |
| **⚡ TECHNICAL FEATURES** | | | | | |
| **Supports traditional frame-by-frame animation?** | ✅ YES (primary method: pre-rendered frames = no runtime interpolation computation, faster playback, higher frame rates) | ✅ YES, but manual (must create frames in After Effects - runtime interpolation used between frames) | ✅ YES, but manual (must create explicit frames - runtime skeletal animation) | ✅ YES (sprite-based frame animation - runtime bone deformation) | ✅ YES, but manual (must define all frames - pre-rendered approach) |
| **Supports runtime skeletal/bone animation (for interactive control)?** | N/A (pre-rendered: all movement precalculated, faster even on slow CPUs) | ❌ NO (runtime tween interpolation, not skeletal rigging) | ✅ YES (runtime bones, IK, skin deformation - requires CPU power) | ✅ YES (primary feature: runtime skeletal animation - requires CPU power) | N/A (pre-rendered: movement precalculated, faster on slow CPUs) |
| **Supports interactive state machines and triggers?** | ✅ YES, basic (SVG events: click, hover via SMIL) | ✅ YES (via lottie API and interactivity) | ✅ YES (powerful state machines built-in) | ✅ YES (animation mixing and events) | ✅ YES, basic (Flutter gesture handling) |
| **Maintains vector quality throughout pipeline?** | ✅ YES (vector creation → vector storage → vector display) | ✅ YES (vector in AE → vector JSON → vector rendering) | ✅ YES (vector throughout) | ✅ YES (vector with optional raster images) | ✅ YES (vector throughout) |
| **Typical animation file sizes** | ⚠️ VARIES (larger for complex frame-by-frame, KB to MB range) | ✅ SMALL (compact JSON, typically 10-100KB) | ✅ SMALL (binary compression, typically 10-100KB) | ✅ SMALL (binary + images, typically 50-200KB) | ⚠️ VARIES (SVG size depends on complexity) |

### iOS SVG Libraries (Open Source & FREE)

| Library | License | Full SVG 1.1 Support | Notes | GitHub Stars |
|---|:---:|:---:|---|:---:|
| **SVGKit**⁶⁹ | MIT | ⚠️ Most features | CoreAnimation rendering, mature library | 4.4k+ |
| **SVGView (Exyte)**⁷⁰ | MIT | ⚠️ Good coverage | SwiftUI native, modern | 800+ |
| **Macaw (Exyte)**⁷¹ | MIT | ⚠️ Good coverage | Vector graphics with SVG support | 6k+ |
| **SwiftSVG**⁷² | MIT | ⚠️ Basic | Lightweight, performant | 1.8k+ |

### Android SVG Libraries (Open Source & FREE)

| Library | License | Full SVG 1.1 Support | Notes | GitHub Stars |
|---|:---:|:---:|---|:---:|
| **AndroidSVG**⁷³ | Apache 2.0 | ✅ Almost complete | Best SVG 1.1 support, actively maintained | 1.3k+ |
| **SVG-Android**⁷⁴ | MIT | ⚠️ Good coverage | Android 4.0+, powerful | 1.1k+ |
| **Coil-SVG**⁷⁵ | Apache 2.0 | ⚠️ Basic | Image loading with SVG support | - |

### Cross-Platform Mobile Frameworks

| Framework | SVG Support Library | License | Full SVG 1.1 | Notes |
|---|---|:---:|:---:|---|
| **React Native** | react-native-svg⁷⁶ | MIT | ⚠️ Good coverage | Most popular, well-maintained |
| **Flutter** | flutter_svg⁷⁷ | MIT | ⚠️ Basic | No animation/SMIL support |
| **Xamarin** | SkiaSharp⁷⁸ | MIT | ⚠️ Good coverage | Cross-platform 2D graphics |
| **Ionic/Capacitor** | Native browser | N/A | ✅ Browser-dependent | Uses WebView |

### Key Findings: Hidden Costs in Mobile Animation

**FBF.SVG Advantages:**
- ✅ **$0 creation tools** (Inkscape, Krita, OpenToonz, Blender)
- ✅ **$0 runtime licenses** (uses free open-source SVG libraries)
- ✅ **$0 per-app fees** (no licensing per application)
- ✅ **$0 per-install fees** (no runtime charges)
- ✅ **$0 revenue sharing** (keep 100% of your revenue)
- ✅ **$0 export fees** (unlimited production use)
- ✅ **Standard format** (works with any SVG 1.1 library)

**Competitor Hidden Costs:**
- **Lottie**: ❌ Requires After Effects subscription ($22.99/mo = $275/year)
- **Rive**: ⚠️ Free tier limited, paid exports required for production ($14-45/mo = $168-540/year)
- **Spine**: ⚠️ Per-product option for large studios ($3,300 one-time per app for enterprise)
- **Unity Runtime Fee**: ✅ Cancelled in 2024 (after massive developer backlash)

**Real Cost Comparison Example** (1 year, 5 mobile apps):
- **FBF.SVG**: $0 (use Inkscape + free SVG libraries)
- **Lottie**: $275 (After Effects subscription only, runtime free)
- **Rive**: $168-540 (subscription for exports)
- **Spine Professional**: $330 (one-time) + $0 (runtime free for 5 apps)
- **Spine Enterprise** (per-product): $3,300 × 5 = $16,500 (if using per-product licensing)

> **"For mobile app developers: FBF.SVG saves you hundreds to thousands of dollars per year in licensing fees while giving you the freedom of a standard, open format."**

---

## References and Documentation

### Format Specifications

1. **FBF.SVG Apache 2.0 License**: https://github.com/Emasoft/svg2fbf/blob/main/LICENSE
2. **Lottie-web MIT License**: https://github.com/airbnb/lottie-web/blob/master/LICENSE.md
3. **OCA GPL-3.0 License**: https://github.com/RxLaboratory/OCA/blob/main/LICENSE
4. **Rive Runtimes MIT License**: https://github.com/rive-app/rive-cpp/blob/master/LICENSE
5. **Adobe Animate Pricing**: https://www.adobe.com/products/animate.html (Commercial subscription)
6. **W3C Standards**: https://www.w3.org/standards/ (Royalty-free, public domain standards)

### Creation Tools & Workflow

7. **FBF.SVG Free Tools**: Works with Inkscape (GPL), Krita (GPL), OpenToonz (BSD), Blender (GPL) - all free and open source
8. **Lottie Requires After Effects**: https://airbnb.io/lottie/ - "Export animations from After Effects using the Bodymovin plugin"
9. **OCA Free Tools**: https://oca.rxlab.guide/ - Plugins available for Krita, Blender, After Effects
10. **Rive Free Tier**: https://rive.app/pricing - Free tier available, paid plans for advanced features
11. **Adobe Animate Subscription**: https://www.adobe.com/products/animate.html - $22.99/month required
12. **FBF.SVG Mesh Gradients**: SVG 2.0 mesh gradients fully supported, polyfill injected when detected
13. **FBF.SVG Editable in Apps**: Output is standard SVG 1.1, editable in Inkscape, Adobe Illustrator, Affinity Designer, etc.
14. **Lottie Workflow**: https://lottiefiles.com/blog/working-with-lottie/how-to-edit-your-lottie-animation - "You cannot edit a Lottie file directly, you must go back to After Effects"
15. **FBF.SVG as Exchange Format**: Standard SVG accepted by all vector graphic applications, animation tools, and media software

### Playback & Runtime

16. **FBF.SVG No JavaScript**: Uses native SMIL animation (built into SVG standard), optional polyfill only for mesh gradients
17. **Lottie Requires JavaScript**: https://github.com/airbnb/lottie-web - JavaScript library required for playback (~160KB)
18. **Rive Requires Runtime**: https://rive.app/runtimes - Proprietary runtime required for playback
19. **Lottie Rendering Options**: https://github.com/airbnb/lottie-web#renderers - Supports SVG (vector), Canvas (raster), HTML renderers
20. **Lottie Vector Pipeline**: After Effects uses vector, but some effects are rasterized during JSON export
21. **SMIL Performance**: https://developer.mozilla.org/en-US/docs/Web/SVG/SVG_animation_with_SMIL - Native browser implementation
22. **SMIL Hardware Acceleration**: https://webkit.org/blog/ - WebKit does not hardware-accelerate SMIL transforms
23. **FBF.SVG Loop Modes**: Eight modes supported: once, once_reversed, loop, loop_reversed, pingpong_once, pingpong_loop, pingpong_once_reversed, pingpong_loop_reversed

### Browser Compatibility

24. **FBF.SVG Browser Support**: SMIL supported in Chrome, Firefox, Safari, Edge (Chromium-based) - https://caniuse.com/svg-smil
25. **SMIL Limited Support**: Not supported in Internet Explorer, Edge Legacy - https://caniuse.com/svg-smil (94% global support as of 2024)
26. **WAAPI Browser Support**: https://caniuse.com/web-animation - 98% global support, polyfill available
27. **Lottie Medium Limitations**: Requires JavaScript runtime, limited to web/mobile contexts
28. **CSS Animation Limitations**: CSS animations only work in browsers, not in video editors or standalone SVG viewers
29. **Lottie Standard Status**: JSON format is open, but tightly coupled to After Effects proprietary workflow
30. **Rive Proprietary**: .riv format is proprietary, though runtimes are open source (MIT)

### Tool Ecosystem

31. **FBF.SVG Tool Support**: svg2fbf (converter), Inkscape (frames), Krita (frames), OpenToonz (frames), Blender (frames via SVG export)
32. **Lottie Tool Support**: After Effects (Bodymovin plugin), Haiku Animator, LottieFiles platform, various web tools
33. **OCA Tool Support**: Krita (native plugin), custom plugins for other software - https://oca.rxlab.guide/
34. **Rive Tool Support**: Rive Editor only (proprietary) - https://rive.app/
35. **Adobe Animate License**: Subscription required ($22.99/month or $263.88/year) - https://www.adobe.com/products/animate.html
36. **After Effects Cost**: Required for Lottie creation - $22.99/month subscription - https://www.adobe.com/products/aftereffects.html
37. **Rive Pricing**: Free tier for personal/learning, paid tiers from $14-45/month for teams - https://rive.app/pricing
38. **Adobe Content Streaming**: No additional fees for streaming content created with Adobe tools, but creation requires subscription
39. **OCA GPL License**: Format is free, but reference implementation code is GPL-3.0 - https://codeberg.org/RxLaboratory/OCA

### Distribution

40. **Lottie Distribution**: lottie-web library is MIT licensed, can be distributed freely - https://github.com/airbnb/lottie-web/blob/master/LICENSE.md
41. **Rive Runtime Requirement**: .riv files require Rive runtime for playback - https://rive.app/runtimes
42. **Snap.svg**: https://github.com/adobe-webplatform/Snap.svg - Apache 2.0 license
43. **Fabric.js**: https://github.com/fabricjs/fabric.js - MIT license
44. **GraphicsJS**: https://github.com/AnyChart/GraphicsJS - BSD-3-Clause license
45. **Faces.js**: https://github.com/zengm-games/facesjs - Apache 2.0 license
46. **GSAP**: https://greensock.com/gsap/ - Free for most use cases, commercial license for business use
47. **Anime.js**: https://github.com/juliangarnier/anime - MIT license
48. **SVG.js**: https://github.com/svgdotjs/svg.js - MIT license
49. **Tumult Hype**: https://tumult.com/hype/ - $99.99 one-time purchase
50. **Haiku Animator**: https://github.com/HaikuTeam/animator - MIT license, open source
51. **Boxy SVG**: https://boxy-svg.com/pricing - Various pricing plans, $9.99 for desktop
52. **LottieFiles**: https://lottiefiles.com/pricing - Free tier, paid plans $192-495/year
53. **Creattie**: https://creattie.com/pricing - Subscription $14.99-24.99/month
54. **Sketch2React**: https://sketch2react.io/ - Free and paid tiers
55. **Cavalry**: https://cavalry.scenegroup.co/ - Free, Standard ($24/mo), Pro ($599 one-time)
56. **Flow**: https://createwithflow.com/ - $99 one-time purchase (development paused)

### Mobile Animation Formats & Libraries

57. **After Effects Pricing**: https://www.adobe.com/products/aftereffects.html - $22.99/month (required for Lottie creation)
58. **Rive Pricing**: https://rive.app/pricing - Free tier with limitations, Pro $14/mo, Org $45/mo, exports require paid tier for production
59. **Spine Pricing**: https://esotericsoftware.com/spine-purchase - Essential $70, Professional $330, Enterprise annual subscription
60. **Lottie-iOS License**: https://github.com/airbnb/lottie-ios/blob/master/LICENSE - Apache 2.0, free runtime
61. **Rive Runtimes License**: https://github.com/rive-app/rive-ios/blob/main/LICENSE - MIT, free runtime
62. **Spine Runtimes License**: https://esotericsoftware.com/spine-runtimes-license - Free runtime with editor license
63. **Flutter SVG License**: https://pub.dev/packages/flutter_svg - MIT, free and open source
64. **Spine Per-Product License**: https://esotericsoftware.com/spine-runtimes-license - $3,300 one-time per product for Enterprise (alternative to annual renewal)
65. **Rive Export Restrictions**: https://rive.app/pricing - Free tier limited to 3 files, exports to production require paid subscription
66. **iOS SVG Support**: https://developer.apple.com/forums/thread/113015 - No native SVG runtime support, requires third-party libraries
67. **Android SVG Support**: https://stackoverflow.com/questions/3889882/svg-support-on-android - VectorDrawable since Android 21, not full SVG 1.1
68. **SVG Standard Libraries**: Multiple free open-source libraries support standard SVG 1.1 (SVGKit, AndroidSVG, etc.)
69. **SVGKit**: https://github.com/SVGKit/SVGKit - MIT license, CoreAnimation-based SVG rendering for iOS
70. **SVGView by Exyte**: https://github.com/exyte/SVGView - MIT license, SwiftUI native SVG parser and renderer
71. **Macaw by Exyte**: https://github.com/exyte/Macaw - MIT license, vector graphics Swift library with SVG support
72. **SwiftSVG**: https://github.com/mchoe/SwiftSVG - MIT license, simple, performant, lightweight SVG parser
73. **AndroidSVG**: https://github.com/BigBadaboom/androidsvg - Apache 2.0, almost complete SVG 1.1 support, actively maintained
74. **SVG-Android**: https://github.com/MegatronKing/SVG-Android - MIT license, supports svg images for Android 4.0+
75. **Coil-SVG**: https://coil-kt.github.io/coil/svgs/ - Apache 2.0, SVG support for Coil image loading library
76. **React Native SVG**: https://github.com/software-mansion/react-native-svg - MIT license, most popular React Native SVG library
77. **Flutter SVG**: https://pub.dev/packages/flutter_svg - MIT license, basic SVG support without animation/SMIL
78. **SkiaSharp**: https://github.com/mono/SkiaSharp - MIT license, cross-platform 2D graphics API for .NET platforms

### Additional Technical References

- **Can I Use - SVG SMIL**: https://caniuse.com/svg-smil
- **Can I Use - CSS Animations**: https://caniuse.com/css-animation
- **Can I Use - Web Animations API**: https://caniuse.com/web-animation
- **MDN - SVG Animation with SMIL**: https://developer.mozilla.org/en-US/docs/Web/SVG/SVG_animation_with_SMIL
- **MDN - CSS Animations**: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Animations
- **MDN - Web Animations API**: https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API
- **W3C SVG Specification**: https://www.w3.org/TR/SVG/
- **W3C CSS Animations**: https://www.w3.org/TR/css-animations-1/
- **W3C Web Animations**: https://www.w3.org/TR/web-animations-1/

---

## Methodology

### Research Approach

This comparison table was created through:

1. **Primary Source Review**: Official documentation, specifications, and licensing files from GitHub repositories and project websites
2. **Technical Testing**: Hands-on testing of format capabilities, browser compatibility, and tool workflows
3. **Community Documentation**: Analysis of community resources, tutorials, and developer discussions
4. **Pricing Verification**: Review of official pricing pages and license agreements (as of November 2024)
5. **Browser Testing**: Verification using Can I Use database and direct browser testing

### Limitations & Disclaimers

- **Pricing Subject to Change**: Software and service pricing may change. Prices listed are accurate as of November 2024.
- **Feature Evolution**: Formats and tools are actively developed. Some limitations may be addressed in future releases.
- **Use Case Variance**: "Best" choice depends on specific project requirements, team skills, existing tools, and workflows.
- **Open Source Licenses**: GPL licenses have specific requirements for derivative works. Consult license text for details.
- **Subjective Assessments**: "Limited", "Growing", and "Partial" ratings reflect current (2024) ecosystem state and may improve.

### Update Schedule

This comparison will be updated:
- Quarterly for major changes (new versions, pricing changes, new tools)
- Annually for comprehensive review
- As needed for significant ecosystem developments

**Last major review:** November 12, 2024
**Next scheduled review:** February 12, 2025

### Contributing Corrections

Found an error or have updated information? Please submit:
- **Issues**: https://github.com/Emasoft/svg2fbf/issues
- **Pull Requests**: https://github.com/Emasoft/svg2fbf/pulls

Include references to official sources when submitting corrections.

---

## Summary: Why FBF.SVG?

Looking at the comprehensive comparison above, **FBF.SVG is the only format that achieves:**

✅ **Complete Openness**: Created with free tools, output is standard SVG
✅ **Zero Dependencies**: Self-contained files, no JavaScript required
✅ **True Standards-Based**: Built on W3C SVG specification
✅ **Universal Compatibility**: Works anywhere SVG works
✅ **Bidirectional Workflow**: Full round-trip editing capability
✅ **Artist-Friendly**: Edit output in any graphic application
✅ **Commercial-Friendly**: Apache 2.0 license, no fees

**FBF.SVG combines the best of both worlds:**
- The **openness and editability** of native SVG/SMIL
- The **single-file convenience** of Lottie
- The **artist workflow** of traditional animation
- The **standards compliance** of W3C formats
- Without the **vendor lock-in** of proprietary formats
- Without the **runtime dependencies** of JavaScript libraries

This makes FBF.SVG ideal for frame-by-frame vector animation that prioritizes **openness, standards, and artist control** over animation delivery.

---

**📥 [Download Excel Version](../assets/comparison_table.xlsx)** — Spreadsheet with all comparison data

**🏠 [Back to Main README](../README.md)** — Return to project documentation
