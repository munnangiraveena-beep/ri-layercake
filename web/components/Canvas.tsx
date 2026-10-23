"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { colour, money } from "@/lib/draw";
import { snap, snapStep, topValue, valueToY, yToValue } from "@/lib/scale";
import { useStore } from "@/lib/store";
import type { Hit, LayerRow, Scene, Shape } from "@/lib/types";

type Drag =
  | { kind: "edge"; layer: LayerRow; edge: "top" | "bottom"; hit: Hit; y0: number; value: number }
  | { kind: "body"; layer: LayerRow; hit: Hit; y0: number; value: number; only: boolean }
  | { kind: "placed"; layer: LayerRow; hit: Hit; x0: number; value: number }
  | { kind: "loss"; value: number };

type Menu = { x: number; y: number; layer: LayerRow; at: number } | null;

const EDGE_PX = 6;

export default function Canvas() {
  const result = useStore((s) => s.result);
  const preview = useStore((s) => s.preview);
  const selected = useStore((s) => s.selected);
  const hovered = useStore((s) => s.hovered);
  const loss = useStore((s) => s.loss);
  const lossResult = useStore((s) => s.lossResult);
  const coverMode = useStore((s) => s.coverMode);
  const aggregateResult = useStore((s) => s.aggregateResult);
  const { edit, select, hover, setLoss, announce } = useStore.getState();

  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
  const [edgeHover, setEdgeHover] = useState<{ hit: Hit; layer: LayerRow } | null>(null);
  const [menu, setMenu] = useState<Menu>(null);
  const [tip, setTip] = useState<{ x: number; y: number; layer: LayerRow } | null>(null);

  const scene = result?.scene;
  const tower = result?.tower;
  const layers = useMemo(() => result?.layers ?? [], [result]);
  const byId = useMemo(() => new Map(layers.map((l) => [l.id, l])), [layers]);
  const fmt = useCallback((v: number) => money(tower?.currency ?? "GBP", tower?.units ?? "m", v), [tower]);
  const step = useMemo(() => (scene?.scale ? snapStep(topValue(scene.scale)) : 1), [scene]);

  const toScene = useCallback((e: { clientX: number; clientY: number }) => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return { x: 0, y: 0 };
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }, []);

  const valueAt = useCallback(
    (y: number, hit?: Hit, y0?: number, start?: number): number => {
      if (!scene?.scale) return 0;
      if (scene.scale.type === "schematic" && hit?.per_px !== undefined && y0 !== undefined && start !== undefined) {
        return start - (y - y0) * hit.per_px;
      }
      return yToValue(scene.scale, y);
    },
    [scene],
  );

  // ------------------------------------------------------------------ pointer handling

  function findHit(x: number, y: number): { hit: Hit; layer: LayerRow; edge: "top" | "bottom" | "body" | "placed" } | null {
    if (!scene) return null;
    for (const h of scene.hit) {
      const l = byId.get(h.layer);
      if (!l) continue;
      if ((h.edge === "top" || h.edge === "bottom") && x >= h.x && x <= h.x + (h.w ?? 0) && Math.abs(y - h.y) <= EDGE_PX) {
        return { hit: h, layer: l, edge: h.edge };
      }
    }
    for (const h of scene.hit) {
      const l = byId.get(h.layer);
      if (!l) continue;
      if (h.edge === "placed" && Math.abs(x - h.x) <= EDGE_PX && y >= h.y && y <= h.y + (h.h ?? 0) && l.placed < 1) {
        return { hit: h, layer: l, edge: "placed" };
      }
    }
    for (const h of scene.hit) {
      const l = byId.get(h.layer);
      if (l && h.edge === "body" && x >= h.x && x <= h.x + (h.w ?? 0) && y >= h.y && y <= h.y + (h.h ?? 0)) {
        return { hit: h, layer: l, edge: "body" };
      }
    }
    return null;
  }

  function onPointerDown(e: React.PointerEvent) {
    if (e.button !== 0 || !scene || preview) return;
    setMenu(null);
    const p = toScene(e);
    const found = findHit(p.x, p.y);
    if (!found) {
      select(null);
      return;
    }
    const { hit, layer, edge } = found;
    select(layer.id);
    (e.target as Element).setPointerCapture?.(e.pointerId);
    if (edge === "top" || edge === "bottom") {
      setDrag({ kind: "edge", layer, edge, hit, y0: p.y, value: edge === "top" ? layer.exhaust : layer.attachment });
    } else if (edge === "placed") {
      setDrag({ kind: "placed", layer, hit, x0: p.x, value: layer.placed });
    } else if (layer.kind === "xl") {
      setDrag({ kind: "body", layer, hit, y0: p.y, value: layer.attachment, only: e.shiftKey });
    }
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!scene) return;
    const p = toScene(e);
    setPointer(p);
    if (!drag) {
      const found = findHit(p.x, p.y);
      setEdgeHover(found && found.edge === "top" ? { hit: found.hit, layer: found.layer } : null);
      if (found) hover(found.layer.id);
      else hover(null);
      setTip(found && found.edge === "body" ? { x: p.x, y: p.y, layer: found.layer } : null);
      const svg = svgRef.current;
      if (svg) {
        svg.style.cursor = !found ? "default" : found.edge === "body" ? "grab" : found.edge === "placed" ? "ew-resize" : "ns-resize";
      }
      return;
    }
    setTip(null);
    const free = e.altKey;
    if (drag.kind === "edge") {
      const start = drag.edge === "top" ? drag.layer.exhaust : drag.layer.attachment;
      let v = valueAt(p.y, drag.hit, drag.y0, start);
      if (!free) v = snap(v, step);
      if (drag.edge === "top") v = Math.max(v, drag.layer.attachment + (free ? 0.1 : step));
      else v = Math.min(Math.max(0, v), drag.layer.exhaust - (free ? 0.1 : step));
      setDrag({ ...drag, value: v });
    } else if (drag.kind === "body") {
      const startY = valueAt(drag.y0, drag.hit, drag.y0, drag.layer.attachment);
      let v = drag.layer.attachment + (valueAt(p.y, drag.hit, drag.y0, drag.layer.attachment) - startY);
      if (!free) v = snap(v, step);
      setDrag({ ...drag, value: Math.max(0, v), only: e.shiftKey });
    } else if (drag.kind === "placed") {
      const x0 = drag.hit.x0 ?? 0;
      const w = drag.hit.w ?? 1;
      let v = Math.min(1, Math.max(0, (p.x - x0) / w));
      if (!free) v = Math.round(v * 40) / 40;
      setDrag({ ...drag, value: v });
    } else if (drag.kind === "loss" && scene.scale) {
      let v = Math.max(0, yToValue(scene.scale, p.y));
      if (!free) v = snap(v, step);
      setDrag({ ...drag, value: v });
      void setLoss(v);
    }
  }

  function onPointerUp() {
    if (!drag) return;
    const d = drag;
    setDrag(null);
    if (d.kind === "edge") {
      const l = d.layer;
      if (d.edge === "top" && d.value !== l.exhaust) {
        if (l.kind === "retention") void edit({ type: "update", layer: l.id, fields: { limit: d.value } }, `${l.display} set to ${fmt(d.value)}`);
        else void edit({ type: "update", layer: l.id, fields: { limit: d.value - l.attachment } },
          `${l.display} exhaust set to ${fmt(d.value)}`);
      } else if (d.edge === "bottom" && d.value !== l.attachment) {
        void edit({ type: "update", layer: l.id, fields: { attachment: d.value, limit: l.exhaust - d.value } },
          `${l.display} attachment set to ${fmt(d.value)}`);
      }
    } else if (d.kind === "body" && d.value !== d.layer.attachment) {
      void edit({ type: "move", layer: d.layer.id, attachment: d.value, shift_above: !d.only },
        `${d.layer.display} moved to attach at ${fmt(d.value)}`);
    } else if (d.kind === "placed" && d.value !== d.layer.placed) {
      void edit({ type: "update", layer: d.layer.id, fields: { placed: d.value } },
        `${d.layer.display} placed ${Math.round(d.value * 1000) / 10}%`);
    }
  }

  function onContextMenu(e: React.MouseEvent) {
    if (!scene || preview) return;
    const p = toScene(e);
    const found = findHit(p.x, p.y);
    if (!found) return;
    e.preventDefault();
    select(found.layer.id);
    const at = snap(valueAt(p.y), step);
    const rect = svgRef.current!.getBoundingClientRect();
    setMenu({ x: e.clientX - rect.left, y: e.clientY - rect.top, layer: found.layer, at });
  }

  // ------------------------------------------------------------------ keyboard

  function onKeyDown(e: React.KeyboardEvent) {
    if (!scene || preview) return;
    const order = layers;
    const idx = order.findIndex((l) => l.id === selected);
    const cur = idx >= 0 ? order[idx] : null;
    if ((e.key === "ArrowUp" || e.key === "ArrowDown") && !e.shiftKey) {
      e.preventDefault();
      const next = e.key === "ArrowUp" ? Math.min(order.length - 1, idx + 1) : Math.max(0, idx < 0 ? 0 : idx - 1);
      const l = order[next];
      if (l) {
        select(l.id);
        announce(`${l.display}: ${l.label}`);
      }
    } else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && e.shiftKey && cur) {
      e.preventDefault();
      const dir = e.key === "ArrowUp" ? 1 : -1;
      if (e.altKey && cur.kind === "xl") {
        const att = Math.max(0, cur.attachment + dir * step);
        if (att < cur.exhaust) void edit({ type: "update", layer: cur.id, fields: { attachment: att, limit: cur.exhaust - att } },
          `${cur.display} attachment set to ${fmt(att)}`);
      } else {
        const limit = cur.limit + dir * step;
        if (limit > 0) void edit({ type: "update", layer: cur.id, fields: { limit } }, `${cur.display} limit set to ${fmt(limit)}`);
      }
    } else if ((e.key === "Delete" || e.key === "Backspace") && cur) {
      e.preventDefault();
      void edit({ type: "remove", layer: cur.id }, `${cur.display} deleted`);
    } else if (e.key === "Enter" && cur) {
      e.preventDefault();
      window.dispatchEvent(new CustomEvent("ri:focus-inspector"));
    } else if (e.key === "Escape") {
      select(null);
      setMenu(null);
    }
  }

  useEffect(() => {
    const close = () => setMenu(null);
    window.addEventListener("scroll", close, true);
    return () => window.removeEventListener("scroll", close, true);
  }, []);

  if (!scene || !tower) {
    return <div className="canvas-frame canvas-empty" aria-busy="true">Loading tower…</div>;
  }

  // ------------------------------------------------------------------ optimistic geometry

  const shapes = optimistic(scene, drag, byId);
  const colors = scene.colors;
  const hasQs = layers.some((l) => l.kind === "qs");
  const lossValue = drag?.kind === "loss" ? drag.value : loss;
  // The gross loss line only makes sense when the whole loss enters the XL tower (no QS in front of it).
  const lossY = coverMode === "risk" && !hasQs && lossValue !== null && scene.scale ? valueToY(scene.scale, lossValue) : null;
  const fills = coverMode === "risk" && loss !== null ? lossResult?.fills : coverMode === "aggregate" ? aggregateResult?.fills : undefined;
  const bodies = scene.hit.filter((h) => h.edge === "body");
  const gaps = scene.shapes.filter((s) => s.role === "gap") as Extract<Shape, { type: "rect" }>[];
  const axisX = Math.min(...bodies.map((b) => b.x), 400) - 16;
  const tag = drag && pointer ? dragLabel(drag, fmt) : null;
  const W = scene.frame.w;
  const H = scene.frame.h;

  return (
    <div className="canvas-frame" style={{ aspectRatio: `${W} / ${H}` }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="canvas-svg"
        role="application"
        aria-roledescription="tower editor"
        aria-label="Tower canvas. Arrow keys select layers, Shift with arrows changes the limit, Alt Shift with arrows changes the attachment, Delete removes, Enter edits."
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          setEdgeHover(null);
          setTip(null);
          hover(null);
        }}
        onContextMenu={onContextMenu}
        onKeyDown={onKeyDown}
      >
        <defs>
          {hatchDefs(scene)}
        </defs>
        <rect width={W} height={H} fill={colors.bg1} />
        {shapes.map((s) => (s.role === "title" || s.role === "subtitle" ? null : draw(s, colors, selected, hovered, byId)))}
        {fills &&
          bodies.map((b) => {
            const f = fills[b.layer];
            if (!f || b.h === undefined || b.w === undefined) return null;
            const fh = b.h * Math.min(1, f);
            return (
              <g key={`fill-${b.layer}`} className="loss-fill" pointerEvents="none">
                <rect x={b.x} y={b.y + b.h - fh} width={b.w} height={fh} fill={colors.accent6} opacity={0.35} />
                {f >= 1 && <rect x={b.x + 1} y={b.y + 1} width={b.w - 2} height={b.h - 2} fill="none"
                  stroke={colors.accent6} strokeWidth={3} />}
              </g>
            );
          })}
        {lossY !== null && (
          <g className="loss-handle" onPointerDown={(e) => {
            e.stopPropagation();
            (e.target as Element).setPointerCapture?.(e.pointerId);
            setDrag({ kind: "loss", value: lossValue ?? 0 });
          }}>
            <line x1={axisX - 30} x2={Math.max(...bodies.map((b) => b.x + (b.w ?? 0))) + 8} y1={lossY} y2={lossY}
              stroke={colors.accent6} strokeWidth={2.5} strokeDasharray="8 5" />
            <rect x={axisX - 64} y={lossY - 11} width={60} height={22} rx={11} fill={colors.accent6} style={{ cursor: "ns-resize" }} />
            <text x={axisX - 34} y={lossY + 4} textAnchor="middle" fontSize={11} fill="#fff" fontWeight={700}>
              {fmt(lossValue ?? 0)}
            </text>
          </g>
        )}
        {edgeHover && !drag && (
          <g className="insert-plus" onPointerDown={(e) => {
            e.stopPropagation();
            const l = edgeHover.layer;
            const limit = l.kind === "retention" ? Math.max(step, l.limit) : l.limit;
            void edit({ type: "insert", at: l.exhaust, limit }, `Layer inserted at ${fmt(l.exhaust)}`);
            setEdgeHover(null);
          }}>
            <circle cx={edgeHover.hit.x + (edgeHover.hit.w ?? 0) + 14} cy={edgeHover.hit.y} r={10} fill={colors.accent1} />
            <text x={edgeHover.hit.x + (edgeHover.hit.w ?? 0) + 14} y={edgeHover.hit.y + 4.5} textAnchor="middle"
              fontSize={15} fontWeight={700} fill="#fff">+</text>
            <title>Insert a layer here</title>
          </g>
        )}
      </svg>

      <TitleOverlay scene={scene} />

      {gaps.map((g) => {
        const w = result!.warnings.find((d) => d.key === g.key);
        if (!w) return null;
        return (
          <div key={g.id} className="gap-actions" style={pos(scene, g.x + g.w + 8, g.y + g.h / 2)}>
            <button type="button" onClick={() => void edit({ type: "apply_fix", fix: w.fixes[0] }, "Gap closed")}>Close gap</button>
            <button type="button" onClick={() => void edit({ type: "apply_fix", fix: w.fixes[w.fixes.length - 1] }, "Gap kept")}>Keep</button>
          </div>
        );
      })}

      {tag && pointer && (
        <div className="value-tag" style={pos(scene, pointer.x + 14, pointer.y - 18)} aria-hidden="true">{tag}</div>
      )}

      {tip && !drag && <LayerTip scene={scene} tip={tip} fmt={fmt} />}

      {menu && (
        <ul className="context-menu" role="menu" style={{ left: menu.x, top: menu.y }}>
          {menu.layer.kind === "xl" && menu.at > menu.layer.attachment && menu.at < menu.layer.exhaust && (
            <li role="menuitem" tabIndex={0} onClick={() => {
              void edit({ type: "split", layer: menu.layer.id, at: menu.at }, `${menu.layer.display} split at ${fmt(menu.at)}`);
              setMenu(null);
            }}>Split here at {fmt(menu.at)}</li>
          )}
          {(() => {
            const above = layers.find((l) => l.kind === "xl" && l.id !== menu.layer.id && l.attachment >= menu.layer.attachment &&
              layers.indexOf(l) === layers.indexOf(menu.layer) + 1);
            return above ? (
              <li role="menuitem" tabIndex={0} onClick={() => {
                void edit({ type: "merge", a: menu.layer.id, b: above.id }, `${menu.layer.display} merged with ${above.display}`);
                setMenu(null);
              }}>Merge with layer above</li>
            ) : null;
          })()}
          <li role="menuitem" tabIndex={0} onClick={() => {
            void edit({ type: "remove", layer: menu.layer.id }, `${menu.layer.display} deleted`);
            setMenu(null);
          }}>Delete</li>
        </ul>
      )}

      {preview && <div className="preview-badge">Preview · engine loading</div>}
    </div>
  );
}

// ---------------------------------------------------------------------- helpers

function pos(scene: Scene, x: number, y: number): React.CSSProperties {
  return { left: `${(x / scene.frame.w) * 100}%`, top: `${(y / scene.frame.h) * 100}%` };
}

function dragLabel(d: Drag, fmt: (v: number) => string): string {
  if (d.kind === "placed") return `${Math.round(d.value * 1000) / 10}% placed`;
  if (d.kind === "edge") return d.edge === "top" ? `Exhaust ${fmt(d.value)}` : `Attach ${fmt(d.value)}`;
  if (d.kind === "body") return `Attach ${fmt(d.value)}${d.only ? " (this layer only)" : ""}`;
  return `Loss ${fmt(d.value)}`;
}

/** Move the dragged layer's shapes with simple geometry until the engine answers. */
function optimistic(scene: Scene, drag: Drag | null, byId: Map<string, LayerRow>): Shape[] {
  if (!drag || drag.kind === "loss" || !scene.scale) return scene.shapes;
  const id = drag.layer.id;
  const body = scene.hit.find((h) => h.layer === id && h.edge === "body");
  if (!body || body.h === undefined) return scene.shapes;
  let top = body.y;
  let bottom = body.y + body.h;
  let shiftAbove = 0;
  if (drag.kind === "edge") {
    const perPx = drag.hit.per_px || 1;
    const dy = scene.scale.type === "schematic"
      ? -(drag.value - (drag.edge === "top" ? drag.layer.exhaust : drag.layer.attachment)) / perPx
      : valueToY(scene.scale, drag.value) - (drag.edge === "top" ? top : bottom);
    if (drag.edge === "top") top += dy;
    else bottom += dy;
  } else if (drag.kind === "body") {
    const perPx = drag.hit.per_px || 1;
    const dy = scene.scale.type === "schematic"
      ? -(drag.value - drag.layer.attachment) / ((body.h ? drag.layer.limit / body.h : perPx) || 1)
      : valueToY(scene.scale, drag.value) - bottom;
    top += dy;
    bottom += dy;
    if (!drag.only) shiftAbove = dy;
  }
  const placedFrac = drag.kind === "placed" ? drag.value : null;
  return scene.shapes.map((s) => {
    const l = s.layer ? byId.get(s.layer) : undefined;
    if (s.layer !== id) {
      if (shiftAbove && l && l.kind === "xl" && l.attachment >= drag.layer.exhaust) {
        return s.type === "line" ? { ...s, y1: s.y1 + shiftAbove, y2: s.y2 + shiftAbove } : { ...s, y: s.y + shiftAbove };
      }
      return s;
    }
    if (s.type === "rect") {
      if (placedFrac !== null) {
        const x0 = body.x;
        const w = body.w ?? s.w;
        if (s.role === "unplaced") return { ...s, x: x0 + w * placedFrac, w: w * (1 - placedFrac) };
      }
      return { ...s, y: top, h: Math.max(1, bottom - top) };
    }
    if (s.type === "text") {
      const mid = (top + bottom) / 2;
      return { ...s, y: s.y + (mid - (body.y + body.h! / 2)) };
    }
    return s;
  });
}

function hatchDefs(scene: Scene) {
  const seen = new Set<string>();
  const out: React.ReactNode[] = [];
  for (const s of scene.shapes) {
    if (s.type === "rect" && s.fill?.pattern) {
      const fg = colour(scene.colors, s.fill);
      if (seen.has(fg)) continue;
      seen.add(fg);
      out.push(
        <pattern key={fg} id={`hatch-${fg.slice(1)}`} width={8} height={8} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width={8} height={8} fill={scene.colors.bg1} />
          <line x1={0} y1={0} x2={0} y2={8} stroke={fg} strokeWidth={3} />
        </pattern>,
      );
    }
  }
  return out;
}

function draw(s: Shape, colors: Record<string, string>, selected: string | null, hovered: string | null,
  byId: Map<string, LayerRow>) {
  const active = s.layer && (s.layer === selected || s.layer === hovered);
  if (s.type === "rect") {
    const fill = s.fill?.pattern ? `url(#hatch-${colour(colors, s.fill).slice(1)})` : colour(colors, s.fill);
    const isBlock = s.role === "layer" || s.role === "retention";
    const l = s.layer ? byId.get(s.layer) : undefined;
    return (
      <rect key={s.id} x={s.x} y={s.y} width={Math.max(0, s.w)} height={Math.max(0, s.h)} fill={fill}
        stroke={colour(colors, s.stroke)} strokeWidth={s.stroke?.w ?? 0} strokeDasharray={s.stroke?.dash ? "6 4" : undefined}
        className={`shape-${s.role}${active && isBlock ? " is-active" : ""}`}
        role={isBlock ? "img" : undefined}
        aria-label={isBlock && l ? `${l.display}: ${l.label}, ${Math.round(l.placed * 1000) / 10}% placed` : undefined}
      />
    );
  }
  if (s.type === "line") {
    return (
      <line key={s.id} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={colour(colors, s.stroke ?? { theme: "tx1" })}
        strokeWidth={s.stroke?.w ?? 1} strokeDasharray={s.stroke?.dash ? "8 5" : undefined} pointerEvents="none" />
    );
  }
  return (
    <text key={s.id} x={s.x} y={s.y} textAnchor={s.anchor} fill={colour(colors, s.fill ?? { theme: "tx1" })}
      pointerEvents="none" className={`shape-${s.role}`}>
      {s.runs.map((r, i) => (
        <tspan key={i} x={s.x} dy={i === 0 ? 0 : (r.s ?? s.size) * 1.25} fontSize={r.s ?? s.size}
          fontWeight={r.b ? 700 : undefined} fill={r.warn ? colors.error : undefined}>{r.t}</tspan>
      ))}
    </text>
  );
}

function LayerTip({ scene, tip, fmt }: { scene: Scene; tip: { x: number; y: number; layer: LayerRow }; fmt: (v: number) => string }) {
  const l = tip.layer;
  const p = (v: number | null) => (v === null ? "" : `${Math.round(v * 1000) / 10}%`);
  const x = Math.min(tip.x + 16, scene.frame.w - 240);
  return (
    <div className="layer-tip" role="tooltip" style={pos(scene, x, tip.y + 12)}>
      <strong>{l.display}</strong>
      <dl>
        {l.kind === "qs" && (<><dt>Cession</dt><dd>{p(l.cession)}</dd><dt>Limit per risk</dt><dd>{fmt(l.limit)}</dd>
          {l.agg_limit !== null && (<><dt>Agg limit</dt><dd>{fmt(l.agg_limit)}</dd></>)}</>)}
        {l.kind === "sl" && (<><dt>Layer</dt><dd>{p(l.limit)} xs {p(l.attachment)} EPI</dd>
          {l.amounts && (<><dt>In amounts</dt><dd>{l.amounts}</dd></>)}</>)}
        {(l.kind === "xl" || l.kind === "retention") && (<><dt>Limit</dt><dd>{fmt(l.limit)}</dd></>)}
        {l.kind === "xl" && (<><dt>Attachment</dt><dd>{fmt(l.attachment)}</dd></>)}
        {(l.kind === "xl" || l.kind === "retention") && (<><dt>Exhaust</dt><dd>{fmt(l.exhaust)}</dd></>)}
        {l.kind !== "retention" && (<><dt>Order × placed</dt><dd>{p(l.order)} × {p(l.placed)}</dd></>)}
        {l.derived.premium !== null && (<><dt>Premium (RTE)</dt><dd>{fmt(l.derived.premium)}</dd></>)}
        {l.derived.rol !== null && (<><dt>ROL</dt><dd>{p(l.derived.rol)}</dd></>)}
        {l.derived.adj_rate !== null && (<><dt>Adj. rate</dt><dd>{p(l.derived.adj_rate)}</dd></>)}
        {l.kind === "xl" && l.derived.agg_limit !== null && (<><dt>Agg limit</dt><dd>{l.derived.agg_unlimited ? "Unlimited" : fmt(l.derived.agg_limit)}</dd></>)}
        {l.reinstatements && (<><dt>Reinstatements</dt><dd>{l.reinstatements}</dd></>)}
      </dl>
    </div>
  );
}

function TitleOverlay({ scene }: { scene: Scene }) {
  const tower = useStore((s) => s.tower);
  const preview = useStore((s) => s.preview);
  const edit = useStore((s) => s.edit);
  const title = scene.shapes.find((s) => s.role === "title") as Extract<Shape, { type: "text" }> | undefined;
  const subtitle = scene.shapes.find((s) => s.role === "subtitle") as Extract<Shape, { type: "text" }> | undefined;
  if (preview) {
    return (
      <>
        {title && <div className="title-overlay title" style={titlePos(scene, title)}>{title.runs[0].t}</div>}
        {subtitle && <div className="title-overlay subtitle" style={titlePos(scene, subtitle)}>{subtitle.runs[0].t}</div>}
      </>
    );
  }
  const commit = (field: "title" | "subtitle", value: string) => {
    const v = value.trim() || null;
    if ((tower?.[field] ?? null) !== v) void edit({ type: "meta", fields: { [field]: v } }, `${field} changed`);
  };
  return (
    <>
      {title ? (
        <input key={`t-${title.runs[0].t}`} className="title-overlay title" aria-label="Slide title" defaultValue={title.runs[0].t}
          style={titlePos(scene, title)} onBlur={(e) => commit("title", e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
      ) : (
        <button type="button" className="add-title" onClick={() => commit("title", "Untitled tower")}>+ Add title</button>
      )}
      {title && (subtitle ? (
        <input key={`s-${subtitle.runs[0].t}`} className="title-overlay subtitle" aria-label="Slide subtitle"
          defaultValue={subtitle.runs[0].t} style={titlePos(scene, subtitle)} onBlur={(e) => commit("subtitle", e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
      ) : (
        <button type="button" className="add-subtitle" style={titlePos(scene, { ...title, y: title.y + 34, size: 16 })}
          onClick={() => commit("subtitle", "Subtitle")}>+ Add subtitle</button>
      ))}
    </>
  );
}

function titlePos(scene: Scene, s: Extract<Shape, { type: "text" }>): React.CSSProperties {
  const W = scene.frame.w;
  const H = scene.frame.h;
  return {
    left: `${(s.x / W) * 100}%`,
    top: `${((s.y - s.size) / H) * 100}%`,
    width: `${((W - 2 * s.x) / W) * 100}%`,
    fontSize: `${(s.size / W) * 100}cqw`,
    color: s.fill?.tint ? "var(--slide-muted)" : "var(--slide-ink)",
  };
}
