import json
import subprocess
import sys

import pytest
from PIL import Image

from ai_paint import document, svgrender
from ai_paint.errors import PaintError

needs_rsvg = pytest.mark.skipif(not svgrender.available(), reason="librsvg is not installed")
WHITE = (255, 255, 255, 255)


def run(*args):
    return subprocess.run([sys.executable, "-m", "ai_paint.cli", *args], capture_output=True, text=True)


def _doc_with(svg_markup, width=120, height=120):
    doc = document.new_document(width, height, "#ffffff")
    return document.apply_changes(doc, {"ops": [{"id": "art", "op": "svg", "layer": "l1", "svg": svg_markup}]})


def test_every_part_loads_with_a_description():
    parts = svgrender.library()
    assert len(parts) >= 13
    for name, part in parts.items():
        assert name.startswith("lib-")
        assert part["description"]
        assert name in part["ids"]


def test_expand_library_adds_only_the_parts_used():
    expanded = svgrender.expand_library('<use href="#lib-heart"/>')
    assert 'id="lib-heart"' in expanded
    assert "lib-eye-anime" not in expanded


def test_unknown_part_is_explained():
    with pytest.raises(PaintError, match="not a library part; available parts"):
        _doc_with('<use href="#lib-dragon"/>')


@needs_rsvg
def test_part_takes_its_colour_from_the_use_element():
    doc = _doc_with('<use href="#lib-heart" transform="translate(60 60) scale(2)" color="#00aa00"/>')
    red, green, blue, _ = document.render(doc).getpixel((60, 58))
    assert green > 120 and red < 60 and blue < 60


@needs_rsvg
def test_mirrored_eye_draws_on_both_sides():
    doc = _doc_with('<use href="#lib-eye-anime" transform="translate(35 60)" color="#3f7fe0"/>'
                    '<use href="#lib-eye-anime" transform="translate(85 60) scale(-1 1)" color="#3f7fe0"/>')
    img = document.render(doc)
    assert img.getpixel((38, 62)) != WHITE
    assert img.getpixel((82, 62)) != WHITE


@needs_rsvg
def test_svg_set_changes_one_element():
    doc = _doc_with('<circle id="ball" cx="60" cy="60" r="30" fill="#ff0000"/>')
    changed = document.apply_changes(doc, {"svg_set": {"art": {"ball": {"fill": "#0000ff"}}}})
    assert document.render(changed).getpixel((60, 60)) == (0, 0, 255, 255)
    assert document.render(doc).getpixel((60, 60)) == (255, 0, 0, 255)  # the input is unchanged


@needs_rsvg
def test_svg_remove_and_replace():
    doc = _doc_with('<rect id="a" x="0" y="0" width="60" height="120" fill="#ff0000"/>'
                    '<rect id="b" x="60" y="0" width="60" height="120" fill="#00ff00"/>')
    removed = document.apply_changes(doc, {"svg_remove": {"art": ["a"]}})
    assert document.render(removed).getpixel((30, 60)) == WHITE
    replaced = document.apply_changes(doc, {"svg_replace": {"art": {
        "b": '<circle id="c" cx="90" cy="60" r="20" fill="#0000ff"/>'}}})
    img = document.render(replaced)
    assert img.getpixel((90, 60)) == (0, 0, 255, 255)
    assert img.getpixel((65, 5)) == WHITE


def test_svg_edits_report_missing_ids_and_file_based_ops(tmp_path):
    doc = _doc_with('<rect id="a" width="10" height="10"/>')
    with pytest.raises(PaintError, match="no element with id 'zz'"):
        document.apply_changes(doc, {"svg_set": {"art": {"zz": {"fill": "red"}}}})
    with pytest.raises(PaintError, match="cannot be changed"):
        document.apply_changes(doc, {"svg_set": {"art": {"a": {"id": "b"}}}})
    (tmp_path / "x.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    file_doc = document.apply_changes(document.new_document(10, 10),
                                      {"ops": [{"id": "f", "op": "svg", "layer": "l1", "file": "x.svg"}]}, tmp_path)
    with pytest.raises(PaintError, match="edit that file directly"):
        document.apply_changes(file_doc, {"svg_set": {"f": {"a": {"fill": "red"}}}}, tmp_path)


def test_svg_edits_cannot_sneak_in_unsafe_markup():
    doc = _doc_with('<g id="slot"/>')
    with pytest.raises(PaintError, match="<script> is not allowed"):
        document.apply_changes(doc, {"svg_replace": {"art": {"slot": "<script>alert(1)</script>"}}})


def test_elements_lists_ids_and_tags():
    rows = svgrender.elements('<g id="face"><circle id="eye" fill="#000"/></g><rect/>')
    assert [(row["id"], row["tag"]) for row in rows] == [("face", "g"), ("eye", "circle")]
    assert rows[1]["fill"] == "#000"


@needs_rsvg
def test_parts_command_lists_and_previews(tmp_path):
    listing = json.loads(run("parts").stdout)
    assert any(item["part"] == "lib-eye-anime" for item in listing)
    out = tmp_path / "eye.png"
    result = run("parts", "--preview", "lib-eye-anime", "-o", str(out))
    assert result.returncode == 0, result.stderr
    with Image.open(out) as img:
        assert img.size == (200, 140)


def test_elements_command(tmp_path):
    path = tmp_path / "doc.json"
    document.save(_doc_with('<circle id="dot" r="3"/>'), path)
    rows = json.loads(run("elements", str(path), "art").stdout)
    assert rows == [{"id": "dot", "tag": "circle"}]
    missing = run("elements", str(path), "nope")
    assert missing.returncode == 1 and "no svg op" in missing.stderr


def test_new_parts_are_present():
    parts = svgrender.library()
    for name in ("lib-hair-bob", "lib-hair-ponytail", "lib-hand-open", "lib-hand-fist",
                "lib-speed-lines", "lib-impact-burst", "lib-thought-bubble"):
        assert name in parts, name
