"""Coverage: how an exposure or a loss is shared out across the programme.

Per risk (an exposure, or a single loss to one risk), for a quota share with cession c and
per-risk limit Lq, and excess of loss layers L xs A:

    QS ceded      = c x min(X, Lq)
    Net after QS  = X - QS ceded
    Stacked       : each XL takes median(0, Net - A, L)                 (XL on the net of QS)
    Side by side  : each XL takes median(0, Net - A(1-c), L(1-c))       (attachment and limit scaled)
    Recovery      = taken x order x placed
    RIP           = r x P x min(taken, n L) / L                         (pro rata to amount)

Annual aggregate (stop loss and QS terms): the aggregate loss X is ceded to the QS at c, capped
by the QS aggregate limit; the stop loss takes median(0, LR - attachment, limit) x EPI on the
loss ratio LR = (X - QS ceded) / EPI.

Whatever no cover takes stays with the cedant, so retained + recovered + uncovered = X.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from . import fmt
from . import formulas as f
from .model import ONE, ZERO

if TYPE_CHECKING:
    from .model import Layer, Tower


def median3(a: Decimal, b: Decimal, c: Decimal) -> Decimal:
    return sorted((a, b, c))[1]


def layer_loss(layer: Layer, x: Decimal) -> Decimal:
    """median(0, X - A, L): the part of X that a layer takes on a 100% basis."""
    return median3(ZERO, x - layer.attachment, layer.limit)


def reinstatement_premium(layer: Layer, r100: Decimal, premium: Decimal | None = None) -> Decimal:
    ri = layer.reinstatements
    p = premium if premium is not None else layer.effective_premium
    if ri is None or p is None or layer.limit <= 0 or r100 <= 0:
        return ZERO
    used = r100 if ri.count is None else min(r100, ri.count * layer.limit)
    return Decimal(repr(ri.rate)) * p * used / layer.limit


@dataclass(frozen=True)
class LayerLoss:
    layer: str
    name: str
    recovery_100: Decimal  # what the layer takes, 100% basis (trapped exposure or loss)
    placed: Decimal  # effective share with reinsurers: order x placed
    recovery_placed: Decimal
    exhausted: bool
    reinstatement_premium: Decimal  # placed basis
    net: Decimal  # recovery placed less reinstatement premium
    kind: str = "xl"
    limit_used: Decimal = ZERO  # the layer's limit as applied (scaled when side by side)
    ncb_lost: bool = False


@dataclass(frozen=True)
class LossResult:
    loss: Decimal
    layers: tuple[LayerLoss, ...]
    retention: Decimal  # the band below the first XL attachment, on the net of QS
    unplaced: Decimal  # taken by a cover but not placed with reinsurers
    uncovered: Decimal  # in gaps between XL layers or above the top
    tower: Any = None
    qs_ceded: Decimal = ZERO  # 100% of the QS order
    net_of_qs: Decimal = ZERO

    @property
    def recovered(self) -> Decimal:
        return sum((l.recovery_placed for l in self.layers), ZERO)

    @property
    def retained(self) -> Decimal:
        """What the cedant keeps inside the programme: the retention band plus unplaced shares."""
        return self.retention + self.unplaced

    @property
    def reinstatement_premium(self) -> Decimal:
        return sum((l.reinstatement_premium for l in self.layers), ZERO)

    @property
    def net_cost(self) -> Decimal:
        return self.retained + self.uncovered + self.reinstatement_premium

    def rows(self) -> list[dict[str, Any]]:
        t = self.tower
        n = (lambda v: fmt.num(t, v)) if t is not None else str
        out = []
        for l in self.layers:
            if l.kind == "qs":
                out.append(_row(l, n))
        if t is not None and t.retention is not None:
            out.append({"layer": "R", "name": t.display_name(t.retention), "kind": "retention",
                        "recovery_100": "", "placed": "", "recovery_placed": "",
                        "exhausted": self.retention >= t.retention.exhaust and self.retention > 0,
                        "reinstatement_premium": "", "net": "", "retained": n(self.retention), "ncb": ""})
        for l in self.layers:
            if l.kind != "qs":
                out.append(_row(l, n))
        return out

    def to_dict(self) -> dict[str, Any]:
        t = self.tower
        n = (lambda v: fmt.num(t, v)) if t is not None else str
        return {
            "loss": n(self.loss),
            "rows": self.rows(),
            "totals": {
                "retained": n(self.retained), "uncovered": n(self.uncovered), "recovered": n(self.recovered),
                "reinstatement_premium": n(self.reinstatement_premium), "net_cost": n(self.net_cost),
                "qs_ceded": n(self.qs_ceded), "net_of_qs": n(self.net_of_qs),
            },
        }

    def _repr_html_(self) -> str:
        from html import escape

        head = ["Layer", "Takes (100%)", "Share", "Recovery", "Exhausted", "Reinstatement premium"]
        keys = ["name", "recovery_100", "placed", "recovery_placed", "exhausted", "reinstatement_premium"]
        body = "".join(
            "<tr>" + "".join(
                f"<td>{escape(('yes' if r[k] else 'no') if k == 'exhausted' else str(r[k]))}</td>" for k in keys
            ) + "</tr>"
            for r in self.rows()
        )
        d = self.to_dict()["totals"]
        foot = (f"<p>Recovered {d['recovered']} · Retained {d['retained']} · Uncovered {d['uncovered']} · "
                f"Reinstatement premium {d['reinstatement_premium']}</p>")
        return ("<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in head) +
                f"</tr></thead><tbody>{body}</tbody></table>{foot}")


def _row(l: LayerLoss, n: Any) -> dict[str, Any]:
    return {"layer": l.layer, "name": l.name, "kind": l.kind, "recovery_100": n(l.recovery_100),
            "placed": fmt.pct(l.placed), "recovery_placed": n(l.recovery_placed), "exhausted": l.exhausted,
            "reinstatement_premium": n(l.reinstatement_premium), "net": n(l.net),
            "limit_used": n(l.limit_used), "ncb": "lost" if l.ncb_lost else ""}


def xl_bands(t: Tower, line: str | None = None) -> list[tuple[Layer, Decimal, Decimal]]:
    """Each XL layer's (attachment, limit) as applied: scaled by (1 - c) when side by side."""
    scale = ONE - f.qs_cession(t, line) if t.arrangement == "side_by_side" and t.qs is not None else ONE
    return [(l, l.attachment * scale, l.limit * scale) for l in t.xl_layers]


def drop_loss(tower: Tower, x: Decimal, line: str | None = None) -> LossResult:
    """One risk's exposure or loss X through the programme (per risk basis), on a line's QS cession."""
    rows: list[LayerLoss] = []
    unplaced = ZERO
    q = tower.qs
    qs_100 = ZERO
    cession = f.qs_cession(tower, line) if q is not None else ZERO
    if q is not None and cession:
        qs_100 = cession * min(x, q.limit)
        share = q.share
        unplaced += qs_100 * (ONE - min(share, ONE))
        rows.append(LayerLoss(q.id, tower.display_name(q), qs_100, share, qs_100 * share, x >= q.limit,
                              ZERO, qs_100 * share, kind="qs", limit_used=q.limit))
    net = x - qs_100

    bands = xl_bands(tower, line)
    for l, a, lim in bands:
        taken = median3(ZERO, net - a, lim)
        share = l.share
        prem = f.premium(tower, l)
        scaled = replace_limit(l, lim)
        rip = share * reinstatement_premium(scaled, taken, None if prem is None else prem)
        unplaced += taken * (ONE - min(share, ONE))
        rows.append(LayerLoss(l.id, tower.display_name(l), taken, share, taken * share,
                              taken > 0 and taken >= lim, rip, taken * share - rip, kind="xl", limit_used=lim,
                              ncb_lost=taken > 0 and l.terms.no_claims_bonus is not None))

    first = min((a for _, a, _ in bands), default=None)
    if tower.retention is not None:
        first = tower.retention.exhaust if first is None else first
    retention = min(net, first) if first is not None else net
    covered = _covered_length([(a, a + lim) for _, a, lim in bands], net)
    uncovered = max(net - min(net, first if first is not None else net) - covered, ZERO)
    return LossResult(x, tuple(rows), retention, unplaced, uncovered, tower, qs_100, net)


def replace_limit(l: Layer, limit: Decimal) -> Layer:
    from dataclasses import replace

    return replace(l, limit=limit)


def _covered_length(spans_in: list[tuple[Decimal, Decimal]], x: Decimal) -> Decimal:
    """Length of [0, x] covered by at least one band (union of intervals)."""
    spans = sorted((s, min(e, x)) for s, e in spans_in if s < x)
    total, cur_s, cur_e = ZERO, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s  # type: ignore[operator]
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s  # type: ignore[operator]
    return total


# ---------------------------------------------------------------------- annual aggregate

@dataclass(frozen=True)
class AggregateResult:
    loss: Decimal
    qs_ceded: Decimal
    net_of_qs: Decimal
    loss_ratio: Decimal | None  # net of QS, on gross EPI
    stop_loss: tuple[LayerLoss, ...]
    qs_terms: dict[str, Decimal | None] = field(default_factory=dict)
    tower: Any = None

    @property
    def recovered(self) -> Decimal:
        return self.qs_ceded + sum((s.recovery_placed for s in self.stop_loss), ZERO)

    def to_dict(self) -> dict[str, Any]:
        t = self.tower
        n = (lambda v: "" if v is None else fmt.num(t, v)) if t is not None else str
        terms = {k: (fmt.pct(v) if k in ("loss_ratio", "commission_rate") else n(v)) for k, v in self.qs_terms.items()}
        ncb = []
        for l in t.xl_layers if t is not None else ():
            amount = f.no_claims_bonus(t, l)
            if amount is not None:
                ncb.append({"layer": l.id, "name": t.display_name(l), "rate": fmt.pct(l.terms.no_claims_bonus),
                            "amount": n(amount * l.share)})
        return {
            "loss": n(self.loss), "qs_ceded": n(self.qs_ceded), "net_of_qs": n(self.net_of_qs),
            "loss_ratio": fmt.pct(self.loss_ratio), "rows": [_row(s, n) for s in self.stop_loss],
            "qs_terms": terms, "no_claims_bonus": ncb,
        }


def aggregate(tower: Tower, x: Decimal) -> AggregateResult:
    """A year's aggregate loss X: QS cession and terms, then the stop loss on the net loss ratio."""
    q = tower.qs
    qs_100 = ZERO
    if q is not None:
        # The year's loss is shared out across lines by their expected losses, each ceded at its own cession.
        rows_l = f.qs_lines(tower)
        weights = [(epi * (el if el is not None else ONE), c) for _, epi, el, c in rows_l]
        total = sum((w for w, _ in weights), ZERO)
        qs_100 = sum((x * w / total * c for w, c in weights), ZERO) if total else (q.cession or ZERO) * x
        if q.agg_limit is not None:
            qs_100 = min(qs_100, q.agg_limit)
    net = x - qs_100
    epi = tower.epi
    lr = net / epi if epi else None
    rows = []
    for s in tower.sl_layers:
        if lr is None or epi is None:
            continue
        taken_ratio = median3(ZERO, lr - s.attachment, s.limit)
        taken = taken_ratio * epi
        rows.append(LayerLoss(s.id, tower.display_name(s), taken, s.share, taken * s.share,
                              taken_ratio > 0 and taken_ratio >= s.limit, ZERO, taken * s.share, kind="sl",
                              limit_used=s.limit * epi))
    terms = f.qs_result(tower, qs_100) if q is not None else {}
    return AggregateResult(x, qs_100 * (q.share if q else ONE), net, lr, tuple(rows), terms, tower)


# ---------------------------------------------------------------------- portfolio

@dataclass(frozen=True)
class PortfolioResult:
    risks: tuple[tuple[str, Decimal, LossResult], ...]
    tower: Any = None

    def summary(self) -> list[dict[str, Any]]:
        t = self.tower
        n = (lambda v: fmt.num(t, v)) if t is not None else str
        if not self.risks:
            return []
        out = []
        ids = [l.layer for l in self.risks[0][2].layers]
        names = {l.layer: l.name for l in self.risks[0][2].layers}
        for lid in ids:
            taken = [next(l for l in r[2].layers if l.layer == lid) for r in self.risks]
            out.append({
                "layer": lid, "name": names[lid],
                "trapped": n(sum((l.recovery_100 for l in taken), ZERO)),
                "ceded": n(sum((l.recovery_placed for l in taken), ZERO)),
                "risks_reaching": sum(1 for l in taken if l.recovery_100 > 0),
                "risks_exhausting": sum(1 for l in taken if l.exhausted),
                "max": n(max((l.recovery_100 for l in taken), default=ZERO)),
            })
        return out

    def to_dict(self) -> dict[str, Any]:
        t = self.tower
        n = (lambda v: fmt.num(t, v)) if t is not None else str
        total = sum((r[1] for r in self.risks), ZERO)
        retained = sum((r[2].retained + r[2].uncovered for r in self.risks), ZERO)
        return {
            "count": len(self.risks), "total_exposure": n(total), "retained": n(retained),
            "layers": self.summary(),
            "risks": [{"id": rid, "exposure": n(e),
                       "layers": {l.layer: n(l.recovery_100) for l in res.layers},
                       "retained": n(res.retained + res.uncovered)} for rid, e, res in self.risks],
        }


def portfolio(tower: Tower, risks: list[tuple[str, Decimal]] | list[tuple[str, Decimal, str | None]]
              ) -> PortfolioResult:
    """Trapped exposure for every risk in a portfolio: median(0, E - A, L) per layer, at each risk's line."""
    out = []
    for r in risks:
        rid, e = r[0], r[1]
        line = r[2] if len(r) > 2 else None
        out.append((rid, e, drop_loss(tower, e, line)))
    return PortfolioResult(tuple(out), tower)
