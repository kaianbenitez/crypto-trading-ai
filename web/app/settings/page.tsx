"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Bell, Flask, ShieldWarning, Warning } from "@phosphor-icons/react";
import { api, AgentStatus, RosterInfo, SettingsSnapshot, StrategyProfile } from "@/lib/api";

type DraftValue = string | number | boolean;

type FieldDef =
  | { key: string; label: string; type: "number"; step?: number; min?: number; max?: number; hint?: string }
  | { key: string; label: string; type: "text"; hint?: string }
  | { key: string; label: string; type: "select"; options: string[]; hint?: string }
  | { key: string; label: string; type: "checkbox"; hint?: string };

type SectionDef = { title: string; description: string; fields: FieldDef[] };

const SECTIONS: SectionDef[] = [
  {
    title: "Bankroll & risk",
    description: "Live bankroll source, trade sizing, drawdown caps, and risk tiers.",
    fields: [
      { key: "bankroll_usdt", label: "Bankroll (USDT)", type: "number", step: 1, min: 0, hint: "Base capital used by risk validation." },
      { key: "bankroll_mode", label: "Bankroll mode", type: "select", options: ["static", "equity"], hint: "Static uses the configured bankroll; equity follows the exchange." },
      { key: "max_risk_per_trade_pct", label: "Max risk per trade (%)", type: "number", step: 0.1, min: 0 },
      { key: "max_concurrent_positions", label: "Max concurrent positions", type: "number", step: 1, min: 0 },
      { key: "split_risk_across_slots", label: "Split risk across slots", type: "checkbox" },
      { key: "max_portfolio_risk_pct", label: "Portfolio risk cap (%)", type: "number", step: 0.1, min: 0 },
      { key: "max_same_direction_risk_pct", label: "Same-direction risk cap (%)", type: "number", step: 0.1, min: 0 },
      { key: "min_entry_risk_pct", label: "Minimum entry risk (%)", type: "number", step: 0.05, min: 0 },
      { key: "default_leverage", label: "Default leverage", type: "number", step: 1, min: 1 },
      { key: "max_leverage", label: "Max leverage", type: "number", step: 1, min: 1 },
      { key: "confidence_risk_scaling", label: "Scale risk by confidence", type: "checkbox" },
      { key: "confidence_full_risk_at", label: "Full-risk confidence", type: "number", step: 0.01, min: 0, max: 1 },
      { key: "max_daily_drawdown_pct", label: "Daily drawdown cap (%)", type: "number", step: 0.1, min: 0 },
      { key: "risk_tier_mode", label: "Risk tier mode", type: "select", options: ["auto", "fixed"] },
      { key: "risk_base_pct", label: "Base risk (%)", type: "number", step: 0.1, min: 0 },
      { key: "risk_recovery_pct", label: "Recovery risk (%)", type: "number", step: 0.1, min: 0 },
      { key: "risk_drawdown_pct", label: "Drawdown risk (%)", type: "number", step: 0.1, min: 0 },
      { key: "risk_proven_pct", label: "Proven risk (%)", type: "number", step: 0.1, min: 0 },
      { key: "risk_proven_min_days", label: "Validation days", type: "number", step: 1, min: 1 },
      { key: "risk_proven_min_trades", label: "Validation trades", type: "number", step: 1, min: 1 },
      { key: "risk_proven_min_expectancy_r", label: "Min expectancy (R)", type: "number", step: 0.01 },
      { key: "risk_proven_min_net_r_after_cost", label: "Min net EV after cost (R)", type: "number", step: 0.01 },
      { key: "risk_proven_min_profit_factor", label: "Min profit factor", type: "number", step: 0.01, min: 0 },
      { key: "risk_proven_max_drawdown_pct", label: "Max drawdown (%)", type: "number", step: 0.1, min: 0 },
      { key: "risk_recovery_loss_streak_trigger", label: "Recovery loss streak", type: "number", step: 1, min: 1 },
      { key: "reentry_max_trades_per_symbol_per_day", label: "Re-entry cap per symbol/day", type: "number", step: 1, min: 0 },
      { key: "reentry_min_ev_multiplier", label: "Re-entry EV multiplier", type: "number", step: 0.1, min: 0 },
    ],
  },
  {
    title: "Scanner & roster",
    description: "Universe scan, shortlist sizing, filters, and coin coverage.",
    fields: [
      { key: "dynamic_market_scan", label: "Dynamic market scan", type: "checkbox" },
      { key: "market_scan_top_n", label: "Shortlist size", type: "number", step: 1, min: 1 },
      { key: "market_scan_active_symbols", label: "Active roster size", type: "number", step: 1, min: 1 },
      { key: "market_scan_refresh_minutes", label: "Scan refresh (min)", type: "number", step: 1, min: 1 },
      { key: "market_scan_min_quote_volume", label: "Min quote volume", type: "number", step: 1, min: 0 },
      { key: "market_scan_max_spread_pct", label: "Max spread (%)", type: "number", step: 0.01, min: 0 },
      { key: "market_scan_max_abs_24h_change_pct", label: "Max 24h move (%)", type: "number", step: 0.1, min: 0 },
      { key: "market_scan_include_fixed_majors", label: "Pin fixed majors", type: "checkbox" },
      { key: "market_scan_fixed_majors", label: "Fixed majors", type: "text", hint: "Comma-separated symbols, e.g. BTC/USDT,ETH/USDT,SOL/USDT" },
      { key: "market_scan_require_market_cap_rank", label: "Require market-cap rank", type: "checkbox" },
      { key: "market_scan_min_market_cap_rank", label: "Min market-cap rank", type: "number", step: 1, min: 1 },
      { key: "market_scan_use_mainnet_liquidity", label: "Use mainnet liquidity", type: "checkbox" },
      { key: "market_scan_exclude_symbols", label: "Excluded symbols", type: "text", hint: "Comma-separated symbols to skip." },
      { key: "market_scan_news_nudge_enabled", label: "News nudges shortlist", type: "checkbox" },
      { key: "market_scan_news_nudge_weight", label: "News shortlist weight", type: "number", step: 0.01, min: 0 },
    ],
  },
  {
    title: "Strategy & exits",
    description: "Active profile, partial take-profit, and trailing behavior.",
    fields: [
      { key: "strategy_profile", label: "Strategy profile", type: "select", options: ["baseline_simple", "guarded_agentic", "full_agentic", "smc_observe", "memory_observe"] },
      { key: "enable_partial_take_profit", label: "Enable partial TP", type: "checkbox" },
      { key: "partial_take_profit_pct", label: "Partial TP size", type: "number", step: 0.01, min: 0, max: 1 },
      { key: "partial_take_profit_r", label: "Partial TP at (R)", type: "number", step: 0.01, min: 0 },
      { key: "enable_trailing_take_profit", label: "Enable trailing TP", type: "checkbox" },
      { key: "tp_trail_activation_r", label: "TP trail activation (R)", type: "number", step: 0.01, min: 0 },
      { key: "tp_trail_min_locked_r", label: "Min locked R", type: "number", step: 0.01, min: 0 },
      { key: "tp_trail_min_ev_r", label: "Min EV for runner", type: "number", step: 0.01, min: 0 },
      { key: "trail_activation_r", label: "Stop trail activation (R)", type: "number", step: 0.01, min: 0 },
      { key: "trail_atr_mult", label: "ATR trail multiplier", type: "number", step: 0.1, min: 0 },
      { key: "trail_high_vol_atr_ratio", label: "High-vol ATR ratio", type: "number", step: 0.1, min: 0 },
      { key: "trail_chandelier_lookback", label: "Chandelier lookback", type: "number", step: 1, min: 1 },
      { key: "trail_chandelier_atr_mult", label: "Chandelier ATR multiplier", type: "number", step: 0.1, min: 0 },
      { key: "trail_structure_lookback", label: "Structure lookback", type: "number", step: 1, min: 1 },
      { key: "trail_min_move_pct", label: "Min stop move (%)", type: "number", step: 0.0001, min: 0 },
    ],
  },
  {
    title: "News & alerts",
    description: "Sentiment nudges, Telegram behavior, and feed selection.",
    fields: [
      { key: "news_enabled", label: "Enable news", type: "checkbox" },
      { key: "news_provider", label: "News provider", type: "text" },
      { key: "news_confidence_nudge_pct", label: "News confidence nudge (%)", type: "number", step: 0.01, min: 0 },
      { key: "telegram_show_close_lessons", label: "Send close lessons in Telegram", type: "checkbox" },
      { key: "coin_digest_hour_ph", label: "Daily digest hour (PH)", type: "number", step: 1, min: 0, max: 23 },
    ],
  },
];

function toDraftValue(field: FieldDef, value: unknown): DraftValue {
  if (field.type === "checkbox") return Boolean(value);
  if (typeof value === "number" || typeof value === "string") return value;
  return field.type === "number" ? 0 : "";
}

function parseDraftValue(field: FieldDef, value: DraftValue): DraftValue {
  if (field.type === "checkbox") return Boolean(value);
  if (field.type === "number") {
    const num = typeof value === "number" ? value : Number(value);
    return Number.isFinite(num) ? num : 0;
  }
  return String(value ?? "");
}

function FieldEditor({
  field,
  value,
  onChange,
}: {
  field: FieldDef;
  value: DraftValue;
  onChange: (key: string, value: DraftValue) => void;
}) {
  const base = "mt-2 w-full border border-[#304250] bg-[#09131a] px-3 py-2 text-[12px] text-[#dbe6ef] outline-none transition focus:border-[#3b8cff]";
  const label = <div className="text-[12px] font-semibold text-[#dce5ed]">{field.label}</div>;
  const hint = field.hint ? <div className="mt-1 text-[10px] text-[#8091a0]">{field.hint}</div> : null;

  return (
    <label className="block">
      {label}
      {field.type === "checkbox" ? (
        <div className="mt-2 flex items-center gap-3 rounded border border-[#304250] bg-[#09131a] px-3 py-2">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(field.key, e.target.checked)}
            className="h-4 w-4 accent-[#3b8cff]"
          />
          <span className="text-[12px] text-[#b8c6d0]">{Boolean(value) ? "Enabled" : "Disabled"}</span>
        </div>
      ) : field.type === "select" ? (
        <select
          value={String(value ?? "")}
          onChange={(e) => onChange(field.key, e.target.value)}
          className={base}
        >
          {field.options.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ) : field.type === "number" ? (
        <input
          type="number"
          step={field.step ?? 1}
          min={field.min}
          max={field.max}
          value={typeof value === "number" ? value : Number(value || 0)}
          onChange={(e) => onChange(field.key, e.target.value === "" ? 0 : Number(e.target.value))}
          className={base}
        />
      ) : (
        <input
          type="text"
          value={String(value ?? "")}
          onChange={(e) => onChange(field.key, e.target.value)}
          className={base}
        />
      )}
      {hint}
    </label>
  );
}

function SectionCard({
  section,
  draft,
  onChange,
}: {
  section: SectionDef;
  draft: Record<string, DraftValue>;
  onChange: (key: string, value: DraftValue) => void;
}) {
  return (
    <section className="border border-[#1a303b] bg-[#071118]">
      <div className="border-b border-[#1a303b] px-4 py-3">
        <h2 className="text-[13px] font-semibold">{section.title}</h2>
        <p className="mt-1 text-[10px] text-[#8595a1]">{section.description}</p>
      </div>
      <div className="grid grid-cols-2 gap-4 px-4 py-4">
        {section.fields.map((field) => (
          <FieldEditor
            key={field.key}
            field={field}
            value={draft[field.key] ?? (field.type === "checkbox" ? false : field.type === "number" ? 0 : "")}
            onChange={onChange}
          />
        ))}
      </div>
    </section>
  );
}

function SettingsPageContent() {
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [roster, setRoster] = useState<RosterInfo | null>(null);
  const [profile, setProfile] = useState<StrategyProfile | null>(null);
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<Record<string, DraftValue>>({});
  const [statusError, setStatusError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      Promise.all([api.agentStatus(), api.roster(), api.strategyProfile(), api.settings()])
        .then(([nextAgent, nextRoster, nextProfile, nextSnapshot]) => {
          if (!active) return;
          setAgent(nextAgent);
          setRoster(nextRoster);
          setProfile(nextProfile);
          setSnapshot(nextSnapshot);
          const nextDraft: Record<string, DraftValue> = {};
          for (const section of SECTIONS) {
            for (const field of section.fields) {
              nextDraft[field.key] = toDraftValue(field, nextSnapshot.values[field.key]);
            }
          }
          setDraft(nextDraft);
          setStatusError(false);
          setMessage(null);
        })
        .catch(() => active && setStatusError(true));
    };
    load();
    const timer = window.setInterval(load, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const summaryPills = useMemo(() => [
    { label: "Editable groups", value: String(SECTIONS.length) },
    { label: "Dynamic roster", value: String(roster?.active?.length ?? 0) },
    { label: "Active profile", value: profile?.profile ?? "—" },
    { label: "News", value: agent?.testnet ? "Testnet" : "Live" },
  ], [agent, profile, roster]);

  const onChange = (key: string, value: DraftValue) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, DraftValue> = {};
      for (const section of SECTIONS) {
        for (const field of section.fields) {
          payload[field.key] = parseDraftValue(field, draft[field.key] ?? (field.type === "checkbox" ? false : ""));
        }
      }
      const result = await api.updateSettings(payload);
      setSnapshot({ updated_at: result.updated_at, values: result.values });
      setMessage("Saved to runtime_settings.json. Live code will pick it up on the next read.");
    } catch {
      setMessage("Could not save settings.");
    } finally {
      setSaving(false);
    }
  };

  const onReset = () => {
    if (!snapshot) return;
    const nextDraft: Record<string, DraftValue> = {};
    for (const section of SECTIONS) {
      for (const field of section.fields) {
        nextDraft[field.key] = toDraftValue(field, snapshot.values[field.key]);
      }
    }
    setDraft(nextDraft);
    setMessage("Reset to the last loaded runtime snapshot.");
  };

  return (
    <div className="min-h-screen bg-[#04090e] text-[#dce5ed]">
      <main className="px-6 py-6">
        <header className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-[22px] font-semibold">Settings</h1>
            <p className="mt-1 text-[12px] text-[#8495a3]">Live settings editor for risk, scanner, strategy, and alert behavior.</p>
          </div>
          <div className="flex items-center gap-4 text-[11px] text-[#9ba8b4]">
            <span>Environment <b className="ml-2 rounded bg-[#164d2d] px-2 py-1 text-[#6ee392]">{agent?.testnet === false ? "LIVE" : "TESTNET"}</b></span>
            <span>Health <b className={statusError ? "ml-2 text-[#e4b63e]" : "ml-2 text-[#6ee392]"}>● {statusError ? "API UNAVAILABLE" : "ALL SYSTEMS OPERATIONAL"}</b></span>
            <Bell size={18} />
          </div>
        </header>

        <section className="mt-4 grid grid-cols-4 border border-[#1c303b] bg-[#071118]">
          {summaryPills.map((pill, index) => (
            <div key={pill.label} className={`border-r border-[#1c303b] px-4 py-3 ${index === 0 ? "border-t-2 border-t-[#3186ff]" : ""} last:border-r-0`}>
              <div className="text-[10px] text-[#9aa8b2]">{pill.label}</div>
              <div className="mt-2 text-[18px] font-semibold">{pill.value}</div>
            </div>
          ))}
        </section>

        <section className="mt-4 border border-[#1a303b] bg-[#071118]">
          <div className="flex items-center justify-between border-b border-[#1a303b] px-4 py-3">
            <div>
              <h2 className="text-[13px] font-semibold">What you can configure here</h2>
              <p className="mt-1 text-[10px] text-[#8495a3]">These controls persist to the runtime settings file. No API credentials or exchange keys are edited here.</p>
            </div>
            <div className="flex items-center gap-3 text-[11px]">
              <button onClick={onReset} className="border border-[#304250] px-3 py-2 text-[#dbe5ed]">Reset</button>
              <button onClick={onSave} disabled={saving} className="border border-[#3b8cff] bg-[#0c2440] px-3 py-2 text-[#7fc7ff] disabled:opacity-50">{saving ? "Saving…" : "Save settings"}</button>
            </div>
          </div>
          {message && <div className="border-b border-[#1a303b] px-4 py-2 text-[11px] text-[#eab83c]">{message}</div>}
          <div className="grid gap-4 p-4">
            {SECTIONS.map((section) => <SectionCard key={section.title} section={section} draft={draft} onChange={onChange} />)}
          </div>
        </section>

        <div className="mt-4 grid grid-cols-[1.2fr_1fr] gap-4">
          <section className="border border-[#1a303b] bg-[#071118] p-4">
            <div className="flex items-center gap-3">
              <ShieldWarning size={18} />
              <h2 className="text-[13px] font-semibold">Live roster snapshot</h2>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-3 text-[11px]">
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Shortlisted</div>
                <div className="mt-2 text-[18px] font-semibold text-[#45dd84]">{roster?.active.length ?? "—"}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Benched</div>
                <div className="mt-2 text-[18px] font-semibold">{roster?.benched.length ?? "—"}</div>
              </div>
              <div className="rounded border border-[#213443] bg-[#09131a] p-3">
                <div className="text-[#82939f]">Scanner</div>
                <div className="mt-2 text-[18px] font-semibold">{roster?.scan.status ?? "—"}</div>
              </div>
            </div>
          </section>

          <section className="border border-[#1a303b] bg-[#071118] p-4">
            <div className="flex items-center gap-3">
              <Flask size={18} />
              <h2 className="text-[13px] font-semibold">Current live profile</h2>
            </div>
            <div className="mt-4 grid gap-3 text-[11px]">
              <div><span className="text-[#82939f]">Active profile:</span> <b className="text-[#43aaff]">{profile?.profile ?? "—"}</b></div>
              <div><span className="text-[#82939f]">Decision-active modules:</span> <b>{profile?.decision_active.length ?? "—"}</b></div>
              <div><span className="text-[#82939f]">Observe-only modules:</span> <b>{profile?.observe_only.length ?? "—"}</b></div>
              <div><span className="text-[#82939f]">Telegram close lessons:</span> <b>{String(Boolean(draft.telegram_show_close_lessons))}</b></div>
            </div>
            <Link href="/strategy" className="mt-4 inline-flex text-[11px] text-[#7fc7ff]">Open strategy breakdown →</Link>
          </section>
        </div>

        <section className="mt-4 border border-[#47272a] bg-[#2a1012] p-4">
          <div className="flex items-center gap-3">
            <Warning size={18} color="#ff555e" />
            <div>
              <h2 className="text-[13px] font-semibold text-[#ff7a7f]">Danger zone</h2>
              <p className="mt-1 text-[11px] text-[#c18f95]">Kill-switch actions still happen elsewhere on the dashboard. Settings here only covers runtime configuration.</p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default function SettingsPage() {
  return <SettingsPageContent />;
}
