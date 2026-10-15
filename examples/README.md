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
