const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
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

export interface Summary {
  total_trades: number;
  win_rate_pct: number;
  roi_pct: number;
  open_positions: number;
  kill_switch_active: boolean;
  bankroll_usdt: number;
}

export const api = {
  login: (password: string) =>
    request<{ ok: boolean }>("/api/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>("/api/logout", { method: "POST" }),
  summary: () => request<Summary>("/api/summary"),
  trades: (limit = 100) => request<Trade[]>(`/api/trades?limit=${limit}`),
  trade: (id: number) => request<Trade>(`/api/trades/${id}`),
  setKillSwitch: (active: boolean, reason?: string) =>
    request<{ ok: boolean; kill_switch_active: boolean }>("/api/kill-switch", {
      method: "POST",
      body: JSON.stringify({ active, reason }),
    }),
};

export function wsPricesUrl(symbol: string) {
  const wsBase = API_URL.replace("http", "ws");
  return `${wsBase}/ws/prices?symbol=${encodeURIComponent(symbol)}`;
}
