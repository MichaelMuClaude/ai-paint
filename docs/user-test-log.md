# User test log

I used ai-paint as its end user, drawing three pictures: a three-step flowchart, a badge with a shadow and a custom font, and a seaside scene. For each problem I noted what I was trying to do, what happened, and what I changed.

## Round 1 (before the fixes)

| # | What I tried | What happened | Decision |
|---|---|---|---|
| 1 | Recolour one box after drawing it | Not possible. `apply` can only add ops, and reusing an id failed with "duplicate id" | Added `update` (merge fields into an op by id) and `remove` |
| 2 | Find the id of an op to change | `info` shows only counts per layer | Added `ai-paint list` with ids, layers, and values (`--text` for one line per op) |
| 3 | Centre a label in a box | Not possible. I placed labels by eye, then checked the grid render | Added `align` and `valign` to `text`, with the point as the anchor |
| 4 | Read an error for an op | "ops[10]: ..." gave no clue which op it was | Errors now include the id: "ops[1] (id disc): ..." |
| 5 | Change a layer's opacity or hide it after creating it | Not possible | Added `update_layers` and `remove_layers` (a layer can only be removed when no ops use it) |

## What worked well

- The grid render (`--grid`) made placement easy. Labels show picture coordinates even on a zoomed crop.
- Layer opacity gave a soft shadow with one shape (the badge).
- Custom fonts work through `font`.
- Error messages named the field and the reason, for example "box must be [x, y, width, height]" and "fill colour is not recognised: 'nope'".

## Still missing (not yet decided)

- **Placing an image** (`place`). I would need this to use a logo or photo.
- **Erasing** (`erase`). Covering with a background colour works, but it is not the same on a transparent layer.
- **Curves** need a list of many points. An `arc` op would be easier.
- **Rotation** is not supported. I could rotate text by drawing it in a separate layer, but there is no way to do that yet.

## Next step

`place` and `erase`, in that order. `place` is needed for real pictures, and `erase` can wait, because `update` and `remove` now cover most corrections.
