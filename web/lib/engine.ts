"use client";

// Client for the engine worker. Calls made before the engine is ready are
// queued by the worker and replayed once Pyodide has loaded.

export type EngineStatus =
  | { state: "loading"; step: number; total: number; label: string }
  | { state: "ready"; version: string; pyodide: string }
  | { state: "failed"; error: string };

type Pending = { resolve: (v: Record<string, unknown>) => void; reject: (e: Error) => void };

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, Pending>();
let status: EngineStatus = { state: "loading", step: 0, total: 5, label: "Loading engine" };
const listeners = new Set<(s: EngineStatus) => void>();

function setStatus(s: EngineStatus) {
  status = s;
  listeners.forEach((fn) => fn(s));
}

export function startEngine(): void {
  if (worker || typeof window === "undefined") return;
  worker = new Worker("/engine-worker.mjs", { type: "module", name: "ri-layercake-engine" });
  worker.onmessage = (e: MessageEvent) => {
    const msg = e.data;
    if (msg.type === "progress") setStatus({ state: "loading", step: msg.step, total: msg.total, label: msg.label });
    else if (msg.type === "ready") setStatus({ state: "ready", version: msg.version, pyodide: msg.pyodide });
    else if (msg.type === "failed") {
      setStatus({ state: "failed", error: msg.error });
      pending.forEach((p) => p.reject(new Error(msg.error)));
      pending.clear();
    } else if (msg.type === "result") {
      const p = pending.get(msg.id);
      if (!p) return;
      pending.delete(msg.id);
      if (msg.result.ok) p.resolve(msg.result);
      else p.reject(new Error(msg.result.error));
    }
  };
  worker.onerror = (e) => setStatus({ state: "failed", error: e.message || "The engine could not start" });
}

export function call<T = Record<string, unknown>>(command: string, payload: object = {}): Promise<T> {
  startEngine();
  const id = nextId++;
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve: resolve as Pending["resolve"], reject });
    worker!.postMessage({ id, command, payload });
  });
}

export function engineStatus(): EngineStatus {
  return status;
}

export function onEngineStatus(fn: (s: EngineStatus) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
