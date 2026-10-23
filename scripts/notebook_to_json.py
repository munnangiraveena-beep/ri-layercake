"""Convert the executed How to use notebook into web/public/docs/how-to-use.json.

Usage: python scripts/notebook_to_json.py notebooks/how-to-use.executed.ipynb web/public/docs/how-to-use.json
"""

from __future__ import annotations

import json
import sys
from typing import Any

import nbformat


def outputs(cell: Any) -> list[dict[str, Any]]:
    out = []
    for o in cell.get("outputs", []):
        kind = o["output_type"]
        if kind == "stream":
            out.append({"type": "stream", "text": o["text"]})
        elif kind == "error":
            raise SystemExit(f"Cell failed: {o['ename']}: {o['evalue']}")
        elif kind in ("execute_result", "display_data"):
            data = o["data"]
            if "image/svg+xml" in data:
                out.append({"type": "svg", "data": data["image/svg+xml"]})
            elif "image/png" in data:
                out.append({"type": "png", "data": data["image/png"].replace("\n", "")})
            elif "text/html" in data:
                out.append({"type": "html", "data": data["text/html"]})
            elif "text/plain" in data:
                out.append({"type": "text", "text": data["text/plain"]})
    return out


def main(src: str, dst: str) -> None:
    nb = nbformat.read(src, as_version=4)
    cells = []
    for c in nb.cells:
        if c.cell_type == "markdown":
            cells.append({"type": "markdown", "source": c.source})
        elif c.cell_type == "code":
            cells.append({"type": "code", "source": c.source, "outputs": outputs(c)})
    import ri_layercake

    with open(dst, "w", encoding="utf-8") as fh:
        json.dump({"version": ri_layercake.__version__, "cells": cells}, fh, ensure_ascii=False)
    print(f"{dst}: {len(cells)} cells")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
