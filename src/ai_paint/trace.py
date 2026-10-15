"""Turn a picture's dark lines into smooth path ops, using ImageTracer (see vendor/README.md)."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from ai_paint.errors import PaintError

VENDOR = Path(__file__).parent / "vendor"
PATH_TAG = re.compile(r"<path\b([^>]*)>")
ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
NUMBER = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _line_image(picture: Path, threshold: int, thicken: int, out: Path) -> tuple[int, int]:
    """Write the dark, opaque pixels as black on white, as raw RGBA. Returns the picture's size.

    `thicken` grows the lines by that many pixels before tracing. One grown contour traces more cleanly
    than an outline drawn around thin lines.
    """
    with Image.open(picture) as opened:
        rgba = np.asarray(opened.convert("RGBA")).astype(np.int32)
    luminance = 0.299 * rgba[..., 0] + 0.587 * rgba[..., 1] + 0.114 * rgba[..., 2]
    lines = (rgba[..., 3] > 200) & (luminance < threshold)
    mask = Image.fromarray((lines * 255).astype(np.uint8), "L")
    for _ in range(thicken):
        mask = mask.filter(ImageFilter.MaxFilter(3))
    lines = np.asarray(mask) > 127
    canvas = np.full(rgba.shape, 255, dtype=np.uint8)
    canvas[lines] = (0, 0, 0, 255)
    canvas.tofile(out)
    return rgba.shape[1], rgba.shape[0]


def _transform(d: str, scale: float, dx: float, dy: float) -> str:
    """Scale and move absolute M and L coordinates. ImageTracer writes only those, with Z to close."""
    tokens = re.findall(r"[MLZ]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    out, pending = [], []
    for token in tokens:
        if token in ("M", "L", "Z"):
            out.append(token)
            continue
        pending.append(float(token))
        if len(pending) == 2:
            x, y = pending
            out.append(f"{x * scale + dx:.2f} {y * scale + dy:.2f}")
            pending = []
    return " ".join(out)


def trace_to_changes(picture: Path, threshold: int = 30, layer: str = "lines",
                     colour: str = "#000000", scale: float = 1.0,
                     offset: tuple = (0.0, 0.0), thicken: int = 0) -> tuple[dict, dict]:
    """Return (changes, info). `changes` adds a layer and path ops for the dark lines; `info` gives sizes."""
    node = shutil.which("node")
    if node is None:
        raise PaintError("ai-paint trace needs Node.js on the PATH; install Node, or draw the lines by hand")
    if not 0 <= threshold <= 255:
        raise PaintError("threshold must be a whole number from 0 to 255")
    if scale <= 0:
        raise PaintError("scale must be above 0")
    if not 0 <= thicken <= 5:
        raise PaintError("thicken must be a whole number from 0 to 5 pixels")
    with tempfile.TemporaryDirectory() as work:
        raw = Path(work) / "lines.raw"
        svg = Path(work) / "lines.svg"
        width, height = _line_image(picture, threshold, thicken, raw)
        result = subprocess.run(
            [node, str(VENDOR / "trace_svg.js"), str(raw), str(width), str(height), str(svg)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0 or not svg.exists():
            raise PaintError(f"tracing failed: {result.stderr.strip() or 'no output from ImageTracer'}")
        text = svg.read_text()
    ops = []
    for match in PATH_TAG.finditer(text):
        attributes = dict(ATTRIBUTE.findall(match.group(1)))
        if attributes.get("fill") != "rgb(0,0,0)" or "d" not in attributes:
            continue  # the white background shapes are skipped
        ops.append({
            "op": "path",
            "layer": layer,
            "d": _transform(attributes["d"], scale, offset[0], offset[1]),
            "fill": colour,
            "fill_rule": "evenodd",
        })
    info = {
        "source_width": width, "source_height": height,
        "canvas_width": round(width * scale + offset[0]), "canvas_height": round(height * scale + offset[1]),
        "paths": len(ops),
    }
    return {"layers": [{"id": layer}], "ops": ops}, info
