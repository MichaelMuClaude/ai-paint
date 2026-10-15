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
| `stroke` | A path of points with a `round` (hard edge) or `soft` (feathered) brush, `size` is the diameter |
| `line` | A straight line or polyline with hard edges and `width` |
| `rect` | A rectangle given as `[x, y, width, height]`, with `fill`, `outline`, or both |
| `ellipse` | An ellipse inside the same kind of box |
| `polygon` | A closed shape through a list of points, with `fill`, `outline`, or both |
| `text` | Text at a point, in a `size` in pixels. `align` (left, center, right) and `valign` (top, middle, bottom) say which part of the text sits on the point. Use `\n` for a new line. The built-in font covers Latin letters; pass `font` (an absolute path to a `.ttf` or `.otf` file) for other scripts. |
| `fill` | Flood fill from a seed point on its layer. `tolerance` (0 to 255) is the total difference allowed across red, green, blue and alpha, so `6` lets through a pixel that is 2 darker in each of R, G and B. |

Every drawing op also takes `layer` (required), `id` (optional), and `opacity` (0 to 1, default 1). The `fill` op sets pixels to the colour and does not blend.

Shapes and strokes are anti-aliased: edges are drawn at three times the resolution and averaged down. Coordinates are continuous, so the point `(x, y)` is a pixel corner, and a box `[x, y, 20, 20]` covers exactly 20 by 20 pixels. Outlines are centred on the box edge.

## Commands

| Command | Purpose |
|---|---|
| `new FILE --width W --height H` | Create an empty document with one layer |
| `info FILE` | Show canvas, layers, op counts, and any problems, as JSON |
| `ops` | List operations and their parameters |
| `validate FILE` | Check a document without drawing |
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
pip install -e .            # needs Pillow
pip install -e ".[dev]"     # adds pytest
```

Requires Python 3.10 or newer.

## Limits

- Canvas up to 10,000 pixels on each side and 25 million pixels in total. Each layer is held in memory at full canvas size.
- A stroke can have up to 5,000 points and 200,000 dabs.
- Each shape or stroke needs up to nine times its own area of temporary memory while it is drawn.
- The built-in font is Latin only. Other scripts need a `font` file.
- There is no image placement or erase operation yet.

## Licence

MIT. See [LICENSE](LICENSE).
