"""Starter gallery: synthetic programmes to open and remix. All numbers are invented but market-shaped.

Pricing follows typical relationships: a per risk working layer at a rate on line around 50-60% (payback under
two years), middle layers in the teens and single digits, top layers around 1-2%; QS commission close to the
cedant's internal expenses; layer expected losses below premium so reinsurers have a margin.
"""

from __future__ import annotations

from typing import Any

from .model import SlidingScale, Terms, Tower

GALLERY: dict[str, dict[str, Any]] = {
    "per_risk_xol": {
        "title": "Property per risk XoL 2027",
        "subtitle": "Illustrative programme · risks attaching",
        "text": ("epi 120, 2 ret, 3 xs 2 2 @ 100% rate 0.96% el 1.1, 5 xs 5 2 @ 100% rate 0.49% el 0.45, "
                 "10 xs 10 1 @ 100% rate 0.18% el 0.15 ncb 10%, 20 xs 20 @ 80% 1 @ 100% rate 0.14% el 0.05"),
        "programme": {"expected_loss_ratio": "0.55", "tax": "0"},
    },
    "qs_xl_stacked": {
        "title": "Property QS with XoL on the net",
        "subtitle": "Stacked: the QS cedes first, the net passes through the XL layers",
        "text": ("epi 120, qs 20% limit 50 agg 100 comm 37%, 3 xs 2 2 @ 100% rate 0.82% el 0.9, "
                 "5 xs 5 2 @ 100% rate 0.39% el 0.35, 15 xs 10 1 @ 100% rate 0.13% el 0.1"),
        "programme": {"counterparty_limit": "50", "expected_loss_ratio": "0.55", "tax": "0"},
    },
    "qs_xl_side_by_side": {
        "title": "Property QS and XoL side by side",
        "subtitle": "XL attachment and limit × (1 − cession), on the retained share",
        "text": ("epi 120, qs 20% limit 50 agg 100 comm 37%, 3 xs 2 2 @ 100% rate 0.82% el 0.9, "
                 "5 xs 5 2 @ 100% rate 0.39% el 0.35, 15 xs 10 1 @ 100% rate 0.13% el 0.1"),
        "programme": {"arrangement": "side_by_side", "counterparty_limit": "50", "expected_loss_ratio": "0.55",
                      "tax": "0"},
    },
    "credit_qs_xl": {
        "title": "Trade credit QS and XoL 2027",
        "subtitle": "QS limited to the largest buyer limit; XoL per buyer on the net",
        "text": ("epi 200, qs 40% limit 25 agg 320, 15 xs 5 1 @ 100% rate 0.54% el 0.8, "
                 "25 xs 20 1 @ 100% rate 0.13% el 0.15 ncb 10%"),
        "programme": {"counterparty_limit": "25", "expected_loss_ratio": "0.5", "tax": "0"},
        "qs_terms": {"sliding_scale": (0.30, 0.40, 0.40, 0.65), "profit_commission": 0.20,
                     "management_expenses": 0.05},
    },
    "credit_surety": {
        "title": "Credit and surety programme 2027",
        "subtitle": "One QS treaty: 35% of credit, 15% of surety; XoL on the combined net",
        "text": ("qs 20% limit 25 agg 400, 15 xs 5 1 @ 100% rate 0.47% el 0.9, "
                 "25 xs 20 1 @ 100% rate 0.11% el 0.2 ncb 10%"),
        "programme": {"counterparty_limit": "25", "tax": "0"},
        "lines": [("Credit", 200, 0.50, 0.35, 0.30), ("Surety", 60, 0.45, 0.15, 0.35)],
        "qs_terms": {"sliding_scale": (0.30, 0.40, 0.40, 0.65), "profit_commission": 0.20,
                     "management_expenses": 0.05},
    },
    "surety_xl": {
        "title": "Surety XoL 2027",
        "subtitle": "Per principal excess of loss",
        "text": "epi 60, 5 ret, 10 xs 5 1 @ 100% rate 0.92% el 0.4 ncb 10%, 20 xs 15 1 @ 100% rate 0.33% el 0.1",
        "programme": {"expected_loss_ratio": "0.45", "tax": "0"},
    },
    "stop_loss": {
        "title": "Stop loss on the net account",
        "subtitle": "Layers set as % of EPI, shown in amounts",
        "text": "epi 80, sl 20% xs 85% rate 0.61% el 0.34, sl 25% xs 105% @ 75% rate 0.25% el 0.03",
        "programme": {"tax": "0"},
        "lines": [("Property", 80, 0.62, None, 0.25)],
    },
    "full_programme": {
        "title": "Full programme 2027",
        "subtitle": "QS, per risk XoL and stop loss",
        "text": ("epi 150, qs 25% limit 40 agg 150 comm 36%, 2 ret, 8 xs 2 2 @ 100% rate 0.81% el 0.95, "
                 "15 xs 10 1 @ 100% rate 0.11% el 0.12 ncb 10%, sl 15% xs 50% rate 0.15% el 0.08"),
        "programme": {"counterparty_limit": "40", "expected_loss_ratio": "0.56", "tax": "0"},
    },
    "property_cat": {
        "title": "Property cat XL 2027",
        "subtitle": "Illustrative programme · loss occurring",
        "text": ("25 ret, 25 xs 25 1 @ 100% prem 4.1, 50 xs 50 1 @ 100% prem 4.6, "
                 "100 xs 100 @ 90% 1 @ 100% prem 5.2, 150 xs 200 @ 85% 1 @ 100% prem 4.4, "
                 "200 xs 350 @ 70% 1 @ 100% prem 3.6"),
        "programme": {"cover": "cat"},
    },
    "casualty_xl": {
        "title": "Casualty XL 2027",
        "subtitle": "Illustrative programme · losses occurring",
        "text": ("5 ret, 5 xs 5 unl @ 0% prem 1.2, 10 xs 10 2 @ 100% prem 0.9, "
                 "20 xs 20 1 @ 100% prem 0.6, 40 xs 40 @ 80% 1 @ 100% prem 0.4"),
    },
    "thin_retention": {
        "title": "Why log scale exists",
        "subtitle": "A thin retention under a tall tower",
        "text": "2 ret, 8 xs 2, 40 xs 10, 150 xs 50, 300 xs 200, 500 xs 500",
    },
    "gap_overlap": {
        "title": "Gap and overlap",
        "subtitle": "Warnings shown in place, with fixes",
        "text": "10 ret, 40 xs 10, 50 xs 60, 60 xs 100, 100 xs 140",
    },
    "partly_placed": {
        "title": "Partly placed programme",
        "subtitle": "Unplaced shares drawn hatched",
        "text": "15 ret, 35 xs 15 @ 100%, 50 xs 50 @ 82.5%, 100 xs 100 @ 60%, 100 xs 200 @ 35%",
    },
}

# A synthetic portfolio for trying trapped exposure: risk, exposure (sum insured) in millions.
EXAMPLE_PORTFOLIO: list[tuple[str, float]] = [
    ("Warehouse, Leeds", 1.5), ("Retail park, Bristol", 4.2), ("Office block, Manchester", 7.8),
    ("Hotel, Edinburgh", 12.0), ("Factory, Coventry", 18.5), ("Shopping centre, Glasgow", 26.0),
    ("Distribution hub, Milton Keynes", 34.0), ("Data centre, Slough", 48.0), ("Refinery, Grangemouth", 65.0),
    ("Airport terminal, Luton", 85.0),
]


def load(name: str) -> Tower:
    g = GALLERY[name]
    t = Tower.from_text(g["text"], title=g["title"], subtitle=g["subtitle"])
    prog = dict(g.get("programme", {}))
    if prog:
        t = t.programme(**{k: (v if k in ("arrangement", "cover") else float(v)) for k, v in prog.items()})
    for name, epi, el, cession, cv in g.get("lines", []):
        t = t.add_line(name, epi, expected_loss_ratio=el, cession=cession, volatility=cv)
    qs_terms = g.get("qs_terms")
    if qs_terms and t.qs is not None:
        lo, hi, lr_lo, lr_hi = qs_terms["sliding_scale"]
        t = t.update(t.qs.id, terms=Terms(
            sliding_scale=SlidingScale(min=lo, max=hi, lr_low=lr_lo, lr_high=lr_hi),
            profit_commission=qs_terms.get("profit_commission"),
            management_expenses=qs_terms.get("management_expenses"),
        ))
    return t


def names() -> list[str]:
    return list(GALLERY)
