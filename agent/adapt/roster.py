"""Coin roster manager — self-aware symbol selection.

Maintains a dynamic list of active trading symbols. Every 24h:
  - Checks 24h volume for all candidate coins (drops illiquid)
  - Reviews per-symbol win rate from last 14 days
  - Benches coins on 3+ consecutive losses
  - Promotes benched coins back after a cooldown period
  - Reports status via Telegram digest

Hard limits:
  - Max 15 active symbols at once
  - Min $50M 24h volume to be eligible
  - Benched coin must wait MIN_BENCH_HOURS before re-evaluation
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

# All candidate symbols to consider
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


class CoinRoster:
    """Tracks active/benched symbols and self-adjusts based on performance."""

    def __init__(self, session, adapter=None):
        self.session  = session
        self.adapter  = adapter
        self._load()

    def _fill_candidate_slots(self) -> bool:
        changed = False
        for symbol in CANDIDATE_SYMBOLS:
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
            self.active  = CANDIDATE_SYMBOLS[:MAX_ACTIVE]
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
            for symbol in CANDIDATE_SYMBOLS:
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
