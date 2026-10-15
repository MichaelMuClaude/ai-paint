"""Parameter types for paint operations: describe them, and check and normalise values."""

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor

from ai_paint import svgpath
from ai_paint.errors import PaintError
from ai_paint.gradient import Gradient
from ai_paint.screentone import ScreenTone

COORD_LIMIT = 100_000
MAX_SIZE = 10_000
MAX_TEXT = 500
MAX_IMAGE_PIXELS = 25_000_000
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True)
class Param:
    name: str
    kind: str  # int, float, bool, colour, paint, point, points, box, choice, text, path, font, image
    summary: str
    required: bool = True
    default: object = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple = ()
    min_items: int = 0
    max_items: int = 0
    inside_canvas: bool = False


def parse_colour(value) -> tuple[int, int, int, int]:
    """Read a colour name, #rrggbb, or #rrggbbaa and return (r, g, b, a)."""
    if not isinstance(value, str):
        raise PaintError("colour must be a colour name or #rrggbb / #rrggbbaa text")
    try:
        rgba = ImageColor.getrgb(value)
    except ValueError as exc:
        raise PaintError(f"colour is not recognised: {value!r}") from exc
    if len(rgba) == 3:
        rgba = (*rgba, 255)
    return rgba


def _gradient_stops(name: str, value) -> list:
    if not isinstance(value, list) or len(value) < 2:
        raise PaintError(f"{name} stops must be a list of at least two [position, colour] pairs")
    stops = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2 or not _is_number(item[0]) or not 0 <= item[0] <= 1:
            raise PaintError(f"{name} stops must be [position, colour] with a position from 0 to 1")
        stops.append((float(item[0]), parse_colour(item[1])))
    positions = [position for position, _ in stops]
    if positions != sorted(positions):
        raise PaintError(f"{name} stop positions must go up from 0 to 1")
    return stops


def parse_paint(name: str, value):
    """A colour name or #hex, or a gradient: {"type": "linear", "from": [x, y], "to": [x, y], "stops": [...]}
    or {"type": "radial", "centre": [x, y], "radius": r, "stops": [...]}."""
    if isinstance(value, str):
        return parse_colour(value)
    if not isinstance(value, dict):
        raise PaintError(f"{name} must be a colour, a gradient object, or a screentone object")
    if value.get("type") == "screen":
        return _screentone(name, value)
    kind = value.get("type")
    if kind == "linear":
        allowed = {"type", "from", "to", "stops"}
    elif kind == "radial":
        allowed = {"type", "centre", "radius", "stops"}
    else:
        raise PaintError(f"{name} gradient type must be 'linear' or 'radial'")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise PaintError(f"{name} gradient has unknown field(s): {', '.join(unknown)}")
    stops = _gradient_stops(name, value.get("stops"))
    if kind == "linear":
        start = _point(Param(name, "point", ""), value.get("from"), (10**9, 10**9))
        end = _point(Param(name, "point", ""), value.get("to"), (10**9, 10**9))
        if start == end:
            raise PaintError(f"{name} linear gradient needs different 'from' and 'to' points")
        return Gradient("linear", stops, start=start, end=end)
    centre = _point(Param(name, "point", ""), value.get("centre"), (10**9, 10**9))
    radius = value.get("radius")
    if not _is_number(radius) or radius <= 0:
        raise PaintError(f"{name} radial gradient needs a positive radius")
    return Gradient("radial", stops, centre=centre, radius=float(radius))


def _screentone(name: str, value: dict) -> ScreenTone:
    """{"type": "screen", "density": 0.3, "cell": 8, "angle": 45, "colour": "#000000"}"""
    unknown = sorted(set(value) - {"type", "density", "cell", "angle", "colour"})
    if unknown:
        raise PaintError(f"{name} screentone has unknown field(s): {', '.join(unknown)}")
    density = value.get("density")
    if not _is_number(density) or not 0 < density <= 1:
        raise PaintError(f"{name} screentone density must be a number above 0 and up to 1")
    cell = value.get("cell", 8)
    if not _is_number(cell) or not 2 <= cell <= 200:
        raise PaintError(f"{name} screentone cell must be a number from 2 to 200 pixels")
    angle = value.get("angle", 45)
    if not _is_number(angle):
        raise PaintError(f"{name} screentone angle must be a number of degrees")
    colour = parse_colour(value.get("colour", "#000000"))
    return ScreenTone(float(density), float(cell), float(angle), colour)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_range(param: Param, value: float) -> None:
    if param.minimum is not None and value < param.minimum:
        raise PaintError(f"{param.name} must be at least {param.minimum:g}")
    if param.maximum is not None and value > param.maximum:
        raise PaintError(f"{param.name} must be at most {param.maximum:g}")


def _coord(name: str, value) -> float:
    if not _is_number(value):
        raise PaintError(f"{name} coordinates must be numbers")
    if abs(value) > COORD_LIMIT:
        raise PaintError(f"{name} coordinates must be between -{COORD_LIMIT} and {COORD_LIMIT}")
    return value


def _point(param: Param, value, size: tuple[int, int]) -> list:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise PaintError(f"{param.name} must be a point [x, y]")
    x, y = _coord(param.name, value[0]), _coord(param.name, value[1])
    if param.inside_canvas and not (0 <= x < size[0] and 0 <= y < size[1]):
        raise PaintError(f"{param.name} {[x, y]} is outside the {size[0]}x{size[1]} canvas")
    return [x, y]


def _resolve(value: str, base: Path) -> Path:
    """A relative path is read from the document's folder, so a document still works when moved with its files."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def _font(param: Param, value, base: Path) -> str:
    if not isinstance(value, str) or not value.lower().endswith(FONT_SUFFIXES):
        raise PaintError(f"{param.name} must be a .ttf, .otf or .ttc font file")
    path = _resolve(value, base)
    if not path.is_file():
        raise PaintError(f"{param.name} file does not exist: {path}")
    return str(path)


def _image(param: Param, value, base: Path) -> str:
    if not isinstance(value, str) or not value.lower().endswith(IMAGE_SUFFIXES):
        raise PaintError(f"{param.name} must be a picture file ending in {', '.join(IMAGE_SUFFIXES)}")
    path = _resolve(value, base)
    if not path.is_file():
        raise PaintError(f"{param.name} file does not exist: {path}")
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError as exc:
        raise PaintError(f"{param.name} is not a readable picture: {path}") from exc
    if width * height > MAX_IMAGE_PIXELS:
        raise PaintError(f"{param.name} is {width}x{height}; the limit is {MAX_IMAGE_PIXELS} pixels")
    return str(path)


def coerce(param: Param, value, size: tuple[int, int], base: Path | None = None):
    """Check one value against its parameter and return the normalised form.

    `base` is the folder that relative file paths are read from. It defaults to the current folder.
    """
    base = Path.cwd() if base is None else base
    kind = param.kind
    if kind == "int":
        if not _is_number(value) or float(value) != int(value):
            raise PaintError(f"{param.name} must be a whole number")
        value = int(value)
        _check_range(param, value)
        return value
    if kind == "float":
        if not _is_number(value):
            raise PaintError(f"{param.name} must be a number")
        _check_range(param, value)
        return float(value)
    if kind == "bool":
        if not isinstance(value, bool):
            raise PaintError(f"{param.name} must be true or false")
        return value
    if kind == "colour":
        try:
            return parse_colour(value)
        except PaintError as exc:
            raise PaintError(f"{param.name} {exc}") from exc
    if kind == "point":
        return _point(param, value, size)
    if kind == "points":
        if not isinstance(value, list):
            raise PaintError(f"{param.name} must be a list of points [[x, y], ...]")
        if not param.min_items <= len(value) <= param.max_items:
            raise PaintError(
                f"{param.name} needs {param.min_items} to {param.max_items} points, got {len(value)}"
            )
        return [_point(param, item, size) for item in value]
    if kind == "box":
        if not isinstance(value, list) or len(value) != 4:
            raise PaintError(f"{param.name} must be [x, y, width, height]")
        x, y = _coord(param.name, value[0]), _coord(param.name, value[1])
        width, height = value[2], value[3]
        for label, number in (("width", width), ("height", height)):
            if not _is_number(number) or number < 1 or number > MAX_SIZE:
                raise PaintError(f"{param.name} {label} must be a number from 1 to {MAX_SIZE}")
        return [x, y, width, height]
    if kind == "choice":
        if value not in param.choices:
            raise PaintError(f"{param.name} must be one of: {', '.join(param.choices)}")
        return value
    if kind == "text":
        if not isinstance(value, str) or not value.strip():
            raise PaintError(f"{param.name} must be text that is not empty")
        if len(value) > MAX_TEXT:
            raise PaintError(f"{param.name} must be at most {MAX_TEXT} characters")
        return value
    if kind == "paint":
        return parse_paint(param.name, value)
    if kind == "path":
        return svgpath.parse(value)
    if kind == "font":
        return _font(param, value, base)
    if kind == "image":
        return _image(param, value, base)
    raise AssertionError(f"unknown parameter kind {kind}")
