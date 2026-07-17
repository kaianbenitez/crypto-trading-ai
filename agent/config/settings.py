import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv

load_dotenv()

_RUNTIME_SETTINGS_PATH = Path(
    os.getenv("RUNTIME_SETTINGS_PATH", str(Path(__file__).resolve().parents[2] / "runtime_settings.json"))
)
_RUNTIME_SETTINGS_LOCK = RLock()
_RUNTIME_SETTINGS_CACHE: dict[str, object] = {"mtime": None, "values": {}}


@dataclass
class Settings:
    # Binance
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    binance_testnet: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # Bybit
    bybit_api_key: str = os.getenv("BYBIT_API_KEY", "")
    bybit_api_secret: str = os.getenv("BYBIT_API_SECRET", "")
    bybit_testnet: bool = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

    # Which exchange to use: "binance" or "bybit"
    exchange: str = os.getenv("EXCHANGE", "binance")

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_allowed_user_ids: str = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    telegram_show_close_lessons: bool = os.getenv("TELEGRAM_SHOW_CLOSE_LESSONS", "false").lower() == "true"

    bankroll_usdt: float = float(os.getenv("BANKROLL_USDT", "1000"))
    bankroll_mode: str = os.getenv("BANKROLL_MODE", "static").lower()  # static | equity
    bankroll_compounding: bool = os.getenv("BANKROLL_COMPOUNDING", "false").lower() == "true"
    bankroll_min_usdt: float = float(os.getenv("BANKROLL_MIN_USDT", "50"))
    bankroll_max_usdt: float = float(os.getenv("BANKROLL_MAX_USDT", "0"))  # 0 = no explicit cap
    bankroll_sync_interval_sec: int = int(os.getenv("BANKROLL_SYNC_INTERVAL_SEC", "900"))
    # Warn (log + surface in metrics) when the configured bankroll and live
    # exchange equity diverge by more than this %, since every %-based
    # validation gate is only meaningful if they're consistent.
    bankroll_divergence_warn_pct: float = float(os.getenv("BANKROLL_DIVERGENCE_WARN_PCT", "20"))

    max_risk_per_trade_pct: float = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "1.5"))
    max_daily_drawdown_pct: float = float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "3"))
    max_concurrent_positions: int = int(os.getenv("MAX_CONCURRENT_POSITIONS", "2"))
    split_risk_across_slots: bool = os.getenv("SPLIT_RISK_ACROSS_SLOTS", "true").lower() == "true"
    max_portfolio_risk_pct: float = float(os.getenv("MAX_PORTFOLIO_RISK_PCT", "1.5"))  # 0 = use active risk tier
    # Below the portfolio cap by default: alts are heavily BTC-correlated, so
    # two same-direction alt positions are effectively one levered BTC-beta bet.
    max_same_direction_risk_pct: float = float(os.getenv("MAX_SAME_DIRECTION_RISK_PCT", "1.0"))  # 0 = portfolio cap
    min_entry_risk_pct: float = float(os.getenv("MIN_ENTRY_RISK_PCT", "0.25"))
    min_stop_cost_multiple: float = float(os.getenv("MIN_STOP_COST_MULTIPLE", "5"))
    default_leverage: int = int(os.getenv("DEFAULT_LEVERAGE", "3"))
    max_leverage: int = int(os.getenv("MAX_LEVERAGE", "5"))
    # "net" = wins offset losses (standard daily-drawdown definition);
    # "losses_only" = gross losses trip the kill switch even on a net-green day.
    daily_drawdown_mode: str = os.getenv("DAILY_DRAWDOWN_MODE", "net")
    # Scale position risk down (never up) for low-confidence signals: full tier
    # risk at/above confidence_full_risk_at, proportionally less below it.
    confidence_risk_scaling: bool = os.getenv("CONFIDENCE_RISK_SCALING", "true").lower() == "true"
    confidence_full_risk_at: float = float(os.getenv("CONFIDENCE_FULL_RISK_AT", "0.6"))

    taker_fee_pct: float = float(os.getenv("TAKER_FEE_PCT", "0.05"))
    slippage_pct: float = float(os.getenv("SLIPPAGE_PCT", "0.03"))
    min_live_ev_r: float = float(os.getenv("MIN_LIVE_EV_R", "0.25"))
    min_edge_after_cost_r: float = float(os.getenv("MIN_EDGE_AFTER_COST_R", "0.15"))
    news_confidence_nudge_pct: float = float(os.getenv("NEWS_CONFIDENCE_NUDGE_PCT", "0.03"))

    # Strategy profile: which modules may affect a trade decision.
    #   baseline_simple (default) — base signal + MTF + cost/risk gates only;
    #     SMC/news/memory/adaptive observe & log but cannot change the decision.
    #   full_agentic — the full stack (current behavior).
    #   smc_observe / memory_observe — baseline with extra ablation logging.
    # See agent/strategy/profiles.py.
    strategy_profile: str = os.getenv("STRATEGY_PROFILE", "baseline_simple")

    risk_tier_mode: str = os.getenv("RISK_TIER_MODE", "auto").lower()  # auto | fixed
    risk_base_pct: float = float(os.getenv("RISK_BASE_PCT", "1.0"))
    risk_recovery_pct: float = float(os.getenv("RISK_RECOVERY_PCT", "0.75"))
    risk_drawdown_pct: float = float(os.getenv("RISK_DRAWDOWN_PCT", "0.5"))
    risk_proven_pct: float = float(os.getenv("RISK_PROVEN_PCT", "1.5"))
    risk_recovery_drawdown_pct: float = float(os.getenv("RISK_RECOVERY_DRAWDOWN_PCT", "2.0"))
    risk_drawdown_trigger_pct: float = float(os.getenv("RISK_DRAWDOWN_TRIGGER_PCT", "5.0"))
    risk_proven_min_trades: int = int(os.getenv("RISK_PROVEN_MIN_TRADES", "50"))
    # Raw floor is secondary to the cost-adjusted gate below — kept mainly so a
    # strategy can't "pass" on cost-adjusted terms while its raw edge is trivial.
    risk_proven_min_expectancy_r: float = float(os.getenv("RISK_PROVEN_MIN_EXPECTANCY_R", "0.15"))
    # Primary expectancy gate: must clear real trading costs, not just be positive.
    risk_proven_min_net_r_after_cost: float = float(os.getenv("RISK_PROVEN_MIN_NET_R_AFTER_COST", "0.10"))
    risk_proven_min_profit_factor: float = float(os.getenv("RISK_PROVEN_MIN_PROFIT_FACTOR", "1.3"))
    risk_proven_max_drawdown_pct: float = float(os.getenv("RISK_PROVEN_MAX_DRAWDOWN_PCT", "8.0"))
    risk_proven_min_symbols: int = int(os.getenv("RISK_PROVEN_MIN_SYMBOLS", "3"))
    # Concentration: promotion must not depend on one lucky coin.
    risk_proven_max_top_coin_pct: float = float(os.getenv("RISK_PROVEN_MAX_TOP_COIN_PCT", "50"))
    # Calendar-time floor: N trades in one lucky week can't promote.
    risk_proven_min_days: int = int(os.getenv("RISK_PROVEN_MIN_DAYS", "30"))
    # Per-leg (strategy_name + regime) minimum sample before that leg's own
    # readiness can be considered — deliberately looser than the global floor
    # since it's evaluated per leg, not overall.
    risk_proven_min_trades_per_leg: int = int(os.getenv("RISK_PROVEN_MIN_TRADES_PER_LEG", "30"))
    # Consecutive-loss streak that triggers the "recovery" (reduced-size) tier.
    # 2 is noise for a real >=50% win-rate system (happens ~1-in-5 stretches);
    # default raised so recovery reflects a real signal, not variance.
    risk_recovery_loss_streak_trigger: int = int(os.getenv("RISK_RECOVERY_LOSS_STREAK_TRIGGER", "3"))

    # Timestamp of the last strategy-logic change (ISO date). Trades opened
    # before this date used different entry rules — filter them out when
    # evaluating the current logic so an old regime's trades don't dilute
    # the readiness-gate stats. Update this string whenever trend/mean-reversion
    # signal logic changes.
    strategy_epoch: str = os.getenv("STRATEGY_EPOCH", "2026-07-13")

    reentry_max_trades_per_symbol_per_day: int = int(os.getenv("REENTRY_MAX_TRADES_PER_SYMBOL_PER_DAY", "3"))
    reentry_min_ev_multiplier: float = float(os.getenv("REENTRY_MIN_EV_MULTIPLIER", "1.5"))

    # Deprecated: CryptoPanic's free tier was discontinued/paywalled. Left
    # here only so an old .env with this var set doesn't break; unused by
    # agent.fundamental.news_sentiment, which now uses marketaux.com.
    cryptopanic_api_key: str = os.getenv("CRYPTOPANIC_API_KEY", "")
    coin_digest_hour_ph: int = int(os.getenv("COIN_DIGEST_HOUR_PH", "21"))  # 9 PM PHT ≈ start of a 9-5 Eastern workday

    # News context (marketaux.com) — display/sentiment-nudge only, never a
    # trading signal on its own. Degrades to "no data" on any failure;
    # trading is never blocked by this. Free tier is 100 requests/day —
    # keep total daily call volume (digest + any future per-position polling)
    # well under that.
    # cryptocurrency.cv (the prior provider) went dark (HTTP 402
    # "DEPLOYMENT_DISABLED") — migrated 2026-07.
    news_enabled: bool = os.getenv("NEWS_ENABLED", "true").lower() == "true"
    news_provider: str = os.getenv("NEWS_PROVIDER", "marketaux")
    news_api_url: str = os.getenv("NEWS_API_URL", "https://api.marketaux.com/v1/news/all")
    marketaux_api_key: str = os.getenv("MARKETAUX_API_KEY", "")
    news_timeout_sec: int = int(os.getenv("NEWS_TIMEOUT_SEC", "8"))
    news_max_headlines: int = int(os.getenv("NEWS_MAX_HEADLINES", "5"))

    # Rolling news-sentiment refresh (agent/fundamental/news_refresh.py) —
    # replaces the old once-daily digest fetch as the source of sentiment
    # freshness. Two lanes so the whole roster stays continuously refreshed
    # instead of one daily burst, while staying under the 100/day free quota:
    # open positions get an individual call each on their own cadence; the
    # active roster is refreshed in small batches on a separate, tighter
    # cadence. At defaults (2 positions hourly + 3-coin batches every 30 min)
    # this uses roughly 48 + 48 = 96 calls/day.
    news_position_refresh_minutes: int = int(os.getenv("NEWS_POSITION_REFRESH_MINUTES", "60"))
    news_roster_refresh_minutes: int = int(os.getenv("NEWS_ROSTER_REFRESH_MINUTES", "30"))
    news_roster_batch_size: int = int(os.getenv("NEWS_ROSTER_BATCH_SIZE", "3"))

    # Sentiment nudge on market-scan shortlisting (agent/adapt/roster.py) —
    # unlike apply_sentiment_adjustment (a confidence nudge on trades already
    # selected), this changes WHICH coins even become candidates. Default OFF:
    # this is a bigger behavior change than a confidence tweak, and should be
    # watched/validated before it's live. Reuses the same cached CoinDigest
    # data the rolling refresh job already maintains — zero extra API cost.
    market_scan_news_nudge_enabled: bool = os.getenv("MARKET_SCAN_NEWS_NUDGE_ENABLED", "false").lower() == "true"
    market_scan_news_nudge_weight: float = float(os.getenv("MARKET_SCAN_NEWS_NUDGE_WEIGHT", "0.05"))

    # Exit-management defaults for new trades. The orchestrator copies these
    # into each trade's parameter snapshot so the Settings page can tune
    # partial TP and trailing behavior without editing code.
    enable_partial_take_profit: bool = os.getenv("ENABLE_PARTIAL_TAKE_PROFIT", "true").lower() == "true"
    partial_take_profit_pct: float = float(os.getenv("PARTIAL_TAKE_PROFIT_PCT", "0.33"))
    partial_take_profit_r: float = float(os.getenv("PARTIAL_TAKE_PROFIT_R", "1.5"))
    enable_trailing_take_profit: bool = os.getenv("ENABLE_TRAILING_TAKE_PROFIT", "true").lower() == "true"
    trail_activation_r: float = float(os.getenv("TRAIL_ACTIVATION_R", "1.0"))
    trail_atr_mult: float = float(os.getenv("TRAIL_ATR_MULT", "2.2"))
    trail_high_vol_atr_ratio: float = float(os.getenv("TRAIL_HIGH_VOL_ATR_RATIO", "1.8"))
    trail_chandelier_lookback: int = int(os.getenv("TRAIL_CHANDELIER_LOOKBACK", "22"))
    trail_chandelier_atr_mult: float = float(os.getenv("TRAIL_CHANDELIER_ATR_MULT", "3.0"))
    trail_structure_lookback: int = int(os.getenv("TRAIL_STRUCTURE_LOOKBACK", "5"))
    trail_min_move_pct: float = float(os.getenv("TRAIL_MIN_MOVE_PCT", "0.0005"))
    tp_trail_activation_r: float = float(os.getenv("TP_TRAIL_ACTIVATION_R", "1.6"))
    tp_trail_min_locked_r: float = float(os.getenv("TP_TRAIL_MIN_LOCKED_R", "0.5"))
    tp_trail_min_ev_r: float = float(os.getenv("TP_TRAIL_MIN_EV_R", "0.35"))

    # SMC swing-structure (BOS/CHoCH) — display/alert only, never a gate or
    # confidence input (see agent/analysis/smc_structure.py). Checked on its
    # own cadence per open position, independent of the 60s main loop, since
    # 1h swing structure doesn't change fast enough to need checking every
    # cycle. A Telegram alert fires only for a fresh CHoCH against the open
    # position's own side — a BOS (continuation) never pings.
    smc_structure_enabled: bool = os.getenv("SMC_STRUCTURE_ENABLED", "true").lower() == "true"
    smc_structure_pivot_size: int = int(os.getenv("SMC_STRUCTURE_PIVOT_SIZE", "50"))
    smc_structure_check_minutes: int = int(os.getenv("SMC_STRUCTURE_CHECK_MINUTES", "15"))

    # Dynamic two-stage market scanner (agent/adapt/roster.py). Stage 1 is one
    # cheap fetch_tickers() call across the whole exchange; only the top N
    # shortlisted symbols get the full indicator/MTF/EV stack (stage 2).
    dynamic_market_scan: bool = os.getenv("DYNAMIC_MARKET_SCAN", "true").lower() == "true"
    market_scan_top_n: int = int(os.getenv("MARKET_SCAN_TOP_N", "30"))
    market_scan_active_symbols: int = int(os.getenv("MARKET_SCAN_ACTIVE_SYMBOLS", os.getenv("MARKET_SCAN_TOP_N", "30")))
    market_scan_min_quote_volume: float = float(os.getenv("MARKET_SCAN_MIN_QUOTE_VOLUME", "50000000"))
    market_scan_max_spread_pct: float = float(os.getenv("MARKET_SCAN_MAX_SPREAD_PCT", "0.15"))
    market_scan_refresh_minutes: int = int(os.getenv("MARKET_SCAN_REFRESH_MINUTES", "60"))
    market_scan_exclude_symbols: str = os.getenv("MARKET_SCAN_EXCLUDE_SYMBOLS", "USDC/USDT,TUSD/USDT,FDUSD/USDT")
    market_scan_include_fixed_majors: bool = os.getenv("MARKET_SCAN_INCLUDE_FIXED_MAJORS", "true").lower() == "true"
    market_scan_fixed_majors: str = os.getenv("MARKET_SCAN_FIXED_MAJORS", "BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,ADA/USDT")

    # Market-cap/rank filter (CoinGecko, free/no-key) — excludes micro-caps and
    # synthetic index/dominance products (e.g. BTCDOM) that can pass a pure
    # volume filter but aren't real coins or aren't established enough to
    # trust. Degrades to volume-only filtering if the API is unavailable.
    market_scan_require_market_cap_rank: bool = os.getenv("MARKET_SCAN_REQUIRE_MARKET_CAP_RANK", "true").lower() == "true"
    market_scan_min_market_cap_rank: int = int(os.getenv("MARKET_SCAN_MIN_MARKET_CAP_RANK", "150"))
    market_scan_market_cap_api_url: str = os.getenv(
        "MARKET_SCAN_MARKET_CAP_API_URL", "https://api.coingecko.com/api/v3/coins/markets"
    )
    market_scan_market_cap_refresh_hours: int = int(os.getenv("MARKET_SCAN_MARKET_CAP_REFRESH_HOURS", "12"))

    # On testnet, the exchange's own ticker volume/spread is inflated/weird
    # (thin, artificial liquidity), so ranking off it can shortlist symbols
    # that wouldn't make sense as real trades. When true and exchange is
    # Binance, the scanner instead sources quote volume/spread/24h change
    # from Binance's MAINNET public tickers (no keys needed, read-only) for
    # candidate selection/ranking only — order placement/execution is
    # unaffected and still goes through the configured (testnet) adapter.
    # Falls back to the adapter's own tickers if the mainnet fetch fails.
    market_scan_use_mainnet_liquidity: bool = os.getenv("MARKET_SCAN_USE_MAINNET_LIQUIDITY", "true").lower() == "true"
    # Reject symbols with an abnormal 24h move (event-driven spikes/crashes)
    # by default — not representative of the trend/mean-reversion baseline
    # this bot trades, regardless of how liquid they are.
    market_scan_max_abs_24h_change_pct: float = float(os.getenv("MARKET_SCAN_MAX_ABS_24H_CHANGE_PCT", "35"))
    # Off by default — single-letter bases (e.g. "M/USDT") aren't inherently
    # bad, but this is available if they turn out to be noisy in practice.
    market_scan_exclude_single_letter_bases: bool = os.getenv("MARKET_SCAN_EXCLUDE_SINGLE_LETTER_BASES", "false").lower() == "true"

    # Extra cost/edge gates layered on top of MIN_EDGE_AFTER_COST_R — these
    # add rejection criteria only, they never change position size.
    max_estimated_cost_r: float = float(os.getenv("MAX_ESTIMATED_COST_R", "0.20"))
    min_net_ev_after_cost_r: float = float(os.getenv("MIN_NET_EV_AFTER_COST_R", "0.25"))
    min_expected_reward_cost_multiple: float = float(os.getenv("MIN_EXPECTED_REWARD_COST_MULTIPLE", "5"))

    _runtime_override_fields = {
        "bankroll_usdt",
        "bankroll_mode",
        "bankroll_compounding",
        "bankroll_min_usdt",
        "bankroll_max_usdt",
        "max_risk_per_trade_pct",
        "max_daily_drawdown_pct",
        "max_concurrent_positions",
        "split_risk_across_slots",
        "max_portfolio_risk_pct",
        "max_same_direction_risk_pct",
        "min_entry_risk_pct",
        "min_stop_cost_multiple",
        "default_leverage",
        "max_leverage",
        "daily_drawdown_mode",
        "confidence_risk_scaling",
        "confidence_full_risk_at",
        "taker_fee_pct",
        "slippage_pct",
        "min_live_ev_r",
        "min_edge_after_cost_r",
        "news_confidence_nudge_pct",
        "strategy_profile",
        "risk_tier_mode",
        "risk_base_pct",
        "risk_recovery_pct",
        "risk_drawdown_pct",
        "risk_proven_pct",
        "risk_recovery_drawdown_pct",
        "risk_drawdown_trigger_pct",
        "risk_proven_min_trades",
        "risk_proven_min_expectancy_r",
        "risk_proven_min_net_r_after_cost",
        "risk_proven_min_profit_factor",
        "risk_proven_max_drawdown_pct",
        "risk_proven_min_symbols",
        "risk_proven_max_top_coin_pct",
        "risk_proven_min_days",
        "risk_proven_min_trades_per_leg",
        "risk_recovery_loss_streak_trigger",
        "reentry_max_trades_per_symbol_per_day",
        "reentry_min_ev_multiplier",
        "coin_digest_hour_ph",
        "news_enabled",
        "news_provider",
        "telegram_show_close_lessons",
        "dynamic_market_scan",
        "market_scan_top_n",
        "market_scan_active_symbols",
        "market_scan_min_quote_volume",
        "market_scan_max_spread_pct",
        "market_scan_refresh_minutes",
        "market_scan_exclude_symbols",
        "market_scan_include_fixed_majors",
        "market_scan_fixed_majors",
        "market_scan_require_market_cap_rank",
        "market_scan_min_market_cap_rank",
        "market_scan_use_mainnet_liquidity",
        "market_scan_max_abs_24h_change_pct",
        "market_scan_news_nudge_enabled",
        "market_scan_news_nudge_weight",
        "enable_partial_take_profit",
        "partial_take_profit_pct",
        "partial_take_profit_r",
        "enable_trailing_take_profit",
        "trail_activation_r",
        "trail_atr_mult",
        "trail_high_vol_atr_ratio",
        "trail_chandelier_lookback",
        "trail_chandelier_atr_mult",
        "trail_structure_lookback",
        "trail_min_move_pct",
        "tp_trail_activation_r",
        "tp_trail_min_locked_r",
        "tp_trail_min_ev_r",
    }

    def __getattribute__(self, name: str):
        if name not in {"_runtime_override_fields", "_load_runtime_overrides", "runtime_snapshot", "__dict__", "__class__"}:
            try:
                override_fields = object.__getattribute__(self, "_runtime_override_fields")
                if name in override_fields:
                    overrides = object.__getattribute__(self, "_load_runtime_overrides")()
                    if name in overrides:
                        return overrides[name]
            except Exception:
                pass
        return object.__getattribute__(self, name)

    def _load_runtime_overrides(self) -> dict[str, object]:
        path = _RUNTIME_SETTINGS_PATH
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            with _RUNTIME_SETTINGS_LOCK:
                _RUNTIME_SETTINGS_CACHE["mtime"] = None
                _RUNTIME_SETTINGS_CACHE["values"] = {}
            return {}

        with _RUNTIME_SETTINGS_LOCK:
            if _RUNTIME_SETTINGS_CACHE["mtime"] == mtime:
                return dict(_RUNTIME_SETTINGS_CACHE["values"])
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                values = payload.get("values", payload) if isinstance(payload, dict) else {}
                if not isinstance(values, dict):
                    values = {}
            except Exception:
                values = {}
            _RUNTIME_SETTINGS_CACHE["mtime"] = mtime
            _RUNTIME_SETTINGS_CACHE["values"] = dict(values)
            return dict(values)

    def runtime_snapshot(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in sorted(self._runtime_override_fields)}


settings = Settings()


def save_runtime_overrides(values: dict[str, object]) -> None:
    clean = {k: v for k, v in values.items() if k in settings._runtime_override_fields}
    payload = {
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "values": clean,
    }
    _RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _RUNTIME_SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(_RUNTIME_SETTINGS_PATH)
    with _RUNTIME_SETTINGS_LOCK:
        _RUNTIME_SETTINGS_CACHE["mtime"] = None
        _RUNTIME_SETTINGS_CACHE["values"] = dict(clean)


def load_runtime_overrides() -> dict[str, object]:
    return settings._load_runtime_overrides()
