import json
import subprocess
import sys

import pytest
from PIL import Image

from ai_paint import document
from ai_paint.errors import PaintError
from ai_paint.view import crop_and_zoom, draw_grid, parse_box


def run(*args):
    return subprocess.run([sys.executable, "-m", "ai_paint.cli", *args], capture_output=True, text=True)


def test_grid_marks_every_step_and_leaves_the_rest_alone():
    base = Image.new("RGBA", (40, 40), (255, 255, 255, 255))
    gridded = draw_grid(base, 10)
    assert gridded.size == base.size
    assert gridded.getpixel((10, 5)) != (255, 255, 255, 255)  # on a grid line
    assert gridded.getpixel((13, 5)) == (255, 255, 255, 255)  # between lines
    assert base.getpixel((10, 5)) == (255, 255, 255, 255)  # the input is not changed


def test_every_fifth_grid_line_is_darker():
    base = Image.new("RGBA", (120, 20), (255, 255, 255, 255))
    gridded = draw_grid(base, 10)
    minor = gridded.getpixel((10, 5))  # 1st line: not a multiple of 50
    major = gridded.getpixel((50, 5))  # 5th line
    assert major[0] < minor[0]


def test_grid_labels_use_picture_coordinates_inside_a_crop():
    picture = Image.new("RGBA", (400, 400), (255, 255, 255, 255))
    crop = picture.crop((300, 200, 360, 260))
    gridded = draw_grid(crop, 50, origin=(300, 200), scale=1)
    # The line at picture x=350 is at crop x=50; it is a major line, so it is darker than a minor one.
    assert gridded.getpixel((50, 30))[0] < 255


def test_grid_step_below_two_is_refused():
    with pytest.raises(PaintError, match="at least 2"):
        draw_grid(Image.new("RGBA", (10, 10)), 1)


def test_crop_and_zoom_uses_hard_pixels():
    img = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    img.putpixel((1, 1), (255, 0, 0, 255))
    zoomed = crop_and_zoom(img, (1, 1, 2, 2), 3)
    assert zoomed.size == (6, 6)
    assert zoomed.getpixel((0, 0)) == (255, 0, 0, 255)
    assert zoomed.getpixel((3, 0)) == (0, 0, 0, 255)


def test_crop_outside_the_picture_is_refused():
    with pytest.raises(PaintError, match="outside the 10x10 picture"):
        crop_and_zoom(Image.new("RGBA", (10, 10)), (5, 5, 10, 10), 1)


@pytest.mark.parametrize("zoom", [0, 9])
def test_zoom_must_be_between_one_and_eight(zoom):
    with pytest.raises(PaintError, match="zoom must be"):
        crop_and_zoom(Image.new("RGBA", (10, 10)), None, zoom)


def test_oversized_zoom_is_refused():
    with pytest.raises(PaintError, match="larger than"):
        crop_and_zoom(Image.new("RGBA", (2000, 2000)), None, 8)


def test_parse_box_reads_four_numbers():
    assert parse_box("10, 20,30,40") == (10, 20, 30, 40)
    with pytest.raises(PaintError, match="four whole numbers"):
        parse_box("10,20,30")
    with pytest.raises(PaintError, match="four whole numbers"):
        parse_box("a,b,c,d")


def test_render_with_grid_crop_and_zoom_from_the_command_line(tmp_path):
    doc_path = tmp_path / "pic.json"
    document.save(document.new_document(100, 80, "#ffffff"), doc_path)
    out = tmp_path / "view.png"
    result = run("render", str(doc_path), "-o", str(out), "--grid", "10", "--crop", "20,10,40,30", "--zoom", "2")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert (summary["width"], summary["height"]) == (80, 60)
    assert summary["view"] == {"crop": [20, 10, 40, 30], "zoom": 2, "grid": 10}
    with Image.open(out) as img:
        assert img.size == (80, 60)


def test_plain_render_has_no_view_block(tmp_path):
    doc_path = tmp_path / "pic.json"
    document.save(document.new_document(30, 20, "#ffffff"), doc_path)
    result = run("render", str(doc_path), "-o", str(tmp_path / "plain.png"))
    assert result.returncode == 0
    assert "view" not in json.loads(result.stdout)


def test_view_options_never_change_the_document(tmp_path):
    doc_path = tmp_path / "pic.json"
    document.save(document.new_document(30, 20, "#ffffff"), doc_path)
    before = doc_path.read_text()
    run("render", str(doc_path), "-o", str(tmp_path / "view.png"), "--grid", "5", "--zoom", "2")
    assert doc_path.read_text() == before


def test_bad_crop_from_the_command_line_is_a_clean_error(tmp_path):
    doc_path = tmp_path / "pic.json"
    document.save(document.new_document(30, 20, "#ffffff"), doc_path)
    result = run("render", str(doc_path), "-o", str(tmp_path / "x.png"), "--crop", "0,0,99,5")
    assert result.returncode == 1
    assert "outside the 30x20 picture" in result.stderr
    assert "Traceback" not in result.stderr
