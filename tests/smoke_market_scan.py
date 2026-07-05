"""Smoke script for the dynamic two-stage market scanner
(agent/adapt/roster.py). Run directly: `python3 tests/smoke_market_scan.py`.

Verifies:
- stablecoin/leveraged-token/excluded-symbol filtering
- top-N limiting
- fixed-majors are always included
- fallback to the fixed CANDIDATE_SYMBOLS list when fetch_all_tickers fails
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.config.settings import settings  # noqa: E402
from agent.adapt import roster as roster_mod  # noqa: E402
from agent.adapt.roster import CANDIDATE_SYMBOLS, discover_market_universe  # noqa: E402
from agent.db.models import get_session  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def _ticker(quote_volume, last=1.0, pct=0.0, bid=None, ask=None):
    t = {"quoteVolume": quote_volume, "last": last, "percentage": pct}
    if bid is not None:
        t["bid"] = bid
    if ask is not None:
        t["ask"] = ask
    return t


class FakeAdapter:
    def __init__(self, tickers=None, raise_error=False):
        self._tickers = tickers or {}
        self._raise_error = raise_error

    def fetch_all_tickers(self):
        if self._raise_error:
            raise ConnectionError("simulated exchange outage")
        return self._tickers


def main():
    # Use generous thresholds so the fake fixtures below are realistic.
    settings.market_scan_min_quote_volume = 10_000_000
    settings.market_scan_max_spread_pct = 0.5
    settings.market_scan_top_n = 3
    settings.market_scan_include_fixed_majors = True
    settings.market_scan_fixed_majors = "BTC/USDT,ETH/USDT"
    settings.market_scan_exclude_symbols = "MANUALEXCLUDE/USDT"

    tickers = {
        "BTC/USDT:USDT": _ticker(500_000_000, last=60000, pct=1.0),
        "ETH/USDT:USDT": _ticker(300_000_000, last=3000, pct=2.0),
        "SOL/USDT:USDT": _ticker(200_000_000, last=150, pct=5.0),
        "AVAX/USDT:USDT": _ticker(150_000_000, last=20, pct=3.0),
        "DOGE/USDT:USDT": _ticker(100_000_000, last=0.1, pct=1.0),
        # Should be filtered out:
        "USDC/USDT:USDT": _ticker(900_000_000, last=1.0, pct=0.0),          # stablecoin base
        "BTCUP/USDT:USDT": _ticker(50_000_000, last=1.0, pct=0.0),          # leveraged token marker
        "MANUALEXCLUDE/USDT:USDT": _ticker(999_000_000, last=1.0, pct=0.0),  # explicit exclude list
        "TINY/USDT:USDT": _ticker(1_000_000, last=1.0, pct=0.0),            # below min volume
        "BTC/USD:USD": _ticker(999_000_000, last=60000, pct=0.0),           # not a USDT perp
        "WIDE/USDT:USDT": {"quoteVolume": 200_000_000, "last": 1.0, "percentage": 0.0, "bid": 1.0, "ask": 1.2},  # ~18% spread
    }

    # --- 1. Filtering: stablecoin/leveraged/excluded/low-volume/non-USDT/wide-spread all rejected ---
    adapter = FakeAdapter(tickers)
    selected, meta = discover_market_universe(adapter)
    check("USDC excluded as a stablecoin", "USDC/USDT" not in selected)
    check("BTCUP excluded as a leveraged token", "BTCUP/USDT" not in selected)
    check("MANUALEXCLUDE excluded via config list", "MANUALEXCLUDE/USDT" not in selected)
    check("TINY excluded for low volume", "TINY/USDT" not in selected)
    check("BTC/USD (non-USDT-perp) excluded", "BTC/USD" not in selected)
    check("WIDE excluded for spread too wide", "WIDE/USDT" not in selected)
    check("Rejection reasons recorded", sum(meta["rejected"].values()) >= 5)

    # --- 2. Fixed majors always included regardless of ranking ---
    check("BTC/USDT included (fixed major)", "BTC/USDT" in selected)
    check("ETH/USDT included (fixed major)", "ETH/USDT" in selected)

    # --- 3. Top-N limiting: with top_n=3 and 2 fixed majors, only 1 more slot from ranking ---
    non_major_selected = [s for s in selected if s not in ("BTC/USDT", "ETH/USDT")]
    check(f"Only top_n-worth of ranked candidates beyond majors (got {len(non_major_selected)})", len(non_major_selected) <= settings.market_scan_top_n)

    # --- 4. Fallback: adapter failure must not raise out of CoinRoster ---
    failing_adapter = FakeAdapter(raise_error=True)
    session = get_session("sqlite:///:memory:")
    roster_obj = roster_mod.CoinRoster(session, failing_adapter)
    pool = roster_obj.candidate_pool()
    check("Fallback pool equals fixed CANDIDATE_SYMBOLS on scan failure", pool == CANDIDATE_SYMBOLS)
    status = roster_obj.scan_status()
    check("Scan status reports error, not a crash", status.get("status") == "error")
    session.close()

    # --- 5. Disabled scanner also falls back cleanly ---
    settings.dynamic_market_scan = False
    session2 = get_session("sqlite:///:memory:")
    roster_disabled = roster_mod.CoinRoster(session2, FakeAdapter(tickers))
    pool2 = roster_disabled.candidate_pool()
    check("Disabled scanner falls back to fixed list", pool2 == CANDIDATE_SYMBOLS)
    settings.dynamic_market_scan = True
    session2.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
