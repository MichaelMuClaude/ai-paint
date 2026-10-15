import pytest
from PIL import Image

from ai_paint import document, ops, svgpath
from ai_paint.errors import PaintError
from ai_paint.gradient import Gradient

WHITE = (255, 255, 255, 255)


def _render(*op_list, width=100, height=100, background="#ffffff"):
    doc = document.new_document(width, height, background)
    doc = document.apply_changes(doc, {"ops": list(op_list)})
    return document.render(doc)


LINEAR = {"type": "linear", "from": [0, 0], "to": [0, 100], "stops": [[0, "#ff0000"], [1, "#0000ff"]]}
RADIAL = {"type": "radial", "centre": [50, 50], "radius": 50, "stops": [[0, "#ffffff"], [1, "#000000"]]}


def test_linear_gradient_runs_from_its_start_to_its_end():
    img = _render({"op": "rect", "layer": "l1", "box": [0, 0, 100, 100], "fill": LINEAR})
    top = img.getpixel((50, 1))
    bottom = img.getpixel((50, 98))
    assert top[0] > 240 and top[2] < 20
    assert bottom[2] > 240 and bottom[0] < 20
    middle = img.getpixel((50, 50))
    assert 110 < middle[0] < 140 and 110 < middle[2] < 140


def test_radial_gradient_is_brightest_at_the_centre():
    img = _render({"op": "ellipse", "layer": "l1", "box": [0, 0, 100, 100], "fill": RADIAL})
    assert img.getpixel((50, 50))[0] > 240
    assert img.getpixel((5, 50))[0] < 40


def test_gradient_clamps_outside_its_stops():
    gradient = Gradient("linear", [(0.25, (255, 0, 0, 255)), (0.75, (0, 0, 255, 255))],
                        start=(0, 0), end=(100, 0))
    colours = gradient.render((0, 0, 100, 1))
    assert tuple(colours[0, 0]) == (255, 0, 0, 255)  # before the first stop
    assert tuple(colours[0, 99]) == (0, 0, 255, 255)  # after the last stop


@pytest.mark.parametrize("value, message", [
    ({"type": "spiral"}, "type must be 'linear' or 'radial'"),
    ({"type": "linear", "from": [0, 0], "to": [0, 0], "stops": [[0, "red"], [1, "blue"]]},
     "different 'from' and 'to'"),
    ({"type": "linear", "from": [0, 0], "to": [1, 1], "stops": [[0, "red"]]}, "at least two"),
    ({"type": "linear", "from": [0, 0], "to": [1, 1], "stops": [[0.8, "red"], [0.2, "blue"]]}, "go up"),
    ({"type": "radial", "centre": [0, 0], "radius": 0, "stops": [[0, "red"], [1, "blue"]]}, "positive radius"),
    ({"type": "radial", "centre": [0, 0], "radius": 5, "stops": [[0, "red"], [1, "blue"]], "angle": 4},
     "unknown field"),
    ({"type": "linear", "from": [0, 0], "to": [1, 1], "stops": [[0, "nope"], [1, "blue"]]}, "not recognised"),
])
def test_bad_gradients_are_explained(value, message):
    with pytest.raises(PaintError, match=message):
        ops.normalise({"op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": value}, (100, 100))


def test_path_triangle_fills_inside_only():
    img = _render({"op": "path", "layer": "l1", "d": "M 10 90 L 90 90 L 50 10 Z", "fill": "#ff0000"})
    assert img.getpixel((50, 70)) == (255, 0, 0, 255)
    assert img.getpixel((10, 10)) == WHITE


def test_relative_commands_match_absolute_ones():
    absolute = _render({"op": "path", "layer": "l1", "d": "M 10 10 L 60 10 L 60 60 L 10 60 Z", "fill": "#000000"})
    relative = _render({"op": "path", "layer": "l1", "d": "m 10 10 l 50 0 l 0 50 l -50 0 z", "fill": "#000000"})
    assert absolute.tobytes() == relative.tobytes()


def test_cubic_curve_bulges_towards_its_control_points():
    # A curve from (10, 80) to (90, 80) pulled up by control points at y = 10.
    img = _render({"op": "path", "layer": "l1", "d": "M 10 80 C 10 10 90 10 90 80 Z", "fill": "#000000"})
    assert img.getpixel((50, 40)) == (0, 0, 0, 255)  # inside the bulge
    assert img.getpixel((50, 15)) == WHITE  # above the curve's top, which is near y 30


def test_smooth_cubic_and_quadratic_commands_are_accepted():
    subpaths = svgpath.parse("M 0 0 Q 10 0 20 10 T 40 10 S 60 20 80 10 Z")
    assert len(subpaths) == 1
    points, closed = subpaths[0]
    assert closed
    assert points[-1] == pytest.approx((80, 10))


def test_path_outline_has_the_given_width():
    img = _render({"op": "path", "layer": "l1", "d": "M 10 50 L 90 50", "outline": "#000000", "width": 6})
    assert img.getpixel((50, 50)) == (0, 0, 0, 255)
    assert img.getpixel((50, 40)) == WHITE


@pytest.mark.parametrize("data, message", [
    ("", "must be SVG path text"),
    ("L 10 10", "must start with a move command"),
    ("M 10", "needs 2 numbers"),
    ("M 10 10 X 5 5", "text it does not understand"),
    ("10 20 30 40", "must start with a move command"),
    ("M 10 10", "needs at least two points"),
])
def test_bad_path_data_is_explained(data, message):
    with pytest.raises(PaintError, match=message):
        svgpath.parse(data)


def test_path_without_fill_or_outline_is_refused():
    with pytest.raises(PaintError, match="give a fill colour"):
        ops.normalise({"op": "path", "layer": "l1", "d": "M 0 0 L 9 9"}, (100, 100))


def test_layer_blur_spreads_colour_beyond_the_shape_and_keeps_its_colour():
    doc = document.new_document(60, 60, None)
    doc = document.apply_changes(doc, {
        "update_layers": {"l1": {"blur": 3}},
        "ops": [{"op": "rect", "layer": "l1", "box": [20, 20, 20, 20], "fill": "#ff0000"}],
    })
    img = document.render(doc)
    outside = img.getpixel((18, 30))
    assert 0 < outside[3] < 255  # the blur reaches past the edge
    assert outside[0] > 200 and outside[1] < 40 and outside[2] < 40  # and stays red, not dark
    assert img.getpixel((30, 30)) == (255, 0, 0, 255)


def test_blur_is_validated():
    doc = document.new_document(10, 10)
    doc["layers"][0]["blur"] = 500
    assert any("blur must be" in problem for problem in document.validate_document(doc))
