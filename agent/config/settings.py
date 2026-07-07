import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


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

    bankroll_usdt: float = float(os.getenv("BANKROLL_USDT", "1000"))
    bankroll_mode: str = os.getenv("BANKROLL_MODE", "static").lower()  # static | equity
    bankroll_compounding: bool = os.getenv("BANKROLL_COMPOUNDING", "false").lower() == "true"
    bankroll_min_usdt: float = float(os.getenv("BANKROLL_MIN_USDT", "50"))
    bankroll_max_usdt: float = float(os.getenv("BANKROLL_MAX_USDT", "0"))  # 0 = no explicit cap
    bankroll_sync_interval_sec: int = int(os.getenv("BANKROLL_SYNC_INTERVAL_SEC", "900"))

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
    risk_proven_min_expectancy_r: float = float(os.getenv("RISK_PROVEN_MIN_EXPECTANCY_R", "0.15"))
    risk_proven_min_profit_factor: float = float(os.getenv("RISK_PROVEN_MIN_PROFIT_FACTOR", "1.3"))
    risk_proven_max_drawdown_pct: float = float(os.getenv("RISK_PROVEN_MAX_DRAWDOWN_PCT", "8.0"))
    risk_proven_min_symbols: int = int(os.getenv("RISK_PROVEN_MIN_SYMBOLS", "3"))

    reentry_max_trades_per_symbol_per_day: int = int(os.getenv("REENTRY_MAX_TRADES_PER_SYMBOL_PER_DAY", "3"))
    reentry_min_ev_multiplier: float = float(os.getenv("REENTRY_MIN_EV_MULTIPLIER", "1.5"))

    # Deprecated: CryptoPanic's free tier was discontinued/paywalled. Left
    # here only so an old .env with this var set doesn't break; unused by
    # agent.fundamental.news_sentiment, which now uses cryptocurrency.cv.
    cryptopanic_api_key: str = os.getenv("CRYPTOPANIC_API_KEY", "")
    coin_digest_hour_ph: int = int(os.getenv("COIN_DIGEST_HOUR_PH", "21"))  # 9 PM PHT ≈ start of a 9-5 Eastern workday

    # Free, no-auth news context (cryptocurrency.cv) — display/sentiment-nudge
    # only, never a trading signal on its own. Degrades to "no data" on any
    # failure; trading is never blocked by this.
    news_enabled: bool = os.getenv("NEWS_ENABLED", "true").lower() == "true"
    news_provider: str = os.getenv("NEWS_PROVIDER", "cryptocurrency_cv")
    news_api_url: str = os.getenv("NEWS_API_URL", "https://cryptocurrency.cv/api/news")
    news_timeout_sec: int = int(os.getenv("NEWS_TIMEOUT_SEC", "8"))
    news_max_headlines: int = int(os.getenv("NEWS_MAX_HEADLINES", "5"))

    # Dynamic two-stage market scanner (agent/adapt/roster.py). Stage 1 is one
    # cheap fetch_tickers() call across the whole exchange; only the top N
    # shortlisted symbols get the full indicator/MTF/EV stack (stage 2).
    dynamic_market_scan: bool = os.getenv("DYNAMIC_MARKET_SCAN", "true").lower() == "true"
    market_scan_top_n: int = int(os.getenv("MARKET_SCAN_TOP_N", "30"))
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

    # Extra cost/edge gates layered on top of MIN_EDGE_AFTER_COST_R — these
    # add rejection criteria only, they never change position size.
    max_estimated_cost_r: float = float(os.getenv("MAX_ESTIMATED_COST_R", "0.20"))
    min_net_ev_after_cost_r: float = float(os.getenv("MIN_NET_EV_AFTER_COST_R", "0.25"))
    min_expected_reward_cost_multiple: float = float(os.getenv("MIN_EXPECTED_REWARD_COST_MULTIPLE", "5"))


settings = Settings()
