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

## Round 2 (after `place` and `erase`)

I made a poster with a pasted logo, a bitten hole in a band, and two-line text. The same test as round 1, run again.

| # | What I tried | What happened | Decision |
|---|---|---|---|
| 6 | Paste a logo with a relative path, from another working folder | Not possible before. Paths were read from the current folder | Relative paths now follow the document's folder |
| 7 | Erase a hole, with the background the same colour | The hole did not show. Erasing reveals the background, which matched it | Expected behaviour. Noted in the docs |
| 8 | Fit a title in a space | Guessed from the render each time | Added `measure` (width and height of a line of text) |
| 9 | Change the background colour after creating the document | Not possible | Added `canvas` to changes |
| 10 | Type two lines in `measure` on the command line | A typed `\n` was read as two characters | `measure` reads `\n` as a new line |

## Still missing

- Reordering layers, and rotating or scaling existing ops. Documented as workarounds.

## Round 3 decision

The tool now covers the drawing tasks I tried. Changes are by id, and checking is by rendering and looking. The next thing to test is a larger, real-looking piece with many layers, to see whether the file gets hard to read.

## Round 4: a larger picture (270 ops, six layers)

I drew a night skyline: stars, a moon, twelve buildings with about 190 windows, and a title. Rendering took about 0.07 seconds, and `list --layer windows` found the window ops straightaway.

| # | What I tried | What happened | Decision |
|---|---|---|---|
| 11 | Cut a crescent from the moon with a disc in the sky colour | The disc showed as a dark patch where the sky changed colour | Use `erase` on the moon layer instead. Matching colours is fragile |
| 12 | Write 270 ops by hand | Too slow to write directly. I generated the window ops with a short script, then applied the file | No change. Scripts are a fine way to produce changes files |

The picture is judged satisfactory for drawing and editing. The remaining gaps are layer reordering and rotation, both documented.
