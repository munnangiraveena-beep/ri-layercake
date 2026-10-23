"""Shorthand grammar and paste parser.

Both return a Tower whose ``diagnostics`` hold anything that could not be
read; neither ever raises on user input.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any

from .fmt import plain, reinst
from .model import ONE, UNIT_FACTOR, ZERO, Layer, Reinstatements, Terms, Tower, normalize
from .validate import Diagnostic

CURRENCIES = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY", "gbp": "GBP", "usd": "USD", "eur": "EUR", "jpy": "JPY"}
UNIT_ALIASES = {"k": "k", "m": "m", "mn": "m", "mm": "m", "bn": "bn"}

CUR = r"(?:£|\$|€|¥|gbp|usd|eur|jpy)"
NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
UNIT = r"(?:bn|mn|mm|m|k)(?![a-z])"


def _amt(p: str) -> str:
    return rf"(?:(?P<{p}cur>{CUR})\s*)?(?P<{p}num>{NUM})(?:\s*(?P<{p}unit>{UNIT}))?"


RE_RET = re.compile(rf"(?:ret(?:ention)?\s*{_amt('a')}|{_amt('b')}\s*ret(?:ention)?)\s*$")
RE_XL = re.compile(
    rf"(?:(?P<pp>{NUM})\s*%\s*part\s+of\s+)?{_amt('l')}\s*(?:xs|x/s)\s*{_amt('t')}(?P<mods>.*)$"
)
RE_QS = re.compile(rf"(?:qs|quota\s*share)\s*(?P<c>{NUM})\s*%(?P<mods>.*)$")
def _sl_side_rx(p: str) -> str:
    return rf"(?:(?P<{p}pct>{NUM})\s*%|{_amt(p)})"


RE_SL = re.compile(
    rf"(?:sl|stop\s*loss)\s*{_sl_side_rx('l')}\s*(?:xs|x/s)\s*{_sl_side_rx('t')}"
    rf"(?:\s*(?:of\s*)?epi)?(?P<mods>.*)$"
)
RE_EPI = re.compile(rf"epi\s*{_amt('e')}\s*$")
RE_MODS = [
    ("reinst", re.compile(rf"(?P<n>\d+|unl(?:imited)?)\s*@\s*(?P<r>{NUM})\s*%(?P<pr>\s*pro\s*rata)?")),
    ("share", re.compile(rf"@\s*(?P<s>{NUM})\s*%(?:\s*placed)?")),
    ("premium", re.compile(rf"prem(?:ium)?\s*{_amt('p')}")),
    ("rol", re.compile(rf"rol\s*(?P<rol>{NUM})\s*%")),
    ("order", re.compile(rf"order\s*(?P<o>{NUM})\s*%")),
    ("rate", re.compile(rf"(?:adj\.?\s*)?rate\s*(?P<ar>{NUM})\s*%")),
    ("ncb", re.compile(rf"ncb\s*(?P<ncb>{NUM})\s*%")),
    ("comm", re.compile(rf"comm(?:ission)?\s*(?P<cm>{NUM})\s*%")),
    ("agg", re.compile(rf"agg(?:regate)?(?:\s*limit)?\s*{_amt('g')}")),
    ("limit", re.compile(rf"(?:limit|of)\s*{_amt('q')}")),
    ("el", re.compile(rf"el\s*{_amt('x')}")),
]
RE_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _num(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


@dataclass
class _Amount:
    value: Decimal
    unit: str | None
    currency: str | None

    @classmethod
    def from_match(cls, m: re.Match[str], p: str) -> _Amount:
        unit = m.group(p + "unit")
        cur = m.group(p + "cur")
        return cls(_num(m.group(p + "num")), UNIT_ALIASES[unit] if unit else None,
                   CURRENCIES[cur] if cur else None)


@dataclass
class _Item:
    kind: str
    start: int
    limit: _Amount | None
    attachment: _Amount | None = None
    placed: Decimal = ONE
    premium: _Amount | None = None
    rol: Decimal | None = None
    reinstatements: Reinstatements | None = None
    name: str | None = None
    amounts: list[_Amount] = field(default_factory=list)
    order: Decimal = ONE
    adj_rate: Decimal | None = None
    ncb: Decimal | None = None
    commission: Decimal | None = None
    cession: Decimal | None = None
    agg: _Amount | None = None
    el: _Amount | None = None
    ratio_limit: Decimal | None = None  # stop loss as % of EPI
    ratio_attachment: Decimal | None = None


def _split(text: str) -> list[tuple[int, str]]:
    """Split on , ; and newlines, keeping thousands commas inside numbers."""
    protected = RE_THOUSANDS_COMMA.sub("\x00", text)
    out, start = [], 0
    for i, ch in enumerate(protected):
        if ch in ",;\n":
            out.append((start, text[start:i]))
            start = i + 1
    out.append((start, text[start:]))
    return [(s + len(f) - len(f.lstrip()), f.strip()) for s, f in out if f.strip()]


ALLOWED_MODS = {
    "xl": {"reinst", "share", "premium", "rol", "order", "rate", "ncb", "el"},
    "qs": {"share", "premium", "order", "comm", "agg", "limit"},
    "sl": {"share", "premium", "rol", "order", "rate", "el"},
}


def _parse_mods(item: _Item, text: str, offset: int, diags: list[Diagnostic]) -> None:
    pos = 0
    low = text.lower()
    allowed = ALLOWED_MODS.get(item.kind, set())
    while pos < len(low):
        while pos < len(low) and low[pos].isspace():
            pos += 1
        if pos >= len(low):
            break
        for kind, rx in RE_MODS:  # noqa: B007 (used after break)
            m = rx.match(low, pos)
            if m and kind in allowed:
                break
        else:
            diags.append(_parse_error(text[pos:].strip(), offset + pos, offset + len(text)))
            return
        if kind == "reinst":
            n = m.group("n")
            item.reinstatements = Reinstatements(
                count=None if n.startswith("unl") else int(n),
                rate=float(_num(m.group("r")) / 100),
            )
        elif kind == "share":
            item.placed = _num(m.group("s")) / 100
        elif kind == "premium":
            item.premium = _Amount.from_match(m, "p")
            item.amounts.append(item.premium)
        elif kind == "rol":
            item.rol = _num(m.group("rol")) / 100
        elif kind == "order":
            item.order = _num(m.group("o")) / 100
        elif kind == "rate":
            item.adj_rate = _num(m.group("ar")) / 100
        elif kind == "ncb":
            item.ncb = _num(m.group("ncb")) / 100
        elif kind == "comm":
            item.commission = _num(m.group("cm")) / 100
        elif kind == "agg":
            item.agg = _Amount.from_match(m, "g")
            item.amounts.append(item.agg)
        elif kind == "limit":
            item.limit = _Amount.from_match(m, "q")
            item.amounts.append(item.limit)
        elif kind == "el":
            item.el = _Amount.from_match(m, "x")
            item.amounts.append(item.el)
        pos = m.end()


def _parse_error(fragment: str, start: int, end: int) -> Diagnostic:
    return Diagnostic("parse", "error", f"Could not read “{fragment}”", span=(start, end))


def _sl_side(m: re.Match[str], p: str) -> tuple[Decimal | None, _Amount | None]:
    if m.group(p + "pct"):
        return _num(m.group(p + "pct")) / 100, None
    return None, _Amount.from_match(m, p)


def parse_shorthand(
    text: str,
    currency: str | None = None,
    units: str | None = None,
    title: str | None = None,
    subtitle: str | None = None,
) -> Tower:
    diags: list[Diagnostic] = []
    items: list[_Item] = []
    epi: _Amount | None = None
    for start, frag in _split(text):
        name = None
        body, body_start = frag, start
        if ":" in frag:
            head, _, rest = frag.partition(":")
            name, body = head.strip() or None, rest.strip()
            body_start = start + frag.index(rest.strip()) if rest.strip() else start + len(frag)
        low = body.lower()
        m = RE_EPI.match(low)
        if m:
            epi = _Amount.from_match(m, "e")
            continue
        m = RE_RET.match(low)
        if m:
            p = "a" if m.group("anum") else "b"
            amt = _Amount.from_match(m, p)
            items.append(_Item("retention", start, amt, name=name, amounts=[amt]))
            continue
        m = RE_QS.match(low)
        if m:
            item = _Item("qs", start, None, name=name, cession=_num(m.group("c")) / 100)
            _parse_mods(item, body[m.start("mods"):], body_start + m.start("mods"), diags)
            items.append(item)
            continue
        m = RE_SL.match(low)
        if m:
            lr, la = _sl_side(m, "l")
            ar, aa = _sl_side(m, "t")
            item = _Item("sl", start, la, aa, name=name, ratio_limit=lr, ratio_attachment=ar,
                         amounts=[x for x in (la, aa) if x is not None])
            _parse_mods(item, body[m.start("mods"):], body_start + m.start("mods"), diags)
            items.append(item)
            continue
        m = RE_XL.match(low)
        if m:
            lim, att = _Amount.from_match(m, "l"), _Amount.from_match(m, "t")
            item = _Item("xl", start, lim, att, name=name, amounts=[lim, att])
            if m.group("pp"):
                item.placed = _num(m.group("pp")) / 100
            mods = body[m.start("mods"):]
            _parse_mods(item, mods, body_start + m.start("mods"), diags)
            items.append(item)
            continue
        if items and items[-1].kind in ("xl", "qs", "sl") and name is None:
            _parse_mods(items[-1], frag, start, diags)
            continue
        diags.append(_parse_error(frag, start, start + len(frag)))

    all_amounts = [a for it in items for a in it.amounts] + ([epi] if epi else [])
    seen_units = [a.unit for a in all_amounts if a.unit is not None]
    tower_units = units if units is not None else (seen_units[0] if seen_units else "m")
    if currency is None:
        currency = next((a.currency for a in all_amounts if a.currency), "GBP")
    if any(u != tower_units for u in seen_units):
        diags.append(Diagnostic("units_mixed", "info",
                                f"Amounts were entered in different units and shown in {tower_units or 'units'}",
                                key="units_mixed"))

    def full(a: _Amount | None) -> Decimal | None:
        if a is None:
            return None
        return normalize(a.value * UNIT_FACTOR[a.unit if a.unit is not None else tower_units])

    epi_full = full(epi)
    layers: list[Layer] = []
    have_ret = have_qs = False
    for it in items:
        span = (it.start, it.start + 1)
        if it.kind == "retention":
            if have_ret:
                diags.append(Diagnostic("parse", "error", "Only one retention is allowed", span=span))
                continue
            have_ret = True
            layers.append(Layer("R", "retention", full(it.limit), ZERO, name=it.name))  # type: ignore[arg-type]
        elif it.kind == "qs":
            if have_qs:
                diags.append(Diagnostic("parse", "error", "Only one quota share is allowed", span=span))
                continue
            if it.limit is None:
                diags.append(Diagnostic("parse", "error", "Give the quota share a limit, e.g. qs 20% limit 50",
                                        span=span))
                continue
            have_qs = True
            layers.append(Layer(
                "", "qs", full(it.limit), ZERO, placed=normalize(it.placed), order=normalize(it.order),  # type: ignore[arg-type]
                cession=normalize(it.cession) if it.cession is not None else None, premium=full(it.premium),
                agg_limit=full(it.agg), name=it.name,
                terms=Terms(commission=None if it.commission is None else normalize(it.commission)),
            ))
        elif it.kind == "sl":
            lim_r, att_r = it.ratio_limit, it.ratio_attachment
            if (lim_r is None or att_r is None) and not epi_full:
                diags.append(Diagnostic("parse", "error",
                                        "A stop loss in amounts needs the EPI, e.g. epi 100, sl 20 xs 80", span=span))
                continue
            if lim_r is None:
                lim_r = full(it.limit) / epi_full  # type: ignore[operator]
            if att_r is None:
                att_r = full(it.attachment) / epi_full  # type: ignore[operator]
            layers.append(Layer(
                "", "sl", normalize(lim_r), normalize(att_r), placed=normalize(it.placed), order=normalize(it.order),
                premium=full(it.premium), rol=None if it.rol is None else normalize(it.rol),
                adj_rate=None if it.adj_rate is None else normalize(it.adj_rate), name=it.name,
                terms=Terms(expected_loss=full(it.el)),
            ))
        else:
            layers.append(Layer(
                "", "xl", full(it.limit), full(it.attachment),  # type: ignore[arg-type]
                placed=normalize(it.placed), order=normalize(it.order), premium=full(it.premium),
                reinstatements=it.reinstatements, name=it.name,
                rol=None if it.rol is None else normalize(it.rol),
                adj_rate=None if it.adj_rate is None else normalize(it.adj_rate),
                terms=Terms(no_claims_bonus=None if it.ncb is None else normalize(it.ncb), expected_loss=full(it.el)),
            ))
    t = _finish(layers, diags, currency, tower_units, title, subtitle)
    return replace(t, epi=epi_full, diagnostics=t.diagnostics) if epi_full is not None else t


def _finish(layers: list[Layer], diags: list[Diagnostic], currency: str, units: str,
            title: str | None, subtitle: str | None) -> Tower:
    ordered = sorted(layers, key=Layer.sort_key)
    counts = {"xl": 0, "qs": 0, "sl": 0}
    prefix = {"xl": "L", "qs": "Q", "sl": "S"}
    final = []
    for l in ordered:
        if l.kind in counts:
            counts[l.kind] += 1
            l = replace(l, id=f"{prefix[l.kind]}{counts[l.kind]}")
        final.append(l)
    return Tower(tuple(final), currency=currency, units=units,  # type: ignore[arg-type]
                 title=title, subtitle=subtitle, diagnostics=tuple(diags))


def parse_amount(text: str, default_units: str = "m") -> Decimal | None:
    m = re.fullmatch(_amt("x"), text.strip().lower())
    if not m:
        return None
    a = _Amount.from_match(m, "x")
    return a.value * UNIT_FACTOR[a.unit if a.unit is not None else default_units]


def format_shorthand(tower: Tower) -> str:
    """Print a tower as shorthand that parses back to the same layers."""
    from .fmt import symbol

    def n(v: Decimal) -> str:
        return plain(normalize(v / tower.factor))

    def p(v: Decimal) -> str:
        return plain(normalize(v * 100)) + "%"

    cur = symbol(tower.currency).strip()
    if cur not in CURRENCIES:
        cur = ""
    first = True

    def amt(v: Decimal) -> str:
        nonlocal first
        if first:
            first = False
            return f"{cur}{n(v)}{tower.units}"
        return n(v)

    def shares(l: Layer) -> str:
        s = ""
        if l.placed != ONE:
            s += f" @ {p(l.placed)}"
        if l.order != ONE:
            s += f" order {p(l.order)}"
        return s

    parts = []
    if tower.epi is not None:
        parts.append(f"epi {amt(tower.epi)}")
    for l in tower.layers:
        prefix = f"{_clean_name(l.name)}: " if l.name else ""
        if l.kind == "retention":
            parts.append(f"{prefix}{amt(l.limit)} ret")
            continue
        if l.kind == "qs":
            s = f"{prefix}qs {p(l.cession or ZERO)} limit {amt(l.limit)}"
            if l.agg_limit is not None:
                s += f" agg {amt(l.agg_limit)}"
            if l.terms.commission is not None:
                s += f" comm {p(l.terms.commission)}"
            if l.premium is not None:
                s += f" prem {amt(l.premium)}"
            parts.append(s + shares(l))
            continue
        if l.kind == "sl":
            s = f"{prefix}sl {p(l.limit)} xs {p(l.attachment)}"
        else:
            s = f"{prefix}{amt(l.limit)} xs {amt(l.attachment)}"
        s += shares(l)
        if l.reinstatements is not None:
            s += " " + reinst(l)
        if l.premium is not None:
            s += f" prem {amt(l.premium)}"
        if l.rol is not None:
            s += f" rol {p(l.rol)}"
        if l.adj_rate is not None:
            s += f" rate {p(l.adj_rate)}"
        if l.terms.no_claims_bonus is not None:
            s += f" ncb {p(l.terms.no_claims_bonus)}"
        if l.terms.expected_loss is not None:
            s += f" el {amt(l.terms.expected_loss)}"
        parts.append(s)
    return ", ".join(parts)


def _clean_name(name: str) -> str:
    return re.sub(r"[,;:\n]", " ", name).strip()


# ---------------------------------------------------------------------- paste

SYNONYMS = {
    "limit": ["limit", "layer limit", "cover", "occurrence limit", "limit 100%"],
    "attachment": ["attachment", "excess", "xs", "deductible", "retention", "priority",
                   "attachment point", "excess point"],
    "placed": ["placed", "share", "signed", "% placed", "placement", "signed share", "% signed",
               "placed %", "signed %", "share %"],
    "premium": ["premium", "rate", "gross premium", "premium 100%", "deposit premium"],
    "rol": ["rol", "rate on line", "rol %"],
    "name": ["layer", "name", "layer name", "description"],
    "written": ["written", "written line", "our line", "our share"],
    "reinstatements": ["reinstatements", "reinstatement", "reinst", "reinsts", "rips"],
}
FIELDS = list(SYNONYMS)


def _norm_header(cell: str) -> tuple[str, str | None, str | None]:
    """Normalise a header cell; return (text, unit hint, currency hint)."""
    low = cell.strip().lower()
    unit = cur = None
    for hint in re.findall(r"\(([^)]*)\)|\[([^\]]*)\]", low):
        h = "".join(hint).strip()
        hm = re.fullmatch(rf"({CUR})?\s*({UNIT})?", h)
        if hm and (hm.group(1) or hm.group(2)):
            cur = CURRENCIES.get(hm.group(1) or "")
            unit = UNIT_ALIASES.get(hm.group(2) or "")
    low = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", low)
    m = re.search(rf"\b({CUR})?\s*({UNIT})\s*$", low)
    if m and low.strip() != m.group(0).strip():
        unit = UNIT_ALIASES[m.group(2)]
        cur = CURRENCIES.get(m.group(1) or "", cur)
        low = low[: m.start()]
    low = re.sub(r"[^a-z%/ ]", " ", low.replace("£", " "))
    return re.sub(r"\s+", " ", low).strip(), unit, cur


def _header_field(cell: str) -> str | None:
    if _is_shorthand(cell) or parse_number(cell) is not None:
        return None
    text, _, _ = _norm_header(cell)
    if not text:
        return None
    for f in FIELDS:
        if text in SYNONYMS[f]:
            return f
    return None


@dataclass
class Mapping:
    header_row: int | None  # index of the header row, None when inferred
    columns: dict[int, str]  # column index -> field
    unit_hints: dict[int, str] = field(default_factory=dict)
    currency: str | None = None
    european: dict[int, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"header_row": self.header_row,
                "columns": {str(k): v for k, v in sorted(self.columns.items())}}


class _TableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None and not self._skip:
            self._cell.append(data)


def split_rows(text: str) -> list[list[str]]:
    """Turn clipboard text (TSV, CSV or an HTML table) into rows of cells."""
    if re.search(r"<t[dhr][\s>]", text, re.I):
        p = _TableHTML()
        p.feed(text)
        return p.rows
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in text.split("\n")]
    if any("\t" in ln for ln in lines):
        return [ln.split("\t") for ln in lines]
    sample = "\n".join(lines[:10])
    delim = ";" if sample.count(";") > sample.count(",") else ","
    if delim == "," and not _looks_like_csv(lines):
        return [[ln] for ln in lines]
    return [row for row in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)]


def _looks_like_csv(lines: list[str]) -> bool:
    rows = list(csv.reader(io.StringIO("\n".join(ln for ln in lines if ln.strip()))))
    counts = {len(r) for r in rows}
    return len(counts) == 1 and counts != {1} and not any(re.search(r"\bxs\b", ln, re.I) for ln in lines)


def read_csv_rows(path: str) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return split_rows(fh.read())


def read_excel_rows(path: str, sheet: str | None = None) -> list[list[str]]:
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover
        raise ImportError("Reading Excel needs: pip install ri-layercake[excel]") from e
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(["" if v is None else _cell_str(v) for v in row])
    return rows


def _cell_str(v: Any) -> str:
    if isinstance(v, float):
        return repr(v)
    return str(v)


RE_EU = re.compile(r"^\s*-?[^\d]*\d{1,3}(\.\d{3})+(,\d+)?\b|^\s*-?[^\d]*\d+,\d{1,2}\s*[^\d,]*$")
RE_CELL = re.compile(
    rf"^(?P<neg>\()?\s*(?P<sign>-)?\s*(?P<cur>{CUR})?\s*(?P<num>[\d][\d.,  ']*|\.\d+)\s*"
    rf"(?P<unit>{UNIT})?\s*(?P<pct>%)?\s*\)?$"
)


@dataclass
class _Cell:
    value: Decimal
    unit: str | None = None
    currency: str | None = None
    pct: bool = False


def parse_number(cell: str, european: bool = False) -> _Cell | None:
    s = cell.strip().lower().replace(" ", " ")
    if s in ("", "-", "–", "—", "n/a", "na"):
        return None
    m = RE_CELL.match(s)
    if not m:
        return None
    raw = m.group("num").strip().replace(" ", "").replace("'", "")
    if european:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if m.group("neg") or m.group("sign"):
        value = -value
    unit = m.group("unit")
    cur = m.group("cur")
    return _Cell(value, UNIT_ALIASES[unit] if unit else None, CURRENCIES[cur] if cur else None,
                 bool(m.group("pct")))


def _is_shorthand(cell: str) -> bool:
    return bool(re.search(r"\d.*\bx/?s\b.*\d", cell, re.I))


def _is_total(row: list[str]) -> bool:
    return any(re.match(r"\s*(grand\s+)?totals?\b", c, re.I) for c in row[:2])


def detect_mapping(rows: list[list[str]]) -> Mapping:
    """Find the header row and map columns to fields, or infer from values."""
    for i, row in enumerate(rows[:8]):
        found_raw = {j: _header_field(c) for j, c in enumerate(row)}
        found = {j: f for j, f in found_raw.items() if f}
        if len(found) >= 2 or (len(found) == 1 and _column_is_shorthand(rows, i, next(iter(found)))):
            columns: dict[int, str] = {}
            used: set[str] = set()
            for j, f in found.items():
                if f not in used:
                    columns[j] = f
                    used.add(f)
            hints: dict[int, str] = {}
            currency: str | None = None
            for j, c in enumerate(row):
                _, unit, cur = _norm_header(c)
                if unit:
                    hints[j] = unit
                currency = currency or cur
            mapping = Mapping(i, columns, hints, currency)
            for j, f in columns.items():
                if f == "name" and _column_is_shorthand(rows, i, j):
                    columns[j] = "combined"
            if "limit" not in used and "combined" not in columns.values():
                for j in range(len(row)):
                    if j not in columns and _column_is_shorthand(rows, i, j):
                        columns[j] = "combined"
                        break
            _detect_european(rows[i + 1:], mapping)
            return mapping
    return _infer_mapping(rows)


def _column_is_shorthand(rows: list[list[str]], header: int, j: int) -> bool:
    vals = [r[j] for r in rows[header + 1:] if j < len(r) and r[j].strip()]
    return bool(vals) and sum(_is_shorthand(v) for v in vals) >= max(1, len(vals) // 2)


def _detect_european(body: list[list[str]], mapping: Mapping) -> None:
    width = max((len(r) for r in body), default=0)
    for j in range(width):
        vals = [r[j] for r in body if j < len(r) and r[j].strip()]
        mapping.european[j] = any(RE_EU.match(v) for v in vals) and not any(
            re.search(r"\d,\d{3}\.\d", v) for v in vals)


def _infer_mapping(rows: list[list[str]]) -> Mapping:
    body = [r for r in rows if any(c.strip() for c in r) and not _is_total(r)]
    width = max((len(r) for r in body), default=0)
    mapping = Mapping(None, {})
    _detect_european(body, mapping)
    amount_cols: list[int] = []
    for j in range(width):
        vals = [r[j] for r in body if j < len(r) and r[j].strip()]
        if not vals:
            continue
        if sum(_is_shorthand(v) for v in vals) >= max(1, len(vals) // 2):
            mapping.columns[j] = "combined"
            continue
        nums = [parse_number(v, mapping.european.get(j, False)) for v in vals]
        if not all(nums):
            if not any(nums):
                mapping.columns[j] = "name"
            continue
        if all(n.pct for n in nums if n) or all(n and ZERO < n.value <= ONE and n.value != n.value.to_integral_value() for n in nums):  # noqa: E501
            mapping.columns.setdefault(j, "placed") if "placed" not in mapping.columns.values() else None
            continue
        amount_cols.append(j)
    if len(amount_cols) >= 2:
        a, b = amount_cols[0], amount_cols[1]
        if _chain_score(body, b, a, mapping) > _chain_score(body, a, b, mapping):
            a, b = b, a
        mapping.columns[a] = "limit"
        mapping.columns[b] = "attachment"
        if len(amount_cols) >= 3:
            mapping.columns[amount_cols[2]] = "premium"
    elif len(amount_cols) == 1 and "combined" not in mapping.columns.values():
        mapping.columns[amount_cols[0]] = "limit"
    return mapping


def _chain_score(body: list[list[str]], lim: int, att: int, mapping: Mapping) -> int:
    pairs = []
    for r in body:
        if max(lim, att) < len(r):
            l = parse_number(r[lim], mapping.european.get(lim, False))
            a = parse_number(r[att], mapping.european.get(att, False))
            if l and a:
                pairs.append((a.value, l.value))
    pairs.sort()
    return sum(1 for (a1, l1), (a2, _) in zip(pairs, pairs[1:]) if a1 + l1 == a2)


def parse_paste(text: str, **kwargs: Any) -> Tower:
    if len(text) > 1_000_000:
        return _finish([], [Diagnostic("parse", "error", "Pasted text is over 1 MB")],
                       kwargs.get("currency") or "GBP", kwargs.get("units") or "m",
                       kwargs.get("title"), kwargs.get("subtitle"))
    rows = split_rows(text)
    if all(len(r) == 1 for r in rows) and not any(_header_field(r[0]) for r in rows[:3]):
        return parse_shorthand("\n".join(r[0] for r in rows), **kwargs)
    return parse_rows(rows, **kwargs)


def parse_rows(
    rows: list[list[str]],
    currency: str | None = None,
    units: str | None = None,
    title: str | None = None,
    subtitle: str | None = None,
    mapping: Mapping | dict[str, Any] | None = None,
) -> Tower:
    rows = [[c if isinstance(c, str) else str(c) for c in r] for r in rows]
    if isinstance(mapping, dict):
        m = detect_mapping(rows)
        m.columns = {int(k): v for k, v in mapping.get("columns", {}).items() if v}
        if "header_row" in mapping:
            m.header_row = mapping["header_row"]
        mapping = m
    mapping = mapping or detect_mapping(rows)
    body = rows[mapping.header_row + 1:] if mapping.header_row is not None else rows
    diags: list[Diagnostic] = []
    cols = mapping.columns

    if "limit" not in cols.values() and "combined" not in cols.values():
        diags.append(Diagnostic("parse", "error", "Could not find a limit column"))
        return _finish([], diags, currency or "GBP", units or "m", title, subtitle)

    records: list[dict[str, Any]] = []
    for r in body:
        if not any(c.strip() for c in r) or _is_total(r):
            continue
        rec: dict[str, Any] = {}
        for j, f in cols.items():
            cell = r[j].strip() if j < len(r) else ""
            if not cell:
                continue
            if f in ("name", "reinstatements"):
                rec[f] = cell
            elif f == "combined":
                rec[f] = cell
            else:
                rec[f] = parse_number(cell, mapping.european.get(j, False))
                rec[f + "_col"] = j
                if rec[f] is None:
                    rec.pop(f)
        if any(k in rec for k in ("limit", "attachment", "combined")):
            records.append(rec)

    # Decide the display unit and whether bare numbers are full units.
    explicit = [rec[f].unit for rec in records for f in ("limit", "attachment") if f in rec and rec[f].unit]
    hints = list(mapping.unit_hints.values())
    bare = [rec[f].value for rec in records for f in ("limit", "attachment")
            if f in rec and rec[f].unit is None and mapping.unit_hints.get(rec[f + "_col"]) is None]
    full_units = bool(bare) and max(abs(v) for v in bare) >= 100_000
    tower_units = units or (explicit[0] if explicit else hints[0] if hints else None)
    if tower_units is None:
        tower_units = _units_for(max(bare)) if full_units else "m"
    if any(u != tower_units for u in explicit + hints):
        diags.append(Diagnostic("units_mixed", "info",
                                f"Amounts were entered in different units and shown in {tower_units or 'units'}",
                                key="units_mixed"))
    cur = currency or mapping.currency or next(
        (rec[f].currency for rec in records for f in ("limit", "attachment") if f in rec and rec[f].currency), None
    ) or "GBP"

    def full(rec: dict[str, Any], f: str) -> Decimal | None:
        c: _Cell | None = rec.get(f)
        if c is None:
            return None
        unit = c.unit or mapping.unit_hints.get(rec[f + "_col"])
        if unit is None:
            unit = "" if full_units else tower_units
        return normalize(c.value * UNIT_FACTOR[unit])

    def share(c: _Cell | None) -> Decimal | None:
        if c is None:
            return None
        v = c.value / 100 if c.pct or c.value > 1 else c.value
        return normalize(v)

    layers: list[Layer] = []
    for n, rec in enumerate(records):
        name = rec.get("name")
        if "combined" in rec:
            sub = parse_shorthand(rec["combined"], currency=cur, units=tower_units)
            if not sub.layers:
                diags.append(Diagnostic("parse", "error", f"Could not read “{rec['combined']}” in row {n + 1}"))
                continue
            l = sub.layers[0]
            if "placed" in rec:
                l = _with(l, placed=share(rec["placed"]))
            if name and not l.name and not _is_shorthand(name):
                l = _with(l, name=name)
            if "premium" in rec:
                l = _with(l, premium=full(rec, "premium"))
            layers.append(l)
            continue
        is_ret = bool(name and re.fullmatch(r"\s*(retention|ret|deductible|cedant retention)\s*", name, re.I))
        limit = full(rec, "limit")
        attachment = full(rec, "attachment")
        if is_ret:
            layers.append(Layer("R", "retention", limit or attachment or ZERO, ZERO))
            continue
        if limit is None:
            diags.append(Diagnostic("parse", "error", f"Row {n + 1} has no limit"))
            continue
        prem_cell: _Cell | None = rec.get("premium")
        rol = share(rec.get("rol")) if "rol" in rec else None
        premium = full(rec, "premium")
        if prem_cell is not None and prem_cell.pct:
            rol, premium = normalize(prem_cell.value / 100), None
        reinstatements = None
        if "reinstatements" in rec:
            reinstatements = _parse_reinst(rec["reinstatements"])
        layers.append(Layer(
            "", "xl", limit, attachment or ZERO,
            placed=share(rec.get("placed")) or ONE,
            written=share(rec.get("written")),
            premium=premium, rol=rol, reinstatements=reinstatements,
            name=name if name and not re.fullmatch(r"(layer\s*)?\d+", name, re.I) else None,
        ))
    if sum(1 for l in layers if l.kind == "retention") > 1:
        first = next(l for l in layers if l.kind == "retention")
        layers = [l for l in layers if l.kind != "retention" or l is first]
        diags.append(Diagnostic("parse", "error", "Only one retention is allowed"))
    return _finish(layers, diags, cur, tower_units, title, subtitle)


def _with(layer: Layer, **changes: Any) -> Layer:
    from dataclasses import replace

    return replace(layer, **changes)


def _parse_reinst(text: str) -> Reinstatements | None:
    m = RE_MODS[0][1].search(text.lower())
    if m:
        n = m.group("n")
        return Reinstatements(None if n.startswith("unl") else int(n), float(_num(m.group("r")) / 100))
    m = re.fullmatch(r"\s*(\d+|unl\w*)\s*", text.lower())
    if m:
        n = m.group(1)
        return Reinstatements(None if n.startswith("unl") else int(n))
    return None


def _units_for(v: Decimal) -> str:
    v = abs(v)
    if v >= 1_000_000_000:
        return "bn"
    if v >= 1_000_000:
        return "m"
    if v >= 1_000:
        return "k"
    return ""


# ---------------------------------------------------------------------- portfolio

EXPOSURE_HEADERS = ["exposure", "sum insured", "si", "tsi", "tiv", "pml", "mpl", "eml", "value", "limit",
                    "total sum insured", "insured value", "exposure 100%"]
RISK_HEADERS = ["risk", "id", "risk id", "name", "policy", "location", "insured", "risk name", "account"]


def parse_portfolio(source: str, tower: Tower) -> list[tuple[str, Decimal]]:
    """Risks and exposures from pasted text or a CSV/Excel path: [(risk id, exposure in full units)]."""
    import os

    if os.path.exists(source):
        ext = os.path.splitext(source)[1].lower()
        rows = read_excel_rows(source) if ext in (".xlsx", ".xlsm") else read_csv_rows(source)
    else:
        rows = split_rows(source)
    rows = [[c.strip() for c in r] for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    exp_col = id_col = None
    header = None
    for i, row in enumerate(rows[:6]):
        texts = [_norm_header(c)[0] for c in row]
        for j, t in enumerate(texts):
            if exp_col is None and t in EXPOSURE_HEADERS:
                exp_col = j
            elif id_col is None and t in RISK_HEADERS:
                id_col = j
        if exp_col is not None:
            header = i
            break
    hint = None
    if header is not None:
        hint = _norm_header(rows[header][exp_col])[1]  # type: ignore[index]
    body = rows[header + 1:] if header is not None else rows
    if exp_col is None:
        width = max(len(r) for r in body)
        numeric = [j for j in range(width) if all(j < len(r) and parse_number(r[j]) for r in body)]
        if not numeric:
            return []
        exp_col = numeric[-1]
        id_col = next((j for j in range(width) if j != exp_col), None)
    values = []
    for n, r in enumerate(body, 1):
        if exp_col >= len(r) or _is_total(r):
            continue
        c = parse_number(r[exp_col])
        if c is None:
            continue
        rid = r[id_col] if id_col is not None and id_col < len(r) and r[id_col] else f"Risk {n}"
        values.append((rid, c))
    bare = [c.value for _, c in values if c.unit is None]
    full_units = hint is None and bool(bare) and max(abs(v) for v in bare) >= 100_000
    out = []
    for rid, c in values:
        unit = c.unit or hint or ("" if full_units else tower.units)
        out.append((rid, normalize(c.value * UNIT_FACTOR[unit])))
    return out
