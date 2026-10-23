"""Premium walk: from gross EPI to the cedant's result after reinsurance.

    Result = EPI − Internal expenses − QS premium − XL premium − Reinst. premium − EL (analytic)
             + EL saved by QS + EL saved by XL + QS commission + Profit commission + NCB
             − Brokerage − Tax
    Margin = Result ÷ EPI

Reinsurance figures are the cedant's: each cover's premium, recoveries and commissions are
taken at its effective share (order x placed). The "approx." steps use these approximations:

    EL saved by QS        ≈ Cession × EL (analytic), capped by the QS aggregate limit
    EL saved by XL        = the expected loss entered for each XL or stop loss layer
    Reinst. premium       ≈ r × Premium × min(Layer EL, n × Limit) ÷ Limit     (pro rata to amount)
    QS commission         = commission rate at the expected ceded loss ratio × QS premium
    Profit commission     = PC % × max(0, QS premium − ceded EL − commission − RME)
    NCB                   = NCB % × Premium, assuming no claims to the layer
    Brokerage             = 2.5% × QS premium + 10% × XL and stop loss premium, unless set
    Tax                   = rate × ceded reinsurance premium (QS + XL + stop loss)
    Internal expenses     = 30% of EPI unless set
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from . import fmt
from . import formulas as f
from .model import ZERO

if TYPE_CHECKING:
    from .model import Tower


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    amount: Decimal  # signed: negative reduces the result
    formula: str
    approx: bool = False
    missing: str | None = None  # what to enter to fill this step in
    default: bool = False  # uses a market default rather than an entered value


@dataclass(frozen=True)
class Walk:
    epi: Decimal
    steps: tuple[Step, ...]
    tower: Any = None

    @property
    def result(self) -> Decimal:
        return self.epi + sum((s.amount for s in self.steps), ZERO)

    @property
    def margin(self) -> Decimal | None:
        return self.result / self.epi if self.epi else None

    @property
    def result_without_reinsurance(self) -> Decimal:
        keep = ("internal_expenses", "expected_loss")
        return self.epi + sum((s.amount for s in self.steps if s.key in keep), ZERO)

    @property
    def cost_of_reinsurance(self) -> Decimal:
        return self.result_without_reinsurance - self.result

    def before_after(self) -> dict[str, dict[str, Decimal | None]]:
        """Loss ratio, expense ratio, combined ratio, result and margin, before and after reinsurance.

        After reinsurance:
            Net premium  = EPI − QS premium − XL premium − Reinst. premium
            Net losses   = EL − EL saved by QS − EL saved by XL
            Net expenses = Internal expenses − QS commission − Profit comm. − NCB + Brokerage + Tax
            Result       = Net premium − Net losses − Net expenses   (the walk's result)
        Margin is shown on gross EPI for both, so the two are directly comparable.
        """
        s = {x.key: x.amount for x in self.steps}

        def ratios(premium: Decimal, losses: Decimal, expenses: Decimal) -> dict[str, Decimal | None]:
            result = premium - losses - expenses
            return {
                "premium": premium, "losses": losses, "expenses": expenses,
                "loss_ratio": losses / premium if premium else None,
                "expense_ratio": expenses / premium if premium else None,
                "combined_ratio": (losses + expenses) / premium if premium else None,
                "result": result,
                "margin": result / self.epi if self.epi else None,
                "margin_on_premium": result / premium if premium else None,
            }

        gross = ratios(self.epi, -s["expected_loss"], -s["internal_expenses"])
        net = ratios(
            self.epi + s["qs_premium"] + s["xl_premium"] + s["reinstatement_premium"],
            -s["expected_loss"] - s["el_saved_qs"] - s["el_saved_xl"],
            -s["internal_expenses"] - s["qs_commission"] - s["profit_commission"] - s["no_claims_bonus"]
            - s["brokerage"] - s["tax"],
        )
        return {"before": gross, "after": net}

    def plot(self, ax: Any = None) -> Any:
        """The walk as a matplotlib waterfall."""
        from .render_mpl import plot_walk

        return plot_walk(self, ax=ax)

    def _repr_html_(self) -> str:
        d = self.to_dict()
        rows = "".join(f"<tr><td>{s['label']}{' *' if s['approx'] else ''}</td><td style='text-align:right'>"
                       f"{s['amount']}</td><td>{s['formula']}</td></tr>" for s in d["steps"])
        return (f"<table><tr><th>EPI</th><th style='text-align:right'>{d['epi']}</th><th></th></tr>{rows}"
                f"<tr><th>Result</th><th style='text-align:right'>{d['result']}</th><th>Margin {d['margin']}</th></tr>"
                "</table><p>* approximate</p>")

    def to_dict(self) -> dict[str, Any]:
        t = self.tower

        def n(v: Decimal) -> str:
            return fmt.num(t, v) if t is not None else str(v)

        return {
            "epi": n(self.epi),
            "steps": [{"key": s.key, "label": s.label, "amount": n(s.amount), "value": float(t.in_units(s.amount)),
                       "formula": s.formula, "approx": s.approx, "missing": s.missing, "default": s.default}
                      for s in self.steps],
            "result": n(self.result), "result_value": float(t.in_units(self.result)),
            "margin": fmt.pct(self.margin),
            "result_without_reinsurance": n(self.result_without_reinsurance),
            "cost_of_reinsurance": n(self.cost_of_reinsurance),
            "before_after": {
                side: {k: "" if v is None else fmt.pct(v) if k.endswith("ratio") or k.startswith("margin") else n(v)
                       for k, v in vals.items()}
                for side, vals in self.before_after().items()
            },
        }


def premium_walk(t: Tower) -> Walk:
    if t.epi is None:
        raise ValueError("Enter the gross EPI to build the premium walk")
    epi = t.epi
    q = t.qs
    excess = [l for l in t.layers if l.kind in ("xl", "sl")]
    el_gross = None if t.expected_loss_ratio is None else t.expected_loss_ratio * epi
    steps: list[Step] = []

    def add(key: str, label: str, amount: Decimal, formula: str, approx: bool = False,
            missing: str | None = None, default: bool = False) -> None:
        steps.append(Step(key, label, amount, formula, approx, missing, default))

    ie, ie_default = f.setting(t, "internal_expenses")
    add("internal_expenses", "Internal expenses", -(ie or ZERO) * epi,
        f"Internal expense % × EPI = {fmt.pct(ie)} × EPI" + (" (default)" if ie_default else ""), default=ie_default)

    qs_prem = ZERO
    ceded_el = ZERO
    if q is not None:
        qs_prem = (f.premium(t, q) or ZERO) * q.share
    add("qs_premium", "QS premium", -qs_prem, f.FORMULAS["qs_premium"] + " × share",
        missing="cession and EPI" if q is not None and not qs_prem else None)

    xl_prem = sum(((f.premium(t, l) or ZERO) * l.share for l in excess), ZERO)
    no_price = [t.display_name(l) for l in excess if f.premium(t, l) is None]
    add("xl_premium", "XL premium", -xl_prem, "Σ Premium (RTE) × share, XL and stop loss",
        missing=("premium for " + ", ".join(no_price)) if no_price else None)

    rip = ZERO
    no_el = [t.display_name(l) for l in excess if l.terms.expected_loss is None]
    for l in t.xl_layers:
        el, p, r = l.terms.expected_loss, f.premium(t, l), l.reinstatements
        if el is None or p is None or r is None or l.limit <= 0:
            continue
        used = el if r.count is None else min(el, r.count * l.limit)
        rip += Decimal(repr(r.rate)) * p * used / l.limit * l.share
    add("reinstatement_premium", "Reinst. premium", -rip, "r × Premium × min(Layer EL, n × Limit) ÷ Limit × share",
        approx=True)

    add("expected_loss", "EL (analytic)", -(el_gross or ZERO), "Analytic loss ratio × EPI",
        missing=None if el_gross is not None else "analytic EL %")

    lines_el = f.qs_ceded_el(t) if q is not None else None
    if q is not None and lines_el is not None:
        ceded_el = lines_el
        if q.agg_limit is not None:
            ceded_el = min(ceded_el, q.agg_limit)
    add("el_saved_qs", "EL saved by QS", ceded_el * (q.share if q else 0), "Cession × EL (analytic) × share",
        approx=True)

    el_xl = sum(((l.terms.expected_loss or ZERO) * l.share for l in excess), ZERO)
    add("el_saved_xl", "EL saved by XL", el_xl, "Σ Layer EL × share", approx=True,
        missing=("layer EL for " + ", ".join(no_el)) if no_el and excess else None)

    commission = rme = pc = ZERO
    if q is not None:
        res = f.qs_result(t, ceded_el)
        if res.get("premium"):
            commission = (res["commission"] or ZERO) * q.share
            pc = (res["profit_commission"] or ZERO) * q.share
            rme = (res["management_expenses"] or ZERO) * q.share
    add("qs_commission", "QS commission", commission, f.FORMULAS["qs_commission"] + " (at the expected loss ratio)")
    add("profit_commission", "Profit comm.", pc,
        "PC % × max(0, QS premium − ceded EL − commission − RME)", approx=True)

    ncb = sum(((f.no_claims_bonus(t, l) or ZERO) * l.share for l in t.xl_layers), ZERO)
    add("no_claims_bonus", "NCB", ncb, "NCB % × Premium × share, assuming no claims", approx=True)

    ceded = qs_prem + xl_prem
    bq, bq_default = f.setting(t, "brokerage_qs")
    bx, bx_default = f.setting(t, "brokerage_xl")
    brokerage = (bq or ZERO) * qs_prem + (bx or ZERO) * xl_prem
    add("brokerage", "Brokerage", -brokerage,
        f"{fmt.pct(bq)} × QS premium + {fmt.pct(bx)} × XL premium"
        + (" (market defaults)" if (bq_default and qs_prem) or (bx_default and xl_prem) else ""),
        default=(bq_default and bool(qs_prem)) or (bx_default and bool(xl_prem)))
    add("tax", "Tax", -(t.tax or ZERO) * ceded, "Tax % × ceded reinsurance premium",
        missing=None if t.tax is not None or not ceded else "tax %")
    del rme
    return Walk(epi, tuple(steps), t)
