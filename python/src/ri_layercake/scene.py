"""Layout: turn a tower and view options into a neutral scene.

The scene is a list of shapes in abstract slide coordinates, plus the table
rows. Every renderer (SVG, PPTX, the web canvas) draws the scene and nothing
else, so preview equals export. The same input always gives byte-identical
scene JSON.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from . import fmt
from .model import ONE, ZERO
from .table import table_data

if TYPE_CHECKING:
    from .model import Layer, Tower

SCENE_SCHEMA = "ri-layercake/scene@1"
FRAMES = {"slide_16x9": (1280, 720), "square": (720, 720), "tall": (720, 1280)}
MARGIN = 40
CHAR_W = 0.56  # average glyph width as a share of font size
LABEL_SIZES = ((14, 12), (12, 10.5))  # (main, detail); one shrink step


@dataclass(frozen=True)
class View:
    scale: Literal["schematic", "linear", "log"] = "schematic"
    labels: Literal["inside", "side", "auto"] = "auto"
    show_axis: bool | None = None  # None: on for linear and log
    show_retention: bool = True
    show_unplaced: bool = True
    palette: str = "ocean"
    frame: Literal["slide_16x9", "square", "tall"] = "slide_16x9"
    table: Literal["below", "right", "none"] = "below"
    loss: float | None = None  # in tower units; draws a loss line and callout

    @property
    def axis(self) -> bool:
        return self.scale != "schematic" if self.show_axis is None else self.show_axis

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> View:
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class Scene:
    def __init__(self, data: dict[str, Any], tower: Tower | None = None, view: View | None = None):
        self.data = data
        self.tower = tower
        self.view = view

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    @property
    def shapes(self) -> list[dict[str, Any]]:
        shapes: list[dict[str, Any]] = self.data["shapes"]
        return shapes

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))

    def _repr_svg_(self) -> str:
        from .render_svg import render_svg

        return render_svg(self)


def _r(v: float | Decimal) -> float:
    x = round(float(v), 2)
    return 0.0 if x == 0 else x


def _v(tower: Tower, value: Decimal) -> float:
    """A value in tower units as a JSON number."""
    return float(value / tower.factor)


def _text_w(text: str, size: float) -> float:
    return len(text) * size * CHAR_W


class _Mapper:
    """Maps values (full units) to y and back for one scale."""

    def __init__(self, kind: str, y_bottom: float, y_top: float, vmax: Decimal, vmin: Decimal | None = None,
                 floor: float = 0, breaks: list[tuple[Decimal, float]] | None = None):
        self.kind, self.yb, self.yt = kind, y_bottom, y_top
        self.vmax, self.vmin, self.floor = vmax, vmin, floor
        self.breaks = breaks or []

    def y(self, v: Decimal) -> float:
        if self.kind == "linear":
            return self.yb - float(v / self.vmax) * (self.yb - self.yt) if self.vmax else self.yb
        if self.kind == "log":
            vmin = self.vmin or Decimal(1)
            if v <= vmin:
                return self.yb - self.floor * float(v / vmin)
            span = math.log(float(self.vmax / vmin)) or 1.0
            return self.yb - self.floor - math.log(float(v / vmin)) / span * (self.yb - self.yt - self.floor)
        for (v0, y0), (v1, y1) in zip(self.breaks, self.breaks[1:]):
            if v0 <= v <= v1 and v1 > v0:
                return y0 + (y1 - y0) * float((v - v0) / (v1 - v0))
        return self.breaks[-1][1] if self.breaks and v > self.breaks[-1][0] else self.yb

    def to_dict(self, tower: Tower) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.kind, "y_bottom": _r(self.yb), "y_top": _r(self.yt)}
        if self.kind in ("linear", "log"):
            d["v_max"] = _v(tower, self.vmax)
        if self.kind == "log":
            d["v_min"] = _v(tower, self.vmin or Decimal(1))
            d["floor"] = _r(self.floor)
        if self.kind == "schematic":
            d["breaks"] = [[_v(tower, v), _r(y)] for v, y in self.breaks]
        return d


def _nice_step(span: float, target: int = 6) -> float:
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def layout(tower: Tower, view: View | None = None) -> Scene:
    view = view or View()
    W, H = FRAMES[view.frame]
    shapes: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []

    # Title block
    y = MARGIN
    if tower.title:
        shapes.append({"type": "text", "id": "title", "x": MARGIN, "y": y + 26, "anchor": "start",
                       "runs": [{"t": tower.title, "b": True}], "size": 28, "fill": {"theme": "tx1"},
                       "role": "title"})
        y += 44
    if tower.subtitle:
        shapes.append({"type": "text", "id": "subtitle", "x": MARGIN, "y": y + 16, "anchor": "start",
                       "runs": [{"t": tower.subtitle}], "size": 16, "fill": {"theme": "tx1", "tint": 0.35},
                       "role": "subtitle"})
        y += 30
    top = y + 20 if (tower.title or tower.subtitle) else MARGIN

    # Table box
    tdata = table_data(tower)
    n_rows = len(tdata.rows) + 2
    table_box = None
    left, right, bottom = float(MARGIN), float(W - MARGIN), float(H - MARGIN)
    if view.table == "below" and tdata.rows:
        row_h = max(14.0, min(24.0, (H * 0.42 - MARGIN) / n_rows))
        th = row_h * n_rows
        table_box = {"x": MARGIN, "y": _r(H - MARGIN - th), "w": W - 2 * MARGIN, "h": _r(th), "row_h": _r(row_h)}
        bottom = H - MARGIN - th - 28
    elif view.table == "right" and tdata.rows:
        tw = min(560.0, W * 0.46)
        row_h = max(14.0, min(26.0, (bottom - top) / n_rows))
        table_box = {"x": _r(W - MARGIN - tw), "y": _r(top), "w": _r(tw), "h": _r(row_h * n_rows),
                     "row_h": _r(row_h)}
        right = W - MARGIN - tw - 32

    bands = [l for l in tower.layers if l.kind == "xl" or (l.kind == "retention" and view.show_retention)]
    q = tower.qs
    sls = list(tower.sl_layers)
    if not bands and q is None and not sls:
        shapes.append({"type": "text", "id": "empty", "x": _r((left + right) / 2), "y": _r((top + bottom) / 2),
                       "anchor": "middle", "runs": [{"t": "Add a layer to start your tower"}], "size": 16,
                       "fill": {"theme": "tx1", "tint": 0.5}, "role": "empty", "export": False})
        return _finish(tower, view, W, H, shapes, hits, None, tdata, table_box)

    # Horizontal geometry: [QS column if side by side] [axis + XL tower + side labels] [stop loss column]
    stacked = tower.arrangement == "stacked"
    axis_w = 72 if view.axis and bands else 0
    sl_w = 200.0 if sls else 0.0
    sl_gap = 36.0 if sls else 0.0
    qs_w = 130.0 if (q is not None and not stacked) else 0.0
    qs_gap = 8.0 if qs_w else 0.0
    area_w = right - left
    side_w = 220 if view.labels == "side" else 0
    block_w = min(560.0, area_w - axis_w - side_w - sl_w - sl_gap - qs_w - qs_gap)
    if view.labels == "auto":
        side_w = 0  # decided after heights are known

    # A stacked QS sits as a slab under the XL tower; the tower stands on it.
    slab_h = 58.0 if (q is not None and stacked) else 0.0
    tower_bottom = bottom - slab_h

    mapper: _Mapper | None = None
    rects: dict[str, tuple[float, float, float]] = {}
    if bands:
        mapper, rects = _vertical(tower, bands, view, top, tower_bottom)
        needs_side = view.labels == "side" or (
            view.labels != "inside" and any(h < _inside_height(LABEL_SIZES[-1]) for _, _, h in rects.values()))
        if needs_side and side_w == 0:
            side_w = 220
            block_w = min(block_w, area_w - axis_w - side_w - sl_w - sl_gap - qs_w - qs_gap)
    group_w = qs_w + qs_gap + axis_w + block_w + side_w + sl_gap + sl_w
    gx = left + (area_w - group_w) / 2
    bx = gx + qs_w + qs_gap + axis_w

    columns = _columns(bands) if view.scale != "schematic" else {}
    xl_ids = [l.id for l in tower.xl_layers]
    n_xl = len(xl_ids)
    for l in bands:
        y_top, y_bot, h = rects[l.id]
        col, ncol = columns.get(l.id, (0, 1))
        w = block_w / ncol if ncol > 1 else block_w
        x = bx + col * w
        _layer_shapes(tower, view, l, x, y_top, w, h, xl_ids, n_xl, shapes, hits, mapper, bx + block_w)  # type: ignore[arg-type]

    if bands:
        _spread_side_labels(shapes, top, tower_bottom, bx + block_w, rects)
        _gap_overlap_shapes(tower, view, bands, rects, mapper, bx, block_w, shapes)  # type: ignore[arg-type]

    if q is not None:
        if stacked:
            _qs_slab(tower, q, bx, tower_bottom + 10, block_w, slab_h - 10, shapes, hits, bool(bands))
        else:
            qs_top = mapper.y(min(q.limit, mapper.vmax)) if mapper is not None else top
            _qs_column(tower, q, gx, qs_top, qs_w, bottom - qs_top, shapes, hits)
            if bands:
                retained = fmt.pct(ONE - (q.cession or ZERO))
                shapes.append({"type": "text", "id": "xl.caption", "x": _r(bx + block_w / 2), "y": _r(bottom + 16),
                               "anchor": "middle", "runs": [{"t": f"XL on the retained {retained}: attachment and "
                                                              f"limit × {retained}", "s": 10.5}],
                               "size": 10.5, "fill": {"theme": "tx1", "tint": 0.35}, "role": "caption"})

    if sls:
        _sl_column(tower, sls, bx + block_w + side_w + sl_gap, top, sl_w, bottom, shapes, hits)

    if view.axis and bands and mapper is not None:
        axis_shapes: list[dict[str, Any]] = []
        _axis(tower, view, bands, mapper, bx, block_w, axis_shapes)
        first_layer = next(i for i, s in enumerate(shapes) if s.get("layer"))
        shapes[first_layer:first_layer] = axis_shapes

    if view.loss is not None and mapper is not None:
        _loss_line(tower, view, mapper, bx, block_w, shapes)

    return _finish(tower, view, W, H, shapes, hits, mapper, tdata, table_box)


def _qs_slab(tower: Tower, q: Layer, x: float, y: float, w: float, h: float, shapes: list[dict[str, Any]],
             hits: list[dict[str, Any]], under_tower: bool) -> None:
    """Stacked QS: ceded share on the left, retained share (what flows into the XL tower) on the right."""
    c = float(q.cession or ZERO)
    cw = w * c
    shapes.append({"type": "rect", "id": f"{q.id}.block", "layer": q.id, "x": _r(x), "y": _r(y), "w": _r(cw),
                   "h": _r(h), "fill": {"theme": "accent3", "tint": 0}, "stroke": {"theme": "bg1", "w": 1.5},
                   "role": "qs"})
    shapes.append({"type": "rect", "id": f"{q.id}.retained", "layer": q.id, "x": _r(x + cw), "y": _r(y),
                   "w": _r(w - cw), "h": _r(h), "fill": {"theme": "accent3", "tint": 0.8},
                   "stroke": {"theme": "bg1", "w": 1.5}, "role": "qs_retained"})
    if q.share < 1:
        shapes.append({"type": "rect", "id": f"{q.id}.unplaced", "layer": q.id, "x": _r(x + cw * float(q.share)),
                       "y": _r(y), "w": _r(cw * (1 - float(q.share))), "h": _r(h),
                       "fill": {"pattern": "hatch", "theme": "accent3", "tint": 0},
                       "stroke": {"theme": "bg1", "w": 1.5}, "role": "unplaced"})
    main = f"QS {fmt.pct(q.cession)} ceded"
    detail = f"limit {fmt.amount(tower, q.limit)}"
    if q.agg_limit is not None:
        detail += f" · agg {fmt.amount(tower, q.agg_limit)}"
    fits = cw >= _text_w(main, 13) + 12
    detail_fits = fits and cw >= _text_w(detail, 10.5) + 12
    runs: list[dict[str, Any]] = [{"t": main, "b": True, "s": 13}]
    if detail_fits:
        runs.append({"t": detail, "s": 10.5})
    shapes.append({"type": "text", "id": f"{q.id}.label", "layer": q.id,
                   "x": _r(x + cw / 2 if fits else x + 8), "y": _r(y + h / 2 + (-2 if detail_fits else 5)),
                   "anchor": "middle" if fits else "start", "runs": runs, "size": 13,
                   "fill": {"theme": "bg1"} if fits else {"theme": "tx1"}, "role": "label"})
    retained = fmt.pct(ONE - (q.cession or ZERO))
    note = f"{retained} retained, into the XL layers" if under_tower else f"{retained} retained"
    note_runs: list[dict[str, Any]] = [{"t": note, "s": 11.5}]
    if not detail_fits:
        note_runs.append({"t": f"QS {detail}", "s": 10.5})
    shapes.append({"type": "text", "id": f"{q.id}.retained.label", "layer": q.id, "x": _r(x + cw + (w - cw) / 2),
                   "y": _r(y + h / 2 + (4 if detail_fits else -2)), "anchor": "middle", "runs": note_runs,
                   "size": 11.5, "fill": {"theme": "tx1"}, "role": "label"})
    hits.append({"layer": q.id, "edge": "body", "x": _r(x), "y": _r(y), "w": _r(w), "h": _r(h)})


def _qs_column(tower: Tower, q: Layer, x: float, y: float, w: float, h: float, shapes: list[dict[str, Any]],
               hits: list[dict[str, Any]]) -> None:
    """Side by side QS: its own column from 0 to the QS limit, beside the XL tower."""
    shapes.append({"type": "rect", "id": f"{q.id}.block", "layer": q.id, "x": _r(x), "y": _r(y), "w": _r(w),
                   "h": _r(max(h, 30)), "fill": {"theme": "accent3", "tint": 0}, "stroke": {"theme": "bg1", "w": 1.5},
                   "role": "qs"})
    if q.share < 1:
        ph = max(h, 30) * (1 - float(q.share))
        shapes.append({"type": "rect", "id": f"{q.id}.unplaced", "layer": q.id, "x": _r(x), "y": _r(y), "w": _r(w),
                       "h": _r(ph), "fill": {"pattern": "hatch", "theme": "accent3", "tint": 0},
                       "stroke": {"theme": "bg1", "w": 1.5}, "role": "unplaced"})
    runs = [{"t": f"QS {fmt.pct(q.cession)}", "b": True, "s": 13},
            {"t": f"limit {fmt.amount(tower, q.limit)}", "s": 10.5}]
    if q.agg_limit is not None:
        runs.append({"t": f"agg {fmt.amount(tower, q.agg_limit)}", "s": 10.5})
    shapes.append({"type": "text", "id": f"{q.id}.label", "layer": q.id, "x": _r(x + w / 2),
                   "y": _r(y + max(h, 30) / 2 - 6), "anchor": "middle", "runs": runs, "size": 13,
                   "fill": {"theme": "bg1"}, "role": "label"})
    hits.append({"layer": q.id, "edge": "body", "x": _r(x), "y": _r(y), "w": _r(w), "h": _r(max(h, 30))})


def _sl_column(tower: Tower, sls: list[Layer], x: float, top: float, w: float, bottom: float,
               shapes: list[dict[str, Any]], hits: list[dict[str, Any]]) -> None:
    """Stop loss: a column of layers on the loss ratio, labelled in % of EPI and amounts."""
    shapes.append({"type": "text", "id": "sl.header", "x": _r(x), "y": _r(top + 12), "anchor": "start",
                   "runs": [{"t": "Stop loss", "b": True, "s": 13}, {"t": "annual aggregate, % of EPI", "s": 10.5}],
                   "size": 13, "fill": {"theme": "tx1"}, "role": "caption"})
    ordered = sorted(sls, key=lambda s: (s.attachment, s.limit))
    avail = bottom - (top + 44)
    h = min(80.0, avail / len(ordered))
    y = bottom
    n = len(ordered)
    for i, s in enumerate(ordered):
        tint = round(0.5 * i / (n - 1), 2) if n > 1 else 0.0
        y -= h
        shapes.append({"type": "rect", "id": f"{s.id}.block", "layer": s.id, "x": _r(x), "y": _r(y), "w": _r(w),
                       "h": _r(h), "fill": {"theme": "accent5", "tint": tint}, "stroke": {"theme": "bg1", "w": 1.5},
                       "role": "sl"})
        if s.share < 1:
            pw = w * float(s.share)
            shapes.append({"type": "rect", "id": f"{s.id}.unplaced", "layer": s.id, "x": _r(x + pw), "y": _r(y),
                           "w": _r(w - pw), "h": _r(h), "fill": {"pattern": "hatch", "theme": "accent5", "tint": tint},
                           "stroke": {"theme": "bg1", "w": 1.5}, "role": "unplaced"})
        runs: list[dict[str, Any]] = [{"t": f"{fmt.pct(s.limit)} xs {fmt.pct(s.attachment)}", "b": True, "s": 13}]
        amounts = fmt.sl_amounts(tower, s)
        if amounts and h >= 40:
            runs.append({"t": amounts, "s": 10.5})
        if s.share < 1 and h >= 54:
            runs.append({"t": f"{fmt.pct(s.share)} placed", "s": 10.5})
        lines_h = sum(r["s"] * 1.25 for r in runs)
        shapes.append({"type": "text", "id": f"{s.id}.label", "layer": s.id, "x": _r(x + w / 2),
                       "y": _r(y + h / 2 - lines_h / 2 + 13), "anchor": "middle", "runs": runs, "size": 13,
                       "fill": {"theme": "tx1"} if tint >= 0.35 else {"theme": "bg1"}, "role": "label"})
        hits.append({"layer": s.id, "edge": "body", "x": _r(x), "y": _r(y), "w": _r(w), "h": _r(h)})


def _spread_side_labels(shapes: list[dict[str, Any]], top: float, bottom: float, right_edge: float,
                        rects: dict[str, tuple[float, float, float]]) -> None:
    """Push side labels apart so they never overlap; add a leader line when one moves."""
    side = sorted((s for s in shapes if s.get("side")), key=lambda s: -s["y"])
    if not side:
        return
    heights = {s["id"]: sum(r["s"] * 1.25 for r in s["runs"]) for s in side}
    gap = 4.0
    # Bottom-up pass: each label sits at or above the one below it.
    floor = bottom + 12
    for s in side:
        h = heights[s["id"]]
        first = s["runs"][0]["s"]
        box_bottom = min(s["y"] - first + h, floor)
        s["y"] = _r(box_bottom - h + first)
        floor = box_bottom - h - gap
    # Top-down pass keeps the stack inside the tower area.
    ceiling = top
    for s in reversed(side):
        first = s["runs"][0]["s"]
        box_top = s["y"] - first
        if box_top < ceiling:
            s["y"] = _r(ceiling + first)
        ceiling = s["y"] - first + heights[s["id"]] + gap
    for s in side:
        y0, _, h = rects[s["layer"]]
        mid = y0 + h / 2
        label_mid = s["y"] - s["runs"][0]["s"] + heights[s["id"]] / 2
        if abs(label_mid - mid) > 2:
            s["x"] = _r(right_edge + 28)
            idx = shapes.index(s)
            shapes.insert(idx, {"type": "line", "id": f"{s['layer']}.leader", "layer": s["layer"],
                                "x1": _r(right_edge + 2), "y1": _r(mid), "x2": _r(right_edge + 24),
                                "y2": _r(label_mid), "stroke": {"theme": "tx1", "w": 0.75, "tint": 0.5},
                                "role": "leader"})


def _inside_height(sizes: tuple[float, float]) -> float:
    main, detail = sizes
    return main * 1.25 + 6


def _vertical(tower: Tower, bands: list[Layer], view: View, top: float, bottom: float
              ) -> tuple[_Mapper, dict[str, tuple[float, float, float]]]:
    rects: dict[str, tuple[float, float, float]] = {}
    vmax = max(l.exhaust for l in bands)
    if view.loss is not None:
        vmax = max(vmax, tower.amount(view.loss))
    if view.scale == "linear":
        m = _Mapper("linear", bottom, top, vmax)
    elif view.scale == "log":
        edges = sorted({e for l in bands for e in (l.attachment, l.exhaust) if e > 0})
        vmin = edges[0] if edges else Decimal(1)
        floor = 36.0 if any(l.attachment == 0 for l in bands) else 0.0
        if vmax <= vmin:
            m = _Mapper("linear", bottom, top, vmax)
        else:
            m = _Mapper("log", bottom, top, vmax, vmin, floor)
    else:
        return _schematic(tower, bands, top, bottom)
    for l in bands:
        yt, yb = m.y(l.exhaust), m.y(l.attachment)
        rects[l.id] = (yt, yb, yb - yt)
    return m, rects


def _schematic(tower: Tower, bands: list[Layer], top: float, bottom: float
               ) -> tuple[_Mapper, dict[str, tuple[float, float, float]]]:
    """Equal-height blocks stacked in attachment order, with half-height gap slots."""
    ordered = sorted(bands, key=lambda l: (l.attachment, l.limit))
    slots: list[tuple[str, Decimal, Decimal, float]] = []  # (layer id or "", from, to, weight)
    reach = Decimal(0) if ordered[0].attachment == 0 else ordered[0].attachment
    for l in ordered:
        if l.attachment > reach and slots:
            slots.append(("", reach, l.attachment, 0.5))
        slots.append((l.id, l.attachment, l.exhaust, 1.0))
        reach = max(reach, l.exhaust)
    total = sum(s[3] for s in slots)
    slot_h = min((bottom - top) / total, 96.0)
    used = slot_h * total
    y = bottom - ((bottom - top) - used) / 2
    rects: dict[str, tuple[float, float, float]] = {}
    breaks: list[tuple[Decimal, float]] = []
    for lid, v0, v1, weight in slots:
        h = slot_h * weight
        if lid:
            rects[lid] = (y - h, y, h)
        if not breaks or v0 >= breaks[-1][0]:
            breaks.append((v0, y))
            breaks.append((v1, y - h))
        y -= h
    m = _Mapper("schematic", bottom, top, max(l.exhaust for l in bands), breaks=breaks)
    return m, rects


def _columns(bands: list[Layer]) -> dict[str, tuple[int, int]]:
    """Side-by-side columns for layers that overlap in to-scale views."""
    ordered = sorted(bands, key=lambda l: (l.attachment, l.limit))
    groups: list[list[Layer]] = []
    reach = None
    for l in ordered:
        if reach is None or l.attachment >= reach:
            groups.append([l])
            reach = l.exhaust
        else:
            groups[-1].append(l)
            reach = max(reach, l.exhaust)
    out: dict[str, tuple[int, int]] = {}
    for g in groups:
        if len(g) == 1:
            continue
        ends: list[Decimal] = []
        assign: dict[str, int] = {}
        for l in g:
            for i, e in enumerate(ends):
                if l.attachment >= e:
                    ends[i] = l.exhaust
                    assign[l.id] = i
                    break
            else:
                ends.append(l.exhaust)
                assign[l.id] = len(ends) - 1
        for lid, c in assign.items():
            out[lid] = (c, len(ends))
    return out


def _layer_shapes(tower: Tower, view: View, l: Layer, x: float, y: float, w: float, h: float,
                  xl_ids: list[str], n_xl: int, shapes: list[dict[str, Any]], hits: list[dict[str, Any]],
                  mapper: _Mapper, right_edge: float) -> None:
    is_ret = l.kind == "retention"
    if is_ret:
        fill: dict[str, Any] = {"theme": "tx1", "tint": 0.88}
        stroke: dict[str, Any] = {"theme": "tx1", "w": 1, "tint": 0.4, "dash": "dash"}
        text_fill = {"theme": "tx1"}
    else:
        i = xl_ids.index(l.id)
        tint = round(0.6 * i / (n_xl - 1), 2) if n_xl > 1 else 0.0
        fill = {"theme": "accent1", "tint": tint}
        stroke = {"theme": "bg1", "w": 1.5}
        text_fill = {"theme": "bg1"} if tint < 0.35 else {"theme": "tx1"}

    shapes.append({"type": "rect", "id": f"{l.id}.block", "layer": l.id, "x": _r(x), "y": _r(y),
                   "w": _r(w), "h": _r(h), "fill": fill, "stroke": stroke,
                   "role": "retention" if is_ret else "layer"})

    placed_w = w
    if not is_ret and view.show_unplaced and l.placed < 1:
        placed_w = w * float(max(l.placed, Decimal(0)))
        shapes.append({"type": "rect", "id": f"{l.id}.unplaced", "layer": l.id, "x": _r(x + placed_w),
                       "y": _r(y), "w": _r(w - placed_w), "h": _r(h),
                       "fill": {"pattern": "hatch", "theme": fill["theme"], "tint": fill.get("tint", 0)},
                       "stroke": stroke, "role": "unplaced"})

    # Label: try inside at full size, shrink one step, then move beside the block.
    main = fmt.layer_label(tower, l)
    details = [] if is_ret else [tower.display_name(l)]
    if not is_ret and l.placed != 1:
        details.append(f"{fmt.pct(l.placed)} placed")
    if l.reinstatements is not None:
        details.append(fmt.reinst(l))
    if is_ret and l.name:
        main = f"{l.name} {fmt.amount(tower, l.limit)}"
    detail = " · ".join(details)
    over = l.placed > 1

    label = None
    room_w = max(placed_w, w * 0.5) - 16
    if view.labels != "side":
        for sizes in LABEL_SIZES if view.labels == "auto" else LABEL_SIZES + ((10, 9),):
            ms, ds = sizes
            two = detail and h >= ms * 1.25 + ds * 1.25 + 8 and _text_w(detail, ds) <= room_w
            one = h >= ms * 1.25 + 4 or view.labels == "inside"
            if (two or one) and _text_w(main, ms) <= room_w:
                runs: list[dict[str, Any]] = [{"t": main, "b": True, "s": ms}]
                if two:
                    runs.append({"t": detail, "s": ds, **({"warn": True} if over else {})})
                cx = x + (placed_w if placed_w >= w * 0.5 else w) / 2
                lines_h = sum(r["s"] * 1.25 for r in runs)
                label = {"type": "text", "id": f"{l.id}.label", "layer": l.id, "x": _r(cx),
                         "y": _r(y + h / 2 - lines_h / 2 + ms), "anchor": "middle", "runs": runs,
                         "size": ms, "fill": text_fill, "role": "label"}
                break
    if label is None:
        runs = [{"t": main, "b": True, "s": 12}]
        if detail:
            runs.append({"t": detail, "s": 10.5, **({"warn": True} if over else {})})
        lines_h = sum(r["s"] * 1.25 for r in runs)
        label = {"type": "text", "id": f"{l.id}.label", "layer": l.id, "x": _r(right_edge + 12),
                 "y": _r(y + h / 2 - lines_h / 2 + 12), "anchor": "start", "runs": runs, "size": 12,
                 "fill": {"theme": "tx1"}, "role": "label", "side": True}
    shapes.append(label)

    # Hit regions use the engine's scale so drag-to-value is exact.
    per_px = float(l.limit / tower.factor) / h if h else 0.0
    edges = [("top", y, l.exhaust)]
    if not is_ret:
        edges.append(("bottom", y + h, l.attachment))
    for edge, ey, value in edges:
        hits.append({"layer": l.id, "edge": edge, "x": _r(x), "w": _r(w), "y": _r(ey),
                     "value": _v(tower, value), "per_px": _r(per_px * 1000) / 1000})
    hits.append({"layer": l.id, "edge": "body", "x": _r(x), "y": _r(y), "w": _r(w), "h": _r(h)})
    if not is_ret:
        hits.append({"layer": l.id, "edge": "placed", "x": _r(x + placed_w), "y": _r(y), "h": _r(h),
                     "x0": _r(x), "w": _r(w), "value": float(l.placed)})


def _gap_overlap_shapes(tower: Tower, view: View, bands: list[Layer], rects: dict[str, tuple[float, float, float]],
                        mapper: _Mapper, bx: float, bw: float, shapes: list[dict[str, Any]]) -> None:
    from .validate import _chain

    ids = {l.id for l in bands}
    for lower, nxt, top in _chain(tower):
        if lower.id not in ids or nxt.id not in ids:
            continue
        if nxt.attachment > top:
            y0 = rects[lower.id][0] if view.scale == "schematic" else mapper.y(top)
            y1 = rects[nxt.id][1] if view.scale == "schematic" else mapper.y(nxt.attachment)
            key = f"gap:{lower.id}:{nxt.id}"
            accepted = key in tower.accepted
            label = ("Unreinsured " if accepted else "Gap ") + fmt.amount(tower, nxt.attachment - top)
            shapes.append({"type": "rect", "id": f"gap.{lower.id}.{nxt.id}", "x": _r(bx), "y": _r(y1),
                           "w": _r(bw), "h": _r(y0 - y1), "fill": None,
                           "stroke": {"theme": "tx1", "w": 1, "tint": 0.3, "dash": "dash"},
                           "role": "gap", "key": key, "layers": [lower.id, nxt.id]})
            if y0 - y1 >= 12:
                shapes.append({"type": "text", "id": f"gap.{lower.id}.{nxt.id}.label", "x": _r(bx + bw / 2),
                               "y": _r((y0 + y1) / 2 + 4), "anchor": "middle", "runs": [{"t": label, "s": 11}],
                               "size": 11, "fill": {"theme": "tx1", "tint": 0.3}, "role": "gap_label"})
        elif nxt.attachment < top:
            key = f"overlap:{lower.id}:{nxt.id}"
            if key in tower.accepted:
                continue
            if view.scale == "schematic":
                y0 = min(rects[lower.id][0], rects[nxt.id][0])
                y1 = max(rects[lower.id][1], rects[nxt.id][1])
            else:
                y0, y1 = mapper.y(min(top, nxt.exhaust)), mapper.y(nxt.attachment)
            shapes.append({"type": "rect", "id": f"overlap.{lower.id}.{nxt.id}", "x": _r(bx - 4),
                           "y": _r(y0), "w": _r(bw + 8), "h": _r(y1 - y0), "fill": None,
                           "stroke": {"status": "error", "w": 2}, "role": "overlap", "key": key,
                           "layers": [lower.id, nxt.id], "export": False})


def _axis(tower: Tower, view: View, bands: list[Layer], mapper: _Mapper, bx: float, bw: float,
          shapes: list[dict[str, Any]]) -> None:
    ax = bx - 16
    shapes.append({"type": "line", "id": "axis.y", "x1": _r(ax), "y1": _r(mapper.yb), "x2": _r(ax),
                   "y2": _r(mapper.yt), "stroke": {"theme": "tx1", "w": 1, "tint": 0.4}, "role": "axis"})
    if view.scale == "linear":
        vmax = float(mapper.vmax / tower.factor)
        step = _nice_step(vmax)
        ticks = [Decimal(str(round(i * step, 6))) for i in range(int(vmax / step + 1e-9) + 1)]
    elif view.scale == "log":
        lo = float((mapper.vmin or Decimal(1)) / tower.factor)
        hi = float(mapper.vmax / tower.factor)
        ticks = [Decimal(0)] if mapper.floor else []
        for k in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1):
            for mlt in (1, 2, 5):
                v = mlt * 10 ** k
                if lo * 0.999 <= v <= hi * 1.001:
                    ticks.append(Decimal(str(v)))
    else:
        ticks = sorted({e / tower.factor for l in bands for e in (l.attachment, l.exhaust)})
    for i, t in enumerate(ticks):
        y = mapper.y(t * tower.factor)
        shapes.append({"type": "line", "id": f"axis.tick.{i}", "x1": _r(ax - 5), "y1": _r(y), "x2": _r(ax),
                       "y2": _r(y), "stroke": {"theme": "tx1", "w": 1, "tint": 0.4}, "role": "axis"})
        if view.scale != "schematic":
            shapes.append({"type": "line", "id": f"grid.{i}", "x1": _r(bx), "y1": _r(y), "x2": _r(bx + bw),
                           "y2": _r(y), "stroke": {"theme": "tx1", "w": 0.5, "tint": 0.85}, "role": "grid"})
        shapes.append({"type": "text", "id": f"axis.label.{i}", "x": _r(ax - 8), "y": _r(y + 4), "anchor": "end",
                       "runs": [{"t": fmt.amount(tower, t * tower.factor), "s": 11}], "size": 11,
                       "fill": {"theme": "tx1", "tint": 0.3}, "role": "axis_label"})


def _loss_line(tower: Tower, view: View, mapper: _Mapper, bx: float, bw: float,
               shapes: list[dict[str, Any]]) -> None:
    from .loss import drop_loss

    x = tower.amount(view.loss)  # type: ignore[arg-type]
    y = mapper.y(x)
    res = drop_loss(tower, x)
    shapes.append({"type": "line", "id": "loss.line", "x1": _r(bx - 24), "y1": _r(y), "x2": _r(bx + bw + 24),
                   "y2": _r(y), "stroke": {"theme": "accent6", "w": 2.5, "dash": "dash"}, "role": "loss"})
    shapes.append({"type": "text", "id": "loss.callout", "x": _r(bx + bw + 30), "y": _r(y - 6), "anchor": "start",
                   "runs": [{"t": f"Loss {fmt.amount(tower, x)}", "b": True, "s": 13},
                            {"t": f"Recovered {fmt.amount(tower, res.recovered)}", "s": 11},
                            {"t": f"Retained {fmt.amount(tower, res.retained + res.uncovered)}", "s": 11}],
                   "size": 13, "fill": {"theme": "accent6"}, "role": "loss_callout"})


def _finish(tower: Tower, view: View, W: int, H: int, shapes: list[dict[str, Any]], hits: list[dict[str, Any]],
            mapper: _Mapper | None, tdata: Any, table_box: dict[str, Any] | None) -> Scene:
    table: dict[str, Any] = tdata.to_dict()
    if table_box is not None:
        table["box"] = table_box
        table["col_w"] = _col_widths(tdata, table_box["w"])
        table_box["size"] = _table_font(tdata, table_box)
    data: dict[str, Any] = {
        "schema": SCENE_SCHEMA,
        "frame": {"w": W, "h": H, "name": view.frame},
        "palette": view.palette,
        "colors": _colors(view.palette),
        "shapes": shapes,
        "hit": hits,
        "scale": mapper.to_dict(tower) if mapper is not None else None,
        "table": table,
        "show_table": table_box is not None,
    }
    return Scene(data, tower, view)


def _table_font(tdata: Any, box: dict[str, Any]) -> float:
    """Largest font up to 13 that fits the row height and every column's text."""
    size = min(13.0, box["row_h"] * 0.55)
    chars = 0
    for j, col in enumerate(tdata.columns):
        chars += max([len(col)] + [len(r[j]) for r in tdata.rows] + [len(tdata.totals[j])])
    padding = 16 * len(tdata.columns)
    fit = (box["w"] - padding) / (chars * CHAR_W * 1.05)
    return _r(max(8.0, min(size, fit)))


def _colors(palette: str) -> dict[str, str]:
    from .themes import PALETTES, SLOT_ALIASES, WARN_HEX

    pal = PALETTES.get(palette, PALETTES["ocean"])
    out = {k: "#" + v for k, v in pal.items()}
    out.update({alias: "#" + pal[slot] for alias, slot in SLOT_ALIASES.items()})
    out["error"] = "#" + WARN_HEX
    return dict(sorted(out.items()))


def _col_widths(tdata: Any, total: float) -> list[float]:
    weights = []
    for j, col in enumerate(tdata.columns):
        longest = max([len(col)] + [len(r[j]) for r in tdata.rows] + [len(tdata.totals[j])])
        weights.append(max(longest, 4) + 3 + (3 if j == 0 else 0))
    s = sum(weights)
    widths = [_r(total * w / s) for w in weights]
    widths[-1] = _r(total - sum(widths[:-1]))
    return widths
