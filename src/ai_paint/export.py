"""Compile a whole document into one standalone SVG file.

Each layer becomes an Inkscape layer (a group), with its opacity, blur and outline as SVG attributes and
filters. Shapes, paths, strokes, text, balloons, gradients, screentones, erasing, pasted pictures and svg ops
all become SVG elements. A flood fill works on pixels, so a layer that uses one is drawn by ai-paint and
embedded as a picture; the export report lists those layers.
"""

import base64
import io
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from PIL import Image

from ai_paint import document, ops, raster, svgpath
from ai_paint.gradient import Gradient
from ai_paint.params import parse_colour
from ai_paint.screentone import ScreenTone
from ai_paint.svgrender import SVG_NS, XLINK_NS, expand_library, wrap_fragment

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
PIXEL_OPS = {"fill"}


def _n(value: float) -> str:
    """A short number for SVG output."""
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _hex(colour: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour[:3])


def _points(points: list) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in points)


def _png_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class _Builder:
    def __init__(self, size: tuple[int, int]):
        self.size = size
        self.defs: list[str] = []
        self.counter = 0

    def new_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter}"

    def paint(self, kind: str, value) -> str:
        """Attributes that paint the fill or stroke with a colour, gradient or screentone."""
        if isinstance(value, Gradient):
            gradient_id = self.new_id("gradient")
            stops = "".join(
                f'<stop offset="{_n(position)}" stop-color="{_hex(colour)}" stop-opacity="{_n(colour[3] / 255)}"/>'
                for position, colour in zip(value.positions, value.colours.astype(int))
            )
            if value.kind == "linear":
                (x1, y1), (x2, y2) = value.geometry["start"], value.geometry["end"]
                self.defs.append(f'<linearGradient id="{gradient_id}" gradientUnits="userSpaceOnUse" '
                                 f'x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}">{stops}</linearGradient>')
            else:
                cx, cy = value.geometry["centre"]
                self.defs.append(f'<radialGradient id="{gradient_id}" gradientUnits="userSpaceOnUse" '
                                 f'cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(value.geometry["radius"])}">{stops}</radialGradient>')
            return f'{kind}="url(#{gradient_id})"'
        if isinstance(value, ScreenTone):
            pattern_id = self.new_id("screentone")
            cell = value.cell
            radius = cell * math.sqrt(value.density / math.pi)
            colour = value.colour
            self.defs.append(
                f'<pattern id="{pattern_id}" patternUnits="userSpaceOnUse" width="{_n(cell)}" height="{_n(cell)}" '
                f'patternTransform="rotate({_n(math.degrees(value.angle))})">'
                f'<circle cx="{_n(cell / 2)}" cy="{_n(cell / 2)}" r="{_n(radius)}" fill="{_hex(colour)}" '
                f'fill-opacity="{_n(colour[3] / 255)}"/></pattern>'
            )
            return f'{kind}="url(#{pattern_id})"'
        attributes = f'{kind}="{_hex(value)}"'
        if value[3] < 255:
            attributes += f' {kind}-opacity="{_n(value[3] / 255)}"'
        return attributes

    def filter(self, body: str) -> str:
        filter_id = self.new_id("filter")
        width, height = self.size
        self.defs.append(f'<filter id="{filter_id}" filterUnits="userSpaceOnUse" x="0" y="0" '
                         f'width="{width}" height="{height}">{body}</filter>')
        return filter_id


def _box_element(shape: str, box: list, attributes: str) -> str:
    x, y, w, h = box
    if shape == "rect":
        return f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" {attributes}/>'
    return (f'<ellipse cx="{_n(x + w / 2)}" cy="{_n(y + h / 2)}" rx="{_n(w / 2)}" ry="{_n(h / 2)}" '
            f'{attributes}/>')


def _filled_and_outlined(builder, make, v) -> list[str]:
    out = []
    if v.get("fill") is not None:
        out.append(make(builder.paint("fill", v["fill"])))
    if v.get("outline") is not None:
        out.append(make(f'fill="none" {builder.paint("stroke", v["outline"])} stroke-width="{_n(v["width"])}" '
                        f'stroke-linejoin="round"'))
    return out


def _text_elements(text: str, xy, size: int, font_path, colour, align: str, valign: str) -> list[str]:
    font, origin_x, origin_y, _ = raster.text_layout(text, xy, size, font_path, align, valign)
    family, style = font.getname()
    weight = ' font-weight="bold"' if style and "bold" in style.lower() else ""
    lines = text.split("\n")
    line_spacing = font.getbbox("A")[3] + 4  # the same spacing Pillow uses for multi-line text
    ascent = font.getmetrics()[0]
    widths = [font.getlength(line) for line in lines]
    widest = max(widths)
    share = {"left": 0.0, "center": 0.5, "right": 1.0}[align]
    paint = f'fill="{_hex(colour)}"' + (f' fill-opacity="{_n(colour[3] / 255)}"' if colour[3] < 255 else "")
    out = []
    for index, (line, line_width) in enumerate(zip(lines, widths)):
        x = origin_x + (widest - line_width) * share
        y = origin_y + index * line_spacing + ascent
        out.append(f'<text x="{_n(x)}" y="{_n(y)}" font-family={quoteattr(family)} font-size="{size}"{weight} '
                   f'{paint} xml:space="preserve">{escape(line)}</text>')
    return out


def _stroke_elements(builder, v) -> list[str]:
    style = raster.BRUSHES[v["brush"]]
    radius = v["size"] / 2
    colour = v["colour"]
    points = v["points"]
    simple = v["taper"] == 0 and v["size_end"] is None and style["hardness"] >= 1.0
    if simple:
        if len(points) == 1:
            return [f'<circle cx="{_n(points[0][0])}" cy="{_n(points[0][1])}" r="{_n(radius)}" '
                    f'{builder.paint("fill", colour)}/>']
        return [f'<polyline points="{_points(points)}" fill="none" {builder.paint("stroke", colour)} '
                f'stroke-width="{_n(v["size"])}" stroke-linecap="round" stroke-linejoin="round"/>']
    # Tapered, thinning or soft strokes: the same dabs ai-paint stamps, as circles in one group,
    # so overlapping dabs do not darken each other.
    end_radius = v["size_end"] / 2 if v["size_end"] is not None else None
    positions, total = raster._dab_positions(points, max(1.0, style["spacing"] * radius))
    circles = []
    for x, y, along in positions:
        dab = radius
        if end_radius is not None and total > 0:
            dab = radius + (end_radius - radius) * along / total
        if v["taper"] > 0 and total > 0:
            dab *= max(raster.MIN_TAPER, min(1.0, min(along, total - along) / (v["taper"] * total)))
        circles.append(f'<circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(dab)}"/>')
    blur = ""
    if style["hardness"] < 1.0:
        soften = '<feGaussianBlur stdDeviation="' + _n(radius * 0.35) + '"/>'
        blur = ' filter="url(#' + builder.filter(soften) + ')"'
    return [f'<g fill="{_hex(colour)}" opacity="{_n(colour[3] / 255)}"{blur}>{"".join(circles)}</g>']


def _prefix_ids(markup: str, prefix: str) -> str:
    """Rename every id in the markup, and every reference to it, so several svg ops can share one file."""
    ids = set(re.findall(r'\bid="([^"]+)"', markup))
    if not ids:
        return markup

    def rename(match):
        return match.group(1) + prefix + match.group(2) + match.group(3)

    for element_id in sorted(ids, key=len, reverse=True):
        quoted = re.escape(element_id)
        markup = re.sub(rf'(\bid=")({quoted})(")', lambda m: f'{m.group(1)}{prefix}{m.group(2)}{m.group(3)}', markup)
        markup = re.sub(rf'(href="#)({quoted})(")', rename, markup)
        markup = re.sub(rf'(url\(\s*#)({quoted})(\s*\))', rename, markup)
    return markup


def _svg_op_element(v, size, prefix: str) -> str:
    box = v["box"] if v["box"] is not None else [0, 0, size[0], size[1]]
    width, height = max(1, round(box[2])), max(1, round(box[3]))
    markup = v["svg"] if v["svg"] is not None else v["file"]
    markup = _prefix_ids(expand_library(markup), prefix)
    root = ET.fromstring(wrap_fragment(markup, width, height))
    if root.get("viewBox") is None:
        try:
            root.set("viewBox", f'0 0 {_n(float(root.get("width")))} {_n(float(root.get("height")))}')
        except (TypeError, ValueError):
            root.set("viewBox", f"0 0 {width} {height}")
    root.set("x", _n(box[0]))
    root.set("y", _n(box[1]))
    root.set("width", _n(width))
    root.set("height", _n(height))
    root.set("overflow", "hidden")
    return ET.tostring(root, encoding="unicode")


def _op_elements(builder, raw, name, v, size) -> list[str]:
    if name in ("rect", "ellipse"):
        return _filled_and_outlined(builder, lambda attrs: _box_element(name, v["box"], attrs), v)
    if name == "polygon":
        return _filled_and_outlined(builder, lambda attrs: f'<polygon points="{_points(v["points"])}" {attrs}/>', v)
    if name == "line":
        return [f'<polyline points="{_points(v["points"])}" fill="none" {builder.paint("stroke", v["colour"])} '
                f'stroke-width="{_n(v["width"])}" stroke-linejoin="round"/>']
    if name == "path":
        rule = "evenodd" if v["fill_rule"] == "evenodd" else "nonzero"
        return _filled_and_outlined(
            builder, lambda attrs: f'<path d={quoteattr(raw["d"])} fill-rule="{rule}" {attrs}/>', v)
    if name == "spline":
        points = svgpath.spline(v["points"], closed=v["closed"])
        d = "M " + " L ".join(f"{_n(x)} {_n(y)}" for x, y in points) + (" Z" if v["closed"] else "")
        return _filled_and_outlined(builder, lambda attrs: f'<path d="{d}" {attrs}/>', v)
    if name == "stroke":
        return _stroke_elements(builder, v)
    if name == "text":
        return _text_elements(v["text"], v["point"], v["size"], v["font"], v["colour"], v["align"], v["valign"])
    if name == "balloon":
        points = ops.balloon_points(v)
        fill = v["fill"] if v["fill"] is not None else (255, 255, 255, 255)
        outline = v["outline"] if v["outline"] is not None else (0, 0, 0, 255)
        text_colour = v["colour"] if v["colour"] is not None else (0, 0, 0, 255)
        return [f'<polygon points="{_points(points)}" {builder.paint("fill", fill)}/>',
                f'<polygon points="{_points(points)}" fill="none" {builder.paint("stroke", outline)} '
                f'stroke-width="{_n(v["width"])}" stroke-linejoin="round"/>',
                *_text_elements(v["text"], v["centre"], v["size"], v["font"], text_colour, "center", "middle")]
    if name == "place":
        with Image.open(v["image"]) as opened:
            picture = opened.convert("RGBA")
        width, height = v["width"], v["height"]
        if width is not None or height is not None:
            if width is None:
                width = round(picture.width * height / picture.height)
            if height is None:
                height = round(picture.height * width / picture.width)
            picture = picture.resize((max(1, width), max(1, height)), Image.LANCZOS)
        x, y = round(v["point"][0]), round(v["point"][1])
        return [f'<image x="{x}" y="{y}" width="{picture.width}" height="{picture.height}" '
                f'href="{_png_data_uri(picture)}"/>']
    if name == "svg":
        return [_svg_op_element(v, size, builder.new_id("svg") + "-")]
    raise AssertionError(f"export does not handle {name}")


def _layer_filter(builder, layer: dict) -> str | None:
    steps, source = [], "SourceGraphic"
    if layer.get("blur", 0):
        steps.append(f'<feGaussianBlur in="SourceGraphic" stdDeviation="{_n(layer["blur"])}" result="blurred"/>')
        source = "blurred"
    if layer.get("outline") is not None:
        outline = layer["outline"]
        colour = parse_colour(outline.get("colour", "#000000"))
        steps.append(
            f'<feMorphology in="{source}" operator="dilate" radius="{_n(round(outline.get("width", 2)))}" '
            f'result="grown"/>'
            f'<feFlood flood-color="{_hex(colour)}" flood-opacity="{_n(colour[3] / 255)}" result="ink"/>'
            f'<feComposite in="ink" in2="grown" operator="in" result="ring"/>'
            f'<feMerge><feMergeNode in="ring"/><feMergeNode in="{source}"/></feMerge>'
        )
    return builder.filter("".join(steps)) if steps else None


def compile_document(doc, base: Path | None = None) -> tuple[str, dict]:
    """Return (svg_text, report). The report lists layers that had to be embedded as pictures."""
    document._raise_if_invalid(doc, base)
    size = document._canvas_size(doc["canvas"])
    width, height = size
    builder = _Builder(size)
    grouped = document.ops_by_layer(doc, size, base)
    body: list[str] = []
    background = doc["canvas"].get("background")
    if background is not None:
        body.append(f'<rect width="{width}" height="{height}" {builder.paint("fill", parse_colour(background))}/>')
    pictured = []
    for layer in doc["layers"]:
        items = grouped.get(layer["id"], [])
        attributes = [f'id={quoteattr("layer-" + layer["id"])}', 'inkscape:groupmode="layer"',
                      f'inkscape:label={quoteattr(layer.get("name", layer["id"]))}']
        if not layer.get("visible", True):
            attributes.append('style="display:none"')
        if layer.get("opacity", 1.0) < 1:
            attributes.append(f'opacity="{_n(layer["opacity"])}"')
        if any(name in PIXEL_OPS for _, name, _ in items):
            content = document.layer_content(layer, [(name, values) for _, name, values in items], size)
            pictured.append(layer["id"])
            elements = [f'<image x="0" y="0" width="{width}" height="{height}" href="{_png_data_uri(content)}"/>']
        else:
            filter_id = _layer_filter(builder, layer)
            if filter_id:
                attributes.append(f'filter="url(#{filter_id})"')
            elements = []
            for raw, name, values in items:
                if name == "erase":
                    mask_id = builder.new_id("erase")
                    shape = _box_element(values["shape"], values["box"],
                                         f'fill="#000000" fill-opacity="{_n(values["opacity"])}"')
                    builder.defs.append(f'<mask id="{mask_id}" maskUnits="userSpaceOnUse" x="0" y="0" '
                                        f'width="{width}" height="{height}"><rect width="{width}" '
                                        f'height="{height}" fill="#ffffff"/>{shape}</mask>')
                    elements = [f'<g mask="url(#{mask_id})">{"".join(elements)}</g>']
                    continue
                parts = _op_elements(builder, raw, name, values, size)
                opacity = values.get("opacity", 1.0)
                group = []
                if raw.get("id"):
                    group.append(f'id={quoteattr("op-" + raw["id"])}')
                if opacity < 1:
                    group.append(f'opacity="{_n(opacity)}"')
                if group:
                    elements.append(f'<g {" ".join(group)}>{"".join(parts)}</g>')
                else:
                    elements.extend(parts)
        body.append(f'<g {" ".join(attributes)}>{"".join(elements)}</g>')
    svg = (f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}" xmlns:inkscape="{INKSCAPE_NS}" '
           f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
           f'<defs>{"".join(builder.defs)}</defs>{"".join(body)}</svg>')
    return svg, {"width": width, "height": height, "layers_as_pictures": pictured}
