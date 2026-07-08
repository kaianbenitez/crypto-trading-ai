"""Coin roster manager — self-aware symbol selection.

Two layers work together:

1. Dynamic market scanner (stage 1, cheap): one fetch_all_tickers() call
   across the whole exchange, filtered (stablecoins/leveraged tokens/
   synthetic index-dominance products/excluded symbols/min volume/max
   spread/market-cap rank/abnormal 24h moves) and ranked (volume + momentum),
   kept to the top N. This replaces the old fixed CANDIDATE_SYMBOLS list as
   the source of *candidates* — it does not run any indicators/MTF/signal
   logic itself. Falls back to CANDIDATE_SYMBOLS if disabled, if the adapter
   doesn't support it, or if the scan fails for any reason. The market-cap
   filter (CoinGecko, free/no-key, top MARKET_SCAN_MIN_MARKET_CAP_RANK coins)
   keeps micro-caps and index products like BTCDOM out even when they clear
   the volume floor; it degrades to volume-only filtering if unavailable.

   Liquidity/ranking data source vs tradability (MARKET_SCAN_USE_MAINNET_LIQUIDITY):
   candidates are always enumerated from the exchange the bot actually trades
   on (so nothing gets shortlisted that can't be executed), but on Binance
   TESTNET the ticker volume/spread there is inflated/artificial — good
   enough to prove execution works, useless for judging whether a coin is
   genuinely liquid. When this flag is on (default) and running Binance
   testnet, the quote volume/bid-ask spread/24h % change used to filter and
   rank each candidate are instead read from Binance's real MAINNET public
   tickers (see fetch_mainnet_liquidity_tickers — no API keys, read-only,
   never touches order placement). A symbol only earns a shortlist slot if
   it would look liquid on the real market, not just on testnet. Falls back
   to the adapter's own ticker data (with a clear log line) if the mainnet
   fetch fails for any reason. On mainnet-live trading this is a no-op (the
   adapter's own tickers already are the real data).

   Abnormal-move filter (MARKET_SCAN_MAX_ABS_24H_CHANGE_PCT, default 35%):
   rejects symbols whose 24h % change exceeds this magnitude, applied BEFORE
   ranking. A coin that just moved -50%/+70% on news is not a good candidate
   for this bot's trend/mean-reversion baseline regardless of its liquidity.

   Symbol denylist (MARKET_SCAN_EXCLUDE_SYMBOLS): comma-separated list of
   exact "BASE/USDT" symbols, matched case-insensitively — works for any
   symbol (e.g. "SUN/USDT,GWEI/USDT,M/USDT"), no special-casing needed.

   Single-letter-base filter (MARKET_SCAN_EXCLUDE_SINGLE_LETTER_BASES,
   default off): optionally reject symbols whose base is a single letter
   (e.g. "M/USDT"). Off by default — not inherently bad, just available.

2. Existing roster/bench logic (stage 2 gate, unchanged): every 24h, checks
   volume for active coins (drops illiquid), reviews win rate, benches on
   3+ consecutive losses, promotes benched coins back after cooldown. Only
   symbols that make it through both layers ever reach the full indicator/
   SMC/MTF/EV/risk-admission stack in the orchestrator.

Hard limits:
  - Max MARKET_SCAN_ACTIVE_SYMBOLS active symbols at once (defaults to
    MARKET_SCAN_TOP_N, currently 30)
  - Min $50M 24h volume to be eligible (stage 2 recheck; stage 1 has its own
    configurable floor via MARKET_SCAN_MIN_QUOTE_VOLUME, judged against
    mainnet liquidity data when testnet — see above)
  - Benched coin must wait MIN_BENCH_HOURS before re-evaluation
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

import requests

from agent.config.settings import settings

log = logging.getLogger(__name__)

# Fallback candidate symbols — used when the dynamic scanner is disabled,
# unsupported by the active adapter, or fails for any reason.
CANDIDATE_SYMBOLS = [
    # Tier 1
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "ADA/USDT",
    # Tier 2
    "BNB/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
    "POL/USDT", "LTC/USDT", "UNI/USDT", "ATOM/USDT", "FIL/USDT",
]

MAX_ACTIVE = max(1, settings.market_scan_active_symbols)
MIN_VOLUME_USD = 50_000_000   # $50M 24h volume minimum
CONSECUTIVE_LOSS_BENCH = 3    # bench after this many consecutive losses
MIN_BENCH_HOURS = 48          # cooldown before re-evaluation
MIN_TRADES_TO_EVALUATE = 5    # don't bench/promote without enough data

_STABLE_BASES = {
    "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PYUSD", "USTC",
    "EUR", "GBP", "GUSD", "USDD",
}
_LEVERAGED_MARKERS = ("UP", "DOWN", "BULL", "BEAR")

# Defense-in-depth: known synthetic index/dominance products that trade as
# regular-looking perpetuals but aren't real coins (e.g. BTCDOM tracks BTC's
# share of total crypto market cap, not BTC itself). The market-cap filter
# below already excludes these naturally (CoinGecko doesn't list them as
# coins), but this denylist still applies even if that filter is disabled or
# its API call fails, since these should never be traded by a per-coin
# momentum/mean-reversion strategy regardless.
_INDEX_PRODUCT_MARKERS = ("DOM",)
_INDEX_PRODUCT_DENYLIST = {"BTCDOM", "ETHDOM", "DEFI", "ALTS", "TOTAL", "ALT"}

# Module-level cache for the CoinGecko top-market-cap symbol set — market cap
# ranking changes slowly, so this is refreshed on its own (long) cadence
# independent of the ticker scan, and shared across CoinRoster instances.
_market_cap_symbols: set[str] | None = None
_market_cap_fetched_at: datetime | None = None


def _normalize_futures_symbol(raw_symbol: str) -> str:
    """ccxt unified futures symbols look like 'BTC/USDT:USDT' — strip the
    settlement suffix to match this project's 'BTC/USDT' convention."""
    return raw_symbol.split(":", 1)[0]


# Standalone, keyless ccxt client for Binance's MAINNET public futures
# tickers — used ONLY to source scanner liquidity/spread/ranking data when
# running on testnet (whose ticker volume is inflated/artificial). This never
# touches execution: it has no API keys, places no orders, and is entirely
# separate from the adapter used for trading. Built lazily and cached at
# module level since constructing a ccxt client has a small fixed cost and
# the scanner only runs a handful of times per hour.
_mainnet_ticker_client = None


def _get_mainnet_ticker_client():
    global _mainnet_ticker_client
    if _mainnet_ticker_client is None:
        import ccxt
        # No apiKey/secret — fetch_tickers() is public market data, and
        # omitting keys guarantees this client can never place an order.
        _mainnet_ticker_client = ccxt.binanceusdm({
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {"fetchCurrencies": False},
        })
    return _mainnet_ticker_client


def fetch_mainnet_liquidity_tickers() -> dict | None:
    """Binance mainnet USDT-M perpetual tickers (quote volume, bid/ask,
    24h % change), independent of whatever exchange/testnet the trading
    adapter is configured for. Returns None on any failure so callers can
    fall back to the adapter's own tickers."""
    try:
        client = _get_mainnet_ticker_client()
        tickers = client.fetch_tickers()
        if not tickers:
            return None
        return tickers
    except Exception as e:
        log.warning(f"Mainnet liquidity ticker fetch failed, will fall back to adapter tickers: {e}")
        return None


def _is_index_product(base: str) -> bool:
    if base in _INDEX_PRODUCT_DENYLIST:
        return True
    return any(base.endswith(marker) for marker in _INDEX_PRODUCT_MARKERS)


def get_top_market_cap_symbols(force: bool = False) -> set[str] | None:
    """Fetches the top MARKET_SCAN_MIN_MARKET_CAP_RANK coins by market cap
    from CoinGecko's free public API (no key required) and returns their
    uppercased symbols. Cached for MARKET_SCAN_MARKET_CAP_REFRESH_HOURS.
    Returns None (not an empty set) on any failure — callers must treat that
    as "skip this filter", not "nothing passes"."""
    global _market_cap_symbols, _market_cap_fetched_at

    now = datetime.now(timezone.utc)
    stale = (
        _market_cap_fetched_at is None
        or (now - _market_cap_fetched_at).total_seconds() >= settings.market_scan_market_cap_refresh_hours * 3600
    )
    if _market_cap_symbols is not None and not stale and not force:
        return _market_cap_symbols

    try:
        per_page = min(max(settings.market_scan_min_market_cap_rank, 1), 250)
        resp = requests.get(
            settings.market_scan_market_cap_api_url,
            params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": per_page, "page": 1},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        symbols = {str(r["symbol"]).upper() for r in rows if r.get("symbol")}
        if not symbols:
            raise ValueError("empty market cap response")
        _market_cap_symbols = symbols
        _market_cap_fetched_at = now
        log.info(f"Market-cap filter refreshed: top {len(symbols)} coins by market cap")
        return symbols
    except Exception as e:
        log.warning(f"Market-cap fetch failed, skipping that filter this cycle: {e}")
        return _market_cap_symbols  # serve the last good cache if we have one, else None


def discover_market_universe(adapter, session=None) -> tuple[list[str], dict]:
    """Stage 1 of the two-stage scanner: one cheap fetch_tickers() call
    across the exchange, filtered and ranked. Returns (selected_symbols, meta)
    where meta carries counts/reject-reasons for logging and API exposure.

    `session`, when provided and MARKET_SCAN_NEWS_NUDGE_ENABLED is on, is used
    to apply a small news-sentiment nudge to each candidate's score — see the
    scoring block below. Optional and no-op by default: existing callers that
    don't pass a session (or run with the flag off) are unaffected.

    Raises on any hard failure (network, adapter doesn't support it, etc.) —
    callers are expected to catch and fall back to CANDIDATE_SYMBOLS.

    Liquidity/ranking data source (quality_score inputs: quote volume, bid/ask
    spread, 24h % change) is decoupled from tradability. Candidates are always
    enumerated from the ADAPTER's tickers (i.e. only symbols actually tradable
    on the configured — possibly testnet — exchange), so execution is never
    affected. But when running on Binance testnet, whose ticker volume is
    inflated/artificial, the *numbers* used to filter/rank each candidate are
    sourced from Binance's real MAINNET public tickers instead (see
    fetch_mainnet_liquidity_tickers) — a symbol only earns a shortlist slot if
    it looks like a real, liquid market, not a testnet volume artifact. Falls
    back to the adapter's own ticker data if the mainnet fetch fails.
    """
    tickers = adapter.fetch_all_tickers()
    if not tickers:
        raise RuntimeError("fetch_all_tickers returned no data")

    liquidity_source = "adapter"
    liquidity_tickers = tickers
    use_mainnet = (
        settings.market_scan_use_mainnet_liquidity
        and settings.exchange == "binance"
        and settings.binance_testnet
    )
    if use_mainnet:
        mainnet_tickers = fetch_mainnet_liquidity_tickers()
        if mainnet_tickers:
            liquidity_tickers = mainnet_tickers
            liquidity_source = "mainnet_public"
            log.info(
                f"Market scan: sourcing liquidity/ranking from Binance MAINNET public "
                f"tickers ({len(mainnet_tickers)} symbols) — execution stays on testnet"
            )
        else:
            log.warning(
                "Market scan: mainnet liquidity fetch failed this cycle — "
                "falling back to the adapter's own (testnet) ticker data"
            )

    liquidity_by_symbol: dict[str, dict] = {
        _normalize_futures_symbol(raw): t for raw, t in liquidity_tickers.items()
    }

    exclude = {s.strip().upper() for s in settings.market_scan_exclude_symbols.split(",") if s.strip()}
    market_cap_symbols = (
        get_top_market_cap_symbols() if settings.market_scan_require_market_cap_rank else None
    )
    if settings.market_scan_require_market_cap_rank and market_cap_symbols is None:
        log.warning("Market-cap filter enabled but unavailable this cycle — falling back to volume-only filtering")

    rejected = {
        "not_usdt_perp": 0, "stablecoin": 0, "leveraged": 0, "index_product": 0,
        "excluded": 0, "single_letter_base": 0, "not_top_market_cap": 0,
        "low_volume": 0, "wide_spread": 0, "abnormal_move": 0, "bad_data": 0,
    }

    candidates = []
    # Enumerate TRADABLE symbols (the adapter's own tickers) so nothing gets
    # shortlisted that the configured exchange can't actually execute — only
    # the quality numbers below come from the liquidity source.
    for raw_symbol in tickers:
        symbol = _normalize_futures_symbol(raw_symbol)
        if "/" not in symbol or not symbol.endswith("/USDT"):
            rejected["not_usdt_perp"] += 1
            continue

        base = symbol.split("/")[0]
        if base in _STABLE_BASES:
            rejected["stablecoin"] += 1
            continue
        if any(marker in base for marker in _LEVERAGED_MARKERS):
            rejected["leveraged"] += 1
            continue
        if _is_index_product(base):
            rejected["index_product"] += 1
            continue
        if symbol.upper() in exclude:
            rejected["excluded"] += 1
            continue
        if settings.market_scan_exclude_single_letter_bases and len(base) == 1:
            rejected["single_letter_base"] += 1
            continue
        if market_cap_symbols is not None and base not in market_cap_symbols:
            rejected["not_top_market_cap"] += 1
            continue

        # Quality data for this symbol: from the liquidity source if it has a
        # counterpart there (e.g. real mainnet data), else rejected outright —
        # a symbol with no real-market counterpart can't be judged as liquid.
        quality_ticker = liquidity_by_symbol.get(symbol)
        if quality_ticker is None:
            rejected["bad_data"] += 1
            continue

        quote_volume = quality_ticker.get("quoteVolume")
        last_price = quality_ticker.get("last") or quality_ticker.get("close")
        if not quote_volume or not last_price or float(last_price) <= 0:
            rejected["bad_data"] += 1
            continue
        quote_volume = float(quote_volume)
        if quote_volume < settings.market_scan_min_quote_volume:
            rejected["low_volume"] += 1
            continue

        bid, ask = quality_ticker.get("bid"), quality_ticker.get("ask")
        spread_pct = None
        if bid and ask and bid > 0:
            spread_pct = (float(ask) - float(bid)) / ((float(ask) + float(bid)) / 2) * 100
            if spread_pct > settings.market_scan_max_spread_pct:
                rejected["wide_spread"] += 1
                continue

        pct_change_raw = quality_ticker.get("percentage")
        pct_change = float(pct_change_raw) if pct_change_raw is not None else 0.0
        # Abnormal event-driven moves rejected BEFORE ranking — not
        # representative of this bot's trend/mean-reversion baseline,
        # regardless of how liquid the symbol otherwise is.
        if abs(pct_change) > settings.market_scan_max_abs_24h_change_pct:
            rejected["abnormal_move"] += 1
            continue

        candidates.append({
            "symbol": symbol,
            "quote_volume": quote_volume,
            "pct_change": pct_change,
            "spread_pct": spread_pct,
        })

    news_nudge_by_symbol: dict[str, float] = {}
    if candidates and settings.market_scan_news_nudge_enabled and session is not None:
        # Small nudge from whatever's already cached by the rolling news
        # refresh (agent/fundamental/news_refresh.py) — no extra API calls
        # here, just a read of data that's already being kept fresh for the
        # confidence-adjustment path. Unlike that path (which only affects
        # trades already selected), this changes which coins even become
        # candidates, so it's symmetric and small by design (±weight, default
        # ±0.05) rather than a hard include/exclude — a coin isn't blocked
        # from the shortlist over news, just nudged relative to its peers.
        from agent.fundamental.coin_digest import cached_sentiment

        for c in candidates:
            try:
                sentiment = cached_sentiment(session, c["symbol"])
                if sentiment.label not in (None, "no data"):
                    news_nudge_by_symbol[c["symbol"]] = sentiment.score * settings.market_scan_news_nudge_weight
            except Exception as e:
                log.warning(f"[{c['symbol']}] Cached sentiment read failed for scan nudge: {e}")

    if candidates:
        max_vol = max(c["quote_volume"] for c in candidates) or 1.0
        for c in candidates:
            vol_score = c["quote_volume"] / max_vol
            # Momentum is a tiebreaker/boost, not the primary sort key —
            # liquidity is the real gate, a volatile illiquid coin is still
            # a bad candidate. Abnormal movers are already excluded above,
            # so this only ranks ordinary/healthy momentum among survivors.
            momentum_score = min(abs(c["pct_change"]) / 20.0, 1.0)
            base_score = vol_score * 0.8 + momentum_score * 0.2
            c["score"] = round(base_score + news_nudge_by_symbol.get(c["symbol"], 0.0), 4)
        candidates.sort(key=lambda c: c["score"], reverse=True)

    selected_candidates = candidates[: settings.market_scan_top_n]
    selected = [c["symbol"] for c in selected_candidates]

    if settings.market_scan_include_fixed_majors:
        majors = [m.strip() for m in settings.market_scan_fixed_majors.split(",") if m.strip()]
        selected = majors + [s for s in selected if s not in majors]

    meta = {
        "scanned": len(tickers),
        "eligible": len(candidates),
        "selected_count": len(selected),
        "active_limit": MAX_ACTIVE,
        "liquidity_source": liquidity_source,
        "rejected": rejected,
        "selected_detail": selected_candidates,  # [{symbol, quote_volume, pct_change, spread_pct, score}]
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
    log.info(
        f"Market scan ({liquidity_source}): {len(tickers)} tickers -> {len(candidates)} eligible -> "
        f"{len(selected)} selected | rejected: {rejected}"
    )
    log.info(f"Market scan selected: {', '.join(selected[:15])}{' ...' if len(selected) > 15 else ''}")
    return selected, meta


class CoinRoster:
    """Tracks active/benched symbols and self-adjusts based on performance."""

    def __init__(self, session, adapter=None):
        self.session  = session
        self.adapter  = adapter
        self._scan_cache: list[str] | None = None
        self._scan_cache_at: datetime | None = None
        self._scan_meta: dict = {
            "enabled": settings.dynamic_market_scan,
            "status": "not_run_yet",
            "last_scan_at": None,
        }
        self._load()

    # ------------------------------------------------------------------
    # Dynamic market scan (stage 1) — candidate SOURCE, not a signal gate
    # ------------------------------------------------------------------

    def refresh_market_scan(self, force: bool = False, session=None) -> list[str] | None:
        """Refreshes the cached dynamic universe if the refresh interval has
        elapsed (or force=True). Returns the cached/new universe, or None if
        the scan is disabled/unsupported/failed — callers should fall back
        to CANDIDATE_SYMBOLS in that case.

        `session` is optional and only used to apply the news-sentiment scan
        nudge (see discover_market_universe) when that flag is enabled."""
        if not settings.dynamic_market_scan or self.adapter is None:
            self._scan_meta = {"enabled": False, "status": "disabled", "last_scan_at": None}
            return None

        now = datetime.now(timezone.utc)
        stale = (
            self._scan_cache_at is None
            or (now - self._scan_cache_at).total_seconds() >= settings.market_scan_refresh_minutes * 60
        )
        if self._scan_cache is not None and not stale and not force:
            return self._scan_cache

        try:
            universe, meta = discover_market_universe(self.adapter, session=session)
        except Exception as e:
            log.warning(f"Dynamic market scan failed, falling back to fixed roster: {e}")
            self._scan_meta = {
                "enabled": True, "status": "error", "error": str(e),
                "last_scan_at": now.isoformat(),
            }
            return self._scan_cache  # keep serving the last good scan if we have one

        if not universe:
            self._scan_meta = {"enabled": True, "status": "empty", "last_scan_at": now.isoformat()}
            self._persist_scan_status()
            return self._scan_cache

        self._scan_cache = universe
        self._scan_cache_at = now
        self._scan_meta = {"enabled": True, "status": "ok", **meta, "selected": universe}
        self._persist_scan_status()
        return universe

    def _persist_scan_status(self) -> None:
        """Persists scan status to the DB so the separate webapi process can
        expose it via /api/roster — the live CoinRoster instance only exists
        in the trading-agent process's memory."""
        from agent.db.models import RosterState
        try:
            record = self.session.query(RosterState).first()
            if not record:
                record = RosterState(active_symbols=json.dumps(self.active if hasattr(self, "active") else []),
                                      benched_symbols=json.dumps(self.benched if hasattr(self, "benched") else {}))
                self.session.add(record)
            record.scan_status = json.dumps(self._scan_meta, default=str)
            self.session.commit()
        except Exception as e:
            log.warning(f"Failed to persist scan status: {e}")

    def candidate_pool(self) -> list[str]:
        """The list new roster slots get filled from — the dynamic scan
        result when available, else the fixed fallback list."""
        pool = self.refresh_market_scan()
        return pool if pool else CANDIDATE_SYMBOLS

    def scan_status(self) -> dict:
        """Compact status for API/dashboard exposure."""
        return dict(self._scan_meta)

    def _fill_candidate_slots(self) -> bool:
        pool = self.candidate_pool()
        if settings.dynamic_market_scan and self._scan_meta.get("status") == "ok" and pool:
            target = [s for s in pool if s not in self.benched][:MAX_ACTIVE]
            if target != self.active:
                old_count = len(self.active)
                self.active = target
                log.info(
                    "Active roster synced to dynamic shortlist: "
                    f"{old_count} -> {len(self.active)} symbols"
                )
                return True
            return False

        changed = False
        for symbol in pool:
            if len(self.active) >= MAX_ACTIVE:
                break
            if symbol not in self.active and symbol not in self.benched:
                self.active.append(symbol)
                changed = True
        return changed

    def _load(self):
        """Load roster state from DB."""
        from agent.db.models import RosterState
        record = self.session.query(RosterState).first()
        if record:
            self.active  = json.loads(record.active_symbols)
            self.benched = json.loads(record.benched_symbols)  # {symbol: bench_until_iso}
            self.last_review = record.last_review
            if self._fill_candidate_slots():
                self._save()
        else:
            # Bootstrap: keep the full configured candidate roster active.
            self.active  = self.candidate_pool()[:MAX_ACTIVE]
            self.benched = {}
            self.last_review = None
            self._save()

    def _save(self):
        from agent.db.models import RosterState
        record = self.session.query(RosterState).first()
        if not record:
            record = RosterState()
            self.session.add(record)
        record.active_symbols  = json.dumps(self.active)
        record.benched_symbols = json.dumps(self.benched)
        record.last_review     = datetime.now(timezone.utc)
        self.session.commit()

    # ------------------------------------------------------------------
    # Called after every closed trade
    # ------------------------------------------------------------------

    def record_trade(self, symbol: str, outcome: str) -> str | None:
        """Update consecutive loss counter. Returns bench reason if benched."""
        from agent.db.models import Trade
        if symbol not in self.active:
            return None

        # Count consecutive losses (most recent trades first)
        recent = (
            self.session.query(Trade)
            .filter(Trade.symbol == symbol, Trade.closed_at.isnot(None))
            .order_by(Trade.closed_at.desc())
            .limit(CONSECUTIVE_LOSS_BENCH + 2)
            .all()
        )

        if len(recent) < MIN_TRADES_TO_EVALUATE:
            return None

        consecutive_losses = 0
        for t in recent:
            if t.outcome == "loss":
                consecutive_losses += 1
            else:
                break

        if consecutive_losses >= CONSECUTIVE_LOSS_BENCH:
            return self._bench(symbol, f"{consecutive_losses} consecutive losses")

        return None

    def _bench(self, symbol: str, reason: str) -> str:
        """Move symbol to benched list."""
        if symbol in self.active:
            self.active.remove(symbol)
        until = (datetime.now(timezone.utc) + timedelta(hours=MIN_BENCH_HOURS)).isoformat()
        self.benched[symbol] = until
        self._save()
        msg = f"🚫 {symbol} benched for {MIN_BENCH_HOURS}h — {reason}"
        log.info(msg)
        return msg

    # ------------------------------------------------------------------
    # Daily review (call once per day from orchestrator)
    # ------------------------------------------------------------------

    def daily_review(self, tg_fn=None) -> list[str]:
        """Full daily roster review. Returns list of status messages."""
        messages = []

        # 0. Refresh the dynamic market scan (forced, once a day minimum)
        self.refresh_market_scan(force=True)
        if self._fill_candidate_slots():
            messages.append(
                f"Active roster synced to dynamic shortlist ({len(self.active)}/{MAX_ACTIVE})"
            )

        # 1. Unbenched coins whose cooldown expired
        now = datetime.now(timezone.utc)
        to_unban = [
            s for s, until_iso in self.benched.items()
            if datetime.fromisoformat(until_iso) <= now
        ]
        for symbol in to_unban:
            del self.benched[symbol]
            if len(self.active) < MAX_ACTIVE and symbol not in self.active:
                self.active.append(symbol)
                msg = f"✅ {symbol} reinstated after cooldown"
                log.info(msg)
                messages.append(msg)

        # 2. Volume filter — drop illiquid symbols if adapter available
        if self.adapter:
            for symbol in list(self.active):
                try:
                    ticker = self.adapter._client.fetch_ticker(symbol)
                    vol_usd = float(ticker.get("quoteVolume") or 0)
                    if vol_usd < MIN_VOLUME_USD:
                        msg = self._bench(symbol, f"24h volume ${vol_usd/1e6:.1f}M < ${MIN_VOLUME_USD/1e6:.0f}M minimum")
                        messages.append(msg)
                except Exception as e:
                    log.warning(f"Volume check failed for {symbol}: {e}")

        # 3. Performance review — bench underperformers
        cutoff = now - timedelta(days=14)
        from agent.db.models import Trade
        for symbol in list(self.active):
            recent = (
                self.session.query(Trade)
                .filter(
                    Trade.symbol == symbol,
                    Trade.closed_at >= cutoff,
                    Trade.closed_at.isnot(None),
                )
                .all()
            )
            if len(recent) < MIN_TRADES_TO_EVALUATE:
                continue
            wins = sum(1 for t in recent if t.outcome == "win")
            wr = wins / len(recent)
            total_pnl = sum(t.pnl_usdt or 0 for t in recent)

            if wr < 0.30 and total_pnl < 0:
                msg = self._bench(
                    symbol,
                    f"14d WR {wr:.0%} + PnL {total_pnl:+.2f} USDT below threshold"
                )
                messages.append(msg)
            else:
                msg = f"📊 {symbol}: {wr:.0%} WR | {total_pnl:+.2f} USDT (14d, {len(recent)} trades)"
                messages.append(msg)

        # 4. Promote candidates if slots available
        if len(self.active) < MAX_ACTIVE:
            for symbol in self.candidate_pool():
                if symbol not in self.active and symbol not in self.benched:
                    if len(self.active) < MAX_ACTIVE:
                        self.active.append(symbol)
                        msg = f"➕ {symbol} added to active roster (slot available)"
                        log.info(msg)
                        messages.append(msg)

        self._save()

        # 5. Send digest
        digest = (
            f"🤖 Daily Roster Review\n"
            f"Active ({len(self.active)}): {', '.join(self.active)}\n"
            f"Benched ({len(self.benched)}): {', '.join(self.benched.keys()) or 'none'}\n"
        )
        if messages:
            digest += "\n" + "\n".join(messages)

        log.info(digest)

        return messages

    def get_active(self) -> list[str]:
        return list(self.active)
