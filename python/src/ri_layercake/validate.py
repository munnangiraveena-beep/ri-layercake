"""Validation: diagnostics with severity, plain-language message and fixes.

Only true parse errors block export. Each fix carries a patch the engine
can apply, so the web app can show fix buttons in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from . import fmt
from .model import ONE, ZERO, Layer

if TYPE_CHECKING:
    from .model import Tower
    from .scene import View

Severity = Literal["error", "warning", "info"]

MAX_PLACEABLE_CESSION = Decimal("0.5")  # above this a quota share is hard to place


@dataclass(frozen=True)
class Fix:
    label: str
    op: Literal["update", "accept", "view"]
    layer: str | None = None
    fields: dict[str, Any] = field(default_factory=dict, hash=False)
    key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"label": self.label, "op": self.op}
        if self.layer is not None:
            d["layer"] = self.layer
        if self.fields:
            d["fields"] = {k: str(v) if isinstance(v, Decimal) else v for k, v in self.fields.items()}
        if self.key is not None:
            d["key"] = self.key
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fix:
        return cls(
            label=d["label"],
            op=d["op"],
            layer=d.get("layer"),
            fields=dict(d.get("fields", {})),
            key=d.get("key"),
        )


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    layers: tuple[str, ...] = ()
    fixes: tuple[Fix, ...] = ()
    span: tuple[int, int] | None = None
    key: str | None = None

    def __repr__(self) -> str:
        return f"Diagnostic({self.severity}, {self.message!r})"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "layers": list(self.layers),
            "fixes": [f.to_dict() for f in self.fixes],
        }
        if self.span is not None:
            d["span"] = list(self.span)
        if self.key is not None:
            d["key"] = self.key
        return d


def _accept(key: str, label: str) -> Fix:
    return Fix(label=label, op="accept", key=key)


def _chain(tower: Tower) -> list[tuple[Layer, Layer, Decimal]]:
    """Consecutive pairs (lower, next, top_so_far) up the excess of loss tower by attachment."""
    layers = sorted((l for l in tower.layers if l.kind in ("retention", "xl")), key=lambda l: (l.attachment, l.limit))
    pairs: list[tuple[Layer, Layer, Decimal]] = []
    if not layers:
        return pairs
    top_layer = layers[0]
    for nxt in layers[1:]:
        pairs.append((top_layer, nxt, top_layer.exhaust))
        if nxt.exhaust > top_layer.exhaust:
            top_layer = nxt
    return pairs


def validate(tower: Tower, view: View | None = None) -> list[Diagnostic]:
    from . import formulas as f

    out: list[Diagnostic] = list(tower.diagnostics)
    name = tower.display_name

    def a(v: Decimal) -> str:
        return fmt.amount(tower, v)

    for l in tower.layers:
        if l.limit <= 0 or l.attachment < 0:
            what = "a limit of zero or less" if l.limit <= 0 else "a negative attachment"
            out.append(Diagnostic("non_positive", "error", f"{name(l)} has {what}", (l.id,)))

    for lower, nxt, top in _chain(tower):
        if nxt.attachment > top:
            key = f"gap:{lower.id}:{nxt.id}"
            fixes = [
                Fix("Lower next attachment", "update", nxt.id,
                    {"attachment": top, "limit": nxt.exhaust - top}),
                Fix("Extend layer below", "update", lower.id,
                    {"limit": nxt.attachment - lower.attachment}),
                _accept(key, "Leave as unreinsured"),
            ]
            out.append(Diagnostic(
                "gap", "warning",
                f"Gap of {a(nxt.attachment - top)} between {name(lower)} (exhausts {a(top)}) "
                f"and {name(nxt)} (attaches {a(nxt.attachment)})",
                (lower.id, nxt.id), tuple(fixes), key=key,
            ))
        elif nxt.attachment < top:
            key = f"overlap:{lower.id}:{nxt.id}"
            fixes = []
            if nxt.exhaust > top:
                fixes.append(Fix("Raise upper attachment", "update", nxt.id,
                                 {"attachment": top, "limit": nxt.exhaust - top}))
            fixes.append(_accept(key, "Keep"))
            band = min(top, nxt.exhaust) - nxt.attachment
            out.append(Diagnostic(
                "overlap", "warning",
                f"{name(lower)} and {name(nxt)} both cover {a(band)} "
                f"from {a(nxt.attachment)} to {a(nxt.attachment + band)}",
                (lower.id, nxt.id), tuple(fixes), key=key,
            ))

    for l in tower.layers:
        if l.kind == "retention":
            continue
        if l.order > ONE:
            out.append(Diagnostic("share_over", "warning", f"{name(l)} has an order of {fmt.pct(l.order)}, over 100%",
                                  (l.id,), (Fix("Cap order at 100%", "update", l.id, {"order": ONE}),),
                                  key=f"order_over:{l.id}"))
        if l.placed > ONE:
            out.append(Diagnostic(
                "share_over", "warning", f"{name(l)} is {fmt.pct(l.placed)} placed, over 100%",
                (l.id,), (Fix("Cap at 100%", "update", l.id, {"placed": ONE}),),
                key=f"share_over:{l.id}",
            ))
        elif l.placed < ONE:
            out.append(Diagnostic(
                "share_under", "info", f"{name(l)} is {fmt.pct(l.placed)} placed", (l.id,),
                key=f"share_under:{l.id}",
            ))
        if l.order < ONE:
            kept = fmt.pct(ONE - l.order)
            out.append(Diagnostic("order_under", "info",
                                  f"{name(l)} has an order of {fmt.pct(l.order)}; the cedant keeps {kept}",
                                  (l.id,), key=f"order_under:{l.id}"))

    # Premium, rate on line and adjusted rate: any one prices the layer; entered ones must agree.
    for l in tower.layers:
        if l.kind in ("retention", "qs"):
            continue
        lim = f.limit_amount(tower, l)
        implied: list[tuple[str, str, Decimal]] = []
        if l.premium is not None:
            implied.append(("premium", "premium", l.premium))
        if l.rol is not None and lim:
            implied.append(("rol", "rate on line", l.rol * lim))
        if l.adj_rate is not None and tower.epi:
            implied.append(("adj_rate", "adjusted rate", l.adj_rate * tower.epi))
        if l.adj_rate is not None and not tower.epi:
            out.append(Diagnostic("epi_missing", "warning",
                                  f"{name(l)} is priced by adjusted rate; enter the gross EPI to derive its premium",
                                  (l.id,), key=f"epi_missing:{l.id}"))
        if len(implied) >= 2:
            values = [v for _, _, v in implied]
            lo, hi = min(values), max(values)
            if lo > 0 and (hi - lo) / lo > Decimal("0.005"):
                key = f"rol_mismatch:{l.id}"
                desc = ", ".join(f"{label} gives {a(v)}" for _, label, v in implied)
                price_fixes = tuple(
                    Fix(f"Use {label}", "update", l.id, {k: None for k, _, _ in implied if k != keep})
                    for keep, label, _ in implied
                )
                out.append(Diagnostic("rol_mismatch", "warning",
                                      f"{name(l)} pricing disagrees: {desc}", (l.id,), price_fixes, key=key))

    q = tower.qs
    if q is not None:
        if q.cession is None or not (ZERO < q.cession <= ONE):
            out.append(Diagnostic("qs_cession", "error", "The quota share needs a cession between 0% and 100%",
                                  (q.id,)))
        from .formulas import qs_lines

        too_high = [name for name, _, _, c in qs_lines(tower) if c > MAX_PLACEABLE_CESSION]
        if (q.cession or ZERO) > MAX_PLACEABLE_CESSION or too_high:
            where = f" ({', '.join(too_high)})" if tower.lines and too_high else ""
            out.append(Diagnostic(
                "qs_placeable", "warning",
                f"A QS cession above {fmt.pct(MAX_PLACEABLE_CESSION)}{where} is hard to place: reinsurers want the "
                "cedant to keep a meaningful share of every risk",
                (q.id,), (_accept("qs_placeable", "Keep"),), key="qs_placeable"))
        prem = f.premium(tower, q)
        ceded_el = f.qs_ceded_el(tower)
        if prem and ceded_el is not None:
            lr = ceded_el / prem
            rate = f.commission_rate(q, lr) or ZERO
            costs = lr + rate + (q.terms.management_expenses or ZERO) + (f.setting(tower, "brokerage_qs")[0] or ZERO)
            if costs >= ONE - Decimal("0.03"):
                out.append(Diagnostic(
                    "qs_reinsurer_margin", "warning",
                    f"QS reinsurers expect a combined ratio of {fmt.pct(costs)} (loss ratio {fmt.pct(lr)} + commission "
                    f"{fmt.pct(rate)} + expenses): below a 3% margin it is unlikely to place",
                    (q.id,), (_accept("qs_reinsurer_margin", "Keep"),), key="qs_reinsurer_margin"))
        if tower.counterparty_limit is None:
            out.append(Diagnostic(
                "qs_limit_crm", "info",
                "A QS limit is usually the CRM team's limit for your largest counterparty; enter it to check against",
                (q.id,), key="qs_limit_crm",
            ))
        elif q.limit > tower.counterparty_limit:
            out.append(Diagnostic(
                "qs_limit_crm", "warning",
                f"QS limit {a(q.limit)} is above the largest counterparty limit {a(tower.counterparty_limit)}",
                (q.id,), (Fix("Set QS limit to the counterparty limit", "update", q.id,
                              {"limit": tower.counterparty_limit}),
                          _accept("qs_limit_crm_over", "Keep")),
                key="qs_limit_crm_over",
            ))
        prem = f.premium(tower, q)
        if q.agg_limit is None:
            out.append(Diagnostic("qs_agg_limit", "info",
                                  "No QS aggregate limit entered; QS aggregate limits are usually large",
                                  (q.id,), key="qs_agg_limit_missing"))
        elif prem and q.agg_limit < prem:
            out.append(Diagnostic(
                "qs_agg_limit", "warning",
                f"QS aggregate limit {a(q.agg_limit)} is below the QS premium {a(prem)}; it caps the QS "
                "below a 100% ceded loss ratio, and QS aggregate limits are usually much larger",
                (q.id,), (Fix("Set to 3 × QS premium", "update", q.id, {"agg_limit": prem * 3}),
                          _accept("qs_agg_limit_low", "Keep")),
                key="qs_agg_limit_low",
            ))
        if q.terms.sliding_scale is not None and q.terms.commission is not None:
            out.append(Diagnostic("qs_commission", "info", "The sliding scale replaces the flat QS commission",
                                  (q.id,), key="qs_commission_both"))
        if tower.epi is None:
            out.append(Diagnostic("epi_missing", "warning", "Enter the gross EPI to price the quota share", (q.id,),
                                  key="epi_missing:qs"))

    sls = tower.sl_layers
    if sls and tower.epi is None:
        out.append(Diagnostic("epi_missing", "warning",
                              "Stop loss layers are set as % of EPI; enter the gross EPI to show amounts",
                              tuple(s.id for s in sls), key="epi_missing:sl"))
    ordered = sorted(sls, key=lambda s: s.attachment)
    for below, above in zip(ordered, ordered[1:]):
        if above.attachment > below.exhaust:
            gap = fmt.pct(above.attachment - below.exhaust)
            out.append(Diagnostic("gap", "warning", f"Gap of {gap} of EPI between {name(below)} and {name(above)}",
                                  (below.id, above.id), (_accept(f"gap:{below.id}:{above.id}", "Keep"),),
                                  key=f"gap:{below.id}:{above.id}"))

    if view is not None and view.scale == "linear":
        limits = [l.limit for l in tower.layers if l.limit > 0 and l.kind in ("retention", "xl")]
        if limits and max(limits) > 30 * min(limits):
            out.append(Diagnostic(
                "extreme_scale", "info",
                "The largest layer is over 30 times the smallest, so thin layers are hard to see",
                (), (Fix("Switch to schematic", "view", fields={"scale": "schematic"}),
                     Fix("Switch to log", "view", fields={"scale": "log"})),
                key="extreme_scale",
            ))

    return [d for d in out if d.key is None or d.key not in tower.accepted]


def has_errors(diagnostics: list[Diagnostic]) -> bool:
    return any(d.severity == "error" for d in diagnostics)


def apply_fix(tower: Tower, fix: Fix | dict[str, Any]) -> Tower:
    if isinstance(fix, dict):
        fix = Fix.from_dict(fix)
    if fix.op == "accept" and fix.key:
        return tower.accept(fix.key)
    if fix.op == "update" and fix.layer:
        old = tower.layer(fix.layer)
        changes: dict[str, Any] = {k: None if v is None else Decimal(str(v)) for k, v in fix.fields.items()}
        new = replace(old, **changes)
        return tower.with_layers([new if l.id == old.id else l for l in tower.layers])
    return tower
