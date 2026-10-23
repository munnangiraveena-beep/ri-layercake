"""Show code: Python that rebuilds a tower and view."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .fmt import plain
from .model import ONE, Terms, normalize
from .scene import View

if TYPE_CHECKING:
    from .model import Layer, Tower


def to_code(tower: Tower, view: View | None = None) -> str:
    def n(v: Decimal) -> str:
        return plain(normalize(v / tower.factor))

    def r(v: Decimal) -> str:
        return plain(normalize(v))

    def terms(l: Layer) -> str | None:
        t = l.terms
        if t == Terms():
            return None
        args = []
        for key in ("commission", "profit_commission", "management_expenses", "no_claims_bonus"):
            v = getattr(t, key)
            if v is not None:
                args.append(f"{key}={r(v)}")
        if t.expected_loss is not None:
            args.append(f"expected_loss={n(t.expected_loss)}")
        if t.sliding_scale is not None:
            ss = t.sliding_scale
            args.append(f"sliding_scale=lc.SlidingScale(min={r(ss.min)}, max={r(ss.max)}, "
                        f"lr_low={r(ss.lr_low)}, lr_high={r(ss.lr_high)})")
        return f"terms=lc.Terms({', '.join(args)})"

    def shares(l: Layer) -> list[str]:
        out = []
        if l.placed != ONE:
            out.append(f"placed={r(l.placed)}")
        if l.order != ONE:
            out.append(f"order={r(l.order)}")
        return out

    head = [f"currency={tower.currency!r}", f"units={tower.units!r}"]
    if tower.title:
        head.append(f"title={tower.title!r}")
    if tower.subtitle:
        head.append(f"subtitle={tower.subtitle!r}")
    lines = ["import ri_layercake as lc", "", "tower = (", f"    lc.Tower({', '.join(head)})"]
    prog = []
    for key in ("epi", "counterparty_limit"):
        v = getattr(tower, key)
        if v is not None:
            prog.append(f"{key}={n(v)}")
    for key in ("internal_expenses", "expected_loss_ratio", "brokerage_xl", "brokerage_qs", "tax"):
        v = getattr(tower, key)
        if v is not None:
            prog.append(f"{key}={r(v)}")
    if tower.arrangement != "stacked":
        prog.append(f"arrangement={tower.arrangement!r}")
    if tower.cover != "per_risk":
        prog.append(f"cover={tower.cover!r}")
    if prog:
        lines.append(f"    .programme({', '.join(prog)})")
    for l in tower.layers:
        if l.kind == "retention":
            lines.append(f"    .add_retention({n(l.limit)})")
            continue
        if l.kind == "qs":
            args = [r(l.cession if l.cession is not None else Decimal(0)), n(l.limit)]
            if l.agg_limit is not None:
                args.append(f"agg_limit={n(l.agg_limit)}")
            if l.premium is not None:
                args.append(f"premium={n(l.premium)}")
            args += shares(l)
        elif l.kind == "sl":
            args = [r(l.limit), r(l.attachment)]
            if l.premium is not None:
                args.append(f"premium={n(l.premium)}")
            if l.adj_rate is not None:
                args.append(f"adj_rate={r(l.adj_rate)}")
            if l.rol is not None:
                args.append(f"rol={r(l.rol)}")
            args += shares(l)
        else:
            args = [n(l.limit), n(l.attachment)]
            args += shares(l)
            if l.premium is not None:
                args.append(f"premium={n(l.premium)}")
            if l.rol is not None:
                args.append(f"rol={r(l.rol)}")
            if l.adj_rate is not None:
                args.append(f"adj_rate={r(l.adj_rate)}")
            if l.reinstatements is not None:
                ri = l.reinstatements
                args.append(f"reinstatements=lc.Reinstatements(count={ri.count!r}, rate={ri.rate!r})")
        tm = terms(l)
        if tm:
            args.append(tm)
        if l.name:
            args.append(f"name={l.name!r}")
        method = {"qs": "add_qs", "sl": "add_sl"}.get(l.kind, "add_xl")
        lines.append(f"    .{method}({', '.join(args)})")
    lines.append(")")
    for key in sorted(tower.accepted):
        lines.append(f"tower = tower.accept({key!r})")
    defaults = View()
    view = view or defaults
    opts = [f"{k}={getattr(view, k)!r}" for k in View.__dataclass_fields__
            if getattr(view, k) != getattr(defaults, k)]
    lines += ["", f"view = lc.View({', '.join(opts)})", "tower.scene(view)  # draws in Jupyter",
              'tower.to_pptx("tower.pptx", view=view)']
    return "\n".join(lines) + "\n"
