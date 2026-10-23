"""Core immutable data model: Reinstatements, Layer, Tower.

Amounts are stored as Decimal in full currency units on a 100% basis.
Public methods that take amounts accept numbers in the tower's display
unit (``units``), or strings such as ``"50m"``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .loss import LossResult
    from .scene import Scene, View
    from .validate import Diagnostic, Fix

Units = Literal["", "k", "m", "bn"]
Amount = int | float | Decimal | str

UNIT_FACTOR: dict[str, Decimal] = {
    "": Decimal(1),
    "k": Decimal(1_000),
    "m": Decimal(1_000_000),
    "bn": Decimal(1_000_000_000),
}
CURRENCY_SYMBOL = {"GBP": "£", "USD": "$", "EUR": "€", "JPY": "¥"}
TOWER_SCHEMA = "ri-layercake/tower@1"
ONE = Decimal(1)
ZERO = Decimal(0)


def to_decimal(x: int | float | Decimal | str) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        return Decimal(repr(x))
    return Decimal(x)


def normalize(d: Decimal) -> Decimal:
    """Strip trailing zeros without switching to exponent notation."""
    if d == d.to_integral_value():
        return d.quantize(ONE)
    return d.normalize()


@dataclass(frozen=True)
class Reinstatements:
    count: int | None = None  # None = unlimited
    rate: float = 1.0  # 1.0 = 100% additional premium
    pro_rata: str = "amount"  # "amount" | "time" | "amount_and_time"


@dataclass(frozen=True)
class SlidingScale:
    """Commission that slides with the loss ratio: max at or below lr_low, min at or above lr_high."""

    min: Decimal
    max: Decimal
    lr_low: Decimal
    lr_high: Decimal

    def __post_init__(self) -> None:
        for k in ("min", "max", "lr_low", "lr_high"):
            object.__setattr__(self, k, to_decimal(getattr(self, k)))
        if self.lr_high <= self.lr_low:
            raise ValueError("Sliding scale: the high loss ratio must be above the low one")

    def rate(self, loss_ratio: Decimal) -> Decimal:
        if loss_ratio <= self.lr_low:
            return self.max
        if loss_ratio >= self.lr_high:
            return self.min
        span = self.lr_high - self.lr_low
        return self.max - (self.max - self.min) * (loss_ratio - self.lr_low) / span


@dataclass(frozen=True)
class Terms:
    """Commercial terms. All rates are fractions of the relevant premium."""

    commission: Decimal | None = None  # QS ceding commission
    sliding_scale: SlidingScale | None = None  # QS: replaces the flat commission
    profit_commission: Decimal | None = None  # QS: share of the reinsurer's profit
    management_expenses: Decimal | None = None  # QS: reinsurer management expenses (RME)
    no_claims_bonus: Decimal | None = None  # XL: premium returned if no claims
    expected_loss: Decimal | None = None  # XL/SL: the layer's expected loss (amount, 100% basis)

    def __post_init__(self) -> None:
        for k in ("commission", "profit_commission", "management_expenses", "no_claims_bonus", "expected_loss"):
            v = getattr(self, k)
            if v is not None and not isinstance(v, Decimal):
                object.__setattr__(self, k, to_decimal(v))


@dataclass(frozen=True)
class Line:
    """A line of business inside one programme, e.g. Credit or Surety.

    Each line has its own gross EPI, expected loss ratio and QS cession (the QS treaty is shared but its
    cession can differ by line); the XoL and stop loss sit over the combined net. Volatility is the
    coefficient of variation of the line's annual loss ratio, used by the risk view.
    """

    name: str
    epi: Decimal
    expected_loss_ratio: Decimal | None = None
    cession: Decimal | None = None  # None: the QS treaty's own cession
    volatility: Decimal | None = None  # attritional loss ratio volatility; None: the default (10%)

    def __post_init__(self) -> None:
        for k in ("epi", "expected_loss_ratio", "cession", "volatility"):
            v = getattr(self, k)
            if v is not None and not isinstance(v, Decimal):
                object.__setattr__(self, k, to_decimal(v))


KINDS = ("retention", "qs", "xl", "sl")
Kind = Literal["retention", "qs", "xl", "sl"]


@dataclass(frozen=True)
class Layer:
    """One cover in the programme.

    For ``retention``, ``qs`` and ``xl`` layers, limit and attachment are amounts on a 100% basis
    (a QS limit is its per-risk limit). For ``sl`` (stop loss) layers they are loss ratios: fractions
    of the gross EPI, so ``SL 20% xs 80%`` is limit 0.2, attachment 0.8.
    """

    id: str  # stable, e.g. "L3", "Q1", "S1"
    kind: Kind
    limit: Decimal
    attachment: Decimal
    placed: Decimal = ONE  # share of the order that is placed, 0..1
    written: Decimal | None = None  # optional: the user's own line
    premium: Decimal | None = None  # premium (RTE), 100% basis
    reinstatements: Reinstatements | None = None
    name: str | None = None
    note: str | None = None
    rol: Decimal | None = None  # rate on line as entered, if any
    order: Decimal = ONE  # share of the 100% layer put to market
    cession: Decimal | None = None  # QS: share of each risk ceded
    adj_rate: Decimal | None = None  # adjusted rate on EPI, as entered
    agg_limit: Decimal | None = None  # QS: aggregate limit as entered
    terms: Terms = field(default_factory=Terms)

    @property
    def exhaust(self) -> Decimal:
        return self.attachment + self.limit

    @property
    def share(self) -> Decimal:
        """Effective share with reinsurers: order x placed."""
        return self.order * self.placed

    @property
    def effective_premium(self) -> Decimal | None:
        """Premium on 100% basis, derived from rate on line when not entered."""
        if self.premium is not None:
            return self.premium
        if self.rol is not None:
            return self.rol * self.limit
        return None

    @property
    def rate_on_line(self) -> Decimal | None:
        p = self.effective_premium
        if p is None or self.limit <= 0:
            return None
        return p / self.limit

    def sort_key(self) -> tuple[int, Decimal, Decimal]:
        return (KINDS.index(self.kind), self.attachment, self.limit)


def terms_to_dict(t: Terms) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("commission", "profit_commission", "management_expenses", "no_claims_bonus", "expected_loss"):
        v = getattr(t, key)
        if v is not None:
            out[key] = str(v)
    if t.sliding_scale is not None:
        ss = t.sliding_scale
        out["sliding_scale"] = {"min": str(ss.min), "max": str(ss.max), "lr_low": str(ss.lr_low),
                                "lr_high": str(ss.lr_high)}
    return out


def terms_from_dict(d: dict[str, Any] | None) -> Terms:
    if not d:
        return Terms()

    def dec(v: Any) -> Decimal | None:
        return None if v is None or v == "" else to_decimal(v)

    ss = d.get("sliding_scale")
    sliding = None
    if ss and all(ss.get(k) not in (None, "") for k in ("min", "max", "lr_low", "lr_high")):
        sliding = SlidingScale(*(to_decimal(ss[k]) for k in ("min", "max", "lr_low", "lr_high")))
    return Terms(
        commission=dec(d.get("commission")), sliding_scale=sliding,
        profit_commission=dec(d.get("profit_commission")),
        management_expenses=dec(d.get("management_expenses")),
        no_claims_bonus=dec(d.get("no_claims_bonus")),
        expected_loss=dec(d.get("expected_loss")),
    )


def _sorted(layers: tuple[Layer, ...] | list[Layer]) -> tuple[Layer, ...]:
    return tuple(sorted(layers, key=Layer.sort_key))


@dataclass(frozen=True)
class Tower:
    layers: tuple[Layer, ...] = ()
    currency: str = "GBP"  # ISO 4217
    units: Units = "m"
    title: str | None = None
    subtitle: str | None = None
    basis: Literal["loss_occurring", "risks_attaching"] | None = None
    accepted: frozenset[str] = frozenset()  # diagnostic keys the user chose to keep
    epi: Decimal | None = None  # gross estimated premium income
    arrangement: Literal["stacked", "side_by_side"] = "stacked"  # how QS and XL combine
    cover: Literal["per_risk", "cat"] = "per_risk"
    counterparty_limit: Decimal | None = None  # CRM limit for the largest counterparty
    internal_expenses: Decimal | None = None  # fraction of EPI
    expected_loss_ratio: Decimal | None = None  # analytic EL, fraction of EPI
    brokerage_xl: Decimal | None = None  # fraction of XL and stop loss premium; None uses the default (10%)
    brokerage_qs: Decimal | None = None  # fraction of QS premium; None uses the default (2.5%)
    tax: Decimal | None = None  # fraction of ceded reinsurance premium
    lines: tuple[Line, ...] = ()  # lines of business; when present they set the EPI and expected loss ratio
    diagnostics: tuple[Diagnostic, ...] = field(default=(), compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "layers", _sorted(self.layers))
        if self.lines:
            epi = sum((l.epi for l in self.lines), ZERO)
            object.__setattr__(self, "epi", epi)
            if epi and all(l.expected_loss_ratio is not None for l in self.lines):
                el = sum((l.epi * l.expected_loss_ratio for l in self.lines), ZERO)  # type: ignore[operator]
                object.__setattr__(self, "expected_loss_ratio", normalize(el / epi))

    # ------------------------------------------------------------------ helpers

    @property
    def factor(self) -> Decimal:
        return UNIT_FACTOR[self.units]

    def amount(self, x: Amount) -> Decimal:
        """Convert a user amount (tower units, or a string like '50m') to full units."""
        if isinstance(x, str):
            from .parse import parse_amount

            value = parse_amount(x, self.units)
            if value is None:
                raise ValueError(f"Not an amount: {x!r}")
            return value
        return to_decimal(x) * self.factor

    def in_units(self, value: Decimal) -> Decimal:
        return normalize(value / self.factor)

    @property
    def retention(self) -> Layer | None:
        return next((l for l in self.layers if l.kind == "retention"), None)

    @property
    def xl_layers(self) -> tuple[Layer, ...]:
        return tuple(l for l in self.layers if l.kind == "xl")

    @property
    def qs(self) -> Layer | None:
        return next((l for l in self.layers if l.kind == "qs"), None)

    @property
    def sl_layers(self) -> tuple[Layer, ...]:
        return tuple(l for l in self.layers if l.kind == "sl")

    def layer(self, layer_id: str) -> Layer:
        for l in self.layers:
            if l.id == layer_id:
                return l
        raise KeyError(layer_id)

    def _next_id(self, prefix: str = "L") -> str:
        nums = [int(l.id[1:]) for l in self.layers if l.id.startswith(prefix) and l.id[1:].isdigit()]
        return f"{prefix}{max(nums, default=0) + 1}"

    def with_layers(self, layers: tuple[Layer, ...] | list[Layer]) -> Tower:
        return replace(self, layers=tuple(layers), diagnostics=())

    def layer_number(self, layer_id: str) -> int:
        """1-based position among layers of the same kind, used in names like 'Layer 3'."""
        kind = self.layer(layer_id).kind
        same = [l for l in self.layers if l.kind == kind]
        for i, l in enumerate(same, 1):
            if l.id == layer_id:
                return i
        return 0

    def display_name(self, layer: Layer) -> str:
        if layer.name:
            return layer.name
        if layer.kind == "retention":
            return "Retention"
        if layer.kind == "qs":
            return "Quota share"
        n = self.layer_number(layer.id)
        if layer.kind == "sl":
            return "Stop loss" if len(self.sl_layers) == 1 else f"Stop loss {n}"
        return f"Layer {n}"

    # ------------------------------------------------------------------ editing

    def add_retention(self, amount: Amount) -> Tower:
        others = [l for l in self.layers if l.kind != "retention"]
        ret = Layer(id="R", kind="retention", limit=self.amount(amount), attachment=ZERO)
        return self.with_layers([ret, *others])

    def add_xl(
        self,
        limit: Amount,
        attachment: Amount,
        placed: float | Decimal = 1,
        premium: Amount | None = None,
        reinstatements: Reinstatements | None = None,
        name: str | None = None,
        rol: float | Decimal | None = None,
        order: float | Decimal = 1,
        adj_rate: float | Decimal | None = None,
        terms: Terms | None = None,
    ) -> Tower:
        """Add an excess of loss layer. Terms carry the expected loss (in tower units) and no claims bonus."""
        if terms is not None and terms.expected_loss is not None:
            terms = replace(terms, expected_loss=self.amount(terms.expected_loss))
        layer = Layer(
            id=self._next_id(),
            kind="xl",
            limit=self.amount(limit),
            attachment=self.amount(attachment),
            placed=to_decimal(placed),
            premium=None if premium is None else self.amount(premium),
            reinstatements=reinstatements,
            name=name,
            rol=None if rol is None else to_decimal(rol),
            order=to_decimal(order),
            adj_rate=None if adj_rate is None else to_decimal(adj_rate),
            terms=terms or Terms(),
        )
        return self.with_layers([*self.layers, layer])

    def add_qs(
        self,
        cession: float | Decimal,
        limit: Amount,
        agg_limit: Amount | None = None,
        premium: Amount | None = None,
        placed: float | Decimal = 1,
        order: float | Decimal = 1,
        name: str | None = None,
        terms: Terms | None = None,
    ) -> Tower:
        """Add a quota share: cession is the share of each risk ceded, limit is its per-risk limit."""
        if self.qs is not None:
            raise ValueError("A programme has one quota share; update it instead")
        layer = Layer(
            id=self._next_id("Q"), kind="qs", limit=self.amount(limit), attachment=ZERO,
            cession=to_decimal(cession), agg_limit=None if agg_limit is None else self.amount(agg_limit),
            premium=None if premium is None else self.amount(premium), placed=to_decimal(placed),
            order=to_decimal(order), name=name, terms=terms or Terms(),
        )
        return self.with_layers([*self.layers, layer])

    def add_sl(
        self,
        limit: float | Decimal,
        attachment: float | Decimal,
        premium: Amount | None = None,
        adj_rate: float | Decimal | None = None,
        placed: float | Decimal = 1,
        order: float | Decimal = 1,
        name: str | None = None,
        rol: float | Decimal | None = None,
        terms: Terms | None = None,
    ) -> Tower:
        """Add a stop loss. Limit and attachment are loss ratios: add_sl(0.2, 0.8) is 20% xs 80% of EPI."""
        if terms is not None and terms.expected_loss is not None:
            terms = replace(terms, expected_loss=self.amount(terms.expected_loss))
        layer = Layer(
            id=self._next_id("S"), kind="sl", limit=to_decimal(limit), attachment=to_decimal(attachment),
            premium=None if premium is None else self.amount(premium),
            adj_rate=None if adj_rate is None else to_decimal(adj_rate),
            placed=to_decimal(placed), order=to_decimal(order), name=name,
            rol=None if rol is None else to_decimal(rol), terms=terms or Terms(),
        )
        return self.with_layers([*self.layers, layer])

    def line(self, name: str) -> Line:
        for l in self.lines:
            if l.name == name:
                return l
        raise KeyError(name)

    def add_line(self, name: str, epi: Amount, expected_loss_ratio: float | Decimal | None = None,
                 cession: float | Decimal | None = None, volatility: float | Decimal | None = None) -> Tower:
        """Add a line of business: its EPI (tower units), expected loss ratio, QS cession and volatility."""
        if any(l.name == name for l in self.lines):
            raise ValueError(f"A line called {name!r} already exists")
        line = Line(name, self.amount(epi), expected_loss_ratio, cession, volatility)  # type: ignore[arg-type]
        return replace(self, lines=(*self.lines, line), diagnostics=())

    def update_line(self, name: str, **fields: Any) -> Tower:
        old = self.line(name)
        changes = {k: (self.amount(v) if k == "epi" and v is not None else v) for k, v in fields.items()}
        if "name" in changes and changes["name"] != name and any(l.name == changes["name"] for l in self.lines):
            raise ValueError(f"A line called {changes['name']!r} already exists")
        new = Line(**{**{k: getattr(old, k) for k in ("name", "epi", "expected_loss_ratio", "cession", "volatility")},
                      **changes})
        return replace(self, lines=tuple(new if l.name == name else l for l in self.lines), diagnostics=())

    def remove_line(self, name: str) -> Tower:
        self.line(name)
        lines = tuple(l for l in self.lines if l.name != name)
        out = replace(self, lines=lines, diagnostics=())
        return out if lines else replace(out, epi=self.epi, expected_loss_ratio=self.expected_loss_ratio)

    def programme(self, **fields: Any) -> Tower:
        """Set programme-wide fields: epi, counterparty_limit (tower units), arrangement, cover, title..."""
        changes: dict[str, Any] = {}
        for key, value in fields.items():
            if key in ("epi", "counterparty_limit"):
                changes[key] = None if value is None else self.amount(value)
            elif key in ("internal_expenses", "expected_loss_ratio", "brokerage_xl", "brokerage_qs", "tax"):
                changes[key] = None if value is None else to_decimal(value)
            elif key == "arrangement" and value not in ("stacked", "side_by_side"):
                raise ValueError("arrangement is 'stacked' or 'side_by_side'")
            elif key == "cover" and value not in ("per_risk", "cat"):
                raise ValueError("cover is 'per_risk' or 'cat'")
            elif key in ("arrangement", "cover", "title", "subtitle", "currency", "units", "basis"):
                changes[key] = value
            else:
                raise TypeError(f"Unknown programme field: {key}")
        return replace(self, **changes, diagnostics=())

    def update(self, layer_id: str, **fields: Any) -> Tower:
        """Change fields of one layer. Amount fields take tower units; rates and shares are fractions.

        Stop loss limit and attachment are loss ratios (fractions of EPI).
        """
        old = self.layer(layer_id)
        changes: dict[str, Any] = {}
        for key, value in fields.items():
            if key in ("limit", "attachment") and old.kind == "sl":
                changes[key] = to_decimal(value)
            elif key in ("limit", "attachment", "premium", "agg_limit"):
                changes[key] = None if value is None else self.amount(value)
            elif key in ("placed", "written", "rol", "order", "cession", "adj_rate"):
                changes[key] = None if value is None else to_decimal(value)
                if key in ("placed", "order") and value is None:
                    changes[key] = ONE
            elif key == "reinstatements" and isinstance(value, dict):
                changes[key] = Reinstatements(**value)
            elif key == "terms":
                changes[key] = value if isinstance(value, Terms) else terms_from_dict(value)
            elif key in ("name", "note", "reinstatements"):
                changes[key] = value
            else:
                raise TypeError(f"Unknown layer field: {key}")
        new = replace(old, **changes)
        return self.with_layers([new if l.id == layer_id else l for l in self.layers])

    def remove(self, layer_id: str) -> Tower:
        self.layer(layer_id)
        return self.with_layers([l for l in self.layers if l.id != layer_id])

    def split(self, layer_id: str, at: Amount) -> Tower:
        """Split a layer at an absolute value inside it into two stacked layers."""
        old = self.layer(layer_id)
        if old.kind not in ("xl", "retention"):
            raise ValueError("Only excess of loss layers can be split")
        cut = self.amount(at)
        if not (old.attachment < cut < old.exhaust):
            raise ValueError("Split point must lie strictly inside the layer")
        lower_limit = cut - old.attachment
        upper_limit = old.exhaust - cut
        def share(p: Decimal | None) -> Decimal | None:
            return None if p is None else p * (lower_limit / old.limit)

        lower = replace(
            old,
            limit=lower_limit,
            premium=share(old.premium),
            name=None if old.name is None else f"{old.name} (lower)",
        )
        upper = replace(
            old,
            id=self._next_id(),
            limit=upper_limit,
            attachment=cut,
            premium=None if old.premium is None else old.premium - lower.premium,  # type: ignore[operator]
            name=None if old.name is None else f"{old.name} (upper)",
        )
        if old.kind == "retention":
            upper = replace(upper, kind="xl")
        rest = [l for l in self.layers if l.id != layer_id]
        return self.with_layers([*rest, lower, upper])

    def merge(self, a: str, b: str) -> Tower:
        """Merge two adjacent layers into one spanning both."""
        la, lb = sorted((self.layer(a), self.layer(b)), key=Layer.sort_key)
        if la.kind not in ("xl", "retention") or lb.kind not in ("xl", "retention"):
            raise ValueError("Only excess of loss layers can be merged")
        attachment = min(la.attachment, lb.attachment)
        exhaust = max(la.exhaust, lb.exhaust)
        premium = None
        if la.effective_premium is not None or lb.effective_premium is not None:
            premium = (la.effective_premium or ZERO) + (lb.effective_premium or ZERO)
        merged = replace(
            la,
            kind="xl" if la.kind == "xl" or lb.kind == "xl" else la.kind,
            attachment=attachment,
            limit=exhaust - attachment,
            placed=min(la.placed, lb.placed),
            premium=premium,
            rol=None,
        )
        rest = [l for l in self.layers if l.id not in (la.id, lb.id)]
        return self.with_layers([*rest, merged])

    def accept(self, key: str) -> Tower:
        return replace(self, accepted=self.accepted | {key})

    # ------------------------------------------------------------------ loading

    @classmethod
    def from_text(cls, text: str, **kwargs: Any) -> Tower:
        from .parse import parse_shorthand

        return parse_shorthand(text, **kwargs)

    @classmethod
    def from_paste(cls, text: str, **kwargs: Any) -> Tower:
        from .parse import parse_paste

        return parse_paste(text, **kwargs)

    @classmethod
    def from_csv(cls, path: str, **kwargs: Any) -> Tower:
        from .parse import parse_rows, read_csv_rows

        return parse_rows(read_csv_rows(path), **kwargs)

    @classmethod
    def from_excel(cls, path: str, sheet: str | None = None, **kwargs: Any) -> Tower:
        from .parse import parse_rows, read_excel_rows

        return parse_rows(read_excel_rows(path, sheet), **kwargs)

    @classmethod
    def from_dataframe(cls, df: Any, **kwargs: Any) -> Tower:
        from .parse import parse_rows

        rows = [[str(c) for c in df.columns]]
        rows += [["" if v is None else str(v) for v in rec] for rec in df.itertuples(index=False)]
        return parse_rows(rows, **kwargs)

    @classmethod
    def from_json(cls, text: str | dict[str, Any]) -> Tower:
        data = json.loads(text) if isinstance(text, str) else text
        if data.get("schema") != TOWER_SCHEMA:
            raise ValueError(f"Unsupported schema: {data.get('schema')!r}")

        def dec(v: Any) -> Decimal | None:
            return None if v is None else Decimal(v)

        layers = []
        for d in data["layers"]:
            ri = d.get("reinstatements")
            layers.append(
                Layer(
                    id=d["id"],
                    kind=d["kind"],
                    limit=Decimal(d["limit"]),
                    attachment=Decimal(d["attachment"]),
                    placed=Decimal(d.get("placed", "1")),
                    written=dec(d.get("written")),
                    premium=dec(d.get("premium")),
                    reinstatements=None if ri is None else Reinstatements(**ri),
                    name=d.get("name"),
                    note=d.get("note"),
                    rol=dec(d.get("rol")),
                    order=Decimal(d.get("order", "1")),
                    cession=dec(d.get("cession")),
                    adj_rate=dec(d.get("adj_rate")),
                    agg_limit=dec(d.get("agg_limit")),
                    terms=terms_from_dict(d.get("terms")),
                )
            )
        return cls(
            layers=tuple(layers),
            currency=data.get("currency", "GBP"),
            units=data.get("units", "m"),
            title=data.get("title"),
            subtitle=data.get("subtitle"),
            basis=data.get("basis"),
            accepted=frozenset(data.get("accepted", [])),
            epi=dec(data.get("epi")),
            arrangement=data.get("arrangement", "stacked"),
            cover=data.get("cover", "per_risk"),
            counterparty_limit=dec(data.get("counterparty_limit")),
            internal_expenses=dec(data.get("internal_expenses")),
            expected_loss_ratio=dec(data.get("expected_loss_ratio")),
            brokerage_xl=dec(data.get("brokerage_xl", data.get("brokerage"))),
            brokerage_qs=dec(data.get("brokerage_qs")),
            tax=dec(data.get("tax")),
            lines=tuple(Line(d["name"], Decimal(d["epi"]), dec(d.get("expected_loss_ratio")), dec(d.get("cession")),
                             dec(d.get("volatility"))) for d in data.get("lines", [])),
        )

    # ------------------------------------------------------------------ output

    def to_dict(self) -> dict[str, Any]:
        def s(v: Decimal | None) -> str | None:
            return None if v is None else str(v)

        layers = []
        for l in self.layers:
            d: dict[str, Any] = {
                "id": l.id,
                "kind": l.kind,
                "limit": s(l.limit),
                "attachment": s(l.attachment),
                "placed": s(l.placed),
            }
            if l.order != ONE:
                d["order"] = s(l.order)
            for key in ("written", "premium", "rol", "cession", "adj_rate", "agg_limit"):
                if getattr(l, key) is not None:
                    d[key] = s(getattr(l, key))
            terms = terms_to_dict(l.terms)
            if terms:
                d["terms"] = terms
            if l.reinstatements is not None:
                r = l.reinstatements
                d["reinstatements"] = {"count": r.count, "rate": r.rate, "pro_rata": r.pro_rata}
            for key in ("name", "note"):
                if getattr(l, key) is not None:
                    d[key] = getattr(l, key)
            layers.append(d)
        out: dict[str, Any] = {"schema": TOWER_SCHEMA, "currency": self.currency, "units": self.units}
        for key in ("title", "subtitle", "basis"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        for key in ("epi", "counterparty_limit", "internal_expenses", "expected_loss_ratio", "brokerage_xl",
                    "brokerage_qs", "tax"):
            if getattr(self, key) is not None:
                out[key] = s(getattr(self, key))
        if self.arrangement != "stacked":
            out["arrangement"] = self.arrangement
        if self.lines:
            out["lines"] = [{k: (str(v) if isinstance(v, Decimal) else v) for k, v in
                             (("name", l.name), ("epi", l.epi), ("expected_loss_ratio", l.expected_loss_ratio),
                              ("cession", l.cession), ("volatility", l.volatility)) if v is not None}
                            for l in self.lines]
        if self.cover != "per_risk":
            out["cover"] = self.cover
        if self.accepted:
            out["accepted"] = sorted(self.accepted)
        out["layers"] = layers
        return out

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=False)

    def to_text(self) -> str:
        from .parse import format_shorthand

        return format_shorthand(self)

    def to_code(self, view: View | None = None) -> str:
        from .codegen import to_code

        return to_code(self, view)

    def validate(self, view: View | None = None) -> list[Diagnostic]:
        from .validate import validate

        return validate(self, view)

    def apply(self, fix: Fix) -> Tower:
        from .validate import apply_fix

        return apply_fix(self, fix)

    def table(self) -> Any:
        from .table import table

        return table(self)

    def drop_loss(self, amount: Amount, line: str | None = None) -> LossResult:
        """One risk's loss (or exposure) through the programme, per risk, at its line's QS cession."""
        from .loss import drop_loss

        return drop_loss(self, self.amount(amount), line)

    def exposure(self, amount: Amount, line: str | None = None) -> LossResult:
        """Trapped exposure for one risk: median(0, E - A, L) per layer, after the QS."""
        return self.drop_loss(amount, line)

    def aggregate(self, amount: Amount) -> Any:
        """A year's aggregate loss: QS cession and terms, then stop loss on the net loss ratio."""
        from .loss import aggregate

        return aggregate(self, self.amount(amount))

    def portfolio(self, risks: Any) -> Any:
        """Trapped exposure across a portfolio: [(id, exposure)], a dict, pasted text, or a CSV/Excel path."""
        from .loss import portfolio
        from .parse import parse_portfolio

        if isinstance(risks, dict):
            pairs = [(str(k), self.amount(v)) for k, v in risks.items()]
        elif isinstance(risks, str):
            pairs = parse_portfolio(risks, self)
        else:
            pairs = [(str(k), self.amount(v)) for k, v in risks]
        return portfolio(self, pairs)

    def premium_walk(self) -> Any:
        """From gross EPI to result and margin after reinsurance."""
        from .walk import premium_walk

        return premium_walk(self)

    def scene(self, view: View | None = None, **options: Any) -> Scene:
        from .scene import View, layout

        return layout(self, view or View(**options))

    def to_svg(self, view: View | None = None, **options: Any) -> str:
        from .render_svg import render_svg

        return render_svg(self.scene(view, **options))

    def to_pptx(
        self,
        path_or_buffer: Any = None,
        view: View | None = None,
        template: Any = None,
        **options: Any,
    ) -> Any:
        from .render_pptx import to_pptx

        return to_pptx(self, path_or_buffer, view=view, template=template, **options)

    def plot(self, view: View | None = None, ax: Any = None, **options: Any) -> Any:
        """Draw the tower with matplotlib; returns the Figure (same layout as the slide)."""
        from .render_mpl import plot_scene

        return plot_scene(self.scene(view, **options), ax=ax)

    def show(self, **options: Any) -> Any:
        from .render_svg import TowerDisplay

        return TowerDisplay(self, **options)

    def _repr_svg_(self) -> str:
        return self.to_svg()

    def _repr_html_(self) -> str:
        from .render_svg import html_with_table

        return html_with_table(self)
