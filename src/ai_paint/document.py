"""The document: a JSON file with a canvas, a list of layers, and an ordered list of operations."""

import copy
import json
from pathlib import Path

from PIL import Image

from ai_paint import ops
from ai_paint.errors import PaintError
from ai_paint.params import ID_PATTERN, MAX_SIZE, parse_colour

SCHEMA = "ai-paint/1"
MAX_PIXELS = 25_000_000
BLEND_MODES = ("normal",)
DOCUMENT_KEYS = {"schema", "canvas", "layers", "ops"}
LAYER_KEYS = {"id", "name", "opacity", "visible", "blend"}
CHANGE_KEYS = {"layers", "ops", "update", "remove", "update_layers", "remove_layers", "canvas"}


def _whole(value, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise PaintError(f"{label} must be a whole number from {low} to {high}")
    return value


def _canvas_size(canvas) -> tuple[int, int]:
    if not isinstance(canvas, dict):
        raise PaintError("canvas must be an object with width and height")
    width = _whole(canvas.get("width"), "canvas width", 1, MAX_SIZE)
    height = _whole(canvas.get("height"), "canvas height", 1, MAX_SIZE)
    if width * height > MAX_PIXELS:
        raise PaintError(f"canvas is {width * height} pixels; the limit is {MAX_PIXELS}")
    background = canvas.get("background")
    if background is not None:
        parse_colour(background)
    return width, height


def new_document(width: int, height: int, background: str | None = "#ffffff", layer_name: str = "base") -> dict:
    canvas = {"width": width, "height": height, "background": background}
    _canvas_size(canvas)  # raises PaintError if the size or colour is wrong
    return {
        "schema": SCHEMA,
        "canvas": canvas,
        "layers": [{"id": "l1", "name": layer_name, "opacity": 1.0, "visible": True, "blend": "normal"}],
        "ops": [],
    }


def _layer_problems(layers) -> tuple[list[str], set]:
    if not isinstance(layers, list) or not layers:
        return ["layers must be a non-empty list"], set()
    problems, ids = [], set()
    for index, layer in enumerate(layers):
        prefix = f"layers[{index}]: "
        if not isinstance(layer, dict):
            problems.append(prefix + "must be an object")
            continue
        unknown = sorted(set(layer) - LAYER_KEYS)
        if unknown:
            problems.append(prefix + f"unknown field(s): {', '.join(unknown)}")
        layer_id = layer.get("id")
        if not isinstance(layer_id, str) or not ID_PATTERN.match(layer_id):
            problems.append(prefix + "id must be 1 to 40 letters, digits, '-' or '_'")
            continue
        if layer_id in ids:
            problems.append(prefix + f"duplicate id {layer_id!r}")
        ids.add(layer_id)
        opacity = layer.get("opacity", 1.0)
        if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
            problems.append(prefix + "opacity must be a number from 0 to 1")
        if not isinstance(layer.get("visible", True), bool):
            problems.append(prefix + "visible must be true or false")
        if layer.get("blend", "normal") not in BLEND_MODES:
            problems.append(prefix + f"blend must be one of: {', '.join(BLEND_MODES)}")
        if "name" in layer and not isinstance(layer["name"], str):
            problems.append(prefix + "name must be text")
    return problems, ids


def validate_document(doc, base: Path | None = None) -> list[str]:
    """Return every problem found, as text. An empty list means the document can be rendered.

    `base` is the folder that relative file paths (fonts and pictures) are read from.
    """
    if not isinstance(doc, dict):
        return ["document must be a JSON object"]
    problems = []
    unknown = sorted(set(doc) - DOCUMENT_KEYS)
    if unknown:
        problems.append(f"unknown top-level field(s): {', '.join(unknown)}")
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA!r}")
    try:
        size = _canvas_size(doc.get("canvas"))
    except PaintError as exc:
        problems.append(f"canvas: {exc}")
        return problems
    layer_problems, layer_ids = _layer_problems(doc.get("layers"))
    problems += layer_problems
    operations = doc.get("ops", [])
    if not isinstance(operations, list):
        return problems + ["ops must be a list"]
    op_ids = set()
    for index, raw in enumerate(operations):
        label = raw.get("id") if isinstance(raw, dict) else None
        prefix = f"ops[{index}]" + (f" (id {label})" if isinstance(label, str) else "") + ": "
        try:
            ops.normalise(raw, size, base)
        except PaintError as exc:
            problems.append(prefix + str(exc))
            continue
        if raw["layer"] not in layer_ids:
            problems.append(prefix + f"layer {raw['layer']!r} does not exist")
        if "id" in raw:
            if raw["id"] in op_ids:
                problems.append(prefix + f"duplicate id {raw['id']!r}")
            op_ids.add(raw["id"])
    return problems


def _raise_if_invalid(doc, base: Path | None = None) -> None:
    problems = validate_document(doc, base)
    if problems:
        raise PaintError("; ".join(problems))


def render(doc, base: Path | None = None) -> Image.Image:
    """Draw every visible layer, bottom to top, and return an RGBA image."""
    _raise_if_invalid(doc, base)
    size = _canvas_size(doc["canvas"])
    background = doc["canvas"].get("background")
    result = Image.new("RGBA", size, (0, 0, 0, 0) if background is None else parse_colour(background))

    by_layer: dict[str, list] = {}
    for raw in doc.get("ops", []):
        name, values = ops.normalise(raw, size, base)
        by_layer.setdefault(raw["layer"], []).append((name, values))

    for layer in doc["layers"]:
        if not layer.get("visible", True):
            continue
        content = Image.new("RGBA", size, (0, 0, 0, 0))
        for name, values in by_layer.get(layer["id"], []):
            ops.draw(name, content, values, size)
        opacity = layer.get("opacity", 1.0)
        if opacity < 1:
            alpha = content.getchannel("A").point(lambda v: round(v * opacity))
            content.putalpha(alpha)
        result = Image.alpha_composite(result, content)
    return result


def _next_id(prefix: str, taken: set) -> str:
    number = 1
    while f"{prefix}{number}" in taken:
        number += 1
    taken.add(f"{prefix}{number}")
    return f"{prefix}{number}"


def _layer_index(layers: list, layer_id: str, action: str) -> int:
    for index, layer in enumerate(layers):
        if isinstance(layer, dict) and layer.get("id") == layer_id:
            return index
    raise PaintError(f"{action}: there is no layer with id {layer_id!r}; run 'ai-paint info' to see the ids")


def _op_index(operations: list, op_id: str, action: str) -> int:
    for index, op in enumerate(operations):
        if isinstance(op, dict) and op.get("id") == op_id:
            return index
    raise PaintError(f"{action}: there is no op with id {op_id!r}; run 'ai-paint list' to see the ids")


def apply_changes(doc: dict, changes, base: Path | None = None) -> dict:
    """Return a new document with the changes applied. The input document is not modified.

    `changes` may contain:
    - "layers": layers to add to the top of the stack
    - "ops": operations to append, in order
    - "update": {op_id: {field: value, ...}} to change fields of existing ops; other fields stay
    - "remove": [op_id, ...] to delete existing ops
    - "update_layers": {layer_id: {field: value, ...}} to change fields of existing layers
    - "remove_layers": [layer_id, ...] to delete layers that have no ops left on them
    - "canvas": {"background": "#ffffff"} to change canvas fields (width, height, or background)
    Items without an id get one. The result is validated before it is returned.
    """
    if not isinstance(changes, dict):
        raise PaintError("changes must be a JSON object with optional 'layers', 'ops', 'update' and 'remove'")
    unknown = sorted(set(changes) - CHANGE_KEYS)
    if unknown:
        raise PaintError(f"changes has unknown field(s): {', '.join(unknown)}")
    new_layers = changes.get("layers", [])
    new_ops = changes.get("ops", [])
    updates = changes.get("update", {})
    removals = changes.get("remove", [])
    layer_updates = changes.get("update_layers", {})
    layer_removals = changes.get("remove_layers", [])
    if not isinstance(layer_updates, dict):
        raise PaintError("'update_layers' must be an object mapping layer ids to fields")
    if not isinstance(layer_removals, list) or not all(isinstance(item, str) for item in layer_removals):
        raise PaintError("'remove_layers' must be a list of layer ids")
    if not isinstance(new_layers, list) or not isinstance(new_ops, list):
        raise PaintError("'layers' and 'ops' must be lists")
    if not isinstance(updates, dict):
        raise PaintError("'update' must be an object mapping op ids to fields")
    if not isinstance(removals, list) or not all(isinstance(item, str) for item in removals):
        raise PaintError("'remove' must be a list of op ids")

    result = copy.deepcopy(doc)
    operations = result.setdefault("ops", [])
    layer_ids = {layer.get("id") for layer in result.get("layers", []) if isinstance(layer, dict)}
    op_ids = {op.get("id") for op in operations if isinstance(op, dict)}

    for op_id in removals:
        del operations[_op_index(operations, op_id, "remove")]
        op_ids.discard(op_id)
    for op_id, fields in updates.items():
        index = _op_index(operations, op_id, "update")
        if not isinstance(fields, dict):
            raise PaintError(f"update {op_id!r}: fields must be an object")
        if "id" in fields and fields["id"] != op_id:
            raise PaintError(f"update {op_id!r}: an op's id cannot be changed")
        operations[index] = {**operations[index], **fields}
    if "canvas" in changes:
        canvas_fields = changes["canvas"]
        if not isinstance(canvas_fields, dict):
            raise PaintError("'canvas' must be an object with width, height, or background")
        unknown_canvas = sorted(set(canvas_fields) - {"width", "height", "background"})
        if unknown_canvas:
            raise PaintError(f"canvas has unknown field(s): {', '.join(unknown_canvas)}")
        result["canvas"] = {**result.get("canvas", {}), **canvas_fields}
    layers = result.setdefault("layers", [])
    for layer_id, fields in layer_updates.items():
        index = _layer_index(layers, layer_id, "update_layers")
        if not isinstance(fields, dict):
            raise PaintError(f"update_layers {layer_id!r}: fields must be an object")
        if "id" in fields and fields["id"] != layer_id:
            raise PaintError(f"update_layers {layer_id!r}: a layer's id cannot be changed")
        layers[index] = {**layers[index], **fields}
    for layer_id in layer_removals:
        index = _layer_index(layers, layer_id, "remove_layers")
        still_used = [op for op in operations if isinstance(op, dict) and op.get("layer") == layer_id]
        if still_used:
            raise PaintError(
                f"remove_layers {layer_id!r}: the layer still has {len(still_used)} op(s); "
                "remove those ops first"
            )
        del layers[index]
        layer_ids.discard(layer_id)
    for layer in new_layers:
        if isinstance(layer, dict) and "id" not in layer:
            layer = {"id": _next_id("l", layer_ids), **layer}
        layers.append(layer)
    for op in new_ops:
        if isinstance(op, dict) and "id" not in op:
            op = {"id": _next_id("o", op_ids), **op}
        elif isinstance(op, dict):
            if op["id"] in op_ids:
                raise PaintError(
                    f"duplicate id {op['id']!r}: to change that op use 'update', or 'remove' it first"
                )
            op_ids.add(op["id"])
        operations.append(op)
    _raise_if_invalid(result, base)
    return result


def load(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PaintError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PaintError(f"not valid JSON: {path}: {exc}") from exc


def save(doc: dict, path: Path, force: bool = False) -> None:
    path = Path(path)
    if path.exists() and not force:
        raise PaintError(f"{path} already exists; use --force to replace it")
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


IMAGE_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}


def save_image(image: Image.Image, path: Path, force: bool = False) -> None:
    path = Path(path)
    fmt = IMAGE_FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise PaintError(f"output must end in one of: {', '.join(IMAGE_FORMATS)}")
    if path.exists() and not force:
        raise PaintError(f"{path} already exists; use --force to replace it")
    if fmt == "JPEG":
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.getchannel("A"))
        flat.save(path, fmt, quality=95)
    else:
        image.save(path, fmt)
