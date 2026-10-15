"""Looking at a picture: a coordinate grid and a zoomed crop. These never change the document."""

from PIL import Image, ImageDraw, ImageFont

from ai_paint.errors import PaintError

MAX_ZOOM = 8
MAX_OUTPUT_SIDE = 8_000
GRID_LINE = (0, 0, 0, 70)
GRID_MAJOR = (0, 0, 0, 140)
LABEL_TEXT = (0, 0, 0, 255)
LABEL_BOX = (255, 255, 255, 220)


def _label_font():
    try:
        return ImageFont.load_default(size=11)
    except TypeError:  # Pillow older than 10.1 has no size argument
        return ImageFont.load_default()


def draw_grid(image: Image.Image, step: int, origin: tuple[int, int] = (0, 0), scale: int = 1) -> Image.Image:
    """Return a copy with a line every `step` picture pixels, a darker line every 5th, and labels.

    `image` may be a crop of the picture that starts at `origin` and is enlarged by `scale`.
    Labels show the picture's own coordinates, so they stay correct after a crop or zoom.
    """
    if step < 2:
        raise PaintError("grid step must be at least 2 pixels")
    out = image.copy()
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _label_font()
    x0, y0 = origin
    width, height = out.size
    first_x = -(-x0 // step) * step  # first multiple of step at or after x0
    for X in range(first_x, x0 + -(-width // scale), step):
        px = (X - x0) * scale
        major = (X // step) % 5 == 0
        draw.line([(px, 0), (px, height)], fill=GRID_MAJOR if major else GRID_LINE, width=1)
        if major and X > 0:
            _label(draw, font, str(X), px + 2, 2)
    first_y = -(-y0 // step) * step
    for Y in range(first_y, y0 + -(-height // scale), step):
        py = (Y - y0) * scale
        major = (Y // step) % 5 == 0
        draw.line([(0, py), (width, py)], fill=GRID_MAJOR if major else GRID_LINE, width=1)
        if major and Y > 0:
            _label(draw, font, str(Y), 2, py + 2)
    return Image.alpha_composite(out, overlay)


def _label(draw: ImageDraw.ImageDraw, font, text: str, x: int, y: int) -> None:
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    draw.rectangle([left - 1, top - 1, right + 1, bottom + 1], fill=LABEL_BOX)
    draw.text((x, y), text, fill=LABEL_TEXT, font=font)


def crop_and_zoom(image: Image.Image, box: tuple[int, int, int, int] | None, zoom: int) -> Image.Image:
    """Crop to `box` (x, y, width, height), then enlarge by `zoom` with hard pixels so each one is easy to count."""
    if not 1 <= zoom <= MAX_ZOOM:
        raise PaintError(f"zoom must be a whole number from 1 to {MAX_ZOOM}")
    if box is not None:
        x, y, w, h = box
        if w < 1 or h < 1:
            raise PaintError("crop width and height must be at least 1")
        if x < 0 or y < 0 or x + w > image.width or y + h > image.height:
            raise PaintError(
                f"crop {box} is outside the {image.width}x{image.height} picture"
            )
        image = image.crop((x, y, x + w, y + h))
    if image.width * zoom > MAX_OUTPUT_SIDE or image.height * zoom > MAX_OUTPUT_SIDE:
        raise PaintError(f"zoomed output would be larger than {MAX_OUTPUT_SIDE} pixels on a side; use a smaller crop or zoom")
    if zoom == 1:
        return image
    return image.resize((image.width * zoom, image.height * zoom), Image.NEAREST)


def parse_box(text: str) -> tuple[int, int, int, int]:
    """Read 'x,y,width,height' from the command line."""
    parts = [part.strip() for part in text.split(",")]
    try:
        numbers = [int(part) for part in parts]
    except ValueError as exc:
        raise PaintError(f"crop must be four whole numbers x,y,width,height (got {text!r})") from exc
    if len(numbers) != 4:
        raise PaintError(f"crop must be four whole numbers x,y,width,height (got {text!r})")
    return tuple(numbers)
