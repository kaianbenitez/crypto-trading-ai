function browserApiUrl() {
  if (typeof window === "undefined") return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return process.env.NEXT_PUBLIC_API_URL || window.location.origin;
}

function apiUrl() {
  return browserApiUrl().replace(/\/$/, "");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${apiUrl()}${path}`, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || res.statusText);
  }
  return res.json();
}

export interface Trade {
  id: number;
  symbol: string;
  side: string;
  strategy_name: string;
  regime: string;
  entry_price: number;
  exit_price: number | null;
  qty: number;
  stop_loss: number;
  take_profit: number;
  leverage: number;
  entry_reasoning: string[];
  indicator_snapshot: Record<string, unknown>;
  pnl_usdt: number | null;
  outcome: string | null;
  exit_reason: string | null;
  postmortem: string[];
  opened_at: string;
  closed_at: string | null;
}

export interface PositionReasoning {
  thesis: string[];
  why_accepted: string[];
  weakness: string | null;
  invalidation: string;
  past_context: string | null;
  now: string[];
  next: string[];
}

export interface TradeNarrative {
  symbol: string;
  side: string;
  strategy_name: string;
  regime: string;
  confidence: number | null;
  ev_r: number | null;
  thesis_lines: string[];
  why_accepted_lines: string[];
  weakness_line: string | null;
  entry: number;
  stop_loss: number;
  take_profit: number;
  rr: number;
  risk_pct: number | null;
  risk_usdt: number | null;
  invalidation_line: string;
  past_context_line: string | null;
  outcome: string | null;
  exit_reason: string | null;
  exit_price: number | null;
  pnl_usdt: number | null;
  r_multiple: number | null;
  held_duration: string | null;
  lesson_line: string | null;
  failure_line: string | null;
}

export interface OpenPositionDetail {
  trade: Pick<
    Trade,
    | "id"
    | "symbol"
    | "side"
    | "strategy_name"
    | "regime"
    | "entry_price"
    | "stop_loss"
    | "take_profit"
    | "qty"
    | "opened_at"
    | "indicator_snapshot"
  >;
  reasoning: PositionReasoning;
}

export interface CandlePoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlePayload {
  symbol: string;
  candles: CandlePoint[];
  overlays: {
    entry?: number;
    stop_loss?: number;
    take_profit?: number;
    side?: string;
    regime?: string;
    strategy?: string;
    trail?: Array<{ time: string; price: number; mode: string }>;
  };
}

export interface Summary {
  total_trades: number;
  win_rate_pct: number;
  roi_pct: number;
  total_pnl_usdt: number;
  open_positions: number;
  kill_switch_active: boolean;
  bankroll_usdt: number;
}

export interface LivePosition {
  symbol: string;
  mark_price: number | null;
  unrealized_pnl: number | null;
  roi_pct: number | null;
  break_even_price: number | null;
}

export interface CoinDigest {
  symbol: string;
  price_low_24h: number | null;
  price_high_24h: number | null;
  price_change_pct_24h: number | null;
  regime: string | null;
  watching_side: string | null;
  watch_low: number | null;
  watch_high: number | null;
  sentiment_score: number | null;
  sentiment_label: string | null;
  headlines: string[];
  summary: string;
  created_at: string;
}

export interface RiskStatus {
  effective_bankroll_usdt: number;
  configured_bankroll_usdt: number;
  account_equity_usdt: number | null;
  risk_pct: number;
  tier: string;
  mode: string;
  drawdown_pct: number;
  reason: string;
  created_at: string | null;
}

export interface PerformanceMetrics {
  days: number;
  bankroll_usdt: number;
  trade_count: number;
  closed_count: number;
  open_count: number;
  total_pnl_usdt: number;
  roi_pct: number;
  win_rate_pct: number;
  expectancy_r: number;
  profit_factor: number;
  max_drawdown_pct: number;
  max_consecutive_losses: number;
  distinct_symbols: number;
  reentry_count: number;
  reentry_pnl_usdt: number;
  reentry_expectancy_r: number;
  avg_estimated_cost_r: number;
  high_cost_trade_count: number;
  avg_net_r_after_estimated_cost: number;
  expectancy_after_estimated_cost_r: number;
  tiny_win_count: number;
  runner_count: number;
  runner_pnl_usdt: number;
  exit_reason_breakdown: Record<string, number>;
  by_symbol: Record<string, { pnl: number; avg_r: number; win_rate_pct: number }>;
  by_strategy: Record<string, { pnl: number; avg_r: number; win_rate_pct: number }>;
}

export interface Readiness {
  ready: boolean;
  checks: Record<string, boolean>;
  failed: string[];
}

export interface Validation {
  risk: {
    effective_bankroll_usdt: number;
    risk_pct: number;
    tier: string;
    mode: string;
    reason: string;
  };
  metrics: PerformanceMetrics;
  readiness: Readiness;
}

export interface CoinBrain {
  symbol: string;
  params: Record<string, unknown>;
  leg_stats: Record<string, unknown>;
  regime_stats: Record<string, unknown>;
  disabled_legs: string[];
  version: number;
  updated_at: string;
}

export interface AdaptiveActivityEntry {
  type: "param_change" | "trail_move";
  symbol: string;
  message: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface MarketScanStatus {
  enabled: boolean;
  status: string;
  last_scan_at?: string | null;
  scanned?: number;
  eligible?: number;
  selected_count?: number;
  selected?: string[];
  rejected?: Record<string, number>;
  error?: string;
}

export interface RosterInfo {
  active: string[];
  benched: { symbol: string; until: string }[];
  last_review: string | null;
  scan: MarketScanStatus;
}

export interface NewsStatus {
  enabled: boolean;
  provider: string;
  api_url: string;
}

export interface Changelog {
  markdown: string;
}

export interface AgentStatus {
  trading_agent: string;
  webapi: string;
  dashboard: string;
  nginx: string;
  exchange: string;
  testnet: boolean;
  symbols: string[];
  macro_regime?: string;
  kill_switch_active?: boolean;
  bankroll_usdt: number;
  checked_at: string;
}

export const api = {
  login: (password: string) =>
    request<{ ok: boolean }>("/api/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>("/api/logout", { method: "POST" }),
  summary: () => request<Summary>("/api/summary"),
  agentStatus: () => request<AgentStatus>("/api/agent-status"),
  trades: (limit = 100) => request<Trade[]>(`/api/trades?limit=${limit}`),
  trade: (id: number) => request<Trade>(`/api/trades/${id}`),
  tradeNarrative: (id: number) => request<TradeNarrative>(`/api/trades/${id}/narrative`),
  openPositionDetails: () => request<OpenPositionDetail[]>("/api/open-positions-detail"),
  livePositions: () => request<LivePosition[]>("/api/live-positions"),
  coinDigests: () => request<CoinDigest[]>("/api/coin-digests"),
  riskStatus: () => request<RiskStatus>("/api/risk-status"),
  validation: () => request<Validation>("/api/validation"),
  coinBrains: () => request<CoinBrain[]>("/api/coin-brains"),
  adaptiveActivity: (limit = 50) => request<AdaptiveActivityEntry[]>(`/api/adaptive-activity?limit=${limit}`),
  roster: () => request<RosterInfo>("/api/roster"),
  newsStatus: () => request<NewsStatus>("/api/news-status"),
  changelog: () => request<Changelog>("/api/changelog"),
  candles: (symbol: string, timeframe = "1h", limit = 120) =>
    request<CandlePayload>(`/api/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`),
  setKillSwitch: (active: boolean, reason?: string) =>
    request<{ ok: boolean; kill_switch_active: boolean }>("/api/kill-switch", {
      method: "POST",
      body: JSON.stringify({ active, reason }),
    }),
};

export function wsPricesUrl(symbol: string) {
  const wsBase = apiUrl().replace(/^http/, "ws");
  return `${wsBase}/ws/prices?symbol=${encodeURIComponent(symbol)}`;
}
