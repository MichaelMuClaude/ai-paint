"""Pixel work: anti-aliased brush dabs and shapes, flood fill, and compositing onto a layer.

Coordinates are continuous. A point (x, y) is a pixel corner, so pixel (i, j) covers i..i+1 and j..j+1,
and a box [x, y, w, h] covers exactly w by h pixels.

Shapes and strokes are drawn at AA times the picture's resolution, inside a region just large enough
to hold them, and then averaged back down. Edges therefore get partial coverage instead of hard steps.
"""

import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFont

from ai_paint.errors import PaintError

AA = 3  # samples per pixel along each axis, so each pixel is averaged from AA x AA samples
MAX_DABS = 200_000

# hardness: 1.0 means a hard edge; 0.0 means the alpha fades from the centre to the edge.
# spacing: distance between dabs as a fraction of the brush radius.
BRUSHES = {
    "round": {"hardness": 1.0, "spacing": 0.2, "summary": "hard edge, smoothed by anti-aliasing"},
    "soft": {"hardness": 0.0, "spacing": 0.1, "summary": "feathered edge, fades out towards the rim"},
}


@lru_cache(maxsize=256)
def brush_mask(radius: float, hardness: float) -> Image.Image:
    """A square L-mode dab with a circular alpha profile, in supersampled pixels. Cached and never modified."""
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
    """Points spaced `step` picture pixels apart along the path, always including the first and last points."""
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


def _stamp(big: Image.Image, dab: Image.Image, cx: float, cy: float) -> None:
    """Merge one dab into the supersampled mask with `lighter`, so overlapping dabs do not add up."""
    width, height = big.size
    half = dab.size[0] // 2
    x0 = round(cx) - half
    y0 = round(cy) - half
    left, top = max(0, x0), max(0, y0)
    right = min(width, x0 + dab.size[0])
    bottom = min(height, y0 + dab.size[1])
    if left >= right or top >= bottom:
        return
    source = dab.crop((left - x0, top - y0, right - x0, bottom - y0))
    region = big.crop((left, top, right, bottom))
    big.paste(ImageChops.lighter(region, source), (left, top))


def _region(points: list, pad: float, size: tuple[int, int]):
    """The pixel box (x0, y0, x1, y1) that holds the points plus `pad`, clipped to the picture. None if empty."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0 = max(0, math.floor(min(xs) - pad))
    y0 = max(0, math.floor(min(ys) - pad))
    x1 = min(size[0], math.ceil(max(xs) + pad))
    y1 = min(size[1], math.ceil(max(ys) + pad))
    if x0 >= x1 or y0 >= y1:
        return None
    return (x0, y0, x1, y1)


class _Sampler:
    """A supersampled L-mode mask for one region of the picture. Draw in picture coordinates, then `finish`."""

    def __init__(self, region):
        self.x0, self.y0, x1, y1 = region
        self.width, self.height = x1 - self.x0, y1 - self.y0
        self.big = Image.new("L", (self.width * AA, self.height * AA), 0)
        self.draw = ImageDraw.Draw(self.big)

    def point(self, p) -> tuple[float, float]:
        return ((p[0] - self.x0) * AA, (p[1] - self.y0) * AA)

    def points(self, pts) -> list:
        return [self.point(p) for p in pts]

    def finish(self) -> Image.Image:
        return self.big.resize((self.width, self.height), Image.BOX)


def paint(layer: Image.Image, mask: Image.Image, region: tuple, colour: tuple, opacity: float) -> None:
    """Blend `colour` onto `layer` through the mask, scaled by the colour's alpha and `opacity`."""
    alpha = colour[3] / 255 * opacity
    if alpha <= 0:
        return
    shade = mask.point(lambda v: round(v * alpha))
    box = shade.getbbox()
    if box is None:
        return
    x0, y0 = region[0], region[1]
    target = (x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3])
    overlay = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), colour[:3] + (0,))
    overlay.putalpha(shade.crop(box))
    existing = layer.crop(target)
    layer.paste(Image.alpha_composite(existing, overlay), target[:2])


def draw_stroke(layer: Image.Image, points: list, radius: float, hardness: float, spacing: float,
                colour: tuple, opacity: float) -> None:
    """Paint a path of round dabs. `radius` and `spacing` are in picture pixels."""
    region = _region(points, radius + 2, layer.size)
    if region is None:
        return
    step = max(1.0, spacing * radius)
    positions = _dab_positions(points, step)
    if len(positions) > MAX_DABS:
        raise PaintError(
            f"stroke needs {len(positions)} dabs, the limit is {MAX_DABS}; "
            "use fewer points or a larger size"
        )
    sampler = _Sampler(region)
    dab = brush_mask(radius * AA, hardness)
    for x, y in positions:
        _stamp(sampler.big, dab, *sampler.point((x, y)))
    paint(layer, sampler.finish(), region, colour, opacity)


def _box_shape(sampler: _Sampler, shape: str, corners: tuple, value: int) -> None:
    """Fill a rect or ellipse given by two opposite corners, with `value` (0 clears, 255 sets)."""
    a = sampler.point(corners[:2])
    b = sampler.point(corners[2:])
    box = [round(a[0]), round(a[1]), round(b[0]) - 1, round(b[1]) - 1]
    if shape == "rect":
        sampler.draw.rectangle(box, fill=value)
    else:
        sampler.draw.ellipse(box, fill=value)


def draw_shape(layer: Image.Image, shape: str, coords: list, colour: tuple, opacity: float,
               filled: bool = True, width: float = 1) -> None:
    """Paint a rect, ellipse, polygon, or polyline.

    rect and ellipse take a box [x, y, width, height]. polygon and polyline take a list of points.
    An outline is centred on the edge, so it grows half its width on each side.
    """
    if shape in ("rect", "ellipse"):
        x, y, w, h = coords
        half = 0 if filled else width / 2
        region = _region([[x - half, y - half], [x + w + half, y + h + half]], 2, layer.size)
        if region is None:
            return
        sampler = _Sampler(region)
        _box_shape(sampler, shape, (x - half, y - half, x + w + half, y + h + half), 255)
        if not filled and w > width and h > width:
            _box_shape(sampler, shape, (x + half, y + half, x + w - half, y + h - half), 0)
    elif shape in ("polygon", "polyline"):
        pad = 2 if filled else width / 2 + 2
        region = _region(coords, pad, layer.size)
        if region is None:
            return
        sampler = _Sampler(region)
        pts = sampler.points(coords)
        if shape == "polygon" and filled:
            sampler.draw.polygon(pts, fill=255)
        elif shape == "polygon":
            sampler.draw.line(pts + pts[:1], fill=255, width=round(width * AA), joint="curve")
        else:
            sampler.draw.line(pts, fill=255, width=round(width * AA), joint="curve")
    else:
        raise AssertionError(f"unknown shape {shape}")
    paint(layer, sampler.finish(), region, colour, opacity)


def _font(size: int, font_path: str | None):
    try:
        if font_path is None:
            return ImageFont.load_default(size=size)
        return ImageFont.truetype(font_path, size)
    except OSError as exc:
        raise PaintError(f"could not load font {font_path}: {exc}") from exc


def draw_text(layer: Image.Image, text: str, xy: list, size: int, font_path: str | None,
              colour: tuple, opacity: float) -> None:
    """Write text with its top-left corner at `xy`. Lines are separated by newlines."""
    font = _font(size, font_path)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = measure.multiline_textbbox((xy[0], xy[1]), text, font=font)
    region = _region([[left, top], [right, bottom]], 1, layer.size)
    if region is None:
        return
    mask = Image.new("L", (region[2] - region[0], region[3] - region[1]), 0)
    ImageDraw.Draw(mask).multiline_text((xy[0] - region[0], xy[1] - region[1]), text, fill=255, font=font)
    paint(layer, mask, region, colour, opacity)


def flood_fill(layer: Image.Image, seed: list, colour: tuple, tolerance: int) -> None:
    """Replace the connected area of similar pixels around `seed` with `colour`. Works on one layer."""
    x, y = round(seed[0]), round(seed[1])
    ImageDraw.floodfill(layer, (x, y), colour, thresh=tolerance)
