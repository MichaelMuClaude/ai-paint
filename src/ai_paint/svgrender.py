"""Draw SVG code with librsvg, the SVG renderer that ships with most Linux desktops.

SVG gives a drawing agent groups, transforms, clipping, masks, reuse with <use>, gradients, filters such as
blur and drop shadow, and text. The markup is checked against an allow-list before it is drawn: scripts,
event attributes, external links, and DOCTYPE declarations are refused, and every reference must point
inside the same SVG (#id).

librsvg and cairo are loaded at run time from the system (packages librsvg2-2 and libcairo2 on Debian and
Ubuntu). They are not bundled with ai-paint.
"""

import ctypes
import re
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

from ai_paint.errors import PaintError

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_MARKUP = 2_000_000
MAX_ELEMENTS = 50_000

ALLOWED_ELEMENTS = {
    "svg", "g", "defs", "symbol", "use", "title", "desc",
    "path", "circle", "ellipse", "rect", "line", "polyline", "polygon",
    "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "pattern", "clipPath", "mask", "marker",
    "filter", "feGaussianBlur", "feOffset", "feFlood", "feComposite", "feMerge", "feMergeNode",
    "feBlend", "feColorMatrix", "feDropShadow", "feMorphology", "feTurbulence",
    "feDisplacementMap", "feComponentTransfer", "feFuncR", "feFuncG", "feFuncB", "feFuncA",
}
URL_REFERENCE = re.compile(r"url\(\s*([^)]*)\)")


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def check_svg(markup: str) -> ET.Element:
    """Parse and check SVG markup. Returns the root element, or raises PaintError naming the problem."""
    if not isinstance(markup, str) or not markup.strip():
        raise PaintError("svg must be SVG markup text")
    if len(markup) > MAX_MARKUP:
        raise PaintError(f"svg markup is longer than {MAX_MARKUP} characters")
    if re.search(r"<!DOCTYPE|<!ENTITY", markup, re.IGNORECASE):
        raise PaintError("svg must not contain DOCTYPE or ENTITY declarations")
    try:
        root = ET.fromstring(markup)
    except ET.ParseError as exc:
        raise PaintError(f"svg is not well-formed XML: {exc}") from exc
    count = 0
    for element in root.iter():
        count += 1
        if count > MAX_ELEMENTS:
            raise PaintError(f"svg has more than {MAX_ELEMENTS} elements")
        name = _local_name(element.tag)
        if name not in ALLOWED_ELEMENTS:
            raise PaintError(f"svg element <{name}> is not allowed")
        for attribute, value in element.attrib.items():
            local = _local_name(attribute)
            if local.lower().startswith("on"):
                raise PaintError(f"svg attribute {local} is not allowed (no event handlers)")
            if local == "href" and not value.strip().startswith("#"):
                raise PaintError(f"svg href must point inside the same SVG, like '#id' (got {value!r})")
            for target in URL_REFERENCE.findall(value):
                if not target.strip().strip("'\"").startswith("#"):
                    raise PaintError(f"svg url() must point inside the same SVG, like url(#id) (got {target!r})")
    return root


def wrap_fragment(markup: str, width: int, height: int) -> str:
    """Wrap SVG elements without an <svg> root in one sized to the box, so coordinates are box pixels."""
    if re.match(r"\s*(<\?xml[^>]*>\s*)?<svg\b", markup):
        return markup
    return (f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">{markup}</svg>')


class _GError(ctypes.Structure):
    _fields_ = [("domain", ctypes.c_uint32), ("code", ctypes.c_int), ("message", ctypes.c_char_p)]


class _Rectangle(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double),
                ("width", ctypes.c_double), ("height", ctypes.c_double)]


_LIBRARIES = None


def _libraries():
    global _LIBRARIES
    if _LIBRARIES is None:
        try:
            rsvg = ctypes.CDLL("librsvg-2.so.2")
            cairo = ctypes.CDLL("libcairo.so.2")
            gobject = ctypes.CDLL("libgobject-2.0.so.0")
            glib = ctypes.CDLL("libglib-2.0.so.0")
        except OSError as exc:
            raise PaintError("drawing SVG needs librsvg and cairo; on Debian or Ubuntu install librsvg2-2") from exc
        rsvg.rsvg_handle_new_from_data.restype = ctypes.c_void_p
        rsvg.rsvg_handle_new_from_data.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                                   ctypes.POINTER(ctypes.POINTER(_GError))]
        rsvg.rsvg_handle_render_document.restype = ctypes.c_int
        rsvg.rsvg_handle_render_document.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_Rectangle),
                                                     ctypes.POINTER(ctypes.POINTER(_GError))]
        cairo.cairo_image_surface_create.restype = ctypes.c_void_p
        cairo.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        cairo.cairo_create.restype = ctypes.c_void_p
        cairo.cairo_create.argtypes = [ctypes.c_void_p]
        cairo.cairo_surface_flush.argtypes = [ctypes.c_void_p]
        cairo.cairo_image_surface_get_data.restype = ctypes.POINTER(ctypes.c_ubyte)
        cairo.cairo_image_surface_get_data.argtypes = [ctypes.c_void_p]
        cairo.cairo_image_surface_get_stride.restype = ctypes.c_int
        cairo.cairo_image_surface_get_stride.argtypes = [ctypes.c_void_p]
        cairo.cairo_destroy.argtypes = [ctypes.c_void_p]
        cairo.cairo_surface_destroy.argtypes = [ctypes.c_void_p]
        gobject.g_object_unref.argtypes = [ctypes.c_void_p]
        glib.g_error_free.argtypes = [ctypes.POINTER(_GError)]
        _LIBRARIES = (rsvg, cairo, gobject, glib)
    return _LIBRARIES


def available() -> bool:
    """True when librsvg and cairo can be loaded, so SVG can be drawn on this machine."""
    try:
        _libraries()
    except PaintError:
        return False
    return True


def _raise_gerror(error, what: str) -> None:
    glib = _libraries()[3]
    message = error.contents.message.decode("utf-8", "replace") if error and error.contents.message else "unknown"
    if error:
        glib.g_error_free(error)
    raise PaintError(f"{what}: {message}")


def render_svg(markup: str, width: int, height: int) -> Image.Image:
    """Draw checked SVG markup into a transparent RGBA image of the given size."""
    if width < 1 or height < 1:
        raise PaintError("svg box must be at least 1 by 1 pixels")
    rsvg, cairo, gobject, _ = _libraries()
    data = markup.encode("utf-8")
    error = ctypes.POINTER(_GError)()
    handle = rsvg.rsvg_handle_new_from_data(data, len(data), ctypes.byref(error))
    if not handle:
        _raise_gerror(error, "librsvg could not read the svg")
    surface = cairo.cairo_image_surface_create(0, width, height)  # 0 = CAIRO_FORMAT_ARGB32
    context = cairo.cairo_create(surface)
    try:
        viewport = _Rectangle(0, 0, width, height)
        if not rsvg.rsvg_handle_render_document(handle, context, ctypes.byref(viewport), ctypes.byref(error)):
            _raise_gerror(error, "librsvg could not draw the svg")
        cairo.cairo_surface_flush(surface)
        stride = cairo.cairo_image_surface_get_stride(surface)
        buffer = ctypes.string_at(cairo.cairo_image_surface_get_data(surface), stride * height)
    finally:
        cairo.cairo_destroy(context)
        cairo.cairo_surface_destroy(surface)
        gobject.g_object_unref(handle)
    # cairo stores premultiplied pixels as B, G, R, A on little-endian machines
    pixels = np.frombuffer(buffer, dtype=np.uint8).reshape(height, stride)[:, :width * 4].reshape(height, width, 4)
    blue, green, red, alpha = (pixels[..., i].astype(np.float64) for i in range(4))
    safe = np.maximum(alpha, 1.0)
    rgba = np.stack([
        np.where(alpha > 0, red * 255 / safe, 0),
        np.where(alpha > 0, green * 255 / safe, 0),
        np.where(alpha > 0, blue * 255 / safe, 0),
        alpha,
    ], axis=-1)
    return Image.fromarray(np.clip(np.round(rgba), 0, 255).astype(np.uint8), "RGBA")


# --- the part library -----------------------------------------------------------------------------

from functools import lru_cache  # noqa: E402
from pathlib import Path  # noqa: E402

LIBRARY_DIR = Path(__file__).parent / "library"
LIBRARY_REFERENCE = re.compile(r"#(lib-[a-z0-9-]+)")
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


@lru_cache(maxsize=1)
def library() -> dict:
    """The built-in parts, as {"lib-name": {"description": ..., "defs": markup, "ids": set of ids}}."""
    parts = {}
    for path in sorted(LIBRARY_DIR.glob("*.svg")):
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        description = ""
        defs_markup = []
        ids = set()
        for child in root:
            name = _local_name(child.tag)
            if name == "desc":
                description = (child.text or "").strip()
            elif name == "defs":
                for item in child:
                    defs_markup.append(ET.tostring(item, encoding="unicode"))
                    ids.update(element.get("id") for element in item.iter() if element.get("id"))
        parts["lib-" + path.stem] = {"description": description, "defs": "".join(defs_markup), "ids": ids}
    return parts


def _part_for(reference: str) -> str:
    parts = library()
    for name, part in parts.items():
        if reference in part["ids"]:
            return name
    raise PaintError(
        f"svg refers to #{reference}, which is not a library part; available parts: {', '.join(parts)}"
    )


def expand_library(markup: str) -> str:
    """Add the definitions of every library part the markup uses (href="#lib-...") to the markup."""
    needed: list[str] = []
    pending = LIBRARY_REFERENCE.findall(markup)
    defined_here = set(re.findall(r'\bid="(lib-[a-z0-9-]+)"', markup))
    while pending:
        reference = pending.pop()
        if reference in defined_here:
            continue
        name = _part_for(reference)
        if name not in needed:
            needed.append(name)
            pending.extend(LIBRARY_REFERENCE.findall(library()[name]["defs"]))
    if not needed:
        return markup
    defs = "<defs>" + "".join(library()[name]["defs"] for name in needed) + "</defs>"
    root = re.match(r"\s*(<\?xml[^>]*>\s*)?<svg\b[^>]*>", markup)
    if root:
        return markup[:root.end()] + defs + markup[root.end():]
    return defs + markup


# --- editing elements by id -----------------------------------------------------------------------

def _parse_for_edit(markup: str):
    if re.match(r"\s*(<\?xml[^>]*>\s*)?<svg\b", markup):
        return ET.fromstring(markup), False
    return ET.fromstring(f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}">{markup}</svg>'), True


def _serialise(root, fragment: bool) -> str:
    if fragment:
        return "".join(ET.tostring(child, encoding="unicode") for child in root)
    return ET.tostring(root, encoding="unicode")


def _find(root, element_id: str):
    for parent in root.iter():
        for index, child in enumerate(list(parent)):
            if child.get("id") == element_id:
                return parent, index, child
    raise PaintError(f"there is no element with id {element_id!r} in this svg; run 'ai-paint elements' to see them")


def set_attributes(markup: str, element_id: str, attributes: dict) -> str:
    """Change attributes of one element. A value of null removes the attribute."""
    if not isinstance(attributes, dict):
        raise PaintError(f"svg_set for {element_id!r} must be an object of attribute names and values")
    root, fragment = _parse_for_edit(markup)
    _, _, element = _find(root, element_id)
    for name, value in attributes.items():
        if name == "id":
            raise PaintError("an element's id cannot be changed with svg_set; use svg_replace")
        if value is None:
            element.attrib.pop(name, None)
        else:
            element.set(name, str(value))
    return _serialise(root, fragment)


def remove_element(markup: str, element_id: str) -> str:
    root, fragment = _parse_for_edit(markup)
    parent, index, _ = _find(root, element_id)
    del parent[index]
    return _serialise(root, fragment)


def replace_element(markup: str, element_id: str, new_markup: str) -> str:
    """Put new markup (one or more elements) where the element with this id was."""
    if not isinstance(new_markup, str) or not new_markup.strip():
        raise PaintError(f"svg_replace for {element_id!r} needs SVG markup text")
    root, fragment = _parse_for_edit(markup)
    parent, index, _ = _find(root, element_id)
    try:
        replacement = ET.fromstring(f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}">{new_markup}</svg>')
    except ET.ParseError as exc:
        raise PaintError(f"svg_replace markup for {element_id!r} is not well-formed: {exc}") from exc
    del parent[index]
    for offset, child in enumerate(list(replacement)):
        parent.insert(index + offset, child)
    return _serialise(root, fragment)


def elements(markup: str) -> list[dict]:
    """Every element that has an id, with its tag and a few useful attributes."""
    root, _ = _parse_for_edit(markup)
    rows = []
    for element in root.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        details = {key: element.get(key) for key in ("href", "fill", "stroke", "transform", "color", "opacity")
                   if element.get(key) is not None}
        rows.append({"id": element_id, "tag": _local_name(element.tag), **details})
    return rows
