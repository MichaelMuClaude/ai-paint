"""Pixel work: brush dabs, shape masks, flood fill, and compositing a colour onto a layer."""

import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

from ai_paint.errors import PaintError

MAX_DABS = 200_000

# hardness: 1.0 means a hard edge; 0.0 means the alpha fades from the centre to the edge.
# spacing: distance between dabs as a fraction of the brush radius.
BRUSHES = {
    "round": {"hardness": 1.0, "spacing": 0.2, "summary": "hard edge"},
    "soft": {"hardness": 0.0, "spacing": 0.1, "summary": "feathered edge, fades out towards the rim"},
}


@lru_cache(maxsize=256)
def brush_mask(radius: float, hardness: float) -> Image.Image:
    """A square L-mode dab with a circular alpha profile. Cached and never modified."""
    radius = max(radius, 0.5)
    half = math.ceil(radius)
    mask = Image.new("L", (2 * half + 1, 2 * half + 1), 0)
    draw = ImageDraw.Draw(mask)
    steps = max(2, math.ceil(radius * 2))
    # Draw from the outside in, so each smaller ring overwrites the one around it.
    # Each ring takes the value at its inner edge, so the centre reaches full strength.
    for step in range(steps, 0, -1):
        ring = radius * step / steps
        inner = (step - 1) / steps  # inner edge as a fraction of the radius, 0.0 at the centre
        if inner <= hardness or hardness >= 1.0:
            value = 255
        else:
            value = round(255 * (1 - inner) / (1 - hardness))
        draw.ellipse([half - ring, half - ring, half + ring, half + ring], fill=value)
    return mask


def _dab_positions(points: list, step: float) -> list:
    """Points spaced `step` pixels apart along the path, always including the first point."""
    if len(points) == 1:
        return [tuple(points[0])]
    out = [tuple(points[0])]
    travelled = 0.0  # distance covered since the last dab
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        if length == 0:
            continue
        along = step - travelled  # distance from this segment's start to its next dab
        while along <= length:
            t = along / length
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            along += step
        travelled = length - (along - step)
    if out[-1] != tuple(points[-1]):
        out.append(tuple(points[-1]))
    return out


def _stamp(mask: Image.Image, dab: Image.Image, cx: float, cy: float) -> None:
    """Merge one dab into the stroke mask with `lighter`, so overlapping dabs do not add up."""
    width, height = mask.size
    half = dab.size[0] // 2
    x0 = round(cx) - half
    y0 = round(cy) - half
    left, top = max(0, x0), max(0, y0)
    right = min(width, x0 + dab.size[0])
    bottom = min(height, y0 + dab.size[1])
    if left >= right or top >= bottom:
        return
    source = dab.crop((left - x0, top - y0, right - x0, bottom - y0))
    region = mask.crop((left, top, right, bottom))
    mask.paste(ImageChops.lighter(region, source), (left, top))


def stroke_mask(size: tuple, points: list, radius: float, hardness: float, spacing: float) -> Image.Image:
    dab = brush_mask(radius, hardness)
    step = max(1.0, spacing * radius)
    positions = _dab_positions(points, step)
    if len(positions) > MAX_DABS:
        raise PaintError(
            f"stroke needs {len(positions)} dabs, the limit is {MAX_DABS}; "
            "use fewer points or a larger size"
        )
    mask = Image.new("L", size, 0)
    for x, y in positions:
        _stamp(mask, dab, x, y)
    return mask


def shape_mask(size: tuple, shape: str, coords: list, filled: bool, width: int = 1) -> Image.Image:
    """An L-mode mask for a rect, ellipse, polygon, or polyline. `coords` is a box or a point list."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if shape in ("rect", "ellipse"):
        x, y, w, h = coords
        box = [round(x), round(y), round(x + w) - 1, round(y + h) - 1]
        draw_shape = draw.rectangle if shape == "rect" else draw.ellipse
        if filled:
            draw_shape(box, fill=255)
        else:
            draw_shape(box, outline=255, width=width)
    elif shape == "polygon":
        if filled:
            draw.polygon([tuple(p) for p in coords], fill=255)
        else:
            closed = [tuple(p) for p in coords] + [tuple(coords[0])]
            draw.line(closed, fill=255, width=width, joint="curve")
    elif shape == "polyline":
        draw.line([tuple(p) for p in coords], fill=255, width=width, joint="curve")
    else:
        raise AssertionError(f"unknown shape {shape}")
    return mask


def paint(layer: Image.Image, mask: Image.Image, colour: tuple, opacity: float) -> None:
    """Blend `colour` onto `layer` wherever the mask is set, scaled by the colour's alpha and `opacity`."""
    alpha = colour[3] / 255 * opacity
    if alpha <= 0:
        return
    shade = mask.point(lambda v: round(v * alpha))
    box = shade.getbbox()
    if box is None:
        return
    overlay = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), colour[:3] + (0,))
    overlay.putalpha(shade.crop(box))
    region = layer.crop(box)
    layer.paste(Image.alpha_composite(region, overlay), box[:2])


def flood_fill(layer: Image.Image, seed: list, colour: tuple, tolerance: int) -> None:
    """Replace the connected area of similar pixels around `seed` with `colour`. Works on one layer."""
    x, y = round(seed[0]), round(seed[1])
    ImageDraw.floodfill(layer, (x, y), colour, thresh=tolerance)
