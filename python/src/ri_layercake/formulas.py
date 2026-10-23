"""Derived figures, in one place, so the table, the inspector and the slide always agree.

    Premium (RTE) = EPI (gross) x Adj. rate
    ROL           = Premium (RTE) / Layer limit
    Adj. rate     = ROL x Layer limit / EPI
    Agg limit     = Limit x (1 + Reinstatements)
    Payback       = Layer limit / Premium (RTE)

A layer can be priced by any one of premium, rate on line or adjusted rate; the
other two are derived. A quota share's premium is its cession of the EPI.
Stop loss limits and attachments are loss ratios, turned into amounts with the EPI.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .model import ONE, ZERO, Layer

if TYPE_CHECKING:
    from .model import Tower

INFINITY = Decimal("Infinity")

# Market defaults used when the programme does not set its own: internal expenses 30% of EPI,
# brokerage 10% of non-proportional (XL and stop loss) premium and 2.5% of QS premium.
DEFAULTS: dict[str, Decimal] = {
    "internal_expenses": Decimal("0.30"),
    "brokerage_xl": Decimal("0.10"),
    "brokerage_qs": Decimal("0.025"),
}


def setting(t: Tower, key: str) -> tuple[Decimal | None, bool]:
    """A programme setting and whether it is the default (not entered)."""
    v = getattr(t, key)
    if v is not None:
        return v, False
    return DEFAULTS.get(key), key in DEFAULTS

FORMULAS: dict[str, str] = {
    "premium": "Premium (RTE) = EPI (gross) × Adj. rate",
    "rol": "ROL = Premium (RTE) ÷ Layer limit",
    "adj_rate": "Adj. rate = ROL × Layer limit ÷ EPI",
    "agg_limit": "Agg limit = Limit × (1 + Reinstatements)",
    "payback": "Payback = Layer limit ÷ Premium (RTE)",
    "exhaust": "Exhaust = Attachment + Limit",
    "share": "Share = Order % × Placed %",
    "qs_premium": "QS premium = Cession % × EPI (gross)",
    "qs_commission": "QS commission = Commission % × QS premium",
    "sliding_scale": "Sliding scale: max at or below the low loss ratio, min at or above the high, linear between",
    "rme": "Reinsurer management expenses = RME % × QS premium",
    "profit_commission": "Profit commission = PC % × max(0, QS premium − QS losses − commission − RME)",
    "no_claims_bonus": "No claims bonus = NCB % × Premium (RTE), if the layer has no claims in the year",
    "trapped": "Trapped = median(0, Exposure − Attachment, Limit)",
    "side_by_side": "Side by side: XL attachment and limit × (1 − QS cession), on the net retained",
    "sl_amounts": "Stop loss amount = Loss ratio × EPI (gross)",
}


def to_decimal_ratio(v: float | str | Decimal) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def limit_amount(t: Tower, l: Layer) -> Decimal | None:
    if l.kind == "sl":
        return None if t.epi is None else l.limit * t.epi
    return l.limit


def attachment_amount(t: Tower, l: Layer) -> Decimal | None:
    if l.kind == "sl":
        return None if t.epi is None else l.attachment * t.epi
    return l.attachment


def qs_lines(t: Tower) -> list[tuple[str, Decimal, Decimal | None, Decimal]]:
    """(line, EPI, expected loss ratio, QS cession) for each line; one line for the whole book when none are set."""
    q = t.qs
    base = ZERO if q is None or q.cession is None else q.cession
    if t.lines:
        return [(l.name, l.epi, l.expected_loss_ratio if l.expected_loss_ratio is not None else t.expected_loss_ratio,
                 l.cession if l.cession is not None else base) for l in t.lines]
    if t.epi is None:
        return []
    return [("All", t.epi, t.expected_loss_ratio, base)]


def premium(t: Tower, l: Layer) -> Decimal | None:
    """Premium (RTE) on a 100% basis, from whichever input was given."""
    if l.premium is not None:
        return l.premium
    if l.kind == "qs":
        if t.lines:
            return sum((c * epi for _, epi, _, c in qs_lines(t)), ZERO)
        return None if l.cession is None or t.epi is None else l.cession * t.epi
    if l.adj_rate is not None and t.epi is not None:
        return t.epi * l.adj_rate
    lim = limit_amount(t, l)
    if l.rol is not None and lim is not None:
        return l.rol * lim
    return None


def rol(t: Tower, l: Layer) -> Decimal | None:
    if l.kind in ("qs", "retention"):
        return None
    p, lim = premium(t, l), limit_amount(t, l)
    return None if p is None or not lim else p / lim


def adj_rate(t: Tower, l: Layer) -> Decimal | None:
    if l.kind == "retention":
        return None
    p = premium(t, l)
    return None if p is None or not t.epi else p / t.epi


def payback(t: Tower, l: Layer) -> Decimal | None:
    p, lim = premium(t, l), limit_amount(t, l)
    return None if not p or lim is None or l.kind == "qs" else lim / p


def agg_limit(t: Tower, l: Layer) -> Decimal | None:
    """XL: Limit x (1 + reinstatements); unlimited reinstatements give infinity. QS: as entered."""
    if l.kind == "qs":
        return l.agg_limit
    if l.kind == "sl":
        return limit_amount(t, l)
    if l.kind == "retention":
        return None
    r = l.reinstatements
    if r is None:
        return l.limit
    if r.count is None:
        return INFINITY
    return l.limit * (1 + r.count)


def qs_cession(t: Tower, line: str | None = None) -> Decimal:
    """The QS cession for one line, or the EPI-weighted cession across lines."""
    q = t.qs
    base = ZERO if q is None or q.cession is None else q.cession
    if q is None or not t.lines:
        return base
    rows = qs_lines(t)
    if line is not None:
        return next((c for name, _, _, c in rows if name == line), base)
    epi = sum((e for _, e, _, _ in rows), ZERO)
    return sum((c * e for _, e, _, c in rows), ZERO) / epi if epi else base


def qs_ceded_el(t: Tower) -> Decimal | None:
    """Σ cession × EPI × expected loss ratio, by line: the expected loss ceded to the QS (100% of the order)."""
    rows = qs_lines(t)
    if not rows or any(el is None for _, _, el, _ in rows):
        return None
    return sum((c * epi * el for _, epi, el, c in rows), ZERO)  # type: ignore[operator]


def commission_rate(l: Layer, loss_ratio: Decimal | None = None) -> Decimal | None:
    """QS commission rate: the sliding scale at this loss ratio, else the flat commission."""
    ss = l.terms.sliding_scale
    if ss is not None:
        return ss.rate(loss_ratio) if loss_ratio is not None else ss.max
    return l.terms.commission


def qs_result(t: Tower, ceded_loss: Decimal) -> dict[str, Decimal | None]:
    """Commission, RME, profit commission and reinsurer result for a year's ceded QS losses (100% of order)."""
    q = t.qs
    if q is None:
        return {}
    prem = premium(t, q)
    if prem is None:
        return {"premium": None}
    lr = ceded_loss / prem if prem else None
    rate = commission_rate(q, lr) or ZERO
    commission = rate * prem
    rme = (q.terms.management_expenses or ZERO) * prem
    profit = prem - ceded_loss - commission - rme
    pc = (q.terms.profit_commission or ZERO) * max(profit, ZERO)
    return {
        "premium": prem, "loss": ceded_loss, "loss_ratio": lr, "commission_rate": rate, "commission": commission,
        "management_expenses": rme, "profit": profit, "profit_commission": pc,
        "reinsurer_result": profit - pc,
    }


def no_claims_bonus(t: Tower, l: Layer) -> Decimal | None:
    rate = l.terms.no_claims_bonus
    p = premium(t, l)
    return None if rate is None or p is None else rate * p


def effective_share(l: Layer) -> Decimal:
    return l.order * l.placed if l.kind != "retention" else ONE
