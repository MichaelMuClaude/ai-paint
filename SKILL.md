---
name: ai-paint
description: Draw or edit pictures and manga pages from a JSON document of layered operations, including SVG code (groups, transforms, mirroring, clip paths, gradients, blur filters), curves, tapered strokes, text in Latin or CJK fonts, speech balloons, screentones, pasted pictures, and tracing a sketch into line art. Use when the user asks to draw, paint, illustrate, design a character, or lay out a comic or manga page. Every change is a separate operation with an id, so an agent can check and correct one piece at a time, and render grid or zoomed views to look closely. The input document is never overwritten.
---

# ai-paint

## Workflow

1. Create a document: `ai-paint new drawing.json --width 640 --height 400`.
2. Read the operations: `ai-paint ops`. Use only the parameters it lists.
3. Write the changes as JSON, for example `{"ops": [{"op": "rect", "layer": "l1", "box": [20, 20, 200, 120], "fill": "#ffcc00"}]}`.
4. Apply the changes to a new file: `ai-paint apply drawing.json --changes changes.json -o drawing-2.json`. `apply` refuses any change that would make the document invalid, and says why.
5. Check any document at any time: `ai-paint validate drawing-2.json`.
6. Render it: `ai-paint render drawing-2.json -o drawing-2.png`, then look at the PNG with the Read tool and compare it with what the user asked for. To place things accurately, render with a grid first: `ai-paint render drawing-2.json -o grid.png --grid 20`. Zoom into a detail with `--crop X,Y,W,H --zoom 3`. Grids and crops are for looking only.
7. If something is wrong, write a changes file that uses `update` (change fields of an op by id) or `remove` (delete an op), and apply it to a new file name. Do not overwrite earlier results.

Run `ai-paint list drawing-2.json --text` to see every op's id before you change one.

Use `ai-paint info FILE` to see the layers, the op counts, and any problems in one place.

To hand a picture over for editing in Inkscape, run `ai-paint export drawing.json -o drawing.svg`. Layers stay separate.

## Rules

- Never write to the input document or picture. Always use a new output name.
- Coordinates are pixels from the top-left corner. `box` is `[x, y, width, height]`. Points can be decimals.
- Give important ops an `id` (for example `"id": "logo-box"`), so you can `update` or `remove` them later without looking up a generated id.
- Operations are drawn in order, so a later one lands on top of an earlier one in the same layer.
- To centre text on a point, use `"align": "center", "valign": "middle"`. Do not estimate the text width.
- Use the built-in parts before drawing your own: `ai-paint parts` lists eyes, brows, mouths, blush and manga symbols (`<use href="#lib-eye-anime" color="#3f7fe0"/>`). Define a character's head once in `<defs>` and reuse it for every pose or mood.
- Give elements ids, then adjust them with `svg_set`, `svg_remove` and `svg_replace` in a changes file instead of rewriting the SVG. `ai-paint elements DOC OP_ID` lists them.
- For an arm, leg, neck or tail, use `limb` with 2 or 3 joint points instead of guessing a `path` or `stroke` by hand. It tapers smoothly and bends through the middle joint.
- For characters and detailed drawings, prefer the `svg` op: write SVG with `<defs>`, `<use>` (mirror symmetric parts with `scale(-1 1)`), `clipPath` (keep an iris inside its eye), gradients, and `feGaussianBlur` for blush and shadows. It gives far better results than placing shapes one by one.
- For organic shapes (faces, limbs, clothes), use `path` with curves or arcs (`A`). Plain rectangles and ellipses look blocky.
- For a limb, use one `stroke` with `size` and `size_end`, so it thins from shoulder to wrist. It is easier than a closed path.
- For a smooth outline, give a `spline` a few key points instead of writing control points by hand.
- Faces need detail to read as faces: almond eyes with an iris and a highlight, tapered brows, a nose, and a grin with teeth. Blush on a blurred layer softens them. Check the face at `--crop ... --zoom 4`.
- Keep a hat's brim above the brows, or draw the features on a layer above the hat.
- Cartoon look: put the figure's silhouette parts on layers with `"outline"`. Flat colour with dark outlines reads as a cartoon; gradients on the figure do not.
- Use gradients for sky, sun, and shading. A `radial` gradient with a layer `blur` makes a glow.
- For a shadow or glow, put the shape on its own layer with `"blur"` and a lower `"opacity"`.
- To fill inside a shape, draw its outline first on the same layer, then use `fill` from a point inside it.
- Colours are names such as `red`, or `#rrggbb` or `#rrggbbaa` for transparency.
- Layers are stacked in list order, bottom first. A layer with `"visible": false` is not drawn.
- Put the sky or background first, then things that sit behind others on lower layers. Check overlaps in the grid render.

## Limits

- The built-in font is Latin only. For other scripts, pass `font` with a path to a `.ttf` or `.otf` file. Relative paths are read from the document's folder.
- To fit a line of text in a space, run `ai-paint measure --text "..." --size 40` first.
- Use `place` to paste a picture (PNG, JPEG, or WebP) and `erase` to cut a hole in a layer.
- Shapes and strokes are anti-aliased. A point `(x, y)` is a pixel corner, and `box` `[x, y, w, h]` covers exactly `w` by `h` pixels.
- Canvas up to 10,000 pixels on each side and 25 million pixels in total.
