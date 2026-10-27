"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { bracketMatching, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";
import { call, engineStatus, onEngineStatus, startEngine, type EngineStatus } from "@/lib/engine";
import { HANDOVER_KEY } from "@/components/Panels";
import { useStore } from "@/lib/store";
import type { TowerJSON } from "@/lib/types";

type Output =
  | { type: "stream" | "text" | "error"; text: string }
  | { type: "svg" | "html" | "png"; data: string; tower?: TowerJSON | null };

type Cell =
  | { id: number; type: "markdown"; source: string }
  | { id: number; type: "code"; source: string; outputs: Output[]; files: { name: string; url: string }[];
      count: number | null; running: boolean; tower: TowerJSON | null };

type RunResult = { outputs: Output[]; files: { name: string; base64: string }[]; tower: TowerJSON | null };

let counter = 0;

// Syntax colours that keep 4.5:1 contrast on white.
const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.operatorKeyword, t.controlKeyword, t.definitionKeyword], color: "#7a1fa2" },
  { tag: [t.string, t.special(t.string)], color: "#0b6b2e" },
  { tag: [t.number, t.bool, t.null], color: "#0d5a8a" },
  { tag: t.comment, color: "#5b6470", fontStyle: "italic" },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "#8a3b00" },
  { tag: [t.className, t.typeName], color: "#8a3b00" },
]);

export default function Notebook() {
  const [cells, setCells] = useState<Cell[]>([]);
  const [status, setStatus] = useState<EngineStatus>(engineStatus());
  const [busy, setBusy] = useState(false);
  const exec = useRef(0);
  const sources = useRef(new Map<number, string>());
  const router = useRouter();

  useEffect(() => {
    startEngine();
    const off = onEngineStatus(setStatus);
    fetch("/docs/how-to-use.json")
      .then((r) => r.json())
      .then((nb: { cells: { type: string; source: string; outputs?: Output[] }[] }) => {
        const loaded: Cell[] = nb.cells.map((c) => c.type === "markdown"
          ? { id: ++counter, type: "markdown", source: c.source }
          : { id: ++counter, type: "code", source: c.source, outputs: c.outputs ?? [], files: [], count: null, running: false, tower: null });
        const code = takeHandOver();
        if (code) {
          loaded.unshift(
            { id: ++counter, type: "markdown", source: "## From the Playground\n\nThe Python that rebuilds your tower. Press **Run**." },
            { id: ++counter, type: "code", source: code, outputs: [], files: [], count: null, running: false, tower: null },
          );
        }
        setCells(loaded);
      })
      .catch(() => setCells([{ id: ++counter, type: "markdown", source: "The guide could not be loaded." }]));
    return () => {
      off();
    };
  }, []);

  async function runCell(id: number) {
    const code = sources.current.get(id) ?? (cells.find((c) => c.id === id) as Extract<Cell, { type: "code" }>).source;
    setCells((cs) => cs.map((c) => (c.id === id && c.type === "code" ? { ...c, running: true } : c)));
    let result: RunResult;
    try {
      result = await call<RunResult>("run_cell", { code });
    } catch (e) {
      result = { outputs: [{ type: "error", text: (e as Error).message }], files: [], tower: null };
    }
    const n = ++exec.current;
    const files = result.files.map((f) => ({ name: f.name, url: URL.createObjectURL(b64Blob(f.base64)) }));
    setCells((cs) => cs.map((c) => (c.id === id && c.type === "code"
      ? { ...c, running: false, outputs: result.outputs, files, count: n, tower: result.tower }
      : c)));
    return !result.outputs.some((o) => o.type === "error");
  }

  async function runAll() {
    setBusy(true);
    for (const c of cells) {
      if (c.type === "code" && !(await runCell(c.id))) break;
    }
    setBusy(false);
  }

  async function reset() {
    await call("reset");
    exec.current = 0;
    setCells((cs) => cs.map((c) => (c.type === "code" ? { ...c, count: null } : c)));
  }

  function openInPlayground(tower: TowerJSON) {
    useStore.setState({ pending: tower });
    router.push("/");
  }

  return (
    <div>
      <div className="nb-header">
        <button type="button" className="primary" disabled={busy || cells.length === 0} onClick={() => void runAll()}>
          {busy ? "Running…" : "Run all"}
        </button>
        <button type="button" onClick={() => void reset()} title="Clear the shared namespace, like restarting a kernel">Reset</button>
        <span className="status" role="status">
          {status.state === "ready" ? `Engine ${status.version} ready · cells share one namespace, top to bottom`
            : status.state === "failed" ? `Engine failed: ${status.error}` : `${status.label}… outputs below are from the last release build`}
        </span>
      </div>
      {cells.map((c) => c.type === "markdown" ? (
        <Markdown key={c.id} source={c.source} />
      ) : (
        <section key={c.id} className="nb-cell" aria-label="Code cell">
          <div className="nb-cell-head">
            <span className="count">[{c.running ? "*" : c.count ?? " "}]</span>
            <button type="button" onClick={() => void runCell(c.id)} disabled={c.running} aria-label="Run cell">▶ Run</button>
            <span className="muted" style={{ fontSize: 11.5 }}>Shift+Enter</span>
          </div>
          <Editor initial={c.source} onChange={(v) => sources.current.set(c.id, v)} onRun={() => void runCell(c.id)} />
          {(c.outputs.length > 0 || c.files.length > 0) && (
            <div className="nb-outputs" aria-live="polite">
              {c.outputs.map((o, i) => <OutputView key={i} o={o} onOpen={openInPlayground} />)}
              {c.files.length > 0 && (
                <div className="nb-files">
                  {c.files.map((f) => <a key={f.name} href={f.url} download={f.name}>⬇ {f.name}</a>)}
                </div>
              )}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

function OutputView({ o, onOpen }: { o: Output; onOpen: (t: TowerJSON) => void }) {
  if (o.type === "svg") {
    return (
      <div>
        <div dangerouslySetInnerHTML={{ __html: o.data }} />
        {o.tower && <button type="button" onClick={() => onOpen(o.tower!)}>Open in Playground</button>}
      </div>
    );
  }
  if (o.type === "html") return <div className="nb-html" dangerouslySetInnerHTML={{ __html: o.data }} />;
  // eslint-disable-next-line @next/next/no-img-element
  if (o.type === "png") return <img className="nb-png" src={`data:image/png;base64,${o.data}`} alt="Plot output" />;
  return <pre className={o.type === "error" ? "error" : undefined}>{"text" in o ? o.text : ""}</pre>;
}

function Editor({ initial, onChange, onRun }: { initial: string; onChange: (v: string) => void; onRun: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const runRef = useRef(onRun);
  useEffect(() => {
    runRef.current = onRun;
  });
  useEffect(() => {
    const view = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: initial,
        extensions: [
          lineNumbers(), history(), bracketMatching(), python(), EditorView.lineWrapping,
          syntaxHighlighting(highlight),
          keymap.of([{ key: "Shift-Enter", run: () => { runRef.current(); return true; } }, indentWithTab, ...defaultKeymap, ...historyKeymap]),
          EditorView.updateListener.of((u) => u.docChanged && onChange(u.state.doc.toString())),
          EditorView.contentAttributes.of({ "aria-label": "Python code" }),
        ],
      }),
    });
    return () => view.destroy();
    // The editor owns its text after mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div className="nb-editor" ref={host} />;
}

// Code from the Playground's "Open in How to use" arrives through this site's own storage, never
// the URL, so a link from elsewhere cannot pre-fill a cell. Read once, and only if just written.
function takeHandOver(): string | null {
  try {
    const raw = localStorage.getItem(HANDOVER_KEY);
    localStorage.removeItem(HANDOVER_KEY);
    const v = raw ? (JSON.parse(raw) as { code?: unknown; at?: unknown }) : null;
    return v && typeof v.code === "string" && typeof v.at === "number" && Date.now() - v.at < 60_000 ? v.code : null;
  } catch {
    return null;
  }
}

/** A small markdown renderer for our own guide text: headings, paragraphs, lists, code, bold, links. */
function Markdown({ source }: { source: string }) {
  const blocks: React.ReactNode[] = [];
  const lines = source.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={i} className="formula"><code>{body.join("\n")}</code></pre>);
    } else if (/^#{1,3} /.test(line)) {
      const level = line.match(/^#+/)![0].length;
      const text = inline(line.replace(/^#+ /, ""));
      blocks.push(level === 1 ? <h1 key={i}>{text}</h1> : level === 2 ? <h2 key={i}>{text}</h2> : <h3 key={i}>{text}</h3>);
      i++;
    } else if (/^[-*] /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*] /.test(lines[i])) items.push(lines[i++].slice(2));
      blocks.push(<ul key={i}>{items.map((t, k) => <li key={k}>{inline(t)}</li>)}</ul>);
    } else if (line.trim()) {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(#|```|[-*] )/.test(lines[i])) para.push(lines[i++]);
      blocks.push(<p key={i}>{inline(para.join(" "))}</p>);
    } else i++;
  }
  return <div className="nb-md">{blocks}</div>;
}

function inline(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let at = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push(text.slice(at, m.index));
    const t = m[0];
    if (t.startsWith("`")) out.push(<code key={m.index}>{t.slice(1, -1)}</code>);
    else if (t.startsWith("**")) out.push(<strong key={m.index}>{t.slice(2, -2)}</strong>);
    else {
      const [, label, href] = t.match(/\[([^\]]+)\]\(([^)]+)\)/)!;
      out.push(<a key={m.index} href={href} rel="noopener noreferrer">{label}</a>);
    }
    at = m.index + t.length;
  }
  out.push(text.slice(at));
  return out;
}

function b64Blob(b64: string): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes]);
}
