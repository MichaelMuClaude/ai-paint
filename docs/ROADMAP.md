# Roadmap: from a paint tool to a manga-page tool

Goal: an AI agent can draw a manga page the way a manga artist does: clean line art with tapered strokes, panels, screentones, speech balloons, and lettering, with each step checked by looking at a render.

## Milestones

1. **Line art** (in progress)
   - Done: tapered strokes (`taper`), SVG paths with curves and arcs, layer outlines (`outline`).
   - Next: a stroke width profile (thick to thin along a stroke), and a line stabiliser that smooths a hand-written path.
2. **Page layout** (first version done)
   - Done: page presets (`--preset manga-b5`, `manga-b6`) at 300 dpi; panels as framed rectangles; speech balloons with tails (`balloon`); CJK text through Noto Sans CJK (`font`); examples/manga-page-changes.json.
   - Next: slanted panels, vertical text for Japanese-style lettering, and balloon padding rules.
3. **Screentones** (first version done)
   - Done: generated dot screens, as a fill with `density`, `cell` and `angle`. No downloads are needed, so there is no licence issue.
   - Next: line screens and gradient screens.
4. **Reference sketches** (first version done)
   - Done: `ai-paint trace` turns a picture's dark lines into path ops, using ImageTracer (public domain). It was tested on a CC0 figure sheet from OpenGameArt.
   - Done too: `--thicken` for bolder lines. It also cleared the dark shadow patch, which had come through as solid black.
   - Next: a reference layer that is shown while drawing but not exported.
5. **Character construction**
   - A skeleton of bones for pose, with body parts attached to bones, so a pose change moves the whole figure.
6. **Review loop**
   - Render, look at the page, and fix. Grid and zoom views are already there.

## What other open-source projects teach us

| Project | Licence (to check before copying anything) | What to learn |
|---|---|---|
| [Krita](https://github.com/KDE/krita) | GPL | Brush engine, stroke stabilisation, one stroke is one undo step |
| [MyPaint](https://github.com/mypaint/mypaint) | GPL | Mapping pressure and speed onto brush settings |
| [Synfig](https://github.com/synfig/synfig) | GPL | Skeleton rigs: each part is a layer attached to a bone |
| [ImageTracer](https://github.com/jankovicsandras/imagetracerjs) | Unlicense (checked in jspaint's `lib/imagetracer_v1.2.5.js`) | Tracing a bitmap into smooth curves |
| [Potrace](https://potrace.sourceforge.net/) | GPL | Tracing black-and-white bitmaps |
| [Graphite](https://github.com/GraphiteEditor/Graphite) | Apache-2.0 / MIT | Non-destructive, node-based effects |

## Rules we keep

- Do not copy code from GPL projects. Learn from the design, and write our own code.
- Do not copy or trace official artwork of existing characters. Use the user's own sketches, or original designs.
- Every milestone ends with rendered pages that the user can look at.
