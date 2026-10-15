import pytest
from PIL import Image

from ai_paint import document, ops
from ai_paint.errors import PaintError
from ai_paint.svgrender import check_svg, render_svg

WHITE = (255, 255, 255, 255)
RED = (255, 0, 0, 255)


def _render(*op_list, width=100, height=100, background="#ffffff", base=None):
    doc = document.new_document(width, height, background)
    doc = document.apply_changes(doc, {"ops": list(op_list)}, base)
    return document.render(doc, base)


def test_render_svg_draws_shapes_with_correct_colour_and_transparency():
    img = render_svg('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
                     '<rect x="0" y="0" width="10" height="20" fill="#ff0000"/></svg>', 20, 20)
    assert img.getpixel((5, 10)) == RED
    assert img.getpixel((15, 10))[3] == 0


def test_svg_fragment_uses_box_pixels_and_lands_in_the_box():
    img = _render({"op": "svg", "layer": "l1", "box": [50, 50, 40, 40],
                   "svg": '<circle cx="20" cy="20" r="15" fill="#ff0000"/>'})
    assert img.getpixel((70, 70)) == RED  # the circle centre, in page pixels
    assert img.getpixel((20, 20)) == WHITE  # outside the box nothing is drawn


def test_svg_transforms_clip_paths_and_use_work():
    markup = (
        '<defs><clipPath id="c"><rect x="0" y="0" width="50" height="100"/></clipPath>'
        '<rect id="bar" x="0" y="40" width="100" height="20" fill="#0000ff"/></defs>'
        '<g clip-path="url(#c)"><rect x="0" y="0" width="100" height="100" fill="#ff0000"/></g>'
        '<use href="#bar" transform="translate(0 30)"/>'
    )
    img = _render({"op": "svg", "layer": "l1", "svg": markup})
    assert img.getpixel((25, 10)) == RED  # inside the clip
    assert img.getpixel((75, 10)) == WHITE  # clipped away
    assert img.getpixel((75, 80)) == (0, 0, 255, 255)  # the reused bar, moved down 30


def test_svg_whole_canvas_when_no_box():
    img = _render({"op": "svg", "layer": "l1", "svg": '<rect width="100" height="100" fill="#ff0000"/>'})
    assert img.getpixel((99, 99)) == RED


def test_svg_file_is_read_from_the_document_folder(tmp_path):
    (tmp_path / "dot.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="#ff0000"/></svg>')
    img = _render({"op": "svg", "layer": "l1", "file": "dot.svg", "box": [0, 0, 10, 10]}, base=tmp_path)
    assert img.getpixel((5, 5)) == RED


@pytest.mark.parametrize("markup, message", [
    ('<script>alert(1)</script>', "<script> is not allowed"),
    ('<rect width="5" height="5" onclick="x()"/>', "no event handlers"),
    ('<use href="http://example.com/a.svg#x"/>', "must point inside the same SVG"),
    ('<rect width="5" height="5" fill="url(http://example.com/x)"/>', "url\\(\\) must point inside"),
    ('<foreignObject><div/></foreignObject>', "<foreignObject> is not allowed"),
    ('<image href="#x"/>', "<image> is not allowed"),
    ('<rect width="5"', "not well-formed"),
])
def test_unsafe_or_broken_svg_is_refused(markup, message):
    with pytest.raises(PaintError, match=message):
        ops.normalise({"op": "svg", "layer": "l1", "svg": markup}, (100, 100))


def test_doctype_and_entities_are_refused():
    with pytest.raises(PaintError, match="DOCTYPE or ENTITY"):
        check_svg('<!DOCTYPE svg [<!ENTITY a "x">]><svg xmlns="http://www.w3.org/2000/svg"/>')


def test_svg_needs_exactly_one_source(tmp_path):
    (tmp_path / "a.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(PaintError, match="either svg"):
        ops.normalise({"op": "svg", "layer": "l1"}, (100, 100))
    with pytest.raises(PaintError, match="either svg"):
        ops.normalise({"op": "svg", "layer": "l1", "svg": "<g/>", "file": "a.svg"}, (100, 100), tmp_path)


def test_svg_opacity_and_layers_still_apply():
    img = _render({"op": "svg", "layer": "l1", "opacity": 0.5,
                   "svg": '<rect width="100" height="100" fill="#000000"/>'})
    assert abs(img.getpixel((50, 50))[0] - 128) <= 1
