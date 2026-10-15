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

## Round 5: the Pirate King (the picture was judged weak)

I drew an original straw-hat captain (not an official character drawing) with the first version of the tool. The result was blocky, and the feedback was clear: the app needed to improve, not just my drawing.

| # | What was missing | Why it hurt | Decision |
|---|---|---|---|
| 13 | Curves | Limbs and clothes were rectangles and polygons | `path` op with SVG path data (M, L, H, V, C, S, Q, T, Z), flattened to smooth edges |
| 14 | Gradients | Flat colour made the sky and sun look like stickers | Linear and radial gradient fills for any `fill` or `outline` |
| 15 | Glows and soft shadows | Shadows were hard-edged discs | Layer `blur`, so a shape on its own layer can glow or shade |
| 16 | Numeric precision | Pure Pillow cannot do per-pixel gradients fast enough | Added numpy as a dependency (recorded in DESIGN.md and AGENTS.md) |

The redrawn captain (`examples/pirate-king-changes.json`) renders in about 0.14 seconds. It has curved hair, a shaded vest, a glowing sun, and a soft shadow. Remaining weak spots: the face is still simple, and there is no arc command, so round shapes need curves.

## Round 6: the face

The round-5 face was two dots and a line, and it looked bad. The problem was the app's vocabulary rather than only the drawing.

| # | What was missing | Why it hurt | Decision |
|---|---|---|---|
| 17 | Arc command | Eyelids, smiles, and cheeks had to be approximated with curves | Added `A` to `path`, following the SVG endpoint-to-centre conversion |
| 18 | Decimal outline widths | `2.5` was rejected, so fine lines had to be rounded up to 3 | `width` accepts decimals from 0.5 |
| 19 | Feature layering | The hat brim hid the eyebrows | Drew the features above the hat, and raised the hat 10 px |

The new face has almond eyes with irises, highlights, and eyelids; tapered brows; a nose with nostrils; an open grin with teeth; blush on a blurred layer; and ears. It is checked at 4x zoom. The redrawn captain is `examples/pirate-king-changes.json`. The tests now number 136.

## Round 7: reference check

I checked the reference online (Wikipedia's article on Luffy, plus a fan article on early sketches). The article describes the classic outfit as a red vest and denim shorts, with a yellow sash in later arcs. The captain now has a yellow sash with a hanging end, and denim shorts with a blue gradient. The scar under the left eye and the straw hat with a red band were already there. Still missing from the reference: the chest scar and the messy hair shape.

## Round 8: why it still looks ugly

Reasons, from looking at the renders:
- Cartoons are drawn with a dark outline around every shape. My figure had almost none, so it looked like clip art.
- Shapes were typed as coordinates with no construction or sketch, so proportions were guessed.
- Gradients on a figure read as stock illustration rather than cartoon.

What other open-source projects do:
- Synfig (GPL) builds cartoons from rigged parts: each limb is a layer attached to bones, so the drawing is made once and moved. Its [skeleton tutorial](https://synfig.readthedocs.io/en/latest/tutorials/bones_morphing.html) describes the process.
- Potrace (GPL) and ImageTracer (Unlicense, in jspaint's lib folder) turn a bitmap sketch into smooth curves, so an artist draws a sketch and the tool makes the outlines. Potrace's licence is described in its [README](https://potrace.sourceforge.net/README).

What I added: a layer-level `outline`, which draws a dark line around every shape on the layer. The captain now uses outlines on the hair, body, face and hat. It reads as a character now, but it is still not a polished cartoon.

Next options, not yet built: a `trace` command that turns a user-supplied sketch into path ops (like Potrace), and rigging for moving parts.

## Round 9: drawing with SVG code

The anime figures drawn with ai-paint's own ops still looked crude. The tool's own vocabulary was the limit: no groups, no transforms, no clipping, no reuse. SVG has all of these, and it is a language an agent writes fluently.

| # | What was missing | Decision |
|---|---|---|
| 20 | Groups, transforms and mirroring | The `svg` op draws SVG code through the system's librsvg, inside a box on a layer |
| 21 | Clipping (an iris inside its eye) | `clipPath` in SVG |
| 22 | Drawing a symmetric part once | `<use>` with `scale(-1 1)` |
| 23 | Safety | An allow-list: no scripts, no event attributes, no outside links, no DOCTYPE |

The redrawn girl (`examples/anime-girl.svg`) renders in about 0.13 seconds and is the best character so far.

## Round 10: SVG as the core

Drawing with SVG worked better than ai-paint's own ops, so SVG becomes the core. Phase 1 adds what I needed most while drawing:

| # | What was missing | Decision |
|---|---|---|
| 24 | Redrawing common parts every time | A part library: eyes, brows, mouths, nose, blush, manga symbols, recoloured with `color` |
| 25 | Changing one detail meant rewriting the SVG | `svg_set`, `svg_remove` and `svg_replace` by element id |
| 26 | Finding what to change | `ai-paint elements DOC OP_ID` |

Test: a four-mood expression sheet took 69 lines of SVG, and it is the clearest drawing so far.

## Round 11: export to SVG

`ai-paint export` compiles a document into one SVG. Three earlier documents exported with no layer turned into a picture, and librsvg's render of each export matched ai-paint's own: mean difference 0.29 (captain), 1.57 (pirate king) and 0.96 (manga page) on a 0 to 255 scale. The visible difference is a slightly softer layer outline in the SVG.

Decision: keep ai-paint's own renderer as the main render path for now, because 181 pixel-level tests rest on it. Switch to rendering through the exported SVG only after the export has been used on more real pages.

## Round 12: a limb-drawing tool, and more library parts

Every arm and leg so far was a hand-tuned path or tapered stroke, redone by trial and render each time. Added `limb`: a tapered capsule through 2 or 3 joints (shoulder[-elbow]-hand), curved smoothly through the middle joint, taper computed exactly rather than eyeballed.

Test: redrew the straw-hat captain's raised arm with `limb` plus the new `lib-hand-open` part. First pass left the old round hand-blob op in place by mistake (an orphan shape, visible as a floating circle above the fingers) — removed it once spotted in a zoomed render. Result: the hand's fingers visibly grip the hat brim, and the arm tapers smoothly shoulder to wrist, both clear improvements over the earlier hand-drawn arm.

Also added two hairstyles (bob, ponytail), two hand poses (open, fist), and three manga effects (speed lines, impact burst, thought bubble) — checked each renders as intended with a small preview sheet before committing.

Mistake caught before committing: initially overwrote `examples/pirate-king-changes.json` (a changes file for a different, earlier composition) with the new captain document. Reverted via git before it was committed, then saved the new picture under its own name (`captain-limb-changes.json`).
