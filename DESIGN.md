# ai-paint: design notes

Status: version 0.1.0 has the document format, validation, six drawing operations, rendering, and the CLI. 57 tests pass. Text, image placement, and erase are not built yet.

## Why build it

No mainstream open-source paint program is built for AI agents. Each one is GUI-first: the document lives in a binary file, and every action is a click or a drag. An agent can't read it, edit one stroke, or check the result without a screen.

ai-paint is a command-line paint tool where the document is plain JSON, every change is a typed operation, and the output is a PNG that the agent can look at.

## What we looked at

Shallow clones were made into the session scratchpad. Nothing was built or run from them, and no code was copied.

| Project | Licence | Language | What we learned |
|---|---|---|---|
| [excalidraw](https://github.com/excalidraw/excalidraw) | MIT | TypeScript | Closest to AI-friendly. The scene is a flat list of JSON elements with stable `id`s and `version` numbers. Its `transform.ts` converts a short "skeleton" input into full elements with defaults filled in. |
| [graphite](https://github.com/GraphiteEditor/Graphite) | Apache-2.0 / MIT | Rust | The document is a node graph, and every edit stays re-editable. This supports the idea of a document that is a list of operations, with the picture derived from them. |
| [mypaint](https://github.com/mypaint/mypaint) | GPL | Python + C++ | Strokes are turned into dabs placed along the path at a spacing tied to the brush radius. Its brush file has 53 settings, which is too many for an agent. We keep two presets. |
| [krita](https://github.com/KDE/krita) | GPL-2.0+ | C++ | A whole stroke is one undo unit. Its code is large and tied to Qt, so we take the idea only. |
| [pinta](https://github.com/PintaProject/Pinta) | MIT | C# | Tools are kept apart from history, and history items store surface diffs. |
| [jspaint](https://github.com/1j01/jspaint) | MIT | JavaScript | A short list of tools covers most everyday needs. |

Licence rule: GPL code is not copied. Everything in ai-paint is written from scratch under MIT.

## What was built, and the decisions behind it

### The document

```json
{
  "schema": "ai-paint/1",
  "canvas": {"width": 640, "height": 400, "background": "#ffffff"},
  "layers": [{"id": "l1", "name": "base", "opacity": 1.0, "visible": true, "blend": "normal"}],
  "ops": [{"id": "o1", "op": "rect", "layer": "l1", "box": [20, 20, 200, 120], "fill": "#ffcc00"}]
}
```

- The file is the source of truth. `render` replays the ops in order onto each layer, then stacks the layers.
- Ids are stable. `apply` gives an id to any new item that has none.
- Undo is removing the last op. There is no separate history.

### Operations (version 1)

`stroke`, `line`, `rect`, `ellipse`, `polygon`, `fill`. Each is registered in `ops.py`, and the `ops` command is generated from that list.

Text, image placement, and erase come next.

### Decisions I made

- **Pillow only, no numpy.** Pillow handles masks, compositing, and flood fill. numpy was not installed, and this keeps the dependency list to one.
- **Full-canvas layers, no tile cache yet.** Each layer is one RGBA image. The canvas is capped at 25 million pixels, which keeps memory bounded. The 64 px tile cache from the first design is for when large canvases need it.
- **Shapes are drawn as masks, then blended.** Each shape becomes an L-mode mask, and the colour is composited through it with its alpha and the op's `opacity`. This gives correct blending for semi-transparent colours.
- **Strokes use `lighter` between dabs.** Overlapping dabs in one stroke do not add up, so a semi-transparent stroke has one strength along its path.
- **Two brush presets.** `round` has a hard edge. `soft` fades linearly from the centre to the rim. Both use dabs spaced at 20% (round) or 10% (soft) of the radius.
- **Fill tolerance is Pillow's rule.** Pillow compares the sum of the absolute differences over red, green, blue, and alpha. The README and the parameter description state this exactly, because the per-channel reading is what most people would guess, and it is wrong.
- **Fill sets pixels, it does not blend.** `fill` replaces matching pixels with the colour. Use a `#rrggbbaa` colour for a transparent fill.
- **Shapes are aliased.** There is no anti-aliasing yet. It can be added later as a supersampled mask.

### Not in version 1

- Real-time painting or tablet pressure. This is for agents, not for hand-drawing.
- PSD and other layered formats. PNG, JPEG, and WebP output are enough to start.
- Procedural node graphs like Graphite. The op list stays flat so it is easy to read.
- Brush files with many settings. The brush parameters stay a small set.

## Next steps

1. Text, using a font file the user supplies (the same rule as ai-photoshop).
2. Anti-aliased shape edges.
3. `place` (paste a PNG onto a layer) and `erase`.
4. A tile cache, if large canvases become slow.

## Open questions for the user

- Should ai-paint be published on GitHub? It is local git only for now. The repo is not committed yet.
- Are PNG, JPEG, and WebP enough for output, or is PSD needed?
