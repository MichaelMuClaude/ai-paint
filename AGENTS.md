# AGENTS.md — guide for AI agents contributing to ai-paint

This file is for AI coding agents that read, test, or change this project. The human-facing rules are in the README.

## What this project is

`ai-paint` draws pictures from a JSON document. The document is a list of operations, each with an `id`. An agent can read it, add or change one operation, check it, and render a PNG to look at. It is built for AI agents, not for drawing by hand.

## Promises to keep

1. **The input is never overwritten.** `apply` and `render` refuse an output that is the input file.
2. **Validate before drawing.** Every operation passes `ops.normalise` before any pixel is touched. Unknown fields and values are errors, never ignored.
3. **Every operation is in `ops.py`.** Each has a summary, typed parameters with limits, and an implementation. The `ops` command is generated from that list.
4. **Stable output.** Commands print JSON. Keep the keys stable.
5. **Limits stay.** `MAX_PIXELS`, `MAX_POINTS`, and `MAX_DABS` protect memory and time. Do not remove them.
6. **No network access.** Everything is local.

## Layout

```
src/ai_paint/
  params.py    parameter types, colour parsing, value checks
  ops.py       operations, their parameters and drawing code
  raster.py    brush dabs, shape masks, compositing, flood fill, layer blur
  svgpath.py   SVG path data: parsing and curve flattening
  gradient.py  linear and radial gradient fills
  svgrender.py SVG allow-list check, drawing through the system's librsvg and cairo (ctypes),
               the part library loader, and element edits by id
  library/     built-in SVG parts (eyes, hair, hands, mouths, manga effects); each file's ids start with lib-<file name>
  export.py    compiles a whole document into one SVG (Inkscape layers, filters, masks, patterns)
  document.py  document schema, validation, rendering, apply, save
  view.py      grid overlay, crop and zoom (for looking only)
  cli.py       new, info, ops, validate, apply, render
tests/         pytest suite; test_ops, test_document, test_cli, test_view
```

## Setup and checks

```bash
python3 -m venv ~/.venvs/ai-paint-dev
~/.venvs/ai-paint-dev/bin/pip install -e ".[dev]"
~/.venvs/ai-paint-dev/bin/python -m pytest -q
```

## Adding an operation

1. Write the drawing function in `ops.py` and register it with `_register`, with a summary and typed parameters.
2. Add a `check` if some combinations of parameters are not allowed.
3. Add tests that check pixels in the rendered output, and tests for each invalid value.
4. Update the operation table in `README.md` and `SKILL.md`.

## Known behaviour to keep in mind

- Every op type must stay exportable: when you add an op, add it to `export.py` and to the comparison cases in `tests/test_export.py`.
- The `svg` op must keep its allow-list in `svgrender.py`: no scripts, no event attributes, no `<image>` or `<foreignObject>`, no DOCTYPE, and every `href` or `url()` must point inside the same SVG. Add a refusal test for every new rule.
- `apply` only changes ops by id: `update` merges fields, `remove` deletes. An op id cannot be changed.
- `fill` tolerance is the total difference over red, green, blue and alpha, because that is what Pillow's flood fill uses. The README states it.
- Strokes merge their dabs with `lighter`, so a semi-transparent stroke has one strength along its path.
- Coordinates are continuous: a point is a pixel corner. Shapes and strokes are drawn at `raster.AA` times the resolution in a small region, then averaged down. Keep that, or edges will look jagged again.

## Rules for changes

- One change per pull request, with tests.
- Keep the Python floor at 3.10.
- Do not add a dependency unless Pillow cannot do the job. numpy was added for gradients and layer blur, which need per-pixel maths.
