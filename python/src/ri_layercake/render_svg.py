"""SVG renderer: Jupyter output, SVG export and the How to use tab."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any

from .themes import WARN_HEX, resolve

if TYPE_CHECKING:
    from .model import Tower
    from .scene import Scene

FONT = "Calibri, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def _colour(palette: str, spec: dict[str, Any] | None) -> str:
    if not spec:
        return "none"
    if spec.get("status") == "error":
        return "#" + WARN_HEX
    return "#" + resolve(palette, spec["theme"], spec.get("tint", 0) or 0)


def _n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def render_svg(scene: Scene, canvas_only: bool = False, transparent: bool = False) -> str:
    d = scene.data
    pal = d["palette"]
    W, H = d["frame"]["w"], d["frame"]["h"]
    out: list[str] = []
    defs: dict[str, str] = {}

    def hatch(spec: dict[str, Any]) -> str:
        fg = resolve(pal, spec["theme"], spec.get("tint", 0) or 0)
        pid = f"hatch-{fg}"
        if pid not in defs:
            bg = resolve(pal, "bg1")
            defs[pid] = (f'<pattern id="{pid}" width="8" height="8" patternUnits="userSpaceOnUse" '
                         f'patternTransform="rotate(45)"><rect width="8" height="8" fill="#{bg}"/>'
                         f'<line x1="0" y1="0" x2="0" y2="8" stroke="#{fg}" stroke-width="3"/></pattern>')
        return f"url(#{pid})"

    for s in d["shapes"]:
        if s.get("export") is False and not canvas_only:
            continue
        t = s["type"]
        if t == "rect":
            fill = s.get("fill")
            fill_attr = hatch(fill) if fill and fill.get("pattern") else _colour(pal, fill)
            st = s.get("stroke")
            attrs = f'x="{_n(s["x"])}" y="{_n(s["y"])}" width="{_n(s["w"])}" height="{_n(s["h"])}" fill="{fill_attr}"'
            if st:
                attrs += f' stroke="{_colour(pal, st)}" stroke-width="{_n(st.get("w", 1))}"'
                if st.get("dash"):
                    attrs += ' stroke-dasharray="6 4"'
            out.append(f'<rect id="{escape(s["id"])}" {attrs}/>')
        elif t == "line":
            st = s.get("stroke") or {"theme": "tx1", "w": 1}
            dash = ' stroke-dasharray="8 5"' if st.get("dash") else ""
            out.append(f'<line id="{escape(s["id"])}" x1="{_n(s["x1"])}" y1="{_n(s["y1"])}" x2="{_n(s["x2"])}" '
                       f'y2="{_n(s["y2"])}" stroke="{_colour(pal, st)}" stroke-width="{_n(st.get("w", 1))}"{dash}/>')
        elif t == "text":
            anchor = s.get("anchor", "start")
            fill = _colour(pal, s.get("fill") or {"theme": "tx1"})
            spans = []
            for i, run in enumerate(s["runs"]):
                size = run.get("s", s.get("size", 14))
                dy = "0" if i == 0 else _n(size * 1.25)
                weight = ' font-weight="700"' if run.get("b") else ""
                colour = f' fill="#{WARN_HEX}"' if run.get("warn") else ""
                spans.append(f'<tspan x="{_n(s["x"])}" dy="{dy}" font-size="{_n(size)}"{weight}{colour}>'
                             f'{escape(run["t"])}</tspan>')
            out.append(f'<text id="{escape(s["id"])}" x="{_n(s["x"])}" y="{_n(s["y"])}" text-anchor="{anchor}" '
                       f'fill="{fill}">{"".join(spans)}</text>')

    if d.get("show_table"):
        out.append(_table_svg(d["table"], pal))

    bg = "" if transparent else f'<rect width="{W}" height="{H}" fill="#{resolve(pal, "bg1")}"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'font-family="{FONT}"><defs>{"".join(defs[k] for k in sorted(defs))}</defs>{bg}'
            + "".join(out) + "</svg>")


def _table_svg(table: dict[str, Any], pal: str) -> str:
    box = table["box"]
    rh = box["row_h"]
    widths = table["col_w"]
    size = box.get("size", min(13.0, rh * 0.55))
    head_bg, head_fg = resolve(pal, "accent1"), resolve(pal, "bg1")
    band, fg = resolve(pal, "bg2"), resolve(pal, "tx1")
    rows = [("head", table["columns"])] + [("body", r) for r in table["rows"]] + [("total", table["totals"])]
    parts = ['<g id="table">']
    y = box["y"]
    for i, (kind, cells) in enumerate(rows):
        if kind == "head":
            parts.append(f'<rect x="{_n(box["x"])}" y="{_n(y)}" width="{_n(box["w"])}" height="{_n(rh)}" '
                         f'fill="#{head_bg}"/>')
        elif kind == "body" and i % 2 == 0:
            parts.append(f'<rect x="{_n(box["x"])}" y="{_n(y)}" width="{_n(box["w"])}" height="{_n(rh)}" '
                         f'fill="#{band}"/>')
        elif kind == "total":
            parts.append(f'<line x1="{_n(box["x"])}" y1="{_n(y)}" x2="{_n(box["x"] + box["w"])}" y2="{_n(y)}" '
                         f'stroke="#{fg}" stroke-width="1"/>')
        x = box["x"]
        colour = head_fg if kind == "head" else fg
        weight = ' font-weight="700"' if kind in ("head", "total") else ""
        for j, cell in enumerate(cells):
            w = widths[j]
            if j == 0:
                tx, anchor = x + 8, "start"
            else:
                tx, anchor = x + w - 8, "end"
            parts.append(f'<text x="{_n(tx)}" y="{_n(y + rh / 2 + size * 0.35)}" font-size="{_n(size)}" '
                         f'text-anchor="{anchor}" fill="#{colour}"{weight}>{escape(cell)}</text>')
            x += w
        y += rh
    parts.append("</g>")
    return "".join(parts)


def html_with_table(tower: Tower) -> str:
    svg = tower.to_svg()
    diags = tower.validate()
    items = "".join(f"<li><b>{d.severity}</b> {escape(d.message)}</li>" for d in diags)
    notes = f'<ul style="font-size:12px;margin:4px 0">{items}</ul>' if items else ""
    return f'<div style="max-width:960px">{svg}{notes}</div>'


class TowerDisplay:
    """What tower.show(...) returns: draws with other view options in Jupyter."""

    def __init__(self, tower: Tower, **options: Any):
        self.tower = tower
        self.options = options

    def _repr_svg_(self) -> str:
        return self.tower.to_svg(**self.options)
