"""The layer table, exactly as it is drawn and exported."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from . import fmt
from . import formulas as f
from .model import ZERO

if TYPE_CHECKING:
    from .model import Layer, Tower

TIPS = {
    "Premium (RTE)": f.FORMULAS["premium"],
    "ROL": f.FORMULAS["rol"],
    "Adj. rate": f.FORMULAS["adj_rate"],
    "Agg limit": f.FORMULAS["agg_limit"],
    "Order": "Share of the 100% layer put to market",
    "Placed": "Share of the order that is placed",
}


@dataclass(frozen=True)
class TableData:
    columns: list[str]
    rows: list[list[str]]
    totals: list[str]
    layer_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        tips = {c: TIPS[k] for c in self.columns for k in TIPS if c.startswith(k)}
        return {"columns": self.columns, "rows": self.rows, "totals": self.totals, "layers": self.layer_ids,
                "tips": tips}


def _row_order(tower: Tower) -> list[Layer]:
    """Stop loss first, then the XL tower top down, then retention, then the QS, as a broker slide reads."""
    sl = sorted(tower.sl_layers, key=lambda l: l.attachment, reverse=True)
    xl = list(reversed([l for l in tower.layers if l.kind in ("xl", "retention")]))
    qs = [tower.qs] if tower.qs else []
    return [*sl, *xl, *qs]


def table_data(tower: Tower) -> TableData:
    unit = f"{fmt.symbol(tower.currency).strip()}{tower.units}"
    our = any(l.written is not None for l in tower.layers)
    columns = ["Layer", f"Limit ({unit})", f"Attachment ({unit})", "Order", "Placed", f"Premium (RTE) ({unit})",
               "ROL", "Adj. rate", f"Agg limit ({unit})"]
    if our:
        columns.append("Our share")

    def n(v: Decimal | None) -> str:
        return fmt.num(tower, v)

    rows, ids = [], []
    for l in _row_order(tower):
        name = tower.display_name(l)
        if l.kind == "retention":
            row = [name, n(l.limit), "", "", "", "", "", "", ""]
        elif l.kind == "qs":
            row = [f"{name} {fmt.pct(l.cession)}", n(l.limit), "", fmt.pct(l.order), fmt.pct(l.placed),
                   n(f.premium(tower, l)), "", fmt.pct(f.adj_rate(tower, l)), n(f.agg_limit(tower, l))]
        elif l.kind == "sl":
            lim, att = f.limit_amount(tower, l), f.attachment_amount(tower, l)
            row = [name, n(lim) if lim is not None else f"{fmt.pct(l.limit)} EPI",
                   n(att) if att is not None else f"{fmt.pct(l.attachment)} EPI",
                   fmt.pct(l.order), fmt.pct(l.placed), n(f.premium(tower, l)), fmt.pct(f.rol(tower, l)),
                   fmt.pct(f.adj_rate(tower, l)), n(f.agg_limit(tower, l))]
        else:
            row = [name, n(l.limit), n(l.attachment), fmt.pct(l.order), fmt.pct(l.placed), n(f.premium(tower, l)),
                   fmt.pct(f.rol(tower, l)), fmt.pct(f.adj_rate(tower, l)), n(f.agg_limit(tower, l))]
        if our:
            row.append(fmt.pct(l.written))
        rows.append(row)
        ids.append(l.id)
    total_limit = sum((l.limit for l in tower.xl_layers), ZERO)
    known = [p for p in (f.premium(tower, l) for l in tower.layers if l.kind != "retention") if p is not None]
    total_prem: Decimal | None = sum(known, ZERO) if known else None
    totals = ["Total", n(total_limit), "", "", "", n(total_prem), "", "", ""]
    if our:
        totals.append("")
    return TableData(columns, rows, totals, ids)


def table(tower: Tower) -> Any:
    """Rows as a pandas DataFrame."""
    import pandas as pd

    data = table_data(tower)
    return pd.DataFrame([dict(zip(data.columns, r)) for r in data.rows], columns=data.columns)
