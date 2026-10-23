"use client";

import { useEffect, useRef, useState } from "react";
import { call } from "@/lib/engine";
import { money, pct } from "@/lib/draw";
import { useStore } from "@/lib/store";

const EMPTY: never[] = [];
import type { Diagnostic, View } from "@/lib/types";

// ---------------------------------------------------------------------- toolbar

export function Toolbar() {
  const view = useStore((s) => s.view);
  const canUndo = useStore((s) => s.past.length > 0);
  const canRedo = useStore((s) => s.future.length > 0);
  const arrangement = useStore((s) => s.result?.programme.arrangement ?? "stacked");
  const hasQs = useStore((s) => s.result?.layers.some((l) => l.kind === "qs") ?? false);
  const { setView, undo, redo, edit } = useStore.getState();

  return (
    <div className="toolbar" role="toolbar" aria-label="View controls">
      <Segmented label="Scale" value={view.scale} options={[["schematic", "Schematic"], ["linear", "Linear"], ["log", "Log"]]}
        onChange={(scale) => void setView({ scale: scale as View["scale"] })}
        tip="Schematic: equal blocks, like most broker slides. Linear: heights proportional to limit. Log: thin layers stay visible." />
      <Select label="Palette" value={view.palette} options={[["ocean", "Ocean"], ["slate", "Slate"], ["ember", "Ember"]]}
        onChange={(palette) => void setView({ palette: palette as View["palette"] })}
        tip="Palettes map onto theme colour slots, so exports still take on your deck's theme." />
      <Select label="Labels" value={view.labels} options={[["auto", "Auto"], ["inside", "Inside"], ["side", "Beside"]]}
        onChange={(labels) => void setView({ labels: labels as View["labels"] })} tip="Auto moves a label beside a block that is too thin." />
      <Select label="Table" value={view.table} options={[["below", "Below"], ["right", "Right"], ["none", "None"]]}
        onChange={(table) => void setView({ table: table as View["table"] })} tip="Where the layer table sits on the slide." />
      <Select label="Frame" value={view.frame} options={[["slide_16x9", "16:9"], ["square", "Square"], ["tall", "Tall"]]}
        onChange={(frame) => void setView({ frame: frame as View["frame"] })} tip="Slide shape for the export." />
      <Toggle label="Retention" checked={view.show_retention} onChange={(v) => void setView({ show_retention: v })} tip="Show the cedant's retention band." />
      <Toggle label="Unplaced" checked={view.show_unplaced} onChange={(v) => void setView({ show_unplaced: v })} tip="Draw unplaced shares hatched." />
      <Toggle label="Axis" checked={view.show_axis ?? view.scale !== "schematic"} onChange={(v) => void setView({ show_axis: v })} tip="Show the value axis." />
      <Toggle label={hasQs ? "Stacked" : "Stacked (with a QS)"} checked={arrangement === "stacked"}
        onChange={(v) => void edit({ type: "programme", fields: { arrangement: v ? "stacked" : "side_by_side" } }, v ? "QS and XL stacked" : "QS and XL side by side")}
        tip="Stacked: the QS cedes first and the net passes through the XL layers. Untick for side by side: XL attachment and limit × (1 − cession), on the retained share." />
      <span className="toolbar-spacer" />
      <button type="button" onClick={() => void undo()} disabled={!canUndo} title="Undo (Ctrl+Z)" aria-label="Undo">↶</button>
      <button type="button" onClick={() => void redo()} disabled={!canRedo} title="Redo (Ctrl+Shift+Z)" aria-label="Redo">↷</button>
    </div>
  );
}

function Segmented({ label, value, options, onChange, tip }: {
  label: string; value: string; options: [string, string][]; onChange: (v: string) => void; tip: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label} title={tip}>
      {options.map(([v, text]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? "on" : undefined}
          onClick={() => onChange(v)}>{text}</button>
      ))}
    </div>
  );
}

function Select({ label, value, options, onChange, tip }: {
  label: string; value: string; options: [string, string][]; onChange: (v: string) => void; tip: string;
}) {
  return (
    <label className="tool-select" title={tip}>
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
      </select>
    </label>
  );
}

function Toggle({ label, checked, onChange, tip }: { label: string; checked: boolean; onChange: (v: boolean) => void; tip: string }) {
  return (
    <label className="tool-toggle" title={tip}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

// ---------------------------------------------------------------------- gallery, code, clear

export function ProgrammeMenu() {
  const [gallery, setGallery] = useState<{ name: string; title: string; subtitle: string }[]>([]);
  const [showCode, setShowCode] = useState(false);
  const { loadGallery, edit, clearData } = useStore.getState();

  useEffect(() => {
    call<{ gallery: typeof gallery }>("gallery").then((r) => setGallery(r.gallery)).catch(() => undefined);
  }, []);

  return (
    <div className="programme-menu">
      <label className="tool-select">
        <span>Gallery</span>
        <select value="" aria-label="Open a gallery tower" onChange={(e) => e.target.value && void loadGallery(e.target.value)}>
          <option value="">Open a starter tower…</option>
          {gallery.map((g) => <option key={g.name} value={g.name}>{g.title}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => setShowCode(true)}>Show code</button>
      <button type="button" onClick={() => {
        if (window.confirm("Clear the tower and start empty? You can undo this.")) {
          void edit({ type: "clear" }, "Tower cleared");
          useStore.setState({ paste: null });
        }
      }}>Clear</button>
      <button type="button" className="link-button" title="Remove the autosaved tower from this browser" onClick={() => {
        clearData();
        useStore.getState().announce("Saved data cleared from this browser");
      }}>Clear data</button>
      {showCode && <CodePanel onClose={() => setShowCode(false)} />}
    </div>
  );
}

function CodePanel({ onClose }: { onClose: () => void }) {
  const tower = useStore((s) => s.tower);
  const view = useStore((s) => s.view);
  const [code, setCode] = useState("");
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    ref.current?.showModal();
    call<{ code: string }>("code", { tower, view }).then((r) => setCode(r.code)).catch((e) => setCode(`# ${e.message}`));
  }, [tower, view]);

  return (
    <dialog ref={ref} className="code-panel" onClose={onClose} aria-labelledby="code-title">
      <h2 id="code-title">Python that rebuilds this tower</h2>
      <pre><code>{code}</code></pre>
      <div className="dialog-actions">
        <button type="button" onClick={() => void navigator.clipboard.writeText(code)}>Copy</button>
        <a className="button" href={`/how-to-use/#code=${encodeURIComponent(code)}`}>Open in How to use</a>
        <button type="button" onClick={() => ref.current?.close()}>Close</button>
      </div>
    </dialog>
  );
}

// ---------------------------------------------------------------------- warnings

export function Warnings() {
  const warnings = useStore((s) => s.result?.warnings ?? EMPTY);
  const { edit, setView, select } = useStore.getState();
  const shown = warnings.filter((w) => w.code !== "parse");
  function apply(w: Diagnostic, i: number) {
    const fix = w.fixes[i];
    if (fix.op === "view") void setView(fix.fields as Partial<View>);
    else void edit({ type: "apply_fix", fix }, `${fix.label}: done`);
  }
  return (
    <section className="panel" aria-labelledby="warnings-h">
      <h2 id="warnings-h">Checks {shown.length > 0 && <span className="count">{shown.length}</span>}</h2>
      {shown.length === 0 ? (
        <p className="muted">No gaps, overlaps or share issues.</p>
      ) : (
        <ul className="warnings">
          {shown.map((w, n) => (
            <li key={`${w.code}-${w.key ?? n}`} className={`sev-${w.severity}`} onMouseEnter={() => w.layers[0] && select(w.layers[0])}>
              <span className="sev" aria-label={w.severity}>{w.severity === "error" ? "!" : w.severity === "warning" ? "▲" : "i"}</span>
              <span>{w.message}</span>
              {w.fixes.length > 0 && (
                <span className="fixes">
                  {w.fixes.map((f, i) => <button key={f.label} type="button" onClick={() => apply(w, i)}>{f.label}</button>)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------- export

export function ExportPanel() {
  const tower = useStore((s) => s.tower);
  const view = useStore((s) => s.view);
  const result = useStore((s) => s.result);
  const announce = useStore((s) => s.announce);
  const [template, setTemplate] = useState<{ name: string; base64: string } | null>(null);
  const [tableSlide, setTableSlide] = useState(false);
  const [transparent, setTransparent] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const blocked = !result || result.blocking || !tower?.layers.length;
  const base = (tower?.title || "tower").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-").toLowerCase() || "tower";

  async function run(kind: string, fn: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      announce(`${kind} ready`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const pptx = () => run("PowerPoint", async () => {
    const r = await call<{ base64: string; mime: string }>("export", {
      tower, view, format: "pptx", template: template?.base64, table_slide: tableSlide,
    });
    download(`${base}.pptx`, b64ToBlob(r.base64, r.mime));
  });
  const svg = () => run("SVG", async () => {
    const r = await call<{ text: string }>("export", { tower, view, format: "svg", transparent });
    download(`${base}.svg`, new Blob([r.text], { type: "image/svg+xml" }));
  });
  const png = (scale: number) => run("PNG", async () => {
    const r = await call<{ text: string }>("export", { tower, view, format: "svg", transparent });
    download(`${base}@${scale}x.png`, await rasterise(r.text, scale));
  });

  return (
    <section className="panel" aria-labelledby="export-h">
      <h2 id="export-h">Export</h2>
      {result?.blocking && <p className="field-error">Fix the errors above before exporting.</p>}
      <button type="button" className="primary wide" disabled={blocked || !!busy} onClick={() => void pptx()}>
        {busy === "PowerPoint" ? "Building slide…" : "Download PowerPoint"}
      </button>
      <label className="file-pick" title="Your .pptx or .potx: the slide uses its theme, fonts and title layout. The file stays in your browser.">
        <span>{template ? `Template: ${template.name}` : "Use my template (.pptx, .potx)"}</span>
        <input type="file" accept=".pptx,.potx" onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          if (f.size > 10 * 1024 * 1024) {
            setError("Templates over 10 MB are not supported");
            return;
          }
          setTemplate({ name: f.name, base64: await fileToBase64(f) });
        }} />
      </label>
      {template && <button type="button" className="link-button" onClick={() => setTemplate(null)}>Use the built-in template</button>}
      <label className="tool-toggle"><input type="checkbox" checked={tableSlide} onChange={(e) => setTableSlide(e.target.checked)} />
        <span>Add a full-size table slide</span></label>
      <div className="button-row">
        <button type="button" disabled={blocked || !!busy} onClick={() => void svg()}>SVG</button>
        <button type="button" disabled={blocked || !!busy} onClick={() => void png(2)}>PNG 2x</button>
        <button type="button" disabled={blocked || !!busy} onClick={() => void png(4)}>PNG 4x</button>
      </div>
      <label className="tool-toggle"><input type="checkbox" checked={transparent} onChange={(e) => setTransparent(e.target.checked)} />
        <span>Transparent background</span></label>
      <div className="button-row">
        <button type="button" onClick={() => { void navigator.clipboard.writeText(result?.text ?? ""); announce("Shorthand copied"); }}>Copy shorthand</button>
        <button type="button" onClick={() => { void navigator.clipboard.writeText(JSON.stringify(tower, null, 2)); announce("JSON copied"); }}>Copy JSON</button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
    </section>
  );
}

function download(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function b64ToBlob(b64: string, mime: string): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

async function fileToBase64(f: File): Promise<string> {
  const bytes = new Uint8Array(await f.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

/** PNG export: rasterise the engine's SVG on a canvas, so Python needs no imaging library. */
async function rasterise(svg: string, scale: number): Promise<Blob> {
  const m = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  const w = Number(m?.[1] ?? 1280);
  const h = Number(m?.[2] ?? 720);
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    await img.decode();
    const canvas = document.createElement("canvas");
    canvas.width = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("PNG failed"))), "image/png"));
  } finally {
    URL.revokeObjectURL(url);
  }
}

// ---------------------------------------------------------------------- layer table

export function LayerTable() {
  const table = useStore((s) => s.result?.scene.table);
  const hovered = useStore((s) => s.hovered);
  const selected = useStore((s) => s.selected);
  const { hover, select } = useStore.getState();
  if (!table || !table.rows.length) return null;
  const tips: Record<string, string> = {
    Exhaust: "attachment + limit", Placed: "share of the 100% layer that is placed", RoL: "rate on line = premium ÷ limit",
    Premium: "100% basis", Limit: "100% basis", Attachment: "100% basis",
  };
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Layer table, scrolls sideways">
      <table className="layer-table" aria-label="Layer table as exported">
        <thead>
          <tr>{table.columns.map((c) => <th key={c} scope="col" title={tips[c.split(" ")[0]]}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => {
            const id = table.layers[i];
            return (
              <tr key={id} className={id === selected ? "is-selected" : id === hovered ? "is-hovered" : undefined}
                onMouseEnter={() => hover(id)} onMouseLeave={() => hover(null)} onClick={() => select(id)}>
                {r.map((c, j) => (j === 0 ? <th key={j} scope="row">{c}</th> : <td key={j}>{c}</td>))}
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>{table.totals.map((c, j) => (j === 0 ? <th key={j} scope="row">{c}</th> : <td key={j}>{c}</td>))}</tr>
        </tfoot>
      </table>
    </div>
  );
}
