# ri-layercake

Turn reinsurance programmes into presentation-ready towers. Paste your layers, shape them, drop a loss through the
tower, and export a native, editable PowerPoint slide that takes on your deck's theme.

It comes as two things built from one Python engine:

- **A Python package**: `pip install ri-layercake`, for scripts, Jupyter and the command line.
- **A web app**: the [Playground](https://ri-layercake.vercel.app) runs the same package in your browser (Pyodide). There is no server, and your
  programme data never leaves your machine.

## Quick start: Python

```bash
pip install ri-layercake    # one install: PowerPoint, Excel/CSV input, DataFrames and matplotlib plots
```

```python
import ri_layercake as lc

tower = lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 50 @ 75%, 100 xs 100", title="Property cat 2027")
tower                                  # draws the tower and its table in Jupyter
tower.validate()                       # [Diagnostic(info, 'Layer 2 is 75% placed')]
tower.drop_loss(120)                   # recovery per layer for a £120m loss
tower.to_pptx("renewal_2027.pptx", template="house_style.potx")
```

Quota share, per risk XoL and stop loss in one programme, with the premium walk:

```python
prog = lc.Tower.from_text(
    "epi 150, qs 25% limit 40 agg 400 comm 32%, 2 ret, 8 xs 2 rate 1.8% el 1.2 ncb 10%, sl 20% xs 85% rate 1.5%"
).programme(internal_expenses=0.11, expected_loss_ratio=0.6, brokerage_xl=0.1, brokerage_qs=0.025, tax=0.02)

prog.exposure(50)                  # one risk: QS cedes first, the net passes through the XL layers
prog.programme(arrangement="side_by_side").exposure(50)   # XL attachment and limit x (1 - cession)
prog.aggregate(130)                # a year: QS terms, stop loss on the net loss ratio
prog.portfolio("risks.xlsx")       # trapped exposure: median(0, E - A, L) per risk and layer
prog.premium_walk().plot()         # EPI to result and margin, as a waterfall
prog.plot()                        # the tower with matplotlib
```

Find the structure that balances net loss ratio, margin and return on capital (20,000 simulated years, capital as
the 1-in-200 shortfall from the expected result):

```python
from ri_layercake import risk

ex = risk.explore(prog, "qs:*", "commission")   # QS cession against a commission change
ex.current, ex.best                              # today's metrics; the best-balanced placeable cell
ex.plot()                                        # efficient frontier and return on capital map
```

From a workbook, one slide per programme:

```python
for sheet in ["Marine", "Casualty", "Property"]:
    lc.Tower.from_excel("programmes.xlsx", sheet=sheet, title=sheet).to_pptx(f"{sheet}.pptx")
```

Command line:

```bash
ri-layercake tower programme.xlsx --out renewal.pptx
ri-layercake tower "10 ret, 40 xs 10, 50 xs 50" --scale linear --svg tower.svg
ri-layercake check programme.xlsx          # diagnostics; exit code 1 on errors
ri-layercake loss "40 xs 10, 50 xs 50" 75  # drop-a-loss table
```

## Quick start: web app

Open the [Playground](https://ri-layercake.vercel.app), paste a block from Excel (or type `10 ret, 40 xs 10, 50 xs 50`), drag the layer edges, slide a
loss up the tower, and press **Download PowerPoint**. Add your own .pptx or .potx to use its theme and title layout.

## Three example towers

| Tower | Shorthand |
| --- | --- |
| Property cat XL | `25 ret, 25 xs 25, 50 xs 50, 100 xs 100 @ 90%, 150 xs 200 @ 85%, 200 xs 350 @ 70%` |
| Casualty XL | `5 ret, 5 xs 5, 10 xs 10 2 @ 100%, 20 xs 20, 40 xs 40 @ 80%` |
| Gap and overlap | `10 ret, 40 xs 10, 50 xs 60, 60 xs 100, 100 xs 140` |

More are in the [examples folder](https://github.com/munnangiraveena-beep/ri-layercake/tree/main/examples) and in the Playground's gallery. All numbers are invented.

## Shorthand

| Input | Means |
| --- | --- |
| `10 ret` | Retention of 10 |
| `40 xs 10` | 40 excess of 10, 100% placed |
| `50 xs 50 @ 75%` or `75% part of 50 xs 50` | 75% placed |
| `Cat 3: 100 xs 100, 1 @ 100%, prem 4.2` | Named layer, one reinstatement at 100%, premium 4.2 |
| `£25m xs £5m rol 12%` | Premium derived from rate on line (3.0) |
| `epi 120, 5 xs 5 rate 2%` | Premium (RTE) = EPI × adj. rate = 2.4 |
| `40 xs 10 @ 90% order 80%` | Order 80% of the layer, 90% of the order placed |
| `qs 20% limit 50 agg 300 comm 30%` | Quota share: cession, per-risk limit, aggregate limit, commission |
| `sl 20% xs 80%` | Stop loss, 20% of EPI excess of an 80% loss ratio |
| `10 xs 10 ncb 10% el 0.6` | No claims bonus 10%, layer expected loss 0.6 |

Formulas used everywhere (inspector, table, slide):

- Premium (RTE) = EPI (gross) × Adj. rate · ROL = Premium (RTE) ÷ Layer limit · Adj. rate = ROL × Layer limit ÷ EPI
- Agg limit = Limit × (1 + Reinstatements) · Share = Order % × Placed %
- Result = EPI − Internal expenses − QS premium − XL premium − Reinst. premium − EL + EL saved by QS + EL saved by XL
  + QS commission + Profit comm. + NCB − Brokerage − Tax; Margin = Result ÷ EPI

## Privacy

All parsing, maths and export run in your browser. The site is static, Pyodide and every wheel are self-hosted with
integrity hashes, and a strict Content Security Policy (`connect-src 'self'`) stops the page sending data anywhere.
You can check this in your browser's network tab: no requests are made while you edit or export. Autosave stays in
your browser, and **Clear data** removes it.

## Repository

```
python/      the ri_layercake package (model, parser, validation, maths, scene, SVG and PPTX renderers, CLI)
web/         the Next.js static site: Playground, How to use, Formulas
notebooks/   how-to-use.ipynb, executed in CI and shown in the How to use tab
examples/    synthetic programmes
scripts/     notebook and pre-render helpers
```

Development:

```bash
cd python && pip install -e ".[dev]" && pytest          # engine tests
pip wheel --no-deps -w dist .                           # build the wheel the web app loads
cd ../web && npm ci && npm run py && npm run build      # self-host Pyodide, build the site
npx playwright test                                      # end-to-end in Chromium, Firefox and WebKit
```

## Disclaimer

ri-layercake is an independent personal project, built in the author's own time on openly published, textbook
methods with synthetic or illustrative data. It contains no data, code, models or methodology from any current or
former employer or its clients, and it is not affiliated with or endorsed by any of them. Outputs are illustrative and
depend entirely on the inputs provided: they are not pricing, underwriting, actuarial, investment or professional
advice, and should not be relied on for any real transaction.

Licence: MIT.
