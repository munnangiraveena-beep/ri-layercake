"use client";

import { create } from "zustand";
import { call } from "./engine";
import type { AggregateResult, LossResult, Mapping, Op, PortfolioResult, RenderResult, TowerJSON, View } from "./types";
import { DEFAULT_VIEW } from "./types";

const AUTOSAVE_KEY = "ri-layercake/autosave@2";
const LEGACY_KEY = "ri-layercake/autosave@1";
const HISTORY = 200;

/** One portfolio (line of business) in the book, e.g. Credit or Surety, each with its own programme. */
export type PortfolioTab = { name: string; tower: TowerJSON | null };

type Snapshot = { portfolios: PortfolioTab[]; active: number; view: View };

type Saved = Snapshot & { title?: string; result?: RenderResult };

type State = {
  result: RenderResult | null;
  tower: TowerJSON | null; // the active portfolio's tower
  portfolios: PortfolioTab[];
  active: number;
  bookTitle: string | null;
  view: View;
  selected: string | null;
  hovered: string | null;
  past: Snapshot[];
  future: Snapshot[];
  error: string | null;
  busy: boolean;
  preview: boolean; // showing a saved or pre-rendered scene while the engine loads
  loss: number | null;
  lossLine: string | null;
  lossResult: LossResult | null;
  coverMode: "risk" | "portfolio" | "aggregate";
  aggregate: { amount: number; asRatio: boolean } | null;
  aggregateResult: AggregateResult | null;
  portfolioInput: { text?: string; base64?: string; name?: string; example?: boolean } | null;
  portfolioResult: PortfolioResult | null;
  coverError: string | null;
  paste: { text: string; mapping: Mapping } | null;
  announcement: string;
  textDraft: string | null; // shorthand being typed, until the engine confirms it
  pending: TowerJSON | null; // a tower handed over from the How to use tab

  init: () => Promise<void>;
  setPreview: (r: RenderResult) => void;
  edit: (op: Op, message?: string) => Promise<void>;
  parseText: (text: string) => Promise<void>;
  pasteTable: (text: string, mapping?: Mapping | null) => Promise<void>;
  loadGallery: (name: string) => Promise<void>;
  loadTower: (tower: TowerJSON) => Promise<void>;
  setView: (patch: Partial<View>) => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  select: (id: string | null) => void;
  hover: (id: string | null) => void;
  setLoss: (amount: number | null) => Promise<void>;
  setLossLine: (line: string | null) => Promise<void>;
  setCoverMode: (mode: State["coverMode"]) => void;
  setAggregate: (input: { amount: number; asRatio: boolean } | null) => Promise<void>;
  runPortfolio: (input: State["portfolioInput"]) => Promise<void>;
  refreshCover: () => void;
  announce: (msg: string) => void;
  clearData: () => void;
};

let seq = 0;

function persist(s: { portfolios: PortfolioTab[]; active: number; view: View; bookTitle: string | null; result: RenderResult | null }) {
  try {
    const saved: Saved = { portfolios: s.portfolios, active: s.active, view: s.view, title: s.bookTitle ?? undefined,
      result: s.result ?? undefined };
    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(saved));
  } catch {
    // Private windows and blocked storage still work, just without autosave.
  }
}

function restore(): Saved | null {
  try {
    const raw = localStorage.getItem(AUTOSAVE_KEY);
    if (raw) return JSON.parse(raw) as Saved;
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const { tower, view } = JSON.parse(legacy) as { tower: TowerJSON; view: View };
      return { portfolios: [{ name: "Portfolio 1", tower }], active: 0, view };
    }
  } catch {
    // ignore unreadable storage
  }
  return null;
}

export const useStore = create<State>((set, get) => {
  const snapshot = (): Snapshot => ({ portfolios: get().portfolios, active: get().active, view: get().view });

  /** Send a command to the engine for the active portfolio; only the latest response wins. */
  async function apply(command: string, payload: object, opts: { record?: boolean; message?: string } = {}) {
    const mine = ++seq;
    const before = snapshot();
    set({ busy: true });
    try {
      const r = await call<RenderResult>(command, { view: get().view, ...payload });
      if (mine !== seq) return;
      const changed = JSON.stringify(r.tower) !== JSON.stringify(get().tower);
      set((s) => {
        const portfolios = s.portfolios.length ? [...s.portfolios] : [{ name: "Portfolio 1", tower: null }];
        portfolios[s.active] = { ...portfolios[s.active], tower: r.tower };
        return {
          result: r,
          tower: r.tower,
          portfolios,
          error: null,
          busy: false,
          preview: false,
          textDraft: null,
          past: opts.record && changed && before.portfolios.length ? [...s.past, before].slice(-HISTORY) : s.past,
          future: opts.record && changed ? [] : s.future,
          selected: s.selected && r.layers.some((l) => l.id === s.selected) ? s.selected : null,
          announcement: opts.message ?? s.announcement,
        };
      });
      persist(get());
      get().refreshCover();
    } catch (e) {
      if (mine === seq) set({ error: (e as Error).message, busy: false });
    }
  }

  async function restoreSnapshot(snap: Snapshot, message: string) {
    set({ portfolios: snap.portfolios, active: snap.active, view: snap.view, tower: snap.portfolios[snap.active]?.tower ?? null });
    await apply("render", { tower: snap.portfolios[snap.active]?.tower ?? null }, { message });
  }

  return {
    result: null,
    tower: null,
    portfolios: [],
    active: 0,
    bookTitle: null,
    view: DEFAULT_VIEW,
    selected: null,
    hovered: null,
    past: [],
    future: [],
    error: null,
    busy: false,
    preview: true,
    loss: null,
    lossLine: null,
    lossResult: null,
    coverMode: "risk",
    aggregate: null,
    aggregateResult: null,
    portfolioInput: null,
    portfolioResult: null,
    coverError: null,
    paste: null,
    announcement: "",
    textDraft: null,
    pending: null,

    init: async () => {
      const handed = get().pending;
      if (handed) {
        set({ pending: null });
        await apply("render", { tower: handed }, { record: true, message: "Opened tower from How to use" });
        return;
      }
      if (get().tower) return;
      const saved = restore();
      if (saved?.portfolios?.length) {
        const active = Math.min(saved.active ?? 0, saved.portfolios.length - 1);
        // Show exactly what was there last time, straight away, so the page does not jump when the engine is ready.
        set({ portfolios: saved.portfolios, active, view: { ...DEFAULT_VIEW, ...saved.view }, bookTitle: saved.title ?? null,
          tower: saved.portfolios[active].tower, result: saved.result ?? null });
        await apply("render", { tower: saved.portfolios[active].tower });
      } else {
        set({ portfolios: [{ name: "Property", tower: null }], active: 0 });
        await apply("gallery", { name: "per_risk_xol" });
      }
    },

    setPreview: (r) => {
      // The pre-rendered default only fills an empty canvas; a saved tower always wins.
      if (get().preview && !get().result && !get().tower) set({ result: r });
    },

    edit: (op, message) => apply("edit", { tower: get().tower, op }, { record: true, message }),

    parseText: (text) => {
      set({ textDraft: text });
      return apply("parse_text", { tower: get().tower, text }, { record: true });
    },

    pasteTable: async (text, mapping) => {
      await apply("paste", { tower: get().tower, text, mapping }, { record: true, message: "Pasted table" });
      const m = get().result?.mapping;
      set({ paste: m ? { text, mapping: m } : null });
    },

    loadGallery: (name) => apply("gallery", { name }, { record: true, message: "Opened gallery tower in this portfolio" }),


    loadTower: (tower) => apply("render", { tower }, { record: true, message: "Loaded tower" }),





    setView: async (patch) => {
      const before = snapshot();
      set((s) => ({ view: { ...s.view, ...patch }, past: [...s.past, before].slice(-HISTORY), future: [] }));
      await apply("render", { tower: get().tower });
    },

    undo: async () => {
      const prev = get().past.at(-1);
      if (!prev) return;
      const now = snapshot();
      set((s) => ({ past: s.past.slice(0, -1), future: [now, ...s.future].slice(0, HISTORY) }));
      await restoreSnapshot(prev, "Undone");
    },

    redo: async () => {
      const next = get().future[0];
      if (!next) return;
      const now = snapshot();
      set((s) => ({ future: s.future.slice(1), past: [...s.past, now].slice(-HISTORY) }));
      await restoreSnapshot(next, "Redone");
    },

    select: (id) => set({ selected: id }),
    hover: (id) => set({ hovered: id }),

    setLoss: async (amount) => {
      set({ loss: amount });
      if (amount === null || !get().tower) {
        set({ lossResult: null });
        return;
      }
      try {
        const r = await call<LossResult>("loss", { tower: get().tower, amount, line: get().lossLine });
        if (get().loss === amount) set({ lossResult: r });
      } catch {
        set({ lossResult: null });
      }
    },

    setLossLine: async (line) => {
      set({ lossLine: line });
      if (get().loss !== null) await get().setLoss(get().loss);
    },

    setCoverMode: (mode) => set({ coverMode: mode }),

    setAggregate: async (input) => {
      set({ aggregate: input, coverMode: "aggregate" });
      if (!input || !get().tower) {
        set({ aggregateResult: null });
        return;
      }
      try {
        const r = await call<AggregateResult>("aggregate", { tower: get().tower, amount: input.amount, as_loss_ratio: input.asRatio });
        if (get().aggregate === input) set({ aggregateResult: r, coverError: null });
      } catch (e) {
        set({ aggregateResult: null, coverError: (e as Error).message });
      }
    },

    runPortfolio: async (input) => {
      set({ portfolioInput: input, coverMode: "portfolio" });
      if (!input || !get().tower) {
        set({ portfolioResult: null });
        return;
      }
      try {
        const r = await call<PortfolioResult>("portfolio", { tower: get().tower, ...input });
        if (get().portfolioInput === input) set({ portfolioResult: r, coverError: null });
      } catch (e) {
        set({ portfolioResult: null, coverError: (e as Error).message });
      }
    },

    refreshCover: () => {
      // Re-run every coverage view against the edited tower, keeping the tab the user is on.
      const s = get();
      const mode = s.coverMode;
      if (s.loss !== null) void s.setLoss(s.loss);
      if (s.aggregate) void s.setAggregate({ ...s.aggregate });
      if (s.portfolioInput) void s.runPortfolio({ ...s.portfolioInput });
      set({ coverMode: mode });
    },

    announce: (msg) => set({ announcement: msg }),

    clearData: () => {
      try {
        localStorage.removeItem(AUTOSAVE_KEY);
        localStorage.removeItem(LEGACY_KEY);
      } catch {
        // nothing stored
      }
    },
  };
});
