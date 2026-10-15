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
    assert names == ["stroke", "line", "rect", "ellipse", "polygon", "fill", "text"]


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
