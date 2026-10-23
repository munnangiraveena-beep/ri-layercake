"use client";

import { useRef, useState } from "react";
import { useStore } from "@/lib/store";

const EMPTY: never[] = [];
import type { LayerRow } from "@/lib/types";

const FIELD_LABELS: Record<string, string> = {
  "": "Ignore", limit: "Limit", attachment: "Attachment", placed: "Placed %", premium: "Premium", rol: "Rate on line",
  name: "Name", combined: "Shorthand (50 xs 10)", written: "Our line", reinstatements: "Reinstatements",
};

/** Shorthand bar: type 10 ret, 40 xs 10, 50 xs 50 @ 75%. Unreadable fragments are underlined in place. */
export function ShorthandBar() {
  const text = useStore((s) => s.result?.text ?? "");
  const draft = useStore((s) => s.textDraft);
  const warnings = useStore((s) => s.result?.warnings ?? EMPTY);
  const parseText = useStore((s) => s.parseText);
  const [value, setValue] = useState(text);
  const [focused, setFocused] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Re-print from the tower after any edit elsewhere, unless the user is typing here.
  const [printed, setPrinted] = useState(text);
  if (text !== printed && !focused && draft === null) {
    setPrinted(text);
    setValue(text);
  }

  const spans = warnings.filter((w) => w.code === "parse" && w.span).map((w) => w.span!) as [number, number][];

  function onChange(v: string) {
    setValue(v);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void parseText(v), 150);
  }

  return (
    <div className="shorthand">
      <label htmlFor="shorthand" className="panel-label">
        Shorthand <span className="hint" title="Examples: 10 ret · 40 xs 10 · 50 xs 50 @ 75% · Cat 3: 100 xs 100, 1 @ 100%, prem 4.2">?</span>
      </label>
      <div className="shorthand-wrap">
        <div className="shorthand-mirror" aria-hidden="true">{highlight(value, focused || draft !== null ? spans : spans)}</div>
        <textarea
          id="shorthand"
          value={value}
          rows={3}
          spellCheck={false}
          placeholder="10 ret, 40 xs 10, 50 xs 50 @ 75%"
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onPaste={(e) => e.stopPropagation()}
          aria-describedby={spans.length ? "shorthand-errors" : undefined}
        />
      </div>
      {spans.length > 0 && (
        <p id="shorthand-errors" className="field-error">
          {warnings.filter((w) => w.code === "parse").map((w) => w.message).join(" · ")}
        </p>
      )}
    </div>
  );
}

function highlight(text: string, spans: [number, number][]) {
  if (!spans.length) return text + "\n";
  const out: React.ReactNode[] = [];
  let at = 0;
  for (const [s, e] of [...spans].sort((a, b) => a[0] - b[0])) {
    if (s < at || s > text.length) continue;
    out.push(text.slice(at, s));
    out.push(<mark key={s}>{text.slice(s, e)}</mark>);
    at = e;
  }
  out.push(text.slice(at) + "\n");
  return out;
}

const KIND_SHORT = { retention: "Ret", qs: "QS", xl: "XL", sl: "SL" } as const;

/** Editable layer grid. Pasting a block anywhere on the page lands here. */
export function LayerGrid() {
  const layers = useStore((s) => s.result?.layers ?? EMPTY);
  const programme = useStore((s) => s.result?.programme);
  const selected = useStore((s) => s.selected);
  const hovered = useStore((s) => s.hovered);
  const tower = useStore((s) => s.tower);
  const { edit, select, hover } = useStore.getState();
  const [menu, setMenu] = useState(false);
  const units = `${tower?.currency === "GBP" ? "£" : tower?.currency === "USD" ? "$" : tower?.currency === "EUR" ? "€" : ""}${tower?.units ?? ""}`;

  function commit(l: LayerRow, field: string, raw: string) {
    const v = raw.trim();
    const num = Number(v.replace(/[,%£$€]/g, ""));
    let fields: Record<string, unknown> | null = null;
    const isSl = l.kind === "sl";
    if (field === "name") fields = { name: v || null };
    else if (field === "share") {
      if (!Number.isFinite(num)) return;
      fields = l.kind === "qs" ? { cession: num / 100 } : { placed: num / 100 };
    } else if (field === "premium") fields = v === "" ? { premium: null } : Number.isFinite(num) ? { premium: num, rol: null, adj_rate: null } : null;
    else if (Number.isFinite(num) && v !== "") {
      const value = isSl ? num / 100 : num;
      fields = field === "attachment" ? { attachment: value } : { limit: value };
    }
    if (fields) void edit({ type: "update", layer: l.id, fields }, `${l.display} ${field} updated`);
  }

  // QS first, then the XL tower top down, then stop loss, as the grid reads best
  const rows = [
    ...layers.filter((l) => l.kind === "sl").reverse(),
    ...layers.filter((l) => l.kind === "xl" || l.kind === "retention").reverse(),
    ...layers.filter((l) => l.kind === "qs"),
  ];
  const xls = layers.filter((l) => l.kind === "xl");
  const top = xls.reduce((m, l) => Math.max(m, l.exhaust), 0);
  const ret = layers.find((l) => l.kind === "retention");
  const qs = layers.find((l) => l.kind === "qs");
  const sls = layers.filter((l) => l.kind === "sl");
  const lastLimit = xls.at(-1)?.limit ?? 10;

  function add(kind: "qs" | "xl" | "sl") {
    setMenu(false);
    if (kind === "xl") void edit({ type: "add_xl", limit: lastLimit, attachment: top || (ret?.exhaust ?? 0) }, "Excess of loss layer added");
    if (kind === "qs") void edit({ type: "add_qs", cession: 0.2, limit: programme?.counterparty_limit ?? (top || 10) }, "Quota share added");
    if (kind === "sl") {
      const lastSl = sls.at(-1);
      void edit({ type: "add_sl", limit: 0.2, attachment: lastSl ? lastSl.exhaust : 0.8 }, "Stop loss added");
    }
  }

  return (
    <div className="grid-wrap">
      <MappingChips />
      <table className="layer-grid" aria-label="Layers">
        <thead>
          <tr>
            <th scope="col"><span className="sr-only">Type</span></th>
            <th scope="col">Layer</th>
            <th scope="col" title="Layer limit, 100% basis. Stop loss: % of EPI">Limit {units}</th>
            <th scope="col" title="Attachment, 100% basis. Stop loss: % of EPI">Attach</th>
            <th scope="col" title="QS: cession %. Others: placed %">Share %</th>
            <th scope="col" title="Premium (RTE), 100% basis">Prem {units}</th>
            <th scope="col"><span className="sr-only">Delete</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => {
            const pctCell = l.kind === "sl";
            return (
              <tr key={`${l.id}-${l.limit}-${l.attachment}-${l.placed}-${l.cession}-${l.premium}-${l.name}`}
                className={l.id === selected ? "is-selected" : l.id === hovered ? "is-hovered" : undefined}
                onMouseEnter={() => hover(l.id)} onMouseLeave={() => hover(null)} onFocus={() => select(l.id)}>
                <td><span className={`kind-badge kind-${l.kind}`}>{KIND_SHORT[l.kind]}</span></td>
                <td><Cell label={`${l.display} name`} value={l.name ?? ""} placeholder={l.display} onCommit={(v) => commit(l, "name", v)} /></td>
                <td><Cell label={`${l.display} limit${pctCell ? " percent of EPI" : ""}`} value={pctCell ? num(l.limit * 100) + "%" : num(l.limit)} numeric onCommit={(v) => commit(l, "limit", v)} /></td>
                <td>{l.kind === "xl" || l.kind === "sl" ? (
                  <Cell label={`${l.display} attachment`} value={pctCell ? num(l.attachment * 100) + "%" : num(l.attachment)} numeric onCommit={(v) => commit(l, "attachment", v)} />
                ) : <span className="muted">—</span>}</td>
                <td>{l.kind === "retention" ? <span className="muted">—</span> : (
                  <Cell label={`${l.display} ${l.kind === "qs" ? "cession" : "placed"} percent`}
                    value={num((l.kind === "qs" ? l.cession ?? 0 : l.placed) * 100)} numeric onCommit={(v) => commit(l, "share", v)} />
                )}</td>
                <td>{l.kind === "xl" || l.kind === "sl" ? (
                  <Cell label={`${l.display} premium`} value={l.premium === null ? "" : num(l.premium)}
                    placeholder={l.derived.premium !== null ? num(l.derived.premium) : ""} numeric onCommit={(v) => commit(l, "premium", v)} />
                ) : l.kind === "qs" ? <span className="cell-static numeric" title="QS premium = Cession × EPI">{l.derived.premium !== null ? num(l.derived.premium) : "—"}</span> : null}</td>
                <td>
                  <button type="button" className="icon-button" aria-label={`Delete ${l.display}`} title="Delete layer"
                    onClick={() => void edit({ type: "remove", layer: l.id }, `${l.display} deleted`)}>×</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="grid-actions">
        <div className="add-menu">
          <button type="button" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>+ Add layer ▾</button>
          {menu && (
            <ul role="menu" className="menu">
              <li role="none"><button type="button" role="menuitem" disabled={!!qs} onClick={() => add("qs")}
                title={qs ? "A programme has one quota share" : "Proportional: a cession of every risk, up to its limit"}>
                <span className="kind-badge kind-qs">QS</span> Quota share</button></li>
              <li role="none"><button type="button" role="menuitem" onClick={() => add("xl")}>
                <span className="kind-badge kind-xl">XL</span> Excess of loss layer</button></li>
              <li role="none"><button type="button" role="menuitem" onClick={() => add("sl")}
                title="Annual aggregate cover, set as % of EPI">
                <span className="kind-badge kind-sl">SL</span> Stop loss</button></li>
            </ul>
          )}
        </div>
        {!ret && (
          <button type="button" onClick={() => void edit({ type: "add_retention", amount: xls[0]?.attachment || 10 }, "Retention added")}>
            + Add retention
          </button>
        )}
      </div>
      <p className="hint-line">Paste an Excel block anywhere on the page to replace the layers. Shorthand: qs 20% limit 50 · 5 xs 5 · sl 20% xs 80% · epi 120</p>
    </div>
  );
}

function num(v: number): string {
  const r = Math.round(v * 1000) / 1000;
  return String(r);
}

function Cell({ value, onCommit, label, numeric, placeholder }: {
  value: string; onCommit: (v: string) => void; label: string; numeric?: boolean; placeholder?: string;
}) {
  return (
    <input
      className={numeric ? "cell numeric" : "cell"}
      defaultValue={value}
      aria-label={label}
      placeholder={placeholder}
      inputMode={numeric ? "decimal" : undefined}
      onBlur={(e) => e.target.value !== value && onCommit(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          (e.target as HTMLInputElement).value = value;
          (e.target as HTMLInputElement).blur();
        }
      }}
    />
  );
}

/** After a table paste: the detected column mapping as dropdown chips, so a wrong guess is one click to fix. */
export function MappingChips() {
  const paste = useStore((s) => s.paste);
  const pasteTable = useStore((s) => s.pasteTable);
  if (!paste) return null;
  const { mapping } = paste;
  return (
    <div className="mapping" role="group" aria-label="Detected columns">
      <span className="panel-label">Columns</span>
      {Array.from({ length: mapping.width }, (_, j) => (
        <label key={j} className="chip">
          <span className="chip-head">{mapping.headers[j] || `Column ${j + 1}`}</span>
          <select
            value={mapping.columns[String(j)] ?? ""}
            onChange={(e) => {
              const columns = { ...mapping.columns, [String(j)]: e.target.value };
              if (!e.target.value) delete columns[String(j)];
              void pasteTable(paste.text, { ...mapping, columns });
            }}
          >
            {["", ...mapping.fields].map((f) => <option key={f} value={f}>{FIELD_LABELS[f] ?? f}</option>)}
          </select>
        </label>
      ))}
      <button type="button" className="link-button" onClick={() => useStore.setState({ paste: null })}>Done</button>
    </div>
  );
}
