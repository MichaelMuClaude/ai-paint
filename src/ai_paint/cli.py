import argparse
import json
import sys
from pathlib import Path

from ai_paint import __version__, document, ops
from ai_paint.errors import PaintError
from ai_paint.view import crop_and_zoom, draw_grid, parse_box


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _same_file(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def _folder(document_path) -> Path:
    """Relative picture and font paths in a document are read from the document's own folder."""
    return Path(document_path).resolve().parent


# Manga page sizes at 300 dpi. B5 is 182 x 257 mm and B6 (a tankobon volume) is 128 x 182 mm.
PRESETS = {
    "manga-b5": (2150, 3035, "B5 manga page, 182 x 257 mm at 300 dpi"),
    "manga-b6": (1512, 2150, "B6 tankobon page, 128 x 182 mm at 300 dpi"),
}


def _new(args) -> int:
    background = None if args.background == "none" else args.background
    width, height = args.width, args.height
    if args.preset:
        if width is not None or height is not None:
            return _fail("use either --preset or --width and --height, not both")
        width, height, _ = PRESETS[args.preset]
    if width is None or height is None:
        return _fail("give --width and --height, or a --preset")
    try:
        doc = document.new_document(width, height, background, args.layer)
        document.save(doc, Path(args.output), force=args.force)
    except PaintError as exc:
        return _fail(str(exc))
    print(json.dumps({"file": Path(args.output).name, "width": width, "height": height,
                      "preset": args.preset}, indent=2))
    return 0


def _info(args) -> int:
    try:
        doc = document.load(Path(args.document))
    except PaintError as exc:
        return _fail(str(exc))
    problems = document.validate_document(doc, _folder(args.document))
    layers = doc.get("layers", []) if isinstance(doc.get("layers"), list) else []
    operations = doc.get("ops", []) if isinstance(doc.get("ops"), list) else []
    summary = {
        "file": Path(args.document).name,
        "valid": not problems,
        "problems": problems,
        "canvas": doc.get("canvas"),
        "layers": [
            {
                "id": layer.get("id"),
                "name": layer.get("name", layer.get("id")),
                "opacity": layer.get("opacity", 1.0),
                "visible": layer.get("visible", True),
                "ops": sum(1 for op in operations if isinstance(op, dict) and op.get("layer") == layer.get("id")),
            }
            for layer in layers if isinstance(layer, dict)
        ],
        "ops": len(operations),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _describe(raw: dict) -> str:
    """A short, readable summary of an op's values, for the list command."""
    parts = []
    for key, value in raw.items():
        if key in ("op", "id", "layer"):
            continue
        text = json.dumps(value, ensure_ascii=False)
        if len(text) > 48:
            text = text[:45] + "..."
        parts.append(f"{key}={text}")
    return " ".join(parts)


def _list(args) -> int:
    try:
        doc = document.load(Path(args.document))
    except PaintError as exc:
        return _fail(str(exc))
    operations = doc.get("ops", []) if isinstance(doc.get("ops"), list) else []
    rows = [
        {"index": index, "id": op.get("id"), "layer": op.get("layer"), "op": op.get("op"),
         "values": _describe(op)}
        for index, op in enumerate(operations)
        if isinstance(op, dict) and (args.layer is None or op.get("layer") == args.layer)
    ]
    if args.text:
        for row in rows:
            print(f"{str(row['id']):<8} {str(row['layer']):<12} {str(row['op']):<8} {row['values']}")
    else:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def _measure(args) -> int:
    from ai_paint.params import MAX_TEXT
    from ai_paint.raster import text_size

    text = args.text.replace("\\n", "\n")  # a typed \n on the command line means a new line
    if not text.strip() or len(text) > MAX_TEXT:
        return _fail(f"text must be between 1 and {MAX_TEXT} characters")
    if not 4 <= args.size <= 500:
        return _fail("size must be a whole number from 4 to 500")
    font = None
    if args.font:
        font = str(Path(args.font).expanduser().resolve())
        if not font.lower().endswith((".ttf", ".otf")) or not Path(font).is_file():
            return _fail(f"font must be an existing .ttf or .otf file: {args.font}")
    try:
        width, height = text_size(text, args.size, font)
    except PaintError as exc:
        return _fail(str(exc))
    print(json.dumps({"width": width, "height": height, "size": args.size}, indent=2))
    return 0


def _trace(args) -> int:
    from ai_paint.trace import trace_to_changes

    source, output = Path(args.picture), Path(args.output)
    try:
        offset = tuple(float(part) for part in args.offset.split(",")) if args.offset else (0.0, 0.0)
        if len(offset) != 2:
            raise ValueError
    except ValueError:
        return _fail("offset must be two numbers x,y")
    try:
        changes, info = trace_to_changes(source, threshold=args.threshold, layer=args.layer,
                                         colour=args.colour, scale=args.scale, offset=offset)
        document.save(changes, output, force=args.force)
    except PaintError as exc:
        return _fail(str(exc))
    print(json.dumps({"picture": source.name, "changes": output.name, **info,
                      "note": "apply the changes to a canvas of canvas_width x canvas_height"}, indent=2))
    return 0


def _ops(args) -> int:
    catalogue = []
    for operation in ops.OPERATIONS.values():
        params = []
        for param in operation.params:
            entry = {"name": param.name, "type": param.kind, "summary": param.summary, "required": param.required}
            if param.default is not None:
                entry["default"] = param.default
            if param.minimum is not None:
                entry["minimum"] = param.minimum
            if param.maximum is not None:
                entry["maximum"] = param.maximum
            if param.choices:
                entry["choices"] = list(param.choices)
            if param.min_items or param.max_items:
                entry["items"] = [param.min_items, param.max_items]
            params.append(entry)
        catalogue.append({"op": operation.name, "summary": operation.summary, "params": params})
    print(json.dumps(catalogue, indent=2, ensure_ascii=False))
    return 0


def _validate(args) -> int:
    try:
        doc = document.load(Path(args.document))
    except PaintError as exc:
        return _fail(str(exc))
    problems = document.validate_document(doc, _folder(args.document))
    if problems:
        for problem in problems:
            print(f"invalid: {problem}", file=sys.stderr)
        return 1
    print(json.dumps({"valid": True, "layers": len(doc["layers"]), "ops": len(doc.get("ops", []))}, indent=2))
    return 0


def _apply(args) -> int:
    source, output = Path(args.document), Path(args.output)
    if _same_file(source, output):
        return _fail("the output must be a different file; the input document is never changed")
    try:
        if args.changes:
            changes = document.load(Path(args.changes))
        else:
            try:
                changes = json.loads(args.change)
            except json.JSONDecodeError as exc:
                raise PaintError(f"--change is not valid JSON: {exc}") from exc
        original = document.load(source)
        result = document.apply_changes(original, changes, _folder(source))
        document.save(result, output, force=args.force)
    except PaintError as exc:
        return _fail(str(exc))
    print(json.dumps({
        "input": {"file": source.name, "ops": len(original.get("ops", []))},
        "output": {"file": output.name, "ops": len(result["ops"])},
        "added": {
            "layers": len(result["layers"]) - len(original["layers"]),
            "ops": len(result["ops"]) - len(original.get("ops", [])),
        },
    }, indent=2))
    return 0


def _render(args) -> int:
    source, output = Path(args.document), Path(args.output)
    if _same_file(source, output):
        return _fail("the output must be a different file; the input document is never changed")
    view = {}
    try:
        doc = document.load(source)
        image = document.render(doc, _folder(source))
        box = parse_box(args.crop) if args.crop else None
        if box is not None or args.zoom != 1:
            image = crop_and_zoom(image, box, args.zoom)
            if box is not None:
                view["crop"] = list(box)
            view["zoom"] = args.zoom
        if args.grid:
            origin = (box[0], box[1]) if box is not None else (0, 0)
            image = draw_grid(image, args.grid, origin=origin, scale=args.zoom)
            view["grid"] = args.grid
        document.save_image(image, output, force=args.force)
    except PaintError as exc:
        return _fail(str(exc))
    result = {"input": source.name, "output": output.name, "width": image.width, "height": image.height}
    if view:
        result["view"] = view
        result["note"] = "grid and crop are for looking only; the document itself is unchanged"
    print(json.dumps(result, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ai-paint",
        description="Draw pictures from a JSON document of explicit operations that an AI agent can write and check",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="Create an empty document with one layer")
    new.add_argument("output", help="New document file (.json)")
    new.add_argument("--width", type=int)
    new.add_argument("--height", type=int)
    new.add_argument("--preset", choices=tuple(PRESETS),
                     help="A manga page size: " + "; ".join(f"{k} = {v[2]}" for k, v in PRESETS.items()))
    new.add_argument("--background", default="#ffffff", help="Colour, or 'none' for a transparent canvas")
    new.add_argument("--layer", default="base", help="Name of the first layer")
    new.add_argument("--force", action="store_true", help="Replace the file if it exists")
    new.set_defaults(func=_new)

    info = sub.add_parser("info", help="Show a document's canvas, layers, and validity as JSON")
    info.add_argument("document")
    info.set_defaults(func=_info)

    listing = sub.add_parser("list", help="List a document's ops with their ids, layers, and values")
    listing.add_argument("document")
    listing.add_argument("--layer", help="Only show ops on this layer id")
    listing.add_argument("--text", action="store_true", help="Print one line per op instead of JSON")
    listing.set_defaults(func=_list)

    measure = sub.add_parser("measure", help="Report how many pixels a line of text takes at a font size")
    measure.add_argument("--text", required=True, help="The text; use \\n for a new line")
    measure.add_argument("--size", type=int, required=True, help="Font size in pixels")
    measure.add_argument("--font", help="Optional .ttf or .otf font file")
    measure.set_defaults(func=_measure)

    trace = sub.add_parser("trace", help="Trace a picture's dark lines into path ops, as a changes file")
    trace.add_argument("picture", help="A PNG, JPEG or WebP picture with dark lines")
    trace.add_argument("-o", "--output", required=True, help="Changes file to write (.json)")
    trace.add_argument("--threshold", type=int, default=30,
                       help="Pixels darker than this (0 to 255) count as lines. Default 30.")
    trace.add_argument("--layer", default="lines", help="Layer id for the traced lines")
    trace.add_argument("--colour", default="#000000", help="Colour of the traced lines")
    trace.add_argument("--scale", type=float, default=1.0, help="Size factor for the traced lines")
    trace.add_argument("--offset", help="Move the lines by x,y pixels, for example 120,80")
    trace.add_argument("--force", action="store_true", help="Replace the output file if it exists")
    trace.set_defaults(func=_trace)

    catalogue = sub.add_parser("ops", help="List every operation and its parameters as JSON")
    catalogue.set_defaults(func=_ops)

    validate = sub.add_parser("validate", help="Check a document without drawing anything")
    validate.add_argument("document")
    validate.set_defaults(func=_validate)

    apply = sub.add_parser("apply", help="Add, change, or remove layers and operations, and write a new document")
    apply.add_argument("document", help="Input document; it is never changed")
    apply.add_argument("-o", "--output", required=True, help="New document file (.json)")
    source = apply.add_mutually_exclusive_group(required=True)
    source.add_argument("--changes", help="JSON file with optional 'layers' and 'ops' lists")
    source.add_argument("--change", help="The same JSON as a string")
    apply.add_argument("--force", action="store_true", help="Replace the output file if it exists")
    apply.set_defaults(func=_apply)

    render = sub.add_parser("render", help="Draw the document and write a picture")
    render.add_argument("document")
    render.add_argument("-o", "--output", required=True, help="Output picture (.png, .jpg, .webp)")
    render.add_argument("--force", action="store_true", help="Replace the output file if it exists")
    render.add_argument("--grid", type=int, metavar="STEP",
                        help="Draw a labelled coordinate grid every STEP pixels (for looking only)")
    render.add_argument("--crop", metavar="X,Y,W,H",
                        help="Only write this part of the picture (for looking only)")
    render.add_argument("--zoom", type=int, default=1,
                        help="Enlarge the output by this whole number, 1 to 8, with hard pixels")
    render.set_defaults(func=_render)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
