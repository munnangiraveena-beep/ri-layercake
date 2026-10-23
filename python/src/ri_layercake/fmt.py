"""Display formatting. Rounding is display only: one decimal place unless whole."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from .model import CURRENCY_SYMBOL, Layer

if TYPE_CHECKING:
    from .model import Tower

TENTH = Decimal("0.1")


def plain(d: Decimal) -> str:
    """A Decimal as plain digits, no exponent, no trailing zeros."""
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def round1(d: Decimal) -> str:
    r = d.quantize(TENTH, rounding=ROUND_HALF_UP)
    if r == r.to_integral_value():
        return plain(r.to_integral_value())
    return plain(r)


def num(tower: Tower, value: Decimal | None) -> str:
    """A number in tower units, e.g. 50 or 2.4."""
    if value is None:
        return ""
    if value.is_infinite():
        return "Unlimited"
    return round1(value / tower.factor)


def symbol(currency: str) -> str:
    return CURRENCY_SYMBOL.get(currency, currency + " ")


def amount(tower: Tower, value: Decimal | None) -> str:
    """A labelled amount, e.g. £50m."""
    if value is None:
        return ""
    if value.is_infinite():
        return "Unlimited"
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol(tower.currency)}{num(tower, abs(value))}{tower.units}"


def pct(d: Decimal | None) -> str:
    if d is None:
        return ""
    if d.is_infinite():
        return "Unlimited"
    return round1(d * 100) + "%"


def reinst(layer: Layer) -> str:
    r = layer.reinstatements
    if r is None:
        return ""
    count = "unl" if r.count is None else str(r.count)
    return f"{count} @ {round1(Decimal(repr(r.rate)) * 100)}%"


def layer_label(tower: Tower, layer: Layer) -> str:
    if layer.kind == "retention":
        return f"Retention {amount(tower, layer.limit)}"
    if layer.kind == "qs":
        return f"QS {pct(layer.cession)} · limit {amount(tower, layer.limit)}"
    if layer.kind == "sl":
        return f"SL {pct(layer.limit)} xs {pct(layer.attachment)} of EPI"
    return f"{amount(tower, layer.limit)} xs {amount(tower, layer.attachment)}"


def sl_amounts(tower: Tower, layer: Layer) -> str:
    """A stop loss in amounts, e.g. £20m xs £80m, when the EPI is known."""
    if tower.epi is None:
        return ""
    return f"{amount(tower, layer.limit * tower.epi)} xs {amount(tower, layer.attachment * tower.epi)}"


def short_label(tower: Tower, layer: Layer) -> str:
    """Unit-free label used in shape names, e.g. 50 xs 50."""
    if layer.kind == "retention":
        return f"{num(tower, layer.limit)} ret"
    if layer.kind == "qs":
        return f"QS {pct(layer.cession)}"
    if layer.kind == "sl":
        return f"SL {pct(layer.limit)} xs {pct(layer.attachment)}"
    return f"{num(tower, layer.limit)} xs {num(tower, layer.attachment)}"


def words(tower: Tower, value: Decimal) -> str:
    """An amount in words for alt text, e.g. 50 million."""
    names = {"": "", "k": " thousand", "m": " million", "bn": " billion"}
    return f"{num(tower, value)}{names[tower.units]}"


def escape(text: str) -> str:
    """Neutralise formula injection in user text written to exports."""
    if text and text[0] in "=+-@":
        return "'" + text
    return text
