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


def test_registry_has_the_drawing_operations():
    assert set(ops.OPERATIONS) == {"stroke", "line", "rect", "ellipse", "polygon", "fill", "text", "erase", "place", "path"}
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


def test_text_is_drawn_inside_its_box_and_nowhere_else():
    img = _render({"op": "text", "layer": "l1", "text": "Hi", "point": [10, 10], "size": 20, "colour": "#000000"},
                  width=120, height=60)
    inked = [(x, y) for x in range(120) for y in range(60) if img.getpixel((x, y))[0] < 128]
    assert inked
    assert all(10 <= x < 60 and 10 <= y < 40 for x, y in inked)


def test_multiline_text_is_taller_than_one_line():
    one = _render({"op": "text", "layer": "l1", "text": "Hi", "point": [5, 5], "size": 16, "colour": "#000000"},
                  width=100, height=100)
    two = _render({"op": "text", "layer": "l1", "text": "Hi\nHi", "point": [5, 5], "size": 16, "colour": "#000000"},
                  width=100, height=100)

    def bottom(img):
        return max(y for x in range(100) for y in range(100) if img.getpixel((x, y))[0] < 128)

    assert bottom(two) > bottom(one) + 10


def test_text_partly_off_the_canvas_is_clipped_not_an_error():
    img = _render({"op": "text", "layer": "l1", "text": "Edge", "point": [90, 90], "size": 30, "colour": "#000000"})
    assert img.size == (100, 100)


def test_text_font_file_must_exist_and_be_a_font():
    with pytest.raises(PaintError, match="file does not exist"):
        ops.normalise({"op": "text", "layer": "l1", "text": "x", "point": [0, 0], "size": 10,
                       "colour": "red", "font": "/nonexistent/font.ttf"}, (100, 100))
    with pytest.raises(PaintError, match=r"must be a \.ttf or \.otf"):
        ops.normalise({"op": "text", "layer": "l1", "text": "x", "point": [0, 0], "size": 10,
                       "colour": "red", "font": "photo.png"}, (100, 100))


def test_text_must_not_be_empty_or_too_long():
    with pytest.raises(PaintError, match="must be text that is not empty"):
        ops.normalise({"op": "text", "layer": "l1", "text": "   ", "point": [0, 0], "size": 10, "colour": "red"},
                      (100, 100))
    with pytest.raises(PaintError, match="at most 500 characters"):
        ops.normalise({"op": "text", "layer": "l1", "text": "x" * 501, "point": [0, 0], "size": 10,
                       "colour": "red"}, (100, 100))


def test_text_centred_on_a_point_is_centred_on_it():
    img = _render({"op": "text", "layer": "l1", "text": "M", "point": [50, 50], "size": 30, "align": "center",
                   "valign": "middle", "colour": "#000000"}, width=100, height=100)
    inked = [(x, y) for x in range(100) for y in range(100) if img.getpixel((x, y))[0] < 128]
    xs = [x for x, _ in inked]
    ys = [y for _, y in inked]
    assert abs((min(xs) + max(xs)) / 2 - 50) <= 1
    assert abs((min(ys) + max(ys)) / 2 - 50) <= 1


def test_text_right_aligned_ends_at_the_point():
    img = _render({"op": "text", "layer": "l1", "text": "Hi", "point": [60, 10], "size": 20, "align": "right",
                   "colour": "#000000"}, width=100, height=40)
    inked_x = [x for x in range(100) for y in range(40) if img.getpixel((x, y))[0] < 128]
    assert max(inked_x) <= 60
    assert max(inked_x) >= 55


def _picture(path, size=(10, 10), colour=(0, 0, 255, 255)):
    Image.new("RGBA", size, colour).save(path)
    return path


def test_erase_makes_a_rect_transparent_on_its_own_layer_only(tmp_path):
    doc = document.new_document(20, 20, "#ffffff")
    doc = document.apply_changes(doc, {
        "layers": [{"id": "top"}],
        "ops": [
            {"op": "rect", "layer": "l1", "box": [0, 0, 20, 20], "fill": "#ff0000"},
            {"op": "erase", "layer": "top", "box": [5, 5, 10, 10]},
            {"op": "erase", "layer": "l1", "box": [0, 0, 4, 4]},
        ],
    })
    img = document.render(doc)
    assert img.getpixel((0, 0)) == (255, 255, 255, 255)  # erased on l1, the white background shows
    assert img.getpixel((10, 10)) == (255, 0, 0, 255)  # top layer has nothing to erase
    assert img.getpixel((18, 18)) == (255, 0, 0, 255)


def test_partial_erase_reduces_alpha_by_the_given_amount():
    doc = document.new_document(10, 10, None)
    doc = document.apply_changes(doc, {"ops": [
        {"op": "rect", "layer": "l1", "box": [0, 0, 10, 10], "fill": "#000000"},
        {"op": "erase", "layer": "l1", "box": [0, 0, 10, 10], "opacity": 0.5},
    ]})
    assert abs(document.render(doc).getpixel((5, 5))[3] - 128) <= 1  # half of 255, rounded


def test_erase_needs_a_box():
    with pytest.raises(PaintError, match="erase needs box"):
        ops.normalise({"op": "erase", "layer": "l1"}, (10, 10))


def test_place_copies_pixels_at_the_point(tmp_path):
    picture = _picture(tmp_path / "blue.png", (6, 4))
    doc = document.new_document(20, 20, "#ffffff")
    doc = document.apply_changes(doc, {"ops": [
        {"op": "place", "layer": "l1", "image": str(picture), "point": [3, 5]},
    ]}, tmp_path)
    img = document.render(doc, tmp_path)
    assert img.getpixel((3, 5)) == (0, 0, 255, 255)
    assert img.getpixel((8, 8)) == (0, 0, 255, 255)
    assert img.getpixel((9, 5)) == (255, 255, 255, 255)
    assert img.getpixel((2, 5)) == (255, 255, 255, 255)


def test_place_keeps_the_pictures_own_transparency(tmp_path):
    picture = tmp_path / "half.png"
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(picture)
    doc = document.new_document(8, 8, "#ffffff")
    doc = document.apply_changes(doc, {"ops": [{"op": "place", "layer": "l1", "image": "half.png", "point": [0, 0]}]}, tmp_path)
    assert document.render(doc, tmp_path).getpixel((1, 1)) == (255, 255, 255, 255)


def test_place_can_resize_keeping_proportion(tmp_path):
    picture = _picture(tmp_path / "wide.png", (40, 20))
    doc = document.new_document(60, 60, None)
    doc = document.apply_changes(doc, {"ops": [
        {"op": "place", "layer": "l1", "image": "wide.png", "point": [0, 0], "width": 20},
    ]}, tmp_path)
    img = document.render(doc, tmp_path)
    assert img.getpixel((19, 9))[3] == 255  # 20 wide, 10 tall
    assert img.getpixel((5, 12))[3] == 0  # below the 10 px height


def test_place_opacity_scales_the_picture(tmp_path):
    picture = _picture(tmp_path / "red.png", (4, 4), (255, 0, 0, 255))
    doc = document.new_document(4, 4, "#ffffff")
    doc = document.apply_changes(doc, {"ops": [
        {"op": "place", "layer": "l1", "image": str(picture), "point": [0, 0], "opacity": 0.5},
    ]}, tmp_path)
    red, green, blue, _ = document.render(doc, tmp_path).getpixel((1, 1))
    assert red == 255 and abs(green - 128) <= 1 and abs(blue - 128) <= 1  # half strength red over white


def test_place_outside_the_canvas_is_clipped(tmp_path):
    picture = _picture(tmp_path / "blue.png", (10, 10))
    doc = document.new_document(10, 10, None)
    doc = document.apply_changes(doc, {"ops": [{"op": "place", "layer": "l1", "image": str(picture), "point": [-5, 5]}]}, tmp_path)
    img = document.render(doc, tmp_path)
    assert img.getpixel((0, 6))[3] == 255
    assert img.getpixel((9, 6))[3] == 0


def test_place_reports_missing_and_unreadable_files(tmp_path):
    with pytest.raises(PaintError, match="file does not exist"):
        ops.normalise({"op": "place", "layer": "l1", "image": "nope.png", "point": [0, 0]}, (10, 10), tmp_path)
    (tmp_path / "fake.png").write_text("not a picture")
    with pytest.raises(PaintError, match="not a readable picture"):
        ops.normalise({"op": "place", "layer": "l1", "image": "fake.png", "point": [0, 0]}, (10, 10), tmp_path)
    with pytest.raises(PaintError, match="must be a picture file"):
        ops.normalise({"op": "place", "layer": "l1", "image": "doc.pdf", "point": [0, 0]}, (10, 10), tmp_path)


def test_relative_paths_follow_the_document_folder_not_the_current_folder(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _picture(tmp_path / "logo.png")
    monkeypatch.chdir(elsewhere)
    doc = document.new_document(10, 10, None)
    doc = document.apply_changes(doc, {"ops": [{"op": "place", "layer": "l1", "image": "logo.png", "point": [0, 0]}]}, tmp_path)
    assert document.validate_document(doc, tmp_path) == []
    assert document.render(doc, tmp_path).getpixel((5, 5)) == (0, 0, 255, 255)
    assert document.validate_document(doc, elsewhere)  # from the wrong folder it cannot be found


def test_place_accepts_jpeg_and_webp(tmp_path):
    Image.new("RGB", (8, 8), (0, 255, 0)).save(tmp_path / "green.jpg")
    Image.new("RGB", (8, 8), (255, 0, 0)).save(tmp_path / "red.webp", "WEBP", lossless=True)
    doc = document.new_document(20, 10, "#ffffff")
    doc = document.apply_changes(doc, {"ops": [
        {"op": "place", "layer": "l1", "image": "green.jpg", "point": [0, 0]},
        {"op": "place", "layer": "l1", "image": "red.webp", "point": [10, 0]},
    ]}, tmp_path)
    img = document.render(doc, tmp_path)
    assert img.getpixel((4, 4))[1] > 200
    assert img.getpixel((14, 4))[0] > 200
