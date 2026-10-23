# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Quota share (cession, per-risk limit, aggregate limit), stop loss (% of EPI) and excess of loss in one programme;
  QS and XL stacked (XL on the net of QS, the default) or side by side (XL attachment and limit × (1 − cession)).
- Order % and placed % on every cover; pricing by premium (RTE), ROL or adjusted rate on EPI, with agg limit.
- QS commission, sliding scale, reinsurer management expenses, profit commission; XL no claims bonus.
- Exposure and loss coverage per risk, portfolio trapped exposure (median(0, E − A, L)) from paste or upload,
  and annual aggregate results; premium walk to result and margin.
- Validators: QS limit against the CRM counterparty limit, QS aggregate limit, EPI needed, pricing consistency.
- `tower.plot()` and `walk.plot()` with matplotlib; `pip install ri-layercake` now includes Excel, pandas and
  matplotlib.
- The default starter tower is a per risk XoL.

## [0.1.0] - unreleased

### Added
- Python package `ri-layercake`: immutable Tower model, shorthand grammar, Excel/CSV/HTML paste parser,
  validation with fixes, drop-a-loss maths, scene layout (schematic, linear, log), SVG and native PPTX
  renderers with theme colours and template support, Show code, CLI.
- Web app: Playground with synced shorthand, grid and canvas editors; drag, insert, split, merge; in-place
  warnings; drop a loss; undo, redo and autosave; starter gallery; PPTX, SVG and PNG export; How to use and
  Formulas tabs. Runs entirely in the browser on Pyodide.
