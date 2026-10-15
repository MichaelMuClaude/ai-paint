"""Every drawing operation: its parameters, its checks, and how it changes a layer.

The `ops` command is generated from this list, so it always matches the code.
"""

from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image

from ai_paint import raster
from ai_paint.errors import PaintError
from ai_paint.params import ID_PATTERN, MAX_SIZE, Param, coerce

MAX_POINTS = 5_000
MAX_WIDTH = 500
MAX_SIZE_PX = 1_000
MAX_TOLERANCE = 255


@dataclass(frozen=True)
class Operation:
    name: str
    summary: str
    params: tuple
    draw: Callable  # draw(layer, values, canvas_size) changes the layer in place
    check: Callable | None = None  # check(values) raises PaintError for combinations that are not allowed


OPERATIONS: dict[str, Operation] = {}


def _register(name, summary, params, draw, check=None):
    OPERATIONS[name] = Operation(name, summary, tuple(params), draw, check)


OPACITY = Param("opacity", "float", "How strongly the colour is applied, 0 to 1",
                required=False, default=1.0, minimum=0, maximum=1)
WIDTH = Param("width", "int", "Outline width in pixels", required=False, default=1,
              minimum=1, maximum=MAX_WIDTH)
FILL = Param("fill", "paint", "Fill: a colour such as #ff0000 or #ff000080, or a gradient object", required=False)
OUTLINE = Param("outline", "paint", "Outline: a colour or a gradient object", required=False)


def _need_fill_or_outline(values):
    if values["fill"] is None and values["outline"] is None:
        raise PaintError("give a fill colour, an outline colour, or both")


def _draw_stroke(layer, v, size):
    style = raster.BRUSHES[v["brush"]]
    raster.draw_stroke(layer, v["points"], v["size"] / 2, style["hardness"], style["spacing"],
                       v["colour"], v["opacity"])


_register(
    "stroke",
    "Paint a path with a round or soft brush. One point makes a single dab.",
    [
        Param("points", "points", "Path as [[x, y], ...] in pixels", min_items=1, max_items=MAX_POINTS),
        Param("size", "float", "Brush diameter in pixels", minimum=1, maximum=MAX_SIZE_PX),
        Param("colour", "colour", "Brush colour"),
        OPACITY,
        Param("brush", "choice", "round: hard edge. soft: feathered edge", required=False,
              default="round", choices=tuple(raster.BRUSHES)),
    ],
    _draw_stroke,
)


def _draw_line(layer, v, size):
    raster.draw_shape(layer, "polyline", v["points"], v["colour"], v["opacity"], filled=False, width=v["width"])


_register(
    "line",
    "Draw a straight line, or a polyline through several points, with hard edges.",
    [
        Param("points", "points", "Points [[x, y], ...]", min_items=2, max_items=MAX_POINTS),
        Param("colour", "colour", "Line colour"),
        WIDTH,
        OPACITY,
    ],
    _draw_line,
)


def _draw_box_shape(shape):
    def draw(layer, v, size):
        if v["fill"] is not None:
            raster.draw_shape(layer, shape, v["box"], v["fill"], v["opacity"], filled=True)
        if v["outline"] is not None:
            raster.draw_shape(layer, shape, v["box"], v["outline"], v["opacity"], filled=False, width=v["width"])
    return draw


_register(
    "rect",
    "Draw a rectangle given as [x, y, width, height], filled, outlined, or both.",
    [Param("box", "box", "[x, y, width, height] in pixels"), FILL, OUTLINE, WIDTH, OPACITY],
    _draw_box_shape("rect"),
    _need_fill_or_outline,
)

_register(
    "ellipse",
    "Draw an ellipse inside a box given as [x, y, width, height], filled, outlined, or both.",
    [Param("box", "box", "[x, y, width, height] in pixels"), FILL, OUTLINE, WIDTH, OPACITY],
    _draw_box_shape("ellipse"),
    _need_fill_or_outline,
)


def _draw_polygon(layer, v, size):
    if v["fill"] is not None:
        raster.draw_shape(layer, "polygon", v["points"], v["fill"], v["opacity"], filled=True)
    if v["outline"] is not None:
        raster.draw_shape(layer, "polygon", v["points"], v["outline"], v["opacity"], filled=False, width=v["width"])


_register(
    "polygon",
    "Draw a closed shape through the points, filled, outlined, or both.",
    [
        Param("points", "points", "Corners [[x, y], ...] in order", min_items=3, max_items=MAX_POINTS),
        FILL,
        OUTLINE,
        WIDTH,
        OPACITY,
    ],
    _draw_polygon,
    _need_fill_or_outline,
)


def _draw_fill(layer, v, size):
    raster.flood_fill(layer, v["point"], v["colour"], v["tolerance"])


_register(
    "fill",
    "Flood-fill the connected area of similar pixels around a point on this layer. "
    "Draw an outline on the same layer first to fill inside it.",
    [
        Param("point", "point", "Seed point [x, y] inside the area to fill", inside_canvas=True),
        Param("colour", "colour", "Fill colour; use #rrggbbaa for a transparent fill"),
        Param("tolerance", "int", "Total difference allowed from the seed pixel, summed over red, green, blue and alpha; 0 to 255",
              required=False, default=0, minimum=0, maximum=MAX_TOLERANCE),
    ],
    _draw_fill,
)


def _draw_text(layer, v, size):
    raster.draw_text(layer, v["text"], v["point"], v["size"], v["font"], v["colour"], v["opacity"],
                     align=v["align"], valign=v["valign"])


_register(
    "text",
    "Write text. The point is the anchor: align and valign say which part of the text box sits on it. "
    "Use \\n inside the text for a new line.",
    [
        Param("text", "text", "The text to write"),
        Param("point", "point", "Anchor [x, y] in pixels; by default the top-left corner of the text"),
        Param("align", "choice", "Which side of the text the point is on, for each line",
              required=False, default="left", choices=("left", "center", "right")),
        Param("valign", "choice", "Which edge of the text the point is on",
              required=False, default="top", choices=("top", "middle", "bottom")),
        Param("size", "int", "Font size in pixels", minimum=4, maximum=500),
        Param("colour", "colour", "Text colour"),
        Param("font", "font", "Optional .ttf or .otf font file, relative to the document's folder or absolute. "
              "The built-in font is Latin only; use a font file for other scripts.", required=False),
        OPACITY,
    ],
    _draw_text,
)


def _draw_erase(layer, v, size):
    raster.erase_shape(layer, v["shape"], v["box"], v["opacity"])


_register(
    "erase",
    "Make a rectangle or ellipse transparent on this layer. Other layers below are not affected.",
    [
        Param("shape", "choice", "rect or ellipse", required=False, default="rect",
              choices=("rect", "ellipse")),
        Param("box", "box", "[x, y, width, height] of the area to erase"),
        Param("opacity", "float", "How much to erase, 0 to 1; 1 removes it completely",
              required=False, default=1.0, minimum=0, maximum=1),
    ],
    _draw_erase,
)


def _draw_place(layer, v, size):
    with Image.open(v["image"]) as opened:
        picture = opened.convert("RGBA")
    width, height = v["width"], v["height"]
    if width is not None or height is not None:
        if width is None:
            width = round(picture.width * height / picture.height)
        if height is None:
            height = round(picture.height * width / picture.width)
        picture = picture.resize((max(1, width), max(1, height)), Image.LANCZOS)
    raster.place_image(layer, picture, v["point"], v["opacity"])


_register(
    "place",
    "Paste a picture file (PNG, JPEG, or WebP) with its top-left corner at a point. "
    "Its own transparency is kept. Give width or height to resize; the other side keeps its proportion.",
    [
        Param("image", "image", "Picture file, relative to the document's folder or absolute"),
        Param("point", "point", "Top-left corner [x, y] in pixels"),
        Param("width", "int", "Width in pixels after resizing", required=False, minimum=1, maximum=MAX_SIZE),
        Param("height", "int", "Height in pixels after resizing", required=False, minimum=1, maximum=MAX_SIZE),
        OPACITY,
    ],
    _draw_place,
)


def _draw_path(layer, v, size):
    if v["fill"] is not None:
        raster.draw_path(layer, v["d"], v["fill"], v["opacity"], filled=True)
    if v["outline"] is not None:
        raster.draw_path(layer, v["d"], v["outline"], v["opacity"], filled=False, width=v["width"])


_register(
    "path",
    "Draw a shape or line from SVG path data: M, L, H, V, C, S, Q, T, and Z, in absolute or relative form. "
    "Curves are smooth. Use it for organic shapes such as faces, limbs, and clothes.",
    [
        Param("d", "path", "SVG path data, for example 'M 10 10 C 40 0 60 0 90 10 L 90 60 Z'"),
        FILL,
        OUTLINE,
        WIDTH,
        OPACITY,
    ],
    _draw_path,
    _need_fill_or_outline,
)


def normalise(raw, size: tuple[int, int], base=None) -> tuple[str, dict]:
    """Check one operation dict and return (name, values). Raises PaintError with a clear message.

    `base` is the folder that relative file paths are read from.
    """
    if not isinstance(raw, dict):
        raise PaintError("each operation must be a JSON object")
    name = raw.get("op")
    if name not in OPERATIONS:
        raise PaintError(f"op must be one of: {', '.join(OPERATIONS)} (got {name!r})")
    operation = OPERATIONS[name]
    allowed = {"op", "layer", "id"} | {p.name for p in operation.params}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise PaintError(f"{name} has unknown field(s): {', '.join(unknown)}")
    if not isinstance(raw.get("layer"), str):
        raise PaintError(f"{name} needs a layer id (text)")
    if "id" in raw and (not isinstance(raw["id"], str) or not ID_PATTERN.match(raw["id"])):
        raise PaintError(f"{name} id must be 1 to 40 letters, digits, '-' or '_'")
    values = {}
    for param in operation.params:
        if param.name in raw:
            values[param.name] = coerce(param, raw[param.name], size, base)
        elif param.required:
            raise PaintError(f"{name} needs {param.name}")
        else:
            values[param.name] = param.default
    if operation.check is not None:
        operation.check(values)
    return name, values


def draw(name: str, layer: Image.Image, values: dict, size: tuple[int, int]) -> None:
    OPERATIONS[name].draw(layer, values, size)
