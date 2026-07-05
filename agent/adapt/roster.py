"""Coin roster manager — self-aware symbol selection.

Two layers work together:

1. Dynamic market scanner (stage 1, cheap): one fetch_all_tickers() call
   across the whole exchange, filtered (stablecoins/leveraged tokens/excluded
   symbols/min volume/max spread) and ranked (volume + momentum), kept to the
   top N. This replaces the old fixed CANDIDATE_SYMBOLS list as the source of
   *candidates* — it does not run any indicators/MTF/signal logic itself.
   Falls back to CANDIDATE_SYMBOLS if disabled, if the adapter doesn't
   support it, or if the scan fails for any reason.

2. Existing roster/bench logic (stage 2 gate, unchanged): every 24h, checks
   volume for active coins (drops illiquid), reviews win rate, benches on
   3+ consecutive losses, promotes benched coins back after cooldown. Only
   symbols that make it through both layers ever reach the full indicator/
   SMC/MTF/EV/risk-admission stack in the orchestrator.

Hard limits:
  - Max 15 active symbols at once
  - Min $50M 24h volume to be eligible (stage 2 recheck; stage 1 has its own
    configurable floor via MARKET_SCAN_MIN_QUOTE_VOLUME)
  - Benched coin must wait MIN_BENCH_HOURS before re-evaluation
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

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

MAX_ACTIVE = 15
MIN_VOLUME_USD = 50_000_000   # $50M 24h volume minimum
CONSECUTIVE_LOSS_BENCH = 3    # bench after this many consecutive losses
MIN_BENCH_HOURS = 48          # cooldown before re-evaluation
MIN_TRADES_TO_EVALUATE = 5    # don't bench/promote without enough data

_STABLE_BASES = {
    "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PYUSD", "USTC",
    "EUR", "GBP", "GUSD", "USDD",
}
_LEVERAGED_MARKERS = ("UP", "DOWN", "BULL", "BEAR")


def _normalize_futures_symbol(raw_symbol: str) -> str:
    """ccxt unified futures symbols look like 'BTC/USDT:USDT' — strip the
    settlement suffix to match this project's 'BTC/USDT' convention."""
    return raw_symbol.split(":", 1)[0]


def discover_market_universe(adapter) -> tuple[list[str], dict]:
    """Stage 1 of the two-stage scanner: one cheap fetch_tickers() call
    across the exchange, filtered and ranked. Returns (selected_symbols, meta)
    where meta carries counts/reject-reasons for logging and API exposure.

    Raises on any hard failure (network, adapter doesn't support it, etc.) —
    callers are expected to catch and fall back to CANDIDATE_SYMBOLS.
    """
    tickers = adapter.fetch_all_tickers()
    if not tickers:
        raise RuntimeError("fetch_all_tickers returned no data")

    exclude = {s.strip().upper() for s in settings.market_scan_exclude_symbols.split(",") if s.strip()}
    rejected = {
        "not_usdt_perp": 0, "stablecoin": 0, "leveraged": 0,
        "excluded": 0, "low_volume": 0, "wide_spread": 0, "bad_data": 0,
    }

    candidates = []
    for raw_symbol, ticker in tickers.items():
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
        if symbol.upper() in exclude:
            rejected["excluded"] += 1
            continue

        quote_volume = ticker.get("quoteVolume")
        last_price = ticker.get("last") or ticker.get("close")
        if not quote_volume or not last_price or float(last_price) <= 0:
            rejected["bad_data"] += 1
            continue
        quote_volume = float(quote_volume)
        if quote_volume < settings.market_scan_min_quote_volume:
            rejected["low_volume"] += 1
            continue

        bid, ask = ticker.get("bid"), ticker.get("ask")
        spread_pct = None
        if bid and ask and bid > 0:
            spread_pct = (float(ask) - float(bid)) / ((float(ask) + float(bid)) / 2) * 100
            if spread_pct > settings.market_scan_max_spread_pct:
                rejected["wide_spread"] += 1
                continue

        pct_change = ticker.get("percentage")
        candidates.append({
            "symbol": symbol,
            "quote_volume": quote_volume,
            "pct_change": float(pct_change) if pct_change is not None else 0.0,
            "spread_pct": spread_pct,
        })

    if candidates:
        max_vol = max(c["quote_volume"] for c in candidates) or 1.0
        for c in candidates:
            vol_score = c["quote_volume"] / max_vol
            # Momentum is a tiebreaker/boost, not the primary sort key —
            # liquidity is the real gate, a volatile illiquid coin is still
            # a bad candidate.
            momentum_score = min(abs(c["pct_change"]) / 20.0, 1.0)
            c["score"] = vol_score * 0.8 + momentum_score * 0.2
        candidates.sort(key=lambda c: c["score"], reverse=True)

    selected = [c["symbol"] for c in candidates[: settings.market_scan_top_n]]

    if settings.market_scan_include_fixed_majors:
        majors = [m.strip() for m in settings.market_scan_fixed_majors.split(",") if m.strip()]
        selected = majors + [s for s in selected if s not in majors]

    meta = {
        "scanned": len(tickers),
        "eligible": len(candidates),
        "selected_count": len(selected),
        "rejected": rejected,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
    log.info(
        f"Market scan: {len(tickers)} tickers -> {len(candidates)} eligible -> "
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

    def refresh_market_scan(self, force: bool = False) -> list[str] | None:
        """Refreshes the cached dynamic universe if the refresh interval has
        elapsed (or force=True). Returns the cached/new universe, or None if
        the scan is disabled/unsupported/failed — callers should fall back
        to CANDIDATE_SYMBOLS in that case."""
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
            universe, meta = discover_market_universe(self.adapter)
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
        changed = False
        pool = self.candidate_pool()
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
