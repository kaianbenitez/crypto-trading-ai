"""Smoke script for the dynamic two-stage market scanner
(agent/adapt/roster.py). Run directly: `python3 tests/smoke_market_scan.py`.

Verifies:
- stablecoin/leveraged-token/excluded-symbol/index-product filtering
- market-cap-rank filtering (and graceful degradation when unavailable)
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
    settings.market_scan_require_market_cap_rank = True
    # This file tests the filter/rank logic itself, independent of liquidity
    # source — mainnet-liquidity sourcing has its own dedicated smoke test
    # (smoke_market_scan_mainnet_liquidity.py) with a mocked fetch, so this
    # never needs a live network call.
    settings.market_scan_use_mainnet_liquidity = False

    tickers = {
        "BTC/USDT:USDT": _ticker(500_000_000, last=60000, pct=1.0),
        "ETH/USDT:USDT": _ticker(300_000_000, last=3000, pct=2.0),
        "SOL/USDT:USDT": _ticker(200_000_000, last=150, pct=5.0),
        "AVAX/USDT:USDT": _ticker(150_000_000, last=20, pct=3.0),
        "DOGE/USDT:USDT": _ticker(100_000_000, last=0.1, pct=1.0),
        # Should be filtered out:
        "USDC/USDT:USDT": _ticker(900_000_000, last=1.0, pct=0.0),          # stablecoin base
        "BTCUP/USDT:USDT": _ticker(50_000_000, last=1.0, pct=0.0),          # leveraged token marker
        "BTCDOM/USDT:USDT": _ticker(300_000_000, last=1000, pct=0.0),       # synthetic index/dominance product
        "MANUALEXCLUDE/USDT:USDT": _ticker(999_000_000, last=1.0, pct=0.0),  # explicit exclude list
        "TINY/USDT:USDT": _ticker(1_000_000, last=1.0, pct=0.0),            # below min volume
        "BTC/USD:USD": _ticker(999_000_000, last=60000, pct=0.0),           # not a USDT perp
        "WIDE/USDT:USDT": {"quoteVolume": 200_000_000, "last": 1.0, "percentage": 0.0, "bid": 1.0, "ask": 1.2},  # ~18% spread
        "MICROCAP/USDT:USDT": _ticker(60_000_000, last=1.0, pct=0.0),       # clears volume but not top market cap
    }

    # Mock the market-cap filter so the smoke test doesn't make a live network
    # call — includes the legit candidates above, excludes MICROCAP (and
    # naturally BTCDOM/BTCUP/etc, which aren't real CoinGecko-listed coins,
    # though those are caught earlier by their own dedicated filters anyway).
    original_get_market_cap = roster_mod.get_top_market_cap_symbols
    roster_mod.get_top_market_cap_symbols = lambda force=False: {"BTC", "ETH", "SOL", "AVAX", "DOGE"}

    try:
        # --- 1. Filtering: stablecoin/leveraged/index/excluded/low-volume/non-USDT/wide-spread/market-cap all rejected ---
        adapter = FakeAdapter(tickers)
        selected, meta = discover_market_universe(adapter)
        check("USDC excluded as a stablecoin", "USDC/USDT" not in selected)
        check("BTCUP excluded as a leveraged token", "BTCUP/USDT" not in selected)
        check("BTCDOM excluded as a synthetic index product", "BTCDOM/USDT" not in selected)
        check("MANUALEXCLUDE excluded via config list", "MANUALEXCLUDE/USDT" not in selected)
        check("TINY excluded for low volume", "TINY/USDT" not in selected)
        check("BTC/USD (non-USDT-perp) excluded", "BTC/USD" not in selected)
        check("WIDE excluded for spread too wide", "WIDE/USDT" not in selected)
        check("MICROCAP excluded for failing the market-cap rank filter", "MICROCAP/USDT" not in selected)
        check("index_product rejection reason recorded", meta["rejected"]["index_product"] >= 1)
        check("not_top_market_cap rejection reason recorded", meta["rejected"]["not_top_market_cap"] >= 1)
        check("Rejection reasons recorded", sum(meta["rejected"].values()) >= 7)

        # --- 2. Fixed majors always included regardless of ranking ---
        check("BTC/USDT included (fixed major)", "BTC/USDT" in selected)
        check("ETH/USDT included (fixed major)", "ETH/USDT" in selected)

        # --- 3. Top-N limiting: with top_n=3 and 2 fixed majors, only 1 more slot from ranking ---
        non_major_selected = [s for s in selected if s not in ("BTC/USDT", "ETH/USDT")]
        check(f"Only top_n-worth of ranked candidates beyond majors (got {len(non_major_selected)})", len(non_major_selected) <= settings.market_scan_top_n)

        # --- 4. Market-cap filter unavailable -> degrades to volume-only, doesn't reject everything ---
        roster_mod.get_top_market_cap_symbols = lambda force=False: None
        selected_no_capfilter, meta_no_capfilter = discover_market_universe(adapter)
        check("Degrades gracefully when market-cap data unavailable (still selects real coins)", "BTC/USDT" in selected_no_capfilter)
        check("MICROCAP now passes when market-cap filter is unavailable (volume-only fallback)", "MICROCAP/USDT" in selected_no_capfilter or meta_no_capfilter["rejected"]["not_top_market_cap"] == 0)
        check("BTCDOM still excluded even without market-cap data (denylist is independent)", "BTCDOM/USDT" not in selected_no_capfilter)
    finally:
        roster_mod.get_top_market_cap_symbols = original_get_market_cap

    # --- 5. Fallback: adapter failure must not raise out of CoinRoster ---
    failing_adapter = FakeAdapter(raise_error=True)
    session = get_session("sqlite:///:memory:")
    roster_obj = roster_mod.CoinRoster(session, failing_adapter)
    pool = roster_obj.candidate_pool()
    check("Fallback pool equals fixed CANDIDATE_SYMBOLS on scan failure", pool == CANDIDATE_SYMBOLS)
    status = roster_obj.scan_status()
    check("Scan status reports error, not a crash", status.get("status") == "error")
    session.close()

    # --- 6. Disabled scanner also falls back cleanly ---
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
