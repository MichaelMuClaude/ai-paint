import json
import subprocess
import sys

from PIL import Image


def run(*args):
    return subprocess.run([sys.executable, "-m", "ai_paint.cli", *args], capture_output=True, text=True)


def test_new_apply_validate_render_round_trip(tmp_path):
    doc = tmp_path / "pic.json"
    assert run("new", str(doc), "--width", "80", "--height", "60").returncode == 0

    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps({"ops": [
        {"op": "rect", "layer": "l1", "box": [10, 10, 30, 20], "fill": "#ff0000"},
    ]}))
    second = tmp_path / "pic-2.json"
    result = run("apply", str(doc), "--changes", str(changes), "-o", str(second))
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["input"]["ops"] == 0
    assert summary["added"]["ops"] == 1

    assert run("validate", str(second)).returncode == 0

    png = tmp_path / "pic.png"
    assert run("render", str(second), "-o", str(png)).returncode == 0
    with Image.open(png) as img:
        assert img.size == (80, 60)
        assert img.getpixel((12, 12))[:3] == (255, 0, 0)


def test_apply_never_overwrites_its_input(tmp_path):
    doc = tmp_path / "pic.json"
    run("new", str(doc), "--width", "10", "--height", "10")
    before = doc.read_text()
    result = run("apply", str(doc), "--change", '{"ops": []}', "-o", str(doc), "--force")
    assert result.returncode == 1
    assert "never changed" in result.stderr
    assert doc.read_text() == before


def test_render_refuses_to_replace_an_existing_picture(tmp_path):
    doc = tmp_path / "pic.json"
    run("new", str(doc), "--width", "10", "--height", "10")
    png = tmp_path / "pic.png"
    assert run("render", str(doc), "-o", str(png)).returncode == 0
    again = run("render", str(doc), "-o", str(png))
    assert again.returncode == 1
    assert "already exists" in again.stderr
    assert run("render", str(doc), "-o", str(png), "--force").returncode == 0


def test_validate_reports_problems_on_stderr_and_fails(tmp_path):
    doc = tmp_path / "bad.json"
    doc.write_text(json.dumps({
        "schema": "ai-paint/1",
        "canvas": {"width": 10, "height": 10, "background": "#ffffff"},
        "layers": [{"id": "l1"}],
        "ops": [{"op": "rect", "layer": "l1", "box": [0, 0, 5, 5]}],
    }))
    result = run("validate", str(doc))
    assert result.returncode == 1
    assert "invalid: ops[0]: give a fill colour, an outline colour, or both" in result.stderr


def test_info_reports_validity_and_layer_counts(tmp_path):
    doc = tmp_path / "pic.json"
    run("new", str(doc), "--width", "10", "--height", "10")
    result = run("info", str(doc))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["valid"] is True
    assert data["layers"] == [{"id": "l1", "name": "base", "opacity": 1.0, "visible": True, "ops": 0}]


def test_info_on_a_broken_document_still_prints_the_problems(tmp_path):
    doc = tmp_path / "broken.json"
    doc.write_text('{"schema": "ai-paint/1", "canvas": {"width": 10, "height": 10}, "layers": "none"}')
    result = run("info", str(doc))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["valid"] is False
    assert data["problems"]


def test_ops_lists_every_operation_as_json():
    result = run("ops")
    assert result.returncode == 0
    names = [entry["op"] for entry in json.loads(result.stdout)]
    assert set(names) == {"stroke", "line", "rect", "ellipse", "polygon", "fill", "text", "erase", "place", "path", "balloon", "spline"}


def test_missing_file_is_a_clean_error(tmp_path):
    result = run("validate", str(tmp_path / "nope.json"))
    assert result.returncode == 1
    assert "file not found" in result.stderr
    assert "Traceback" not in result.stderr


def test_new_refuses_to_replace_without_force(tmp_path):
    doc = tmp_path / "pic.json"
    assert run("new", str(doc), "--width", "10", "--height", "10").returncode == 0
    again = run("new", str(doc), "--width", "10", "--height", "10")
    assert again.returncode == 1
    assert "already exists" in again.stderr


def test_list_shows_ids_layers_and_values(tmp_path):
    doc = tmp_path / "pic.json"
    run("new", str(doc), "--width", "50", "--height", "50")
    changes = tmp_path / "c.json"
    changes.write_text(json.dumps({"layers": [{"id": "top"}], "ops": [
        {"id": "box", "op": "rect", "layer": "l1", "box": [1, 2, 3, 4], "fill": "red"},
        {"op": "text", "layer": "top", "text": "Hi", "point": [5, 5], "size": 12, "colour": "blue"},
    ]}))
    out = tmp_path / "pic2.json"
    assert run("apply", str(doc), "--changes", str(changes), "-o", str(out)).returncode == 0
    rows = json.loads(run("list", str(out)).stdout)
    assert [row["id"] for row in rows] == ["box", "o1"]
    assert rows[0]["values"] == 'box=[1, 2, 3, 4] fill="red"'
    only_top = json.loads(run("list", str(out), "--layer", "top").stdout)
    assert [row["id"] for row in only_top] == ["o1"]
    text = run("list", str(out), "--text").stdout
    assert "box" in text and "rect" in text


def test_apply_can_update_and_remove_from_the_command_line(tmp_path):
    doc = tmp_path / "pic.json"
    run("new", str(doc), "--width", "50", "--height", "50")
    first = tmp_path / "first.json"
    run("apply", str(doc), "--change", '{"ops":[{"id":"box","op":"rect","layer":"l1","box":[0,0,9,9],"fill":"red"}]}', "-o", str(first))
    second = tmp_path / "second.json"
    result = run("apply", str(first), "--change", '{"update":{"box":{"fill":"blue"}}}', "-o", str(second))
    assert result.returncode == 0, result.stderr
    assert json.loads(second.read_text())["ops"][0]["fill"] == "blue"
    third = tmp_path / "third.json"
    run("apply", str(second), "--change", '{"remove":["box"]}', "-o", str(third))
    assert json.loads(third.read_text())["ops"] == []


def test_measure_reports_text_size_and_grows_with_more_lines():
    one = json.loads(run("measure", "--text", "Hello", "--size", "24").stdout)
    two = json.loads(run("measure", "--text", "Hello\nHello", "--size", "24").stdout)
    assert one["width"] > 0 and one["height"] > 0
    assert two["height"] > one["height"] * 1.5
    assert two["width"] == one["width"]


def test_measure_rejects_bad_input():
    result = run("measure", "--text", "Hi", "--size", "2")
    assert result.returncode == 1
    assert "size must be" in result.stderr
    result = run("measure", "--text", "Hi", "--size", "20", "--font", "missing.ttf")
    assert result.returncode == 1
    assert "font must be" in result.stderr


def test_manga_presets_create_pages_of_the_right_size(tmp_path):
    doc = tmp_path / "page.json"
    result = run("new", str(doc), "--preset", "manga-b5")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["width"] == 2150
    data = json.loads(doc.read_text())
    assert (data["canvas"]["width"], data["canvas"]["height"]) == (2150, 3035)


def test_new_needs_a_size_or_a_preset(tmp_path):
    result = run("new", str(tmp_path / "x.json"))
    assert result.returncode == 1
    assert "--preset" in result.stderr


def test_trace_turns_a_dark_ring_into_a_hollow_outline(tmp_path):
    import shutil

    import pytest

    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    picture = tmp_path / "ring.png"
    img = Image.new("RGBA", (120, 120), (255, 255, 255, 255))
    from PIL import ImageDraw
    ImageDraw.Draw(img).ellipse([20, 20, 100, 100], outline=(0, 0, 0, 255), width=6)
    img.save(picture)
    changes = tmp_path / "ring-changes.json"
    result = run("trace", str(picture), "-o", str(changes))
    assert result.returncode == 0, result.stderr
    info = json.loads(result.stdout)
    assert info["paths"] >= 1
    doc = tmp_path / "canvas.json"
    run("new", str(doc), "--width", str(info["canvas_width"]), "--height", str(info["canvas_height"]),
        "--background", "#ffffff")
    out = tmp_path / "canvas2.json"
    assert run("apply", str(doc), "--changes", str(changes), "-o", str(out)).returncode == 0
    rendered = tmp_path / "rendered.png"
    assert run("render", str(out), "-o", str(rendered)).returncode == 0
    with Image.open(rendered) as traced:
        assert traced.getpixel((60, 60))[0] > 200  # the middle stays empty
        assert traced.getpixel((20, 60))[0] < 100  # the ring is drawn


def test_trace_refuses_a_bad_threshold(tmp_path):
    picture = tmp_path / "p.png"
    Image.new("RGBA", (10, 10), (255, 255, 255, 255)).save(picture)
    result = run("trace", str(picture), "-o", str(tmp_path / "c.json"), "--threshold", "300")
    assert result.returncode == 1
    assert "threshold must be" in result.stderr


def test_trace_thicken_makes_the_lines_bolder(tmp_path):
    import shutil

    import pytest

    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    from PIL import ImageDraw
    picture = tmp_path / "line.png"
    img = Image.new("RGBA", (80, 40), (255, 255, 255, 255))
    ImageDraw.Draw(img).line([(5, 20), (75, 20)], fill=(0, 0, 0, 255), width=2)
    img.save(picture)
    from ai_paint.errors import PaintError
    from ai_paint.trace import trace_to_changes
    thin, _ = trace_to_changes(picture, thicken=0)
    thick, _ = trace_to_changes(picture, thicken=2)

    def height_of(changes):
        import re
        numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", changes["ops"][0]["d"])]
        ys = numbers[1::2]
        return max(ys) - min(ys)

    assert height_of(thick) > height_of(thin)
    with pytest.raises(PaintError, match="thicken"):
        trace_to_changes(picture, thicken=9)
