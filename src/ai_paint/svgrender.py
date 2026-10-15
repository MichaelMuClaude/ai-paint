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
