"""Pixel work: anti-aliased brush dabs and shapes, flood fill, and compositing onto a layer.

Coordinates are continuous. A point (x, y) is a pixel corner, so pixel (i, j) covers i..i+1 and j..j+1,
and a box [x, y, w, h] covers exactly w by h pixels.

Shapes and strokes are drawn at AA times the picture's resolution, inside a region just large enough
to hold them, and then averaged back down. Edges therefore get partial coverage instead of hard steps.
"""

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from ai_paint import svgpath
from ai_paint.errors import PaintError

AA = 3  # samples per pixel along each axis, so each pixel is averaged from AA x AA samples
MAX_DABS = 200_000
MIN_TAPER = 0.12  # the thinnest a tapered stroke gets, as a fraction of its full width

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


def _dab_positions(points: list, step: float) -> tuple[list, float]:
    """Dab centres spaced `step` pixels apart along the path, as (x, y, distance_along_path) triples.

    The first and last points are always included. Also returns the total length of the path.
    """
    if len(points) == 1:
        return [(points[0][0], points[0][1], 0.0)], 0.0
    out = [(points[0][0], points[0][1], 0.0)]
    travelled = 0.0  # distance covered since the last dab
    along_path = 0.0  # distance from the start of the whole path to the start of this segment
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        if length == 0:
            continue
        along = step - travelled  # distance from this segment's start to its next dab
        while along <= length:
            t_seg = along / length
            out.append((x0 + (x1 - x0) * t_seg, y0 + (y1 - y0) * t_seg, along_path + along))
            along += step
        travelled = length - (along - step)
        along_path += length
    if (out[-1][0], out[-1][1]) != tuple(points[-1]):
        out.append((points[-1][0], points[-1][1], along_path))
    return out, along_path


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


def paint(layer: Image.Image, mask: Image.Image, region: tuple, colour, opacity: float) -> None:
    """Blend a colour or gradient onto `layer` through the mask, scaled by its alpha and `opacity`."""
    if hasattr(colour, "render"):  # a gradient or a screentone
        colours = Image.fromarray(colour.render(region), "RGBA")
    else:
        colours = Image.new("RGBA", mask.size, colour[:3] + (colour[3],))
    shade = mask.point(lambda v: round(v * opacity))
    alpha = ImageChops.multiply(shade, colours.getchannel("A"))
    box = alpha.getbbox()
    if box is None:
        return
    x0, y0 = region[0], region[1]
    target = (x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3])
    overlay = colours.crop(box)
    overlay.putalpha(alpha.crop(box))
    existing = layer.crop(target)
    layer.paste(Image.alpha_composite(existing, overlay), target[:2])


def add_outline(content: Image.Image, colour: tuple, width: float) -> Image.Image:
    """Return the layer with an outline drawn around its shapes, under the shapes.

    The outline is the layer's alpha grown by `width` pixels, minus the shapes themselves. It is made by
    growing the alpha one pixel at a time, so it follows the shapes closely.
    """
    alpha = content.getchannel("A")
    grown = alpha
    for _ in range(max(1, round(width))):
        grown = grown.filter(ImageFilter.MaxFilter(3))
    ring = ImageChops.subtract(grown, alpha).filter(ImageFilter.GaussianBlur(0.6))
    outline = Image.new("RGBA", content.size, colour[:3] + (0,))
    outline.putalpha(ImageChops.multiply(ring, Image.new("L", content.size, colour[3])))
    return Image.alpha_composite(outline, content)


def blur_layer(image: Image.Image, radius: float) -> Image.Image:
    """Blur a layer's pixels, keeping their colour. Colour is blurred before transparency is applied,
    so edges do not pick up a dark fringe."""
    values = np.asarray(image, dtype=np.float64) / 255
    alpha = values[..., 3:4]
    premultiplied = np.concatenate([values[..., :3] * alpha, alpha], axis=2)
    blurred_image = Image.fromarray(np.round(premultiplied * 255).astype(np.uint8), "RGBA")
    blurred = np.asarray(blurred_image.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float64) / 255
    new_alpha = blurred[..., 3:4]
    colour = np.where(new_alpha > 0, blurred[..., :3] / np.maximum(new_alpha, 1e-9), 0.0)
    out = np.concatenate([np.clip(colour, 0, 1), new_alpha], axis=2)
    return Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA")


def draw_stroke(layer: Image.Image, points: list, radius: float, hardness: float, spacing: float,
                colour: tuple, opacity: float, taper: float = 0.0, end_radius: float | None = None) -> None:
    """Paint a path of round dabs. `radius` and `spacing` are in picture pixels.

    `taper` is the fraction of the path's length at each end over which the line narrows to a point.
    `end_radius`, if given, makes the radius change evenly from `radius` at the start to it at the end.
    """
    region = _region(points, radius + 2, layer.size)
    if region is None:
        return
    step = max(1.0, spacing * radius)
    positions, total = _dab_positions(points, step)
    if len(positions) > MAX_DABS:
        raise PaintError(
            f"stroke needs {len(positions)} dabs, the limit is {MAX_DABS}; "
            "use fewer points or a larger size"
        )
    sampler = _Sampler(region)
    for x, y, along in positions:
        dab_radius = radius
        if end_radius is not None and total > 0:
            dab_radius = radius + (end_radius - radius) * along / total
        if taper > 0 and total > 0:
            distance_to_end = min(along, total - along)
            dab_radius = radius * max(MIN_TAPER, min(1.0, distance_to_end / (taper * total)))
        dab = brush_mask(round(dab_radius * AA, 2), hardness)
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


def shape_coverage(size: tuple[int, int], shape: str, coords: list, filled: bool, width: float = 1):
    """The anti-aliased coverage of a rect, ellipse, polygon, or polyline, as (region, mask).

    rect and ellipse take a box [x, y, width, height]. polygon and polyline take a list of points.
    An outline is centred on the edge, so it grows half its width on each side.
    Returns None when the shape is entirely off the picture.
    """
    if shape in ("rect", "ellipse"):
        x, y, w, h = coords
        half = 0 if filled else width / 2
        region = _region([[x - half, y - half], [x + w + half, y + h + half]], 2, size)
        if region is None:
            return None
        sampler = _Sampler(region)
        _box_shape(sampler, shape, (x - half, y - half, x + w + half, y + h + half), 255)
        if not filled and w > width and h > width:
            _box_shape(sampler, shape, (x + half, y + half, x + w - half, y + h - half), 0)
        return region, sampler.finish()
    if shape in ("polygon", "polyline"):
        pad = 2 if filled else width / 2 + 2
        region = _region(coords, pad, size)
        if region is None:
            return None
        sampler = _Sampler(region)
        pts = sampler.points(coords)
        if shape == "polygon" and filled:
            sampler.draw.polygon(pts, fill=255)
        elif shape == "polygon":
            sampler.draw.line(pts + pts[:1], fill=255, width=round(width * AA), joint="curve")
        else:
            sampler.draw.line(pts, fill=255, width=round(width * AA), joint="curve")
        return region, sampler.finish()
    raise AssertionError(f"unknown shape {shape}")


def draw_shape(layer: Image.Image, shape: str, coords: list, colour: tuple, opacity: float,
               filled: bool = True, width: float = 1) -> None:
    coverage = shape_coverage(layer.size, shape, coords, filled, width)
    if coverage is not None:
        region, mask = coverage
        paint(layer, mask, region, colour, opacity)


def path_coverage(size: tuple[int, int], subpaths: list, filled: bool, width: float = 1,
                  evenodd: bool = False):
    """Coverage of several flattened subpaths, as (region, mask). None if entirely off the picture.

    `subpaths` is a list of (points, closed). A filled path is the union of its subpaths, or, with
    `evenodd`, the areas covered by an odd number of subpaths, so holes stay empty.
    """
    every_point = [point for points, _ in subpaths for point in points]
    pad = 2 if filled else width / 2 + 2
    region = _region(every_point, pad, size)
    if region is None:
        return None
    sampler = _Sampler(region)
    if filled and evenodd:
        total = Image.new("L", sampler.big.size, 0)
        for points, _ in subpaths:
            piece = Image.new("L", sampler.big.size, 0)
            ImageDraw.Draw(piece).polygon(sampler.points(points), fill=255)
            total = ImageChops.difference(total, piece)
        sampler.big.paste(total)
        return region, sampler.finish()
    for points, closed in subpaths:
        pts = sampler.points(points)
        if filled:
            sampler.draw.polygon(pts, fill=255)
        else:
            if closed:
                pts = pts + pts[:1]
            sampler.draw.line(pts, fill=255, width=round(width * AA), joint="curve")
    return region, sampler.finish()


def draw_path(layer: Image.Image, subpaths: list, colour, opacity: float, filled: bool = True, width: float = 1,
              evenodd: bool = False) -> None:
    coverage = path_coverage(layer.size, subpaths, filled, width, evenodd)
    if coverage is not None:
        region, mask = coverage
        paint(layer, mask, region, colour, opacity)


def erase_shape(layer: Image.Image, shape: str, coords: list, opacity: float) -> None:
    """Make the filled shape transparent on this layer. `opacity` 1 removes it completely."""
    coverage = shape_coverage(layer.size, shape, coords, filled=True)
    if coverage is None:
        return
    region, mask = coverage
    keep = mask.point(lambda v: 255 - round(v * opacity))
    piece = layer.crop(region)
    piece.putalpha(ImageChops.multiply(piece.getchannel("A"), keep))
    layer.paste(piece, region[:2])


def place_image(layer: Image.Image, image: Image.Image, xy: list, opacity: float) -> None:
    """Composite a picture onto the layer with its top-left corner at `xy`, using its own transparency."""
    x, y = round(xy[0]), round(xy[1])
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    if opacity < 1:
        image = image.copy()
        image.putalpha(image.getchannel("A").point(lambda v: round(v * opacity)))
    region = _region([[x, y], [x + image.width, y + image.height]], 0, layer.size)
    if region is None:
        return
    piece = image.crop((region[0] - x, region[1] - y, region[2] - x, region[3] - y))
    existing = layer.crop(region)
    layer.paste(Image.alpha_composite(existing, piece), region[:2])


def limb_outline(joints: list, start_radius: float, end_radius: float) -> list:
    """The outline of a tapered capsule through 2 or 3 joints (shoulder[-elbow]-hand), as a closed polygon.

    The centreline is a Catmull-Rom spline through the joints (straight if there are only 2). The radius
    changes evenly along its length from `start_radius` to `end_radius`. Returns points for a single
    closed subpath, suitable for `shape_coverage`/`path_coverage` with `filled=True`.
    """
    centre = svgpath.spline(joints) if len(joints) > 2 else list(joints)
    lengths = [0.0]
    for (x0, y0), (x1, y1) in zip(centre, centre[1:]):
        lengths.append(lengths[-1] + math.hypot(x1 - x0, y1 - y0))
    total = lengths[-1] or 1.0
    left, right = [], []
    for i, (x, y) in enumerate(centre):
        radius = start_radius + (end_radius - start_radius) * lengths[i] / total
        if i == 0:
            dx, dy = centre[1][0] - x, centre[1][1] - y
        elif i == len(centre) - 1:
            dx, dy = x - centre[i - 1][0], y - centre[i - 1][1]
        else:
            dx, dy = centre[i + 1][0] - centre[i - 1][0], centre[i + 1][1] - centre[i - 1][1]
        norm = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / norm, dx / norm
        left.append((x + nx * radius, y + ny * radius))
        right.append((x - nx * radius, y - ny * radius))
    return left + list(reversed(right))


def _font(size: int, font_path: str | None):
    try:
        if font_path is None:
            return ImageFont.load_default(size=size)
        return ImageFont.truetype(font_path, size)
    except OSError as exc:
        raise PaintError(f"could not load font {font_path}: {exc}") from exc


def text_size(text: str, size: int, font_path: str | None) -> tuple[int, int]:
    """The width and height in pixels of the text's ink box, for one font size."""
    font = _font(size, font_path)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = measure.multiline_textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def text_layout(text: str, xy: list, size: int, font_path: str | None,
                align: str = "left", valign: str = "top"):
    """Where the text goes: returns (font, origin_x, origin_y, ink_box).

    The origin is where Pillow's multiline_text starts the first line (its left edge and ascender), chosen so
    that the text's ink box sits on `xy` as `align` and `valign` say. Both drawing and SVG export use it.
    """
    font = _font(size, font_path)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = measure.multiline_textbbox((0, 0), text, font=font, align=align)
    width, height = right - left, bottom - top
    anchor_x = {"left": 0, "center": width / 2, "right": width}[align]
    anchor_y = {"top": 0, "middle": height / 2, "bottom": height}[valign]
    origin_x = xy[0] - anchor_x - left
    origin_y = xy[1] - anchor_y - top
    return font, origin_x, origin_y, (origin_x + left, origin_y + top, origin_x + right, origin_y + bottom)


def draw_text(layer: Image.Image, text: str, xy: list, size: int, font_path: str | None,
              colour: tuple, opacity: float, align: str = "left", valign: str = "top") -> None:
    """Write text so that its ink box sits on `xy`.

    align: left, center or right, which side of the box `xy` is on.
    valign: top, middle or bottom, which edge of the box `xy` is on.
    Lines are separated by newlines and are aligned to each other by `align`.
    """
    font, origin_x, origin_y, box = text_layout(text, xy, size, font_path, align, valign)
    region = _region([box[:2], box[2:]], 1, layer.size)
    if region is None:
        return
    mask = Image.new("L", (region[2] - region[0], region[3] - region[1]), 0)
    ImageDraw.Draw(mask).multiline_text(
        (origin_x - region[0], origin_y - region[1]), text, fill=255, font=font, align=align
    )
    paint(layer, mask, region, colour, opacity)


def flood_fill(layer: Image.Image, seed: list, colour: tuple, tolerance: int) -> None:
    """Replace the connected area of similar pixels around `seed` with `colour`. Works on one layer."""
    x, y = round(seed[0]), round(seed[1])
    ImageDraw.floodfill(layer, (x, y), colour, thresh=tolerance)
