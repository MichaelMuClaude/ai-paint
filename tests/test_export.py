import json
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from ai_paint import document, svgrender
from ai_paint.export import compile_document

needs_rsvg = pytest.mark.skipif(not svgrender.available(), reason="librsvg is not installed")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(*args):
    return subprocess.run([sys.executable, "-m", "ai_paint.cli", *args], capture_output=True, text=True)


def _doc(changes, width=120, height=100, background="#ffffff", base=None):
    return document.apply_changes(document.new_document(width, height, background), changes, base)


def _difference(doc, base=None):
    """Mean absolute difference (0 to 255) between ai-paint's render and the exported SVG drawn by librsvg."""
    native = np.asarray(document.render(doc, base)).astype(int)
    svg, _ = compile_document(doc, base)
    exported = np.asarray(svgrender.render_svg(svg, native.shape[1], native.shape[0])).astype(int)
    return np.abs(native - exported).mean()


CASES = {
    "rect and ellipse": {"ops": [
        {"op": "rect", "layer": "l1", "box": [10, 10, 50, 40], "fill": "#ff0000", "outline": "#000000", "width": 3},
        {"op": "ellipse", "layer": "l1", "box": [60, 30, 50, 50], "fill": "#0000ff80"}]},
    "polygon and line": {"ops": [
        {"op": "polygon", "layer": "l1", "points": [[10, 90], [60, 10], [110, 90]], "fill": "#00aa00",
         "outline": "#004400", "width": 2},
        {"op": "line", "layer": "l1", "points": [[5, 50], [115, 55]], "colour": "#000000", "width": 4}]},
    "path and spline": {"ops": [
        {"op": "path", "layer": "l1", "d": "M 10 80 C 10 10 110 10 110 80 Z", "fill": "#ffaa00"},
        {"op": "spline", "layer": "l1", "points": [[10, 90], [60, 60], [110, 90]], "outline": "#333333",
         "width": 3}]},
    "strokes": {"ops": [
        {"op": "stroke", "layer": "l1", "points": [[10, 20], [110, 20]], "size": 8, "colour": "#000000"},
        {"op": "stroke", "layer": "l1", "points": [[10, 60], [110, 60]], "size": 16, "size_end": 4,
         "colour": "#aa0000"},
        {"op": "stroke", "layer": "l1", "points": [[10, 85], [110, 85]], "size": 10, "taper": 0.4,
         "colour": "#0000aa"}]},
    "gradients and screentone": {"ops": [
        {"op": "rect", "layer": "l1", "box": [0, 0, 60, 100],
         "fill": {"type": "linear", "from": [0, 0], "to": [0, 100], "stops": [[0, "#ff0000"], [1, "#0000ff"]]}},
        {"op": "ellipse", "layer": "l1", "box": [60, 10, 60, 60],
         "fill": {"type": "radial", "centre": [90, 40], "radius": 30, "stops": [[0, "#ffffff"], [1, "#008800"]]}},
        {"op": "rect", "layer": "l1", "box": [60, 70, 60, 30],
         "fill": {"type": "screen", "density": 0.3, "cell": 6, "angle": 45}}]},
    "erase": {"ops": [
        {"op": "rect", "layer": "l1", "box": [0, 0, 120, 100], "fill": "#ff0000"},
        {"op": "erase", "layer": "l1", "box": [30, 20, 60, 60], "shape": "ellipse"},
        {"op": "rect", "layer": "l1", "box": [50, 40, 20, 20], "fill": "#0000ff"}]},
    "layer opacity, blur and outline": {
        "layers": [{"id": "glow", "blur": 4, "opacity": 0.6}, {"id": "ink", "outline": {"colour": "#000000",
                                                                                      "width": 2}}],
        "ops": [{"op": "ellipse", "layer": "glow", "box": [20, 20, 40, 40], "fill": "#ffcc00"},
                {"op": "ellipse", "layer": "ink", "box": [60, 30, 40, 40], "fill": "#ff8888"}]},
    "svg op": {"ops": [
        {"op": "svg", "layer": "l1", "box": [10, 10, 100, 80],
         "svg": '<use href="#lib-heart" transform="translate(50 40) scale(2)" color="#ff4d6d"/>'}]},
    "limb": {"ops": [
        {"op": "limb", "layer": "l1", "joints": [[10, 10], [60, 50], [110, 90]], "start_size": 24,
         "end_size": 10, "fill": "#e8a86e", "outline": "#9a6a46", "width": 2}]},
}


@needs_rsvg
@pytest.mark.parametrize("name", list(CASES))
def test_exported_svg_matches_the_native_render(name):
    assert _difference(_doc(CASES[name])) < 3.0


@needs_rsvg
def test_text_and_balloons_export_close_to_the_native_render():
    doc = _doc({"ops": [
        {"op": "text", "layer": "l1", "text": "Hi\nthere", "point": [60, 30], "size": 18, "font": FONT,
         "align": "center", "valign": "middle", "colour": "#000000"},
        {"op": "balloon", "layer": "l1", "text": "Go!", "centre": [60, 75], "size": 14, "font": FONT,
         "tail": [110, 95]}]}, height=110)
    assert _difference(doc) < 6.0  # text rasterisers differ slightly in hinting


@needs_rsvg
def test_place_is_embedded_and_matches(tmp_path):
    Image.new("RGBA", (30, 20), (0, 120, 255, 255)).save(tmp_path / "pic.png")
    doc = _doc({"ops": [{"op": "place", "layer": "l1", "image": "pic.png", "point": [10, 10], "width": 60}]},
               base=tmp_path)
    assert _difference(doc, tmp_path) < 2.0


def test_flood_fill_layers_become_pictures_and_are_reported():
    doc = _doc({"ops": [
        {"op": "rect", "layer": "l1", "box": [10, 10, 50, 50], "outline": "#000000", "width": 2},
        {"op": "fill", "layer": "l1", "point": [30, 30], "colour": "#ff0000"}]})
    svg, report = compile_document(doc)
    assert report["layers_as_pictures"] == ["l1"]
    assert "data:image/png;base64," in svg


def test_export_has_inkscape_layers_and_hidden_layers_stay_hidden():
    doc = _doc({"layers": [{"id": "secret", "visible": False}],
                "ops": [{"op": "rect", "layer": "secret", "box": [0, 0, 5, 5], "fill": "#ff0000"}]})
    svg, _ = compile_document(doc)
    root = ET.fromstring(svg)
    layers = [g for g in root.iter("{http://www.w3.org/2000/svg}g")
              if g.get("{http://www.inkscape.org/namespaces/inkscape}groupmode") == "layer"]
    assert [g.get("id") for g in layers] == ["layer-l1", "layer-secret"]
    assert layers[1].get("style") == "display:none"


@needs_rsvg
def test_two_svg_ops_with_the_same_ids_do_not_clash():
    first = '<defs><rect id="shape" width="20" height="20" fill="#ff0000"/></defs><use href="#shape"/>'
    second = '<defs><rect id="shape" width="20" height="20" fill="#0000ff"/></defs><use href="#shape"/>'
    doc = _doc({"ops": [{"op": "svg", "layer": "l1", "box": [0, 0, 20, 20], "svg": first},
                        {"op": "svg", "layer": "l1", "box": [50, 0, 20, 20], "svg": second}]})
    svg, _ = compile_document(doc)
    picture = svgrender.render_svg(svg, 120, 100)
    assert picture.getpixel((10, 10))[:3] == (255, 0, 0)
    assert picture.getpixel((60, 10))[:3] == (0, 0, 255)


def test_export_command_writes_svg_and_protects_files(tmp_path):
    doc_path = tmp_path / "pic.json"
    document.save(_doc(CASES["rect and ellipse"]), doc_path)
    out = tmp_path / "pic.svg"
    result = run("export", str(doc_path), "-o", str(out))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["layers_as_pictures"] == []
    ET.fromstring(out.read_text())  # well-formed
    again = run("export", str(doc_path), "-o", str(out))
    assert again.returncode == 1 and "already exists" in again.stderr
    wrong = run("export", str(doc_path), "-o", str(tmp_path / "pic.png"))
    assert wrong.returncode == 1 and "must end in .svg" in wrong.stderr
