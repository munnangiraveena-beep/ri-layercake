"use client";

import { useEffect, useRef } from "react";
import { money, pct } from "@/lib/draw";
import { fmtNum } from "@/lib/scale";
import { useStore } from "@/lib/store";
import type { LayerRow, Programme } from "@/lib/types";

const NO_FORMULAS: Record<string, string> = {};

const KIND_LABEL = { retention: "Retention", qs: "Quota share", xl: "Excess of loss", sl: "Stop loss" } as const;

/** A number input. `percent` shows and takes 20 for 0.2. Empty commits null. */
function Field({ label, value, onCommit, percent, placeholder, hint, inputRef, suffix }: {
  label: string; value: number | null | undefined; onCommit: (v: number | null) => void; percent?: boolean;
  placeholder?: string; hint?: string; inputRef?: React.Ref<HTMLInputElement>; suffix?: string;
}) {
  const shown = value === null || value === undefined ? "" : percent ? round(value * 100) : round(value);
  return (
    <label title={hint}>
      <span>{label}{suffix && <span className="unit"> {suffix}</span>}</span>
      <input ref={inputRef} inputMode="decimal" defaultValue={shown} placeholder={placeholder} key={`${label}-${shown}`}
        onBlur={(e) => {
          const raw = e.target.value.trim().replace(/[,%£$€]/g, "");
          if (raw === String(shown)) return;
          if (raw === "") return onCommit(null);
          const n = Number(raw);
          if (Number.isFinite(n)) onCommit(percent ? n / 100 : n);
        }}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
    </label>
  );
}

function round(v: number): string {
  return String(Math.round(v * 10000) / 10000);
}

/** A derived figure with its formula and the numbers that went into it. */
function Derived({ label, value, formula, working }: { label: string; value: string; formula: string; working?: string }) {
  return (
    <div className="derived">
      <div className="derived-head"><span>{label}</span><strong>{value || "—"}</strong></div>
      <div className="derived-formula">{formula}{working && value ? <span> = {working}</span> : null}</div>
    </div>
  );
}

export default function Inspector() {
  const layers = useStore((s) => s.result?.layers);
  const programme = useStore((s) => s.result?.programme);
  const formulas = useStore((s) => s.result?.formulas ?? NO_FORMULAS);
  const selected = useStore((s) => s.selected);
  const edit = useStore((s) => s.edit);
  const firstInput = useRef<HTMLInputElement>(null);
  const l = layers?.find((x) => x.id === selected);

  useEffect(() => {
    const focus = () => firstInput.current?.focus();
    window.addEventListener("ri:focus-inspector", focus);
    return () => window.removeEventListener("ri:focus-inspector", focus);
  }, []);

  if (!l || !programme || !layers) {
    return (
      <section className="panel" aria-labelledby="inspector-h">
        <h2 id="inspector-h">Layer</h2>
        <p className="muted">Select a layer on the canvas or in the grid. Drag edges to change limit and attachment;
          every derived figure shows its formula here.</p>
      </section>
    );
  }

  const m = (v: number | null | undefined) => money(programme.currency, programme.units, v);
  const set = (fields: Record<string, unknown>, what: string) => void edit({ type: "update", layer: l.id, fields }, `${l.display} ${what}`);
  const setTerms = (terms: Record<string, unknown>, what: string) => void edit({ type: "terms", layer: l.id, terms }, `${l.display} ${what}`);
  const idx = layers.indexOf(l);
  const above = layers[idx + 1];

  return (
    <section className="panel inspector" aria-labelledby="inspector-h">
      <h2 id="inspector-h">{l.display} <span className={`kind-badge kind-${l.kind}`}>{KIND_LABEL[l.kind]}</span></h2>
      <NameField l={l} set={set} inputRef={firstInput} />
      <div className="form-grid">
        {l.kind === "qs" && <QsFields l={l} p={programme} set={set} m={m} />}
        {l.kind === "xl" && <XlFields l={l} set={set} />}
        {l.kind === "sl" && <SlFields l={l} set={set} />}
        {l.kind === "retention" && <Field label="Retention" suffix={programme.units} value={l.limit} onCommit={(v) => v !== null && set({ limit: v }, "set")} />}
      </div>

      {l.kind !== "retention" && (
        <div className="derived-list">
          <Derived label="Share with reinsurers" value={pct(l.share)} formula={formulas.share ?? "Share = Order % × Placed %"}
            working={`${pct(l.order)} × ${pct(l.placed)}`} />
          {l.kind === "qs" ? (
            <Derived label="QS premium" value={m(l.derived.premium)} formula={formulas.qs_premium}
              working={programme.epi !== null && l.cession !== null ? `${pct(l.cession)} × ${m(programme.epi)}` : undefined} />
          ) : (
            <>
              <Derived label="Premium (RTE)" value={m(l.derived.premium)} formula={formulas.premium}
                working={programme.epi !== null && l.derived.adj_rate !== null ? `${m(programme.epi)} × ${pct(l.derived.adj_rate)}` : undefined} />
              <Derived label="ROL" value={pct(l.derived.rol)} formula={formulas.rol}
                working={l.derived.premium !== null && l.limit_amount !== null ? `${m(l.derived.premium)} ÷ ${m(l.limit_amount)}` : undefined} />
              <Derived label="Adj. rate" value={pct(l.derived.adj_rate)} formula={formulas.adj_rate}
                working={l.derived.rol !== null && l.limit_amount !== null && programme.epi ? `${pct(l.derived.rol)} × ${m(l.limit_amount)} ÷ ${m(programme.epi)}` : undefined} />
              {l.derived.payback !== null && (
                <Derived label="Payback" value={`${fmtNum(l.derived.payback)} years`} formula={formulas.payback} />
              )}
            </>
          )}
          <Derived label="Agg limit" value={l.derived.agg_unlimited ? "Unlimited" : m(l.derived.agg_limit)}
            formula={l.kind === "xl" ? formulas.agg_limit : l.kind === "qs" ? "As entered; QS aggregate limits are usually large" : "The stop loss limit, annual aggregate"}
            working={l.kind === "xl" && !l.derived.agg_unlimited ? `${m(l.limit)} × (1 + ${reinstCount(l)})` : undefined} />
          {l.kind === "sl" && l.amounts && <Derived label="In amounts" value={l.amounts} formula={formulas.sl_amounts} />}
        </div>
      )}

      {l.kind === "qs" && <QsTerms l={l} setTerms={setTerms} formulas={formulas} m={m} />}
      {l.kind === "xl" && (
        <fieldset className="terms">
          <legend>Terms</legend>
          <div className="form-grid">
            <Field label="No claims bonus" suffix="%" percent value={num(l.terms.no_claims_bonus)}
              hint={formulas.no_claims_bonus} onCommit={(v) => setTerms({ no_claims_bonus: v === null ? null : String(v) }, "no claims bonus set")} />
            <Field label="Layer EL" suffix={programme.units} value={num(l.terms.expected_loss)}
              hint="The layer's expected loss, 100% basis: used for EL saved and reinstatement premium in the premium walk"
              onCommit={(v) => setTerms({ expected_loss: v }, "expected loss set")} />
          </div>
          {l.derived.no_claims_bonus !== null && (
            <Derived label="NCB if no claims" value={m(l.derived.no_claims_bonus)} formula={formulas.no_claims_bonus} />
          )}
        </fieldset>
      )}
      {l.kind === "sl" && (
        <fieldset className="terms">
          <legend>Terms</legend>
          <div className="form-grid">
            <Field label="Layer EL" suffix={programme.units} value={num(l.terms.expected_loss)}
              onCommit={(v) => setTerms({ expected_loss: v }, "expected loss set")} />
          </div>
        </fieldset>
      )}

      <div className="button-row">
        {l.kind === "xl" && (
          <button type="button" onClick={() => void edit({ type: "split", layer: l.id, at: l.attachment + l.limit / 2 }, `${l.display} split`)}>Split in half</button>
        )}
        {above && l.kind === "xl" && above.kind === "xl" && (
          <button type="button" onClick={() => void edit({ type: "merge", a: l.id, b: above.id }, `${l.display} merged`)}>Merge with above</button>
        )}
        <button type="button" className="danger" onClick={() => void edit({ type: "remove", layer: l.id }, `${l.display} deleted`)}>Delete</button>
      </div>
    </section>
  );
}

function num(v: unknown): number | null {
  if (v === undefined || v === null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function reinstCount(l: LayerRow): string {
  const m = l.reinstatements?.match(/^(\d+)/);
  return m ? m[1] : "0";
}

function NameField({ l, set, inputRef }: {
  l: LayerRow; set: (f: Record<string, unknown>, w: string) => void; inputRef: React.Ref<HTMLInputElement>;
}) {
  return (
    <label className="name-field">
      <span>Name</span>
      <input ref={inputRef} defaultValue={l.name ?? ""} key={`name-${l.id}-${l.name}`} placeholder={l.display}
        onBlur={(e) => e.target.value !== (l.name ?? "") && set({ name: e.target.value || null }, "renamed")}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
    </label>
  );
}

/** Pricing by any one of premium, ROL or adjusted rate; entering one clears the other two. */
function Pricing({ l, set }: { l: LayerRow; set: (f: Record<string, unknown>, w: string) => void }) {
  const by = l.priced_by;
  return (
    <>
      <Field label="Premium (RTE)" value={l.premium} placeholder={by && by !== "premium" ? round(l.derived.premium ?? 0) : ""}
        hint="Enter premium, ROL or adjusted rate; the other two are derived"
        onCommit={(v) => set({ premium: v, rol: null, adj_rate: null }, "premium set")} />
      <Field label="ROL" suffix="%" percent value={l.rol} placeholder={by && by !== "rol" && l.derived.rol !== null ? round(l.derived.rol * 100) : ""}
        onCommit={(v) => set({ rol: v, premium: null, adj_rate: null }, "rate on line set")} />
      <Field label="Adj. rate" suffix="% EPI" percent value={l.adj_rate}
        placeholder={by && by !== "adj_rate" && l.derived.adj_rate !== null ? round(l.derived.adj_rate * 100) : ""}
        onCommit={(v) => set({ adj_rate: v, premium: null, rol: null }, "adjusted rate set")} />
    </>
  );
}

function XlFields({ l, set }: { l: LayerRow; set: (f: Record<string, unknown>, w: string) => void }) {
  return (
    <>
      <Field label="Limit" value={l.limit} onCommit={(v) => v !== null && set({ limit: v }, "limit set")} />
      <Field label="Attachment" value={l.attachment} onCommit={(v) => v !== null && set({ attachment: v }, "attachment set")} />
      <Field label="Order" suffix="%" percent value={l.order} hint="Share of the 100% layer put to market"
        onCommit={(v) => set({ order: v ?? 1 }, "order set")} />
      <Field label="Placed" suffix="%" percent value={l.placed} hint="Share of the order that is placed"
        onCommit={(v) => set({ placed: v ?? 1 }, "placed set")} />
      <Pricing l={l} set={set} />
      <label>
        <span>Reinstatements</span>
        <input defaultValue={l.reinstatements ?? ""} key={`ri-${l.id}-${l.reinstatements}`} placeholder="1 @ 100%"
          onBlur={(e) => e.target.value !== (l.reinstatements ?? "") && set({ reinstatements: e.target.value }, "reinstatements set")}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
      </label>
    </>
  );
}

function SlFields({ l, set }: { l: LayerRow; set: (f: Record<string, unknown>, w: string) => void }) {
  return (
    <>
      <Field label="Limit" suffix="% EPI" percent value={l.limit} onCommit={(v) => v !== null && set({ limit: v }, "limit set")} />
      <Field label="Attachment" suffix="% EPI" percent value={l.attachment}
        hint="Loss ratio at which the stop loss attaches" onCommit={(v) => v !== null && set({ attachment: v }, "attachment set")} />
      <Field label="Order" suffix="%" percent value={l.order} onCommit={(v) => set({ order: v ?? 1 }, "order set")} />
      <Field label="Placed" suffix="%" percent value={l.placed} onCommit={(v) => set({ placed: v ?? 1 }, "placed set")} />
      <Pricing l={l} set={set} />
    </>
  );
}

function QsFields({ l, p, set, m }: { l: LayerRow; p: Programme; set: (f: Record<string, unknown>, w: string) => void; m: (v: number | null) => string }) {
  return (
    <>
      <Field label="Cession" suffix="%" percent value={l.cession} hint="Share of each risk ceded to the quota share"
        onCommit={(v) => v !== null && set({ cession: v }, "cession set")} />
      <label title="Usually the CRM team's limit for your largest counterparty">
        <span>Limit (per risk)</span>
        <input inputMode="decimal" defaultValue={l.limit} key={`ql-${l.limit}`}
          onBlur={(e) => Number(e.target.value) !== l.limit && Number.isFinite(Number(e.target.value)) && set({ limit: Number(e.target.value) }, "limit set")}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
        {p.counterparty_limit !== null && p.counterparty_limit !== l.limit && (
          <button type="button" className="link-button" onClick={() => set({ limit: p.counterparty_limit }, "limit set to the CRM limit")}>
            Use CRM limit {m(p.counterparty_limit)}
          </button>
        )}
      </label>
      <Field label="Agg limit" value={l.agg_limit} hint="QS aggregate limits are usually large"
        onCommit={(v) => set({ agg_limit: v }, "aggregate limit set")} />
      <Field label="Order" suffix="%" percent value={l.order} onCommit={(v) => set({ order: v ?? 1 }, "order set")} />
      <Field label="Placed" suffix="%" percent value={l.placed} onCommit={(v) => set({ placed: v ?? 1 }, "placed set")} />
    </>
  );
}

function QsTerms({ l, setTerms, formulas, m }: {
  l: LayerRow; setTerms: (t: Record<string, unknown>, w: string) => void; formulas: Record<string, string>; m: (v: number | null) => string;
}) {
  const ss = l.terms.sliding_scale;
  const setSs = (key: "min" | "max" | "lr_low" | "lr_high", v: number | null) => {
    const next = { min: ss?.min ?? "", max: ss?.max ?? "", lr_low: ss?.lr_low ?? "", lr_high: ss?.lr_high ?? "", [key]: v === null ? "" : String(v) };
    const complete = Object.values(next).every((x) => x !== "");
    const cleared = Object.values(next).every((x) => x === "");
    setTerms({ sliding_scale: complete ? next : cleared ? null : next }, "sliding scale set");
  };
  return (
    <fieldset className="terms">
      <legend>QS terms</legend>
      <div className="form-grid">
        <Field label="QS commission" suffix="%" percent value={num(l.terms.commission)} hint={formulas.qs_commission}
          onCommit={(v) => setTerms({ commission: v === null ? null : String(v) }, "commission set")} />
        <Field label="Reinsurer mgmt exp." suffix="%" percent value={num(l.terms.management_expenses)} hint={formulas.rme}
          onCommit={(v) => setTerms({ management_expenses: v === null ? null : String(v) }, "management expenses set")} />
        <Field label="Profit commission" suffix="%" percent value={num(l.terms.profit_commission)} hint={formulas.profit_commission}
          onCommit={(v) => setTerms({ profit_commission: v === null ? null : String(v) }, "profit commission set")} />
      </div>
      <p className="terms-sub" title={formulas.sliding_scale}>Sliding scale commission <span className="muted">(replaces the flat commission)</span></p>
      <div className="form-grid four">
        <Field label="Max comm." suffix="%" percent value={num(ss?.max)} onCommit={(v) => setSs("max", v)} />
        <Field label="at LR ≤" suffix="%" percent value={num(ss?.lr_low)} onCommit={(v) => setSs("lr_low", v)} />
        <Field label="Min comm." suffix="%" percent value={num(ss?.min)} onCommit={(v) => setSs("min", v)} />
        <Field label="at LR ≥" suffix="%" percent value={num(ss?.lr_high)} onCommit={(v) => setSs("lr_high", v)} />
      </div>
      <div className="derived-list">
        <Derived label="Commission rate" value={pct(l.derived.commission_rate)}
          formula={ss ? "Sliding scale: shown at its maximum; see Annual aggregate for a loss ratio" : formulas.qs_commission} />
        {l.derived.premium !== null && l.derived.commission_rate !== null && (
          <Derived label="QS commission" value={m(l.derived.premium * l.derived.commission_rate)} formula={formulas.qs_commission}
            working={`${pct(l.derived.commission_rate)} × ${m(l.derived.premium)}`} />
        )}
        <Derived label="Profit commission" value="" formula={formulas.profit_commission} />
      </div>
    </fieldset>
  );
}
