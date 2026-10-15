# Roadmap: from a paint tool to a manga-page tool

Goal: an AI agent can draw a manga page the way a manga artist does: clean line art with tapered strokes, panels, screentones, speech balloons, and lettering, with each step checked by looking at a render.

## Milestones

1. **Line art** (in progress)
   - Done: tapered strokes (`taper`), SVG paths with curves and arcs, layer outlines (`outline`).
   - Next: a stroke width profile (thick to thin along a stroke), and a line stabiliser that smooths a hand-written path.
2. **Page layout**
   - Page sizes (for example B5 and A4) with a margin.
   - Panels: rectangles with borders and gutters, plus slanted panels.
   - Speech balloons: an ellipse or rounded shape with a tail path, and text centred in it (`align`, `valign`, `measure`).
   - Vertical text for Japanese-style lettering.
3. **Screentones**
   - A pattern fill: dot and line screens, with a density and an angle. Pillow can generate the dot pattern.
4. **Reference sketches**
   - A `trace` command that turns a user-supplied sketch into path ops.
   - A reference layer that is shown while drawing but not exported.
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
