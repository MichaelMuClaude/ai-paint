import copy

import pytest

from ai_paint import document
from ai_paint.errors import PaintError


def test_new_document_has_one_layer_and_a_valid_shape():
    doc = document.new_document(64, 32)
    assert doc["schema"] == "ai-paint/1"
    assert doc["canvas"] == {"width": 64, "height": 32, "background": "#ffffff"}
    assert [layer["id"] for layer in doc["layers"]] == ["l1"]
    assert document.validate_document(doc) == []


def test_new_document_rejects_bad_sizes():
    with pytest.raises(PaintError, match="canvas width"):
        document.new_document(0, 10)
    with pytest.raises(PaintError, match="canvas height"):
        document.new_document(10, 20_000)
    with pytest.raises(PaintError, match="pixels; the limit"):
        document.new_document(9_000, 9_000)


def test_validate_collects_several_problems():
    doc = document.new_document(50, 50)
    doc["ops"] = [
        {"op": "rect", "layer": "nope", "box": [0, 0, 5, 5], "fill": "red"},
        {"op": "circle", "layer": "l1"},
        {"op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red", "id": "dup"},
        {"op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red", "id": "dup"},
    ]
    problems = document.validate_document(doc)
    assert any("ops[0]" in p and "layer 'nope' does not exist" in p for p in problems)
    assert any("ops[1]" in p and "op must be one of" in p for p in problems)
    assert any("ops[3]" in p and "duplicate id 'dup'" in p for p in problems)


def test_validate_checks_layers():
    doc = document.new_document(20, 20)
    doc["layers"].append({"id": "l1", "opacity": 3})
    doc["layers"].append({"id": "bad id!"})
    doc["layers"][0]["blend"] = "multiply"
    problems = document.validate_document(doc)
    assert any("duplicate id 'l1'" in p for p in problems)
    assert any("opacity must be a number from 0 to 1" in p for p in problems)
    assert any("id must be" in p for p in problems)
    assert any("blend must be one of" in p for p in problems)


def test_validate_rejects_unknown_top_level_fields_and_bad_schema():
    doc = document.new_document(20, 20)
    doc["schema"] = "ai-paint/2"
    doc["history"] = []
    problems = document.validate_document(doc)
    assert any("schema must be" in p for p in problems)
    assert any("unknown top-level field(s): history" in p for p in problems)


def test_apply_assigns_ids_and_leaves_the_input_untouched():
    doc = document.new_document(40, 40)
    before = copy.deepcopy(doc)
    result = document.apply_changes(doc, {
        "layers": [{"name": "ink"}],
        "ops": [
            {"op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"},
            {"op": "rect", "layer": "l2", "box": [5, 5, 5, 5], "fill": "blue"},
        ],
    })
    assert doc == before
    assert [layer["id"] for layer in result["layers"]] == ["l1", "l2"]
    assert [op["id"] for op in result["ops"]] == ["o1", "o2"]


def test_apply_continues_ids_after_existing_ones():
    doc = document.new_document(40, 40)
    doc = document.apply_changes(doc, {"ops": [{"op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"}]})
    doc = document.apply_changes(doc, {"ops": [{"op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"}]})
    assert [op["id"] for op in doc["ops"]] == ["o1", "o2"]


def test_apply_rejects_an_invalid_result_and_names_the_problem():
    doc = document.new_document(40, 40)
    with pytest.raises(PaintError, match="ops\\[0\\].*unknown field"):
        document.apply_changes(doc, {"ops": [{"op": "rect", "layer": "l1", "box": [0, 0, 5, 5],
                                              "fill": "red", "shadow": True}]})


def test_apply_rejects_unknown_change_fields():
    with pytest.raises(PaintError, match="unknown field"):
        document.apply_changes(document.new_document(10, 10), {"undo": True})


def test_ops_can_refer_to_a_layer_added_in_the_same_change():
    doc = document.new_document(40, 40)
    result = document.apply_changes(doc, {
        "layers": [{"id": "ink"}],
        "ops": [{"op": "rect", "layer": "ink", "box": [0, 0, 5, 5], "fill": "red"}],
    })
    assert document.validate_document(result) == []


def test_render_draws_in_op_order_and_matches_size():
    doc = document.new_document(30, 20)
    doc = document.apply_changes(doc, {"ops": [
        {"op": "rect", "layer": "l1", "box": [0, 0, 30, 20], "fill": "#ff0000"},
        {"op": "rect", "layer": "l1", "box": [0, 0, 15, 20], "fill": "#00ff00"},
    ]})
    img = document.render(doc)
    assert img.size == (30, 20)
    assert img.getpixel((5, 5)) == (0, 255, 0, 255)
    assert img.getpixel((25, 5)) == (255, 0, 0, 255)


def test_render_refuses_an_invalid_document():
    doc = document.new_document(30, 20)
    doc["ops"] = [{"op": "rect", "layer": "l1", "box": [0, 0, 5, 5]}]
    with pytest.raises(PaintError, match="give a fill colour"):
        document.render(doc)


def test_save_refuses_to_overwrite_without_force(tmp_path):
    path = tmp_path / "doc.json"
    document.save(document.new_document(10, 10), path)
    with pytest.raises(PaintError, match="already exists"):
        document.save(document.new_document(10, 10), path)
    document.save(document.new_document(12, 12), path, force=True)
    assert document.load(path)["canvas"]["width"] == 12


def test_save_image_refuses_unknown_suffixes(tmp_path):
    from PIL import Image

    with pytest.raises(PaintError, match="output must end in"):
        document.save_image(Image.new("RGBA", (4, 4)), tmp_path / "pic.gif")


def test_jpeg_output_is_flattened_onto_white(tmp_path):
    from PIL import Image

    path = tmp_path / "pic.jpg"
    document.save_image(Image.new("RGBA", (4, 4), (0, 0, 0, 0)), path)
    with Image.open(path) as saved:
        assert saved.getpixel((1, 1))[0] > 240


def test_update_merges_fields_and_keeps_the_rest():
    doc = document.new_document(40, 40)
    doc = document.apply_changes(doc, {"ops": [
        {"id": "box", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"},
    ]})
    result = document.apply_changes(doc, {"update": {"box": {"fill": "blue"}}})
    assert result["ops"][0] == {"id": "box", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "blue"}
    assert doc["ops"][0]["fill"] == "red"  # the input is unchanged


def test_remove_deletes_by_id():
    doc = document.new_document(40, 40)
    doc = document.apply_changes(doc, {"ops": [
        {"id": "a", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"},
        {"id": "b", "op": "rect", "layer": "l1", "box": [5, 5, 5, 5], "fill": "blue"},
    ]})
    result = document.apply_changes(doc, {"remove": ["a"]})
    assert [op["id"] for op in result["ops"]] == ["b"]


def test_unknown_ids_in_update_or_remove_are_reported():
    doc = document.new_document(40, 40)
    with pytest.raises(PaintError, match="no op with id 'ghost'.*ai-paint list"):
        document.apply_changes(doc, {"remove": ["ghost"]})
    with pytest.raises(PaintError, match="no op with id 'ghost'"):
        document.apply_changes(doc, {"update": {"ghost": {"fill": "red"}}})


def test_an_op_id_cannot_be_changed_by_update():
    doc = document.new_document(40, 40)
    doc = document.apply_changes(doc, {"ops": [{"id": "a", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"}]})
    with pytest.raises(PaintError, match="cannot be changed"):
        document.apply_changes(doc, {"update": {"a": {"id": "z"}}})


def test_reusing_an_existing_id_suggests_update():
    doc = document.new_document(40, 40)
    doc = document.apply_changes(doc, {"ops": [{"id": "a", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"}]})
    with pytest.raises(PaintError, match="use 'update'"):
        document.apply_changes(doc, {"ops": [{"id": "a", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"}]})


def test_remove_then_add_with_the_same_id_is_allowed():
    doc = document.new_document(40, 40)
    doc = document.apply_changes(doc, {"ops": [{"id": "a", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5], "fill": "red"}]})
    result = document.apply_changes(doc, {"remove": ["a"],
                                          "ops": [{"id": "a", "op": "rect", "layer": "l1", "box": [0, 0, 9, 9], "fill": "blue"}]})
    assert result["ops"][0]["box"] == [0, 0, 9, 9]


def test_update_layers_changes_opacity_and_visibility():
    doc = document.new_document(40, 40)
    result = document.apply_changes(doc, {"update_layers": {"l1": {"opacity": 0.5, "visible": False}}})
    assert result["layers"][0]["opacity"] == 0.5
    assert result["layers"][0]["visible"] is False


def test_remove_layers_only_when_no_ops_use_them():
    doc = document.new_document(40, 40)
    doc = document.apply_changes(doc, {"layers": [{"id": "ink"}],
                                       "ops": [{"op": "rect", "layer": "ink", "box": [0, 0, 5, 5], "fill": "red"}]})
    with pytest.raises(PaintError, match="still has 1 op"):
        document.apply_changes(doc, {"remove_layers": ["ink"]})
    cleaned = document.apply_changes(doc, {"remove": ["o1"], "remove_layers": ["ink"]})
    assert [layer["id"] for layer in cleaned["layers"]] == ["l1"]


def test_op_errors_name_the_op_id():
    doc = document.new_document(40, 40)
    doc["ops"] = [{"id": "disc", "op": "rect", "layer": "l1", "box": [0, 0, 5, 5]}]
    problems = document.validate_document(doc)
    assert problems == ["ops[0] (id disc): give a fill colour, an outline colour, or both"]
