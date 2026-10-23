"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { call } from "@/lib/engine";
import { useStore } from "@/lib/store";
import type { RiskLever, RiskMetrics, RiskResult } from "@/lib/types";

type Settings = {
  return_period: number; correlation: number; max_cession: number; appetite: number | null;
  w_lr: number; w_margin: number; w_roc: number; // importance, 0 to 100
};
const DEFAULTS: Settings = { return_period: 200, correlation: 30, max_cession: 50, appetite: null, w_lr: 50, w_margin: 50, w_roc: 50 };
type Cell = [number, number];
type Explore = NonNullable<RiskResult["explore"]>;

// Sequential blue ramp (light -> dark) from the reference palette, for RoC.
const RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281"];

function shown(l: RiskLever, v: number): string {
  if (l.unit === "%" || l.unit === "% EPI") return `${Math.round(v * 100)}%`;
  if (l.unit === "pts") return `${v > 0 ? "+" : ""}${Math.round(v * 1000) / 10} pts`;
  if (l.unit === "×") return `${v.toFixed(1)}×`;
  return `${Math.round(v * 100) / 100}${l.unit}`;
}

function fmt(v: number | null | undefined, d = 1): string {
  return v === null || v === undefined ? "—" : (Math.round(v * 10 ** d) / 10 ** d).toFixed(d);
}

function nearest(values: number[], v: number): number {
  let k = 0;
  for (let i = 0; i < values.length; i++) if (Math.abs(values[i] - v) < Math.abs(values[k] - v)) k = i;
  return k;
}

/** Levers -> the engine's what-if payload (only levers moved away from the programme). */
function payload(levers: RiskLever[], values: Record<string, number>) {
  const out: { cessions?: Record<string, number>; commission_shift?: number; xl_retention?: number; xl_price?: number; sl_attachment?: number } = {};
  for (const l of levers) {
    const v = values[l.key];
    if (v === undefined || Math.abs(v - l.current) < 1e-9) continue;
    if (l.key.startsWith("qs:")) out.cessions = { ...(out.cessions ?? {}), [l.key.slice(3)]: v };
    else if (l.key === "commission") out.commission_shift = v;
    else if (l.key === "xl_retention") out.xl_retention = v;
    else if (l.key === "xl_price") out.xl_price = v;
    else if (l.key === "sl_attachment") out.sl_attachment = v;
  }
  return out;
}

/** Loss ratio, margin and capital, and so return on capital: across what-ifs, as a frontier and a map. */
export default function RiskPanel() {
  const tower = useStore((s) => s.tower);
  const programme = useStore((s) => s.result?.programme);
  const edit = useStore((s) => s.edit);
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [values, setValues] = useState<Record<string, number>>({});
  const [axes, setAxes] = useState<{ x?: string; y?: string }>({});
  const [result, setResult] = useState<RiskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState<Cell | null>(null);
  const [table, setTable] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const ready = programme && programme.epi !== null && programme.expected_loss_ratio !== null;
  const units = programme?.units ?? "";
  const levers = result?.levers ?? [];

  useEffect(() => {
    let saved = false;
    try {
      saved = localStorage.getItem("ri-layercake/optimiser") === "open";
    } catch {
      // storage blocked: start closed
    }
    if (saved) Promise.resolve().then(() => setOpen(true));
  }, []);

  // A new tower resets the what-ifs to the programme as it stands.
  useEffect(() => {
    Promise.resolve().then(() => setValues({}));
  }, [tower]);

  useEffect(() => {
    if (!tower || !ready || !open) return;
    clearTimeout(timer.current);
    let live = true;
    timer.current = setTimeout(() => {
      setBusy(true);
      call<RiskResult>("risk", {
        tower, x: axes.x, y: axes.y,
        levers: payload(levers, values),
        settings: { return_period: settings.return_period, correlation: settings.correlation / 100,
          max_cession: settings.max_cession / 100, appetite: settings.appetite === null ? null : settings.appetite / 100, sims: 20000,
          weight_loss_ratio: settings.w_lr, weight_margin: settings.w_margin, weight_roc: settings.w_roc },
      }).then((r) => {
        if (live) {
          setResult(r);
          setError(null);
        }
      }).catch((e) => live && setError((e as Error).message)).finally(() => live && setBusy(false));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer.current);
    };
    // levers arrive with each result; re-running on them would loop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tower, ready, open, settings, values, axes]);

  function toggle(next: boolean) {
    setOpen(next);
    try {
      localStorage.setItem("ri-layercake/optimiser", next ? "open" : "closed");
    } catch {
      // not remembered
    }
  }

  if (!ready) {
    return (
      <section className="panel risk-panel" aria-labelledby="risk-h">
        <h2 id="risk-h">Optimise reinsurance</h2>
        <p className="muted">Enter the gross EPI and the analytic EL in Programme (or add lines) to see loss ratio, margin, capital and return on capital with and without reinsurance.</p>
      </section>
    );
  }
  if (!open) {
    return (
      <section className="panel risk-panel" aria-labelledby="risk-h">
        <h2 id="risk-h">Optimise reinsurance</h2>
        <p className="hint-line">Net loss ratio, margin and capital, and so return on capital: slide QS cessions, commission, XoL retention and
          price, and stop loss attachment, and see the efficient frontier and the best placeable programme.</p>
        <button type="button" className="primary" onClick={() => toggle(true)}>Open the optimiser</button>
        <span className="hint-line"> Simulates 20,000 years in your browser; the first time it loads the numerical library (about 3 MB, from this site).</span>
      </section>
    );
  }

  const ex = result?.explore;
  const best = ex ? ex.grid[ex.best[0]][ex.best[1]] : null;
  const value = (l: RiskLever) => values[l.key] ?? l.current;
  const setS = (patch: Partial<Settings>) => setSettings((s) => ({ ...s, ...patch }));
  const moved = Object.keys(payload(levers, values)).length > 0;

  function tryBest() {
    if (!ex) return;
    setValues((v) => ({ ...v, [ex.x.key]: ex.best_values.x, ...(ex.y && ex.best_values.y !== null ? { [ex.y.key]: ex.best_values.y } : {}) }));
  }

  return (
    <section className="panel risk-panel viz-root" aria-labelledby="risk-h">
      <h2 id="risk-h">Optimise reinsurance {busy && <span className="muted small">· simulating…</span>}
        <button type="button" className="link-button small" onClick={() => toggle(false)}>Close</button></h2>
      <p className="hint-line">
        All on gross EPI. Reinsurance lowers the net loss ratio and the capital a bad year needs, and costs some expected margin;
        return on capital (expected result ÷ capital) shows whether the trade is worth it. Only programmes the market will write count.
      </p>

      {(ex || result?.current) && (
        <Compare gross={ex?.gross ?? result!.gross!} current={ex?.current ?? result!.current!} whatif={moved ? ex?.whatif : undefined}
          rp={settings.return_period} units={units} />
      )}

      <div className="risk-grid">
        <fieldset className="levers">
          <legend>What-if levers</legend>
          {levers.map((l) => {
            const isMoved = Math.abs(value(l) - l.current) > 1e-9;
            return (
              <label key={l.key} className="risk-slider">
                <span>{l.label} <b>{shown(l, value(l))}</b>{isMoved && <span className="unit"> (now {shown(l, l.current)})</span>}</span>
                <input type="range" min={0} max={l.values.length - 1} step={1} value={nearest(l.values, value(l))}
                  aria-label={l.label} onChange={(e) => setValues((v) => ({ ...v, [l.key]: l.values[Number(e.target.value)] }))} />
              </label>
            );
          })}
          <div className="button-row">
            <button type="button" className="link-button" onClick={() => setValues({})} disabled={!moved}>Reset to programme</button>
            <button type="button" onClick={() => void edit({ type: "apply_levers", levers: payload(levers, values) }, "What-if applied to the programme")}
              disabled={!moved}>Apply what-if to programme</button>
          </div>
        </fieldset>
        <fieldset className="levers">
          <legend>What matters</legend>
          <p className="hint-line">The best programme is one you cannot improve on loss ratio, margin and RoC all at once; of those, the best weighted balance.</p>
          <Slider label="Lower net loss ratio" unit="" min={0} max={100} step={5} value={settings.w_lr} onChange={(v) => setS({ w_lr: v })} />
          <Slider label="Higher margin" unit="" min={0} max={100} step={5} value={settings.w_margin} onChange={(v) => setS({ w_margin: v })} />
          <Slider label="Higher return on capital" unit="" min={0} max={100} step={5} value={settings.w_roc} onChange={(v) => setS({ w_roc: v })} />
          <button type="button" className="link-button" onClick={() => setS({ w_lr: 50, w_margin: 50, w_roc: 50 })}>Equal weights</button>
        </fieldset>
        <fieldset className="levers">
          <legend>Settings</legend>
          <label className="tool-select"><span>Bad year</span>
            <select value={settings.return_period} onChange={(e) => setS({ return_period: Number(e.target.value) })}>
              {[10, 20, 50, 100, 200].map((n) => <option key={n} value={n}>1 in {n}</option>)}
            </select></label>
          <Slider label="Correlation between lines" unit="%" min={0} max={100} step={5} value={settings.correlation} onChange={(v) => setS({ correlation: v })} />
          <Slider label="Max placeable cession" unit="%" min={10} max={70} step={5} value={settings.max_cession} onChange={(v) => setS({ max_cession: v })} />
          <label className="tool-toggle"><input type="checkbox" checked={settings.appetite !== null}
            onChange={(e) => setS({ appetite: e.target.checked ? -15 : null })} /><span>Bad year must stay within an appetite</span></label>
          {settings.appetite !== null && (
            <Slider label="Appetite, worst margin" unit="% EPI" min={-50} max={0} step={1} value={settings.appetite} onChange={(v) => setS({ appetite: v })} />
          )}
          {ex && <p className="hint-line">Large losses: Pareto α {ex.calibration.alpha}, {ex.calibration.large_share[0]}% of EL
            {ex.calibration.calibrated ? ", calibrated to your XoL layer ELs" : " (default; enter layer ELs to calibrate)"}.</p>}
        </fieldset>
      </div>

      {ex && (
        <>
          <div className="map-axes">
            <label className="tool-select"><span>Map across</span>
              <select value={ex.x.key} onChange={(e) => setAxes((a) => ({ x: e.target.value, y: (a.y ?? ex.y?.key) === e.target.value ? "" : a.y ?? ex.y?.key }))}>
                {levers.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
              </select></label>
            <label className="tool-select"><span>and up</span>
              <select value={ex.y?.key ?? ""} onChange={(e) => setAxes((a) => ({ x: a.x ?? ex.x.key, y: e.target.value }))}>
                <option value="">Nothing (a line)</option>
                {levers.filter((l) => l.key !== ex.x.key).map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
              </select></label>
          </div>
          <div className="risk-charts">
            <Frontier ex={ex} hover={hover} setHover={setHover} units={units} rp={settings.return_period} />
            {ex.y ? <RocMap ex={ex} hover={hover} setHover={setHover} /> : <RocLine ex={ex} hover={hover} setHover={setHover} />}
          </div>
          <ThreeWay ex={ex} hover={hover} setHover={setHover} />
          {best && (
            <div className="risk-best" role="status">
              <span><b>Best placeable: {ex.x.label} {shown(ex.x, ex.best_values.x)}
                {ex.y && ex.best_values.y !== null ? ` · ${ex.y.label} ${shown(ex.y, ex.best_values.y)}` : ""}</b> → net LR {fmt(best.net_loss_ratio)}%
                (now {fmt(ex.current.net_loss_ratio)}%), margin {fmt(best.margin)}% (now {fmt(ex.current.margin)}%), RoC {fmt(best.roc)}% (now {fmt(ex.current.roc)}%),
                capital {fmt(best.capital)}{units}.</span>
              <button type="button" onClick={tryBest}>Try it</button>
              <button type="button" className="link-button" onClick={() => setTable((t) => !t)}>{table ? "Hide table" : "Show as table"}</button>
            </div>
          )}
          {table && <GridTable ex={ex} units={units} />}
        </>
      )}
      <p className="hint-line">
        Simulated: attritional losses (lognormal, correlated between lines) and large losses (Poisson count, Pareto size, calibrated to your
        XoL layer ELs) run through the QS at each line&apos;s cession and the QS limit, the XoL loss by loss with reinstatements and NCB,
        and the stop loss on the year&apos;s net loss ratio. Capital = expected result − 1-in-{settings.return_period} result. When cession or
        retention change, XoL premiums re-price with the modelled exposure at their current loading.
      </p>
      {error && <p className="field-error">{error}</p>}
    </section>
  );
}

function Slider({ label, unit, min, max, step, value, onChange }: {
  label: string; unit: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void;
}) {
  return (
    <label className="risk-slider">
      <span>{label} <b>{value}{unit === "" ? "" : unit.startsWith("%") ? "%" : ` ${unit}`}</b>{unit.length > 1 && unit.startsWith("%") ? <span className="unit"> {unit.slice(1).trim()}</span> : null}</span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label={label} />
    </label>
  );
}

function Compare({ gross, current, whatif, rp, units }: { gross: RiskMetrics; current: RiskMetrics; whatif?: RiskMetrics; rp: number; units: string }) {
  const rows: [string, (m: RiskMetrics) => string, string][] = [
    ["Net loss ratio", (m) => `${fmt(m.net_loss_ratio)}%`, "(gross losses − recoveries) ÷ gross EPI; lower is better"],
    ["Expected margin", (m) => `${fmt(m.margin)}%`, "expected result ÷ gross EPI"],
    [`Margin in a 1-in-${rp} year`, (m) => `${fmt(m.bad_year_margin)}%`, "the worst-year result ÷ gross EPI; higher is better"],
    ["Capital", (m) => `${fmt(m.capital)}${units}`, `expected result − 1-in-${rp} result; lower is better`],
    ["Return on capital", (m) => `${fmt(m.roc)}%`, "expected result ÷ capital; higher is better"],
  ];
  return (
    <table className="ba-table risk-compare" aria-label="No reinsurance, current programme and what-if">
      <thead><tr><th scope="col"></th><th scope="col">No reinsurance</th><th scope="col">Current</th>{whatif && <th scope="col">What-if</th>}</tr></thead>
      <tbody>
        {rows.map(([label, f, tip], i) => (
          <tr key={label} title={tip} className={i === 4 ? "ba-key" : undefined}>
            <th scope="row">{label}</th><td>{f(gross)}</td><td>{f(current)}</td>{whatif && <td>{f(whatif)}{whatif.placeable ? "" : " *"}</td>}
          </tr>
        ))}
      </tbody>
      {whatif && !whatif.placeable && <caption className="caption-bottom">* Not placeable: a cession above the market maximum, or reinsurers left with under 3%.</caption>}
    </table>
  );
}

function rocColour(roc: number | null, lo: number, hi: number): string {
  if (roc === null) return "#d6dde3";
  return RAMP[Math.min(RAMP.length - 1, Math.max(0, Math.floor(((roc - lo) / (hi - lo || 1)) * (RAMP.length - 1))))];
}

function rocRange(ex: Explore): [number, number] {
  const r = ex.grid.flat().filter((m) => m.placeable && m.roc !== null).map((m) => m.roc as number);
  return r.length ? [Math.min(...r), Math.max(...r)] : [0, 1];
}

function star(cx: number, cy: number, r: number): string {
  const pts = [];
  for (let i = 0; i < 10; i++) {
    const a = (Math.PI / 5) * i - Math.PI / 2;
    const rr = i % 2 === 0 ? r : r * 0.45;
    pts.push(`${cx + rr * Math.cos(a)},${cy + rr * Math.sin(a)}`);
  }
  return `M${pts.join("L")}Z`;
}

function niceTicks(lo: number, hi: number, n: number): number[] {
  const span = hi - lo || 1;
  const raw = span / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

// ---------------------------------------------------------------------- frontier

function Frontier({ ex, hover, setHover, units, rp }: { ex: Explore; hover: Cell | null; setHover: (c: Cell | null) => void; units: string; rp: number }) {
  const W = 520, H = 330, L = 52, R = 16, T = 14, B = 44;
  const cells = ex.grid.flatMap((row, iy) => row.map((m, ix) => ({ m, c: [iy, ix] as Cell })));
  const special = [ex.gross, ex.current, ex.whatif];
  const x1 = Math.max(...[...cells.map((p) => p.m.capital), ...special.map((m) => m.capital)]) * 1.08;
  const mars = [...cells.map((p) => p.m.margin), ...special.map((m) => m.margin)];
  const y0 = Math.floor(Math.min(...mars) - 1), y1 = Math.ceil(Math.max(...mars) + 1);
  const x = (v: number) => L + (v / (x1 || 1)) * (W - L - R);
  const y = (v: number) => T + ((y1 - v) / (y1 - y0 || 1)) * (H - T - B);
  const [lo, hi] = rocRange(ex);
  const epi = ex.gross.margin ? ex.gross.expected_result / (ex.gross.margin / 100) : 0;
  // Iso-RoC rays through the origin: margin% = RoC × capital ÷ EPI.
  const rays = useMemo(() => {
    if (!epi) return [];
    return [10, 25, 50, 75, 100, 150, 200, 300].filter((r) => r >= lo * 0.6 && r <= hi * 1.5).map((r) => {
      const cEnd = Math.min(x1, ((y1 / 100) * epi) / (r / 100));
      return { r, cEnd, mEnd: ((r / 100) * cEnd) / epi * 100 };
    });
  }, [epi, lo, hi, x1, y1]);
  const eff = cells
    .filter((p) => p.m.placeable && !cells.some((q) => q !== p && q.m.placeable && q.m.capital <= p.m.capital && q.m.margin > p.m.margin + 1e-9))
    .sort((a, b) => a.m.capital - b.m.capital);
  const bm = ex.grid[ex.best[0]][ex.best[1]];
  const hm = hover ? ex.grid[hover[0]]?.[hover[1]] : null;
  const label = (c: Cell) => `${shown(ex.x, ex.x.values[c[1]])}${ex.y ? `, ${shown(ex.y, ex.y.values[c[0]])}` : ""}`;
  const whatifMoved = Math.abs(ex.whatif.expected_result - ex.current.expected_result) > 1e-6;

  return (
    <figure className="risk-chart frontier">
      <figcaption><b>Efficient frontier</b> <span className="muted">· capital across, expected margin up, colour = RoC; dashed rays are equal RoC</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Efficient frontier of capital against expected margin, coloured by return on capital" onPointerLeave={() => setHover(null)}>
        {niceTicks(y0, y1, 6).map((v) => <g key={`y${v}`}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" /><text x={L - 6} y={y(v) + 4} className="tick" textAnchor="end">{v}%</text></g>)}
        {niceTicks(0, x1, 5).map((v) => <text key={`x${v}`} x={x(v)} y={H - B + 16} className="tick" textAnchor="middle">{v}</text>)}
        <text x={(L + W - R) / 2} y={H - 8} className="axis-label" textAnchor="middle">Capital ({units}): expected − 1-in-{rp} result</text>
        <text x={14} y={(T + H - B) / 2} className="axis-label" textAnchor="middle" transform={`rotate(-90 14 ${(T + H - B) / 2})`}>Expected margin, % of EPI</text>
        <g className="iso">
          {rays.map((r) => {
            const yy0 = Math.max(y0, 0);
            const c0 = (yy0 / 100) * epi / (r.r / 100);
            return (
              <g key={r.r}>
                <line x1={x(c0)} y1={y(yy0)} x2={x(r.cEnd)} y2={y(r.mEnd)} />
                <text x={x(r.cEnd) - 4} y={y(r.mEnd) + 12} textAnchor="end">RoC {r.r}%</text>
              </g>
            );
          })}
        </g>
        {eff.length > 1 && <polyline className="frontier-line" points={eff.map((p) => `${x(p.m.capital)},${y(p.m.margin)}`).join(" ")} />}
        {cells.map(({ m, c }) => (
          <circle key={`${c[0]}-${c[1]}`} cx={x(m.capital)} cy={y(m.margin)} r={hover && hover[0] === c[0] && hover[1] === c[1] ? 7.5 : 5}
            className={!m.placeable ? "pt unplaceable-pt" : ex.efficient[c[0]][c[1]] ? "pt efficient-pt" : "pt"} fill={m.placeable ? rocColour(m.roc, lo, hi) : "none"}
            onPointerEnter={() => setHover(c)}>
            <title>{`${label(c)}: RoC ${fmt(m.roc)}%, margin ${fmt(m.margin)}%, net LR ${fmt(m.net_loss_ratio)}%, capital ${fmt(m.capital)}${units}${m.placeable ? "" : " (not placeable)"}`}</title>
          </circle>
        ))}
        <rect x={x(ex.gross.capital) - 5} y={y(ex.gross.margin) - 5} width={10} height={10} className="mk-gross"><title>No reinsurance</title></rect>
        <circle cx={x(ex.current.capital)} cy={y(ex.current.margin)} r={8} className="mk-current"><title>Current programme</title></circle>
        {whatifMoved && <path d={`M${x(ex.whatif.capital)},${y(ex.whatif.margin) - 8} l8,8 l-8,8 l-8,-8 z`} className="mk-whatif"><title>What-if</title></path>}
        <path d={star(x(bm.capital), y(bm.margin), 9)} className="mk-best"><title>Best balance of loss ratio, margin and RoC</title></path>
        {hm && hover && (
          <text x={Math.min(x(hm.capital) + 10, W - 170)} y={y(hm.margin) - 10} className="hover-label" pointerEvents="none">
            {label(hover)} · RoC {fmt(hm.roc)}% · LR {fmt(hm.net_loss_ratio)}%
          </text>
        )}
      </svg>
      <div className="legend">
        <span className="legend-item"><i className="swatch mk-gross-sw" />No reinsurance</span>
        <span className="legend-item"><i className="swatch mk-current-sw" />Current</span>
        {whatifMoved && <span className="legend-item"><i className="swatch mk-current-sw" style={{ transform: "rotate(45deg)", borderRadius: 0 }} />What-if</span>}
        <span className="legend-item"><i className="swatch mk-best-sw" />Best balance</span>
        <span className="legend-item"><i className="swatch efficient-sw" />Efficient on LR, margin and RoC</span>
        <span className="legend-item"><i className="swatch unplaceable-sw" />Not placeable</span>
        <span className="legend-item"><span className="ramp small" style={{ background: `linear-gradient(90deg, ${RAMP[0]}, ${RAMP[RAMP.length - 1]})` }} /> RoC {fmt(lo, 0)}–{fmt(hi, 0)}%</span>
      </div>
    </figure>
  );
}

// ---------------------------------------------------------------------- RoC map and line

function RocMap({ ex, hover, setHover }: { ex: Explore; hover: Cell | null; setHover: (c: Cell | null) => void }) {
  const y = ex.y!;
  const nx = ex.x.values.length, ny = y.values.length;
  const cell = Math.min(30, Math.floor(300 / Math.max(nx, ny)));
  const L = 70, T = 10, B = 46;
  const W = L + nx * cell + 10, H = T + ny * cell + B;
  const [lo, hi] = rocRange(ex);
  const cur: Cell = [nearest(y.values, y.current), nearest(ex.x.values, ex.x.current)];
  return (
    <figure className="risk-chart rocmap">
      <figcaption><b>Return on capital</b> <span className="muted">· {ex.x.label} across, {y.label} up; hatched = not placeable</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Return on capital by ${ex.x.label} and ${y.label}`} onPointerLeave={() => setHover(null)}>
        <defs>
          <pattern id="roc-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="5" className="hatch-line" />
          </pattern>
        </defs>
        {ex.grid.map((row, iy) => row.map((m, ix) => {
          const x0 = L + ix * cell, y0 = T + (ny - 1 - iy) * cell;
          const on = hover && hover[0] === iy && hover[1] === ix;
          return (
            <g key={`${iy}-${ix}`} onPointerEnter={() => setHover([iy, ix])}>
              <rect x={x0 + 1} y={y0 + 1} width={cell - 2} height={cell - 2} rx={2} fill={m.placeable ? rocColour(m.roc, lo, hi) : "var(--surface-2)"} />
              {!m.placeable && <rect x={x0 + 1} y={y0 + 1} width={cell - 2} height={cell - 2} fill="url(#roc-hatch)" />}
              {on && <rect x={x0} y={y0} width={cell} height={cell} className="cell-hover" />}
              <title>{`${shown(ex.x, ex.x.values[ix])}, ${shown(y, y.values[iy])}: RoC ${fmt(m.roc)}%, margin ${fmt(m.margin)}%, net LR ${fmt(m.net_loss_ratio)}%${m.placeable ? "" : " (not placeable)"}`}</title>
            </g>
          );
        }))}
        <rect x={L + ex.best[1] * cell} y={T + (ny - 1 - ex.best[0]) * cell} width={cell} height={cell} className="mix-best" />
        <circle cx={L + cur[1] * cell + cell / 2} cy={T + (ny - 1 - cur[0]) * cell + cell / 2} r={4} className="mix-current" />
        {ex.x.values.map((v, k) => (k % Math.ceil(nx / 6) === 0 ? <text key={`x${k}`} x={L + k * cell + cell / 2} y={T + ny * cell + 14} className="tick" textAnchor="middle">{shown(ex.x, v)}</text> : null))}
        {y.values.map((v, k) => (k % Math.ceil(ny / 6) === 0 ? <text key={`y${k}`} x={L - 6} y={T + (ny - 1 - k) * cell + cell / 2 + 4} className="tick" textAnchor="end">{shown(y, v)}</text> : null))}
        <text x={L + (nx * cell) / 2} y={H - 8} className="axis-label" textAnchor="middle">{ex.x.label}</text>
      </svg>
      <div className="legend">
        <span className="legend-item"><i className="swatch bestbox" />Best</span>
        <span className="legend-item"><i className="swatch currentdot" />Current</span>
        <span className="legend-item muted">Up the side: {y.label}</span>
      </div>
    </figure>
  );
}

function RocLine({ ex, hover, setHover }: { ex: Explore; hover: Cell | null; setHover: (c: Cell | null) => void }) {
  const row = ex.grid[0];
  const W = 420, H = 300, L = 48, R = 14, T = 14, B = 44;
  const rocs = row.map((m) => m.roc ?? 0);
  const y0 = Math.floor(Math.min(...rocs) / 5) * 5, y1 = Math.ceil(Math.max(...rocs) / 5) * 5;
  const x = (i: number) => L + (i / Math.max(1, row.length - 1)) * (W - L - R);
  const y = (v: number) => T + ((y1 - v) / (y1 - y0 || 1)) * (H - T - B);
  return (
    <figure className="risk-chart rocline">
      <figcaption><b>Return on capital</b> <span className="muted">· by {ex.x.label}</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Return on capital by ${ex.x.label}`} onPointerLeave={() => setHover(null)}>
        {niceTicks(y0, y1, 5).map((v) => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" /><text x={L - 6} y={y(v) + 4} className="tick" textAnchor="end">{v}%</text></g>)}
        <polyline className="series s1" fill="none" points={row.map((m, i) => `${x(i)},${y(m.roc ?? 0)}`).join(" ")} />
        {row.map((m, i) => (
          <circle key={i} cx={x(i)} cy={y(m.roc ?? 0)} r={hover && hover[1] === i ? 7 : 5} className={m.placeable ? "series-dot s1" : "pt unplaceable-pt"}
            onPointerEnter={() => setHover([0, i])}><title>{`${shown(ex.x, ex.x.values[i])}: RoC ${fmt(m.roc)}%`}</title></circle>
        ))}
        <path d={star(x(ex.best[1]), y(row[ex.best[1]].roc ?? 0), 9)} className="mk-best" />
        {row.map((_, i) => (i % Math.ceil(row.length / 6) === 0 ? <text key={`t${i}`} x={x(i)} y={H - B + 16} className="tick" textAnchor="middle">{shown(ex.x, ex.x.values[i])}</text> : null))}
        <text x={(L + W - R) / 2} y={H - 8} className="axis-label" textAnchor="middle">{ex.x.label}</text>
      </svg>
    </figure>
  );
}

// ---------------------------------------------------------------------- three measures together

/** Parallel axes: net loss ratio, margin and RoC, each drawn so up is better; one line per efficient programme. */
function ThreeWay({ ex, hover, setHover }: { ex: Explore; hover: Cell | null; setHover: (c: Cell | null) => void }) {
  const W = 760, H = 250, L = 70, R = 70, T = 26, B = 30;
  const cells = ex.grid.flatMap((row, iy) => row.map((m, ix) => ({ m, c: [iy, ix] as Cell }))).filter((p) => p.m.placeable);
  const eff = cells.filter((p) => ex.efficient[p.c[0]][p.c[1]]);
  const all = [...cells.map((p) => p.m), ex.gross, ex.current];
  const axes = [
    { key: "net_loss_ratio" as const, label: "Net loss ratio", better: "lower", lo: Math.min(...all.map((m) => m.net_loss_ratio)), hi: Math.max(...all.map((m) => m.net_loss_ratio)) },
    { key: "margin" as const, label: "Expected margin", better: "higher", lo: Math.min(...all.map((m) => m.margin)), hi: Math.max(...all.map((m) => m.margin)) },
    { key: "roc" as const, label: "Return on capital", better: "higher", lo: Math.min(...all.map((m) => m.roc ?? 0)), hi: Math.max(...all.map((m) => m.roc ?? 0)) },
  ];
  const ax = (i: number) => L + (i / (axes.length - 1)) * (W - L - R);
  const ay = (i: number, v: number) => {
    const a = axes[i];
    const f = (v - a.lo) / (a.hi - a.lo || 1);
    return T + (a.better === "lower" ? f : 1 - f) * (H - T - B);
  };
  const path = (m: RiskMetrics) => axes.map((a, i) => `${i ? "L" : "M"}${ax(i)},${ay(i, (a.key === "roc" ? m.roc ?? 0 : m[a.key]))}`).join(" ");
  const scoreOf = (c: Cell) => ex.score[c[0]][c[1]] ?? 0;
  const bm = ex.grid[ex.best[0]][ex.best[1]];
  const label = (c: Cell) => `${shown(ex.x, ex.x.values[c[1]])}${ex.y ? `, ${shown(ex.y, ex.y.values[c[0]])}` : ""}`;
  const hm = hover && ex.grid[hover[0]]?.[hover[1]];
  return (
    <figure className="risk-chart threeway">
      <figcaption><b>The three together</b> <span className="muted">· each line is an efficient programme; up is better on every axis; colour = weighted score</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Parallel axes of net loss ratio, expected margin and return on capital for the efficient programmes" onPointerLeave={() => setHover(null)}>
        {axes.map((a, i) => (
          <g key={a.key}>
            <line x1={ax(i)} x2={ax(i)} y1={T} y2={H - B} className="pc-axis" />
            <text x={i === 0 ? ax(i) - 8 : i === axes.length - 1 ? ax(i) + 8 : ax(i)} y={T - 10} className="axis-label"
              textAnchor={i === 0 ? "start" : i === axes.length - 1 ? "end" : "middle"}>{a.label} ({a.better} is better)</text>
            <text x={ax(i) + (i === 0 ? -8 : 8)} y={T + 4} className="tick" textAnchor={i === 0 ? "end" : "start"}>{fmt(a.better === "lower" ? a.lo : a.hi)}%</text>
            <text x={ax(i) + (i === 0 ? -8 : 8)} y={H - B + 4} className="tick" textAnchor={i === 0 ? "end" : "start"}>{fmt(a.better === "lower" ? a.hi : a.lo)}%</text>
          </g>
        ))}
        {eff.map(({ m, c }) => {
          const on = hover && hover[0] === c[0] && hover[1] === c[1];
          return (
            <path key={`${c[0]}-${c[1]}`} d={path(m)} className={on ? "pc-line on" : "pc-line"} stroke={RAMP[Math.min(RAMP.length - 1, Math.floor((scoreOf(c) / 100) * (RAMP.length - 1)))]}
              onPointerEnter={() => setHover(c)}>
              <title>{`${label(c)}: net LR ${fmt(m.net_loss_ratio)}%, margin ${fmt(m.margin)}%, RoC ${fmt(m.roc)}%, score ${fmt(scoreOf(c), 0)}`}</title>
            </path>
          );
        })}
        <path d={path(ex.gross)} className="pc-gross"><title>No reinsurance</title></path>
        <path d={path(ex.current)} className="pc-current"><title>Current programme</title></path>
        <path d={path(bm)} className="pc-best"><title>Best balance</title></path>
        {hm && hover && <text x={W / 2} y={H - 8} className="hover-label" textAnchor="middle">{label(hover)}: LR {fmt(hm.net_loss_ratio)}% · margin {fmt(hm.margin)}% · RoC {fmt(hm.roc)}%</text>}
      </svg>
      <div className="legend">
        <span className="legend-item"><i className="swatch pc-best-sw" />Best balance</span>
        <span className="legend-item"><i className="swatch pc-current-sw" />Current</span>
        <span className="legend-item"><i className="swatch pc-gross-sw" />No reinsurance</span>
        <span className="legend-item"><span className="ramp small" style={{ background: `linear-gradient(90deg, ${RAMP[0]}, ${RAMP[RAMP.length - 1]})` }} /> Weighted score, low to high</span>
      </div>
    </figure>
  );
}

function GridTable({ ex, units }: { ex: Explore; units: string }) {
  const rows = ex.grid.flatMap((row, iy) => row.map((m, ix) => ({ m, iy, ix })));
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Programmes on the map">
      <table className="loss-table">
        <thead><tr><th scope="col">{ex.x.label}</th>{ex.y && <th scope="col">{ex.y.label}</th>}<th scope="col">Net LR</th><th scope="col">Margin</th>
          <th scope="col">Bad-year margin</th><th scope="col">Capital</th><th scope="col">RoC</th><th scope="col">Efficient</th><th scope="col">Score</th><th scope="col">Placeable</th></tr></thead>
        <tbody>
          {rows.map(({ m, iy, ix }) => (
            <tr key={`${iy}-${ix}`} className={iy === ex.best[0] && ix === ex.best[1] ? "is-selected" : undefined}>
              <th scope="row">{shown(ex.x, ex.x.values[ix])}</th>{ex.y && <td>{shown(ex.y, ex.y.values[iy])}</td>}
              <td>{fmt(m.net_loss_ratio)}%</td><td>{fmt(m.margin)}%</td><td>{fmt(m.bad_year_margin)}%</td>
              <td>{fmt(m.capital)}{units}</td><td>{fmt(m.roc)}%</td><td>{ex.efficient[iy][ix] ? "yes" : ""}</td>
              <td>{ex.score[iy][ix] === null ? "" : fmt(ex.score[iy][ix], 0)}</td><td>{m.placeable ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
