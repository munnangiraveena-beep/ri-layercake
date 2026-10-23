"""The web worker's JSON bridge."""

import base64
import json

from ri_layercake import bridge, gallery


def call(command, **payload):
    out = json.loads(bridge.run(command, json.dumps(payload)))
    assert out["ok"], out
    return out


def test_gallery_list_and_load():
    names = [g["name"] for g in call("gallery")["gallery"]]
    assert names == gallery.names()
    r = call("gallery", name="gap_overlap")
    assert {w["code"] for w in r["warnings"]} == {"gap", "overlap"}
    assert r["scene"]["schema"] == "ri-layercake/scene@1"
    assert r["text"].startswith("£10m ret")


def test_parse_text_keeps_title():
    t = gallery.load("casualty_xl").to_dict()
    r = call("parse_text", tower=t, text="40 xs 10")
    assert r["tower"]["title"] == "Casualty XL 2027"
    assert len(r["layers"]) == 1 and r["layers"][0]["limit"] == 40


def test_paste_returns_mapping_and_override():
    text = "A\tB\n10\t40\n50\t50\n100\t150\n"
    r = call("paste", text=text)
    assert r["mapping"]["width"] == 2
    r2 = call("paste", text=text, mapping={"header_row": 0, "columns": {"0": "limit", "1": "attachment"}})
    assert [l["limit"] for l in r2["layers"]] == [10, 50, 100]


def test_edits():
    t = call("parse_text", text="40 xs 10, 50 xs 50")["tower"]
    fields = {"limit": 60, "reinstatements": "1 @ 100%"}
    t = call("edit", tower=t, op={"type": "update", "layer": "L2", "fields": fields})["tower"]
    assert t["layers"][1]["limit"] == "60000000"
    assert t["layers"][1]["reinstatements"]["count"] == 1
    t = call("edit", tower=t, op={"type": "split", "layer": "L2", "at": 80})["tower"]
    assert len(t["layers"]) == 3
    t = call("edit", tower=t, op={"type": "merge", "a": "L2", "b": "L3"})["tower"]
    assert len(t["layers"]) == 2
    t = call("edit", tower=t, op={"type": "move", "layer": "L1", "attachment": 20})["tower"]
    assert [l["attachment"] for l in t["layers"]] == ["20000000", "60000000"]
    t = call("edit", tower=t, op={"type": "insert", "at": 60, "limit": 10})["tower"]
    assert [(l["attachment"], l["limit"]) for l in t["layers"]] == [
        ("20000000", "40000000"), ("60000000", "10000000"), ("70000000", "60000000")]
    r = call("edit", tower=t, op={"type": "meta", "fields": {"title": "Renewal"}})
    assert r["tower"]["title"] == "Renewal"


def test_apply_fix_from_warning():
    r = call("gallery", name="gap_overlap")
    gap = next(w for w in r["warnings"] if w["code"] == "gap")
    r2 = call("edit", tower=r["tower"], op={"type": "apply_fix", "fix": gap["fixes"][0]})
    assert "gap" not in {w["code"] for w in r2["warnings"]}


def test_loss_and_exports():
    t = gallery.load("property_cat").to_dict()
    loss = call("loss", tower=t, amount=120)
    assert loss["loss"]["totals"]["recovered"]
    pptx = call("export", tower=t, format="pptx")
    assert base64.b64decode(pptx["base64"])[:2] == b"PK"
    svg = call("export", tower=t, format="svg", transparent=True)
    assert svg["text"].startswith("<svg")


def test_export_blocked_by_errors():
    t = call("parse_text", text="0 xs 10")["tower"]
    out = json.loads(bridge.run("export", json.dumps({"tower": t})))
    assert out["ok"] is False and "errors" in out["error"]


def test_code_and_errors_never_raise():
    assert "lc.Tower(" in call("code", tower=gallery.load("casualty_xl").to_dict())["code"]
    bad = json.loads(bridge.run("edit", json.dumps({"op": {"type": "remove", "layer": "nope"}})))
    assert bad["ok"] is False
    assert json.loads(bridge.run("nope", "{}"))["ok"] is False


def test_run_cell_namespace_outputs_and_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    call("reset")
    r = call("run_cell", code="import ri_layercake as lc\nt = lc.Tower.from_text('40 xs 10')\nprint('hi')\nt")
    kinds = [o["type"] for o in r["outputs"]]
    assert kinds == ["stream", "svg"] and r["tower"]["layers"][0]["id"] == "L1"
    r = call("run_cell", code="t.to_pptx('out.pptx')")
    assert [f["name"] for f in r["files"]] == ["out.pptx"]
    r = call("run_cell", code="1/0")
    assert r["outputs"][-1]["type"] == "error" and "ZeroDivisionError" in r["outputs"][-1]["text"]


def test_programme_commands():
    t = gallery.load("full_programme").to_dict()
    r = call("render", tower=t)
    q = next(l for l in r["layers"] if l["kind"] == "qs")
    assert q["derived"]["premium"] == 37.5 and r["programme"]["epi"] == 150
    assert "Premium (RTE) = EPI (gross) × Adj. rate" in r["formulas"].values()
    agg = call("aggregate", tower=t, amount=0.9, as_loss_ratio=True)["aggregate"]
    assert agg["rows"][0]["recovery_100"]
    port = call("portfolio", tower=t, example=True)["portfolio"]
    assert port["count"] == 10
    walk = call("walk", tower=t)["walk"]
    assert walk["margin"].endswith("%")


def test_programme_edits_and_text_keeps_terms():
    t = call("parse_text", text="epi 100, qs 20% limit 50")["tower"]
    t = call("edit", tower=t, op={"type": "terms", "layer": "Q1", "terms": {"profit_commission": "0.2"}})["tower"]
    t = call("edit", tower=t, op={"type": "programme", "fields": {"arrangement": "side_by_side", "tax": 0.02}})["tower"]
    t = call("edit", tower=t, op={"type": "add_sl", "limit": 0.2, "attachment": 0.8})["tower"]
    r = call("parse_text", tower=t, text="epi 100, qs 25% limit 50, sl 20% xs 80%")
    assert r["tower"]["layers"][0]["terms"]["profit_commission"] == "0.2"
    assert r["tower"]["arrangement"] == "side_by_side" and r["programme"]["tax"] == 0.02


def test_run_cell_captures_matplotlib_figures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    call("reset")
    r = call("run_cell", code="from ri_layercake import gallery\ngallery.load('full_programme').premium_walk().plot()")
    assert [o["type"] for o in r["outputs"]] == ["png"]
    assert base64.b64decode(r["outputs"][0]["data"])[:4] == b"\x89PNG"


def test_text_does_not_carry_layer_terms_to_a_new_layer():
    t = call("parse_text", text="epi 100, 3 xs 2 ncb 10% el 1.8")["tower"]
    r = call("parse_text", tower=t, text="40 xs 10")
    assert r["text"] == "epi £100m, 40 xs 10"


def test_lines_and_risk_commands():
    t = call("parse_text", text="qs 20% limit 25, 15 xs 5 rate 0.75% el 0.9")["tower"]
    t = call("edit", tower=t, op={"type": "add_line", "name": "Credit", "epi": 200, "expected_loss_ratio": 0.5,
                                  "cession": 0.2, "volatility": 0.35})["tower"]
    r = call("edit", tower=t, op={"type": "add_line", "name": "Surety", "epi": 60, "expected_loss_ratio": 0.45,
                                  "cession": 0.3, "volatility": 0.5})
    assert r["programme"]["epi"] == 260 and [l["name"] for l in r["programme"]["lines"]] == ["Credit", "Surety"]
    assert next(l for l in r["layers"] if l["kind"] == "qs")["derived"]["premium"] == 58
    kept = call("parse_text", tower=r["tower"], text="qs 20% limit 25, 15 xs 5")
    assert len(kept["programme"]["lines"]) == 2
    risk = call("risk", tower=r["tower"], settings={"sims": 5000})
    assert risk["explore"]["x"]["key"] == "qs:Credit" and risk["explore"]["y"]["key"] == "qs:Surety"
    assert risk["explore"]["gross"]["capital"] > risk["explore"]["current"]["capital"]
    what_if = call("risk", tower=r["tower"], settings={"sims": 5000}, x="xl_retention", y="",
                   levers={"cessions": {"Credit": 0.4}})
    assert what_if["explore"]["y"] is None and what_if["explore"]["whatif"]["capital"] > 0
    both = call("edit", tower=r["tower"], op={"type": "set_cessions", "cessions": {"Credit": 0.5, "Surety": 0.2}})
    assert [l["cession"] for l in both["programme"]["lines"]] == [0.5, 0.2]
    t2 = call("edit", tower=r["tower"], op={"type": "update_line", "name": "Surety", "fields": {"cession": 0.4}})
    assert next(l for l in t2["programme"]["lines"] if l["name"] == "Surety")["cession"] == 0.4
