# ai-paint

Draw pictures from a JSON document of explicit operations. An AI agent can read the document, add or change one operation, check it, and render a PNG to look at.

Most paint programs keep their work in binary files and need a person at the screen. ai-paint keeps everything in plain JSON: each stroke, shape, and fill is one item in a list with its own `id`.

```bash
ai-paint new drawing.json --width 640 --height 400
ai-paint apply drawing.json --change '{"ops":[{"op":"rect","layer":"l1","box":[20,20,200,120],"fill":"#ffcc00","outline":"#000000","width":3}]}' -o drawing-2.json
ai-paint validate drawing-2.json
ai-paint render drawing-2.json -o drawing.png
```

## The document

```json
{
  "schema": "ai-paint/1",
  "canvas": {"width": 640, "height": 400, "background": "#ffffff"},
  "layers": [{"id": "l1", "name": "base", "opacity": 1.0, "visible": true, "blend": "normal"}],
  "ops": [
    {"id": "o1", "op": "rect", "layer": "l1", "box": [20, 20, 200, 120], "fill": "#ffcc00"}
  ]
}
```

- Operations are drawn in order. A later one lands on top of an earlier one in the same layer.
- Layers are stacked in list order, bottom first. A hidden layer (`"visible": false`) is skipped when rendering.
- `background: null` gives a transparent canvas.
- Colours are names such as `red`, or `#rrggbb` or `#rrggbbaa` (the last two digits are alpha).
- Coordinates are pixels from the top-left corner.

## Operations

Run `ai-paint ops` for the full list with types and limits, generated from the code.

| Op | What it draws |
|---|---|
| `stroke` | A path of points with a `round` (hard edge) or `soft` (feathered) brush. `size` is the diameter. `size_end` makes the width change evenly to a second size, for example an arm that thins from 34 to 22. `taper` narrows both ends to a point. |
| `line` | A straight line or polyline with hard edges and `width` |
| `rect` | A rectangle given as `[x, y, width, height]`, with `fill`, `outline`, or both |
| `ellipse` | An ellipse inside the same kind of box |
| `polygon` | A closed shape through a list of points, with `fill`, `outline`, or both |
| `text` | Text at a point, in a `size` in pixels. `align` (left, center, right) and `valign` (top, middle, bottom) say which part of the text sits on the point. Use `\n` for a new line. The built-in font covers Latin letters; pass `font` (an absolute path to a `.ttf` or `.otf` file) for other scripts. |
| `place` | Paste a PNG, JPEG, or WebP picture with its top-left corner at a point. Its own transparency is kept. `width` or `height` resizes it, keeping its proportions. |
| `erase` | Make a `rect` or `ellipse` box transparent on its own layer. `opacity` 1 removes it fully. |
| `balloon` | A speech balloon: an ellipse around centred text, with a `tail` that points at a character. Text uses `size`, and `font` takes a CJK font for Chinese or Japanese. |
| `svg` | Draw SVG code inside a box on a layer: groups and transforms (rotate, scale, mirror), clip paths, masks, `<use>` to reuse shapes, gradients, blur and drop-shadow filters, and text. Give `svg` (markup) or `file` (a `.svg` file). Scripts, event attributes and outside links are refused. Drawn by the system's librsvg. |
| `limb` | A tapered capsule through 2 or 3 joints: `[shoulder, hand]` for a straight limb, or `[shoulder, elbow, hand]` for a bend, smoothly curved through the middle joint. Use it for arms, legs, necks and tails instead of a hand-tuned path. |
| `spline` | A smooth curve through key points you give, so you do not have to work out control points. `closed` loops back to the start. Fill and outline work. |
| `path` | A shape or line from SVG path data: `M`, `L`, `H`, `V`, `C`, `S`, `Q`, `T`, `A` (arc), `Z`, absolute or relative. Arc flags are separate `0` or `1` numbers. Curves are smooth. Use it for faces, limbs, clothing, and anything organic. `fill` and `outline` both work. |
| `fill` | Flood fill from a seed point on its layer. `tolerance` (0 to 255) is the total difference allowed across red, green, blue and alpha, so `6` lets through a pixel that is 2 darker in each of R, G and B. |

Fills and outlines (`fill`, `outline`) take a colour, or a gradient:

```json
{"type": "linear", "from": [0, 0], "to": [0, 300], "stops": [[0, "#ff9e6d"], [1, "#ffe9c2"]]}
{"type": "radial", "centre": [315, 85], "radius": 33, "stops": [[0, "#fff8dc"], [1, "#ffd166"]]}
```

Stop positions go from 0 to 1. A layer can be blurred for glows and soft shadows with `"blur": 14` (pixels), set in the layer's entry in `layers`.

A layer can also get a cartoon outline with `"outline": {"colour": "#2b1a10", "width": 2}`. The outline goes around every shape on that layer, under the shapes. Put shapes that should share an outline on one layer.

Outline `width` can be a decimal, for example `2.5`, down to `0.5`.

A fill can also be a screentone, the dot pattern manga artists use for grey: `{"type": "screen", "density": 0.3, "cell": 10, "angle": 45}`. `density` is the grey share, from above 0 to 1. `cell` is the dot spacing in pixels.

Every drawing op also takes `layer` (required), `id` (optional), and `opacity` (0 to 1, default 1). Relative picture and font paths are read from the document's own folder, so a document and its pictures can be moved together. The `fill` op sets pixels to the colour and does not blend.

- Shapes and strokes are anti-aliased: edges are drawn at three times the resolution and averaged down. Coordinates are continuous, so the point `(x, y)` is a pixel corner, and a box `[x, y, 20, 20]` covers exactly 20 by 20 pixels. Outlines are centred on the box edge.

## Drawing with SVG code

For detailed drawings, especially characters, the `svg` op is the most flexible tool. An agent can write SVG it already knows, and still use ai-paint's layers, grid views, balloons, screentones and tracing around it:

```bash
ai-paint apply page.json --change '{"ops":[{"op":"svg","layer":"l1","file":"girl.svg"}]}' -o page-2.json
```

Without an `<svg>` root, the markup's coordinates are the box's own pixels. SVG drawing needs librsvg and cairo (packages `librsvg2-2` and `libcairo2` on Debian and Ubuntu), loaded at run time and not bundled. See `examples/anime-girl.svg`: the eye is defined once and mirrored with `<use>`, the iris is clipped to the eye white, and blush uses a blur filter.

### The part library

ai-paint ships SVG parts that any `svg` op can use without defining them: anime eyes (open and closed), brows, three mouths, a nose, blush, two hairstyles (bob, ponytail), two hand poses (open, fist), and manga symbols and effects (sweat drop, anger mark, sparkle, heart, star, speed lines, impact burst, thought bubble). Write `<use href="#lib-eye-anime" transform="translate(120 80)" color="#3f7fe0"/>` and the part is added for you. Most parts take their colour from `color`, and `scale(-1 1)` mirrors them.

```bash
ai-paint parts                                        # list the parts and what they look like
ai-paint parts --preview lib-eye-anime -o eye.png     # draw one part
```

See `examples/expression-sheet.svg`: one character in four moods, 69 lines of SVG.

### Changing one element

Give SVG elements an `id`, then change them one at a time instead of rewriting the markup:

```json
{"svg_set": {"art": {"iris-left": {"fill": "#2e8b57"}}},
 "svg_remove": {"art": ["sweat"]},
 "svg_replace": {"art": {"mouth": "<use href=\"#lib-mouth-grin\" transform=\"translate(0 60)\"/>"}}}
```

`ai-paint elements DOC OP_ID` lists the elements with ids in an svg op. Edits work on inline `svg` markup; for a `.svg` file, edit the file.

### Exporting to SVG

`ai-paint export DOC -o page.svg` writes the whole document as one SVG file. Each layer becomes an Inkscape layer, with its opacity, blur and outline kept as SVG attributes and filters, so the page can be edited further in Inkscape or any SVG editor. Shapes, paths, strokes, text, balloons, gradients, screentones, erasing, pasted pictures and svg ops all become SVG elements. A flood fill works on pixels, so a layer that uses one is embedded as a picture, and the command's report lists such layers.

Exported files contain embedded pictures (`<image>`), so they cannot be fed back into an `svg` op, which refuses `<image>` for safety. Tests check that each kind of operation, exported and drawn by librsvg, matches ai-paint's own render closely.

## Tracing a sketch

`ai-paint trace PICTURE.png -o lines.json` turns the picture's dark lines into smooth path ops. Pixels darker than `--threshold` (default 30) count as lines. The output is a changes file: `apply` it to a canvas of the size the command reports, and the lines appear on their own layer. `--scale` and `--offset` move and resize the traced lines, so a figure can go into a panel. `--thicken N` grows the lines by N pixels (0 to 5) before tracing; use 2 for manga-weight lines. Thickening the mask works better than a layer outline, which doubles thin lines. Tracing uses [ImageTracer](src/ai_paint/vendor/README.md), which is public domain, and needs Node.js.

## Commands

| Command | Purpose |
|---|---|
| `new FILE --width W --height H` | Create an empty document with one layer. Or use `--preset manga-b5` (182 × 257 mm at 300 dpi) or `--preset manga-b6` (128 × 182 mm). |
| `info FILE` | Show canvas, layers, op counts, and any problems, as JSON |
| `ops` | List operations and their parameters |
| `validate FILE` | Check a document without drawing |
| `export FILE -o PAGE.svg` | Write the whole document as one SVG file with Inkscape layers |
| `parts` | List the built-in SVG parts; `--preview NAME -o PICTURE.png` draws one |
| `elements FILE OP_ID` | List the elements with ids inside an svg op |
| `measure --text T --size N [--font F]` | Width and height in pixels of a line of text, so you can fit it |
| `apply FILE --changes CHANGES.json -o NEW.json` | Add layers and ops and write a new document. The input is never changed. |
| `render FILE -o PICTURE.png` | Draw the document. Output can be `.png`, `.jpg`, or `.webp`. Add `--grid STEP`, `--crop X,Y,W,H`, and `--zoom N` to look at it more closely (see below). |

`apply` takes a JSON object. All keys are optional:

| Key | Effect |
|---|---|
| `layers` | Add layers to the top of the stack |
| `ops` | Append operations, in order |
| `update` | `{"op-id": {"fill": "#ffd6a5"}}` changes only the fields given |
| `remove` | `["op-id", ...]` deletes ops |
| `update_layers` | `{"layer-id": {"opacity": 0.5}}` changes layer fields |
| `remove_layers` | `["layer-id", ...]` deletes layers that have no ops left |
| `canvas` | `{"background": "#0b132b"}` changes the canvas background (or width and height) |

Items without an `id` get one. The result is validated before anything is written, and errors name the op id.

`ai-paint list FILE` shows every op with its id, layer, and values. Use `--text` for one line per op, and `--layer ID` to filter.

### Looking at a picture

To place things accurately, render with a grid. The grid has a line every `STEP` pixels, a darker line every fifth, and labels with the picture's own coordinates:

```bash
ai-paint render drawing.json -o grid.png --grid 20
ai-paint render drawing.json -o detail.png --grid 10 --crop 280,40,120,120 --zoom 3
```

`--crop` writes only part of the picture, and `--zoom` (1 to 8) enlarges it with hard pixels. Grid and crop are for looking only, and the document is not changed. The JSON printed by `render` records them in a `view` block, so a view is never mistaken for the real output.

Use `--force` to replace an existing output file. The input document or picture is never overwritten.

## Install

```bash
pip install -e .            # needs Pillow and numpy
pip install -e ".[dev]"     # adds pytest
```

Requires Python 3.10 or newer.

## Limits

- Canvas up to 10,000 pixels on each side and 25 million pixels in total. Each layer is held in memory at full canvas size.
- A stroke can have up to 5,000 points and 200,000 dabs.
- Each shape or stroke needs up to nine times its own area of temporary memory while it is drawn.
- The built-in font is Latin only. Other scripts need a `font` file.
- Layers keep their order. To change it, remove the layer's ops and layer, and add them again.
- No rotation or scaling of existing ops yet; `place` can resize pictures only when placed.

## Licence

MIT. See [LICENSE](LICENSE).
