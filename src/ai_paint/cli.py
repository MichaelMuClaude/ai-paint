import argparse
import json
import sys
from pathlib import Path

from ai_paint import __version__, document, ops
from ai_paint.errors import PaintError


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _same_file(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def _new(args) -> int:
    background = None if args.background == "none" else args.background
    try:
        doc = document.new_document(args.width, args.height, background, args.layer)
        document.save(doc, Path(args.output), force=args.force)
    except PaintError as exc:
        return _fail(str(exc))
    print(json.dumps({"file": Path(args.output).name, "width": args.width, "height": args.height}, indent=2))
    return 0


def _info(args) -> int:
    try:
        doc = document.load(Path(args.document))
    except PaintError as exc:
        return _fail(str(exc))
    problems = document.validate_document(doc)
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
    problems = document.validate_document(doc)
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
        result = document.apply_changes(original, changes)
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
    try:
        doc = document.load(source)
        image = document.render(doc)
        document.save_image(image, output, force=args.force)
    except PaintError as exc:
        return _fail(str(exc))
    print(json.dumps({"input": source.name, "output": output.name, "width": image.width, "height": image.height}, indent=2))
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
    new.add_argument("--width", type=int, required=True)
    new.add_argument("--height", type=int, required=True)
    new.add_argument("--background", default="#ffffff", help="Colour, or 'none' for a transparent canvas")
    new.add_argument("--layer", default="base", help="Name of the first layer")
    new.add_argument("--force", action="store_true", help="Replace the file if it exists")
    new.set_defaults(func=_new)

    info = sub.add_parser("info", help="Show a document's canvas, layers, and validity as JSON")
    info.add_argument("document")
    info.set_defaults(func=_info)

    catalogue = sub.add_parser("ops", help="List every operation and its parameters as JSON")
    catalogue.set_defaults(func=_ops)

    validate = sub.add_parser("validate", help="Check a document without drawing anything")
    validate.add_argument("document")
    validate.set_defaults(func=_validate)

    apply = sub.add_parser("apply", help="Add layers and operations, and write a new document")
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
    render.set_defaults(func=_render)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
