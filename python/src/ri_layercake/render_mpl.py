"""Matplotlib renderer: tower.plot() draws the same scene as the slide, as a Figure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .themes import WARN_HEX, resolve

if TYPE_CHECKING:
    from .scene import Scene
    from .walk import Walk

PX_TO_PT = 0.75
FONTS = ("Calibri", "Segoe UI", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans")
_font: dict[str, Any] | None = None


def _fontdict() -> dict[str, Any]:
    """The first of the slide's fonts that is installed, found once without warnings."""
    global _font
    if _font is None:
        from matplotlib import font_manager

        installed = {f.name for f in font_manager.fontManager.ttflist}
        _font = {"family": next((f for f in FONTS if f in installed), "sans-serif")}
    return _font


def _c(palette: str, spec: dict[str, Any] | None) -> str:
    if not spec:
        return "none"
    if spec.get("status") == "error":
        return "#" + WARN_HEX
    return "#" + resolve(palette, spec["theme"], spec.get("tint", 0) or 0)


def plot_scene(scene: Scene, ax: Any = None, canvas_only: bool = False) -> Any:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    d = scene.data
    pal = d["palette"]
    W, H = d["frame"]["w"], d["frame"]["h"]
    if ax is None:
        fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
        ax = fig.add_axes((0, 0, 1, 1))
    else:
        fig = ax.figure
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_axis_off()
    ax.add_patch(Rectangle((0, 0), W, H, facecolor=_c(pal, {"theme": "bg1"}), edgecolor="none", zorder=0))
    font = _fontdict()

    for z, s in enumerate(d["shapes"], start=1):
        if s.get("export") is False and not canvas_only:
            continue
        if s["type"] == "rect":
            fill = s.get("fill")
            st = s.get("stroke") or {}
            if fill and fill.get("pattern"):
                ax.add_patch(Rectangle((s["x"], s["y"]), s["w"], s["h"], facecolor=_c(pal, {"theme": "bg1"}),
                                       edgecolor=_c(pal, fill), hatch="////", linewidth=0, zorder=z))
            else:
                ax.add_patch(Rectangle((s["x"], s["y"]), s["w"], s["h"], facecolor=_c(pal, fill),
                                       edgecolor=_c(pal, st) if st else "none", linewidth=st.get("w", 0) * PX_TO_PT,
                                       linestyle="--" if st.get("dash") else "-", zorder=z))
        elif s["type"] == "line":
            st = s.get("stroke") or {"theme": "tx1", "w": 1}
            ax.plot([s["x1"], s["x2"]], [s["y1"], s["y2"]], color=_c(pal, st), linewidth=st.get("w", 1) * PX_TO_PT,
                    linestyle="--" if st.get("dash") else "-", zorder=z)
        elif s["type"] == "text":
            ha = {"start": "left", "middle": "center", "end": "right"}[s.get("anchor", "start")]
            y = s["y"]
            for i, run in enumerate(s["runs"]):
                size = run.get("s", s.get("size", 14))
                if i:
                    y += size * 1.25
                ax.text(s["x"], y, run["t"], ha=ha, va="baseline", fontsize=size * PX_TO_PT,
                        fontweight="bold" if run.get("b") else "normal",
                        color="#" + WARN_HEX if run.get("warn") else _c(pal, s.get("fill") or {"theme": "tx1"}),
                        zorder=z + 1000, fontdict=font)

    if d.get("show_table"):
        _table(ax, d["table"], pal, font)
    return fig


def _table(ax: Any, table: dict[str, Any], pal: str, font: dict[str, Any]) -> None:
    from matplotlib.patches import Rectangle

    box = table["box"]
    rh = box["row_h"]
    size = box.get("size", min(13.0, rh * 0.55)) * PX_TO_PT
    rows = [("head", table["columns"])] + [("body", r) for r in table["rows"]] + [("total", table["totals"])]
    y = box["y"]
    for i, (kind, cells) in enumerate(rows):
        if kind == "head":
            ax.add_patch(Rectangle((box["x"], y), box["w"], rh, facecolor=_c(pal, {"theme": "accent1"}), zorder=5000))
        elif kind == "body" and i % 2 == 0:
            ax.add_patch(Rectangle((box["x"], y), box["w"], rh, facecolor=_c(pal, {"theme": "bg2"}), zorder=5000))
        elif kind == "total":
            ax.plot([box["x"], box["x"] + box["w"]], [y, y], color=_c(pal, {"theme": "tx1"}), linewidth=0.75,
                    zorder=5001)
        x = box["x"]
        colour = _c(pal, {"theme": "bg1"}) if kind == "head" else _c(pal, {"theme": "tx1"})
        for j, cell in enumerate(cells):
            w = table["col_w"][j]
            ax.text(x + 8 if j == 0 else x + w - 8, y + rh / 2, cell, ha="left" if j == 0 else "right", va="center",
                    fontsize=size, color=colour, fontweight="bold" if kind != "body" else "normal", zorder=5002,
                    fontdict=font)
            x += w
        y += rh


def plot_walk(walk: Walk, ax: Any = None) -> Any:
    """The premium walk as a waterfall: EPI, each step up or down, the result."""
    import matplotlib.pyplot as plt

    t = walk.tower
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 5), dpi=100)
    else:
        fig = ax.figure
    unit = t.units
    epi = float(t.in_units(walk.epi))
    labels = ["EPI"] + [s.label + (" *" if s.approx else "") for s in walk.steps] + ["Result"]
    level = epi
    bottoms, heights, colours = [0.0], [epi], ["#0E5A8A"]
    for s in walk.steps:
        v = float(t.in_units(s.amount))
        bottoms.append(level if v >= 0 else level + v)
        heights.append(abs(v))
        colours.append("#3FA7B5" if v >= 0 else "#C4513A")
        level += v
    bottoms.append(0.0)
    heights.append(level)
    colours.append("#1B2733")
    xs = range(len(labels))
    ax.bar(xs, heights, bottom=bottoms, color=colours, width=0.62)
    for x, b, h in zip(xs, bottoms, heights):
        ax.text(x, b + h, f"{h:,.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(list(xs), labels, rotation=35, ha="right", fontsize=8.5)
    ax.set_ylabel(f"{t.currency} {unit}")
    margin = walk.margin
    title = f"Premium walk · result {level:,.1f}{unit}"
    if margin:
        title += f" · margin {float(margin) * 100:.1f}%"
    ax.set_title(title)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.text(0.01, 0.01, "* approximate", fontsize=7.5, color="#5b6876")
    fig.tight_layout()
    return fig
