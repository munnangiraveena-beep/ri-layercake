import type { ThemeRef } from "./types";

/** Resolve a theme reference against the palette colours the engine sent. */
export function colour(colors: Record<string, string>, ref: ThemeRef | null | undefined): string {
  if (!ref) return "none";
  if (ref.status === "error") return colors.error ?? "#C0392B";
  const hex = colors[ref.theme ?? "tx1"] ?? "#000000";
  const t = ref.tint ?? 0;
  if (!t) return hex;
  const rgb = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return "#" + rgb.map((c) => Math.round(c + (255 - c) * t).toString(16).padStart(2, "0")).join("").toUpperCase();
}

export const CURRENCY: Record<string, string> = { GBP: "£", USD: "$", EUR: "€", JPY: "¥" };

export function money(currency: string, units: string, v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  const r = Math.round(v * 10) / 10;
  const s = Number.isInteger(r) ? String(r) : r.toFixed(1);
  const sym = CURRENCY[currency] ?? `${currency} `;
  return `${v < 0 ? "-" : ""}${sym}${s.replace("-", "")}${units}`;
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  const r = Math.round(v * 1000) / 10;
  return `${Number.isInteger(r) ? r : r.toFixed(1)}%`;
}
