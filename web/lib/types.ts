export type ThemeRef = { theme?: string; tint?: number; status?: "error"; pattern?: "hatch"; w?: number; dash?: string };

export type Run = { t: string; b?: boolean; s?: number; warn?: boolean };

export type Shape =
  | { type: "rect"; id: string; layer?: string; x: number; y: number; w: number; h: number; fill: ThemeRef | null;
      stroke?: ThemeRef; role: string; key?: string; layers?: string[]; export?: boolean }
  | { type: "text"; id: string; layer?: string; x: number; y: number; anchor: "start" | "middle" | "end"; runs: Run[];
      size: number; fill?: ThemeRef; role: string; side?: boolean; export?: boolean }
  | { type: "line"; id: string; layer?: string; x1: number; y1: number; x2: number; y2: number; stroke?: ThemeRef;
      role: string };

export type Hit = {
  layer: string; edge: "top" | "bottom" | "body" | "placed"; x: number; y: number; w?: number; h?: number;
  x0?: number; value?: number; per_px?: number;
};

export type Scale =
  | { type: "linear"; y_bottom: number; y_top: number; v_max: number }
  | { type: "log"; y_bottom: number; y_top: number; v_max: number; v_min: number; floor: number }
  | { type: "schematic"; y_bottom: number; y_top: number; breaks: [number, number][] };

export type TableData = {
  columns: string[]; rows: string[][]; totals: string[]; layers: string[];
  box?: { x: number; y: number; w: number; h: number; row_h: number; size?: number }; col_w?: number[];
};

export type Scene = {
  schema: string; frame: { w: number; h: number; name: string }; palette: string; colors: Record<string, string>;
  shapes: Shape[]; hit: Hit[]; scale: Scale | null; table: TableData; show_table: boolean;
};

export type Fix = { label: string; op: "update" | "accept" | "view"; layer?: string; fields?: Record<string, unknown>; key?: string };

export type Diagnostic = {
  code: string; severity: "error" | "warning" | "info"; message: string; layers: string[]; fixes: Fix[];
  span?: [number, number]; key?: string;
};

export type Kind = "retention" | "qs" | "xl" | "sl";

export type Terms = {
  commission?: string; profit_commission?: string; management_expenses?: string; no_claims_bonus?: string;
  expected_loss?: number | string; sliding_scale?: { min: string; max: string; lr_low: string; lr_high: string };
};

/** Stop loss limit and attachment are loss ratios (fractions of EPI); everything else is in tower units. */
export type LayerRow = {
  id: string; kind: Kind; name: string | null; display: string; label: string; amounts: string | null;
  limit: number; attachment: number; exhaust: number; limit_amount: number | null; attachment_amount: number | null;
  placed: number; order: number; share: number; cession: number | null;
  premium: number | null; rol: number | null; adj_rate: number | null; agg_limit: number | null;
  derived: {
    premium: number | null; rol: number | null; adj_rate: number | null; agg_limit: number | null;
    agg_unlimited: boolean; payback: number | null; no_claims_bonus: number | null; commission_rate: number | null;
  };
  priced_by: "premium" | "adj_rate" | "rol" | "cession" | null;
  terms: Terms;
  effective_premium: number | null; rate_on_line: number | null; reinstatements: string | null; written: number | null;
};

export type Programme = {
  epi: number | null; counterparty_limit: number | null; arrangement: "stacked" | "side_by_side";
  cover: "per_risk" | "cat"; currency: string; units: string;
  internal_expenses: number | null; expected_loss_ratio: number | null; brokerage_xl: number | null;
  brokerage_qs: number | null; tax: number | null;
  defaults: { internal_expenses: number; brokerage_xl: number; brokerage_qs: number };
  lines: { name: string; epi: number | null; expected_loss_ratio: number | null; cession: number | null; volatility: number | null }[];
};

export type TowerJSON = {
  schema: string; currency: string; units: "" | "k" | "m" | "bn"; title?: string; subtitle?: string;
  accepted?: string[]; layers: Record<string, unknown>[];
};

export type Mapping = {
  header_row: number | null; columns: Record<string, string>; headers: string[]; width: number; fields: string[];
};

export type RenderResult = {
  tower: TowerJSON; programme: Programme; formulas: Record<string, string>; warnings: Diagnostic[]; blocking: boolean;
  scene: Scene; text: string; layers: LayerRow[]; mapping?: Mapping | null;
};

export type View = {
  scale: "schematic" | "linear" | "log";
  labels: "inside" | "side" | "auto";
  show_axis: boolean | null;
  show_retention: boolean;
  show_unplaced: boolean;
  palette: "ocean" | "slate" | "ember";
  frame: "slide_16x9" | "square" | "tall";
  table: "below" | "right" | "none";
  loss: number | null;
};

export const DEFAULT_VIEW: View = {
  scale: "schematic", labels: "auto", show_axis: null, show_retention: true, show_unplaced: true,
  palette: "ocean", frame: "slide_16x9", table: "below", loss: null,
};

export type LossRow = {
  layer: string; name: string; kind?: Kind; recovery_100: string; placed: string; recovery_placed: string;
  exhausted: boolean; reinstatement_premium: string; net: string; retained?: string; limit_used?: string; ncb?: string;
};

export type LossResult = {
  loss: { loss: string; rows: LossRow[]; totals: Record<string, string> };
  exhausted: string[];
  fills: Record<string, number>;
};

export type AggregateResult = {
  aggregate: {
    loss: string; qs_ceded: string; net_of_qs: string; loss_ratio: string; rows: LossRow[];
    qs_terms: Record<string, string>; no_claims_bonus: { layer: string; name: string; rate: string; amount: string }[];
  };
  fills: Record<string, number>;
};

export type PortfolioResult = {
  portfolio: {
    count: number; total_exposure: string; retained: string;
    layers: { layer: string; name: string; trapped: string; ceded: string; risks_reaching: number; risks_exhausting: number; max: string }[];
    risks: { id: string; exposure: string; layers: Record<string, string>; retained: string }[];
  };
};

export type WalkResult = {
  walk: {
    epi: string; result: string; result_value: number; margin: string; result_without_reinsurance: string;
    cost_of_reinsurance: string;
    steps: { key: string; label: string; amount: string; value: number; formula: string; approx: boolean;
      missing: string | null; default: boolean }[];
    before_after: BeforeAfter;
  };
  summary?: { columns: string[]; rows: string[][]; totals: string[] };
};

export type BeforeAfter = Record<"before" | "after", Record<
  "premium" | "losses" | "expenses" | "loss_ratio" | "expense_ratio" | "combined_ratio" | "result" | "margin" | "margin_on_premium", string>>;

export type RiskMetrics = {
  expected_result: number; bad_year_result: number; capital: number; margin: number; bad_year_margin: number;
  net_loss_ratio: number; roc: number | null; qs_reinsurer_margin: number | null; xl_reinsurer_margins: number[];
  placeable: boolean;
};

export type RiskLever = { key: string; label: string; unit: string; values: number[]; current: number };

export type RiskResult = {
  levers: RiskLever[];
  gross?: RiskMetrics;
  current?: RiskMetrics;
  explore?: {
    x: RiskLever; y: RiskLever | null; grid: RiskMetrics[][]; best: [number, number];
    efficient: boolean[][]; score: (number | null)[][]; weights: { loss_ratio: number; margin: number; roc: number };
    best_values: { x: number; y: number | null }; gross: RiskMetrics; current: RiskMetrics; whatif: RiskMetrics;
    calibration: { alpha: number; large_share: number[]; calibrated: boolean; layer_el: Record<string, number> };
  };
};

export type Op =
  | { type: "update"; layer: string; fields: Record<string, unknown> }
  | { type: "add_xl"; limit: number; attachment: number; placed?: number; name?: string }
  | { type: "add_retention"; amount: number }
  | { type: "add_qs"; cession: number; limit: number; agg_limit?: number }
  | { type: "add_sl"; limit: number; attachment: number }
  | { type: "programme"; fields: Record<string, unknown> }
  | { type: "terms"; layer: string; terms: Record<string, unknown> }
  | { type: "add_line"; name: string; epi: number; expected_loss_ratio?: number | null; cession?: number | null; volatility?: number | null }
  | { type: "update_line"; name: string; fields: Record<string, unknown> }
  | { type: "remove_line"; name: string }
  | { type: "set_cessions"; cessions: Record<string, number> }
  | { type: "apply_levers"; levers: Record<string, unknown> }
  | { type: "remove"; layer: string }
  | { type: "split"; layer: string; at: number }
  | { type: "merge"; a: string; b: string }
  | { type: "insert"; at: number; limit: number }
  | { type: "move"; layer: string; attachment: number; shift_above?: boolean }
  | { type: "apply_fix"; fix: Fix }
  | { type: "meta"; fields: Record<string, unknown> }
  | { type: "clear" };
