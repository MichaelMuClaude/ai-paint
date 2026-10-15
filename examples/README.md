# Examples

Each file is a changes file for `ai-paint apply`. Start from a blank canvas and apply one of them:

```bash
ai-paint new flowchart.json --width 600 --height 220 --background "#fafafa"
ai-paint apply flowchart.json --changes examples/flowchart-changes.json -o flowchart-v1.json
ai-paint render flowchart-v1.json -o flowchart.png --grid 20
```

- `flowchart-changes.json`: three boxes, arrows, and centred labels. Each op has an id, so you can change one with `update`.
- `poster-changes.json`: a pasted logo, a hole cut with `erase`, and two lines of text. It reads `logo.png`, so copy `examples/logo.png` next to your document first (relative paths are read from the document's folder).
- `badge-changes.json`: a shadow from layer opacity, rings, and a custom font. Its font path is absolute (`/usr/share/fonts/...`), so change it if your system keeps DejaVu fonts elsewhere.
- `anime-girl.svg`: an anime girl drawn as SVG code: the eye defined once and mirrored with `<use>`, the iris clipped to the eye white, blush with a blur filter, layered bangs and a sailor collar. Draw it with `{"op": "svg", "layer": "l1", "file": "anime-girl.svg"}` on a 600 × 700 canvas.
- `madameberry-body1-lines-changes.json`: the dark lines of a CC0 figure model sheet, traced with `ai-paint trace`. The source is `madameberry-body1-outline.png`, from Madame Berry's Visual Novel Set 1 on OpenGameArt (licence CC0). Apply it to a canvas of 1078 × 2559 pixels. Some dark shadow areas also come through as solid black, which needs a lower `--threshold` or hand cleaning.
- `madameberry-page-changes.json`: a complete B5 page (`--preset manga-b5`): three frames, screentones, two balloons, and the traced CC0 figure in the second panel, with `--thicken 2` for bolder lines. It is self-contained apart from the CJK font path.
- `manga-page-changes.json`: a B5 manga page with three framed panels, a 2 mm gutter, screentone shading, two speech balloons with Chinese text, and a caption. Make the page with `ai-paint new page.json --preset manga-b5`, copy `examples/captain.png` next to it, and apply. The font path is absolute, so change it if your Noto CJK files are elsewhere.
- `pirate-king-changes.json`: an original straw-hat captain with curved paths, arcs, gradient shading, a glowing sun, a soft shadow, and a detailed face. Make the canvas first with `--width 400 --height 500 --background none`.
