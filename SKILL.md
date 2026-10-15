---
name: ai-paint
description: Draw or edit a picture from a JSON document of explicit operations (strokes, lines, rectangles, ellipses, polygons, and flood fills, on layers). Use when the user asks to draw, sketch, paint, colour in, or mock up a picture from scratch. Every change is a separate operation with an id, so an agent can add, check, and correct one piece at a time. The input document is never overwritten.
---

# ai-paint

## Workflow

1. Create a document: `ai-paint new drawing.json --width 640 --height 400`.
2. Read the operations: `ai-paint ops`. Use only the parameters it lists.
3. Write the changes as JSON, for example `{"ops": [{"op": "rect", "layer": "l1", "box": [20, 20, 200, 120], "fill": "#ffcc00"}]}`.
4. Apply the changes to a new file: `ai-paint apply drawing.json --changes changes.json -o drawing-2.json`. `apply` refuses any change that would make the document invalid, and says why.
5. Check any document at any time: `ai-paint validate drawing-2.json`.
6. Render it: `ai-paint render drawing-2.json -o drawing-2.png`, then look at the PNG with the Read tool and compare it with what the user asked for.
7. If something is wrong, write a new changes file and apply it to a new file name. Do not overwrite earlier results.

Use `ai-paint info FILE` to see the layers, the op counts, and any problems in one place.

## Rules

- Never write to the input document or picture. Always use a new output name.
- Coordinates are pixels from the top-left corner. `box` is `[x, y, width, height]`.
- Operations are drawn in order, so a later one lands on top of an earlier one in the same layer.
- To fill inside a shape, draw its outline first on the same layer, then use `fill` from a point inside it.
- Colours are names such as `red`, or `#rrggbb` or `#rrggbbaa` for transparency.
- Layers are stacked in list order, bottom first. A layer with `"visible": false` is not drawn.

## Limits

- No text, image placement, or erase operations yet.
- Shapes have hard edges. Anti-aliasing is not in yet.
- Canvas up to 10,000 pixels on each side and 25 million pixels in total.
