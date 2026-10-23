"""JSON bridge for the web app's engine worker: run(command, payload) -> JSON.

The worker calls ``run`` with a command name and a JSON payload; every
number the web app shows comes from here. Towers travel as tower@1 JSON;
amounts in edits are in the tower's display unit.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import traceback
from dataclasses import replace
from typing import Any

from . import __version__, fmt, gallery
from . import formulas as f
from .model import Reinstatements, Tower, terms_from_dict, terms_to_dict
from .parse import detect_mapping, parse_rows, split_rows
from .scene import View
from .validate import Fix, has_errors


def run(command: str, payload_json: str) -> str:
    payload = json.loads(payload_json) if payload_json else {}
    try:
        handler = COMMANDS[command]
    except KeyError:
        return json.dumps({"ok": False, "error": f"Unknown command {command!r}"})
    try:
        return json.dumps({"ok": True, **handler(payload)}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 - errors go back to the UI, never crash the worker
        return json.dumps({"ok": False, "error": str(e) or type(e).__name__})


# ---------------------------------------------------------------------- helpers

def _tower(payload: dict[str, Any]) -> Tower:
    data = payload.get("tower")
    return Tower.from_json(data) if data else Tower()


def _view(payload: dict[str, Any]) -> View:
    return View.from_dict(payload.get("view"))


def render(tower: Tower, view: View, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything the Playground needs after an edit."""
    diags = tower.validate(view)
    scene = tower.scene(view)
    out = {
        "tower": tower.to_dict(),
        "programme": _programme(tower),
        "formulas": f.FORMULAS,
        "warnings": [d.to_dict() for d in diags],
        "blocking": has_errors(diags),
        "scene": scene.to_dict(),
        "text": tower.to_text(),
        "layers": [_layer_row(tower, l) for l in tower.layers],
    }
    if extra:
        out.update(extra)
    return out


def _num(tower: Tower, v: Any) -> float | None:
    if v is None:
        return None
    if v.is_infinite():
        return None
    return float(tower.in_units(v))


def _ratio(v: Any) -> float | None:
    return None if v is None else float(v)


def _programme(t: Tower) -> dict[str, Any]:
    return {
        "epi": _num(t, t.epi), "counterparty_limit": _num(t, t.counterparty_limit),
        "arrangement": t.arrangement, "cover": t.cover, "currency": t.currency, "units": t.units,
        "internal_expenses": _ratio(t.internal_expenses), "expected_loss_ratio": _ratio(t.expected_loss_ratio),
        "brokerage_xl": _ratio(t.brokerage_xl), "brokerage_qs": _ratio(t.brokerage_qs), "tax": _ratio(t.tax),
        "defaults": {k: float(v) for k, v in f.DEFAULTS.items()},
        "lines": [{"name": l.name, "epi": _num(t, l.epi), "expected_loss_ratio": _ratio(l.expected_loss_ratio),
                   "cession": _ratio(l.cession), "volatility": _ratio(l.volatility)} for l in t.lines],
    }


def _layer_row(tower: Tower, l: Any) -> dict[str, Any]:
    def n(v: Any) -> float | None:
        return _num(tower, v)

    is_sl = l.kind == "sl"
    agg = f.agg_limit(tower, l)
    terms = terms_to_dict(l.terms)
    if l.terms.expected_loss is not None:
        terms["expected_loss"] = n(l.terms.expected_loss)
    return {
        "id": l.id, "kind": l.kind, "name": l.name, "display": tower.display_name(l),
        "label": fmt.layer_label(tower, l), "amounts": fmt.sl_amounts(tower, l) if is_sl else None,
        # Stop loss limit and attachment are loss ratios; everything else is in tower units.
        "limit": float(l.limit) if is_sl else n(l.limit),
        "attachment": float(l.attachment) if is_sl else n(l.attachment),
        "exhaust": float(l.exhaust) if is_sl else n(l.exhaust),
        "limit_amount": n(f.limit_amount(tower, l)), "attachment_amount": n(f.attachment_amount(tower, l)),
        "placed": float(l.placed), "order": float(l.order), "share": float(l.share),
        "cession": _ratio(l.cession),
        "premium": n(l.premium), "rol": _ratio(l.rol), "adj_rate": _ratio(l.adj_rate),
        "agg_limit": n(l.agg_limit),
        "derived": {
            "premium": n(f.premium(tower, l)), "rol": _ratio(f.rol(tower, l)), "adj_rate": _ratio(f.adj_rate(tower, l)),
            "agg_limit": n(agg), "agg_unlimited": bool(agg is not None and agg.is_infinite()),
            "payback": _ratio(f.payback(tower, l)), "no_claims_bonus": n(f.no_claims_bonus(tower, l)),
            "commission_rate": _ratio(f.commission_rate(l)) if l.kind == "qs" else None,
        },
        "priced_by": "premium" if l.premium is not None else "adj_rate" if l.adj_rate is not None
        else "rol" if l.rol is not None else ("cession" if l.kind == "qs" else None),
        "terms": terms,
        "effective_premium": n(f.premium(tower, l)),
        "rate_on_line": _ratio(f.rol(tower, l)),
        "reinstatements": fmt.reinst(l) or None,
        "written": None if l.written is None else float(l.written),
    }


# ---------------------------------------------------------------------- commands

def cmd_render(p: dict[str, Any]) -> dict[str, Any]:
    return render(_tower(p), _view(p))


def cmd_gallery(p: dict[str, Any]) -> dict[str, Any]:
    name = p.get("name")
    if not name:
        return {"gallery": [{"name": k, "title": v["title"], "subtitle": v["subtitle"]}
                            for k, v in gallery.GALLERY.items()]}
    return render(gallery.load(name), _view(p))


def cmd_parse_text(p: dict[str, Any]) -> dict[str, Any]:
    base = _tower(p)
    t = Tower.from_text(p.get("text", ""), currency=base.currency if p.get("tower") else None,
                        units=base.units if p.get("keep_units") else None)
    return render(_keep_programme(base, t), _view(p))


TEXTLESS_TERMS = ("profit_commission", "management_expenses", "sliding_scale")


def _keep_programme(base: Tower, t: Tower) -> Tower:
    """Text and pastes describe layers; keep the programme settings and any terms the shorthand cannot carry."""
    keep = {k: getattr(base, k) for k in ("title", "subtitle", "basis", "arrangement", "cover", "counterparty_limit",
                                           "internal_expenses", "expected_loss_ratio", "brokerage_xl",
                                           "brokerage_qs", "tax", "lines")}
    if t.epi is None:
        keep["epi"] = base.epi
    t = replace(t, **keep, diagnostics=t.diagnostics)
    old = {(l.id, l.kind): l for l in base.layers}
    layers = []
    for l in t.layers:
        prev = old.get((l.id, l.kind))
        if prev is not None:
            # Only terms the shorthand cannot express carry over; NCB, layer EL and commission come from the text.
            kept = {k: v for k, v in terms_to_dict(prev.terms).items() if k in TEXTLESS_TERMS}
            if kept:
                l = replace(l, terms=terms_from_dict(terms_to_dict(l.terms) | kept))
        layers.append(l)
    return replace(t, layers=tuple(layers))


def cmd_paste(p: dict[str, Any]) -> dict[str, Any]:
    text = p.get("text", "")
    rows = split_rows(text)
    base = _tower(p)
    is_table = not all(len(r) == 1 for r in rows)
    if not is_table:
        t = _keep_programme(base, Tower.from_paste(text))
        return render(t, _view(p), {"mapping": None})
    mapping = detect_mapping(rows)
    if p.get("mapping"):
        mapping.columns = {int(k): v for k, v in p["mapping"]["columns"].items() if v}
        if "header_row" in p["mapping"]:
            mapping.header_row = p["mapping"]["header_row"]
    t = _keep_programme(base, parse_rows(rows, mapping=mapping))
    width = max((len(r) for r in rows), default=0)
    header = rows[mapping.header_row] if mapping.header_row is not None else [f"Column {j + 1}" for j in range(width)]
    return render(t, _view(p), {"mapping": {
        **mapping.to_dict(), "headers": header + [""] * (width - len(header)), "width": width,
        "fields": ["limit", "attachment", "placed", "premium", "rol", "name", "combined", "written", "reinstatements"],
    }})


def cmd_edit(p: dict[str, Any]) -> dict[str, Any]:
    t = _tower(p)
    op = p["op"]
    kind = op["type"]
    if kind == "update":
        fields = dict(op["fields"])
        if isinstance(fields.get("reinstatements"), str):
            fields["reinstatements"] = _reinst(fields["reinstatements"])
        t = t.update(op["layer"], **fields)
    elif kind == "add_xl":
        t = t.add_xl(op["limit"], op["attachment"], placed=op.get("placed", 1), name=op.get("name"))
    elif kind == "add_qs":
        t = t.add_qs(op.get("cession", 0.2), op["limit"], agg_limit=op.get("agg_limit"))
    elif kind == "add_sl":
        t = t.add_sl(op.get("limit", 0.2), op.get("attachment", 0.8))
    elif kind == "programme":
        t = t.programme(**op["fields"])
    elif kind == "add_line":
        t = t.add_line(op["name"], op["epi"], expected_loss_ratio=op.get("expected_loss_ratio"),
                       cession=op.get("cession"), volatility=op.get("volatility"))
    elif kind == "update_line":
        t = t.update_line(op["name"], **op["fields"])
    elif kind == "remove_line":
        t = t.remove_line(op["name"])
    elif kind == "apply_levers":
        from . import risk

        t = risk.apply_levers(t, risk.Levers.from_dict(op["levers"], t))
    elif kind == "set_cessions":
        # One edit for several cessions, so applying a mix is a single step (and a single undo).
        for name, c in op["cessions"].items():
            if name == "*" and t.qs is not None:
                t = t.update(t.qs.id, cession=c)
            else:
                t = t.update_line(name, cession=c)
    elif kind == "terms":
        old = t.layer(op["layer"])
        merged = terms_to_dict(old.terms) | {k: v for k, v in op["terms"].items()}
        if "expected_loss" in op["terms"] and op["terms"]["expected_loss"] not in (None, ""):
            merged["expected_loss"] = str(t.amount(op["terms"]["expected_loss"]))
        merged = {k: v for k, v in merged.items() if v not in (None, "")}
        t = t.update(op["layer"], terms=terms_from_dict(merged))
    elif kind == "add_retention":
        t = t.add_retention(op["amount"])
    elif kind == "remove":
        t = t.remove(op["layer"])
    elif kind == "split":
        t = t.split(op["layer"], op["at"])
    elif kind == "merge":
        t = t.merge(op["a"], op["b"])
    elif kind == "insert":
        t = _insert(t, op["at"], op["limit"])
    elif kind == "move":
        t = _move(t, op["layer"], op["attachment"], op.get("shift_above", True))
    elif kind == "apply_fix":
        t = t.apply(Fix.from_dict(op["fix"]))
    elif kind == "meta":
        allowed = {k: v for k, v in op["fields"].items() if k in ("title", "subtitle", "currency", "units", "basis")}
        t = replace(t, **allowed)
    elif kind == "clear":
        t = Tower(currency=t.currency, units=t.units)
    else:
        raise ValueError(f"Unknown edit {kind!r}")
    return render(t, _view(p))


def _reinst(text: str) -> Reinstatements | None:
    from .parse import _parse_reinst

    return _parse_reinst(text) if text.strip() else None


def _insert(t: Tower, at: float, limit: float) -> Tower:
    """Insert a layer at a boundary; layers at or above it move up by its limit."""
    v, size = t.amount(at), t.amount(limit)
    shifted = [replace(l, attachment=l.attachment + size) if l.kind == "xl" and l.attachment >= v else l
               for l in t.layers]
    return t.with_layers(shifted).add_xl(limit, at)


def _move(t: Tower, layer_id: str, attachment: float, shift_above: bool) -> Tower:
    """Move a layer's attachment; layers above shift by the same amount to keep the stack contiguous."""
    old = t.layer(layer_id)
    new_att = t.amount(attachment)
    delta = new_att - old.attachment
    layers = []
    for l in t.layers:
        if l.id == layer_id:
            layers.append(replace(l, attachment=new_att))
        elif shift_above and l.kind == "xl" and l.attachment >= old.exhaust:
            layers.append(replace(l, attachment=l.attachment + delta))
        else:
            layers.append(l)
    return t.with_layers(layers)


def cmd_loss(p: dict[str, Any]) -> dict[str, Any]:
    """Per risk: one risk's exposure or loss through the programme."""
    t = _tower(p)
    r = t.drop_loss(p["amount"], p.get("line") or None)
    fills = {l.layer: (float(l.recovery_100 / l.limit_used) if l.limit_used else 0.0) for l in r.layers}
    return {"loss": r.to_dict(), "exhausted": [l.layer for l in r.layers if l.exhausted], "fills": fills}


def cmd_aggregate(p: dict[str, Any]) -> dict[str, Any]:
    """A year's aggregate loss: QS cession and terms, stop loss on the net loss ratio."""
    t = _tower(p)
    amount = p["amount"]
    if p.get("as_loss_ratio"):
        if t.epi is None:
            raise ValueError("Enter the gross EPI to use a loss ratio")
        amount = float(t.in_units(t.epi * f.to_decimal_ratio(amount)))
    a = t.aggregate(amount)
    fills = {s.layer: float(s.recovery_100 / s.limit_used) if s.limit_used else 0.0 for s in a.stop_loss}
    return {"aggregate": a.to_dict(), "fills": fills}


def cmd_portfolio(p: dict[str, Any]) -> dict[str, Any]:
    """Trapped exposure across a portfolio: median(0, E - A, L) per risk and layer."""
    t = _tower(p)
    if p.get("example"):
        res = t.portfolio([(rid, e * (10 ** 6) / float(t.factor)) for rid, e in gallery.EXAMPLE_PORTFOLIO])
    else:
        text = p.get("text", "")
        if p.get("base64"):
            import tempfile

            data = base64.b64decode(p["base64"])
            suffix = ".xlsx" if p.get("name", "").lower().endswith((".xlsx", ".xlsm")) else ".csv"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
                fh.write(data)
                text = fh.name
        res = t.portfolio(text)
    if not res.risks:
        raise ValueError("No risks found: paste or upload a table with an exposure (sum insured) column")
    return {"portfolio": res.to_dict()}


def cmd_walk(p: dict[str, Any]) -> dict[str, Any]:
    return {"walk": _tower(p).premium_walk().to_dict()}


def cmd_risk(p: dict[str, Any]) -> dict[str, Any]:
    """Loss ratio, margin, capital and RoC: no reinsurance, the programme, a what-if, and a map over two levers."""
    from . import risk

    t = _tower(p)
    s = risk.RiskSettings.from_dict(p.get("settings"))
    options = risk.lever_options(t, s)
    keys = [o["key"] for o in options]
    if not keys:
        sim = risk.simulate(t, s)
        k = float(t.factor)
        return {"levers": [], "gross": risk.gross(sim).to_dict(k), "current": risk.evaluate(sim).to_dict(k)}
    line_keys = [k for k in keys if k.startswith("qs:") and k != "qs:*"]
    default_x = line_keys[0] if len(line_keys) >= 2 else keys[0]
    default_y = line_keys[1] if len(line_keys) >= 2 else next((k for k in keys if k != default_x), None)
    x = p.get("x") if p.get("x") in keys else default_x
    y = p.get("y") if p.get("y") in keys and p.get("y") != x else (default_y if default_y != x else None)
    if p.get("y") == "":
        y = None
    levers = risk.Levers.from_dict(p.get("levers"), t)
    ex = risk.explore(t, str(x), y, levers, s)
    return {"levers": options, "explore": ex.to_dict()}


def cmd_export(p: dict[str, Any]) -> dict[str, Any]:
    t = _tower(p)
    view = _view(p)
    fmt_ = p.get("format", "pptx")
    if has_errors(t.validate()):
        raise ValueError("Fix the errors before exporting")
    if fmt_ == "svg":
        return {"text": _svg(t, view, bool(p.get("transparent"))), "mime": "image/svg+xml"}
    template = base64.b64decode(p["template"]) if p.get("template") else None
    data = t.to_pptx(view=view, template=template, table_slide=bool(p.get("table_slide")),
                     layout=p.get("layout") or None)
    assert isinstance(data, bytes)
    return {"base64": base64.b64encode(data).decode(),
            "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}


def _svg(t: Tower, view: View, transparent: bool) -> str:
    from .render_svg import render_svg

    return render_svg(t.scene(view), transparent=transparent)


def cmd_code(p: dict[str, Any]) -> dict[str, Any]:
    return {"code": _tower(p).to_code(_view(p))}


def cmd_version(p: dict[str, Any]) -> dict[str, Any]:
    return {"version": __version__}


# ---------------------------------------------------------------------- notebook kernel

_NAMESPACE: dict[str, Any] = {}


def cmd_reset(p: dict[str, Any]) -> dict[str, Any]:
    _NAMESPACE.clear()
    return {}


def cmd_run_cell(p: dict[str, Any]) -> dict[str, Any]:
    """Run a notebook cell in a shared namespace; return Jupyter-like outputs."""
    import ast
    import os

    code = p.get("code", "")
    os.environ.setdefault("MPLBACKEND", "Agg")
    outputs: list[dict[str, Any]] = []
    stdout = io.StringIO()
    before = _files()
    try:
        tree = ast.parse(code, mode="exec")
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            exec(compile(tree, "<cell>", "exec"), _NAMESPACE)  # noqa: S102 - the user's own cell, in their browser
            value = eval(compile(last, "<cell>", "eval"), _NAMESPACE) if last else None  # noqa: S307
        if stdout.getvalue():
            outputs.append({"type": "stream", "text": stdout.getvalue()})
        if value is not None and not _is_figure(value):
            outputs.append(_display(value))
        outputs.extend(_figures())
    except Exception:  # noqa: BLE001
        if stdout.getvalue():
            outputs.append({"type": "stream", "text": stdout.getvalue()})
        tb = traceback.format_exc().split("\n")
        tb = [ln for ln in tb if 'File "/lib/' not in ln]
        outputs.append({"type": "error", "text": "\n".join(tb)})
    files = []
    for path, mtime in _files().items():
        if before.get(path) != mtime:
            with open(path, "rb") as fh:
                files.append({"name": os.path.basename(path), "base64": base64.b64encode(fh.read()).decode()})
    tower = None
    for v in reversed(list(_NAMESPACE.values())):
        if isinstance(v, Tower):
            tower = v.to_dict()
            break
    return {"outputs": outputs, "files": files, "tower": tower}


def _is_figure(value: Any) -> bool:
    return type(value).__module__.startswith("matplotlib")


def _figures() -> list[dict[str, Any]]:
    """Every open matplotlib figure, as PNG, like Jupyter's inline backend; then close them."""
    import sys

    if "matplotlib.pyplot" not in sys.modules:
        return []
    import matplotlib.pyplot as plt

    out = []
    for num in plt.get_fignums():
        buf = io.BytesIO()
        plt.figure(num).savefig(buf, format="png", dpi=100, bbox_inches="tight")
        out.append({"type": "png", "data": base64.b64encode(buf.getvalue()).decode()})
    plt.close("all")
    return out


def _files() -> dict[str, float]:
    import os

    out = {}
    for name in os.listdir("."):
        if os.path.isfile(name) and os.path.splitext(name)[1] in (".pptx", ".svg", ".json", ".csv", ".txt"):
            out[os.path.abspath(name)] = os.path.getmtime(name)
    return out


def _display(value: Any) -> dict[str, Any]:
    for attr, kind in (("_repr_svg_", "svg"), ("_repr_html_", "html")):
        fn = getattr(value, attr, None)
        if fn is not None:
            try:
                data = fn()
            except Exception:  # noqa: BLE001
                continue
            if data:
                if kind == "html" and hasattr(value, "_repr_svg_") and isinstance(value, Tower):
                    continue
                return {"type": kind, "data": data, "tower": value.to_dict() if isinstance(value, Tower) else None}
    if hasattr(value, "to_html") and hasattr(value, "columns"):
        return {"type": "html", "data": value.to_html(index=False)}
    return {"type": "text", "text": repr(value)}


COMMANDS = {
    "render": cmd_render,
    "gallery": cmd_gallery,
    "parse_text": cmd_parse_text,
    "paste": cmd_paste,
    "edit": cmd_edit,
    "loss": cmd_loss,
    "aggregate": cmd_aggregate,
    "portfolio": cmd_portfolio,
    "walk": cmd_walk,
    "risk": cmd_risk,
    "export": cmd_export,
    "code": cmd_code,
    "version": cmd_version,
    "run_cell": cmd_run_cell,
    "reset": cmd_reset,
}
