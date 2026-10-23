// Value <-> y conversion using the scale the engine returned with the scene,
// so drag-to-value matches the engine's layout exactly.
import type { Scale } from "./types";

export function valueToY(s: Scale, v: number): number {
  if (s.type === "linear") return s.y_bottom - (v / s.v_max) * (s.y_bottom - s.y_top);
  if (s.type === "log") {
    if (v <= s.v_min) return s.y_bottom - s.floor * (v / s.v_min);
    const span = Math.log(s.v_max / s.v_min) || 1;
    return s.y_bottom - s.floor - (Math.log(v / s.v_min) / span) * (s.y_bottom - s.y_top - s.floor);
  }
  const b = s.breaks;
  for (let i = 0; i < b.length - 1; i++) {
    const [v0, y0] = b[i];
    const [v1, y1] = b[i + 1];
    if (v >= v0 && v <= v1 && v1 > v0) return y0 + ((y1 - y0) * (v - v0)) / (v1 - v0);
  }
  return b.length && v > b[b.length - 1][0] ? b[b.length - 1][1] : s.y_bottom;
}

export function yToValue(s: Scale, y: number): number {
  if (s.type === "linear") return ((s.y_bottom - y) / (s.y_bottom - s.y_top)) * s.v_max;
  if (s.type === "log") {
    if (y >= s.y_bottom - s.floor) return (s.v_min * (s.y_bottom - y)) / (s.floor || 1);
    const span = Math.log(s.v_max / s.v_min) || 1;
    const f = (s.y_bottom - s.floor - y) / (s.y_bottom - s.y_top - s.floor);
    return s.v_min * Math.exp(f * span);
  }
  const b = s.breaks;
  for (let i = 0; i < b.length - 1; i++) {
    const [v0, y0] = b[i];
    const [v1, y1] = b[i + 1];
    if (y <= y0 && y >= y1 && y0 !== y1) return v0 + ((v1 - v0) * (y0 - y)) / (y0 - y1);
  }
  if (!b.length) return 0;
  if (y > b[0][1]) return b[0][0];
  // Above the top: extend with the top band's rate.
  const [vA, yA] = b[b.length - 2] ?? [0, s.y_bottom];
  const [vB, yB] = b[b.length - 1];
  const rate = yA !== yB ? (vB - vA) / (yA - yB) : 1;
  return vB + (yB - y) * rate;
}

/** Snap steps 1, 2.5, 5, 10, 25, 50...: the one giving about 20 to 40 positions across the range. */
export function snapStep(range: number): number {
  if (!(range > 0)) return 1;
  const bases = [1, 2.5, 5];
  let best = 1;
  for (let exp = -3; exp <= 12; exp++) {
    for (const b of bases) {
      const step = b * 10 ** exp;
      const n = range / step;
      if (n >= 20 && n <= 40) return step;
      if (n >= 20) best = step;
    }
  }
  return best;
}

export function snap(v: number, step: number): number {
  return Math.round(v / step) * step;
}

export function topValue(s: Scale): number {
  if (s.type === "schematic") return s.breaks.length ? s.breaks[s.breaks.length - 1][0] : 0;
  return s.v_max;
}

export function fmtNum(v: number): string {
  const r = Math.round(v * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
}
