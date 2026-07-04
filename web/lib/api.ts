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
  now: string[];
  next: string[];
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
  openPositionDetails: () => request<OpenPositionDetail[]>("/api/open-positions-detail"),
  livePositions: () => request<LivePosition[]>("/api/live-positions"),
  coinDigests: () => request<CoinDigest[]>("/api/coin-digests"),
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
