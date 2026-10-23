"use client";

import { useEffect, useState } from "react";
import { call } from "@/lib/engine";
import { money } from "@/lib/draw";
import { useStore } from "@/lib/store";
import type { WalkResult } from "@/lib/types";

function round(v: number): string {
  return String(Math.round(v * 10000) / 10000);
}

function Num({ label, value, percent, onCommit, hint, suffix, placeholder }: {
  label: string; value: number | null; percent?: boolean; onCommit: (v: number | null) => void; hint?: string; suffix?: string;
  placeholder?: string;
}) {
  const shown = value === null ? "" : percent ? round(value * 100) : round(value);
  return (
    <label title={hint}>
      <span>{label}{suffix && <span className="unit"> {suffix}</span>}</span>
      <input inputMode="decimal" defaultValue={shown} key={`${label}-${shown}`} placeholder={placeholder}
        onBlur={(e) => {
          const raw = e.target.value.trim().replace(/[,%£$€]/g, "");
          if (raw === shown) return;
          if (raw === "") return onCommit(null);
          const n = Number(raw);
          if (Number.isFinite(n)) onCommit(percent ? n / 100 : n);
        }}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
    </label>
  );
}

// ---------------------------------------------------------------------- programme

export function ProgrammePanel() {
  const p = useStore((s) => s.result?.programme);
  const edit = useStore((s) => s.edit);
  if (!p) return null;
  const set = (fields: Record<string, unknown>, what: string) => void edit({ type: "programme", fields }, what);
  return (
    <section className="panel" aria-labelledby="programme-h">
      <h2 id="programme-h">Programme</h2>
      <div className="form-grid">
        {p.lines.length ? (
          <label title="The sum of the lines' EPI"><span>EPI (gross)<span className="unit"> {p.units}, total of lines</span></span>
            <input readOnly value={p.epi ?? ""} /></label>
        ) : (
          <Num label="EPI (gross)" suffix={p.units} value={p.epi} hint="Estimated premium income, gross: drives premium from adj. rate, QS premium and stop loss amounts"
            onCommit={(v) => set({ epi: v }, "EPI set")} />
        )}
        <label title="Per risk is the default">
          <span>Cover</span>
          <select value={p.cover} onChange={(e) => set({ cover: e.target.value }, "cover type set")}>
            <option value="per_risk">Per risk XoL</option>
            <option value="cat">Cat XoL</option>
          </select>
        </label>
        <Num label="CRM counterparty limit" suffix={p.units} value={p.counterparty_limit}
          hint="The CRM team's limit for your largest counterparty: the expected QS limit"
          onCommit={(v) => set({ counterparty_limit: v }, "counterparty limit set")} />
        <Num label="Internal expenses" suffix="% EPI" percent value={p.internal_expenses}
          placeholder={`${round(p.defaults.internal_expenses * 100)} (default)`} hint="Leave empty to use the 30% default"
          onCommit={(v) => set({ internal_expenses: v }, "internal expenses set")} />
        {p.lines.length ? (
          <label title="EPI-weighted from the lines"><span>EL (analytic)<span className="unit"> % EPI, from lines</span></span>
            <input readOnly value={p.expected_loss_ratio === null ? "" : round(p.expected_loss_ratio * 100)} /></label>
        ) : (
          <Num label="EL (analytic)" suffix="% EPI" percent value={p.expected_loss_ratio} hint="Gross expected loss ratio"
            onCommit={(v) => set({ expected_loss_ratio: v }, "expected loss set")} />
        )}
        <Num label="Brokerage XoL" suffix="% XL prem" percent value={p.brokerage_xl}
          placeholder={`${round(p.defaults.brokerage_xl * 100)} (default)`} hint="On XL and stop loss premium; usually 10%"
          onCommit={(v) => set({ brokerage_xl: v }, "XoL brokerage set")} />
        <Num label="Brokerage QS" suffix="% QS prem" percent value={p.brokerage_qs}
          placeholder={`${round(p.defaults.brokerage_qs * 100)} (default)`} hint="On QS premium; usually 2.5%"
          onCommit={(v) => set({ brokerage_qs: v }, "QS brokerage set")} />
        <Num label="Tax" suffix="% RI prem" percent value={p.tax} hint="On ceded reinsurance premium"
          onCommit={(v) => set({ tax: v }, "tax set")} />
      </div>
      <Lines />
    </section>
  );
}

/** Lines of business inside this one programme: each its own EPI, EL, QS cession and volatility. */
function Lines() {
  const p = useStore((s) => s.result?.programme);
  const edit = useStore((s) => s.edit);
  if (!p) return null;
  const upd = (name: string, fields: Record<string, unknown>, what: string) => void edit({ type: "update_line", name, fields }, `${name} ${what}`);
  const cell = (name: string, field: string, value: number | null, percent: boolean, label: string) => (
    <input className="cell numeric" inputMode="decimal" aria-label={`${name} ${label}`} key={`${name}-${field}-${value}`}
      defaultValue={value === null ? "" : percent ? round(value * 100) : round(value)}
      placeholder={field === "cession" ? "QS" : field === "volatility" ? "25" : ""}
      onBlur={(e) => {
        const raw = e.target.value.trim().replace(/[,%]/g, "");
        const n = raw === "" ? null : Number(raw);
        if (n !== null && !Number.isFinite(n)) return;
        const v = n === null ? null : percent ? n / 100 : n;
        if (v !== value) upd(name, { [field]: v }, `${label} set`);
      }}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
  );
  return (
    <div className="lines">
      <p className="terms-sub">Lines in this programme <span className="muted">(one QS treaty, a cession per line; XoL on the combined net)</span></p>
      {p.lines.length > 0 && (
        <table className="layer-grid" aria-label="Lines of business">
          <thead><tr><th scope="col">Line</th><th scope="col">EPI {p.units}</th><th scope="col">EL %</th>
            <th scope="col" title="This line's QS cession; empty uses the QS treaty's cession">QS %</th>
            <th scope="col" title="Volatility: coefficient of variation of the line's annual loss ratio, for the risk view">Vol %</th><th scope="col"><span className="sr-only">Remove</span></th></tr></thead>
          <tbody>
            {p.lines.map((l) => (
              <tr key={l.name}>
                <th scope="row"><input className="cell" aria-label={`${l.name} name`} defaultValue={l.name} key={l.name}
                  onBlur={(e) => e.target.value.trim() && e.target.value !== l.name && upd(l.name, { name: e.target.value.trim() }, "renamed")}
                  onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} /></th>
                <td>{cell(l.name, "epi", l.epi, false, "EPI")}</td>
                <td>{cell(l.name, "expected_loss_ratio", l.expected_loss_ratio, true, "expected loss ratio")}</td>
                <td>{cell(l.name, "cession", l.cession, true, "QS cession")}</td>
                <td>{cell(l.name, "volatility", l.volatility, true, "volatility")}</td>
                <td><button type="button" className="icon-button" aria-label={`Remove ${l.name}`}
                  onClick={() => void edit({ type: "remove_line", name: l.name }, `${l.name} removed`)}>×</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button type="button" onClick={() => {
        const n = p.lines.length + 1;
        const names = ["Credit", "Surety", "Bond", "Property", "Casualty"];
        const name = names.find((x) => !p.lines.some((l) => l.name === x)) ?? `Line ${n}`;
        const epi = p.lines.length ? 50 : p.epi ?? 100;
        void edit({ type: "add_line", name, epi, expected_loss_ratio: p.expected_loss_ratio ?? 0.55, volatility: 0.3 }, `${name} added`);
      }}>+ Add line</button>
    </div>
  );
}

// ---------------------------------------------------------------------- coverage

export function CoveragePanel() {
  const mode = useStore((s) => s.coverMode);
  const setMode = useStore((s) => s.setCoverMode);
  const error = useStore((s) => s.coverError);
  return (
    <section className="panel" aria-labelledby="cover-h">
      <h2 id="cover-h">Exposure and loss coverage</h2>
      <div className="segmented small" role="tablist" aria-label="Coverage view">
        {([["risk", "Per risk"], ["portfolio", "Portfolio"], ["aggregate", "Annual aggregate"]] as const).map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={mode === k} className={mode === k ? "on" : undefined}
            onClick={() => setMode(k)}>{label}</button>
        ))}
      </div>
      {mode === "risk" && <PerRisk />}
      {mode === "portfolio" && <Portfolio />}
      {mode === "aggregate" && <Aggregate />}
      {error && <p className="field-error" role="alert">{error}</p>}
    </section>
  );
}

function PerRisk() {
  const loss = useStore((s) => s.loss);
  const r = useStore((s) => s.lossResult);
  const layers = useStore((s) => s.result?.layers);
  const p = useStore((s) => s.result?.programme);
  const { setLoss, setView } = useStore.getState();
  const view = useStore((s) => s.view);
  const top = (layers ?? []).filter((l) => l.kind !== "sl").reduce((m, l) => Math.max(m, l.exhaust), 0);
  const unit = p ? `${money(p.currency, p.units, 0).replace(/0.*/, "")}${p.units}` : "";
  const hasQs = (layers ?? []).some((l) => l.kind === "qs");
  const lossLine = useStore((s) => s.lossLine);
  const setLossLine = useStore((s) => s.setLossLine);
  return (
    <>
      <p className="hint-line">One risk&apos;s exposure (trapped exposure) or a single loss to it. Trapped = median(0, X − A, L).</p>
      {hasQs && p && p.lines.length > 0 && (
        <label className="tool-select">
          <span>Risk is in</span>
          <select value={lossLine ?? ""} onChange={(e) => void setLossLine(e.target.value || null)}>
            <option value="">Weighted across lines</option>
            {p.lines.map((l) => <option key={l.name} value={l.name}>{l.name} (QS {l.cession !== null ? Math.round(l.cession * 100) : "treaty"}%)</option>)}
          </select>
        </label>
      )}
      <div className="loss-controls">
        <input type="range" min={0} max={Math.ceil(top * 1.2) || 100} step={top > 200 ? 5 : 0.5} value={loss ?? 0}
          aria-label={`Exposure or loss in ${unit}`} onChange={(e) => void setLoss(Number(e.target.value))} />
        <label className="loss-amount">
          <span className="sr-only">Exposure or loss amount</span>
          <input inputMode="decimal" value={loss ?? ""} placeholder="e.g. 50"
            onChange={(e) => void setLoss(e.target.value === "" ? null : Number(e.target.value))} />
          <span>{unit}</span>
        </label>
      </div>
      {loss === null && (
        <button type="button" className="link-button" onClick={() => void setLoss(Math.round(top * 0.7) || 50)}>
          Try an example: a {Math.round(top * 0.7) || 50}{p?.units} risk
        </button>
      )}
      {r && loss !== null && (
        <>
          <table className="loss-table">
            <thead>
              <tr><th scope="col">Cover</th><th scope="col" title="What the cover takes, 100% basis">Takes</th>
                <th scope="col" title="Order × placed">Share</th><th scope="col">Recovery</th></tr>
            </thead>
            <tbody>
              {[...r.loss.rows].reverse().map((row) => (
                <tr key={row.layer} className={row.exhausted ? "exhausted" : undefined}>
                  <th scope="row">{row.name}{row.exhausted && <span className="tag">exhausted</span>}
                    {row.ncb === "lost" && <span className="tag muted-tag" title="This loss uses up the no claims bonus">NCB lost</span>}</th>
                  <td>{row.layer === "R" ? row.retained : row.recovery_100}</td>
                  <td>{row.placed}</td>
                  <td>{row.recovery_placed}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="facts">
            {hasQs && (<><dt>Ceded to QS</dt><dd>{r.loss.totals.qs_ceded}</dd><dt>Net after QS, into the XL</dt><dd>{r.loss.totals.net_of_qs}</dd></>)}
            <dt>Recovered</dt><dd>{r.loss.totals.recovered}</dd>
            <dt title="Retention plus unplaced shares">Retained</dt><dd>{r.loss.totals.retained}</dd>
            {r.loss.totals.uncovered !== "0" && (<><dt title="In gaps or above the top">Uncovered</dt><dd>{r.loss.totals.uncovered}</dd></>)}
            <dt>Reinstatement premium</dt><dd>{r.loss.totals.reinstatement_premium}</dd>
          </dl>
          <div className="button-row">
            {!hasQs && (
              <button type="button" onClick={() => void setView({ loss: view.loss !== null ? null : loss })}>
                {view.loss !== null ? "Remove from slide" : "Add loss line to slide"}
              </button>
            )}
            <button type="button" className="link-button" onClick={() => void setLoss(null)}>Clear</button>
          </div>
        </>
      )}
    </>
  );
}

function Portfolio() {
  const r = useStore((s) => s.portfolioResult);
  const run = useStore((s) => s.runPortfolio);
  const [text, setText] = useState("");
  return (
    <>
      <p className="hint-line">Paste or upload risks with an exposure (sum insured, TSI, PML) column: trapped exposure per layer.</p>
      <textarea className="portfolio-input" rows={3} value={text} placeholder={"Risk\tSum insured\nWarehouse\t1.5\nHotel\t12"}
        aria-label="Portfolio of risks" onChange={(e) => setText(e.target.value)} onPaste={(e) => e.stopPropagation()} />
      <div className="button-row">
        <button type="button" disabled={!text.trim()} onClick={() => void run({ text })}>Calculate</button>
        <label className="button file-button">
          Upload CSV or Excel
          <input type="file" accept=".csv,.tsv,.txt,.xlsx,.xlsm" onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            if (f.size > 10 * 1024 * 1024) {
              useStore.setState({ coverError: "Files over 10 MB are not supported" });
              return;
            }
            const bytes = new Uint8Array(await f.arrayBuffer());
            let bin = "";
            for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
            void run({ base64: btoa(bin), name: f.name });
          }} />
        </label>
        <button type="button" className="link-button" onClick={() => void run({ example: true })}>Try an example portfolio</button>
      </div>
      {r && (
        <>
          <p className="hint-line">{r.portfolio.count} risks · total exposure {r.portfolio.total_exposure} · retained {r.portfolio.retained}</p>
          <table className="loss-table">
            <thead>
              <tr><th scope="col">Cover</th><th scope="col" title="Σ median(0, E − A, L), 100% basis">Trapped</th>
                <th scope="col">Ceded</th><th scope="col">Risks in</th><th scope="col">Exhausted</th></tr>
            </thead>
            <tbody>
              {[...r.portfolio.layers].reverse().map((l) => (
                <tr key={l.layer}><th scope="row">{l.name}</th><td>{l.trapped}</td><td>{l.ceded}</td>
                  <td>{l.risks_reaching}</td><td>{l.risks_exhausting}</td></tr>
              ))}
            </tbody>
          </table>
          <details className="risk-list">
            <summary>Per risk</summary>
            <div className="table-scroll" tabIndex={0} role="region" aria-label="Trapped exposure per risk">
              <table className="loss-table">
                <thead><tr><th scope="col">Risk</th><th scope="col">Exposure</th>
                  {r.portfolio.layers.map((l) => <th key={l.layer} scope="col">{l.name}</th>)}<th scope="col">Retained</th></tr></thead>
                <tbody>
                  {r.portfolio.risks.map((risk) => (
                    <tr key={risk.id}><th scope="row">{risk.id}</th><td>{risk.exposure}</td>
                      {r.portfolio.layers.map((l) => <td key={l.layer}>{risk.layers[l.layer]}</td>)}<td>{risk.retained}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </>
  );
}

function Aggregate() {
  const input = useStore((s) => s.aggregate);
  const r = useStore((s) => s.aggregateResult);
  const p = useStore((s) => s.result?.programme);
  const setAgg = useStore((s) => s.setAggregate);
  const asRatio = input?.asRatio ?? true;
  const shown = input ? (asRatio ? round(input.amount * 100) : round(input.amount)) : "";
  const t = r?.aggregate;
  return (
    <>
      <p className="hint-line">A year&apos;s aggregate loss: ceded to the QS (capped by its agg limit), then the stop loss on the net loss ratio.</p>
      <div className="loss-controls">
        <label className="loss-amount">
          <span className="sr-only">Annual aggregate loss</span>
          <input inputMode="decimal" defaultValue={shown} key={`${asRatio}-${shown}`} placeholder={asRatio ? "e.g. 95" : "e.g. 110"}
            onBlur={(e) => {
              const n = Number(e.target.value);
              if (e.target.value === "") return void setAgg(null);
              if (Number.isFinite(n)) void setAgg({ amount: asRatio ? n / 100 : n, asRatio });
            }}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
        </label>
        <div className="segmented small" role="radiogroup" aria-label="Enter as">
          <button type="button" role="radio" aria-checked={asRatio} className={asRatio ? "on" : undefined}
            onClick={() => input && void setAgg({ amount: input.amount, asRatio: true })}>% of EPI</button>
          <button type="button" role="radio" aria-checked={!asRatio} className={!asRatio ? "on" : undefined}
            onClick={() => input && void setAgg({ amount: input.amount, asRatio: false })}>{p?.units ?? ""} amount</button>
        </div>
      </div>
      {!input && (
        <button type="button" className="link-button" onClick={() => void setAgg({ amount: 0.95, asRatio: true })}>
          Try an example: a 95% loss ratio year
        </button>
      )}
      {t && (
        <>
          <dl className="facts">
            <dt>Aggregate loss</dt><dd>{t.loss}</dd>
            <dt>Ceded to QS</dt><dd>{t.qs_ceded}</dd>
            <dt>Net of QS</dt><dd>{t.net_of_qs}</dd>
            <dt>Net loss ratio</dt><dd>{t.loss_ratio}</dd>
          </dl>
          {t.rows.length > 0 && (
            <table className="loss-table">
              <thead><tr><th scope="col">Stop loss</th><th scope="col">Takes</th><th scope="col">Share</th><th scope="col">Recovery</th></tr></thead>
              <tbody>
                {[...t.rows].reverse().map((row) => (
                  <tr key={row.layer} className={row.exhausted ? "exhausted" : undefined}>
                    <th scope="row">{row.name}{row.exhausted && <span className="tag">exhausted</span>}</th>
                    <td>{row.recovery_100}</td><td>{row.placed}</td><td>{row.recovery_placed}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {Object.keys(t.qs_terms).length > 0 && t.qs_terms.premium && (
            <dl className="facts">
              <dt>QS premium</dt><dd>{t.qs_terms.premium}</dd>
              <dt>QS loss ratio</dt><dd>{t.qs_terms.loss_ratio}</dd>
              <dt title="Sliding scale at this loss ratio, else the flat commission">Commission rate</dt><dd>{t.qs_terms.commission_rate}</dd>
              <dt>QS commission</dt><dd>{t.qs_terms.commission}</dd>
              <dt>Reinsurer mgmt expenses</dt><dd>{t.qs_terms.management_expenses}</dd>
              <dt>Reinsurer profit</dt><dd>{t.qs_terms.profit}</dd>
              <dt>Profit commission</dt><dd>{t.qs_terms.profit_commission}</dd>
            </dl>
          )}
          {t.no_claims_bonus.length > 0 && (
            <p className="hint-line">No claims bonus if a layer has no claims this year: {t.no_claims_bonus.map((n) => `${n.name} ${n.amount}`).join(" · ")}</p>
          )}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------- premium walk

export function WalkPanel() {
  const tower = useStore((s) => s.tower);
  const epi = useStore((s) => s.result?.programme.epi);
  const [walk, setWalk] = useState<WalkResult["walk"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    if (!tower || epi === null || epi === undefined) {
      Promise.resolve().then(() => live && setWalk(null));
      return;
    }
    call<WalkResult>("walk", { tower }).then((r) => {
      if (live) {
        setWalk(r.walk);
        setError(null);
      }
    }).catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [tower, epi]);

  return (
    <section className="panel" aria-labelledby="walk-h">
      <h2 id="walk-h">Premium walk</h2>
      {epi === null || epi === undefined ? (
        <p className="muted">Enter the gross EPI in Programme to see the walk from EPI to result and margin.</p>
      ) : walk ? (
        <>
          <Waterfall walk={walk} />
          <table className="walk-table">
            <tbody>
              <tr className="walk-total"><th scope="row">EPI (gross)</th><td>{walk.epi}</td></tr>
              {walk.steps.map((s) => (
                <tr key={s.key} title={s.formula}>
                  <th scope="row">
                    {s.value >= 0 ? "+ " : "− "}{s.label}{s.approx && <span className="approx" title="Approximate">*</span>}
                    {s.missing && <span className="missing" title={`Enter ${s.missing}`}>needs {s.missing}</span>}
                    {s.default && <span className="default-tag" title="Market default; set your own in Programme">default</span>}
                  </th>
                  <td className={s.value < 0 ? "neg" : s.value > 0 ? "pos" : undefined}>{s.amount.replace("-", "")}</td>
                </tr>
              ))}
              <tr className="walk-total"><th scope="row">Result</th><td>{walk.result}</td></tr>
              <tr><th scope="row">Margin</th><td>{walk.margin}</td></tr>
            </tbody>
          </table>
          <p className="hint-line">Without reinsurance {walk.result_without_reinsurance} · cost of reinsurance {walk.cost_of_reinsurance}. * approximate; hover a row for its formula.</p>
          <BeforeAfterTable ba={walk.before_after} />
        </>
      ) : error ? (
        <p className="field-error">{error}</p>
      ) : (
        <p className="muted">Calculating…</p>
      )}
    </section>
  );
}

/** Loss ratio, expense ratio, combined ratio and margin before and after reinsurance: what the programme does. */
function BeforeAfterTable({ ba }: { ba: WalkResult["walk"]["before_after"] }) {
  const rows: [keyof typeof ba.before, string, string][] = [
    ["premium", "Premium", "Gross EPI; after RI: less QS, XL and reinstatement premium"],
    ["loss_ratio", "Loss ratio", "Expected losses ÷ premium; after RI: net of EL saved by QS and XL"],
    ["expense_ratio", "Expense ratio", "Internal expenses ÷ premium; after RI: less commissions and NCB, plus brokerage and tax"],
    ["combined_ratio", "Combined ratio", "Loss ratio + expense ratio"],
    ["result", "Result", "Premium − losses − expenses"],
    ["margin", "Margin (on gross EPI)", "Result ÷ gross EPI: the same base before and after"],
    ["margin_on_premium", "Margin (on its premium)", "Result ÷ the premium in that column"],
  ];
  return (
    <table className="ba-table" aria-label="Before and after reinsurance">
      <thead><tr><th scope="col"></th><th scope="col">Before RI</th><th scope="col">After RI</th></tr></thead>
      <tbody>
        {rows.map(([k, label, tip]) => (
          <tr key={k} title={tip} className={k === "margin" ? "ba-key" : undefined}>
            <th scope="row">{label}</th><td>{ba.before[k]}</td><td>{ba.after[k]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Waterfall({ walk }: { walk: WalkResult["walk"] }) {
  const epi = Number(walk.epi.replace(/,/g, ""));
  let level = epi;
  const bars: { label: string; from: number; to: number; kind: "total" | "pos" | "neg" }[] = [{ label: "EPI", from: 0, to: epi, kind: "total" }];
  for (const s of walk.steps) {
    if (!s.value) continue;
    bars.push({ label: s.label, from: level, to: level + s.value, kind: s.value > 0 ? "pos" : "neg" });
    level += s.value;
  }
  bars.push({ label: "Result", from: 0, to: level, kind: "total" });
  const max = Math.max(...bars.map((b) => Math.max(b.from, b.to)), 1);
  const min = Math.min(0, ...bars.map((b) => Math.min(b.from, b.to)));
  const W = 300;
  const H = 120;
  const bw = W / bars.length;
  const y = (v: number) => H - ((v - min) / (max - min)) * H;
  return (
    <svg className="waterfall" viewBox={`0 0 ${W} ${H + 4}`} role="img" aria-label={`Premium walk from EPI ${walk.epi} to result ${walk.result}`}>
      {bars.map((b, i) => (
        <rect key={i} x={i * bw + 2} width={bw - 4} y={Math.min(y(b.from), y(b.to))} height={Math.max(1, Math.abs(y(b.from) - y(b.to)))}
          className={`wf-${b.kind}`}><title>{`${b.label}: ${Math.round((b.to - b.from) * 10) / 10}`}</title></rect>
      ))}
      <line x1={0} x2={W} y1={y(0)} y2={y(0)} className="wf-axis" />
    </svg>
  );
}
