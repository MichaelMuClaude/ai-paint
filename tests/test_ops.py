import pytest
from PIL import Image

from ai_paint import document, ops, raster
from ai_paint.errors import PaintError
from ai_paint.params import parse_colour

WHITE = (255, 255, 255, 255)
RED = (255, 0, 0, 255)
BLACK = (0, 0, 0, 255)


def _render(*op_list, width=100, height=100, background="#ffffff"):
    doc = document.new_document(width, height, background)
    doc = document.apply_changes(doc, {"ops": list(op_list)})
    return document.render(doc)


def test_registry_has_the_six_first_ops():
    assert set(ops.OPERATIONS) == {"stroke", "line", "rect", "ellipse", "polygon", "fill"}
    for operation in ops.OPERATIONS.values():
        assert operation.summary
        assert operation.params


def test_colour_parsing_accepts_names_and_alpha():
    assert parse_colour("red") == (255, 0, 0, 255)
    assert parse_colour("#00ff00") == (0, 255, 0, 255)
    assert parse_colour("#ff000080") == (255, 0, 0, 128)
    with pytest.raises(PaintError, match="not recognised"):
        parse_colour("notacolour")


def test_filled_rect_covers_its_box_only():
    img = _render({"op": "rect", "layer": "l1", "box": [10, 10, 20, 20], "fill": "#ff0000"})
    assert img.getpixel((10, 10)) == RED
    assert img.getpixel((29, 29)) == RED
    assert img.getpixel((30, 30)) == WHITE
    assert img.getpixel((9, 10)) == WHITE


def test_outline_rect_leaves_the_middle_empty():
    img = _render({"op": "rect", "layer": "l1", "box": [10, 10, 40, 40], "outline": "#000000", "width": 2})
    assert img.getpixel((10, 10)) == BLACK
    assert img.getpixel((30, 30)) == WHITE


def test_ellipse_centre_is_filled_and_corner_is_not():
    img = _render({"op": "ellipse", "layer": "l1", "box": [10, 10, 80, 80], "fill": "#ff0000"})
    assert img.getpixel((50, 50)) == RED
    assert img.getpixel((12, 12)) == WHITE


def test_polygon_fills_a_triangle():
    img = _render({"op": "polygon", "layer": "l1", "points": [[10, 90], [90, 90], [50, 10]], "fill": "#ff0000"})
    assert img.getpixel((50, 80)) == RED
    assert img.getpixel((12, 12)) == WHITE


def test_line_draws_a_thick_hard_edged_line():
    img = _render({"op": "line", "layer": "l1", "points": [[10, 50], [90, 50]], "colour": "#000000", "width": 5})
    assert img.getpixel((50, 50)) == BLACK
    assert img.getpixel((50, 40)) == WHITE


def test_hard_stroke_is_solid_along_its_path():
    img = _render({"op": "stroke", "layer": "l1", "points": [[10, 50], [90, 50]], "size": 6, "colour": "#000000"})
    assert img.getpixel((50, 50)) == BLACK
    assert img.getpixel((50, 46)) == WHITE  # radius is 3, so 4 pixels out is clear


def test_single_point_stroke_makes_one_dot():
    img = _render({"op": "stroke", "layer": "l1", "points": [[50, 50]], "size": 10, "colour": "#000000"})
    assert img.getpixel((50, 50)) == BLACK
    assert img.getpixel((80, 80)) == WHITE


def test_soft_brush_fades_towards_the_rim():
    # The point is a pixel centre, so the centre pixel sits near the peak of the falloff.
    img = _render({"op": "stroke", "layer": "l1", "points": [[50.5, 50.5]], "size": 20,
                   "colour": "#000000", "brush": "soft"})
    centre = img.getpixel((50, 50))[0]
    near_rim = img.getpixel((58, 50))[0]
    assert centre < 30
    assert centre < near_rim < 255


def test_stroke_is_not_darker_where_its_own_dabs_overlap():
    # Overlapping dabs use `lighter`, so a semi-transparent stroke has one strength everywhere along it.
    img = _render({"op": "stroke", "layer": "l1", "points": [[10, 50], [90, 50]], "size": 10,
                   "colour": "#00000080"})
    along = img.getpixel((30, 50))
    assert along == img.getpixel((70, 50))


def test_fill_stays_inside_a_closed_outline():
    img = _render(
        {"id": "edge", "op": "rect", "layer": "l1", "box": [10, 10, 40, 40], "outline": "#000000", "width": 2},
        {"op": "fill", "layer": "l1", "point": [30, 30], "colour": "#00ff00"},
    )
    assert img.getpixel((30, 30)) == (0, 255, 0, 255)
    assert img.getpixel((80, 80)) == WHITE


def test_fill_tolerance_decides_whether_similar_colours_join():
    # Left half is #101010, right half is #121212: a difference of 2 per channel.
    base = [
        {"op": "rect", "layer": "l1", "box": [0, 0, 10, 20], "fill": "#101010"},
        {"op": "rect", "layer": "l1", "box": [10, 0, 10, 20], "fill": "#121212"},
    ]
    strict = _render(*base, {"op": "fill", "layer": "l1", "point": [5, 5], "colour": "#ff0000", "tolerance": 0},
                     width=20, height=20)
    assert strict.getpixel((5, 5)) == RED
    assert strict.getpixel((15, 5)) == (0x12, 0x12, 0x12, 255)

    # The tolerance is the total difference over R, G, B and A: 2 + 2 + 2 = 6.
    almost = _render(*base, {"op": "fill", "layer": "l1", "point": [5, 5], "colour": "#ff0000", "tolerance": 5},
                     width=20, height=20)
    assert almost.getpixel((15, 5)) == (0x12, 0x12, 0x12, 255)

    loose = _render(*base, {"op": "fill", "layer": "l1", "point": [5, 5], "colour": "#ff0000", "tolerance": 6},
                    width=20, height=20)
    assert loose.getpixel((15, 5)) == RED


def test_fill_seed_outside_canvas_is_an_error():
    with pytest.raises(PaintError, match="outside the 100x100 canvas"):
        _render({"op": "fill", "layer": "l1", "point": [500, 5], "colour": "#ff0000"})


@pytest.mark.parametrize("raw, message", [
    ({"op": "circle", "layer": "l1"}, "op must be one of"),
    ({"op": "rect", "layer": "l1", "box": [1, 1, 5, 5]}, "give a fill colour"),
    ({"op": "rect", "layer": "l1", "box": [1, 1, 0, 5], "fill": "red"}, "width must be a number from 1"),
    ({"op": "stroke", "layer": "l1", "points": [[1, 1]], "size": 0, "colour": "red"}, "size must be at least 1"),
    ({"op": "stroke", "layer": "l1", "points": [[1, 1]], "size": 4, "colour": "nope"}, "colour is not recognised"),
    ({"op": "stroke", "layer": "l1", "points": [], "size": 4, "colour": "red"}, "needs 1 to"),
    ({"op": "stroke", "layer": "l1", "points": [[1, 1]], "size": 4, "colour": "red", "brush": "spray"},
     "brush must be one of"),
    ({"op": "line", "layer": "l1", "points": [[1, 1]], "colour": "red"}, "needs 2 to"),
    ({"op": "polygon", "layer": "l1", "points": [[1, 1], [2, 2]], "fill": "red"}, "needs 3 to"),
    ({"op": "fill", "layer": "l1", "point": [1, 1], "colour": "red", "tolerance": 300}, "tolerance must be at most"),
    ({"op": "stroke", "layer": "l1", "points": [[1, 1]], "size": 4, "colour": "red", "pressure": 1},
     "unknown field"),
    ({"op": "stroke", "layer": "l1", "points": [[1, 1]], "size": 4.5, "colour": "red", "opacity": 2},
     "opacity must be at most"),
    ({"op": "stroke", "points": [[1, 1]], "size": 4, "colour": "red"}, "needs a layer id"),
    ({"op": "stroke", "layer": "l1", "points": [[1, 1]], "size": True, "colour": "red"}, "size must be a number"),
])
def test_invalid_operations_are_rejected_with_a_reason(raw, message):
    with pytest.raises(PaintError, match=message):
        ops.normalise(raw, (100, 100))


def test_render_skips_hidden_layers_and_applies_opacity():
    doc = document.new_document(20, 20, "#ffffff")
    doc = document.apply_changes(doc, {
        "layers": [{"id": "top", "name": "top", "opacity": 0.5}, {"id": "hidden", "visible": False}],
        "ops": [
            {"op": "rect", "layer": "l1", "box": [0, 0, 20, 20], "fill": "#000000"},
            {"op": "rect", "layer": "hidden", "box": [0, 0, 20, 20], "fill": "#ff0000"},
            {"op": "rect", "layer": "top", "box": [0, 0, 10, 20], "fill": "#ff0000"},
        ],
    })
    img = document.render(doc)
    assert img.getpixel((15, 5)) == BLACK  # the hidden red layer is not drawn
    left = img.getpixel((5, 5))
    assert left[0] == 128 and left[1] == 0  # half-strength red over black


def test_later_ops_are_drawn_on_top():
    img = _render(
        {"op": "rect", "layer": "l1", "box": [0, 0, 50, 50], "fill": "#ff0000"},
        {"op": "rect", "layer": "l1", "box": [0, 0, 50, 50], "fill": "#0000ff"},
    )
    assert img.getpixel((10, 10)) == (0, 0, 255, 255)


def test_transparent_background_is_transparent():
    img = _render({"op": "rect", "layer": "l1", "box": [0, 0, 10, 10], "fill": "#ff0000"}, background=None)
    assert img.getpixel((50, 50))[3] == 0


def test_brush_mask_is_cached_and_not_modified():
    first = raster.brush_mask(5.0, 1.0)
    assert raster.brush_mask(5.0, 1.0) is first
    assert first.getpixel((5, 5)) == 255


def test_stroke_with_too_many_dabs_is_refused(monkeypatch):
    monkeypatch.setattr(raster, "MAX_DABS", 100)
    with pytest.raises(PaintError, match="needs .* dabs, the limit is 100"):
        raster.draw_stroke(Image.new("RGBA", (200, 200)), [[0, 0], [150, 150]], 2.0, 1.0, 0.2, BLACK, 1.0)


def test_curved_edges_are_anti_aliased():
    img = _render({"op": "ellipse", "layer": "l1", "box": [10.4, 10.4, 30, 30], "fill": "#000000"}, width=60, height=60)
    partial = [img.getpixel((x, y))[0] for x in range(60) for y in range(60)]
    assert any(0 < value < 255 for value in partial)


def test_box_covers_exactly_its_width_in_pixels():
    img = _render({"op": "rect", "layer": "l1", "box": [10, 10, 20, 20], "fill": "#000000"})
    assert img.getpixel((29, 10)) == BLACK
    assert img.getpixel((30, 10)) == WHITE
