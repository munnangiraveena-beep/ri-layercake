"""Scene golden tests: gallery scenes match committed snapshots byte for byte.

Regenerate after an intended layout change with: UPDATE_GOLDEN=1 pytest tests/test_scene.py
"""

import json
import os
from pathlib import Path

import pytest

import ri_layercake as lc
from ri_layercake import gallery

GOLDEN = Path(__file__).parent / "golden"
VIEWS = {
    "schematic": lc.View(),
    "linear": lc.View(scale="linear", loss=120),
    "log": lc.View(scale="log", table="right"),
}


@pytest.mark.parametrize("name", gallery.names())
@pytest.mark.parametrize("view", sorted(VIEWS))
def test_scene_golden(name, view):
    scene = gallery.load(name).scene(VIEWS[view]).to_json(indent=1)
    path = GOLDEN / f"{name}.{view}.json"
    if os.environ.get("UPDATE_GOLDEN") or not path.exists():
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(scene + "\n")
    assert scene + "\n" == path.read_text()


def test_scene_is_deterministic():
    a = gallery.load("gap_overlap").scene(scale="linear").to_json()
    b = gallery.load("gap_overlap").scene(scale="linear").to_json()
    assert a == b


def test_scene_schema_and_theme_colours():
    s = gallery.load("partly_placed").scene().to_dict()
    assert s["schema"] == "ri-layercake/scene@1"
    assert s["frame"]["w"] == 1280 and s["frame"]["h"] == 720
    for shape in s["shapes"]:
        for key in ("fill", "stroke"):
            spec = shape.get(key)
            if spec:
                assert "theme" in spec or spec.get("status") == "error"
    roles = {sh["role"] for sh in s["shapes"]}
    assert {"layer", "unplaced", "label", "retention", "title"} <= roles


def test_hit_regions_cover_edges():
    s = lc.Tower.from_text("40 xs 10, 50 xs 50").scene(scale="linear").to_dict()
    edges = {(h["layer"], h["edge"]) for h in s["hit"]}
    assert {("L1", "top"), ("L1", "bottom"), ("L2", "placed"), ("L2", "body")} <= edges
    top = next(h for h in s["hit"] if h["layer"] == "L2" and h["edge"] == "top")
    assert top["value"] == 100


def test_gap_and_overlap_are_drawn():
    s = gallery.load("gap_overlap").scene().to_dict()
    roles = [sh["role"] for sh in s["shapes"]]
    assert "gap" in roles and "overlap" in roles
    overlap = next(sh for sh in s["shapes"] if sh["role"] == "overlap")
    assert overlap["export"] is False


def test_thin_layers_label_beside_block():
    s = gallery.load("thin_retention").scene(scale="linear").to_dict()
    assert any(sh.get("side") for sh in s["shapes"] if sh["role"] == "label")


def test_empty_tower():
    s = lc.Tower().scene().to_dict()
    assert [sh["role"] for sh in s["shapes"]] == ["empty"]


def test_svg_renders_every_gallery_tower():
    for name in gallery.names():
        svg = gallery.load(name).to_svg(scale="log")
        assert svg.startswith("<svg") and "</svg>" in svg
    assert json.loads(gallery.load("casualty_xl").scene().to_json())
