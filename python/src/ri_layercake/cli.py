"""Command line: ri-layercake tower | check | loss."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__, fmt
from .model import Tower
from .scene import View
from .validate import has_errors


def load(source: str, sheet: str | None = None) -> Tower:
    """A file path (xlsx, csv, json, txt) or shorthand text."""
    if os.path.exists(source):
        ext = os.path.splitext(source)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            return Tower.from_excel(source, sheet=sheet)
        if ext in (".csv", ".tsv"):
            return Tower.from_csv(source)
        with open(source, encoding="utf-8") as fh:
            text = fh.read()
        if ext == ".json":
            return Tower.from_json(text)
        return Tower.from_paste(text)
    return Tower.from_text(source)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ri-layercake", description="Reinsurance towers as editable slides.")
    p.add_argument("--version", action="version", version=f"ri-layercake {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tower", help="draw a tower to PPTX and/or SVG")
    t.add_argument("source", help="workbook, CSV, JSON, or shorthand like '10 ret, 40 xs 10'")
    t.add_argument("--sheet")
    t.add_argument("--out", help="PPTX path")
    t.add_argument("--svg", help="SVG path")
    t.add_argument("--template", help=".pptx or .potx whose theme and layout are used")
    t.add_argument("--scale", choices=["schematic", "linear", "log"], default="schematic")
    t.add_argument("--palette", choices=["ocean", "slate", "ember"], default="ocean")
    t.add_argument("--table", choices=["below", "right", "none"], default="below")
    t.add_argument("--title")
    t.add_argument("--units", choices=["", "k", "m", "bn"])
    t.add_argument("--currency")

    c = sub.add_parser("check", help="print diagnostics; exit code 1 on errors")
    c.add_argument("source")
    c.add_argument("--sheet")

    lo = sub.add_parser("loss", help="drop-a-loss table")
    lo.add_argument("source")
    lo.add_argument("amount", help="loss in tower units, or with a unit like 120m")
    lo.add_argument("--sheet")

    a = p.parse_args(argv)
    tower = load(a.source, getattr(a, "sheet", None))

    if a.cmd == "check":
        diags = tower.validate()
        for d in diags:
            print(f"{d.severity:8} {d.code:14} {d.message}")
        if not diags:
            print("No issues found.")
        return 1 if has_errors(diags) else 0

    if a.cmd == "loss":
        res = tower.drop_loss(a.amount)
        rows = [("Layer", "Recovery 100%", "Placed", "Recovery placed", "Exhausted", "Reinst. premium")]
        for r in res.layers:
            rows.append((r.name, fmt.num(tower, r.recovery_100), fmt.pct(r.placed), fmt.num(tower, r.recovery_placed),
                         "yes" if r.exhausted else "no", fmt.num(tower, r.reinstatement_premium)))
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            print("  ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(row, widths))))
        print()
        print(f"Loss {fmt.amount(tower, res.loss)}: recovered {fmt.amount(tower, res.recovered)}, "
              f"retained {fmt.amount(tower, res.retained)}, uncovered {fmt.amount(tower, res.uncovered)}")
        return 0

    from dataclasses import replace

    if a.title or a.units is not None or a.currency:
        tower = replace(tower, title=a.title or tower.title, currency=a.currency or tower.currency,
                        units=a.units if a.units is not None else tower.units)
    diags = tower.validate()
    for d in diags:
        if d.severity != "info":
            print(f"{d.severity}: {d.message}", file=sys.stderr)
    if has_errors(diags):
        return 1
    view = View(scale=a.scale, palette=a.palette, table=a.table)
    if not a.out and not a.svg:
        a.out = "tower.pptx"
    if a.out:
        tower.to_pptx(a.out, view=view, template=a.template)
        print(f"Wrote {a.out}")
    if a.svg:
        with open(a.svg, "w", encoding="utf-8") as fh:
            fh.write(tower.to_svg(view))
        print(f"Wrote {a.svg}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
