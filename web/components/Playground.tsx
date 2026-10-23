"use client";

import { useEffect } from "react";
import Canvas from "./Canvas";
import { LayerGrid, ShorthandBar } from "./Inputs";
import Inspector from "./Inspector";
import { ExportPanel, LayerTable, ProgrammeMenu, Toolbar, Warnings } from "./Panels";
import { CoveragePanel, ProgrammePanel, WalkPanel } from "./Programme";
import RiskPanel from "./Risk";
import EngineBar from "./EngineBar";
import { startEngine } from "@/lib/engine";
import { useStore } from "@/lib/store";
import type { RenderResult } from "@/lib/types";

export default function Playground() {
  const announcement = useStore((s) => s.announcement);
  const error = useStore((s) => s.error);

  useEffect(() => {
    startEngine();
    // Pre-rendered gallery scene so the canvas has something to show while the engine loads.
    void useStore.getState().init();
    fetch("/prerender/default.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((r: RenderResult | null) => r && useStore.getState().setPreview(r))
      .catch(() => undefined);
  }, []);

  // Undo and redo everywhere; pasting a block anywhere goes to the grid.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.key.toLowerCase() !== "z") return;
      const t = e.target as HTMLElement;
      if (t.tagName === "TEXTAREA" || (t.tagName === "INPUT" && (t as HTMLInputElement).type === "text")) return;
      e.preventDefault();
      void (e.shiftKey ? useStore.getState().redo() : useStore.getState().undo());
    };
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement;
      const html = e.clipboardData?.getData("text/html") ?? "";
      const text = e.clipboardData?.getData("text/plain") ?? "";
      const multi = /\t|\n/.test(text.trim()) || /<table/i.test(html);
      if (!multi && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (!text.trim() && !html) return;
      e.preventDefault();
      const payload = /<table/i.test(html) ? html : text;
      if (payload.length > 1_000_000) {
        useStore.setState({ error: "Pasted text is over 1 MB" });
        return;
      }
      void useStore.getState().pasteTable(payload);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("paste", onPaste);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("paste", onPaste);
    };
  }, []);

  return (
    <div className="playground">
      <EngineBar />
      <aside className="col-input" aria-label="Input">
        <ProgrammeMenu />
        <ShorthandBar />
        <LayerGrid />
        <ProgrammePanel />
      </aside>
      <section className="col-canvas" aria-label="Canvas">
        <Toolbar />
        <Canvas />
        {error && <p className="field-error" role="alert">{error}</p>}
        <LayerTable />
        <RiskPanel />
      </section>
      <aside className="col-inspector" aria-label="Inspector">
        <Inspector />
        <Warnings />
        <CoveragePanel />
        <WalkPanel />
        <ExportPanel />
      </aside>
      <div className="sr-only" aria-live="polite" role="status">{announcement}</div>
    </div>
  );
}
