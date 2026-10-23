"""Risk view: what reinsurance costs on average and what it saves in a bad year.

Every simulated year runs the whole programme. Per line:

    Attritional losses  lognormal around (1 − large share) × EL, with the line's volatility, correlated
                        between lines (Gaussian copula)
    Large losses        a Poisson number of risk losses a year, Pareto severities above a threshold, capped at
                        the largest risk; calibrated so the modelled XoL layer losses match the layer ELs entered

    QS          each risk ceded at its line's cession up to the QS limit; attritional ceded at the cession;
                capped by the QS aggregate limit; sliding scale and profit commission follow the year's QS LR
    XoL         each large loss after the QS (stacked) or with attachment and limit × (1 − c) (side by side);
                annual cap Limit × (1 + reinstatements); reinstatement premium pro rata; NCB if no claims
    Stop loss   on the year's net loss ratio after the QS and XoL

Everything is on gross EPI:  Net LR = (gross losses − recoveries) ÷ EPI,  Margin = result ÷ EPI.

    Capital  = Expected result − Result in a 1-in-N year       (shortfall from expected)
    RoC      = Expected result ÷ Capital

Levers (what-ifs) change the programme without editing it: QS cession by line, QS commission, XoL
retention, XoL price (rate on line), stop loss attachment. When cession or retention change, XoL premiums
re-price with the modelled layer exposure at the layer's current loading (× the price lever).

Best programme: among the placeable programmes on the map, the Pareto-efficient ones (no other is at least as
good on net LR, margin and RoC and better on one); of those, the highest weighted score, each measure scaled
0 (worst) to 1 (best) across the map, equal weights by default.

Placeable: QS cession ≤ the market maximum and QS reinsurers keep ≥ 3% after losses, commission, RME and
brokerage; each XoL and stop loss layer priced so reinsurers keep ≥ 3% after expected losses and brokerage,
at no more than 100% rate on line; a stop loss attaches at least 5 points above the expected net loss ratio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from . import formulas as f

if TYPE_CHECKING:
    from .model import Layer, Tower

DEFAULT_VOLATILITY = 0.10  # attritional losses are fairly stable; large losses carry the volatility


@dataclass(frozen=True)
class RiskSettings:
    sims: int = 20_000
    seed: int = 7
    return_period: int = 200  # 1-in-200 year, as Solvency II's 99.5%
    correlation: float = 0.30
    default_volatility: float = DEFAULT_VOLATILITY  # attritional loss ratio volatility
    large_share: float = 0.25  # share of EL from large losses, when layer ELs do not calibrate it
    pareto_alpha: float = 1.5
    max_cession: float = 0.50  # the most the market will take
    min_reinsurer_margin: float = 0.03
    appetite: float | None = None  # optional: the worst acceptable 1-in-N margin, fraction of EPI
    # How the best programme weighs the three measures; each is scaled 0 (worst) to 1 (best) across the map.
    weight_loss_ratio: float = 1.0
    weight_margin: float = 1.0
    weight_roc: float = 1.0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> RiskSettings:
        base = cls()
        out: dict[str, Any] = {}
        for k, v in (d or {}).items():
            if k not in cls.__dataclass_fields__:
                continue
            if k == "appetite":
                out[k] = None if v is None else float(v)
            else:
                out[k] = type(getattr(base, k))(v)
        return cls(**out)


@dataclass(frozen=True)
class Levers:
    """What-if values. None means: as the programme stands."""

    cessions: dict[str, float] | None = None  # by line; "*" sets every line
    commission_shift: float = 0.0  # added to the QS commission (flat and sliding scale), e.g. +0.05
    xl_retention: float | None = None  # first XoL attachment, full currency units
    xl_price: float = 1.0  # multiplies XoL premium (rate on line)
    sl_attachment: float | None = None  # first stop loss attachment, loss ratio

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None, t: Tower) -> Levers:
        d = d or {}
        ret = d.get("xl_retention")
        return cls(
            cessions={k: float(v) for k, v in d["cessions"].items()} if d.get("cessions") else None,
            commission_shift=float(d.get("commission_shift", 0) or 0),
            xl_retention=None if ret is None else float(ret) * float(t.factor),
            xl_price=float(d.get("xl_price", 1) or 1),
            sl_attachment=None if d.get("sl_attachment") is None else float(d["sl_attachment"]),
        )


def _f(v: Any, default: float = 0.0) -> float:
    return default if v is None else float(v)


def reprice(base_premium: float, base_el: float, new_el: float, limit: float, price: float = 1.0) -> float:
    """Premium after the layer changes: new expected loss at the layer's current loading (capped 1.05x to 4x;
    a 70% reinsurer loss ratio when the old layer had almost no expected loss), times the price lever."""
    priced = bool(base_premium) and base_el > 1e-9 * max(limit, 1.0)
    loading = min(max(base_premium / base_el, 1.05), 4.0) if priced else 1 / 0.7
    if priced or new_el:
        return new_el * loading * price
    return base_premium * price


# ---------------------------------------------------------------------- simulation

@dataclass
class Simulation:
    tower: Any
    settings: RiskSettings
    names: list[str]
    epis: Any  # (lines,)
    base_cessions: Any  # (lines,)
    attritional: Any  # (sims, lines)
    loss_year: Any  # (n,) year of each large loss
    loss_line: Any  # (n,) line of each large loss
    loss_size: Any  # (n,) gross size
    alpha: float
    large_share: list[float]
    model_layer_el: dict[str, float] = field(default_factory=dict)  # at the programme as it stands
    calibrated: bool = False
    layer_factor: dict[str, float] = field(default_factory=dict)  # per layer: entered EL ÷ fitted EL

    @property
    def epi(self) -> float:
        return float(self.epis.sum())


def _lines(t: Tower, s: RiskSettings) -> list[tuple[str, float, float, float, float]]:
    if t.epi is None or t.expected_loss_ratio is None:
        raise ValueError("Enter the gross EPI and the analytic EL to run the risk view")
    vols = {l.name: _f(l.volatility, s.default_volatility) for l in t.lines}
    return [(name, float(epi), _f(el, float(t.expected_loss_ratio)), float(c), vols.get(name, s.default_volatility))
            for name, epi, el, c in f.qs_lines(t)]


def _threshold_and_cap(t: Tower) -> tuple[float, float]:
    """Large losses start at half the first XoL attachment and are capped at 1.25 × the largest risk limit."""
    xl = t.xl_layers
    q = t.qs
    tops = [float(l.exhaust) for l in xl] + [float(q.limit) if q is not None else 0.0, _f(t.counterparty_limit)]
    cap = max(tops) * 1.25 if max(tops) > 0 else float(t.epi or 1) * 0.1
    first = min((float(l.attachment) for l in xl), default=0.0)
    u = 0.5 * first if first > 0 else cap * 0.05
    return max(u, cap * 0.01), cap


def _capped_pareto_mean(u: float, alpha: float, cap: float) -> float:
    """E[min(X, cap)] for X ~ Pareto(u, alpha)."""
    if abs(alpha - 1) < 1e-9:
        return u + u * math.log(cap / u)
    return float(u + u ** alpha * (cap ** (1 - alpha) - u ** (1 - alpha)) / (1 - alpha))


def simulate(t: Tower, settings: RiskSettings | None = None) -> Simulation:
    import numpy as np

    s = settings or RiskSettings()
    rows = _lines(t, s)
    n = len(rows)
    rng = np.random.default_rng(s.seed)
    el = np.array([r[1] * r[2] for r in rows])
    base_c = np.array([r[3] for r in rows]) if t.qs is not None else np.zeros(n)
    u, cap = _threshold_and_cap(t)
    lq = float(t.qs.limit) if t.qs is not None else 0.0

    # Calibrate the large-loss model to the XoL layer ELs entered, if any: Pareto alpha from the shape across
    # layers, large-loss share from the level.
    alpha, share = s.pareto_alpha, [s.large_share] * n
    entered = [(l, float(l.terms.expected_loss)) for l in t.xl_layers if l.terms.expected_loss]
    calibrated = False
    probe = rng.random(40_000)
    if entered:
        target = np.array([e for _, e in entered])
        best: tuple[float, float, float] | None = None
        for a in [1.1 + 0.1 * i for i in range(20)]:
            sev = np.minimum(u * probe ** (-1 / a), cap)
            mean_sev = _capped_pareto_mean(u, a, cap)
            model = np.zeros(len(entered))
            for i in range(n):
                net = sev - base_c[i] * np.minimum(sev, lq)
                scale = 1 - base_c[i] if t.arrangement == "side_by_side" else 1.0
                for j, (layer, _) in enumerate(entered):
                    take = np.clip(net - float(layer.attachment) * scale, 0, float(layer.limit) * scale)
                    model[j] += el[i] / mean_sev * float(take.mean())
            k = float((model @ target) / (model @ model)) if float(model @ model) > 0 else 0.0
            err = float(((k * model - target) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, a, k)
        assert best is not None
        _, alpha, k = best
        share = [min(max(k, 0.02), 0.6)] * n
        calibrated = True

    mean_sev = _capped_pareto_mean(u, alpha, cap)
    lam = el * np.array(share) / mean_sev
    counts = rng.poisson(lam, size=(s.sims, n))
    years, lines_idx = np.nonzero(counts)
    # Indices must be the platform's index type: 32-bit in the browser (Pyodide), 64-bit on most desktops.
    reps = counts[years, lines_idx].astype(np.intp)
    loss_year = np.repeat(years.astype(np.intp), reps)
    loss_line = np.repeat(lines_idx.astype(np.intp), reps)
    loss_size = np.minimum(u * rng.random(loss_year.size) ** (-1 / alpha), cap)

    corr = np.full((n, n), s.correlation)
    np.fill_diagonal(corr, 1.0)
    z = rng.standard_normal((s.sims, n)) @ np.linalg.cholesky(corr).T
    sig = np.sqrt(np.log1p(np.array([r[4] for r in rows]) ** 2))
    attr = el * (1 - np.array(share)) * np.exp(sig * z - sig ** 2 / 2)

    sim = Simulation(t, s, [r[0] for r in rows], np.array([r[1] for r in rows]), base_c, attr, loss_year,
                     loss_line, loss_size, alpha, share, calibrated=calibrated)
    fitted = {layer.id: float(annual.mean()) for layer, _, annual in _xl_takes(sim, Levers(), base_c)}
    # One Pareto curve cannot hit every layer exactly; a per-layer factor makes each match its entered EL.
    for layer, e in entered:
        if fitted.get(layer.id, 0) > 1e-9:
            sim.layer_factor[layer.id] = e / fitted[layer.id]
    sim.model_layer_el = {layer.id: float(annual.mean()) for layer, _, annual in _xl_takes(sim, Levers(), base_c)}
    return sim


def _xl_layers(sim: Simulation, lv: Levers) -> list[tuple[Layer, float, float]]:
    """XoL layers as the levers set them: (layer, attachment, limit)."""
    out = []
    for i, l in enumerate(sorted(sim.tower.xl_layers, key=lambda l: l.attachment)):
        A, L = float(l.attachment), float(l.limit)
        if i == 0 and lv.xl_retention is not None:
            top = A + L
            if lv.xl_retention >= top:
                continue
            A, L = lv.xl_retention, top - lv.xl_retention
        out.append((l, A, L))
    return out


def _cessions(sim: Simulation, lv: Levers) -> Any:
    c = sim.base_cessions.copy()
    if sim.tower.qs is None or not lv.cessions:
        return c
    for i, name in enumerate(sim.names):
        if "*" in lv.cessions:
            c[i] = lv.cessions["*"]
        if name in lv.cessions:
            c[i] = lv.cessions[name]
    return c


def _xl_takes(sim: Simulation, lv: Levers, c: Any) -> list[tuple[Layer, float, Any]]:
    """(layer, effective limit, annual amount taken per simulated year, 100% basis, before the annual cap)."""
    import numpy as np

    q = sim.tower.qs
    x = sim.loss_size
    cl = c[sim.loss_line]
    lq = float(q.limit) if q is not None else 0.0
    net = x - cl * np.minimum(x, lq)
    side = sim.tower.arrangement == "side_by_side"
    scale = (1 - cl) if side else 1.0
    out = []
    for layer, A, L in _xl_layers(sim, lv):
        take = np.clip(net - A * scale, 0, L * scale) * sim.layer_factor.get(layer.id, 1.0)
        annual = np.bincount(sim.loss_year, weights=take, minlength=sim.settings.sims)
        out.append((layer, L * (float(np.mean(1 - c)) if side else 1.0), annual))
    return out


# ---------------------------------------------------------------------- evaluation

@dataclass(frozen=True)
class Metrics:
    expected_result: float
    bad_year_result: float
    capital: float
    net_loss_ratio: float  # (gross losses − recoveries) ÷ EPI
    epi: float
    qs_reinsurer_margin: float | None = None
    xl_reinsurer_margins: tuple[float, ...] = ()
    placeable: bool = True

    @property
    def margin(self) -> float:
        return self.expected_result / self.epi

    @property
    def bad_year_margin(self) -> float:
        return self.bad_year_result / self.epi

    @property
    def roc(self) -> float | None:
        return self.expected_result / self.capital if self.capital > 0 else None

    def to_dict(self, k: float) -> dict[str, Any]:
        return {
            "expected_result": round(self.expected_result / k, 3),
            "bad_year_result": round(self.bad_year_result / k, 3),
            "capital": round(self.capital / k, 3),
            "margin": round(self.margin * 100, 2),
            "bad_year_margin": round(self.bad_year_margin * 100, 2),
            "net_loss_ratio": round(self.net_loss_ratio * 100, 2),
            "roc": None if self.roc is None else round(self.roc * 100, 2),
            "qs_reinsurer_margin": None if self.qs_reinsurer_margin is None
            else round(self.qs_reinsurer_margin * 100, 2),
            "xl_reinsurer_margins": [round(m * 100, 2) for m in self.xl_reinsurer_margins],
            "placeable": self.placeable,
        }


def _summarise(sim: Simulation, result: Any, net_losses: Any, **extra: Any) -> Metrics:
    import numpy as np

    alpha = 1 / sim.settings.return_period
    mean, bad = float(result.mean()), float(np.quantile(result, alpha))
    return Metrics(mean, bad, max(mean - bad, 0.0), float(net_losses.mean()) / sim.epi, sim.epi, **extra)


def _gross_losses(sim: Simulation) -> Any:
    import numpy as np

    return sim.attritional.sum(axis=1) + np.bincount(sim.loss_year, weights=sim.loss_size, minlength=sim.settings.sims)


def gross(sim: Simulation) -> Metrics:
    """No reinsurance at all: the 'before' column."""
    losses = _gross_losses(sim)
    ie = _f(f.setting(sim.tower, "internal_expenses")[0]) * sim.epi
    return _summarise(sim, sim.epi - ie - losses, losses)


def evaluate(sim: Simulation, lv: Levers | None = None) -> Metrics:
    import numpy as np

    lv = lv or Levers()
    t, s = sim.tower, sim.settings
    epi, n_years = sim.epi, s.sims
    c = _cessions(sim, lv)
    gross_loss = _gross_losses(sim)
    ie = _f(f.setting(t, "internal_expenses")[0]) * epi
    tax = _f(t.tax)
    bq = _f(f.setting(t, "brokerage_qs")[0])
    bx = _f(f.setting(t, "brokerage_xl")[0])
    result = np.full(n_years, epi - ie) - gross_loss
    recovered = np.zeros(n_years)
    placeable = True

    # Quota share
    q = t.qs
    qs_margin = None
    if q is not None and c.any():
        if float(c.max()) > s.max_cession + 1e-9:
            placeable = False
        lq = float(q.limit)
        per_risk = np.bincount(sim.loss_year, weights=c[sim.loss_line] * np.minimum(sim.loss_size, lq),
                               minlength=n_years)
        qs_100 = sim.attritional @ c + per_risk
        if q.agg_limit is not None:
            qs_100 = np.minimum(qs_100, float(q.agg_limit))
        share = float(q.share)
        prem = float((c * sim.epis).sum())
        lr = qs_100 / prem
        ss = q.terms.sliding_scale
        if ss is not None:
            lo, hi = float(ss.min) + lv.commission_shift, float(ss.max) + lv.commission_shift
            rate = np.clip(hi - (hi - lo) * (lr - float(ss.lr_low)) / float(ss.lr_high - ss.lr_low), lo, hi)
        else:
            rate = np.full(n_years, _f(q.terms.commission) + lv.commission_shift)
        commission = rate * prem
        rme = _f(q.terms.management_expenses) * prem
        pc = _f(q.terms.profit_commission) * np.maximum(prem - qs_100 - commission - rme, 0)
        rec = share * qs_100
        recovered += rec
        result += rec + share * (commission + pc - prem) - (bq + tax) * prem * share
        qs_margin = float(((prem - qs_100 - commission - pc - rme) / prem).mean()) - bq
        if qs_margin < s.min_reinsurer_margin:
            placeable = False

    # Excess of loss, loss by loss
    xl_margins = []
    for layer, limit, annual in _xl_takes(sim, lv, c):
        base_p = _f(f.premium(t, layer))
        base_el = sim.model_layer_el.get(layer.id, 0.0)
        el_now = float(annual.mean())
        moved = lv.xl_retention is not None or lv.cessions is not None
        p = reprice(base_p, base_el, el_now, limit) * lv.xl_price if moved and base_p else base_p * lv.xl_price
        if p > limit * float(layer.share or 1):
            placeable = False  # priced above 100% rate on line: nobody would buy it
        r = layer.reinstatements
        count = r.count if r is not None else 0
        cap = math.inf if count is None else limit * (1 + count)
        taken = np.minimum(annual, cap)
        share = float(layer.share)
        rip = np.zeros(n_years)
        if r is not None and limit > 0 and p > 0:
            used = taken if r.count is None else np.minimum(taken, r.count * limit)
            rip = r.rate * p * used / limit
        ncb = _f(layer.terms.no_claims_bonus) * p * (annual == 0)
        rec = share * taken
        recovered += rec
        result += rec - share * (p + rip - ncb) - (bx + tax) * p * share
        if p > 0:
            m = 1 - (float(taken.mean()) - float(rip.mean()) + float(ncb.mean())) / p - bx
            xl_margins.append(m)
            if m < s.min_reinsurer_margin:
                placeable = False

    # Stop loss on the net loss ratio after QS and XoL
    net_lr = (gross_loss - recovered) / epi
    expected_net_lr = float(net_lr.mean())
    for i, layer in enumerate(sorted(t.sl_layers, key=lambda l: l.attachment)):
        own = float(layer.attachment)
        att = lv.sl_attachment if (i == 0 and lv.sl_attachment is not None) else own
        taken = np.clip(net_lr - att, 0, float(layer.limit)) * epi
        p = _f(f.premium(t, layer))
        if att != own and p:
            # re-price on the change in expected stop loss losses, at the layer's current loading
            base = float(np.clip(net_lr - own, 0, float(layer.limit)).mean()) * epi
            p = reprice(p, base, float(taken.mean()), float(layer.limit) * epi)
        if p > float(layer.limit) * epi:
            placeable = False
        if att < expected_net_lr + 0.05:
            placeable = False  # a stop loss attaching at or below the expected loss ratio is not written
        share = float(layer.share)
        rec = share * taken
        recovered += rec
        result += rec - p * share * (1 + bx + tax)
        if p > 0:
            m = 1 - float(taken.mean()) / p - bx
            xl_margins.append(m)
            if m < s.min_reinsurer_margin:
                placeable = False

    return _summarise(sim, result, gross_loss - recovered, qs_reinsurer_margin=qs_margin,
                      xl_reinsurer_margins=tuple(xl_margins), placeable=placeable)


def risk_metrics(t: Tower, settings: RiskSettings | None = None) -> Metrics:
    return evaluate(simulate(t, settings))


# ---------------------------------------------------------------------- levers and exploration

def lever_options(t: Tower, s: RiskSettings) -> list[dict[str, Any]]:
    """The levers that apply to this programme, with a value range for each."""
    k = float(t.factor)
    opts: list[dict[str, Any]] = []
    if t.qs is not None:
        steps = int(round(s.max_cession / 0.05))
        vals = [round(i * 0.05, 2) for i in range(steps + 1)]
        opts.append({"key": "qs:*", "label": "QS cession, all lines", "unit": "%", "values": vals,
                     "current": round(float(f.qs_cession(t)), 4)})
        for name, _, _, c in (f.qs_lines(t) if t.lines else []):
            opts.append({"key": f"qs:{name}", "label": f"QS cession, {name}", "unit": "%", "values": vals,
                         "current": round(float(c), 4)})
        opts.append({"key": "commission", "label": "QS commission (change)", "unit": "pts",
                     "values": [round(-0.10 + 0.025 * i, 3) for i in range(9)], "current": 0.0})
    xl = sorted(t.xl_layers, key=lambda l: l.attachment)
    if xl:
        a, top = float(xl[0].attachment), float(xl[0].exhaust)
        base = a if a > 0 else top * 0.25
        mults = (0.4, 0.55, 0.7, 0.85, 1.0, 1.25, 1.5, 2.0, 2.5)
        vals = sorted({round(min(base * m, top * 0.9) / k, 3) for m in mults})
        opts.append({"key": "xl_retention", "label": "XoL retention", "unit": t.units, "values": vals,
                     "current": round(a / k, 3)})
        opts.append({"key": "xl_price", "label": "XoL price (ROL ×)", "unit": "×",
                     "values": [round(0.6 + 0.1 * i, 2) for i in range(9)], "current": 1.0})
    sl = sorted(t.sl_layers, key=lambda l: l.attachment)
    if sl:
        a = float(sl[0].attachment)
        opts.append({"key": "sl_attachment", "label": "Stop loss attachment", "unit": "% EPI",
                     "values": sorted({round(a + d, 3) for d in (-0.2, -0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15, 0.2)}),
                     "current": round(a, 3)})
    return opts


def with_lever(lv: Levers, key: str, value: float, t: Tower) -> Levers:
    if key.startswith("qs:"):
        name = key[3:]
        cess = {"*": value} if name == "*" else {**(lv.cessions or {}), name: value}
        return replace(lv, cessions=cess)
    if key == "commission":
        return replace(lv, commission_shift=value)
    if key == "xl_retention":
        return replace(lv, xl_retention=value * float(t.factor))
    if key == "xl_price":
        return replace(lv, xl_price=value)
    if key == "sl_attachment":
        return replace(lv, sl_attachment=value)
    raise ValueError(f"Unknown lever {key!r}")


def pareto(points: list[Metrics]) -> list[bool]:
    """Efficient on all three: no other point has a lower-or-equal net LR, higher-or-equal margin and RoC,
    and is strictly better on at least one."""
    def key(m: Metrics) -> tuple[float, float, float]:
        return (-m.net_loss_ratio, m.margin, m.roc if m.roc is not None else -1e18)

    keys = [key(m) for m in points]
    out = []
    for i, ki in enumerate(keys):
        dominated = any(all(a >= b for a, b in zip(kj, ki)) and any(a > b for a, b in zip(kj, ki))
                        for j, kj in enumerate(keys) if j != i)
        out.append(not dominated)
    return out


def scores(points: list[Metrics], s: RiskSettings) -> list[float]:
    """Weighted score: each measure scaled 0 (worst) to 1 (best) across the points; LR lower is better."""
    def scale(vals: list[float], higher_better: bool) -> list[float]:
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-12:
            return [1.0] * len(vals)
        return [((v - lo) if higher_better else (hi - v)) / (hi - lo) for v in vals]

    lr = scale([m.net_loss_ratio for m in points], False)
    mg = scale([m.margin for m in points], True)
    rc = scale([m.roc if m.roc is not None else 0.0 for m in points], True)
    w = (s.weight_loss_ratio, s.weight_margin, s.weight_roc)
    total = sum(w) or 1.0
    return [(w[0] * a + w[1] * b + w[2] * c) / total for a, b, c in zip(lr, mg, rc)]


@dataclass(frozen=True)
class Explore:
    x: dict[str, Any]
    y: dict[str, Any] | None
    grid: list[list[Metrics]]  # [iy][ix]; one row when there is no y lever
    best: tuple[int, int]
    gross: Metrics
    current: Metrics
    whatif: Metrics
    sim: Any = None
    efficient: list[list[bool]] | None = None  # Pareto-efficient on LR, margin and RoC, among placeable
    score: list[list[float | None]] | None = None

    def to_dict(self) -> dict[str, Any]:
        t = self.sim.tower
        k = float(t.factor)
        iy, ix = self.best
        return {
            "x": self.x, "y": self.y,
            "grid": [[m.to_dict(k) for m in row] for row in self.grid],
            "efficient": self.efficient,
            "score": [[None if v is None else round(v * 100, 1) for v in row] for row in (self.score or [])],
            "weights": {"loss_ratio": self.sim.settings.weight_loss_ratio, "margin": self.sim.settings.weight_margin,
                        "roc": self.sim.settings.weight_roc},
            "best": [iy, ix],
            "best_values": {"x": self.x["values"][ix], "y": self.y["values"][iy] if self.y else None},
            "gross": self.gross.to_dict(k), "current": self.current.to_dict(k), "whatif": self.whatif.to_dict(k),
            "calibration": {"alpha": round(self.sim.alpha, 2),
                            "large_share": [round(v * 100, 1) for v in self.sim.large_share],
                            "calibrated": self.sim.calibrated,
                            "layer_el": {lid: round(v / k, 3) for lid, v in self.sim.model_layer_el.items()}},
        }

    def plot(self) -> Any:
        """Frontier (capital across, expected margin up, colour = RoC) beside the RoC map."""
        import matplotlib.pyplot as plt

        k = float(self.sim.tower.factor)
        pts = [m for row in self.grid for m in row]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8), dpi=100)
        roc = [(m.roc or 0) * 100 for m in pts]
        sc = a1.scatter([m.capital / k for m in pts], [m.margin * 100 for m in pts], c=roc, cmap="Blues",
                        edgecolors=["none" if m.placeable else "#c4513a" for m in pts], s=36)
        g, cur = self.gross, self.current
        a1.scatter([g.capital / k], [g.margin * 100], marker="s", color="#52514e", label="No reinsurance")
        a1.scatter([cur.capital / k], [cur.margin * 100], marker="o", facecolor="white", edgecolor="#0b0b0b",
                   s=70, label="Current")
        b = self.grid[self.best[0]][self.best[1]]
        a1.scatter([b.capital / k], [b.margin * 100], marker="*", color="#eb6834", s=180, label="Best RoC")
        a1.set_xlabel(f"Capital ({self.sim.tower.units})")
        a1.set_ylabel("Expected margin, % of EPI")
        a1.legend(frameon=False, fontsize=8)
        fig.colorbar(sc, ax=a1, label="RoC %")
        if self.y:
            im = a2.imshow([[(m.roc or 0) * 100 for m in row] for row in self.grid], origin="lower", cmap="Blues",
                           aspect="auto")
            a2.set_xticks(range(len(self.x["values"])), [str(v) for v in self.x["values"]], fontsize=7)
            a2.set_yticks(range(len(self.y["values"])), [str(v) for v in self.y["values"]], fontsize=7)
            a2.set_xlabel(self.x["label"])
            a2.set_ylabel(self.y["label"])
            a2.plot([self.best[1]], [self.best[0]], marker="*", color="#eb6834", markersize=14)
            fig.colorbar(im, ax=a2, label="RoC %")
        else:
            a2.plot(self.x["values"], roc, color="#2a78d6")
            a2.set_xlabel(self.x["label"])
            a2.set_ylabel("RoC %")
        fig.tight_layout()
        return fig


def explore(t: Tower, x: str, y: str | None = None, levers: Levers | None = None,
            settings: RiskSettings | None = None, sim: Simulation | None = None) -> Explore:
    """Metrics over one or two levers, holding the rest at `levers`; best = highest RoC that is placeable."""
    s = settings or RiskSettings()
    sim = sim or simulate(t, s)
    lv = levers or Levers()
    opts = {o["key"]: o for o in lever_options(t, s)}
    if x not in opts:
        raise ValueError(f"{x!r} is not a lever for this programme; choose from {sorted(opts)}")
    xo = opts[x]
    yo = opts.get(y) if y and y != x else None
    grid = []
    for yv in (yo["values"] if yo else [None]):
        base = with_lever(lv, yo["key"], float(yv), t) if yo and yv is not None else lv
        grid.append([evaluate(sim, with_lever(base, xo["key"], xv, t)) for xv in xo["values"]])

    def ok(m: Metrics) -> bool:
        return m.placeable and (s.appetite is None or m.bad_year_margin >= s.appetite)

    cells = [(iy, ix) for iy in range(len(grid)) for ix in range(len(grid[0]))]
    scored = [cl for cl in cells if grid[cl[0]][cl[1]].roc is not None]
    pool = [cl for cl in scored if ok(grid[cl[0]][cl[1]])] or scored or cells
    pts = [grid[iy][ix] for iy, ix in pool]
    eff_flags = pareto(pts)
    sc = scores(pts, s)
    efficient = [[False] * len(grid[0]) for _ in grid]
    score: list[list[float | None]] = [[None] * len(grid[0]) for _ in grid]
    for (iy, ix), e, v in zip(pool, eff_flags, sc):
        efficient[iy][ix] = e
        score[iy][ix] = v
    # The best balances the three measures, and is always one of the efficient programmes.
    best = max((cl for cl, e in zip(pool, eff_flags) if e), key=lambda cl: score[cl[0]][cl[1]] or 0.0)
    return Explore(xo, yo, grid, best, gross(sim), evaluate(sim), evaluate(sim, lv), sim, efficient, score)


def apply_levers(t: Tower, lv: Levers, settings: RiskSettings | None = None) -> Tower:
    """Write what-if levers into the programme: cessions, commission, XoL retention and price, SL attachment."""
    from decimal import Decimal

    from .model import SlidingScale

    def d(v: float) -> Decimal:
        return Decimal(str(round(v, 6)))

    sim = simulate(t, settings or replace(RiskSettings(), sims=10_000)) if lv.xl_retention is not None else None
    out = t
    if lv.cessions and out.qs is not None:
        for name, c in lv.cessions.items():
            q0 = out.qs
            if name == "*":
                if out.lines:
                    for line in out.lines:
                        out = out.update_line(line.name, cession=c)
                else:
                    out = out.update(q0.id, cession=c)
            else:
                out = out.update_line(name, cession=c)
    if lv.commission_shift and out.qs is not None:
        q = out.qs
        terms = q.terms
        if terms.sliding_scale is not None:
            ss = terms.sliding_scale
            shift = d(lv.commission_shift)
            terms = replace(terms, sliding_scale=SlidingScale(ss.min + shift, ss.max + shift, ss.lr_low, ss.lr_high))
        else:
            terms = replace(terms, commission=(terms.commission or Decimal(0)) + d(lv.commission_shift))
        out = out.update(q.id, terms=terms)
    xl = sorted(out.xl_layers, key=lambda l: l.attachment)
    if xl and (lv.xl_retention is not None or lv.xl_price != 1.0):
        first = xl[0]
        for layer in xl:
            p = f.premium(out, layer)
            changes: dict[str, Any] = {}
            if layer.id == first.id and lv.xl_retention is not None and lv.xl_retention < float(layer.exhaust):
                assert sim is not None
                before = sim.model_layer_el.get(layer.id, 0.0)
                takes = {lay.id: a for lay, _, a in _xl_takes(sim, lv, sim.base_cessions)}
                after = float(takes[layer.id].mean())
                new_att = d(lv.xl_retention / float(out.factor))
                changes.update(attachment=new_att, limit=d(float(layer.exhaust) / float(out.factor)) - new_att)
                if p is not None and before > 1e-9:
                    p = p * d(after / before)
                if layer.terms.expected_loss is not None and before > 1e-9:
                    changes["terms"] = replace(layer.terms, expected_loss=layer.terms.expected_loss * d(after / before))
            if p is not None:
                changes.update(premium=float(p * d(lv.xl_price)) / float(out.factor), rol=None, adj_rate=None)
            if changes:
                terms = changes.pop("terms", None)
                out = out.update(layer.id, **changes)
                if terms is not None:
                    out = out.update(layer.id, terms=terms)
        if out.retention is not None and lv.xl_retention is not None:
            out = out.update(out.retention.id, limit=lv.xl_retention / float(out.factor))
    if lv.sl_attachment is not None and out.sl_layers:
        s0 = sorted(out.sl_layers, key=lambda l: l.attachment)[0]
        out = out.update(s0.id, attachment=lv.sl_attachment)
    return out
